"""Group chats: who is in one, who may be added, and the small events shown in the thread (PHP: gmem, gpm, gcount, gblk, gev, member-list parsing)."""
from .chatview import GroupAccess

MAX_PEOPLE = 31       # a group holds up to 31 names (members plus pending invites)
MAX_LISTED = 30       # how many names one create / add request looks at


class Groups(GroupAccess):
    """GroupAccess (member, masque_only) plus counting, blocking and the event log."""

    def count(self, gid) -> int:
        """How many names the group shows: members plus Masques that sit beside a real member (Masque-only members already have a row)."""
        n = int(self.db.value("SELECT COUNT(*) FROM gmembers WHERE gid=?", (gid,), 0))
        return n + int(self.db.value(
            "SELECT COUNT(*) FROM gmasks a JOIN gmembers b ON b.gid=a.gid AND b.uid=a.uid AND b.pm=0 WHERE a.gid=?", (gid,), 0))

    def blocked_with_member(self, gid, uid) -> bool:
        """Someone already in the group blocked this person, or was blocked by them."""
        return bool(self.db.value(
            "SELECT 1 FROM gmembers mb JOIN blocks b ON (b.a=mb.uid AND b.b=?) OR (b.a=? AND b.b=mb.uid) WHERE mb.gid=? LIMIT 1", (uid, uid, gid)))

    def event(self, gid, uid, kind: str, tid=0, arg="", pm=0, tpm=0, now: int = 0):
        """One line in the thread ('x invited y'); only the newest 200 per group are kept."""
        import time
        db, gid = self.db, int(gid)
        db.execute("INSERT INTO gevents(gid,uid,kind,tid,arg,ts,pm,tpm) VALUES(?,?,?,?,?,?,?,?)",
                   (gid, int(uid), kind, int(tid), str(arg)[:40], now or int(time.time()), int(pm), int(tpm)))
        db.execute("DELETE FROM gevents WHERE gid=? AND id NOT IN (SELECT id FROM gevents WHERE gid=? ORDER BY id DESC LIMIT 200)", (gid, gid))

    @staticmethod
    def names(raw: str) -> list:
        """'a,b,,0,a' -> ['a', 'b'] (array_slice(array_unique(array_filter(explode(',', ...))), 0, 30))."""
        seen = []
        for x in str(raw).split(","):
            if x not in ("", "0") and x not in seen:
                seen.append(x)
        return seen[:MAX_LISTED]

    def user_id(self, name: str):
        v = self.db.value("SELECT id FROM users WHERE name=?", (name,))
        return int(v) if v else None


class Membership:
    """Putting people into a group and taking a whole group away (PHP: gjoin, gjoinmask, and the clean-up in gleave).
    Every method returns an error text, or '' when it worked."""

    def __init__(self, groups: Groups):
        self.groups = groups
        self.db = groups.db

    def _next_read_mark(self, gid) -> int:
        return int(self.db.value("SELECT COALESCE(MAX(id),0) FROM gmessages WHERE gid=?", (gid,), 0))

    def join(self, gid, uid, how: str) -> str:
        """After an accepted invite or an opened invite link."""
        g, db = self.groups, self.db
        if g.member(gid, uid):
            if not g.masque_only(gid, uid):
                return ""
            db.execute("UPDATE gmembers SET pm=0 WHERE gid=? AND uid=?", (gid, uid))  # was only here as their Masque, now also as themselves
            db.execute("DELETE FROM ginvites WHERE gid=? AND uid=?", (gid, uid))
            g.event(gid, uid, "join", 0, how)
            return ""
        if g.count(gid) >= MAX_PEOPLE:
            return "That group is full."
        if g.blocked_with_member(gid, uid):
            return "You cannot join this group."
        rd = self._next_read_mark(gid)
        db.execute("INSERT OR IGNORE INTO gmembers(gid,uid,rd,since) VALUES(?,?,?,?)", (gid, uid, rd, rd))
        db.execute("DELETE FROM ginvites WHERE gid=? AND uid=?", (gid, uid))
        g.event(gid, uid, "join", 0, how)
        return ""

    def join_mask(self, gid, uid) -> str:
        """Somebody accepted an invite for their Masque."""
        g, db = self.groups, self.db
        if not db.value("SELECT 1 FROM masks WHERE uid=?", (uid,)):
            return "You do not have a Masque any more."
        if db.value("SELECT 1 FROM gmasks WHERE gid=? AND uid=?", (gid, uid)):
            db.execute("DELETE FROM ginvites WHERE gid=? AND uid=?", (gid, uid))
            return ""
        if g.count(gid) >= MAX_PEOPLE:
            return "That group is full."
        if g.blocked_with_member(gid, uid):
            return "You cannot join this group."
        if not g.member(gid, uid):
            rd = self._next_read_mark(gid)
            db.execute("INSERT OR IGNORE INTO gmembers(gid,uid,rd,since,pm) VALUES(?,?,?,?,1)", (gid, uid, rd, rd))
        db.execute("INSERT OR IGNORE INTO gmasks(gid,uid) VALUES(?,?)", (gid, uid))
        db.execute("DELETE FROM ginvites WHERE gid=? AND uid=?", (gid, uid))
        g.event(gid, uid, "join", 0, "invite", 1)
        return ""

    def dissolve(self, gid) -> list:
        """Delete an empty group with everything in it. Returns the file names (avatar, attachments) for Uploads.remove()."""
        db = self.db
        files = [str(db.value("SELECT avatar FROM gchats WHERE id=?", (gid,)) or "")]
        files += [str(r["img"]) for r in db.all("SELECT img FROM gmessages WHERE gid=? AND img!=''", (gid,))]
        for t in ("gmessages", "gevents", "ginvites", "glinks", "gmasks"):
            db.execute("DELETE FROM %s WHERE gid=?" % t, (gid,))
        db.execute("DELETE FROM gchats WHERE id=?", (gid,))
        return files
