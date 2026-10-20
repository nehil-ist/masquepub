"""The user and session layer: who is signed in (PHP's me() and need()), the admin check, and device tokens (devtouch)."""
import base64
import hashlib
import secrets
import time

from .actions.base import Abort, Reply
from .config import ascii_lower

# Same column list, same order as PHP's me() query.
_USER_COLS = ("id,name,nick,bio,avatar,cy,cover,dm,priv,askon,askp,ncts,sv,sus,rc,mail,pin,pst,tbg,tbp,"
              "tcd,tfn,tas,taf,tcf,tpl,xp,ts")
# Actions a suspended (or banned) account may still POST.
SUSPENDED_OK = ("logout", "pw", "newrc", "delacct", "appeal")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_BROWSERS = (("Edg", "Edge"), ("OPR", "Opera"), ("SamsungBrowser", "Samsung Internet"), ("Firefox", "Firefox"),
             ("FxiOS", "Firefox"), ("CriOS", "Chrome"), ("Chrome", "Chrome"), ("Safari", "Safari"))
_SYSTEMS = (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"),
            ("Macintosh", "Mac"), ("CrOS", "ChromeOS"), ("Linux", "Linux"))


class Admins:
    """Admin accounts come from the ADMIN_USER / ADMIN_USERS server variables (case-insensitive names)."""

    def __init__(self, names):
        self.names = frozenset(ascii_lower(n) for n in names)

    def is_admin(self, name: str) -> bool:
        return ascii_lower(str(name)) in self.names


class MailVault:
    """Reads the encrypted recovery email (AES-256-GCM, layout iv|tag|ciphertext, base64) written by PHP's mail_enc()."""

    def __init__(self, secret: str):
        self.key = hashlib.sha256(b"masque-mail-v1|" + secret.encode()).digest()

    def decrypt(self, stored: str) -> str:
        try:
            raw = base64.b64decode(str(stored), validate=True)
            if len(raw) < 29:
                return ""
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            iv, tag, ct = raw[:12], raw[12:28], raw[28:]
            return AESGCM(self.key).decrypt(iv, ct + tag, None).decode("utf-8", "replace")
        except Exception:
            return ""

    def encrypt(self, plain: str) -> str:
        """Same layout PHP writes: base64(iv | tag | ciphertext)."""
        import os
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        iv = os.urandom(12)
        sealed = AESGCM(self.key).encrypt(iv, str(plain).encode(), None)  # ciphertext + 16-byte tag
        return base64.b64encode(iv + sealed[-16:] + sealed[:-16]).decode()

    @staticmethod
    def mask(email: str) -> str:
        at = email.find("@")
        return "" if at <= 0 else email[0] + "***" + email[at:]


class Devices:
    """One row per signed-in browser; the row's token lives in the session. Deleting the row signs that browser out."""

    def __init__(self, db, session, user_agent: str):
        self.db, self.session, self.ua = db, session, user_agent

    def label(self) -> str:
        b = next((name for key, name in _BROWSERS if key.lower() in self.ua.lower()), "Browser")
        o = next((name for key, name in _SYSTEMS if key.lower() in self.ua.lower()), "")
        return "%s on %s" % (b, o) if o else b

    def new(self, uid: int):
        uid = int(uid)
        old = self.session.get("d")
        if old:
            self.db.execute("DELETE FROM devices WHERE tok=?", (old,))
        tok = secrets.token_hex(16)
        sv = int(self.db.value("SELECT sv FROM users WHERE id=?", (uid,), 0) or 0)
        now = int(time.time())
        self.db.execute("INSERT INTO devices(tok,uid,label,ts,last,sv) VALUES(?,?,?,?,?,?)",
                        (tok, uid, self.label(), now, now, sv))
        self.session.set("d", tok)
        self.db.execute("DELETE FROM devices WHERE last<?", (now - 3456000,))
        self.db.execute("DELETE FROM devices WHERE uid=? AND n NOT IN "
                        "(SELECT n FROM devices WHERE uid=? ORDER BY last DESC LIMIT 20)", (uid, uid))

    def touch(self, uid: int) -> bool:
        """True while this browser's device row exists (and is refreshed at most every 5 minutes)."""
        tok = str(self.session.get("d") or "")
        if tok == "":
            self.new(uid)
            return True
        r = self.db.one("SELECT n,last FROM devices WHERE tok=? AND uid=?", (tok, int(uid)))
        if not r:
            return False
        now = int(time.time())
        if now - int(r["last"]) > 300:
            self.db.execute("UPDATE devices SET last=? WHERE n=?", (now, r["n"]))
        return True


