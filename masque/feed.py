"""The post feed: which posts a viewer may see (SQL filter), the "For you" order, and how a post row is shaped for the page (PHP: case 'feed', fyrank)."""
import math
import time

from .access import mqts
from .moderation import AutoHide
from .php import ids_sql, like_escape

_FRIEND_IDS = "SELECT CASE WHEN a=? THEN b ELSE a END FROM friends WHERE st=1 AND (a=? OR b=?)"


class FeedFilter:
    """Builds the WHERE part of the feed query for one request. `sql` always starts with WHERE and `params` lines up with its ? marks."""

    def __init__(self, ctx, viewer):
        self.ctx = ctx
        self.m = viewer
        self.vid = int(viewer["id"]) if viewer else 0
        self.sql = ""
        self.params = []
        self.is_home = False
        self.home_sql = ""  # the filter before the prompt-answer and question exclusions (used for the daily threads)
        self.home_params = []

    def build(self) -> "FeedFilter":
        ctx, m, vid = self.ctx, self.m, self.vid
        w, p = "", []
        if ctx.qflag("u"):
            w, p = "WHERE u.name=?", [ctx.arg("u")]
        elif ctx.qflag("t"):
            w, p = "WHERE p.id IN (SELECT pid FROM posttags WHERE tag=?)", [_lower(ctx.arg("t"))]
        elif ctx.qflag("sv") and m:
            w, p = "WHERE p.id IN (SELECT pid FROM saves WHERE uid=?)", [vid]
        elif ctx.qflag("s"):
            w, p = "WHERE p.cap LIKE ? ESCAPE '\\'", ["%" + like_escape(ctx.arg("s").strip(" \t\n\r\0\x0b")) + "%"]
        elif ctx.qflag("k"):
            w, p = "WHERE mk.name=?", [ctx.arg("k")]
        elif ctx.qflag("pd"):
            w, p = "WHERE p.pd=?", [ctx.int_arg("pd")]
        elif ctx.qflag("id"):
            w, p = "WHERE p.id=?", [ctx.int_arg("id")]
        elif ctx.qflag("fl") and m:
            # Following: only ordinary public posts. Masque and anonymous posts are left out on purpose, so following an account can never be used to work out whose Masque it is.
            w, p = "WHERE p.anon=0 AND p.mid=0 AND p.vis=0 AND p.uid IN (SELECT b FROM follows WHERE a=?)", [vid]
        elif ctx.qflag("f") and m:
            w = "WHERE (p.uid=? OR p.uid IN (%s))" % _FRIEND_IDS
            p = [vid, vid, vid, vid]
        # an account block never hides a Masque post (it would show whose it is); blocking the Masque itself does
        w = (w + " AND " if w else "WHERE ") + ("(p.mid>0 OR p.anon=1 OR p.uid NOT IN (SELECT b FROM blocks WHERE a=? UNION SELECT a FROM blocks WHERE b=?)) "
                                                "AND (p.mid=0 OR p.mid NOT IN (SELECT kid FROM mblocks WHERE a=?))")
        p += [vid, vid, vid]
        # Masque and old anonymous posts skip the private-account check, so who can see them never hints at whose they are
        w += " AND (u.priv=0 OR p.mid>0 OR p.anon=1 OR p.uid=? OR p.uid IN (%s))" % _FRIEND_IDS
        p += [vid, vid, vid, vid]
        w += " AND (p.vis=0 OR p.uid=? OR (p.vis=1 AND p.uid IN (%s)))" % _FRIEND_IDS
        p += [vid, vid, vid, vid]
        admin = bool(m and m["admin"])
        hide = AutoHide()
        if hide.threshold() > 0 and not admin:
            w += (" AND (p.uid=? OR p.id NOT IN (SELECT r.tid FROM reports r JOIN users ru ON ru.id=r.uid WHERE r.kind='post' AND ru.ts<=? "
                  "GROUP BY r.tid HAVING COUNT(DISTINCT r.uid)>=CAST(? AS INTEGER)))")
            p += [vid, int(time.time()) - hide.min_age(), hide.threshold()]
        if not admin:
            w += " AND (p.hold=0 OR p.uid=?)"
            p.append(vid)
        # home (Everyone / Friends): prompt answers are not listed one by one; they live in one thread per day, opened with #/d/<day>
        self.is_home = bool(m) and not any(ctx.qflag(k) for k in ("u", "t", "sv", "s", "k", "pd", "id", "top"))
        if self.is_home:
            self.home_sql, self.home_params = w, list(p)
            w += " AND p.pd=0 AND COALESCE(p.aq,'')=''"  # answers to anonymous questions live in the Questions tab of the answerer's profile
        if ctx.qflag("u"):
            w += " AND (p.anon=0 OR p.uid=?) AND p.mid=0"
            p.append(vid)
            w += (" AND p.pd=0 AND COALESCE(p.aq,'')!=''") if ctx.arg("tab") == "q" else " AND NOT (p.pd=0 AND COALESCE(p.aq,'')!='')"
        if ctx.qflag("k"):
            w += " AND (p.anon=0 OR p.uid=?)"
            p.append(vid)
        self.sql, self.params = w, p
        return self


