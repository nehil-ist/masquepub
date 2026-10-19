"""Chat rooms (PHP: case 'rlist', 'rcreate', 'rthread', 'rsend', 'rclose', 'rvote', 'rdelmsg')."""
from ..php import collapse_space, php_trim
from ..rooms import ACTIVE_SECONDS, BLOCKED_MASQUE_OWNERS, DEFAULT_SECONDS, DURATIONS, MAX_OPEN, THEMES, Rooms
from .base import Action, Context, Reply, registry


@registry.register
class RoomList(Action):
    """?a=rlist: open rooms, busiest first (not those made by a Masque I blocked)."""
    name = "rlist"
    SQL = ("SELECT r.id,r.name,r.theme,r.exp,r.ts,(r.owner=?) own,(SELECT COUNT(*) FROM rpres p WHERE p.rid=r.id AND p.ts>?) here,"
           "(SELECT COUNT(*) FROM rmsgs x WHERE x.rid=r.id) n FROM rooms r WHERE r.closed=0 AND r.exp>? AND r.owner NOT IN (" + BLOCKED_MASQUE_OWNERS + ") "
           "ORDER BY here DESC,r.ts DESC LIMIT 40")

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        Rooms(ctx.db).sweep()
        now = ctx.now
        return Reply({"rooms": ctx.db.all(self.SQL, (m["id"], now - ACTIVE_SECONDS, now, m["id"])), "now": now})


@registry.register
class RoomCreate(Action):
    """?a=rcreate: open a room (Masques only; 1, 6 or 24 hours; at most 2 open per person)."""
    name = "rcreate"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, rooms = int(m["id"]), ctx.db, Rooms(ctx.db)
        if not rooms.has_masque(me):
            return Reply.error("Create your Masque first. Rooms are for Masques only.", 400)
        ctx.limits.lim("rc:%d" % me, 3, 3600, m, 1, 3600)
        rooms.sweep()
        n = php_trim(collapse_space(ctx.form("name"))[:40])
        if n == "":
            return Reply.error("Give the room a name.", 400)
        if not m["admin"] and ctx.words.match(n):
            return Reply.error("That name is not allowed.", 400)
        th = ctx.form("theme", "midnight")
        if th not in THEMES:
            th = "midnight"
        dur = DURATIONS.get(ctx.int_form("hrs", 24), DEFAULT_SECONDS)
        now = ctx.now
        if not m["admin"] and int(db.value("SELECT COUNT(*) FROM rooms WHERE owner=? AND closed=0 AND exp>?", (me, now), 0)) >= MAX_OPEN:
            return Reply.error("You already have 2 open rooms. Close one first.", 400)
        rid = db.query("INSERT INTO rooms(name,theme,owner,ts,exp) VALUES(?,?,?,?,?)", (n, th, me, now, now + dur)).lastrowid
        return Reply({"id": rid})


@registry.register
class RoomThread(Action):
    """?a=rthread: one room: the newest messages after `after`, what is still in it (so deleted ones vanish), and who is here."""
    name = "rthread"
    ROOM = "SELECT id,name,theme,exp,ts,(owner=?) own FROM rooms WHERE id=? AND closed=0 AND exp>?"
    MSGS = ("SELECT x.id,x.txt,x.ts,(x.uid=?) mine,(SELECT COUNT(*) FROM rvotes v WHERE v.mid=x.id AND v.v=1) up,"
            "COALESCE((SELECT v FROM rvotes v WHERE v.mid=x.id AND v.uid=?),0) mv,COALESCE(k.name,'Masque') name,COALESCE(k.avatar,'') avatar "
            "FROM rmsgs x LEFT JOIN masks k ON k.uid=x.uid WHERE x.rid=? AND x.id>? AND x.uid NOT IN (" + BLOCKED_MASQUE_OWNERS + ") ORDER BY x.id DESC LIMIT 80")
    LIVE = ("SELECT x.id,(SELECT COUNT(*) FROM rvotes v WHERE v.mid=x.id AND v.v=1) up,COALESCE((SELECT v FROM rvotes v WHERE v.mid=x.id AND v.uid=?),0) mv "
            "FROM rmsgs x WHERE x.rid=? ORDER BY x.id DESC LIMIT 80")
    HERE = ("SELECT COALESCE(k.name,'Masque') name,COALESCE(k.avatar,'') avatar FROM rpres p LEFT JOIN masks k ON k.uid=p.uid "
            "WHERE p.rid=? AND p.ts>? AND p.uid NOT IN (" + BLOCKED_MASQUE_OWNERS + ") ORDER BY p.ts DESC LIMIT 30")

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, rooms = int(m["id"]), ctx.db, Rooms(ctx.db)
        rooms.sweep()
        rid, now = ctx.int_arg("id"), ctx.now
        r = db.one(self.ROOM, (me, rid, now))
        if not r:
            return Reply.error("This room has closed.", 404)
        has = rooms.has_masque(me)
        if has:
            rooms.seen(rid, me, now)
        msgs = list(reversed(db.all(self.MSGS, (me, me, rid, ctx.int_arg("after"), me))))
        return Reply({"room": r, "msgs": msgs, "live": db.all(self.LIVE, (me, rid)),
                      "here": db.all(self.HERE, (rid, now - ACTIVE_SECONDS, me)), "has": 1 if has else 0, "now": now})


