"""A second synthetic adapter proves remote providers do not own Buzz delivery."""
import asyncio
from pathlib import Path
import unittest

from test_buzz_durable_jobs import Fixture, CHANNEL, NOW, Application
from buzz_agent_bridge.frontend import Frontend
from buzz_agent_bridge.providers import ProviderInfo, ProviderBinding, get_provider


class FixtureProvider:
    info = ProviderInfo("fixture-bot", "Fixture Bot", "Synthetic local adapter only.")

    def __init__(self):
        self.sent = []

    def bind(self, **context):
        self.context = context
        return ProviderBinding(self, self)

    def handle(self, principal, method, params=None):
        return {"provider": self.info.id, "principal": principal}

    def prepare(self, job, entry):
        return {"destination": "local-fixture", "request_id": job["request_id"]}

    def send(self, plan, lease_fd):
        self.sent.append(plan)
        return {"accepted": True}


class ProviderTests(Fixture, unittest.TestCase):
    def setUp(self): self.setup_fixture()
    def tearDown(self): self.teardown_fixture()

    def app(self, provider=None, channel=CHANNEL):
        return Application(Path(self.temp.name) / "adapter", bytes(range(32)), "dot", channel,
            self.owner.pubkey, self.agent.pubkey, lambda _: "dot", lambda p, c: True,
            lambda ident: [self.events[ident]], "/unused", lambda: {}, activation=NOW - 100,
            now=lambda: NOW, provider=provider)

    def test_second_adapter_uses_common_jobs_and_never_claims_delivery(self):
        provider = FixtureProvider()
        app = self.app(provider)
        try:
            discovery = app.rpc("dot", {"jsonrpc": "2.0", "id": 1, "method": "fixture/discover"})
            self.assertEqual(discovery["result"], {"provider": "fixture-bot", "principal": "dot"})
            source = self.event()
            accepted = app.broker.admit("dot", [source], "fixture-session", "f" * 32, 1)
            ident = accepted["jobs"][0]["request_id"]
            app.broker.drain_one("wake", app.wake)
            status = app.broker.status("dot", [ident])["jobs"][0]
            self.assertEqual(provider.sent[0]["request_id"], ident)
            self.assertEqual(status["dispatch"], "acknowledged")
            self.assertNotEqual(status["delivery"], "delivered")
            self.assertIsNot(app.publisher, provider)
        finally:
            app.close()

    def test_existing_ledger_cannot_silently_switch_provider(self):
        app = self.app()
        app.close()
        with self.assertRaises(PermissionError): self.app(FixtureProvider())
        with self.assertRaises(PermissionError): self.app(channel="different-channel")
        # A rejected adapter releases the lease so the original can resume.
        app = self.app()
        app.close()

    def test_unimplemented_grok_is_not_selectable_and_labels_are_provider_owned(self):
        with self.assertRaises(ValueError): get_provider("grok-bot")
        async def scenario():
            frontend = Frontend(None, provider=FixtureProvider())
            session = await frontend.new_session("/tmp")
            option = session.config_options[0]
            self.assertEqual(option.options[0].name, "Fixture Bot")
            await frontend.set_config_option("model", session.session_id, "fixture-bot")
            with self.assertRaises(ValueError):
                await frontend.set_config_option("model", session.session_id, "chatgpt-dot")
        asyncio.run(scenario())
