"""Unlockable themes, the Sigil marketplace and the Sigil balance (PHP: unl_cat, shop_cat, unl_stats, unl_gate, sg_*, ev_*)."""
import os
import time

from .streaks import Streaks

# Which stat unlocks what: UNLOCKS[setting][id] = (stat, amount). Stats: p posts, c comments, l likes on your posts,
# f friends, s best prompt streak, d days on Masque. Anything not listed is free.
UNLOCKS = {
    "tbg": {"sunset": ("d", 2), "ocean": ("p", 3), "peach": ("d", 4), "dusk": ("c", 10), "forest": ("p", 5), "midnight": ("d", 7),
            "aurora": ("s", 3), "coral": ("l", 5), "lemon": ("f", 2), "berry": ("l", 15), "cocoa": ("c", 25), "ice": ("d", 10),
            "ember": ("s", 5), "sakura": ("f", 5), "moss": ("p", 15), "noir": ("l", 30)},
    "tbp": {"graph": ("p", 2), "fdots": ("d", 3), "fgrid": ("p", 4), "diag": ("c", 5), "hatch": ("c", 15), "check": ("f", 1),
            "zig": ("l", 10), "diamonds": ("d", 5), "rings": ("p", 8), "polka": ("f", 3), "stars": ("d", 7), "spot": ("l", 20),
            "fstripes": ("c", 30), "drift": ("s", 3), "snowfall": ("s", 5), "flow": ("s", 7), "scroll": ("p", 25),
            "twinkle": ("d", 14), "fireflies": ("s", 10)},
    "tcd": {"glass": ("p", 5)},
    "tfn": {"elegant": ("d", 3), "hand": ("c", 8)},
    "tas": {"hex": ("p", 5), "octagon": ("p", 12), "diamond": ("f", 4), "shield": ("l", 10), "pixel": ("c", 12)},
    "taf": {"rainbow": ("p", 3), "gold": ("p", 10), "royal": ("l", 40), "emerald": ("f", 3), "ruby": ("l", 25), "neon": ("d", 7),
            "pixel": ("c", 20), "prism": ("s", 5), "ember": ("s", 3), "snow": ("d", 14), "sakura": ("f", 10),
            "shimmer": ("s", 14), "thorns": ("p", 40)},
    "tcf": {"gold": ("p", 10), "royal": ("l", 40), "neon": ("d", 7), "pixel": ("c", 20), "snow": ("d", 14), "sakura": ("f", 10),
            "shimmer": ("s", 14), "thorns": ("p", 40), "chains": ("p", 25)},
}

# Themes bought with Sigils: SHOP[setting][id] = price.
SHOP = {
    "tbg": {"aurora": 120, "ember": 160, "sakura": 180, "noir": 260},
    "tbp": {"twinkle": 140, "snowfall": 150, "flow": 160, "fireflies": 220},
    "taf": {"prism": 200, "shimmer": 260, "thorns": 300, "royal": 320},
    "tcf": {"chains": 240, "shimmer": 260, "thorns": 300, "royal": 320},
}

# Limited time (Castle Night): anyone may pick these until the event ends; people who already have one equipped keep it.
EVENT_ITEMS = {
    "tbg": ("nightfall", "ashen"),
    "tbp": ("castle", "castlebw", "castlepaint"),
    "taf": ("bats", "batmono", "batpaint"),
    "tcf": ("bats", "batmono", "batpaint"),
}

# Admin exclusives (ids start with x_): admins, or people an admin gave them to.
ADMIN_ITEMS = {
    "tbg": ("x_void", "x_inferno", "x_cyber", "x_vapor", "x_abyss", "x_gilded", "x_nebula", "x_higan", "x_mardi", "x_moonlit", "x_csig"),
    "tbp": ("x_synth", "x_matrix", "x_embers", "x_cosmos", "x_scan", "x_lilies", "x_centi", "x_csigil", "x_cscript"),
    "tcd": ("x_crystal", "x_csigc"),
    "taf": ("x_nova", "x_hell", "x_voidf", "x_sov", "x_higanf", "x_csigf"),
    "tcf": ("x_aurora", "x_fire", "x_voidb", "x_chrome", "x_centib", "x_csigb"),
}

# Every id a profile may store, per setting (nothing typed by a user ever reaches the page). The list order is the picker order.
THEME_OPTIONS = {
    "tbg": ("", "nightfall", "ashen", "sage", "sky", "rose", "sand", "lilac", "sunset", "ocean", "aurora", "peach", "midnight", "mint",
            "slate", "dusk", "forest", "coral", "lemon", "berry", "cocoa", "ice", "ember", "sakura", "moss", "noir") + ADMIN_ITEMS["tbg"],
    "tbp": ("", "castle", "castlebw", "castlepaint", "grid", "graph", "dots", "fdots", "fgrid", "lines", "diag", "hatch", "check", "zig",
            "diamonds", "rings", "polka", "stars", "spot", "fstripes", "drift", "snowfall", "flow", "scroll", "twinkle",
            "fireflies") + ADMIN_ITEMS["tbp"],
    "tcd": ("", "flat", "glass", "outline") + ADMIN_ITEMS["tcd"],
    "tfn": ("", "serif", "elegant", "mono", "round", "hand"),
    "tas": ("", "squircle", "hex", "octagon", "diamond", "shield", "pixel"),
    "taf": ("", "bats", "batmono", "batpaint", "ring", "rainbow", "dash", "glow", "gold", "royal", "emerald", "ruby", "neon", "pixel",
            "prism", "ember", "snow", "sakura", "shimmer", "thorns") + ADMIN_ITEMS["taf"],
    "tpl": ("", "grid", "big"),
    "tcf": ("", "match", "bats", "batmono", "batpaint", "line", "gold", "royal", "neon", "pixel", "chains", "snow", "sakura", "shimmer",
            "thorns") + ADMIN_ITEMS["tcf"],
}

