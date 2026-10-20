#!/usr/bin/env python3
"""Step 3g: reports, appeals, suspend, purge, word filter, stats, backup.   python3 -I tests/test_admin.py -v"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.harness import OfflineCase  # noqa: E402


class AdminTest(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from tests.harness import Browser
        cls.adm = Browser(cls.app)
        cls.adm.me()
        assert cls.adm.post("login", name=cls.ADMIN, pw="adminpass123")[0].status_code == 200
        cls.a, cls.b, cls.c = cls.user("ann_a"), cls.user("ben_a"), cls.user("cy_a")

    def test_admin_only(self):
        for act in ("reports", "bwlist", "astats", "backup", "ipdiag"):
            self.assertEqual(self.a.post(act)[0].status_code, 403, act)
        for act, kw in (("suspend", {"name": "ben_a"}), ("purge", {"name": "ben_a"}), ("bwadd", {"w": "spam"}), ("rfset", {"msg": "x"}), ("appealres", {"id": 1})):
            self.assertEqual(self.a.post(act, **kw)[0].status_code, 403, act)

    def test_moderator_role(self):
        adm = self.adm
        mod, victim, other = self.user("mod_a"), self.user("vic_a"), self.user("mod2_a")
        # a normal account can't see the queue or hand out roles
        self.assertEqual(mod.post("reports")[0].status_code, 403)
        self.assertEqual(mod.post("setrole", name="vic_a", role="mod")[0].status_code, 403)
        self.assertEqual(mod.post("staff")[0].status_code, 403)
        # only admins promote; bad input is refused
        self.assertEqual(adm.post("setrole", name="nobody_a", role="mod")[0].status_code, 404)
        self.assertEqual(adm.post("setrole", name="mod_a", role="boss")[0].status_code, 400)
        self.assertEqual(adm.post("setrole", name=self.ADMIN, role="mod")[0].status_code, 400)
        self.assertEqual(adm.post("setrole", name="mod_a", role="mod")[1], {"ok": 1, "role": "mod"})
        adm.post("setrole", name="mod2_a", role="mod")
        self.assertEqual(self.val("SELECT role FROM users WHERE name='mod_a'"), 1)
        j = adm.post("staff")[1]
        self.assertEqual([x["name"] for x in j["admins"]], [self.ADMIN])
        self.assertEqual({x["name"] for x in j["mods"]}, {"mod_a", "mod2_a"})
        # me() tells the front end
        me = mod.me()["me"]
        self.assertEqual((me["admin"], me["mod"], me["role"]), (False, True, "mod"))
        self.assertEqual(adm.me()["me"]["role"], "admin")
        self.assertEqual(victim.me()["me"]["role"], "user")
        # a moderator works the queue
        victim.post("post", cap="spammy text")
        pid = self.val("SELECT MAX(id) FROM posts")
        self.b.post("report", kind="post", id=pid, why="spam")
        j = mod.post("reports")[1]
        self.assertEqual(j["role"], "mod")
        rid = next(x["id"] for x in j["reports"] if x["kind"] == "post" and x["tid"] == pid)
        self.assertEqual(mod.post("rdel", id=rid)[1], {"ok": 1})
        self.assertIsNone(self.val("SELECT id FROM posts WHERE id=?", pid))
        self.assertIn("deleted post", [x["act"] for x in adm.post("reports")[1]["log"]])
        # moderators are protected from other moderators in the queue
        self.b.post("report", kind="user", to="mod2_a", why="x")
        t = next(x for x in mod.post("reports")[1]["reports"] if x["kind"] == "user" and x["target"]["name"] == "mod2_a")
        self.assertEqual(t["target"]["adm"], 1)
        # suspensions: short only, no bans, never staff
        self.assertEqual(mod.post("suspend", name="vic_a", days=-1)[0].status_code, 403)
        self.assertEqual(mod.post("suspend", name="mod2_a", days=1)[0].status_code, 403)
        self.assertEqual(mod.post("suspend", name=self.ADMIN, days=1)[0].status_code, 400)
        self.assertEqual(mod.post("suspend", name="vic_a", days=365)[1], {"ok": 1})
        left = self.val("SELECT sus FROM users WHERE name='vic_a'") - __import__("time").time()
        self.assertLess(left, 30 * 86400 + 5)
        self.assertEqual(mod.post("suspend", name="vic_a", days=0)[1], {"ok": 1})
        # admin-only tools stay closed to moderators
        for act in ("bwlist", "astats", "backup", "ipdiag", "staff"):
            self.assertEqual(mod.post(act)[0].status_code, 403, act)
        for act, kw in (("purge", {"name": "vic_a"}), ("bwadd", {"w": "spam"}), ("rfset", {"msg": "x"}), ("setrole", {"name": "vic_a", "role": "mod"})):
            self.assertEqual(mod.post(act, **kw)[0].status_code, 403, act)
        # demote
        self.assertEqual(adm.post("setrole", name="mod_a", role="user")[1], {"ok": 1, "role": "user"})
        self.assertEqual(mod.post("reports")[0].status_code, 403)

    def test_report_and_reports(self):
        a, b, adm = self.a, self.b, self.adm
        a.post("post", cap="rude words")
        pid = self.val("SELECT MAX(id) FROM posts")
        self.assertEqual(a.post("report", kind="post", id=pid, why="x")[0].status_code, 400)  # own content
        self.assertEqual(b.post("report", kind="nope")[0].status_code, 400)
        self.assertEqual(b.post("report", kind="post", id=999999)[0].status_code, 404)
        self.assertEqual(b.post("report", kind="post", id=pid, why="  rude ")[1], {"ok": 1})
        b.post("report", kind="post", id=pid, why="again")  # duplicate ignored
        self.assertEqual(self.val("SELECT COUNT(*) FROM reports WHERE kind='post' AND tid=?", pid), 1)
        self.assertEqual(b.post("report", kind="user", to="ann_a")[1], {"ok": 1})
        j = adm.post("reports")[1]
        r = next(x for x in j["reports"] if x["kind"] == "post" and x["tid"] == pid)
        self.assertEqual((r["why"], r["rname"], r["auto"], r["target"]["name"], r["target"]["cap"], r["target"]["n"], r["target"]["adm"]),
                         ("rude", "ben_a", 0, "ann_a", "rude words", 2, 0))
        self.assertEqual(set(j), {"reports", "log", "appeals", "role"})
        # ask reports hide the question
        self.c.post("ask", to="ann_a", txt="mean question")
        aid = self.val("SELECT MAX(id) FROM asks")
        a.post("report", kind="ask", id=aid, why="mean")
        self.assertEqual(self.val("SELECT hid FROM asks WHERE id=?", aid), 1)
        self.assertEqual(self.sql("SELECT name FROM users WHERE id=(SELECT frm FROM asks WHERE id=?)", aid)[0]["name"], "cy_a")

    def test_suspend_appeal(self):
        b, adm = self.b, self.adm
        self.assertEqual(adm.post("suspend", name=self.ADMIN)[0].status_code, 400)
        self.assertEqual(adm.post("suspend", name="nobody_a")[0].status_code, 404)
        self.assertEqual(b.post("appeal", txt="x" * 30)[0].status_code, 400)  # not suspended
        self.assertEqual(adm.post("suspend", name="ben_a", days=2)[1], {"ok": 1})
        self.assertGreater(self.val("SELECT sus FROM users WHERE name='ben_a'"), 0)
        self.assertEqual(b.post("post", cap="blocked")[0].status_code, 403)
        self.assertEqual(b.post("appeal", txt="short")[0].status_code, 400)
        self.assertEqual(b.post("appeal", txt="I did not mean it, please lift this.")[1], {"ok": 1})
        self.assertEqual(b.post("appeal", txt="I did not mean it, please lift this.")[0].status_code, 400)  # one waiting
        st = b.get("a=appealst")[1]
        self.assertEqual((st["appeal"]["st"], st["next"]), (0, 0))
        apps = adm.post("reports")[1]["appeals"]
        self.assertEqual([x["name"] for x in apps], ["ben_a"])
        self.assertEqual(adm.post("appealres", id=apps[0]["id"], note="no")[1], {"ok": 1})  # denied
        self.assertEqual(adm.post("appealres", id=apps[0]["id"])[0].status_code, 404)
        st = b.get("a=appealst")[1]
        self.assertEqual((st["appeal"]["st"], st["appeal"]["note"]), (2, "no"))
        self.assertEqual(b.post("appeal", txt="I did not mean it, please lift this.")[0].status_code, 400)  # wait a week
        self.db.execute("UPDATE appeals SET rts=1")
        self.assertEqual(b.post("appeal", txt="Second try, I am really sorry about it.")[1], {"ok": 1})
        aid = self.val("SELECT MAX(id) FROM appeals")
        self.assertEqual(adm.post("appealres", id=aid, ok=1)[1], {"ok": 1})
        self.assertEqual(self.val("SELECT sus FROM users WHERE name='ben_a'"), 0)
        adm.post("suspend", name="ben_a", days=-1)
        self.assertEqual(self.val("SELECT sus FROM users WHERE name='ben_a'"), 2147483647)
        adm.post("suspend", name="ben_a", days=0)
        self.assertEqual(self.val("SELECT sus FROM users WHERE name='ben_a'"), 0)
        self.assertIn("lifted suspension on", [x["act"] for x in adm.post("reports")[1]["log"]])

    def test_purge(self):
        adm, c = self.adm, self.c
        c2 = self.user("spam_a")
        c2.post("post", cap="buy stuff")
        c2.post("comment", pid=self.val("SELECT MAX(id) FROM posts"), txt="spam")
        self.assertEqual(adm.post("purge", name=self.ADMIN)[0].status_code, 400)
        j = adm.post("purge", name="spam_a")[1]
        self.assertEqual((j["ok"], j["posts"], j["comments"]), (1, 1, 1))
        self.assertEqual(self.val("SELECT COUNT(*) FROM posts WHERE uid=?", self.uid("spam_a")), 0)
        self.assertEqual(self.val("SELECT sus FROM users WHERE name='spam_a'"), 2147483647)

    def test_words_and_site(self):
        adm = self.adm
        self.assertEqual(adm.post("bwadd", w="x")[0].status_code, 400)
        self.assertEqual(adm.post("bwadd", w="  Bad   WORD ", hold=1)[1], {"ok": 1})
        self.assertEqual(adm.post("bwlist")[1]["words"], [{"w": "bad word", "hold": 1}])
        adm.post("bwadd", w="bad word")
        self.assertEqual(adm.post("bwlist")[1]["words"], [{"w": "bad word", "hold": 0}])
        self.a.post("post", cap="this has a bad word in it")
        self.assertEqual(self.val("SELECT COUNT(*) FROM reports WHERE uid=0"), 1)
        self.assertEqual(adm.post("bwdel", w="BAD WORD")[1], {"ok": 1})
        self.assertEqual(adm.post("bwlist")[1]["words"], [])
        j = adm.post("rfset", msg="  hi\x01there ", go=1)[1]
        self.assertEqual(j["msg"], "hithere")
        self.assertRegex(j["v"], r"^\d+-[0-9a-f]{6}$")
        self.assertEqual(self.a.get("a=rfstat")[1], j)

    def test_stats_backup_ip_suggest(self):
        adm, a = self.adm, self.a
        j = adm.post("astats")[1]
        self.assertGreaterEqual(j["users"], 4)
        self.assertEqual((len(j["sg"]), len(j["pg"])), (14, 14))
        self.assertGreaterEqual(j["sg"][13], 1)  # the admin signed up today (the others are back-dated by the test harness)
        self.assertGreater(j["db"], 0)
        r = adm.c.post("/?a=backup", headers={"X-CSRF": adm.csrf, "X-Real-IP": adm.ip})
        self.assertEqual(r.status_code, 200)
        self.assertIn("masque-backup-", r.headers["Content-Disposition"])
        p = Path(tempfile.mkdtemp()) / "b.db"
        p.write_bytes(r.data)
        self.assertGreater(sqlite3.connect(p).execute("SELECT COUNT(*) FROM users").fetchone()[0], 3)
        self.assertEqual(list((Path(self.cfg.data_dir) / "backups").glob("dl-*")), [])  # the temporary copy is removed
        d = adm.post("ipdiag")[1]
        self.assertIn("ip_the_app_uses", d)
        self.assertEqual(d["headers_received"]["X-Real-IP"], adm.ip)
        names = [x["name"] for x in a.post("suggest")[1]["list"]]
        self.assertNotIn("ann_a", names)
        self.assertIn("cy_a", names)


if __name__ == "__main__":
    unittest.main()