@registry.register
class RoomSend(Action):
    """?a=rsend: write in a room, as my Masque."""
    name = "rsend"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, rooms = int(m["id"]), ctx.db, Rooms(ctx.db)
        ctx.limits.lim("rm:%d" % me, 40, 60, m, 15, 60)
        rid = ctx.int_form("id")
        t = php_trim(ctx.form("txt")[:300])
        if t == "":
            return Reply.error("Write something first.", 400)
        if not rooms.has_masque(me):
            return Reply.error("Create your Masque first.", 400)
        now = ctx.now
        if not rooms.is_open(rid, now):
            return Reply.error("This room has closed.", 404)
        ctx.limits.nolinks(m, t)
        if not m["admin"] and ctx.words.match(t):
            return Reply.error("That message cannot be sent.", 400)
        mid = db.query("INSERT INTO rmsgs(rid,uid,txt,ts) VALUES(?,?,?,?)", (rid, me, t, now)).lastrowid
        rooms.seen(rid, me, now)
        return Reply({"id": mid})


@registry.register
class RoomClose(Action):
    """?a=rclose: the owner (or an admin) closes a room; its messages are deleted."""
    name = "rclose"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        rid = ctx.int_form("id")
        r = ctx.db.one("SELECT owner FROM rooms WHERE id=?", (rid,))
        if not r or (int(r["owner"]) != int(m["id"]) and not m["admin"]):
            return Reply.error("Not allowed.", 403)
        ctx.db.execute("UPDATE rooms SET closed=1 WHERE id=?", (rid,))
        Rooms(ctx.db).sweep()
        return Reply({"ok": 1})


@registry.register
class RoomVote(Action):
    """?a=rvote: mark (+1) or downvote (-1) a room message, 0 takes the vote back. Counts toward the writer's Masque reputation; nobody is told who voted."""
    name = "rvote"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, rooms = int(m["id"]), ctx.db, Rooms(ctx.db)
        ctx.limits.lim("rv:%d" % me, 60, 60, m, 20, 60)
        if not rooms.has_masque(me):
            return Reply.error("Create your Masque to vote.", 400)
        mid = ctx.int_form("id")
        raw = ctx.int_form("v")
        v = 1 if raw > 0 else (-1 if raw < 0 else 0)
        x = db.one("SELECT x.uid FROM rmsgs x JOIN rooms r ON r.id=x.rid WHERE x.id=? AND r.closed=0 AND r.exp>?", (mid, ctx.now))
        if not x:
            return Reply.error("That message is gone.", 404)
        author = int(x["uid"])
        if author == me:
            return Reply.error("You can't vote on your own message.", 400)
        if db.value("SELECT 1 FROM mblocks b JOIN masks k ON k.id=b.kid WHERE b.a=? AND k.uid=?", (me, author)):
            return Reply.error("Not allowed.", 403)
        return Reply({"ok": 1, "up": rooms.vote(mid, me, author, v), "mv": v})


@registry.register
class RoomDeleteMessage(Action):
    """?a=rdelmsg: the writer, the room's owner or an admin deletes one room message."""
    name = "rdelmsg"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        mid = ctx.int_form("id")
        x = ctx.db.one("SELECT x.uid,r.owner FROM rmsgs x JOIN rooms r ON r.id=x.rid WHERE x.id=?", (mid,))
        me = int(m["id"])
        if not x or (int(x["uid"]) != me and int(x["owner"]) != me and not m["admin"]):
            return Reply.error("Not allowed.", 403)
        ctx.db.execute("DELETE FROM rvotes WHERE mid=?", (mid,))
        ctx.db.execute("DELETE FROM rmsgs WHERE id=?", (mid,))
        return Reply({"ok": 1})
