"""
Selene - 数据库模块
SQLite 本地存储，一张表存经期记录，一张表存用户配置。
另有两张表存每日情绪日志和症状日志（供前端持久化）。
"""

import json
import sqlite3
import os
from datetime import date

DB_PATH = os.path.join(os.path.dirname(__file__), "selene.db")

# 标准化症状词白名单（与前端 selene.jsx SYMPTOMS_LIST 一致）
# ★ 喂入 memora 的内容只放行这些词，自定义症状等敏感文本一律不进 memora
SYMPTOMS_LIST = ["头疼", "偏头痛", "头晕", "腰酸", "腿酸", "水肿", "乳房胀痛", "小腹坠痛", "痛经", "腹痛", "腹胀", "恶心", "腹泻", "便秘", "食欲旺盛", "食欲不振", "疲惫", "乏力", "失眠", "嗜睡", "长痘", "畏寒", "情绪波动", "易怒", "焦虑", "心情低落", "状态良好"]


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表。"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_date TEXT NOT NULL,
            end_date TEXT,
            flow INTEGER DEFAULT 2,        -- 1少 2中 3多
            pain INTEGER DEFAULT 0,        -- 0-3
            mood TEXT DEFAULT '',           -- 情绪标签，逗号分隔
            body_note TEXT DEFAULT '',      -- 身体感觉（胀、坠、分泌物等）
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS mood_log (
            day INTEGER PRIMARY KEY,
            score INTEGER
        );

        CREATE TABLE IF NOT EXISTS symptom_log (
            day INTEGER PRIMARY KEY,
            symptoms TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS care_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day INTEGER,
            date TEXT,
            score INTEGER,
            memory_id INTEGER,
            related_count INTEGER DEFAULT 0,
            memora_ok INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS feed_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            kind TEXT,               -- day=每日状态 / month=月度报告
            memory_id INTEGER,
            ok INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()
    conn.close()


def _ensure_columns():
    """安全迁移：给 mood_log / symptom_log 补 date 列（真实日期 YYYY-MM-DD）。"""
    conn = get_db()
    for table in ("mood_log", "symptom_log"):
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "date" not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN date TEXT DEFAULT ''")
    conn.commit()
    conn.close()


# ---- 经期记录 CRUD ----

def add_period(start_date: str, end_date: str = "", flow: int = 2,
               pain: int = 0, mood: str = "", body_note: str = "", note: str = "") -> int:
    """新增一条经期记录，返回记录 id。"""
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO periods (start_date, end_date, flow, pain, mood, body_note, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (start_date, end_date, flow, pain, mood, body_note, note)
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_periods(limit: int = 12) -> list[dict]:
    """获取最近的经期记录，按开始日期升序。"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM periods ORDER BY start_date ASC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_period_by_id(period_id: int) -> dict | None:
    """按ID获取单条记录。"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM periods WHERE id=?", (period_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_period(period_id: int, **kwargs) -> bool:
    """更新一条记录的部分字段。"""
    allowed = {"start_date", "end_date", "flow", "pain", "mood", "body_note", "note"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    conn = get_db()
    sets = ", ".join(f"{k}=?" for k in updates)
    conn.execute(
        f"UPDATE periods SET {sets} WHERE id=?",
        (*updates.values(), period_id)
    )
    conn.commit()
    conn.close()
    return True


def delete_period(period_id: int) -> bool:
    """删除一条经期记录。返回是否删除了记录。"""
    conn = get_db()
    cur = conn.execute("DELETE FROM periods WHERE id=?", (period_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def get_last_period() -> dict | None:
    """获取最近一次经期记录。"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM periods ORDER BY start_date DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ---- 配置 ----

def set_config(key: str, value: str):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()
    conn.close()


def get_config(key: str, default: str = "") -> str:
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM config WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


# ---- 情绪日志 ----

def get_mood_log() -> dict:
    """返回 { date: score }，只含已有真实日期的记录。"""
    conn = get_db()
    rows = conn.execute("SELECT date, score FROM mood_log WHERE date != ''").fetchall()
    conn.close()
    return {r["date"]: r["score"] for r in rows}


def set_mood(day: int, score: int, date: str = ""):
    """写入/覆盖某天的情绪分数。score=-1 表示'无感觉'。date 为真实日期 YYYY-MM-DD。"""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO mood_log (day, score, date) VALUES (?, ?, ?)",
        (day, score, date)
    )
    conn.commit()
    conn.close()


# ---- 症状日志 ----

def get_symptom_log() -> dict:
    """返回 { date: [症状数组] }，只含已有真实日期的记录。"""
    conn = get_db()
    rows = conn.execute("SELECT date, symptoms FROM symptom_log WHERE date != ''").fetchall()
    conn.close()
    result = {}
    for r in rows:
        try:
            result[r["date"]] = json.loads(r["symptoms"]) if r["symptoms"] else []
        except json.JSONDecodeError:
            result[r["date"]] = []
    return result


def set_symptoms(day: int, symptoms: list, date: str = ""):
    """写入/覆盖某天的症状数组。date 为真实日期 YYYY-MM-DD。"""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO symptom_log (day, symptoms, date) VALUES (?, ?, ?)",
        (day, json.dumps(symptoms, ensure_ascii=False), date)
    )
    conn.commit()
    conn.close()


# ---- 情绪关怀 / 互喂留痕 ----

def add_care_log(day: int, date: str, score: int, memory_id,
                 related_count: int, memora_ok: bool):
    """记录一次低情绪关怀联动结果（排查用）。"""
    conn = get_db()
    conn.execute(
        "INSERT INTO care_log (day, date, score, memory_id, related_count, memora_ok) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (day, date, score, memory_id, related_count, 1 if memora_ok else 0)
    )
    conn.commit()
    conn.close()


def add_feed_log(date: str, kind: str, memory_id, ok: bool):
    """记录一次喂数据动作（每日状态 / 月度报告），用于幂等去重。"""
    conn = get_db()
    conn.execute(
        "INSERT INTO feed_log (date, kind, memory_id, ok) VALUES (?, ?, ?, ?)",
        (date, kind, memory_id, 1 if ok else 0)
    )
    conn.commit()
    conn.close()


def has_feed(date: str, kind: str) -> bool:
    """判断某天某类喂数据是否已执行过。"""
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM feed_log WHERE date=? AND kind=?", (date, kind)
    ).fetchone()
    conn.close()
    return row is not None


def get_day_log(date: str) -> dict:
    """取某真实日期当天的记录。返回 {day, score, symptoms}，无记录返回空 dict。"""
    conn = get_db()
    mood = conn.execute(
        "SELECT day, score FROM mood_log WHERE date=?", (date,)
    ).fetchone()
    sym = conn.execute(
        "SELECT day, symptoms FROM symptom_log WHERE date=?", (date,)
    ).fetchone()
    conn.close()
    result = {}
    if mood:
        result["day"] = mood["day"]
        result["score"] = mood["score"]
    if sym:
        result.setdefault("day", sym["day"])
        try:
            result["symptoms"] = json.loads(sym["symptoms"]) if sym["symptoms"] else []
        except json.JSONDecodeError:
            result["symptoms"] = []
    return result


# ---- 周期设置（前端 MePage 用的配置） ----

def get_cycle_config() -> dict:
    return {
        "cycleLength": int(get_config("cycle_length", "28")),
        "periodStart": get_config("period_start", ""),
        "periodEnd": get_config("period_end", ""),
    }


def set_cycle_config(cycleLength: int, periodStart: str, periodEnd: str):
    set_config("cycle_length", str(cycleLength))
    set_config("period_start", periodStart)
    set_config("period_end", periodEnd)
