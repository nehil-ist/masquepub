"""Uploads: photos (metadata removed), chat attachments, stickers (PHP: clean_img, save_img, save_att, save_att_raw, stk_save, stkcheck, giparse)."""
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import struct
import time
from pathlib import Path

from .php import intval

_ATT_NAME = re.compile(r"^[a-f0-9]{24}\.(jpg|png|webp|gif|mp3|m4a|aac|ogg|opus|wav|flac)$")
IMG_NAME = re.compile(r"^[a-f0-9]{24}\.(jpg|png|webp|gif)$")


class Upload:
    """One uploaded file read into memory (PHP $_FILES entry)."""

    def __init__(self, storage):
        self.name = storage.filename or ""
        self.data = storage.read()
        self.size = len(self.data)

    @property
    def ext(self) -> str:
        return self.name.rsplit(".", 1)[-1].lower() if "." in self.name else ""


def image_kind(b: bytes):
    """'jpg', 'png', 'webp', 'gif' from the first bytes, or None (PHP getimagesize type)."""
    if b[:2] == b"\xff\xd8":
        return "jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def image_size(b: bytes):
    """(width, height) or None."""
    try:
        from io import BytesIO
        from PIL import Image
        with Image.open(BytesIO(b)) as im:
            return im.size
    except Exception:
        return None


