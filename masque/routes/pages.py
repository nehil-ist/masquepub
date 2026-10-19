"""Pages: ?manifest, ?page=privacy|terms, ?sw, and the HTML shell that answers everything else."""
import secrets

from flask import Response, request

from ..assets import AssetFiles
from ..pages import LegalPages, PrettyLinks, ServiceWorker, ShellPage
from .base import Route


class ManifestRoute(Route):
    key, needs_db = "manifest", False

    def serve(self, ctx) -> Response:
        data = (AssetFiles(ctx.cfg.root).dir / "manifest.json").read_bytes()
        return Response(data, headers={"Content-Type": "application/manifest+json", "Cache-Control": "public,max-age=3600"})


class LegalRoute(Route):
    key, needs_db = "page", False

    def matches(self, args) -> bool:
        return args.get("page") in LegalPages.NAMES

    def serve(self, ctx) -> Response:
        from ..mailer import Mailer
        files = AssetFiles(ctx.cfg.root)
        mail_on = Mailer(ctx.cfg, ctx.db, ctx.users.vault, ctx.limiter).enabled() if ctx.cfg.db_path.exists() else False
        return Response(LegalPages(ctx.cfg, files, mail_on).render(request.args["page"]), headers={
            "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public,max-age=600",
            "Content-Security-Policy": "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'",
            "X-Content-Type-Options": "nosniff"})


class ServiceWorkerRoute(Route):
    key, needs_db = "sw", False

    def serve(self, ctx) -> Response:
        return Response(ServiceWorker(AssetFiles(ctx.cfg.root)).script(),
                        headers={"Content-Type": "application/javascript", "Service-Worker-Allowed": "./", "Cache-Control": "no-cache"})


class ShellRoute:
    """The page itself. Not picked by a query key: the front door uses it for any request that is not an action, a file or a route."""

    def serve(self, ctx) -> Response:
        ctx.begin_session()  # PHP starts the session here too: a first-time visitor gets a cookie and a CSRF token
        base, u, p = PrettyLinks.resolve(request.path, request.args, request.method)
        page = ShellPage(ctx)
        nonce = page.new_nonce()
        https = request.is_secure or request.headers.get("X-Forwarded-Proto", "") == "https"
        head = {
            "Content-Type": "text/html; charset=UTF-8",
            "Expires": "Thu, 19 Nov 1981 08:52:00 GMT", "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache",
            "X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin",
        }
        if not ctx.cfg.csp_off:
            head["Content-Security-Policy"] = page.csp(nonce)
        return Response(page.render(base, u, p, nonce, https, request.host), headers=head)
