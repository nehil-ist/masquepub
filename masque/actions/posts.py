"""Posts, the feed, comments, likes, polls, pins, saves, hashtags and the mute lists (PHP: case 'feed' ... 'like')."""
import json
import re
import time

from ..feed import FeedFilter, FeedRanker, PostPresenter
from ..access import mqts
from ..mentions import hashtags
from ..media import IMG_NAME
from ..php import clamp_int, collapse_space, ids_sql, intval, php_trim
from ..prompts import DailyPrompt
from .base import Action, Context, Reply, registry

_TAG_OK = re.compile(r"^[a-z0-9_]{1,40}$")
_TOKEN = re.compile(r"^[a-f0-9]{32}$")
_ALT_NAME = re.compile(r"^[a-f0-9]{24}\.(jpg|png|webp|gif)$")


def _lower(s: str) -> str:
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)


def _json_list(raw):
    """json_decode(..., true) when it is a list (or any array), else None."""
    try:
        v = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return list(v.values())
    return None


def _alt_map(raw) -> dict:
    """PHP altmap(): {file name: description up to 200 characters}."""
    out = {}
    try:
        j = json.loads(str(raw or ""))
    except ValueError:
        return out
    if isinstance(j, dict):
        for k, v in j.items():
            if isinstance(k, str) and isinstance(v, str) and _ALT_NAME.match(k):
                v = collapse_space(v).strip()
                if v != "":
                    out[k] = v[:200]
    return out


def _caption(ctx: Context, name: str = "cap") -> str:
    return php_trim(ctx.form(name)[:300])


class PostFiles:
    """The photo files that belong to a post, and removing a post with everything that hangs on it."""

    def __init__(self, ctx: Context):
        self.ctx, self.db = ctx, ctx.db

    def of(self, pid: int) -> list:
        files = [r[0] for r in self.db.query("SELECT img FROM postimgs WHERE pid=?", (pid,)).fetchall()]
        i = self.db.value("SELECT img FROM posts WHERE id=?", (pid,))
        if i:
            files.append(i)
        return list(dict.fromkeys(files))

    def delete_post(self, pid: int):
        from ..tidy import Tidy
        files = self.of(pid)
        for sql in ("DELETE FROM posts WHERE id=?", "DELETE FROM likes WHERE pid=?", "DELETE FROM comments WHERE pid=?"):
            self.db.execute(sql, (pid,))
        Tidy(self.db).run()
        self.ctx.media.remove(files)


def _own_masque_id(ctx: Context, m) -> int:
    """The signed-in person's Masque id (stops the request when `as=mask` was asked for but they have none)."""
    mid = int(ctx.db.value("SELECT id FROM masks WHERE uid=?", (m["id"],), 0) or 0)
    if not mid:
        ctx.deny("Create your Masque first.", 400)
    return mid


@registry.register
class Feed(Action):
    """?a=feed  Home, profile, tag, saved, search, one Masque, one prompt day or one post; also the "new posts" counter and the daily prompt threads."""
    name = "feed"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.me()
        vid = int(m["id"]) if m else 0
        ff = FeedFilter(ctx, m).build()
        w, p = ff.sql, list(ff.params)
        home = ff.is_home
        newer = ctx.int_arg("newer")
        fy_ids = None
        if ctx.qflag("fy") and home and m and not ctx.qflag("cnt"):
            try:
                fy_ids = FeedRanker(ctx.db).rank(w, p, m, ctx.int_arg("before"), newer)
            except Exception:
                fy_ids = None  # if ranking ever fails, the list simply stays newest-first
            if fy_ids is not None:
                w += " AND p.id IN (%s)" % (ids_sql(fy_ids) if fy_ids else "0")
                newer = 0
        if fy_ids is None:
            if ctx.qflag("before"):
                w += " AND p.id<?"
                p.append(ctx.int_arg("before"))
            if newer > 0:  # post pager (PC): the one post right before / after a given post in this same list
                w += " AND p.id>?"
                p.append(newer)
        if ctx.qflag("cnt") and home:
            # "New posts" pill: how many posts arrived after the newest one the page has (capped at 21), through the SAME filters as the list
            w += " AND p.id>? AND p.uid<>?"
            p += [max(0, ctx.int_arg("after")), vid]
            n = ctx.db.value("SELECT COUNT(*) FROM (SELECT p.id FROM posts p JOIN users u ON u.id=p.uid LEFT JOIN masks mk ON mk.id=p.mid %s LIMIT 21)" % w, p, 0)
            return Reply({"n": int(n)})
        order = "ORDER BY p.id DESC LIMIT 21"
        top = ctx.int_arg("top")  # highlights: the most liked prompt answers of a day (span=1) or of the 7 days up to it (span=7)
        if ctx.qflag("u") and not top and ctx.arg("tab") == "q":
            if not ctx.qflag("before"):
                order = "ORDER BY p.qp DESC,p.id DESC LIMIT 21"
            else:
                w += " AND p.qp=0"
        elif ctx.qflag("u") and not top:
            if not ctx.qflag("before"):
                order = "ORDER BY (p.id=u.pin) DESC,p.id DESC LIMIT 21"
            else:
                w += " AND p.id!=u.pin"
        if top > 0:
            span = 7 if ctx.arg("span", "1") == "7" else 1
            w += " AND p.pd BETWEEN ? AND ? AND (SELECT COUNT(*) FROM likes l WHERE l.pid=p.id)>=1"
            p += [top - span + 1, top]
            order = "ORDER BY n DESC,p.id DESC LIMIT 6"
        if newer > 0:
            order = "ORDER BY p.id ASC LIMIT 2"
        rows = ctx.db.all(
            "SELECT p.id,p.uid,p.anon,p.cap,p.img,p.ts,p.ed,p.bg,p.hg,p.qp,p.aq,p.pd,p.mid,p.sens,p.hold,p.exp,p.vis,u.pin,mk.name mkn,mk.avatar mka,u.name,u.nick,u.avatar,"
            "(SELECT COUNT(*) FROM comments c WHERE c.pid=p.id AND c.hold=0) cc,(SELECT COUNT(*) FROM likes l WHERE l.pid=p.id) n,"
            "(SELECT COUNT(*) FROM likes l WHERE l.pid=p.id AND l.uid=?) me,"
            "(SELECT COUNT(*) FROM dislikes d WHERE d.pid=p.id AND d.uid=%(v)d) dv,(SELECT COUNT(*) FROM saves sx WHERE sx.pid=p.id AND sx.uid=%(v)d) sv,"
            "(SELECT COUNT(*) FROM postviews v WHERE v.pid=p.id) vw,(SELECT COUNT(*) FROM postviews v2 WHERE v2.pid=p.id AND v2.uid=%(v)d) vm "
            "FROM posts p JOIN users u ON u.id=p.uid LEFT JOIN masks mk ON mk.id=p.mid %(w)s %(o)s" % {"v": vid, "w": w, "o": order}, [vid, *p])
        if fy_ids:
            pos = {pid: i for i, pid in enumerate(fy_ids)}
            rows.sort(key=lambda r: pos.get(int(r["id"]), 0))
        PostPresenter(ctx.db).present(rows, vid, ctx.qflag("u"))
        tf = 0
        if ctx.qflag("t") and m:
            tf = int(ctx.db.value("SELECT COUNT(*) FROM tagfollows WHERE uid=? AND tag=?", (m["id"], _lower(ctx.arg("t"))), 0))
        threads = []
        if home and not ctx.qflag("before") and newer <= 0:
            threads = self._threads(ctx, ff, m)
        return Reply({"posts": rows[:20], "more": len(rows) > 20, "tf": tf, "threads": threads})

    @staticmethod
    def _threads(ctx: Context, ff: FeedFilter, m) -> list:
        """One thread per day of prompt answers (today and the two days before), with up to 3 faces."""
        out = []
        today = ctx.now // 86400
        w0, p0 = ff.home_sql, ff.home_params
        for z in ctx.db.all("SELECT p.pd d,COUNT(*) n FROM posts p JOIN users u ON u.id=p.uid LEFT JOIN masks mk ON mk.id=p.mid %s AND p.pd>=? GROUP BY p.pd ORDER BY p.pd DESC" % w0,
                            [*p0, today - 2]):
            d = int(z["d"])
            if d < 1 or d > today:
                continue
            who = {}
            for y in ctx.db.all("SELECT p.mid,u.name,u.avatar,mk.name mkn,mk.avatar mka FROM posts p JOIN users u ON u.id=p.uid LEFT JOIN masks mk ON mk.id=p.mid %s AND p.pd=? AND p.anon=0 ORDER BY p.id DESC LIMIT 12"
                                % w0, [*p0, d]):
                masked = int(y["mid"]) > 0
                k = ("m:" + str(y["mkn"])) if masked else ("u:" + str(y["name"]))
                if k in who:
                    continue
                who[k] = {"name": y["mkn"], "avatar": y["mka"], "mk": 1} if masked else {"name": y["name"], "avatar": y["avatar"], "mk": 0}
                if len(who) >= 3:
                    break
            out.append({"day": d, "text": DailyPrompt.for_day(d), "n": int(z["n"]), "who": list(who.values()),
                        "done": 1 if ctx.db.value("SELECT 1 FROM posts WHERE uid=? AND pd=?", (m["id"], d)) else 0})
        return out


