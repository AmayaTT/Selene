"""Install in Memora/: date-based signals and shared Selene MCP tools."""
import hashlib
import os
import re
import sys

_SELENE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Selene"))
if _SELENE_DIR not in sys.path:
    sys.path.insert(0, _SELENE_DIR)

import db as _selene_db
import sync_storage

_EMOTIONS = {
    "不开心": ("sad", 3), "不高兴": ("sad", 3),
    "开心": ("happy", 9), "高兴": ("happy", 9), "快乐": ("happy", 9),
    "兴奋": ("happy", 10), "幸福": ("happy", 9),
    "感动": ("moved", 8), "温暖": ("moved", 8),
    "放松": ("calm", 7), "平静": ("calm", 7), "安心": ("calm", 7), "舒服": ("calm", 7),
    "惊讶": ("surprised", 6), "震惊": ("surprised", 6),
    "焦虑": ("anxious", 4), "紧张": ("anxious", 4), "担心": ("anxious", 4),
    "不安": ("anxious", 3), "烦躁": ("anxious", 4),
    "低落": ("sad", 3), "难过": ("sad", 3), "伤心": ("sad", 3), "委屈": ("sad", 3),
    "想哭": ("sad", 2), "抑郁": ("sad", 2),
    "生气": ("angry", 2), "愤怒": ("angry", 2), "暴躁": ("angry", 2), "不爽": ("angry", 3),
}
_MOOD_SCORES = {"happy": 9, "moved": 8, "calm": 7, "surprised": 6, "anxious": 4, "sad": 3, "angry": 2}


def _affirmed(content, word):
    """Conservative local negation check; ambiguous mixed moods are skipped."""
    for clause in re.split(r"[，,。！？!?；;\n]|但是|不过|但", content):
        for match in re.finditer(re.escape(word), clause):
            prefix = clause[:match.start()]
            suffix = clause[match.end():]
            if re.search(r"(?:没有|并非|不是|不再|不会|不|没|无|未|别)(?:[\u4e00-\u9fff]{0,5})$", prefix):
                continue
            if re.match(r"(?:已经)?(?:好了|消失|缓解了|不见了)", suffix):
                continue
            return True
    return False


def _auto_sync_from_feel(content: str, event_date: str = "", memory_id=None,
                         source: str = "", mood: str = "") -> dict:
    if source == "selene" or content.lstrip().startswith("【Selene"):
        return {"synced": False, "reason": "selene_origin"}
    try:
        value = _selene_db.normalize_log_date(event_date)
    except ValueError:
        return {"synced": False, "reason": "invalid_event_date"}
    hits = [s for s in _selene_db.SYMPTOMS_LIST if _affirmed(content, s)]
    detected = [entry for word, entry in _EMOTIONS.items() if _affirmed(content, word)]
    score = _MOOD_SCORES.get(mood)
    if score is None and len({entry[0] for entry in detected}) == 1:
        score = min(entry[1] for entry in detected)
    if not hits and score is None:
        return {"synced": False, "reason": "no_unambiguous_signal"}
    _selene_db.init_db()
    info = _selene_db.log_date_info(value)
    event_key = f"memory:{memory_id}" if memory_id is not None else hashlib.sha256(
        (value + "\0" + content).encode()).hexdigest()
    return sync_storage.apply_event(value, info["day"], score, hits, memory_id, event_key)


def mount(memora):
    """Use the same implementation as Selene's standalone MCP endpoint."""
    import selene_server

    @memora.tool()
    async def selene_record(start_date: str, end_date: str = "", flow: int = 2,
                            pain: int = 0, mood: str = "", body_note: str = "", note: str = "") -> str:
        """记录经期；start_date/end_date 使用 YYYY-MM-DD。"""
        _selene_db.init_db()
        _selene_db.migrate_cycle_config()
        return await selene_server.selene_record(start_date, end_date, flow, pain, mood, body_note, note)

    @memora.tool()
    async def selene_status(couple_mode: bool = True) -> str:
        """查看周期状态、提醒和科普，与 Selene 独立接口一致。"""
        _selene_db.init_db()
        _selene_db.migrate_cycle_config()
        return await selene_server.selene_status(couple_mode)

    @memora.tool()
    async def selene_history(limit: int = 12) -> str:
        """查看历史经期记录，最新记录在前。"""
        _selene_db.init_db()
        _selene_db.migrate_cycle_config()
        return await selene_server.selene_history(limit)

    return memora
