"""
Selene - 主动提醒推送模块
内置调度：到点判断周期阶段 → 从文案库取话 → 通过推送通道发到手机。

推送通道：Server酱（微信推送），需配置 sendkey。
所有提醒均为可选功能：不配置 key 或关闭开关，就完全不推送，
不影响 Selene 核心的记录功能（这是"能选"的哲学）。

隐私：所有数据只在本地 selene.db，推送只发出生成的文案，不传敏感原始数据。
"""

import asyncio
import urllib.parse
import urllib.request
from datetime import datetime, date

import cycle
import db
import prompts

# 默认提醒时间点（可配置，逗号分隔多个）
DEFAULT_REMIND_TIMES = ["08:30"]

# 哪些阶段每天推关怀（due_check 特殊：只要还欠着就每天提醒记）
CARE_PHASES = {"menstrual", "luteal", "pre_menstrual"}

# flow 数字 -> 流量描述
_FLOW_DESC = {1: "量少", 2: "量适中", 3: "量多"}


def _cfg(key, default=""):
    return db.get_config(key, default)


def _cfg_bool(key, default: bool) -> bool:
    return db.get_config(key, "1" if default else "0") == "1"


def _config_times() -> list:
    raw = db.get_config("remind_times", ",".join(DEFAULT_REMIND_TIMES))
    return [t.strip() for t in raw.split(",") if t.strip()]


def _flow_desc() -> str:
    """从最近一次经期记录读流量，转成描述。没记录给中性默认。"""
    last = db.get_last_period()
    if not last:
        return "量正常"
    return _FLOW_DESC.get(last.get("flow", 2), "量适中")


def decide_reminder(today: date | None = None) -> dict | None:
    """
    判断今天该提醒什么。返回 {phase, day, days_left} 或 None（不提醒）。
    - 初次无记录：first_time（引导录入）
    - 预测日已过且这轮未记录：due_check（欠着就每天催）
    - 经期 / 黄体 / 经前：每天关怀
    - 卵泡 / 排卵：状态好，不打扰
    """
    today = today or date.today()
    periods = db.get_periods()
    if not periods:
        return {"phase": "first_time", "day": 0, "days_left": 0}

    st = db.current_cycle_status(today)
    phase = st["phase"]

    # 预测日到了但还没记这轮 → 欠着，每天提醒记 D1
    if phase != "menstrual" and st["next_date"] != "未知":
        try:
            nxt = date.fromisoformat(st["next_date"])
        except ValueError:
            nxt = None
        if nxt and nxt <= today:
            return {
                "phase": "due_check",
                "day": st["day"],
                "days_left": 0,
            }

    # 经期 / 黄体 / 经前 关怀
    if phase in CARE_PHASES:
        return {
            "phase": phase,
            "day": st["day"],
            "days_left": st["days_left"],
        }

    return None  # 卵泡 / 排卵 / 其他：不打扰


def _push_serverchan(sendkey: str, title: str, desp: str) -> bool:
    """Server酱推送（微信）。成功返回 True。"""
    try:
        url = f"https://sctapi.ftqq.com/{sendkey}.send"
        data = urllib.parse.urlencode({"title": title, "desp": desp}).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"[Selene] serverchan push failed: {e}")
        return False


def build_reminder(info: dict) -> dict | None:
    """根据判断结果，从文案库取一条话，返回 {title, body}。

    2026-10-20：`couple_mode` 以前**写死 False**，配置里的 couple_mode=1 根本
    没生效，所以一直推的是中性科普口吻。现在改成读配置。

    标题也走配置（`reminder_title`），默认「Selene 关心你 💕」——
    想用自己的名字，往 config 里填一行就行，不用改代码。
    """
    phase = info["phase"]
    couple = _cfg("couple_mode", "1") == "1"
    text = prompts.get_reminder(
        phase, couple_mode=couple,
        days_left=info.get("days_left", 0),
        day=info.get("day", 0),
        flow_desc=_flow_desc(),
    )
    if not text:
        return None
    title = _cfg("reminder_title", "") or "Selene 关心你 💕"
    return {"title": title, "body": text}


def remind_once(now: datetime | None = None) -> bool:
    """
    执行一次提醒检查。返回是否真的推送了。
    幂等：同一个阶段同一天只推一次。
    """
    now = now or datetime.now()
    if not _cfg_bool("remind_enabled", True):
        return False
    sendkey = _cfg("serverchan_key", "")
    if not sendkey:
        return False

    info = decide_reminder(now.date())
    if not info:
        return False

    today = now.date().isoformat()
    phase = info["phase"]
    if db.get_config(f"last_push_{phase}") == today:
        return False  # 今天这个阶段已推过

    msg = build_reminder(info)
    if not msg:
        return False

    ok = _push_serverchan(sendkey, msg["title"], msg["body"])
    if ok:
        db.set_config(f"last_push_{phase}", today)
    return ok


async def reminder_loop():
    """每分钟检查一次时间，到点执行推送。外层 try/except 防任务死掉（重启自愈）。"""
    while True:
        try:
            now = datetime.now()
            if now.strftime("%H:%M") in _config_times():
                await asyncio.to_thread(remind_once, now)
        except Exception as e:
            print(f"[Selene] reminder loop error: {e}")
        await asyncio.sleep(30)
