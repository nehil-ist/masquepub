"""Group chats, part 1 (PHP: case 'gcreate', 'ginbox', 'gthread', 'gsend', 'gedit', 'gdel', 'gadd'; 'gopen' is a gift action that sits with them).

Members are (user id, pm) rows: pm=1 means the person is in the group only as their Masque.
"""
import sys

from ..chatview import MAX_PINS, Decorator, pin_info
from ..groupchat import MAX_PEOPLE, Groups
from ..media import GameInvite
from ..php import php_trim
from ..streaks import ChatStreaks
from .base import Action, Context, Reply, registry

_BLOCKED = "SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?"
_NOT_A_MEMBER = "No such group."


def _text(ctx: Context, name: str = "txt") -> str:
    return php_trim(ctx.form(name)[:500])


@registry.register
class GroupCreate(Action):
    """?a=gcreate: a new group with a name and friends (members=a,b,c). Friends who blocked each other are not put together."""
    name = "gcreate"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, groups = int(m["id"]), ctx.db, Groups(ctx.db)
        ctx.limits.lim("gc:%d" % me, 10, 3600, m, 2, 3600)
        n = php_trim(ctx.form("name")[:40])
        ids = []
        for x in Groups.names(ctx.form("members")):
            u = groups.user_id(x)
            if not u or u == me:
                continue
            if ctx.rel.blocked(me, u) or not ctx.rel.friends(me, u):
                continue
            if any(ctx.rel.blocked(o, u) for o in ids):
                continue
            ids.append(u)
        if n == "":
            return Reply.error("Give the group a name.", 400)
        if not ids:
            return Reply.error("Pick at least one friend.", 400)
        g = db.query("INSERT INTO gchats(name,owner,ts) VALUES(?,?,?)", (n, me, ctx.now)).lastrowid
        for u in [me] + ids:
            db.execute("INSERT OR IGNORE INTO gmembers(gid,uid) VALUES(?,?)", (g, u))
        return Reply({"id": g})


@registry.register
class GroupInbox(Action):
    """?a=ginbox: my groups, newest activity first, with the last message and what I have not read."""
    name = "ginbox"
    SQL = (
        "SELECT g.id,g.name,g.avatar,COALESCE(x.ts,g.ts) ts,x.txt,x.img,CASE WHEN x.pm=1 THEN COALESCE(k.name,'Masque') ELSE COALESCE(NULLIF(u.nick,''),u.name) END who,"
        "(x.uid=?) mine,mb.mute mu,mb.pm gp,(SELECT COUNT(*) FROM gmasks gk WHERE gk.gid=g.id AND gk.uid=mb.uid) gk,"
        "(SELECT COUNT(*) FROM gmessages z WHERE z.gid=g.id AND z.id>mb.rd AND z.uid!=? AND (z.pm=1 OR z.uid NOT IN (" + _BLOCKED + "))) un "
        "FROM gchats g JOIN gmembers mb ON mb.gid=g.id AND mb.uid=? LEFT JOIN gmessages x ON x.id=(SELECT MAX(id) FROM gmessages WHERE gid=g.id AND uid NOT IN (" + _BLOCKED + ")) "
        "LEFT JOIN users u ON u.id=x.uid LEFT JOIN masks k ON k.uid=x.uid ORDER BY ts DESC LIMIT 50")

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        i = int(m["id"])
        rows = ctx.db.all(self.SQL, (i, i, i, i, i, i, i))
        streaks = ChatStreaks(ctx.db)
        for g in rows:
            g["cs"] = streaks.group(int(g["id"]))
        return Reply({"groups": rows})


