"""Masques (PHP: case 'maskinb', 'mblock', 'maskset', 'maskdel', 'maskuser', 'mreveal', 'mcomments')."""
import sqlite3

from ..access import mqts
from ..names import NameRules
from ..php import php_trim
from .posts import PostFiles
from ..tidy import Tidy
from .base import Action, Context, Reply, registry


@registry.register
class MasqueInbox(Action):
    """?a=maskinb: open (on=1) or close my Masque to message requests."""
    name = "maskinb"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.db.execute("UPDATE masks SET inb=? WHERE uid=?", (1 if ctx.flag("on") else 0, int(m["id"])))
        return Reply({"ok": 1})


@registry.register
class MasqueBlock(Action):
    """?a=mblock: block (default) or unblock (on=0) one Masque by name, without blocking the account behind it."""
    name = "mblock"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me = int(m["id"])
        k = ctx.db.one("SELECT id,uid FROM masks WHERE name=?", (ctx.form("k"),))
        if not k or int(k["uid"]) == me:
            return Reply.error("No such Masque.", 404)
        if ctx.form("on", "1") == "0":
            ctx.db.execute("DELETE FROM mblocks WHERE a=? AND kid=?", (me, k["id"]))
        else:
            ctx.db.execute("INSERT OR IGNORE INTO mblocks VALUES(?,?)", (me, k["id"]))
        return Reply({"ok": 1})


@registry.register
class MasqueSet(Action):
    """?a=maskset: make my Masque (name, bio, picture) or change its bio and picture. The name can never change."""
    name = "maskset"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        ctx.limits.throttle("mk:%d" % me, 20, 3600)
        k = db.one("SELECT id,name,avatar FROM masks WHERE uid=?", (me,))
        bio = php_trim(ctx.form("bio")[:160])
        if not k:
            n = php_trim(ctx.form("name"))
            if not NameRules.valid(n):
                return Reply.error("Masque names are 3 to 20 letters, numbers or _.", 400)
            h = NameRules.digest(n)
            if (db.value("SELECT 1 FROM gone WHERE h=?", (h,))
                    or db.value("SELECT 1 FROM oldnames WHERE ts>? AND h=?", (ctx.now - NameRules.RESERVE_SECS, h))
                    or ctx.names.clash(n, 0, True)):
                return Reply.error("That name is taken.", 409)
            av = ctx.media.save_img(ctx.file("avatar"))
            try:
                db.execute("INSERT INTO masks(uid,name,bio,avatar,ts) VALUES(?,?,?,?,?)", (me, n, bio, av, ctx.now))
            except sqlite3.IntegrityError:
                return Reply.error("That name is taken.", 409)
        else:
            av = str(k["avatar"] or "")
            if ctx.flag("noavatar") or ctx.file("avatar"):
                new = ctx.media.save_img(ctx.file("avatar"))
                ctx.media.remove([av])
                av = new
            db.execute("UPDATE masks SET bio=?,avatar=? WHERE id=?", (bio, av, k["id"]))
        return Reply({"mask": db.one("SELECT name,bio,avatar FROM masks WHERE uid=?", (me,))})


