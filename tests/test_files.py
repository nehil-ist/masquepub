#!/usr/bin/env python3
"""Step 4: ?img=, ?stk=, ?lpi=, ?og=, ?ogp=, ?ogdiag and the lpv action.   python3 -I tests/test_files.py -v"""
import hashlib
import io
import json
import re
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image  # noqa: E402
from masque.actions.links import LinkPreview  # noqa: E402
from masque.linkpreview import AddressGuard, LinkUrls, PagePreview  # noqa: E402
from tests.harness import Browser, OfflineCase  # noqa: E402


def png_bytes(color=(200, 10, 10), size=(60, 60)):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "PNG")
    return b.getvalue()


class FakeFetcher:
    """Stands in for the network: pages and pictures by URL."""
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def fetch(self, url, image=False):
        self.calls.append(url)
        return self.pages.get(url)


class FilesTest(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b, cls.c = cls.user("ann_f"), cls.user("ben_f"), cls.user("cy_f")
        cls.out = Browser(cls.app)  # a visitor who never signed in
        cls.ida, cls.idb, cls.idc = cls.uid("ann_f"), cls.uid("ben_f"), cls.uid("cy_f")

    @classmethod
    def uid(cls, name):  # classmethod version for setUpClass
        return cls.db.execute("SELECT id FROM users WHERE name=?", (name,)).fetchone()[0]

    def put(self, name, data):
        (self.tmp / "up" / name).write_bytes(data)

    def raw(self, who, qs, headers=None):
        return who.c.get("/?" + qs, headers=dict(headers or {}, **{"X-Real-IP": who.ip}))

    # ---- ?img= ----
    def test_img_rules(self):
        self.assertEqual(self.raw(self.a, "img=nothex.png").status_code, 404)
        n = "a1" * 12 + ".png"
        self.assertEqual(self.raw(self.a, "img=" + n).status_code, 404)  # no such file
        self.put(n, png_bytes())
        r = self.raw(self.out, "img=" + n)  # a file nothing refers to: public
        self.assertEqual((r.status_code, r.mimetype, r.headers["Cache-Control"]), (200, "image/png", "public,max-age=31536000,immutable"))
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.data, png_bytes())

    def test_img_chat_and_group_and_pending(self):
        n1, n2, n3, n4 = [("%02x" % i) * 12 + ".jpg" for i in (1, 2, 3, 4)]
        for n in (n1, n2, n3, n4):
            self.put(n, b"\xff\xd8\xff\xd9")
        self.db.execute("INSERT INTO messages(a,b,img,ts) VALUES(?,?,?,?)", (self.ida, self.idb, n1, int(time.time())))
        self.db.execute("INSERT INTO gmessages(gid,uid,img,ts) VALUES(?,?,?,?)", (77, self.ida, n2, int(time.time())))
        self.db.execute("INSERT INTO gmembers(gid,uid) VALUES(77,?)", (self.idb,))
        self.db.execute("INSERT INTO pend(img,uid,ts) VALUES(?,?,?)", (n3, self.idc, int(time.time())))
        self.db.execute("INSERT INTO gchats(id,avatar) VALUES(78,?)", (n4,))
        for who, qs, want in [(self.a, n1, 200), (self.b, n1, 200), (self.c, n1, 404), (self.out, n1, 404),
                              (self.b, n2, 200), (self.c, n2, 404), (self.out, n2, 404),
                              (self.c, n3, 200), (self.a, n3, 404), (self.out, n3, 404),
                              (self.a, n4, 404), (self.out, n4, 404)]:
            self.assertEqual(self.raw(who, "img=" + qs).status_code, want, (qs, who.ip))
        self.assertEqual(self.raw(self.b, "img=" + n1).headers["Cache-Control"], "private,max-age=31536000,immutable")
        self.db.execute("INSERT INTO gmembers(gid,uid) VALUES(78,?)", (self.ida,))
        self.assertEqual(self.raw(self.a, "img=" + n4).status_code, 200)

    def test_img_post_visibility(self):
        n = "b1" * 12 + ".png"
        self.put(n, png_bytes())
        self.a.post("post", cap="mine")
        pid = self.val("SELECT MAX(id) FROM posts")
        self.db.execute("UPDATE posts SET img=? WHERE id=?", (n, pid))
        self.assertEqual(self.raw(self.out, "img=" + n).status_code, 200)  # public post, public account
        self.db.execute("UPDATE users SET priv=1 WHERE id=?", (self.ida,))
        self.assertEqual(self.raw(self.out, "img=" + n).status_code, 404)
        self.assertEqual(self.raw(self.b, "img=" + n).status_code, 404)  # not friends
        self.assertEqual(self.raw(self.a, "img=" + n).status_code, 200)  # the owner
        self.db.execute("INSERT INTO friends(a,b,st) VALUES(?,?,1)", (self.ida, self.idb))
        self.assertEqual(self.raw(self.b, "img=" + n).status_code, 200)  # friends
        self.db.execute("UPDATE posts SET mid=5 WHERE id=?", (pid,))  # a Masque post ignores the private account
        self.assertEqual(self.raw(self.out, "img=" + n).status_code, 200)
        self.db.execute("UPDATE posts SET mid=0,vis=2 WHERE id=?", (pid,))  # only me
        self.assertEqual(self.raw(self.b, "img=" + n).status_code, 404)
        self.assertEqual(self.raw(self.a, "img=" + n).status_code, 200)
        self.db.execute("UPDATE users SET priv=0 WHERE id=?", (self.ida,))

    def test_audio_ranges(self):
        n = "c1" * 12 + ".mp3"
        self.put(n, bytes(range(100)))
        r = self.raw(self.a, "img=" + n)
        self.assertEqual((r.status_code, r.mimetype, r.headers["Accept-Ranges"], r.headers["Content-Length"]), (200, "audio/mpeg", "bytes", "100"))
        r = self.raw(self.a, "img=" + n, {"Range": "bytes=10-19"})
        self.assertEqual((r.status_code, r.headers["Content-Range"], r.data), (206, "bytes 10-19/100", bytes(range(10, 20))))
        r = self.raw(self.a, "img=" + n, {"Range": "bytes=-5"})
        self.assertEqual((r.status_code, r.data), (206, bytes(range(95, 100))))
        r = self.raw(self.a, "img=" + n, {"Range": "bytes=90-"})
        self.assertEqual((r.headers["Content-Range"], len(r.data)), ("bytes 90-99/100", 10))
        r = self.raw(self.a, "img=" + n, {"Range": "bytes=200-300"})
        self.assertEqual((r.status_code, r.headers["Content-Range"]), (416, "bytes */100"))

    # ---- ?stk= and ?lpi= ----
    def test_stickers_and_thumbs(self):
        sid = "d1" * 8
        (self.tmp / "stk").mkdir(exist_ok=True)
        (self.tmp / "stk" / (sid + ".png")).write_bytes(png_bytes())
        self.db.execute("INSERT INTO stkimg(id,sha,ext,sz,ts) VALUES(?,?,?,?,?)", (sid, "x" * 64, "png", 10, 1))
        r = self.raw(self.a, "stk=" + sid)
        self.assertEqual((r.status_code, r.mimetype, r.headers["Content-Security-Policy"]), (200, "image/png", "default-src 'none'"))
        r = self.raw(self.out, "stk=" + sid)
        self.assertEqual((r.status_code, r.headers["Cache-Control"]), (404, "no-store"))
        self.assertEqual(self.raw(self.a, "stk=" + "e1" * 8).status_code, 404)
        (self.tmp / "lp").mkdir(exist_ok=True)
        (self.tmp / "lp" / (sid + ".jpg")).write_bytes(b"\xff\xd8\xff\xd9")
        self.assertEqual(self.raw(self.a, "lpi=" + sid).headers["Cache-Control"], "private,max-age=2592000,immutable")
        self.assertEqual(self.raw(self.out, "lpi=" + sid).status_code, 404)

    # ---- cards ----
    def test_profile_card(self):
        av = "f1" * 12 + ".png"
        self.put(av, png_bytes((20, 90, 160), (300, 200)))
        self.db.execute("UPDATE users SET nick=?,bio=?,avatar=? WHERE id=?", ("Ann \U0001F600 Pirate", "Loves masks and long walks on the beach. " * 4, av, self.ida))
        r = self.raw(self.out, "og=ann_f")
        self.assertEqual((r.status_code, r.mimetype, r.headers["Cache-Control"]), (200, "image/png", "public, max-age=3600"))
        self.assertEqual(Image.open(io.BytesIO(r.data)).size, (1200, 630))
        mine = lambda: sorted((self.tmp / "og").glob(hashlib.sha1(b"ann_f").hexdigest() + "-*.png"))
        first = mine()
        self.assertEqual(len(first), 1)
        self.raw(self.out, "og=ann_f")
        self.assertEqual(mine(), first)  # served from the cache
        self.db.execute("UPDATE users SET bio='changed' WHERE id=?", (self.ida,))
        self.raw(self.out, "og=ann_f")
        self.assertEqual(len(mine()), 1)  # the older card of this person is gone
        self.assertNotEqual(mine(), first)
        # missing user: falls back
        r = self.raw(self.out, "og=nobody_x")
        self.assertEqual((r.status_code, r.headers["Location"]), (302, "assets/og.png"))
        r = self.raw(self.out, "og=bad%20name")
        self.assertEqual(r.headers["Location"], "assets/og.png")

    def test_post_card(self):
        self.b.post("post", cap="Hello world")
        pid = self.val("SELECT MAX(id) FROM posts")
        r = self.raw(self.out, "ogp=%d" % pid)
        self.assertEqual((r.status_code, r.mimetype), (200, "image/png"))
        self.assertEqual(Image.open(io.BytesIO(r.data)).size, (1200, 630))
        self.b.post("post", cap="A longer caption that has to wrap over several lines because the card is only so wide, and it keeps going " * 3)
        pid2 = self.val("SELECT MAX(id) FROM posts")
        self.assertEqual(self.raw(self.out, "ogp=%d" % pid2).status_code, 200)
        self.db.execute("UPDATE users SET priv=1 WHERE id=?", (self.idb,))
        r = self.raw(self.out, "ogp=%d" % pid)  # not public: no card
        self.assertEqual((r.status_code, r.headers["Location"]), (302, "assets/og.png"))
        self.db.execute("UPDATE users SET priv=0 WHERE id=?", (self.idb,))
        self.assertEqual(self.raw(self.out, "ogp=999999").status_code, 302)

    def test_og_diag_admin_only(self):
        self.assertEqual(self.raw(self.a, "ogdiag").status_code, 404)
        adm = Browser(self.app)
        adm.me()
        r, j = adm.post("login", name=self.ADMIN, pw="adminpass123")
        self.assertEqual(r.status_code, 200, j)
        r = self.raw(adm, "ogdiag&u=ann_f")
        text = r.data.decode()
        self.assertIn("Pillow loaded: yes", text)
        self.assertIn("profile card: made", text)
        self.assertNotIn("MISSING", text)

    # ---- lpv ----
    def lpv(self, who, url):
        return who.get("a=lpv&lu=" + url)

    def test_lpv_basics(self):
        self.assertEqual(self.out.get("a=lpv&lu=https://x.test/")[0].status_code, 401)
        self.assertEqual(self.lpv(self.a, "ftp://x.test")[1], {"none": 1})
        self.assertEqual(self.lpv(self.a, "")[1], {"none": 1})
        # links to this site: from the database, never fetched
        j = self.lpv(self.a, "http://localhost/u/ben_f")[1]
        self.assertEqual((j["t"], j["s"], j["i"]), ("@ben_f on Masque", "Masque", ""))
        self.assertTrue(re.fullmatch(r"\?og=ben_f&v=[0-9a-f]{8}", j["iu"]), j)
        self.b.post("post", cap="  spaced   out  caption ")
        pid = self.val("SELECT MAX(id) FROM posts")
        j = self.lpv(self.a, "http://localhost/?p=%d" % pid)[1]
        self.assertEqual((j["t"], j["d"]), ("ben_f on Masque", "spaced out caption"))
        self.assertTrue(j["iu"].startswith("?ogp=%d&v=" % pid))
        self.assertEqual(self.lpv(self.a, "http://localhost/u/nobody_zz")[1], {"none": 1})
        self.assertEqual(self.lpv(self.a, "http://localhost/")[1]["t"], "Masque")
        self.assertEqual(self.lpv(self.a, "http://localhost/other")[1], {"none": 1})
        # the real network guard: loopback and private addresses are never fetched
        self.assertEqual(self.lpv(self.a, "http://127.0.0.1:8080/x")[1], {"none": 1})
        self.assertEqual(self.lpv(self.a, "http://192.168.1.5/")[1], {"none": 1})
        self.assertEqual(self.val("SELECT ok FROM lpv WHERE h=?", __import__("hashlib").sha1(b"http://127.0.0.1:8080/x").hexdigest()), 0)

    def test_lpv_fetch_cache_thumb(self):
        page = (b'<html><head><title>Fallback</title><meta property="og:title" content="Big &amp; Bold">'
                b'<meta property="og:description" content="  A   nice\npage  "><meta property="og:image" content="/pic.png"></head></html>')
        fake = FakeFetcher({"https://news.test/a": (page, "text/html; charset=utf-8", "https://news.test/a"),
                            "https://news.test/pic.png": (png_bytes((9, 99, 199), (800, 400)), "image/png", "https://news.test/pic.png")})
        LinkPreview.fetcher = fake
        try:
            j = self.lpv(self.a, "https://news.test/a")[1]
            self.assertEqual((j["t"], j["d"], j["s"]), ("Big & Bold", "A nice page", "news.test"))
            self.assertTrue(re.fullmatch(r"[0-9a-f]{16}", j["i"]), j)
            thumb = Image.open(self.tmp / "lp" / (j["i"] + ".jpg"))
            self.assertEqual((thumb.format, thumb.size), ("JPEG", (480, 240)))
            self.assertEqual(self.raw(self.a, "lpi=" + j["i"]).status_code, 200)
            n = len(fake.calls)
            self.assertEqual(self.lpv(self.b, "https://news.test/a")[1], j)  # cached for everyone
            self.assertEqual(len(fake.calls), n)
            # a page that cannot be read is cached as "none" for an hour
            self.assertEqual(self.lpv(self.a, "https://gone.test/")[1], {"none": 1})
            n = len(fake.calls)
            self.assertEqual(self.lpv(self.a, "https://gone.test/")[1], {"none": 1})
            self.assertEqual(len(fake.calls), n)
        finally:
            LinkPreview.fetcher = None

    def test_lpv_rate_limit(self):
        LinkPreview.fetcher = FakeFetcher({})
        try:
            c = self.user("dee_f")
            codes = [self.lpv(c, "https://rate%d.test/" % i)[0].status_code for i in range(32)]
            self.assertEqual(codes[:30], [200] * 30)
            self.assertEqual(codes[30], 429)
        finally:
            LinkPreview.fetcher = None


