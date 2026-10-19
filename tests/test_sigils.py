#!/usr/bin/env python3
"""Step 3f: setxp xpall setstatus sgive shopbuy agift gift agrants agive prompt sfreeze.

    python3 -I tests/test_sigils.py -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.harness import Browser, OfflineCase  # noqa: E402

MINE = {"setxp", "xpall", "setstatus", "sgive", "shopbuy", "agift", "gift", "agrants", "agive", "prompt", "sfreeze"}


class SigilsOffline(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b = cls.user("ann_s"), cls.user("ben_s")
        cls.adm = Browser(cls.app)
        cls.adm.me()
        cls.adm.post("login", name=cls.ADMIN, pw="adminpass123")

    def setUp(self):
        for t in ("sigadj", "shop", "ugrants", "gifts", "gitems", "sfreeze", "pstreak", "rl", "badwords", "notifs", "alog", "posts"):
            self.db.execute("DELETE FROM " + t)
        self.db.execute("UPDATE users SET ts=CAST(strftime('%s','now') AS INT)-200000")

    def test_python_owns_these_actions(self):
        from masque.actions import load_all
        self.assertEqual(MINE - set(load_all().names()), set())

    def test_xp_and_status(self):
        self.assertEqual(self.a.post("setxp", on="1")[1]["me"]["xp"], 1)
        self.assertEqual(self.a.post("setxp")[1]["me"]["xp"], 0)
        self.assertEqual(self.a.post("xpall", on="1")[0].status_code, 403)
        self.assertEqual(self.adm.post("xpall", on="1")[1]["me"]["xpall"], 1)
        self.adm.post("xpall")
        self.assertEqual(self.a.post("setstatus", txt="  out   for  tea  ")[1], {"status": "out for tea", "stleft": 86400})
        self.assertEqual(self.a.post("setstatus", txt="")[1], {"status": "", "stleft": 0})
        self.db.execute("INSERT INTO badwords(w,hold) VALUES('rude',0)")
        self.assertEqual(self.a.post("setstatus", txt="so rude")[0].status_code, 400)

    def test_sigils_and_shop(self):
        self.assertEqual(self.a.post("sgive", u="ben_s", n="5")[0].status_code, 403)
        self.assertEqual(self.adm.post("sgive", u="nobody", n="5")[0].status_code, 404)
        self.assertEqual(self.adm.post("sgive", u="ben_s", n="0")[0].status_code, 400)
        base = self.b.post("unl")[1]["sg"]["bal"]
        r = self.adm.post("sgive", u="BEN_S", n="150")[1]
        self.assertEqual((r["name"], r["bal"]), ("ben_s", base + 150))
        self.assertEqual(self.b.post("shopbuy", k="tbg", id="nope")[0].status_code, 404)
        self.assertEqual(self.a.post("shopbuy", k="tbg", id="noir")[0].status_code, 400)  # too poor
        r = self.b.post("shopbuy", k="tbg", id="aurora")[1]
        self.assertEqual((r["bal"], r["gr"]), (base + 150 - 120, ["tbg:aurora"]))
        self.assertEqual(self.b.post("shopbuy", k="tbg", id="aurora")[0].status_code, 400)  # already has it
        self.assertEqual(self.adm.post("sgive", u="ben_s", n="-9999999")[0].status_code, 400)

    def test_gifts_and_grants(self):
        self.assertEqual(self.adm.post("agift", u="ben_s", items="nonsense,tbg:x_void")[1]["n"], 1)
        self.assertEqual(self.adm.post("agift", u="ben_s", items="tbg:x_void")[0].status_code, 400)  # has it now
        self.adm.post("agift", u="ann_s", items="tbp:castle,taf:bats,tbg:nope", msg="  hi\x00there ")
        gid = self.val("SELECT id FROM gifts WHERE uid=?", self.uid("ann_s"))
        g = self.a.post("gift", id=str(gid))[1]
        self.assertEqual((g["msg"], g["opened"], g["items"]), ("hi there", 0, [["tbp", "castle"], ["taf", "bats"]]))
        self.assertEqual(self.b.post("gift", id=str(gid))[0].status_code, 404)
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE kind='gift'"), 2)
        self.assertEqual(self.a.post("agrants", u="ann_s")[0].status_code, 403)
        self.assertEqual(sorted(self.adm.post("agrants", u="ann_s")[1]["gr"]), ["taf:bats", "tbp:castle"])
        self.assertEqual(self.adm.post("agive", u="ann_s", k="tbg", id="x_nova")[0].status_code, 400)
        self.assertEqual(self.adm.post("agive", u="ann_s", k="taf", id="x_nova", on="1")[1]["gr"].count("taf:x_nova"), 1)
        self.assertNotIn("taf:x_nova", self.adm.post("agive", u="ann_s", k="taf", id="x_nova")[1]["gr"])

    def test_prompt_and_freeze(self):
        d = int(self.val("SELECT strftime('%s','now')")) // 86400
        j = self.a.post("prompt")[1]
        self.assertEqual((j["streak"], j["done"], j["fz"], j["day"], j["ms"][0]), (0, 0, None, d, [7, 30]))
        self.assertTrue(j["text"])
        self.assertEqual(self.a.post("sfreeze")[0].status_code, 400)  # nothing to save
        for x in (d - 5, d - 4, d - 3):
            self.db.execute("INSERT INTO pstreak(uid,day) VALUES(?,?)", (self.uid("ann_s"), x))  # then 2 missed days
        self.assertEqual(self.a.post("prompt")[1]["fz"]["n"], 2)
        self.assertEqual(self.a.post("sfreeze")[0].status_code, 400)  # not enough Sigils
        self.adm.post("sgive", u="ann_s", n="500")
        r = self.a.post("sfreeze")[1]
        self.assertEqual((r["n"], r["streak"]), (2, 3))
        self.assertEqual(self.val("SELECT COUNT(*) FROM sfreeze"), 2)


if __name__ == "__main__":
    unittest.main()
