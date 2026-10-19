"""Routes: answers picked by a query-string key (?img=, ?stk=, ?og=, ...) instead of ?a=. They run before the actions, in a fixed order, like the top of index.php."""
from abc import ABC, abstractmethod
from pathlib import Path

from flask import Response


class FileBody:
    """Streams a file (or a byte range of it) in 64 KB pieces."""

    @staticmethod
    def chunks(path: Path, start: int = 0, length: int = None):
        left = (path.stat().st_size - start) if length is None else length
        with open(path, "rb") as fh:
            fh.seek(start)
            while left > 0:
                data = fh.read(min(65536, left))
                if not data:
                    break
                left -= len(data)
                yield data

    @classmethod
    def response(cls, path: Path, mime: str, headers: dict, status: int = 200, start: int = 0, length: int = None) -> Response:
        size = path.stat().st_size
        length = size - start if length is None else length
        h = dict(headers)
        h["Content-Length"] = str(length)
        return Response(cls.chunks(path, start, length), status=status, mimetype=mime, headers=h)


class Route(ABC):
    """One query key. `key` is the ?name that selects it; serve() answers with a Flask Response."""
    key: str = ""
    needs_db = True  # False = also answers before the database exists

    def matches(self, args) -> bool:
        return self.key in args

    @abstractmethod
    def serve(self, ctx) -> Response: ...

    @staticmethod
    def not_found(no_store: bool = False) -> Response:
        return Response(status=404, headers={"Cache-Control": "no-store"} if no_store else {})

    @staticmethod
    def viewer(ctx):
        """$_SESSION['u'] as an int (0 when signed out). Never starts a session."""
        try:
            return int(ctx.session.get("u") or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def arg_text(name: str) -> str:
        from flask import request
        v = request.args.get(name, "")
        return v if isinstance(v, str) else ""


class RouteTable:
    def __init__(self):
        self._routes = []

    def add(self, route: Route):
        self._routes.append(route)
        return route

    def match(self, args):
        """The first route (in the order they were added) whose key is in the query string."""
        return next((r for r in self._routes if r.matches(args)), None)

    def keys(self):
        return [r.key for r in self._routes]
