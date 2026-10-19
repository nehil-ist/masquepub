"""Recovery-email actions: mailset, mailverify, mailrm, mailreq, mailreset. Email is optional (see Mailer.enabled)."""
import time

from ..config import ascii_lower
from ..security import byte_len, php_substr, php_trim
from .account import PasswordRules
from .base import Action, Context, Reply, registry


@registry.register
class MailSet(Action):
    """Save a new recovery email: a confirmation link goes to it first."""
    name = "mailset"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        mailer = ctx.mailer
        if not mailer.enabled():
            return Reply.error("Recovery email is not set up on this server.", 400)
        if mailer.daily_cap_reached():
            return Reply.error("Email is busy today. Try again tomorrow.", 503)
        ctx.accounts.confirm_password(m["id"], ctx.form("pw"))
        em = ascii_lower(php_trim(ctx.form("mail")))
        if not mailer.valid_address(em) or byte_len(em) > 120:
            return Reply.error("That does not look like an email address.", 400)
        ctx.limiter.throttle("mls:%d" % m["id"], 5, 3600)
        ctx.limiter.throttle("mlsi:" + ctx.ip.cip(), 10, 3600)  # only real send attempts count; wrong passwords have their own limit
        tok = ctx.tokens.new(m["id"], "v", ctx.users.vault.encrypt(em), 3600)
        sent = mailer.send(
            em, "Confirm your Masque recovery email",
            "Someone, hopefully you, asked to use this address as the recovery email for the Masque account @" + m["name"]
            + ".\n\nOpen the link below within 1 hour to confirm it. If this was not you, ignore this email and nothing will change.",
            mailer.site + "/?mv=" + tok, "Confirm email")
        if not sent:
            ctx.tokens.delete(tok)
            return Reply.error("Could not send the email right now. Check the address and try again later.", 502)
        return Reply({"ok": 1})


@registry.register
class MailVerify(Action):
    """Public: the secret link proves this person can read the inbox."""
    name = "mailverify"

    def handle(self, ctx: Context) -> Reply:
        ctx.limiter.throttle("mvf:" + ctx.ip.cip(), 20, 900)
        t = ctx.form("t")
        r = ctx.tokens.get(t, "v")
        if not r:
            return Reply.error("This link has expired or was already used. Ask for a new one in Settings.", 400)
        row = ctx.db.one("SELECT mail FROM users WHERE id=?", (r["uid"],))
        if row is None:
            ctx.tokens.delete(t)
            return Reply.error("This account no longer exists.", 400)
        old = row["mail"]
        ctx.db.execute("UPDATE users SET mail=? WHERE id=?", (r["val"], r["uid"]))
        ctx.tokens.delete(t)
        if old != "" and old != r["val"]:
            ctx.mailer.note(r["uid"], "Your Masque recovery email was changed",
                            "The recovery email on your Masque account was changed, so this address no longer receives password reset links. "
                            "If this was not you, sign in and change your password.", ctx.users.vault.decrypt(old))
        return Reply({"ok": 1})


@registry.register
class MailRemove(Action):
    name = "mailrm"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.accounts.confirm_password(m["id"], ctx.form("pw"))
        old = str(ctx.db.value("SELECT mail FROM users WHERE id=?", (m["id"],), ""))
        ctx.db.execute("UPDATE users SET mail='' WHERE id=?", (m["id"],))
        ctx.db.execute("DELETE FROM mailtok WHERE uid=?", (m["id"],))
        if old != "":
            ctx.mailer.note(m["id"], "Your Masque recovery email was removed",
                            "This address was removed as the recovery email for your Masque account and will not receive password reset links "
                            "any more. If this was not you, sign in and change your password.", ctx.users.vault.decrypt(old))
        ctx.users.reset()
        return Reply({"me": ctx.users.me()})


@registry.register
class MailRequest(Action):
    """Public: ask for a reset link. The answer (and the time it takes) is the same whether or not the account exists or has an email."""
    name = "mailreq"

    def handle(self, ctx: Context) -> Reply:
        t0 = time.monotonic()
        mailer = ctx.mailer
        if not mailer.enabled():
            return Reply.error("Email reset is not available here. Use your recovery code instead.", 400)
        nm = php_substr(php_trim(ctx.form("name")), 64)
        ctx.limiter.throttle("mrq:" + ctx.ip.cip(), 5, 3600)
        ctx.limiter.throttle("mrqu:" + ascii_lower(nm), 3, 3600)
        u = ctx.db.one("SELECT id,name,mail FROM users WHERE name=?", (nm,))
        addr = ctx.users.vault.decrypt(u["mail"]) if u and u["mail"] != "" else ""
        if u and addr != "":
            if mailer.daily_cap_reached():
                return Reply.error("Email is busy today. Use your recovery code or try again tomorrow.", 503)
            tok = ctx.tokens.new(u["id"], "r", "", 1800)
            if not mailer.send(
                    addr, "Reset your Masque password",
                    "A password reset was asked for the Masque account @" + u["name"]
                    + ".\n\nOpen the link below within 30 minutes to choose a new password. If this was not you, ignore this email: "
                      "your password has not changed.", mailer.site + "/?mr=" + tok, "Choose new password"):
                ctx.tokens.delete(tok)
        left = 1.5 - (time.monotonic() - t0)
        if left > 0:
            time.sleep(left)
        return Reply({"ok": 1})


@registry.register
class MailReset(Action):
    """Public: the secret link plus a new password. Signs in on this device and out everywhere else."""
    name = "mailreset"

    def handle(self, ctx: Context) -> Reply:
        ctx.limiter.throttle("mrs:" + ctx.ip.cip(), 20, 900)
        p = ctx.form("pw")
        bad = PasswordRules.check(p, "New password needs at least 8 characters.")
        if bad:
            return bad
        t = ctx.form("t")
        r = ctx.tokens.get(t, "r")
        if not r:
            return Reply.error("This link has expired or was already used. Ask for a new one.", 400)
        u = ctx.db.one("SELECT id,sv,mail FROM users WHERE id=?", (r["uid"],))
        if not u:
            ctx.tokens.delete(t)
            return Reply.error("This account no longer exists.", 400)
        sv = int(u["sv"]) + 1
        ctx.db.execute("UPDATE users SET pw=?,sv=? WHERE id=?", (ctx.hasher.hash(p), sv, u["id"]))
        ctx.db.execute("DELETE FROM mailtok WHERE uid=? AND kind='r'", (u["id"],))
        ctx.accounts.forget_other_devices(u["id"])
        ctx.accounts.sign_in(int(u["id"]), sv)
        ctx.mailer.note(u["id"], "Your Masque password was reset",
                        "The password for your Masque account was just reset with the link from your email, and every other device was "
                        "signed out. If this was not you, use your recovery code to take the account back.")
        return Reply({"me": ctx.users.me()})