class ImageScrubber:
    """Removes EXIF/GPS and other metadata so photos cannot leak where they were taken.
    clean() returns cleaned bytes, None when nothing needs removing (GIF), or False when the file is malformed."""

    @classmethod
    def clean(cls, b: bytes, kind: str):
        if not b:
            return False
        if kind == "jpg":
            return cls._jpeg(b)
        if kind == "png":
            return cls._png(b)
        if kind == "webp":
            return cls._webp(b)
        return None

    @staticmethod
    def _jpeg(b: bytes):
        n = len(b)
        if b[:2] != b"\xff\xd8":
            return False
        out = bytearray(b"\xff\xd8")
        i = 2
        while i + 2 <= n:
            if b[i] != 0xFF:
                return False
            m = b[i + 1]
            if m == 0xFF:
                i += 1
                continue
            if m == 0xDA:
                return bytes(out) + b[i:]
            if m == 0xD9:
                return bytes(out) + b"\xff\xd9"
            if 0xD0 <= m <= 0xD8 or m == 0x01:
                out += b[i:i + 2]
                i += 2
                continue
            if i + 4 > n:
                return False
            ln = struct.unpack(">H", b[i + 2:i + 4])[0]
            if ln < 2 or i + 2 + ln > n:
                return False
            seg = b[i:i + 2 + ln]
            keep = m == 0xE0 or m == 0xEE or (m == 0xE2 and seg[4:16] == b"ICC_PROFILE\0") or not (m == 0xFE or 0xE1 <= m <= 0xEF)
            if keep:
                out += seg
            i += 2 + ln
        return False

    @staticmethod
    def _png(b: bytes):
        n = len(b)
        if b[:8] != b"\x89PNG\r\n\x1a\n":
            return False
        out = bytearray(b[:8])
        i = 8
        while i + 12 <= n:
            ln = struct.unpack(">I", b[i:i + 4])[0]
            ty = b[i + 4:i + 8]
            e = i + 12 + ln
            if e > n:
                return False
            if ty not in (b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"):
                out += b[i:i + 12 + ln]
            i = e
            if ty == b"IEND":
                return bytes(out)
        return False

    @staticmethod
    def _webp(b: bytes):
        n = len(b)
        if b[:4] != b"RIFF" or b[8:12] != b"WEBP":
            return False
        out = bytearray(b[:12])
        i = 12
        while i + 8 <= n:
            ty = b[i:i + 4]
            ln = struct.unpack("<I", b[i + 4:i + 8])[0]
            if i + 8 + ln > n:
                return False
            c = bytearray(b[i:i + 8 + ln + (ln & 1)])
            if ty == b"VP8X" and ln >= 1:
                c[8] = c[8] & ~0x0C & 0xFF
            if ty not in (b"EXIF", b"XMP "):
                out += c
            i += len(c)
        out[4:8] = struct.pack("<I", len(out) - 8)
        return bytes(out)


class GameInvite:
    """A chat message that is ONLY ':gi:<base64url JSON>:' is drawn as an invite card. JSON = {n: game name, u: join link, o: note, x: minutes open}."""
    _SHAPE = re.compile(r"^:gi:([A-Za-z0-9_-]{8,470}):$")
    _BADCHARS = re.compile(r'[\x00-\x20\x7f-\xff"<>\\^`{|}]')
    _HTTPS = re.compile(r"^https://[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+(:\d{1,5})?([/?#]|$)", re.I)
    _STEAM = re.compile(r"^steam://[A-Za-z0-9/_.:=&?%+-]{1,200}$")

    @staticmethod
    def is_invite(text) -> bool:
        return str(text).startswith(":gi:")

    @classmethod
    def parse(cls, text):
        m = cls._SHAPE.match(str(text))
        if not m:
            return None
        b = m.group(1).replace("-", "+").replace("_", "/")
        try:
            j = base64.b64decode(b + "=" * ((4 - len(b) % 4) % 4), validate=True)
            d = json.loads(j)
        except Exception:
            return None
        if not isinstance(d, dict):
            return None
        n, u, o, x = d.get("n"), d.get("u"), d.get("o", ""), d.get("x")
        if not isinstance(n, str) or not isinstance(u, str) or not isinstance(o, str):
            return None
        n = n.strip(" \t\n\r\0\x0b")
        if n == "" or len(n) > 40 or len(o) > 60:
            return None
        if isinstance(x, bool) or x not in (15, 60, 1440):
            return None
        if len(u.encode("utf-8")) > 220 or cls._BADCHARS.search(u.encode("utf-8").decode("latin-1")):
            return None
        if re.match(r"^https://[\d.]+(:\d+)?([/?#]|$)", u):
            return None
        if not cls._HTTPS.match(u) and not cls._STEAM.match(u):
            return None
        return {"n": n, "u": u, "o": o, "x": x}


class Uploads:
    """Saving files under DATA_DIR/up (photos, chat attachments) and DATA_DIR/stk (stickers)."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.root = Path(ctx.cfg.data_dir)

    # -- helpers --
    @property
    def up_dir(self) -> Path:
        d = self.root / "up"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def min_free(self) -> int:
        v = os.environ.get("MIN_FREE_MB")
        if v is None or v == "":
            return 500 * 1048576
        return max(0, intval(v)) * 1048576

    def _space_left(self, size: int) -> bool:
        mf = self.min_free()
        if mf <= 0:
            return True
        try:
            return shutil.disk_usage(self.root).free - size >= mf
        except OSError:
            return True

    def remove(self, files):
        """PHP rmfiles(): delete uploaded files by name (only names this site would have made)."""
        for f in files:
            if f and _ATT_NAME.match(f):
                try:
                    (self.up_dir / f).unlink()
                except OSError:
                    pass

    # -- photos --
    def save_img(self, storage) -> str:
        """One photo: type checked, metadata removed. '' when nothing was sent; stops the request with an error when it is not usable."""
        if storage is None:
            return ""
        up = Upload(storage) if not isinstance(storage, Upload) else storage
        if up.size > 4000000:
            self.ctx.deny("Image must be under 4 MB.", 400)
        kind = image_kind(up.data)
        if not kind:
            self.ctx.deny("Use a JPG, PNG, WebP or GIF image.", 400)
        name = "%s.%s" % (secrets.token_hex(12), kind)
        cleaned = ImageScrubber.clean(up.data, kind)
        if cleaned is False:
            self.ctx.deny("Could not read that image. Try another one.", 400)
        (self.up_dir / name).write_bytes(up.data if cleaned is None else cleaned)
        return name

    # -- chat attachments: audio recognised by its first bytes (never by its name alone), else an image --
    def save_attachment(self, storage, m) -> str:
        if storage is None:
            return ""
        up = Upload(storage)
        ctx = self.ctx
        is_admin = ctx.users.is_admin(m)
        if self.min_free() > 0 and not is_admin and not self._space_left(up.size):
            ctx.deny("Attachments are paused because the server is almost out of space. Text messages still work.", 503)
        if not is_admin:
            ctx.limits.lim("att:m:%d" % m["id"], 10, 60, m, 4, 60)
            ctx.limits.lim("att:h:%d" % m["id"], 60, 3600, m, 20, 3600)
            used = int(ctx.db.value("SELECT COALESCE(SUM(sz),0) FROM attlog WHERE uid=? AND ts>?", (m["id"], int(time.time()) - 86400), 0))
            if used + up.size > (100 if ctx.limits.is_new(m) else 300) * 1048576:
                ctx.deny("You have reached the daily limit for attachments. Try again later.", 429)
        name = self.save_attachment_raw(up)
        if name:
            if secrets.randbelow(50) == 0:
                ctx.db.execute("DELETE FROM attlog WHERE ts<?", (int(time.time()) - 172800,))
            try:
                size = (self.up_dir / name).stat().st_size
            except OSError:
                size = 0
            ctx.db.execute("INSERT INTO attlog(uid,ts,sz) VALUES(?,?,?)", (m["id"], int(time.time()), size))
        return name

    def save_attachment_raw(self, up) -> str:
        if not isinstance(up, Upload):
            if up is None:
                return ""
            up = Upload(up)
        h = up.data[:16]
        e = up.ext
        kind = None
        b1 = h[1] if len(h) > 1 else 0
        sync = len(h) > 1 and h[0] == 0xFF and (b1 & 0xE0) == 0xE0
        if h[:3] == b"ID3":
            kind = "mp3"
        elif sync and (b1 & 0xF6) == 0xF0:
            kind = "aac"
        elif sync and (b1 & 0x06) != 0:
            kind = "mp3"
        elif h[:4] == b"OggS":
            kind = "opus" if e == "opus" else "ogg"
        elif h[:4] == b"fLaC":
            kind = "flac"
        elif h[:4] == b"RIFF" and h[8:12] == b"WAVE":
            kind = "wav"
        elif h[4:8] == b"ftyp" and e in ("m4a", "m4b", "mp4", "aac"):
            kind = "m4a"
        if kind is None:
            return self.save_img(up)
        if up.size > 25000000:
            self.ctx.deny("Audio must be under 25 MB.", 400)
        name = "%s.%s" % (secrets.token_hex(12), kind)
        try:
            (self.up_dir / name).write_bytes(up.data)
        except OSError:
            self.ctx.deny("Could not save that file.", 500)
        return name

    # -- stickers --
    @staticmethod
    def sticker_kind(text) -> int:
        """1 = built-in ':stk:name:', 2 = image sticker ':sti:<16 hex>:', 0 = not a sticker."""
        t = str(text)
        if re.match(r"^:stk:[a-z0-9]{1,12}:$", t):
            return 1
        return 2 if re.match(r"^:sti:[a-f0-9]{16}:$", t) else 0

    def check_sticker(self, m, text: str):
        """send / gsend: stickers have their own spam limit (10 per 30 s), and an image sticker must still exist."""
        k = self.sticker_kind(text)
        if not k:
            return
        self.ctx.limits.throttle("stk:%d" % m["id"], 10, 30)
        if k == 2 and not self.ctx.db.value("SELECT 1 FROM stkimg WHERE id=?", (text[5:21],)):
            self.ctx.deny("That sticker is no longer available.", 404)

    def check_game_invite(self, m, text: str):
        if not GameInvite.is_invite(text):
            return
        if not GameInvite.parse(text):
            self.ctx.deny("That game invite is not valid. Check the game name and the link.", 400)
        self.ctx.limits.throttle("gi:%d" % m["id"], 12, 600)

    def save_sticker(self, storage) -> str:
        ctx = self.ctx
        if storage is None:
            ctx.deny("No image received.", 400)
        up = Upload(storage)
        if up.size < 1 or up.size > 153600:
            ctx.deny("That sticker is too big. Pick a smaller picture.", 400)
        if self.min_free() > 0 and not ctx.users.admnow() and not self._space_left(up.size):
            ctx.deny("Stickers are paused because the server is almost out of space.", 503)
        kind = image_kind(up.data)
        if kind not in ("jpg", "png", "webp"):
            ctx.deny("Use a JPG, PNG or WebP picture.", 400)
        size = image_size(up.data)
        if not size or size[0] < 1 or size[1] < 1 or size[0] > 512 or size[1] > 512:
            ctx.deny("Stickers can be at most 512 px wide or tall.", 400)
        b = ImageScrubber.clean(up.data, kind)
        if b is False or b is None:
            ctx.deny("Could not read that image. Try another one.", 400)
        animated = kind == "webp" and b[12:16] == b"VP8X" and (b[20] & 0x02)
        if animated:
            frames, o = 0, 12
            while o + 8 <= len(b):
                ln = struct.unpack("<I", b[o + 4:o + 8])[0]
                if b[o:o + 4] == b"ANMF":
                    frames += 1
                o += 8 + ln + (ln & 1)
            if frames < 2 or frames > 30:
                ctx.deny("Animated stickers can have 2 to 30 frames.", 400)
        if len(b) > (153600 if animated else 81920):
            ctx.deny("That sticker is too big. Pick a smaller picture.", 400)
        sha = hashlib.sha256(b).hexdigest()
        found = ctx.db.value("SELECT id FROM stkimg WHERE sha=?", (sha,))
        if found is not None:
            ctx.db.execute("UPDATE stkimg SET ts=? WHERE id=?", (int(time.time()), found))
            return str(found)
        sid = secrets.token_hex(8)
        d = self.root / "stk"
        d.mkdir(parents=True, exist_ok=True)
        try:
            (d / ("%s.%s" % (sid, kind))).write_bytes(b)
        except OSError:
            ctx.deny("Could not save that sticker.", 500)
        try:
            ctx.db.execute("INSERT INTO stkimg(id,sha,ext,sz,ts) VALUES(?,?,?,?,?)", (sid, sha, kind, len(b), int(time.time())))
        except Exception:
            try:
                (d / ("%s.%s" % (sid, kind))).unlink()
            except OSError:
                pass
            sid = ctx.db.value("SELECT id FROM stkimg WHERE sha=?", (sha,))
            if sid is None:
                ctx.deny("Could not save that sticker.", 500)
        return str(sid)