class UnitTest(unittest.TestCase):
    def test_address_guard(self):
        ok, bad = AddressGuard.ok, lambda ip: not AddressGuard.ok(ip)
        for ip in ("8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"):
            self.assertTrue(ok(ip), ip)
        for ip in ("127.0.0.1", "10.0.0.1", "172.16.5.5", "192.168.0.1", "169.254.169.254", "0.0.0.0", "100.64.0.1", "198.18.0.1", "192.0.0.8",
                   "224.0.0.1", "240.0.0.1", "::1", "fe80::1", "fc00::1", "2002::1", "::ffff:127.0.0.1", "nonsense"):
            self.assertTrue(bad(ip), ip)
        self.assertEqual(AddressGuard.resolve("a b"), [])
        self.assertEqual(AddressGuard.resolve("8.8.8.8"), ["8.8.8.8"])

    def test_urls(self):
        f = LinkUrls.absolute
        base = "https://site.test:8443/dir/page.html?x=1"
        self.assertEqual(f("/a.png", base), "https://site.test:8443/a.png")
        self.assertEqual(f("a.png", base), "https://site.test:8443/dir/a.png")
        self.assertEqual(f("//cdn.test/a.png#frag", base), "https://cdn.test/a.png")
        self.assertEqual(f("http://o.test/x", base), "http://o.test/x")
        self.assertEqual(f("javascript:alert(1)", base), "")
        self.assertEqual(f("", base), "")
        self.assertEqual(f("x" * 700, base), "")

    def test_page_parse(self):
        html = '<meta charset="iso-8859-1"><title> T\n itle </title><meta name="description" content="d"><meta name="twitter:image" content="i.png">'.encode("latin-1")
        r = PagePreview.parse(html, "text/html", "https://www.ex.test/p/")
        self.assertEqual(r, {"t": "T itle", "d": "d", "s": "ex.test", "iu": "https://www.ex.test/p/i.png"})
        self.assertIsNone(PagePreview.parse(b"<p>no title</p>", "text/html", "https://ex.test/"))


if __name__ == "__main__":
    unittest.main()