@registry.register
class PendingUpload(Action):
    """?a=pup  A photo uploaded ahead of posting; it waits (up to 6 hours) until a post claims it."""
    name = "pup"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("pup:%d" % m["id"], 40, 600)
        for r in ctx.db.all("SELECT img FROM pend WHERE ts<?", (ctx.now - 21600,)):
            ctx.db.execute("DELETE FROM pend WHERE img=?", (r["img"],))
            ctx.media.remove([r["img"]])
        if not m["admin"] and int(ctx.db.value("SELECT COUNT(*) FROM pend WHERE uid=?", (m["id"],), 0)) >= 30:
            return Reply.error("Too many photos waiting. Post them or try again in a bit.", 429)
        name = ctx.media.save_img(ctx.file("img"))
        if not name:
            return Reply.error("No photo received.", 400)
        ctx.db.execute("INSERT INTO pend(img,uid,ts) VALUES(?,?,?)", (name, m["id"], ctx.now))
        return Reply({"img": name})


@registry.register
class NewPost(Action):
    """?a=post"""
    name = "post"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        ctx.limits.lim("post:%d" % m["id"], 20, 600, m, 5, 3600)
        cap = _caption(ctx)
        ctx.limits.nolinks(m, cap)
        pd, aq = 0, ""
        if ctx.flag("pd"):
            pd = ctx.now // 86400
            if db.value("SELECT 1 FROM posts WHERE uid=? AND pd=?", (m["id"], pd)):
                return Reply.error("You already answered today's prompt.", 400)
            aq = DailyPrompt.for_day(pd)
        mid = _own_masque_id(ctx, m) if ctx.form("as") == "mask" else 0
        images = []
        lst = _json_list(ctx.form("imgs", "[]"))
        for n in (lst or [])[:10]:
            if not isinstance(n, str) or not _ALT_NAME.match(n) or n in images:
                continue
            if not db.value("SELECT 1 FROM pend WHERE img=? AND uid=?", (n, m["id"])):
                return Reply.error("A photo expired. Please add it again.", 400)
            images.append(n)
        if not images:
            one = ctx.media.save_img(ctx.file("img"))
            if one:
                images.append(one)
        first = images[0] if images else ""
        if cap == "" and not first:
            return Reply.error("Add a photo or a caption.", 400)
        options, ends, multi = [], 0, 0
        if ctx.flag("poll"):
            pj = _json_list(ctx.form("poll"))
            for z in pj or []:
                if isinstance(z, str) and php_trim(z) != "":
                    options.append(php_trim(z)[:40])
            if len(options) < 2 or len(options) > 4:
                return Reply.error("A poll needs 2 to 4 options.", 400)
            if cap == "":
                return Reply.error("Write the question for your poll.", 400)
            if first or pd:
                return Reply.error("A poll can't have photos.", 400)
            ends = ctx.int_form("pend")
            if ends != 0 and (ends < 600 or ends > 2592000):
                return Reply.error("Pick how long the poll stays open.", 400)
            multi = 1 if ctx.flag("pmulti") else 0
        anon = 0  # anonymous posting was removed: a post is from you or from your Masque (old anonymous posts still show, and can still be revealed)
        bg = 0 if first else clamp_int(ctx.form("bg"), 0, 7)
        sens = 1 if (first and ctx.flag("sens")) else 0
        vis = clamp_int(ctx.form("vis"), 0, 2)
        if vis == 1 and mid:
            return Reply.error("Masque posts can't be friends-only, because that would show whose Masque it is. Pick Everyone or Only me.", 400)
        ev = ctx.form("exp")
        ex = 0
        if ev == "24h":
            ex = 86400
        elif ev == "7d":
            ex = 604800
        elif re.fullmatch(r"\d{1,8}", ev) and int(ev) > 0:
            ex = max(60, min(2592000, int(ev)))
        now = ctx.now
        cur = db.query("INSERT INTO posts(uid,cap,img,ts,anon,bg,aq,pd,mid,sens,exp,vis,hg) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (m["id"], cap, first, now, anon, bg, aq, pd, mid, sens, now + ex if ex else 0, vis,
                        0 if (first or ctx.form("hg", "1") == "0") else 1))
        pid = int(cur.lastrowid)
        alts = _alt_map(ctx.form("alts"))
        for k, n in enumerate(images):
            db.execute("INSERT INTO postimgs(pid,pos,img,alt) VALUES(?,?,?,?)", (pid, k, n, alts.get(n, "")))
            db.execute("DELETE FROM pend WHERE img=?", (n,))
        if pd:
            db.execute("INSERT OR IGNORE INTO pstreak VALUES(?,?)", (m["id"], pd))
        for k, z in enumerate(options):
            db.execute("INSERT INTO polls(pid,pos,txt) VALUES(?,?,?)", (pid, k, z))
        if options:
            db.execute("INSERT OR REPLACE INTO pollmeta(pid,ends,multi) VALUES(?,?,?)", (pid, now + ends if ends > 0 else 0, multi))
        ctx.tags.set(pid, cap)
        held = ctx.words.apply("post", pid, cap, m)
        if not anon and not held and vis == 0:
            ctx.mentions.in_post(pid, cap, m["id"], "", 0, mid)
            ctx.tags.notify_followers(pid, cap, m["id"], mid)
        return Reply({"ok": 1, "hold": held})


