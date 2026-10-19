"""Recovery email: sending through Brevo, one-time links, security notices (PHP: mail_*, mtok_*)."""
import hashlib
import html as _html
import json
import re
import secrets
import time
import urllib.error
import urllib.request

from .security import php_trim


def _x(s) -> str:
    return _html.escape(str(s), quote=True).replace("&#x27;", "&#039;")  # PHP htmlspecialchars(ENT_QUOTES)


class Mailer:
    """Turned on only when BREVO_API_KEY, MAIL_FROM, MAIL_KEY (16+ chars) and a clean SITE_URL are all set."""
    _SITE_RE = re.compile(r"https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._/-]*)?")

    def __init__(self, cfg, db, vault, limiter):
        self.cfg, self.db, self.vault, self.limiter = cfg, db, vault, limiter

    _LOCAL = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    _DOMAIN = r"([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    _ADDR = re.compile(_LOCAL + "@" + _DOMAIN)

    @classmethod
    def valid_address(cls, em: str) -> bool:
        """About what PHP's FILTER_VALIDATE_EMAIL accepts: a dotted local part, a domain with at least one dot."""
        local = em.partition("@")[0]
        return len(em) <= 120 and len(local) <= 64 and cls._ADDR.fullmatch(em) is not None

    @property
    def site(self) -> str:
        return self.cfg.site_url

    def enabled(self) -> bool:
        c = self.cfg
        return bool(c.brevo_key and c.mail_from and len(c.mail_key) >= 16 and self._SITE_RE.fullmatch(self.site))

    def daily_cap_reached(self) -> bool:
        return self.limiter.count("mailg", 86400) >= self.cfg.mail_daily_max

    # -- the look of every email --
    def render(self, title: str, text: str, link: str = "", btn: str = "Open link") -> str:
        ar = "font-family:Arial,Helvetica,sans-serif"
        pi = "font-family:Pirata One,UnifrakturCook,Old English Text MT,Georgia,serif"
        ps = "".join(
            '<p style="margin:0 0 16px;font-size:20px;line-height:1.45;color:#16352a;%s">%s</p>' % (pi, _x(p).replace("\n", "<br />\n"))
            for p in re.split(r"\n\s*\n", php_trim(text)))
        bt = ""
        if link != "":
            bt = ('<table role="presentation" cellpadding="0" cellspacing="0" style="margin:10px 0 24px"><tr><td style="background:#3d4447;'
                  'border:2px solid #1b2420;border-radius:10px;box-shadow:3px 3px 0 #1b2420"><a href="%s" style="display:inline-block;'
                  'padding:13px 26px;%s;font-size:22px;font-weight:normal;letter-spacing:1px;color:#ffffff;text-decoration:none">%s</a>'
                  '</td></tr></table><p style="margin:0 0 4px;font-size:12px;line-height:1.5;color:#5d7064;%s">Button not working? Paste this '
                  'into your browser:</p><p style="margin:0;font-size:12px;line-height:1.5;word-break:break-all;%s"><a href="%s" '
                  'style="color:#16352a">%s</a></p>') % (_x(link), pi, _x(btn), ar, ar, _x(link), _x(link))
        pre = _x(re.sub(r"\s+", " ", str(text))[:90])
        font = ('<style>@font-face{font-family:"Pirata One";src:url(%s/assets/fonts/PirataOne-Regular.ttf) format("truetype");'
                'font-display:swap}</style>' % _x(self.site)) if self.site != "" else ""
        return ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<meta name="color-scheme" content="light"><title>' + _x(title) + "</title>" + font + "</head>"
                '<body style="margin:0;padding:0;background:#e8ede4"><div style="display:none;max-height:0;overflow:hidden;opacity:0;'
                'color:#e8ede4">' + pre + "</div>"
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e8ede4"><tr><td align="center" '
                'style="padding:32px 16px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px">'
                '<tr><td align="center" style="padding:0 0 20px;' + pi + ';font-size:48px;line-height:1;color:#16352a">Mas<i>que</i></td></tr>'
                '<tr><td style="background:#ffffff;border:2px solid #1b2420;border-radius:14px;box-shadow:5px 5px 0 #1b2420;padding:30px 28px">'
                '<h1 style="margin:0 0 18px;' + pi + ';font-size:30px;line-height:1.15;font-weight:normal;color:#16352a">' + _x(title) + "</h1>"
                + ps + bt + "</td></tr>"
                '<tr><td align="center" style="padding:24px 8px 0;font-size:12px;line-height:1.6;color:#5d7064;' + ar + '">Masque. No real '
                "names, ever.<br>You got this because someone used this address on Masque. If that was not you, you can ignore it.</td></tr>"
                "</table></td></tr></table></body></html>")

    def send(self, to: str, subject: str, text: str, link: str = "", btn: str = "Open link") -> bool:
        """One email through Brevo's HTTPS API. True when Brevo accepted it."""
        url = "https://api.brevo.com/v3/smtp/email"
        if self.cfg.brevo_url and re.match(r"http://(127\.0\.0\.1|localhost)[:/]", self.site):
            url = self.cfg.brevo_url  # local testing only
        body = json.dumps({
            "sender": {"name": self.cfg.mail_name, "email": self.cfg.mail_from},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": self.render(subject, text, link, btn),
            "textContent": text + ("\n\n" + link if link != "" else ""),
        })
        req = urllib.request.Request(url, body.encode(), method="POST", headers={
            "api-key": self.cfg.brevo_key, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception:
            code = 0
        if code < 200 or code >= 300:
            return False
        self.limiter.add("mailg")
        return True

    def note(self, uid: int, subject: str, text: str, addr=None):
        """Security notice to a saved email. Silent when mail is off, there is no address, or the daily cap is used up."""
        if not self.enabled():
            return
        if addr is None:
            enc = self.db.value("SELECT mail FROM users WHERE id=?", (uid,))
            addr = self.vault.decrypt(enc) if enc else ""
        if not addr or self.daily_cap_reached():
            return
        try:
            self.send(addr, subject, text)
        except Exception:
            pass


class MailTokens:
    """One-time links: only a hash of the token is stored. kind 'v' = confirm a new email, 'r' = reset a password."""
    _RE = re.compile(r"[a-f0-9]{48}")

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _h(t: str) -> str:
        return hashlib.sha256(str(t).encode()).hexdigest()

    def new(self, uid: int, kind: str, val: str, ttl: int) -> str:
        t = secrets.token_hex(24)
        now = int(time.time())
        self.db.execute("DELETE FROM mailtok WHERE exp<?", (now,))
        self.db.execute("DELETE FROM mailtok WHERE uid=? AND kind=?", (uid, kind))
        self.db.execute("INSERT INTO mailtok(h,uid,kind,val,exp) VALUES(?,?,?,?,?)", (self._h(t), uid, kind, val, now + ttl))
        return t

    def get(self, t: str, kind: str):
        if not self._RE.fullmatch(str(t)):
            return None
        return self.db.one("SELECT uid,val FROM mailtok WHERE h=? AND kind=? AND exp>?", (self._h(t), kind, int(time.time())))

    def delete(self, t: str):
        self.db.execute("DELETE FROM mailtok WHERE h=?", (self._h(t),))
