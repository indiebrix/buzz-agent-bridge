"""Local IPC/stdio/crash integration only. No production credential or relay."""
import contextlib
import http.client
import json
import os
from pathlib import Path
import queue
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from test_buzz_durable_jobs import (
    Fixture, FakeTransport, CHANNEL, NOW, SENTINEL, SCRIPTS, frame,
    Ledger, LocalServer, LocalClient, Application, verify_nostr,
)
from buzz_agent_bridge import VERSION
from buzz_agent_bridge.broker import outbox_id

FRONTEND = Path(__file__).parent / "fixtures/frontend.py"
BUZZ = Path(os.environ.get("BUZZ_ACP_BINARY", "/nonexistent/buzz-acp"))


@contextlib.contextmanager
def ipc_server(broker, root):
    server = LocalServer(root / "ipc" / "socket", broker)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield server, LocalClient(server.path)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


class Wire:
    def __init__(self, path):
        self.proc = subprocess.Popen(
            [sys.executable, str(FRONTEND), "--socket", str(path)],
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1)
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.counter = 0
        self.updates = []

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(json.loads(line))

    def send(self, method, params, ident=None):
        data = {"jsonrpc": "2.0", "method": method, "params": params}
        if ident is not None:
            data["id"] = ident
        self.proc.stdin.write(json.dumps(data) + "\n")
        self.proc.stdin.flush()

    def reply(self, ident, timeout=5):
        until = time.monotonic() + timeout
        while True:
            row = self.lines.get(timeout=max(.01, until - time.monotonic()))
            if row.get("id") == ident:
                return row
            self.updates.append(row)

    def call(self, method, params):
        self.counter += 1
        self.send(method, params, self.counter)
        return self.reply(self.counter)

    def session(self):
        self.assertion = self.call("initialize", {"protocolVersion": 2, "clientCapabilities": {}})
        assert self.assertion["result"]["protocolVersion"] == 1
        return self.call("session/new", {"cwd": "/tmp", "mcpServers": []})["result"]["sessionId"]

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)
        self.reader.join(2)
        errors = self.proc.stderr.read()
        self.proc.stdout.close()
        self.proc.stderr.close()
        return errors