@registry.register
class DeletePost(Action):
    """?a=del  Your own post (admins can delete anyone's, and it is written to the admin log)."""
    name = "del"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        pid = ctx.int_form("id")
        if m["admin"]:
            r = ctx.db.one("SELECT img,uid FROM posts WHERE id=?", (pid,))
        else:
            r = ctx.db.one("SELECT img FROM posts WHERE id=? AND uid=?", (pid, m["id"]))
        if r:
            if m["admin"] and int(r["uid"]) != int(m["id"]):
                ctx.adminlog.add(m, "deleted post", ctx.adminlog.target_name("post", pid))
            PostFiles(ctx).delete_post(pid)
        return Reply({"ok": 1})


@registry.register
class EditHistory(Action):
    """?a=pedhist  Earlier versions of a post's text; shown to anyone who is allowed to see the post."""
    name = "pedhist"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("peh:%d" % m["id"], 60, 600)
        pid = ctx.int_arg("id")
        r = ctx.db.one("SELECT uid,cap,ed,ts,hold,mid,anon FROM posts WHERE id=?", (pid,))
        own = bool(r) and int(r["uid"]) == int(m["id"])
        if not r or not ctx.access.can_view(pid, int(m["id"])) or (int(r["hold"]) and not own and not m["admin"]):
            return Reply.error("Post not found.", 404)
        rt = mqts if (not own and (int(r["mid"]) > 0 or int(r["anon"]))) else (lambda t: int(t))
        versions = ctx.db.all("SELECT cap,ts FROM pedits WHERE pid=? ORDER BY id DESC", (pid,))
        return Reply({"cur": {"cap": str(r["cap"] or ""), "ts": rt(max(int(r["ed"]), int(r["ts"])))}, "ts0": rt(r["ts"]),
                      "v": [{"cap": z["cap"], "ts": rt(z["ts"])} for z in versions], "own": 1 if own else 0})


@registry.register
class ClearEditHistory(Action):
    """?a=pedclear  The author (or an admin) can remove the earlier versions, for example if something private was posted by mistake."""
    name = "pedclear"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        pid = ctx.int_form("id")
        r = ctx.db.one("SELECT uid FROM posts WHERE id=?", (pid,))
        if not r or (int(r["uid"]) != int(m["id"]) and not m["admin"]):
            return Reply.error("Post not found.", 404)
        ctx.db.execute("DELETE FROM pedits WHERE pid=?", (pid,))
        if int(r["uid"]) != int(m["id"]):
            ctx.adminlog.add(m, "cleared edit history", ctx.adminlog.target_name("post", pid))
        return Reply({"ok": 1})


@registry.register
class Unmask(Action):
    """?a=unmask  Reveal an old anonymous post as your own."""
    name = "unmask"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        pid = ctx.int_form("id")
        r = ctx.db.one("SELECT anon FROM posts WHERE id=? AND uid=?", (pid, m["id"]))
        if not r:
            return Reply.error("Not found.", 404)
        if not int(r["anon"]):
            return Reply.error("This post is not anonymous.", 400)
        if not ctx.flag("confirm"):
            return Reply.error("Please confirm.", 400)
        ctx.db.execute("UPDATE posts SET anon=0 WHERE id=?", (pid,))
        return Reply({"ok": 1})


