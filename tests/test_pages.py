#!/usr/bin/env python3
"""Step 5: the HTML shell, privacy/terms pages, /u/ and /p/ links, manifest, service worker, assets and gzip.   python3 -I tests/test_pages.py -v"""
import dataclasses
import gzip
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from masque.app import create_app  # noqa: E402
from masque.assets import AssetFiles  # noqa: E402
from masque.pages import PrettyLinks  # noqa: E402
from tests.harness import OfflineCase, ROOT  # noqa: E402


class PagesTest(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a = cls.user("ann_s")
        cls.db.execute("UPDATE users SET nick=?,bio=? WHERE name='ann_s'", ("Ann <b>", "Bio  with \"quotes\" & more"))

    def get(self, url, headers=None, app=None):
        return (app or self.app).test_client().get(url, headers=headers or {})

    # ---- shell ----
    def test_shell_home(self):
        r = self.get("/")
        self.assertEqual((r.status_code, r.mimetype), (200, "text/html"))
        html = r.data.decode()
        nonce = re.search(r"script-src 'self' 'nonce-([^']+)'", r.headers["Content-Security-Policy"]).group(1)
        self.assertIn('<script nonce="%s">' % nonce, html)
        self.assertEqual((r.headers["X-Frame-Options"], r.headers["Referrer-Policy"], r.headers["X-Content-Type-Options"]), ("DENY", "same-origin", "nosniff"))
        self.assertIn("no-store", r.headers["Cache-Control"])
        self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])
        self.assertIn("PHPSESSID=", r.headers["Set-Cookie"])  # a first visit gets a session, like PHP
        self.assertIn('<title>Masque</title>', html)
        self.assertIn('<link rel="canonical" href="http://localhost/">', html)
        self.assertRegex(html, r'og:image" content="http://localhost/assets/og\.png\?v=\d+"')
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', html)
        self.assertRegex(html, r'href="assets/style\.min\.css\?v=\d+"')
        self.assertRegex(html, r'src="assets/app(?:\.min)?\.js\?v=\d+"></script></body></html>\s*$')
        self.assertNotIn("@@", html)
        self.assertNotIn("<?", html)
        self.assertNotIn("<base", html)
        r2 = self.get("/")  # a second visit has a different nonce
        self.assertNotEqual(r2.headers["Content-Security-Policy"], r.headers["Content-Security-Policy"])

    def test_shell_any_path_and_post(self):
        self.assertIn("<!DOCTYPE html>", self.get("/whatever/else").data.decode())
        self.assertIn("<!DOCTYPE html>", self.get("/assets/nope.txt").data.decode())  # missing file: the page, like PHP
        self.assertEqual(self.get("/assets/../index.php").status_code, 200)  # never the source file
        self.assertNotIn(b"<?php", self.get("/assets/../index.php").data)
        r = self.app.test_client().post("/")
        self.assertIn(b"<!DOCTYPE html>", r.data)
        r = self.get("/?a=nosuchaction")  # every action is ported: unknown ones answer like PHP's last line
        self.assertEqual((r.status_code, r.data), (404, b'{"e":"Not found."}'))

    def test_pretty_links_and_og(self):
        r = self.get("/u/ann_s")
        html = r.data.decode()
        self.assertIn('<base href="/">', html)
        self.assertIn("<title>Ann &lt;b&gt; (@ann_s) on Masque</title>", html)
        self.assertIn('<meta name="description" content="Bio with &quot;quotes&quot; &amp; more">'.replace("Bio with", "Bio  with"), html)
        self.assertRegex(html, r'og:image" content="http://localhost/\?og=ann_s&amp;v=[0-9a-f]{8}"')
        self.assertIn('content="http://localhost/u/ann_s"', html)
        self.assertIn("profile card", html)
        self.assertIn('og:image:width" content="1200"', html)
        self.assertIn('<base href="/sub/">', self.get("/sub/u/ann_s").data.decode())
        html = self.get("/?u=ann_s").data.decode()  # old style link
        self.assertIn("(@ann_s) on Masque", html)
        self.assertNotIn("<base", html)
        html = self.get("/u/nobody_q").data.decode()  # unknown profile: the site's own tags, base still set
        self.assertIn("<title>Masque</title>", html)
        self.assertIn('<base href="/">', html)
        self.db.execute("UPDATE users SET priv=1 WHERE name='ann_s'")
        self.assertIn("Private account. Send a friend request", self.get("/u/ann_s").data.decode())
        self.db.execute("UPDATE users SET priv=0 WHERE name='ann_s'")

    def test_post_link(self):
        self.a.post("post", cap="  Hello   <world>  ")
        pid = self.val("SELECT MAX(id) FROM posts")
        html = self.get("/p/%d" % pid).data.decode()
        self.assertIn("<title>Ann &lt;b&gt; on Masque</title>", html)
        self.assertIn('content="Hello &lt;world&gt;"', html)
        self.assertRegex(html, r'content="http://localhost/\?ogp=%d&amp;v=[0-9a-f]{8}"' % pid)
        self.assertIn("post card", html)
        self.assertIn("<title>Masque</title>", self.get("/p/999999").data.decode())
        self.assertIn('<base href="/">', self.get("/p/abc").data.decode())
        self.db.execute("UPDATE posts SET mid=3 WHERE id=?", (pid,))  # a Masque post never names the account
        self.assertIn("<title>Masque on Masque</title>", self.get("/p/%d" % pid).data.decode())

    def test_site_url_and_https(self):
        cfg = dataclasses.replace(self.cfg, site_url="https://masque.example")
        html = self.get("/", app=create_app(cfg)).data.decode()
        self.assertIn('rel="canonical" href="https://masque.example/"', html)
        html = self.get("/", {"X-Forwarded-Proto": "https", "Host": "m.test"}).data.decode()
        self.assertIn('rel="canonical" href="https://m.test/"', html)
        r = self.get("/", {"X-Forwarded-Proto": "https"})
        self.assertIn("Secure", r.headers["Set-Cookie"])

    def test_csp_off(self):
        r = self.get("/", app=create_app(dataclasses.replace(self.cfg, csp_off=True)))
        self.assertNotIn("Content-Security-Policy", r.headers)

    # ---- legal pages, manifest, service worker ----
    def test_legal_pages(self):
        r = self.get("/?page=privacy")
        html = r.data.decode()
        self.assertEqual((r.status_code, r.headers["Cache-Control"], r.headers["X-Content-Type-Options"]), (200, "public,max-age=600", "nosniff"))
        self.assertEqual(r.headers["Content-Security-Policy"], "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'")
        self.assertIn("<title>Privacy - Masque</title>", html)
        self.assertEqual(html.count("<section>"), 11)
        self.assertIn("We do not ask for a phone number or real name. We do not ask for an email address.", html)
        self.assertIn("by using Report inside the app", html)
        self.assertIn('<a href="?page=terms">Terms</a>', html)
        t = self.get("/?page=terms").data.decode()
        self.assertEqual(t.count("<section>"), 8)
        self.assertIn('<a href="?page=privacy">Privacy</a>', t)
        self.assertRegex(html, r'href="assets/style\.min\.css\?v=\d+"')
        # CONTACT and the recovery email switch change the text
        cfg = dataclasses.replace(self.cfg, contact="me@x.test <hi>", site_url="https://m.example", brevo_key="k", mail_from="a@b.co",
                                  mail_key="0123456789abcdef0123")
        html = self.get("/?page=privacy", app=create_app(cfg)).data.decode()
        self.assertIn("at <b>me@x.test &lt;hi&gt;</b>.", html)
        self.assertIn("An email address is optional", html)
        self.assertEqual(self.get("/?page=other").status_code, 200)  # not a legal page: the shell
        self.assertIn("<!DOCTYPE html>", self.get("/?page=other").data.decode())

    def test_manifest_and_sw(self):
        r = self.get("/?manifest=1")
        self.assertEqual((r.mimetype, r.headers["Cache-Control"]), ("application/manifest+json", "public,max-age=3600"))
        self.assertEqual(json.loads(r.data)["name"], "Masque")
        r = self.get("/?sw=1")
        self.assertEqual((r.mimetype, r.headers["Service-Worker-Allowed"], r.headers["Cache-Control"]), ("application/javascript", "./", "no-cache"))
        self.assertRegex(r.data.decode(), r'const V = "mq-shell-[0-9a-f]{8}";')
        self.assertNotIn("96bcdefgh", r.data.decode())
        self.assertEqual(self.get("/?sw=1").data, r.data)

    # ---- assets ----
    def test_gzip_assets(self):
        src = (ROOT / "assets" / "app.js").read_bytes()
        r = self.get("/assets/app.js?v=123", {"Accept-Encoding": "gzip, br"})
        self.assertEqual((r.status_code, r.headers["Content-Encoding"], r.headers["Vary"], r.mimetype), (200, "gzip", "Accept-Encoding", "application/javascript"))
        self.assertEqual(r.headers["Cache-Control"], "public, max-age=31536000, immutable")
        self.assertEqual(gzip.decompress(r.data), src)
        self.assertEqual(int(r.headers["Content-Length"]), len(r.data))
        self.assertEqual(len(list((self.tmp / "gz").glob("*.gz"))), 1)
        etag = r.headers["ETag"]
        self.assertTrue(etag.startswith('"') and etag.endswith('-gz"'))
        r304 = self.get("/assets/app.js?v=123", {"Accept-Encoding": "gzip", "If-None-Match": etag})
        self.assertEqual((r304.status_code, r304.data), (304, b""))
        r = self.get("/assets/app.js", {"Accept-Encoding": "gzip"})  # no ?v=: checked every time
        self.assertEqual(r.headers["Cache-Control"], "no-cache")
        self.assertEqual(len(list((self.tmp / "gz").glob("*.gz"))), 1)  # same file, same copy
        css = self.get("/assets/style.css", {"Accept-Encoding": "gzip"})
        self.assertEqual((css.mimetype, css.headers["Content-Encoding"]), ("text/css", "gzip"))
        plain = self.get("/assets/app.js")  # a browser that does not take gzip gets the file as it is
        self.assertEqual((plain.status_code, plain.data), (200, src))
        self.assertNotIn("Content-Encoding", plain.headers)

    def test_static_assets(self):
        r = self.get("/assets/icon-192.png")
        self.assertEqual((r.status_code, r.mimetype), (200, "image/png"))
        self.assertEqual(r.data, (ROOT / "assets" / "icon-192.png").read_bytes())
        self.assertEqual(self.get("/assets/icon-192.png", {"If-Modified-Since": "Wed, 01 Jan 2100 00:00:00 GMT"}).status_code, 304)
        f = self.get("/assets/fonts/PirataOne-Regular.ttf")
        self.assertEqual(f.status_code, 200)

    def test_asset_choice(self):
        d = Path(tempfile.mkdtemp())
        (d / "assets").mkdir()
        files = AssetFiles(d)
        for n in ("app.js", "app.min.js"):
            (d / "assets" / n).write_text("x")
        os.utime(d / "assets" / "app.js", (1000000, 1000000))
        os.utime(d / "assets" / "app.min.js", (1000000, 1000000))
        self.assertEqual(files.pick("app.js"), "app.min.js")
        os.utime(d / "assets" / "app.js", (1000500, 1000500))  # source edited more than 2 minutes after the build: plain file
        self.assertEqual((files.pick("app.js"), files.version("app.js")), ("app.js", 1000500))
        os.utime(d / "assets" / "app.js", (1000100, 1000100))  # within the slack
        self.assertEqual(files.pick("app.js"), "app.min.js")
        self.assertEqual(files.pick("style.css"), "style.css")
        self.assertIsNone(files.resolve("../x"))

    def test_pretty_link_parser(self):
        f = PrettyLinks.resolve
        self.assertEqual(f("/u/abc", {}, "GET"), ("/", "abc", ""))
        self.assertEqual(f("/x/y/p/42/", {}, "GET"), ("/x/y/", "", "42"))
        self.assertEqual(f("/u/a b", {}, "GET"), ("/", "", ""))
        self.assertEqual(f("/u/ab", {}, "GET"), ("/", "", ""))  # too short to be a name
        self.assertEqual(f("/u/abc", {"img": "x"}, "GET"), ("", "", ""))
        self.assertEqual(f("/u/abc", {}, "POST"), ("", "", ""))
        self.assertEqual(f("/", {"u": "keep"}, "GET"), ("", "keep", ""))


if __name__ == "__main__":
    unittest.main()
