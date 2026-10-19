"""Rate limits that depend on how new the account is (PHP: newsecs, isnew, lim, nolinks)."""
import re
import time

_LINK = re.compile(
    r"(https?://|www\.|\b[a-z0-9-]+\.(com|net|org|io|co|me|ly|gg|xyz|app|dev|info|biz|ru|cn|tk|ml|ga|cf|gq|link|click|top|site|online|shop|live|tv|to|ws|cc)\b)",
    re.I)


class Limits:
    """New accounts: tighter limits for the first day, no links for the first hour. Admins and older accounts are never affected."""

    def __init__(self, ctx):
        self.ctx = ctx
        self._joined = {}

    def is_new(self, m, window: int = 86400) -> bool:
        if self.ctx.users.is_admin(m):
            return False
        window = min(window, self.ctx.cfg.newacct_secs)
        uid = int(m["id"])
        if uid not in self._joined:
            self._joined[uid] = int(self.ctx.db.value("SELECT ts FROM users WHERE id=?", (uid,), 0) or 0)
        return time.time() - self._joined[uid] < window

    def lim(self, key: str, maximum: int, sec: int, m, new_maximum: int, new_sec: int):
        """Usual limit for everyone, a lower one while the account is new; admins have none."""
        if self.ctx.users.is_admin(m):
            return
        lm = self.ctx.limiter
        if self.is_new(m):
            if lm.count(key, new_sec) >= new_maximum:
                self.ctx.deny("New accounts have lower limits for the first day. Try again in a bit.", 429)
            lm.add(key)
            return
        if maximum > 0:
            lm.throttle(key, maximum, sec)

    def throttle(self, key: str, maximum: int, sec: int):
        self.ctx.limiter.throttle(key, maximum, sec)

    def nolinks(self, m, text: str):
        if self.is_new(m, 3600) and _LINK.search(str(text)):
            self.ctx.deny("Links are turned off for the first hour on a new account.", 400)
