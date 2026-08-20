"""
Selene - REST API 后端
给前端 selene.jsx 提供持久化接口（刷新不丢数据）。
独立于原来的 MCP 服务器（selene_server.py，端口8003），互不影响。

启动：python selene_rest.py        # 默认端口 8010
      python selene_rest.py 8011   # 指定端口

接口：
  GET  /get_logs      -> { moodLog: {day: score}, symptomLog: {day: [症状]} }
  POST /log_mood      -> body: { day, score }
  POST /log_symptoms  -> body: { day, symptoms: [] }
  GET  /get_config    -> { cycleLength, periodStart, periodEnd }
  POST /save_config   -> body: { cycleLength, periodStart, periodEnd }
  POST /care_low_mood -> 低情绪关怀：写 memora + 回看相关记忆（memora 挂了不影响主流程）
  GET  /care/emotion_history -> 拉取近期情绪相关记忆（memora），供前端关怀卡片展示

后台任务（lifespan 启动，每分钟检查）：
  每天 21:00 且当天有记录且未喂过 -> 喂每日状态到 memora（type=digest）
  每月 1 日 09:00 且本月未生成 -> 生成月度报告注入 memora（type=digest）
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
import memora_client
import report_builder
import reminder

# 与前端一致的阶段映射（28 天周期）
_PHASE_RULES = [(1, 5, "月经期"), (6, 13, "卵泡期"), (14, 16, "排卵期"), (17, 28, "黄体期")]


def _phase_of_day(day: int) -> str:
    """周期日 -> 阶段名（与前端 getPhase 一致）。"""
    for lo, hi, name in _PHASE_RULES:
        if lo <= day <= hi:
            return name
    return "黄体期"


def _std_symptoms(symptoms: list) -> list:
    """只保留标准化症状词（白名单在 db.SYMPTOMS_LIST，去掉"状态良好"和自定义文本）。"""
    return [s for s in (symptoms or []) if s and s != "状态良好"]


# Windows 控制台默认 GBK，先切到 UTF-8，避免 print emoji/中文崩
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动后台定时任务；退出时取消，重启自愈（feed_log 幂等兜底）。"""
    task = asyncio.create_task(_feed_loop())
    task_rem = asyncio.create_task(reminder.reminder_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Selene REST API", lifespan=lifespan)

# 允许跨域，前端任何地址都能调
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- 请求体模型 ----

class MoodBody(BaseModel):
    day: int
    score: int
    date: str = ""          # 真实日期 YYYY-MM-DD，缺省取今天


class SymptomsBody(BaseModel):
    day: int
    symptoms: list[str] = []
    date: str = ""          # 真实日期 YYYY-MM-DD，缺省取今天


class ConfigBody(BaseModel):
    cycleLength: int = 28
    periodStart: str = ""
    periodEnd: str = ""


class CareBody(BaseModel):
    day: int
    score: int
    date: str = ""          # 真实日期 YYYY-MM-DD，缺省取今天
    symptoms: list[str] = []
    phase: str = ""


# ---- 接口 ----

@app.get("/get_logs")
def get_logs():
    """返回所有情绪日志和症状日志。"""
    return {
        "moodLog": db.get_mood_log(),
        "symptomLog": db.get_symptom_log(),
    }


@app.post("/log_mood")
def log_mood(body: MoodBody):
    """记录/覆盖某天情绪分数。score=-1 表示'无感觉'。date 缺省取今天。"""
    db.set_mood(body.day, body.score, body.date or datetime.now().date().isoformat())
    return {"success": True, "day": body.day, "score": body.score}


@app.post("/log_symptoms")
def log_symptoms(body: SymptomsBody):
    """记录/覆盖某天症状数组。date 缺省取今天。"""
    db.set_symptoms(body.day, body.symptoms, body.date or datetime.now().date().isoformat())
    return {"success": True, "day": body.day, "symptoms": body.symptoms}


@app.get("/get_config")
def get_config():
    """返回周期设置。"""
    return db.get_cycle_config()


@app.post("/save_config")
def save_config(body: ConfigBody):
    """保存周期设置。"""
    db.set_cycle_config(body.cycleLength, body.periodStart, body.periodEnd)
    return {"success": True}


# ═══════════════════════════════════════════════
#  功能A：情绪关怀（低情绪联动写 memora）
# ═══════════════════════════════════════════════

@app.post("/care_low_mood")
async def care_low_mood(body: CareBody):
    """低情绪关怀：score<=4 且非"无感觉"(-1) 时联动：
    1) 把这次低情绪写进 memora（type=feel, importance=5）；
    2) 回看近期相关记忆，返回给前端展示。
    memora 挂了只返回 memora_ok:false，绝不阻塞/报错主流程。"""
    if body.score > 4 or body.score == -1:
        return {"success": True, "skipped": True}

    date_str = body.date or datetime.now().date().isoformat()
    std_symptoms = _std_symptoms(body.symptoms)
    symptoms_txt = "、".join(std_symptoms) if std_symptoms else "无"
    # ★ 措辞必须带"低落"等情绪触发词，memora 才能检测出 sad 情绪标签
    content = (
        f"【Selene】{date_str} 周期Day{body.day} {body.phase}，"
        f"情绪很低落（{body.score}/10），症状：{symptoms_txt}"
    )

    # 写 memora（失败返回 None，不影响后续）
    result = await memora_client.record(
        content, importance=5, mem_type="feel", event_date=date_str
    )
    memory_id = (result or {}).get("id") if result else None

    # 回看近期相关记忆（仅 memora 写入成功后才搜）
    related = []
    if result:
        r = await memora_client.recall("情绪 低落 焦虑 难过", days=30)
        if r:
            related = [
                {"content": m.get("content", ""), "time_ago": m.get("time_ago", ""), "mood": m.get("mood", "")}
                for m in (r.get("results") or [])
            ]

    memora_ok = result is not None
    db.add_care_log(body.day, date_str, body.score, memory_id, len(related), memora_ok)

    return {"success": True, "memory_id": memory_id, "related": related, "memora_ok": memora_ok}


@app.get("/care/emotion_history")
async def emotion_history(days: int = 30):
    """拉取近期情绪相关记忆（memora_recall），供前端关怀卡片展示。memora 挂了返回空列表。"""
    r = await memora_client.recall("情绪 低落 焦虑 开心", days=days)
    if not r:
        return {"related": [], "memora_ok": False}
    related = [
        {"content": m.get("content", ""), "time_ago": m.get("time_ago", ""), "mood": m.get("mood", "")}
        for m in (r.get("results") or [])
    ]
    return {"related": related, "memora_ok": True}


# ═══════════════════════════════════════════════
#  功能B：每日状态喂入 + 月度报告注入（后台任务）
# ═══════════════════════════════════════════════

async def _feed_loop():
    """每分钟检查一次时间，到点执行喂数据。外层 try/except 防任务死掉（重启自愈）。"""
    while True:
        try:
            await _maybe_feed_daily()
            await _maybe_feed_monthly()
        except Exception as e:
            print(f"[Selene] feed loop error: {e}")
        await asyncio.sleep(60)


async def _maybe_feed_daily():
    """每天 21 点（整点小时窗口内，错过也补喂）且当天有记录且未喂过 -> 喂每日状态。"""
    now = datetime.now()
    if now.hour != 21:
        return
    today = now.date().isoformat()
    if db.has_feed(today, "day"):
        return

    log = db.get_day_log(today)
    if not log:
        return  # 当天无任何记录，不喂空记忆

    day = log.get("day", 1)
    phase = _phase_of_day(day)
    score = log.get("score")
    std_symptoms = _std_symptoms(log.get("symptoms", []))
    score_txt = f"{score}/10" if score and score > 0 else "未记录"
    symptoms_txt = "、".join(std_symptoms) if std_symptoms else "无"
    content = f"【Selene 每日状态】{today} 周期Day{day} {phase}｜情绪 {score_txt}｜症状：{symptoms_txt}"

    result = await memora_client.record(
        content, importance=3, mem_type="digest", event_date=today
    )
    memory_id = (result or {}).get("id") if result else None
    db.add_feed_log(today, "day", memory_id, ok=result is not None)


async def _maybe_feed_monthly():
    """每月 1 日 09 点（整点小时窗口）且本月未生成过月报 -> 生成并注入 memora。"""
    now = datetime.now()
    if now.day != 1 or now.hour != 9:
        return
    month = now.strftime("%Y-%m")
    if db.get_config("last_report_month") == month:
        return

    report = report_builder.build_monthly_report(month)
    if not report:
        return  # 当月无有效情绪数据，不生成不注入

    result = await memora_client.record(
        report, importance=5, mem_type="digest", event_date=month + "-01"
    )
    memory_id = (result or {}).get("id") if result else None
    if result:
        db.set_config("last_report_month", month)  # 幂等：本月不再重复注入
    db.add_feed_log(now.date().isoformat(), "month", memory_id, ok=result is not None)


# ═══════════════════════════════════════════════
#  功能C：主动提醒配置与测试（可选推送）
# ═══════════════════════════════════════════════

class ReminderConfigBody(BaseModel):
    enabled: bool | None = None          # 总开关
    serverchan_key: str | None = None    # Server酱 sendkey
    times: str | None = None             # "08:30,21:00"
    couple_mode: bool | None = None      # True=伴侣版 False=中性版(Selene)


@app.get("/reminder_config")
def get_reminder_config():
    """返回当前提醒配置。"""
    return {
        "enabled": db.get_config("remind_enabled", "1") == "1",
        "serverchan_key": db.get_config("serverchan_key", ""),
        "times": db.get_config("remind_times", ",".join(reminder.DEFAULT_REMIND_TIMES)),
        "couple_mode": db.get_config("couple_mode", "1") == "1",
    }


@app.post("/reminder_config")
def save_reminder_config(body: ReminderConfigBody):
    """保存提醒配置。只更新传入的字段。"""
    if body.enabled is not None:
        db.set_config("remind_enabled", "1" if body.enabled else "0")
    if body.serverchan_key is not None:
        db.set_config("serverchan_key", body.serverchan_key.strip())
    if body.times:
        db.set_config("remind_times", ",".join(t.strip() for t in body.times.split(",") if t.strip()))
    if body.couple_mode is not None:
        db.set_config("couple_mode", "1" if body.couple_mode else "0")
    return {"success": True}


@app.post("/reminder_test")
async def reminder_test():
    """手动触发一次提醒（测试推送通道是否通）。"""
    ok = await asyncio.to_thread(reminder.remind_once)
    return {"success": ok, "pushed": ok}


# ---- 启动 ----

if __name__ == "__main__":
    db.init_db()
    db._ensure_columns()  # 迁移：mood_log / symptom_log 补 date 列
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
    print(f"[Selene REST] starting... http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
