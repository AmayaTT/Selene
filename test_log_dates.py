import shutil
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import db
import log_migration
import report_builder
import selene_rest


@contextmanager
def connection(path):
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


class LogDateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "selene.db"
        self.override = patch.object(db, "DB_PATH", str(self.path))
        self.override.start()

    def tearDown(self):
        self.override.stop()
        self.temp.cleanup()

    def legacy(self, dates=True):
        with connection(self.path) as conn:
            suffix = ", date TEXT" if dates else ""
            conn.execute(f"CREATE TABLE mood_log(day INTEGER PRIMARY KEY, score INTEGER{suffix})")
            conn.execute(f"CREATE TABLE symptom_log(day INTEGER PRIMARY KEY, symptoms TEXT{suffix})")

    def test_cross_cycle_and_date_specific_updates(self):
        db.init_db()
        db.add_period("2026-08-21", "2026-08-26")
        db.add_period("2026-09-18", "2026-09-23")
        client = TestClient(selene_rest.app)
        for value, score in (("2026-08-21", 2), ("2026-09-18", 8)):
            response = client.post("/log_mood", json={"day": 99, "date": value, "score": score})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["day"], 1)
            self.assertEqual(client.post("/log_symptoms", json={"day": 99, "date": value, "symptoms": [value]}).status_code, 200)
        client.post("/log_mood", json={"day": 1, "date": "2026-08-21", "score": 4})
        client.post("/log_symptoms", json={"day": 1, "date": "2026-08-21", "symptoms": ["changed"]})
        db.init_db()  # Repeated startup does not erase or remigrate records.
        logs = client.get("/get_logs").json()
        self.assertEqual(logs["moodLog"], {"2026-08-21": 4, "2026-09-18": 8})
        self.assertEqual(logs["symptomLog"], {"2026-08-21": ["changed"], "2026-09-18": ["2026-09-18"]})
        self.assertEqual(db.get_day_log("2026-09-18")["score"], 8)
        self.assertEqual(len(report_builder._fetch_month_moods("2026-08")), 1)
        self.assertEqual(len(report_builder._fetch_month_moods("2026-09")), 1)

    def test_migration_backup_conflicts_and_unknown_dates(self):
        self.legacy()
        with connection(self.path) as conn:
            conn.executemany("INSERT INTO mood_log VALUES (?,?,?)", [
                (1, 2, "2026-08-21"), (2, 4, ""), (3, 6, "2026-08-23"),
                (4, 8, "2026-08-23"), (5, 10, "2026-02-30"), (6, -1, None)])
            conn.execute("INSERT INTO symptom_log VALUES (1, '[\"original\"]', '2026-08-21')")
        backup = db._ensure_columns()
        self.assertTrue(Path(backup).exists())
        self.assertEqual(db.get_mood_log(), {"2026-08-21": 2})
        self.assertEqual(db.get_symptom_log(), {"2026-08-21": ["original"]})
        with connection(self.path) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM mood_log_legacy_by_day").fetchone()[0], 6)
        self.assertIsNone(db._ensure_columns())
        self.assertEqual(len(list((self.path.parent / "backups").glob("*.db"))), 1)
        restored = self.path.parent / "restored.db"
        shutil.copy2(backup, restored)
        with connection(restored) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM mood_log").fetchone()[0], 6)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        db.set_mood(1, 8, "2026-09-18")
        self.assertEqual(len(db.get_mood_log()), 2)

    def test_legacy_without_date_column_is_preserved(self):
        self.legacy(dates=False)
        with connection(self.path) as conn:
            conn.execute("INSERT INTO mood_log VALUES (1, 8)")
            conn.execute("INSERT INTO symptom_log VALUES (1, '[\"old\"]')")
        db.init_db()
        self.assertEqual(db.get_mood_log(), {})
        with connection(self.path) as conn:
            self.assertEqual(conn.execute("SELECT day,score FROM mood_log_legacy_by_day").fetchone(), (1, 8))

    def test_backup_failure_leaves_old_tables_untouched(self):
        self.legacy()
        with patch.object(log_migration.Path, "mkdir", side_effect=OSError("no space")):
            with self.assertRaises(OSError):
                db._ensure_columns()
        with connection(self.path) as conn:
            self.assertEqual(conn.execute("PRAGMA table_info(mood_log)").fetchall()[0][1], "day")

    def test_failure_mid_migration_rolls_back_both_tables(self):
        self.legacy()
        original_connect = sqlite3.connect

        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql.startswith("CREATE TABLE symptom_log "):
                    raise sqlite3.OperationalError("injected migration failure")
                return super().execute(sql, *args)

        def connect(*args, **kwargs):
            return original_connect(*args, factory=FailingConnection, **kwargs)

        with patch.object(log_migration.sqlite3, "connect", side_effect=connect):
            with self.assertRaises(sqlite3.OperationalError):
                db._ensure_columns()
        with connection(self.path) as conn:
            for table in ("mood_log", "symptom_log"):
                self.assertEqual(conn.execute(f"PRAGMA table_info({table})").fetchall()[0][1], "day")
                self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name=?", (table + "_legacy_by_day",)).fetchone())

    def test_invalid_dates_rejected_and_missing_date_defaults_to_today(self):
        db.init_db()
        client = TestClient(selene_rest.app)
        for route, fields in (("/log_mood", {"score": 8}), ("/log_symptoms", {"symptoms": []})):
            for value in ("2026-02-30", "20260911", "not-a-date"):
                self.assertEqual(client.post(route, json={"day": 1, "date": value, **fields}).status_code, 422)
        self.assertEqual(db.get_mood_log(), {})
        response = client.post("/log_mood", json={"day": 1, "score": 8})
        self.assertEqual(response.json()["date"], db.date.today().isoformat())


if __name__ == "__main__":
    unittest.main()
