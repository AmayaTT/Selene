"""
Selene - 存储接口抽象层（万能数据库接口示例）

Selene 默认用本地 SQLite（db.py 直接操作 selene.db，零依赖）。
如果你想换成 MySQL / PostgreSQL / 其他数据库，不需要改业务逻辑——
只要实现本文件的 StorageInterface 抽象方法，再在启动时把全局 STORE 换成你的实现即可。

本文件提供：
  - StorageInterface ：抽象基类，列出业务需要的全部存储方法（契约）
  - SQLiteStorage    ：默认实现（内部直接复用 db.py，保持现有行为不变）
  - MySQLStorage     ：示例实现（用 pymysql，SQL 思路可直接套用）
  - PostgresStorage  ：示例实现（用 psycopg2，SQL 思路可直接套用）

如何切换：见 README 的「接入其他数据库」章节。
"""

import abc
from datetime import date


class StorageInterface(abc.ABC):
    """存储契约。业务层（cycle / reminder / selene_rest）只依赖这一层，
    不关心背后是 SQLite 还是 MySQL。"""

    # ---- 经期记录 ----
    @abc.abstractmethod
    def add_period(self, start_date: str, end_date: str, flow: int,
                   pain: int, mood: str, body_note: str, note: str) -> int: ...

    @abc.abstractmethod
    def get_periods(self, limit: int = 12) -> list[dict]: ...

    @abc.abstractmethod
    def get_period_by_id(self, period_id: int) -> dict | None: ...

    @abc.abstractmethod
    def update_period(self, period_id: int, **kwargs) -> bool: ...

    @abc.abstractmethod
    def delete_period(self, period_id: int) -> bool: ...

    @abc.abstractmethod
    def get_last_period(self) -> dict | None: ...

    # ---- 配置 ----
    @abc.abstractmethod
    def set_config(self, key: str, value: str): ...

    @abc.abstractmethod
    def get_config(self, key: str, default: str = "") -> str: ...

    # ---- 情绪 / 症状日志（按真实日期）----
    @abc.abstractmethod
    def set_mood(self, day: int, score: int, date: str = ""): ...

    @abc.abstractmethod
    def get_mood_log(self) -> dict: ...

    @abc.abstractmethod
    def set_symptoms(self, day: int, symptoms: list, date: str = ""): ...

    @abc.abstractmethod
    def get_symptom_log(self) -> dict: ...

    # ---- 关怀 / 互喂留痕 ----
    @abc.abstractmethod
    def add_care_log(self, day: int, date: str, score: int, memory_id,
                     related_count: int, memora_ok: bool): ...

    @abc.abstractmethod
    def add_feed_log(self, date: str, kind: str, memory_id, ok: bool): ...

    @abc.abstractmethod
    def has_feed(self, date: str, kind: str) -> bool: ...

    @abc.abstractmethod
    def get_day_log(self, date: str) -> dict: ...


# ======================================================================
#  默认实现：SQLite（零依赖，复用 db.py）
# ======================================================================

class SQLiteStorage(StorageInterface):
    """默认存储：直接走 db.py 的 SQLite 实现。行为与旧版完全一致。"""

    def add_period(self, start_date, end_date, flow, pain, mood, body_note, note):
        import db
        return db.add_period(start_date, end_date, flow, pain, mood, body_note, note)

    def get_periods(self, limit=12):
        import db
        return db.get_periods(limit)

    def get_period_by_id(self, period_id):
        import db
        return db.get_period_by_id(period_id)

    def update_period(self, period_id, **kwargs):
        import db
        return db.update_period(period_id, **kwargs)

    def delete_period(self, period_id):
        import db
        return db.delete_period(period_id)

    def get_last_period(self):
        import db
        return db.get_last_period()

    def set_config(self, key, value):
        import db
        return db.set_config(key, value)

    def get_config(self, key, default=""):
        import db
        return db.get_config(key, default)

    def set_mood(self, day, score, date=""):
        import db
        return db.set_mood(day, score, date)

    def get_mood_log(self):
        import db
        return db.get_mood_log()

    def set_symptoms(self, day, symptoms, date=""):
        import db
        return db.set_symptoms(day, symptoms, date)

    def get_symptom_log(self):
        import db
        return db.get_symptom_log()

    def add_care_log(self, day, date, score, memory_id, related_count, memora_ok):
        import db
        return db.add_care_log(day, date, score, memory_id, related_count, memora_ok)

    def add_feed_log(self, date, kind, memory_id, ok):
        import db
        return db.add_feed_log(date, kind, memory_id, ok)

    def has_feed(self, date, kind):
        import db
        return db.has_feed(date, kind)

    def get_day_log(self, date):
        import db
        return db.get_day_log(date)


