"""Buzz -> MCP Events core. No listener, credential lookup or network by default.

The host must authenticate each request and inject authorize, verified_https_post
and a durable transactional store. post MUST pin validated public addresses,
verify TLS, reject redirects, and enforce timeouts on every connection.
"""
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit

NAME = 'buzz.message.created'
VERSION = '2026-07-28'


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def key(secret):
    if not isinstance(secret, str) or not secret.startswith('whsec_'):
        raise ValueError('Invalid webhook key')
    raw = base64.b64decode(secret[6:], validate=True)
    if not 24 <= len(raw) <= 64:
        raise ValueError('Invalid webhook key length')
    return raw


def headers(secret, sub_id, event_id, body, now):
    stamp = str(int(now))
    signed = event_id.encode() + b'.' + stamp.encode() + b'.' + body
    signature = base64.b64encode(hmac.new(key(secret), signed, hashlib.sha256).digest()).decode()
    return {'Content-Type': 'application/json', 'webhook-id': event_id,
            'webhook-timestamp': stamp, 'webhook-signature': 'v1,' + signature,
            'X-MCP-Subscription-Id': sub_id}


class Events:
    """Injected store mapping is in-memory in tests; never use it for deployment.

    authorize(principal, channel) must recheck membership each invocation.
    Input messages must come from a signature-validated Buzz relay client.
    No replay is advertised; caller must not feed historical messages as new.
    """
    def __init__(self, store, authorize, verified_https_post, now, own_pubkey, queue=None):
        self.store, self.authorize, self.post = store, authorize, verified_https_post
        self.now, self.own_pubkey = now, own_pubkey
        self.queue = queue

    def args(self, principal, params):
        args = params.get('arguments', {})
        if params.get('name') != NAME or set(args) != {'channel'}:
            raise ValueError('Invalid event filter')
        channel = args['channel']
        if not isinstance(channel, str) or not channel or not self.authorize(principal, channel):
            raise PermissionError('Channel denied')
        delivery = params['delivery']
        parsed = urlsplit(delivery['url'])
        if (delivery.get('mode') != 'webhook' or parsed.scheme != 'https'
                or not parsed.hostname or parsed.username or parsed.password or parsed.fragment
                or parsed.port not in (None, 443)):
            raise ValueError('Invalid callback')
        # DNS/IP validation at connection time is mandatory in the injected transport.
        identity = [principal, delivery['url'], NAME, args]
        return channel, delivery, 'sub_' + hashlib.sha256(encoded(identity)).hexdigest()

    def handle(self, principal, method, params=None):
        if not principal:
            raise PermissionError('Authentication required')
        params = params or {}
        if method == 'server/discover':
            return {'resultType': 'complete', 'supportedVersions': [VERSION],
                    'capabilities': {'events': {}}}
        if method == 'events/list':
            return {'events': [{'name': NAME, 'description': 'New message in an authorized Buzz channel.',
                'delivery': ['webhook'], 'inputSchema': {'type': 'object', 'properties': {
                    'channel': {'type': 'string'}}, 'required': ['channel'], 'additionalProperties': False},
                'payloadSchema': {'type': 'object', 'properties': {field: {'type': 'string'} for field in
                    ['channel', 'message_id', 'author', 'text']}, 'required':
                    ['channel', 'message_id', 'author', 'text'], 'additionalProperties': False}}]}
        if method not in ('events/subscribe', 'events/unsubscribe'):
            raise ValueError('Unsupported method')
        channel, delivery, sub_id = self.args(principal, params)
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
        challenge = secrets.token_urlsafe(32)
        body = encoded({'type': 'verification', 'challenge': challenge})
        status, response = self.post(delivery['url'], body, headers(secret, sub_id,
            'verify_' + secrets.token_hex(16), body, self.now()))
        if not 200 <= status < 300 or not isinstance(response, dict) or not hmac.compare_digest(
                str(response.get('challenge', '')), challenge):
            raise ValueError('Callback verification failed')
        self.store[sub_id] = {'principal': principal, 'channel': channel, 'url': delivery['url'],
            'secret': secret, 'expires': expires,
            'seen': self.store.get(sub_id, {}).get('seen', set())}
        return {'id': sub_id, 'refreshBefore': datetime.fromtimestamp(expires, timezone.utc).isoformat(),
                'cursor': None, 'truncated': False}

    def ingest(self, message):
        """Deliver a normalized signature-validated kind-9 message; no raw event logging.

        Returns only counts. Delivery failures remain retryable by caller with same
        message ID; permanent 410/413 disables this subscription. No hidden retry loop.
        """
        if set(message) != {'channel', 'id', 'author', 'text', 'created_at', 'kind'}:
            raise ValueError('Invalid normalized message')
        if message['kind'] != 9 or message['author'] == self.own_pubkey:
            return 0
        if any(not isinstance(message[f], str) for f in ['channel', 'id', 'author', 'text']):
            raise ValueError('Invalid message fields')
        if len(message['id']) != 64 or any(c not in '0123456789abcdef' for c in message['id']):
            raise ValueError('Invalid event ID')
        event = {'eventId': 'buzz_' + message['id'], 'name': NAME,
            'timestamp': datetime.fromtimestamp(message['created_at'], timezone.utc).isoformat(),
            'data': {'channel': message['channel'], 'message_id': message['id'],
                     'author': message['author'], 'text': message['text']}, 'cursor': None}
        body = encoded(event)
        if len(body) > 262144:
            raise ValueError('Event too large')
        count = 0
        for sub_id, sub in list(self.store.items()):
            if not sub_id.startswith('sub_'):
                continue
            if sub['expires'] <= self.now() or not self.authorize(sub['principal'], sub['channel']):
                del self.store[sub_id]
                continue
            if sub['channel'] != message['channel'] or message['id'] in sub['seen']:
                continue
            if self.queue is not None:
                self.queue.enqueue(sub_id, event, body)
                continue
            status, _ = self.post(sub['url'], body, headers(sub['secret'], sub_id,
                event['eventId'], body, self.now()))
            if 200 <= status < 300:
                sub['seen'].add(message['id'])
                self.store[sub_id] = sub
                count += 1
            elif status in (410, 413):
                del self.store[sub_id]
        return count


