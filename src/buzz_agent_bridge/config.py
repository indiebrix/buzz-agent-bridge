"""Public deployment configuration, separate from injected credentials and state."""
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

from .providers import get_provider

FIELDS = {"relay_url", "channel", "owner_pubkey", "agent_pubkey", "principal",
          "state_directory", "buzz_cli", "mcp_port", "provider"}


def validate(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("Invalid configuration fields")
    if any(not isinstance(value[key], str) or not value[key] for key in FIELDS - {"mcp_port"}):
        raise ValueError("Invalid configuration value")
    for name in ("owner_pubkey", "agent_pubkey"):
        if not re.fullmatch("[0-9a-f]{64}", value[name]):
            raise ValueError("Invalid public identity")
    if value["owner_pubkey"] == value["agent_pubkey"]:
        raise ValueError("Owner and agent must be distinct")
    if type(value["mcp_port"]) is not int or not 1024 <= value["mcp_port"] <= 65535:
        raise ValueError("Invalid MCP port")
    if any(len(value[key]) > 256 for key in ("channel", "principal")):
        raise ValueError("Scope too long")
    parsed = urlsplit(value["relay_url"])
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("Explicit HTTPS relay origin required")
    for name in ("state_directory", "buzz_cli"):
        if not Path(value[name]).is_absolute():
            raise ValueError("Absolute local paths required")
    if len(os.fsencode(Path(value["state_directory"]) / "identity/socket")) > 100:
        raise ValueError("State path is too long for a Unix socket")
    get_provider(value["provider"])
    return {**value, "relay_url": value["relay_url"].rstrip("/")}


def load(path):
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) & 0o022 or info.st_size > 16384):
        raise PermissionError("Unsafe configuration file")
    return validate(json.loads(path.read_text()))


def read_secrets(descriptor):
    """Only an inherited anonymous pipe; never a credential file or argv value."""
    if not stat.S_ISFIFO(os.fstat(descriptor).st_mode):
        raise PermissionError("Secrets require an anonymous pipe")
    with os.fdopen(descriptor, "rb") as stream:
        data = stream.read(8193)
    if len(data) > 8192:
        raise ValueError("Secret payload too large")
    return validate_secrets(json.loads(data))


def validate_secrets(value):
    """Shared validation for explicit secret sources; never includes values in errors."""
    if not isinstance(value, dict) or set(value) != {"storage_key", "mcp_token"}:
        raise ValueError("Invalid secret payload")
    if not isinstance(value["storage_key"], str) or not re.fullmatch("[0-9a-f]{64}", value["storage_key"]):
        raise ValueError("Invalid storage key")
    token = value["mcp_token"]
    if not isinstance(token, str) or not 32 <= len(token) <= 4096 or any(c.isspace() for c in token):
        raise ValueError("Provision a high-entropy MCP token")
    return value
