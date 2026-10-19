"""Sigils, the Marketplace and the daily prompt (PHP: case 'sgive', 'shopbuy', 'sfreeze', 'prompt')."""
from ..php import php_trim
from ..prompts import DailyPrompt
from ..streaks import FREEZE_PRICE, Streaks
from ..unlockables import SHOP, STREAK_BONUS
from .base import Action, Context, Reply, registry


def _find_user(ctx: Context, name: str):
    """A user by name, ignoring upper/lower case (admin tools)."""
    return ctx.db.one("SELECT id,name FROM users WHERE name=? COLLATE NOCASE", (php_trim(name),))


@registry.register
class SigilGive(Action):
    """?a=sgive: an admin gives (or with a minus takes back) Sigils; works on yourself too."""
    name = "sgive"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need_admin()
        t = _find_user(ctx, ctx.form("u"))
        if not t:
            return Reply.error("No such user.", 404)
        n = ctx.int_form("n")
        if n == 0 or abs(n) > 1000000:
            return Reply.error("Enter an amount between 1 and 1,000,000 (use a minus to take some back).", 400)
        ctx.db.execute("INSERT INTO sigadj(uid,amt,by,ts) VALUES(?,?,?,?)", (t["id"], n, m["id"], ctx.now))
        ctx.adminlog.add(m, "sigils " + ("+" if n > 0 else "") + str(n), t["name"])
        return Reply({"ok": 1, "name": t["name"], "bal": ctx.unlocks.balance(t, ctx.unlocks.stats(t))})


@registry.register
class ShopBuy(Action):
    """?a=shopbuy: buy one Marketplace theme with Sigils."""
    name = "shopbuy"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, un = int(m["id"]), ctx.db, ctx.unlocks
        ctx.limits.lim("shopb:%d" % me, 30, 3600, m, 20, 3600)
        k, x = ctx.form("k"), ctx.form("id")
        if x not in SHOP.get(k, {}):
            return Reply.error("That is not in the Marketplace.", 404)
        st = un.stats(m)
        if m["admin"] or db.value("SELECT 1 FROM ugrants WHERE uid=? AND k=? AND id=?", (me, k, x)) or un.legacy(k, x, st):
            return Reply.error("You already have this one.", 400)
        price = int(SHOP[k][x])
        bal = un.balance(m, st)
        if bal < price:
            return Reply.error("You need %d more Sigils for this one." % (price - bal), 400)
        with db.transaction():
            db.execute("INSERT OR IGNORE INTO shop(uid,k,id,price,ts) VALUES(?,?,?,?,?)", (me, k, x, price, ctx.now))
            db.execute("INSERT OR IGNORE INTO ugrants(uid,k,id,by,ts) VALUES(?,?,?,?,?)", (me, k, x, 0, ctx.now))
        return Reply({"ok": 1, "bal": un.balance(m, st), "gr": un.grants(m)})


@registry.register
class StreakFreeze(Action):
    """?a=sfreeze: spend Sigils to save a streak after missed days (the missed days turn icy and keep the chain going)."""
    name = "sfreeze"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, un = int(m["id"]), ctx.db, ctx.unlocks
        ctx.limits.lim("sfz:%d" % me, 10, 3600, m, 10, 3600)
        streaks = Streaks(db)
        offer = streaks.calc(me)["offer"]
        if not offer:
            return Reply.error("There is no streak to save right now.", 400)
        admin = bool(m["admin"])
        bal = un.balance(m, un.stats(m))
        if not admin and bal < offer["price"]:
            return Reply.error("You need %d more Sigils to save this streak." % (offer["price"] - bal), 400)
        with db.transaction():
            for day in offer["days"]:
                db.execute("INSERT OR IGNORE INTO sfreeze(uid,day,price,ts) VALUES(?,?,?,?)", (me, day, 0 if admin else FREEZE_PRICE, ctx.now))
        return Reply({"ok": 1, "n": offer["n"], "bal": un.balance(m, un.stats(m)), "streak": streaks.calc(me)["cur"]})


@registry.register
class PromptOfTheDay(Action):
    """?a=prompt: today's question, my streak, a streak-saving offer, my Sigils and how many people answered."""
    name = "prompt"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        me, db, un = int(m["id"]), ctx.db, ctx.unlocks
        d = ctx.now // 86400
        sc = Streaks(db).calc(me, d)
        o = sc["offer"]
        fz = {"n": o["n"], "price": 0 if m["admin"] else o["price"], "was": o["was"], "after": o["after"]} if o else None
        return Reply({
            "streak": sc["cur"], "wk": sc["wk"], "best": sc["best"], "icy": sc["icy"], "fz": fz, "fzp": FREEZE_PRICE,
            "bal": un.balance(m, un.stats(m)), "ms": [list(x) for x in STREAK_BONUS], "day": d, "text": DailyPrompt.for_day(d),
            "n": int(db.value("SELECT COUNT(*) FROM posts p JOIN users u ON u.id=p.uid WHERE p.pd=? AND u.priv=0 AND p.vis=0 AND p.hold=0", (d,), 0)),
            "done": 1 if db.value("SELECT 1 FROM posts WHERE uid=? AND pd=?", (me, d)) else 0,
        })
