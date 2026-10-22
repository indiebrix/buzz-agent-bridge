"""Encrypted durable-job tests. Synthetic identities; no external relay or model."""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import Mock, patch

if os.name != "posix" or any(importlib.util.find_spec(name) is None
                            for name in ("acp", "cryptography", "coincurve")):
    raise unittest.SkipTest("Optional Unix Buzz runtime gate requires the role's crypto and ACP dependencies")

SCRIPTS = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SCRIPTS))
from buzz_agent_bridge.crypto import AEADCodec, NostrSigner, verify_nostr
from buzz_agent_bridge import VERSION
from buzz_agent_bridge.broker import Broker, AdmissionCancelled, NotReady, outbox_id
from buzz_agent_bridge.ledger import Ledger
from buzz_agent_bridge.framing import source_ids
from buzz_agent_bridge.ipc import LocalClient, LocalServer
from buzz_agent_bridge.frontend import Frontend
from buzz_agent_bridge.transports import CliTransport, WebhookTransport
from buzz_agent_bridge.tools import JobTools
from buzz_agent_bridge.application import Application
from acp import text_block
from acp.connection import StreamDirection, StreamEvent

CHANNEL = "00000000-0000-4000-8000-000000000001"
NOW = 1800000000
SENTINEL = "PRIVATE-FIXTURE-CONTENT-NOT-FOR-LOGS"


def frame(ids, tag=None):
    if len(ids) == 1 and tag is None:
        return f'<buzz-event type="@mention">\nEvent ID: {ids[0]}\nContent: ignored\n</buzz-event>'
    tag = tag or "buzz-events"
    body = "\n\n".join(f"--- Event {i} (@mention) ---\nEvent ID: {ident}\nContent: ignored"
                       for i, ident in enumerate(ids, 1))
    return f'<{tag} count="{len(ids)}">\n{body}\n</{tag}>'


class Fixture:
    def setup_fixture(self):
        self.temp = tempfile.TemporaryDirectory(prefix="abj-", dir="/tmp")
        self.directory = Path(self.temp.name) / "state"
        self.codec = AEADCodec(bytes(range(32)))  # Public test fixture, no vault.
        self.owner = NostrSigner(bytes([2]) * 32)
        self.agent = NostrSigner(bytes([1]) * 32)
        self.clock, self.allowed, self.events, self.audit = NOW, True, {}, []
        self.ledger = self.new_ledger()
        self.broker = self.new_broker()

    def teardown_fixture(self):
        self.ledger.close()
        self.temp.cleanup()

    def new_ledger(self, **kwargs):
        return Ledger(self.directory, self.codec.seal, self.codec.open, **kwargs)

    def new_broker(self):
        return Broker(self.ledger, "dot", CHANNEL, self.owner.pubkey,
                      lambda principal, channel: self.allowed and principal == "dot" and channel == CHANNEL,
                      lambda ident: [self.events[ident]] if ident in self.events else [],
                      verify_nostr, activation=NOW - 100, now=lambda: self.clock, audit=self.audit.append)

    def event(self, index=0, root=None, **changes):
        tags = [["h", CHANNEL]]
        if root:
            tags += [["e", root, "", "root"], ["e", root, "", "reply"]]
        event = self.owner({"kind": 9, "created_at": self.clock,
                            "content": f"{SENTINEL}-{index}", "tags": tags, **changes})
        self.events[event["id"]] = event
        return event["id"]

    def admit(self, ids=None, session="session", **kwargs):
        ids = ids or [self.event()]
        result = self.broker.admit("dot", ids, session, uuid.uuid4().hex, jsonrpc_id=42, **kwargs)
        return result["jobs"][0]["request_id"]

    def reopen(self, **kwargs):
        self.ledger.close()
        self.ledger = self.new_ledger(**kwargs)
        self.broker = self.new_broker()


class FakeTransport:
    def __init__(self, receipt=None, error=None):
        self.calls = []
        self.receipt = receipt or {"accepted": True, "event_id": "c" * 64, "signed_readback": True}
        self.error = error

    def prepare(self, job, entry):
        return {"destination": "fixture", "job": job, "entry": entry}

    def send(self, plan, lease_fd):
        self.calls.append(plan)
        if self.error:
            raise self.error
        return self.receipt


