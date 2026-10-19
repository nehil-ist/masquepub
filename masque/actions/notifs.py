"""The bell, signed-in devices and web push: notifs, devices, devout, devoutall, pushkey, pushsub, pushoff, pushtest."""
import hmac
import time

from ..notify import PushService, b64ud
from .base import Action, Context, Reply, registry


@registry.register
class Notifs(Action):
    """?a=notifs: the last 100 alerts (and mark them all seen)."""
    name = "notifs"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        db.execute("DELETE FROM notifs WHERE ts<? AND NOT (kind='gift' AND pid IN (SELECT id FROM gifts WHERE opened=0))", (int(time.time()) - 2592000,))
        rows = db.all("SELECT n.id,n.kind,n.pid,n.ts,n.seen,n.mid,mk.name mkn,mk.avatar mka,u.name,u.nick,u.avatar,p.cap FROM notifs n "
                      "JOIN users u ON u.id=n.actor LEFT JOIN posts p ON p.id=n.pid LEFT JOIN masks mk ON mk.id=n.mid "
                      "WHERE n.uid=? ORDER BY n.id DESC LIMIT 100", (m["id"],))
        for x in rows:
            kind, pid = x["kind"], int(x["pid"] or 0)
            if kind in ("gment", "gall"):
                x["cap"] = str(db.value("SELECT name FROM gchats WHERE id=?", (pid,)) or "")
            if kind == "reveal":
                x["cap"] = str(db.value("SELECT name FROM masks WHERE uid=(SELECT actor FROM notifs WHERE id=?)", (x["id"],)) or "")
            # a post that was public when the alert arrived may have been switched to Friends / Only me since: its caption must not keep showing
            if kind not in ("gment", "gall", "reveal", "gift") and pid > 0 and not ctx.access.can_view(pid, m["id"]):
                x["cap"] = ""
                x["gone"] = 1
            if kind == "gift":
                x["cap"] = str(db.value("SELECT msg FROM gifts WHERE id=? AND uid=?", (pid, m["id"])) or "")
                x["cnt"] = int(db.value("SELECT COUNT(*) FROM gitems WHERE gid=?", (pid,), 0))
                x["opened"] = int(db.value("SELECT opened FROM gifts WHERE id=? AND uid=?", (pid, m["id"]), 0) or 0)
            if int(x["mid"] or 0) > 0:
                x["name"], x["nick"], x["avatar"] = x["mkn"], "", x["mka"]
            for k in ("mid", "mkn", "mka"):
                del x[k]
        db.execute("UPDATE notifs SET seen=1 WHERE uid=?", (m["id"],))
        return Reply({"list": rows})


@registry.register
class Devices(Action):
    """?a=devices: where I am signed in."""
    name = "devices"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        sv = int(db.value("SELECT sv FROM users WHERE id=?", (m["id"],), 0) or 0)
        db.execute("DELETE FROM devices WHERE uid=? AND sv<>?", (m["id"], sv))
        cur = str(ctx.session.get("d") or "")
        out = [{"n": int(r["n"]), "label": r["label"], "ts": int(r["ts"]), "last": int(r["last"]),
                "cur": 1 if hmac.compare_digest(cur.encode(), str(r["tok"]).encode()) else 0}
               for r in db.all("SELECT n,tok,label,ts,last FROM devices WHERE uid=? ORDER BY last DESC", (m["id"],))]
        return Reply({"list": out})


@registry.register
class DeviceOut(Action):
    """?a=devout: sign one other device out."""
    name = "devout"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("dev:%d" % m["id"], 30, 600)
        ctx.db.execute("DELETE FROM devices WHERE n=? AND uid=? AND tok<>?", (ctx.int_form("id"), m["id"], str(ctx.session.get("d") or "")))
        return Reply({"ok": 1})


@registry.register
class DeviceOutAll(Action):
    """?a=devoutall: sign every other device out."""
    name = "devoutall"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("dev:%d" % m["id"], 30, 600)
        ctx.db.execute("DELETE FROM devices WHERE uid=? AND tok<>?", (m["id"], str(ctx.session.get("d") or "")))
        return Reply({"ok": 1})


def _service(ctx: Context) -> PushService:
    from flask import request
    return PushService(ctx.db, ctx.cfg.site_url, request.host)


@registry.register
class PushKey(Action):
    """?a=pushkey: the server's public push key."""
    name = "pushkey"

    def handle(self, ctx: Context) -> Reply:
        ctx.users.need()
        try:
            keys = _service(ctx).keys()
        except Exception:
            keys = None
        if not keys:
            return Reply.error("Push notifications are not available on this server.", 501)
        return Reply({"key": keys["pub"]})


@registry.register
class PushSubscribe(Action):
    """?a=pushsub: remember this browser's push address (newest 10 per person)."""
    name = "pushsub"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        ctx.limits.throttle("pushs:%d" % m["id"], 20, 600)
        ep, pk, au = ctx.form("ep"), ctx.form("k"), ctx.form("a")
        if not _service(ctx).host_ok(ep) or len(b64ud(pk)) != 65 or len(b64ud(au)) < 16 or len(au) > 64:
            return Reply.error("This browser cannot receive notifications from here.", 400)
        db.execute("INSERT OR REPLACE INTO pushsubs(uid,ep,k,a,ts) VALUES(?,?,?,?,?)", (m["id"], ep, pk, au, int(time.time())))
        db.execute("DELETE FROM pushsubs WHERE uid=? AND id NOT IN (SELECT id FROM pushsubs WHERE uid=? ORDER BY id DESC LIMIT 10)", (m["id"], m["id"]))
        return Reply({"ok": 1})


@registry.register
class PushOff(Action):
    """?a=pushoff"""
    name = "pushoff"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.db.execute("DELETE FROM pushsubs WHERE uid=? AND ep=?", (m["id"], ctx.form("ep")))
        return Reply({"ok": 1})


@registry.register
class PushTest(Action):
    """?a=pushtest: send myself a test alert."""
    name = "pushtest"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.limits.throttle("pusht:%d" % m["id"], 5, 600)
        if not ctx.db.value("SELECT 1 FROM pushsubs WHERE uid=?", (m["id"],)):
            return Reply.error("Turn notifications on first.", 400)
        ctx.notes.push_now(m["id"], "Masque", "Notifications are working.", "./", "test")
        return Reply({"ok": 1})
