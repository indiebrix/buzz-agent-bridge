"""Executable non-Buzz integration check. Synthetic callback, real loopback MCP.

Run with only chatgpt-dots-connector installed. No provider account, credential,
Buzz import or external network is used. This is protocol evidence, not a live
Dot acceptance test or a production build service.
"""
import base64
import hashlib
import hmac
import http.client
import json
import secrets
import threading

from chatgpt_dots.definition import EventDefinition
from chatgpt_dots.delivery import Delivery
from chatgpt_dots.events import Subscriptions
from chatgpt_dots.http import BearerAuth, RPC, http_server


def exercise():
    definition = EventDefinition.string_fields(
        "build.finished", "A build is ready for review.", "project", ("build_id", "result", "summary"))
    clock = lambda: 1800000000
    authorize = lambda principal, scope: principal == "reviewer" and scope == "sample-project"
    store, received, completed = {}, [], {}
    lock = threading.RLock()
    signing_key = secrets.token_bytes(32)
    bearer = secrets.token_urlsafe(32)

    def callback(url, body, headers):
        assert url == "https://callback.example.invalid/events"
        signed = headers["webhook-id"].encode() + b"." + headers["webhook-timestamp"].encode() + b"." + body
        signature = "v1," + base64.b64encode(hmac.new(signing_key, signed, hashlib.sha256).digest()).decode()
        assert hmac.compare_digest(signature, headers["webhook-signature"])
        value = json.loads(body)
        if value.get("type") == "verification":
            return 200, {"challenge": value["challenge"]}
        assert value["name"] == "build.finished" and value["data"]["build_id"] == "42"
        received.append(value)
        return 202, {}

    def tools(principal, method, params):
        if not authorize(principal, "sample-project"):
            raise PermissionError("Scope denied")
        if method == "tools/list":
            return {"tools": [{"name": "build_review", "description": "Record a review for build 42.",
                "inputSchema": {"type": "object", "properties": {
                    "build_id": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["build_id", "text"], "additionalProperties": False}}]}
        args = params.get("arguments", {})
        if (method != "tools/call" or params.get("name") != "build_review"
                or set(args) != {"build_id", "text"} or args["build_id"] != "42"
                or not isinstance(args["text"], str) or not 1 <= len(args["text"]) <= 1000
                or not received):
            raise ValueError("Review rejected")
        if completed and completed != args:
            raise ValueError("Conflicting completion")
        completed.update(args)
        return {"content": [{"type": "text", "text": "Review recorded."}],
                "structuredContent": {"build_id": "42", "recorded": True}}

    subscriptions = Subscriptions(definition, store, authorize, callback, clock)
    rpc = RPC(subscriptions, tools)
    class LockedRPC:
        def __call__(self, *args):
            with lock:
                return rpc(*args)
    hosts = set()
    server = http_server(("127.0.0.1", 0), LockedRPC(),
        BearerAuth({hashlib.sha256(bearer.encode()).hexdigest(): "reviewer"}), hosts)
    hosts.add(f"127.0.0.1:{server.server_port}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def call(method, params, token=bearer):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            connection.request("POST", "/mcp", json.dumps({"jsonrpc": "2.0", "id": 1,
                "method": method, "params": params}), {"Content-Type": "application/json",
                "Authorization": "Bearer " + token})
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
        finally:
            connection.close()
    try:
        assert call("events/list", {}, "wrong")[0] == 401
        status, discovery = call("server/discover", {})
        assert status == 200 and set(discovery["result"]["capabilities"]) == {"tools", "events"}
        assert call("tools/list", {})[1]["result"]["tools"][0]["name"] == "build_review"
        params = {"name": definition.name, "arguments": {"project": "sample-project"},
                  "delivery": {"mode": "webhook", "url": "https://callback.example.invalid/events",
                               "secret": "whsec_" + base64.b64encode(signing_key).decode()}}
        assert "result" in call("events/subscribe", params)[1]
        delivery = Delivery(definition, store, callback, authorize, clock, lock)
        event = definition.event("build-42", clock(),
            {"build_id": "42", "result": "passed", "summary": "Synthetic build complete"})
        receipt = delivery.send(delivery.prepare("reviewer", "sample-project", event))
        assert receipt == {"accepted": True, "http_status": 202} and len(received) == 1
        assert not completed  # A callback ACK did not complete the work.
        assert call("tools/call", {"name": "build_review", "arguments": {
            "build_id": "42", "text": "Synthetic review complete"}})[1]["result"]["structuredContent"]["recorded"]
        assert "result" in call("events/unsubscribe", params)[1] and not store
        return {"non_buzz_integration": "passed", "authenticated_loopback": True,
                "event": "build.finished", "scope": "project", "custom_tool": "build_review",
                "callback_signature_verified": True, "remote_dot_acceptance": False}
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    print(json.dumps(exercise(), sort_keys=True))
