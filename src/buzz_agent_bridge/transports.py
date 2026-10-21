"""Existing MCP Events and official Buzz CLI adapters; no secret acquisition."""
from datetime import datetime, timezone
import json
import subprocess

from buzz_agent_bridge.events import NAME, encoded, headers, validate_serialized_event
from .broker import NotReady, identifier


class WebhookTransport:
    """One HTTP attempt per persisted wake intent. HTTP ACK is not execution."""
    def __init__(self, subscriptions, post, authorize, now, lock):
        self.subscriptions, self.post = subscriptions, post
        self.authorize, self.now, self.lock = authorize, now, lock

    def prepare(self, job, entry):
        with self.lock:
            candidates = [(key, self.subscriptions[key]) for key in self.subscriptions
                          if key.startswith("sub_")]
            candidates = [(key, sub) for key, sub in candidates
                          if sub["principal"] == job["principal"]
                          and sub["channel"] == job["source"]["channel"]
                          and sub["expires"] > self.now()
                          and self.authorize(sub["principal"], sub["channel"])]
            if len(candidates) != 1:
                raise NotReady("One active subscription required")
            ident, sub = candidates[0]
            source = job["source"]
            body = encoded({
                "eventId": "buzz_" + source["message_id"], "name": NAME, "cursor": None,
                "timestamp": datetime.fromtimestamp(source["created_at"], timezone.utc).isoformat(),
                "data": {"channel": source["channel"], "message_id": source["message_id"],
                         "author": source["author"], "text": source["text"]},
            })
            validate_serialized_event(body)
            # Persist only destination ID, never a new plaintext credential copy.
            return {"destination": ident, "body": body, "principal": job["principal"],
                    "channel": source["channel"], "message_id": source["message_id"]}

    def send(self, plan, lease_fd):
        with self.lock:
            sub = self.subscriptions.get(plan["destination"])
            if (sub is None or sub["expires"] <= self.now()
                    or sub["principal"] != plan["principal"] or sub["channel"] != plan["channel"]
                    or not self.authorize(sub["principal"], sub["channel"])):
                raise PermissionError("Subscription no longer available")
            status, _ = self.post(sub["url"], plan["body"], headers(
                sub["secret"], plan["destination"], "buzz_" + plan["message_id"],
                plan["body"], self.now()))
        return {"accepted": 200 <= status < 300, "http_status": status}


class CliTransport:
    """One fixed-channel subprocess; credentials are injected by an approved host.

    env_loader must return only the approved existing identity's minimal env.
    The child inherits the broker lease, so a surviving CLI prevents another
    broker/publisher starting after its parent dies. Never retries a timeout.
    """
    def __init__(self, binary, channel, own_pubkey, env_loader, fetch, verify, *,
                 relay_url="https://relay.example.invalid", timeout=30, popen=subprocess.Popen, on_spawn=lambda ident, pid: None):
        self.binary, self.channel, self.own_pubkey = binary, channel, own_pubkey
        self.relay_url = relay_url
        self.env_loader, self.fetch, self.verify = env_loader, fetch, verify
        self.timeout, self.popen, self.on_spawn = timeout, popen, on_spawn

    def prepare(self, job, entry):
        if job["source"]["channel"] != self.channel or entry["stage"] != "response":
            raise PermissionError("Publication scope denied")
        return {"destination": self.channel, "source": job["source"], "route": entry["route"],
                "text": entry["text"], "outbox_id": entry["id"]}

    def send(self, plan, lease_fd):
        args = [self.binary, "--relay", self.relay_url, "messages", "send",
                "--channel", self.channel, "--content", "-"]
        if plan["route"] == "thread":
            args += ["--reply-to", plan["source"]["message_id"]]
        env = dict(self.env_loader())
        process = None
        try:
            process = self.popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, env=env, pass_fds=(lease_fd,))
            self.on_spawn(plan["outbox_id"], process.pid)
            stdout, _ = process.communicate(plan["text"], timeout=self.timeout)
        except subprocess.TimeoutExpired:
            # Killing only the child cannot undo a relay write. Persist uncertainty.
            process.kill()
            process.communicate()
            raise RuntimeError("CLI outcome unknown") from None
        except BaseException:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
            raise
        finally:
            env.clear()
        if process.returncode or len(stdout.encode()) > 1048576:
            raise RuntimeError("CLI outcome unknown")
        receipt = json.loads(stdout)
        ident = receipt.get("event_id")
        if receipt.get("accepted") is not True or not identifier(ident):
            raise ValueError("CLI acceptance unconfirmed")
        return self.verify_receipt(plan, ident)

    def verify_receipt(self, plan, ident):
        """Read-only proof shared by first delivery and explicit reconciliation."""
        if not identifier(ident) or plan["destination"] != self.channel:
            raise ValueError("Invalid receipt identity")
        rows = self.fetch(ident)
        if len(rows) != 1:
            raise ValueError("Signed readback unavailable")
        event = rows[0]
        if (not self.verify(event) or event["id"] != ident or event["pubkey"] != self.own_pubkey
                or event["kind"] != 9 or event["content"] != plan["text"]
                or [tag[1] for tag in event["tags"] if len(tag) >= 2 and tag[0] == "h"] != [self.channel]):
            raise ValueError("Signed readback mismatch")
        edges = [tag for tag in event["tags"] if tag and tag[0] == "e"]
        if plan["route"] == "channel":
            if edges:
                raise ValueError("Unexpected thread")
        else:
            source = plan["source"]
            # Official SDK thread_tags emits one reply edge for a direct reply,
            # and root + reply edges only for a nested reply.
            expected = {"reply": source["message_id"]}
            if source["thread_root"] != source["message_id"]:
                expected["root"] = source["thread_root"]
            if (len(edges) != len(expected) or any(len(tag) < 4 for tag in edges)
                    or {tag[3]: tag[1] for tag in edges} != expected):
                raise ValueError("Thread readback mismatch")
        return {"accepted": True, "event_id": ident, "signed_readback": True}