class IPCTests(Fixture, unittest.TestCase):
    def setUp(self): self.setup_fixture()
    def tearDown(self): self.teardown_fixture()

    def test_same_uid_permissions_version_and_no_remote_controls(self):
        with ipc_server(self.broker, Path(self.temp.name)) as (server, client):
            self.assertEqual(server.path.stat().st_mode & 0o777, 0o600)
            result = client.call("admit", {"source_ids": [self.event()], "session_id": "s",
                                          "admission_id": uuid.uuid4().hex, "jsonrpc_id": 12})
            self.assertTrue(result["durably_accepted"])
            with self.assertRaises(RuntimeError):
                client.call("cancel", {"request_id": result["jobs"][0]["request_id"]})
            with socket.socket(socket.AF_UNIX) as connection:
                connection.connect(str(server.path))
                connection.sendall(json.dumps({"version": "wrong", "id": "1",
                    "method": "status", "args": {}}).encode() + b"\n")
                with connection.makefile("rb") as stream:
                    reply = stream.readline()
                self.assertIn(b"request_rejected", reply)
            with patch("buzz_agent_bridge.ipc.peer_uid", return_value=os.getuid() + 1):
                with self.assertRaises(PermissionError): client.call("status", {"ids": []})

    def test_real_sdk_admission_50_context_duplicate_and_frontend_exit(self):
        ids = [self.event(index) for index in range(50)]
        with ipc_server(self.broker, Path(self.temp.name)) as (server, client):
            wire = Wire(server.path)
            try:
                session = wire.session()
                context = "<thread-context>\n" + frame(["f" * 64]) + "\n</thread-context>"
                response = wire.call("session/prompt", {"sessionId": session, "prompt": [
                    {"type": "text", "text": context}, {"type": "text", "text": frame(ids)}]})
                self.assertEqual(response["result"]["stopReason"], "end_turn")
                self.assertEqual(len(self.ledger.rows("jobs")), 50)
                self.assertTrue(all(row["execution"] == "accepted" and row["delivery"] == "waiting"
                                    for row in self.ledger.rows("jobs")))
                self.assertEqual(self.ledger.rows("jobs")[0]["acp"][0]["jsonrpc_id"], 3)
                again = wire.call("session/prompt", {"sessionId": session, "prompt": [
                    {"type": "text", "text": frame(ids)}]})
                self.assertEqual(again["result"]["stopReason"], "end_turn")
                self.assertEqual(len(self.ledger.rows("outbox")), 50)
                self.assertNotIn(SENTINEL, json.dumps(wire.updates))
            finally:
                self.assertNotIn(SENTINEL, wire.close())
            # Closing ACP stdio did not cancel the already admitted remote jobs.
            self.assertTrue(all(not row["cancel_requested"] for row in self.ledger.rows("jobs")))

    def test_sdk_cancel_during_validation_and_after_admission(self):
        entered, release = threading.Event(), threading.Event()
        original = self.broker.fetch
        def fetch(ident):
            entered.set()
            release.wait(3)
            return original(ident)
        self.broker.fetch = fetch
        with ipc_server(self.broker, Path(self.temp.name)) as (server, _):
            wire = Wire(server.path)
            try:
                session = wire.session()
                wire.send("session/prompt", {"sessionId": session,
                    "prompt": [{"type": "text", "text": frame([self.event()])}]}, 30)
                self.assertTrue(entered.wait(2))
                wire.send("session/cancel", {"sessionId": session})
                # Observe cancellation at the broker before releasing source read.
                until = time.monotonic() + 2
                while not any(row["cancel"].is_set() for row in self.broker.admissions.values()):
                    self.assertLess(time.monotonic(), until)
                    time.sleep(.01)
                release.set()
                self.assertEqual(wire.reply(30)["result"]["stopReason"], "cancelled")
                self.assertEqual(self.ledger.rows("jobs"), [])
                self.broker.fetch = original
                wire.send("session/prompt", {"sessionId": session,
                    "prompt": [{"type": "text", "text": frame([self.event(1)])}]}, 31)
                until = time.monotonic() + 2
                while not self.ledger.rows("jobs"):
                    self.assertLess(time.monotonic(), until)
                    time.sleep(.005)
                wire.send("session/cancel", {"sessionId": session})
                self.assertEqual(wire.reply(31)["result"]["stopReason"], "cancelled")
                self.assertFalse(self.ledger.rows("jobs")[0]["cancel_requested"])
            finally:
                release.set()
                self.assertNotIn(SENTINEL, wire.close())

    @unittest.skipUnless(BUZZ.exists(), "Installed mini Buzz contract is a separate host gate")
    def test_installed_buzz_acp_runs_real_sdk_to_durable_admission(self):
        from coincurve import PrivateKey
        fixture = (1).to_bytes(32, "big")  # Public scalar-one fixture; never admitted to relay.
        public = PrivateKey(fixture).public_key_xonly.format().hex()
        with ipc_server(self.broker, Path(self.temp.name)) as (server, _):
            cmd = [str(BUZZ), "run", "--task", "-", "--relay-url", "ws://127.0.0.1:9",
                   "--agent-command", sys.executable, "--agent-args",
                   f"{FRONTEND},--socket,{server.path}", "--no-memory", "--no-base-prompt",
                   "--permission-mode", "default", "--idle-timeout", "5", "--max-turn-duration", "15"]
            result = subprocess.run(cmd, input=json.dumps({"version": 1, "taskId": "durable-local",
                "agentPubkey": public, "prompt": frame([self.event()]), "maxDurationMs": 12000}),
                env={"PATH": "/usr/bin:/bin", "BUZZ_PRIVATE_KEY": fixture.hex(), "RUST_LOG": "error"},
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, "Installed ACP run failed; output suppressed")
            self.assertEqual(json.loads(result.stdout)["stopReason"], "end_turn")
            self.assertEqual(len(self.ledger.rows("jobs")), 1)
            self.assertEqual(self.ledger.rows("jobs")[0]["execution"], "accepted")
            self.assertNotIn(SENTINEL, result.stderr)


