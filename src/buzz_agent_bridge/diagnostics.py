"""Bounded operator metadata: no source text, URLs, credentials or exception text."""
from collections import Counter
import json
import re
import sys


def audit(event):
    safe = {}
    for name in ("event", "stage", "state"):
        value = event.get(name)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_]{1,64}", value):
            safe[name] = value
    count = event.get("count")
    if type(count) is int and 0 <= count <= 100000:
        safe["count"] = count
    if safe.get("event"):
        print(json.dumps(safe, sort_keys=True), file=sys.stderr, flush=True)


def snapshot(broker, subscriptions=None):
    jobs = broker.ledger.rows("jobs")
    result = {"host": "running", "job_count": len(jobs),
              "execution": dict(Counter(job["execution"] for job in jobs)),
              "dispatch": dict(Counter(job["dispatch"] for job in jobs)),
              "delivery": dict(Counter(job["delivery"] for job in jobs)),
              "quarantined": sum(bool(job["quarantined"]) for job in jobs),
              "credentials_checked": False, "relay_checked": False}
    if subscriptions is not None:
        result["active_subscriptions"] = sum(
            1 for key in subscriptions if key.startswith("sub_")
            and subscriptions[key].get("principal") == broker.principal
            and subscriptions[key].get("channel") == broker.channel
            and subscriptions[key].get("expires", 0) > broker.now())
    return result


def delivery_proof(broker, publisher, query, request_id, generation):
    """Re-fetch signed evidence; never publish, complete, retry or mutate jobs."""
    from .crypto import verify_nostr
    if query is None or type(generation) is not int or generation < 1:
        raise ValueError("Readback unavailable")
    with broker.effects:
        job = broker._job(broker.principal, request_id, generation)
        if job["delivery"] != "delivered" or not job.get("event_id"):
            raise ValueError("Delivery not confirmed")
        source = broker.current_source(broker.principal, job)
        entry = broker.ledger.get("outbox", f"{request_id}:{generation}:response")
        if not entry or entry.get("receipt", {}).get("signed_readback") is not True:
            raise ValueError("Signed receipt absent")
        plan = publisher.prepare({**job, "source": source}, entry)
        publisher.verify_receipt(plan, job["event_id"])
        rows = query([{"kinds": [9], "#h": [broker.channel], "authors": [broker.own_pubkey],
                       "since": source["created_at"], "limit": 100}])
        if (not isinstance(rows, list) or len(rows) > 100
                or any(not verify_nostr(row) for row in rows)):
            raise ValueError("Readback signature rejected")
        def same_destination(row):
            channels = [tag[1] for tag in row["tags"] if len(tag) >= 2 and tag[0] == "h"]
            edges = [tag for tag in row["tags"] if tag and tag[0] == "e"]
            if channels != [broker.channel]:
                return False
            if entry["route"] == "channel":
                return not edges
            expected = {"reply": source["message_id"]}
            if source["thread_root"] != source["message_id"]:
                expected["root"] = source["thread_root"]
            return (len(edges) == len(expected) and all(len(tag) >= 4 for tag in edges)
                    and {tag[3]: tag[1] for tag in edges} == expected)

        matches = [row for row in rows if row["kind"] == 9 and row["pubkey"] == broker.own_pubkey
                   and row["content"] == entry["text"] and same_destination(row)]
        if len(matches) != 1 or matches[0]["id"] != job["event_id"]:
            raise ValueError("Unique receipt not confirmed")
        return {"request_id": request_id, "generation": generation, "delivery": "delivered",
                "event_id": job["event_id"], "signed_relay_readback": True, "exact_body": True,
                "exact_thread": True, "route": entry["route"], "matching_reply_count": 1,
                "bounded_query_limit": 100, "message_published_by_verifier": False}
