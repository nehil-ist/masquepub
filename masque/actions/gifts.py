"""Admin gifts and theme grants (PHP: case 'agift', 'gift', 'agrants', 'agive'). `gopen` (mark a gift opened) lives in groups.py for now."""
import unicodedata

from ..php import intval, php_trim
from ..unlockables import Unlocks
from .base import Action, Context, Reply, registry
from .sigils import _find_user

MAX_GIFT_ITEMS = 40
MAX_GIFT_NOTE = 140


def _note(raw: str) -> str:
    """PHP: control/format characters become spaces, then trim and cut at 140 characters."""
    s = "".join(" " if unicodedata.category(c)[0] == "C" else c for c in raw)
    return php_trim(s)[:MAX_GIFT_NOTE]


def _request(ctx: Context, name: str) -> str:
    """PHP $_REQUEST: form first, then the query string."""
    return ctx.form(name) if ctx.has_form(name) else ctx.arg(name)


@registry.register
class GiftSend(Action):
    """?a=agift: an admin sends one gift (several items at once) to a person."""
    name = "agift"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need_admin()
        db, un = ctx.db, ctx.unlocks
        t = _find_user(ctx, ctx.form("u"))
        if not t:
            return Reply.error("No such user.", 404)
        items = {}
        for z in ctx.form("items").split(",")[:MAX_GIFT_ITEMS]:
            parts = php_trim(z).split(":", 1)
            if len(parts) != 2:
                continue
            k, x = parts
            if not Unlocks.known_item(k, x):
                continue
            if db.value("SELECT 1 FROM ugrants WHERE uid=? AND k=? AND id=?", (t["id"], k, x)):
                continue  # they already have it
            items[k + ":" + x] = (k, x)
        if not items:
            return Reply.error("Pick at least one item they do not have yet.", 400)
        msg = _note(ctx.form("msg"))
        now = ctx.now
        with db.transaction():
            gid = db.query("INSERT INTO gifts(uid,by,ts,msg,opened) VALUES(?,?,?,?,0)", (t["id"], m["id"], now, msg)).lastrowid
            for k, x in items.values():
                db.execute("INSERT OR IGNORE INTO ugrants(uid,k,id,by,ts) VALUES(?,?,?,?,?)", (t["id"], k, x, m["id"], now))
                db.execute("INSERT INTO gitems(gid,k,id) VALUES(?,?,?)", (gid, k, x))
            db.execute("INSERT INTO notifs(uid,kind,actor,pid,ts) VALUES(?,?,?,?,?)", (t["id"], "gift", t["id"], gid, now))
        ctx.adminlog.add(m, "gift " + " ".join(items), t["name"])
        ctx.notes.push(t["id"], "Masque", "You got a gift", "./#/n", "gift-%d" % gid, 0)
        return Reply({"ok": 1, "n": len(items), "gr": un.grants(t)})


@registry.register
class GiftOpenView(Action):
    """?a=gift: what is inside one of my gifts."""
    name = "gift"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        g = ctx.db.one("SELECT id,msg,opened,ts FROM gifts WHERE id=? AND uid=?", (intval(_request(ctx, "id")), m["id"]))
        if not g:
            return Reply.error("No such gift.", 404)
        g["items"] = [[r["k"], r["id"]] for r in ctx.db.all("SELECT k,id FROM gitems WHERE gid=? ORDER BY rowid", (g["id"],))]
        return Reply(g)


class GrantAction(Action):
    """Base for the two admin grant screens: admin only, finds the person from `u`."""

    def person(self, ctx: Context):
        m = ctx.users.need_admin()
        t = _find_user(ctx, _request(ctx, "u"))
        if not t:
            ctx.deny("No such user.", 404)
        return m, t


@registry.register
class GrantList(GrantAction):
    """?a=agrants: the theme items an admin gave to one person."""
    name = "agrants"

    def handle(self, ctx: Context) -> Reply:
        m, t = self.person(ctx)
        return Reply({"gr": ctx.unlocks.grants(t)})


@registry.register
class GrantChange(GrantAction):
    """?a=agive: give (on=1) or take back one theme item."""
    name = "agive"

    def handle(self, ctx: Context) -> Reply:
        m, t = self.person(ctx)
        k, x = ctx.form("k"), ctx.form("id")
        if not Unlocks.known_item(k, x):
            return Reply.error("Unknown item.", 400)
        if ctx.flag("on"):
            ctx.db.execute("INSERT OR IGNORE INTO ugrants(uid,k,id,by,ts) VALUES(?,?,?,?,?)", (t["id"], k, x, m["id"], ctx.now))
            ctx.adminlog.add(m, "gave %s:%s" % (k, x), t["name"])
        else:
            ctx.db.execute("DELETE FROM ugrants WHERE uid=? AND k=? AND id=?", (t["id"], k, x))
            ctx.adminlog.add(m, "took %s:%s" % (k, x), t["name"])
        return Reply({"gr": ctx.unlocks.grants(t)})
