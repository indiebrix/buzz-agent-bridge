"""Operator commands use existing peer-authenticated IPC and broker guards."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest

from test_buzz_durable_jobs import Fixture, FakeTransport, CHANNEL, SENTINEL
from buzz_agent_bridge.diagnostics import audit, snapshot, delivery_proof
from buzz_agent_bridge.ipc import LocalClient, LocalServer
from buzz_agent_bridge.transports import CliTransport
from buzz_agent_bridge.crypto import verify_nostr


class OperatorTests(Fixture, unittest.TestCase):
    def setUp(self):
        self.setup_fixture()
        self.broker.own_pubkey = self.agent.pubkey
        self.server = LocalServer(self.directory / "ipc/socket", self.broker)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = LocalClient(self.directory / "ipc/socket")

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        self.teardown_fixture()

    def test_local_diagnostics_are_metadata_only(self):
        self.admit()
        result = self.client.call("diagnostics", {})
        self.assertEqual(result["dispatch"], {"pending": 1})
        self.assertEqual(result["job_count"], 1)
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertNotIn("source", result)
        self.assertFalse(result["credentials_checked"])

    def test_resume_over_ipc_preserves_same_generation_and_one_attempt(self):
        ident = self.admit()
        self.allowed = False
        self.broker.drain_one("wake", FakeTransport())
        self.allowed = True
        args = {"request_id": ident, "generation": 1}
        result = self.client.call("resume_blocked_wake", args)
        self.assertEqual((result["request_id"], result["generation"], result["dispatch"]), (ident, 1, "pending"))
        with self.assertRaises(RuntimeError): self.client.call("resume_blocked_wake", args)
        sender = FakeTransport()
        self.broker.drain_one("wake", sender)
        self.assertEqual(len(sender.calls), 1)

    def test_real_cli_status_checks_configured_identity(self):
        config = Path(self.temp.name) / "config.json"
        value = {"relay_url": "https://relay.example.invalid", "owner_pubkey": self.owner.pubkey,
                 "agent_pubkey": self.agent.pubkey, "channel": CHANNEL, "principal": "dot",
                 "state_directory": str(self.directory), "buzz_cli": sys.executable,
                 "provider": "chatgpt-dot", "mcp_port": 18302}
        config.write_text(json.dumps(value)); config.chmod(0o600)
        run = lambda: subprocess.run([sys.executable, "-m", "buzz_agent_bridge.cli", "status", "--config", str(config)],
                                    capture_output=True, text=True, timeout=10)
        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["host"], "running")
        value["agent_pubkey"] = "ab" * 32
        config.write_text(json.dumps(value))
        self.assertNotEqual(run().returncode, 0)

    def test_audit_omits_arbitrary_payload_and_exception_text(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            audit({"event": "relay_authorization_failed", "stage": "http_429", "count": 0,
                   "secret": "synthetic secret", "state": "https://private.example.invalid/value"})
        self.assertEqual(json.loads(output.getvalue()), {
            "event": "relay_authorization_failed", "stage": "http_429", "count": 0})

    def proof_fixture(self):
        source = self.event()
        ident = self.admit([source])
        self.broker.complete("dot", ident, 1, "Synthetic verified response", "succeeded")
        reply = self.agent({"kind": 9, "created_at": self.clock, "content": "Synthetic verified response",
                            "tags": [["h", CHANNEL], ["e", source, "", "reply"]]})
        self.events[reply["id"]] = reply
        self.broker.drain_one("response", FakeTransport({"accepted": True,
            "event_id": reply["id"], "signed_readback": True}))
        publisher = CliTransport("/unused", CHANNEL, self.agent.pubkey, lambda: {},
            lambda ident: [self.events[ident]], verify_nostr)
        return ident, reply, publisher

    def test_delivery_proof_refetches_signed_receipt_without_job_mutation(self):
        ident, reply, publisher = self.proof_fixture()
        before = self.ledger.rows("jobs")
        self.server.delivery_proof = lambda request_id, generation: delivery_proof(
            self.broker, publisher, lambda filters: [reply], request_id, generation)
        result = self.client.call("delivery_proof", {"request_id": ident, "generation": 1})
        self.assertEqual(result["matching_reply_count"], 1)
        self.assertTrue(result["signed_relay_readback"])
        self.assertFalse(result["message_published_by_verifier"])
        self.assertEqual(self.ledger.rows("jobs"), before)

    def test_delivery_proof_rejects_forged_or_duplicate_readback(self):
        ident, reply, publisher = self.proof_fixture()
        unrelated = self.agent({"kind": 9, "created_at": self.clock + 1,
                               "content": reply["content"], "tags": [["h", CHANNEL]]})
        result = delivery_proof(self.broker, publisher, lambda _: [reply, unrelated], ident, 1)
        self.assertEqual(result["matching_reply_count"], 1)
        forged = {**reply, "content": "changed"}
        with self.assertRaises(ValueError):
            delivery_proof(self.broker, publisher, lambda _: [forged], ident, 1)
        duplicate = self.agent({"kind": 9, "created_at": self.clock + 1,
                               "content": reply["content"], "tags": reply["tags"]})
        with self.assertRaises(ValueError):
            delivery_proof(self.broker, publisher, lambda _: [reply, duplicate], ident, 1)


if __name__ == "__main__": unittest.main()
