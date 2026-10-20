"""Management system: dashboard (one per role), users CRUD (admins), posts and comments CRUD (moderators and admins).

Actions: dash, ulist, uget, uadd, uedit, udel, mposts, mpedit, mpdel, mcomments, mcedit, mcdel.

Masques stay hidden: a post or comment written as a Masque (or anonymously) is listed as "Masque" with no owner, never counts toward
a person's totals here, and the admin log names no owner for it.
"""
from ..accounts import AccountEraser
from ..php import php_trim
from ..streaks import Streaks
from ..tidy import Tidy
from .account import PasswordRules
from .base import Action, Context, Reply, registry

PAGE = 25
HIDDEN = "Masque"


def _staff(ctx: Context):
    m = ctx.users.need()
    if not m["mod"]:
        ctx.deny("Not allowed.", 403)
    return m


def _admin(ctx: Context):
    m = ctx.users.need()
    if not m["admin"]:
        ctx.deny("Not allowed.", 403)
    return m


def _page(ctx: Context) -> int:
    return max(0, ctx.int_form("page"))


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _count(db, sql, p=()):
    return int(db.value(sql, p, 0) or 0)


# ---------------------------------------------------------------- dashboards
@registry.register
class Dashboard(Action):
    """?a=mg_dash: the landing page for my role. Users see their own numbers, moderators the queue, admins the whole site."""
    name = "mg_dash"

    def handle(self, ctx: Context) -> Reply:
        db, m = ctx.db, ctx.users.need()
        me, n = int(m["id"]), ctx.now
        out = {"role": m["role"], "name": m["name"]}
        st = ctx.unlocks.stats(m)
        out["mine"] = {
            "posts": st["p"], "comments": st["c"], "likes": st["l"], "friends": st["f"], "best": st["s"], "days": st["d"],
            "streak": Streaks(db).calc(me)["cur"], "sigils": ctx.unlocks.balance(m, st),
            "requests": _count(db, "SELECT COUNT(*) FROM friends WHERE st=0 AND b=?", (me,)),
            "bell": _count(db, "SELECT COUNT(*) FROM notifs WHERE uid=? AND seen=0", (me,)),
            "unread": _count(db, "SELECT COUNT(*) FROM messages WHERE b=? AND seen=0", (me,)),
            "recent": db.all("SELECT p.id,substr(p.cap,1,80) cap,p.ts,(SELECT COUNT(*) FROM likes l WHERE l.pid=p.id) likes "
                             "FROM posts p WHERE p.uid=? ORDER BY p.id DESC LIMIT 5", (me,)),
        }
        if m["mod"]:
            out["queue"] = {
                "reports": _count(db, "SELECT COUNT(DISTINCT kind||':'||tid) FROM reports"),
                "appeals": _count(db, "SELECT COUNT(*) FROM appeals WHERE st=0"),
                "held": _count(db, "SELECT COUNT(*) FROM posts WHERE hold=1") + _count(db, "SELECT COUNT(*) FROM comments WHERE hold=1"),
                "suspended": _count(db, "SELECT COUNT(*) FROM users WHERE sus>?", (n,)),
            }
            out["actions"] = db.all("SELECT act,tgt,ts FROM alog WHERE aid=? ORDER BY id DESC LIMIT 8", (me,))
            out["flagged"] = self._flagged(db)
        if m["admin"]:
            out["site"] = {
                "users": _count(db, "SELECT COUNT(*) FROM users"),
                "mods": _count(db, "SELECT COUNT(*) FROM users WHERE role=1"),
                "new7": _count(db, "SELECT COUNT(*) FROM users WHERE ts>?", (n - 604800,)),
                "active1": _count(db, "SELECT COUNT(*) FROM users WHERE la>?", (n - 86400,)),
                "posts": _count(db, "SELECT COUNT(*) FROM posts"),
                "comments": _count(db, "SELECT COUNT(*) FROM comments"),
            }
            out["newest"] = db.all("SELECT name,nick,avatar,ts FROM users ORDER BY id DESC LIMIT 5")
        return Reply(out)

    _SNIP = {"post": "SELECT substr(cap,1,90) t,(img!='') himg FROM posts WHERE id=?", "comment": "SELECT substr(txt,1,90) t,0 himg FROM comments WHERE id=?",
             "ask": "SELECT substr(txt,1,90) t,0 himg FROM asks WHERE id=?"}

    @classmethod
    def _flagged(cls, db) -> list:
        """The newest reported things, one line each. Only the text and the reason: who wrote it is never shown here (Masque posts stay anonymous)."""
        out, seen = [], set()
        for r in db.all("SELECT kind,tid,why,ts FROM reports ORDER BY id DESC LIMIT 40"):
            key = "%s:%s" % (r["kind"], r["tid"])
            if key in seen:
                continue
            seen.add(key)
            q = cls._SNIP.get(r["kind"])
            row = db.one(q, (r["tid"],)) if q else None
            txt = (row["t"] if row else "") or ("(photo)" if row and int(row["himg"]) else "")
            out.append({"kind": r["kind"], "txt": txt, "why": (r["why"] or "")[:60], "ts": int(r["ts"] or 0)})
            if len(out) >= 5:
                break
        return out


