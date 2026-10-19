"""Chat link previews (PHP: lp_ip_ok, lp_resolve, lp_fetch, lp_abs, lp_thumb, lp_clean, lp_parse, lp_own and the `lpv` cache).

The SERVER fetches a linked page's title and description, so the linked site never sees the reader's IP address. Guards against
the server being tricked into reaching internal addresses (SSRF): http(s) only, ports 80/443/8080/8443 only, every address the
name resolves to must be a public one, the connection is pinned to the address that was checked (no DNS switching), redirects are
re-checked at each hop, the download is capped, and results are cached in `lpv`.
"""
import codecs
import hashlib
import http.client
import ipaddress
import json
import re
import secrets
import socket
import ssl
import time
import zlib
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

_PORTS = (80, 443, 8080, 8443)
_HOST_OK = re.compile(r"^[A-Za-z0-9.-]+$")
_HTML_TYPE = re.compile(r"text/html|application/xhtml", re.I)
_IMG_TYPE = re.compile(r"^image/(jpeg|png|webp|gif)", re.I)
_UA = "Mozilla/5.0 (compatible; MasqueLinkPreview/1.0)"


class AddressGuard:
    """Decides which addresses the server may connect to, and resolves names."""

    @staticmethod
    def ok(ip: str) -> bool:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if a.is_multicast or not a.is_global:  # private, loopback, link-local, reserved, 100.64/10, 192.0.0/24, 198.18/15 ...
            return False
        if a.version == 6:  # global unicast only, not 6to4
            low = a.compressed.lower()
            return low[0] in "23" and not low.startswith("2002:")
        return True

    @staticmethod
    def resolve(host: str) -> list:
        try:
            ipaddress.ip_address(host)
            return [host]
        except ValueError:
            pass
        if len(host) > 253 or not _HOST_OK.match(host):
            return []
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            return []
        out = []
        for info in infos:
            ip = info[4][0]
            if ip not in out:
                out.append(ip)
        return out


class _Pinned:
    """Mixin: connect to the address that was checked, but talk to (and verify) the real host name."""
    pin = ""

    def _sock(self):
        return socket.create_connection((self.pin, self.port), 4)


class _PinnedHttp(_Pinned, http.client.HTTPConnection):
    def connect(self):
        self.sock = self._sock()


class _PinnedHttps(_Pinned, http.client.HTTPSConnection):
    def connect(self):
        self.sock = ssl.create_default_context().wrap_socket(self._sock(), server_hostname=self.host)


class SafeFetcher:
    """Downloads one page or one picture through the guards above. fetch() returns (bytes, content_type, final_url) or None."""

    def __init__(self, guard: AddressGuard = None):
        self.guard = guard or AddressGuard()

    def fetch(self, url: str, image: bool = False):
        ok_type = _IMG_TYPE if image else _HTML_TYPE
        cap = 3000000 if image else 400000
        for _ in range(4):
            try:
                p = urlsplit(url)
                host = (p.hostname or "").lower()
                port = p.port or (443 if p.scheme.lower() == "https" else 80)
            except ValueError:
                return None
            if not host or p.username is not None or p.password is not None or p.scheme.lower() not in ("http", "https"):
                return None
            if port not in _PORTS:
                return None
            ips = self.guard.resolve(host)
            if not ips or not all(self.guard.ok(i) for i in ips):
                return None
            pin = next((i for i in ips if ":" not in i), ips[0])
            res = self._get_once(p, host, port, pin, image, ok_type, cap)
            if res is None:
                return None
            code, ctype, loc, body, big = res
            if 300 <= code < 400 and loc:
                url = LinkUrls.absolute(loc, url)
                if url == "":
                    return None
                continue
            if image and big:
                return None
            if code == 200 and body and (bool(ok_type.search(ctype)) if image else (ctype == "" or bool(ok_type.search(ctype)))):
                return body, ctype, url
            return None
        return None

    @staticmethod
    def _get_once(p, host, port, pin, image, ok_type, cap):
        cls = _PinnedHttps if p.scheme.lower() == "https" else _PinnedHttp
        conn = cls(host, port, timeout=7)
        conn.pin = pin
        path = (p.path or "/") + ("?" + p.query if p.query else "")
        accept = "image/jpeg,image/png,image/webp,image/gif;q=0.9" if image else "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"
        deadline = time.monotonic() + 7
        try:
            conn.request("GET", path, headers={"User-Agent": _UA, "Accept": accept, "Accept-Language": "en", "Accept-Encoding": "gzip"})
            r = conn.getresponse()
            ctype = (r.getheader("Content-Type") or "").strip()
            loc = (r.getheader("Location") or "").strip()
            if ctype != "" and not ok_type.search(ctype) and not (300 <= r.status < 400):
                return r.status, ctype, loc, b"", False  # not the kind of file we want
            inflate = zlib.decompressobj(31) if (r.getheader("Content-Encoding") or "").lower() == "gzip" else None
            buf, big = bytearray(), False
            while time.monotonic() < deadline:
                chunk = r.read(16384)
                if not chunk:
                    break
                buf += inflate.decompress(chunk, cap + 1) if inflate else chunk
                if len(buf) > cap:
                    big = True  # a page: enough, the title and meta tags are at the top. A picture: too big, give up
                    del buf[cap:]
                    break
            return r.status, ctype, loc, bytes(buf), big
        except (OSError, http.client.HTTPException, zlib.error):
            return None
        finally:
            conn.close()


