#!/usr/bin/env python3
"""Step 3c, groups part 2: gaddmask gmaskme gremove gleave grename gicon gsetbg gmute ginv gacc glink glinkinfo gjoin gsearch gpin greact.

    python3 -I tests/test_groups2.py -v
"""
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.harness import OfflineCase  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0000003010100c9fe92ef0000000049454e44ae426082")
MINE = {"gaddmask", "gmaskme", "gremove", "gleave", "grename", "gicon", "gsetbg", "gmute", "ginv", "gacc", "glink", "glinkinfo", "gjoin", "gsearch", "gpin", "greact"}


class Groups2Offline(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b, cls.c, cls.d = cls.user("ann_h"), cls.user("ben_h"), cls.user("cy_h"), cls.user("dee_h")

    def setUp(self):
        for t in ("gchats", "gmembers", "gmessages", "gevents", "ginvites", "gmasks", "glinks", "mreact", "friends", "blocks", "rl", "masks"):
            self.db.execute("DELETE FROM " + t)
        self.db.execute("UPDATE users SET ts=ts-2000000")
        for y in ("ben_h", "cy_h", "dee_h"):
            self.db.execute("INSERT INTO friends(a,b,st) VALUES(?,?,1)", (self.uid("ann_h"), self.uid(y)))

    def group(self, members="ben_h,cy_h"):
        return self.a.post("gcreate", name="Crew", members=members)[1]["id"]

    def mask(self, who, name):
        self.db.execute("INSERT INTO masks(uid,name,ts) VALUES(?,?,1)", (self.uid(who), name))

    def test_python_owns_these_actions(self):
        from masque.actions import load_all
        self.assertEqual(MINE - set(load_all().names()), set())

    def test_rename_mute_background(self):
        g = str(self.group())
        self.assertEqual(self.b.post("grename", gid=g, name=" New ")[1], {"name": "New"})
        self.b.post("grename", gid=g, name="New")  # same name: no second notice
        self.assertEqual(self.val("SELECT COUNT(*) FROM gevents WHERE kind='name'"), 1)
        self.assertEqual(self.b.post("grename", gid=g, name="")[0].status_code, 400)
        self.assertEqual(self.d.post("grename", gid=g, name="x")[0].status_code, 404)
        self.assertEqual(self.b.post("gmute", gid=g, on="1")[1], {"mu": 1})
        self.assertEqual(self.b.post("gmute", gid=g)[1], {"mu": 0})
        self.assertEqual(self.b.post("gsetbg", gid=g, bg="dusk")[1], {"bg": "dusk"})
        self.assertEqual(self.b.post("gsetbg", gid=g, bg="nope")[0].status_code, 400)
        self.assertEqual(self.val("SELECT COUNT(*) FROM gevents WHERE kind='bg'"), 1)

    def test_icon(self):
        g = str(self.group())
        self.assertEqual(self.b.post("gicon", gid=g)[0].status_code, 400)
        av = self.b.post("gicon", gid=g, files={"avatar": (io.BytesIO(PNG), "p.png")})[1]["avatar"]
        self.assertTrue((Path(self.cfg.data_dir) / "up" / av).exists())
        self.assertEqual(self.b.post("gicon", gid=g, noavatar="1")[1], {"avatar": ""})
        self.assertFalse((Path(self.cfg.data_dir) / "up" / av).exists())

    def test_remove_and_leave(self):
        g = self.group()
        self.assertEqual(self.b.post("gremove", gid=str(g), name="cy_h")[0].status_code, 403)
        self.assertEqual(self.a.post("gremove", gid=str(g), name="ann_h")[0].status_code, 400)
        self.assertEqual(self.a.post("gremove", gid=str(g), name="cy_h")[1], {"ok": 1})
        self.assertEqual(self.a.post("gremove", gid=str(g), name="cy_h")[0].status_code, 404)
        self.assertEqual(self.a.post("gleave", gid=str(g))[1], {"ok": 1})
        self.assertEqual(self.val("SELECT owner FROM gchats WHERE id=?", g), self.uid("ben_h"))  # next member takes over
        self.db.execute("INSERT INTO gmessages(gid,uid,txt,ts) VALUES(?,?,'x',1)", (g, self.uid("ben_h")))
        self.db.execute("INSERT INTO mreact(k,mid,uid,e) VALUES('g',1,?,'x')", (self.uid("ben_h"),))
        self.b.post("gleave", gid=str(g))
        self.assertEqual([self.val("SELECT COUNT(*) FROM " + t) for t in ("gchats", "gmessages", "gevents", "mreact")], [0, 0, 0, 0])

    def test_invites_and_links(self):
        g = str(self.group(members="ben_h"))
        self.a.post("gadd", gid=g, members="cy_h")
        inv = self.c.post("ginv")[1]["invites"]
        self.assertEqual((len(inv), inv[0]["name"], inv[0]["who"]), (1, "Crew", "ann_h"))
        self.assertEqual(self.c.post("gacc", id="999")[0].status_code, 404)
        self.assertEqual(self.c.post("gacc", id=str(inv[0]["id"]))[1], {"id": int(g)})
        self.assertEqual(self.val("SELECT COUNT(*) FROM gmembers WHERE gid=?", g), 3)
        self.a.post("gadd", gid=g, members="dee_h")
        self.d.post("gacc", id=str(self.val("SELECT id FROM ginvites")), act="decline")
        self.assertEqual(self.val("SELECT COUNT(*) FROM ginvites"), 0)
        code = self.b.post("glink", gid=g)[1]["code"]
        self.assertEqual(self.a.post("glink", gid=g)[1]["code"], code)
        self.assertNotEqual(self.a.post("glink", gid=g, reset="1")[1]["code"], code)
        code = self.a.post("glink", gid=g)[1]["code"]
        self.assertEqual(self.d.get("a=glinkinfo&c=" + code)[1]["in"], 0)
        self.assertEqual(self.d.get("a=glinkinfo&c=zz")[0].status_code, 404)
        self.assertEqual(self.d.post("gjoin", c="bad")[0].status_code, 404)
        self.assertEqual(self.d.post("gjoin", c=code)[1], {"id": int(g)})
        self.assertEqual(self.val("SELECT COUNT(*) FROM gevents WHERE kind='join' AND arg='link'"), 1)

    def test_masques(self):
        g = str(self.group(members="ben_h"))
        self.assertEqual(self.a.post("gmaskme", gid=g, on="1")[0].status_code, 400)  # no Masque yet
        self.mask("ann_h", "Ghost")
        self.mask("cy_h", "Shade")
        self.assertEqual(self.a.post("gmaskme", gid=g, on="1")[1], {"ok": 1, "on": 1})
        self.assertEqual(self.a.post("gmaskme", gid=g)[1], {"ok": 1, "on": 0})
        self.assertEqual(self.a.post("gaddmask", gid=g, name="Ghost")[0].status_code, 400)  # own Masque
        self.assertEqual(self.a.post("gaddmask", gid=g, name="Nobody")[0].status_code, 404)
        self.assertEqual(self.a.post("gaddmask", gid=g, name="Shade")[1], {"added": 1})
        self.assertEqual(self.a.post("gaddmask", gid=g, name="Shade")[0].status_code, 400)  # already invited
        inv = self.c.post("ginv")[1]["invites"][0]
        self.assertEqual(inv["mq"], "Shade")
        self.c.post("gacc", id=str(inv["id"]))
        self.assertEqual(self.val("SELECT pm FROM gmembers WHERE uid=?", self.uid("cy_h")), 1)
        self.assertEqual(self.a.post("gremove", gid=g, name="Shade", mk="1")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM gmembers WHERE uid=?", self.uid("cy_h")), 0)  # Masque was how they were here

    def test_search_pin_react(self):
        g = self.group()
        for t in ("hello 100%", "other"):
            self.a.post("gsend", gid=str(g), txt=t)
        self.assertEqual([r["txt"] for r in self.b.get("a=gsearch&id=%d&q=100%%25" % g)[1]["res"]], ["hello 100%"])
        self.assertEqual(self.b.get("a=gsearch&id=%d&q=h" % g)[1], {"res": []})
        self.assertEqual(self.d.get("a=gsearch&id=%d&q=hello" % g)[0].status_code, 404)
        self.assertEqual(self.b.post("gpin", id="1")[1]["pin"] > 0, True)
        self.assertEqual(self.b.post("gpin", id="1")[1], {"pin": 0})
        self.assertEqual(self.d.post("gpin", id="1")[0].status_code, 404)
        r = self.b.post("greact", id="1", e="\U0001f525")[1]["rx"]
        self.assertEqual((r[0]["n"], r[0]["me"]), (1, 1))
        self.assertEqual(self.b.post("greact", id="1", e="\U0001f525")[1]["rx"], [])
        self.assertEqual(self.b.post("greact", id="1", e="zz")[0].status_code, 400)
        self.db.execute("INSERT INTO blocks VALUES(?,?)", (self.uid("ben_h"), self.uid("ann_h")))
        self.assertEqual(self.b.post("greact", id="1", e="\U0001f525")[0].status_code, 403)


if __name__ == "__main__":
    unittest.main()
