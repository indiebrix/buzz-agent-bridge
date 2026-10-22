"""MCP Events transport independent of any external message system.

Hosts own source validation, durable effect intents, result tools and publication.
An injected HTTPS transport must pin public addresses, verify TLS, reject redirects
and enforce bounded I/O. No credentials, endpoints or tasks are created on import.
"""
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit

VERSION = '2026-07-28'


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def subscription_id(principal, url, name, arguments):
    return 'sub_' + hashlib.sha256(encoded([principal, url, name, arguments])).hexdigest()


def key(secret):
    if not isinstance(secret, str) or not secret.startswith('whsec_'):
        raise ValueError('Invalid webhook key')
    raw = base64.b64decode(secret[6:], validate=True)
    if not 24 <= len(raw) <= 64:
        raise ValueError('Invalid webhook key length')
    return raw


def headers(secret, sub_id, event_id, body, now, *, previous_secret=None):
    stamp = str(int(now))
    signed = event_id.encode() + b'.' + stamp.encode() + b'.' + body
    secrets_to_sign = [secret]
    if previous_secret is not None and previous_secret != secret:
        secrets_to_sign.append(previous_secret)
    signatures = ['v1,' + base64.b64encode(hmac.new(key(value), signed, hashlib.sha256).digest()).decode()
                  for value in secrets_to_sign]
    return {'Content-Type': 'application/json', 'webhook-id': event_id,
            'webhook-timestamp': stamp, 'webhook-signature': ' '.join(signatures),
            'X-MCP-Subscription-Id': sub_id}


from .definition import EventDefinition


class Subscriptions:
    """One configured event type; authorization is checked for every operation.

    The store must be encrypted and durable in production. The host serializes
    subscription changes with sends using the same lock. Callback acceptance does
    not establish remote execution or application delivery.
    """
    def __init__(self, definition, store, authorize, verified_https_post, now):
        self.definition = definition
        self.store, self.authorize, self.post = store, authorize, verified_https_post
        self.now = now

    def args(self, principal, params):
        args = params.get('arguments', {})
        if params.get('name') != self.definition.name or set(args) != {self.definition.scope_field}:
            raise ValueError('Invalid event filter')
        scope = args[self.definition.scope_field]
        if not isinstance(scope, str) or not scope or not self.authorize(principal, scope):
            raise PermissionError('Scope denied')
        delivery = params['delivery']
        parsed = urlsplit(delivery['url'])
        if (delivery.get('mode') != 'webhook' or parsed.scheme != 'https'
                or not parsed.hostname or parsed.username or parsed.password or parsed.fragment
                or parsed.port not in (None, 443)):
            raise ValueError('Invalid callback')
        # DNS/IP validation at connection time is mandatory in the injected transport.
        return scope, delivery, subscription_id(principal, delivery['url'], self.definition.name, args)

    def handle(self, principal, method, params=None):
        if not principal:
            raise PermissionError('Authentication required')
        params = params or {}
        if method == 'server/discover':
            return {'resultType': 'complete', 'supportedVersions': [VERSION],
                    'capabilities': {'events': {}}}
        if method == 'events/list':
            return {'events': [self.definition.schema()]}
        if method not in ('events/subscribe', 'events/unsubscribe'):
            raise ValueError('Unsupported method')
        scope, delivery, sub_id = self.args(principal, params)
        if method == 'events/unsubscribe':
            self.store.pop(sub_id, None)
            return {}
        if params.get('cursor') is not None:
            raise ValueError('Replay unsupported')
        secret = delivery['secret']
        key(secret)
        ttl = params.get('ttlMs', 3600000)
        if ttl is None:
            ttl = 3600000
        if type(ttl) is not int or ttl <= 0:
            raise ValueError('Invalid lifetime')
        expires = self.now() + min(ttl, 3600000) / 1000
        previous = self.store.get(sub_id, {})
        verified_at = previous.get('verified_at', float('-inf'))
        cached = (previous.get('principal') == principal and previous.get('url') == delivery['url']
                  and previous.get('secret') == secret and previous.get('expires', 0) > self.now()
                  and 0 <= self.now() - verified_at < 300)
        if not cached:
            challenge = secrets.token_urlsafe(32)
            body = encoded({'type': 'verification', 'challenge': challenge})
            status, response = self.post(delivery['url'], body, headers(secret, sub_id,
                'verify_' + secrets.token_hex(16), body, self.now()))
            if not 200 <= status < 300 or not isinstance(response, dict) or not hmac.compare_digest(
                    str(response.get('challenge', '')), challenge):
                raise ValueError('Callback verification failed')
            verified_at = self.now()
        rotation = {}
        if previous.get('secret') and previous['secret'] != secret and previous.get('expires', 0) > self.now():
            rotation = {'previous_secret': previous['secret'], 'rotate_until': self.now() + 300}
        elif previous.get('rotate_until', 0) > self.now():
            rotation = {name: previous[name] for name in ('previous_secret', 'rotate_until')}
        self.store[sub_id] = {'principal': principal, self.definition.scope_field: scope, 'url': delivery['url'],
            'secret': secret, 'expires': expires, 'verified_at': verified_at, **rotation,
            'seen': previous.get('seen', set())}
        return {'id': sub_id, 'refreshBefore': datetime.fromtimestamp(expires, timezone.utc).isoformat(),
                'cursor': None, 'truncated': False}

