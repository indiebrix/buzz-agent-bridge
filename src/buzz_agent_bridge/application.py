"""Injectable resident host. Existing credential consumption requires deployment approval."""
from pathlib import Path
import threading
import time

from buzz_agent_bridge.crypto import AEADCodec, verify_nostr
from buzz_agent_bridge.http import ProtectedStore, PublicHTTPS, RPC, http_server
from .broker import Broker
from .ipc import LocalServer
from .ledger import Ledger, private_directory
from .tools import JobTools
from .transports import CliTransport
from .providers import bind_provider_scope, get_provider


class Application:
    """Same package/version as frontend, independent process lifetime.

    No relay receive loop: official buzz-acp is the sole incoming receiver.
    No legacy direct reply/send tools or retrying DeliveryQueue in this path.
    This constructor never looks up a vault, generates keys, or installs a job.
    """
    def __init__(self, directory, storage_key, principal, channel, owner, own_pubkey,
                 authenticate, authorize, fetch, cli_binary, credential_env, *,
                 activation, relay_url="https://relay.example.invalid", now=time.time, post=None, audit=lambda value: None,
                 restored=False, subscriptions_directory=None, provider=None):
        self.provider = provider or get_provider()
        directory = private_directory(directory)
        self.codec = AEADCodec(storage_key)
        self.ledger = Ledger(directory / "ledger", self.codec.seal, self.codec.open, restored=restored)
        try:
            self.subscriptions = ProtectedStore(
                private_directory(subscriptions_directory or directory / "subscriptions"),
                self.codec.seal, self.codec.open)
        except BaseException:
            self.ledger.close()
            raise
        self.subscription_lock = threading.RLock()
        self.authorize = lambda actor, target: actor == principal and target == channel and authorize(actor, target)
        try:
            self.broker = Broker(self.ledger, principal, channel, owner, self.authorize, fetch,
                                 verify_nostr, activation=activation, now=now, audit=audit)
        except BaseException:
            self.close()
            raise
        self.broker.own_pubkey = own_pubkey
        try:
            bind_provider_scope(self.ledger, self.provider.info.id)
            binding = self.provider.bind(subscriptions=self.subscriptions, authorize=self.authorize,
                post=post or PublicHTTPS(), now=now, own_pubkey=own_pubkey, lock=self.subscription_lock)
        except BaseException:
            self.close()
            raise
        self.events = binding.registration
        self.tools = JobTools(self.broker)
        events, subscription_lock = self.events, self.subscription_lock
        class SubscriptionRPC:
            def handle(self, *args, **kwargs):
                with subscription_lock:
                    return events.handle(*args, **kwargs)
        # Do not hold subscription_lock across job controls: the worker takes
        # effect gate -> subscription_lock, while cancellation takes effect gate.
        self.rpc = RPC(SubscriptionRPC(), self.tools)
        self.authenticate, self.directory, self.audit = authenticate, directory, audit
        self.wake = binding.wake
        self.publisher = CliTransport(cli_binary, channel, own_pubkey, credential_env, fetch,
                                      verify_nostr, relay_url=relay_url, on_spawn=self.record_child)

    def record_child(self, ident, pid):
        with self.ledger.transaction():
            entry = self.ledger.get("outbox", ident)
            if entry is None or entry["state"] != "sending":
                raise RuntimeError("Publication intent missing")
            entry["child_pid"] = pid  # Diagnostic only; inherited lease is the authority.
            self.ledger.put("outbox", ident, entry)

    def server(self, port=18302):
        # port=0 is explicitly supported for isolated tests.
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        server = http_server(("127.0.0.1", port), self.rpc, self.authenticate, allowed_hosts)
        if port == 0:
            allowed_hosts.clear()
            allowed_hosts.update({f"127.0.0.1:{server.server_port}", f"localhost:{server.server_port}"})
        return server

    def run(self, stop, *, socket_path, port=18302, on_ready=lambda: None):
        servers, threads = [], []
        try:
            servers.append(LocalServer(socket_path, self.broker))
            servers.append(self.server(port))
            for server in servers:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                threads.append(thread)
            on_ready()
            while not stop.is_set():
                for stage, transport in (("wake", self.wake), ("response", self.publisher)):
                    try:
                        self.broker.drain_one(stage, transport)
                    except Exception:
                        self.audit({"event": "worker_blocked", "stage": stage})
                stop.wait(.2)
        finally:
            # shutdown() blocks when serve_forever() has never started.
            for server in servers[:len(threads)]:
                server.shutdown()
            for server in servers:
                server.server_close()
            for thread in threads:
                thread.join(timeout=2)
            self.close()

    def close(self):
        self.subscriptions.close()
        self.ledger.close()
