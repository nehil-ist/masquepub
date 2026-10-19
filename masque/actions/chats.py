"""Direct chats (PHP: case 'inbox', 'thread', 'typing', 'send', 'msearch', 'editm', 'delm', 'react', 'rxwho', 'pinm', 'setpn', 'setbg', 'mreq').

The two sides of a private chat are (user id, side) pairs. Side 0 is the real account, side 1 is that person's Masque.
In the `messages` table `fm` is the sender's side and `tm` the receiver's side; `ms` below is MY side, `ps` is THEIR side.
"""
import sys
import time

from ..chatview import (BACKGROUNDS, EVENT_BACKGROUNDS, MAX_PINS, REACTS, Counterpart, Decorator, GroupAccess, Pair, pin_info)
from ..chatstate import DirectChats
from ..media import GameInvite
from ..php import collapse_space, like_escape, php_trim
from ..presence import Presence
from ..streaks import ChatStreaks
from .base import Action, Context, Reply, registry

_BLOCKED = "SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?"
_MAXINT = sys.maxsize


class Peer:
    """The other person in the chat the request is about, plus both sides' numbers. Built from the request's name / mk / as values."""

    def __init__(self, ctx: Context, m, name: str, ps: int):
        self.ctx, self.me = ctx, int(m["id"])
        self.ps = ps
        self.oid = ctx.dms.other(name, ps)

    @property
    def ok(self) -> bool:
        return bool(self.oid) and self.oid != self.me

    def need(self) -> int:
        if not self.ok:
            self.ctx.deny("No such user.", 404)
        return self.oid


def _text(ctx: Context, name: str = "txt", limit: int = 500) -> str:
    return php_trim(ctx.form(name)[:limit])