@registry.register
class MasqueDelete(Action):
    """?a=maskdel: delete my Masque with everything it made (posts, comments, chats, group seats) and reserve its name for good."""
    name = "maskdel"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        k = db.one("SELECT id,name,avatar FROM masks WHERE uid=?", (me,))
        if not k:
            return Reply({"ok": 1})
        col = lambda sql, *p: [r[0] for r in db.query(sql, p).fetchall()]  # noqa: E731
        files = [k["avatar"]]
        for pid in col("SELECT id FROM posts WHERE mid=?", k["id"]):
            files += PostFiles(ctx).of(int(pid))
        files += col("SELECT img FROM messages WHERE img!='' AND ((a=? AND fm=1) OR (b=? AND tm=1))", me, me)
        with db.transaction():
            for sql, args in (
                ("DELETE FROM messages WHERE (a=? AND fm=1) OR (b=? AND tm=1)", (me, me)),
                ("DELETE FROM mblocks WHERE kid=?", (k["id"],)),
                ("DELETE FROM mreveals WHERE uid=?", (me,)),
                ("DELETE FROM notifs WHERE kind='reveal' AND actor=?", (me,)),
                ("DELETE FROM likes WHERE pid IN (SELECT id FROM posts WHERE mid=?)", (k["id"],)),
                ("DELETE FROM comments WHERE mid=? OR pid IN (SELECT id FROM posts WHERE mid=?)", (k["id"], k["id"])),
                ("DELETE FROM posts WHERE mid=?", (k["id"],)),
            ):
                db.execute(sql, args)
            files += col("SELECT img FROM gmessages WHERE uid=? AND pm=1 AND img!=''", me)
            for sql, args in (
                ("DELETE FROM gmessages WHERE uid=? AND pm=1", (me,)),
                ("DELETE FROM gevents WHERE (uid=? AND pm=1) OR (tid=? AND tpm=1)", (me, me)),
                ("DELETE FROM ginvites WHERE uid=? AND pm=1", (me,)),
                ("DELETE FROM gmasks WHERE uid=?", (me,)),
            ):
                db.execute(sql, args)
            for g in col("SELECT gid FROM gmembers WHERE uid=? AND pm=1", me):
                db.execute("DELETE FROM gmembers WHERE gid=? AND uid=?", (g, me))
                if not int(db.value("SELECT COUNT(*) FROM gmembers WHERE gid=?", (g,), 0)):  # last member left: the group goes
                    files += col("SELECT img FROM gmessages WHERE gid=? AND img!=''", g)
                    files.append(str(db.value("SELECT avatar FROM gchats WHERE id=?", (g,), "")))
                    for t in ("gmessages", "gevents", "ginvites", "glinks", "gmasks"):
                        db.execute("DELETE FROM %s WHERE gid=?" % t, (g,))
                    db.execute("DELETE FROM gchats WHERE id=?", (g,))
                elif db.value("SELECT owner FROM gchats WHERE id=?", (g,)) == me:  # the owner left: the first member takes over
                    nx = db.value("SELECT uid FROM gmembers WHERE gid=? ORDER BY pm,rowid LIMIT 1", (g,))
                    db.execute("UPDATE gchats SET owner=? WHERE id=?", (nx, g))
            db.execute("DELETE FROM notifs WHERE mid=?", (k["id"],))
            db.execute("INSERT OR IGNORE INTO gone VALUES(?,?)", (NameRules.digest(k["name"]), me))
            db.execute("DELETE FROM rrep WHERE uid=?", (me,))
            db.execute("DELETE FROM masks WHERE id=?", (k["id"],))
            Tidy(db).run()
        ctx.media.remove(files)
        return Reply({"ok": 1})


class MasqueRep:
    """A Masque's reputation: 3 points per post, 1 per comment, 1 per mark (like) received, minus 1 per downvote. Can go negative."""
    THRESHOLDS = (0, 10, 40, 120, 300)
    TITLES = ("Stranger", "Whisper", "Regular", "Familiar", "Legend")

    def __init__(self, db):
        self.db = db

    def of(self, kid: int, uid: int) -> dict:
        db = self.db
        n = lambda sql, *p: int(db.value(sql, p, 0) or 0)  # noqa: E731
        posts = n("SELECT COUNT(*) FROM posts WHERE mid=? AND hold=0 AND vis=0", kid)
        comments = n("SELECT COUNT(*) FROM comments WHERE mid=? AND hold=0", kid)
        marks = (n("SELECT COUNT(*) FROM likes l JOIN posts p ON p.id=l.pid WHERE p.mid=?", kid)
                 + n("SELECT COUNT(*) FROM clikes l JOIN comments c ON c.id=l.cid WHERE c.mid=?", kid))
        downs = (n("SELECT COUNT(*) FROM dislikes d JOIN posts p ON p.id=d.pid WHERE p.mid=?", kid)
                 + n("SELECT COUNT(*) FROM cdislikes d JOIN comments c ON c.id=d.cid WHERE c.mid=?", kid))
        room = db.one("SELECT up,down FROM rrep WHERE uid=?", (uid,))  # room messages count too
        if room:
            marks += int(room["up"] or 0)
            downs += int(room["down"] or 0)
        score = posts * 3 + comments + marks - downs
        counts = {"posts": posts, "comments": comments, "marks": marks, "downs": downs}
        if score < 0:
            return {"lv": -1, "title": "Shunned", "score": score, "from": -100, "next": 0, "nextTitle": "Stranger", **counts}
        lv = max(j for j, t in enumerate(self.THRESHOLDS) if score >= t)
        more = lv + 1 < len(self.THRESHOLDS)
        return {"lv": lv, "title": self.TITLES[lv], "score": score, "from": self.THRESHOLDS[lv],
                "next": self.THRESHOLDS[lv + 1] if more else None, "nextTitle": self.TITLES[lv + 1] if more else None, **counts}


