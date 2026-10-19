"""People: profile pages, follows, friends, blocks and search (PHP: case 'user', 'fol', 'unfol', 'flist', 'ufriends', 'friends', 'here', 'find', 'fadd', 'facc', 'frem', 'block', 'unblock')."""
import time

from ..php import like_escape, php_trim
from ..config import ascii_lower
from ..presence import AWAY, Presence
from .base import Action, Context, Reply, registry


class Roster:
    """Shared by the actions that list people: the other person by name, and the 'who do I already follow / befriend' sets."""

    def __init__(self, ctx: Context):
        self.ctx, self.db = ctx, ctx.db

    def id_of(self, name):
        o = self.db.value("SELECT id FROM users WHERE name=?", (name,))
        return int(o) if o else 0

    def following(self, uid) -> set:
        return {int(r["b"]) for r in self.db.all("SELECT b FROM follows WHERE a=?", (uid,))}

    def friend_ids(self, uid) -> set:
        return {int(r[0]) for r in self.db.query("SELECT CASE WHEN a=? THEN b ELSE a END FROM friends WHERE st=1 AND (a=? OR b=?)", (uid, uid, uid)).fetchall()}

    def target(self, name, viewer_id):
        """A user row (id, priv) the viewer may look at, or None when missing or blocked either way."""
        t = self.db.one("SELECT id,priv FROM users WHERE name=?", (name,))
        if not t or self.ctx.rel.blocked(viewer_id, int(t["id"])):
            return None
        return t


@registry.register
class UserProfile(Action):
    """?a=user: one public profile, as the viewer (signed in or not) may see it."""
    name = "user"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        u = db.one("SELECT id,name,nick,bio,avatar,cy,cover,dm,priv,askon,askp,tbg,tbp,tcd,tfn,tas,taf,tcf,tpl,stx,stts FROM users WHERE name=?", (ctx.arg("u"),))
        if not u:
            return Reply.error("No such user.", 404)
        uid = int(u["id"])
        v = ctx.users.me()
        own = bool(v) and int(v["id"]) == uid
        pw = " WHERE mid=0 AND uid=?" + ("" if own else " AND anon=0 AND hold=0 AND vis" + ("<=1" if v and ctx.rel.friends(v["id"], uid) else "=0"))
        u["posts"] = int(db.value("SELECT COUNT(*) FROM posts" + pw + " AND NOT (pd=0 AND COALESCE(aq,'')!='')", (uid,), 0))
        u["qs"] = int(db.value("SELECT COUNT(*) FROM posts" + pw + " AND pd=0 AND COALESCE(aq,'')!=''", (uid,), 0))
        u["friends"] = int(db.value("SELECT COUNT(*) FROM friends WHERE st=1 AND (a=? OR b=?)", (uid, uid), 0))
        u["followers"] = int(db.value("SELECT COUNT(*) FROM follows WHERE b=?", (uid,), 0))
        u["following"] = int(db.value("SELECT COUNT(*) FROM follows WHERE a=?", (uid,), 0))
        u["fol"] = 0
        u["rel"] = "none"
        if v:
            r = db.one("SELECT a,st FROM friends WHERE (a=? AND b=?) OR (a=? AND b=?)", (v["id"], uid, uid, v["id"]))
            if r:
                u["rel"] = "friends" if r["st"] else ("sent" if int(r["a"]) == int(v["id"]) else "got")
            u["fol"] = int(db.value("SELECT COUNT(*) FROM follows WHERE a=? AND b=?", (v["id"], uid), 0))
        u["blocked"] = 0
        if v:
            if db.value("SELECT 1 FROM blocks WHERE a=? AND b=?", (uid, v["id"])):
                return Reply.error("No such user.", 404)
            u["blocked"] = int(db.value("SELECT COUNT(*) FROM blocks WHERE a=? AND b=?", (v["id"], uid), 0))
        u["locked"] = int(bool(int(u["priv"])) and (not v or (int(v["id"]) != uid and u["rel"] != "friends")))
        if own:
            u["asks"] = int(db.value("SELECT COUNT(*) FROM asks WHERE uid=? AND hid=0", (uid,), 0))
        now = int(time.time())
        # the status line is shown for 24 hours after it was set, then it is simply gone
        live = int(u["stts"]) > now - 86400 and str(u["stx"] or "") != ""
        u["status"] = str(u["stx"]) if live else ""
        u["stleft"] = max(60, int(u["stts"]) + 86400 - now) if u["status"] != "" else 0
        # the streak flame: you and your friends see it
        if v and (own or u["rel"] == "friends"):
            sc = ctx.streaks.calc(uid)
            if sc["cur"] > 0:
                u["streak"] = {"n": sc["cur"], "icy": sc["icy"]}
        for k in ("stx", "stts", "id"):
            u.pop(k, None)
        return Reply({"u": u})