# ======================================================================
#  示例实现①：MySQL
#  需要先装驱动：pip install pymysql
#  建表 SQL 见 README 附录。这里只演示关键方法如何用 SQL 实现。
# ======================================================================

class MySQLStorage(StorageInterface):
    """MySQL 示例。把连接信息改成你自己的即可使用。"""

    def __init__(self, host="127.0.0.1", port=3306, user="root",
                 password="", database="selene"):
        import pymysql
        self._conn = pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=database, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        )

    def _q(self, sql, args=()):
        with self._conn.cursor() as cur:
            cur.execute(sql, args)
            self._conn.commit()
            return cur

    def add_period(self, start_date, end_date, flow, pain, mood, body_note, note):
        cur = self._q(
            "INSERT INTO periods (start_date,end_date,flow,pain,mood,body_note,note) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (start_date, end_date, flow, pain, mood, body_note, note),
        )
        return cur.lastrowid

    def get_periods(self, limit=12):
        cur = self._q(
            "SELECT * FROM periods ORDER BY start_date ASC LIMIT %s", (limit,))
        return cur.fetchall()

    def get_period_by_id(self, period_id):
        cur = self._q("SELECT * FROM periods WHERE id=%s", (period_id,))
        return cur.fetchone()

    def update_period(self, period_id, **kwargs):
        allowed = {"start_date", "end_date", "flow", "pain", "mood", "body_note", "note"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        sets = ", ".join(f"{k}=%s" for k in updates)
        cur = self._q(f"UPDATE periods SET {sets} WHERE id=%s",
                      (*updates.values(), period_id))
        return cur.rowcount > 0

    def delete_period(self, period_id):
        cur = self._q("DELETE FROM periods WHERE id=%s", (period_id,))
        return cur.rowcount > 0

    def get_last_period(self):
        cur = self._q("SELECT * FROM periods ORDER BY start_date DESC LIMIT 1")
        return cur.fetchone()

    def set_config(self, key, value):
        self._q("INSERT INTO config (k,value) VALUES (%s,%s) "
                "ON DUPLICATE KEY UPDATE value=%s", (key, value, value))

    def get_config(self, key, default=""):
        cur = self._q("SELECT value FROM config WHERE k=%s", (key,))
        row = cur.fetchone()
        return row["value"] if row else default

    def set_mood(self, day, score, date=""):
        self._q("INSERT INTO mood_log (day,score,date) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE score=%s,date=%s",
                (day, score, date, score, date))

    def get_mood_log(self):
        cur = self._q("SELECT date,score FROM mood_log WHERE date<>''")
        return {r["date"]: r["score"] for r in cur.fetchall()}

    def set_symptoms(self, day, symptoms, date=""):
        import json
        s = json.dumps(symptoms, ensure_ascii=False)
        self._q("INSERT INTO symptom_log (day,symptoms,date) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE symptoms=%s,date=%s",
                (day, s, date, s, date))

    def get_symptom_log(self):
        import json
        cur = self._q("SELECT date,symptoms FROM symptom_log WHERE date<>''")
        out = {}
        for r in cur.fetchall():
            try:
                out[r["date"]] = json.loads(r["symptoms"]) if r["symptoms"] else []
            except Exception:
                out[r["date"]] = []
        return out

    def add_care_log(self, day, date, score, memory_id, related_count, memora_ok):
        self._q("INSERT INTO care_log (day,date,score,memory_id,related_count,memora_ok) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (day, date, score, memory_id, related_count, 1 if memora_ok else 0))

    def add_feed_log(self, date, kind, memory_id, ok):
        self._q("INSERT INTO feed_log (date,kind,memory_id,ok) VALUES (%s,%s,%s,%s)",
                (date, kind, memory_id, 1 if ok else 0))

    def has_feed(self, date, kind):
        cur = self._q("SELECT id FROM feed_log WHERE date=%s AND kind=%s", (date, kind))
        return cur.fetchone() is not None

    def get_day_log(self, date):
        cur = self._q("SELECT day,score FROM mood_log WHERE date=%s", (date,))
        mood = cur.fetchone()
        cur = self._q("SELECT day,symptoms FROM symptom_log WHERE date=%s", (date,))
        sym = cur.fetchone()
        import json
        result = {}
        if mood:
            result["day"], result["score"] = mood["day"], mood["score"]
        if sym:
            result.setdefault("day", sym["day"])
            try:
                result["symptoms"] = json.loads(sym["symptoms"]) if sym["symptoms"] else []
            except Exception:
                result["symptoms"] = []
        return result


# ======================================================================
#  示例实现②：PostgreSQL
#  需要先装驱动：pip install psycopg2-binary
#  占位符用 %s（psycopg2 语法），建表 SQL 见 README 附录。
# ======================================================================

class PostgresStorage(MySQLStorage):
    """
    PostgreSQL 示例。psycopg2 的 %s 占位符与 pymysql 一致，
    这里复用 MySQLStorage 的 SQL 逻辑，仅替换连接方式与去重语法。
    """

    def __init__(self, host="127.0.0.1", port=5432, user="postgres",
                 password="", database="selene"):
        import psycopg2
        self._conn = psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname=database,
        )

    def _q(self, sql, args=()):
        with self._conn.cursor() as cur:
            cur.execute(sql, args)
            self._conn.commit()
            return cur

    def set_config(self, key, value):
        # PostgreSQL 用 ON CONFLICT 而非 ON DUPLICATE KEY
        self._q("INSERT INTO config (k,value) VALUES (%s,%s) "
                "ON CONFLICT (k) DO UPDATE SET value=EXCLUDED.value", (key, value))

    def set_mood(self, day, score, date=""):
        self._q("INSERT INTO mood_log (day,score,date) VALUES (%s,%s,%s) "
                "ON CONFLICT (day) DO UPDATE SET score=EXCLUDED.score,date=EXCLUDED.date",
                (day, score, date))

    def set_symptoms(self, day, symptoms, date=""):
        import json
        s = json.dumps(symptoms, ensure_ascii=False)
        self._q("INSERT INTO symptom_log (day,symptoms,date) VALUES (%s,%s,%s) "
                "ON CONFLICT (day) DO UPDATE SET symptoms=EXCLUDED.symptoms,date=EXCLUDED.date",
                (day, s, date))


# ======================================================================
#  全局存储实例（业务代码从这里拿）
#  默认 SQLite。切换成 MySQL：改这一行即可。
# ======================================================================

STORE: StorageInterface = SQLiteStorage()


def use_mysql(host="127.0.0.1", port=3306, user="root",
              password="", database="selene"):
    """把全局存储切换成 MySQL（示例）。"""
    global STORE
    STORE = MySQLStorage(host, port, user, password, database)


def use_postgres(host="127.0.0.1", port=5432, user="postgres",
                 password="", database="selene"):
    """把全局存储切换成 PostgreSQL（示例）。"""
    global STORE
    STORE = PostgresStorage(host, port, user, password, database)


# 方便：如果直接跑这个文件，打印当前存储
if __name__ == "__main__":
    print(f"当前存储：{type(STORE).__name__}")
