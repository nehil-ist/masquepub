"""Group chats, part 2 (PHP: case 'gaddmask', 'gmaskme', 'gremove', 'gleave', 'grename', 'gicon', 'gsetbg', 'gmute', 'ginv', 'gacc',
'glink', 'glinkinfo', 'gjoin', 'gsearch', 'gpin', 'greact').

Same rules as part 1: members are (user id, pm) rows, pm=1 = only here as their Masque.
"""
import re
import secrets

from ..chatview import BACKGROUNDS, EVENT_BACKGROUNDS, MAX_PINS, REACTS, Decorator
from ..groupchat import MAX_PEOPLE, Groups, Membership
from ..php import like_escape, php_trim
from ..tidy import Tidy
from .base import Action, Context, Reply, registry

_BLOCKED = "SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?"
_NO_GROUP = "No such group."


class GroupAction(Action):
    """Base for group actions: signed in, group id from the form, must be a member."""

    def member_of(self, ctx: Context, name: str = "gid"):
        """(me row, my id, group id, Groups); stops with 404 when the person is not in the group."""
        m = ctx.users.need()
        me, g = int(m["id"]), ctx.int_form(name)
        groups = Groups(ctx.db)
        if not groups.member(g, me):
            ctx.deny(_NO_GROUP, 404)
        return m, me, g, groups


@registry.register
class GroupInviteMasque(GroupAction):
    """?a=gaddmask: invite somebody's Masque by name; the invite reaches its owner and nobody in the group learns who that is."""
    name = "gaddmask"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, groups = int(m["id"]), ctx.db, Groups(ctx.db)
        ctx.limits.lim("ga:%d" % me, 0, 0, m, 5, 3600)
        g = ctx.int_form("gid")
        if not groups.member(g, me):
            return Reply.error(_NO_GROUP, 404)
        k = db.one("SELECT id,uid FROM masks WHERE name=?", (php_trim(ctx.form("name")),))
        if not k:
            return Reply.error("There is no Masque with that name.", 404)
        u = int(k["uid"])
        if u == me:
            return Reply.error("That is your own Masque. Use Add my Masque instead.", 400)
        if db.value("SELECT 1 FROM gmasks WHERE gid=? AND uid=?", (g, u)):
            return Reply.error("That Masque is already in this group.", 400)
        if ctx.rel.blocked(me, u) or groups.blocked_with_member(g, u):
            return Reply({"added": 1})  # looks like a sent invite, so it cannot be used to find out who owns a Masque
        if groups.count(g) + int(db.value("SELECT COUNT(*) FROM ginvites WHERE gid=?", (g,), 0)) >= MAX_PEOPLE:
            return Reply.error("This group is full.", 400)
        if db.value("SELECT 1 FROM ginvites WHERE gid=? AND uid=?", (g, u)):
            return Reply.error("That Masque already has an invite.", 400)
        db.execute("INSERT INTO ginvites(gid,uid,inv,ts,pm) VALUES(?,?,?,?,1)", (g, u, me, ctx.now))
        groups.event(g, me, "invite", u, "", 0, 1, now=ctx.now)
        return Reply({"added": 1})


@registry.register
class GroupMaskMe(GroupAction):
    """?a=gmaskme: my own Masque joins (on=1) or leaves a group I am in; nobody is told they are the same person."""
    name = "gmaskme"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, groups = int(m["id"]), ctx.db, Groups(ctx.db)
        ctx.limits.throttle("gk:%d" % me, 30, 3600)
        g = ctx.int_form("gid")
        if not groups.member(g, me):
            return Reply.error(_NO_GROUP, 404)
        if not db.value("SELECT 1 FROM masks WHERE uid=?", (me,)):
            return Reply.error("Create your Masque first.", 400)
        has = bool(db.value("SELECT 1 FROM gmasks WHERE gid=? AND uid=?", (g, me)))
        if ctx.flag("on"):
            if has:
                return Reply({"ok": 1, "on": 1})
            if groups.count(g) >= MAX_PEOPLE:
                return Reply.error("That group is full.", 400)
            db.execute("INSERT OR IGNORE INTO gmasks(gid,uid) VALUES(?,?)", (g, me))
            groups.event(g, me, "join", 0, "", 1, now=ctx.now)
            return Reply({"ok": 1, "on": 1})
        if groups.masque_only(g, me):
            return Reply.error("Your Masque is how you are in this group. Use Leave group to go.", 400)
        if has:
            db.execute("DELETE FROM gmasks WHERE gid=? AND uid=?", (g, me))
            groups.event(g, me, "leave", 0, "", 1, now=ctx.now)
        return Reply({"ok": 1, "on": 0})


