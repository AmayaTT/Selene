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
from itertools import count

import httpx

# memora 与 Selene 同机部署
MEMORA_URL = "http://127.0.0.1:8004/mcp"
TIMEOUT_SECONDS = 3  # 连接/调用超时（秒）

# 全局单例：_client 为 None 表示未连接或已失效
_client = None
_lock = threading.RLock()
_ids = count(1)


def _rpc_payload(response, expected_id):
    """Accept JSON and SSE responses, matching the response to its request."""
    candidates = []
    try:
        candidates.append(response.json())
    except (ValueError, TypeError):
        for block in response.text.replace("\r\n", "\n").split("\n\n"):
            data = "\n".join(line[5:].lstrip() for line in block.splitlines() if line.startswith("data:"))
            if data:
                try:
                    candidates.append(json.loads(data))
                except ValueError:
                    continue
    for payload in candidates:
        if isinstance(payload, dict) and payload.get("id") == expected_id:
            return payload
    return None


def _invalidate():
    global _client
    if _client is not None:
        _client.close()
        _client = None


def _get_client():
    """懒加载单例 httpx.Client（已含 session id 头）。并发安全；失败返回 None。"""
    global _client
    with _lock:
        if _client is not None:
            return _client
        c = None
        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            c = httpx.Client(timeout=TIMEOUT_SECONDS, headers=headers)

            # 1) initialize（响应头带 Mcp-Session-Id）
            request_id = next(_ids)
            init = c.post(MEMORA_URL, json={
                "jsonrpc": "2.0", "id": request_id, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18",
                           "capabilities": {},
                           "clientInfo": {"name": "selene", "version": "1.0"}},
            })
            init.raise_for_status()
            initialized = _rpc_payload(init, request_id)
            if not initialized or "result" not in initialized:
                raise ValueError("MCP initialize failed")
            sid = init.headers.get("Mcp-Session-Id")
            if sid:
                c.headers["Mcp-Session-Id"] = sid

            # 2) initialized 通知（单向）
            notice = c.post(MEMORA_URL, json={
                "jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
            notice.raise_for_status()

            _client = c
            return c
        except Exception as e:
            print(f"[Selene] memora connect failed: {e}")
            _client = None
            if c is not None:
                c.close()
            return None


def _call(tool_name: str, args: dict):
    """调用 memora 工具。成功返回解析后的 dict，任何失败返回 None。"""
    with _lock:
        try:
            for attempt in range(2):
                c = _get_client()
                if c is None:
                    return None
                request_id = next(_ids)
                response = c.post(MEMORA_URL, json={
                    "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                    "params": {"name": tool_name, "arguments": args},
                })
                if response.status_code != 200:
                    _invalidate()
                    # An expired session was rejected before executing the tool.
                    if response.status_code == 404 and attempt == 0:
                        continue
                    return None
                payload = _rpc_payload(response, request_id)
                if not payload or "result" not in payload:
                    _invalidate()
                    return None
                result = payload["result"]
                if result.get("isError"):
                    return None
                parsed = result.get("structuredContent")
                if parsed is None:
                    parsed = json.loads("".join(item.get("text", "") for item in result.get("content", [])))
                # ★ FastMCP 把「返回字符串」的工具结果包成 {"result": "<json字符串>"}。
                # memora 的工具全都 return json.dumps(...)，所以要再拆一层才能拿到 success/id。
                if isinstance(parsed, dict) and set(parsed) == {"result"} and isinstance(parsed["result"], str):
                    try:
                        inner = json.loads(parsed["result"])
                    except ValueError:
                        inner = None
                    if isinstance(inner, dict):
                        parsed = inner
                if not isinstance(parsed, dict) or parsed.get("success") is False:
                    return None
                return parsed
        except Exception as e:
            print(f"[Selene] memora call {tool_name} failed: {e}")
            _invalidate()
            return None


def _record_sync(content: str, importance: int, mem_type: str, event_date: str, source_key: str) -> dict | None:
    return _call("memora_record", {
        "content": content,
        "importance": importance,
        "type": mem_type,
        "event_date": event_date,
        "source": "selene",
        "source_key": source_key,
    })


def _recall_sync(query: str, days: int) -> dict | None:
    return _call("memora_recall", {"query": query, "days": days})


async def record(content: str, importance: int = 3, mem_type: str = "fact",
                 event_date: str = "", source_key: str = "") -> dict | None:
    """记一条记忆到 memora（async）。mem_type 可选 fact/feel/digest。"""
    return await asyncio.to_thread(_record_sync, content, importance, mem_type, event_date, source_key)


async def recall(query: str = "", days: int = 30) -> dict | None:
    """回看近期相关记忆（async，memora_recall，FTS5+向量混合搜索）。"""
    return await asyncio.to_thread(_recall_sync, query, days)
