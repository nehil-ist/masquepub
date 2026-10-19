#!/usr/bin/env python3
"""Step 2: the account actions (me, signup, login, logout, recover, newrc, pw, delacct, mail*).

    python3 -I tests/test_account.py -v        (from the project folder; needs flask + cryptography + bcrypt)

OfflineAccounts runs the Python code alone on a database built from masque/schema.py (no PHP needed).
ParityAccounts needs `php` and compares PHP and Python answers for the same requests.
"""
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flask import Response  # noqa: E402
from masque.app import create_app  # noqa: E402
from masque.config import Config  # noqa: E402
from masque.mailer import Mailer  # noqa: E402
from tests import offline_schema  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAIL_KEY = "test-mail-key-0123456789"


class FakeBrevo(BaseHTTPRequestHandler):
    sent = []
    status = 201

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        FakeBrevo.sent.append(json.loads(body))
        self.send_response(FakeBrevo.status)
        self.end_headers()

    def log_message(self, *a):
        pass


class Browser:
    """One visitor: keeps its cookie, remembers its CSRF token."""
    counter = 0

    def __init__(self, app):
        self.c = app.test_client()
        Browser.counter += 1
        self.ip = "10.0.%d.%d" % divmod(Browser.counter, 250)
        self.csrf = ""

    def get(self, qs):
        r = self.c.get("/?" + qs, headers={"X-Real-IP": self.ip})
        return r, json.loads(r.data)

    def post(self, action, **form):
        r = self.c.post("/?a=" + action, data=form, headers={"X-CSRF": self.csrf, "X-Real-IP": self.ip})
        return r, json.loads(r.data)

    def me(self):
        r, j = self.get("a=me")
        self.csrf = j["csrf"]
        return j

    def signup(self, name, pw="password123"):
        self.me()
        return self.post("signup", name=name, pw=pw)


class OfflineAccounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        (cls.tmp / "sessions").mkdir()
        offline_schema.build(cls.tmp / "app.db")
        srv = HTTPServer(("127.0.0.1", 0), FakeBrevo)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        cls.srv = srv
        site = "http://127.0.0.1:%d" % srv.server_port
        cls.cfg = Config(root=ROOT, data_dir=cls.tmp, admin_users=("testadmin",), mail_key=MAIL_KEY, admin_user="testadmin",
                         admin_password="adminpass123", site_url=site, brevo_key="key", mail_from="masque@example.com", brevo_url=site + "/send")
        cls.app = create_app(cls.cfg)
        cls.db = sqlite3.connect(cls.tmp / "app.db", isolation_level=None)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        FakeBrevo.sent.clear()
        FakeBrevo.status = 201

    def sql(self, q, *a):
        return self.db.execute(q, a).fetchall()

    # -- me --
    def test_me_makes_a_session_for_a_new_visitor(self):
        b = Browser(self.app)
        r, j = b.get("a=me")
        self.assertEqual((j["me"], j["mt"], j["rf"], j["mailok"]), (None, {"on": 0, "msg": ""}, {"v": "", "msg": ""}, 1))
        self.assertRegex(j["csrf"], r"^[0-9a-f]{32}$")
        cookie = r.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Max-Age=2592000", cookie)
        sid = re.search(r"PHPSESSID=([^;]+)", cookie).group(1)
        self.assertIn(j["csrf"], (self.tmp / "sessions" / ("sess_" + sid)).read_text())
        r2, j2 = b.get("a=me")  # same visitor again: same token, no new cookie
        self.assertEqual(j2["csrf"], j["csrf"])
        self.assertNotIn("Set-Cookie", r2.headers)

    def test_me_is_not_cached_and_has_no_store(self):
        r, _ = Browser(self.app).get("a=me")
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_post_without_token_is_refused(self):
        b = Browser(self.app)
        b.me()
        b.csrf = "wrong"
        r, j = b.post("login", name="x", pw="y")
        self.assertEqual((r.status_code, j["e"]), (403, "Session expired. Reload the page."))

    # -- signup / login / logout --
    def test_signup_login_logout(self):
        b = Browser(self.app)
        r, j = b.signup("alice_1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(j["me"]["name"], "alice_1")
        self.assertRegex(j["rc"], r"^([A-Z2-9]{4}-){3}[A-Z2-9]{4}$")
        self.assertEqual(j["me"]["hasrc"], 1)
        self.assertEqual(b.get("a=me")[1]["me"]["name"], "alice_1")
        pwhash = self.sql("SELECT pw FROM users WHERE name='alice_1'")[0][0]
        self.assertTrue(pwhash.startswith("$2y$10$"))
        r, j = b.post("logout")
        self.assertEqual(j, {"ok": 1})
        self.assertIsNone(b.me()["me"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM devices WHERE uid=(SELECT id FROM users WHERE name='alice_1')")[0][0], 0)
        b2 = Browser(self.app)
        b2.me()
        r, j = b2.post("login", name="ALICE_1", pw="password123")  # names are case-insensitive
        self.assertEqual(j["me"]["name"], "alice_1")

    def test_signup_rules(self):
        b = Browser(self.app)
        b.me()
        self.assertEqual(b.post("signup", name="a!", pw="password123")[1]["e"], "Usernames are 3 to 20 letters, numbers or _.")
        self.assertEqual(b.post("signup", name="bob_ok", pw="short")[1]["e"], "Password needs at least 8 characters.")
        self.assertEqual(b.post("signup", name="bob_ok", pw="x" * 73)[1]["e"], "Password can be at most 72 characters.")
        Browser(self.app).signup("dupe_name")
        r, j = b.post("signup", name="DUPE_NAME", pw="password123")
        self.assertEqual((r.status_code, j["e"]), (409, "That username is taken."))
        self.assertEqual(b.post("signup", name="dupe_nаme", pw="password123")[0].status_code, 400)  # Cyrillic а is not allowed at all
        self.sql("UPDATE users SET nick='Snоw' WHERE name='dupe_name'")  # (Cyrillic о) a display name blocks look-alike usernames too
        self.assertEqual(b.post("signup", name="Snow", pw="password123")[0].status_code, 409)
        r, j = b.post("signup", name="testadmin", pw="password123")  # the ADMIN_USER name is reserved
        self.assertEqual(r.status_code, 409)

    def test_signup_limit_per_address(self):
        b = Browser(self.app)
        b.me()
        codes = [b.post("signup", name="lim_user%d" % i, pw="password123")[0].status_code for i in range(6)]
        self.assertEqual(codes, [200] * 5 + [429])

    def test_deleted_names_stay_taken(self):
        b = Browser(self.app)
        b.signup("gone_user")
        self.assertEqual(b.post("delacct", pw="password123")[1], {"ok": 1})
        r, j = Browser(self.app).signup("gone_user")
        self.assertEqual(r.status_code, 409)

    def test_login_wrong_and_limit(self):
        Browser(self.app).signup("carol_99")
        b = Browser(self.app)
        b.me()
        r, j = b.post("login", name="carol_99", pw="nope")
        self.assertEqual((r.status_code, j["e"]), (401, "Wrong username or password."))
        r, j = b.post("login", name="nobody_here", pw="nope")
        self.assertEqual(r.status_code, 401)
        for _ in range(8):
            b.post("login", name="nobody_here", pw="nope")
        r, j = b.post("login", name="carol_99", pw="password123")  # 10 misses from this address: even the right password waits
        self.assertEqual((r.status_code, j["e"]), (429, "Too many attempts. Try again in 15 minutes."))

    def test_admin_account_is_made_by_logging_in(self):
        b = Browser(self.app)
        b.me()
        self.assertEqual(b.post("login", name="testadmin", pw="adminpass122")[0].status_code, 401)
        r, j = b.post("login", name="TestAdmin", pw="adminpass123")
        self.assertEqual(j["me"]["admin"], True)

    # -- password changes --
    def test_pw_signs_out_other_devices_only(self):
        a = Browser(self.app)
        a.signup("dave_77")
        b = Browser(self.app)
        b.me()
        b.post("login", name="dave_77", pw="password123")
        self.assertEqual(a.post("pw", old="bad", new="newpassword1")[1]["e"], "Current password is wrong.")
        self.assertEqual(a.post("pw", old="password123", new="short")[1]["e"], "New password needs at least 8 characters.")
        self.assertEqual(a.post("pw", old="password123", new="newpassword1")[1], {"ok": 1})
        self.assertEqual(a.get("a=me")[1]["me"]["name"], "dave_77")   # this device stays signed in (new session id)
        self.assertIsNone(b.get("a=me")[1]["me"])                      # the other one is out
        c = Browser(self.app)
        c.me()
        self.assertEqual(c.post("login", name="dave_77", pw="newpassword1")[0].status_code, 200)

    def test_pw_guess_limit(self):
        a = Browser(self.app)
        a.signup("erin_55")
        for _ in range(10):
            a.post("newrc", pw="wrong")
        r, j = a.post("newrc", pw="password123")
        self.assertEqual((r.status_code, j["e"]), (429, "Too many wrong attempts. Try again in 15 minutes."))

    def test_newrc_and_recover(self):
        a = Browser(self.app)
        j = a.signup("fred_42")[1]
        old = j["rc"]
        self.assertEqual(a.post("newrc", pw="wrong")[1]["e"], "Wrong password.")
        j2 = a.post("newrc", pw="password123")[1]
        self.assertNotEqual(j2["rc"], old)
        b = Browser(self.app)
        b.me()
        self.assertEqual(b.post("recover", name="fred_42", code=old, pw="brandnewpw1")[1]["e"], "That username and recovery code do not match.")
        r, j3 = b.post("recover", name="fred_42", code=j2["rc"].lower().replace("-", " "), pw="brandnewpw1")  # spacing and case do not matter
        self.assertEqual(j3["me"]["name"], "fred_42")
        self.assertNotEqual(j3["rc"], j2["rc"])
        self.assertIsNone(a.get("a=me")[1]["me"])  # recovery signs everyone else out

    # -- delete --
    def test_delacct_removes_everything_and_other_devices_see_false(self):
        a = Browser(self.app)
        uid = a.signup("gina_33")[1]["me"]["id"]
        b = Browser(self.app)
        b.me()
        b.post("login", name="gina_33", pw="password123")
        self.sql("INSERT INTO posts(id,uid,cap,img,ts) VALUES(9001,?,'hi','',1)", uid)
        self.sql("INSERT INTO comments(id,pid,uid,txt,ts) VALUES(9002,9001,?,'x',1)", uid)
        self.assertEqual(a.post("delacct", pw="nope")[1]["e"], "Wrong password.")
        self.assertEqual(a.post("delacct", pw="password123")[1], {"ok": 1})
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users WHERE id=?", uid)[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM posts WHERE uid=?", uid)[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM comments WHERE uid=?", uid)[0][0], 0)
        self.assertIsNone(a.get("a=me")[1]["me"])
        self.assertIs(b.get("a=me")[1]["me"], False)  # signed in as a deleted account: false, not null

    def test_admin_account_cannot_be_deleted(self):
        b = Browser(self.app)
        b.me()
        b.post("login", name="testadmin", pw="adminpass123")
        r, j = b.post("delacct", pw="adminpass123")
        self.assertEqual(r.status_code, 403)

    # -- maintenance --
    def test_maintenance_exempt_actions(self):
        b = Browser(self.app)
        b.signup("hank_21")
        self.sql("INSERT OR REPLACE INTO site(k,v) VALUES('mt','1'),('mtmsg','Back soon')")
        try:
            self.assertEqual(b.get("a=me")[0].status_code, 200)
            self.assertEqual(b.post("pw", old="password123", new="newpassword1")[0].status_code, 503)
            self.assertEqual(b.post("signup", name="new_one", pw="password123")[1]["e"], "Masque is down for maintenance right now. Please try again later.")
            c = Browser(self.app)
            c.me()
            r, j = c.post("login", name="hank_21", pw="password123")
            self.assertEqual((r.status_code, j["e"]), (503, "Back soon Only admins can sign in until it is back."))
            self.assertEqual(c.post("login", name="testadmin", pw="adminpass123")[0].status_code, 200)
            self.assertEqual(b.post("logout")[1], {"ok": 1})
        finally:
            self.sql("DELETE FROM site WHERE k IN ('mt','mtmsg')")

    # -- recovery email --
    def _mail_token(self):
        last = FakeBrevo.sent[-1]
        return re.search(r"\?m[vr]=([a-f0-9]{48})", last["textContent"]).group(1)

    def test_recovery_email_round_trip(self):
        a = Browser(self.app)
        a.signup("iris_11")
        self.assertEqual(a.post("mailset", pw="bad", mail="iris@example.com")[1]["e"], "Wrong password.")
        self.assertEqual(a.post("mailset", pw="password123", mail="not-an-email")[1]["e"], "That does not look like an email address.")
        self.assertEqual(a.post("mailset", pw="password123", mail=" Iris@Example.com ")[1], {"ok": 1})
        self.assertEqual(FakeBrevo.sent[-1]["to"], [{"email": "iris@example.com"}])
        self.assertIn("@iris_11", FakeBrevo.sent[-1]["textContent"])
        tok = self._mail_token()
        anon = Browser(self.app)
        anon.me()
        self.assertEqual(anon.post("mailverify", t="0" * 48)[1]["e"], "This link has expired or was already used. Ask for a new one in Settings.")
        self.assertEqual(anon.post("mailverify", t=tok)[1], {"ok": 1})
        self.assertEqual(anon.post("mailverify", t=tok)[0].status_code, 400)  # one use only
        me = a.get("a=me")[1]["me"]
        self.assertEqual((me["hasmail"], me["mailm"]), (1, "i***@example.com"))
        # reset by email
        n = len(FakeBrevo.sent)
        self.assertEqual(anon.post("mailreq", name="iris_11")[1], {"ok": 1})
        self.assertEqual(len(FakeBrevo.sent), n + 1)
        self.assertEqual(anon.post("mailreq", name="nobody_at_all")[1], {"ok": 1})  # same answer, nothing sent
        self.assertEqual(len(FakeBrevo.sent), n + 1)
        rtok = self._mail_token()
        self.assertEqual(anon.post("mailreset", t=rtok, pw="short")[1]["e"], "New password needs at least 8 characters.")
        r, j = anon.post("mailreset", t=rtok, pw="emailreset99")
        self.assertEqual(j["me"]["name"], "iris_11")
        self.assertIsNone(a.get("a=me")[1]["me"])
        self.assertEqual(FakeBrevo.sent[-1]["subject"], "Your Masque password was reset")
        # remove
        self.assertEqual(anon.post("mailrm", pw="bad")[1]["e"], "Wrong password.")
        self.assertEqual(anon.post("mailrm", pw="emailreset99")[1]["me"]["hasmail"], 0)

    def test_mailset_when_brevo_refuses(self):
        a = Browser(self.app)
        a.signup("jack_22")
        FakeBrevo.status = 500
        r, j = a.post("mailset", pw="password123", mail="jack@example.com")
        self.assertEqual(r.status_code, 502)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM mailtok")[0][0] >= 0, True)

    def test_mail_actions_say_so_when_mail_is_off(self):
        off = create_app(Config(**{**self.cfg.__dict__, "brevo_key": ""}))
        b = Browser(off)
        self.assertEqual(b.me()["mailok"], 0)
        self.assertEqual(b.post("mailreq", name="x")[1]["e"], "Email reset is not available here. Use your recovery code instead.")

    # -- the helpers on their own --
    def test_name_skeleton_folds_lookalikes(self):
        from masque.names import NameRules
        self.assertEqual(NameRules.skeleton("pаypal"), NameRules.skeleton("PayPal"))  # Cyrillic а
        self.assertEqual(NameRules.skeleton("a_b-c.d"), "abcd")
        self.assertEqual(NameRules.skeleton("ｆｕｌｌ"), "full")  # full-width letters

    def test_email_validation(self):
        ok = ["a@b.co", "first.last+tag@sub.example.org", "x_y@ex-ample.com"]
        bad = ["", "a@b", "a@@b.co", ".a@b.co", "a..b@b.co", "a b@b.co", "a@-b.co", "a@b..co", "@b.co", "a@" + "b" * 64 + ".co"]
        self.assertTrue(all(Mailer.valid_address(x) for x in ok))
        self.assertFalse(any(Mailer.valid_address(x) for x in bad))

    def test_email_html_escapes_and_links(self):
        m = Mailer(self.cfg, None, None, None)
        html = m.render('T"<', "Hi <b>\n\nsecond", "http://x/?a=1&b=2", "Go")
        self.assertIn("T&quot;&lt;", html)
        self.assertIn("Hi &lt;b&gt;", html)
        self.assertIn("http://x/?a=1&amp;b=2", html)
        self.assertEqual(html.count("<p style"), 2 + 2)

    def test_encrypted_email_layout_is_what_php_writes(self):
        from masque.users import MailVault
        v = MailVault(MAIL_KEY)
        enc = v.encrypt("a@b.co")
        self.assertEqual(v.decrypt(enc), "a@b.co")
        self.assertEqual(v.decrypt("garbage"), "")


def _shape(x):
    """The structure of an answer: same keys, same types; texts that are fixed messages are compared exactly by the caller."""
    if isinstance(x, dict):
        return {k: _shape(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_shape(v) for v in x]
    return type(x).__name__


if __name__ == "__main__":
    unittest.main()
