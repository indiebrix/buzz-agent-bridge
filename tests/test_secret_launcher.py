"""Exercise the optional launcher without any vault, CLI authentication, or network."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

from buzz_agent_bridge import secret_launcher


class SecretLauncherTests(unittest.TestCase):
    def test_environment_injection_uses_pipe_and_cleans_child_environment(self):
        path = Path(__file__).parents[1] / "examples" / "launch_host.py"
        spec = importlib.util.spec_from_file_location("secret_launcher_fixture", path)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        payload = {"storage_key": bytes(range(32)).hex(),
                   "mcp_token": "synthetic-fixture-not-a-credential"}
        received, processes = {}, []

        class Child:
            def __init__(self, argv, *, pass_fds, env):
                processes.append(argv)
                self.reader = os.dup(pass_fds[0])
                self.thread = threading.Thread(target=self.read)
                self.thread.start()
                self_outer.assertEqual(argv, [sys.executable, "-m", "buzz_agent_bridge.cli",
                    "host", "--config", "/example/bridge.json", "--secrets-fd", str(pass_fds[0])])
                self_outer.assertEqual(env, {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})
                self_outer.assertNotIn("BRIDGE_STORAGE_KEY", os.environ)
                self_outer.assertNotIn("BRIDGE_MCP_TOKEN", os.environ)

            def read(self):
                with os.fdopen(self.reader, "rb") as stream:
                    received.update(json.load(stream))

            def wait(self):
                self.thread.join(timeout=3)
                self_outer.assertFalse(self.thread.is_alive())
                return 0

        self_outer = self
        output = io.StringIO()
        with patch.dict(os.environ, {"BRIDGE_STORAGE_KEY": payload["storage_key"],
                "BRIDGE_MCP_TOKEN": payload["mcp_token"]}, clear=True), \
                patch.object(sys, "argv", [str(path), "/example/bridge.json"]), \
                patch.object(secret_launcher.subprocess, "Popen", Child), \
                patch.object(sys, "stdout", output), patch.object(sys, "stderr", output):
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(len(processes), 1)
        self.assertEqual(received, payload)
        self.assertEqual(output.getvalue(), "")
