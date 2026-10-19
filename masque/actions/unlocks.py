"""Unlockable themes (PHP: case 'unl')."""
from ..unlockables import SHOP, UNLOCKS, Unlocks
from .base import Action, Context, Reply, registry


@registry.register
class UnlockList(Action):
    """?a=unl: what each theme needs, my progress, my Sigils, and what I already own."""
    name = "unl"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        un = ctx.unlocks
        req = {}
        for k, ids in Unlocks.without_shop().items():
            for i, (stat, n) in ids.items():
                req.setdefault(k, {})[i] = {"s": stat, "n": n, "t": Unlocks.need_text(stat, n)}
        for k, ids in SHOP.items():
            for i in ids:
                req.setdefault(k, {})[i] = {"s": "shop", "n": 1, "t": "Get it in the Marketplace"}
        st = un.stats(m)
        granted = un.grants(m)
        granted += ["%s:%s" % (k, i) for k, ids in SHOP.items() for i in ids if Unlocks.legacy(k, i, st)]
        return Reply({
            "st": st,
            "req": req,
            "admin": 1 if m.get("admin") else 0,
            "eq": {k: str(m.get(k) or "") for k in UNLOCKS},
            "gr": list(dict.fromkeys(granted)),
            "ev": {"on": 1 if un.event_on() else 0, "end": un.event_end()},
            "sg": {"bal": un.balance(m, st), "earned": un.earned(st)},
            "shop": SHOP,
        })
