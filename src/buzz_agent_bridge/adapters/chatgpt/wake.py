"""MCP Events wake-up; the existing Dot remains the execution owner."""
from datetime import datetime, timezone
from .events import NAME, encoded, headers, validate_serialized_event
from ...core.broker import NotReady


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
                plan["body"], self.now(), previous_secret=(
                    sub.get("previous_secret") if sub.get("rotate_until", 0) > self.now() else None)))
        return {"accepted": 200 <= status < 300, "http_status": status}
