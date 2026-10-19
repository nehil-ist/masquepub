"""The numbers on the navigation badges: unread chats, friend requests, notifications (PHP: ucounts)."""
from .chatstate import DirectChats


class UnreadCounts:
    def __init__(self, ctx):
        self.ctx, self.db = ctx, ctx.db

    def get(self, uid) -> dict:
        db, i = self.db, int(uid)
        dm = int(db.value(
            "SELECT COUNT(*) FROM messages WHERE b=? AND seen=0 AND NOT EXISTS(SELECT 1 FROM dmstate s WHERE s.uid=messages.b AND s.oid=messages.a "
            "AND s.ps=messages.fm AND s.ms=messages.tm AND (s.mute=1 OR s.clr>=messages.id)) AND NOT " + DirectChats.held("messages"), (i,), 0))
        grp = int(db.value(
            "SELECT COUNT(*) FROM gmessages z JOIN gmembers mb ON mb.gid=z.gid AND mb.uid=? WHERE mb.mute=0 AND z.id>mb.rd AND z.uid!=? "
            "AND (z.pm=1 OR z.uid NOT IN (SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?))", (i, i, i, i), 0))
        o = {
            "n": dm + grp,
            "r": int(db.value("SELECT COUNT(*) FROM friends WHERE b=? AND st=0", (i,), 0)),
            "o": int(db.value("SELECT COUNT(*) FROM notifs WHERE uid=? AND seen=0", (i,), 0)),
            "og": int(db.value("SELECT COUNT(*) FROM notifs WHERE uid=? AND seen=0 AND kind='gift'", (i,), 0)),  # unseen gifts turn the bell gold
        }
        if self.ctx.notes.quiet(i):
            o["n"] = o["r"] = o["o"] = o["og"] = 0
            o["q"] = 1
        return o
