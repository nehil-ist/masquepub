"""The pages: the HTML shell every visitor loads, the privacy and terms pages, the manifest, the service worker and the pretty /u/ and /p/ links."""
import base64
import hashlib
import html
import os
import re
from urllib.parse import quote

from .assets import AssetFiles
from .legal_content import MAIL_OFF, MAIL_ON, PAGES
from .ogcard import CardKeys, pillow_ready
from .php import php_trim

_UP_NAME = re.compile(r"^[a-f0-9]{24}\.(jpg|png|webp|gif)$")
_GOOGLE_FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Pirata+One&family=Figtree:wght@400;600;700&family=Space+Mono:wght@400;700'
                 '&family=Lora:wght@400;700&family=Playfair+Display:wght@400;700&family=Nunito:wght@400;700&family=Caveat:wght@400;700&display=swap" rel="stylesheet">')


def esc(x) -> str:
    """PHP htmlspecialchars($x, ENT_QUOTES)."""
    return html.escape(str(x), quote=False).replace('"', "&quot;").replace("'", "&#039;")


class PrettyLinks:
    """/u/<name> and /p/<id> open the same page as ?u= and ?p= (old links keep working). `base` is the folder the app lives in; it becomes
    <base href> so ?a=, assets/ and ?img= still resolve from the app root."""
    SKIP = ("a", "img", "stk", "og", "ogp", "ogdiag", "manifest", "sw")
    _PATH = re.compile(r"^(.*?)/(u|p)/([^/]*)/?$")

    @classmethod
    def resolve(cls, path: str, args, method: str):
        """(base, u, p): base '' when the path is not a pretty link; u / p only when the value is valid."""
        u, p, base = args.get("u", ""), args.get("p", ""), ""
        if method in ("GET", "HEAD") and not any(k in args for k in cls.SKIP):
            m = cls._PATH.match(path)
            if m:
                base = m.group(1) + "/"
                if m.group(2) == "u" and re.fullmatch(r"[A-Za-z0-9_]{3,20}", m.group(3)):
                    u = m.group(3)
                elif m.group(2) == "p" and re.fullmatch(r"[0-9]{1,12}", m.group(3)):
                    p = m.group(3)
        return base, u, p


class ShellPage:
    """The page every visitor loads (templates/shell.html). Its head carries the link-preview tags: for a profile or a public post
    they describe that profile or post, otherwise the site."""

    def __init__(self, ctx, files: AssetFiles = None):
        self.ctx = ctx
        self.files = files or AssetFiles(ctx.cfg.root)
        self.template = (ctx.cfg.root / "masque" / "templates" / "shell.html").read_text(encoding="utf-8")

    def site_root(self, scheme_https: bool, host: str) -> str:
        sp = self.ctx.cfg.site_url or ("%s://%s" % ("https" if scheme_https else "http", host or "localhost"))
        return sp.rstrip("/")

    def meta(self, sp: str, u: str, p: str) -> dict:
        ctx, f = self.ctx, self.files
        m = {"ot": "Masque", "od": "Post, chat and ask anonymously. No email needed.", "ou": sp + "/",
             "oi": "%s/assets/og.png?v=%d" % (sp, f.mtime("og.png")), "big": 1,
             "oa": "Masque: post, chat and ask anonymously, with a laughing mask"}
        cards = pillow_ready()
        pu = ctx.db.one("SELECT name,nick,bio,avatar,priv FROM users WHERE name=?", (u,)) if u != "" and ctx.names.valid(u) else None
        if pu:
            m["ot"] = ("%s (@%s)" % (pu["nick"], pu["name"]) if str(pu["nick"] or "") != "" else "@" + pu["name"]) + " on Masque"
            m["ou"] = sp + "/u/" + quote(pu["name"], safe="")
            bio = php_trim(pu["bio"] or "")
            m["od"] = "Private account. Send a friend request on Masque to see their posts." if int(pu["priv"]) else (bio[:160] if bio != "" else "See their profile on Masque.")
            if cards:
                m["oi"] = "%s/?og=%s&v=%s" % (sp, quote(pu["name"], safe=""), CardKeys.profile(pu))
                m["oa"] = m["ot"] + ", profile card"
            else:
                m["oi"] = sp + ("/?img=" + pu["avatar"] if _UP_NAME.match(str(pu["avatar"] or "")) else "/assets/og-avatar.png")
                m["big"] = 0
        pp = ctx.access.public_post(p) if u == "" and re.fullmatch(r"[0-9]{1,12}", p) else None
        if pp:
            if int(pp["anon"]) or int(pp["mid"]) > 0:
                who = str(pp["mkn"]) if int(pp["mid"]) > 0 and str(pp["mkn"] or "") != "" else "Masque"
            else:
                who = str(pp["nick"]) if str(pp["nick"] or "") != "" else str(pp["name"])
            m["ot"], m["ou"] = who + " on Masque", "%s/p/%d" % (sp, int(pp["id"]))
            cap = php_trim(re.sub(r"\s+", " ", str(pp["cap"] or "")))
            m["od"] = cap[:160] if cap != "" else ("Photo post on Masque." if str(pp["img"] or "") != "" else "See this post on Masque.")
            if cards:
                m["oi"] = "%s/?ogp=%d&v=%s" % (sp, int(pp["id"]), CardKeys.post(pp))
                m["oa"] = m["ot"] + ", post card"
            elif str(pp["img"] or "") != "" and not int(pp["sens"]) and not int(pp["anon"]) and _UP_NAME.match(str(pp["img"])):
                m["oi"], m["big"] = sp + "/?img=" + pp["img"], 0
        return m

    def render(self, base: str, u: str, p: str, nonce: str, https: bool, host: str) -> str:
        f = self.files
        m = self.meta(self.site_root(https, host), u, p)
        local_fonts = (f.dir / "fonts" / "fonts.css").is_file()
        ot = esc(m["ot"])
        vals = {
            "base": '<base href="%s">' % esc(base) if base != "" else "",
            "nonce": nonce, "ot": ot, "od": esc(m["od"]), "ou": esc(m["ou"]), "oi": esc(m["oi"]),
            "alt": esc(m["oa"]) if m["big"] else ot,
            "bigmeta": ('<meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200">'
                        '<meta property="og:image:height" content="630">') if m["big"] else "",
            "card": "summary_large_image" if m["big"] else "summary",
            "fonts": ('<link rel="stylesheet" href="assets/fonts/fonts.css?v=%d">' % f.mtime("fonts/fonts.css")) if local_fonts else _GOOGLE_FONTS,
            "css": f.pick("style.css"), "css_v": str(f.version("style.css")),
            "js": f.pick("app.js"), "js_v": str(f.version("app.js")),
        }
        return re.sub(r"@@(\w+)@@", lambda mo: vals[mo.group(1)], self.template)

    def csp(self, nonce: str) -> str:
        """Fonts saved on this site (tools/fetch-fonts.sh)? then Google is not used or allowed."""
        local = (self.files.dir / "fonts" / "fonts.css").is_file()
        gfs = "" if local else " https://fonts.googleapis.com"
        gff = "'self'" if local else "https://fonts.gstatic.com"
        return ("default-src 'self'; script-src 'self' 'nonce-%s'; style-src 'self' 'unsafe-inline'%s; font-src %s; img-src 'self' data: blob:; "
                "connect-src 'self' blob:; worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
                "frame-ancestors 'none'" % (nonce, gfs, gff))

    @staticmethod
    def new_nonce() -> str:
        return base64.b64encode(os.urandom(16)).decode()


