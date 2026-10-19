"""Private-chat settings kept per person: mute, "delete chat for me", nickname and background (PHP: dmother, dmset, dmst, dmstset, held)."""


class DirectChats:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def held(alias: str) -> str:
        """SQL for 'this message is a Masque message still waiting for the receiver to accept the request'."""
        z = alias
        return ("(%s.tm=1 AND NOT EXISTS(SELECT 1 FROM mreq hr WHERE hr.owner=%s.b AND hr.peer=%s.a AND hr.pm=%s.fm AND hr.st=1)"
                " AND NOT EXISTS(SELECT 1 FROM messages hy WHERE hy.a=%s.b AND hy.fm=1 AND hy.b=%s.a AND hy.tm=%s.fm))" % ((z,) * 7))

    def other(self, name: str, ps: int):
        """The other side of a chat by name: its user id, or None. ps=1 means the name belongs to a Masque."""
        sql = "SELECT uid FROM masks WHERE name=?" if ps else "SELECT id FROM users WHERE name=?"
        o = self.db.value(sql, (name,))
        return int(o) if o else None

    def state(self, uid, oid, ps, ms) -> dict:
        return self.db.one("SELECT mute,clr FROM dmstate WHERE uid=? AND oid=? AND ps=? AND ms=?", (uid, oid, ps, ms)) or {"mute": 0, "clr": 0}

    def set_state(self, uid, oid, ps, ms, col: str, val):
        if col not in ("mute", "clr"):
            raise ValueError(col)
        self.db.execute("INSERT INTO dmstate(uid,oid,ps,ms,%s) VALUES(?,?,?,?,?) ON CONFLICT(uid,oid,ps,ms) DO UPDATE SET %s=excluded.%s" % (col, col, col),
                        (uid, oid, ps, ms, val))
        self.db.execute("DELETE FROM dmstate WHERE uid=? AND oid=? AND ps=? AND ms=? AND mute=0 AND clr=0", (uid, oid, ps, ms))

    def set_pref(self, uid, oid, ps, col: str, val):
        if col not in ("nick", "bg"):
            raise ValueError(col)
        self.db.execute("INSERT INTO dmpref(uid,oid,ps,%s) VALUES(?,?,?,?) ON CONFLICT(uid,oid,ps) DO UPDATE SET %s=excluded.%s" % (col, col, col),
                        (uid, oid, ps, val))
        self.db.execute("DELETE FROM dmpref WHERE uid=? AND oid=? AND ps=? AND nick='' AND bg=''", (uid, oid, ps))
