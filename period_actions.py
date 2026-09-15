"""Transactional quick period actions with idempotent retries and guarded undo."""
import json
from datetime import date


class ActionConflict(ValueError):
    pass


def init_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS period_actions (
        request_id TEXT PRIMARY KEY, action TEXT NOT NULL, action_date TEXT NOT NULL,
        period_id INTEGER NOT NULL, before_json TEXT, after_json TEXT NOT NULL,
        changed INTEGER NOT NULL, undone INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")


def _row(conn, period_id):
    row = conn.execute("SELECT * FROM periods WHERE id=?", (period_id,)).fetchone()
    return dict(row) if row else None


def _snapshot(row):
    return json.dumps(row, sort_keys=True, ensure_ascii=False)


def apply(action, value, request_id, period_id=None, today=None):
    import db
    today = today or date.today()
    if not request_id or len(request_id) > 120:
        raise ValueError("操作标识无效，请刷新后重试")
    if not value:
        raise ValueError("请选择实际经期日期")
    value = db.normalize_log_date(value)
    if value > today.isoformat():
        raise ValueError("实际经期日期不能晚于今天")
    if action not in ("start", "end"):
        raise ValueError("不支持的经期操作")
    conn = db.get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute("SELECT * FROM period_actions WHERE request_id=?", (request_id,)).fetchone()
        if previous:
            if previous["action"] != action or previous["action_date"] != value or (action == "end" and previous["period_id"] != period_id):
                raise ActionConflict("这次操作的内容已改变，请重新提交")
            return {"success": True, "changed": bool(previous["changed"]), "undone": bool(previous["undone"]), "duplicate": True}
        if action == "start":
            found = conn.execute("SELECT id FROM periods WHERE start_date=? ORDER BY id DESC LIMIT 1", (value,)).fetchone()
            if found:
                period_id = found["id"]
                before = _row(conn, period_id)
            else:
                overlap = conn.execute("SELECT id FROM periods WHERE start_date<? AND end_date>=? LIMIT 1", (value, value)).fetchone()
                if overlap:
                    raise ValueError("该日期已在另一条经期记录中，请核对日期")
                before = None
                period_id = conn.execute("INSERT INTO periods(start_date,end_date) VALUES (?, '')", (value,)).lastrowid
        else:
            before = _row(conn, period_id)
            if not before:
                raise ActionConflict("经期记录已不存在，请刷新后重试")
            if value < before["start_date"]:
                raise ValueError("结束日期不能早于开始日期")
            following = conn.execute("SELECT start_date FROM periods WHERE start_date>? ORDER BY start_date LIMIT 1", (before["start_date"],)).fetchone()
            if following and value >= following["start_date"]:
                raise ValueError("结束日期不能覆盖下一轮经期，请核对日期")
            conn.execute("UPDATE periods SET end_date=? WHERE id=?", (value, period_id))
        after = _row(conn, period_id)
        changed = before != after
        conn.execute("INSERT INTO period_actions(request_id,action,action_date,period_id,before_json,after_json,changed) VALUES (?,?,?,?,?,?,?)",
                     (request_id, action, value, period_id, _snapshot(before), _snapshot(after), int(changed)))
        conn.commit()
        return {"success": True, "changed": changed, "undone": False, "duplicate": False}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def undo(request_id):
    import db
    conn = db.get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        entry = conn.execute("SELECT * FROM period_actions WHERE request_id=?", (request_id,)).fetchone()
        if not entry:
            raise ActionConflict("未找到可撤销的操作，请刷新后重试")
        if entry["undone"] or not entry["changed"]:
            return {"success": True, "changed": False, "undone": True}
        if _snapshot(_row(conn, entry["period_id"])) != entry["after_json"]:
            raise ActionConflict("这条记录已有后续修改，不能直接撤销，请刷新查看")
        before = json.loads(entry["before_json"])
        if before is None:
            conn.execute("DELETE FROM periods WHERE id=?", (entry["period_id"],))
        else:
            # Quick actions only change end_date on an existing record.
            conn.execute("UPDATE periods SET end_date=? WHERE id=?", (before["end_date"], entry["period_id"]))
        conn.execute("UPDATE period_actions SET undone=1 WHERE request_id=?", (request_id,))
        conn.commit()
        return {"success": True, "changed": True, "undone": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def latest_undo():
    import db
    conn = db.get_db()
    try:
        entry = conn.execute("SELECT * FROM period_actions WHERE undone=0 AND changed=1 ORDER BY rowid DESC LIMIT 1").fetchone()
        if not entry or _snapshot(_row(conn, entry["period_id"])) != entry["after_json"]:
            return None
        return {"request_id": entry["request_id"], "action": entry["action"], "date": entry["action_date"]}
    finally:
        conn.close()