@registry.register
class GroupThread(Action):
    """?a=gthread: one group: details, the latest events, members, the newest 100 messages (or the ones around an old one), pins, who has seen my last message."""
    name = "gthread"

    EVENTS = (
        "SELECT e.id,e.kind,e.arg,e.ts,CASE WHEN e.pm=1 THEN COALESCE(ka.name,'a Masque') ELSE COALESCE(NULLIF(a.nick,''),a.name) END who,"
        "CASE WHEN e.tpm=1 THEN COALESCE(kt.name,'a Masque') ELSE COALESCE(NULLIF(t.nick,''),t.name) END tw FROM gevents e JOIN users a ON a.id=e.uid "
        "LEFT JOIN users t ON t.id=e.tid LEFT JOIN masks ka ON ka.uid=e.uid LEFT JOIN masks kt ON kt.uid=e.tid WHERE e.gid=? AND e.uid NOT IN (" + _BLOCKED + ") ORDER BY e.id DESC LIMIT 60")
    MEMBERS = (
        "SELECT * FROM (SELECT u.name,u.nick,u.avatar,(u.id=g.owner) own,0 mk FROM gmembers mb JOIN users u ON u.id=mb.uid JOIN gchats g ON g.id=mb.gid WHERE mb.gid=? AND mb.pm=0 "
        "UNION ALL SELECT k.name,'' nick,k.avatar,(mb.uid=g.owner AND mb.pm=1) own,1 mk FROM gmasks gm JOIN masks k ON k.uid=gm.uid JOIN gmembers mb ON mb.gid=gm.gid AND mb.uid=gm.uid "
        "JOIN gchats g ON g.id=gm.gid WHERE gm.gid=?) ORDER BY name COLLATE NOCASE")
    MESSAGES = (
        "SELECT x.id,x.txt,x.img,x.ts,x.ed,x.rp,x.pin,(x.uid=?) mine,(x.uid=(SELECT owner FROM gchats WHERE id=x.gid) AND (x.pm=0 OR (SELECT pm FROM gmembers WHERE gid=x.gid AND uid=x.uid)=1)) co,"
        "CASE WHEN x.pm=1 THEN COALESCE(k.name,'Masque') ELSE u.name END name,CASE WHEN x.pm=1 THEN '' ELSE u.nick END nick,"
        "CASE WHEN x.pm=1 THEN COALESCE(k.avatar,'') ELSE u.avatar END avatar,x.pm mk FROM gmessages x JOIN users u ON u.id=x.uid LEFT JOIN masks k ON k.uid=x.uid "
        "WHERE x.gid=? AND (x.pm=1 OR x.uid NOT IN (" + _BLOCKED + ")) AND x.id<=? ORDER BY x.id DESC LIMIT 100")
    PINS = (
        "SELECT x.id,x.txt,x.img,(x.uid=?) mine,CASE WHEN x.pm=1 THEN COALESCE(k.name,'Masque') ELSE COALESCE(NULLIF(u.nick,''),u.name) END who,"
        "CASE WHEN x.pm=1 THEN COALESCE(k.avatar,'') ELSE u.avatar END av,x.pm mk FROM gmessages x JOIN users u ON u.id=x.uid LEFT JOIN masks k ON k.uid=x.uid "
        "WHERE x.gid=? AND x.pin>0 AND (x.pm=1 OR x.uid NOT IN (" + _BLOCKED + ")) ORDER BY x.pin DESC,x.id DESC LIMIT %d" % MAX_PINS)
    SEEN_BY = (
        "SELECT CASE WHEN mb.pm=1 THEN COALESCE(k.name,'Masque') ELSE u.name END FROM gmembers mb JOIN users u ON u.id=mb.uid LEFT JOIN masks k ON k.uid=mb.uid "
        "WHERE mb.gid=? AND mb.uid!=? AND mb.rd>=? AND mb.since<? AND mb.uid NOT IN (" + _BLOCKED + ") ORDER BY 1")

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, groups = int(m["id"]), ctx.db, Groups(ctx.db)
        g = ctx.int_arg("id")
        if not groups.member(g, me):
            return Reply.error(_NOT_A_MEMBER, 404)
        info = db.one("SELECT id,name,avatar,bg,(owner=?) own FROM gchats WHERE id=?", (me, g))
        events = list(reversed(db.all(self.EVENTS, (g, me, me))))
        members = db.all(self.MEMBERS, (g, g))
        around = ctx.int_arg("around")
        msgs = list(reversed(db.all(self.MESSAGES, (me, g, me, me, around + 40 if around > 0 else sys.maxsize))))
        Decorator(db).apply("g", msgs, me, g)
        pins = [pin_info(r) for r in db.all(self.PINS, (me, g, me, me))]
        db.execute("UPDATE gmembers SET rd=(SELECT COALESCE(MAX(id),0) FROM gmessages WHERE gid=?) WHERE gid=? AND uid=?", (g, g, me))
        mid = int(db.value("SELECT COALESCE(MAX(id),0) FROM gmessages WHERE gid=? AND uid=?", (g, me), 0))
        by = [r[0] for r in db.query(self.SEEN_BY, (g, me, mid, mid, me, me)).fetchall()] if mid else []
        mask = db.one("SELECT name,avatar FROM masks WHERE uid=?", (me,))
        gm = {"has": 1 if mask else 0, "in": 1 if db.value("SELECT 1 FROM gmasks WHERE gid=? AND uid=?", (g, me)) else 0,
              "only": groups.masque_only(g, me), "name": str((mask or {}).get("name") or ""), "avatar": str((mask or {}).get("avatar") or "")}
        return Reply({"g": info, "events": events, "members": members, "msgs": msgs, "seen": {"mid": mid, "by": by}, "pins": pins, "gm": gm,
                      "cs": ChatStreaks(db).group(g)})