class LinkUrls:
    @staticmethod
    def absolute(ref: str, base: str) -> str:
        """Turns a link found in a page (absolute, //host/x, /x or x) into a full http(s) URL, or ''."""
        ref = str(ref).strip(" \t\n\r\0\x0b")
        try:
            p = urlsplit(base)
            host = p.hostname
        except ValueError:
            return ""
        if ref == "" or len(ref) > 600 or not host:
            return ""
        sc = (p.scheme or "https").lower()
        root = "%s://%s%s" % (sc, p.netloc.rsplit("@", 1)[-1], "")
        if re.match(r"^https?://", ref, re.I):
            u = ref
        elif ref.startswith("//"):
            u = sc + ":" + ref
        elif ref[0] == "/":
            u = root + ref
        elif re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", ref):
            return ""
        else:
            u = root + re.sub(r"/[^/]*$", "/", p.path or "/") + ref
        return re.sub(r"#.*$", "", u)


class PagePreview:
    """Reads title, description, site name and picture address out of a fetched page (PHP lp_parse)."""

    class _Meta(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.meta, self.title, self._in_title = {}, None, False

        def handle_starttag(self, tag, attrs):
            if tag == "meta":
                a = dict((k, v or "") for k, v in attrs)
                k = (a.get("property") or a.get("name") or "").strip().lower()
                v = a.get("content", "")
                if k != "" and v != "" and k not in self.meta:
                    self.meta[k] = v
            elif tag == "title" and self.title is None:
                self.title, self._in_title = "", True

        def handle_endtag(self, tag):
            if tag == "title":
                self._in_title = False

        def handle_data(self, data):
            if self._in_title:
                self.title += data

    @staticmethod
    def clean(s, n: int) -> str:
        s = re.sub(r"[\x00-\x1f\x7f\s]+", " ", str(s or ""))
        return s.strip()[:n].strip()

    @staticmethod
    def decode(body: bytes, ctype: str) -> str:
        cs = "utf-8"
        m = re.search(r"charset=([A-Za-z0-9_-]+)", ctype, re.I) or re.search(rb"<meta[^>]+charset=[\"']?([A-Za-z0-9_-]+)", body[:4096], re.I)
        if m:
            g = m.group(1)
            cs = g.decode("latin-1") if isinstance(g, bytes) else g
        try:
            codecs.lookup(cs)
        except LookupError:
            cs = "utf-8"
        return body.decode(cs, "replace")

    @classmethod
    def parse(cls, body: bytes, ctype: str, url: str):
        p = cls._Meta()
        try:
            p.feed(cls.decode(body, ctype))
            p.close()
        except Exception:
            pass
        m = p.meta
        t = cls.clean(m.get("og:title") or m.get("twitter:title") or p.title or "", 120)
        if t == "":
            return None
        host = re.sub(r"^www\.", "", (urlsplit(url).hostname or ""), flags=re.I)
        site = cls.clean(m.get("og:site_name", ""), 60)
        iu = LinkUrls.absolute(m.get("og:image") or m.get("og:image:url") or m.get("twitter:image") or m.get("twitter:image:src") or "", url)
        desc = m.get("og:description") or m.get("twitter:description") or m.get("description") or ""
        return {"t": t, "d": cls.clean(desc, 200), "s": site or host, "iu": iu}


class ThumbMaker:
    """Downloads a page's preview picture through the guarded fetcher, re-draws it as a small JPEG (nothing of the original file is kept)
    and returns its id in DATA_DIR/lp, or ''."""

    def __init__(self, data_dir: Path, fetcher: SafeFetcher):
        self.dir = Path(data_dir) / "lp"
        self.fetcher = fetcher

    def make(self, image_url: str) -> str:
        if image_url == "":
            return ""
        f = self.fetcher.fetch(image_url, True)
        if not f:
            return ""
        try:
            from PIL import Image
            with Image.open(BytesIO(f[0])) as src:
                if src.format not in ("JPEG", "PNG", "WEBP", "GIF"):
                    return ""
                w, h = src.size
                if w < 40 or h < 40 or w * h > 12000000:
                    return ""
                src = src.convert("RGBA")
            sc = min(1, 480 / max(w, h))
            nw, nh = max(1, round(w * sc)), max(1, round(h * sc))
            canvas = Image.new("RGB", (nw, nh), (255, 255, 255))
            canvas.paste(src.resize((nw, nh), Image.LANCZOS), (0, 0), src.resize((nw, nh), Image.LANCZOS))
            tid = hashlib.sha1(image_url.encode()).hexdigest()[:16]
            self.dir.mkdir(parents=True, exist_ok=True)
            canvas.save(self.dir / (tid + ".jpg"), "JPEG", quality=78)
            return tid
        except Exception:
            return ""


from .ogcard import CardKeys  # noqa: E402


class OwnLinks:
    """Preview for a link that points at this site, built straight from the database (never fetched over HTTP, so it works on localhost
    and behind a proxy). preview() gives a dict for a profile / public post / the home page, {} when it is ours but has nothing to show
    (private or missing), None when it is not our site."""

    def __init__(self, ctx, cards_ready: bool):
        self.ctx, self.cards_ready = ctx, cards_ready

    def preview(self, url: str):
        from flask import request
        try:
            p = urlsplit(url)
            host = (p.hostname or "").lower()
        except ValueError:
            return None
        if not host:
            return None
        ours = set()
        hh = request.host.lower()
        if hh:
            ours.add(re.sub(r":\d+$", "", hh))
        if self.ctx.cfg.site_url:
            ours.add((urlsplit(self.ctx.cfg.site_url).hostname or "").lower())
        ours.discard("")
        if host not in ours:
            return None
        kind = val = ""
        path = unquote(p.path or "/")
        qs = parse_qs(p.query, keep_blank_values=True)
        m = re.search(r"/(u|p)/([^/]+)/?$", path)
        frag = re.match(r"^/?(u|p)/([^/]+)/?$", p.fragment or "")
        if m:
            kind, val = m.group(1), m.group(2)
        elif qs.get("u", [""])[0] != "":
            kind, val = "u", qs["u"][0]
        elif qs.get("p", [""])[0] != "":
            kind, val = "p", qs["p"][0]
        elif frag:
            kind, val = frag.group(1), frag.group(2)
        if kind == "u":
            return self._profile(val)
        if kind == "p":
            return self._post(val)
        if path.strip("/") == "" or path.endswith("/index.php"):
            return {"t": "Masque", "d": "Post, chat and ask anonymously. No email needed.", "s": "Masque", "i": ""}
        return {}

    def _profile(self, name):
        ctx = self.ctx
        if not ctx.names.valid(name):
            return {}
        pu = ctx.db.one("SELECT name,nick,bio,avatar,priv FROM users WHERE name=?", (name,))
        if not pu:
            return {}
        bio = str(pu["bio"] or "").strip()
        r = {
            "t": ("%s (@%s)" % (pu["nick"], pu["name"]) if str(pu["nick"] or "") != "" else "@" + pu["name"]) + " on Masque",
            "d": "Private account. Send a friend request on Masque to see their posts." if int(pu["priv"]) else (bio[:160] if bio != "" else "See their profile on Masque."),
            "s": "Masque", "i": "",
        }
        if self.cards_ready:
            r["iu"] = "?og=%s&v=%s" % (pu["name"], CardKeys.profile(pu))
        return r

    def _post(self, val):
        ctx = self.ctx
        if not re.fullmatch(r"[0-9]{1,12}", val):
            return {}
        pp = ctx.access.public_post(val)
        if not pp:
            return {}
        masked = int(pp["anon"]) or int(pp["mid"]) > 0
        if masked:
            who = str(pp["mkn"]) if int(pp["mid"]) > 0 and str(pp["mkn"] or "") != "" else "Masque"
        else:
            who = str(pp["nick"]) if str(pp["nick"] or "") != "" else str(pp["name"])
        cap = re.sub(r"\s+", " ", str(pp["cap"] or "")).strip()
        r = {"t": who + " on Masque",
             "d": cap[:160] if cap != "" else ("Photo post on Masque." if str(pp["img"] or "") != "" else "See this post on Masque."),
             "s": "Masque", "i": ""}
        if self.cards_ready:
            r["iu"] = "?ogp=%d&v=%s" % (int(pp["id"]), CardKeys.post(pp))
        return r


class LinkPreviews:
    """The `lpv` action's brain: own links straight from the database, other links from the cache or fetched (rate-limited)."""

    def __init__(self, ctx, fetcher: SafeFetcher = None, cards_ready: bool = False):
        self.ctx = ctx
        self.fetcher = fetcher or SafeFetcher()
        self.thumbs = ThumbMaker(ctx.cfg.data_dir, self.fetcher)
        self.own = OwnLinks(ctx, cards_ready)

    def lookup(self, m, url: str) -> dict:
        ctx, db = self.ctx, self.ctx.db
        own = self.own.preview(url)
        if own is not None:
            return own or {"none": 1}
        hk = hashlib.sha1(url.encode()).hexdigest()
        c = db.one("SELECT t,d,s,i,ts,ok FROM lpv WHERE h=?", (hk,))
        if c and ctx.now - int(c["ts"]) < (604800 if int(c["ok"]) else 3600):
            return {"t": c["t"], "d": c["d"], "s": c["s"], "i": str(c["i"] or "")} if int(c["ok"]) else {"none": 1}
        ctx.limits.throttle("lp%d" % m["id"], 30, 600)
        r, im = None, ""
        try:
            f = self.fetcher.fetch(url)
            if f:
                r = PagePreview.parse(f[0], f[1], f[2])
            if r:
                im = self.thumbs.make(r["iu"])
        except Exception:
            pass
        db.execute("INSERT OR REPLACE INTO lpv(h,t,d,s,i,ts,ok) VALUES(?,?,?,?,?,?,?)",
                   (hk, (r or {}).get("t", ""), (r or {}).get("d", ""), (r or {}).get("s", ""), im, ctx.now, 1 if r else 0))
        if secrets.randbelow(100) == 0:
            self._forget_old()
        return {"t": r["t"], "d": r["d"], "s": r["s"], "i": im} if r else {"none": 1}

    def _forget_old(self):
        db = self.ctx.db
        for o in db.all("SELECT h,i FROM lpv WHERE ts<?", (self.ctx.now - 2592000,)):
            db.execute("DELETE FROM lpv WHERE h=?", (o["h"],))
            if o["i"] and not db.value("SELECT 1 FROM lpv WHERE i=?", (o["i"],)):
                try:
                    (self.thumbs.dir / (o["i"] + ".jpg")).unlink()
                except OSError:
                    pass