class LedgerTests(Fixture, unittest.TestCase):
    def setUp(self): self.setup_fixture()
    def tearDown(self): self.teardown_fixture()

    def test_encrypted_storage_modes_row_binding_and_exclusive_owner(self):
        self.admit()
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.directory / "jobs.sqlite3").stat().st_mode), 0o600)
        self.assertNotIn(SENTINEL.encode(), (self.directory / "jobs.sqlite3").read_bytes())
        with self.assertRaises(BlockingIOError): self.new_ledger()
        self.ledger.db.execute("UPDATE outbox SET payload=(SELECT payload FROM jobs LIMIT 1)")
        with self.assertRaises(ValueError): self.ledger.rows("outbox")

    def test_transaction_rollback_wrong_cipher_and_future_schema_rejected(self):
        with self.assertRaises(RuntimeError):
            with self.ledger.transaction():
                self.ledger.put("controls", "fixture", {"secret": SENTINEL})
                raise RuntimeError()
        self.assertIsNone(self.ledger.get("controls", "fixture"))
        self.admit()
        self.ledger.close()
        other = AEADCodec(bytes(reversed(range(32))))
        with self.assertRaises(Exception): Ledger(self.directory, other.seal, other.open)
        self.ledger = self.new_ledger()
        self.ledger.db.execute("PRAGMA user_version=99")
        self.ledger.close()
        with self.assertRaises(ValueError): self.new_ledger()

    def test_migration_backup_and_explicit_restore_quarantine(self):
        ident = self.admit()
        self.ledger.db.execute("DROP TABLE controls")
        self.ledger.db.execute("PRAGMA user_version=1")
        self.reopen()
        backup = self.directory / "before-schema-2.sqlite3"
        self.assertTrue(backup.exists())
        self.assertEqual(self.ledger.db.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertNotIn(SENTINEL.encode(), backup.read_bytes())
        self.broker.complete("dot", ident, 1, "answer", "succeeded")
        snapshot = Path(self.temp.name) / "snapshot" / "jobs.sqlite3"
        self.ledger.backup(snapshot)
        self.ledger.close()
        shutil.copyfile(snapshot, self.directory / "jobs.sqlite3")
        self.ledger = self.new_ledger(restored=True)
        self.broker = self.new_broker()
        job = self.ledger.get("jobs", ident)
        self.assertTrue(job["quarantined"])
        self.assertEqual(job["generation"], 2)
        with self.assertRaises(ValueError):
            self.broker.complete("dot", ident, 1, "late", "succeeded")
        transport = FakeTransport()
        self.assertIsNone(self.broker.drain_one("response", transport))
        self.assertEqual(transport.calls, [])

    def test_insecure_directory_and_symlink_fail_closed(self):
        wrong = Path(self.temp.name) / "world"
        wrong.mkdir(mode=0o755)
        wrong.chmod(0o755)  # Explicit fixture, independent of the process umask.
        with self.assertRaises(PermissionError): Ledger(wrong, self.codec.seal, self.codec.open)
        link = Path(self.temp.name) / "link"
        link.symlink_to(self.directory)
        with self.assertRaises(PermissionError): Ledger(link, self.codec.seal, self.codec.open)


class BrokerTests(Fixture, unittest.TestCase):
    def setUp(self): self.setup_fixture()
    def tearDown(self): self.teardown_fixture()

    def test_atomic_batch_50_source_dedup_and_separate_correlation_ids(self):
        ids = [self.event(i) for i in range(50)]
        first = self.broker.admit("dot", ids, "session-one", uuid.uuid4().hex, jsonrpc_id="rpc-7")
        second = self.broker.admit("dot", ids, "session-two", uuid.uuid4().hex, jsonrpc_id=9)
        self.assertEqual(first["jobs"], second["jobs"])
        self.assertEqual(len(self.ledger.rows("jobs")), 50)
        self.assertEqual(len(self.ledger.rows("outbox")), 50)
        row = self.ledger.rows("jobs")[0]
        self.assertNotEqual(row["request_id"], row["source"]["message_id"])
        self.assertEqual([item["session_id"] for item in row["acp"]], ["session-one", "session-two"])
        self.assertIsNone(row["dot_job_id"])
        self.assertFalse(first["remote_work_complete"])

    def test_invalid_last_source_rolls_back_entire_batch(self):
        ids = [self.event(i) for i in range(49)] + ["f" * 64]
        with self.assertRaises(ValueError): self.admit(ids)
        self.assertEqual(self.ledger.rows("jobs"), [])
        self.assertEqual(self.ledger.rows("outbox"), [])

    def test_exact_author_signature_channel_time_scope_and_capacity(self):
        ident = self.event()
        original = self.events[ident]
        for bad in ({**original, "content": "tampered"},
                    self.agent({"kind": 9, "created_at": NOW, "content": "sibling", "tags": [["h", CHANNEL]]}),
                    self.owner({"kind": 9, "created_at": NOW, "content": "other", "tags": [["h", "other"]]}),
                    self.owner({"kind": 9, "created_at": NOW - 101, "content": "old", "tags": [["h", CHANNEL]]}),
                    self.owner({"kind": 9, "created_at": NOW + 61, "content": "future", "tags": [["h", CHANNEL]]})):
            self.events[bad["id"]] = bad
            with self.assertRaises((ValueError, PermissionError)): self.admit([bad["id"]])
        self.events[ident] = original
        self.broker.capacity = 0
        with self.assertRaises(ValueError): self.admit([ident])
        with self.assertRaises(PermissionError):
            self.broker.admit("sibling", [ident], "session", uuid.uuid4().hex)

    def test_cancel_admission_before_commit_and_after_commit_are_different(self):
        ident = self.event()
        admission = uuid.uuid4().hex
        entered, release = threading.Event(), threading.Event()
        original_fetch = self.broker.fetch
        def fetch(ident):
            entered.set()
            release.wait(2)
            return original_fetch(ident)
        self.broker.fetch = fetch
        with ThreadPoolExecutor() as pool:
            pending = pool.submit(self.broker.admit, "dot", [ident], "s", admission)
            self.assertTrue(entered.wait(1))
            self.assertFalse(self.broker.cancel_admission(admission)["durably_accepted"])
            release.set()
            with self.assertRaises(AdmissionCancelled): pending.result(2)
        self.assertEqual(self.ledger.rows("jobs"), [])
        self.broker.fetch = original_fetch
        admission = uuid.uuid4().hex
        result = self.broker.admit("dot", [ident], "s", admission)
        cancellation = self.broker.cancel_admission(admission)
        self.assertTrue(cancellation["durably_accepted"])
        job = self.ledger.get("jobs", result["jobs"][0]["request_id"])
        self.assertFalse(job["cancel_requested"])
        self.assertEqual(job["execution"], "accepted")

    def test_execution_and_delivery_separate_completion_race_is_single_intent(self):
        ident = self.admit()
        self.broker.start("dot", ident, 1, "dot-execution-42")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.broker.complete(
                "dot", ident, 1, "answer", "succeeded"), range(8)))
        self.assertTrue(all(result["execution"] == "succeeded" and result["delivery"] == "queued"
                            for result in results))
        self.assertEqual(sum(row["stage"] == "response" for row in self.ledger.rows("outbox")), 1)
        with self.assertRaises(ValueError): self.broker.complete("dot", ident, 1, "conflict", "succeeded")
        transport = FakeTransport()
        self.broker.drain_one("response", transport)
        self.broker.drain_one("response", transport)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(self.ledger.get("jobs", ident)["delivery"], "delivered")
        self.assertEqual(self.ledger.get("jobs", ident)["dot_job_id"], "dot-execution-42")

    def test_http_ack_is_not_execution_and_ambiguous_wake_or_cli_never_retry(self):
        first = self.admit()
        accepted = FakeTransport({"accepted": True, "http_status": 200})
        self.broker.drain_one("wake", accepted)
        self.assertEqual(self.ledger.get("jobs", first)["execution"], "accepted")
        self.assertEqual(self.ledger.get("jobs", first)["dispatch"], "acknowledged")
        second = self.admit([self.event(2)])
        timeout = FakeTransport(error=TimeoutError(SENTINEL))
        self.assertEqual(self.broker.drain_one("wake", timeout)["state"], "uncertain")
        self.reopen()
        self.assertIsNone(self.broker.drain_one("wake", timeout))
        self.assertEqual(len(timeout.calls), 1)
        self.broker.complete("dot", second, 1, "answer", "succeeded")
        self.broker.drain_one("response", timeout)
        self.reopen()
        self.assertIsNone(self.broker.drain_one("response", timeout))
        self.assertEqual(len(timeout.calls), 2)
        self.assertNotIn(SENTINEL, json.dumps(self.audit))

    def test_explicit_cancel_generation_fence_and_remote_execution_not_claimed_stopped(self):
        ident = self.admit()
        self.broker.start("dot", ident, 1, "remote-job")
        control = uuid.uuid4().hex
        result = self.broker.cancel("dot", ident, 1, control)
        self.assertEqual(self.broker.cancel("dot", ident, 1, control), result)
        self.assertEqual(result["generation"], 2)
        self.assertEqual(result["execution"], "running")
        self.assertFalse(result["remote_execution_stopped"])
        self.assertTrue(result["future_publication_suppressed"])
        with self.assertRaises(ValueError): self.broker.complete("dot", ident, 1, "late", "succeeded")
        with self.assertRaises(ValueError): self.broker.complete("dot", ident, 2, "late", "succeeded")
        self.assertIsNone(self.broker.drain_one("wake", FakeTransport()))

    def test_cancel_racing_with_inflight_publish_reports_delivery_without_future_send(self):
        ident = self.admit()
        self.broker.complete("dot", ident, 1, "answer", "succeeded")
        entered, release = threading.Event(), threading.Event()
        transport = FakeTransport()
        original = transport.send
        def send(plan, lease):
            entered.set()
            release.wait(2)
            return original(plan, lease)
        transport.send = send
        with ThreadPoolExecutor() as pool:
            sending = pool.submit(self.broker.drain_one, "response", transport)
            self.assertTrue(entered.wait(1))
            cancel = pool.submit(self.broker.cancel, "dot", ident, 1, uuid.uuid4().hex)
            self.assertFalse(cancel.done())
            release.set()
            sending.result(2)
            result = cancel.result(2)
        self.assertEqual(result["delivery"], "delivered")
        self.assertEqual(len(transport.calls), 1)
        self.assertIsNone(self.broker.drain_one("response", transport))

    def test_independent_threads_and_revocation_before_effect(self):
        roots = ["a" * 64, "b" * 64]
        ids = [self.event(index, root) for index, root in enumerate(roots)]
        for index, ident in enumerate(ids):
            job = self.admit([ident], session=f"thread-{index}")
            self.broker.complete("dot", job, 1, f"answer-{index}", "succeeded")
        transport = FakeTransport()
        self.broker.drain_one("response", transport)
        self.allowed = False
        self.assertEqual(self.broker.drain_one("response", transport)["state"], "blocked")
        self.assertEqual(len(transport.calls), 1)
        self.assertIn(transport.calls[0]["job"]["source"]["thread_root"], roots)


