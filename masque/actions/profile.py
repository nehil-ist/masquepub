"""Editing my own profile: names, bio, pictures, privacy and themes (PHP: case 'profile')."""
import math
import sqlite3

from ..config import ascii_lower
from ..names import NameRules, TextCleaner
from ..php import clamp_int, collapse_space, empty as php_empty, php_trim
from ..unlockables import THEME_OPTIONS
from .base import Action, Context, Reply, registry

CHANGE_WAIT = 604800  # username and display name share one timer: once every 7 days
FREE_FIRST_DAY = 86400


class NameChange:
    """The checks that decide whether a new username or display name may be used."""

    def __init__(self, ctx: Context, m):
        self.ctx, self.m = ctx, m
        self.db, self.names = ctx.db, ctx.names

    def username(self, n: str):
        """A Reply when the new username is not allowed, else None."""
        ctx, m = self.ctx, self.m
        changed = ascii_lower(n) != ascii_lower(m["name"])
        if changed and ascii_lower(m["name"]) == ascii_lower(php_trim(ctx.cfg.admin_user)):
            return Reply.error("This account's username is set by the ADMIN_USER variable on the server and can't be changed here.", 403)
        if not NameRules.valid(n):
            return Reply.error("Usernames are 3 to 20 letters, numbers or _.", 400)
        if not changed:
            return None
        taken = Reply.error("That username is taken.", 409)
        h = NameRules.digest(n)
        if self.db.value("SELECT 1 FROM gone WHERE h=?", (h,)):
            return taken
        # a name someone renamed away from stays reserved for that person; admin names can only be taken by admins
        holder = self.db.value("SELECT uid FROM oldnames WHERE ts>? AND h=?", (self.ctx.now - NameRules.RESERVE_SECS, h))
        if holder is not None and int(holder) != int(m["id"]):
            return taken
        if not m["admin"] and ctx.users.admins.is_admin(n):
            return Reply.error("That username is reserved.", 409)
        if self.names.clash(n, m["id"], not m["admin"]):
            return taken
        return None

    def nickname(self, raw):
        """(clean nick, None) or (None, Reply)."""
        ctx, m = self.ctx, self.m
        nk = TextCleaner.nick(raw)
        if nk is None:
            return None, Reply.error("That display name has invalid characters.", 400)
        if nk != "":
            # not allowed: another person's @username, a deleted user's name, or an admin's name (unless it is yours)
            if (self.db.value("SELECT 1 FROM users WHERE name=? AND id!=?", (nk, m["id"]))
                    or self.db.value("SELECT 1 FROM gone WHERE h=?", (NameRules.digest(nk),))
                    or (not m["admin"] and ctx.users.admins.is_admin(nk))):
                return None, Reply.error("That display name is reserved. Try another.", 409)
            if nk != str(m.get("nick") or "") and self.names.clash(nk, m["id"], not m["admin"]):
                return None, Reply.error("That display name is too similar to another name. Try another.", 409)
        return nk, None


