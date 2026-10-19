"""Building blocks every migrated action uses."""
import json
import secrets
from abc import ABC, abstractmethod
from functools import cached_property

from flask import Response, request

from ..config import Config
from ..database import Database
from ..php import empty as php_empty, intval
from ..php_session import COOKIE, PhpSession


class Reply:
    """A JSON answer. Mirrors PHP's out(): no-store, compact JSON."""

    def __init__(self, data, status: int = 200):
        self.data = data
        self.status = status

    def to_response(self) -> Response:
        body = json.dumps(self.data, separators=(",", ":"), ensure_ascii=False)
        return Response(body, status=self.status, headers={"Content-Type": "application/json", "Cache-Control": "no-store"})

    @classmethod
    def error(cls, msg: str, status: int = 400, **extra) -> "Reply":
        return cls({"e": msg, **extra}, status)


class Abort(Exception):
    """Stop the action and answer with this Reply (PHP's out() inside need()/limits)."""

    def __init__(self, reply: "Reply"):
        super().__init__(reply.data)
        self.reply = reply


class Context:
    """Everything an action may need about the current request."""

    def __init__(self, cfg: Config, db: Database, action: str = ""):
        self.cfg = cfg
        self.db = db
        self.action = action  # the ?a= name, like PHP's $_GET['a']
        self._session = None
        self._users = None
        self._deferred = []  # jobs to run after the answer has been sent (push alerts, clean-ups)

    @property
    def users(self):
        """The signed-in-user layer (me(), need(), admin check) for this request."""
        if self._users is None:
            from ..users import Users
            self._users = Users(self)
        return self._users

    @property
    def method(self) -> str:
        return request.method

    @property
    def session(self) -> PhpSession:
        if self._session is None:
            self._session = PhpSession(request.cookies.get(COOKIE, ""), self.cfg.session_dir)
        return self._session

    def begin_session(self) -> PhpSession:
        """PHP's session_start() for a visitor who may be new: makes the session and its CSRF token when missing."""
        s = self.session
        s.start()
        if s.get("c") is None:
            s.set("c", secrets.token_hex(16))
        return s

    def finish(self, response: Response) -> Response:
        """After the action: save the session if it changed, and hand the browser its cookie if the id is new."""
        if self._deferred:
            jobs, self._deferred = self._deferred, []
            response.call_on_close(lambda: [job() for job in jobs])
        s = self._session
        if s is not None:
            s.commit()
            if s.fresh and s.sid:
                https = request.is_secure or request.headers.get("X-Forwarded-Proto", "") == "https"
                response.set_cookie(COOKIE, s.sid, max_age=2592000, path="/", httponly=True, samesite="Lax", secure=https)
                s.fresh = False
        return response

    # -- helpers the account actions share (each is created once per request) --
    @cached_property
    def ip(self):
        from ..security import ClientIp
        return ClientIp(self.cfg, request.headers, request.remote_addr)

    @cached_property
    def limiter(self):
        from ..security import RateLimiter
        return RateLimiter(self.db, self.users)

    @cached_property
    def hasher(self):
        from ..security import PasswordHasher
        return PasswordHasher()

    @cached_property
    def codes(self):
        from ..security import RecoveryCodes
        return RecoveryCodes(self.hasher)

    @cached_property
    def names(self):
        from ..names import NameRules
        return NameRules(self.db, self.cfg.admin_users)

    @cached_property
    def mailer(self):
        from ..mailer import Mailer
        return Mailer(self.cfg, self.db, self.users.vault, self.limiter)

    @cached_property
    def tokens(self):
        from ..mailer import MailTokens
        return MailTokens(self.db)

    @cached_property
    def accounts(self):
        from ..accounts import Accounts
        return Accounts(self)

    # -- more services (each is created once per request) --
    @cached_property
    def rel(self):
        from ..access import Relations
        return Relations(self.db)

    @cached_property
    def access(self):
        from ..access import PostAccess
        return PostAccess(self.db, self.rel)

    @cached_property
    def limits(self):
        from ..limits import Limits
        return Limits(self)

    @cached_property
    def words(self):
        from ..moderation import WordFilter
        return WordFilter(self.db)

    @cached_property
    def adminlog(self):
        from ..moderation import AdminLog
        return AdminLog(self.db)

    @cached_property
    def notes(self):
        from ..notify import Notifier
        return Notifier(self)

    @cached_property
    def media(self):
        from ..media import Uploads
        return Uploads(self)

    @cached_property
    def tags(self):
        from ..mentions import PostTags
        return PostTags(self)

    @cached_property
    def mentions(self):
        from ..mentions import Mentions
        return Mentions(self)

    @cached_property
    def mutelist(self):
        from ..mutes import MuteList
        return MuteList(self.db)

    @cached_property
    def streaks(self):
        from ..streaks import Streaks
        return Streaks(self.db)

    @cached_property
    def unlocks(self):
        from ..unlockables import Unlocks
        return Unlocks(self)

    @cached_property
    def dms(self):
        from ..chatstate import DirectChats
        return DirectChats(self.db)

    @cached_property
    def unread(self):
        from ..counters import UnreadCounts
        return UnreadCounts(self)

    def defer(self, job):
        """Run `job` after the answer is sent (PHP register_shutdown_function)."""
        self._deferred.append(job)

    def deny(self, msg: str, status: int = 400, **extra):
        """PHP out(['e' => ...], status): stop the request with an error answer."""
        raise Abort(Reply.error(msg, status, **extra))

    def done(self, data, status: int = 200):
        """PHP out($data): stop the request with this answer from anywhere in the code."""
        raise Abort(Reply(data, status))

    def flag(self, name: str) -> bool:
        """!empty($_POST[name])"""
        return not php_empty(request.form.get(name))

    def qflag(self, name: str) -> bool:
        """!empty($_GET[name])"""
        return not php_empty(request.args.get(name))

    def int_form(self, name: str, default: int = 0) -> int:
        return intval(request.form.get(name), default)

    def int_arg(self, name: str, default: int = 0) -> int:
        return intval(request.args.get(name), default)

    def has_form(self, name: str) -> bool:
        return name in request.form

    def file(self, name: str):
        """The uploaded file called `name` (PHP $_FILES[name]) or None when nothing was sent."""
        f = request.files.get(name)
        return f if f is not None and (f.filename or "") != "" else None

    @property
    def now(self) -> int:
        import time
        return int(time.time())

    def arg(self, name: str, default: str = "") -> str:
        """Query-string value (PHP $_GET)."""
        return request.args.get(name, default)

    def form(self, name: str, default: str = "") -> str:
        """Form value (PHP $_POST)."""
        return request.form.get(name, default)


class Action(ABC):
    """One endpoint. Subclasses set `name` and implement handle()."""

    name: str = ""
    maintenance_exempt = False  # True = still answers while the site is in maintenance mode

    def __init__(self, ctx_factory=None):
        pass

    @abstractmethod
    def handle(self, ctx: Context) -> Reply: ...


class ActionRegistry:
    def __init__(self):
        self._actions = {}

    def register(self, cls):
        inst = cls()
        if not inst.name:
            raise ValueError("%s has no name" % cls.__name__)
        if inst.name in self._actions:
            raise ValueError("action %r registered twice" % inst.name)
        self._actions[inst.name] = inst
        return cls

    def get(self, name: str):
        return self._actions.get(name)

    def names(self):
        return sorted(self._actions)


registry = ActionRegistry()
