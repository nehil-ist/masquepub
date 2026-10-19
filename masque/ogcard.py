"""Link-preview cards, 1200x630 PNG (PHP: assets/ogcard.php, needs GD+FreeType; now Pillow).
Drawn at 2x and scaled down so the edges stay smooth. Cards are cached in DATA_DIR/og."""
import hashlib
import json
import os
import random
import re
import time
from pathlib import Path

_EMOJI = re.compile("[\U0001F000-\U0001FFFF\u2190-\u2BFF\uFE00-\uFE0F\u200D\uE000-\uF8FF]")
_DRAWABLE = re.compile("[\u0020-\u024F\u0370-\u052F\u2010-\u206F]*")
_NOT_DRAWABLE = re.compile("[^\u0020-\u024F\u0370-\u052F\u2010-\u206F]")
_LATIN = re.compile("[\u0020-\u017F]+")
_UP_NAME = re.compile(r"^[a-f0-9]{24}\.(jpg|png|webp|gif)$")
S = 2  # drawing scale


def pillow_ready() -> bool:
    """Pillow with FreeType (what PHP called 'GD with FreeType')."""
    try:
        from PIL import features
        return bool(features.check("freetype2")) and bool(features.check("zlib"))
    except Exception:
        return False


class CardKeys:
    """The short `v=` value on card addresses (?og=, ?ogp=): changes whenever what the card shows changes, so chat apps fetch a fresh picture."""

    @staticmethod
    def _v(parts) -> str:
        return hashlib.sha1(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()[:8]

    @classmethod
    def profile(cls, u) -> str:
        return cls._v([u["nick"], u["bio"], u["avatar"], u["priv"], "og2"])

    @classmethod
    def post(cls, p) -> str:
        return cls._v([p["cap"], p["ln"], p["cn"], p["img"], p["sens"], p["mid"], p["anon"], "og2"])


class CardAssets:
    """The fonts, stamp and default avatar the cards need."""
    NEEDED = ("fonts/PirataOne-Regular.ttf", "fonts/DejaVuSansMono-Bold.ttf", "og-avatar.png", "og-stamp.png")

    def __init__(self, root: Path, data_dir: Path):
        self.dir = Path(root) / "assets"
        self.data = Path(data_dir)
        self.title_font = str(self.dir / "fonts/PirataOne-Regular.ttf")
        self.mono_font = str(self.dir / "fonts/DejaVuSansMono-Bold.ttf")

    def complete(self) -> bool:
        return all((self.dir / n).is_file() for n in self.NEEDED)

    def upload(self, name):
        """A photo from DATA_DIR/up as an RGB image on white, or None."""
        from PIL import Image
        p = self.data / "up" / str(name)
        try:
            if not _UP_NAME.match(str(name)) or not p.is_file() or p.stat().st_size >= 20000000:
                return None
            with Image.open(p) as im:
                if im.size[0] * im.size[1] > 60000000:
                    return None
                return self._flatten(im.convert("RGBA"))
        except Exception:
            return None

    def asset(self, name):
        from PIL import Image
        try:
            with Image.open(self.dir / name) as im:
                return im.convert("RGBA")
        except Exception:
            return None

    @staticmethod
    def _flatten(rgba):
        from PIL import Image
        bg = Image.new("RGB", rgba.size, (255, 255, 255))  # transparent photos sit on white
        bg.paste(rgba, (0, 0), rgba)
        return bg


class Text:
    """Text clean-up: drop emoji and symbols the bundled fonts cannot draw."""

    @staticmethod
    def strip(s) -> str:
        return re.sub(r"\s+", " ", _EMOJI.sub("", str(s or ""))).strip()

    @staticmethod
    def drawable(s) -> bool:
        return _DRAWABLE.fullmatch(str(s)) is not None

    @classmethod
    def clean(cls, s) -> str:
        s = cls.strip(s)
        if not cls.drawable(s):
            s = _NOT_DRAWABLE.sub("", s).strip()
        return s

    @staticmethod
    def latin(s) -> bool:
        return _LATIN.fullmatch(str(s)) is not None


class Canvas:
    """The 2x drawing surface with the helpers both cards share (frame, dots, header, button, round photos)."""
    W, H = 1200, 630
    INK, OL, BG, MUTE = (22, 53, 42), (27, 36, 32), (232, 237, 228), (93, 112, 100)
    SIG, SH, DOT, WHITE = (61, 68, 71), (185, 196, 182), (196, 206, 192), (255, 255, 255)

    def __init__(self, assets: CardAssets):
        from PIL import Image, ImageDraw
        self.assets = assets
        self.im = Image.new("RGB", (self.W * S, self.H * S))
        self.d = ImageDraw.Draw(self.im)
        self._fonts = {}

    # -- primitives (coordinates are in 1x pixels, like the PHP code) --
    def rect(self, x1, y1, x2, y2, col):
        self.d.rectangle([int(x1 * S), int(y1 * S), int(x2 * S - 1), int(y2 * S - 1)], fill=col)

    def font(self, path, px):
        from PIL import ImageFont
        key = (path, int(px * S))
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(path, int(px * S))
        return self._fonts[key]

    def text(self, px, x, y, col, path, s):
        self.d.text((round(x * S), round(y * S)), s, font=self.font(path, px), fill=col, anchor="ls")

    def width(self, px, path, s) -> float:
        return self.font(path, px).getlength(s) / S

    def fit(self, px, path, s, maxw):
        while self.width(px, path, s) > maxw and len(s) > 1:
            s = s[:-1]
        return s

    def wrap(self, px, path, words, maxw, maxlines):
        """Greedy word wrap; the last allowed line ends in '...' when the text is longer."""
        lines, cur = [], ""
        for w in words:
            attempt = (cur + " " + w).strip()
            if self.width(px, path, attempt) <= maxw:
                cur = attempt
            else:
                if cur != "":
                    lines.append(cur)
                cur = w
        if cur != "":
            lines.append(cur)
        if len(lines) > maxlines:
            lines = lines[:maxlines]
            last = lines[-1]
            while self.width(px, path, last + "...") > maxw and len(last) > 1:
                last = last[:-1]
            lines[-1] = last.rstrip() + "..."
        return lines

    # -- shared pieces --
    def paper(self, tag: str):
        a = self.assets
        self.rect(0, 0, 1200, 630, self.BG)
        for y in range(10, 630, 20):
            for x in range(10, 1200, 20):
                self.rect(x - .5, y - .5, x + .5, y + .5, self.DOT)
        self.rect(34, 34, 1166, 40, self.OL); self.rect(34, 590, 1166, 596, self.OL)
        self.rect(34, 34, 40, 596, self.OL); self.rect(1160, 34, 1166, 596, self.OL)
        self.rect(40, 40, 1160, 90, self.WHITE); self.rect(34, 90, 1166, 96, self.OL)
        self.text(40, 60, 76, self.INK, a.title_font, "Masque")
        self.text(40, 60 + self.width(40, a.title_font, "Masque"), 76, self.SIG, a.title_font, ".")
        self.text(17, 1136 - self.width(17, a.mono_font, tag), 72, self.MUTE, a.mono_font, tag)

    def button(self, x, y, w=300, h=62):
        a = self.assets
        self.rect(x + 6, y + 6, x + w + 6, y + h + 6, self.OL); self.rect(x, y, x + w, y + h, self.OL)
        self.rect(x + 4, y + 4, x + w - 4, y + h - 4, self.SIG)
        lab = "OPEN ON MASQUE"
        self.text(22, x + w / 2 - self.width(22, a.mono_font, lab) / 2, y + 39, self.WHITE, a.mono_font, lab)

    def disc(self, src, x, y, d, outline_extra=8, outline_shift=0):
        """A round photo at (x,y), diameter d, with a dark ring. outline_shift draws a hard shadow first."""
        from PIL import Image, ImageDraw
        if outline_shift:
            self._ring(x + outline_shift, y + outline_shift, d, outline_extra)
        self._ring(x, y, d, outline_extra)
        ds = int(d * S)
        w, h = src.size
        m = min(w, h)
        if m < 1:
            return
        left, top = (w - m) // 2, (h - m) // 2
        tile = src.crop((left, top, left + m, top + m)).resize((ds, ds), Image.LANCZOS)
        mask = Image.new("L", (ds, ds), 0)
        md = ImageDraw.Draw(mask)
        r = ds / 2
        for yy in range(ds):  # same scan-line circle the PHP code clipped with
            dx = max(0, r * r - (yy + .5 - r) ** 2) ** .5
            x0, x1 = int(-(-(r - dx) // 1)), int((r + dx) // 1)
            if x1 > x0:
                md.line([(x0, yy), (x1 - 1, yy)], fill=255)
        self.im.paste(tile, (int(x * S), int(y * S)), mask)

    def _ring(self, x, y, d, extra):
        cx, cy, rad = (x + d / 2) * S, (y + d / 2) * S, (d + extra) * S / 2
        self.d.ellipse([int(cx - rad), int(cy - rad), int(cx + rad), int(cy + rad)], fill=self.OL)

    def stamp(self, x, y, size):
        from PIL import Image
        st = self.assets.asset("og-stamp.png")
        if st is None:
            return
        st = st.resize((int(size * S), int(size * S)), Image.LANCZOS)
        self.im.paste(st, (int(x * S), int(y * S)), st)

    def save(self, file: Path, owner_glob: str):
        from PIL import Image
        out = self.im.resize((self.W, self.H), Image.LANCZOS)
        file.parent.mkdir(parents=True, exist_ok=True)
        tmp = file.with_name(file.name + ".%d.tmp" % os.getpid())
        out.save(tmp, "PNG", compress_level=6)
        os.replace(tmp, file)  # readers never see a half-written card
        for old in file.parent.glob(owner_glob):
            if old != file:
                old.unlink(missing_ok=True)
        if random.randint(1, 50) == 1:
            for old in file.parent.glob("*.png"):
                try:
                    if old.stat().st_mtime < time.time() - 2592000:
                        old.unlink()
                except OSError:
                    pass
        return file


class Card:
    """Base: a cached card. Subclasses build `key`, `owner_glob` and draw()."""
    tag = ""

    def __init__(self, assets: CardAssets):
        self.assets = assets

    @property
    def dir(self) -> Path:
        return self.assets.data / "og"

    @staticmethod
    def digest(parts) -> str:
        return hashlib.sha1(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()[:12]

    def file_for(self) -> Path:
        raise NotImplementedError

    def owner_glob(self) -> str:
        raise NotImplementedError

    def draw(self, cv: Canvas):
        raise NotImplementedError

    def render(self):
        """The cached or freshly drawn PNG path, or None when something it needs is missing."""
        if not self.assets.complete():
            return None
        f = self.file_for()
        if f.is_file():
            return f
        cv = Canvas(self.assets)
        cv.paper(self.tag)
        if self.draw(cv) is False:
            return None
        cv.save(f, self.owner_glob())
        return f if f.is_file() else None


class ProfileCard(Card):
    """?og=<username>. `u` has name, nick, bio, avatar, priv."""
    tag = "MASQUE PROFILE"

    def __init__(self, assets, u):
        super().__init__(assets)
        self.u = u

    def _id(self):
        return hashlib.sha1(str(self.u["name"]).lower().encode()).hexdigest()

    def file_for(self):
        u = self.u
        return self.dir / ("%s-%s.png" % (self._id(), self.digest([u["name"], u["nick"], u["bio"], u["avatar"], 1 if int(u["priv"]) else 0, "og2"])))

    def owner_glob(self):
        return self._id() + "-*.png"

    def draw(self, cv: Canvas):
        a, u = self.assets, self.u
        name, nick, priv = str(u["name"]), str(u["nick"] or ""), int(u["priv"])
        title = Text.strip(nick)
        if title == "" or not Text.drawable(title):
            title = "@" + name
        fn_title = a.title_font if Text.latin(title) else a.mono_font
        if priv:
            txt = "Private account. Send a friend request to see their posts."
        else:
            txt = Text.clean(str(u["bio"] or "").strip()) or "See their profile on Masque."
        src = a.upload(u["avatar"]) or (a.asset("og-avatar.png") and a._flatten(a.asset("og-avatar.png")))
        if src is None:
            return False
        cv.disc(src, 84, 150, 290, outline_extra=16, outline_shift=12)
        cv.stamp(84 + 290 - 96, 150 + 290 - 96, 120)
        x0, maxw = 440, 690
        sz = 132
        while sz > 56 and cv.width(sz, fn_title, title) > maxw:
            sz -= 4
        cv.text(sz, x0 + 6, 262 + 6, cv.SH, fn_title, title)
        cv.text(sz, x0, 262, cv.INK, fn_title, title)
        cv.text(30, x0, 322, cv.MUTE, a.mono_font, "@" + name)
        for i, line in enumerate(cv.wrap(25, a.mono_font, txt.split(), maxw, 3)):
            cv.text(25, x0, 384 + i * 38, cv.INK, a.mono_font, cv.fit(25, a.mono_font, line, maxw))
        cv.button(x0, 494)


class PostCard(Card):
    """?ogp=<post id>. `r` comes from PostAccess.public_post(), so it is already known to be public."""
    tag = "MASQUE POST"

    def __init__(self, assets, r):
        super().__init__(assets)
        self.r = r
        r = self.r
        self.masq = 1 if (int(r["anon"]) or int(r["mid"]) > 0) else 0
        if self.masq:
            mkn = str(r["mkn"] or "") if int(r["mid"]) > 0 else ""
            self.who, self.handle, self.av = (mkn or "Masque"), ("Masque" if mkn else ""), (str(r["mka"] or "") if mkn else "")
        else:
            self.who = str(r["nick"]) if str(r["nick"] or "") != "" else str(r["name"])
            self.handle, self.av = "@" + str(r["name"]), str(r["avatar"] or "")

    def file_for(self):
        r = self.r
        key = self.digest([str(r["cap"] or ""), str(r["aq"] or ""), self.who, self.handle, self.av, str(r["img"] or ""), 1 if int(r["sens"]) else 0,
                           int(r["ln"]), int(r["cn"]), 1 if int(r["pl"]) > 0 else 0, self.masq, "op2"])
        return self.dir / ("p%d-%s.png" % (int(r["id"]), key))

    def owner_glob(self):
        return "p%d-*.png" % int(self.r["id"])

    def draw(self, cv: Canvas):
        a, r = self.assets, self.r
        mono, pira = a.mono_font, a.title_font
        who = Text.strip(self.who)
        if who == "" or not Text.drawable(who):
            who = "Masque" if self.masq else "@" + str(r["name"])
        cap, aq = Text.clean(r["cap"]), Text.clean(r["aq"])
        img = str(r["img"] or "")
        ph = a.upload(img) if img != "" and not int(r["sens"]) else None
        if ph is not None:  # photo on the left
            px, py, pw = 84, 150, 330
            cv.rect(px + 4, py + 4, px + pw + 20, py + pw + 20, cv.OL)
            cv.rect(px - 8, py - 8, px + pw + 8, py + pw + 8, cv.OL)
            from PIL import Image
            w, h = ph.size
            m = min(w, h)
            if m > 0:
                tile = ph.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)).resize((pw * S, pw * S), Image.LANCZOS)
                cv.im.paste(tile, (px * S, py * S))
            if self.masq:
                cv.stamp(px + pw - 80, py + pw - 80, 120)
            x0, maxw = 480, 650
        else:
            x0, maxw = 84, 1046
            if self.masq:
                cv.stamp(1010, 128, 110)
        au = a.upload(self.av) or a._flatten(a.asset("og-avatar.png"))
        cv.disc(au, x0 + 4, 150, 64, outline_extra=8)
        nx, nw = x0 + 4 + 64 + 26, maxw - 96
        if self.handle != "":
            cv.text(30, nx, 176, cv.INK, mono, cv.fit(30, mono, who, nw))
            cv.text(22, nx, 208, cv.MUTE, mono, cv.fit(22, mono, self.handle, nw))
        else:
            cv.text(30, nx, 192, cv.INK, mono, cv.fit(30, mono, who, nw))
        top = 290
        if aq != "":
            cv.text(22, x0, 252, cv.MUTE, mono, cv.fit(22, mono, aq, maxw))
            top = 316
        words = cap.split()
        if cap == "":
            cap = "Shared a photo." if ph is not None else "See this post on Masque."
            words, huge = cap.split(), False
        else:
            huge = ph is None and len(words) <= 4 and len(cap) <= 28 and Text.latin(cap)
        if huge:
            sz = 150
            while sz > 64 and cv.width(sz, pira, cap) > maxw:
                sz -= 4
            by0 = 372 if aq != "" else 352
            cv.text(sz, x0 + 6, by0 + 6, cv.SH, pira, cap)
            cv.text(sz, x0, by0, cv.INK, pira, cap)
        else:
            fs, lh = (27, 38) if ph is not None else (32, 46)
            for i, line in enumerate(cv.wrap(fs, mono, words, maxw, 4 if aq != "" else 5)):
                cv.text(fs, x0, top + i * lh, cv.INK, mono, cv.fit(fs, mono, line, maxw))
        if int(r["sens"]):
            cv.text(20, x0, 478, cv.MUTE, mono, "Sensitive photo hidden")
        bx, by, bw = x0, 504, 300
        cv.button(bx, by)
        ln, cn = int(r["ln"]), int(r["cn"])
        parts = (["Poll"] if int(r["pl"]) > 0 else []) + ["%d mark%s" % (ln, "" if ln == 1 else "s"), "%d comment%s" % (cn, "" if cn == 1 else "s")]
        cl, cx = "  \u00b7  ".join(parts), bx + bw + 36
        cw, cs = 1130 - cx, 22
        while cs > 14 and cv.width(cs, mono, cl) > cw:
            cs -= 1
        cv.text(cs, cx, by + 39, cv.MUTE, mono, cl)
