"""Encrypted subscriptions and bounded authenticated loopback MCP transport."""
from collections.abc import MutableMapping
import hashlib
import fcntl
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import os
from pathlib import Path
import socket
import socketserver
import sqlite3
import ssl
import stat
import threading
from urllib.parse import urlsplit
from .events import encoded, VERSION
MAX_BODY = 262144

class ProtectedStore(MutableMapping):
    """Single-process SQLite mapping, 0700 directory/0600 DB, encrypted rows.

    seal/open_blob must provide authenticated encryption from an approved external
    secret provider. They are deliberately mandatory; this module generates no key.
    Store must live outside Git. Use persist after mutations of fetched objects.
    Concurrent processes are unsupported; host must take an exclusive process lock.
    """
    def __init__(self, directory, seal, open_blob):
        directory = Path(directory)
        if directory.is_symlink():
            raise PermissionError('Unsafe state directory')
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        st = directory.stat()
        if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
            raise PermissionError('State directory must be owner-only')
        target = directory / 'subscriptions.sqlite3'
        fd = os.open(target, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1:
                raise PermissionError('Unsafe state file')
        finally:
            os.close(fd)
        self.process_lock = os.open(directory/'bridge.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.process_lock)
            raise
        self.db = sqlite3.connect(target, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (id TEXT PRIMARY KEY, payload BLOB NOT NULL)')
        self.db.commit()
        self.seal, self.open_blob = seal, open_blob
        self.lock = threading.RLock()

    def __getitem__(self, item):
        with self.lock:
            row = self.db.execute('SELECT payload FROM state WHERE id=?', (item,)).fetchone()
            if row is None:
                raise KeyError(item)
            envelope = json.loads(self.open_blob(row[0]))
            if envelope.get('id') != item:
                raise ValueError('Storage row binding rejected')
            value = envelope['value']
            if 'seen' in value:
                value['seen'] = set(value['seen'])
            return value

    def __setitem__(self, item, value):
        value = dict(value)
        if 'seen' in value:
            value['seen'] = sorted(value['seen'])
        blob = self.seal(encoded({'id': item, 'value': value}))
        if not isinstance(blob, bytes):
            raise ValueError('Encrypted bytes required')
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO state VALUES (?,?)', (item, blob))

    def __delitem__(self, item):
        with self.lock, self.db:
            cursor = self.db.execute('DELETE FROM state WHERE id=?', (item,))
            if cursor.rowcount == 0:
                raise KeyError(item)

    def __iter__(self):
        with self.lock:
            return iter([row[0] for row in self.db.execute('SELECT id FROM state')])

    def __len__(self):
        with self.lock:
            return self.db.execute('SELECT COUNT(*) FROM state').fetchone()[0]

    def close(self):
        self.db.close()
        os.close(self.process_lock)


class BearerAuth:
    """Configured SHA256 digest -> stable principal; no token issuance.

    Digests are for high-entropy provisioned tokens, never human passwords. MCP
    bearer auth is independent of Buzz's Nostr identity. OAuth needs its own adapter.
    """
    def __init__(self, digests):
        self.digests = dict(digests)
        if not self.digests or any(len(d) != 64 or not p for d,p in self.digests.items()):
            raise ValueError('Explicit credential bindings required')

    def __call__(self, header):
        if not isinstance(header, str) or not header.startswith('Bearer '):
            raise PermissionError('Authentication required')
        token = header[7:]
        if not token or len(token) > 4096 or any(c.isspace() for c in token):
            raise PermissionError('Authentication required')
        digest = hashlib.sha256(token.encode()).hexdigest()
        for expected, principal in self.digests.items():
            if hmac.compare_digest(expected, digest):
                return principal
        raise PermissionError('Authentication required')


class PublicHTTPS:
    """Pinned public IP, original TLS name, no redirects or proxies, bounded I/O."""
    def __init__(self, resolver=socket.getaddrinfo, connect=socket.create_connection, context=None):
        self.resolver, self.connect = resolver, connect
        self.context = context or ssl.create_default_context()

    def __call__(self, url, body, headers):
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.fragment or parsed.port not in (None, 443) or len(body) > MAX_BODY):
            raise ValueError('Callback rejected')
        addresses = self.resolver(parsed.hostname, 443, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(item[4][0] for item in addresses))
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError('Non-public callback rejected')
        # Use precisely a validated address; never resolve hostname again for connect.
        sock = self.connect((ips[0], 443), timeout=10)
        try:
            tls = self.context.wrap_socket(sock, server_hostname=parsed.hostname)
        except BaseException:
            sock.close()
            raise
        conn = http.client.HTTPConnection(parsed.hostname, 443, timeout=10)
        conn.sock = tls
        try:
            path = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
            conn.request('POST', path, body=body, headers=headers)
            response = conn.getresponse()
            raw = response.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                raise ValueError('Callback response too large')
            if 300 <= response.status < 400:
                raise ValueError('Callback redirect rejected')
            try:
                result = json.loads(raw) if raw else {}
            except (ValueError, UnicodeDecodeError):
                result = {}
            return response.status, result
        finally:
            conn.close()


class RPC:
    def __init__(self, events, tools=None):
        self.events, self.tools = events, tools
        self.lock = threading.RLock()

    def __call__(self, principal, request):
        if not principal:
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32001, 'message': 'Access denied'}}
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'), str):
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid request'}}
        ident = request.get('id')
        method = request['method']
        if 'id' not in request:
            return None
        if not isinstance(request.get('params', {}), dict):
            return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32602, 'message': 'Invalid params'}}
        try:
            with self.lock:
                if method == 'ping':
                    result = {}
                elif method.startswith('tools/') and self.tools:
                    result = self.tools(principal, method, request.get('params', {}))
                else:
                    result = self.events.handle(principal, method, request.get('params'))
                    if method == 'server/discover' and self.tools:
                        result['capabilities']['tools'] = {}
            return {'jsonrpc': '2.0', 'id': ident, 'result': result}
        except PermissionError:
            error = {'code': -32001, 'message': 'Access denied'}
        except (TimeoutError, OSError):
            error = {'code': -32015, 'message': 'Callback unavailable', 'data': {'reason': 'timeout'}}
        except ValueError as exc:
            # Do not return exception text; it could include remote-controlled data.
            callback = str(exc) == 'Callback verification failed'
            error = {'code': -32015 if callback else -32602, 'message': 'Request rejected'}
            if callback:
                error['data'] = {'reason': 'challenge_failed'}
        except Exception:
            error = {'code': -32603, 'message': 'Request unavailable'}
        return {'jsonrpc': '2.0', 'id': ident, 'error': error}


