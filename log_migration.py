"""Lossless migration from cycle-day keys to calendar-date keys."""

from collections import Counter
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
import sqlite3
from uuid import uuid4


def valid_date(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        pending = []
        for table, column, kind in (("mood_log", "score", "INTEGER"),
                                    ("symptom_log", "symptoms", "TEXT")):
            info = conn.execute(f"PRAGMA table_info({table})").fetchall()
            if info and not any(r["name"] == "date" and r["pk"] for r in info):
                pending.append((table, column, kind))
        if not pending:
            conn.commit()
            return None

        # A separate reader can back up the committed database while this
        # connection holds the write reservation, preventing concurrent writes.
        folder = Path(db_path).resolve().parent / "backups"
        folder.mkdir(exist_ok=True)
        backup = folder / f"{Path(db_path).stem}-before-date-logs-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.db"
        with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Log migration backup integrity check failed")

        for table, column, kind in pending:
            # Keep the complete original table, including undated/conflicting
            # rows, rather than inventing dates or choosing a conflict winner.
            archive = f"{table}_legacy_by_day"
            conn.execute(f"ALTER TABLE {table} RENAME TO {archive}")
            conn.execute(f"CREATE TABLE {table} (date TEXT PRIMARY KEY NOT NULL, day INTEGER, {column} {kind})")
            rows = [dict(r) for r in conn.execute(f"SELECT * FROM {archive}")]
            counts = Counter(r.get("date") for r in rows if valid_date(r.get("date")))
            accepted = [r for r in rows if valid_date(r.get("date")) and counts[r["date"]] == 1]
            conn.executemany(f"INSERT INTO {table} (date,day,{column}) VALUES (?,?,?)",
                             [(r["date"], r.get("day"), r.get(column)) for r in accepted])
        conn.commit()
        return str(backup)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
