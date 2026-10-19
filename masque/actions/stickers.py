"""Stickers (PHP: case 'stkup', 'stkfavs', 'stkfav'). Picture stickers are saved by `Uploads.save_sticker`; this module is the favourites list.

A favourite is a `ref`: 'b:<name>' for a built-in sticker, 'i:<16 hex>' for a picture sticker.
"""
import re

from .base import Action, Context, Reply, registry

_REF = re.compile(r"(b:[a-z0-9]{1,12}|i:[a-f0-9]{16})$")


class Favourites:
    """One person's sticker favourites: up to 100 in all, up to 60 of them pictures."""
    MAX_ALL = 100
    MAX_PICTURES = 60
    TOO_MANY_PICTURES = "You already have 60 picture stickers. Remove one first."

    def __init__(self, ctx: Context, uid: int):
        self.ctx, self.db, self.uid = ctx, ctx.db, int(uid)

    def pictures(self) -> int:
        return int(self.db.value("SELECT COUNT(*) FROM stkfav WHERE uid=? AND ref LIKE 'i:%'", (self.uid,), 0))

    def total(self) -> int:
        return int(self.db.value("SELECT COUNT(*) FROM stkfav WHERE uid=?", (self.uid,), 0))

    def has(self, ref: str) -> bool:
        return bool(self.db.value("SELECT 1 FROM stkfav WHERE uid=? AND ref=?", (self.uid, ref)))

    def add(self, ref: str):
        self.db.execute("INSERT OR IGNORE INTO stkfav(uid,ref,ts) VALUES(?,?,?)", (self.uid, ref, self.ctx.now))

    def remove(self, ref: str):
        self.db.execute("DELETE FROM stkfav WHERE uid=? AND ref=?", (self.uid, ref))

    def refs(self) -> list:
        """Newest first; a picture sticker that no longer exists is left out."""
        return [r[0] for r in self.db.query(
            "SELECT ref FROM stkfav WHERE uid=? AND (ref LIKE 'b:%' OR substr(ref,3) IN (SELECT id FROM stkimg)) ORDER BY ts DESC,rowid DESC",
            (self.uid,)).fetchall()]


@registry.register
class StickerUpload(Action):
    """?a=stkup: upload a picture sticker (img) and keep it in my favourites. Answers with its id."""
    name = "stkup"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.lim("stku:%d" % m["id"], 10, 3600, m, 4, 3600)
        fav = Favourites(ctx, m["id"])
        if fav.pictures() >= Favourites.MAX_PICTURES:
            return Reply.error(Favourites.TOO_MANY_PICTURES, 400)
        sid = ctx.media.save_sticker(ctx.file("img"))
        fav.add("i:" + sid)
        return Reply({"id": sid})


@registry.register
class StickerFavourites(Action):
    """?a=stkfavs: my favourite stickers (refs), newest first."""
    name = "stkfavs"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        return Reply({"items": Favourites(ctx, m["id"]).refs()})


@registry.register
class StickerFavourite(Action):
    """?a=stkfav: add a sticker to my favourites, or remove it (on empty)."""
    name = "stkfav"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("stkf:%d" % m["id"], 60, 60)
        ref = ctx.form("ref")
        if not _REF.match(ref):
            return Reply.error("That is not a sticker.", 400)
        fav = Favourites(ctx, m["id"])
        if not ctx.flag("on"):
            fav.remove(ref)
            return Reply({"ok": 1})
        picture = ref[0] == "i"
        if picture and not ctx.db.value("SELECT 1 FROM stkimg WHERE id=?", (ref[2:],)):
            return Reply.error("That sticker is no longer available.", 404)
        if not fav.has(ref):
            if fav.total() >= Favourites.MAX_ALL:
                return Reply.error("You can keep up to 100 favourite stickers. Remove one first.", 400)
            if picture and fav.pictures() >= Favourites.MAX_PICTURES:
                return Reply.error(Favourites.TOO_MANY_PICTURES, 400)
        fav.add(ref)
        return Reply({"ok": 1})