def http_server(address, rpc, authenticate, allowed_hosts, allowed_origins=()):
    """Build HTTP server; caller explicitly chooses when to serve. Loopback by default.

    A TLS/reverse proxy or approved tunnel must front this listener. No proxy header
    can override authentication. Logs are disabled; host may collect counts only.
    JSON responses support stateless POST transport; SSE GET is intentionally 405.
    """
    if address[0] != '127.0.0.1':
        raise ValueError('Only loopback listener allowed')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, value=None):
            body = encoded(value) if value is not None else b''
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            if status == 401:
                self.send_header('WWW-Authenticate', 'Bearer')
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.connection.settimeout(10)
            if self.path != '/mcp':
                return self.reply(404)
            if len(self.headers.get_all('Host', [])) != 1 or self.headers.get('Host') not in allowed_hosts:
                return self.reply(403)
            if self.headers.get('Origin') and self.headers['Origin'] not in allowed_origins:
                return self.reply(403)
            try:
                if len(self.headers.get_all('Authorization', [])) != 1:
                    raise PermissionError()
                principal = authenticate(self.headers.get('Authorization'))
            except PermissionError:
                return self.reply(401)
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
                return self.reply(400)
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return self.reply(400)
            if not 0 < length <= MAX_BODY:
                return self.reply(413)
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415)
            version = self.headers.get('MCP-Protocol-Version')
            if version and version != VERSION:
                return self.reply(400)
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    return self.reply(400)
                request = json.loads(raw)
            except (ValueError, OSError):
                return self.reply(400)
            result = rpc(principal, request)
            return self.reply(202 if result is None else 200, result)

        def do_GET(self):
            if len(self.headers.get_all('Host', [])) != 1 or self.headers.get('Host') not in allowed_hosts:
                return self.reply(403)
            if self.path in ('/.well-known/oauth-protected-resource', '/.well-known/oauth-protected-resource/mcp'):
                return self.reply(200, {'resource': 'http://' + self.headers['Host'] + '/mcp',
                                        'authorization_servers': []})
            self.reply(405 if self.path == '/mcp' else 404)

        def do_DELETE(self):
            self.reply(405)
    class LoopbackHTTPServer(HTTPServer):
        def server_bind(self):
            # HTTPServer normally performs reverse DNS here; local binding needs none.
            socketserver.TCPServer.server_bind(self)
            self.server_name, self.server_port = self.server_address[:2]
    return LoopbackHTTPServer(address, Handler)