@registry.register
class EditPost(Action):
    """?a=edit"""
    name = "edit"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        ctx.limits.lim("ed:%d" % m["id"], 30, 600, m, 10, 600)
        pid = ctx.int_form("id")
        cap = _caption(ctx)
        ctx.limits.nolinks(m, cap)
        r = db.one("SELECT img,cap,anon,mid,sens,hold,vis,ed,ts FROM posts WHERE id=? AND uid=?", (pid, m["id"]))
        if not r:
            return Reply.error("Post not found.", 404)
        vis = clamp_int(ctx.form("vis"), 0, 2) if ctx.has_form("vis") else int(r["vis"])
        if vis == 1 and (int(r["mid"]) or int(r["anon"])):
            return Reply.error("Masque posts can't be friends-only, because that would show whose Masque it is. Pick Everyone or Only me.", 400)
        # photos: when "imgs" is sent it is the post's full new list (order = display order, first = cover)
        old = PostFiles(ctx).of(pid)
        new = None
        if ctx.has_form("imgs"):
            new = []
            for n in (_json_list(ctx.form("imgs")) or [])[:10]:
                if not isinstance(n, str) or not _ALT_NAME.match(n) or n in new:
                    continue
                if n not in old and not db.value("SELECT 1 FROM pend WHERE img=? AND uid=?", (n, m["id"])):
                    return Reply.error("A photo expired. Please add it again.", 400)
                new.append(n)
        has = bool(r["img"]) if new is None else len(new) > 0
        if cap == "" and not has:
            return Reply.error("A post with no photo needs a caption.", 400)
        existing = db.pairs("SELECT img,alt FROM postimgs WHERE pid=?", (pid,))
        alts = _alt_map(ctx.form("alts")) if ctx.has_form("alts") else {k: str(v) for k, v in existing.items() if str(v or "") != ""}
        if new is not None:
            db.execute("DELETE FROM postimgs WHERE pid=?", (pid,))
            for k, n in enumerate(new):
                db.execute("INSERT INTO postimgs(pid,pos,img,alt) VALUES(?,?,?,?)", (pid, k, n, alts.get(n, "")))
                db.execute("DELETE FROM pend WHERE img=?", (n,))
            db.execute("UPDATE posts SET img=? WHERE id=?", (new[0] if new else "", pid))
            ctx.media.remove([f for f in old if f not in new])
        sens = int(r["sens"])
        if not has:
            sens = 0
        elif ctx.has_form("sens") and sens != 2:  # an admin's blur (2) can't be removed by the author
            sens = 1 if ctx.flag("sens") else 0
        # edit history: when the text really changes, the old text is kept (with the time it went live). Newest 20 are kept. Photos are not kept.
        if cap != str(r["cap"] or "") and php_trim(r["cap"] or "") != "":
            db.execute("INSERT INTO pedits(pid,cap,ts) VALUES(?,?,?)", (pid, str(r["cap"]), max(int(r["ed"]), int(r["ts"]))))
            db.execute("DELETE FROM pedits WHERE pid=? AND id NOT IN (SELECT id FROM pedits WHERE pid=? ORDER BY id DESC LIMIT 20)", (pid, pid))
        now = ctx.now
        db.execute("UPDATE posts SET cap=?,ed=?,sens=?,vis=? WHERE id=?", (cap, now, sens, vis, pid))
        ctx.tags.set(pid, cap)
        held = ctx.words.apply("post", pid, cap, m) if cap != str(r["cap"] or "") else int(r["hold"])
        if not int(r["anon"]) and not held and vis == 0:
            ctx.mentions.in_post(pid, cap, m["id"], str(r["cap"] or ""), 0, int(r["mid"]))
        return Reply({"vis": vis, "cap": cap, "ed": now, "imgs": new,
                      "alts": None if new is None else [alts.get(n, "") for n in new], "sens": sens, "hold": held})


@registry.register
class Comments(Action):
    """?a=comments  The comments under a post."""
    name = "comments"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        pid, vid = ctx.int_arg("pid"), int(m["id"])
        po = db.one("SELECT uid,anon,mid FROM posts WHERE id=?", (pid,))
        if not po or not ctx.access.can_view(pid, vid) or (not int(po["mid"]) and not int(po["anon"]) and ctx.rel.blocked(vid, po["uid"])):
            return Reply.error("Post not found.", 404)
        rows = db.all(
            "SELECT c.id,c.par,c.txt,c.ts,c.ed,c.uid,c.mid,c.hold,mk.name mkn,mk.avatar mka,u.name,u.nick,u.avatar,(c.uid=?) mine,"
            "(SELECT COUNT(*) FROM clikes k WHERE k.cid=c.id) n,(SELECT COUNT(*) FROM clikes k WHERE k.cid=c.id AND k.uid=?) lk,"
            "(SELECT COUNT(*) FROM cdislikes k WHERE k.cid=c.id AND k.uid=?) dv FROM comments c JOIN users u ON u.id=c.uid LEFT JOIN masks mk ON mk.id=c.mid "
            "WHERE c.pid=? AND (c.mid>0 OR c.uid NOT IN (SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?)) "
            "AND (c.mid=0 OR c.mid NOT IN (SELECT kid FROM mblocks WHERE a=?)) AND (c.hold=0 OR c.uid=? OR CAST(? AS INTEGER)=1) ORDER BY c.id ASC LIMIT 500",
            (vid, vid, vid, pid, vid, vid, vid, vid, 1 if m["admin"] else 0))
        hidden_count = 0
        if int(po["uid"]) == vid:
            # On your own post, comments from people or with words you muted are left out (and so are replies under them).
            hide = set()
            for c0 in rows:
                if int(c0["uid"]) != vid and ctx.mutelist.hits(vid, c0["uid"], c0["txt"]):
                    hide.add(int(c0["id"]))
            for c0 in rows:
                if int(c0["par"]) and int(c0["par"]) in hide:
                    hide.add(int(c0["id"]))
            if hide:
                rows = [c0 for c0 in rows if int(c0["id"]) not in hide]
                hidden_count = len(hide)
        for c in rows:
            if int(c["mid"]) > 0:
                c["name"], c["nick"], c["avatar"], c["mk"] = c["mkn"], "", c["mka"], 1
            else:
                c["mk"] = 0
            for k in ("mid", "mkn", "mka"):
                del c[k]
            by_anon_author = int(po["anon"]) and int(c["uid"]) == int(po["uid"])
            if by_anon_author and vid != int(po["uid"]):
                c["name"], c["nick"], c["avatar"] = "", "", ""
            if not int(c["mine"]) and (int(c["mk"]) or by_anon_author):
                c["ts"] = mqts(c["ts"])
                if int(c["ed"]):
                    c["ed"] = mqts(c["ed"])
            del c["uid"]
        return Reply({"comments": rows, "owner": 1 if int(po["uid"]) == vid else 0, "hid": hidden_count})