@registry.register
class GroupRemove(Action):
    """?a=gremove: the creator removes a person, or (mk=1) only a Masque (the whole membership when that Masque is how its owner is here)."""
    name = "gremove"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, groups = int(m["id"]), ctx.db, Groups(ctx.db)
        g = ctx.int_form("gid")
        if not db.value("SELECT 1 FROM gchats WHERE id=? AND owner=?", (g, me)):
            return Reply.error("Only the group creator can remove people.", 403)
        name = ctx.form("name")
        if ctx.flag("mk"):
            u = db.value("SELECT uid FROM masks WHERE name=?", (name,))
            if not u or not db.value("SELECT 1 FROM gmasks WHERE gid=? AND uid=?", (g, u)):
                return Reply.error("They are not in this group.", 404)
            u = int(u)
            if u == me:
                return Reply.error("That is your own Masque. Use Remove my Masque instead.", 400)
            db.execute("DELETE FROM gmasks WHERE gid=? AND uid=?", (g, u))
            if groups.masque_only(g, u):
                db.execute("DELETE FROM gmembers WHERE gid=? AND uid=?", (g, u))
            groups.event(g, me, "kick", u, "", 0, 1, now=ctx.now)
            return Reply({"ok": 1})
        u = groups.user_id(name)
        if not u or not groups.member(g, u) or groups.masque_only(g, u):
            return Reply.error("They are not in this group.", 404)
        if u == me:
            return Reply.error("You created this group, so you cannot remove yourself.", 400)
        db.execute("DELETE FROM gmembers WHERE gid=? AND uid=?", (g, u))
        db.execute("DELETE FROM gmasks WHERE gid=? AND uid=?", (g, u))
        groups.event(g, me, "kick", u, now=ctx.now)
        return Reply({"ok": 1})


@registry.register
class GroupLeave(GroupAction):
    """?a=gleave: leave a group. The last person out deletes it; when the creator leaves, the next member becomes the creator."""
    name = "gleave"

    def handle(self, ctx: Context) -> Reply:
        m, me, g, groups = self.member_of(ctx)
        db = ctx.db
        was_owner = bool(db.value("SELECT 1 FROM gchats WHERE id=? AND owner=?", (g, me)))
        only = groups.masque_only(g, me)
        had_mask = bool(db.value("SELECT 1 FROM gmasks WHERE gid=? AND uid=?", (g, me)))
        db.execute("DELETE FROM gmembers WHERE gid=? AND uid=?", (g, me))
        db.execute("DELETE FROM gmasks WHERE gid=? AND uid=?", (g, me))
        if not only:
            groups.event(g, me, "leave", now=ctx.now)
        if had_mask:
            groups.event(g, me, "leave", 0, "", 1, now=ctx.now)
        if not int(db.value("SELECT COUNT(*) FROM gmembers WHERE gid=?", (g,), 0)):
            ctx.media.remove(Membership(groups).dissolve(g))
            Tidy(db).reactions()
        elif was_owner:
            nx = db.value("SELECT uid FROM gmembers WHERE gid=? ORDER BY pm,rowid LIMIT 1", (g,))
            db.execute("UPDATE gchats SET owner=? WHERE id=?", (nx, g))
        return Reply({"ok": 1})


@registry.register
class GroupRename(GroupAction):
    """?a=grename: any member renames the group (a notice goes in the thread when the name really changed)."""
    name = "grename"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, groups = int(m["id"]), ctx.db, Groups(ctx.db)
        g = ctx.int_form("gid")
        n = php_trim(ctx.form("name")[:40])
        if not groups.member(g, me):
            return Reply.error(_NO_GROUP, 404)
        if n == "":
            return Reply.error("Give the group a name.", 400)
        if n != str(db.value("SELECT name FROM gchats WHERE id=?", (g,)) or ""):
            db.execute("UPDATE gchats SET name=? WHERE id=?", (n, g))
            groups.event(g, me, "name", 0, n, now=ctx.now)
        return Reply({"name": n})


@registry.register
class GroupIcon(Action):
    """?a=gicon: set (avatar file) or remove (noavatar=1) the group photo."""
    name = "gicon"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, groups = int(m["id"]), ctx.db, Groups(ctx.db)
        ctx.limits.throttle("gi:%d" % me, 20, 3600)
        g = ctx.int_form("gid")
        if not groups.member(g, me):
            return Reply.error(_NO_GROUP, 404)
        old = str(db.value("SELECT avatar FROM gchats WHERE id=?", (g,)) or "")
        upload = ctx.file("avatar")
        if upload is not None:
            av = ctx.media.save_img(upload)
        elif ctx.flag("noavatar"):
            av = ""
        else:
            return Reply.error("Pick a photo first.", 400)
        db.execute("UPDATE gchats SET avatar=? WHERE id=?", (av, g))
        groups.event(g, me, "icon", 0, "removed" if av == "" else "set", now=ctx.now)
        if old != "" and old != av:
            ctx.media.remove([old])
        return Reply({"avatar": av})


