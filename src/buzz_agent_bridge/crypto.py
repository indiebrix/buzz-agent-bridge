"""Authenticated storage and Nostr signatures; credentials are injected, never provisioned."""
import hashlib
import json
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from coincurve import PrivateKey, PublicKeyXOnly

class AEADCodec:
    """AES-256-GCM envelope. Key is injected; never generated, read or persisted here."""
    AAD = b'buzz-agent-bridge/state/v1'
    def __init__(self, key_bytes):
        if not isinstance(key_bytes, bytes) or len(key_bytes) != 32:
            raise ValueError('32-byte storage key required')
        self.cipher = AESGCM(key_bytes)

    def seal(self, plaintext):
        nonce = os.urandom(12)
        return b'BD1' + nonce + self.cipher.encrypt(nonce, plaintext, self.AAD)

    def open(self, envelope):
        if not isinstance(envelope, bytes) or len(envelope) < 31 or envelope[:3] != b'BD1':
            raise ValueError('Invalid storage envelope')
        return self.cipher.decrypt(envelope[3:15], envelope[15:], self.AAD)


def nostr_digest(event):
    if (type(event.get('created_at')) is not int or type(event.get('kind')) is not int
            or event['created_at'] < 0 or not 0 <= event['kind'] <= 65535
            or not isinstance(event.get('content'), str) or not isinstance(event.get('tags'), list)
            or any(not isinstance(t,list) or any(not isinstance(v,str) for v in t) for t in event['tags'])):
        raise ValueError('Invalid Nostr event')
    pub = event['pubkey']
    if len(pub) != 64 or pub != pub.lower():
        raise ValueError('Invalid public key')
    bytes.fromhex(pub)
    canonical = [0,pub,event['created_at'],event['kind'],event['tags'],event['content']]
    raw = json.dumps(canonical,separators=(',', ':'),ensure_ascii=False).encode()
    return hashlib.sha256(raw).digest()


def verify_nostr(event):
    try:
        if set(event) != {'id','pubkey','created_at','kind','tags','content','sig'}:
            return False
        digest = nostr_digest(event)
        if event['id'] != digest.hex() or len(event['sig']) != 128:
            return False
        return PublicKeyXOnly(bytes.fromhex(event['pubkey'])).verify(bytes.fromhex(event['sig']),digest)
    except (ValueError,KeyError,TypeError,AttributeError):
        return False


class NostrSigner:
    """Approved identity bytes in memory; caller owns provisioning and lifetime."""
    def __init__(self, private_bytes):
        if not isinstance(private_bytes, bytes) or len(private_bytes) != 32:
            raise ValueError('32-byte Nostr key required')
        self.key = PrivateKey(private_bytes)
        self.pubkey = self.key.public_key_xonly.format().hex()

    def __call__(self, unsigned):
        if set(unsigned) != {'kind','created_at','content','tags'}:
            raise ValueError('Invalid unsigned event')
        event = {**unsigned,'pubkey':self.pubkey}
        digest = nostr_digest(event)
        event['id'] = digest.hex()
        event['sig'] = self.key.sign_schnorr(digest).hex()
        return event