@registry.register
class NewComment(Action):
    """?a=comment"""
    name = "comment"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        pid = ctx.int_form("pid")
        text = php_trim(ctx.form("txt")[:300])
        po = db.one("SELECT uid,anon,mid FROM posts WHERE id=?", (pid,))
        if not po or not ctx.access.can_view(pid, m["id"]) or (not int(po["mid"]) and not int(po["anon"]) and ctx.rel.blocked(m["id"], po["uid"])):
            return Reply.error("Post not found.", 404)
        if text == "":
            return Reply.error("Write something first.", 400)
        # Commenting as the mask is opt-in. The owner of a mask's post always replies as that mask, so the two are never shown together.
        mid = _own_masque_id(ctx, m) if ctx.form("as") == "mask" else 0
        if int(po["mid"]) > 0 and int(po["uid"]) == int(m["id"]):
            mid = int(po["mid"])
        ctx.limits.nolinks(m, text)
        if not m["admin"]:
            new = ctx.limits.is_new(m)
            now = ctx.now
            per_min = int(db.value("SELECT COUNT(*) FROM comments WHERE uid=? AND ts>?", (m["id"], now - 60), 0))
            per_hour = int(db.value("SELECT COUNT(*) FROM comments WHERE uid=? AND ts>?", (m["id"], now - 3600), 0)) if new else 0
            if per_min >= (5 if new else 10) or (new and per_hour >= 30):
                return Reply.error("New accounts have lower limits for the first day. Try again in a bit." if new else "Slow down a little, then try again.", 429)
        # Replies are one level deep: replying to a reply attaches to the same top comment.
        par = ctx.int_form("par")
        top, reply_to = 0, 0
        if par:
            pr = db.one("SELECT uid,par FROM comments WHERE id=? AND pid=?", (par, pid))
            if not pr:
                return Reply.error("That comment no longer exists.", 404)
            top = int(pr["par"]) or par
            reply_to = int(pr["uid"])
        cid = int(db.query("INSERT INTO comments(pid,uid,txt,ts,par,mid) VALUES(?,?,?,?,?,?)", (pid, m["id"], text, ctx.now, top, mid)).lastrowid)
        held = ctx.words.apply("comment", cid, text, m)
        # The author of an anonymous post commenting on it sends no notifications, since those would name them. Held comments send none either.
        if not held and not (int(po["anon"]) and int(po["uid"]) == int(m["id"])):
            if reply_to and not ctx.mutelist.hits(reply_to, m["id"], text):
                ctx.notes.note(reply_to, "reply", m["id"], pid, mid)
            if int(po["uid"]) != reply_to and not ctx.mutelist.hits(po["uid"], m["id"], text):
                ctx.notes.note(int(po["uid"]), "comment", m["id"], pid, mid)
            ctx.mentions.in_post(pid, text, m["id"], "", reply_to or int(po["uid"]), mid)
        return Reply({"ok": 1, "id": cid, "hold": held})


@registry.register
class EditComment(Action):
    """?a=editc"""
    name = "editc"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.lim("ed:%d" % m["id"], 30, 600, m, 10, 600)
        cid = ctx.int_form("id")
        text = php_trim(ctx.form("txt")[:300])
        ctx.limits.nolinks(m, text)
        if text == "":
            return Reply.error("A comment cannot be empty. Delete it instead.", 400)
        old = ctx.db.one("SELECT txt,hold FROM comments WHERE id=? AND uid=?", (cid, m["id"]))
        if not old:
            return Reply.error("Comment not found.", 404)
        ctx.db.execute("UPDATE comments SET txt=?,ed=? WHERE id=? AND uid=?", (text, ctx.now, cid, m["id"]))
        held = ctx.words.apply("comment", cid, text, m) if text != str(old["txt"] or "") else int(old["hold"])
        return Reply({"txt": text, "ed": ctx.now, "hold": held})


@registry.register
class DeleteComment(Action):
    """?a=delc  Your comment, a comment on your post, or (admin) any comment."""
    name = "delc"

    def handle(self, ctx: Context) -> Reply:
        from ..tidy import Tidy
        m = ctx.users.need()
        cid = ctx.int_form("id")
        if m["admin"]:
            cu = ctx.db.value("SELECT uid FROM comments WHERE id=?", (cid,))
            if cu is not None and int(cu) != int(m["id"]):
                ctx.adminlog.add(m, "deleted comment", ctx.adminlog.target_name("comment", cid))
            ctx.db.execute("DELETE FROM comments WHERE id=?", (cid,))
        else:
            ctx.db.execute("DELETE FROM comments WHERE id=? AND (uid=? OR pid IN (SELECT id FROM posts WHERE uid=?))", (cid, m["id"], m["id"]))
        Tidy(ctx.db).run()
        return Reply({"ok": 1})


@registry.register
class CommentLike(Action):
    """?a=clike"""
    name = "clike"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        cid = ctx.int_form("id")
        c = db.one("SELECT uid,pid,mid FROM comments WHERE id=?", (cid,))
        if not c or not ctx.access.can_view(c["pid"], m["id"]) or (not int(c["mid"]) and ctx.rel.blocked(m["id"], c["uid"])):
            return Reply.error("Comment not found.", 404)
        mid = _own_masque_id(ctx, m) if ctx.form("as") == "mask" else 0
        if db.execute("DELETE FROM clikes WHERE cid=? AND uid=?", (cid, m["id"])) == 0:
            ctx.limits.lim("lk:%d" % m["id"], 120, 600, m, 30, 600)
            db.execute("INSERT OR IGNORE INTO clikes VALUES(?,?)", (cid, m["id"]))
            db.execute("DELETE FROM cdislikes WHERE cid=? AND uid=?", (cid, m["id"]))
            ctx.notes.note(c["uid"], "clike", m["id"], c["pid"], mid)
        return Reply({"ok": 1})


@registry.register
class CommentDislike(Action):
    """?a=cdislike  A quiet downvote on a Masque comment (takes 1 point off that Masque's reputation; never shown, no alerts)."""
    name = "cdislike"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        cid = ctx.int_form("id")
        c = db.one("SELECT uid,pid,mid FROM comments WHERE id=?", (cid,))
        if not c or not ctx.access.can_view(c["pid"], m["id"]) or (not int(c["mid"]) and ctx.rel.blocked(m["id"], c["uid"])):
            return Reply.error("Comment not found.", 404)
        if int(c["mid"]) <= 0:
            return Reply.error("Only Masque comments can be downvoted.", 400)
        if int(c["uid"]) == int(m["id"]):
            return Reply.error("You can't downvote your own comment.", 400)
        if db.execute("DELETE FROM cdislikes WHERE cid=? AND uid=?", (cid, m["id"])) == 0:
            ctx.limits.throttle("dv:%d" % m["id"], 60, 3600)
            db.execute("INSERT OR IGNORE INTO cdislikes VALUES(?,?)", (cid, m["id"]))
            db.execute("DELETE FROM clikes WHERE cid=? AND uid=?", (cid, m["id"]))
        return Reply({"ok": 1})