STREAK_BONUS = ((7, 30), (30, 120), (100, 400))  # a one-time Sigil bonus the first time the best streak reaches 7, 30 and 100 days


def _plural(n: int, one: str, many: str) -> str:
    return "%d %s" % (n, one if n == 1 else many)


class Unlocks:
    """What a person has unlocked, what they may pick, and their Sigils."""

    def __init__(self, ctx):
        self.ctx, self.db = ctx, ctx.db

    # -- the catalogue --
    @staticmethod
    def without_shop():
        """UNLOCKS minus the items that are sold instead (unl_cat_ms)."""
        return {k: {i: v for i, v in ids.items() if i not in SHOP.get(k, {})} for k, ids in UNLOCKS.items()}

    @staticmethod
    def need_text(stat: str, n: int) -> str:
        if stat == "p":
            return "Make " + _plural(n, "post", "posts")
        if stat == "c":
            return "Write " + _plural(n, "comment", "comments")
        if stat == "l":
            return "Get " + _plural(n, "like", "likes") + " on your posts"
        if stat == "f":
            return "Make " + _plural(n, "friend", "friends")
        if stat == "s":
            return "Answer the daily prompt %d days in a row" % n
        return "Be on Masque for " + _plural(n, "day", "days")

    @staticmethod
    def known_item(k: str, x: str) -> bool:
        """Is (setting, id) something an admin may give: a normal unlock, a Castle Night item or an admin exclusive."""
        return x in UNLOCKS.get(k, {}) or x in EVENT_ITEMS.get(k, ()) or x in ADMIN_ITEMS.get(k, ())

    # -- the Castle Night event --
    @staticmethod
    def event_end() -> int:
        e = os.environ.get("CASTLE_END", "")
        return int(e) if e.isdigit() and int(e) > 0 else 1793664000

    def event_on(self) -> bool:
        return time.time() < self.event_end()

    # -- stats and Sigils --
    def stats(self, m) -> dict:
        u, db = int(m["id"]), self.db
        ts = int(db.value("SELECT ts FROM users WHERE id=?", (u,), 0) or 0)
        return {
            "p": int(db.value("SELECT COUNT(*) FROM posts WHERE uid=?", (u,), 0)),
            "c": int(db.value("SELECT COUNT(*) FROM comments WHERE uid=?", (u,), 0)),
            "l": int(db.value("SELECT COUNT(*) FROM likes l JOIN posts p ON p.id=l.pid WHERE p.uid=? AND l.uid<>?", (u, u), 0)),
            "f": int(db.value("SELECT COUNT(*) FROM friends WHERE st=1 AND (a=? OR b=?)", (u, u), 0)),
            "s": Streaks(db).calc(u)["best"],
            "d": max(0, (int(time.time()) - ts) // 86400),
        }

    @staticmethod
    def streak_bonus(n: int) -> int:
        return sum(s for d, s in STREAK_BONUS if n >= d)

    def earned(self, st) -> int:
        return st["p"] * 5 + st["c"] * 2 + st["l"] + st["f"] * 8 + st["s"] * 6 + st["d"] * 4 + self.streak_bonus(st["s"])

    def balance(self, m, st) -> int:
        db, u = self.db, int(m["id"])
        spent = int(db.value("SELECT COALESCE(SUM(price),0) FROM shop WHERE uid=?", (u,), 0))
        spent += int(db.value("SELECT COALESCE(SUM(price),0) FROM sfreeze WHERE uid=?", (u,), 0))
        adj = int(db.value("SELECT COALESCE(SUM(amt),0) FROM sigadj WHERE uid=?", (u,), 0))
        return max(0, self.earned(st) + adj - spent)

    @staticmethod
    def legacy(k, x, st) -> bool:
        """Someone who already met an item's old unlock requirement keeps it free."""
        if x not in UNLOCKS.get(k, {}):
            return False
        stat, n = UNLOCKS[k][x]
        return st[stat] >= n

    def grants(self, m) -> list:
        return ["%s:%s" % (r["k"], r["id"]) for r in self.db.all("SELECT k,id FROM ugrants WHERE uid=?", (m["id"],))]

    # -- the gate: called when a theme setting is saved --
    def gate(self, m, k: str, x: str):
        """Stops a non-admin from picking something they have not unlocked (keeping what they already wear is fine)."""
        deny = self.ctx.deny
        if x == "" or m.get("admin"):
            return
        cur = str(m.get(k) or "")
        granted = bool(self.db.value("SELECT 1 FROM ugrants WHERE uid=? AND k=? AND id=?", (m["id"], k, x)))
        if x.startswith("x_"):
            if x == cur or granted:
                return
            deny("That theme is admin-only.", 403)
        if granted:
            return
        if x in SHOP.get(k, {}):
            if x == cur or self.legacy(k, x, self.stats(m)):
                return
            deny("Get this one in the Marketplace (Settings).", 403)
        if x in EVENT_ITEMS.get(k, ()):
            if self.event_on() or x == cur:
                return
            deny("Castle Night has ended, so this is not available any more.", 403)
        if x not in UNLOCKS.get(k, {}) or x == cur:
            return
        stat, n = UNLOCKS[k][x]
        st = self.stats(m)
        if st[stat] >= n:
            return
        deny("Still locked. %s (%d/%d)." % (self.need_text(stat, n), st[stat], n), 403)
