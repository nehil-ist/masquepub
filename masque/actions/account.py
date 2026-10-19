"""Account actions: me, signup, login, logout, recover, newrc, pw, delacct."""
import hmac
import time

from ..accounts import AccountEraser
from ..config import ascii_lower
from ..security import byte_len, php_substr, php_trim
from .base import Action, Context, Reply, registry
from .site import SiteSettings


def _maintenance_text(ctx: Context):
    return SiteSettings(ctx.db).maintenance()


class PasswordRules:
    """Length limits every new password has to meet (bcrypt only reads 72 bytes)."""

    @staticmethod
    def check(pw: str, short_msg: str = "Password needs at least 8 characters."):
        if byte_len(pw) < 8:
            return Reply.error(short_msg, 400)
        if byte_len(pw) > 72:
            return Reply.error("Password can be at most 72 characters.", 400)
        return None


@registry.register
class Me(Action):
    """?a=me: who am I, plus the CSRF token and the site status. Makes the session for a first-time visitor."""
    name = "me"
    maintenance_exempt = True

    def handle(self, ctx: Context) -> Reply:
        session = ctx.begin_session()
        me = ctx.users.me()
        if me is None and ctx.users.account_gone:
            me = False  # signed in as an account that was deleted: PHP answers false, not null
        return Reply({"me": me, "csrf": session.get("c"), "mt": _maintenance_text(ctx),
                      "rf": SiteSettings(ctx.db).refresh(), "mailok": 1 if ctx.mailer.enabled() else 0})


@registry.register
class Signup(Action):
    name = "signup"
    maintenance_exempt = True

    def handle(self, ctx: Context) -> Reply:
        if _maintenance_text(ctx)["on"]:
            return Reply.error("Masque is down for maintenance right now. Please try again later.", 503)
        n = php_trim(ctx.form("name"))
        p = ctx.form("pw")
        if not ctx.names.valid(n):
            return Reply.error("Usernames are 3 to 20 letters, numbers or _.", 400)
        bad = PasswordRules.check(p)
        if bad:
            return bad
        taken = Reply.error("That username is taken.", 409)
        if ctx.names.reserved(n) or ctx.names.clash(n, 0):
            return taken
        au = ctx.cfg.admin_user
        if au != "" and ctx.names.skeleton(au) == ctx.names.skeleton(n):
            return taken
        ctx.limiter.throttle("su:" + ctx.ip.cip(), 5, 3600)
        nid = ctx.accounts.next_id_insert(n, ctx.hasher.hash(p))
        if nid == -1:
            return taken
        if nid == 0:
            return Reply.error("Please try again.", 503)
        code, code_hash = ctx.codes.new()
        ctx.db.execute("UPDATE users SET rc=? WHERE id=?", (code_hash, nid))
        ctx.accounts.sign_in(nid, 0)
        return Reply({"me": ctx.users.me(), "rc": code})


@registry.register
class Login(Action):
    name = "login"
    maintenance_exempt = True

    def handle(self, ctx: Context) -> Reply:
        db, cfg = ctx.db, ctx.cfg
        ip = ctx.ip.login_key()
        nm = php_substr(php_trim(ctx.form("name")), 64)
        un = "u:" + ascii_lower(nm)
        pw = ctx.form("pw")
        db.execute("DELETE FROM tries WHERE ts<?", (int(time.time()) - 900,))
        # one limit per address, and one per username in case the address is ever wrong or shared
        if int(db.value("SELECT COUNT(*) FROM tries WHERE ip=?", (ip,), 0)) >= 10 or int(db.value("SELECT COUNT(*) FROM tries WHERE ip=?", (un,), 0)) >= 100:
            return Reply.error("Too many attempts. Try again in 15 minutes.", 429)
        au, ap = cfg.admin_user, cfg.admin_password
        if au != "" and ctx.names.valid(au) and byte_len(ap) >= 8 and ascii_lower(nm) == ascii_lower(au) \
                and hmac.compare_digest(ap.encode(), pw.encode()):
            ctx.accounts.admin_sync(au, ap)
        u = db.one("SELECT id,pw,sv FROM users WHERE name=?", (nm,))
        if not u:
            ctx.hasher.dummy()  # same work whether or not the username exists
        if not u or not ctx.hasher.verify(pw, u["pw"]):
            db.execute("INSERT INTO tries VALUES(?,?)", (ip, int(time.time())))
            db.execute("INSERT INTO tries VALUES(?,?)", (un, int(time.time())))
            return Reply.error("Wrong username or password.", 401)
        mt = _maintenance_text(ctx)
        if mt["on"] and not ctx.users.admins.is_admin(nm):
            return Reply.error((mt["msg"] if mt["msg"] != "" else "Masque is down for maintenance right now.")
                               + " Only admins can sign in until it is back.", 503)
        ctx.accounts.sign_in(u["id"], int(u["sv"]))
        return Reply({"me": ctx.users.me()})


