"""Clean-install checks with public fixtures; no production configuration is used."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from buzz_agent_bridge import VERSION
from buzz_agent_bridge.config import load, read_secrets, validate
from buzz_agent_bridge.crypto import NostrSigner
from buzz_agent_bridge.managed import HandoffServer, handoff, validate_auth_tag
from buzz_agent_bridge.setup import doctor, harness_definition, save_config


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bab-", dir="/tmp")
        self.root = Path(self.temp.name)
        self.agent, self.owner = NostrSigner(bytes([1]) * 32), NostrSigner(bytes([2]) * 32)
        self.config = {"relay_url": "https://relay.example.invalid", "channel": "synthetic-channel",
            "owner_pubkey": self.owner.pubkey, "agent_pubkey": self.agent.pubkey,
            "principal": "fixture-connection", "state_directory": str(self.root / "state"),
            "buzz_cli": sys.executable, "mcp_port": 18302, "provider": "chatgpt-dot"}

    def tearDown(self): self.temp.cleanup()

    def test_init_uses_public_inputs_only_and_refuses_overwrite(self):
        path = self.root / "bridge.json"
        args = [sys.executable, "-m", "buzz_agent_bridge.cli", "init", "--output", str(path)]
        for key, value in self.config.items():
            if key != "provider": args.extend(["--" + key.replace("_", "-"), str(value)])
        done = subprocess.run(args, text=True, capture_output=True, timeout=5)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(load(path), self.config)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        again = subprocess.run(args, text=True, capture_output=True, timeout=5)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(load(path), self.config)
        self.assertFalse((self.root / "state").exists())

    def test_doctor_never_executes_cli_or_reads_credentials(self):
        path = save_config(self.root / "bridge.json", self.config)
        with patch.object(subprocess, "Popen", side_effect=AssertionError("No processes")), \
                patch.object(socket, "create_connection", side_effect=AssertionError("No network")):
            report = doctor(path)
        self.assertTrue(report["buzz_cli_executable"])
        self.assertFalse(report["credentials_checked"])
        self.assertFalse(report["runtime_checked"])
        state = self.root / "state"
        state.mkdir(mode=0o755)
        self.assertFalse(doctor(path)["state_directory_safe"])
        state.rmdir()
        state.symlink_to(self.root / "absent")
        self.assertFalse(doctor(path)["state_directory_safe"])

    def test_invalid_config_provider_and_unsafe_file_are_rejected(self):
        for changes in ({"provider": "grok-bot"}, {"relay_url": "http://localhost"},
                        {"relay_url": "https://user:pass@example.invalid"},
                        {"state_directory": "relative"}, {"mcp_port": True},
                        {"agent_pubkey": self.owner.pubkey}):
            with self.assertRaises(ValueError): validate({**self.config, **changes})
        path = save_config(self.root / "bridge.json", self.config)
        path.chmod(0o666)
        with self.assertRaises(PermissionError): load(path)

    def test_harness_contains_no_credentials_and_works_before_config(self):
        value = harness_definition(self.root / "future.json", "/example/bin/buzz-agent-bridge")
        self.assertEqual(value["label"], "Buzz Agent Bridge")
        self.assertEqual(value["env"], {})
        done = subprocess.run([sys.executable, "-m", "buzz_agent_bridge.cli", "managed",
            "--config", str(self.root / "future.json")], input=json.dumps({"jsonrpc": "2.0", "id": 1,
                "method": "initialize", "params": {"protocolVersion": 1}}) + "\n",
            text=True, capture_output=True, timeout=5,
            env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["result"]["agentInfo"]["name"], "buzz-agent-bridge")

    def test_secrets_accept_only_pipe_and_exact_fields(self):
        def read(value):
            r, w = os.pipe()
            os.write(w, json.dumps(value).encode()); os.close(w)
            return read_secrets(r)
        value = {"storage_key": bytes(range(32)).hex(), "mcp_token": "synthetic-fixture-" * 3}
        self.assertEqual(read(value), value)
        with self.assertRaises(ValueError): read({**value, "signing_key": "not-allowed"})
        with self.assertRaises(ValueError): read({**value, "mcp_token": "too-short"})
        with tempfile.TemporaryFile() as file:
            with self.assertRaises(PermissionError): read_secrets(file.fileno())

    def test_actual_handoff_requires_exact_identity_and_owner_attestation(self):
        digest = hashlib.sha256(f"nostr:agent-auth:{self.agent.pubkey}:".encode()).digest()
        tag = json.dumps(["auth", self.owner.pubkey, "", self.owner.key.sign_schnorr(digest).hex()])
        self.assertTrue(validate_auth_tag(tag, self.agent.pubkey, self.owner.pubkey))
        server = HandoffServer(self.root / "identity/socket", self.agent.pubkey, self.owner.pubkey)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            self.assertFalse(handoff(server.path, (bytes([2]) * 32).hex(), tag)["accepted"])
            response = handoff(server.path, (bytes([1]) * 32).hex(), tag)
            self.assertEqual(response, {"accepted": True, "pubkey": self.agent.pubkey, "version": VERSION})
            self.assertTrue(server.available.is_set())
        finally:
            server.shutdown(); server.server_close(); thread.join(3)
