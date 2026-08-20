"""
Selene - 月度情绪报告生成器
纯模板拼装，不依赖 LLM。读 mood_log / symptom_log 生成月度报告文本。

★ 聚合优先用 date 列（真实日期），date 为空的天跳过，不用周期日换算。
返回 None 表示当月没有有效情绪记录（不生成、不注入）。
"""

import json
from collections import Counter

import db

# 与前端 selene.jsx getPhase 一致的阶段映射（28 天周期）
PHASES = [
    (1, 5, "月经期"),
    (6, 13, "卵泡期"),
    (14, 16, "排卵期"),
    (17, 28, "黄体期"),
]


def _phase_of_day(day: int) -> str:
    """周期日 -> 阶段名（与前端一致）。"""
    for lo, hi, name in PHASES:
        if lo <= day <= hi:
            return name
    return "黄体期"


def _fetch_month_moods(month: str) -> list[dict]:
    """当月情绪记录（date 属于当月且非空、score>0 有效分）。"""
    conn = db.get_db()
    rows = conn.execute(
        "SELECT day, score, date FROM mood_log WHERE date LIKE ?",
        (month + "%",)
    ).fetchall()
    conn.close()
    return [
        {"day": r["day"], "score": r["score"]}
        for r in rows
        if r["date"] and r["score"] is not None and r["score"] > 0
    ]


def _fetch_month_symptoms(month: str) -> list[str]:
    """当月症状列表（date 属于当月且非空，展开成单个症状词）。"""
    conn = db.get_db()
    rows = conn.execute(
        "SELECT symptoms FROM symptom_log WHERE date LIKE ?",
        (month + "%",)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        try:
            items = json.loads(r["symptoms"]) if r["symptoms"] else []
        except json.JSONDecodeError:
            items = []
        result.extend(items)
    return result


def build_monthly_report(month: str) -> str | None:
    """生成月度报告文本。month 形如 '2026-02'。无有效数据返回 None。"""
    moods = _fetch_month_moods(month)
    if not moods:
        return None

    scores = [m["score"] for m in moods]
    avg = sum(scores) / len(scores)

    # 低情绪天：score<=4
    low_days = [m for m in moods if m["score"] <= 4]
    if low_days:
        days = sorted(m["day"] for m in low_days)
        low_desc = f"{len(low_days)} 天，集中在周期 Day {days[0]}-{days[-1]}（{_phase_of_day(days[0])}）"
    else:
        low_desc = "0 天，本月情绪平稳"

    # 高频症状 Top3（只统计标准化症状词，自定义文本不进月报/memora）
    symptoms = [s for s in _fetch_month_symptoms(month) if s in db.SYMPTOMS_LIST and s != "状态良好"]
    counter = Counter(symptoms)
    top = counter.most_common(3)

    # 阶段规律：各阶段情绪均值（只列有数据的阶段）
    by_phase = {}
    for m in moods:
        phase = _phase_of_day(m["day"])
        by_phase.setdefault(phase, []).append(m["score"])
    phase_parts = []
    for _, _, name in PHASES:
        if name in by_phase:
            phase_parts.append(f"{name} {sum(by_phase[name]) / len(by_phase[name]):.1f}")

    # 小建议（模板规则，无 LLM）
    suggestion = _pick_suggestion(by_phase, avg, low_days)

    lines = [
        f"【Selene 月度情绪报告】{month}",
        f"· 情绪：均值 {avg:.1f}/10；低情绪（≤4分）{low_desc}",
        f"· 高频症状：{'、'.join(f'{s}({c}次)' for s, c in top) if top else '无'}",
        f"· 阶段规律：{' · '.join(phase_parts) if phase_parts else '无'}",
        f"· 小建议：{suggestion}",
    ]
    return "\n".join(lines)


def _pick_suggestion(by_phase: dict, avg: float, low_days: list) -> str:
    """按阶段均值/低情绪分布选一条模板建议。"""
    luteal = by_phase.get("黄体期")
    menstrual = by_phase.get("月经期")
    if luteal is not None and (menstrual is None or sum(luteal) / len(luteal) <= sum(menstrual) / len(menstrual)):
        return (
            "黄体期（月经前约一周）情绪容易波动，是孕酮上升的正常生理反应；"
            "那几天提前安排放松活动、少安排高强度日程，多吃香蕉、坚果补镁和B6。"
        )
    if menstrual is not None and sum(menstrual) / len(menstrual) <= 5:
        return (
            "经期雌激素处于低点，情绪低落是常见生理反应；注意保暖和休息，"
            "疼的时候别硬撑，热敷或止痛药都可以。"
        )
    if avg >= 7:
        return "这个月整体情绪不错，继续保持规律作息和适度运动，把好状态延续下去。"
    if low_days:
        return "低情绪时先接纳自己，不用硬撑；记录下来、找信任的人聊聊，月经周期带来的起伏都会过去。"
    return "继续保持记录，数据越多，Selene 越能帮你发现身体规律。"
