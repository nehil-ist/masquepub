#!/usr/bin/env python3
"""Step 3c, Masques: maskinb, mblock, maskset, maskdel, maskuser, mreveal, mcomments.

    python3 -I tests/test_masques.py -v      (offline checks, then the PHP-versus-Python comparison when php is installed)
"""
import io
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.harness import OfflineCase  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0000003010100c9fe92ef0000000049454e44ae426082")
MINE = {"maskinb", "mblock", "maskset", "maskdel", "maskuser", "mreveal", "mcomments"}


class MasquesOffline(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b = cls.user("ann_m"), cls.user("ben_m")

    def setUp(self):
        self.db.execute("DELETE FROM masks")

    def masque(self, who, name):
        self.db.execute("INSERT INTO masks(uid,name,ts) VALUES(?,?,?)", (self.uid(who), name, 1))

    def test_python_owns_these_actions(self):
        from masque.actions import load_all
        self.assertEqual(MINE - set(load_all().names()), set())

    def test_maskinb(self):
        self.masque("ann_m", "Phantom")
        self.assertEqual(self.a.post("maskinb", on="1")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT inb FROM masks WHERE name='Phantom'"), 1)
        self.a.post("maskinb", on="0")
        self.assertEqual(self.val("SELECT inb FROM masks WHERE name='Phantom'"), 0)
        self.a.post("maskinb")  # missing / empty = off, like !empty()
        self.assertEqual(self.val("SELECT inb FROM masks WHERE name='Phantom'"), 0)
        self.a.post("maskinb", on="1")
        self.assertEqual(self.val("SELECT inb FROM masks WHERE name='Phantom'"), 1)
        self.assertEqual(self.b.post("maskinb", on="0")[1], {"ok": 1})  # no Masque: nothing changes, still ok
        self.assertEqual(self.val("SELECT inb FROM masks WHERE name='Phantom'"), 1)

    def test_mblock(self):
        self.db.execute("DELETE FROM mblocks")
        self.masque("ben_m", "Ghost")
        self.masque("ann_m", "Phantom")
        a = self.a
        self.assertEqual(a.post("mblock", k="Ghost")[1], {"ok": 1})
        a.post("mblock", k="ghost")  # again, any case: still one row
        self.assertEqual(self.val("SELECT COUNT(*) FROM mblocks WHERE a=?", self.uid("ann_m")), 1)
        a.post("mblock", k="Ghost", on="0")
        self.assertEqual(self.val("SELECT COUNT(*) FROM mblocks"), 0)
        a.post("mblock", k="Ghost", on="")  # only the exact string "0" unblocks
        self.assertEqual(self.val("SELECT COUNT(*) FROM mblocks"), 1)
        self.assertEqual(a.post("mblock", k="Phantom")[0].status_code, 404)  # my own Masque
        self.assertEqual(a.post("mblock", k="Nobody")[0].status_code, 404)

    def test_maskset(self):
        a, b = self.a, self.b
        self.db.execute("DELETE FROM gone")
        self.db.execute("DELETE FROM oldnames")
        r = a.post("maskset", name="  Phantom ", bio="  hi  ")
        self.assertEqual(r[1], {"mask": {"name": "Phantom", "bio": "hi", "avatar": ""}})
        self.assertEqual(b.post("maskset", name="ab")[0].status_code, 400)  # too short
        self.assertEqual(b.post("maskset", name="phantom")[0].status_code, 409)  # taken (any case)
        self.assertEqual(b.post("maskset", name="ann_m")[0].status_code, 409)  # an account name
        self.db.execute("INSERT INTO gone VALUES(?,?)", (__import__("masque.names", fromlist=["x"]).NameRules.digest("Zed_m"), 99))
        self.assertEqual(b.post("maskset", name="Zed_m")[0].status_code, 409)  # deleted account's name
        r = a.post("maskset", name="Other", bio="b" * 200)  # name ignored once a Masque exists
        self.assertEqual((r[1]["mask"]["name"], len(r[1]["mask"]["bio"])), ("Phantom", 160))
        r = a.post("maskset", files={"avatar": (io.BytesIO(PNG), "a.png")})
        av = r[1]["mask"]["avatar"]
        self.assertTrue(av.endswith(".png"))
        r = a.post("maskset", bio="x", noavatar="1")
        self.assertEqual(r[1]["mask"]["avatar"], "")
        self.assertFalse((Path(self.cfg.data_dir) / "up" / av).exists())  # old picture deleted

    def test_maskdel(self):
        a, b = self.a, self.b
        for tb in ("gone", "messages", "mblocks", "gchats", "gmembers", "gmessages", "posts", "rrep"):
            self.db.execute("DELETE FROM " + tb)
        self.assertEqual(a.post("maskdel")[1], {"ok": 1})  # no Masque: nothing to do
        r = a.post("maskset", name="Phantom", files={"avatar": (io.BytesIO(PNG), "a.png")})
        av = r[1]["mask"]["avatar"]
        mid = self.val("SELECT id FROM masks")
        ai, bi = self.uid("ann_m"), self.uid("ben_m")
        self.db.execute("INSERT INTO messages(a,b,fm,tm,txt,ts) VALUES(?,?,1,0,'from mask',1)", (ai, bi))
        self.db.execute("INSERT INTO messages(a,b,fm,tm,txt,ts) VALUES(?,?,0,0,'plain',1)", (ai, bi))
        self.db.execute("INSERT INTO mblocks VALUES(?,?)", (bi, mid))
        self.db.execute("INSERT INTO gchats(id,name,owner,ts) VALUES(1,'solo',?,1)", (ai,))
        self.db.execute("INSERT INTO gmembers(gid,uid,pm) VALUES(1,?,1)", (ai,))
        self.db.execute("INSERT INTO gchats(id,name,owner,ts) VALUES(2,'two',?,1)", (ai,))
        self.db.execute("INSERT INTO gmembers(gid,uid,pm) VALUES(2,?,1)", (ai,))
        self.db.execute("INSERT INTO gmembers(gid,uid,pm) VALUES(2,?,0)", (bi,))
        self.assertEqual(a.post("maskdel")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM masks"), 0)
        self.assertEqual(self.val("SELECT COUNT(*) FROM messages"), 1)  # only the plain one is left
        self.assertEqual(self.val("SELECT COUNT(*) FROM mblocks"), 0)
        self.assertEqual(self.val("SELECT COUNT(*) FROM gchats"), 1)  # the solo group went, the other one lives on
        self.assertEqual(self.val("SELECT owner FROM gchats WHERE id=2"), bi)
        self.assertEqual(self.val("SELECT COUNT(*) FROM gone"), 1)
        self.assertFalse((Path(self.cfg.data_dir) / "up" / av).exists())
        self.assertEqual(b.post("maskset", name="phantom")[0].status_code, 409)  # the name stays reserved

    def test_maskuser(self):
        for tb in ("mblocks", "mreveals", "posts", "comments", "likes", "dislikes", "rrep"):
            self.db.execute("DELETE FROM " + tb)
        a, b = self.a, self.b
        self.assertEqual(a.get("a=maskuser&k=Nobody")[0].status_code, 404)
        a.post("maskset", name="Phantom", bio="boo")
        kid, ai, bi = self.val("SELECT id FROM masks"), self.uid("ann_m"), self.uid("ben_m")
        j = a.get("a=maskuser&k=%20phantom")[1]["k"]  # trimmed, any case
        self.assertEqual((j["name"], j["bio"], j["mine"], j["mb"], j["rv"]), ("Phantom", "boo", 1, 0, []))
        self.assertEqual((j["rep"]["lv"], j["rep"]["title"], j["rep"]["score"], j["rep"]["next"]), (0, "Stranger", 0, 10))
        self.db.execute("INSERT INTO posts(id,uid,mid,cap,img,ts) VALUES(1,?,?,'x','',1)", (ai, kid))
        self.db.execute("INSERT INTO posts(id,uid,mid,cap,img,ts) VALUES(2,?,?,'x','',1)", (ai, kid))
        self.db.execute("INSERT INTO posts(id,uid,mid,cap,img,ts) VALUES(3,?,?,'x','',1)", (ai, kid))
        self.db.execute("INSERT INTO posts(id,uid,mid,cap,img,ts) VALUES(4,?,?,'x','',1)", (ai, kid))  # 12 points
        self.db.execute("INSERT INTO rrep(uid,up,down) VALUES(?,2,0)", (ai,))
        rep = b.get("a=maskuser&k=Phantom")[1]["k"]
        self.assertEqual((rep["rep"]["lv"], rep["rep"]["title"], rep["rep"]["score"], rep["rep"]["posts"], rep["rep"]["marks"]), (1, "Whisper", 14, 4, 2))
        self.assertEqual((rep["rep"]["from"], rep["rep"]["next"], rep["rep"]["nextTitle"]), (10, 40, "Regular"))
        self.assertEqual((rep["mine"], rep["by"]), (0, None))
        self.assertNotIn("rv", rep)
        self.db.execute("INSERT INTO mreveals VALUES(?,?,5)", (ai, bi))
        self.assertEqual(b.get("a=maskuser&k=Phantom")[1]["k"]["by"]["name"], "ann_m")
        self.assertEqual([x["name"] for x in a.get("a=maskuser&k=Phantom")[1]["k"]["rv"]], ["ben_m"])
        self.db.execute("UPDATE rrep SET down=30")
        self.assertEqual(a.get("a=maskuser&k=Phantom")[1]["k"]["rep"]["title"], "Shunned")
        self.db.execute("INSERT INTO mblocks VALUES(?,?)", (bi, kid))
        blocked = b.get("a=maskuser&k=Phantom")[1]["k"]
        self.assertEqual((blocked["bio"], blocked["mb"], "rep" in blocked), ("", 1, False))

    def test_mreveal(self):
        for tb in ("mreveals", "friends", "blocks", "notifs"):
            self.db.execute("DELETE FROM " + tb)
        a, b = self.a, self.b
        ai, bi = self.uid("ann_m"), self.uid("ben_m")
        self.assertEqual(a.post("mreveal", to="ben_m")[0].status_code, 400)  # no Masque yet
        a.post("maskset", name="Phantom")
        self.assertEqual(a.post("mreveal", to="nobody_m")[0].status_code, 404)
        self.assertEqual(a.post("mreveal", to="ann_m")[0].status_code, 404)
        self.assertEqual(a.post("mreveal", to="ben_m")[0].status_code, 403)  # not friends
        self.db.execute("INSERT INTO friends(a,b,st) VALUES(?,?,1)", (ai, bi))
        self.assertEqual(a.post("mreveal", to="ben_m")[1], {"ok": 1})
        a.post("mreveal", to="ben_m")  # again: no second notification
        self.assertEqual(self.val("SELECT COUNT(*) FROM mreveals"), 1)
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE kind='reveal' AND uid=? AND actor=?", bi, ai), 1)
        a.post("mreveal", to="ben_m", on="0")
        self.assertEqual(self.val("SELECT COUNT(*) FROM mreveals"), 0)
        self.db.execute("INSERT INTO blocks VALUES(?,?)", (bi, ai))
        self.assertEqual(a.post("mreveal", to="ben_m")[0].status_code, 403)  # a block either way

    def test_mcomments(self):
        for tb in ("mblocks", "posts", "comments", "blocks"):
            self.db.execute("DELETE FROM " + tb)
        a, b = self.a, self.b
        ai, bi = self.uid("ann_m"), self.uid("ben_m")
        self.assertEqual(a.get("a=mcomments&k=Nobody")[0].status_code, 404)
        self.masque("ann_m", "Phantom")
        kid = self.val("SELECT id FROM masks")
        self.db.execute("INSERT INTO posts(id,uid,mid,cap,img,ts) VALUES(1,?,0,?,'x.png',1)", (bi, "c" * 100))  # ben's photo post
        self.db.execute("INSERT INTO posts(id,uid,mid,cap,img,ts,anon) VALUES(2,?,0,'mine','',1,1)", (ai,))  # ann's own anonymous post
        self.db.execute("INSERT INTO posts(id,uid,mid,cap,img,ts,vis) VALUES(3,?,0,'hidden','',1,2)", (ai,))  # only ann can see it
        for i in range(1, 36):
            self.db.execute("INSERT INTO comments(id,pid,uid,mid,txt,ts) VALUES(?,1,?,?,?,1000)", (i, ai, kid, "t%d" % i))
        self.db.execute("INSERT INTO comments(id,pid,uid,mid,txt,ts) VALUES(40,2,?,?,'own anon',1000)", (ai, kid))
        self.db.execute("INSERT INTO comments(id,pid,uid,mid,txt,ts) VALUES(41,3,?,?,'secret',1000)", (ai, kid))
        j = b.get("a=mcomments&k=Phantom")[1]
        self.assertEqual((len(j["list"]), j["more"], j["last"]), (28, True, 8))  # 30 rows read; #41 and #40 were hidden from ben
        self.assertEqual((j["list"][0]["id"], j["list"][0]["pcap"], j["list"][0]["photo"]), (35, "c" * 80, 1))
        self.assertNotEqual(j["list"][0]["ts"], 1000)  # time blurred for other people
        j2 = b.get("a=mcomments&k=Phantom&before=%d" % j["last"])[1]
        self.assertEqual(([x["id"] for x in j2["list"]], j2["more"]), ([7, 6, 5, 4, 3, 2, 1], False))
        own = a.get("a=mcomments&k=Phantom")[1]
        self.assertEqual([(x["id"], x["ts"]) for x in own["list"][:2]], [(41, 1000), (40, 1000)])  # the owner sees everything of hers, exact time
        self.db.execute("INSERT INTO mblocks VALUES(?,?)", (bi, kid))
        self.assertEqual(b.get("a=mcomments&k=Phantom")[0].status_code, 404)


if __name__ == "__main__":
    unittest.main()
