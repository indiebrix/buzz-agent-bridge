"""A single verified webhook attempt, composed with a host's durable outbox."""
from .events import encoded, headers, subscription_id


class NotReady(RuntimeError):
    pass


class Delivery:
    def __init__(self, definition, subscriptions, post, authorize, now, lock):
        self.definition, self.subscriptions, self.post = definition, subscriptions, post
        self.authorize, self.now, self.lock = authorize, now, lock

    def prepare(self, principal, scope, event):
        body = encoded(event)
        value = self.definition.validate_wire(body)
        with self.lock:
            candidates = [(key, self.subscriptions[key]) for key in self.subscriptions
                          if key.startswith("sub_")]
            candidates = [(key, sub) for key, sub in candidates
                          if sub["principal"] == principal
                          and sub.get(self.definition.scope_field) == scope
                          and key == subscription_id(principal, sub["url"], self.definition.name,
                                                     {self.definition.scope_field: scope})
                          and sub["expires"] > self.now()
                          and self.authorize(principal, scope)]
            if len(candidates) != 1:
                raise NotReady("One active subscription required")
            ident, _ = candidates[0]
        return {"destination": ident, "body": body, "principal": principal,
                "scope": scope, "event_id": value["eventId"]}

    def send(self, plan):
        # Host persists the sending intent before this call. Never retry here;
        # a timeout can mean that the remote Dot has already received the event.
        event = self.definition.validate_wire(plan["body"])
        if event["eventId"] != plan["event_id"]:
            raise ValueError("Event identity changed")
        with self.lock:
            sub = self.subscriptions.get(plan["destination"])
            if (sub is None or sub["expires"] <= self.now()
                    or sub["principal"] != plan["principal"]
                    or sub.get(self.definition.scope_field) != plan["scope"]
                    or plan["destination"] != subscription_id(plan["principal"], sub["url"],
                        self.definition.name, {self.definition.scope_field: plan["scope"]})
                    or not self.authorize(sub["principal"], sub[self.definition.scope_field])):
                raise PermissionError("Subscription no longer available")
            status, _ = self.post(sub["url"], plan["body"], headers(
                sub["secret"], plan["destination"], plan["event_id"], plan["body"], self.now(),
                previous_secret=(sub.get("previous_secret")
                                 if sub.get("rotate_until", 0) > self.now() else None)))
        return {"accepted": 200 <= status < 300, "http_status": status}
