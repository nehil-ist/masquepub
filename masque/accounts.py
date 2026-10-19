"""Account life cycle: signing up and in, passwords, the admin account, and deleting an account.
(PHP: the helpers behind the signup / login / recover / pw / delacct actions.)"""
import re
import secrets
import sqlite3
import time

from .actions.base import Abort, Reply
from .config import ascii_lower
from .names import NameRules
from .tidy import Tidy

_UPLOAD_NAME = re.compile(r"[a-f0-9]{24}\.(jpg|png|webp|gif|mp3|m4a|aac|ogg|opus|wav|flac)")
_NEXT_ID = "SELECT MAX((SELECT COALESCE(MAX(id),0) FROM users),(SELECT COALESCE(MAX(uid),0) FROM gone))+1"


class Accounts:
    """Everything about one account's sign-in state for the current request."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.db = ctx.db

    # -- sessions --
    def sign_in(self, uid: int, sv: int):
        """New session id, remember who it is, and give this browser a fresh device row."""
        s = self.ctx.begin_session()
        s.regenerate()
        s.set("u", int(uid))
        s.set("sv", int(sv))
        self.ctx.users.devices.new(int(uid))
        self.ctx.users.reset()

    def forget_other_devices(self, uid: int):
        """Every browser of this account is signed out (the caller then signs this one in again)."""
        self.db.execute("DELETE FROM devices WHERE uid=?", (uid,))
        self.ctx.session.unset("d")

    # -- passwords --
    def confirm_password(self, uid: int, given: str, wrong_msg: str = "Wrong password."):
        """Check the signed-in person's password, with the 10-wrong-guesses-per-15-minutes limit."""
        row = self.db.one("SELECT pw FROM users WHERE id=?", (uid,))
        self.ctx.limiter.wrong_password_guard(uid)
        if not row or not self.ctx.hasher.verify(given, row["pw"]):
            self.ctx.limiter.wrong_password(uid)
            raise Abort(Reply.error(wrong_msg, 400))

    # -- creating accounts --
    def next_id_insert(self, name: str, pw_hash: str):
        """Insert with an id above every id ever used (live or deleted), so a new account never inherits a deleted user's leftovers.
        Returns the new id, 0 when it could not be done, or -1 when the name was taken meanwhile."""
        for _ in range(3):
            cand = int(self.db.value(_NEXT_ID))
            try:
                self.db.execute("INSERT INTO users(id,name,pw,ts) VALUES(?,?,?,?)", (cand, name, pw_hash, int(time.time())))
                return cand
            except sqlite3.IntegrityError:
                if self.db.value("SELECT 1 FROM users WHERE name=?", (name,)):
                    return -1
        return 0

    def admin_sync(self, name: str, password: str):
        """ADMIN_USER + ADMIN_PASSWORD define one admin account: created on first login, password reset to the variable's on later ones."""
        hasher = self.ctx.hasher
        u = self.db.one("SELECT id,pw FROM users WHERE name=?", (name,))
        if u:
            if not hasher.verify(password, u["pw"]):
                self.db.execute("UPDATE users SET pw=?,sv=sv+1 WHERE id=?", (hasher.hash(password), u["id"]))
            return
        if NameRules(self.db).reserved(name):
            return
        try:
            self.next_id_insert(name, hasher.hash(password))
        except sqlite3.Error:
            pass


