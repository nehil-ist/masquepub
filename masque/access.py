"""Who may see or reach whom: blocks, friends, and whether a post is visible to a viewer (PHP: blk, frnd, canpost, pubpost, mqts)."""
import time

from .moderation import AutoHide


def mqts(t, up: bool = False) -> int:
    """Masque times: other people see a Masque's post / comment / edit time rounded down to the hour (an expiry time is rounded up),
    so an exact minute can't be matched against what someone's main account was doing. The owner always sees the real time."""
    t = int(t or 0)
    if t <= 0:
        return t
    return t + ((3600 - t % 3600) % 3600) if up else t - t % 3600


class Relations:
    def __init__(self, db):
        self.db = db

    def blocked(self, x, y) -> bool:
        """A block in either direction."""
        return bool(self.db.value("SELECT 1 FROM blocks WHERE (a=? AND b=?) OR (a=? AND b=?)", (x, y, y, x)))

    def friends(self, x, y) -> bool:
        return bool(self.db.value("SELECT 1 FROM friends WHERE st=1 AND ((a=? AND b=?) OR (a=? AND b=?))", (x, y, y, x)))

    def masque_blocked(self, viewer, masque_id) -> bool:
        """The viewer blocked this one Masque (an account block never applies to a Masque: it would show whose it is)."""
        return bool(self.db.value("SELECT 1 FROM mblocks WHERE a=? AND kid=?", (viewer, masque_id)))


class PostAccess:
    def __init__(self, db, rel: Relations):
        self.db, self.rel = db, rel

    def can_view(self, pid, viewer) -> bool:
        """PHP canpost()."""
        r = self.db.one("SELECT p.uid,p.vis,p.mid,p.anon,u.priv FROM posts p JOIN users u ON u.id=p.uid WHERE p.id=?", (pid,))
        if not r:
            return False
        if int(r["uid"]) == int(viewer):
            return True
        masked = int(r["mid"]) > 0 or int(r["anon"]) != 0
        if masked:
            # Masque / old anonymous posts: account blocks do not apply (they would reveal the owner); only a block on that Masque does
            if int(r["mid"]) > 0 and self.rel.masque_blocked(viewer, int(r["mid"])):
                return False
        elif self.rel.blocked(viewer, r["uid"]):
            return False
        vs = int(r["vis"])
        if vs == 2:
            return False
        if vs == 1 and not self.rel.friends(viewer, r["uid"]):
            return False
        # A Masque (or old anonymous) post ignores the owner's private account: if only the owner's friends could see it, that alone would narrow down whose Masque it is.
        if masked:
            return True
        return not r["priv"] or self.rel.friends(viewer, r["uid"])

    def public_post(self, pid):
        """A post anyone (logged out, a link-preview bot) may see, or None (PHP pubpost())."""
        pid = int(pid)
        if pid < 1:
            return None
        r = self.db.one(
            "SELECT p.id,p.uid,p.cap,p.img,p.ts,p.anon,p.aq,p.mid,p.sens,p.hg,u.name,u.nick,u.avatar,mk.name mkn,mk.avatar mka,"
            "(SELECT COUNT(*) FROM likes l WHERE l.pid=p.id) ln,(SELECT COUNT(*) FROM comments c WHERE c.pid=p.id AND c.hold=0) cn,"
            "(SELECT COUNT(*) FROM polls o WHERE o.pid=p.id) pl FROM posts p JOIN users u ON u.id=p.uid LEFT JOIN masks mk ON mk.id=p.mid "
            "WHERE p.id=? AND u.priv=0 AND p.vis=0 AND p.hold=0 AND (p.exp=0 OR p.exp>?)", (pid, int(time.time())))
        if not r:
            return None
        hide = AutoHide()
        if hide.threshold() > 0 and int(self.db.value(
                "SELECT COUNT(DISTINCT r.uid) FROM reports r JOIN users ru ON ru.id=r.uid WHERE r.kind='post' AND r.tid=? AND ru.ts<=?",
                (pid, int(time.time()) - hide.min_age()), 0)) >= hide.threshold():
            return None
        if str(r["img"] or "") == "":
            r["img"] = str(self.db.value("SELECT img FROM postimgs WHERE pid=? ORDER BY pos LIMIT 1", (pid,), "") or "")
        return r
