"""The files in assets/: which build of app.js and style.css to serve, their version numbers, gzip copies, and plain static files
(PHP: mqa(), the gzip block and `return false` at the top of index.php)."""
import gzip
import hashlib
import mimetypes
import re
from pathlib import Path

from flask import Response, request, send_file

_GZIP_RE = re.compile(r"^/assets/[\w.-]+\.(js|css)$")


class AssetFiles:
    """assets/app.min.js and assets/style.min.css are used when they exist and are not older than the source file
    (2 min slack, since a git checkout or Docker copy sets times loosely); otherwise the plain file."""

    def __init__(self, root: Path):
        self.dir = Path(root) / "assets"

    def mtime(self, name: str) -> int:
        try:
            return int((self.dir / name).stat().st_mtime)
        except OSError:
            return 0

    def pick(self, name: str) -> str:
        m = re.sub(r"\.(js|css)$", r".min.\1", name)
        return m if (self.dir / m).is_file() and self.mtime(m) >= self.mtime(name) - 120 else name

    def version(self, name: str) -> int:
        """mtime of the file pick() chooses: the ?v= number on the page's links."""
        return self.mtime(self.pick(name))

    def resolve(self, rel: str):
        """A real file inside assets/ (never outside it), or None."""
        try:
            p = (self.dir / rel).resolve()
            p.relative_to(self.dir.resolve())
        except (ValueError, OSError):
            return None
        return p if p.is_file() else None


class GzipAssets:
    """Big text assets go out gzipped. The compressed copy is made once per file version and kept in DATA_DIR/gz,
    so there is no per-request cost. The pages link these as app.js?v=<mtime>, so a versioned URL is cached for good."""

    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir) / "gz"

    def serve(self, url_path: str, file: Path):
        st = file.stat()
        t, sz = int(st.st_mtime), st.st_size
        cached = self.dir / (hashlib.md5(("%s|%d|%d" % (url_path, t, sz)).encode()).hexdigest() + ".gz")
        if not cached.is_file():
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = cached.with_name(cached.name + ".tmp")
            tmp.write_bytes(gzip.compress(file.read_bytes(), 9, mtime=0))
            tmp.replace(cached)
        etag = '"%s-gz"' % hashlib.md5(("%d|%d" % (t, sz)).encode()).hexdigest()
        head = {
            "Content-Type": ("application/javascript" if url_path.endswith(".js") else "text/css") + "; charset=utf-8",
            "Content-Encoding": "gzip", "Vary": "Accept-Encoding", "ETag": etag,
            "Cache-Control": "public, max-age=31536000, immutable" if "v" in request.args else "no-cache",
        }
        if request.headers.get("If-None-Match", "") == etag:
            return Response(status=304, headers=head)
        head["Content-Length"] = str(cached.stat().st_size)
        return Response(cached.read_bytes(), headers=head)


class AssetServer:
    """Answers /assets/<file>: gzip for .js and .css when the browser accepts it, the plain file otherwise. None = no such file."""

    def __init__(self, cfg, files: AssetFiles = None):
        self.files = files or AssetFiles(cfg.root)
        self.gz = GzipAssets(cfg.data_dir)

    def serve(self, url_path: str):
        f = self.files.resolve(url_path[len("/assets/"):])
        if f is None:
            return None
        if _GZIP_RE.match(url_path) and "gzip" in request.headers.get("Accept-Encoding", "").lower():
            return self.gz.serve(url_path, f)
        return send_file(f, mimetype=mimetypes.guess_type(f.name)[0] or "application/octet-stream", conditional=True, max_age=None)
