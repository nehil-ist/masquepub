"""Moderation and admin actions: report, reports, appeal, appealst, appealres, suspend, purge, bwlist, bwadd, bwdel, rfset, astats, backup, ipdiag, suggest."""
import os
import secrets
import time
import unicodedata
from pathlib import Path

from flask import Response

from ..moderation import AutoHide
from ..php import collapse_space, php_trim, strip_controls, strip_invisible
from ..tidy import Tidy
from .base import Action, Context, Reply, registry
from .site import SiteSettings

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _gmdate(ts: int) -> str:
    t = time.gmtime(ts)
    return "%s %d, %d" % (_MONTHS[t.tm_mon - 1], t.tm_mday, t.tm_year)


def _admin(ctx: Context):
    """need() plus 'Not allowed.' for everyone but admins."""
    m = ctx.users.need()
    if not m["admin"]:
        ctx.deny("Not allowed.", 403)
    return m


class FileReply(Reply):
    """A file download instead of JSON."""

    def __init__(self, path: Path, filename: str):
        super().__init__(None)
        self.path, self.filename = Path(path), filename

    def to_response(self) -> Response:
        data = self.path.read_bytes()
        try:
            self.path.unlink()
        except OSError:
            pass
        return Response(data, headers={"Content-Type": "application/octet-stream", "Cache-Control": "no-store",
                                       "Content-Disposition": 'attachment; filename="%s"' % self.filename,
                                       "Content-Length": str(len(data))})


# ---------------------------------------------------------------- people reporting
@registry.register
class Report(Action):
    """?a=report: report a person, post, comment, Masque or a question I received."""
    name = "report"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        k = ctx.form("kind")
        why = php_trim(ctx.form("why")[:200])
        if k == "user":
            t = db.value("SELECT id FROM users WHERE name=?", (ctx.form("to"),))
        elif k == "post":
            t = db.value("SELECT id FROM posts WHERE id=?", (ctx.int_form("id"),))
        elif k == "comment":
            t = db.value("SELECT id FROM comments WHERE id=?", (ctx.int_form("id"),))
        elif k == "mask":
            t = db.value("SELECT id FROM masks WHERE name=?", (php_trim(ctx.form("to")),))
        elif k == "ask":
            t = db.value("SELECT id FROM asks WHERE id=? AND uid=? AND hid=0", (ctx.int_form("id"), m["id"]))
        else:
            return Reply.error("Bad report.", 400)
        if not t:
            return Reply.error("That no longer exists.", 404)
        if k == "user":
            owner = t
        elif k == "ask":
            owner = db.value("SELECT frm FROM asks WHERE id=?", (t,))
        elif k == "mask":
            owner = db.value("SELECT uid FROM masks WHERE id=?", (t,))
        else:
            owner = db.value("SELECT uid FROM %s WHERE id=?" % ("posts" if k == "post" else "comments"), (t,))
        if int(owner or 0) == int(m["id"]):
            return Reply.error("You can't report your own content.", 400)
        ctx.limits.throttle("rp:%d" % m["id"], 5, 600)
        if not ctx.users.is_admin(m) and int(db.value("SELECT COUNT(*) FROM reports WHERE uid=? AND ts>?", (m["id"], ctx.now - 86400), 0)) >= 20:
            return Reply.error("Too many reports today.", 429)
        if not db.value("SELECT 1 FROM reports WHERE uid=? AND kind=? AND tid=?", (m["id"], k, t)):
            db.execute("INSERT INTO reports(uid,kind,tid,why,ts) VALUES(?,?,?,?,?)", (m["id"], k, t, why, ctx.now))
        if k == "ask":
            db.execute("UPDATE asks SET hid=1 WHERE id=?", (t,))
        return Reply({"ok": 1})