class CrashTests(Fixture, unittest.TestCase):
    def setUp(self): self.setup_fixture()
    def tearDown(self): self.teardown_fixture()

    def child(self, code):
        env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(SCRIPTS), "PYTHONDONTWRITEBYTECODE": "1"}
        return subprocess.Popen([sys.executable, "-c", code, str(self.directory)],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_sigkill_after_committed_sending_recovers_uncertain_no_retry(self):
        ident = self.admit()
        self.broker.complete("dot", ident, 1, "answer", "succeeded")
        self.ledger.close()
        code = """import sys,time
from buzz_agent_bridge.ledger import Ledger
from buzz_agent_bridge.crypto import AEADCodec
c=AEADCodec(bytes(range(32)))
l=Ledger(sys.argv[1],c.seal,c.open)
with l.transaction():
    row=next(e for e in l.rows('outbox') if e['stage']=='response')
    row['state']='sending'
    l.put('outbox',row['id'],row)
print('committed',flush=True)
time.sleep(20)
"""
        process = self.child(code)
        try:
            self.assertEqual(process.stdout.readline().strip(), "committed")
            process.kill()
            process.wait(3)
            self.ledger = self.new_ledger()
            self.broker = self.new_broker()
            transport = FakeTransport()
            self.assertIsNone(self.broker.drain_one("response", transport))
            self.assertEqual(self.ledger.get("jobs", ident)["delivery"], "uncertain")
            self.assertEqual(transport.calls, [])
        finally:
            if process.poll() is None: process.kill()
            process.communicate(timeout=3)

    def test_surviving_cli_child_keeps_exclusive_lease_after_broker_killed(self):
        self.ledger.close()
        code = """import subprocess,sys,time
from buzz_agent_bridge.ledger import Ledger
from buzz_agent_bridge.crypto import AEADCodec
c=AEADCodec(bytes(range(32)))
l=Ledger(sys.argv[1],c.seal,c.open)
p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'],
    pass_fds=(l.lock_fd,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print(p.pid,flush=True)
time.sleep(20)
"""
        process = self.child(code)
        child_pid = None
        try:
            child_pid = int(process.stdout.readline().strip())
            process.kill()
            process.wait(3)
            with self.assertRaises(BlockingIOError): self.new_ledger()
            os.kill(child_pid, signal.SIGKILL)
            child_pid = None
            deadline = time.monotonic() + 3
            while True:
                try:
                    self.ledger = self.new_ledger()
                    break
                except BlockingIOError:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.01)
        finally:
            if child_pid is not None:
                with contextlib.suppress(ProcessLookupError): os.kill(child_pid, signal.SIGKILL)
            if process.poll() is None: process.kill()
            process.communicate(timeout=3)

    def test_sigkill_uncommitted_transaction_leaves_no_outbox(self):
        self.ledger.close()
        code = """import sys,time
from buzz_agent_bridge.ledger import Ledger
from buzz_agent_bridge.crypto import AEADCodec
c=AEADCodec(bytes(range(32)))
l=Ledger(sys.argv[1],c.seal,c.open)
with l.transaction():
    l.put('controls','uncommitted',{'secret':'PRIVATE-FIXTURE-CONTENT-NOT-FOR-LOGS'})
    print('uncommitted',flush=True)
    time.sleep(20)
"""
        process = self.child(code)
        try:
            self.assertEqual(process.stdout.readline().strip(), "uncommitted")
            process.kill()
            process.wait(3)
            self.ledger = self.new_ledger()
            self.assertIsNone(self.ledger.get("controls", "uncommitted"))
            self.ledger.validate()
        finally:
            if process.poll() is None: process.kill()
            process.communicate(timeout=3)


