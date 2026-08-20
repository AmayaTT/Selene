"""
Selene - MCP Streamable HTTP 服务
温柔的女性周期陪伴工具。橘瓣可直接接入。

启动：python selene_server.py
端口：8003

工具列表：
  selene_record  - 记录经期
  selene_status  - 查看周期状态+提醒+科普+症状回顾
  selene_history - 查看历史记录
  selene_edit    - 编辑记录
  selene_delete  - 删除记录
  selene_config  - 设置偏好
"""

import json
import sys
from datetime import date

import uvicorn
from mcp.server.fastmcp import FastMCP

import db
import cycle
import prompts

# ── 创建 MCP Server ──
selene = FastMCP("Selene")
selene.settings.transport_security.enable_dns_rebinding_protection = False

def _phase_cn(phase: str) -> str:
    return {
        "menstrual": "经期",
        "follicular": "卵泡期",
        "ovulation": "排卵期",
        "luteal": "黄体期",
        "unknown": "未知",
    }.get(phase, phase)

def _flow_desc(flow: int) -> str:
    return {1: "量偏少", 2: "流量正常", 3: "量偏大"}.get(flow, "流量正常")


# ═══════════════════════════════════════════════
#  工具1: selene_record
# ═══════════════════════════════════════════════

@selene.tool()
async def selene_record(
    start_date: str,
    end_date: str = "",
    flow: int = 2,
    pain: int = 0,
    mood: str = "",
    body_note: str = "",
    note: str = "",
) -> str:
    """记录一次经期。

    start_date 必填，ISO格式(YYYY-MM-DD)。end_date 可选。
    flow: 1少/2中/3多。pain: 0-3。mood/body_note 自由填。"""
    db.add_period(
        start_date=start_date, end_date=end_date,
        flow=flow, pain=pain, mood=mood, body_note=body_note, note=note,
    )
    periods = db.get_periods()
    now = cycle.current_phase(periods)

    msg = f"已记录 ✅ 今天是周期第{now['day']}天，{_phase_cn(now['phase'])}。"
    if len(periods) >= 2:
        msg += f" 平均周期{now['cycle_length']}天，下次预计 {now['next_date']}。"

    return json.dumps({
        "success": True, "message": msg,
        "phase_info": {
            "phase": now["phase"], "phase_cn": _phase_cn(now["phase"]),
            "day": now["day"], "days_left": now["days_left"],
            "next_date": now["next_date"], "cycle_length": now["cycle_length"],
        },
    }, ensure_ascii=False)


# ═══════════════════════════════════════════════
#  工具2: selene_status
# ═══════════════════════════════════════════════

@selene.tool()
async def selene_status(couple_mode: bool = True) -> str:
    """查看当前周期状态，返回阶段、提醒、科普、近期症状回顾。
    
    couple_mode: true=伴侣语气，false=中性。"""
    periods = db.get_periods()
    now = cycle.current_phase(periods)
    phase = now["phase"]

    result = {
        "phase": phase, "phase_cn": _phase_cn(phase),
        "day": now["day"], "days_left": now["days_left"],
        "next_date": now["next_date"], "cycle_length": now["cycle_length"],
        "periods_recorded": len(periods),
    }

    # ── 提醒文案 ──
    if len(periods) == 0:
        reminder = prompts.get_reminder("first_time", couple_mode)
    elif phase == "unknown":
        last = db.get_last_period()
        if last:
            reminder = prompts.get_reminder("due_check", couple_mode)
        else:
            reminder = ""
    elif now["days_left"] <= 3 and phase != "menstrual":
        reminder = prompts.get_reminder("pre_menstrual", couple_mode, days_left=now["days_left"])
        signs = db.get_config("pre_menstrual_signs")
        if signs:
            reminder += f"（你的经前信号：{signs}）"
    elif phase == "menstrual":
        last = db.get_last_period()
        fm = last.get("flow", 2) if last else 2
        reminder = prompts.get_reminder("menstrual", couple_mode, day=now["day"], flow_desc=_flow_desc(fm))
    else:
        reminder = prompts.get_reminder(phase, couple_mode, day=now["day"])
        if phase == "luteal":
            signs = db.get_config("pre_menstrual_signs")
            if signs:
                reminder += f"（你的经前信号：{signs}）"

    result["reminder"] = reminder
    result["science"] = prompts.get_science(phase)

    # ── 近期身体症状回顾 ──
    recent = db.get_periods(limit=5)
    body_notes = [(p["start_date"], p["body_note"]) for p in recent if p.get("body_note")]
    moods = [(p["start_date"], p["mood"]) for p in recent if p.get("mood")]
    if body_notes:
        result["recent_symptoms"] = [{"date": d, "note": n} for d, n in body_notes[-3:]]
    if moods:
        result["recent_moods"] = [{"date": d, "mood": m} for d, m in moods[-3:]]

    return json.dumps(result, ensure_ascii=False)


