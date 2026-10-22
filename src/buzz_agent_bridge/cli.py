"""Managed ACP launcher and separate durable host; never provisions credentials."""
import argparse
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import signal
import sys
import threading
import time

from . import VERSION
from .application import Application
from .config import load, read_secrets
from .crypto import NostrSigner
from .http import BearerAuth
from .ipc import LocalClient
from .ledger import private_directory, private_file
from .managed import HandoffServer, decode_key, handoff
from .providers import get_provider
from .relay import RelayReader
from .setup import configure, doctor, harness_definition, receiver_configuration


def activation(directory):
    path = directory / "activation.json"
    descriptor = private_file(path)
    try:
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, json.dumps({"since": int(time.time())}).encode())
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        value = json.loads(os.read(descriptor, 1025))
        if set(value) != {"since"} or type(value["since"]) is not int or value["since"] < 0:
            raise ValueError("Invalid activation record")
        return value["since"]
    finally:
        os.close(descriptor)


def managed(config):
    raw = os.environ.pop("BUZZ_PRIVATE_KEY", "")
    auth_tag = os.environ.pop("BUZZ_AUTH_TAG", "")
    directory = Path(config["state_directory"])
    socket_path = directory / "model-probe/socket"
    if raw:
        signer = NostrSigner(decode_key(raw))
        if signer.pubkey != config["agent_pubkey"]:
            raise PermissionError("Managed identity mismatch")
        result = handoff(directory / "identity/socket", raw, auth_tag)
        if result != {"accepted": True, "pubkey": signer.pubkey, "version": VERSION}:
            raise PermissionError("Managed identity handoff rejected")
        socket_path = directory / "ipc/socket"
        until = time.monotonic() + 30
        while True:
            try:
                identity = LocalClient(socket_path, timeout=2).call("identity", {})
                if (identity["pubkey"] != signer.pubkey or identity["channel"] != config["channel"]
                        or identity["owner"] != config["owner_pubkey"]):
                    raise PermissionError("Broker identity mismatch")
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if time.monotonic() >= until:
                    raise RuntimeError("Broker readiness timed out")
                time.sleep(.1)
        raw, auth_tag, signer = "", "", None
    os.execve(sys.executable, [sys.executable, "-m", "buzz_agent_bridge.frontend", "--socket",
        str(socket_path), "--provider", config["provider"]],
        {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})


def host(config, descriptor):
    secrets = read_secrets(descriptor)
    storage_key = bytes.fromhex(secrets.pop("storage_key"))
    token_digest = hashlib.sha256(secrets.pop("mcp_token").encode()).hexdigest()
    secrets.clear()
    directory = private_directory(config["state_directory"])
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    bootstrap = HandoffServer(directory / "identity/socket", config["agent_pubkey"], config["owner_pubkey"])
    thread = threading.Thread(target=bootstrap.serve_forever, daemon=True)
    thread.start()
    try:
        print("Waiting for the configured Buzz managed agent.", file=sys.stderr, flush=True)
        deadline = time.monotonic() + 180
        while not bootstrap.available.wait(.2):
            if stop.is_set(): return
            if time.monotonic() >= deadline: raise RuntimeError("Managed startup timed out")
        signer, auth_tag = bootstrap.signer, bootstrap.auth_tag
        relay = RelayReader(config, signer, auth_tag)
        if not relay.authorize(config["principal"], config["channel"]):
            raise PermissionError("Managed channel membership unavailable")
        app = Application(directory, storage_key, config["principal"], config["channel"],
            config["owner_pubkey"], signer.pubkey, BearerAuth({token_digest: config["principal"]}),
            relay.authorize, relay.fetch, config["buzz_cli"],
            lambda: {"PATH": "/usr/bin:/bin", "BUZZ_PRIVATE_KEY": signer.key.secret.hex(), "BUZZ_AUTH_TAG": auth_tag},
            activation=activation(directory), relay_url=config["relay_url"],
            provider=get_provider(config["provider"]))
        app.run(stop, socket_path=directory / "ipc/socket", port=config["mcp_port"],
                on_ready=lambda: print("Buzz Agent Bridge ready.", file=sys.stderr, flush=True))
    finally:
        bootstrap.shutdown()
        bootstrap.server_close()
        thread.join(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="mode", required=True)
    for name in ("host", "host-keychain", "managed", "check-config", "doctor", "harness", "receiver-config"):
        command = commands.add_parser(name)
        command.add_argument("--config", required=True)
        if name == "host": command.add_argument("--secrets-fd", type=int, required=True)
        if name == "host-keychain":
            command.add_argument("--service", required=True,
                help="Dedicated buzz-agent-bridge.<deployment> service; accounts storage_key and mcp_token")
        if name == "receiver-config":
            command.add_argument("--output", required=True)
            command.add_argument("--receive", choices=("mentions", "owner-messages"), default="mentions")
    command = commands.add_parser("init")
    command.add_argument("--output", required=True)
    for name in ("relay-url", "owner-pubkey", "agent-pubkey", "channel", "state-directory", "buzz-cli"):
        command.add_argument("--" + name)
    command.add_argument("--principal", default="chatgpt-dot-connection")
    command.add_argument("--mcp-port", type=int, default=18302)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        if args.mode == "init":
            configure(args)
            return 0
        if args.mode == "harness":
            print(json.dumps(harness_definition(args.config, Path(sys.executable).parent / "buzz-agent-bridge"), indent=2))
            return 0
        if args.mode == "receiver-config":
            print(json.dumps(receiver_configuration(args.config, args.output, args.receive), indent=2))
            return 0
        if args.mode == "doctor":
            result = doctor(args.config)
            print(json.dumps(result, indent=2))
            return 0 if result["buzz_cli_executable"] and result["state_directory_safe"] else 1
        if args.mode == "managed" and not os.environ.get("BUZZ_PRIVATE_KEY"):
            # Buzz discovers models before an agent identity/config exists.
            # This path cannot admit work and receives no managed credentials.
            from .frontend import serve
            asyncio.run(serve("/nonexistent/buzz-agent-bridge-model-probe/socket"))
            return 0
        config = load(args.config)
        if args.mode == "host-keychain":
            from .keychain import KeychainReadError, read_keychain_secrets
            from .secret_launcher import launch_host
            try:
                return launch_host(args.config, read_keychain_secrets(args.service))
            except KeychainReadError as error:
                print(str(error), file=sys.stderr)
                return 1
        if args.mode == "managed": managed(config)
        elif args.mode == "host": host(config, args.secrets_fd)
        else: print("Configuration valid; no credentials or connections checked.")
        return 0
    except Exception:
        print("Buzz Agent Bridge unavailable; configuration, credentials or readiness require attention.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
