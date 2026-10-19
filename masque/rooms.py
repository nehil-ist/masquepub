"""Chat rooms: temporary Masque-only rooms (PHP: rsweep and the blocked-Masque filter used by every room query)."""
import time

THEMES = ("midnight", "rain", "neon", "castle", "sunrise", "void")
DURATIONS = {1: 3600, 6: 21600}  # anything else is a day
DEFAULT_SECONDS = 86400
MAX_OPEN = 2
ACTIVE_SECONDS = 45  # somebody counts as "here" this long after their last visit

# the Masques I blocked, as user ids (a room owner or writer behind a blocked Masque is hidden)
BLOCKED_MASQUE_OWNERS = "SELECT k.uid FROM mblocks b JOIN masks k ON k.id=b.kid WHERE b.a=?"


class Rooms:
    def __init__(self, db):
        self.db = db

    def sweep(self, now: int = 0):
        """Close finished rooms and delete their messages."""
        db, now = self.db, now or int(time.time())
        for r in db.all("SELECT id FROM rooms WHERE closed=1 OR exp<=?", (now,)):
            x = r["id"]
            db.execute("DELETE FROM rvotes WHERE mid IN (SELECT id FROM rmsgs WHERE rid=?)", (x,))
            db.execute("DELETE FROM rmsgs WHERE rid=?", (x,))
            db.execute("DELETE FROM rpres WHERE rid=?", (x,))
            db.execute("DELETE FROM rooms WHERE id=? AND (closed=1 OR exp<=?)", (x, now))

    def is_open(self, rid: int, now: int) -> bool:
        return bool(self.db.value("SELECT 1 FROM rooms WHERE id=? AND closed=0 AND exp>?", (rid, now)))

    def has_masque(self, uid: int) -> bool:
        return bool(self.db.value("SELECT 1 FROM masks WHERE uid=?", (uid,)))

    def seen(self, rid: int, uid: int, now: int):
        self.db.execute("INSERT OR REPLACE INTO rpres(rid,uid,ts) VALUES(?,?,?)", (rid, uid, now))

    def vote(self, mid: int, voter: int, author: int, v: int) -> int:
        """Set a vote (+1, -1, 0 = take back) and move the author's room reputation (table rrep). Returns the up count."""
        db = self.db
        old = int(db.value("SELECT v FROM rvotes WHERE mid=? AND uid=?", (mid, voter), 0) or 0)
        if old != v:
            db.execute("INSERT OR IGNORE INTO rrep(uid) VALUES(?)", (author,))
            if old == 1:
                db.execute("UPDATE rrep SET up=MAX(0,up-1) WHERE uid=?", (author,))
            if old == -1:
                db.execute("UPDATE rrep SET down=MAX(0,down-1) WHERE uid=?", (author,))
            if v == 1:
                db.execute("UPDATE rrep SET up=up+1 WHERE uid=?", (author,))
            if v == -1:
                db.execute("UPDATE rrep SET down=down+1 WHERE uid=?", (author,))
            if v == 0:
                db.execute("DELETE FROM rvotes WHERE mid=? AND uid=?", (mid, voter))
            else:
                db.execute("INSERT OR REPLACE INTO rvotes(mid,uid,v) VALUES(?,?,?)", (mid, voter, v))
        return int(db.value("SELECT COUNT(*) FROM rvotes WHERE mid=? AND v=1", (mid,), 0))
