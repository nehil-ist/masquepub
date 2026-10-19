"""Link-preview cards: ?og=<username> (profile), ?ogp=<post id> (public post), ?ogdiag (admin check of the card set-up)."""
import re
import sys
from pathlib import Path

from flask import Response

from ..ogcard import CardAssets, PostCard, ProfileCard, pillow_ready
from .base import FileBody, Route

_AVATAR = re.compile(r"^[a-f0-9]{24}\.(jpg|png|webp|gif)$")


class CardRoute(Route):
    """Shared answer: the PNG, or a redirect when the card cannot be drawn."""

    @staticmethod
    def assets(ctx) -> CardAssets:
        return CardAssets(ctx.cfg.root, ctx.cfg.data_dir)

    @staticmethod
    def png(path: Path) -> Response:
        return FileBody.response(path, "image/png", {"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"})

    @staticmethod
    def fallback(target: str) -> Response:
        return Response(status=302, headers={"X-OG-Fail": "card" if pillow_ready() else "nogd", "Location": target})


class ProfileCardRoute(CardRoute):
    key = "og"

    def serve(self, ctx) -> Response:
        n = self.arg_text("og")
        u = ctx.db.one("SELECT name,nick,bio,avatar,priv FROM users WHERE name=?", (n,)) if ctx.names.valid(n) else None
        f = None
        if u and pillow_ready():
            try:
                f = ProfileCard(self.assets(ctx), u).render()
            except Exception as e:  # a card that cannot be drawn must never break the page
                print("og card: %s" % e, file=sys.stderr)
        if f:
            return self.png(f)
        target = "assets/og.png"
        if u:
            target = "?img=" + u["avatar"] if _AVATAR.match(str(u["avatar"] or "")) else "assets/og-avatar.png"
        return self.fallback(target)


class PostCardRoute(CardRoute):
    key = "ogp"

    def serve(self, ctx) -> Response:
        pr = ctx.access.public_post(self.arg_int("ogp")) if pillow_ready() else None
        f = None
        if pr:
            try:
                f = PostCard(self.assets(ctx), pr).render()
            except Exception as e:
                print("og post card: %s" % e, file=sys.stderr)
        return self.png(f) if f else self.fallback("assets/og.png")

    @staticmethod
    def arg_int(name):
        from ..php import intval
        return intval(Route.arg_text(name))


class CardDiagnosticsRoute(CardRoute):
    """?ogdiag[&u=<username>][&p=<post id>]: admin-only plain-text report on whether cards can be drawn here."""
    key = "ogdiag"

    def serve(self, ctx) -> Response:
        m = ctx.users.me()
        if not m or not m["admin"]:
            return self.not_found()
        a = self.assets(ctx)
        out = ["Python %s" % sys.version.split()[0]]
        try:
            from PIL import Image, features
            out.append("Pillow loaded: yes (%s)" % Image.__version__)
            out.append("FreeType: " + ("yes" if features.check("freetype2") else "NO"))
            out.append("PNG: %s, JPEG: %s, WebP: %s" % tuple("yes" if features.check(f) else "no" for f in ("zlib", "jpg", "webp")))
        except ImportError:
            out.append("Pillow loaded: NO")
        for name in CardAssets.NEEDED + ("og.png",):
            out.append("assets/%s: %s" % (name, "ok" if (a.dir / name).is_file() else "MISSING"))
        og = Path(ctx.cfg.data_dir) / "og"
        try:
            og.mkdir(parents=True, exist_ok=True)
            probe = og / ".probe"
            probe.write_text("x")
            probe.unlink()
            out.append("DATA_DIR/og writable: yes")
        except OSError:
            out.append("DATA_DIR/og writable: NO")
        out.append("")
        try:
            u = self.arg_text("u")
            du = ctx.db.one("SELECT name,nick,bio,avatar,priv FROM users WHERE name=?", (u,)) if u and ctx.names.valid(u) else None
            if du:
                f = ProfileCard(a, du).render()
                out.append("profile card: " + ("made, %d bytes" % f.stat().st_size if f else "returned null (a font, a file or an image was missing)"))
            p = self.arg_text("p")
            if p:
                pr = ctx.access.public_post(p if p.isdigit() else 0)
                if not pr:
                    out.append("post: not public, so no card is made on purpose")
                else:
                    f = PostCard(a, pr).render()
                    out.append("post card: " + ("made, %d bytes" % f.stat().st_size if f else "returned null (a font, a file or an image was missing)"))
            if not du and not p:
                out.append("Add &u=<username> and/or &p=<post id> to try drawing a card.")
        except Exception as e:
            out.append("ERROR: %s: %s" % (type(e).__name__, e))
        return Response("\n".join(out) + "\n", mimetype="text/plain", headers={"Cache-Control": "no-store"})
