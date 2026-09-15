import json
import unittest
from unittest.mock import patch

import httpx
import memora_client as client


def rpc_response(request_id, data, sse=False):
    body = {"jsonrpc": "2.0", "id": request_id,
            "result": {"content": [{"type": "text", "text": json.dumps(data)}]}}
    if sse:
        return httpx.Response(200, text="event: message\ndata: " + json.dumps(body) + "\n\n")
    return httpx.Response(200, json=body)


class ClientTests(unittest.TestCase):
    def tearDown(self):
        client._invalidate()

    def test_expired_session_reinitializes_and_recovers(self):
        requests = []
        initialized = []

        def handler(request):
            payload = json.loads(request.content)
            requests.append(payload)
            if payload["method"] == "initialize":
                initialized.append(payload["id"])
                return httpx.Response(200, headers={"Mcp-Session-Id": "new"},
                                      json={"jsonrpc": "2.0", "id": payload["id"], "result": {}})
            if payload["method"] == "notifications/initialized":
                return httpx.Response(202)
            if request.headers.get("Mcp-Session-Id") != "new":
                return httpx.Response(404)
            return rpc_response(payload["id"], {"success": True, "id": 7}, sse=True)

        factory = httpx.Client
        expired = factory(transport=httpx.MockTransport(handler))
        client._client = expired
        with patch.object(client.httpx, "Client", side_effect=lambda **kw: factory(transport=httpx.MockTransport(handler), **kw)):
            self.assertEqual(client._call("memora_record", {"source_key": "stable"})["id"], 7)
        self.assertTrue(expired.is_closed)
        self.assertEqual(len(initialized), 1)
        self.assertEqual(len([r for r in requests if r["method"] == "tools/call"]), 2)

    def test_json_success_and_business_failure(self):
        responses = [{"success": True, "id": 4}, {"success": False, "message": "failed"}]
        def handler(request):
            return rpc_response(json.loads(request.content)["id"], responses.pop(0))
        client._client = httpx.Client(transport=httpx.MockTransport(handler))
        self.assertEqual(client._call("memora_record", {})["id"], 4)
        self.assertIsNone(client._call("memora_record", {}))

    def test_structured_content_string_wrapping_is_unwrapped(self):
        """线上 FastMCP 对 return json.dumps(...) 的工具，给的是
        structuredContent={"result": "<json字符串>"}。不拆这一层就读不到 success/id，
        表现为写入其实成功、但 feed_log 全记 ok=0 并每分钟重试。"""
        def handler(request):
            inner = json.dumps({"success": True, "id": 9})
            body = {"jsonrpc": "2.0", "id": json.loads(request.content)["id"],
                    "result": {"structuredContent": {"result": inner},
                               "content": [{"type": "text", "text": inner}]}}
            return httpx.Response(200, json=body)
        client._client = httpx.Client(transport=httpx.MockTransport(handler))
        self.assertEqual(client._call("memora_record", {})["id"], 9)

    def test_structured_content_plain_dict_passes_through(self):
        """structuredContent 本身已是扁平 dict 时不能被误拆。"""
        def handler(request):
            body = {"jsonrpc": "2.0", "id": json.loads(request.content)["id"],
                    "result": {"structuredContent": {"success": True, "id": 11}}}
            return httpx.Response(200, json=body)
        client._client = httpx.Client(transport=httpx.MockTransport(handler))
        self.assertEqual(client._call("memora_record", {})["id"], 11)

    def test_timeout_is_not_replayed_in_same_call(self):
        requests = []
        def handler(request):
            requests.append(request)
            raise httpx.ReadTimeout("simulated timeout")
        old = httpx.Client(transport=httpx.MockTransport(handler))
        client._client = old
        self.assertIsNone(client._call("memora_record", {"source_key": "same-on-retry"}))
        self.assertEqual(len(requests), 1)
        self.assertTrue(old.is_closed)
        self.assertIsNone(client._client)

    def test_outbound_origin_and_key_are_transmitted(self):
        with patch.object(client, "_call", return_value={"success": True, "id": 3}) as call:
            client._record_sync("care", 5, "feel", "2026-09-11", "unique")
        args = call.call_args.args[1]
        self.assertEqual(args["source"], "selene")
        self.assertEqual(args["source_key"], "unique")


if __name__ == "__main__":
    unittest.main()