@registry.register
class Reports(Action):
    """?a=reports: the admin page (reports, the admin log, waiting appeals)."""
    name = "reports"

    _TARGETS = {
        "post": "SELECT u.id uid,u.name,u.sus,p.cap,p.sens,p.hold held,(p.img!='') himg FROM posts p JOIN users u ON u.id=p.uid WHERE p.id=?",
        "comment": "SELECT u.id uid,u.name,u.sus,c.txt cap,c.hold held FROM comments c JOIN users u ON u.id=c.uid WHERE c.id=?",
        "mask": "SELECT u.id uid,u.name,u.sus,('['||m.name||'] '||m.bio) cap FROM masks m JOIN users u ON u.id=m.uid WHERE m.id=?",
        "ask": "SELECT u.id uid,u.name,u.sus,a.txt cap FROM asks a JOIN users u ON u.id=a.frm WHERE a.id=?",
    }
    _OTHER = "SELECT id uid,name,sus,bio cap FROM users WHERE id=?"
    _COUNT = ("SELECT COUNT(*) FROM reports WHERE uid>0 AND ((kind='user' AND tid=?) OR (kind='post' AND tid IN (SELECT id FROM posts WHERE uid=?)) "
              "OR (kind='comment' AND tid IN (SELECT id FROM comments WHERE uid=?)) OR (kind='ask' AND tid IN (SELECT id FROM asks WHERE frm=?)) "
              "OR (kind='mask' AND tid IN (SELECT id FROM masks WHERE uid=?)))")

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = _admin(ctx)
        rows = db.all("SELECT r.id,r.kind,r.tid,r.why,r.ts,(r.uid=0) auto,COALESCE(u.name,'word filter') rname FROM reports r "
                      "LEFT JOIN users u ON u.id=r.uid ORDER BY r.id DESC LIMIT 100")
        hidn, hida = AutoHide.threshold(), AutoHide.min_age()
        for r in rows:
            i = db.one(self._TARGETS.get(r["kind"], self._OTHER), (r["tid"],))
            if i:
                u0 = int(i["uid"])
                i["n"] = int(db.value(self._COUNT, (u0,) * 5, 0))
                i["hid"] = 1 if (r["kind"] == "post" and hidn > 0 and int(db.value(
                    "SELECT COUNT(DISTINCT r.uid) FROM reports r JOIN users ru ON ru.id=r.uid WHERE r.kind='post' AND r.tid=? AND ru.ts<=?",
                    (r["tid"], ctx.now - hida), 0)) >= hidn) else 0
                i["sus"] = int(i["sus"])
                if "held" in i:
                    i["held"] = int(i["held"])
                if "sens" in i:
                    i["sens"] = int(i["sens"])
                    i["himg"] = int(i["himg"])
                i["adm"] = 1 if (ctx.users.is_admin(i) or u0 == int(m["id"])) else 0
                del i["uid"]
            r["target"] = i or None
        log = db.all("SELECT a.act,a.tgt,a.ts,u.name aname FROM alog a LEFT JOIN users u ON u.id=a.aid ORDER BY a.id DESC LIMIT 30")
        appeals = db.all("SELECT a.id,a.txt,a.ts,u.name,u.sus FROM appeals a JOIN users u ON u.id=a.uid WHERE a.st=0 AND u.sus>? ORDER BY a.id ASC LIMIT 50", (ctx.now,))
        for x in appeals:
            x["sus"] = int(x["sus"])
        return Reply({"reports": rows, "log": log, "appeals": appeals})


# ---------------------------------------------------------------- appeals
@registry.register
class AppealStatus(Action):
    """?a=appealst: where my appeal stands."""
    name = "appealst"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        a = ctx.db.one("SELECT id,txt,ts,st,note,rts FROM appeals WHERE uid=? ORDER BY id DESC LIMIT 1", (m["id"],))
        nxt = int(a["rts"]) + 604800 if a and int(a["st"]) == 2 else 0
        return Reply({"sus": int(m["sus"]), "appeal": a, "next": nxt})


@registry.register
class Appeal(Action):
    """?a=appeal: ask for a suspension to be lifted."""
    name = "appeal"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        if int(m["sus"]) <= ctx.now:
            return Reply.error("Your account is not suspended.", 400)
        t = php_trim(ctx.form("txt")[:1000])
        if len(t) < 20:
            return Reply.error("Please write at least a couple of sentences (20 characters).", 400)
        a = db.one("SELECT st,rts FROM appeals WHERE uid=? ORDER BY id DESC LIMIT 1", (m["id"],))
        if a and int(a["st"]) == 0:
            return Reply.error("You already have an appeal waiting for review.", 400)
        if a and int(a["st"]) == 2 and int(a["rts"]) + 604800 > ctx.now:
            return Reply.error("Your last appeal was denied. You can appeal again after %s (UTC)." % _gmdate(int(a["rts"]) + 604800), 400)
        ctx.limits.throttle("appeal:%d" % m["id"], 3, 86400)
        db.execute("INSERT INTO appeals(uid,txt,ts) VALUES(?,?,?)", (m["id"], t, ctx.now))
        return Reply({"ok": 1})