def validate_serialized_event(body):
    """Validate the actual wire bytes, not a separate pre-serialization object."""
    if not isinstance(body,bytes) or len(body)>262144:raise ValueError('Invalid wire body')
    value=json.loads(body)
    if set(value)!={'eventId','name','timestamp','data','cursor'} or value['name']!=NAME or value['cursor'] is not None:raise ValueError('Invalid envelope')
    if not isinstance(value['eventId'],str) or not value['eventId'].startswith('buzz_'):raise ValueError('Invalid event ID')
    timestamp=datetime.fromisoformat(value['timestamp'].replace('Z','+00:00'))
    if timestamp.tzinfo is None:raise ValueError('Timezone required')
    data=value['data']
    if set(data)!={'channel','message_id','author','text'} or any(not isinstance(v,str) for v in data.values()):raise ValueError('Invalid data')
    if value['eventId']!='buzz_'+data['message_id']:raise ValueError('Event ID mismatch')
    return value


def thread_root(event):
    """Resolve a signed event's explicit NIP-10 root; reject ambiguous metadata."""
    import re
    marked={label:[] for label in ('root','reply')}
    for tag in event.get('tags',[]):
        if len(tag)>=4 and tag[0]=='e' and tag[3] in marked:
            if not re.fullmatch('[0-9a-f]{64}',tag[1]):raise ValueError('Invalid thread reference')
            marked[tag[3]].append(tag[1])
    if any(len(v)>1 for v in marked.values()) or (marked['reply'] and not marked['root']):
        raise ValueError('Ambiguous thread references')
    return marked['root'][0] if marked['root'] else event['id']