# ---------------------------------------------------------------- users CRUD (admins)
def _user_row(ctx: Context, r: dict) -> dict:
    """One account as an admin sees it. Masque posts and comments are left out of the counts."""
    i = int(r["id"])
    return {
        "id": i, "name": r["name"], "nick": r["nick"], "role": ctx.users.role_of({"name": r["name"], "role": int(r["role"] or 0)}),
        "ts": int(r["ts"] or 0), "la": int(r["la"] or 0), "sus": int(r["sus"] or 0),
        "posts": _count(ctx.db, "SELECT COUNT(*) FROM posts WHERE uid=? AND mid=0 AND anon=0", (i,)),
        "comments": _count(ctx.db, "SELECT COUNT(*) FROM comments WHERE uid=? AND mid=0", (i,)),
    }


@registry.register
class UserList(Action):
    """?a=mg_ulist: every account with its role. q = part of a name, role = user|mod|admin|suspended, page = 0, 1, ..."""
    name = "mg_ulist"

    def handle(self, ctx: Context) -> Reply:
        _admin(ctx)
        q, want = php_trim(ctx.form("q"))[:20], ctx.form("role")
        sql, p = "SELECT id,name,nick,role,ts,la,sus FROM users", []
        if q:
            sql += " WHERE name LIKE ? ESCAPE '\\' OR nick LIKE ? ESCAPE '\\'"
            p += [_like(q), _like(q)]
        rows = [_user_row(ctx, r) for r in ctx.db.all(sql + " ORDER BY id DESC LIMIT 3000", tuple(p))]
        if want in ("user", "mod", "admin"):
            rows = [r for r in rows if r["role"] == want]
        elif want == "suspended":
            rows = [r for r in rows if r["sus"] > ctx.now]
        pg = _page(ctx)
        return Reply({"users": rows[pg * PAGE:(pg + 1) * PAGE], "total": len(rows), "page": pg, "per": PAGE})


@registry.register
class UserGet(Action):
    """?a=mg_uget: one account in detail (no Masque information)."""
    name = "mg_uget"

    def handle(self, ctx: Context) -> Reply:
        _admin(ctx)
        r = ctx.db.one("SELECT id,name,nick,role,ts,la,sus,bio,priv,askon,dm,mail FROM users WHERE name=?", (php_trim(ctx.form("name")),))
        if not r:
            return Reply.error("No such user.", 404)
        out = _user_row(ctx, r)
        i = int(r["id"])
        out.update({
            "bio": r["bio"], "priv": int(r["priv"]), "askon": int(r["askon"]), "dm": r["dm"], "hasmail": 1 if r["mail"] else 0,
            "friends": _count(ctx.db, "SELECT COUNT(*) FROM friends WHERE st=1 AND (a=? OR b=?)", (i, i)),
            "reports": _count(ctx.db, "SELECT COUNT(*) FROM reports WHERE kind='user' AND tid=?", (i,)),
        })
        return Reply(out)


