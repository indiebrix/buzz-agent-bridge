"""Single-owner encrypted SQLite ledger, atomic outbox, and explicit restore gate."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import stat
import threading

SCHEMA = 2
APPLICATION_ID = 0x414C4954


def private_directory(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise PermissionError("Unsafe directory")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise PermissionError("Owner-only directory required")
    return directory


def private_file(path):
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    info = os.fstat(descriptor)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        os.close(descriptor)
        raise PermissionError("Unsafe state file")
    return descriptor


class Ledger:
    """One process owns the lock; CLI children inherit it until they exit.

    Cipher callbacks are the existing reviewed AEADCodec, supplied by the host.
    No key generation/lookup. Restore must be explicit: arbitrary file rollback
    cannot be detected without an external monotonic authority.
    """
    def __init__(self, directory, seal, open_blob, *, restored=False):
        self.directory = private_directory(directory)
        self.lock_fd = private_file(self.directory / "broker.lock")
        self.db = None
        self.lock = threading.RLock()
        self.seal, self.open_blob = seal, open_blob
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            target = self.directory / "jobs.sqlite3"
            os.close(private_file(target))
            self.db = sqlite3.connect(target, check_same_thread=False, isolation_level=None)
            self.db.execute("PRAGMA journal_mode=DELETE")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA busy_timeout=3000")
            self._migrate()
            self.validate()
            self.recover(restored=restored)
        except BaseException:
            self.close()
            raise

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def _migrate(self):
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        application = self.db.execute("PRAGMA application_id").fetchone()[0]
        tables = self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if version not in (0, 1, SCHEMA) or (tables and application != APPLICATION_ID):
            raise ValueError("Unsupported ledger schema")
        if version == 0 and tables:
            raise ValueError("Unrecognized ledger")
        if version == 1:
            # Authenticate every existing row before migrating; preserve a backup.
            self.validate(include_controls=False)
            backup = self.directory / "before-schema-2.sqlite3"
            if not backup.exists():
                self.backup(backup)
            else:
                os.close(private_file(backup))
        with self.transaction():
            self.db.execute("CREATE TABLE IF NOT EXISTS jobs "
                            "(id TEXT PRIMARY KEY, payload BLOB NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS outbox "
                            "(id TEXT PRIMARY KEY, payload BLOB NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS controls "
                            "(id TEXT PRIMARY KEY, payload BLOB NOT NULL)")
            self.db.execute(f"PRAGMA application_id={APPLICATION_ID}")
            self.db.execute(f"PRAGMA user_version={SCHEMA}")

    def get(self, table, ident):
        if table not in ("jobs", "outbox", "controls"):
            raise ValueError("Unknown table")
        with self.lock:
            row = self.db.execute(f"SELECT payload FROM {table} WHERE id=?", (ident,)).fetchone()
            if row is None:
                return None
            value = json.loads(self.open_blob(row[0]))
            if value.get("table") != table or value.get("id") != ident or value.get("format") != 1:
                raise ValueError("Encrypted row binding rejected")
            return value["value"]

    def put(self, table, ident, value):
        if table not in ("jobs", "outbox", "controls"):
            raise ValueError("Unknown table")
        if not self.db.in_transaction:
            raise RuntimeError("Explicit transaction required")
        envelope = json.dumps({"table": table, "id": ident, "format": 1, "value": value},
                              ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        blob = self.seal(envelope)
        if not isinstance(blob, bytes):
            raise ValueError("Encrypted bytes required")
        self.db.execute(f"INSERT INTO {table} VALUES (?,?) "
                        "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (ident, blob))

    def rows(self, table):
        if table not in ("jobs", "outbox", "controls"):
            raise ValueError("Unknown table")
        with self.lock:
            ids = self.db.execute(f"SELECT id FROM {table} ORDER BY id").fetchall()
            return [self.get(table, row[0]) for row in ids]

    def validate(self, include_controls=True):
        if self.db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Ledger integrity check failed")
        for table in (("jobs", "outbox", "controls") if include_controls else ("jobs", "outbox")):
            self.rows(table)

    def recover(self, *, restored=False):
        """Never requeue uncertain effects. A restored snapshot quarantines jobs."""
        with self.transaction():
            for job in self.rows("jobs"):
                if restored:
                    job["generation"] += 1
                    job["quarantined"] = True
                    job["cancel_requested"] = True
                    job["delivery"] = "quarantined"
                self.put("jobs", job["request_id"], job)
            for entry in self.rows("outbox"):
                if restored:
                    entry["state"] = "quarantined"
                elif entry["state"] == "sending":
                    entry["state"] = "uncertain"
                    job = self.get("jobs", entry["request_id"])
                    job["dispatch" if entry["stage"] == "wake" else "delivery"] = "uncertain"
                    self.put("jobs", job["request_id"], job)
                self.put("outbox", entry["id"], entry)

    def backup(self, destination):
        destination = Path(destination)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Backup destination exists")
        private_directory(destination.parent)
        with self.lock:
            os.close(private_file(destination))
            backup = sqlite3.connect(destination)
            try:
                self.db.backup(backup)
            finally:
                backup.close()

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None