@registry.register
class AppealResolve(Action):
    """?a=appealres: approve (lifts the suspension) or deny an appeal."""
    name = "appealres"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = _admin(ctx)
        a = db.one("SELECT a.id,a.uid,u.name FROM appeals a JOIN users u ON u.id=a.uid WHERE a.id=? AND a.st=0", (ctx.int_form("id"),))
        if not a:
            return Reply.error("That appeal was already handled.", 404)
        ok = ctx.flag("ok")
        note = php_trim(ctx.form("note")[:300])
        db.execute("UPDATE appeals SET st=?,note=?,rts=?,rby=? WHERE id=?", (1 if ok else 2, note, ctx.now, m["id"], a["id"]))
        if ok:
            db.execute("UPDATE users SET sus=0 WHERE id=?", (a["uid"],))
        ctx.adminlog.add(m, "approved appeal from" if ok else "denied appeal from", a["name"])
        return Reply({"ok": 1})


# ---------------------------------------------------------------- admin tools
@registry.register
class Suspend(Action):
    """?a=suspend: days>0 suspends (max 365), days<0 bans, 0 lifts."""
    name = "suspend"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = _admin(ctx)
        t = db.one("SELECT id,name FROM users WHERE name=?", (php_trim(ctx.form("name")),))
        if not t:
            return Reply.error("No such user.", 404)
        if int(t["id"]) == int(m["id"]) or ctx.users.is_admin(t):
            return Reply.error("Admins cannot be suspended.", 400)
        d = ctx.int_form("days")
        until = 2147483647 if d < 0 else (ctx.now + min(d, 365) * 86400 if d > 0 else 0)
        db.execute("UPDATE users SET sus=? WHERE id=?", (until, t["id"]))
        if until == 0:
            db.execute("UPDATE appeals SET st=1,rts=?,rby=? WHERE uid=? AND st=0", (ctx.now, m["id"], t["id"]))
        ctx.adminlog.add(m, "banned" if d < 0 else ("suspended %d days" % min(d, 365) if d > 0 else "lifted suspension on"), t["name"])
        return Reply({"ok": 1})


@registry.register
class Purge(Action):
    """?a=purge: ban a user and delete everything they made (spam waves). The account stays so the name stays reserved."""
    name = "purge"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = _admin(ctx)
        ctx.limits.throttle("purge:%d" % m["id"], 10, 3600)
        t = db.one("SELECT id,name FROM users WHERE name=?", (php_trim(ctx.form("name")),))
        if not t:
            return Reply.error("No such user.", 404)
        if int(t["id"]) == int(m["id"]) or ctx.users.is_admin(t):
            return Reply.error("Admins cannot be banned.", 400)
        i = int(t["id"])
        po = "(SELECT id FROM posts WHERE uid=%d)" % i
        co = "(SELECT id FROM comments WHERE uid=%d OR pid IN %s)" % (i, po)
        files = [r[0] for r in db.query("SELECT img FROM posts WHERE uid=? AND img!=''", (i,)).fetchall()]
        for sql in ("SELECT img FROM postimgs WHERE pid IN " + po, "SELECT img FROM pend WHERE uid=%d" % i,
                    "SELECT img FROM messages WHERE a=%d AND img!=''" % i, "SELECT img FROM gmessages WHERE uid=%d AND img!=''" % i):
            files += [r[0] for r in db.query(sql).fetchall()]
        np_ = int(db.value("SELECT COUNT(*) FROM posts WHERE uid=?", (i,), 0))
        nc = int(db.value("SELECT COUNT(*) FROM comments WHERE uid=?", (i,), 0))
        rp = ("(kind='user' AND tid=%d) OR (kind='post' AND tid IN %s) OR (kind='comment' AND tid IN (SELECT id FROM comments WHERE uid=%d)) "
              "OR (kind='mask' AND tid IN (SELECT id FROM masks WHERE uid=%d)) OR (kind='ask' AND tid IN (SELECT id FROM asks WHERE frm=%d))" % (i, po, i, i, i))
        with db.transaction():
            for r in db.all("SELECT DISTINCT kind,tid FROM reports WHERE " + rp):
                ctx.notes.reviewed(r["kind"], int(r["tid"]))
            db.execute("DELETE FROM reports WHERE uid=? OR " + rp, (i,))
            db.execute("DELETE FROM likes WHERE uid=? OR pid IN " + po, (i,))
            db.execute("DELETE FROM dislikes WHERE uid=? OR pid IN " + po, (i,))
            db.execute("DELETE FROM clikes WHERE uid=? OR cid IN " + co, (i,))
            db.execute("DELETE FROM cdislikes WHERE uid=? OR cid IN " + co, (i,))
            db.execute("DELETE FROM comments WHERE uid=? OR pid IN " + po, (i,))
            db.execute("DELETE FROM notifs WHERE (actor=? AND kind<>'gift') OR (kind NOT IN ('gift','gment','gall') AND pid>0 AND pid IN %s)" % po, (i,))
            db.execute("DELETE FROM postimgs WHERE pid IN " + po)
            db.execute("DELETE FROM posts WHERE uid=?", (i,))
            db.execute("DELETE FROM pend WHERE uid=?", (i,))
            db.execute("DELETE FROM messages WHERE a=?", (i,))
            db.execute("DELETE FROM gmessages WHERE uid=?", (i,))
            db.execute("DELETE FROM asks WHERE frm=?", (i,))
            db.execute("DELETE FROM friends WHERE a=? AND st=0", (i,))
            db.execute("UPDATE users SET sus=? WHERE id=?", (2147483647, i))
            Tidy(db).run()
        Tidy(db).run()
        ctx.media.remove(files)
        ctx.adminlog.add(m, "banned + deleted content of", t["name"])
        return Reply({"ok": 1, "posts": np_, "comments": nc})