@registry.register
class Follow(Action):
    """?a=fol: follow one way, no approval, public accounts only (private accounts take friend requests)."""
    name = "fol"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.lim("fo:%d" % m["id"], 60, 3600, m, 30, 3600)
        t = ctx.db.one("SELECT id,priv FROM users WHERE name=?", (ctx.form("to"),))
        if not t:
            return Reply.error("No such user.", 404)
        if int(t["id"]) == int(m["id"]):
            return Reply.error("You cannot follow yourself.", 400)
        if ctx.rel.blocked(m["id"], int(t["id"])):
            return Reply.error("You cannot follow this person.", 403)
        if int(t["priv"]):
            return Reply.error("Private accounts take friend requests, not follows.", 403)
        if ctx.db.execute("INSERT OR IGNORE INTO follows(a,b,ts) VALUES(?,?,?)", (m["id"], t["id"], ctx.now)):
            ctx.notes.note(int(t["id"]), "follow", int(m["id"]))
        return Reply({"ok": 1})


@registry.register
class Unfollow(Action):
    name = "unfol"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        o = Roster(ctx).id_of(ctx.form("to"))
        if o:
            ctx.db.execute("DELETE FROM follows WHERE a=? AND b=?", (m["id"], o))
        return Reply({"ok": 1})


@registry.register
class FollowList(Action):
    """?a=flist: followers or following of a public profile. Nobody blocked either way is listed; 'fy' says whether YOU follow them."""
    name = "flist"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        i = int(m["id"])
        ros = Roster(ctx)
        t = ros.target(ctx.arg("u"), i)
        if not t:
            return Reply.error("No such user.", 404)
        ti = int(t["id"])
        if int(t["priv"]) and ti != i:
            return Reply.error("This account is private.", 403)
        mine = ros.following(i)
        if ctx.arg("k") == "following":
            sql = "SELECT u.id,u.name,u.nick,u.avatar FROM follows f JOIN users u ON u.id=f.b WHERE f.a=? AND u.priv=0 ORDER BY f.ts DESC LIMIT 300"
        else:
            sql = "SELECT u.id,u.name,u.nick,u.avatar FROM follows f JOIN users u ON u.id=f.a WHERE f.b=? ORDER BY f.ts DESC LIMIT 300"
        out = []
        for r in ctx.db.all(sql, (ti,)):
            ui = int(r["id"])
            if ui != i and ctx.rel.blocked(i, ui):
                continue
            out.append({"name": r["name"], "nick": r["nick"], "avatar": r["avatar"], "fy": 1 if ui in mine else 0, "you": 1 if ui == i else 0})
        return Reply({"list": out})


@registry.register
class UserFriends(Action):
    """?a=ufriends: someone's friends for their profile. Private accounts only show it to their own friends; 'mu' = also YOUR friend."""
    name = "ufriends"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        i = int(m["id"])
        ros = Roster(ctx)
        t = ros.target(ctx.arg("u"), i)
        if not t:
            return Reply.error("No such user.", 404)
        ti = int(t["id"])
        me_self = ti == i
        if int(t["priv"]) and not me_self and not ctx.rel.friends(i, ti):
            return Reply.error("Only friends can see the friends of a private account.", 403)
        mine = ros.friend_ids(i)
        out, mutual = [], 0
        for r in ctx.db.all("SELECT u.id,u.name,u.nick,u.avatar FROM friends f JOIN users u ON u.id=(CASE WHEN f.a=? THEN f.b ELSE f.a END) "
                            "WHERE f.st=1 AND (f.a=? OR f.b=?) ORDER BY f.ts DESC LIMIT 300", (ti, ti, ti)):
            ui = int(r["id"])
            you = ui == i
            if not you and ctx.rel.blocked(i, ui):
                continue
            mu = 1 if (not you and not me_self and ui in mine) else 0
            mutual += mu
            out.append({"name": r["name"], "nick": r["nick"], "avatar": r["avatar"], "mu": mu, "you": 1 if you else 0})
        out.sort(key=lambda x: (-x["you"], -x["mu"]))  # you first, then mutual friends, then the rest newest first (the sort is stable)
        return Reply({"list": out, "mutual": mutual, "self": 1 if me_self else 0})


@registry.register
class Friends(Action):
    """?a=friends: my friends and my pending requests."""
    name = "friends"

    def handle(self, ctx: Context) -> Reply:
        i = ctx.users.need()["id"]
        return Reply({"list": ctx.db.all(
            "SELECT u.name,u.nick,u.avatar,f.st,f.ts,(f.a=?) mine FROM friends f JOIN users u ON u.id=(CASE WHEN f.a=? THEN f.b ELSE f.a END) "
            "WHERE f.a=? OR f.b=? ORDER BY f.ts DESC LIMIT 300", (i, i, i, i))})


@registry.register
class Here(Action):
    """?a=here: friends online right now (Home 'Here now'): accepted friends only, nobody invisible, nobody blocked either way."""
    name = "here"

    def handle(self, ctx: Context) -> Reply:
        i = int(ctx.users.need()["id"])
        out = []
        for r in ctx.db.all("SELECT u.id,u.name,u.nick,u.avatar,u.la,u.pst,u.idl,u.stx,u.stts FROM friends f JOIN users u ON u.id=(CASE WHEN f.a=? THEN f.b ELSE f.a END) "
                            "WHERE f.st=1 AND (f.a=? OR f.b=?) AND u.la>? ORDER BY u.la DESC LIMIT 60", (i, i, i, int(time.time()) - AWAY)):
            if ctx.rel.blocked(i, int(r["id"])):
                continue
            st = Presence.state(r)
            if st == "off":
                continue
            out.append({"name": r["name"], "nick": r["nick"], "avatar": r["avatar"], "st": st, "sx": Presence.status_text(r)})
        out.sort(key=lambda x: x["st"] == "idle")  # online first, then idle; each group stays most-recent-first
        return Reply({"list": out[:24]})


