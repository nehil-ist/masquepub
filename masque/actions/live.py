"""The page's heartbeat and per-chat switches: unread, live, cmute, cdel (PHP: case 'unread', 'live', 'cmute', 'cdel')."""
import hashlib
import time

from ..chatstate import DirectChats
from ..presence import Presence
from .base import Action, Context, Reply, registry

_BLOCKED = "SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?"


@registry.register
class Unread(Action):
    """?a=unread: the numbers for the navigation badges."""
    name = "unread"

    def handle(self, ctx: Context) -> Reply:
        return Reply(ctx.unread.get(ctx.users.need()["id"]))


class Toasts:
    """The pop-up banners for what arrived since the page's last look."""

    def __init__(self, ctx: Context, uid: int):
        self.db, self.i = ctx.db, uid

    def direct(self, after: int, upto: int):
        i = self.i
        # a Masque sender is only ever shown as the Masque (name and picture), never as the real account
        return self.db.all(
            "SELECT z.id,z.ts,z.fm,z.tm,substr(z.txt,1,140) txt,(z.img!='') img,CASE WHEN z.fm=1 THEN k.name ELSE u.name END name,"
            "CASE WHEN z.fm=1 THEN '' ELSE u.nick END nick,CASE WHEN z.fm=1 THEN k.avatar ELSE u.avatar END avatar,"
            "(SELECT p.nick FROM dmpref p WHERE p.uid=? AND p.oid=z.a AND p.ps=z.fm) pn FROM messages z JOIN users u ON u.id=z.a "
            "LEFT JOIN masks k ON k.uid=z.a WHERE NOT " + DirectChats.held("z") + " AND z.b=? AND z.id>? AND z.id<=? AND z.seen=0 "
            "AND NOT EXISTS(SELECT 1 FROM dmstate s WHERE s.uid=z.b AND s.oid=z.a AND s.ps=z.fm AND s.ms=z.tm AND (s.mute=1 OR s.clr>=z.id)) "
            "AND (z.fm=1 OR z.tm=1 OR z.a NOT IN (SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?)) "
            "AND (z.fm=0 OR (k.id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM mblocks mk WHERE mk.a=? AND mk.kid=k.id))) ORDER BY z.id DESC LIMIT 3",
            (i, i, after, upto, i, i, i))

    def group(self, after: int, upto: int):
        i = self.i
        return self.db.all(
            "SELECT z.id,z.gid,z.ts,substr(z.txt,1,140) txt,(z.img!='') img,g.name gname,g.avatar gav,"
            "CASE WHEN z.pm=1 THEN COALESCE(k.name,'Masque') ELSE COALESCE(NULLIF(u.nick,''),u.name) END who FROM gmessages z "
            "JOIN gmembers mb ON mb.gid=z.gid AND mb.uid=? JOIN gchats g ON g.id=z.gid JOIN users u ON u.id=z.uid LEFT JOIN masks k ON k.uid=z.uid "
            "WHERE mb.mute=0 AND z.id>? AND z.id<=? AND z.uid!=? AND z.id>mb.rd "
            "AND (z.pm=1 OR z.uid NOT IN (SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?)) ORDER BY z.id DESC LIMIT 3",
            (i, after, upto, i, i, i))


