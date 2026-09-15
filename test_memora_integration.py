import asyncio
import json
import logging
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Memora"))
import db
import selene_gateway as gateway
import memora_server as memora
import selene_rest as rest
import selene_server

logging.getLogger("httpx").setLevel(logging.WARNING)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(db, "DB_PATH", str(Path(self.temp.name) / "selene.db")),
                        patch.object(memora, "DB_PATH", str(Path(self.temp.name) / "brain.db")),
                        patch.object(memora, "_get_embedding", return_value=None),
                        patch.object(memora, "_extract_tags", return_value="")]
        for item in self.patches:
            item.start()
        db.init_db()
        memora.init_db()
        memora._ensure_columns()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def incoming(self, content, value="2026-09-11", **kwargs):
        return json.loads(asyncio.run(memora.memora_record(content, type="feel", event_date=value, **kwargs)))

    async def outbound(self, content, importance=3, mem_type="fact", event_date="", source_key=""):
        return json.loads(await memora.memora_record(content, importance=importance, type=mem_type,
                                                    event_date=event_date, source="selene", source_key=source_key))

    def count_memories(self):
        conn = memora.get_db()
        try:
            return conn.execute("SELECT count(*) FROM memories").fetchone()[0]
        finally:
            conn.close()

    def test_manual_mood_survives_and_symptoms_merge(self):
        db.set_mood(22, 8, "2026-09-11")
        db.set_symptoms(22, ["腹痛"], "2026-09-11")
        result = self.incoming("心情低落，还头疼")
        self.assertEqual(db.get_mood_log()["2026-09-11"], 8)
        self.assertIn("腹痛", db.get_symptom_log()["2026-09-11"])
        self.assertIn("头疼", db.get_symptom_log()["2026-09-11"])
        self.assertIn("mood", result["selene_sync"]["protected"])
        sources = rest.get_logs()["logSources"]["2026-09-11"]
        self.assertEqual(sources["mood"]["source"], "manual")
        self.assertEqual(sources["symptoms"]["memory_id"], result["id"])

    def test_negations_and_ambiguous_emotions(self):
        self.incoming("今天不开心，没有头疼")
        self.assertEqual(db.get_mood_log()["2026-09-11"], 3)
        self.assertEqual(db.get_symptom_log(), {})
        self.incoming("不焦虑，也不难过，头疼好了", "2026-09-12")
        self.assertNotIn("2026-09-12", db.get_mood_log())
        self.assertNotIn("2026-09-12", db.get_symptom_log())
        self.incoming("开心又难过", "2026-09-13")
        self.assertNotIn("2026-09-13", db.get_mood_log())

    def test_historical_date_and_no_period_are_supported(self):
        db.add_period("2026-08-21", "2026-08-26")
        db.add_period("2026-09-18", "2026-09-23")
        result = self.incoming("开心", "2026-08-21")
        self.assertEqual(result["selene_sync"]["day"], 1)
        self.incoming("开心", "2026-01-01")
        self.assertEqual(db.get_day_log("2026-01-01")["day"], 0)
        invalid = self.incoming("开心", "bad-date")
        self.assertEqual(invalid["selene_sync"]["reason"], "invalid_event_date")
        self.assertNotIn(date.today().isoformat(), db.get_mood_log())

    def test_duplicates_do_not_undo_manual_edits(self):
        result = self.incoming("开心头疼")
        db.set_mood(0, 4, "2026-09-11")
        db.set_symptoms(0, [], "2026-09-11")
        duplicate = gateway._auto_sync_from_feel("开心头疼", "2026-09-11", memory_id=result["id"])
        self.assertTrue(duplicate["duplicate"])
        self.incoming("头疼", "2026-09-11")
        self.assertEqual(db.get_mood_log()["2026-09-11"], 4)
        self.assertEqual(db.get_symptom_log()["2026-09-11"], [])

    def test_round_trip_care_preserves_score_and_filters_custom_symptoms(self):
        db.set_mood(0, 4, "2026-09-11")
        db.set_symptoms(0, ["头疼", "custom private text"], "2026-09-11")
        with patch.object(rest.memora_client, "record", side_effect=self.outbound), \
                patch.object(rest.memora_client, "recall", new_callable=AsyncMock, return_value={"results": []}):
            for _ in range(2):
                result = asyncio.run(rest.care_low_mood(rest.CareBody(day=0, score=4, date="2026-09-11")))
                self.assertTrue(result["memora_ok"])
        self.assertEqual(self.count_memories(), 1)
        self.assertEqual(db.get_mood_log()["2026-09-11"], 4)
        conn = memora.get_db()
        try:
            content = conn.execute("SELECT content FROM memories").fetchone()[0]
            self.assertNotIn("custom private text", content)
            self.assertIn("头疼", content)
        finally:
            conn.close()

    def test_failed_daily_attempt_is_retried_without_duplicate_memory(self):
        db.set_mood(0, 8, "2026-09-11")
        attempts = []

        async def timeout_once(*args, **kwargs):
            result = await self.outbound(*args, **kwargs)
            attempts.append(result)
            return None if len(attempts) == 1 else result

        with patch.object(rest, "datetime") as clock, patch.object(rest.memora_client, "record", side_effect=timeout_once):
            clock.now.return_value = datetime(2026, 9, 11, 21)
            asyncio.run(rest._maybe_feed_daily())
            self.assertFalse(db.has_feed("2026-09-11", "day"))
            clock.now.return_value = datetime(2026, 9, 12, 10)
            asyncio.run(rest._maybe_feed_daily())
            asyncio.run(rest._maybe_feed_daily())
        self.assertEqual(len(attempts), 2)
        self.assertEqual(self.count_memories(), 1)
        self.assertTrue(db.has_feed("2026-09-11", "day"))

    def test_monthly_uses_previous_month_and_recovers_after_schedule(self):
        db.set_mood(0, 8, "2025-12-31")
        with patch.object(rest, "datetime") as clock, patch.object(rest.memora_client, "record", side_effect=self.outbound) as record:
            clock.now.return_value = datetime(2026, 1, 2, 10)
            asyncio.run(rest._maybe_feed_monthly())
            asyncio.run(rest._maybe_feed_monthly())
        self.assertEqual(record.await_count, 1)
        self.assertEqual(record.call_args.kwargs["event_date"], "2025-12-01")
        self.assertEqual(db.get_config("last_report_month"), "2025-12")

    def test_gateway_matches_standalone(self):
        class Registry:
            def __init__(self):
                self.tools = {}
            def tool(self):
                def register(fn):
                    self.tools[fn.__name__] = fn
                    return fn
                return register
        registered = Registry()
        gateway.mount(registered)
        db.set_cycle_config(35, "2026-08-21", "2026-08-26")
        with patch("cycle.date") as clock, patch.object(selene_server.prompts, "get_reminder", return_value="fixed"):
            clock.today.return_value = date(2026, 9, 11)
            clock.fromisoformat.side_effect = date.fromisoformat
            standalone = json.loads(asyncio.run(selene_server.selene_status()))
            bridged = json.loads(asyncio.run(registered.tools["selene_status"]()))
        self.assertEqual(standalone, bridged)
        self.assertEqual(bridged["phase"], "ovulation")
        self.assertEqual(bridged["cycle_length"], 35)

    def test_deploy_still_serves_frontend(self):
        from fastapi.testclient import TestClient
        import selene_rest_deploy
        client = TestClient(selene_rest_deploy.app)
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/selene_browser.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()
