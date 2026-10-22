"""Internal verified-source contract; no platform SDK, network or credential access."""
from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class VerifiedSource:
    """Normalized evidence from trusted adapter code, never a remote assertion.

    Field names preserve the existing encrypted record and MCP tool contract.
    This small seam is not an independently versioned connector API.
    """
    message_id: str
    author: str
    channel: str
    text: str
    created_at: int
    thread_root: str

    def __post_init__(self):
        if (any(not isinstance(getattr(self, name), str) or not getattr(self, name)
                for name in ("message_id", "author", "channel", "thread_root"))
                or not isinstance(self.text, str) or type(self.created_at) is not int
                or self.created_at < 0):
            raise ValueError("Invalid normalized source")

    def as_dict(self):
        return asdict(self)


class SourcePolicy(Protocol):
    def read(self, ident: str, *, new: bool = False) -> VerifiedSource:
        """Re-fetch and verify authenticity, scope, freshness and routing.

        Raise on unavailable or invalid evidence. Do not publish, create a
        conversation or obtain credentials. The broker rechecks authorization.
        """
        ...
