"""Same-user managed identity handoff; private key lives in memory only."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import stat
import threading
from coincurve import PublicKeyXOnly
from . import VERSION
from .crypto import NostrSigner
from .ipc import LocalServer, peer_uid

def decode_key(raw):
    if re.fullmatch('[0-9a-f]{64}', raw):
        return bytes.fromhex(raw)
    alphabet = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
    if not raw.startswith('nsec1') or len(raw) != 63:
        raise ValueError('Invalid managed identity encoding')
    values = [alphabet.index(c) for c in raw[5:]]
    hrp = 'nsec'
    check = 1
    for value in [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp] + values:
        top = check >> 25
        check = ((check & 0x1ffffff) << 5) ^ value
        for index, generator in enumerate((0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3)):
            if (top >> index) & 1:
                check ^= generator
    if check != 1:
        raise ValueError('Invalid managed identity checksum')
    output, accumulator, bits = bytearray(), 0, 0
    for value in values[:-6]:
        accumulator = (accumulator << 5) | value
        bits += 5
        while bits >= 8:
            bits -= 8
            output.append((accumulator >> bits) & 255)
    if bits >= 5 or (accumulator << (8 - bits)) & 255 or len(output) != 32:
        raise ValueError('Invalid managed identity padding')
    return bytes(output)


def validate_auth_tag(raw, pubkey, owner):
    # Official NIP-OA unconditional owner attestation for this exact managed key.
    # It is existing signed public metadata, never a new grant or owner secret.
    if not isinstance(raw, str) or len(raw) > 1024:
        raise ValueError('Invalid owner attestation')
    value = json.loads(raw)
    if (not isinstance(value, list) or len(value) != 4 or value[:3] != ['auth', owner, '']
            or owner == pubkey or not isinstance(value[3], str)
            or not re.fullmatch('[0-9a-f]{128}', value[3])):
        raise PermissionError('Owner attestation scope mismatch')
    digest = hashlib.sha256(f'nostr:agent-auth:{pubkey}:'.encode()).digest()
    if not PublicKeyXOnly(bytes.fromhex(owner)).verify(bytes.fromhex(value[3]), digest):
        raise PermissionError('Owner attestation signature rejected')
    return json.dumps(value, separators=(',', ':'))


class HandoffHandler(socketserver.StreamRequestHandler):
    def handle(self):
        response = {'accepted': False}
        try:
            self.connection.settimeout(3)
            if peer_uid(self.connection) != os.getuid():
                raise PermissionError('Peer denied')
            raw = self.rfile.readline(4097)
            if len(raw) > 4096 or not raw.endswith(b'\n'):
                raise ValueError('Invalid frame')
            value = json.loads(raw)
            if set(value) != {'version', 'private_key', 'auth_tag'} or value['version'] != VERSION:
                raise ValueError('Invalid fields')
            signer = NostrSigner(decode_key(value['private_key']))
            auth_tag = validate_auth_tag(value['auth_tag'], signer.pubkey, self.server.owner)
            value.clear()
            if signer.pubkey != self.server.expected:
                raise PermissionError('Managed identity mismatch')
            with self.server.key_lock:
                if self.server.signer is None:
                    self.server.signer = signer
                    self.server.auth_tag = auth_tag
                    self.server.available.set()
            response = {'accepted': True, 'pubkey': signer.pubkey, 'version': VERSION}
        except Exception:
            pass  # Never return/log key bytes, provider exceptions, or raw frames.
        try:
            self.wfile.write(json.dumps(response).encode() + b'\n')
        except OSError:
            pass


class HandoffServer(LocalServer):
    def __init__(self, path, expected, owner):
        self.owner = owner
        self.auth_tag = None
        self.expected, self.signer = expected, None
        self.key_lock, self.available = threading.Lock(), threading.Event()
        super().__init__(path, None)
        self.RequestHandlerClass = HandoffHandler


def handoff(path, raw, auth_tag):
    path = Path(path)
    info, parent = path.lstat(), path.parent.stat()
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or path.parent.is_symlink()
            or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700):
        raise PermissionError('Unsafe identity endpoint')
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(3)
        connection.connect(str(path))
        if peer_uid(connection) != os.getuid():
            raise PermissionError('Server denied')
        payload = {'version': VERSION, 'auth_tag': auth_tag}
        payload['private_key'] = raw  # Runtime input, never a literal or persisted value.
        connection.sendall(json.dumps(payload).encode() + b'\n')
        payload.clear()
        with connection.makefile('rb') as stream:
            result = json.loads(stream.readline(1025))
    return result

