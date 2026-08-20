# -*- coding: utf-8 -*-
"""Selene REST 冒烟测试 - 一次跑通全部 5 个接口"""
import sys, json, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "http://127.0.0.1:8010"

def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.loads(r.read().decode("utf-8"))

def post(path, data):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))

ok = True

# 1. 保存配置
r = post("/save_config", {"cycleLength": 30, "periodStart": "2026-08-01", "periodEnd": "2026-08-06"})
print("1) save_config:", r); ok &= r.get("success")

# 2. 读配置
r = get("/get_config")
print("2) get_config:", r)
ok &= r.get("cycleLength") == 30

# 3. 记情绪
r = post("/log_mood", {"day": 1, "score": 3})
print("3) log_mood:", r); ok &= r.get("success")
r = post("/log_mood", {"day": 2, "score": -1})
print("   log_mood day2:", r); ok &= r.get("success")

# 4. 记症状
r = post("/log_symptoms", {"day": 1, "symptoms": ["腹痛", "头疼"]})
print("4) log_symptoms:", r); ok &= r.get("success")
r = post("/log_symptoms", {"day": 2, "symptoms": []})
print("   log_symptoms day2:", r); ok &= r.get("success")

# 5. 读全部日志
r = get("/get_logs")
print("5) get_logs:", json.dumps(r, ensure_ascii=False))
ok &= "1" in r["moodLog"] and r["moodLog"]["1"] == 3
ok &= "腹痛" in r["symptomLog"]["1"]

print("\n===== RESULT:", "ALL PASS" if ok else "SOME FAILED", "=====")
sys.exit(0 if ok else 1)
