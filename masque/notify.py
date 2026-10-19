"""Notifications (the bell) and Web Push (PHP: note, pnote, push_*, npref, nquiet, nmuted, ngroup, rnotify).

Push text is always generic ("Someone commented on your post"): never a name, so Masques and anonymous questions stay anonymous."""
import base64
import hashlib
import hmac
import json
import os
import re
import struct
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_GROUPS = {
    "like": "sigils", "clike": "sigils", "comment": "replies", "reply": "replies", "mention": "mentions", "gment": "mentions",
    "gall": "mentions", "tag": "tags", "freq": "friends", "facc": "friends", "follow": "follows", "ask": "asks",
    "answer": "asks", "reveal": "reveals",
}
_PUSH_TEXT = {
    "like": "Someone marked your post with a sigil", "clike": "Someone marked your comment with a sigil",
    "comment": "Someone commented on your post", "reply": "Someone replied to your comment", "mention": "Someone mentioned you",
    "gment": "Someone mentioned you in a group", "gall": "Someone mentioned everyone in a group", "tag": "New post with a tag you follow",
    "freq": "You have a new friend request", "facc": "Your friend request was accepted", "follow": "Someone started following you",
    "ask": "You have a new anonymous question", "answer": "Your question was answered", "reveal": "Someone told you their Masque is them",
}
_PUSH_MANY = {  # when several are waiting: "5 people marked your post with a sigil"
    "like": " people marked your post with a sigil", "clike": " people marked your comment with a sigil",
    "comment": " people commented on your post", "reply": " people replied to your comment", "follow": " people started following you",
}
_PUSH_COOL = {"like": 900, "clike": 900, "follow": 900, "tag": 900, "comment": 180, "reply": 180, "mention": 180, "gment": 60, "gall": 60}
_PUSH_ORDERS = ("googleapis.com", "push.services.mozilla.com", "notify.windows.com", "push.apple.com")


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def b64ud(s) -> bytes:
    s = str(s or "").replace("-", "+").replace("_", "/")
    try:
        return base64.b64decode(s + "=" * (-len(s) % 4))
    except Exception:
        return b""


def _hmac(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


class PushService:
    """Web Push (RFC 8030 / 8291 / 8292): the server's own signing key, payload encryption and delivery."""

    def __init__(self, db, site_url: str = "", request_host: str = ""):
        self.db, self.site_url, self.request_host = db, site_url, request_host

    # -- the server's signing key (VAPID), made once and kept in the site table --
    def keys(self):
        row = self.db.value("SELECT v FROM site WHERE k='vapid'")
        try:
            j = json.loads(row) if row else None
        except ValueError:
            j = None
        if not isinstance(j, dict) or not j.get("pem") or not j.get("pub"):
            key = ec.generate_private_key(ec.SECP256R1())
            pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
            pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
            j = {"pem": pem, "pub": b64u(pub)}
            self.db.execute("INSERT OR REPLACE INTO site(k,v) VALUES('vapid',?)", (json.dumps(j),))
        return j

    def host_ok(self, endpoint: str) -> bool:
        """Only the browsers' own push services, so nobody can make the server call an address of their choosing."""
        u = urlparse(endpoint)
        if not u.hostname or len(endpoint) > 600:
            return False
        h = u.hostname.lower()
        if u.scheme == "http" and h in ("127.0.0.1", "localhost") and self.request_host.split(":")[0].lower() in ("127.0.0.1", "localhost"):
            return True  # local testing only
        try:
            port = u.port
        except ValueError:
            return False
        if u.scheme != "https" or (port is not None and port != 443):
            return False
        return any(h == d or h.endswith("." + d) for d in _PUSH_ORDERS)

    @staticmethod
    def encrypt(sub, payload: bytes):
        ua_pub, auth = b64ud(sub["k"]), b64ud(sub["a"])
        if len(ua_pub) != 65 or len(auth) < 16:
            return None
        try:
            eph = ec.generate_private_key(ec.SECP256R1())
            as_pub = eph.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
            peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub)
            secret = eph.exchange(ec.ECDH(), peer)
        except ValueError:
            return None
        salt = os.urandom(16)
        ikm = _hmac(_hmac(auth, secret), b"WebPush: info\0" + ua_pub + as_pub + b"\x01")
        prk = _hmac(salt, ikm)
        cek = _hmac(prk, b"Content-Encoding: aes128gcm\0\x01")[:16]
        nonce = _hmac(prk, b"Content-Encoding: nonce\0\x01")[:12]
        sealed = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)  # ciphertext + 16-byte tag
        return salt + struct.pack(">I", 4096) + bytes([65]) + as_pub + sealed

    def jwt(self, endpoint: str):
        k = self.keys()
        u = urlparse(endpoint)
        aud = "%s://%s%s" % (u.scheme, u.hostname, ":%d" % u.port if u.port else "")
        hd = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
        cl = b64u(json.dumps({"aud": aud, "exp": int(time.time()) + 43200,
                              "sub": self.site_url if self.site_url.startswith("https://") else "mailto:admin@masque.invalid"},
                             separators=(",", ":")).encode())
        priv = serialization.load_pem_private_key(k["pem"].encode(), None)
        r, s = decode_dss_signature(priv.sign(("%s.%s" % (hd, cl)).encode(), ec.ECDSA(hashes.SHA256())))
        return {"t": "%s.%s.%s" % (hd, cl, b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))), "k": k["pub"]}

    def flush(self, jobs):
        """Send every queued push (jobs = [(uid, json text)]) to every browser that person turned push on in."""
        sends = []
        for uid, payload in jobs:
            for sub in self.db.all("SELECT id,ep,k,a FROM pushsubs WHERE uid=?", (uid,)):
                body = self.encrypt(sub, payload.encode())
                if body is None:
                    continue
                try:
                    jw = self.jwt(sub["ep"])
                except Exception:
                    continue
                sends.append((int(sub["id"]), sub["ep"], body, jw))
        if not sends:
            return

        def one(job):
            sid, ep, body, jw = job
            req = urllib.request.Request(ep, data=body, method="POST", headers={
                "Authorization": "vapid t=%s, k=%s" % (jw["t"], jw["k"]), "Content-Encoding": "aes128gcm",
                "Content-Type": "application/octet-stream", "TTL": "86400", "Urgency": "normal"})
            try:
                with urllib.request.urlopen(req, timeout=6) as r:
                    return sid, r.status
            except urllib.error.HTTPError as e:
                return sid, e.code
            except Exception:
                return sid, 0

        with ThreadPoolExecutor(max_workers=min(8, len(sends))) as pool:
            for sid, code in pool.map(one, sends):
                if code in (404, 410):  # the browser says this subscription is gone
                    self.db.execute("DELETE FROM pushsubs WHERE id=?", (sid,))