# ═══════════════════════════════════════════════
#  工具3: selene_history
# ═══════════════════════════════════════════════

@selene.tool()
async def selene_history(limit: int = 12) -> str:
    """查看历史经期记录，按日期倒序（最新的在前）。

    返回每条记录的日期、流量、疼痛、情绪、身体症状、持续天数。"""
    periods = db.get_periods(limit=limit)
    records = []
    for p in reversed(periods):
        rec = {
            "id": p["id"],
            "start_date": p["start_date"],
            "end_date": p["end_date"] or "",
            "flow": p["flow"],
            "flow_desc": _flow_desc(p["flow"]),
            "pain": p["pain"],
            "mood": p["mood"] or "",
            "body_note": p["body_note"] or "",
            "note": p["note"] or "",
        }
        if p["end_date"]:
            sd = date.fromisoformat(p["start_date"])
            ed = date.fromisoformat(p["end_date"])
            rec["duration_days"] = (ed - sd).days + 1
        records.append(rec)

    return json.dumps({
        "total": len(records),
        "records": records,
    }, ensure_ascii=False)


# ═══════════════════════════════════════════════
#  工具4: selene_edit
# ═══════════════════════════════════════════════

@selene.tool()
async def selene_edit(
    id: int,
    start_date: str = "",
    end_date: str = "",
    flow: int = -1,
    pain: int = -1,
    mood: str = "",
    body_note: str = "",
    note: str = "",
) -> str:
    """编辑一条经期记录。传要改的字段，不传的保持原样。
    
    id 必填。其他字段可选。flow: 1少/2中/3多。pain: 0-3。"""
    old = db.get_period_by_id(id)
    if not old:
        return json.dumps({"success": False, "message": f"没找到 id={id} 的记录"}, ensure_ascii=False)

    updates = {}
    if start_date:
        updates["start_date"] = start_date
    if end_date:
        updates["end_date"] = end_date
    if flow >= 1:
        updates["flow"] = flow
    if pain >= 0:
        updates["pain"] = pain
    if mood:
        updates["mood"] = mood
    if body_note:
        updates["body_note"] = body_note
    if note:
        updates["note"] = note

    if not updates:
        return json.dumps({"success": False, "message": "没有要改的字段"}, ensure_ascii=False)

    db.update_period(id, **updates)
    new = db.get_period_by_id(id)

    changed = [k for k in updates if str(old.get(k, "")) != str(new.get(k, ""))]
    return json.dumps({
        "success": True,
        "message": f"已更新 id={id}，改动字段：{', '.join(changed)} ✅",
    }, ensure_ascii=False)


# ═══════════════════════════════════════════════
#  工具5: selene_delete
# ═══════════════════════════════════════════════

@selene.tool()
async def selene_delete(id: int) -> str:
    """删除一条经期记录。不可恢复，请确认后再删。"""
    old = db.get_period_by_id(id)
    if not old:
        return json.dumps({"success": False, "message": f"没找到 id={id} 的记录"}, ensure_ascii=False)

    db.delete_period(id)
    return json.dumps({
        "success": True,
        "message": f"已删除 ✅ {old['start_date']} 的记录",
        "deleted": {
            "id": old["id"],
            "start_date": old["start_date"],
            "end_date": old.get("end_date", ""),
        },
    }, ensure_ascii=False)


# ═══════════════════════════════════════════════
#  工具6: selene_config
# ═══════════════════════════════════════════════

@selene.tool()
async def selene_config(key: str, value: str) -> str:
    """设置偏好。key: couple_mode / pre_menstrual_signs 等。"""
    db.set_config(key, value)
    return json.dumps({"success": True, "key": key, "value": value}, ensure_ascii=False)


# ═══════════════════════════════════════════════
#  工具7: selene_care_context — 情绪关怀上下文
# ═══════════════════════════════════════════════

@selene.tool()
async def selene_care_context(days: int = 30) -> str:
    """拉取近期情绪关怀上下文：memora 记忆库里与情绪相关的记忆，
    供 AI 对话安抚用户时参考。memora 不可用时返回失败信息，不影响其他工具。"""
    try:
        import memora_client
        r = await memora_client.recall("情绪 低落 焦虑 开心", days=days)
        if not r:
            return json.dumps({"success": False, "message": "记忆库暂不可用"}, ensure_ascii=False)
        related = [
            {"content": m.get("content", ""), "time_ago": m.get("time_ago", ""), "mood": m.get("mood", "")}
            for m in (r.get("results") or [])
        ]
        return json.dumps({
            "success": True, "count": len(related), "related": related,
            "message": f"找到 {len(related)} 条情绪相关记忆",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "message": f"记忆库暂不可用: {e}"}, ensure_ascii=False)


# ═══════════════════════════════════════════════
#  启动
# ═══════════════════════════════════════════════

def main():
    db.init_db()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8003
    print(f"🌙 Selene 启动中... http://0.0.0.0:{port}")
    app = selene.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