@registry.register
class GroupBackground(GroupAction):
    """?a=gsetbg: the group's shared chat background. Castle Night ones can only be kept once the event is over."""
    name = "gsetbg"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, groups = int(m["id"]), ctx.db, Groups(ctx.db)
        ctx.limits.throttle("gb:%d" % me, 30, 3600)
        g, b = ctx.int_form("gid"), ctx.form("bg")
        if not groups.member(g, me):
            return Reply.error(_NO_GROUP, 404)
        if b != "" and b not in BACKGROUNDS:
            return Reply.error("Unknown background.", 400)
        was = str(db.value("SELECT bg FROM gchats WHERE id=?", (g,)) or "")
        if b in EVENT_BACKGROUNDS and not ctx.unlocks.event_on() and not m["admin"] and b != was:
            return Reply.error("Castle Night has ended, so this is not available any more.", 403)
        if b != was:
            db.execute("UPDATE gchats SET bg=? WHERE id=?", (b, g))
            groups.event(g, me, "bg", 0, b, now=ctx.now)
        return Reply({"bg": b})


@registry.register
class GroupMute(GroupAction):
    """?a=gmute: mute or unmute the pop-up alerts of one group (on=1 mutes)."""
    name = "gmute"

    def handle(self, ctx: Context) -> Reply:
        m, me, g, _ = self.member_of(ctx)
        on = 1 if ctx.flag("on") else 0
        ctx.db.execute("UPDATE gmembers SET mute=? WHERE gid=? AND uid=?", (on, g, me))
        return Reply({"mu": on})


@registry.register
class GroupInvites(Action):
    """?a=ginv: the group invites waiting for me (not from people I blocked or who blocked me)."""
    name = "ginv"
    SQL = ("SELECT v.id,v.gid,v.ts,g.name,g.avatar,COALESCE(NULLIF(u.nick,''),u.name) who,v.pm,(SELECT name FROM masks WHERE uid=v.uid) mq "
           "FROM ginvites v JOIN gchats g ON g.id=v.gid JOIN users u ON u.id=v.inv WHERE v.uid=? AND v.inv NOT IN (" + _BLOCKED + ") ORDER BY v.id DESC LIMIT 30")

    def handle(self, ctx: Context) -> Reply:
        i = int(ctx.users.need()["id"])
        return Reply({"invites": ctx.db.all(self.SQL, (i, i, i))})


@registry.register
class GroupAnswerInvite(Action):
    """?a=gacc: accept an invite (act omitted) or decline it (act=decline)."""
    name = "gacc"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        ctx.limits.throttle("gv:%d" % me, 40, 3600)
        v = db.one("SELECT id,gid,pm FROM ginvites WHERE id=? AND uid=?", (ctx.int_form("id"), me))
        if not v:
            return Reply.error("That invite is gone.", 404)
        g = int(v["gid"])
        if ctx.form("act") == "decline" or not db.value("SELECT 1 FROM gchats WHERE id=?", (g,)):
            db.execute("DELETE FROM ginvites WHERE id=?", (v["id"],))
            return Reply({"ok": 1})
        join = Membership(Groups(db))
        e = join.join_mask(g, me) if int(v["pm"]) else join.join(g, me, "invite")
        return Reply.error(e, 403) if e else Reply({"id": g})


