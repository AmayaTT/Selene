import asyncio
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import db
import reminder
import selene_server
import selene_rest


class StatusSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = patch.object(db, "DB_PATH", str(Path(self.temp.name) / "test.db"))
        self.path.start()
        db.init_db()

    def tearDown(self):
        self.path.stop()
        self.temp.cleanup()

    def test_latest_twelve_in_ascending_order(self):
        starts = [(date(2025, 1, 1) + timedelta(days=28*i)).isoformat() for i in range(13)]
        for start in starts:
            db.add_period(start)
        self.assertEqual([p["start_date"] for p in db.get_periods()], starts[1:])
        self.assertEqual(db.get_periods(1)[0]["start_date"], starts[-1])

    def test_web_save_updates_mcp_without_duplicates(self):
        ident = db.add_period("2026-08-21", pain=3, note="preserve")
        body = selene_rest.ConfigBody(cycleLength=28, periodStart="2026-08-21", periodEnd="2026-08-26")
        for _ in range(2):
            response = selene_rest.save_config(body)
        self.assertEqual(len(db.get_periods()), 1)
        self.assertEqual(db.get_period_by_id(ident)["note"], "preserve")
        self.assertEqual(response["phaseByDay"]["22"], "luteal")
        with patch("cycle.date") as clock:
            clock.today.return_value = date(2026, 9, 11)
            clock.fromisoformat.side_effect = date.fromisoformat
            result = json.loads(asyncio.run(selene_server.selene_status()))
        self.assertEqual((result["phase"], result["days_left"]), ("luteal", 7))
        db.update_period(ident, end_date="2026-08-23")
        self.assertEqual(db.get_cycle_config()["periodEnd"], "2026-08-23")

    def test_new_cycle_preserves_history_and_custom_length(self):
        db.set_cycle_config(35, "2026-07-17", "2026-07-22")
        db.set_cycle_config(35, "2026-08-21", "2026-08-26")
        self.assertEqual(len(db.get_periods()), 2)
        state = db.current_cycle_status(date(2026, 9, 11))
        self.assertEqual((state["phase"], state["days_left"]), ("ovulation", 14))
        self.assertEqual(db.get_cycle_config()["phaseByDay"]["22"], state["phase"])

    def test_due_reminder_without_new_period(self):
        db.set_cycle_config(28, "2026-08-21", "2026-08-26")
        for today in (date(2026, 9, 18), date(2026, 9, 19), date(2026, 11, 1)):
            self.assertEqual(reminder.decide_reminder(today)["phase"], "due_check")
        db.add_period("2026-09-18", "2026-09-23")
        self.assertEqual(reminder.decide_reminder(date(2026, 9, 19))["phase"], "menstrual")

    def test_migration_once_and_no_resurrection(self):
        db.set_config("period_start", "2026-08-21")
        db.set_config("period_end", "2026-08-26")
        db.migrate_cycle_config()
        db.migrate_cycle_config()
        self.assertEqual(len(db.get_periods()), 1)
        db.delete_period(db.get_periods()[0]["id"])
        db.migrate_cycle_config()
        self.assertEqual(db.get_cycle_config()["periodStart"], "")

    def test_invalid_config_does_not_write(self):
        with self.assertRaises(ValueError):
            db.set_cycle_config(28, "2026-08-21", "2026-08-20")
        self.assertEqual(db.get_periods(), [])


if __name__ == "__main__":
    unittest.main()
