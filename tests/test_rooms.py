#!/usr/bin/env python3
"""Step 3c, rooms and report buttons: rlist rcreate rthread rsend rclose rvote rdelmsg + rdone rdel rblur.

    python3 -I tests/test_rooms.py -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.harness import Browser, OfflineCase  # noqa: E402

MINE = {"rlist", "rcreate", "rthread", "rsend", "rclose", "rvote", "rdelmsg", "rdone", "rdel", "rblur"}


class RoomsOffline(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b, cls.c = cls.user("ann_r"), cls.user("ben_r"), cls.user("cy_r")

    def setUp(self):
        for t in ("rooms", "rmsgs", "rpres", "rvotes", "rrep", "masks", "mblocks", "rl", "reports", "posts", "alog", "badwords"):
            self.db.execute("DELETE FROM " + t)
        self.db.execute("UPDATE users SET ts=ts-2000000")
        for n in ("ann_r", "ben_r"):
            self.db.execute("INSERT INTO masks(uid,name,ts) VALUES(?,?,1)", (self.uid(n), "M_" + n))

    def room(self, **kw):
        return self.a.post("rcreate", name="Late night", **kw)[1]["id"]

    def test_python_owns_these_actions(self):
        from masque.actions import load_all
        self.assertEqual(MINE - set(load_all().names()), set())

    def test_create_rules(self):
        self.assertEqual(self.c.post("rcreate", name="x")[0].status_code, 400)  # no Masque
        self.assertEqual(self.a.post("rcreate", name="  ")[0].status_code, 400)
        r = self.room(theme="bogus", hrs="6")
        row = self.db.execute("SELECT theme,exp-ts FROM rooms WHERE id=?", (r,)).fetchone()
        self.assertEqual(tuple(row), ("midnight", 21600))
        self.assertEqual(self.val("SELECT exp-ts FROM rooms WHERE id=?", self.room()), 86400)
        self.db.execute("DELETE FROM rl")
        self.assertEqual(self.a.post("rcreate", name="third")[0].status_code, 400)  # two open rooms at most
        self.db.execute("INSERT INTO badwords(w,hold) VALUES('rude',0)")
        self.assertEqual(self.b.post("rcreate", name="so rude")[0].status_code, 400)

    def test_send_thread_list(self):
        r = str(self.room())
        self.assertEqual(self.a.post("rsend", id=r, txt="")[0].status_code, 400)
        self.assertEqual(self.c.post("rsend", id=r, txt="hi")[0].status_code, 400)  # no Masque
        self.assertEqual(self.a.post("rsend", id="999", txt="hi")[0].status_code, 404)
        self.a.post("rsend", id=r, txt="  hello  ")
        j = self.b.get("a=rthread&id=" + r)[1]
        self.assertEqual([(x["txt"], x["name"], x["mine"]) for x in j["msgs"]], [("hello", "M_ann_r", 0)])
        self.assertEqual((j["has"], len(j["here"]), j["room"]["own"]), (1, 2, 0))
        self.assertEqual(self.b.get("a=rthread&id=%s&after=%d" % (r, j["msgs"][0]["id"]))[1]["msgs"], [])
        self.assertEqual(self.b.post("rlist")[1]["rooms"][0]["n"], 1)
        self.db.execute("INSERT INTO mblocks(a,kid) SELECT ?,id FROM masks WHERE uid=?", (self.uid("ben_r"), self.uid("ann_r")))
        self.assertEqual(self.b.post("rlist")[1]["rooms"], [])  # owner's Masque is blocked
        self.assertEqual(self.b.get("a=rthread&id=" + r)[1]["msgs"], [])

    def test_vote_delete_close(self):
        r = str(self.room())
        self.a.post("rsend", id=r, txt="one")
        mid = str(self.val("SELECT id FROM rmsgs"))
        self.assertEqual(self.a.post("rvote", id=mid, v="1")[0].status_code, 400)  # own message
        self.assertEqual(self.b.post("rvote", id=mid, v="5")[1], {"ok": 1, "up": 1, "mv": 1})
        self.assertEqual(self.val("SELECT up FROM rrep"), 1)
        self.assertEqual(self.b.post("rvote", id=mid, v="-1")[1], {"ok": 1, "up": 0, "mv": -1})
        self.assertEqual(tuple(self.db.execute("SELECT up,down FROM rrep").fetchone()), (0, 1))
        self.b.post("rvote", id=mid, v="0")
        self.assertEqual((self.val("SELECT COUNT(*) FROM rvotes"), self.val("SELECT down FROM rrep")), (0, 0))
        self.assertEqual(self.c.post("rvote", id=mid, v="1")[0].status_code, 400)
        self.assertEqual(self.b.post("rdelmsg", id=mid)[0].status_code, 403)
        self.assertEqual(self.a.post("rclose", id=r)[1], {"ok": 1})
        self.assertEqual((self.val("SELECT COUNT(*) FROM rooms"), self.val("SELECT COUNT(*) FROM rmsgs")), (0, 0))
        r2 = str(self.room())
        self.a.post("rsend", id=r2, txt="two")
        self.assertEqual(self.b.post("rclose", id=r2)[0].status_code, 403)
        self.assertEqual(self.a.post("rdelmsg", id=str(self.val("SELECT id FROM rmsgs")))[1], {"ok": 1})

    def test_expired_room_is_swept(self):
        r = self.room()
        self.a.post("rsend", id=str(r), txt="x")
        self.db.execute("UPDATE rooms SET exp=1")
        self.assertEqual(self.b.get("a=rthread&id=%d" % r)[0].status_code, 404)
        self.assertEqual(self.val("SELECT COUNT(*) FROM rmsgs"), 0)

    def test_report_buttons(self):
        adm = Browser(self.app)
        adm.me()
        adm.post("login", name=self.ADMIN, pw="adminpass123")
        self.db.execute("INSERT INTO posts(id,uid,cap,ts,img,hold) VALUES(1,?,'p',1,'',1)", (self.uid("ben_r"),))
        self.db.execute("INSERT INTO reports(id,uid,kind,tid,why,ts) VALUES(1,?,'post',1,'x',1)", (self.uid("ann_r"),))
        self.assertEqual(self.a.post("rdone", id="1")[0].status_code, 403)
        self.assertEqual(adm.post("rblur", id="1")[0].status_code, 400)  # no photo
        self.db.execute("UPDATE posts SET img='x.png'")
        self.assertEqual(adm.post("rblur", id="1")[1], {"ok": 1, "sens": 2})
        self.assertEqual(adm.post("rblur", id="1")[1]["sens"], 0)
        adm.post("rdone", id="1")
        self.assertEqual((self.val("SELECT hold FROM posts"), self.val("SELECT COUNT(*) FROM reports")), (0, 0))
        self.db.execute("INSERT INTO reports(id,uid,kind,tid,why,ts) VALUES(2,?,'post',1,'x',1)", (self.uid("ann_r"),))
        adm.post("rdel", id="2")
        self.assertEqual((self.val("SELECT COUNT(*) FROM posts"), self.val("SELECT COUNT(*) FROM reports")), (0, 0))
        self.assertEqual(self.val("SELECT act FROM alog ORDER BY id DESC LIMIT 1"), "deleted post")
        self.assertEqual(adm.post("rdel", id="77")[1], {"ok": 1})


if __name__ == "__main__":
    unittest.main()
