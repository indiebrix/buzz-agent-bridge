"""Remote-agent adapters. Broker admission and Buzz publication stay provider-neutral."""
from dataclasses import dataclass
from typing import Protocol

PRODUCT_NAME = "Buzz Agent Bridge"
PRODUCT_ID = "buzz-agent-bridge"


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    description: str
    legacy_model_ids: tuple[str, ...] = ()

    def accepts_model(self, value):
        return value == self.id or value in self.legacy_model_ids


@dataclass(frozen=True)
class ProviderBinding:
    registration: object
    wake: object


class AgentProvider(Protocol):
    info: ProviderInfo

    def bind(self, *, subscriptions, authorize, post, now, own_pubkey, lock) -> ProviderBinding:
        """Supply registration RPC + prepare/send wake transport, never a Buzz publisher."""
        ...


class ChatGPTDot:
    info = ProviderInfo("chatgpt-dot", "ChatGPT Dot",
                        "Connects an existing ChatGPT Dot through MCP Events.",
                        ())

    def bind(self, *, subscriptions, authorize, post, now, own_pubkey, lock):
        from .adapters.chatgpt.events import Events
        from .adapters.chatgpt.wake import WebhookTransport
        events = Events(subscriptions, authorize, post, now, own_pubkey)
        return ProviderBinding(events, WebhookTransport(subscriptions, post, authorize, now, lock))


def get_provider(name="chatgpt-dot") -> AgentProvider:
    # Only implemented adapters are selectable. A future Grok Bot adapter must
    # implement its actual wake/auth contract before it is registered here.
    if name == ChatGPTDot.info.id:
        return ChatGPTDot()
    raise ValueError("Unsupported agent provider")


def bind_provider_scope(ledger, provider_id):
    """Prevent a changed adapter from consuming another provider's durable jobs."""
    with ledger.transaction():
        previous = ledger.get("controls", "__provider__")
        if previous is not None and previous != {"id": provider_id}:
            raise PermissionError("Ledger provider changed; use a separate state directory")
        if previous is None and provider_id != "chatgpt-dot" and (
                ledger.rows("jobs") or ledger.rows("outbox")):
            raise PermissionError("Legacy jobs belong to ChatGPT Dot")
        ledger.put("controls", "__provider__", {"id": provider_id})