def _lower(s: str) -> str:
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)


class FeedRanker:
    """"For you": the order of the Home feed when it is ranked instead of newest-first. It looks at the 300 newest posts the person is allowed to see
    and scores each one by what people did with it compared with how many saw it, how fresh it is (the score halves roughly every 8 to 10 hours),
    for ordinary public posts only friends / follows / people you reacted to in the last 30 days, and posts you have already seen sink.
    Anonymous and Masque posts never get anything that depends on who wrote them, so the order can never be used to work out who is behind one.
    Time is rounded to 10 minutes so the order holds still while you scroll."""

    def __init__(self, db):
        self.db = db

    def rank(self, where: str, params, m, before: int, newer: int):
        """The ids to show (up to 21), or None when the caller should use the plain newest-first list. before = the post this page continues after, newer = the one post just before this one."""
        db = self.db
        vid = int(m["id"])
        asof = int(time.time()) // 600 * 600
        rows = db.all(
            "SELECT p.id,p.uid,p.anon,p.mid,p.ts,(SELECT COUNT(*) FROM likes l WHERE l.pid=p.id) lk,"
            "(SELECT COUNT(*) FROM comments c WHERE c.pid=p.id AND c.hold=0) cm,(SELECT COUNT(*) FROM saves s WHERE s.pid=p.id) sv,"
            "(SELECT COUNT(*) FROM postviews v WHERE v.pid=p.id AND v.ts<=%d) vw,"
            "(SELECT COUNT(*) FROM postviews v WHERE v.pid=p.id AND v.uid=%d AND v.ts<=%d) seen "
            "FROM posts p JOIN users u ON u.id=p.uid LEFT JOIN masks mk ON mk.id=p.mid %s ORDER BY p.id DESC LIMIT 300" % (asof, vid, asof, where), params)
        if not rows:
            return None if newer > 0 else []
        friends = {int(r[0]) for r in db.query(_FRIEND_IDS, (vid, vid, vid)).fetchall()}
        follows = {int(r[0]) for r in db.query("SELECT b FROM follows WHERE a=?", (vid,)).fetchall()}
        affinity = {}
        since = int(time.time()) - 30 * 86400
        for z in db.all("SELECT p2.uid u,COUNT(*) n FROM likes l JOIN posts p2 ON p2.id=l.pid WHERE l.uid=? AND p2.anon=0 AND p2.mid=0 AND p2.ts>? GROUP BY p2.uid", (vid, since)):
            affinity[int(z["u"])] = affinity.get(int(z["u"]), 0) + int(z["n"])
        for z in db.all("SELECT p2.uid u,COUNT(*) n FROM comments c JOIN posts p2 ON p2.id=c.pid WHERE c.uid=? AND c.hold=0 AND p2.anon=0 AND p2.mid=0 AND c.ts>? GROUP BY p2.uid", (vid, since)):
            affinity[int(z["u"])] = affinity.get(int(z["u"]), 0) + 2 * int(z["n"])
        scored = []
        for r in rows:
            uid = int(r["uid"])
            public = not int(r["anon"]) and not int(r["mid"])
            age = max(0, asof - int(r["ts"])) / 3600
            eng = int(r["lk"]) + 2 * int(r["cm"]) + 3 * int(r["sv"])
            qual = min(0.5, (eng + 1) / (int(r["vw"]) + 10))
            s = (0.6 + math.log(1 + eng) + 6 * qual) / math.pow(1 + age / 8, 1.25)
            if public and uid != vid:
                s *= 1 + (0.9 if uid in friends else 0) + (0.7 if uid in follows else 0) + min(1.2, 0.25 * affinity.get(uid, 0))
            if int(r["seen"]) > 0:
                s *= 0.2
            if uid == vid:
                s *= 0.7
            scored.append({"id": int(r["id"]), "k": uid if public else 0, "s": s})
        order, last = [], []
        while scored:
            bi, bv = 0, -1
            for i, x in enumerate(scored):
                v = x["s"]
                if x["k"] and x["k"] in last:
                    v *= 0.5 if last[-1] == x["k"] else 0.75
                if v > bv:
                    bv, bi = v, i
            order.append(scored[bi]["id"])
            last.append(scored[bi]["k"])
            if len(last) > 2:
                last.pop(0)
            del scored[bi]
        if newer > 0:
            if newer not in order:
                return None
            i = order.index(newer)
            return [order[i - 1]] if i > 0 else []
        if before > 0:
            if before not in order:
                return None
            i = order.index(before)
        else:
            i = -1
        ids = order[i + 1:i + 22]
        if len(ids) < 21 and len(rows) >= 300:
            floor = int(rows[-1]["id"])
            more = db.all("SELECT p.id FROM posts p JOIN users u ON u.id=p.uid LEFT JOIN masks mk ON mk.id=p.mid %s AND p.id<? ORDER BY p.id DESC LIMIT %d"
                          % (where, 21 - len(ids)), [*params, floor])
            ids += [int(x["id"]) for x in more]
        return ids