@registry.register
class Like(Action):
    """?a=like  Mark a post with a sigil (or take it back)."""
    name = "like"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        pid = ctx.int_form("id")
        if not ctx.access.can_view(pid, m["id"]):
            return Reply.error("Post not found.", 404)
        # Liking as the mask is opt-in (as=mask). The alert carries the mask instead of your name. If the mask is gone we refuse rather than fall back to your real name.
        mid = _own_masque_id(ctx, m) if ctx.form("as") == "mask" else 0
        if db.execute("DELETE FROM likes WHERE pid=? AND uid=?", (pid, m["id"])) == 0:
            ctx.limits.lim("lk:%d" % m["id"], 120, 600, m, 30, 600)
            db.execute("INSERT OR IGNORE INTO likes VALUES(?,?)", (pid, m["id"]))
            db.execute("DELETE FROM dislikes WHERE pid=? AND uid=?", (pid, m["id"]))
            ctx.notes.note(db.value("SELECT uid FROM posts WHERE id=?", (pid,)), "like", m["id"], pid, mid)
        return Reply({"ok": 1})


@registry.register
class Dislike(Action):
    """?a=dislike  A quiet downvote on a Masque post."""
    name = "dislike"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        pid = ctx.int_form("id")
        if not ctx.access.can_view(pid, m["id"]):
            return Reply.error("Post not found.", 404)
        po = db.one("SELECT uid,mid FROM posts WHERE id=?", (pid,))
        if not po:
            return Reply.error("Post not found.", 404)
        if int(po["mid"]) <= 0:
            return Reply.error("Only Masque posts can be downvoted.", 400)
        if int(po["uid"]) == int(m["id"]):
            return Reply.error("You can't downvote your own post.", 400)
        if db.execute("DELETE FROM dislikes WHERE pid=? AND uid=?", (pid, m["id"])) == 0:
            ctx.limits.throttle("dv:%d" % m["id"], 60, 3600)
            db.execute("INSERT OR IGNORE INTO dislikes VALUES(?,?)", (pid, m["id"]))
            db.execute("DELETE FROM likes WHERE pid=? AND uid=?", (pid, m["id"]))
        return Reply({"ok": 1})


@registry.register
class SavePost(Action):
    """?a=save  Bookmark a post (or remove the bookmark)."""
    name = "save"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("save:%d" % m["id"], 120, 600)
        pid = ctx.int_form("id")
        if not ctx.access.can_view(pid, m["id"]):
            return Reply.error("Post not found.", 404)
        if ctx.db.value("SELECT 1 FROM saves WHERE uid=? AND pid=?", (m["id"], pid)):
            ctx.db.execute("DELETE FROM saves WHERE uid=? AND pid=?", (m["id"], pid))
            return Reply({"on": 0})
        ctx.db.execute("INSERT INTO saves(uid,pid,ts) VALUES(?,?,?)", (m["id"], pid, ctx.now))
        return Reply({"on": 1})


@registry.register
class ViewPosts(Action):
    """?a=view  The feed reports posts that were really on screen for a moment; each person counts once per post and never for their own posts."""
    name = "view"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.lim("vw:%d" % m["id"], 600, 600, m, 200, 600)
        ids = []
        for x in ctx.form("ids").split(","):
            i = intval(x)
            if i and i not in ids:
                ids.append(i)
        n = 0
        for pid in ids[:12]:
            if pid < 1 or not ctx.access.can_view(pid, m["id"]):
                continue
            if int(ctx.db.value("SELECT uid FROM posts WHERE id=?", (pid,), 0) or 0) == int(m["id"]):
                continue
            n += ctx.db.execute("INSERT OR IGNORE INTO postviews VALUES(?,?,?)", (pid, m["id"], ctx.now))
        return Reply({"ok": 1, "n": n})


@registry.register
class TagFollow(Action):
    """?a=tagfollow  Follow or unfollow a hashtag."""
    name = "tagfollow"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        tag = _lower(php_trim(ctx.form("tag")))
        if not _TAG_OK.match(tag):
            return Reply.error("Bad tag.", 400)
        if ctx.db.execute("DELETE FROM tagfollows WHERE uid=? AND tag=?", (m["id"], tag)):
            return Reply({"tf": 0})
        if not m["admin"] and int(ctx.db.value("SELECT COUNT(*) FROM tagfollows WHERE uid=?", (m["id"],), 0)) >= 30:
            return Reply.error("You can follow up to 30 tags.", 400)
        ctx.db.execute("INSERT OR IGNORE INTO tagfollows VALUES(?,?)", (m["id"], tag))
        return Reply({"tf": 1})


@registry.register
class TrendingTags(Action):
    """?a=tags  The tags used most this week on public posts."""
    name = "tags"

    def handle(self, ctx: Context) -> Reply:
        ctx.users.need()
        return Reply({"tags": ctx.db.all(
            "SELECT t.tag,COUNT(*) n FROM posttags t JOIN posts p ON p.id=t.pid JOIN users u ON u.id=p.uid WHERE u.priv=0 AND p.vis=0 AND p.hold=0 AND p.ts>? "
            "GROUP BY t.tag ORDER BY n DESC,t.tag LIMIT 12", (ctx.now - 604800,))})


class PollRules:
    """Shared checks for the three poll actions."""

    def __init__(self, ctx: Context):
        self.ctx, self.db = ctx, ctx.db

    def open_poll(self, m, pid: int, ended_msg: str):
        """Returns (author id, meta) or stops the request when the post is not visible, held, or the poll has ended."""
        if not self.ctx.access.can_view(pid, m["id"]):
            self.ctx.deny("Post not found.", 404)
        author = self.db.value("SELECT uid FROM posts WHERE id=? AND hold=0", (pid,))
        if author is None:
            self.ctx.deny("Post not found.", 404)
        meta = self.db.one("SELECT ends,multi FROM pollmeta WHERE pid=?", (pid,)) or {"ends": 0, "multi": 0}
        if int(meta["ends"]) > 0 and self.ctx.now >= int(meta["ends"]):
            self.ctx.deny(ended_msg, 409)
        return int(author), meta

    def counts(self, pid: int) -> list:
        return [int(r[0]) for r in self.db.query("SELECT n FROM polls WHERE pid=? ORDER BY pos", (pid,)).fetchall()]

    @staticmethod
    def receipt(pid: int, opt, token: str) -> str:
        import hashlib
        return hashlib.sha256(("%d|%d|%s" % (pid, opt, token)).encode()).hexdigest()


