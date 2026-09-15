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


def describe_status(periods, today=None, cycle_length=None):
    """Presentation metadata: recorded dates are distinct from estimated phases."""
    today = today or date.today()
    state = current_phase(periods, today, cycle_length)
    last = periods[-1] if periods else {}
    start, end = last.get("start_date", ""), last.get("end_date", "") or ""
    names = {"menstrual": "经期", "follicular": "卵泡期", "ovulation": "排卵期", "luteal": "黄体期"}
    actual = bool(start and end and start <= today.isoformat() <= end)
    label = "经期中（已记录）" if actual else ("预计" + names[state["phase"]] if state["phase"] in names else "阶段待确认")
    result = {"as_of": today.isoformat(), "phase_label": label, "phase_is_estimated": not actual,
              "start_date": start, "end_date": end, "next_date": state["next_date"],
              "days_left": state["days_left"], "overdue_days": 0}
    if not start or start > today.isoformat():
        result.update(state="pending", title="待记录", detail="记录经期开始日期后，可查看周期预测。", phase_label="待记录")
    elif actual:
        result.update(state="menstrual", title="经期中", detail=f"已记录：{start} 至 {end}")
    elif state["next_date"] != "未知" and state["next_date"] <= today.isoformat():
        overdue = (today - date.fromisoformat(state["next_date"])).days
        result.update(state="overdue" if overdue else "due", overdue_days=overdue,
                      title=f"超过预计日期 {overdue} 天" if overdue else "已到预计日期",
                      detail="请确认本轮是否已经开始；开始后记一下日期。")
    elif end:
        result.update(state="ended", title="已记录结束日期", detail=f"这轮经期：{start} 至 {end}")
    else:
        result.update(state="started", title="已记录开始日期", detail=f"{start} 开始；结束后记一下结束日期。")
    return result
