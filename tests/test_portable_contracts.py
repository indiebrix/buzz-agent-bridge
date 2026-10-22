"""Executable source/provider and upgrade contracts using public fixtures only."""
import ast
from dataclasses import FrozenInstanceError, replace
import hashlib
import inspect
import json
from pathlib import Path
import unittest
import uuid
from unittest.mock import Mock

from buzz_agent_bridge.core.broker import Broker, NotReady, request_id
from buzz_agent_bridge.core.contracts import VerifiedSource
from buzz_agent_bridge.adapters.buzz.source import thread_root
from buzz_agent_bridge.transports import CliTransport
from test_buzz_durable_jobs import Fixture, FakeTransport, CHANNEL, NOW


class PortableContracts(Fixture, unittest.TestCase):
    def setUp(self): self.setup_fixture()
    def tearDown(self): self.teardown_fixture()

    def test_unsigned_response_receipt_stays_uncertain_and_is_not_retried(self):
        for proof in (None, False, 1, "true"):
            with self.subTest(proof=proof):
                ident = self.admit([self.event(len(self.ledger.rows('jobs')))])
                self.broker.complete("dot", ident, 1, "answer", "succeeded")
                receipt = {"accepted": True, "event_id": "c" * 64}
                if proof is not None:
                    receipt["signed_readback"] = proof
                transport = FakeTransport(receipt)
                self.assertEqual(self.broker.drain_one("response", transport), {"state": "uncertain"})
                self.assertIsNone(self.broker.drain_one("response", transport))
                self.assertEqual(len(transport.calls), 1)
                self.assertIsNone(self.broker.status("dot", [ident])["jobs"][0]["event_id"])

    def test_non_nostr_source_policy_runs_lifecycle_and_rechecks_revocation(self):
        ident = hashlib.sha256(b"synthetic-provider-object-1").hexdigest()
        source = VerifiedSource(ident, self.owner.pubkey, CHANNEL, "independent evidence", NOW, ident)
        with self.assertRaises(FrozenInstanceError):
            source.text = "tampered"
        policy = Mock()
        policy.read.return_value = source
        self.broker = Broker(self.ledger, "dot", CHANNEL, self.owner.pubkey,
            lambda p, c: self.allowed and p == "dot" and c == CHANNEL, policy,
            activation=NOW - 100, now=lambda: NOW)
        result = self.broker.admit("dot", [ident], "existing-session", uuid.uuid4().hex)
        job = result["jobs"][0]["request_id"]
        self.assertEqual(job, "job_" + hashlib.sha256(json.dumps(["dot", ident]).encode()).hexdigest())
        self.assertEqual(self.ledger.get("jobs", job)["source"], source.as_dict())
        self.broker.start("dot", job, 1, "existing-dot-execution")
        self.broker.complete("dot", job, 1, "answer", "succeeded")
        self.broker.complete("dot", job, 1, "answer", "succeeded")
        self.assertEqual(sum(x['stage']=='response' for x in self.ledger.rows('outbox')), 1)
        self.assertGreaterEqual(policy.read.call_count, 2)
        self.allowed = False
        transport = FakeTransport()
        self.assertEqual(self.broker.drain_one("response", transport), {"state": "blocked"})
        self.assertEqual(transport.calls, [])

    def test_unverified_or_rescoped_source_object_is_rejected(self):
        ident = "a" * 64
        policy = Mock()
        core = Broker(self.ledger, "dot", CHANNEL, self.owner.pubkey,
                      lambda *_: True, policy, activation=NOW - 100)
        for returned in ({"message_id": ident},
                         VerifiedSource("b" * 64, self.owner.pubkey, CHANNEL, "x", NOW, ident),
                         VerifiedSource(ident, "wrong-author", CHANNEL, "x", NOW, ident),
                         VerifiedSource(ident, self.owner.pubkey, "wrong-channel", "x", NOW, ident)):
            policy.read.return_value = returned
            with self.assertRaises((ValueError, PermissionError)):
                core.admit("dot", [ident], "s", uuid.uuid4().hex)
        self.assertEqual(self.ledger.rows("jobs"), [])

    def test_changed_or_missing_source_never_reaches_a_publisher(self):
        ident = self.admit()
        self.broker.complete("dot", ident, 1, "answer", "succeeded")
        source = self.ledger.get("jobs", ident)["source"]
        policy = Mock()
        self.broker.source_policy = policy
        transport = FakeTransport()
        policy.read.return_value = replace(VerifiedSource(**source), text="changed evidence")
        with self.assertRaises(ValueError): self.broker.drain_one("response", transport)
        policy.read.side_effect = ValueError("Source unavailable")
        with self.assertRaises(ValueError): self.broker.drain_one("response", transport)
        self.assertEqual(transport.calls, [])
        self.assertEqual(self.ledger.get("jobs", ident)["delivery"], "queued")

    def test_buzz_thread_rules_match_upstream_and_keep_strict_ambiguity_policy(self):
        target, other = "a" * 64, "b" * 64
        cases = [([], None), ([["e", target, "", "root"]], None),
                 ([["e", target, "", "reply"]], target),
                 ([["e", target, "", "root"], ["e", other, "", "reply"]], target)]
        for tags, expected in cases:
            source_id = self.event(len(self.events), tags=[["h", CHANNEL], *tags])
            source = self.broker.source("dot", source_id, new=True)
            self.assertEqual(source["thread_root"], expected or source_id)
        for tags in ([["e", "bad", "", "reply"]],
                     [["e", target, "", "root"], ["e", other, "", "root"]]):
            source_id = self.event(len(self.events), tags=[["h", CHANNEL], *tags])
            with self.assertRaises(ValueError): self.broker.source("dot", source_id)

    def test_schema2_root_only_snapshot_uses_fresh_routing_without_rewriting_history(self):
        source_id = self.event(tags=[["h", CHANNEL], ["e", "a" * 64, "", "root"]])
        ident = self.admit([source_id])
        self.broker.complete("dot", ident, 1, "answer", "succeeded")
        legacy = self.ledger.get("jobs", ident)
        legacy["source"]["thread_root"] = "a" * 64  # Literal 0.2.0 normalized shape.
        with self.ledger.transaction(): self.ledger.put("jobs", ident, legacy)
        self.reopen()  # Reopen actual encrypted schema-2 database.
        transport = FakeTransport(error=TimeoutError())
        self.broker.drain_one("response", transport)
        self.assertEqual(transport.calls[0]["job"]["source"]["thread_root"], source_id)
        self.assertEqual(self.ledger.get("jobs", ident)["source"], legacy["source"])
        self.assertIsNone(self.broker.drain_one("response", transport))
        reply = self.agent({"kind": 9, "created_at": NOW, "content": "answer",
            "tags": [["h", CHANNEL], ["e", source_id, "", "reply"]]})
        self.events[reply["id"]] = reply
        publisher = CliTransport("/unused", CHANNEL, self.agent.pubkey,
            lambda: self.fail("Reconciliation must not acquire signing credentials"),
            lambda i: [self.events[i]], self.broker.verify,
            popen=lambda *_a, **_k: self.fail("Reconciliation must not send"))
        result = self.broker.reconcile_delivery("dot", ident, 1, reply["id"], publisher)
        self.assertEqual(result["delivery"], "delivered")
        self.assertEqual(self.ledger.get("jobs", ident)["source"], legacy["source"])

    def test_compatibility_exports_and_core_import_direction(self):
        from buzz_agent_bridge.broker import NotReady as LegacyNotReady
        from buzz_agent_bridge.events import Events, thread_root as LegacyRoot
        from buzz_agent_bridge.adapters.chatgpt.events import Events as CurrentEvents
        from buzz_agent_bridge.transports import WebhookTransport
        from buzz_agent_bridge.adapters.chatgpt.wake import WebhookTransport as CurrentWake
        self.assertIs(LegacyNotReady, NotReady)
        self.assertIs(LegacyRoot, thread_root)
        self.assertIs(Events, CurrentEvents)
        self.assertIs(WebhookTransport, CurrentWake)
        root = Path(inspect.getfile(Broker)).parent
        for file in root.glob('*.py'):
            tree = ast.parse(file.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertLessEqual(node.level, 1)
                    self.assertNotIn((node.module or '').split('.')[0],
                                     {'buzz_agent_bridge', 'acp', 'coincurve'})
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split('.')[0],
                                         {'buzz_agent_bridge', 'acp', 'coincurve'})


if __name__ == '__main__': unittest.main()
