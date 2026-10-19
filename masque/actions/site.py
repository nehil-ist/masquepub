"""Site-wide status that every open page polls: maintenance mode and the forced-refresh token."""
from ..php import php_trim, strip_controls
from .base import Action, Context, Reply, registry


class SiteSettings:
    """Reads the `site` key/value table."""

    def __init__(self, db):
        self.db = db

    def _get(self, *keys) -> dict:
        marks = ",".join("?" * len(keys))
        return self.db.pairs("SELECT k,v FROM site WHERE k IN (%s)" % marks, keys)

    def maintenance(self) -> dict:
        r = self._get("mt", "mtmsg")
        return {"on": 1 if r.get("mt") == "1" else 0, "msg": str(r.get("mtmsg") or "")}

    def refresh(self) -> dict:
        r = self._get("rfv", "rfmsg")
        return {"v": str(r.get("rfv") or ""), "msg": str(r.get("rfmsg") or "")}


@registry.register
class MaintenanceStatus(Action):
    """?a=mtstat  (PHP: case 'mtstat')"""
    name = "mtstat"
    maintenance_exempt = True

    def handle(self, ctx: Context) -> Reply:
        return Reply(SiteSettings(ctx.db).maintenance())


@registry.register
class RefreshStatus(Action):
    """?a=rfstat  (PHP: case 'rfstat')"""
    name = "rfstat"
    maintenance_exempt = True

    def handle(self, ctx: Context) -> Reply:
        return Reply(SiteSettings(ctx.db).refresh())


@registry.register
class MaintenanceSet(Action):
    """?a=mtset (admin): turn maintenance mode on or off and set the message people see."""
    name = "mtset"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        if not m["admin"]:
            return Reply.error("Not allowed.", 403)
        on = "1" if ctx.flag("on") else "0"
        msg = php_trim(strip_controls(ctx.form("msg"))[:300])
        ctx.db.execute("INSERT OR REPLACE INTO site(k,v) VALUES('mt',?),('mtmsg',?)", (on, msg))
        ctx.adminlog.add(m, "maintenance " + ("on" if on == "1" else "off"), "")
        return Reply(SiteSettings(ctx.db).maintenance())