@registry.register
class Live(Action):
    """?a=live: a cheap change-detector the page polls every few seconds. It only says WHAT changed; the page then fetches it."""
    name = "live"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        i = int(m["id"])
        o = ctx.unread.get(i)
        now = ctx.now
        hb = db.one("SELECT la,idl FROM users WHERE id=?", (i,))
        idl = 1 if ctx.qflag("idl") else 0
        if not hb or now - int(hb["la"] or 0) >= 15 or int(hb["idl"] or 0) != idl:
            db.execute("UPDATE users SET la=?,idl=? WHERE id=?", (now, idl, i))
        o["nv"] = int(db.value("SELECT COALESCE(MAX(id),0) FROM notifs WHERE uid=?", (i,), 0))
        o["mv"] = (str(db.value("SELECT COALESCE(MAX(id),0)||':'||COUNT(*) FROM messages WHERE a=? OR b=?", (i, i)))
                   + "/" + str(db.value("SELECT COALESCE(MAX(z.id),0)||':'||COUNT(*) FROM gmessages z JOIN gmembers mb ON mb.gid=z.gid AND mb.uid=?", (i,))))
        o["now"] = now
        o["mid"] = int(db.value("SELECT COALESCE(MAX(id),0) FROM messages WHERE b=?", (i,), 0))
        o["gmid"] = int(db.value("SELECT COALESCE(MAX(z.id),0) FROM gmessages z JOIN gmembers mb ON mb.gid=z.gid AND mb.uid=? WHERE z.uid!=?", (i, i), 0))
        af, gaf = ctx.int_arg("af"), ctx.int_arg("gaf")
        silent = not int(ctx.notes.prefs.get(i)["pop"]) or ctx.notes.quiet(i)
        toasts = Toasts(ctx, i)
        if not silent and af > 0 and o["mid"] > af:
            o["toast"] = toasts.direct(af, o["mid"])
        if not silent and gaf > 0 and o["gmid"] > gaf:
            o["gtoast"] = toasts.group(gaf, o["gmid"])
        kind = ctx.arg("k")
        if kind == "d":
            self._direct(ctx, i, o)
        elif kind == "g":
            self._group(ctx, i, o)
        if ctx.qflag("inb"):
            blocked = {int(r[0]) for r in db.query(_BLOCKED, (i, i)).fetchall()}
            sts = {}
            for r in db.all("SELECT u.id,u.name,u.la,u.pst,u.idl FROM users u WHERE u.id IN (SELECT CASE WHEN a=? THEN b ELSE a END FROM messages "
                            "WHERE (a=? OR b=?) AND fm=0 AND tm=0 GROUP BY 1 ORDER BY MAX(id) DESC LIMIT 50)", (i, i, i)):
                sts[r["name"]] = "off" if int(r["id"]) in blocked else Presence.state(r)
            o["sts"] = sts if sts else []  # PHP sends an empty array, not an empty object
        return Reply(o)

    @staticmethod
    def _direct(ctx: Context, i: int, o: dict):
        """The open private chat: is the other side typing, are they online, did anything in the thread change."""
        db = ctx.db
        ms = 1 if (ctx.arg("as") == "1" and db.value("SELECT 1 FROM masks WHERE uid=?", (i,))) else 0
        ps = 0
        oid = db.value("SELECT id FROM users WHERE name=?", (ctx.arg("u"),))
        if not oid:
            kk = db.value("SELECT uid FROM masks WHERE name=?", (ctx.arg("u"),))
            if kk and int(kk) != i:
                oid, ps = kk, 1
        typing = bool(oid and (ps or ms or not ctx.rel.blocked(i, int(oid)))
                      and not (ps and db.value("SELECT 1 FROM mblocks WHERE a=? AND kid=(SELECT id FROM masks WHERE uid=?)", (i, oid)))
                      and db.value("SELECT 1 FROM typing WHERE uid=? AND oid=? AND fm=? AND tm=? AND gid=0 AND ts>?", (oid, i, ps, ms, int(time.time()) - 5)))
        o["ty"] = 1 if typing else 0
        if oid and not ps and not ms:  # no status in any Masque chat, on either side
            o["st"] = "off" if ctx.rel.blocked(i, int(oid)) else Presence.state(db.one("SELECT la,pst,idl FROM users WHERE id=?", (oid,)))
        if oid:
            o["th"] = db.value("SELECT COALESCE(MAX(id),0)||':'||COUNT(*)||':'||COALESCE(SUM(ed),0)||':'||COALESCE(SUM(seen),0) FROM messages "
                               "WHERE (a=? AND fm=? AND b=? AND tm=?) OR (a=? AND fm=? AND b=? AND tm=?)", (i, ms, oid, ps, oid, ps, i, ms))

    @staticmethod
    def _group(ctx: Context, i: int, o: dict):
        db = ctx.db
        g = ctx.int_arg("id")
        member = bool(g and db.value("SELECT 1 FROM gmembers WHERE gid=? AND uid=?", (g, i)))
        o["ty"] = [r[0] for r in db.query(
            "SELECT CASE WHEN t.tm=1 THEN COALESCE(k.name,'Masque') ELSE COALESCE(NULLIF(u.nick,''),u.name) END FROM typing t JOIN users u ON u.id=t.uid "
            "LEFT JOIN masks k ON k.uid=t.uid WHERE t.gid=? AND t.uid!=? AND t.ts>? AND (t.tm=1 OR t.uid NOT IN (SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?)) "
            "ORDER BY t.ts DESC LIMIT 3", (g, i, int(time.time()) - 5, i, i)).fetchall()] if member else []
        if member:
            look = db.value("SELECT name||'|'||COALESCE(bg,'')||'|'||COALESCE(avatar,'') FROM gchats WHERE id=?", (g,)) or ""
            last_event = db.value("SELECT COALESCE(MAX(id),0) FROM gevents WHERE gid=?", (g,))
            o["th"] = ":".join([
                str(db.value("SELECT COALESCE(MAX(id),0)||':'||COUNT(*)||':'||COALESCE(SUM(ed),0) FROM gmessages WHERE gid=?", (g,))),
                str(db.value("SELECT COALESCE(SUM(rd),0)||':'||COUNT(*) FROM gmembers WHERE gid=?", (g,))),
                hashlib.md5(("%s|%s" % (look, last_event)).encode()).hexdigest()])


class _ChatSwitch(Action):
    """Shared start of cmute and cdel: who is the other side of the chat."""

    def other(self, ctx: Context, m):
        ps = 1 if ctx.flag("mk") else 0
        ms = 1 if (ctx.flag("as") and ctx.db.value("SELECT 1 FROM masks WHERE uid=?", (m["id"],))) else 0
        oid = ctx.dms.other(ctx.form("u"), ps)
        if not oid or oid == int(m["id"]):
            ctx.deny("No such user.", 404)
        return oid, ps, ms


@registry.register
class ChatMute(_ChatSwitch):
    """?a=cmute: no pop-ups or badge counts from this chat."""
    name = "cmute"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        oid, ps, ms = self.other(ctx, m)
        on = 1 if ctx.flag("on") else 0
        ctx.dms.set_state(m["id"], oid, ps, ms, "mute", on)
        return Reply({"mu": on})


@registry.register
class ChatDelete(_ChatSwitch):
    """?a=cdel: 'Delete chat' for this person only. Everything up to now is hidden from them; the other side keeps it, and a new message brings the chat back."""
    name = "cdel"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        oid, ps, ms = self.other(ctx, m)
        last = int(ctx.db.value("SELECT COALESCE(MAX(id),0) FROM messages WHERE (a=? AND fm=? AND b=? AND tm=?) OR (a=? AND fm=? AND b=? AND tm=?)",
                                (m["id"], ms, oid, ps, oid, ps, m["id"], ms), 0))
        ctx.dms.set_state(m["id"], oid, ps, ms, "clr", last)
        return Reply({"ok": 1})
