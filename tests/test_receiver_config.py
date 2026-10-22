"""Offline receiver setup; no production files, credentials, or relay access."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from buzz_agent_bridge.setup import receiver_configuration, save_config


class ReceiverConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bab-rc-", dir="/tmp")
        self.root = Path(self.temp.name)
        self.config = {"relay_url": "https://relay.example.invalid",
            "channel": "11111111-1111-4111-8111-111111111111",
            "owner_pubkey": "ab" * 32, "agent_pubkey": "cd" * 32,
            "principal": "fixture", "state_directory": str(self.root / "state"),
            "buzz_cli": sys.executable, "mcp_port": 18302, "provider": "chatgpt-dot"}
        self.path = save_config(self.root / "bridge.json", self.config)
        self.output = self.root / "receiver.toml"

    def tearDown(self):
        self.temp.cleanup()

    def test_modes_restrict_scope_to_one_channel_and_message_kind(self):
        for mode in ("mentions", "owner-messages"):
            with self.subTest(mode=mode):
                output = self.root / (mode + ".toml")
                report = receiver_configuration(self.path, output, mode)
                rule, = tomllib.loads(output.read_text())["rules"]
                self.assertEqual(rule["channels"], [self.config["channel"]])
                self.assertEqual(rule["kinds"], [9])
                self.assertEqual(rule["require_mention"], mode == "mentions")
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                self.assertEqual(report["environment"], {
                    "BUZZ_ACP_SUBSCRIBE": "config", "BUZZ_ACP_CONFIG": str(output)})
                self.assertEqual(report["required_buzz_author_gate"], "owner-only")
                self.assertFalse(report["runtime_changed"])

    def test_setup_does_not_connect_or_spawn_or_change_host_configuration(self):
        before = self.path.read_bytes()
        with patch.object(socket, "create_connection", side_effect=AssertionError("No network")), \
                patch.object(subprocess, "Popen", side_effect=AssertionError("No subprocess")):
            receiver_configuration(self.path, self.output)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root / "state").exists())
        self.assertTrue(tomllib.loads(self.output.read_text())["rules"][0]["require_mention"])

    def test_existing_output_and_symlink_are_not_overwritten(self):
        self.output.write_text("existing")
        with self.assertRaises(FileExistsError):
            receiver_configuration(self.path, self.output, "owner-messages")
        self.assertEqual(self.output.read_text(), "existing")
        link = self.root / "link.toml"
        link.symlink_to(self.output)
        with self.assertRaises(OSError):
            receiver_configuration(self.path, link)
        self.assertEqual(self.output.read_text(), "existing")

    def test_invalid_scope_and_mode_create_no_file(self):
        for channel in ("all", "*", "", "not-a-uuid", "a\n[[rules]]"):
            path = self.root / "invalid.json"
            path.write_text(json.dumps({**self.config, "channel": channel}))
            path.chmod(0o600)
            with self.assertRaises(ValueError):
                receiver_configuration(path, self.output, "owner-messages")
            self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError):
            receiver_configuration(self.path, self.output, "anyone")
        with self.assertRaises(ValueError):
            receiver_configuration(self.path, "relative.toml")

    def test_cli_emits_explicit_non_secret_apply_instructions(self):
        done = subprocess.run([sys.executable, "-m", "buzz_agent_bridge.cli", "receiver-config",
            "--config", str(self.path), "--output", str(self.output), "--receive", "owner-messages"],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertFalse(report["runtime_changed"])
        self.assertTrue(report["restart_required_after_applying"])
        self.assertNotIn("BUZZ_PRIVATE_KEY", report["environment"])
        self.assertNotIn("BUZZ_ACP_RESPOND_TO", report["environment"])


if __name__ == "__main__":
    unittest.main()
