"""Provenance and atomic incoming Memora synchronization."""

import json


def init_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS log_sources (
            kind TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL,
            memory_id INTEGER, PRIMARY KEY(kind, date)
        );
        CREATE TABLE IF NOT EXISTS memora_sync_events (
            event_key TEXT PRIMARY KEY, memory_id INTEGER, date TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
    """)


def mark_source(conn, kind, value, source, memory_id=None):
    conn.execute("INSERT INTO log_sources(kind,date,source,memory_id) VALUES (?,?,?,?) "
                 "ON CONFLICT(kind,date) DO UPDATE SET source=excluded.source,memory_id=excluded.memory_id",
                 (kind, value, source, memory_id))


def apply_event(value, day, score, symptoms, memory_id, event_key):
    import db
    conn = db.get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute("SELECT result FROM memora_sync_events WHERE event_key=?", (event_key,)).fetchone()
        if previous:
            return {**json.loads(previous["result"]), "duplicate": True}
        written = {}
        protected = []
        if score is not None:
            existing = conn.execute("SELECT score FROM mood_log WHERE date=?", (value,)).fetchone()
            origin = conn.execute("SELECT source,memory_id FROM log_sources WHERE kind='mood' AND date=?", (value,)).fetchone()
            if existing and (not origin or origin["source"] != "memora"):
                protected.append("mood")
            elif existing and memory_id and origin["memory_id"] and memory_id < origin["memory_id"]:
                protected.append("newer_mood")
            else:
                conn.execute("INSERT INTO mood_log(date,day,score) VALUES (?,?,?) "
                             "ON CONFLICT(date) DO UPDATE SET day=excluded.day,score=excluded.score", (value, day, score))
                mark_source(conn, "mood", value, "memora", memory_id)
                written["mood"] = {"date": value, "day": day, "score": score}
        if symptoms:
            existing = conn.execute("SELECT symptoms FROM symptom_log WHERE date=?", (value,)).fetchone()
            origin = conn.execute("SELECT source FROM log_sources WHERE kind='symptoms' AND date=?", (value,)).fetchone()
            old = json.loads(existing["symptoms"] or "[]") if existing else []
            manual = existing and (not origin or origin["source"] != "memora")
            if manual and (not old or "状态良好" in old):
                protected.append("symptoms")
            else:
                merged = list(dict.fromkeys(old + symptoms))
                if "状态良好" in merged and len(merged) > 1:
                    merged.remove("状态良好")
                conn.execute("INSERT INTO symptom_log(date,day,symptoms) VALUES (?,?,?) "
                             "ON CONFLICT(date) DO UPDATE SET day=excluded.day,symptoms=excluded.symptoms",
                             (value, day, json.dumps(merged, ensure_ascii=False)))
                mark_source(conn, "symptoms", value, "mixed" if manual else "memora", memory_id)
                written["symptoms"] = {"date": value, "day": day, "list": merged}
        result = {"synced": bool(written), "date": value, "day": day, "written": written,
                  "protected": protected, "memory_id": memory_id,
                  "summary": value + " " + ", ".join(written)}
        conn.execute("INSERT INTO memora_sync_events(event_key,memory_id,date,result) VALUES (?,?,?,?)",
                     (event_key, memory_id, value, json.dumps(result, ensure_ascii=False)))
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_sources():
    import db
    conn = db.get_db()
    try:
        result = {}
        for row in conn.execute("SELECT * FROM log_sources"):
            result.setdefault(row["date"], {})[row["kind"]] = {"source": row["source"], "memory_id": row["memory_id"]}
        return result
    finally:
        conn.close()