@registry.register
class Inbox(Action):
    """?a=inbox: the chats list (newest first), message requests, and whether Masque requests are open."""
    name = "inbox"

    LAST = (
        "SELECT (CASE WHEN c.ps=1 THEN k.name ELSE u.name END) name,(CASE WHEN c.ps=1 THEN '' ELSE u.nick END) nick,"
        "(CASE WHEN c.ps=1 THEN k.avatar ELSE u.avatar END) avatar,c.ms,c.ps mk,c.txt,c.img,c.ts,c.mine,"
        "(SELECT COUNT(*) FROM messages z WHERE z.a=c.o AND z.fm=c.ps AND z.b=? AND z.tm=c.ms AND z.seen=0 AND z.id>COALESCE((SELECT s.clr FROM dmstate s "
        "WHERE s.uid=? AND s.oid=c.o AND s.ps=c.ps AND s.ms=c.ms),0)) un,"
        "(SELECT p.nick FROM dmpref p WHERE p.uid=? AND p.oid=c.o AND p.ps=c.ps) pn,"
        "COALESCE((SELECT s.mute FROM dmstate s WHERE s.uid=? AND s.oid=c.o AND s.ps=c.ps AND s.ms=c.ms),0) mu,u.id uid,u.la,u.pst,u.idl,u.stx,u.stts "
        "FROM (SELECT id,CASE WHEN a=? THEN b ELSE a END o,CASE WHEN a=? THEN tm ELSE fm END ps,CASE WHEN a=? THEN fm ELSE tm END ms,txt,img,ts,(a=?) mine "
        "FROM messages WHERE id IN (SELECT MAX(id) FROM messages WHERE a=? OR b=? GROUP BY CASE WHEN a=? THEN b ELSE a END,"
        "CASE WHEN a=? THEN fm ELSE tm END,CASE WHEN a=? THEN tm ELSE fm END)) c JOIN users u ON u.id=c.o LEFT JOIN masks k ON k.uid=c.o AND c.ps=1 "
        "WHERE (c.ps=0 OR k.id IS NOT NULL) AND NOT (c.ms=1 AND NOT EXISTS(SELECT 1 FROM mreq hr WHERE hr.owner=? AND hr.peer=c.o AND hr.pm=c.ps AND hr.st=1) "
        "AND NOT EXISTS(SELECT 1 FROM messages hy WHERE hy.a=? AND hy.fm=1 AND hy.b=c.o AND hy.tm=c.ps)) "
        "AND c.id>COALESCE((SELECT s.clr FROM dmstate s WHERE s.uid=? AND s.oid=c.o AND s.ps=c.ps AND s.ms=c.ms),0) ORDER BY c.id DESC LIMIT 50")
    REQUESTS = (
        "SELECT (CASE WHEN m.fm=1 THEN k.name ELSE u.name END) name,(CASE WHEN m.fm=1 THEN k.avatar ELSE u.avatar END) avatar,m.fm mk,m.txt,(m.img!='') img,m.ts,g.cnt "
        "FROM messages m JOIN (SELECT MAX(id) mid,COUNT(*) cnt FROM messages WHERE b=? AND tm=1 GROUP BY a,fm) g ON g.mid=m.id JOIN users u ON u.id=m.a "
        "LEFT JOIN masks k ON k.uid=m.a AND m.fm=1 WHERE (m.fm=0 OR k.id IS NOT NULL) "
        "AND NOT EXISTS(SELECT 1 FROM mreq hr WHERE hr.owner=m.b AND hr.peer=m.a AND hr.pm=m.fm) "
        "AND NOT EXISTS(SELECT 1 FROM messages hy WHERE hy.a=m.b AND hy.fm=1 AND hy.b=m.a AND hy.tm=m.fm) "
        "AND m.a NOT IN (" + _BLOCKED + ") ORDER BY m.id DESC LIMIT 30")

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        i = int(m["id"])
        db = ctx.db
        chats = db.all(self.LAST, (i,) * 16)
        blocked = {int(r[0]) for r in db.query(_BLOCKED, (i, i)).fetchall()}
        streaks = ChatStreaks(db)
        for c in chats:
            uid, ms, mk = int(c["uid"]), int(c["ms"]), int(c["mk"])
            c["cs"] = streaks.direct(i, ms, uid, mk)
            c["st"] = None if (mk or ms) else ("off" if uid in blocked else Presence.state(c))
            # a status line, like the presence dot, never shows in a Masque chat and never for someone you blocked
            c["sx"] = "" if (mk or ms or uid in blocked) else Presence.status_text(c)
            for k in ("uid", "la", "pst", "idl", "stx", "stts"):
                del c[k]
        reqs = db.all(self.REQUESTS, (i, i, i))
        inb = db.value("SELECT inb FROM masks WHERE uid=?", (i,))
        return Reply({"chats": chats, "reqs": reqs, "inb": 1 if inb is None else int(inb)})


@registry.register
class Thread(Action):
    """?a=thread: one chat, the newest 100 messages (or the ones around an old message), its pins and the viewer's own settings for it."""
    name = "thread"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        db, me = ctx.db, int(m["id"])
        found = Counterpart(db)
        ms = 1 if (ctx.arg("as") == "1" and found.own_mask(me)) else 0
        ps, mb = 0, 0
        o = db.one("SELECT id,name,nick,avatar FROM users WHERE name=?", (ctx.arg("u"),))
        if not o:
            k = db.one("SELECT id,uid,name,avatar FROM masks WHERE name=?", (ctx.arg("u"),))
            if k and int(k["uid"]) != me:
                o = {"id": k["uid"], "name": k["name"], "nick": "", "avatar": k["avatar"]}
                ps = 1
                mb = 1 if db.value("SELECT 1 FROM mblocks WHERE a=? AND kid=?", (me, k["id"])) else 0
        if not o:
            return Reply.error("No such user.", 404)
        oid = int(o["id"])
        db.execute("UPDATE messages SET seen=1 WHERE a=? AND fm=? AND b=? AND tm=? AND seen=0", (oid, ps, me, ms))
        clr = int(ctx.dms.state(me, oid, ps, ms)["clr"])
        around = ctx.int_arg("around")
        upto = around + 40 if around > 0 else _MAXINT  # around = open the chat on an older message (search result)
        pair = Pair.args(me, ms, oid, ps)
        rows = db.all("SELECT id,txt,img,ts,ed,seen,rp,pin,(a=?) mine FROM messages WHERE " + Pair.WHERE + " AND id<=? AND id>? ORDER BY id DESC LIMIT 100",
                      (me,) + pair + (upto, clr))
        rows.reverse()
        Decorator(db).apply("d", rows, me)
        pins = [pin_info(r) for r in db.all(
            "SELECT id,txt,img,(a=?) mine FROM messages WHERE pin>0 AND id>? AND " + Pair.WHERE + " ORDER BY pin DESC,id DESC LIMIT %d" % MAX_PINS,
            (me, clr) + pair)]
        pr = db.one("SELECT nick,bg FROM dmpref WHERE uid=? AND oid=? AND ps=?", (me, oid, ps)) or {}
        if ps or ms:
            o["st"] = None
        else:
            o["st"] = "off" if ctx.rel.blocked(me, oid) else Presence.state(db.one("SELECT la,pst,idl FROM users WHERE id=?", (oid,)) or {})
        o["pn"] = str(pr.get("nick") or "")
        o["bg"] = str(pr.get("bg") or "")
        del o["id"]
        o["mk"] = ps
        return Reply({"u": o, "msgs": rows, "as": ms, "mb": mb, "pins": pins, "cs": ChatStreaks(db).direct(me, ms, oid, ps)})


