"""The Flask front door: CSRF and upload-size gates, then the route, action or page that answers."""
from flask import Flask, request

from .actions import Abort, Context, Reply, load_all
from .config import Config
from .database import Database
from .gate import MaintenanceGate
from .assets import AssetServer
from .errors import ErrorPages
from .php import empty as php_empty
from .routes import ShellRoute, load_routes


def create_app(cfg: Config = None, registry=None) -> Flask:
    cfg = cfg or Config.from_env()
    app = Flask(__name__)
    db = Database(cfg.db_path)
    registry = registry or load_all()
    gate = MaintenanceGate()
    routes = load_routes()
    assets = AssetServer(cfg)
    shell = ShellRoute()
    errors = ErrorPages()
    errors.install(app)

    @app.route("/", defaults={"path": ""}, methods=["GET", "POST", "HEAD", "OPTIONS", "PUT", "DELETE"])
    @app.route("/<path:path>", methods=["GET", "POST", "HEAD", "OPTIONS", "PUT", "DELETE"])
    def front(path):
        on_index = request.path in ("/", "/index.php")
        read = request.method in ("GET", "HEAD")
        have_db = cfg.db_path.exists()  # PHP still makes the database on first run
        if read and request.path.startswith("/assets/"):  # app.js, style.css (gzipped), icons, fonts
            served = assets.serve(request.path)
            if served is not None:
                return served
        route = routes.match(request.args) if on_index and read else None
        if route is not None and (have_db or not route.needs_db):  # ?manifest, ?page=, ?sw, ?img=, ?stk=, ?lpi=, ?og=, ?ogp=, ?ogdiag
            ctx = Context(cfg, db)
            try:
                return ctx.finish(route.serve(ctx))
            except Abort as stop:
                return ctx.finish(stop.reply.to_response())
        action = registry.get(request.args.get("a", "")) if on_index else None
        if action is None and have_db and php_empty(request.args.get("a")):  # no action asked for: the page itself
            ctx = Context(cfg, db)
            return ctx.finish(shell.serve(ctx))
        if action is None:  # every action is ported: an unknown ?a= is a 404 (PHP's last line), no database yet is a short wait
            return errors.not_found() if not php_empty(request.args.get("a")) else errors.starting()
        ctx = Context(cfg, db, action.name)
        try:
            if request.method == "POST":
                # same gates as PHP, in the same order: CSRF token, then upload size
                sess = ctx.session
                if not sess.exists or sess.get("c", "") != request.headers.get("X-CSRF", ""):
                    return Reply.error("Session expired. Reload the page.", 403).to_response()
                if request.content_length and request.content_length > cfg.post_max:
                    return Reply.error("That upload is bigger than the server allows. Try a smaller photo.", 413).to_response()
            held = gate.check(ctx, action)  # maintenance mode
            if held is not None:
                return ctx.finish(held.to_response())
            return ctx.finish(action.handle(ctx).to_response())
        except Abort as stop:  # need() and friends
            return ctx.finish(stop.reply.to_response())

    return app