@registry.register
class MasqueUser(Action):
    """?a=maskuser: a Masque's profile card. A Masque you blocked still opens (so you can unblock it) but shows nothing."""
    name = "maskuser"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        k = db.one("SELECT id,uid,name,bio,avatar FROM masks WHERE name=?", (php_trim(ctx.arg("k")),))
        if not k:
            return Reply.error("No such Masque.", 404)
        mine = int(k["uid"]) == me
        mb = 1 if (not mine and db.value("SELECT 1 FROM mblocks WHERE a=? AND kid=?", (me, k["id"]))) else 0
        kk = {"name": k["name"], "bio": "" if mb else k["bio"], "avatar": k["avatar"], "mine": 1 if mine else 0, "mb": mb}
        if not mb:  # shown whatever the owner's privacy setting is
            kk["rep"] = MasqueRep(db).of(int(k["id"]), int(k["uid"]))
        if mine:
            kk["rv"] = db.all("SELECT u.name,u.nick,u.avatar FROM mreveals r JOIN users u ON u.id=r.fid WHERE r.uid=? ORDER BY r.ts DESC", (me,))
        else:
            kk["by"] = db.one("SELECT u.name,u.nick,u.avatar FROM mreveals r JOIN users u ON u.id=r.uid WHERE r.uid=? AND r.fid=?", (k["uid"], me))
        return Reply({"k": kk})


@registry.register
class MasqueReveal(Action):
    """?a=mreveal: tell one accepted friend that this Masque is me (on=0 takes it back)."""
    name = "mreveal"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        ctx.limits.throttle("mrv:%d" % me, 20, 3600)
        if not db.value("SELECT 1 FROM masks WHERE uid=?", (me,)):
            return Reply.error("You do not have a Masque.", 400)
        o = db.value("SELECT id FROM users WHERE name=?", (ctx.form("to"),))
        if not o or int(o) == me:
            return Reply.error("No such user.", 404)
        if ctx.form("on", "1") == "0":
            db.execute("DELETE FROM mreveals WHERE uid=? AND fid=?", (me, o))
            return Reply({"ok": 1})
        if ctx.rel.blocked(me, o) or not ctx.rel.friends(me, o):
            return Reply.error("You can only tell accepted friends.", 403)
        if db.execute("INSERT OR IGNORE INTO mreveals VALUES(?,?,?)", (me, o, ctx.now)):
            ctx.notes.note(o, "reveal", me)
        return Reply({"ok": 1})


@registry.register
class MasqueComments(Action):
    """?a=mcomments: the comments a Masque wrote (30 at a time, newest first), only on posts the viewer may see."""
    name = "mcomments"
    PAGE = 30

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db = int(m["id"]), ctx.db
        k = db.one("SELECT id,uid FROM masks WHERE name=?", (php_trim(ctx.arg("k")),))
        if not k or (int(k["uid"]) != me and ctx.rel.masque_blocked(me, int(k["id"]))):
            return Reply.error("No such Masque.", 404)
        own = int(k["uid"]) == me
        before = ctx.int_arg("before")
        rows = db.all(
            "SELECT c.id,c.pid,c.txt,c.ts,p.cap pcap,p.img pimg,p.anon panon,p.uid puid FROM comments c JOIN posts p ON p.id=c.pid "
            "WHERE c.mid=? AND c.hold=0 AND p.hold=0" + (" AND c.id<?" if before else "") + " ORDER BY c.id DESC LIMIT %d" % (self.PAGE + 1),
            (k["id"], before) if before else (k["id"],))
        more = len(rows) > self.PAGE
        rows = rows[:self.PAGE]
        out = []
        for r in rows:
            if not ctx.access.can_view(int(r["pid"]), me):
                continue
            if int(r["panon"] or 0) and int(r["puid"]) == int(k["uid"]) and not own:
                continue  # the author's comments on their own anonymous post stay anonymous
            out.append({"id": int(r["id"]), "pid": int(r["pid"]), "txt": r["txt"], "ts": int(r["ts"]) if own else mqts(r["ts"]),
                        "pcap": str(r["pcap"] or "")[:80], "photo": 0 if r["pimg"] == "" else 1})
        return Reply({"list": out, "more": more, "last": int(rows[-1]["id"]) if rows else 0})
