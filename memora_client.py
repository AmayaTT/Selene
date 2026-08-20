"""
Selene - memora 记忆库客户端（httpx 原生实现，对外提供 async 接口）
用 HTTP + Mcp-Session-Id 直接调 memora（MCP Streamable HTTP 服务，端口8004）。
不使用 mcp.client.streamable_http：该库在服务器 fastmcp 3.4.7 环境下会话握手有兼容问题，
而原生 HTTP 带 session id 完全兼容（已验证：tools/list 12个工具、memora_record 写入成功）。

对外暴露 async 的 record / recall，内部用 asyncio.to_thread 跑同步 httpx，
避免阻塞 FastAPI 事件循环；同时保留 3 秒超时与失败降级（绝不抛异常）。
"""

import asyncio
import json
import threading

import httpx

# memora 与 Selene 同机部署
MEMORA_URL = "http://127.0.0.1:8004/mcp"
TIMEOUT_SECONDS = 3  # 连接/调用超时（秒）

# 全局单例：_client 为 None 表示未连接或已失效
_client = None
_lock = threading.Lock()


def _get_client():
    """懒加载单例 httpx.Client（已含 session id 头）。并发安全；失败返回 None。"""
    global _client
    with _lock:
        if _client is not None:
            return _client
        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            c = httpx.Client(timeout=TIMEOUT_SECONDS, headers=headers)

            # 1) initialize（响应头带 Mcp-Session-Id）
            init = c.post(MEMORA_URL, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18",
                           "capabilities": {},
                           "clientInfo": {"name": "selene", "version": "1.0"}},
            })
            sid = init.headers.get("Mcp-Session-Id")
            if sid:
                c.headers["Mcp-Session-Id"] = sid

            # 2) initialized 通知（单向）
            c.post(MEMORA_URL, json={
                "jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

            _client = c
            return c
        except Exception as e:
            print(f"[Selene] memora connect failed: {e}")
            _client = None
            return None


def _call(tool_name: str, args: dict):
    """调用 memora 工具。成功返回解析后的 dict，任何失败返回 None。"""
    global _client
    try:
        c = _get_client()
        if c is None:
            return None
        r = c.post(MEMORA_URL, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        })
        if r.status_code != 200:
            return None
        # 解析 text/event-stream 中的 data 行
        result = None
        for line in r.text.splitlines():
            if line.startswith("data:"):
                result = json.loads(line[5:].strip())
                break
        if result is None or "result" not in result:
            return None
        res = result["result"]
        if res.get("isError"):
            return None
        text = "".join(cc.get("text", "") for cc in res.get("content", []))
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"raw": text}
    except Exception as e:
        print(f"[Selene] memora call {tool_name} failed: {e}")
        _client = None  # 连接可能已失效，重置缓存让下次调用重建
        return None


def _record_sync(content: str, importance: int, mem_type: str, event_date: str) -> dict | None:
    return _call("memora_record", {
        "content": content,
        "importance": importance,
        "type": mem_type,
        "event_date": event_date,
    })


def _recall_sync(query: str, days: int) -> dict | None:
    return _call("memora_recall", {"query": query, "days": days})


async def record(content: str, importance: int = 3, mem_type: str = "fact",
                 event_date: str = "") -> dict | None:
    """记一条记忆到 memora（async）。mem_type 可选 fact/feel/digest。"""
    return await asyncio.to_thread(_record_sync, content, importance, mem_type, event_date)


async def recall(query: str = "", days: int = 30) -> dict | None:
    """回看近期相关记忆（async，memora_recall，FTS5+向量混合搜索）。"""
    return await asyncio.to_thread(_recall_sync, query, days)