class InviteLinks:
    """The shareable invite link of a group (table glinks, one hex code per group)."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def clean(code: str) -> str:
        return re.sub(r"[^a-f0-9]", "", str(code))

    def group_of(self, code: str) -> int:
        c = self.clean(code)
        return int(self.db.value("SELECT gid FROM glinks WHERE code=?", (c,), 0) or 0) if c else 0

    def code_for(self, gid: int, reset: bool, now: int) -> str:
        c = self.db.value("SELECT code FROM glinks WHERE gid=?", (gid,))
        if not c or reset:
            c = secrets.token_hex(8)
            self.db.execute("INSERT OR REPLACE INTO glinks(gid,code,ts) VALUES(?,?,?)", (gid, c, now))
        return str(c)


@registry.register
class GroupLink(GroupAction):
    """?a=glink: the invite link code of a group I am in (reset=1 makes a new one and kills the old)."""
    name = "glink"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me = int(m["id"])
        ctx.limits.throttle("gl:%d" % me, 30, 3600)
        g = ctx.int_form("gid")
        if not Groups(ctx.db).member(g, me):
            return Reply.error(_NO_GROUP, 404)
        return Reply({"code": InviteLinks(ctx.db).code_for(g, ctx.flag("reset"), ctx.now)})


@registry.register
class GroupLinkInfo(Action):
    """?a=glinkinfo: what an invite link opens (name, photo, how many people) and whether I am already in."""
    name = "glinkinfo"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me = int(m["id"])
        ctx.limits.throttle("gl2:%d" % me, 60, 3600)
        g = InviteLinks(ctx.db).group_of(ctx.arg("c"))
        gi = ctx.db.one("SELECT id,name,avatar,(SELECT COUNT(*) FROM gmembers WHERE gid=gchats.id) n FROM gchats WHERE id=?", (g,)) if g else None
        if not gi:
            return Reply.error("This invite link is not valid any more.", 404)
        return Reply({"g": gi, "in": 1 if Groups(ctx.db).member(g, me) else 0})


@registry.register
class GroupJoin(Action):
    """?a=gjoin: join through an invite link."""
    name = "gjoin"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me = int(m["id"])
        ctx.limits.throttle("gj:%d" % me, 20, 3600)
        g = InviteLinks(ctx.db).group_of(ctx.form("c"))
        if not g or not ctx.db.value("SELECT 1 FROM gchats WHERE id=?", (g,)):
            return Reply.error("This invite link is not valid any more.", 404)
        e = Membership(Groups(ctx.db)).join(g, me, "link")
        return Reply.error(e, 403) if e else Reply({"id": g})


@registry.register
class GroupSearch(Action):
    """?a=gsearch: find text in one group's messages (newest 40)."""
    name = "gsearch"
    SQL = ("SELECT x.id,x.txt,x.ts,(x.uid=?) mine,CASE WHEN x.pm=1 THEN COALESCE(k.name,'Masque') ELSE COALESCE(NULLIF(u.nick,''),u.name) END who "
           "FROM gmessages x JOIN users u ON u.id=x.uid LEFT JOIN masks k ON k.uid=x.uid WHERE x.gid=? AND x.txt LIKE ? ESCAPE '\\' "
           "AND (x.pm=1 OR x.uid NOT IN (" + _BLOCKED + ")) ORDER BY x.id DESC LIMIT 40")

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me = int(m["id"])
        ctx.limits.throttle("ms:%d" % me, 40, 60)
        g = ctx.int_arg("id")
        if not g or not Groups(ctx.db).member(g, me):
            return Reply.error(_NO_GROUP, 404)
        q = php_trim(ctx.arg("q")[:60])
        if len(q) < 2:
            return Reply({"res": []})
        return Reply({"res": ctx.db.all(self.SQL, (me, g, "%" + like_escape(q) + "%", me, me))})


@registry.register
class GroupPin(Action):
    """?a=gpin: pin or unpin a group message (up to 5 per group)."""
    name = "gpin"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        ctx.limits.throttle("pn:%d" % me, 60, 60)
        mid = ctx.int_form("id")
        r = db.one("SELECT gid,uid,pin FROM gmessages WHERE id=?", (mid,))
        if not r or not Groups(db).member(int(r["gid"]), me):
            return Reply.error("Message not found.", 404)
        n = int(db.value("SELECT COUNT(*) FROM gmessages WHERE gid=? AND pin>0", (r["gid"],), 0))
        new = 0 if int(r["pin"]) > 0 else ctx.now
        if new and n >= MAX_PINS:
            return Reply.error("You can pin up to %d messages. Unpin one first." % MAX_PINS, 400)
        db.execute("UPDATE gmessages SET pin=? WHERE id=?", (new, mid))
        return Reply({"pin": new})


@registry.register
class GroupReact(Action):
    """?a=greact: put (or take back) one emoji on a group message."""
    name = "greact"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        ctx.limits.throttle("rx:%d" % me, 120, 60)
        mid, e = ctx.int_form("id"), ctx.form("e")
        if e != "" and e not in REACTS:
            return Reply.error("Unknown reaction.", 400)
        r = db.one("SELECT gid,uid,pm FROM gmessages WHERE id=?", (mid,))
        if not r or not Groups(db).member(int(r["gid"]), me):
            return Reply.error("Message not found.", 404)
        if int(r["uid"]) != me and not int(r["pm"]) and ctx.rel.blocked(me, int(r["uid"])):
            return Reply.error("You cannot react to this message.", 403)
        cur = db.value("SELECT e FROM mreact WHERE k='g' AND mid=? AND uid=?", (mid, me))
        if e == "" or e == cur:
            db.execute("DELETE FROM mreact WHERE k='g' AND mid=? AND uid=?", (mid, me))
        else:
            db.execute("INSERT INTO mreact(k,mid,uid,e) VALUES('g',?,?,?) ON CONFLICT(k,mid,uid) DO UPDATE SET e=excluded.e", (mid, me, e))
        rows = [{"id": mid, "rp": 0}]
        Decorator(db).apply("g", rows, me, int(r["gid"]))
        return Reply({"rx": rows[0]["rx"]})