class PostPresenter:
    """Shapes post rows for the page: Masque name and avatar swapped in, rounded times for other people's Masque posts, photos, polls."""

    def __init__(self, db):
        self.db = db

    def present(self, rows, vid: int, profile_view: bool = False):
        db = self.db
        if not rows:
            return rows
        ids = ids_sql(r["id"] for r in rows)
        images, alts = {}, {}
        for z in db.all("SELECT pid,img,alt FROM postimgs WHERE pid IN (%s) ORDER BY pid,pos" % ids):
            images.setdefault(int(z["pid"]), []).append(z["img"])
            alts.setdefault(int(z["pid"]), []).append(str(z["alt"] or ""))
        polls, voted, pmeta = {}, set(), {}
        for z in db.all("SELECT pid,pos,txt,n FROM polls WHERE pid IN (%s) ORDER BY pid,pos" % ids):
            polls.setdefault(int(z["pid"]), []).append(z)
        if polls:
            voted = {int(z[0]) for z in db.query("SELECT pid FROM pollvoted WHERE uid=? AND pid IN (%s)" % ids, (vid,)).fetchall()}
            for z in db.all("SELECT pid,ends,multi FROM pollmeta WHERE pid IN (%s)" % ids):
                pmeta[int(z["pid"])] = z
        now = int(time.time())
        for x in rows:
            pid = int(x["id"])
            if int(x["mid"]) > 0:
                x["name"], x["nick"], x["avatar"], x["mk"] = x["mkn"], "", x["mka"], 1
            else:
                x["mk"] = 0
            x["own"] = 1 if int(x["uid"]) == vid else 0
            if not x["own"] and (int(x["mk"]) or int(x["anon"])):
                x["ts"] = mqts(x["ts"])
                if int(x["ed"]):
                    x["ed"] = mqts(x["ed"])
                if int(x["exp"]):
                    x["exp"] = mqts(x["exp"], True)
            x["pinned"] = 1 if (profile_view and int(x["pin"] or 0) == pid) else 0
            del x["pin"]
            if pid in polls:
                o = polls[pid]
                has_voted = pid in voted
                ends = int((pmeta.get(pid) or {}).get("ends") or 0)
                finished = ends > 0 and now >= ends
                x["poll"] = {
                    "o": [z["txt"] for z in o],
                    "v": 1 if has_voted else 0,
                    "n": [int(z["n"]) for z in o] if (has_voted or x["own"] or finished) else None,
                    "end": ends,
                    "done": 1 if finished else 0,
                    "multi": 1 if int((pmeta.get(pid) or {}).get("multi") or 0) else 0,
                }
            for k in ("mid", "mkn", "mka"):
                del x[k]
            x["imgs"] = images.get(pid) or ([x["img"]] if x["img"] else [])
            x["alts"] = alts.get(pid, [])
            if int(x["anon"]) and int(x["uid"]) != vid:
                x["name"], x["nick"], x["avatar"] = "", "", ""
            del x["uid"]
        return rows
