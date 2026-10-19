"""Gates every migrated action passes before it runs (PHP: the checks at the top of `if ($a) {...}`)."""
from .actions.base import Action, Context, Reply
from .actions.site import SiteSettings


class MaintenanceGate:
    """While maintenance mode is on, everyone except admins is held back with the admin's message.
    Actions that set `maintenance_exempt` (me, mtstat, rfstat, logout, login, signup, recover) skip the gate."""

    def check(self, ctx: Context, action: Action):
        if action.maintenance_exempt:
            return None
        mt = SiteSettings(ctx.db).maintenance()
        if not mt["on"]:
            return None
        m = ctx.users.me()
        if m and m["admin"]:
            return None
        return Reply({"e": "Masque is down for maintenance.", "mt": 1, "msg": mt["msg"]}, 503)
