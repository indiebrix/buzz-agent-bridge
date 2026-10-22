"""Compatible Buzz constructor; neutral lifecycle lives in core.broker."""
import time

from .adapters.buzz.source import BuzzSourcePolicy
from .core.broker import (AdmissionCancelled, Broker as CoreBroker, NotReady,
                          identifier, outbox_id, request_id)


class Broker(CoreBroker):
    """Preserve the existing constructor while composing the Buzz source policy."""
    def __init__(self, ledger, principal, channel, owner, authorize, fetch, verify,
                 *, activation, now=time.time, max_age=3600, lifetime=86400,
                 capacity=10000, audit=lambda event: None):
        policy = BuzzSourcePolicy(fetch, verify, owner, channel,
                                  activation=activation, now=now, max_age=max_age)
        super().__init__(ledger, principal, channel, owner, authorize, policy,
                         activation=activation, now=now, max_age=max_age,
                         lifetime=lifetime, capacity=capacity, audit=audit)

    @property
    def fetch(self):
        return self.source_policy.fetch

    @fetch.setter
    def fetch(self, value):
        self.source_policy.fetch = value

    @property
    def verify(self):
        return self.source_policy.verify

    @verify.setter
    def verify(self, value):
        self.source_policy.verify = value
