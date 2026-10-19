#!/usr/bin/env python3
"""Step 3b: profiles, follows, friends, blocks, search, presence and chat switches.

    python3 -I tests/test_people.py -v      (offline checks, then the PHP-versus-Python comparison when php is installed)
"""
import shutil
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.harness import OfflineCase  # noqa: E402


class PeopleOffline(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b, cls.c = cls.user("ann_p"), cls.user("ben_p"), cls.user("cy_p")

    def setUp(self):
        for t in ("friends", "follows", "blocks", "notifs", "asks", "messages", "dmstate"):
            self.db.execute("DELETE FROM " + t)

    def test_python_owns_these_actions(self):
        """The parity tests would pass even if PHP answered; this proves Python does."""
        from masque.actions import load_all
        mine = {"profile", "user", "fol", "unfol", "flist", "ufriends", "friends", "here", "find", "fadd", "facc", "frem", "block", "unblock",
                "unl", "unread", "live", "cmute", "cdel"}
        self.assertEqual(mine - set(load_all().names()), set())

    def test_friend_flow(self):
        a, b = self.a, self.b
        self.assertEqual(a.post("fadd", to="ben_p")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE uid=? AND kind='freq'", self.uid("ben_p")), 1)
        self.assertEqual(self.sql("SELECT st FROM friends")[0]["st"], 0)
        self.assertEqual(b.get("a=user&u=ann_p")[1]["u"]["rel"], "got")
        self.assertEqual(a.get("a=user&u=ben_p")[1]["u"]["rel"], "sent")
        self.assertEqual(b.post("facc", to="ann_p")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE uid=? AND kind='facc'", self.uid("ann_p")), 1)
        self.assertEqual(a.get("a=user&u=ben_p")[1]["u"]["rel"], "friends")
        self.assertEqual([(x["name"], x["st"], x["mine"]) for x in a.post("friends")[1]["list"]], [("ben_p", 1, 1)])
        self.assertEqual(a.post("fadd", to="ann_p")[0].status_code, 400)
        self.assertEqual(a.post("fadd", to="nobody_p")[0].status_code, 404)
        self.assertEqual(a.post("frem", to="ben_p")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM friends"), 0)

    def test_follow_rules_and_lists(self):
        a, b, c = self.a, self.b, self.c
        self.assertEqual(a.post("fol", to="cy_p")[1], {"ok": 1})
        a.post("fol", to="cy_p")  # a second follow changes nothing and sends no second alert
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE uid=? AND kind='follow'", self.uid("cy_p")), 1)
        self.assertEqual(a.post("fol", to="ann_p")[0].status_code, 400)
        self.db.execute("UPDATE users SET priv=1 WHERE name='ben_p'")
        self.assertEqual(a.post("fol", to="ben_p")[0].status_code, 403)
        self.assertEqual(a.get("a=flist&u=ben_p")[0].status_code, 403)
        self.db.execute("UPDATE users SET priv=0 WHERE name='ben_p'")
        lst = c.get("a=flist&u=cy_p")[1]["list"]
        self.assertEqual([(x["name"], x["fy"], x["you"]) for x in lst], [("ann_p", 0, 0)])
        self.assertEqual([x["name"] for x in a.get("a=flist&u=ann_p&k=following")[1]["list"]], ["cy_p"])
        self.assertEqual(a.post("unfol", to="cy_p")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM follows"), 0)

    def test_block_cleans_up_and_hides(self):
        a, b = self.a, self.b
        a.post("fadd", to="ben_p")
        b.post("facc", to="ann_p")
        b.post("fol", to="ann_p")
        self.db.execute("INSERT INTO asks(uid,frm,txt,ts) VALUES(?,?,?,?)", (self.uid("ann_p"), self.uid("ben_p"), "q", 1))
        self.assertEqual(a.post("block", to="ben_p")[1], {"ok": 1})
        for t in ("friends", "follows", "asks"):
            self.assertEqual(self.val("SELECT COUNT(*) FROM " + t), 0, t)
        self.assertEqual(b.get("a=user&u=ann_p")[0].status_code, 404)  # the blocker disappears for the blocked
        self.assertEqual(a.get("a=user&u=ben_p")[1]["u"]["blocked"], 1)
        self.assertEqual(b.post("fadd", to="ann_p")[0].status_code, 403)
        self.assertEqual(a.post("block", to="ann_p")[0].status_code, 400)
        a.post("unblock", to="ben_p")
        self.assertEqual(a.get("a=user&u=ben_p")[1]["u"]["blocked"], 0)

    def test_user_profile_fields(self):
        j = self.a.get("a=user&u=ann_p")[1]["u"]
        self.assertNotIn("id", j)
        self.assertNotIn("stx", j)
        self.assertEqual((j["posts"], j["qs"], j["locked"], j["status"], j["stleft"]), (0, 0, 0, "", 0))
        self.assertIn("asks", j)  # only the owner
        self.assertNotIn("asks", self.b.get("a=user&u=ann_p")[1]["u"])
        self.assertEqual(self.a.get("a=user&u=nobody_p")[0].status_code, 404)
        self.db.execute("UPDATE users SET stx='out and about',stts=? WHERE name='ann_p'", (int(time.time()) - 3600,))
        j = self.b.get("a=user&u=ann_p")[1]["u"]
        self.assertEqual(j["status"], "out and about")
        self.assertTrue(80000 < j["stleft"] <= 82800)
        self.db.execute("UPDATE users SET stx='',stts=0 WHERE name='ann_p'")

    def test_find_and_here(self):
        a = self.a
        self.assertEqual(a.get("a=find&q=%20%23%20")[1], {"users": [], "tags": []})
        self.assertEqual([x["name"] for x in a.get("a=find&q=_p")[1]["users"]][:1], ["ann_p"])
        self.assertNotIn("tags", a.get("a=find&q=ann")[1])
        self.assertEqual(a.get("a=find&q=a%25&tg=1")[1]["tags"], [])  # % is searched as a plain character
        self.assertEqual(a.post("here")[1], {"list": []})
        a.post("fadd", to="cy_p")
        self.c.post("facc", to="ann_p")
        self.db.execute("UPDATE users SET la=? WHERE name='cy_p'", (int(time.time()),))
        self.assertEqual([x["name"] for x in a.post("here")[1]["list"]], ["cy_p"])
        self.db.execute("UPDATE users SET pst='off' WHERE name='cy_p'")
        self.assertEqual(a.post("here")[1]["list"], [])
        a.post("frem", to="cy_p")

    def test_ufriends_order_and_privacy(self):
        a, b, c = self.a, self.b, self.c
        for x, y in ((b, "ann_p"), (b, "cy_p")):
            x.post("fadd", to=y)
        a.post("facc", to="ben_p")
        c.post("facc", to="ben_p")
        j = a.get("a=ufriends&u=ben_p")[1]
        self.assertEqual([(x["name"], x["you"], x["mu"]) for x in j["list"]], [("ann_p", 1, 0), ("cy_p", 0, 0)])
        self.assertEqual((j["mutual"], j["self"]), (0, 0))
        self.db.execute("UPDATE users SET priv=1 WHERE name='ben_p'")
        self.assertEqual(self.sql("SELECT 1")[0]["1"], 1)
        outsider = self.user("dee_p")
        self.assertEqual(outsider.get("a=ufriends&u=ben_p")[0].status_code, 403)
        self.assertEqual(b.get("a=ufriends&u=ben_p")[1]["self"], 1)
        self.db.execute("UPDATE users SET priv=0 WHERE name='ben_p'")
        for n in ("ann_p", "cy_p"):
            b.post("frem", to=n)

    def test_profile_names_and_timer(self):
        d = self.user("dee2_p")
        self.assertEqual(d.post("profile", name="dee2_p", nick="  Dee   D ")[0].status_code, 400)  # needs confirm: nick changed
        j = d.post("profile", nick="  Dee   D ", confirm="1")[1]
        self.assertEqual(j["me"]["nick"], "Dee D")
        self.assertGreater(self.val("SELECT ncts FROM users WHERE name='dee2_p'"), 1)  # the account is older than a day, so the change starts the 7-day timer
        r, j = d.post("profile", nick="Other", confirm="1")
        self.assertEqual(r.status_code, 429)
        self.assertIn("again in 7 days", j["e"])
        self.assertEqual(d.post("profile", name="x!")[0].status_code, 400)
        self.assertEqual(d.post("profile", name="ann_p", confirm="1")[0].status_code, 409)
        self.assertEqual(d.post("profile", bio="  hi  ", priv="1", dm="friends", ask="0")[1]["me"]["bio"], "hi")
        row = self.sql("SELECT bio,priv,dm,askon FROM users WHERE name='dee2_p'")[0]
        self.assertEqual((row["bio"], row["priv"], row["dm"], row["askon"]), ("hi", 1, "friends", 0))

    def test_profile_rename_reserves_old_name(self):
        e = self.user("eve_p")
        self.db.execute("UPDATE users SET ts=? WHERE name='eve_p'", (int(time.time()) - 10 * 86400,))
        self.assertEqual(e.post("profile", name="eve_new", confirm="1")[1]["me"]["name"], "eve_new")
        self.assertEqual(self.val("SELECT COUNT(*) FROM oldnames WHERE uid=?", self.uid("eve_new")), 1)
        self.assertEqual(self.a.post("profile", name="eve_p", confirm="1")[0].status_code, 409)  # reserved for her for 30 days
        self.db.execute("UPDATE users SET ncts=1 WHERE name='eve_new'")
        self.assertEqual(e.post("profile", name="eve_p", confirm="1")[1]["me"]["name"], "eve_p")

    def test_profile_themes_and_unlocks(self):
        f = self.user("fay_p")
        self.assertEqual(f.post("profile", tbg="not-a-theme")[0].status_code, 400)
        r, j = f.post("profile", tbg="ocean")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(j["e"], "Still locked. Make 3 posts (0/3).")
        self.assertEqual(f.post("profile", tbg="x_void")[1]["e"], "That theme is admin-only.")
        self.assertEqual(f.post("profile", tbg="aurora")[1]["e"], "Get this one in the Marketplace (Settings).")
        self.assertEqual(f.post("profile", tbg="sage", tfn="")[1]["me"]["tbg"], "sage")  # free ones always work
        self.db.execute("INSERT INTO ugrants(uid,k,id,by,ts) VALUES(?,?,?,?,?)", (self.uid("fay_p"), "tbg", "x_void", 0, 1))
        self.assertEqual(f.post("profile", tbg="x_void")[1]["me"]["tbg"], "x_void")

    def test_profile_private_drops_followers_and_nolinks(self):
        g = self.user("gus_p")
        self.a.post("fol", to="gus_p")
        g.post("profile", priv="1")
        self.assertEqual(self.val("SELECT COUNT(*) FROM follows WHERE b=?", self.uid("gus_p")), 0)

    def test_unl_shape(self):
        j = self.a.post("unl")[1]
        self.assertEqual(set(j), {"st", "req", "admin", "eq", "gr", "ev", "sg", "shop"})
        self.assertEqual(j["req"]["tbg"]["ocean"], {"s": "p", "n": 3, "t": "Make 3 posts"})
        self.assertEqual(j["req"]["tbg"]["aurora"], {"s": "shop", "n": 1, "t": "Get it in the Marketplace"})
        self.assertNotIn("tpl", j["eq"])
        self.assertEqual(j["sg"]["bal"], j["sg"]["earned"])

    def test_unread_live_and_chat_switches(self):
        a, b = self.a, self.b
        self.db.execute("INSERT INTO messages(id,a,b,txt,ts,fm,tm,seen) VALUES(50,?,?,?,?,0,0,0)", (self.uid("ben_p"), self.uid("ann_p"), "hello", int(time.time())))
        n = a.post("unread")[1]
        self.assertEqual((n["n"], n["r"]), (1, 0))
        j = a.get("a=live&k=d&u=ben_p&af=1&inb=1")[1]
        self.assertEqual(j["n"], 1)
        self.assertEqual(j["toast"][0]["txt"], "hello")
        self.assertEqual(j["ty"], 0)
        self.assertEqual(j["st"], "off")
        self.assertIn("ben_p", j["sts"])
        self.assertEqual(self.val("SELECT idl FROM users WHERE name='ann_p'"), 0)
        a.get("a=live&idl=1")
        self.assertEqual(self.val("SELECT idl FROM users WHERE name='ann_p'"), 1)
        self.assertEqual(a.post("cmute", u="ben_p", on="1")[1], {"mu": 1})
        self.assertEqual(a.post("unread")[1]["n"], 0)  # muted chats do not count
        self.assertEqual(a.post("cmute", u="ben_p", on="0")[1], {"mu": 0})
        self.assertEqual(self.val("SELECT COUNT(*) FROM dmstate"), 0)
        self.assertEqual(a.post("cdel", u="ben_p")[1], {"ok": 1})
        self.assertEqual(a.post("unread")[1]["n"], 0)
        self.assertEqual(a.post("cdel", u="nobody_p")[0].status_code, 404)
        self.assertEqual(a.post("cdel", u="ann_p")[0].status_code, 404)  # not yourself
        self.assertEqual(a.get("a=live&k=g&id=999")[1]["ty"], [])


if __name__ == "__main__":
    unittest.main()
