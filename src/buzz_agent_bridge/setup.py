"""Secret-free setup helpers. Never create keys, contact a vault, or start services."""
import json
import os
from pathlib import Path
import stat

from .config import load, validate
from .providers import PRODUCT_ID, PRODUCT_NAME


def save_config(path, value):
    value = validate(value)
    path = Path(path)
    # Refuse overwrites: setup must not silently re-scope an existing deployment.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return path


def harness_definition(config_path, executable):
    if not Path(config_path).is_absolute() or not Path(executable).is_absolute():
        raise ValueError("Use absolute paths")
    return {"id": PRODUCT_ID, "label": PRODUCT_NAME, "command": str(executable),
            "args": ["managed", "--config", str(config_path)], "env": {}}


def doctor(path):
    config = load(path)
    state = Path(config["state_directory"])
    directory_safe = not state.is_symlink() and (not state.exists() or (
        state.is_dir() and state.stat().st_uid == os.getuid()
        and stat.S_IMODE(state.stat().st_mode) == 0o700))
    binary = Path(config["buzz_cli"])
    return {"configuration": "valid", "provider": config["provider"],
            "buzz_cli_executable": binary.is_file() and os.access(binary, os.X_OK),
            "state_directory_safe": directory_safe,
            "runtime_checked": False, "credentials_checked": False,
            "network_checked": False}


def configure(args):
    def ask(name, prompt):
        return getattr(args, name) or input(prompt + ": ").strip()
    value = {"relay_url": ask("relay_url", "Buzz HTTPS relay origin"),
        "owner_pubkey": ask("owner_pubkey", "Owner PUBLIC key (64 hex characters)"),
        "agent_pubkey": ask("agent_pubkey", "Managed agent PUBLIC key (64 hex characters)"),
        "channel": ask("channel", "Private test channel ID"),
        "state_directory": ask("state_directory", "Absolute short state directory"),
        "buzz_cli": ask("buzz_cli", "Absolute official Buzz CLI path"),
        "principal": args.principal, "mcp_port": args.mcp_port, "provider": "chatgpt-dot"}
    save_config(args.output, value)
    print("Saved configuration with mode 0600. No keys, permissions, or services were created.")
