#!/usr/bin/env python3
"""The user and session layer: me(), need(), admin, device tokens, the maintenance gate and the session file.

    python3 -I tests/test_users.py -v        (offline: needs only flask, bcrypt, cryptography)

People sign up and in through the real Python app; throwaway actions (whoami, needme, ...) are added on a second app
that shares the same database and session folder, so the layer can be asked about the same session files.
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from masque.actions import Action, ActionRegistry, Reply  # noqa: E402
from masque.app import create_app  # noqa: E402
from masque.php_session import PhpSession  # noqa: E402
from masque.users import MailVault  # noqa: E402
from tests.harness import Browser, OfflineCase  # noqa: E402

ADMIN_PW = "adminpass123"


def make_registry():
    reg = ActionRegistry()

    def add(nm, fn, exempt=False):
        reg.register(type("T_" + nm, (Action,), {"name": nm, "maintenance_exempt": exempt, "handle": lambda self, ctx: fn(ctx)}))

    add("whoami", lambda ctx: Reply({"me": ctx.users.me()}))
    add("whoami_ex", lambda ctx: Reply({"me": ctx.users.me()}), exempt=True)
    add("needme", lambda ctx: Reply({"id": ctx.users.need()["id"]}))
    add("appeal", lambda ctx: Reply({"id": ctx.users.need()["id"]}))   # on the suspended-allowed list
    add("adminonly", lambda ctx: Reply({"id": ctx.users.need_admin()["id"]}))
    return reg


class Layer(OfflineCase):
    counter = 0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_app = create_app(cls.cfg, registry=make_registry())

    # ---- helpers ----
    def signup(self):
        """New account: returns (session id, csrf token, user id)."""
        Layer.counter += 1
        self.db.execute("DELETE FROM rl")  # sign-up is limited to 5 an hour per address
        b = Browser(self.app)
        j = b.signup("user%d" % Layer.counter)
        return b.c.get_cookie("PHPSESSID").value, b.csrf, j["me"]["id"]

    def admin_session(self):
        b = Browser(self.app)
        b.me()
        r, j = b.post("login", name=self.ADMIN, pw=ADMIN_PW)
        self.assertEqual(r.status_code, 200, j)
        return b.c.get_cookie("PHPSESSID").value

    def call(self, name, sid="", csrf=None, post=False, headers=None):
        c = self.test_app.test_client()
        if sid:
            c.set_cookie("PHPSESSID", sid)
        if post:
            return c.post("/?a=" + name, headers={"X-CSRF": csrf or "", **(headers or {})})
        return c.get("/?a=" + name, headers=headers or {})

    def sess(self, sid):
        return PhpSession(sid, self.tmp / "sessions")

    def whoami(self, sid=""):
        return self.call("whoami", sid).get_json()["me"]

    def set_site(self, **kv):
        for k, v in kv.items():
            self.db.execute("INSERT OR REPLACE INTO site(k,v) VALUES(?,?)", (k, v))


class TestMe(Layer):
    def test_signed_out(self):
        self.assertIsNone(self.whoami())

    def test_new_user(self):
        sid, csrf, uid = self.signup()
        m = self.whoami(sid)
        self.assertGreater(m["nl"], 0)
        self.assertEqual((m["id"], m["admin"], m["hasrc"], m["hasmail"], m["newish"], m["mask"]), (uid, False, 1, 0, 1, None))

    def test_admin(self):
        m = self.whoami(self.admin_session())
        self.assertTrue(m["admin"])
        self.assertEqual(m["nl"], 0)

    def test_mask_xpall_and_email_mask(self):
        sid, csrf, uid = self.signup()
        enc = MailVault("test-mail-key-0123456789").encrypt("someone@example.com")
        self.db.execute("UPDATE users SET mail=? WHERE id=?", (enc, uid))
        self.db.execute("INSERT INTO masks(uid,name,bio,avatar,ts) VALUES(?,?,?,?,?)", (uid, "Shade%d" % uid, "héllo ✓", "", 1))
        self.set_site(xpall="1")
        try:
            m = self.whoami(sid)
            self.assertEqual((m["hasmail"], m["mailm"], m["xpall"]), (1, "s***@example.com", 1))
            self.assertEqual(m["mask"], {"name": "Shade%d" % uid, "bio": "héllo ✓", "avatar": ""})
        finally:
            self.db.execute("DELETE FROM site WHERE k='xpall'")

    def test_sv_mismatch_signs_out(self):
        sid, csrf, uid = self.signup()
        self.db.execute("UPDATE users SET sv=sv+1 WHERE id=?", (uid,))
        self.assertIsNone(self.whoami(sid))
        self.assertNotIn("u", self.sess(sid))      # the sign-out was written into the session file

    def test_device_row_removed_signs_out(self):
        sid, csrf, uid = self.signup()
        self.db.execute("DELETE FROM devices WHERE uid=?", (uid,))
        self.assertIsNone(self.whoami(sid))
        s = self.sess(sid)
        self.assertNotIn("u", s)
        self.assertNotIn("d", s)

    def test_device_touch_refreshes_last_seen(self):
        sid, csrf, uid = self.signup()
        self.db.execute("UPDATE devices SET last=? WHERE uid=?", (int(time.time()) - 1000, uid))
        self.assertIsNotNone(self.whoami(sid))
        self.assertLess(time.time() - self.val("SELECT last FROM devices WHERE uid=?", uid), 5)

    def test_missing_device_token_creates_one(self):
        sid, csrf, uid = self.signup()
        s = self.sess(sid)
        s.unset("d")
        s.save()                                   # an old session from before devices existed
        self.assertNotIn("d", self.sess(sid))
        self.assertIsNotNone(self.whoami(sid))
        tok = self.sess(sid).get("d")
        self.assertTrue(tok)
        self.assertEqual(self.val("SELECT uid FROM devices WHERE tok=?", tok), uid)
        self.assertIsNotNone(self.whoami(sid))     # and the new token keeps the session valid

    def test_device_label(self):
        sid, csrf, uid = self.signup()
        s = self.sess(sid)
        s.unset("d")
        s.save()
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit Version/17 Safari/604 CriOS/120"
        self.call("whoami", sid, headers={"User-Agent": ua})
        self.assertEqual(self.val("SELECT label FROM devices WHERE tok=?", self.sess(sid).get("d")), "Chrome on iPhone")


class TestNeed(Layer):
    def test_signed_out_is_401(self):
        r = self.call("needme")
        self.assertEqual((r.status_code, r.get_json()), (401, {"e": "Sign in first."}))

    def test_signed_in_passes(self):
        sid, csrf, uid = self.signup()
        self.assertEqual(self.call("needme", sid).get_json(), {"id": uid})

    def test_suspended_can_read_but_not_write(self):
        sid, csrf, uid = self.signup()
        for sus in (int(time.time()) + 5 * 86400, 2000000000):
            self.db.execute("UPDATE users SET sus=? WHERE id=?", (sus, uid))
            self.assertEqual(self.call("needme", sid).status_code, 200)             # reading is fine
            r = self.call("needme", sid, csrf, post=True)
            self.assertEqual(r.status_code, 403)
            self.assertIn("e", r.get_json())
            self.assertEqual(self.call("appeal", sid, csrf, post=True).status_code, 200)  # allow-listed action
        self.db.execute("UPDATE users SET sus=0 WHERE id=?", (uid,))
        self.assertEqual(self.call("needme", sid, csrf, post=True).status_code, 200)

    def test_post_needs_csrf(self):
        sid, csrf, uid = self.signup()
        r = self.call("needme", sid, "wrong", post=True)
        self.assertEqual((r.status_code, r.get_json()), (403, {"e": "Session expired. Reload the page."}))

    def test_admin_only(self):
        sid, csrf, uid = self.signup()
        r = self.call("adminonly", sid)
        self.assertEqual((r.status_code, r.get_json()), (403, {"e": "Not allowed."}))
        self.assertEqual(self.call("adminonly", self.admin_session()).status_code, 200)


class TestMaintenance(Layer):
    def setUp(self):
        self.set_site(mt="1", mtmsg="Back soon ✓")

    def tearDown(self):
        self.db.execute("DELETE FROM site WHERE k IN ('mt','mtmsg')")

    def test_held_back(self):
        r = self.call("whoami")
        body = r.get_json()
        self.assertEqual((r.status_code, body["mt"], body["msg"]), (503, 1, "Back soon ✓"))

    def test_exempt_action_still_answers(self):
        self.assertEqual(self.call("whoami_ex").status_code, 200)

    def test_admin_passes_and_normal_user_is_held(self):
        self.db.execute("DELETE FROM site WHERE k='mt'")   # sign-ups happen while the site is open
        admin = self.admin_session()
        user, csrf, uid = self.signup()
        self.set_site(mt="1")
        self.assertEqual(self.call("whoami", admin).status_code, 200)
        self.assertEqual(self.call("whoami", user).status_code, 503)


class TestSessionFile(unittest.TestCase):
    SID = "abcdefghijklmnopqrstuv"

    def make(self, **values):
        d = Path(tempfile.mkdtemp())
        s = PhpSession("", d)
        s.start()
        s.sid, s.path = self.SID, d / ("sess_" + self.SID)
        for k, v in values.items():
            s.set(k, v)
        s.save()
        return d

    def test_save_keeps_changes_made_meanwhile(self):
        d = self.make(u=5, c="tok")
        mine = PhpSession(self.SID, d)
        other = PhpSession(self.SID, d)       # another request adds a key after we read the file
        other.set("d", "dev1")
        other.save()
        mine.unset("u")
        mine.set("x", "é✓")
        mine.save()
        self.assertEqual(PhpSession(self.SID, d).data, {"c": "tok", "d": "dev1", "x": "é✓"})

    def test_unchanged_session_is_not_rewritten(self):
        d = self.make(u=5)
        p = d / ("sess_" + self.SID)
        before = p.stat().st_mtime_ns
        time.sleep(0.01)
        PhpSession(self.SID, d).save()
        self.assertEqual(p.stat().st_mtime_ns, before)

    def test_bad_cookie_is_no_session(self):
        self.assertFalse(PhpSession("../../etc/passwd", Path("/tmp")).exists)


if __name__ == "__main__":
    unittest.main()