class LegalPages:
    """?page=privacy and ?page=terms: public, no sign-in. CONTACT (an email or link) on the server shows a way to reach you."""
    NAMES = tuple(PAGES)

    def __init__(self, cfg, files: AssetFiles, mail_on: bool):
        self.cfg, self.files, self.mail_on = cfg, files, mail_on

    def reach(self) -> str:
        ct = self.cfg.contact
        if ct != "":
            return "You can reach the people who run Masque at <b>%s</b>." % esc(ct)
        return esc("You can reach the people who run Masque by using Report inside the app, or by sending a message to an admin.")

    def render(self, name: str) -> str:
        title, sub, sections = PAGES[name]
        css = self.files.pick("style.css")
        out = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
               '<title>%s - Masque</title><meta name="robots" content="index"><link rel="icon" type="image/png" href="assets/icon-192.png">'
               '<link rel="stylesheet" href="assets/%s?v=%d"></head><body><main class="legal"><a class="legal-back" href="./">&larr; Back to Masque</a>'
               '<h1 class="logo">%s</h1><p class="sub">%s</p>' % (esc(title), css, self.files.mtime(css), esc(title), esc(sub))]
        for head, text, extra in sections:
            body = esc(text)
            if extra == "mail":
                body += esc(MAIL_ON if self.mail_on else MAIL_OFF)
            elif extra:
                body += self.reach()
            out.append("<section><h2>%s</h2><p>%s</p></section>" % (esc(head), body))
        other = '<a href="?page=terms">Terms</a>' if name == "privacy" else '<a href="?page=privacy">Privacy</a>'
        out.append('<p class="hint legal-sw">%s</p></main></body></html>' % other)
        return "".join(out)


class ServiceWorker:
    """assets/sw.js with a cache name that follows the shell files' mtimes, so every deploy that changes app.js, style.css or sw.js starts a fresh cache."""

    def __init__(self, files: AssetFiles):
        self.files = files

    def cache_name(self) -> str:
        f = self.files
        return "mq-shell-" + hashlib.md5(("%d.%d.%d" % (f.mtime("sw.js"), f.version("app.js"), f.version("style.css"))).encode()).hexdigest()[:8]

    def script(self) -> str:
        src = (self.files.dir / "sw.js").read_text(encoding="utf-8")
        return re.sub(r'const V = "[^"]*";', lambda _: 'const V = "%s";' % self.cache_name(), src, count=1)
