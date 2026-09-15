"""
Selene - 周期计算模块
根据记录的历史经期数据，计算平均周期、预测下次、判断当前所处阶段。
"""

from datetime import date, timedelta

# 默认周期长度（天），初始没有数据时使用
DEFAULT_CYCLE = 28
# 各阶段天数（从经期第1天算起，经典28天周期）
PHASE_DAYS = {
    "menstrual": 5,        # 经期：第1-5天
    "follicular": 8,       # 卵泡期：第6-13天
    "ovulation": 3,        # 排卵期：第14-16天（高峰在第14天）
    "luteal": 12,          # 黄体期：第17-28天
}


def avg_cycle(periods: list[dict]) -> int:
    """
    根据历史经期记录计算平均周期。
    periods 按开始日期升序排列，每条有 start_date。
    返回整数天数，不足2条则返回默认值。
    """
    if len(periods) < 2:
        return DEFAULT_CYCLE

    diffs = []
    for i in range(1, len(periods)):
        d1 = date.fromisoformat(periods[i - 1]["start_date"])
        d2 = date.fromisoformat(periods[i]["start_date"])
        diff = (d2 - d1).days
        if 18 <= diff <= 60:  # 过滤异常值
            diffs.append(diff)

    if not diffs:
        return DEFAULT_CYCLE

    return round(sum(diffs) / len(diffs))


def predict_next(periods: list[dict]) -> date | None:
    """预测下次经期开始日。"""
    if not periods:
        return None
    cycle = avg_cycle(periods)
    last_start = date.fromisoformat(periods[-1]["start_date"])
    return last_start + timedelta(days=cycle)


def cycle_day(periods: list[dict], today: date | None = None) -> int | None:
    """
    当前是周期的第几天（从最近一次经期开始算，第1天=经期第一天）。
    返回 None 表示没有记录无法计算。
    """
    if not periods:
        return None
    today = today or date.today()
    last = date.fromisoformat(periods[-1]["start_date"])
    delta = (today - last).days + 1
    if delta < 1 or delta > 60:
        return None
    return delta


def current_phase(periods: list[dict], today: date | None = None, cycle_length: int | None = None) -> dict:
    """
    返回当前阶段信息：
    {
        "phase": "menstrual" | "follicular" | "ovulation" | "luteal" | "unknown",
        "day": int,       # 当前周期第几天
        "days_left": int, # 距下次经期还有几天（预测）
        "next_date": str, # 预测下次经期日期（ISO）
        "cycle_length": int, # 平均周期
    }
    """
    today = today or date.today()
    cd = cycle_day(periods, today)
    cycle = cycle_length if cycle_length is not None else avg_cycle(periods)
    nxt = date.fromisoformat(periods[-1]["start_date"]) + timedelta(days=cycle) if periods else None

    if cd is None:
        return {
            "phase": "unknown",
            "day": 0,
            "days_left": 0,
            "next_date": nxt.isoformat() if nxt else "未知",
            "cycle_length": cycle,
        }

    # 按经典28天比例映射到实际周期
    ratio = cycle / DEFAULT_CYCLE
    menstrual_end = round(PHASE_DAYS["menstrual"] * ratio)
    follicular_end = menstrual_end + round(PHASE_DAYS["follicular"] * ratio)
    ovulation_end = follicular_end + round(PHASE_DAYS["ovulation"] * ratio)

    days_left = (nxt - today).days if nxt else 0
    end_date = periods[-1].get("end_date")

    if end_date:
        # 实际结束日期优先于按周期比例推算的经期长度。
        start = date.fromisoformat(periods[-1]["start_date"])
        end = date.fromisoformat(end_date)
        if start <= today <= end:
            phase = "menstrual"
        elif today > end:
            if days_left > 14:
                phase = "follicular"
            elif days_left >= 8:
                phase = "ovulation"
            else:
                phase = "luteal"
        else:
            phase = "unknown"
    elif cd <= menstrual_end:
        phase = "menstrual"
    elif cd <= follicular_end:
        phase = "follicular"
    elif cd <= ovulation_end:
        phase = "ovulation"
    elif cd <= cycle:
        phase = "luteal"
    else:
        phase = "unknown"

    return {
        "phase": phase,
        "day": cd,
        "days_left": days_left,
        "next_date": nxt.isoformat() if nxt else "未知",
        "cycle_length": cycle,
    }