class AccountEraser:
    """Deletes an account and everything of it: posts, chats, comments, likes, photos. Its name is kept as taken."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.db = ctx.db

    def erase(self, uid: int, name: str):
        db, i = self.db, int(uid)
        u = db.one("SELECT pw,avatar,cover FROM users WHERE id=?", (i,))
        col = lambda sql, *p: [r[0] for r in db.query(sql, p).fetchall()]  # noqa: E731
        files = col("SELECT img FROM posts WHERE uid=? AND img!=''", i)
        files += [u["avatar"], u["cover"]]
        files += col("SELECT img FROM postimgs WHERE pid IN (SELECT id FROM posts WHERE uid=?)", i)
        files += col("SELECT img FROM pend WHERE uid=?", i)
        files += col("SELECT img FROM messages WHERE (a=? OR b=?) AND img!=''", i, i)
        with db.transaction():
            files += col("SELECT img FROM gmessages WHERE uid=? AND img!=''", i)
            self._groups(i, files)
            db.execute("INSERT OR IGNORE INTO gone VALUES(?,?)", (NameRules.digest(name), i))
            for sql, args in (
                ("DELETE FROM likes WHERE uid=? OR pid IN (SELECT id FROM posts WHERE uid=?)", (i, i)),
                ("DELETE FROM comments WHERE uid=? OR pid IN (SELECT id FROM posts WHERE uid=?)", (i, i)),
                ("DELETE FROM clikes WHERE uid=? OR cid NOT IN (SELECT id FROM comments)", (i,)),
                ("DELETE FROM reports WHERE uid=? OR (kind='user' AND tid=?) OR (kind='post' AND tid IN (SELECT id FROM posts WHERE uid=?)) "
                 "OR (kind='comment' AND tid NOT IN (SELECT id FROM comments))", (i, i, i)),
                ("DELETE FROM notifs WHERE uid=? OR actor=? OR (kind NOT IN ('gift','gment','gall') AND pid>0 AND pid IN "
                 "(SELECT id FROM posts WHERE uid=?))", (i, i, i)),
                ("DELETE FROM nprefs WHERE uid=?", (i,)),
                ("DELETE FROM saves WHERE uid=? OR pid IN (SELECT id FROM posts WHERE uid=?)", (i, i)),
                ("DELETE FROM postviews WHERE uid=? OR pid IN (SELECT id FROM posts WHERE uid=?)", (i, i)),
                ("DELETE FROM postimgs WHERE pid IN (SELECT id FROM posts WHERE uid=?)", (i,)),
                ("DELETE FROM pend WHERE uid=?", (i,)),
                ("DELETE FROM posts WHERE uid=?", (i,)),
                ("DELETE FROM messages WHERE a=? OR b=?", (i, i)),
                ("DELETE FROM tagfollows WHERE uid=?", (i,)),
                ("DELETE FROM friends WHERE a=? OR b=?", (i, i)),
                ("DELETE FROM follows WHERE a=? OR b=?", (i, i)),
                ("DELETE FROM blocks WHERE a=? OR b=?", (i, i)),
            ):
                db.execute(sql, args)
            for mk in db.all("SELECT name,avatar FROM masks WHERE uid=?", (i,)):
                files.append(mk["avatar"])
                db.execute("INSERT OR IGNORE INTO gone VALUES(?,?)", (NameRules.digest(mk["name"]), i))
            for sql, args in (
                ("DELETE FROM reports WHERE kind='mask' AND tid IN (SELECT id FROM masks WHERE uid=?)", (i,)),
                ("DELETE FROM masks WHERE uid=?", (i,)),
                ("DELETE FROM asks WHERE uid=? OR frm=?", (i, i)),
                ("DELETE FROM users WHERE id=?", (i,)),
                ("DELETE FROM devices WHERE uid=?", (i,)),
                ("DELETE FROM appeals WHERE uid=?", (i,)),
            ):
                db.execute(sql, args)
            Tidy(db).run()
        Tidy(db).run()
        up = self.ctx.cfg.data_dir / "up"
        for f in files:
            if f and _UPLOAD_NAME.fullmatch(str(f)):
                try:
                    (up / f).unlink()
                except OSError:
                    pass

    def _groups(self, i: int, files: list):
        db = self.db
        col = lambda sql, *p: [r[0] for r in db.query(sql, p).fetchall()]  # noqa: E731
        db.execute("DELETE FROM gmessages WHERE uid=?", (i,))
        db.execute("DELETE FROM gmasks WHERE uid=?", (i,))
        db.execute("DELETE FROM ginvites WHERE uid=? OR inv=?", (i, i))
        db.execute("DELETE FROM mailtok WHERE uid=?", (i,))
        for g in col("SELECT gid FROM gmembers WHERE uid=?", i):
            db.execute("DELETE FROM gmembers WHERE gid=? AND uid=?", (g, i))
            if not int(db.value("SELECT COUNT(*) FROM gmembers WHERE gid=?", (g,), 0)):  # last member left: the group goes
                files.append(str(db.value("SELECT avatar FROM gchats WHERE id=?", (g,), "")))
                files += col("SELECT img FROM gmessages WHERE gid=? AND img!=''", g)
                for t in ("gmessages", "gevents", "ginvites", "glinks"):
                    db.execute("DELETE FROM %s WHERE gid=?" % t, (g,))
                db.execute("DELETE FROM gchats WHERE id=?", (g,))
            elif db.value("SELECT 1 FROM gchats WHERE id=? AND owner=?", (g, i)):  # the owner left: the oldest member takes over
                nx = db.value("SELECT uid FROM gmembers WHERE gid=? ORDER BY rowid LIMIT 1", (g,))
                db.execute("UPDATE gchats SET owner=? WHERE id=?", (nx, g))
