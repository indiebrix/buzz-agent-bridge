"""Verify Buzz source evidence before it enters the durable lifecycle."""
import time

from ...core.contracts import VerifiedSource


class BuzzSourcePolicy:
    def __init__(self, fetch, verify, owner, channel, *, activation,
                 now=time.time, max_age=3600):
        self.fetch, self.verify = fetch, verify
        self.owner, self.channel = owner, channel
        self.activation, self.now, self.max_age = activation, now, max_age

    def read(self, ident, *, new=False):
        rows = self.fetch(ident)
        if len(rows) != 1:
            raise ValueError("Source unavailable")
        event = rows[0]
        if not self.verify(event) or event.get("id") != ident:
            raise ValueError("Source signature rejected")
        if (event["pubkey"] != self.owner or event["kind"] != 9
                or [tag[1] for tag in event["tags"] if len(tag) >= 2 and tag[0] == "h"] != [self.channel]):
            raise PermissionError("Source scope denied")
        if (event["created_at"] < self.activation or event["created_at"] > self.now() + 60
                or (new and event["created_at"] < self.now() - self.max_age)):
            raise PermissionError("Source outside activation window")
        return VerifiedSource(ident, event["pubkey"], self.channel,
                              event["content"], event["created_at"], thread_root(event))

def thread_root(event):
    """Resolve a signed event's explicit NIP-10 root; reject ambiguous metadata."""
    import re
    marked={label:[] for label in ('root','reply')}
    for tag in event.get('tags',[]):
        if len(tag)>=4 and tag[0]=='e' and tag[3] in marked:
            if not re.fullmatch('[0-9a-f]{64}',tag[1]):raise ValueError('Invalid thread reference')
            marked[tag[3]].append(tag[1])
    if any(len(v)>1 for v in marked.values()):
        raise ValueError('Ambiguous thread references')
    # Buzz ThreadMarkers.resolve: a direct reply has only a reply marker;
    # a lone root marker is top-level. Reject malformed/duplicate markers
    # above rather than silently choosing one as the upstream parser can.
    if marked['reply']:
        return marked['root'][0] if marked['root'] else marked['reply'][0]
    return event['id']
