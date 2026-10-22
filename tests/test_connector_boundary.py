"""Independent connector contracts and event isolation; no external services."""
import ast
import base64
from pathlib import Path
import threading
import unittest

from chatgpt_dots import events
from chatgpt_dots.definition import EventDefinition
from chatgpt_dots.delivery import Delivery, NotReady


class ConnectorBoundary(unittest.TestCase):
    def setUp(self):
        self.store, self.calls = {}, []
        self.allowed, self.clock = True, 1800000000
        self.definition = EventDefinition.string_fields("build.finished", "Build complete.", "project", ("build_id",))
        self.authorize = lambda p, s: self.allowed and p == "reviewer" and s == "sample"
        self.post = lambda u, b, h: (self.calls.append(b) or (200, {"challenge": __import__('json').loads(b).get("challenge")}))
        self.registration = events.Subscriptions(self.definition, self.store, self.authorize, self.post, lambda: self.clock)
        self.delivery = Delivery(self.definition, self.store, self.post, self.authorize, lambda: self.clock, threading.RLock())
        self.params = {"name": "build.finished", "arguments": {"project": "sample"}, "delivery": {
            "mode": "webhook", "url": "https://callback.example.invalid/events",
            "secret": "whsec_" + base64.b64encode(bytes(range(32))).decode()}}

    def test_external_payload_and_tools_need_no_buzz_modules(self):
        root = Path(events.__file__).parent
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text())
            imports = {node.module.split('.')[0] for node in ast.walk(tree)
                       if isinstance(node, ast.ImportFrom) and node.module and node.level == 0}
            imports |= {item.name.split('.')[0] for node in ast.walk(tree)
                        if isinstance(node, ast.Import) for item in node.names}
            self.assertFalse(imports & {"buzz_agent_bridge", "acp", "coincurve"}, path.name)
        self.registration.handle("reviewer", "events/subscribe", self.params)
        event = self.definition.event("build-42", self.clock, {"build_id": "42"})
        self.assertTrue(self.delivery.send(self.delivery.prepare("reviewer", "sample", event))["accepted"])
        with self.assertRaises(ValueError):
            self.definition.event("build-43", self.clock, {"build_id": 43})

    def test_other_event_same_scope_cannot_receive_or_confuse_delivery(self):
        other = EventDefinition.string_fields("deploy.finished", "Deploy complete.", "project", ("build_id",))
        registration = events.Subscriptions(other, self.store, self.authorize, self.post, lambda: self.clock)
        registration.handle("reviewer", "events/subscribe", {**self.params, "name": other.name})
        event = self.definition.event("build-42", self.clock, {"build_id": "42"})
        with self.assertRaises(NotReady):
            self.delivery.prepare("reviewer", "sample", event)
        self.registration.handle("reviewer", "events/subscribe", self.params)
        plan = self.delivery.prepare("reviewer", "sample", event)
        plan["destination"] = next(key for key in self.store if key != plan["destination"])
        with self.assertRaises(PermissionError):
            self.delivery.send(plan)

    def test_revocation_expiry_and_multiple_dots_fail_closed(self):
        self.registration.handle("reviewer", "events/subscribe", self.params)
        event = self.definition.event("build-42", self.clock, {"build_id": "42"})
        plan = self.delivery.prepare("reviewer", "sample", event)
        count = len(self.calls)
        self.allowed = False
        with self.assertRaises(PermissionError): self.delivery.send(plan)
        self.assertEqual(len(self.calls), count)
        self.allowed = True
        self.clock += 3601
        with self.assertRaises(PermissionError): self.delivery.send(plan)
        self.registration.handle("reviewer", "events/subscribe", self.params)
        second = {**self.params, "delivery": {**self.params["delivery"], "url": "https://other.example.invalid/events"}}
        self.registration.handle("reviewer", "events/subscribe", second)
        with self.assertRaises(NotReady): self.delivery.prepare("reviewer", "sample", event)

    def test_scope_cannot_overwrite_subscription_security_fields(self):
        for scope in ("principal", "secret", "url", "expires", "seen", "previous_secret"):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                EventDefinition.string_fields("test.created", "Test.", scope, ("value",))


if __name__ == "__main__": unittest.main()