@registry.register
class Find(Action):
    """?a=find: people (and, with tg, hashtags) matching what was typed."""
    name = "find"

    def handle(self, ctx: Context) -> Reply:
        ctx.users.need()
        s = like_escape(php_trim(ctx.arg("q")).lstrip("#@"))
        if s == "":
            return Reply({"users": [], "tags": []})
        out = {"users": ctx.db.all(
            "SELECT name,nick,avatar FROM users WHERE (name LIKE ? ESCAPE '\\' OR nick LIKE ? ESCAPE '\\') "
            "ORDER BY (name LIKE ? ESCAPE '\\' OR nick LIKE ? ESCAPE '\\') DESC,name LIMIT 10", ("%" + s + "%", "%" + s + "%", s + "%", s + "%"))}
        if ctx.qflag("tg"):
            low = ascii_lower(s)
            out["tags"] = ctx.db.all(
                "SELECT t.tag,COUNT(*) n FROM posttags t JOIN posts p ON p.id=t.pid JOIN users u ON u.id=p.uid "
                "WHERE u.priv=0 AND p.vis=0 AND p.hold=0 AND t.tag LIKE ? ESCAPE '\\' GROUP BY t.tag "
                "ORDER BY (t.tag LIKE ? ESCAPE '\\') DESC,n DESC,t.tag LIMIT 6", ("%" + low + "%", low + "%"))
        return Reply(out)


@registry.register
class FriendRequest(Action):
    """?a=fadd: send a friend request, or accept one that is waiting for me."""
    name = "fadd"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        ctx.limits.lim("fr:%d" % m["id"], 30, 3600, m, 10, 3600)
        o = Roster(ctx).id_of(ctx.form("to"))
        if not o:
            return Reply.error("No such user.", 404)
        if o == int(m["id"]):
            return Reply.error("You cannot friend yourself.", 400)
        if ctx.rel.blocked(m["id"], o):
            return Reply.error("You cannot friend this person.", 403)
        r = db.one("SELECT a,st FROM friends WHERE (a=? AND b=?) OR (a=? AND b=?)", (m["id"], o, o, m["id"]))
        if not r:
            db.execute("INSERT INTO friends(a,b,st,ts) VALUES(?,?,0,?)", (m["id"], o, ctx.now))
            ctx.notes.note(o, "freq", m["id"])
        elif not r["st"] and int(r["a"]) == o:
            db.execute("UPDATE friends SET st=1,ts=? WHERE a=? AND b=?", (ctx.now, o, m["id"]))
            ctx.notes.note(o, "facc", m["id"])
        return Reply({"ok": 1})


@registry.register
class FriendAccept(Action):
    name = "facc"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        o = Roster(ctx).id_of(ctx.form("to"))
        if o and ctx.db.execute("UPDATE friends SET st=1,ts=? WHERE a=? AND b=? AND st=0", (ctx.now, o, m["id"])):
            ctx.notes.note(o, "facc", m["id"])
        return Reply({"ok": 1})


@registry.register
class FriendRemove(Action):
    """?a=frem: unfriend, or cancel / decline a request."""
    name = "frem"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        o = Roster(ctx).id_of(ctx.form("to"))
        if o:
            ctx.db.execute("DELETE FROM friends WHERE (a=? AND b=?) OR (a=? AND b=?)", (m["id"], o, o, m["id"]))
        return Reply({"ok": 1})


@registry.register
class Block(Action):
    """?a=block: also removes the friendship, follows and any waiting questions between us."""
    name = "block"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        o = Roster(ctx).id_of(ctx.form("to"))
        if not o:
            return Reply.error("No such user.", 404)
        if o == int(m["id"]):
            return Reply.error("You cannot block yourself.", 400)
        pair = (m["id"], o, o, m["id"])
        db.execute("INSERT OR IGNORE INTO blocks VALUES(?,?)", (m["id"], o))
        db.execute("DELETE FROM asks WHERE hid=0 AND ((uid=? AND frm=?) OR (uid=? AND frm=?))", pair)
        db.execute("DELETE FROM friends WHERE (a=? AND b=?) OR (a=? AND b=?)", pair)
        db.execute("DELETE FROM follows WHERE (a=? AND b=?) OR (a=? AND b=?)", pair)
        return Reply({"ok": 1})


@registry.register
class Unblock(Action):
    name = "unblock"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        o = Roster(ctx).id_of(ctx.form("to"))
        if o:
            ctx.db.execute("DELETE FROM blocks WHERE a=? AND b=?", (m["id"], o))
        return Reply({"ok": 1})