@registry.register
class BadWordList(Action):
    """?a=bwlist"""
    name = "bwlist"

    def handle(self, ctx: Context) -> Reply:
        _admin(ctx)
        return Reply({"words": ctx.db.all("SELECT w,hold FROM badwords ORDER BY w")})


def _has_letter_or_digit(s: str) -> bool:
    return any(unicodedata.category(c)[0] in "LN" for c in s)


@registry.register
class BadWordAdd(Action):
    """?a=bwadd: add (or change) a blocked word; hold=1 holds the post back instead of just flagging it."""
    name = "bwadd"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = _admin(ctx)
        w = collapse_space(strip_invisible(ctx.form("w")))
        w = php_trim(w).lower()[:40]
        if len(w) < 2 or not _has_letter_or_digit(w):
            return Reply.error("Enter a word or phrase (at least 2 characters).", 400)
        if int(db.value("SELECT COUNT(*) FROM badwords", (), 0)) >= 200 and not db.value("SELECT 1 FROM badwords WHERE w=?", (w,)):
            return Reply.error("The list is full (200 words).", 400)
        db.execute("INSERT INTO badwords(w,hold) VALUES(?,?) ON CONFLICT(w) DO UPDATE SET hold=excluded.hold", (w, 1 if ctx.flag("hold") else 0))
        ctx.words.forget()
        ctx.adminlog.add(m, 'added word "%s"' % w[:24], "")
        return Reply({"ok": 1})


@registry.register
class BadWordDelete(Action):
    """?a=bwdel"""
    name = "bwdel"

    def handle(self, ctx: Context) -> Reply:
        m = _admin(ctx)
        w = php_trim(ctx.form("w")).lower()
        if ctx.db.execute("DELETE FROM badwords WHERE w=?", (w,)):
            ctx.words.forget()
            ctx.adminlog.add(m, 'removed word "%s"' % w[:22], "")
        return Reply({"ok": 1})


@registry.register
class RefreshSet(Action):
    """?a=rfset: set the refresh message and optionally make every open page reload."""
    name = "rfset"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = _admin(ctx)
        msg = php_trim(strip_controls(ctx.form("msg"))[:300])
        db.execute("INSERT OR REPLACE INTO site(k,v) VALUES('rfmsg',?)", (msg,))
        if ctx.flag("go"):
            db.execute("INSERT OR REPLACE INTO site(k,v) VALUES('rfv',?)", ("%d-%s" % (ctx.now, secrets.token_hex(3)),))
            ctx.adminlog.add(m, "forced refresh", "")
        return Reply(SiteSettings(db).refresh())


