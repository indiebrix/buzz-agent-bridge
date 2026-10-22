"""Explicit host-defined schema and validation, without a dynamic plugin loader."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Callable


@dataclass(frozen=True)
class EventDefinition:
    name: str
    description: str
    scope_field: str
    payload_schema: dict
    validate_payload: Callable[[dict], bool]

    def __post_init__(self):
        if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,127}", self.name)
                or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", self.scope_field)
                or self.scope_field in {"principal", "url", "secret", "expires", "verified_at",
                                       "seen", "previous_secret", "rotate_until"}
                or not isinstance(self.description, str) or not self.description
                or not isinstance(self.payload_schema, dict)
                or self.payload_schema.get("type") != "object"
                or not callable(self.validate_payload)):
            raise ValueError("Explicit event schema and validator required")

    @classmethod
    def string_fields(cls, name, description, scope_field, fields):
        fields = tuple(fields)
        if (not fields or len(set(fields)) != len(fields)
                or any(not isinstance(field, str) or not field for field in fields)):
            raise ValueError("Unique payload fields required")
        schema = {"type": "object", "properties": {f: {"type": "string"} for f in fields},
                  "required": list(fields), "additionalProperties": False}
        return cls(name, description, scope_field, schema,
                   lambda value: isinstance(value, dict) and set(value) == set(fields)
                   and all(isinstance(value[f], str) for f in fields))

    def schema(self):
        return {"name": self.name, "description": self.description, "delivery": ["webhook"],
                "inputSchema": {"type": "object", "properties": {
                    self.scope_field: {"type": "string"}}, "required": [self.scope_field],
                    "additionalProperties": False}, "payloadSchema": deepcopy(self.payload_schema)}

    def event(self, event_id, created_at, data):
        value = {"eventId": event_id, "name": self.name, "cursor": None,
                 "timestamp": datetime.fromtimestamp(created_at, timezone.utc).isoformat(),
                 "data": data}
        # Check the actual serialized representation, including size and JSON types.
        raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        return self.validate_wire(raw)

    def validate_wire(self, body):
        if not isinstance(body, bytes) or len(body) > 262144:
            raise ValueError("Invalid event size")
        def reject_constant(_):
            raise ValueError("Non-finite JSON constant")
        value = json.loads(body, parse_constant=reject_constant)
        if (not isinstance(value, dict)
                or set(value) != {"eventId", "name", "timestamp", "data", "cursor"}
                or value["name"] != self.name or value["cursor"] is not None
                or not isinstance(value["eventId"], str) or not 1 <= len(value["eventId"]) <= 256
                or not isinstance(value["timestamp"], str)
                or not isinstance(value["data"], dict)
                or self.validate_payload(value["data"]) is not True):
            raise ValueError("Event contract rejected")
        stamp = datetime.fromisoformat(value["timestamp"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Timezone required")
        return value