@registry.register
class PollVote(Action):
    """?a=pvote"""
    name = "pvote"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        ctx.limits.throttle("pv:%d" % m["id"], 60, 600)
        pid = ctx.int_form("id")
        rules = PollRules(ctx)
        _, meta = rules.open_poll(m, pid, "This poll has ended.")
        # one option for a normal poll; for a "pick several" poll the browser sends the whole choice at once so nobody can stack votes on one option
        if int(meta["multi"]):
            raw = _json_list(ctx.form("opts", "[]"))
            chosen = list(dict.fromkeys(intval(x) for x in raw)) if raw is not None else []
        else:
            chosen = [ctx.int_form("opt", -1)]
        if not chosen:
            return Reply.error("Pick at least one option.", 400)
        for op in chosen:
            if not db.value("SELECT 1 FROM polls WHERE pid=? AND pos=?", (pid, op)):
                return Reply.error("No such option.", 400)
        with db.transaction():
            if db.execute("INSERT OR IGNORE INTO pollvoted VALUES(?,?)", (pid, m["id"])):
                token = ctx.form("t")
                for op in chosen:
                    db.execute("UPDATE polls SET n=n+1 WHERE pid=? AND pos=?", (pid, op))
                    if _TOKEN.match(token):
                        db.execute("INSERT OR IGNORE INTO pollrx(pid,h) VALUES(?,?)", (pid, rules.receipt(pid, op, token)))
        return Reply({"poll": {"v": 1, "n": rules.counts(pid)}})


@registry.register
class PollResults(Action):
    """?a=pres  Results of a poll that has ended (a page that was open when the time ran out asks for them)."""
    name = "pres"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        pid = ctx.int_form("id")
        if not ctx.access.can_view(pid, m["id"]):
            return Reply.error("Post not found.", 404)
        ends = int(ctx.db.value("SELECT ends FROM pollmeta WHERE pid=?", (pid,), 0) or 0)
        if ends <= 0 or ctx.now < ends:
            return Reply.error("Still open.", 409)
        return Reply({"poll": {"n": PollRules(ctx).counts(pid)}})


@registry.register
class PollChange(Action):
    """?a=pchange  Change your vote to another option (opt >= 0) or take it back (opt = -1). Needs the token your browser made when it voted.
    "Pick several" polls: only taking the vote back is supported here (from = [options] as JSON); the browser then votes again."""
    name = "pchange"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        ctx.limits.throttle("pc:%d" % m["id"], 60, 600)
        pid = ctx.int_form("id")
        frm, opt = ctx.int_form("from", -1), ctx.int_form("opt", -1)
        old_token, token = ctx.form("ot"), ctx.form("t")
        rules = PollRules(ctx)
        author, meta = rules.open_poll(m, pid, "This poll has ended, so votes are locked.")
        if not _TOKEN.match(old_token):
            return Reply.error("Could not change your vote.", 400)
        wrong_device = Reply.error("You can only change your vote on the device you voted from.", 409)
        if int(meta["multi"]):
            raw = _json_list(ctx.form("from", "[]"))
            froms = list(dict.fromkeys(intval(x) for x in raw)) if raw is not None else []
            if not froms:
                return Reply.error("Could not change your vote.", 400)
            with db.transaction():
                ok = bool(db.value("SELECT 1 FROM pollvoted WHERE pid=? AND uid=?", (pid, m["id"])))
                for f1 in froms:
                    if not ok or not db.value("SELECT 1 FROM pollrx WHERE pid=? AND h=?", (pid, rules.receipt(pid, f1, old_token))):
                        ok = False
                if ok:
                    for f1 in froms:
                        db.execute("DELETE FROM pollrx WHERE pid=? AND h=?", (pid, rules.receipt(pid, f1, old_token)))
                        db.execute("UPDATE polls SET n=MAX(n-1,0) WHERE pid=? AND pos=?", (pid, f1))
                    db.execute("DELETE FROM pollvoted WHERE pid=? AND uid=?", (pid, m["id"]))
            if not ok:
                return wrong_device
            return Reply({"poll": {"v": 0, "n": rules.counts(pid) if author == int(m["id"]) else None}})
        if opt >= 0 and not _TOKEN.match(token):
            return Reply.error("Could not change your vote.", 400)
        if opt >= 0 and not db.value("SELECT 1 FROM polls WHERE pid=? AND pos=?", (pid, opt)):
            return Reply.error("No such option.", 400)
        old_hash = rules.receipt(pid, frm, old_token)
        with db.transaction():
            ok = bool(db.value("SELECT 1 FROM pollvoted WHERE pid=? AND uid=?", (pid, m["id"]))) and bool(db.value("SELECT 1 FROM pollrx WHERE pid=? AND h=?", (pid, old_hash)))
            if ok:
                db.execute("DELETE FROM pollrx WHERE pid=? AND h=?", (pid, old_hash))
                db.execute("UPDATE polls SET n=MAX(n-1,0) WHERE pid=? AND pos=?", (pid, frm))
                if opt >= 0:
                    db.execute("UPDATE polls SET n=n+1 WHERE pid=? AND pos=?", (pid, opt))
                    db.execute("INSERT OR IGNORE INTO pollrx(pid,h) VALUES(?,?)", (pid, rules.receipt(pid, opt, token)))
                else:
                    db.execute("DELETE FROM pollvoted WHERE pid=? AND uid=?", (pid, m["id"]))
        if not ok:
            return wrong_device
        return Reply({"poll": {"v": 1 if opt >= 0 else 0, "n": rules.counts(pid) if (opt >= 0 or author == int(m["id"])) else None}})


@registry.register
class PinQuestionAnswer(Action):
    """?a=qpin  Pin (up to 3) of your answers to anonymous questions on the Questions tab of your profile."""
    name = "qpin"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("qpin:%d" % m["id"], 30, 600)
        pid = ctx.int_form("id")
        if ctx.form("on", "1") == "0":
            ctx.db.execute("UPDATE posts SET qp=0 WHERE id=? AND uid=?", (pid, m["id"]))
            return Reply({"ok": 1})
        r = ctx.db.one("SELECT pd,aq,mid FROM posts WHERE id=? AND uid=?", (pid, m["id"]))
        if not r:
            return Reply.error("Post not found.", 404)
        if int(r["pd"]) or str(r["aq"] or "") == "" or int(r["mid"]):
            return Reply.error("Only your answers to questions can be pinned here.", 400)
        if not m["admin"] and int(ctx.db.value("SELECT COUNT(*) FROM posts WHERE uid=? AND qp=1 AND id!=?", (m["id"], pid), 0)) >= 3:
            return Reply.error("You can pin up to 3 answers. Unpin one first.", 400)
        ctx.db.execute("UPDATE posts SET qp=1 WHERE id=? AND uid=?", (pid, m["id"]))
        return Reply({"ok": 1})


