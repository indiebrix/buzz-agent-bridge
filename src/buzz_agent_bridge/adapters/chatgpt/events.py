"""Buzz payload policy over the independent ChatGPT Dots connection package."""
from datetime import datetime, timezone
import json
from chatgpt_dots.definition import EventDefinition
from chatgpt_dots.events import Subscriptions, VERSION, encoded, headers, key

NAME = 'buzz.message.created'
DEFINITION = EventDefinition.string_fields(NAME, 'New message in an authorized Buzz channel.',
                                           'channel', ('channel', 'message_id', 'author', 'text'))


class Events(Subscriptions):
    """Compatibility API; Buzz owns source admission and legacy ingest policy."""
    def __init__(self, store, authorize, verified_https_post, now, own_pubkey, queue=None):
        super().__init__(DEFINITION, store, authorize, verified_https_post, now)
        self.own_pubkey, self.queue = own_pubkey, queue

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
                event['eventId'], body, self.now(), previous_secret=(
                    sub.get('previous_secret') if sub.get('rotate_until', 0) > self.now() else None)))
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