class Users:
    """Everything PHP's me() / need() did, for one request."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.db = ctx.db
        self.cfg = ctx.cfg
        self.admins = Admins(ctx.cfg.admin_users)
        self.vault = MailVault(ctx.cfg.mail_key)
        self._me = False  # cache; False = not looked up yet
        self.account_gone = False  # the session names a user that no longer exists (PHP's me() then returns false, not null)

    @property
    def session(self):
        return self.ctx.session

    @property
    def devices(self) -> Devices:
        from flask import request
        return Devices(self.db, self.session, request.headers.get("User-Agent", ""))

    def is_admin(self, user) -> bool:
        """PHP adm(): accepts a user dict (or anything with a 'name')."""
        return self.admins.is_admin(user["name"])

    def me(self):
        """The signed-in user as the front end sees it, or None. Same side effects as PHP: a stale session is signed out,
        a browser without a device row gets one, and the device's 'last seen' is refreshed."""
        if self._me is not False:
            return self._me
        self._me = self._load_me()
        return self._me

    def reset(self):
        """Forget the cached answer (after a sign-in or sign-out changed the session)."""
        self._me = False
        self.account_gone = False

    def _load_me(self):
        s = self.session
        uid = s.get("u")
        if uid is None:
            return None
        r = self.db.one("SELECT %s FROM users WHERE id=?" % _USER_COLS, (uid,))
        if r is None:
            self.account_gone = True
            return None
        if int(s.get("sv", 0) or 0) != int(r["sv"]):
            s.unset("u")
            s.save()
            return None
        if not self.devices.touch(r["id"]):
            s.unset("u", "d")
            s.save()
            return None
        s.save()  # a new device token may have been added
        r["nl"] = 0 if self.is_admin(r) else max(0, self.cfg.newacct_secs - (int(time.time()) - int(r["ts"] or 0)))
        r["newish"] = 1 if int(time.time()) - int(r["ts"] or 0) < 604800 else 0
        del r["ts"], r["sv"]
        r["hasrc"] = 1 if r["rc"] != "" else 0
        del r["rc"]
        r["hasmail"] = 1 if r["mail"] != "" else 0
        r["mailm"] = self.vault.mask(self.vault.decrypt(r["mail"])) if r["mail"] != "" else ""
        del r["mail"]
        r["sus"] = int(r["sus"])
        r["xp"] = int(r["xp"])
        r["xpall"] = 1 if self.db.value("SELECT v FROM site WHERE k='xpall'") == "1" else 0
        r["admin"] = self.is_admin(r)
        r["role"] = self.role_of(r)
        r["mod"] = r["role"] in ("mod", "admin")
        r["mask"] = self.db.one("SELECT name,bio,avatar FROM masks WHERE uid=?", (r["id"],))
        return r

    def role_of(self, user) -> str:
        """'admin' (ADMIN_USER / ADMIN_USERS), 'mod' (role 1 in the users table) or 'user'. Takes a dict with a 'name' and/or an 'id'."""
        name = user.get("name")
        if name is None and user.get("id") is not None:
            name = self.db.value("SELECT name FROM users WHERE id=?", (int(user["id"]),))
        if name is not None and self.admins.is_admin(name):
            return "admin"
        role = user.get("role")
        if isinstance(role, str):  # a me() dict already carries the answer
            return role
        if role is None:
            role = self.db.value("SELECT role FROM users WHERE name=?", (str(name or ""),), 0)
        return "mod" if int(role or 0) == 1 else "user"

    def is_mod(self, user) -> bool:
        """A moderator or an admin (staff)."""
        return self.role_of(user) in ("mod", "admin")

    def admnow(self) -> bool:
        """PHP admnow(): is the account in this session an admin (no full me() lookup, no side effects)."""
        uid = self.session.get("u")
        if not uid:
            return False
        name = self.db.value("SELECT name FROM users WHERE id=?", (int(uid),))
        return name is not None and self.admins.is_admin(name)

    def need(self):
        """The signed-in user, or stop the request: 401 when signed out, 403 when suspended and trying to write."""
        m = self.me()
        if not m:
            raise Abort(Reply.error("Sign in first.", 401))
        if m["sus"] > time.time() and self.ctx.method == "POST" and self.ctx.action not in SUSPENDED_OK:
            if m["sus"] >= 2000000000:
                head = "Your account is banned."
            else:
                t = time.gmtime(m["sus"])
                head = "Your account is suspended until %s %d, %d (UTC)." % (_MONTHS[t.tm_mon - 1], t.tm_mday, t.tm_year)
            raise Abort(Reply.error(head + " You can still read, but not post or send anything.", 403))
        return m

    def need_mod(self):
        """need() plus 'Not allowed.' for everyone but moderators and admins."""
        m = self.need()
        if not m["mod"]:
            raise Abort(Reply.error("Not allowed.", 403))
        return m

    def need_admin(self):
        """need() plus the admin check (what PHP did as need() then `if (!$m['admin'])`)."""
        m = self.need()
        if not m["admin"]:
            raise Abort(Reply.error("Not allowed.", 403))
        return m