@registry.register
class AdminStats(Action):
    """?a=astats"""
    name = "astats"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        _admin(ctx)
        n = ctx.now
        d1, d7 = n - 86400, n - 604800
        day = n // 86400

        def c(sql, p=()):
            return int(db.value(sql, p, 0) or 0)

        def ser(tbl, col):
            out = [0] * 14
            for r in db.all("SELECT (%s/86400) d,COUNT(*) c FROM %s WHERE %s>=? GROUP BY d" % (col, tbl, col), ((day - 13) * 86400,)):
                k = 13 - (day - int(r["d"]))
                if 0 <= k < 14:
                    out[k] = int(r["c"])
            return out
        try:
            size = os.path.getsize(ctx.cfg.db_path)
        except OSError:
            size = 0
        return Reply({
            "users": c("SELECT COUNT(*) FROM users"),
            "new1": c("SELECT COUNT(*) FROM users WHERE ts>?", (d1,)),
            "new7": c("SELECT COUNT(*) FROM users WHERE ts>?", (d7,)),
            "act1": c("SELECT COUNT(*) FROM users WHERE la>?", (d1,)),
            "act7": c("SELECT COUNT(*) FROM users WHERE la>?", (d7,)),
            "now": c("SELECT COUNT(*) FROM users WHERE la>?", (n - 45,)),
            "posts": c("SELECT COUNT(*) FROM posts"),
            "posts1": c("SELECT COUNT(*) FROM posts WHERE ts>?", (d1,)),
            "posts7": c("SELECT COUNT(*) FROM posts WHERE ts>?", (d7,)),
            "com1": c("SELECT COUNT(*) FROM comments WHERE ts>?", (d1,)),
            "msg1": c("SELECT COUNT(*) FROM messages WHERE ts>?", (d1,)) + c("SELECT COUNT(*) FROM gmessages WHERE ts>?", (d1,)),
            "masks": c("SELECT COUNT(*) FROM masks"),
            "sus": c("SELECT COUNT(*) FROM users WHERE sus>?", (n,)),
            "rep": c("SELECT COUNT(*) FROM reports"),
            "app": c("SELECT COUNT(*) FROM appeals WHERE st=0"),
            "held": c("SELECT COUNT(*) FROM posts WHERE hold=1") + c("SELECT COUNT(*) FROM comments WHERE hold=1"),
            "db": size,
            "sg": ser("users", "ts"),
            "pg": ser("posts", "ts"),
            "day": day,
        })


@registry.register
class Backup(Action):
    """?a=backup: download a copy of the database."""
    name = "backup"

    def handle(self, ctx: Context) -> Reply:
        from ..background import BackupService
        m = _admin(ctx)
        ctx.limits.throttle("bk:%d" % m["id"], 5, 3600)
        svc = BackupService(ctx.cfg, ctx.db)
        svc.folder.mkdir(parents=True, exist_ok=True)
        tmp = svc.folder / ("dl-%s.db" % secrets.token_hex(6))
        try:
            svc.snapshot(tmp)
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            return Reply.error("Could not make a backup.", 500)
        ctx.adminlog.add(m, "downloaded backup", "")
        return FileReply(tmp, "masque-backup-%s.db" % time.strftime("%Y%m%d-%H%M%S", time.gmtime()))


@registry.register
class IpDiagnostics(Action):
    """?a=ipdiag: which address the app thinks the visitor has."""
    name = "ipdiag"

    def handle(self, ctx: Context) -> Reply:
        from flask import request
        _admin(ctx)
        hd = {k: request.headers.get(k) or "(not sent)" for k in ("X-Real-IP", "X-Forwarded-For", "True-Client-IP", "CF-Connecting-IP", "X-Forwarded-Proto")}
        return Reply({
            "ip_the_app_uses": ctx.ip.cip(),
            "connection_address": request.remote_addr or "",
            "IP_HEADER": os.environ.get("IP_HEADER") or "(not set)",
            "IP_HOPS": os.environ.get("IP_HOPS") or "(not set, 1)",
            "headers_received": hd,
            "note": "Open this from your own phone or computer. The real visitor IP should show up in one of the headers; "
                    "if ip_the_app_uses equals connection_address and that is not your IP, set IP_HEADER.",
        })


