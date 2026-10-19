"""SQLite access. Uses the same app.db file as the PHP code (PHP still creates and upgrades the tables)."""
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path


class Database:
    """One connection per thread; rows come back as dicts."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._local = threading.local()

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=5, isolation_level=None)  # autocommit, like PDO
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA busy_timeout=5000")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = c
        return c

    def query(self, sql: str, params=()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def one(self, sql: str, params=()):
        r = self.query(sql, params).fetchone()
        return dict(r) if r else None

    def all(self, sql: str, params=()) -> list:
        return [dict(r) for r in self.query(sql, params).fetchall()]

    def value(self, sql: str, params=(), default=None):
        r = self.query(sql, params).fetchone()
        return r[0] if r else default

    def pairs(self, sql: str, params=()) -> dict:
        """Two-column query as {first: second} (PHP's FETCH_KEY_PAIR)."""
        return {r[0]: r[1] for r in self.query(sql, params).fetchall()}

    def execute(self, sql: str, params=()) -> int:
        return self.query(sql, params).rowcount

    @contextmanager
    def transaction(self):
        """BEGIN ... COMMIT, or ROLLBACK when the block raises (PDO beginTransaction / commit)."""
        self.conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")