@registry.register
class Typing(Action):
    """?a=typing: "is typing..." for a direct chat (to=<name>) or a group (k=g, gid=<id>); off=1 clears it."""
    name = "typing"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        i, db = int(m["id"]), ctx.db
        ctx.limits.throttle("ty:%d" % i, 50, 60)
        groups = GroupAccess(db)
        if ctx.form("k") == "g":
            g = ctx.int_form("gid")
            if not g or not groups.member(g, i):
                return Reply({"ok": 0})
            as_mask = groups.masque_only(g, i) or (ctx.form("as") == "mask" and db.value("SELECT 1 FROM gmasks WHERE gid=? AND uid=?", (g, i)))
            key = (i, 0, 0, 1 if as_mask else 0, g)
        else:
            found = Counterpart(db)
            ms = found.masque_side(i, ctx.form("as") == "mask")
            oid, ps = found.find(ctx.form("to"), i)
            if not oid or oid == i or (not ps and not ms and ctx.rel.blocked(i, oid)):
                return Reply({"ok": 0})
            key = (i, oid, ms, ps, 0)
        if ctx.flag("off"):
            db.execute("DELETE FROM typing WHERE uid=? AND oid=? AND fm=? AND tm=? AND gid=?", key)
        else:
            db.execute("INSERT INTO typing(uid,oid,fm,tm,gid,ts) VALUES(?,?,?,?,?,?) ON CONFLICT(uid,oid,fm,tm,gid) DO UPDATE SET ts=excluded.ts", key + (ctx.now,))
            db.execute("DELETE FROM typing WHERE ts<?", (ctx.now - 120,))
        return Reply({"ok": 1})


class Delivery:
    """The rules for 'may this sender message that receiver', which differ when a Masque is on either side.
    A Masque never counts friendships or account blocks: that would tell the other person who it is."""

    def __init__(self, ctx: Context, m, o: int, ms: int, ps: int):
        self.ctx, self.db, self.m, self.o, self.ms, self.ps = ctx, ctx.db, m, o, ms, ps

    def _masque_blocked_by(self, receiver: int, sender: int) -> bool:
        return bool(self.db.value("SELECT 1 FROM mblocks WHERE a=? AND kid=(SELECT id FROM masks WHERE uid=?)", (receiver, sender)))

    def check(self):
        ctx, db, me, o = self.ctx, self.db, int(self.m["id"]), self.o
        dm_pref = lambda: db.value("SELECT dm FROM users WHERE id=?", (o,))  # noqa: E731
        if not self.ms and not self.ps:
            if ctx.rel.blocked(me, o):
                ctx.deny("You cannot message this person.", 403)
            if dm_pref() == "friends" and not db.value("SELECT 1 FROM friends WHERE st=1 AND ((a=? AND b=?) OR (a=? AND b=?))", (me, o, o, me)):
                ctx.deny("This person only accepts messages from friends.", 403)
        elif self.ps:
            # anyone can message a Masque from its profile; it lands in the owner's Requests until they accept
            had = db.value("SELECT 1 FROM messages WHERE a=? AND fm=1 AND b=? AND tm=?", (o, me, self.ms))
            if self.ms and self._masque_blocked_by(o, me):
                ctx.deny("You cannot message this Masque.", 403)
            if not had and (str(db.value("SELECT inb FROM masks WHERE uid=?", (o,))) == "0" or dm_pref() == "friends"):
                ctx.deny("This Masque is not accepting new messages.", 403)
        else:
            if dm_pref() == "friends":
                ctx.deny("This person only accepts messages from friends.", 403)
            if self._masque_blocked_by(o, me):
                ctx.deny("You cannot message this person.", 403)