@registry.register
class Suggest(Action):
    """?a=suggest: people a new account might add (public, not suspended, not a friend or pending, nobody blocked)."""
    name = "suggest"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        i = int(m["id"])
        out = []
        for r in ctx.db.all(
                "SELECT u.id,u.name,u.nick,u.avatar,(SELECT COUNT(*) FROM posts p WHERE p.uid=u.id AND p.vis=0 AND p.hold=0 AND p.mid=0) pn FROM users u "
                "WHERE u.id<>? AND u.priv=0 AND u.sus<=? AND NOT EXISTS (SELECT 1 FROM friends f WHERE (f.a=u.id AND f.b=?) OR (f.b=u.id AND f.a=?)) "
                "ORDER BY (pn>0) DESC,u.la DESC LIMIT 30", (i, ctx.now, i, i)):
            if ctx.rel.blocked(i, int(r["id"])):
                continue
            out.append({"name": r["name"], "nick": r["nick"], "avatar": r["avatar"], "pn": int(r["pn"])})
            if len(out) >= 8:
                break
        return Reply({"list": out})


class ReportAction(Action):
    """Base for the admin buttons on one report: admin only, finds the report (kind and target) from the form id."""

    def report(self, ctx: Context):
        """(admin row, the report row or None)."""
        m = _admin(ctx)
        return m, ctx.db.one("SELECT kind,tid FROM reports WHERE id=?", (ctx.int_form("id"),))


@registry.register
class ReportDismiss(ReportAction):
    """?a=rdone: dismiss every report on one thing (a held post or comment is released again)."""
    name = "rdone"

    def handle(self, ctx: Context) -> Reply:
        m, r = self.report(ctx)
        db = ctx.db
        if r:
            kind, tid = r["kind"], int(r["tid"])
            ctx.adminlog.add(m, "dismissed reports on " + kind, ctx.adminlog.target_name(kind, tid))
            ctx.notes.reviewed(kind, tid)
            db.execute("DELETE FROM reports WHERE kind=? AND tid=?", (kind, tid))
            if kind == "ask":
                db.execute("DELETE FROM asks WHERE id=?", (tid,))
            if kind == "post":
                db.execute("UPDATE posts SET hold=0 WHERE id=?", (tid,))
            if kind == "comment":
                db.execute("UPDATE comments SET hold=0 WHERE id=?", (tid,))
        return Reply({"ok": 1})


@registry.register
class ReportDelete(ReportAction):
    """?a=rdel: delete the reported post, comment or ask, and close its reports."""
    name = "rdel"

    def handle(self, ctx: Context) -> Reply:
        from .posts import PostFiles
        m, r = self.report(ctx)
        db = ctx.db
        if r:
            kind, tid = r["kind"], int(r["tid"])
            ctx.adminlog.add(m, "deleted " + kind, ctx.adminlog.target_name(kind, tid))
            ctx.notes.reviewed(kind, tid)
            if kind == "post":
                PostFiles(ctx).delete_post(tid)
            if kind == "comment":
                db.execute("DELETE FROM comments WHERE id=?", (tid,))
                Tidy(db).run()
            if kind == "ask":
                db.execute("DELETE FROM asks WHERE id=?", (tid,))
            db.execute("DELETE FROM reports WHERE kind=? AND tid=?", (kind, tid))
        return Reply({"ok": 1})


@registry.register
class ReportBlur(ReportAction):
    """?a=rblur: blur (or unblur) the photo of a reported post."""
    name = "rblur"

    def handle(self, ctx: Context) -> Reply:
        m, r = self.report(ctx)
        db = ctx.db
        if not r or r["kind"] != "post":
            return Reply.error("Only reported posts can be blurred.", 400)
        pp = db.one("SELECT sens,img FROM posts WHERE id=?", (r["tid"],))
        if not pp:
            return Reply.error("That post no longer exists.", 404)
        if not pp["img"]:
            return Reply.error("That post has no photo.", 400)
        ns = 0 if int(pp["sens"]) == 2 else 2
        db.execute("UPDATE posts SET sens=? WHERE id=?", (ns, r["tid"]))
        ctx.adminlog.add(m, ("blurred" if ns == 2 else "unblurred") + " photo of post by", ctx.adminlog.target_name("post", r["tid"]))
        return Reply({"ok": 1, "sens": ns})