class NotifyPrefs:
    """Which kinds reach the bell (muted groups), message pop-ups, and quiet hours (times are the user's own clock, minutes after midnight plus their UTC offset)."""
    DEFAULT = {"muted": "", "pop": 1, "qon": 0, "qfrom": 1320, "qto": 420, "tz": 0}

    def __init__(self, db):
        self.db = db
        self._cache = {}

    def get(self, uid) -> dict:
        uid = int(uid)
        if uid not in self._cache:
            self._cache[uid] = self.db.one("SELECT muted,pop,qon,qfrom,qto,tz FROM nprefs WHERE uid=?", (uid,)) or dict(self.DEFAULT)
        return self._cache[uid]

    def forget(self, uid=None):
        if uid is None:
            self._cache.clear()
        else:
            self._cache.pop(int(uid), None)

    def muted(self, uid, group: str) -> bool:
        return group != "" and group in str(self.get(uid)["muted"] or "").split(",")

    def quiet(self, uid) -> bool:
        p = self.get(uid)
        if not int(p["qon"]):
            return False
        a, b = int(p["qfrom"]), int(p["qto"])
        if a == b:
            return False
        t = ((int(time.time()) + 60 * int(p["tz"])) % 86400 + 86400) % 86400
        mi = t // 60
        return (a <= mi < b) if a < b else (mi >= a or mi < b)


