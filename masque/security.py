"""Passwords, recovery codes, rate limits and the visitor's IP address (PHP: password_hash, newrc, rlcount/throttle, cip)."""
import ipaddress
import re
import secrets
import time

from .actions.base import Abort, Reply

try:
    import bcrypt
except ImportError:  # the system crypt() also does bcrypt; fine for tests, bcrypt is the real dependency
    bcrypt = None
    import crypt as _crypt

PHP_WHITESPACE = " \t\n\r\0\x0b"


def php_trim(s) -> str:
    """PHP trim(): strips only space, tab, newline, return, NUL and vertical tab."""
    return str(s).strip(PHP_WHITESPACE)


def php_substr(s: str, n: int) -> str:
    """PHP substr($s, 0, $n) counts bytes."""
    return s.encode("utf-8")[:n].decode("utf-8", "ignore")


def byte_len(s: str) -> int:
    return len(s.encode("utf-8"))


class PasswordHasher:
    """bcrypt, written as $2y$ cost 10, so PHP's password_verify() and Python read each other's hashes."""
    COST = 10

    @staticmethod
    def _bytes(pw: str) -> bytes:
        return pw.encode("utf-8").split(b"\0")[0][:72]  # what bcrypt really uses (and what PHP does with long input)

    def hash(self, pw: str) -> str:
        if bcrypt is not None:
            h = bcrypt.hashpw(self._bytes(pw), bcrypt.gensalt(self.COST)).decode()
        else:
            h = _crypt.crypt(self._bytes(pw).decode("utf-8", "ignore"), _crypt.mksalt(_crypt.METHOD_BLOWFISH, rounds=2 ** self.COST))
        return "$2y$" + h[4:]

    def verify(self, pw: str, stored: str) -> bool:
        try:
            stored = str(stored or "")
            if not stored.startswith("$2"):
                return False
            if bcrypt is not None:
                return bcrypt.checkpw(self._bytes(pw), ("$2b$" + stored[4:]).encode())
            got = _crypt.crypt(self._bytes(pw).decode("utf-8", "ignore"), stored)
            return bool(got) and secrets.compare_digest(got.encode(), stored.encode())
        except Exception:
            return False

    def dummy(self):
        """Same work whether or not the username exists (timing)."""
        self.hash("timing-dummy")


class RecoveryCodes:
    ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    def __init__(self, hasher: PasswordHasher):
        self.hasher = hasher

    def new(self):
        """(code to show the person, hash to store), e.g. ('ABCD-EFGH-JKLM-NPQR', '$2y$...')."""
        c = "".join(secrets.choice(self.ALPHABET) for _ in range(16))
        return "-".join(c[i:i + 4] for i in range(0, 16, 4)), self.hasher.hash(c)

    @staticmethod
    def norm(code: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", str(code)).upper()


class RateLimiter:
    """The `rl` table: one row per hit. Admins have no limits (throttle only)."""

    def __init__(self, db, users):
        self.db, self.users = db, users

    def count(self, key: str, sec: int) -> int:
        return int(self.db.value("SELECT COUNT(*) FROM rl WHERE k=? AND ts>?", (key, int(time.time()) - sec), 0))

    def add(self, key: str):
        if secrets.randbelow(50) == 0:
            self.db.execute("DELETE FROM rl WHERE ts<?", (int(time.time()) - 86400,))
        self.db.execute("INSERT INTO rl(k,ts) VALUES(?,?)", (key, int(time.time())))

    def throttle(self, key: str, maximum: int, sec: int):
        if self.users.admnow():
            return
        if self.count(key, sec) >= maximum:
            raise Abort(Reply.error("Too many requests. Please slow down and try again in a bit.", 429))
        self.add(key)

    def wrong_password_guard(self, uid: int):
        """The 'pwf:<id>' limit: 10 wrong passwords per 15 minutes. Call before checking, then fail() on a miss."""
        if self.count("pwf:%d" % uid, 900) >= 10:
            raise Abort(Reply.error("Too many wrong attempts. Try again in 15 minutes.", 429))

    def wrong_password(self, uid: int):
        self.add("pwf:%d" % uid)


class ClientIp:
    """Visitor address. cip() feeds the sign-up and recovery limits; login_key() is what the sign-in limit uses."""

    def __init__(self, cfg, headers, remote_addr: str):
        self.cfg, self.headers, self.remote = cfg, headers, php_trim(remote_addr or "")

    def _real(self):
        return self.headers.get("X-Real-IP")

    def login_key(self) -> str:
        real = self._real()
        return "ip:" + php_trim(real if real is not None else self.remote)

    def cip(self) -> str:
        h = self.cfg.ip_header
        if h == "" or not re.fullmatch(r"[A-Za-z0-9-]{1,40}", h):
            real = self._real()
            return php_trim(real if real is not None else self.remote)
        parts = [x.strip() for x in self.headers.get(h, "").split(",") if x.strip()]
        if parts:
            x = parts[max(0, len(parts) - max(1, self.cfg.ip_hops))]
            try:
                ipaddress.ip_address(x)
                return x
            except ValueError:
                pass
        return self.remote
