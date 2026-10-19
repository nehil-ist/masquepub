"""#hashtags and @mentions (PHP: settags, tagnotify, mentions, gmre, gevok, gmentions)."""
import re

_TAG = re.compile(r"#([A-Za-z0-9_]{1,40})")
_AT = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]{3,20})")
_GAT = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]{3,20})(?![A-Za-z0-9_])")


def _lower(s: str) -> str:
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)


def _unique(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def hashtags(text: str) -> list:
    return _unique(_lower(t) for t in _TAG.findall(str(text)))


class PostTags:
    def __init__(self, ctx):
        self.ctx = ctx
        self.db = ctx.db

    def set(self, pid: int, caption: str):
        self.db.execute("DELETE FROM posttags WHERE pid=?", (pid,))
        for t in hashtags(caption):
            self.db.execute("INSERT OR IGNORE INTO posttags VALUES(?,?)", (pid, t))

    def notify_followers(self, pid: int, text: str, actor, mid: int = 0):
        """Hashtag follow: tell followers (max 200) about a new post that uses a tag they follow."""
        tags = hashtags(text)
        if not tags:
            return
        marks = ",".join("?" * len(tags))
        for r in self.db.all("SELECT DISTINCT uid FROM tagfollows WHERE tag IN (%s) AND uid!=? LIMIT 200" % marks, (*tags, int(actor))):
            if self.ctx.access.can_view(pid, int(r["uid"])):
                self.ctx.notes.note(int(r["uid"]), "tag", actor, pid, mid)


class Mentions:
    def __init__(self, ctx):
        self.ctx = ctx
        self.db = ctx.db

    @staticmethod
    def _names(text: str) -> list:
        return _unique(_lower(t) for t in _AT.findall(str(text)))[:5]

    def in_post(self, pid: int, text: str, actor, old: str = "", skip_user: int = 0, mid: int = 0):
        """Notify each mentioned user (max 5) who can see the post. `old` = previous text so edits only notify new names."""
        skip = [] if old == "" else self._names(old)
        for n in self._names(text):
            if n in skip:
                continue
            u = self.db.value("SELECT id FROM users WHERE name=?", (n,))
            if u and int(u) != int(skip_user) and self.ctx.access.can_view(pid, int(u)):
                self.ctx.notes.note(int(u), "mention", actor, pid, mid)

    # -- group chats: @name pings a member (their real name or their Masque's; a ping never says which). @everyone pings the whole group. --
    @staticmethod
    def group_names(text) -> list:
        return _unique(_lower(t) for t in _GAT.findall(str(text)))[:8]

    def everyone_ok(self, gid, m, text: str, old: str = "") -> bool:
        """@everyone may be used once per 5 minutes per person per group."""
        fresh = [n for n in self.group_names(text) if n not in self.group_names(old)]
        if "everyone" not in fresh:
            return True
        return self.ctx.limiter.count("ge:%d:%d" % (int(gid), int(m["id"])), 300) < 1

    def in_group(self, gid, text: str, m, as_masque, old: str = ""):
        old_names = [] if old == "" else self.group_names(old)
        names = [n for n in self.group_names(text) if n not in old_names]
        if not names:
            return
        gid = int(gid)
        mid = int(self.db.value("SELECT id FROM masks WHERE uid=?", (m["id"],), 0) or 0) if as_masque else 0
        hit = {}
        for n in names:
            if n == "everyone":
                self.ctx.limiter.add("ge:%d:%d" % (gid, int(m["id"])))
                for r in self.db.all("SELECT uid FROM gmembers WHERE gid=? AND mute=0 AND uid!=?", (gid, m["id"])):
                    hit[int(r["uid"])] = "gall"
                continue
            u = self.db.value("SELECT u.id FROM gmembers mb JOIN users u ON u.id=mb.uid WHERE mb.gid=? AND mb.pm=0 AND u.name=?", (gid, n))
            if not u:
                u = self.db.value("SELECT k.uid FROM masks k JOIN gmasks gm ON gm.uid=k.uid AND gm.gid=? WHERE k.name=?", (gid, n))
            if u and int(u) != int(m["id"]):
                hit[int(u)] = "gment"
        for u, kind in hit.items():
            self.ctx.notes.note(u, kind, m["id"], gid, mid)