@registry.register
class UserAdd(Action):
    """?a=mg_uadd: an admin creates an account (name, pw, role=user|mod). It has no recovery code; the person can make one after signing in."""
    name = "mg_uadd"

    def handle(self, ctx: Context) -> Reply:
        m = _admin(ctx)
        n, p, role = php_trim(ctx.form("name")), ctx.form("pw"), ctx.form("role", "user")
        if not ctx.names.valid(n):
            return Reply.error("Usernames are 3 to 20 letters, numbers or _.", 400)
        bad = PasswordRules.check(p)
        if bad:
            return bad
        if role not in ("user", "mod"):
            return Reply.error("Role must be user or mod.", 400)
        taken = Reply.error("That username is taken.", 409)
        if ctx.names.reserved(n) or ctx.names.clash(n, 0, True):
            return taken
        ctx.limits.throttle("uadd:%d" % m["id"], 30, 3600)
        nid = ctx.accounts.next_id_insert(n, ctx.hasher.hash(p))
        if nid == -1:
            return taken
        if nid == 0:
            return Reply.error("Please try again.", 503)
        if role == "mod":
            ctx.db.execute("UPDATE users SET role=1 WHERE id=?", (nid,))
        ctx.adminlog.add(m, "created account", n)
        return Reply({"ok": 1, "name": n, "role": role})


@registry.register
class UserEdit(Action):
    """?a=mg_uedit: change nick, bio, privacy, role, or set a new password (which signs that person out everywhere). Admins are managed on the server."""
    name = "mg_uedit"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = _admin(ctx)
        t = db.one("SELECT id,name FROM users WHERE name=?", (php_trim(ctx.form("name")),))
        if not t:
            return Reply.error("No such user.", 404)
        if ctx.users.is_admin(t):
            return Reply.error("Admin accounts are managed in the server settings.", 400)
        i, done = int(t["id"]), []
        if ctx.has_form("nick"):
            db.execute("UPDATE users SET nick=? WHERE id=?", (php_trim(ctx.form("nick"))[:30], i))
            done.append("nick")
        if ctx.has_form("bio"):
            db.execute("UPDATE users SET bio=? WHERE id=?", (php_trim(ctx.form("bio"))[:160], i))
            done.append("bio")
        if ctx.has_form("priv"):
            db.execute("UPDATE users SET priv=? WHERE id=?", (1 if ctx.flag("priv") else 0, i))
            done.append("privacy")
        if ctx.has_form("role"):
            role = ctx.form("role")
            if role not in ("user", "mod"):
                return Reply.error("Role must be user or mod.", 400)
            db.execute("UPDATE users SET role=? WHERE id=?", (1 if role == "mod" else 0, i))
            done.append("role")
        if ctx.form("pw") != "":
            bad = PasswordRules.check(ctx.form("pw"))
            if bad:
                return bad
            db.execute("UPDATE users SET pw=?,sv=sv+1 WHERE id=?", (ctx.hasher.hash(ctx.form("pw")), i))
            db.execute("DELETE FROM devices WHERE uid=?", (i,))
            done.append("password")
        if not done:
            return Reply.error("Nothing to change.", 400)
        ctx.adminlog.add(m, "edited " + ", ".join(done) + " of", t["name"])
        return Reply({"ok": 1, "changed": done})