@registry.register
class Profile(Action):
    """?a=profile: save the settings page. Only the fields that were sent change."""
    name = "profile"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        n = php_trim(ctx.form("name", m["name"]))
        checks = NameChange(ctx, m)
        bad = checks.username(n)
        if bad:
            return bad
        nk = str(m.get("nick") or "")
        if ctx.has_form("nick"):
            nk, bad = checks.nickname(ctx.form("nick"))
            if bad:
                return bad
        # username / display name: once every 7 days (one shared timer), and only after the person confirmed
        changed_name = n != m["name"]
        changed_nick = nk != str(m.get("nick") or "")
        ncts = int(m.get("ncts") or 0)
        now = ctx.now
        if changed_name or changed_nick:
            wait = ncts + CHANGE_WAIT - now
            if wait > 0 and not m["admin"]:
                days = max(1, math.ceil(wait / 86400))
                return Reply({"e": "You can change your username or display name again in %d day%s." % (days, "s" if wait > 86400 else ""), "wait": wait}, 429)
            if not ctx.flag("confirm"):
                return Reply.error("Please confirm the name change.", 400)
            # the first change in an account's first 24 hours is free: it does not start the timer (1 marks it as used)
            joined = int(db.value("SELECT ts FROM users WHERE id=?", (m["id"],), 0) or 0)
            ncts = 1 if (not int(m.get("ncts") or 0) and now - joined < FREE_FIRST_DAY) else now
        # themes: only preset ids are ever stored
        tv = {}
        for k, allowed in THEME_OPTIONS.items():
            tv[k] = str(m.get(k) or "")
            if ctx.has_form(k):
                x = ctx.form(k)
                if x not in allowed:
                    return Reply.error("That theme option is not available.", 400)
                ctx.unlocks.gate(m, k, x)
                tv[k] = x
        cv, av = m["cover"], m["avatar"]
        cy = clamp_int(ctx.form("cy", m["cy"]), 0, 100)
        if ctx.flag("nocover") or ctx.file("cover"):
            new = ctx.media.save_img(ctx.file("cover"))
            ctx.media.remove([cv])
            cv = new
        if ctx.flag("noavatar") or ctx.file("avatar"):
            new = ctx.media.save_img(ctx.file("avatar"))
            ctx.media.remove([av])
            av = new
        ap = php_trim(collapse_space(ctx.form("askp")[:80])) if ctx.has_form("askp") else str(m.get("askp") or "")
        if ap != "":
            ctx.limits.nolinks(m, ap)
        private = not php_empty(ctx.form("priv", m["priv"]))
        try:
            with db.transaction():
                db.execute(
                    "UPDATE users SET name=?,bio=?,cover=?,avatar=?,cy=?,dm=?,priv=?,askon=?,askp=?,nick=?,ncts=?,tbg=?,tbp=?,tcd=?,tfn=?,tas=?,taf=?,tcf=?,tpl=? WHERE id=?",
                    (n, php_trim(ctx.form("bio", m["bio"])[:160]), cv, av, cy,
                     "friends" if ctx.form("dm", m["dm"]) == "friends" else "all",
                     1 if private else 0, 0 if php_empty(ctx.form("ask", m["askon"])) else 1, ap, nk, ncts,
                     tv["tbg"], tv["tbp"], tv["tcd"], tv["tfn"], tv["tas"], tv["taf"], tv["tcf"], tv["tpl"], m["id"]))
                if private:
                    db.execute("DELETE FROM follows WHERE b=?", (m["id"],))  # a private account has friends, not followers
                if ascii_lower(n) != ascii_lower(m["name"]):
                    db.execute("INSERT OR REPLACE INTO oldnames(h,uid,ts) VALUES(?,?,?)", (NameRules.digest(m["name"]), m["id"], now))
                    db.execute("DELETE FROM oldnames WHERE h=? AND uid=?", (NameRules.digest(n), m["id"]))
        except sqlite3.IntegrityError:
            return Reply.error("That username is taken.", 409)
        ctx.users.reset()
        return Reply({"me": ctx.users.me()})


@registry.register
class StatusSet(Action):
    """?a=setst: my presence setting: '' (automatic), online, idle, lurk (look offline but stay active) or off."""
    name = "setst"
    CHOICES = ("", "online", "idle", "lurk", "off")

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        v = ctx.form("st")
        if v not in self.CHOICES:
            return Reply.error("Unknown status.", 400)
        ctx.db.execute("UPDATE users SET pst=? WHERE id=?", (v, m["id"]))
        return Reply({"pst": v})


@registry.register
class SetExperimental(Action):
    """?a=setxp: switch the experimental features on or off for myself."""
    name = "setxp"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("xp:%d" % m["id"], 30, 600)
        ctx.db.execute("UPDATE users SET xp=? WHERE id=?", (1 if ctx.flag("on") else 0, m["id"]))
        ctx.users.reset()  # PHP me() reads the row again
        return Reply({"me": ctx.users.me()})


@registry.register
class ExperimentalForAll(Action):
    """?a=xpall: admin switch that turns the experimental features on for everyone."""
    name = "xpall"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need_admin()
        on = "1" if ctx.flag("on") else "0"
        ctx.db.execute("INSERT OR REPLACE INTO site(k,v) VALUES('xpall',?)", (on,))
        ctx.adminlog.add(m, "experimental for everyone " + ("on" if on == "1" else "off"), "")
        ctx.users.reset()
        return Reply({"me": ctx.users.me()})


@registry.register
class SetStatus(Action):
    """?a=setstatus: a short status line that disappears after a day (empty text clears it)."""
    name = "setstatus"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.lim("stt:%d" % m["id"], 20, 3600, m, 10, 3600)
        t = TextCleaner.status(ctx.form("txt"))
        if t is None:
            return Reply.error("That status has invalid characters.", 400)
        if t != "" and not m["admin"] and ctx.words.match(t):
            return Reply.error("That word is not allowed here.", 400)
        ctx.db.execute("UPDATE users SET stx=?,stts=? WHERE id=?", (t, 0 if t == "" else ctx.now, m["id"]))
        return Reply({"status": t, "stleft": 0 if t == "" else 86400})
