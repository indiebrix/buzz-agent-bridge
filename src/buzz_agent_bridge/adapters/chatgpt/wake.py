"""Buzz job serialization over the independent Dot webhook transport."""
from chatgpt_dots.delivery import Delivery, NotReady as ConnectorNotReady
from .events import DEFINITION, validate_serialized_event
from ...core.broker import NotReady


class WebhookTransport:
    """Keep the existing durable job/outbox and wake API unchanged."""
    def __init__(self, subscriptions, post, authorize, now, lock):
        self.subscriptions, self.post = subscriptions, post
        self.authorize, self.now, self.lock = authorize, now, lock

    def connector(self):
        return Delivery(DEFINITION, self.subscriptions, self.post, self.authorize, self.now, self.lock)

    def prepare(self, job, entry):
        source = job["source"]
        event = DEFINITION.event("buzz_" + source["message_id"], source["created_at"],
            {key: source[key] for key in ("channel", "message_id", "author", "text")})
        try:
            plan = self.connector().prepare(job["principal"], source["channel"], event)
        except ConnectorNotReady as error:
            raise NotReady(str(error)) from None
        validate_serialized_event(plan["body"])
        # Retain the documented plan shape for embedding hosts.
        return {"destination": plan["destination"], "body": plan["body"],
                "principal": plan["principal"], "channel": source["channel"],
                "message_id": source["message_id"]}

    def send(self, plan, lease_fd):
        validate_serialized_event(plan["body"])
        return self.connector().send({"destination": plan["destination"], "body": plan["body"],
            "principal": plan["principal"], "scope": plan["channel"],
            "event_id": "buzz_" + plan["message_id"]})