@registry.register
class UserDelete(Action):
    """?a=mg_udel: delete an account and everything it made (the name stays reserved). Not yourself, not admins."""
    name = "mg_udel"

    def handle(self, ctx: Context) -> Reply:
        m = _admin(ctx)
        ctx.limits.throttle("udel:%d" % m["id"], 20, 3600)
        t = ctx.db.one("SELECT id,name FROM users WHERE name=?", (php_trim(ctx.form("name")),))
        if not t:
            return Reply.error("No such user.", 404)
        if int(t["id"]) == int(m["id"]) or ctx.users.is_admin(t):
            return Reply.error("Admin accounts cannot be deleted here.", 400)
        AccountEraser(ctx).erase(t["id"], t["name"])
        ctx.adminlog.add(m, "deleted account", t["name"])
        return Reply({"ok": 1})


# ---------------------------------------------------------------- posts and comments CRUD (moderators and admins)
def _protected(ctx: Context, m, owner: int, masked: bool) -> bool:
    """A moderator may not touch a moderator's or an admin's own content. (Masque content is never checked: that would show whose it is.)"""
    if masked or m["role"] == "admin":
        return False
    return ctx.users.is_mod({"id": owner}) and owner != int(m["id"])


@registry.register
class PostList(Action):
    """?a=mg_mposts: every post, newest first. q = words in the text."""
    name = "mg_mposts"

    def handle(self, ctx: Context) -> Reply:
        _staff(ctx)
        q, pg = php_trim(ctx.form("q"))[:40], _page(ctx)
        where, p = ("WHERE p.cap LIKE ? ESCAPE '\\'", [_like(q)]) if q else ("", [])
        total = _count(ctx.db, "SELECT COUNT(*) FROM posts p " + where, tuple(p))
        rows = ctx.db.all(
            "SELECT p.id,substr(p.cap,1,200) cap,p.ts,p.hold,p.vis,(p.mid>0 OR p.anon<>0) masked,u.name author,(p.img<>'') himg,"
            "(SELECT COUNT(*) FROM likes l WHERE l.pid=p.id) likes,(SELECT COUNT(*) FROM comments c WHERE c.pid=p.id) comments "
            "FROM posts p JOIN users u ON u.id=p.uid %s ORDER BY p.id DESC LIMIT ? OFFSET ?" % where, tuple(p) + (PAGE, pg * PAGE))
        for r in rows:
            r["masked"] = int(r["masked"])
            if r["masked"]:
                r["author"] = HIDDEN
        return Reply({"posts": rows, "total": total, "page": pg, "per": PAGE})


@registry.register
class PostEdit(Action):
    """?a=mg_mpedit: change the text of a post (for example to remove something). The author is not told."""
    name = "mg_mpedit"

    def handle(self, ctx: Context) -> Reply:
        m = _staff(ctx)
        r = ctx.db.one("SELECT id,uid,(mid>0 OR anon<>0) masked FROM posts WHERE id=?", (ctx.int_form("id"),))
        if not r:
            return Reply.error("That post no longer exists.", 404)
        text = php_trim(ctx.form("cap")[:1000])
        if text == "" and not ctx.db.value("SELECT 1 FROM posts WHERE id=? AND (img<>'' OR EXISTS(SELECT 1 FROM postimgs WHERE pid=posts.id))", (r["id"],)):
            return Reply.error("A post without a photo needs some text. Delete it instead.", 400)
        if _protected(ctx, m, int(r["uid"]), bool(r["masked"])):
            return Reply.error("Only an admin can change a moderator's or admin's post.", 403)
        ctx.db.execute("UPDATE posts SET cap=? WHERE id=?", (text, r["id"]))
        ctx.adminlog.add(m, "edited post by", HIDDEN if r["masked"] else ctx.adminlog.target_name("post", r["id"]))
        return Reply({"ok": 1})


