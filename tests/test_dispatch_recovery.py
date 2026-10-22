"""Explicit pre-effect recovery; synthetic source and transport only."""
import unittest
import urllib.error
from unittest.mock import Mock

from test_buzz_durable_jobs import Fixture, FakeTransport
from buzz_agent_bridge.broker import outbox_id
from buzz_agent_bridge.relay import RelayReader


class DispatchRecoveryTests(Fixture, unittest.TestCase):
    def setUp(self):
        self.setup_fixture()

    def tearDown(self):
        self.teardown_fixture()

    def blocked(self):
        self.clock += 1
        ident = self.admit()
        self.allowed = False
        self.assertEqual(self.broker.drain_one('wake', FakeTransport()), {'state': 'blocked'})
        self.allowed = True
        return ident

    def test_resume_same_request_generation_once_then_single_send(self):
        ident = self.blocked()
        before = self.ledger.get('jobs', ident)
        result = self.broker.resume_blocked_wake('dot', ident, 1)
        self.assertEqual((result['request_id'], result['generation'], result['dispatch']), (ident, 1, 'pending'))
        after = self.ledger.get('jobs', ident)
        self.assertEqual(after['source'], before['source'])
        self.assertEqual(after['acp'], before['acp'])
        self.assertIsNone(self.ledger.get('outbox', outbox_id(after, 'response')))
        transport = FakeTransport()
        self.assertEqual(self.broker.drain_one('wake', transport), {'state': 'accepted'})
        self.assertIsNone(self.broker.drain_one('wake', transport))
        self.assertEqual(len(transport.calls), 1)
        with self.assertRaises(ValueError):
            self.broker.resume_blocked_wake('dot', ident, 1)

    def test_scope_and_generation_are_rechecked(self):
        ident = self.blocked()
        self.allowed = False
        with self.assertRaises(PermissionError):
            self.broker.resume_blocked_wake('dot', ident, 1)
        self.allowed = True
        with self.assertRaises(ValueError):
            self.broker.resume_blocked_wake('dot', ident, 2)
        job = self.ledger.get('jobs', ident)
        self.events[job['source']['message_id']]['content'] = 'tampered'
        with self.assertRaises(ValueError):
            self.broker.resume_blocked_wake('dot', ident, 1)

    def test_attempt_metadata_and_ineligible_jobs_never_rearm(self):
        for change in ({'destination': 'sub_test'}, {'receipt': None}, {'child_pid': 123},
                       {'resume_count': 1}, {'state': 'sending'}, {'state': 'uncertain'}):
            with self.subTest(change=change):
                ident = self.blocked()
                job = self.ledger.get('jobs', ident)
                entry = self.ledger.get('outbox', outbox_id(job, 'wake'))
                with self.ledger.transaction():
                    entry.update(change)
                    self.ledger.put('outbox', entry['id'], entry)
                with self.assertRaises(ValueError):
                    self.broker.resume_blocked_wake('dot', ident, 1)
        for key, value in [('cancel_requested', True), ('quarantined', True),
                           ('execution', 'running'), ('delivery', 'queued'), ('deadline', 0)]:
            with self.subTest(field=key):
                ident = self.blocked()
                with self.ledger.transaction():
                    job = self.ledger.get('jobs', ident)
                    job[key] = value
                    self.ledger.put('jobs', ident, job)
                with self.assertRaises(ValueError):
                    self.broker.resume_blocked_wake('dot', ident, 1)

    def test_safe_reason_is_recorded_without_exception_text(self):
        ident = self.blocked()
        job = self.ledger.get('jobs', ident)
        entry = self.ledger.get('outbox', outbox_id(job, 'wake'))
        self.assertEqual(entry['blocked_reason'], 'principal_or_membership')
        self.assertEqual(self.audit[-1]['event'], 'effect_blocked')

    def test_relay_diagnostics_keep_fail_closed_and_redact_raw_errors(self):
        audit = []
        relay = RelayReader({'principal': 'dot', 'channel': 'test'}, self.agent, 'fixture', audit=audit.append)
        relay.query = Mock(side_effect=urllib.error.HTTPError(
            'https://example.invalid/secret', 429, 'PRIVATE ERROR', {}, None))
        self.assertFalse(relay.authorize('dot', 'test'))
        self.assertEqual(audit, [{'event': 'relay_authorization_failed', 'stage': 'http_429'}])
        relay.query = Mock(return_value=[])
        self.assertFalse(relay.authorize('dot', 'test'))
        self.assertEqual(audit[-1]['stage'], 'membership_mismatch')


if __name__ == '__main__':
    unittest.main()