@registry.register
class Recover(Action):
    """?a=recover: new password from the recovery code. Signs out every other device."""
    name = "recover"
    maintenance_exempt = True

    def handle(self, ctx: Context) -> Reply:
        if _maintenance_text(ctx)["on"]:
            return Reply.error("Masque is down for maintenance right now. Please try again later.", 503)
        nm = php_substr(php_trim(ctx.form("name")), 64)
        p = ctx.form("pw")
        bad = PasswordRules.check(p, "New password needs at least 8 characters.")
        if bad:
            return bad
        ctx.limiter.throttle("rcv:" + ctx.ip.cip(), 10, 900)
        ctx.limiter.throttle("rcvu:" + ascii_lower(nm), 30, 900)
        u = ctx.db.one("SELECT id,rc,sv FROM users WHERE name=?", (nm,))
        if not u or u["rc"] == "":
            ctx.hasher.dummy()
        if not u or u["rc"] == "" or not ctx.hasher.verify(ctx.codes.norm(ctx.form("code")), u["rc"]):
            return Reply.error("That username and recovery code do not match.", 401)
        code, code_hash = ctx.codes.new()
        sv = int(u["sv"]) + 1
        ctx.db.execute("UPDATE users SET pw=?,rc=?,sv=? WHERE id=?", (ctx.hasher.hash(p), code_hash, sv, u["id"]))
        ctx.accounts.forget_other_devices(u["id"])
        ctx.accounts.sign_in(int(u["id"]), sv)
        return Reply({"me": ctx.users.me(), "rc": code})


@registry.register
class Logout(Action):
    name = "logout"
    maintenance_exempt = True

    def handle(self, ctx: Context) -> Reply:
        s = ctx.session
        if s.get("d"):
            ctx.db.execute("DELETE FROM devices WHERE tok=?", (s.get("d"),))
        s.destroy()
        return Reply({"ok": 1})


@registry.register
class NewRecoveryCode(Action):
    name = "newrc"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.accounts.confirm_password(m["id"], ctx.form("pw"))
        code, code_hash = ctx.codes.new()
        ctx.db.execute("UPDATE users SET rc=? WHERE id=?", (code_hash, m["id"]))
        ctx.users.reset()
        return Reply({"rc": code, "me": ctx.users.me()})


@registry.register
class ChangePassword(Action):
    """?a=pw: change the password; every other device is signed out, this one stays."""
    name = "pw"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.accounts.confirm_password(m["id"], ctx.form("old"), "Current password is wrong.")
        p = ctx.form("new")
        bad = PasswordRules.check(p, "New password needs at least 8 characters.")
        if bad:
            return bad
        ctx.db.execute("UPDATE users SET pw=?,sv=sv+1 WHERE id=?", (ctx.hasher.hash(p), m["id"]))
        ctx.mailer.note(m["id"], "Your Masque password was changed",
                        "The password for your Masque account was just changed from Settings, and your other devices were signed out. "
                        "If this was not you, use your recovery code to take the account back.")
        s = ctx.session
        sv = int(ctx.db.value("SELECT sv FROM users WHERE id=?", (m["id"],)))
        s.set("sv", sv)
        tok = str(s.get("d") or "")
        ctx.db.execute("DELETE FROM devices WHERE uid=? AND tok<>?", (m["id"], tok))
        ctx.db.execute("UPDATE devices SET sv=? WHERE tok=?", (sv, tok))
        s.regenerate()
        return Reply({"ok": 1})


@registry.register
class DeleteAccount(Action):
    name = "delacct"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        if ascii_lower(m["name"]) == ascii_lower(ctx.cfg.admin_user):
            return Reply.error("This account is set by the ADMIN_USER variable on the server. Remove or change that variable first.", 403)
        ctx.accounts.confirm_password(m["id"], ctx.form("pw"))
        AccountEraser(ctx).erase(m["id"], m["name"])
        ctx.session.destroy()
        return Reply({"ok": 1})