@registry.register
class GroupSend(Action):
    """?a=gsend: a message in a group, as the real account or (as=mask) as my Masque; people only here as a Masque always write as it."""
    name = "gsend"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, groups = int(m["id"]), ctx.db, Groups(ctx.db)
        ctx.limits.lim("gm:%d" % me, 40, 60, m, 15, 60)
        g = ctx.int_form("gid")
        t = _text(ctx)
        ctx.media.check_sticker(m, t)
        ctx.media.check_game_invite(m, t)
        if not groups.member(g, me):
            return Reply.error(_NOT_A_MEMBER, 404)
        upload = ctx.file("img")
        if t == "" and upload is None:
            return Reply.error("Write something first.", 400)
        if not ctx.mentions.everyone_ok(g, m, t):
            return Reply.error("You can use @everyone once every 5 minutes in a group.", 429)
        rp = ctx.int_form("rp")
        if rp > 0 and not db.value("SELECT 1 FROM gmessages WHERE id=? AND gid=?", (rp, g)):
            return Reply.error("The message you are replying to is gone.", 400)
        pm = groups.masque_only(g, me)
        if not pm and ctx.form("as") == "mask":
            if not db.value("SELECT 1 FROM gmasks WHERE gid=? AND uid=?", (g, me)):
                return Reply.error("Your Masque is not in this group.", 400)
            pm = 1
        img = ctx.media.save_attachment(upload, m)
        db.execute("INSERT INTO gmessages(gid,uid,txt,ts,img,rp,pm) VALUES(?,?,?,?,?,?,?)", (g, me, t, ctx.now, img, max(0, rp), pm))
        db.execute("DELETE FROM typing WHERE uid=? AND gid=?", (me, g))
        ctx.mentions.in_group(g, t, m, pm)
        for r in db.all("SELECT uid FROM gmembers WHERE gid=? AND mute=0 AND uid!=?", (g, me)):
            gu = int(r["uid"])
            if int(ctx.notes.prefs.get(gu)["pop"]) and (pm or not ctx.rel.blocked(gu, me)):
                ctx.notes.push(gu, "Masque", "New message in a group", "./", "g-%d" % g, 60)
        return Reply({"ok": 1})