@registry.register
class Send(Action):
    """?a=send: a message with optional picture/audio, as the real account or (as=mask) as the sender's Masque."""
    name = "send"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        ctx.limits.lim("dm:%d" % me, 40, 60, m, 15, 60)
        t = _text(ctx)
        ctx.media.check_sticker(m, t)
        ctx.media.check_game_invite(m, t)
        found = Counterpart(db)
        ms = 1 if ctx.form("as") == "mask" else 0
        if ms and not found.own_mask(me):
            return Reply.error("You do not have a Masque.", 400)
        o, ps = found.find(ctx.form("to"), me, self_mask_ok=True)
        if not o:
            return Reply.error("No such user.", 404)
        if o == me:
            return Reply.error("You cannot message yourself.", 400)
        upload = ctx.file("img")
        if t == "" and upload is None:
            return Reply.error("Write something first.", 400)
        Delivery(ctx, m, o, ms, ps).check()
        rp = ctx.int_form("rp")
        if rp > 0 and not db.value("SELECT 1 FROM messages WHERE id=? AND " + Pair.WHERE, (rp,) + Pair.args(me, ms, o, ps)):
            return Reply.error("The message you are replying to is gone.", 400)
        img = ctx.media.save_attachment(upload, m)
        db.execute("INSERT INTO messages(a,b,txt,ts,img,fm,tm,rp) VALUES(?,?,?,?,?,?,?,?)", (me, o, t, ctx.now, img, ms, ps, max(0, rp)))
        db.execute("DELETE FROM typing WHERE uid=? AND oid=? AND fm=? AND tm=? AND gid=0", (me, o, ms, ps))
        if int(ctx.notes.prefs.get(o)["pop"]) and (ms or ps or not ctx.rel.blocked(o, me)):
            ctx.notes.push(o, "Masque", "You have a new message", "./", "dm", 60)
        return Reply({"ok": 1})


@registry.register
class MessageSearch(Action):
    """?a=msearch: words inside one chat (newest 40 hits), hiding what the viewer deleted for themselves."""
    name = "msearch"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        i, db = int(m["id"]), ctx.db
        ctx.limits.throttle("ms:%d" % i, 40, 60)
        q = php_trim(ctx.arg("q")[:60])
        if len(q) < 2:
            return Reply({"res": []})
        found = Counterpart(db)
        ms = found.masque_side(i, ctx.arg("as") == "1")
        oid, ps = found.find(ctx.arg("u"), i)
        if not oid:
            return Reply.error("No such user.", 404)
        clr = int(ctx.dms.state(i, oid, ps, ms)["clr"])
        like = "%" + like_escape(q) + "%"
        rows = db.all("SELECT id,txt,ts,(a=?) mine FROM messages WHERE " + Pair.WHERE + " AND id>? AND txt LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT 40",
                      (i,) + Pair.args(i, ms, oid, ps) + (clr, like))
        return Reply({"res": rows})