class FullCompositionTests(Fixture, unittest.TestCase):
    def setUp(self): self.setup_fixture()
    def tearDown(self): self.teardown_fixture()

    def test_startup_bind_failure_releases_socket_and_ledger(self):
        directory = Path(self.temp.name) / "startup"
        app = Application(directory, bytes(range(32)), "dot", CHANNEL,
                          self.owner.pubkey, self.agent.pubkey, lambda _: "dot",
                          lambda p, c: True, lambda _: [], "/unused", lambda: {},
                          activation=NOW - 100, now=lambda: NOW)
        path = directory / "ipc" / "socket"
        with patch.object(app, "server", side_effect=OSError("fixture port busy")):
            with self.assertRaises(OSError):
                app.run(threading.Event(), socket_path=path, port=0)
        self.assertFalse(path.exists())
        reopened = Ledger(directory / "ledger", self.codec.seal, self.codec.open)
        reopened.close()

    def test_local_mcp_webhook_and_real_mock_cli_publish_once(self):
        source = self.event(root="a" * 64)
        reply = self.agent({"kind": 9, "created_at": NOW, "content": "synthetic final",
                           "tags": [["h", CHANNEL], ["e", "a" * 64, "", "root"], ["e", source, "", "reply"]]})
        self.events[reply["id"]] = reply
        cli = Path(self.temp.name) / "fixture-cli"
        calls = Path(self.temp.name) / "calls"
        cli.write_text(f"#!{sys.executable}\nimport json,sys\n"
                       f"from pathlib import Path\nPath({str(calls)!r}).open('a').write('called\\n')\n"
                       "body=sys.stdin.read()\n"
                       "assert body=='synthetic final'\n"
                       f"print({json.dumps({'accepted': True, 'event_id': reply['id']})!r})\n")
        cli.chmod(0o700)
        callbacks = []
        def post(url, body, headers):
            value = json.loads(body)
            if value.get("type") == "verification":
                return 200, {"challenge": value["challenge"]}
            callbacks.append(value)
            return 200, {}
        def authenticate(header):
            if header != "Bearer local-test-only":
                raise PermissionError()
            return "dot"
        app = Application(Path(self.temp.name) / "application", bytes(range(32)), "dot",
                          CHANNEL, self.owner.pubkey, self.agent.pubkey, authenticate,
                          lambda p, c: self.allowed, lambda ident: [self.events[ident]],
                          str(cli), lambda: {"PATH": "/usr/bin:/bin"},
                          activation=NOW - 100, now=lambda: NOW, post=post)
        server = app.server(0)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        def rpc(method, params):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                connection.request("POST", "/mcp", body, {"Authorization": "Bearer local-test-only",
                                                          "Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                value = json.loads(response.read())
                self.assertNotIn("error", value)
                return value["result"]
            finally:
                connection.close()
        try:
            for authorization in (None, "Bearer wrong-fixture"):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                try:
                    request_headers = {"Content-Type": "application/json"}
                    if authorization:
                        request_headers["Authorization"] = authorization
                    connection.request("POST", "/mcp", json.dumps({
                        "jsonrpc": "2.0", "id": 1, "method": "tools/list"}), request_headers)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 401)
                    self.assertNotIn(SENTINEL.encode(), response.read())
                finally:
                    connection.close()
            import base64
            rpc("events/subscribe", {"name": "buzz.message.created", "arguments": {"channel": CHANNEL},
                "delivery": {"mode": "webhook", "url": "https://callback.example/hook",
                             "secret": "whsec_" + base64.b64encode(bytes(range(32))).decode()}})
            with ipc_server(app.broker, Path(self.temp.name) / "app-socket") as (_, client):
                accepted = client.call("admit", {"source_ids": [source], "session_id": "local",
                    "admission_id": uuid.uuid4().hex, "jsonrpc_id": 700})
            ident = accepted["jobs"][0]["request_id"]
            app.broker.drain_one("wake", app.wake)
            self.assertEqual(len(callbacks), 1)
            pending = rpc("tools/call", {"name": "buzz_jobs_pending", "arguments": {}})
            self.assertEqual(pending["structuredContent"]["jobs"][0]["source"]["message_id"], source)
            arguments = {"request_id": ident, "generation": 1, "text": "synthetic final",
                         "outcome": "succeeded", "route": "thread"}
            result = rpc("tools/call", {"name": "buzz_job_complete", "arguments": arguments})
            self.assertEqual(result["structuredContent"]["delivery"], "queued")
            app.broker.drain_one("response", app.publisher)
            rpc("tools/call", {"name": "buzz_job_complete", "arguments": arguments})
            app.broker.drain_one("response", app.publisher)
            status = rpc("tools/call", {"name": "buzz_job_status", "arguments": {"request_ids": [ident]}})
            self.assertEqual(status["structuredContent"]["jobs"][0]["delivery"], "delivered")
            self.assertEqual(status["structuredContent"]["jobs"][0]["event_id"], reply["id"])
            self.assertEqual(calls.read_text().splitlines(), ["called"])
            self.assertTrue(any(row.get("child_pid") for row in app.ledger.rows("outbox")))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)
            app.close()


if __name__ == "__main__":
    unittest.main()
