"""Reads and writes PHP session files, so a Python-served action sees the same signed-in user as the PHP code.

PHP's default session format is  key|serialize(value)key|serialize(value)...  ; only the value types Masque
stores (int, string, bool, float, null, array) are supported.
"""
try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt
import os
import re
import secrets
from pathlib import Path

COOKIE = "PHPSESSID"
_SID_RE = re.compile(r"^[A-Za-z0-9,-]{22,128}$")


class PhpSerial:
    """The small slice of PHP serialize()/unserialize() that sessions need. Works on bytes (PHP counts string lengths in bytes)."""

    @classmethod
    def loads(cls, raw: bytes):
        val, pos = cls._read(raw, 0)
        return val

    @classmethod
    def _read(cls, b: bytes, i: int):
        t = b[i:i + 1]
        if t == b"N":
            return None, i + 2
        if t in (b"i", b"b", b"d"):
            j = b.index(b";", i)
            body = b[i + 2:j].decode()
            return ({b"i": int, b"d": float, b"b": lambda s: s == "1"}[t])(body), j + 1
        if t == b"s":
            colon = b.index(b":", i + 2)
            n = int(b[i + 2:colon])
            start = colon + 2  # skip :"
            return b[start:start + n].decode("utf-8", "replace"), start + n + 2  # skip ";
        if t == b"a":
            colon = b.index(b":", i + 2)
            n = int(b[i + 2:colon])
            pos = colon + 2  # skip :{
            out = {}
            for _ in range(n):
                k, pos = cls._read(b, pos)
                v, pos = cls._read(b, pos)
                out[k] = v
            return out, pos + 1  # skip }
        raise ValueError("unsupported serialize type %r" % t)

    @classmethod
    def dumps(cls, v) -> bytes:
        if v is None:
            return b"N;"
        if v is True or v is False:
            return b"b:%d;" % int(v)
        if isinstance(v, int):
            return b"i:%d;" % v
        if isinstance(v, float):
            return b"d:%r;" % v
        if isinstance(v, str):
            s = v.encode()
            return b's:%d:"%s";' % (len(s), s)
        if isinstance(v, dict):
            return b"a:%d:{%s}" % (len(v), b"".join(cls.dumps(k) + cls.dumps(x) for k, x in v.items()))
        raise TypeError("cannot serialize %r" % type(v))


class PhpSession:
    """A session identified by the PHPSESSID cookie. Change values with set()/unset() (or edit .data), then save()."""

    def __init__(self, sid: str, directory: Path):
        self.sid = sid if sid and _SID_RE.match(sid) else ""
        self.path = Path(directory) / ("sess_" + self.sid) if self.sid else None
        self.directory = Path(directory)
        self.data = {}
        self._orig = {}
        self._forced = False  # a brand-new session must be written even while it is still empty
        self.fresh = False    # True when the browser has to be given a (new) PHPSESSID cookie
        self._load()

    @staticmethod
    def _parse(raw: bytes) -> dict:
        out, pos = {}, 0
        while pos < len(raw):
            bar = raw.find(b"|", pos)
            if bar < 0:
                break
            key = raw[pos:bar].decode()
            val, pos = PhpSerial._read(raw, bar + 1)
            out[key] = val
        return out

    def _load(self):
        if not self.path or not self.path.is_file():
            self.sid = ""  # unknown or expired session: treated as no session
            return
        self.data = self._parse(self.path.read_bytes())
        self._orig = dict(self.data)

    @property
    def exists(self) -> bool:
        return bool(self.sid)

    # -- session life cycle (PHP: session_start on a new visitor, session_regenerate_id(true), session_destroy) --
    def _use(self, sid: str):
        self.sid = sid
        self.path = self.directory / ("sess_" + sid)

    def start(self):
        """Begin a new session when the visitor has none (or an unknown one)."""
        if self.sid:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        self._use(secrets.token_hex(16))
        self.data, self._orig = {}, {}
        self._forced = self.fresh = True

    def regenerate(self):
        """New id, same data, old file deleted. Done at every sign-in so an old id cannot be reused."""
        self.start()
        if not self._forced:  # an existing session: move its data to a new id
            old = self.path
            self._use(secrets.token_hex(16))
            self._orig = {}  # everything counts as changed, so the whole session is written to the new file
            self._forced = self.fresh = True
            try:
                old.unlink()
            except FileNotFoundError:
                pass

    def destroy(self):
        if self.path:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self.sid, self.path = "", None
        self.data, self._orig = {}, {}
        self._forced = self.fresh = False

    @property
    def dirty(self) -> bool:
        return bool(self.sid) and (self._forced or self.data != self._orig)

    def commit(self):
        """Write the session if this request changed it (does nothing for no session or no change)."""
        if self.dirty:
            self.save()

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def unset(self, *keys):
        for k in keys:
            self.data.pop(k, None)

    def __contains__(self, key):
        return key in self.data

    def save(self):
        """Write only what this request changed, merged into the file as it is *now*, under the flock PHP uses.
        (A PHP request may have changed other keys since we read the file; those changes are kept.)"""
        if not self.path:
            raise RuntimeError("no session to save")
        changed = {k: v for k, v in self.data.items() if k not in self._orig or self._orig[k] != v}
        removed = [k for k in self._orig if k not in self.data]
        if not changed and not removed and not self._forced:
            return
        os.close(os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600))  # make the file if it is missing
        with open(self.path, "r+b") as f:
            self._lock(f)
            try:
                raw = f.read()
                cur = self._parse(raw) if raw else {}
                cur.update(changed)
                for k in removed:
                    cur.pop(k, None)
                body = b"".join(k.encode() + b"|" + PhpSerial.dumps(v) for k, v in cur.items())
                f.seek(0)
                f.truncate()
                f.write(body)
                f.flush()
                self.data = cur
                self._orig = dict(cur)
                self._forced = False
            finally:
                self._unlock(f)

    @staticmethod
    def _lock(f):
        """Exclusive lock for the whole save (flock, like PHP's session handler; msvcrt on Windows)."""
        if fcntl:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        else:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    @staticmethod
    def _unlock(f):
        if not fcntl:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
