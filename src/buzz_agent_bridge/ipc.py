"""Same-user Unix socket. No TCP listener, bearer secret, or credential creation."""
import ctypes
import json
import os
from pathlib import Path
import socket
import socketserver
import stat
import struct
import sys
import uuid

from . import VERSION
from .broker import AdmissionCancelled
from .ledger import private_directory

MAX_FRAME = 262144


def peer_uid(connection):
    if sys.platform == "darwin":
        uid, gid = ctypes.c_uint(), ctypes.c_uint()
        function = ctypes.CDLL(None, use_errno=True).getpeereid
        function.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
        function.restype = ctypes.c_int
        if function(connection.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
            raise PermissionError("Peer identity unavailable")
        return uid.value
    if hasattr(socket, "SO_PEERCRED"):
        return struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
    raise PermissionError("Unsupported peer authentication")


def _encode(value):
    data = json.dumps(value, separators=(",", ":")).encode() + b"\n"
    if len(data) > MAX_FRAME:
        raise ValueError("IPC frame too large")
    return data


class LocalServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, path, broker):
        self.path = Path(path)
        private_directory(self.path.parent)
        if len(os.fsencode(self.path)) > 100:
            raise ValueError("Unix socket path too long")
        if self.path.exists() or self.path.is_symlink():
            info = self.path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise PermissionError("Unsafe existing socket")
            with socket.socket(socket.AF_UNIX) as probe:
                probe.settimeout(1)
                try:
                    probe.connect(str(self.path))
                except ConnectionRefusedError:
                    self.path.unlink()  # Broker's exclusive ledger lease is already held.
                else:
                    raise RuntimeError("Socket already active")
        self.broker = broker
        super().__init__(str(self.path), Handler)
        os.chmod(self.path, 0o600)
        self.inode = self.path.stat().st_ino

    def server_close(self):
        super().server_close()
        if self.path.exists() and self.path.lstat().st_ino == self.inode:
            self.path.unlink()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(30)
        response = {"version": VERSION, "id": None, "ok": False, "error": "request_rejected"}
        try:
            if peer_uid(self.connection) != os.getuid():
                raise PermissionError("Peer denied")
            raw = self.rfile.readline(MAX_FRAME + 1)
            if not raw.endswith(b"\n") or len(raw) > MAX_FRAME:
                raise ValueError("Invalid frame")
            request = json.loads(raw)
            if (set(request) != {"version", "id", "method", "args"} or request["version"] != VERSION
                    or not isinstance(request["id"], str) or len(request["id"]) > 64
                    or not isinstance(request["args"], dict)):
                raise ValueError("Protocol mismatch")
            response["id"] = request["id"]
            args, broker = request["args"], self.server.broker
            if request["method"] == "admit" and set(args) == {
                    "source_ids", "session_id", "admission_id", "jsonrpc_id"}:
                result = broker.admit(broker.principal, **args)
            elif request["method"] == "cancel_admission" and set(args) == {"admission_id"}:
                result = broker.cancel_admission(**args)
            elif request["method"] == "status" and set(args) == {"ids"}:
                result = broker.status(broker.principal, args["ids"])
            elif request["method"] == "identity" and not args:
                result = {"pubkey": broker.own_pubkey, "channel": broker.channel, "owner": broker.owner}
            else:
                raise ValueError("Unsupported local operation")
            response.update(ok=True, result=result)
            response.pop("error")
        except AdmissionCancelled:
            response["error"] = "admission_cancelled"
        except Exception:
            # Never include source text, credentials, exception messages, or traceback.
            pass
        try:
            self.wfile.write(_encode(response))
        except (OSError, ValueError):
            pass  # Disconnect does not roll back a durable admission.


class LocalClient:
    def __init__(self, path, timeout=30):
        self.path, self.timeout = Path(path), timeout

    def call(self, method, args):
        info = self.path.lstat()
        parent = self.path.parent.stat()
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or parent.st_uid != os.getuid()
                or stat.S_IMODE(parent.st_mode) != 0o700 or self.path.parent.is_symlink()):
            raise PermissionError("Unsafe IPC endpoint")
        ident = uuid.uuid4().hex
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(self.timeout)
            connection.connect(str(self.path))
            if peer_uid(connection) != os.getuid():
                raise PermissionError("Server identity denied")
            connection.sendall(_encode({"version": VERSION, "id": ident, "method": method, "args": args}))
            with connection.makefile("rb") as stream:
                raw = stream.readline(MAX_FRAME + 1)
            if not raw.endswith(b"\n") or len(raw) > MAX_FRAME:
                raise ValueError("Invalid IPC response")
            result = json.loads(raw)
        if result.get("id") != ident or result.get("version") != VERSION:
            raise ValueError("IPC response mismatch")
        if not result.get("ok"):
            if result.get("error") == "admission_cancelled":
                raise AdmissionCancelled()
            raise RuntimeError("Broker request rejected")
        return result["result"]