@registry.register
class PostDelete(Action):
    """?a=mg_mpdel: delete a post with its photos, comments and reports."""
    name = "mg_mpdel"

    def handle(self, ctx: Context) -> Reply:
        from .posts import PostFiles
        m = _staff(ctx)
        r = ctx.db.one("SELECT id,uid,(mid>0 OR anon<>0) masked FROM posts WHERE id=?", (ctx.int_form("id"),))
        if not r:
            return Reply.error("That post no longer exists.", 404)
        if _protected(ctx, m, int(r["uid"]), bool(r["masked"])):
            return Reply.error("Only an admin can delete a moderator's or admin's post.", 403)
        who = HIDDEN if r["masked"] else ctx.adminlog.target_name("post", r["id"])
        ctx.notes.reviewed("post", int(r["id"]))
        PostFiles(ctx).delete_post(int(r["id"]))
        ctx.db.execute("DELETE FROM reports WHERE kind='post' AND tid=?", (r["id"],))
        ctx.adminlog.add(m, "deleted post by", who)
        return Reply({"ok": 1})


@registry.register
class CommentList(Action):
    """?a=mg_mcomments: every comment, newest first. q = words in the text."""
    name = "mg_mcomments"

    def handle(self, ctx: Context) -> Reply:
        _staff(ctx)
        q, pg = php_trim(ctx.form("q"))[:40], _page(ctx)
        where, p = ("WHERE c.txt LIKE ? ESCAPE '\\'", [_like(q)]) if q else ("", [])
        total = _count(ctx.db, "SELECT COUNT(*) FROM comments c " + where, tuple(p))
        rows = ctx.db.all(
            "SELECT c.id,c.pid,substr(c.txt,1,200) txt,c.ts,c.hold,(c.mid>0) masked,u.name author FROM comments c JOIN users u ON u.id=c.uid "
            "%s ORDER BY c.id DESC LIMIT ? OFFSET ?" % where, tuple(p) + (PAGE, pg * PAGE))
        for r in rows:
            r["masked"] = int(r["masked"])
            if r["masked"]:
                r["author"] = HIDDEN
        return Reply({"comments": rows, "total": total, "page": pg, "per": PAGE})


@registry.register
class CommentEdit(Action):
    """?a=mg_mcedit: change the text of a comment."""
    name = "mg_mcedit"

    def handle(self, ctx: Context) -> Reply:
        m = _staff(ctx)
        r = ctx.db.one("SELECT id,uid,(mid>0) masked FROM comments WHERE id=?", (ctx.int_form("id"),))
        if not r:
            return Reply.error("That comment no longer exists.", 404)
        text = php_trim(ctx.form("txt")[:300])
        if text == "":
            return Reply.error("A comment needs some text. Delete it instead.", 400)
        if _protected(ctx, m, int(r["uid"]), bool(r["masked"])):
            return Reply.error("Only an admin can change a moderator's or admin's comment.", 403)
        ctx.db.execute("UPDATE comments SET txt=? WHERE id=?", (text, r["id"]))
        ctx.adminlog.add(m, "edited comment by", HIDDEN if r["masked"] else ctx.adminlog.target_name("comment", r["id"]))
        return Reply({"ok": 1})


@registry.register
class CommentDelete(Action):
    """?a=mg_mcdel: delete a comment (replies to it go too)."""
    name = "mg_mcdel"

    def handle(self, ctx: Context) -> Reply:
        m = _staff(ctx)
        db = ctx.db
        r = db.one("SELECT id,uid,(mid>0) masked FROM comments WHERE id=?", (ctx.int_form("id"),))
        if not r:
            return Reply.error("That comment no longer exists.", 404)
        if _protected(ctx, m, int(r["uid"]), bool(r["masked"])):
            return Reply.error("Only an admin can delete a moderator's or admin's comment.", 403)
        who = HIDDEN if r["masked"] else ctx.adminlog.target_name("comment", r["id"])
        ctx.notes.reviewed("comment", int(r["id"]))
        db.execute("DELETE FROM comments WHERE id=? OR par=?", (r["id"], r["id"]))
        db.execute("DELETE FROM reports WHERE kind='comment' AND tid=?", (r["id"],))
        Tidy(db).run()
        ctx.adminlog.add(m, "deleted comment by", who)
        return Reply({"ok": 1})
