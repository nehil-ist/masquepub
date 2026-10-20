#!/usr/bin/env python3
"""Dashboards, users CRUD, posts and comments management.   python3 -I tests/test_manage.py -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.harness import Browser, OfflineCase  # noqa: E402


class ManageTest(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adm = Browser(cls.app)
        cls.adm.me()
        assert cls.adm.post("login", name=cls.ADMIN, pw="adminpass123")[0].status_code == 200
        cls.u1, cls.u2, cls.mod = cls.user("man_u1"), cls.user("man_u2"), cls.user("man_mod")
        cls.adm.post("setrole", name="man_mod", role="mod")

    def test_dashboards(self):
        self.u1.post("post", cap="hello dash")
        j = self.u1.post("mg_dash")[1]
        self.assertEqual((j["role"], j["mine"]["posts"]), ("user", 1))
        self.assertEqual(j["mine"]["recent"][0]["cap"], "hello dash")
        self.assertNotIn("queue", j)
        self.assertNotIn("site", j)
        j = self.mod.post("mg_dash")[1]
        self.assertEqual(j["role"], "mod")
        self.assertEqual(set(j["queue"]), {"reports", "appeals", "held", "suspended"})
        self.assertIsInstance(j["flagged"], list)
        self.assertNotIn("site", j)
        j = self.adm.post("mg_dash")[1]
        self.assertEqual(j["role"], "admin")
        self.assertGreaterEqual(j["site"]["users"], 4)
        self.assertIn("queue", j)
        self.assertLessEqual(len(j["newest"]), 5)
        self.assertEqual(set(j["newest"][0]), {"name", "nick", "avatar", "ts"})

    def test_users_crud(self):
        adm = self.adm
        for act in ("mg_ulist", "mg_uget", "mg_uadd", "mg_uedit", "mg_udel"):  # users and moderators can't manage accounts
            self.assertEqual(self.u1.post(act, name="man_u2")[0].status_code, 403, act)
            self.assertEqual(self.mod.post(act, name="man_u2")[0].status_code, 403, act)
        # Read
        j = adm.post("mg_ulist")[1]
        roles = {u["name"]: u["role"] for u in j["users"]}
        self.assertEqual((roles[self.ADMIN], roles["man_mod"], roles["man_u1"]), ("admin", "mod", "user"))
        mods = adm.post("mg_ulist", role="mod")[1]["users"]
        self.assertIn("man_mod", {u["name"] for u in mods})
        self.assertEqual({u["role"] for u in mods}, {"mod"})
        self.assertEqual([u["name"] for u in adm.post("mg_ulist", q="man_u2")[1]["users"]], ["man_u2"])
        g = adm.post("mg_uget", name="man_u1")[1]
        self.assertEqual((g["role"], g["posts"]), ("user", self.val("SELECT COUNT(*) FROM posts WHERE uid=(SELECT id FROM users WHERE name='man_u1')")))
        self.assertEqual(adm.post("mg_uget", name="nobody_x")[0].status_code, 404)
        # Create
        self.assertEqual(adm.post("mg_uadd", name="x", pw="longenough1")[0].status_code, 400)
        self.assertEqual(adm.post("mg_uadd", name="new_man", pw="short")[0].status_code, 400)
        self.assertEqual(adm.post("mg_uadd", name="new_man", pw="longenough1", role="boss")[0].status_code, 400)
        self.assertEqual(adm.post("mg_uadd", name="man_u1", pw="longenough1")[0].status_code, 409)
        self.assertEqual(adm.post("mg_uadd", name="new_man", pw="longenough1", role="mod")[1]["role"], "mod")
        self.assertEqual(self.val("SELECT role FROM users WHERE name='new_man'"), 1)
        nb = Browser(self.app)
        nb.me()
        self.assertEqual(nb.post("login", name="new_man", pw="longenough1")[0].status_code, 200)
        # Update
        self.assertEqual(adm.post("mg_uedit", name="new_man")[0].status_code, 400)
        self.assertEqual(adm.post("mg_uedit", name=self.ADMIN, bio="x")[0].status_code, 400)
        self.assertEqual(adm.post("mg_uedit", name="new_man", nick="Newbie", bio="hi there", priv=1, role="user")[1]["changed"], ["nick", "bio", "privacy", "role"])
        r = self.sql("SELECT nick,bio,priv,role FROM users WHERE name='new_man'")[0]
        self.assertEqual((r["nick"], r["bio"], r["priv"], r["role"]), ("Newbie", "hi there", 1, 0))
        self.assertEqual(adm.post("mg_uedit", name="new_man", pw="short")[0].status_code, 400)
        self.assertEqual(adm.post("mg_uedit", name="new_man", pw="brandnewpass1")[1]["changed"], ["password"])
        self.assertEqual(nb.post("me")[0].status_code, 200)
        nb2 = Browser(self.app)
        nb2.me()
        self.assertEqual(nb2.post("login", name="new_man", pw="longenough1")[0].status_code, 401)
        self.assertEqual(nb2.post("login", name="new_man", pw="brandnewpass1")[0].status_code, 200)
        # Delete
        self.assertEqual(adm.post("mg_udel", name=self.ADMIN)[0].status_code, 400)
        self.assertEqual(adm.post("mg_udel", name="nobody_x")[0].status_code, 404)
        self.assertEqual(adm.post("mg_udel", name="new_man")[1], {"ok": 1})
        self.assertIsNone(self.val("SELECT id FROM users WHERE name='new_man'"))
        self.assertEqual(adm.post("mg_uadd", name="new_man", pw="longenough1")[0].status_code, 409)  # the name stays reserved
        acts = [x["act"] for x in adm.post("reports")[1]["log"]]
        self.assertIn("deleted account", acts)
        self.assertIn("created account", acts)

    def test_masques_hidden(self):
        adm, u1 = self.adm, self.u1
        if not self.val("SELECT 1 FROM masks WHERE name='ghostly_a'"):
            self.db.execute("INSERT INTO masks(uid,name,ts) VALUES((SELECT id FROM users WHERE name='man_u1'),'ghostly_a',1)")
        r, j = u1.post("post", cap="masked secret words", **{"as": "mask"})
        pid = self.val("SELECT MAX(id) FROM posts")
        if not self.val("SELECT mid FROM posts WHERE id=?", pid):
            self.skipTest("could not make a Masque post here")
        row = next(x for x in adm.post("mg_mposts", q="masked secret")[1]["posts"] if x["id"] == pid)
        self.assertEqual((row["masked"], row["author"]), (1, "Masque"))
        self.assertNotIn("man_u1", str(adm.post("mg_mposts", q="masked secret")[1]))
        g = adm.post("mg_uget", name="man_u1")[1]
        self.assertNotIn("ghostly_a", str(g))
        adm.post("mg_mpdel", id=pid)
        self.assertNotIn("man_u1", str([x for x in adm.post("reports")[1]["log"] if x["act"] == "deleted post by"][:1]))

    def test_posts_comments_crud(self):
        adm, mod, u1, u2 = self.adm, self.mod, self.u1, self.u2
        for act in ("mg_mposts", "mg_mcomments"):
            self.assertEqual(u1.post(act)[0].status_code, 403, act)
        for act in ("mg_mpedit", "mg_mpdel", "mg_mcedit", "mg_mcdel"):
            self.assertEqual(u1.post(act, id=1)[0].status_code, 403, act)
        u1.post("post", cap="needle in haystack")
        pid = self.val("SELECT MAX(id) FROM posts")
        u2.post("comment", pid=pid, txt="a nasty comment")
        cid = self.val("SELECT MAX(id) FROM comments")
        # Read
        j = mod.post("mg_mposts", q="needle")[1]
        self.assertEqual([(p["id"], p["author"]) for p in j["posts"]], [(pid, "man_u1")])
        self.assertEqual(j["posts"][0]["comments"], 1)
        c = mod.post("mg_mcomments", q="nasty")[1]["comments"]
        self.assertEqual((c[0]["id"], c[0]["author"]), (cid, "man_u2"))
        # Update
        self.assertEqual(mod.post("mg_mpedit", id=pid, cap="")[0].status_code, 400)
        self.assertEqual(mod.post("mg_mpedit", id=999999, cap="x")[0].status_code, 404)
        self.assertEqual(mod.post("mg_mpedit", id=pid, cap="needle (edited by staff)")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT cap FROM posts WHERE id=?", pid), "needle (edited by staff)")
        self.assertEqual(mod.post("mg_mcedit", id=cid, txt="")[0].status_code, 400)
        self.assertEqual(mod.post("mg_mcedit", id=cid, txt="a kind comment")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT txt FROM comments WHERE id=?", cid), "a kind comment")
        # a moderator can't touch another moderator's content, an admin can
        self.mod.post("post", cap="mod's own post")
        mpid = self.val("SELECT MAX(id) FROM posts")
        other = self.user("man_mod2")
        adm.post("setrole", name="man_mod2", role="mod")
        self.assertEqual(other.post("mg_mpedit", id=mpid, cap="hijack")[0].status_code, 403)
        self.assertEqual(other.post("mg_mpdel", id=mpid)[0].status_code, 403)
        self.assertEqual(adm.post("mg_mpedit", id=mpid, cap="fixed by admin")[1], {"ok": 1})
        # Delete
        self.assertEqual(mod.post("mg_mcdel", id=cid)[1], {"ok": 1})
        self.assertIsNone(self.val("SELECT id FROM comments WHERE id=?", cid))
        self.assertEqual(mod.post("mg_mpdel", id=pid)[1], {"ok": 1})
        self.assertIsNone(self.val("SELECT id FROM posts WHERE id=?", pid))
        self.assertEqual(mod.post("mg_mpdel", id=pid)[0].status_code, 404)
        acts = [x["act"] for x in adm.post("reports")[1]["log"]]
        self.assertIn("deleted post by", acts)
        self.assertIn("edited comment by", acts)


if __name__ == "__main__":
    unittest.main()