@registry.register
class PinPost(Action):
    """?a=pin  Pin one post to the top of your profile."""
    name = "pin"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("pin:%d" % m["id"], 30, 600)
        pid = ctx.int_form("id")
        if ctx.form("on", "1") == "0":
            ctx.db.execute("UPDATE users SET pin=0 WHERE id=? AND pin=?", (m["id"], pid))
            return Reply({"ok": 1})
        r = ctx.db.one("SELECT anon,mid,hold FROM posts WHERE id=? AND uid=?", (pid, m["id"]))
        if not r:
            return Reply.error("Post not found.", 404)
        if int(r["anon"]) or int(r["mid"]):
            return Reply.error("Anonymous and Masque posts can't be pinned to your profile.", 400)
        if int(r["hold"]):
            return Reply.error("This post is waiting for review.", 400)
        ctx.db.execute("UPDATE users SET pin=? WHERE id=?", (pid, m["id"]))
        return Reply({"ok": 1})


@registry.register
class Mutes(Action):
    """?a=mutes  People and words you hid on your own posts."""
    name = "mutes"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        users = [{"id": intval(r["val"]), "name": r["lbl"]} for r in ctx.db.all("SELECT val,lbl FROM mutes WHERE uid=? AND kind='u' ORDER BY rowid DESC", (m["id"],))]
        words = [r[0] for r in ctx.db.query("SELECT val FROM mutes WHERE uid=? AND kind='w' ORDER BY rowid DESC", (m["id"],)).fetchall()]
        return Reply({"users": users, "words": words})


@registry.register
class MuteCommenter(Action):
    """?a=mutec  Hide a commenter on your own post."""
    name = "mutec"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        ctx.limits.throttle("mute:%d" % m["id"], 40, 600)
        c = db.one("SELECT c.uid,c.mid,p.uid puid FROM comments c JOIN posts p ON p.id=c.pid WHERE c.id=?", (ctx.int_form("id"),))
        if not c or int(c["puid"]) != int(m["id"]):
            return Reply.error("You can only mute people on your own posts.", 403)
        if int(c["uid"]) == int(m["id"]):
            return Reply.error("You cannot mute yourself.", 400)
        if not m["admin"] and int(db.value("SELECT COUNT(*) FROM mutes WHERE uid=? AND kind='u'", (m["id"],), 0)) >= 200:
            return Reply.error("You have muted as many people as is allowed.", 400)
        label = db.value("SELECT name FROM masks WHERE id=?", (c["mid"],)) if int(c["mid"]) > 0 else db.value("SELECT name FROM users WHERE id=?", (c["uid"],))
        db.execute("INSERT OR REPLACE INTO mutes(uid,kind,val,lbl) VALUES(?,'u',?,?)", (m["id"], str(int(c["uid"])), str(label or "")))
        return Reply({"ok": 1})


@registry.register
class MuteWord(Action):
    """?a=muteword"""
    name = "muteword"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("mute:%d" % m["id"], 40, 600)
        w = php_trim(collapse_space(ctx.form("w"))).lower()
        if len(w) < 2 or len(w) > 30:
            return Reply.error("A muted word needs 2 to 30 characters.", 400)
        if not m["admin"] and int(ctx.db.value("SELECT COUNT(*) FROM mutes WHERE uid=? AND kind='w'", (m["id"],), 0)) >= 50:
            return Reply.error("You can mute up to 50 words.", 400)
        ctx.db.execute("INSERT OR IGNORE INTO mutes(uid,kind,val) VALUES(?,'w',?)", (m["id"], w))
        return Reply({"ok": 1, "w": w})


@registry.register
class Unmute(Action):
    """?a=unmute"""
    name = "unmute"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.db.execute("DELETE FROM mutes WHERE uid=? AND kind=? AND val=?", (m["id"], "u" if ctx.form("kind") == "u" else "w", ctx.form("v")))
        return Reply({"ok": 1})


@registry.register
class NotificationPrefs(Action):
    """?a=np  Which kinds of notifications are on, message pop-ups and quiet hours."""
    name = "np"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        p = ctx.notes.prefs.get(m["id"])
        return Reply({"muted": [x for x in str(p["muted"] or "").split(",") if x != ""], "pop": int(p["pop"]), "qon": int(p["qon"]),
                      "qfrom": int(p["qfrom"]), "qto": int(p["qto"])})


@registry.register
class SetNotificationPrefs(Action):
    """?a=setnp"""
    name = "setnp"
    KINDS = ("sigils", "replies", "mentions", "tags", "friends", "follows", "asks", "reveals", "streak")

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("np:%d" % m["id"], 60, 600)
        o = ctx.notes.prefs.get(m["id"])
        if ctx.has_form("muted"):
            asked = [x for x in ctx.form("muted").split(",") if x != "" and x != "0"]
            muted = [k for k in self.KINDS if k in asked]
        else:
            muted = [x for x in str(o["muted"] or "").split(",") if x != ""]
        pop = (0 if not ctx.flag("pop") else 1) if ctx.has_form("pop") else int(o["pop"])
        qon = (0 if not ctx.flag("qon") else 1) if ctx.has_form("qon") else int(o["qon"])
        fa = clamp_int(ctx.form("qfrom"), 0, 1439) if ctx.has_form("qfrom") else int(o["qfrom"])
        fb = clamp_int(ctx.form("qto"), 0, 1439) if ctx.has_form("qto") else int(o["qto"])
        tz = clamp_int(ctx.form("tz"), -840, 840) if ctx.has_form("tz") else int(o["tz"])
        ctx.db.execute("INSERT OR REPLACE INTO nprefs(uid,muted,pop,qon,qfrom,qto,tz) VALUES(?,?,?,?,?,?,?)", (m["id"], ",".join(muted), pop, qon, fa, fb, tz))
        ctx.notes.prefs.forget(m["id"])
        return Reply({"ok": 1})
