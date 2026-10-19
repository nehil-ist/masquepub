#!/usr/bin/env python3
"""Step 3c, stickers and two loose ones: stkup, stkfavs, stkfav, mtset, setst.

    python3 -I tests/test_stickers.py -v      (offline checks, then the PHP-versus-Python comparison when php is installed)
"""
import io
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.harness import OfflineCase  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0000003010100c9fe92ef0000000049454e44ae426082")
MINE = {"stkup", "stkfavs", "stkfav", "mtset", "setst"}
BAD = "i:" + "0" * 16


class StickersOffline(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b = cls.user("ann_s"), cls.user("ben_s")
        from tests.harness import Browser
        cls.adm = Browser(cls.app)
        cls.adm.me()
        assert cls.adm.post("login", name=cls.ADMIN, pw="adminpass123")[0].status_code == 200

    def setUp(self):
        for t in ("stkfav", "stkimg", "rl"):
            self.db.execute("DELETE FROM " + t)
        self.db.execute("UPDATE users SET ts=ts-2000000")  # no new-account limits
        self.db.execute("DELETE FROM site WHERE k IN ('mt','mtmsg')")

    def test_python_owns_these_actions(self):
        from masque.actions import load_all
        self.assertEqual(MINE - set(load_all().names()), set())

    def test_upload_and_list(self):
        a = self.a
        self.assertEqual(a.post("stkup")[0].status_code, 400)  # no image
        r = a.post("stkup", files={"img": (io.BytesIO(PNG), "s.png")})
        sid = r[1]["id"]
        self.assertRegex(sid, r"^[a-f0-9]{16}$")
        self.assertEqual(a.post("stkup", files={"img": (io.BytesIO(PNG), "s.png")})[1], {"id": sid})  # same picture = same sticker
        self.assertEqual(a.post("stkfavs")[1], {"items": ["i:" + sid]})
        self.assertEqual(self.b.post("stkfavs")[1], {"items": []})
        self.assertEqual(a.post("stkup", files={"img": (io.BytesIO(b"nope"), "s.png")})[0].status_code, 400)

    def test_favourite_rules(self):
        a = self.a
        self.assertEqual(a.post("stkfav", ref="x", on="1")[0].status_code, 400)
        self.assertEqual(a.post("stkfav", ref="b:" + "a" * 13, on="1")[0].status_code, 400)  # name too long
        self.assertEqual(a.post("stkfav", ref=BAD, on="1")[0].status_code, 404)  # no such picture
        self.assertEqual(a.post("stkfav", ref="b:heart", on="1")[1], {"ok": 1})
        a.post("stkfav", ref="b:heart", on="1")
        self.assertEqual(self.val("SELECT COUNT(*) FROM stkfav"), 1)
        self.assertEqual(a.post("stkfav", ref="b:heart")[1], {"ok": 1})  # no `on` = remove
        self.assertEqual(self.val("SELECT COUNT(*) FROM stkfav"), 0)
        self.assertEqual(a.post("stkfav", ref=BAD)[1], {"ok": 1})  # removing something unknown is fine

    def test_limits(self):
        a, uid = self.a, self.uid("ann_s")
        for i in range(60):
            self.db.execute("INSERT INTO stkimg VALUES(?,?,'png',1,1)", ("%016x" % i, "sha%d" % i))
            self.db.execute("INSERT INTO stkfav VALUES(?,?,?)", (uid, "i:%016x" % i, i))
        self.assertEqual(a.post("stkup", files={"img": (io.BytesIO(PNG), "s.png")})[0].status_code, 400)  # 60 pictures
        self.db.execute("INSERT INTO stkimg VALUES(?,?,'png',1,1)", ("f" * 16, "shaf"))
        self.assertEqual(a.post("stkfav", ref="i:" + "f" * 16, on="1")[0].status_code, 400)
        self.assertEqual(a.post("stkfav", ref="i:%016x" % 3, on="1")[1], {"ok": 1})  # already one of them: fine
        for i in range(40):
            self.db.execute("INSERT INTO stkfav VALUES(?,?,?)", (uid, "b:s%d" % i, 100 + i))
        self.assertEqual(a.post("stkfav", ref="b:more", on="1")[0].status_code, 400)  # 100 in all
        self.assertEqual(self.val("SELECT COUNT(*) FROM stkfav"), 100)

    def test_missing_pictures_are_left_out_and_newest_comes_first(self):
        uid = self.uid("ann_s")
        self.db.execute("INSERT INTO stkimg VALUES('a000000000000000','s1','png',1,1)")
        for ref, ts in (("b:old", 1), ("i:a000000000000000", 2), (BAD, 3), ("b:new", 4)):
            self.db.execute("INSERT INTO stkfav VALUES(?,?,?)", (uid, ref, ts))
        self.assertEqual(self.a.post("stkfavs")[1]["items"], ["b:new", "i:a000000000000000", "b:old"])

    def test_maintenance(self):
        adm = self.adm
        self.assertEqual(self.a.post("mtset", on="1")[0].status_code, 403)
        r = adm.post("mtset", on="1", msg="  back \x01soon  " + "x" * 400)
        self.assertEqual((r[1]["on"], r[1]["msg"][:9], len(r[1]["msg"])), (1, "back soon", 298))  # control chars out, cut at 300, then trimmed
        self.assertEqual(self.a.post("mtstat")[1]["on"], 1)
        self.assertEqual(self.a.post("inbox")[0].status_code, 503)  # held back by the gate
        self.assertEqual(adm.post("mtset", msg="x")[1], {"on": 0, "msg": "x"})  # no `on` = off
        self.assertEqual(self.a.post("inbox")[0].status_code, 200)
        self.assertEqual(self.val("SELECT act FROM alog ORDER BY id DESC LIMIT 1"), "maintenance off")

    def test_setst(self):
        a = self.a
        for v in ("online", "idle", "lurk", "off", ""):
            self.assertEqual(a.post("setst", st=v)[1], {"pst": v})
            self.assertEqual(self.val("SELECT pst FROM users WHERE name='ann_s'"), v)
        self.assertEqual(a.post("setst", st="Online")[0].status_code, 400)  # exact words only
        self.assertEqual(a.post("setst")[1], {"pst": ""})  # a missing value is ""


if __name__ == "__main__":
    unittest.main()
