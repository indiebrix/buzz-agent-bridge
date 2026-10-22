"""Verified admission, generation-fenced completion, and one external-effect gate."""
import hashlib
import json
import re
import threading
import time

from .contracts import VerifiedSource

_READ_ONLY = object()


class NotReady(Exception):
    """No effect was attempted; leave the durable entry pending."""


class AdmissionCancelled(Exception):
    pass


def identifier(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def request_id(principal, source_id):
    return "job_" + hashlib.sha256(json.dumps([principal, source_id]).encode()).hexdigest()


def outbox_id(job, stage):
    return f"{job['request_id']}:{job['generation']}:{stage}"


class Broker:
    def __init__(self, ledger, principal, channel, owner, authorize, source_policy,
                 *, activation, now=time.time, max_age=3600, lifetime=86400,
                 capacity=10000, audit=lambda event: None):
        self.ledger, self.principal, self.channel, self.owner = ledger, principal, channel, owner
        self.authorize, self.source_policy = authorize, source_policy
        self.activation, self.now, self.max_age = activation, now, max_age
        self.lifetime, self.capacity, self.audit = lifetime, capacity, audit
        self.effects = threading.RLock()
        self.admissions_lock = threading.RLock()
        self.admissions = {}
        scope = {"principal": principal, "channel": channel, "owner": owner, "activation": activation}
        with ledger.transaction():
            previous = ledger.get("controls", "__scope__")
            if previous is not None and previous != scope:
                raise PermissionError("Ledger scope changed")
            ledger.put("controls", "__scope__", scope)

    def check_principal(self, principal):
        if principal != self.principal or not self.authorize(principal, self.channel):
            raise PermissionError("Scope denied")

    def source(self, principal, ident, *, new=False):
        self.check_principal(principal)
        if not identifier(ident):
            raise ValueError("Exact source ID required")
        source = self.source_policy.read(ident, new=new)
        if not isinstance(source, VerifiedSource) or source.message_id != ident:
            raise ValueError("Verified source contract rejected")
        if source.author != self.owner or source.channel != self.channel:
            raise PermissionError("Source scope denied")
        return source.as_dict()

    def _admission(self, ident):
        if not isinstance(ident, str) or not re.fullmatch("[0-9a-f]{32}", ident):
            raise ValueError("Invalid admission ID")
        with self.admissions_lock:
            cutoff = self.now() - 3600
            self.admissions = {key: value for key, value in self.admissions.items()
                               if not value["finished"] or value["created"] >= cutoff}
            if ident not in self.admissions:
                if len(self.admissions) >= 1000:
                    raise ValueError("Admission capacity reached")
                self.admissions[ident] = {"cancel": threading.Event(), "finished": False,
                                         "created": self.now(), "accepted": False}
            return self.admissions[ident]

    def current_source(self, principal, job):
        """Revalidate immutable evidence; only derived routing may evolve."""
        source = self.source(principal, job["source"]["message_id"])
        if any(source[key] != job["source"][key] for key in
               ("message_id", "author", "channel", "text", "created_at")):
            raise ValueError("Source evidence changed")
        return source

    def cancel_admission(self, admission_id):
        state = self._admission(admission_id)
        with self.ledger.lock:
            state["cancel"].set()
            state["finished"] = True
            return {"durably_accepted": state["accepted"], "remote_jobs_cancelled": False}

    def admit(self, principal, source_ids, session_id, admission_id, jsonrpc_id=None):
        self.check_principal(principal)
        if (not isinstance(source_ids, list) or not 1 <= len(source_ids) <= 50
                or len(set(source_ids)) != len(source_ids) or not all(identifier(i) for i in source_ids)
                or not isinstance(session_id, str) or not 1 <= len(session_id) <= 128
                or type(jsonrpc_id) not in (str, int, type(None))):
            raise ValueError("Invalid admission")
        state = self._admission(admission_id)
        try:
            verified = []
            for ident in source_ids:
                if state["cancel"].is_set():
                    raise AdmissionCancelled()
                previous = self.ledger.get("jobs", request_id(principal, ident))
                verified.append(self.source(principal, ident, new=previous is None))
            with self.ledger.transaction():
                if state["cancel"].is_set():
                    raise AdmissionCancelled()
                self.check_principal(principal)
                existing_count = len(self.ledger.rows("jobs"))
                new_count = sum(self.ledger.get("jobs", request_id(principal, row["message_id"])) is None
                                for row in verified)
                if existing_count + new_count > self.capacity:
                    raise ValueError("Ledger capacity reached; retention review required")
                results = []
                for source in verified:
                    ident = request_id(principal, source["message_id"])
                    job = self.ledger.get("jobs", ident)
                    if job is None:
                        job = {"request_id": ident, "principal": principal, "source": source,
                               "generation": 1, "execution": "accepted", "dispatch": "pending",
                               "delivery": "waiting", "dot_job_id": None, "cancel_requested": False,
                               "quarantined": False, "created": self.now(),
                               "deadline": self.now() + self.lifetime, "acp": []}
                        self._queue(job, "wake")
                    link = {"session_id": session_id, "jsonrpc_id": jsonrpc_id, "admission_id": admission_id}
                    if link not in job["acp"]:
                        job["acp"] = (job["acp"] + [link])[-100:]
                    self.ledger.put("jobs", ident, job)
                    results.append(self.summary(job))
                state["accepted"] = True
            self.audit({"event": "admission_committed", "count": len(results)})
            return {"durably_accepted": True, "remote_work_complete": False, "jobs": results}
        except BaseException:
            state["accepted"] = False
            raise
        finally:
            state["finished"] = True

    def _queue(self, job, stage, **extra):
        ident = outbox_id(job, stage)
        if self.ledger.get("outbox", ident) is not None:
            raise ValueError("Duplicate outbox intent")
        self.ledger.put("outbox", ident, {"id": ident, "request_id": job["request_id"],
                        "generation": job["generation"], "stage": stage, "state": "pending", **extra})

    def _job(self, principal, ident, generation=_READ_ONLY):
        self.check_principal(principal)
        if not isinstance(ident, str) or not re.fullmatch("job_[0-9a-f]{64}", ident):
            raise ValueError("Invalid request ID")
        job = self.ledger.get("jobs", ident)
        if job is None or job["principal"] != principal:
            raise PermissionError("Job unavailable")
        if generation is not _READ_ONLY and (type(generation) is not int or generation != job["generation"]):
            raise ValueError("Stale generation")
        return job

    @staticmethod
    def summary(job):
        return {**{key: job[key] for key in ("request_id", "generation", "execution", "dispatch",
                "delivery", "dot_job_id", "cancel_requested", "quarantined")},
                "event_id": job.get("event_id")}

    def status(self, principal, ids):
        if not isinstance(ids, list) or not 1 <= len(ids) <= 50:
            raise ValueError("Invalid status request")
        return {"jobs": [self.summary(self._job(principal, ident)) for ident in ids]}

    def pending(self, principal, limit=20):
        self.check_principal(principal)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("Invalid limit")
        rows = []
        for job in self.ledger.rows("jobs"):
            if (job["principal"] == principal and job["execution"] in ("accepted", "running")
                    and not job["cancel_requested"] and not job["quarantined"]
                    and job["deadline"] > self.now()):
                source = self.current_source(principal, job)
                rows.append({**self.summary(job), "source": source})
        return {"jobs": rows[:limit]}

    def start(self, principal, ident, generation, dot_job_id):
        if not isinstance(dot_job_id, str) or not 1 <= len(dot_job_id) <= 128:
            raise ValueError("Invalid dot job ID")
        with self.ledger.transaction():
            job = self._job(principal, ident, generation)
            if job["cancel_requested"] or job["quarantined"] or job["deadline"] <= self.now():
                raise ValueError("Job no longer accepts work")
            if job["execution"] not in ("accepted", "running"):
                raise ValueError("Execution already complete")
            if job["dot_job_id"] not in (None, dot_job_id):
                raise ValueError("Execution identity conflict")
            job.update(execution="running", dot_job_id=dot_job_id)
            self.ledger.put("jobs", ident, job)
            return self.summary(job)

    def complete(self, principal, ident, generation, text, outcome, route="thread"):
        if (not isinstance(text, str) or not 1 <= len(text) <= 12000
                or outcome not in ("succeeded", "failed") or route not in ("thread", "channel")):
            raise ValueError("Invalid completion")
        digest = hashlib.sha256(json.dumps([text, outcome, route]).encode()).hexdigest()
        with self.ledger.transaction():
            job = self._job(principal, ident, generation)
            if job["cancel_requested"] or job["quarantined"] or job["deadline"] <= self.now():
                raise ValueError("Job no longer accepts completion")
            if "completion_digest" in job:
                if job["completion_digest"] != digest:
                    raise ValueError("Completion conflict")
                return self.summary(job)
            self.current_source(principal, job)
            job.update(execution=outcome, delivery="queued", completion_digest=digest)
            self._queue(job, "response", text=text, route=route)
            wake = self.ledger.get("outbox", outbox_id(job, "wake"))
            if wake is not None and wake["state"] == "pending":
                wake["state"] = "suppressed"
                self.ledger.put("outbox", wake["id"], wake)
            self.ledger.put("jobs", ident, job)
            return self.summary(job)

    def reconcile_delivery(self, principal, ident, generation, event_id, transport):
        """Explicit operator receipt: verify an existing event; never send/requeue."""
        if not identifier(event_id):
            raise ValueError("Exact relay receipt required")
        with self.effects, self.ledger.transaction():
            job = self._job(principal, ident, generation)
            entry = self.ledger.get("outbox", outbox_id(job, "response"))
            if job["cancel_requested"] or job["quarantined"] or entry is None:
                raise ValueError("Job cannot be reconciled")
            if job["delivery"] == "delivered" and job.get("event_id") == event_id:
                return self.summary(job)
            if (job["delivery"] != "uncertain" or entry["state"] != "uncertain"
                    or entry["generation"] != generation or job["execution"] not in ("succeeded", "failed")):
                raise ValueError("Only uncertain completed publications can be reconciled")
            source = self.current_source(principal, job)
            receipt = transport.verify_receipt(
                transport.prepare({**job, "source": source}, entry), event_id)
            if (receipt.get("accepted") is not True or receipt.get("signed_readback") is not True
                    or receipt.get("event_id") != event_id):
                raise ValueError("Signed publication proof required")
            entry.update(state="accepted", receipt={**receipt, "reconciled": True})
            job.update(delivery="delivered", event_id=event_id)
            self.ledger.put("outbox", entry["id"], entry)
            self.ledger.put("jobs", ident, job)
        self.audit({"event": "delivery_reconciled", "request_id": ident})
        return self.summary(job)

    def cancel(self, principal, ident, generation, control_id):
        self.check_principal(principal)
        if (type(generation) is not int or generation < 1
                or not isinstance(control_id, str) or not re.fullmatch("[0-9a-f]{32}", control_id)):
            raise ValueError("Explicit cancellation control ID required")
        # Serialize with an already-started bounded effect. Once this returns no
        # further effect can start for the cancelled generation.
        with self.effects, self.ledger.transaction():
            existing = self.ledger.get("controls", control_id)
            if existing is not None:
                if (existing["request_id"] != ident or existing["principal"] != principal
                        or existing.get("generation") != generation):
                    raise ValueError("Control identity conflict")
                self.check_principal(principal)
                return existing["result"]
            job = self._job(principal, ident, generation)
            job["generation"] += 1
            job["cancel_requested"] = True
            if job["delivery"] not in ("delivered", "uncertain"):
                job["delivery"] = "suppressed"
            for entry in self.ledger.rows("outbox"):
                if entry["request_id"] == ident and entry["state"] == "pending":
                    entry["state"] = "suppressed"
                    self.ledger.put("outbox", entry["id"], entry)
            result = {**self.summary(job), "remote_execution_stopped": False,
                      "future_publication_suppressed": True}
            self.ledger.put("jobs", ident, job)
            self.ledger.put("controls", control_id, {"request_id": ident, "principal": principal,
                                                    "generation": generation, "result": result})
            return result

    def drain_one(self, stage, transport):
        if stage not in ("wake", "response"):
            raise ValueError("Unknown stage")
        with self.effects:
            entry = next((row for row in self.ledger.rows("outbox")
                          if row["stage"] == stage and row["state"] == "pending"), None)
            if entry is None:
                return None
            try:
                job = self._job(self.principal, entry["request_id"])
                source = self.current_source(self.principal, job)
            except PermissionError as error:
                reason = {"Scope denied": "principal_or_membership",
                          "Source scope denied": "source_scope",
                          "Source outside activation window": "activation_window"}.get(
                              str(error), "permission_denied")
                with self.ledger.transaction():
                    entry.update(state="blocked", blocked_reason=reason)
                    self.ledger.put("outbox", entry["id"], entry)
                    job = self.ledger.get("jobs", entry["request_id"])
                    job["dispatch" if stage == "wake" else "delivery"] = "blocked"
                    self.ledger.put("jobs", job["request_id"], job)
                self.audit({"event": "effect_blocked", "stage": stage,
                            "state": reason, "request_id": job["request_id"]})
                return {"state": "blocked"}
            with self.ledger.transaction():
                if (job["cancel_requested"] or job["quarantined"] or job["deadline"] <= self.now()
                        or job["generation"] != entry["generation"]):
                    entry["state"] = "suppressed"
                    self.ledger.put("outbox", entry["id"], entry)
                    return {"state": "suppressed"}
            try:
                # Routing is derived from current signed source evidence. Keep
                # the original persisted snapshot intact across version upgrades.
                plan = transport.prepare({**job, "source": source}, entry)
            except NotReady:
                return {"state": "pending"}
            with self.ledger.transaction():
                entry.update(state="sending", destination=plan["destination"])
                self.ledger.put("outbox", entry["id"], entry)
                job["dispatch" if stage == "wake" else "delivery"] = "sending"
                self.ledger.put("jobs", job["request_id"], job)
            self.audit({"event": "effect_started", "stage": stage, "request_id": job["request_id"]})
            try:
                receipt = transport.send(plan, self.ledger.lock_fd)
                if not isinstance(receipt, dict) or receipt.get("accepted") is not True:
                    raise ValueError("Effect acceptance unconfirmed")
                if stage == "response" and (not identifier(receipt.get("event_id"))
                        or receipt.get("signed_readback") is not True):
                    raise ValueError("Publication unconfirmed")
            except Exception:
                receipt = None
            with self.ledger.transaction():
                # Completion can arrive concurrently with webhook dispatch. Read
                # current row again so the effect receipt never erases it.
                job = self.ledger.get("jobs", job["request_id"])
                entry = self.ledger.get("outbox", entry["id"])
                entry["state"] = "accepted" if receipt else "uncertain"
                entry["receipt"] = receipt
                field = "dispatch" if stage == "wake" else "delivery"
                job[field] = ("acknowledged" if stage == "wake" else "delivered") if receipt else "uncertain"
                if stage == "response" and receipt:
                    job["event_id"] = receipt["event_id"]
                self.ledger.put("outbox", entry["id"], entry)
                self.ledger.put("jobs", job["request_id"], job)
            self.audit({"event": "effect_finished", "stage": stage, "state": entry["state"],
                        "request_id": job["request_id"]})
            return {"state": entry["state"]}

    def resume_blocked_wake(self, principal, ident, generation):
        """Explicit one-time recovery of a wake that never reached preparation.

        No network send occurs here. Revalidate current signed source and scope,
        then let the ordinary effect gate make its single attempt. Never rearm
        sending, uncertain, acknowledged, completed, or previously resumed work.
        """
        with self.effects, self.ledger.transaction():
            job = self._job(principal, ident, generation)
            self.current_source(principal, job)
            entry = self.ledger.get("outbox", outbox_id(job, "wake"))
            allowed_keys = {"id", "request_id", "generation", "stage", "state", "blocked_reason"}
            if (job["execution"] != "accepted" or job["dispatch"] != "blocked"
                    or job["delivery"] != "waiting" or job["dot_job_id"] is not None
                    or job["cancel_requested"] or job["quarantined"]
                    or job["deadline"] <= self.now() or job.get("event_id")
                    or "completion_digest" in job or entry is None
                    or set(entry) - allowed_keys or entry["state"] != "blocked"
                    or entry["stage"] != "wake" or entry["request_id"] != ident
                    or entry["generation"] != generation
                    or self.ledger.get("outbox", outbox_id(job, "response")) is not None):
                raise ValueError("Only an unattempted blocked wake can resume once")
            entry.update(state="pending", resume_count=1)
            job["dispatch"] = "pending"
            self.ledger.put("outbox", entry["id"], entry)
            self.ledger.put("jobs", ident, job)
        self.audit({"event": "wake_resumed", "stage": "wake", "request_id": ident})
        return self.summary(job)
