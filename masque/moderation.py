"""Word filter, auto-hide of reported posts and the admin log (PHP: wmatch, wapply, hidn, hida, alog)."""
import os
import re
import secrets
import time


class AutoHide:
    """A post reported by AUTOHIDE (default 5, 0 = off) different accounts that are at least AUTOHIDE_AGE seconds old (default 1 day)
    disappears from feeds for everyone except its author and admins, until an admin dismisses or deletes the reports."""

    @staticmethod
    def threshold() -> int:
        v = os.environ.get("AUTOHIDE")
        if v is None:
            return 5
        try:
            return max(0, int(v))
        except ValueError:
            return 0

    @staticmethod
    def min_age() -> int:
        v = os.environ.get("AUTOHIDE_AGE")
        if v is None:
            return 86400
        try:
            return max(0, int(v))
        except ValueError:
            return 0


class WordFilter:
    """Admins keep a list of blocked words/phrases (table badwords). Whole words only, case-insensitive. A match either flags the post/comment
    (still visible, but it shows up on the Reports page) or holds it back (hidden from everyone but its author and admins until an admin approves it).
    Automatic entries are rows in `reports` with uid 0. Admins are never filtered."""

    _ALNUM = r"[^\W_]"  # a letter or a digit (PHP \p{L}\p{N})

    def __init__(self, db):
        self.db = db
        self._list = None

    def _words(self):
        if self._list is None:
            self._list = self.db.all("SELECT w,hold FROM badwords")
        return self._list

    def forget(self):
        self._list = None

    def match(self, text):
        """The matching badwords row (a hold entry wins over a flag entry), or None."""
        words = self._words()
        if not words:
            return None
        t = re.sub(r"[\u00ad\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff]", "", str(text))
        hit = None
        for r in words:
            pat = r"(?<!%s)%s(?!%s)" % (self._ALNUM, r"\s+".join(re.escape(x) for x in str(r["w"]).split(" ")), self._ALNUM)
            try:
                found = re.search(pat, t, re.I) is not None
            except re.error:
                found = False
            if found:
                if int(r["hold"]):
                    return r
                hit = hit or r
        return hit

    def apply(self, kind: str, rid: int, text: str, m) -> int:
        """Flag or hold a post/comment after it was saved. Returns 1 when it is held back."""
        self.db.execute("DELETE FROM reports WHERE uid=0 AND kind=? AND tid=?", (kind, rid))
        held = 0
        r = None if m["admin"] else self.match(text)
        if r:
            held = int(r["hold"])
            self.db.execute("INSERT INTO reports(uid,kind,tid,why,ts) VALUES(0,?,?,?,?)",
                            (kind, rid, 'Word filter: "%s" (%s)' % (r["w"], "held back" if held else "flagged"), int(time.time())))
        self.db.execute("UPDATE %s SET hold=? WHERE id=?" % ("posts" if kind == "post" else "comments"), (held, rid))
        return held


class AdminLog:
    """Admin action log (kept 90 days)."""

    def __init__(self, db):
        self.db = db

    def add(self, m, act: str, target=""):
        if secrets.randbelow(20) == 0:
            self.db.execute("DELETE FROM alog WHERE ts<?", (int(time.time()) - 7776000,))
        self.db.execute("INSERT INTO alog(aid,act,tgt,ts) VALUES(?,?,?,?)",
                        (m["id"], _bytes_cut(act, 40), _bytes_cut(str(target), 40), int(time.time())))

    def target_name(self, kind: str, tid) -> str:
        """PHP rtname(): the account name behind a reported thing."""
        db = self.db
        if kind == "post":
            v = db.value("SELECT u.name FROM posts p JOIN users u ON u.id=p.uid WHERE p.id=?", (tid,))
        elif kind == "comment":
            v = db.value("SELECT u.name FROM comments c JOIN users u ON u.id=c.uid WHERE c.id=?", (tid,))
        elif kind == "ask":
            v = db.value("SELECT u.name FROM asks a JOIN users u ON u.id=a.frm WHERE a.id=?", (tid,))
        else:
            v = db.value("SELECT name FROM users WHERE id=?", (tid,))
        return str(v or "")


def _bytes_cut(s: str, n: int) -> str:
    """PHP substr($s, 0, $n) (counts bytes)."""
    return s.encode("utf-8")[:n].decode("utf-8", "ignore")
