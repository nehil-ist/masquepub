"""Files people see: uploaded photos and audio (?img=), image stickers (?stk=), link-preview thumbnails (?lpi=)."""
import re
from pathlib import Path

from flask import Response, request

from .base import FileBody, Route

_UP_RE = re.compile(r"^[a-f0-9]{24}\.(jpg|png|webp|gif|mp3|m4a|aac|ogg|opus|wav|flac)$")
_AUDIO = {"mp3": "audio/mpeg", "m4a": "audio/mp4", "aac": "audio/aac", "ogg": "audio/ogg", "opus": "audio/ogg", "wav": "audio/wav", "flac": "audio/flac"}
_HEX16 = re.compile(r"^[a-f0-9]{16}$")
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


class UploadAccess:
    """Who may fetch an uploaded file: a chat file only its chat's people, a group file or group picture only its members,
    a not-yet-posted photo only its uploader, a post photo only people who may see that post."""

    def __init__(self, ctx, name: str, viewer: int):
        self.ctx, self.db, self.name, self.viewer = ctx, ctx.db, name, viewer
        self.owned = False  # the file belongs to someone, so browsers must not share it (Cache-Control: private)

    def allowed(self) -> bool:
        db, n, v = self.db, self.name, self.viewer
        mm = db.one("SELECT a,b FROM messages WHERE img=?", (n,))
        if mm:
            self.owned = True
            if v not in (int(mm["a"]), int(mm["b"])):
                return False
        gg = db.one("SELECT gid FROM gmessages WHERE img=?", (n,))
        if gg:
            self.owned = True
            if not (v and self._member(int(gg["gid"]))):
                return False
        ga = db.one("SELECT id FROM gchats WHERE avatar=?", (n,))
        if ga:
            self.owned = True
            if not (v and self._member(int(ga["id"]))):
                return False
        pe = db.one("SELECT uid FROM pend WHERE img=?", (n,))
        if pe:
            self.owned = True
            if v != int(pe["uid"] or 0):
                return False
        pp = db.one("SELECT p.uid,p.vis,p.mid,p.anon,u.priv FROM posts p JOIN users u ON u.id=p.uid "
                    "WHERE p.img=? OR p.id IN (SELECT pid FROM postimgs WHERE img=?)", (n, n))
        if pp:
            self.owned = True
            if (pp["priv"] and not int(pp["mid"]) and not int(pp["anon"])) or int(pp["vis"]) > 0:
                if not v or (int(pp["uid"]) != v and (int(pp["vis"]) == 2 or not self.ctx.rel.friends(v, int(pp["uid"])))):
                    return False
        return True

    def _member(self, gid: int) -> bool:
        return bool(self.db.value("SELECT 1 FROM gmembers WHERE gid=? AND uid=?", (gid, self.viewer)))


class UploadRoute(Route):
    """?img=<24 hex>.<ext>"""
    key = "img"

    def serve(self, ctx) -> Response:
        n = self.arg_text("img")
        m = _UP_RE.match(n)
        path = Path(ctx.cfg.data_dir) / "up" / n
        if not m or not path.is_file():
            return self.not_found()
        acc = UploadAccess(ctx, n, self.viewer(ctx))
        if not acc.allowed():
            return self.not_found()
        ext = m.group(1)
        if ext in _AUDIO:
            return self._audio(path, _AUDIO[ext])
        return FileBody.response(path, "image/" + ("jpeg" if ext == "jpg" else ext), {
            "Cache-Control": ("private" if acc.owned else "public") + ",max-age=31536000,immutable",
            "X-Content-Type-Options": "nosniff"})

    @staticmethod
    def _audio(path: Path, mime: str) -> Response:
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        head = {"Accept-Ranges": "bytes", "Cache-Control": "private,max-age=31536000,immutable",
                "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"}
        rg = _RANGE.match(request.headers.get("Range", ""))
        if rg and (rg.group(1) != "" or rg.group(2) != ""):
            if rg.group(1) == "":
                start = max(0, size - int(rg.group(2)))
            else:
                start = int(rg.group(1))
                if rg.group(2) != "":
                    end = min(end, int(rg.group(2)))
            if start > end or start >= size:
                return Response(status=416, headers={"Content-Range": "bytes */%d" % size})
            status = 206
            head["Content-Range"] = "bytes %d-%d/%d" % (start, end, size)
        return FileBody.response(path, mime, head, status, start, end - start + 1)


class StickerRoute(Route):
    """?stk=<16 hex>: image stickers, for signed-in people only."""
    key = "stk"

    def serve(self, ctx) -> Response:
        n = self.arg_text("stk")
        ext = ctx.db.value("SELECT ext FROM stkimg WHERE id=?", (n,)) if (self.viewer(ctx) and _HEX16.match(n)) else None
        path = Path(ctx.cfg.data_dir) / "stk" / ("%s.%s" % (n, ext))
        if ext not in ("jpg", "png", "webp") or not path.is_file():
            return self.not_found(True)
        return FileBody.response(path, "image/" + ("jpeg" if ext == "jpg" else ext), {
            "Cache-Control": "private,max-age=31536000,immutable", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'"})


class LinkThumbRoute(Route):
    """?lpi=<16 hex>: the small picture of a chat link preview, for signed-in people only."""
    key = "lpi"

    def serve(self, ctx) -> Response:
        n = self.arg_text("lpi")
        path = Path(ctx.cfg.data_dir) / "lp" / (n + ".jpg")
        if not self.viewer(ctx) or not _HEX16.match(n) or not path.is_file():
            return self.not_found(True)
        return FileBody.response(path, "image/jpeg", {
            "Cache-Control": "private,max-age=2592000,immutable", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'"})