class FramingTests(unittest.TestCase):
    def test_current_50_batch_context_and_steer_ignore_prior(self):
        ids = [f"{i:064x}" for i in range(1, 51)]
        context = "<thread-context>\n" + frame(["f" * 64]) + "\n</thread-context>"
        self.assertEqual(source_ids([context, frame(ids)]), ids)
        for tag in ("new-message-arrived-while-you-were-working", "new-request-supersedes-previous"):
            prior = "<previous-request-interrupted-before-completion>\n" + frame(ids) + "\n</previous-request-interrupted-before-completion>"
            self.assertEqual(source_ids([prior, frame(["a" * 64], tag)]), ["a" * 64])

    def test_ambiguous_injected_duplicate_and_oversized_frames_fail(self):
        ident = "a" * 64
        injected = frame([ident, "b" * 64]).replace(
            "Content: ignored", "Content: ignored\n--- Event 2 (@mention) ---\nEvent ID: " + "c" * 64 + "\n", 1)
        for blocks in ([frame([ident]), frame(["b" * 64])], [frame([ident, ident])],
                       [frame([f"{i:064x}" for i in range(51)])], [injected], ["x" * 262145]):
            with self.assertRaises(ValueError): source_ids(blocks)


class TransportTests(Fixture, unittest.TestCase):
    def setUp(self): self.setup_fixture()
    def tearDown(self): self.teardown_fixture()

    def test_webhook_contract_one_subscription_and_no_automatic_retry(self):
        ident = self.admit()
        subscriptions = {"sub_fixture": {"principal": "dot", "channel": CHANNEL, "expires": NOW + 60,
                         "url": "https://callback.example/hook",
                         "secret": "whsec_" + base64.b64encode(bytes(range(32))).decode()}}
        post = Mock(return_value=(200, {}))
        transport = WebhookTransport(subscriptions, post, lambda p, c: True,
                                     lambda: NOW, threading.RLock())
        self.broker.drain_one("wake", transport)
        url, body, hdr = post.call_args.args
        self.assertEqual(json.loads(body)["data"]["message_id"], self.ledger.get("jobs", ident)["source"]["message_id"])
        self.assertEqual(hdr["X-MCP-Subscription-Id"], "sub_fixture")
        self.assertEqual(self.ledger.get("jobs", ident)["execution"], "accepted")
        self.assertIsNone(self.broker.drain_one("wake", transport))
        self.assertEqual(post.call_count, 1)

    def test_cli_fixed_target_stdin_lease_and_signed_readback(self):
        source = self.event(root="a" * 64)
        ident = self.admit([source])
        self.broker.complete("dot", ident, 1, "synthetic answer", "succeeded")
        reply = self.agent({"kind": 9, "created_at": NOW, "content": "synthetic answer",
                            "tags": [["h", CHANNEL], ["e", "a" * 64, "", "root"], ["e", source, "", "reply"]]})
        self.events[reply["id"]] = reply
        process = Mock(pid=123, returncode=0)
        process.communicate.return_value = (json.dumps({"accepted": True, "event_id": reply["id"]}), "")
        spawn = Mock(return_value=process)
        transport = CliTransport("/fixture/buzz", CHANNEL, self.agent.pubkey, lambda: {"PATH": "/usr/bin:/bin"},
                                 lambda i: [self.events[i]], verify_nostr, popen=spawn)
        self.assertEqual(self.broker.drain_one("response", transport)["state"], "accepted")
        args, options = spawn.call_args.args[0], spawn.call_args.kwargs
        self.assertEqual(args[2], "https://relay.example.invalid")
        self.assertIn("--reply-to", args)
        self.assertEqual(options["pass_fds"], (self.ledger.lock_fd,))
        self.assertEqual(process.communicate.call_args.args, ("synthetic answer",))

    def test_mismatched_cli_readback_remains_uncertain(self):
        ident = self.admit()
        self.broker.complete("dot", ident, 1, "answer", "succeeded", "channel")
        reply = self.agent({"kind": 9, "created_at": NOW, "content": "different", "tags": [["h", CHANNEL]]})
        process = Mock(pid=123, returncode=0)
        process.communicate.return_value = (json.dumps({"accepted": True, "event_id": reply["id"]}), "")
        spawn = Mock(return_value=process)
        transport = CliTransport("/fixture/buzz", CHANNEL, self.agent.pubkey, lambda: {},
                                 lambda i: [reply], verify_nostr, popen=spawn)
        self.assertEqual(self.broker.drain_one("response", transport)["state"], "uncertain")
        self.assertIsNone(self.broker.drain_one("response", transport))
        self.assertEqual(spawn.call_count, 1)

    def test_official_direct_reply_single_edge_is_delivered(self):
        source = self.event()
        ident = self.admit([source])
        self.broker.complete("dot", ident, 1, "answer", "succeeded")
        reply = self.agent({"kind": 9, "created_at": NOW, "content": "answer",
                            "tags": [["h", CHANNEL], ["e", source, "", "reply"]]})
        process = Mock(pid=123, returncode=0)
        process.communicate.return_value = (json.dumps({"accepted": True, "event_id": reply["id"]}), "")
        spawn = Mock(return_value=process)
        transport = CliTransport("/fixture/buzz", CHANNEL, self.agent.pubkey, lambda: {},
                                 lambda i: [reply], verify_nostr, popen=spawn)
        self.assertEqual(self.broker.drain_one("response", transport)["state"], "accepted")
        self.assertEqual(self.broker.status("dot", [ident])["jobs"][0]["event_id"], reply["id"])
        self.assertEqual(spawn.call_count, 1)

    def test_uncertain_reconciliation_verifies_receipt_without_any_publish(self):
        source = self.event()
        ident = self.admit([source])
        self.broker.complete("dot", ident, 1, "answer", "succeeded")
        failure = Mock()
        failure.prepare.return_value = {"destination": CHANNEL}
        failure.send.side_effect = RuntimeError("ambiguous")
        self.broker.drain_one("response", failure)
        reply = self.agent({"kind": 9, "created_at": NOW, "content": "answer",
                            "tags": [["h", CHANNEL], ["e", source, "", "reply"]]})
        rows = [reply]
        spawn, credentials = Mock(), Mock()
        transport = CliTransport("/fixture/buzz", CHANNEL, self.agent.pubkey, credentials,
                                 lambda i: rows, verify_nostr, popen=spawn)
        with self.assertRaises(ValueError):
            self.broker.reconcile_delivery("dot", ident, 2, reply["id"], transport)
        bad = self.agent({"kind": 9, "created_at": NOW, "content": "wrong",
                          "tags": [["h", CHANNEL], ["e", source, "", "reply"]]})
        rows[:] = [bad]
        with self.assertRaises(ValueError):
            self.broker.reconcile_delivery("dot", ident, 1, bad["id"], transport)
        self.assertEqual(self.broker.status("dot", [ident])["jobs"][0]["delivery"], "uncertain")
        rows[:] = [reply]
        result = self.broker.reconcile_delivery("dot", ident, 1, reply["id"], transport)
        self.assertEqual(result["delivery"], "delivered")
        self.assertEqual(self.broker.reconcile_delivery("dot", ident, 1, reply["id"], transport), result)
        self.assertIsNone(self.broker.drain_one("response", transport))
        spawn.assert_not_called()
        credentials.assert_not_called()

    def test_tools_expose_job_contract_and_no_direct_send(self):
        tools = JobTools(self.broker)
        names = [row["name"] for row in tools("dot", "tools/list", {})["tools"]]
        self.assertEqual(len(names), 5)
        self.assertNotIn("buzz_reply", names)
        ident = self.admit()
        result = tools("dot", "tools/call", {"name": "buzz_job_complete", "arguments": {
            "request_id": ident, "generation": 1, "text": "answer", "outcome": "succeeded", "route": "thread"}})
        self.assertEqual(result["structuredContent"]["delivery"], "queued")
        self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
        with self.assertRaises(PermissionError): tools("sibling", "tools/list", {})

    def test_all_job_tools_reject_foreign_unknown_and_revoked_access(self):
        tools, ident = JobTools(self.broker), self.admit()
        requests = [
            ("buzz_jobs_pending", {}),
            ("buzz_job_status", {"request_ids": [ident]}),
            ("buzz_job_start", {"request_id": ident, "generation": 1, "dot_job_id": "dot-run"}),
            ("buzz_job_complete", {"request_id": ident, "generation": 1, "text": "answer",
                                   "outcome": "succeeded", "route": "thread"}),
            ("buzz_job_cancel", {"request_id": ident, "generation": 1, "control_id": uuid.uuid4().hex}),
        ]
        for principal, allowed in (("sibling", True), ("dot", False)):
            self.allowed = allowed
            for name, args in requests:
                with self.subTest(name=name, principal=principal), self.assertRaises(PermissionError):
                    tools(principal, "tools/call", {"name": name, "arguments": args})
        self.allowed = True
        for name, args in requests[1:]:
            unknown = {**args, **({"request_ids": ["job_" + "0" * 64]} if "request_ids" in args
                                  else {"request_id": "job_" + "0" * 64})}
            with self.subTest(unknown=name), self.assertRaises(PermissionError):
                tools("dot", "tools/call", {"name": name, "arguments": unknown})
        self.assertEqual(self.ledger.get("jobs", ident)["execution"], "accepted")
        self.assertEqual(len(self.ledger.rows("outbox")), 1)

    def test_mutation_generation_must_be_exact_integer_and_cancel_retry_matches(self):
        ident = self.admit()
        for generation in (None, True, "1", 0, 2):
            for operation in (
                    lambda: self.broker.start("dot", ident, generation, "dot-run"),
                    lambda: self.broker.complete("dot", ident, generation, "answer", "succeeded"),
                    lambda: self.broker.cancel("dot", ident, generation, uuid.uuid4().hex)):
                with self.subTest(generation=generation), self.assertRaises(ValueError):
                    operation()
        control = uuid.uuid4().hex
        first = self.broker.cancel("dot", ident, 1, control)
        self.assertEqual(self.broker.cancel("dot", ident, 1, control), first)
        with self.assertRaises(ValueError): self.broker.cancel("dot", ident, 2, control)
        with self.assertRaises(ValueError): self.broker.complete("dot", ident, 1, "late", "succeeded")
        self.assertFalse(any(row["stage"] == "response" for row in self.ledger.rows("outbox")))


if __name__ == "__main__":
    unittest.main()