@registry.register
class GroupEdit(Action):
    """?a=gedit: change the text of one of my group messages."""
    name = "gedit"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        ctx.limits.lim("em:%d" % me, 30, 600, m, 10, 600)
        mid = ctx.int_form("id")
        t = _text(ctx)
        r = db.one("SELECT gid,img,txt,pm FROM gmessages WHERE id=? AND uid=?", (mid, me))
        if not r or not Groups(db).member(int(r["gid"]), me):
            return Reply.error("Message not found.", 404)
        old = str(r["txt"] or "")
        if GameInvite.is_invite(t) or GameInvite.is_invite(old):
            return Reply.error("A game invite cannot be edited. Delete it and send a new one.", 400)
        if t == "" and not r["img"]:
            return Reply.error("A message cannot be empty. Delete it instead.", 400)
        if not ctx.mentions.everyone_ok(int(r["gid"]), m, t, old):
            return Reply.error("You can use @everyone once every 5 minutes in a group.", 429)
        now = ctx.now
        db.execute("UPDATE gmessages SET txt=?,ed=? WHERE id=? AND uid=?", (t, now, mid, me))
        ctx.mentions.in_group(int(r["gid"]), t, m, int(r["pm"]), old)
        return Reply({"txt": t, "ed": now})


@registry.register
class GroupDelete(Action):
    """?a=gdel: delete one of my group messages. An admin may also delete others', but only in groups they are a member of."""
    name = "gdel"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        mid = ctx.int_form("id")
        row = db.one("SELECT gid,uid,img FROM gmessages WHERE id=?", (mid,))
        own = bool(row) and int(row["uid"]) == me
        by_admin = bool(row) and not own and bool(m["admin"]) and Groups(db).member(int(row["gid"]), me)
        if not own and not by_admin:
            return Reply({"ok": 1})
        if by_admin:
            ctx.adminlog.add(m, "deleted message", str(db.value("SELECT name FROM users WHERE id=?", (row["uid"],)) or ""))
        if db.execute("DELETE FROM gmessages WHERE id=?", (mid,)):
            db.execute("DELETE FROM mreact WHERE k='g' AND mid=?", (mid,))
        ctx.media.remove([row["img"]])  # only names this site would have made are ever deleted
        return Reply({"ok": 1})


@registry.register
class GroupInvite(Action):
    """?a=gadd: invite friends (members=a,b,c) to a group I am in. A group holds up to 31 people; people who already have an invite are skipped."""
    name = "gadd"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, groups = int(m["id"]), ctx.db, Groups(ctx.db)
        ctx.limits.lim("ga:%d" % me, 0, 0, m, 5, 3600)
        g = ctx.int_form("gid")
        if not groups.member(g, me):
            return Reply.error(_NOT_A_MEMBER, 404)
        have = groups.count(g) + int(db.value("SELECT COUNT(*) FROM ginvites WHERE gid=?", (g,), 0))
        n = 0
        for x in Groups.names(ctx.form("members")):
            u = groups.user_id(x)
            if not u or (groups.member(g, u) and not groups.masque_only(g, u)):
                continue
            if ctx.rel.blocked(me, u) or groups.blocked_with_member(g, u) or not ctx.rel.friends(me, u):
                continue
            if have + n >= MAX_PEOPLE:
                break
            if db.value("SELECT 1 FROM ginvites WHERE gid=? AND uid=?", (g, u)):
                continue
            db.execute("INSERT INTO ginvites(gid,uid,inv,ts) VALUES(?,?,?,?)", (g, u, me, ctx.now))
            groups.event(g, me, "invite", u, now=ctx.now)
            n += 1
        if not n:
            return Reply.error("Nobody was invited. A group holds up to 31 people, you can only invite your friends, and people who already have an invite are skipped.", 400)
        return Reply({"added": n})


@registry.register
class GiftOpen(Action):
    """?a=gopen: mark one of my gifts as opened. (Not a group action: it only sits near them in index.php.)"""
    name = "gopen"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.db.execute("UPDATE gifts SET opened=1 WHERE id=? AND uid=?", (ctx.int_form("id"), m["id"]))
        return Reply({"ok": 1})