@registry.register
class EditMessage(Action):
    name = "editm"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        ctx.limits.lim("em:%d" % me, 30, 600, m, 10, 600)
        mid = ctx.int_form("id")
        t = _text(ctx)
        old = db.value("SELECT txt FROM messages WHERE id=? AND a=?", (mid, me)) or ""
        if GameInvite.is_invite(t) or GameInvite.is_invite(old):
            return Reply.error("A game invite cannot be edited. Delete it and send a new one.", 400)
        if t == "" and not db.value("SELECT img FROM messages WHERE id=? AND a=?", (mid, me)):
            return Reply.error("A message cannot be empty. Delete it instead.", 400)
        now = ctx.now
        if db.execute("UPDATE messages SET txt=?,ed=? WHERE id=? AND a=?", (t, now, mid, me)) == 0:
            return Reply.error("Message not found.", 404)
        return Reply({"txt": t, "ed": now})


@registry.register
class DeleteMessage(Action):
    name = "delm"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        mid = ctx.int_form("id")
        img = db.value("SELECT img FROM messages WHERE id=? AND a=?", (mid, me))
        if db.execute("DELETE FROM messages WHERE id=? AND a=?", (mid, me)):
            db.execute("DELETE FROM mreact WHERE k='d' AND mid=?", (mid,))
        if img:
            ctx.media.remove([img])  # only names this site would have made are ever deleted
        return Reply({"ok": 1})


@registry.register
class React(Action):
    """?a=react: put (or take back) one emoji on a message in a direct chat. (greact, the group twin, comes with the groups.)"""
    name = "react"
    kind = "d"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        ctx.limits.throttle("rx:%d" % me, 120, 60)
        mid = ctx.int_form("id")
        e = ctx.form("e")
        if e != "" and e not in REACTS:
            return Reply.error("Unknown reaction.", 400)
        r = db.one("SELECT a,b,fm,tm FROM messages WHERE id=? AND (a=? OR b=?)", (mid, me, me))
        if not r:
            return Reply.error("Message not found.", 404)
        if not int(r["fm"]) and not int(r["tm"]) and ctx.rel.blocked(me, int(r["b"]) if int(r["a"]) == me else int(r["a"])):
            return Reply.error("You cannot react to this message.", 403)
        cur = db.value("SELECT e FROM mreact WHERE k=? AND mid=? AND uid=?", (self.kind, mid, me))
        if e == "" or e == cur:
            db.execute("DELETE FROM mreact WHERE k=? AND mid=? AND uid=?", (self.kind, mid, me))
        else:
            db.execute("INSERT INTO mreact(k,mid,uid,e) VALUES(?,?,?,?) ON CONFLICT(k,mid,uid) DO UPDATE SET e=excluded.e", (self.kind, mid, me, e))
        rows = [{"id": mid, "rp": 0}]
        Decorator(db).apply(self.kind, rows, me)
        return Reply({"rx": rows[0]["rx"]})


@registry.register
class ReactionWho(Action):
    """?a=rxwho: who reacted to a group message. A member who is only here as their Masque is listed by the Masque (same rule as "Seen by"),
    so a reaction never shows a real account the group is not meant to see. Direct chats are drawn in the browser."""
    name = "rxwho"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        ctx.limits.throttle("rw:%d" % me, 120, 60)
        mid = ctx.int_arg("id")
        gid = db.value("SELECT gid FROM gmessages WHERE id=?", (mid,))
        if gid is None or not GroupAccess(db).member(int(gid), me):
            return Reply.error("Message not found.", 404)
        by = {}
        for x in db.all(
                "SELECT x.e,x.uid,mb.uid mbu,mb.pm,COALESCE(NULLIF(u.nick,''),u.name) un,u.avatar ua,k.name kn,k.avatar ka FROM mreact x JOIN users u ON u.id=x.uid "
                "LEFT JOIN gmembers mb ON mb.gid=? AND mb.uid=x.uid LEFT JOIN masks k ON k.uid=x.uid WHERE x.k='g' AND x.mid=? "
                "AND (mb.pm=1 OR x.uid NOT IN (" + _BLOCKED + ")) ORDER BY x.rowid", (int(gid), mid, me, me)):
            masque = int(x["pm"] or 0) == 1
            gone = x["mbu"] is None
            by.setdefault(x["e"], []).append({
                "name": "Former member" if gone else ((x["kn"] or "Masque") if masque else x["un"]),
                "avatar": "" if gone else str((x["ka"] or "") if masque else x["ua"]),
                "mk": 1 if masque else 0,
                "me": 1 if int(x["uid"]) == me else 0,
            })
        out = [{"e": e, "w": w} for e, w in by.items()]
        out.sort(key=lambda o: -len(o["w"]))  # stable, like PHP 8's usort
        return Reply({"rx": out})


