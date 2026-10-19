"""What direct chats and group chats share: reactions, quoted messages, pinned messages, finding the other side, group membership
(PHP: REACTS, MAXPINS, BGS, decor, pinfo, gmem, gpm and the name look-ups repeated in thread, typing, send, msearch)."""
from .php import ids_sql

REACTS = ("\u2764\ufe0f", "\U0001f602", "\U0001f62e", "\U0001f622", "\U0001f44d", "\U0001f525")
MAX_PINS = 5
# the last three are the limited-time Castle Night chat backgrounds (see Unlocks.event_on)
BACKGROUNDS = ("sage", "sky", "rose", "sand", "lilac", "dusk", "dots", "grid", "starry", "petals", "curtain", "castle", "castlepaint", "castleash")
EVENT_BACKGROUNDS = ("castle", "castlepaint", "castleash")

_BLOCKED = "SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?"


def pin_info(r: dict) -> dict:
    """Short form of a message for quotes and the pinned bar."""
    img = str(r.get("img") or "")
    return {
        "id": int(r["id"]),
        "t": str(r["txt"] or "")[:80],
        "i": 1 if img != "" else 0,
        "img": img,
        "mine": int(r["mine"]),
        "who": str(r.get("who") or ""),
        "av": str(r.get("av") or ""),
        "mk": int(r.get("mk") or 0),
    }


class Counterpart:
    """Who is on the other side of a chat, found by name. A name is a real account, or else a Masque (then `ps` is 1)."""

    def __init__(self, db):
        self.db = db

    def find(self, name: str, me: int, self_mask_ok: bool = False):
        """(user id, ps) or (None, 0). A Masque that belongs to `me` only counts when self_mask_ok (send wants to say 'not yourself')."""
        o = self.db.value("SELECT id FROM users WHERE name=?", (name,))
        if o:
            return int(o), 0
        kk = self.db.value("SELECT uid FROM masks WHERE name=?", (name,))
        if kk and (self_mask_ok or int(kk) != int(me)):
            return int(kk), 1
        return None, 0

    def own_mask(self, uid: int) -> bool:
        return bool(self.db.value("SELECT 1 FROM masks WHERE uid=?", (uid,)))

    def masque_side(self, uid: int, flag) -> int:
        """1 when the person asked to speak as their Masque and really has one."""
        return 1 if flag and self.own_mask(uid) else 0


class Pair:
    """The SQL that picks the messages of one direct chat, whichever side sent them: (me, my side ms) <-> (oid, their side ps)."""
    WHERE = "((a=? AND fm=? AND b=? AND tm=?) OR (a=? AND fm=? AND b=? AND tm=?))"

    @staticmethod
    def args(me, ms, oid, ps) -> tuple:
        return (me, ms, oid, ps, oid, ps, me, ms)


class GroupAccess:
    """Who is in a group chat (PHP: gmem, gpm)."""

    def __init__(self, db):
        self.db = db

    def member(self, gid, uid) -> bool:
        return bool(self.db.value("SELECT 1 FROM gmembers WHERE gid=? AND uid=?", (gid, uid)))

    def masque_only(self, gid, uid) -> int:
        """1 = this member is in the group only as their Masque."""
        return int(self.db.value("SELECT pm FROM gmembers WHERE gid=? AND uid=?", (gid, uid), 0) or 0)


class Decorator:
    """Reaction counts and the quoted message for a page of chat rows. kind is 'd' (direct) or 'g' (group).
    Adds `rx` (list of e/n/me) and `rq` (the quoted message, or {id, gone}) to every row and drops `rp`."""

    def __init__(self, db):
        self.db = db

    def apply(self, kind: str, rows: list, me: int, gid: int = 0):
        if not rows:
            return
        db = self.db
        ids = ids_sql(r["id"] for r in rows)
        group = kind == "g"
        sql = ("SELECT mid,e,COUNT(*) n,MAX(uid=?) me FROM mreact WHERE k=? AND mid IN (%s)" % ids
               + (" AND (uid NOT IN (SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?) OR EXISTS(SELECT 1 FROM gmessages gm "
                  "JOIN gmembers gq ON gq.gid=gm.gid AND gq.uid=mreact.uid WHERE gm.id=mreact.mid AND gq.pm=1))" if group else "")
               + " GROUP BY mid,e ORDER BY n DESC,MIN(rowid)")
        by = {}
        for r in db.all(sql, (me, kind, me, me) if group else (me, kind)):
            by.setdefault(int(r["mid"]), []).append({"e": r["e"], "n": int(r["n"]), "me": int(r["me"])})
        quoted = {int(r["rp"]) for r in rows if int(r.get("rp") or 0) > 0}
        parents = {}
        if quoted:
            pi = ids_sql(quoted)
            if group:
                found = db.all(
                    "SELECT x.id,x.txt,x.img,(x.uid=?) mine,CASE WHEN x.pm=1 THEN COALESCE(k.name,'Masque') ELSE COALESCE(NULLIF(u.nick,''),u.name) END who,"
                    "CASE WHEN x.pm=1 THEN COALESCE(k.avatar,'') ELSE u.avatar END av,x.pm mk FROM gmessages x JOIN users u ON u.id=x.uid "
                    "LEFT JOIN masks k ON k.uid=x.uid WHERE x.gid=? AND x.id IN (%s) AND (x.pm=1 OR x.uid NOT IN (%s))" % (pi, _BLOCKED),
                    (me, gid, me, me))
            else:
                found = db.all("SELECT id,txt,img,(a=?) mine FROM messages WHERE (a=? OR b=?) AND id IN (%s)" % pi, (me, me, me))
            parents = {int(r["id"]): pin_info(r) for r in found}
        for r in rows:
            r["rx"] = by.get(int(r["id"]), [])
            p = int(r.pop("rp", 0) or 0)
            r["rq"] = (parents.get(p) or {"id": p, "gone": 1}) if p > 0 else None