class Notifier:
    """Writes bell notifications and queues the matching push alerts (sent after the answer)."""
    GROUPS = _GROUPS

    def __init__(self, ctx):
        self.ctx = ctx
        self.db = ctx.db
        self.prefs = NotifyPrefs(ctx.db)
        self._queue = []

    @staticmethod
    def group(kind: str) -> str:
        return _GROUPS.get(kind, "")

    def muted(self, uid, group: str) -> bool:
        return self.prefs.muted(uid, group)

    def quiet(self, uid) -> bool:
        return self.prefs.quiet(uid)

    # -- push --
    def push(self, uid, title: str, body: str, url: str = "./", tag: str = "", cool: int = 0):
        """Queue a push for one user; everything queued during a request is sent together after the answer."""
        uid = int(uid)
        if not uid or not self.db.value("SELECT 1 FROM pushsubs WHERE uid=? LIMIT 1", (uid,)):
            return
        if self.quiet(uid):  # quiet hours: no pop-ups. Everything is still waiting in the app afterwards.
            return
        if cool > 0 and tag != "":  # one alert per kind of thing per few minutes; the rest just wait in the bell
            lm = self.ctx.limiter
            if lm.count("pn:%d:%s" % (uid, tag), cool) >= 1:
                return
            lm.add("pn:%d:%s" % (uid, tag))
        if not self._queue:
            self.ctx.defer(self.flush)
        self._queue.append((uid, json.dumps({"t": title, "b": body, "u": url, "g": tag}, separators=(",", ":"), ensure_ascii=False)))

    def push_now(self, uid, title: str, body: str, url: str = "./", tag: str = ""):
        """Queue a push with no quiet-hours or cool-down check (the test button)."""
        if not self._queue:
            self.ctx.defer(self.flush)
        self._queue.append((int(uid), json.dumps({"t": title, "b": body, "u": url, "g": tag}, separators=(",", ":"), ensure_ascii=False)))

    def flush(self):
        jobs, self._queue = self._queue, []
        if jobs:
            from flask import request
            PushService(self.db, self.ctx.cfg.site_url, request.host if request else "").flush(jobs)

    # -- the bell --
    def note(self, u, kind: str, actor, pid: int = 0, mid: int = 0):
        """One notification for user `u` about `actor`'s doing (kind), unless blocked, muted or already waiting."""
        db = self.db
        if not u or int(u) == int(actor):
            return
        if int(mid) > 0:
            if self.ctx.rel.masque_blocked(u, int(mid)):  # a Masque is only blocked by a block on that Masque
                return
        elif self.ctx.rel.blocked(u, actor):
            return
        if self.muted(u, self.group(kind)):
            return
        if db.value("SELECT 1 FROM notifs WHERE uid=? AND kind=? AND actor=? AND pid=? AND mid=? AND seen=0", (u, kind, actor, pid, mid)):
            return
        db.execute("INSERT INTO notifs(uid,kind,actor,pid,ts,mid) VALUES(?,?,?,?,?,?)", (u, kind, actor, pid, int(time.time()), mid))
        if kind not in _PUSH_TEXT:
            return
        txt = _PUSH_TEXT[kind]
        gp = 0 if kind in ("follow", "tag", "freq", "facc", "ask", "answer", "reveal") else int(pid)
        if kind in _PUSH_MANY:
            cn = int(db.value("SELECT COUNT(DISTINCT actor) FROM notifs WHERE uid=? AND kind=? AND pid=? AND seen=0",
                              (u, kind, gp if gp > 0 else int(pid)), 0))
            if cn > 1:
                txt = "%d%s" % (cn, _PUSH_MANY[kind])
        if kind in ("gment", "gall"):
            url = "./#/g/%d" % int(pid)
        elif pid > 0 and kind not in ("freq", "facc", "follow", "ask", "answer", "reveal"):
            url = "./#/p/%d" % int(pid)
        else:
            url = "./"
        self.push(u, "Masque", txt, url, "n-%s-%d" % (kind, gp), _PUSH_COOL.get(kind, 0))

    def reviewed(self, kind: str, target):
        """Tell people who reported something that an admin has looked at it. Never says what was decided, and never names the person or content."""
        for r in self.db.all("SELECT DISTINCT uid FROM reports WHERE uid>0 AND kind=? AND tid=?", (kind, target)):
            self.db.execute("INSERT INTO notifs(uid,kind,actor,pid,ts) VALUES(?,?,?,?,?)", (int(r["uid"]), "rview", int(r["uid"]), 0, int(time.time())))


class PushQueue:
    """Push alerts sent outside a request (the streak reminders): queue them, then flush once. Same rules as Notifier.push: nothing for people
    without a subscribed browser, nothing during quiet hours."""

    def __init__(self, db, cfg, prefs: NotifyPrefs):
        self.db, self.cfg, self.prefs = db, cfg, prefs
        self._queue = []

    def send(self, uid, title: str, body: str, url: str = "./", tag: str = ""):
        uid = int(uid)
        if not uid or not self.db.value("SELECT 1 FROM pushsubs WHERE uid=? LIMIT 1", (uid,)) or self.prefs.quiet(uid):
            return
        self._queue.append((uid, json.dumps({"t": title, "b": body, "u": url, "g": tag}, separators=(",", ":"), ensure_ascii=False)))

    def flush(self):
        jobs, self._queue = self._queue, []
        if jobs:
            PushService(self.db, self.cfg.site_url).flush(jobs)