@registry.register
class PinMessage(Action):
    """?a=pinm: pin or unpin a message in a direct chat (up to 5 per chat). (gpin, the group twin, comes with the groups.)"""
    name = "pinm"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        ctx.limits.throttle("pn:%d" % me, 60, 60)
        mid = ctx.int_form("id")
        r = db.one("SELECT a,b,fm,tm,pin FROM messages WHERE id=? AND (a=? OR b=?)", (mid, me, me))
        if not r:
            return Reply.error("Message not found.", 404)
        if not int(r["fm"]) and not int(r["tm"]) and ctx.rel.blocked(me, int(r["b"]) if int(r["a"]) == me else int(r["a"])):
            return Reply.error("You cannot change this chat.", 403)
        n = int(db.value(
            "SELECT COUNT(*) FROM messages WHERE pin>0 AND ((a=? AND b=? AND fm=? AND tm=?) OR (a=? AND b=? AND fm=? AND tm=?))",
            (r["a"], r["b"], r["fm"], r["tm"], r["b"], r["a"], r["tm"], r["fm"]), 0))
        new = 0 if int(r["pin"]) > 0 else ctx.now
        if new and n >= MAX_PINS:
            return Reply.error("You can pin up to %d messages. Unpin one first." % MAX_PINS, 400)
        db.execute("UPDATE messages SET pin=? WHERE id=?", (new, mid))
        return Reply({"pin": new})


@registry.register
class SetNickname(Action):
    """?a=setpn: a private nickname for the other person (only you see it)."""
    name = "setpn"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ps = 1 if ctx.flag("mk") else 0
        nick = php_trim(collapse_space(ctx.form("nick")[:32]))
        oid = Peer(ctx, m, ctx.form("u"), ps).need()
        ctx.dms.set_pref(int(m["id"]), oid, ps, "nick", nick)
        return Reply({"pn": nick})


@registry.register
class SetBackground(Action):
    """?a=setbg: a chat background that only you see. The Castle Night ones can only be kept, not newly picked, once the event is over."""
    name = "setbg"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me = int(m["id"])
        ps = 1 if ctx.flag("mk") else 0
        bg = ctx.form("bg")
        if bg != "" and bg not in BACKGROUNDS:
            return Reply.error("Unknown background.", 400)
        oid = Peer(ctx, m, ctx.form("u"), ps).need()
        if bg in EVENT_BACKGROUNDS and not ctx.unlocks.event_on() and not m["admin"]:
            current = str(ctx.db.value("SELECT bg FROM dmpref WHERE uid=? AND oid=? AND ps=?", (me, oid, ps)) or "")
            if bg != current:
                return Reply.error("Castle Night has ended, so this is not available any more.", 403)
        ctx.dms.set_pref(me, oid, ps, "bg", bg)
        return Reply({"bg": bg})


@registry.register
class MessageRequest(Action):
    """?a=mreq: accept (act=accept) or decline a Masque message request."""
    name = "mreq"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me = int(m["id"])
        pm = 1 if ctx.flag("pm") else 0
        pid = ctx.dms.other(ctx.form("u"), pm)
        if not pid:
            return Reply.error("No such user.", 404)
        if not ctx.db.value("SELECT 1 FROM messages WHERE a=? AND b=? AND fm=? AND tm=1", (pid, me, pm)):
            return Reply.error("No such request.", 404)
        ctx.db.execute("INSERT OR REPLACE INTO mreq(owner,peer,pm,st) VALUES(?,?,?,?)", (me, pid, pm, 1 if ctx.form("act") == "accept" else 2))
        return Reply({"ok": 1})
