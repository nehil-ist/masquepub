#!/usr/bin/env python3
"""Step 3c, groups part 1: gcreate, ginbox, gthread, gsend, gedit, gdel, gadd (and gopen, a gift action).

    python3 -I tests/test_groups.py -v      (offline checks, then the PHP-versus-Python comparison when php is installed)
"""
import io
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.harness import OfflineCase  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0000003010100c9fe92ef0000000049454e44ae426082")
MINE = {"gcreate", "ginbox", "gthread", "gsend", "gedit", "gdel", "gadd", "gopen"}


class GroupsOffline(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b, cls.c, cls.d = cls.user("ann_g"), cls.user("ben_g"), cls.user("cy_g"), cls.user("dee_g")

    def setUp(self):
        for t in ("gchats", "gmembers", "gmessages", "gevents", "ginvites", "gmasks", "mreact", "friends", "blocks", "rl", "typing", "masks", "gifts"):
            self.db.execute("DELETE FROM " + t)
        self.db.execute("UPDATE users SET ts=ts-2000000")  # no new-account limits
        for x, y in (("ann_g", "ben_g"), ("ann_g", "cy_g"), ("ann_g", "dee_g")):
            self.db.execute("INSERT INTO friends(a,b,st) VALUES(?,?,1)", (self.uid(x), self.uid(y)))

    def group(self, members="ben_g,cy_g", name="Crew"):
        return self.a.post("gcreate", name=name, members=members)[1]["id"]

    def test_python_owns_these_actions(self):
        from masque.actions import load_all
        self.assertEqual(MINE - set(load_all().names()), set())

    def test_create_rules(self):
        a = self.a
        self.assertEqual(a.post("gcreate", name="", members="ben_g")[0].status_code, 400)
        self.assertEqual(a.post("gcreate", name="X", members="")[0].status_code, 400)
        self.assertEqual(a.post("gcreate", name="X", members="ann_g,nobody_g,0")[0].status_code, 400)  # self / unknown
        self.db.execute("UPDATE friends SET st=0 WHERE b=?", (self.uid("ben_g"),))
        self.assertEqual(a.post("gcreate", name="X", members="ben_g")[0].status_code, 400)  # only a pending friend request
        self.db.execute("UPDATE friends SET st=1 WHERE b=?", (self.uid("ben_g"),))
        self.db.execute("INSERT INTO blocks VALUES(?,?)", (self.uid("cy_g"), self.uid("dee_g")))  # two friends who blocked each other
        g = a.post("gcreate", name="  " + "n" * 50, members="ben_g,cy_g,dee_g,ben_g")[1]["id"]
        self.assertEqual(sorted(r[0] for r in self.db.execute("SELECT uid FROM gmembers WHERE gid=?", (g,))),
                         sorted([self.uid("ann_g"), self.uid("ben_g"), self.uid("cy_g")]))  # dee_g left out
        self.assertEqual(self.val("SELECT name FROM gchats WHERE id=?", g), "n" * 38)  # cut at 40 characters, then trimmed
        self.assertEqual(self.val("SELECT owner FROM gchats WHERE id=?", g), self.uid("ann_g"))

    def test_send_inbox_thread(self):
        a, b, c = self.a, self.b, self.c
        g = self.group()
        self.assertEqual(c.post("gsend", gid=str(g), txt="  hi all ")[1], {"ok": 1})
        self.assertEqual(a.post("gsend", gid=str(g), txt="")[0].status_code, 400)
        self.assertEqual(a.post("gsend", gid="999", txt="x")[0].status_code, 404)
        self.assertEqual(self.d.post("gsend", gid=str(g), txt="x")[0].status_code, 404)  # not a member
        self.assertEqual(a.post("gsend", gid=str(g), txt="re", rp="999")[0].status_code, 400)
        a.post("gsend", gid=str(g), txt="img", files={"img": (io.BytesIO(PNG), "p.png")})
        ib = b.post("ginbox")[1]["groups"]
        self.assertEqual([(x["name"], x["txt"], x["un"], x["mine"], x["mu"], x["gp"]) for x in ib], [("Crew", "img", 2, 0, 0, 0)])
        self.assertEqual(ib[0]["who"], "ann_g")
        j = b.get("a=gthread&id=%d" % g)[1]
        self.assertEqual([(x["name"], x["txt"], x["mine"], x["co"], x["rx"], x["rq"]) for x in j["msgs"]], [("cy_g", "hi all", 0, 0, [], None), ("ann_g", "img", 0, 1, [], None)])
        self.assertEqual((j["g"]["name"], j["g"]["own"]), ("Crew", 0))
        self.assertEqual([m["name"] for m in j["members"]], ["ann_g", "ben_g", "cy_g"])
        self.assertEqual((j["gm"], j["seen"]), ({"has": 0, "in": 0, "only": 0, "name": "", "avatar": ""}, {"mid": 0, "by": []}))
        self.assertEqual(b.post("ginbox")[1]["groups"][0]["un"], 0)  # opening it marked it read
        a.get("a=gthread&id=%d" % g)
        self.assertEqual(self.a.get("a=gthread&id=%d" % g)[1]["seen"], {"mid": 2, "by": ["ben_g"]})  # only ben has read up to her last message
        self.assertEqual(self.d.get("a=gthread&id=%d" % g)[0].status_code, 404)
        self.assertEqual(a.get("a=gthread&id=%d&around=1" % g)[0].status_code, 200)

    def test_reply_and_masque_sender(self):
        a, b = self.a, self.b
        g = self.group()
        a.post("gsend", gid=str(g), txt="first")
        mid = self.val("SELECT id FROM gmessages")
        b.post("gsend", gid=str(g), txt="answer", rp=str(mid))
        self.assertEqual(a.get("a=gthread&id=%d" % g)[1]["msgs"][1]["rq"]["t"], "first")
        self.assertEqual(b.post("gsend", gid=str(g), txt="x", **{"as": "mask"})[0].status_code, 400)  # no Masque in this group
        self.db.execute("INSERT INTO masks(uid,name,ts) VALUES(?,?,1)", (self.uid("ben_g"), "Ghost"))
        self.db.execute("INSERT INTO gmasks(gid,uid) VALUES(?,?)", (g, self.uid("ben_g")))
        b.post("gsend", gid=str(g), txt="boo", **{"as": "mask"})
        last = a.get("a=gthread&id=%d" % g)[1]["msgs"][-1]
        self.assertEqual((last["name"], last["nick"], last["mk"]), ("Ghost", "", 1))
        self.assertEqual(b.get("a=gthread&id=%d" % g)[1]["gm"], {"has": 1, "in": 1, "only": 0, "name": "Ghost", "avatar": ""})

    def test_everyone_limit_and_mentions(self):
        a = self.a
        g = self.group()
        self.assertEqual(a.post("gsend", gid=str(g), txt="hey @ben_g")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE kind='gment' AND uid=?", self.uid("ben_g")), 1)
        self.assertEqual(a.post("gsend", gid=str(g), txt="@everyone look")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE kind='gall'"), 2)
        self.assertEqual(a.post("gsend", gid=str(g), txt="@everyone again")[0].status_code, 429)

    def test_edit_and_delete(self):
        a, b = self.a, self.b
        g = self.group()
        a.post("gsend", gid=str(g), txt="one", files={"img": (io.BytesIO(PNG), "p.png")})
        mid = self.val("SELECT id FROM gmessages")
        img = self.val("SELECT img FROM gmessages")
        r = a.post("gedit", id=str(mid), txt="  one!  ")[1]
        self.assertEqual((r["txt"], r["ed"] > 0), ("one!", True))
        self.assertEqual(a.post("gedit", id=str(mid), txt="")[1]["txt"], "")  # a photo keeps it from being empty
        self.assertEqual(b.post("gedit", id=str(mid), txt="x")[0].status_code, 404)  # not yours
        self.assertEqual(a.post("gedit", id="999", txt="x")[0].status_code, 404)
        self.db.execute("INSERT INTO gmessages(gid,uid,txt,ts,img) VALUES(?,?,'plain',1,'')", (g, self.uid("ann_g")))
        self.assertEqual(a.post("gedit", id=str(self.val("SELECT MAX(id) FROM gmessages")), txt="")[0].status_code, 400)
        self.db.execute("INSERT INTO mreact(k,mid,uid,e) VALUES('g',?,?,'x')", (mid, self.uid("ben_g")))
        self.assertEqual(b.post("gdel", id=str(mid))[1], {"ok": 1})  # someone else's: nothing happens
        self.assertEqual(self.val("SELECT COUNT(*) FROM gmessages WHERE id=?", mid), 1)
        self.assertEqual(a.post("gdel", id=str(mid))[1], {"ok": 1})
        self.assertEqual((self.val("SELECT COUNT(*) FROM gmessages WHERE id=?", mid), self.val("SELECT COUNT(*) FROM mreact")), (0, 0))
        self.assertFalse((Path(self.cfg.data_dir) / "up" / img).exists())

    def test_add_rules(self):
        a, b = self.a, self.b
        g = self.group(members="ben_g")
        self.assertEqual(a.post("gadd", gid="999", members="cy_g")[0].status_code, 404)
        self.assertEqual(self.c.post("gadd", gid=str(g), members="dee_g")[0].status_code, 404)  # not a member
        self.assertEqual(a.post("gadd", gid=str(g), members="ben_g,nobody_g,ann_g")[0].status_code, 400)  # already in / unknown
        self.assertEqual(a.post("gadd", gid=str(g), members="cy_g,cy_g,dee_g")[1], {"added": 2})
        self.assertEqual(a.post("gadd", gid=str(g), members="cy_g")[0].status_code, 400)  # already invited
        self.assertEqual(self.val("SELECT COUNT(*) FROM ginvites WHERE gid=? AND inv=?", g, self.uid("ann_g")), 2)
        self.assertEqual(self.val("SELECT COUNT(*) FROM gevents WHERE kind='invite'"), 2)
        self.assertEqual(b.post("gadd", gid=str(g), members="cy_g")[0].status_code, 400)  # ben is not friends with cy
        self.assertEqual(a.get("a=gthread&id=%d" % g)[1]["events"][0]["kind"], "invite")

    def test_add_stops_at_31_and_respects_blocks(self):
        a = self.a
        g = self.group(members="ben_g")
        self.db.execute("INSERT INTO blocks VALUES(?,?)", (self.uid("ben_g"), self.uid("cy_g")))  # a member blocked cy
        self.assertEqual(a.post("gadd", gid=str(g), members="cy_g")[0].status_code, 400)
        for i in range(29):
            self.db.execute("INSERT INTO ginvites(gid,uid,inv,ts) VALUES(?,?,1,1)", (g, 1000 + i))
        self.assertEqual(a.post("gadd", gid=str(g), members="dee_g")[0].status_code, 400)  # 2 members + 29 invites = 31: full
        self.db.execute("DELETE FROM ginvites WHERE uid=1000")
        self.assertEqual(a.post("gadd", gid=str(g), members="dee_g")[1], {"added": 1})

    def test_admin_may_delete_in_own_groups_only(self):
        from tests.harness import Browser
        adm = Browser(self.app)
        adm.me()
        adm.post("login", name=self.ADMIN, pw="adminpass123")
        g = self.group()
        self.db.execute("INSERT INTO gmessages(gid,uid,txt,ts,img) VALUES(?,?,'x',1,'')", (g, self.uid("ann_g")))
        mid = self.val("SELECT id FROM gmessages")
        adm.post("gdel", id=str(mid))
        self.assertEqual(self.val("SELECT COUNT(*) FROM gmessages"), 1)  # admin is not in that group
        self.db.execute("INSERT INTO gmembers(gid,uid) VALUES(?,?)", (g, self.uid(self.ADMIN)))
        adm.post("gdel", id=str(mid))
        self.assertEqual(self.val("SELECT COUNT(*) FROM gmessages"), 0)
        self.assertEqual(self.val("SELECT act FROM alog ORDER BY id DESC LIMIT 1"), "deleted message")

    def test_gopen(self):
        self.db.execute("INSERT INTO gifts(id,uid,by,ts) VALUES(1,?,1,1)", (self.uid("ann_g"),))
        self.db.execute("INSERT INTO gifts(id,uid,by,ts) VALUES(2,?,1,1)", (self.uid("ben_g"),))
        self.assertEqual(self.a.post("gopen", id="1")[1], {"ok": 1})
        self.a.post("gopen", id="2")  # not hers
        self.assertEqual(sorted(r[0] for r in self.db.execute("SELECT opened FROM gifts ORDER BY id")), [0, 1])
        self.assertEqual(self.db.execute("SELECT opened FROM gifts WHERE id=1").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
