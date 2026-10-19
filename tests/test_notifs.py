#!/usr/bin/env python3
"""Step 3d: the bell, devices and web push.   python3 -I tests/test_notifs.py -v"""
import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from tests.harness import Browser, OfflineCase  # noqa: E402


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class NotifsTest(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b = cls.user("ann_n"), cls.user("ben_n")

    def test_bell(self):
        a, b = self.a, self.b
        a.post("post", cap="hello bell")
        pid = self.val("SELECT MAX(id) FROM posts")
        b.post("like", id=pid)
        j = a.post("notifs")[1]
        row = j["list"][0]
        self.assertEqual((row["kind"], row["name"], row["cap"], row["seen"]), ("like", "ben_n", "hello bell", 0))
        self.assertNotIn("mid", row)
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE uid=? AND seen=0", self.uid("ann_n")), 0)  # marked seen
        self.assertEqual(a.post("notifs")[1]["list"][0]["seen"], 1)
        # the post goes "Only me": the caption must stop showing
        self.db.execute("UPDATE posts SET vis=2 WHERE id=?", (pid,))
        self.db.execute("UPDATE posts SET uid=? WHERE id=?", (self.uid("ben_n"), pid))
        row = a.post("notifs")[1]["list"][0]
        self.assertEqual((row["cap"], row.get("gone")), ("", 1))
        # old alerts are dropped
        self.db.execute("UPDATE notifs SET ts=1")
        self.assertEqual(a.post("notifs")[1]["list"], [])
        self.assertEqual(Browser(self.app).get("a=me")[1]["me"], None)

    def test_devices(self):
        a1 = self.user("dev_n")
        a2 = Browser(self.app)
        a2.me()
        self.assertEqual(a2.post("login", name="dev_n", pw="password123")[0].status_code, 200)
        lst = a1.post("devices")[1]["list"]
        self.assertEqual((len(lst), sorted(x["cur"] for x in lst)), (2, [0, 1]))
        other = next(x for x in lst if not x["cur"])
        self.assertEqual(set(other), {"n", "label", "ts", "last", "cur"})
        self.assertEqual(a1.post("devout", id=next(x["n"] for x in lst if x["cur"]))[1], {"ok": 1})  # cannot remove itself
        self.assertEqual(len(a1.post("devices")[1]["list"]), 2)
        a1.post("devout", id=other["n"])
        self.assertEqual(len(a1.post("devices")[1]["list"]), 1)
        self.assertFalse(a2.get("a=me")[1]["me"])  # signed out
        a3 = Browser(self.app); a3.me(); a3.post("login", name="dev_n", pw="password123")
        self.assertEqual(a1.post("devoutall")[1], {"ok": 1})
        self.assertEqual(len(a1.post("devices")[1]["list"]), 1)
        self.assertEqual(Browser(self.app).post.__name__, "post")

    def test_push(self):
        a = self.a
        key = a.post("pushkey")[1]["key"]
        self.assertEqual(len(base64.urlsafe_b64decode(key + "==")), 65)
        self.assertEqual(a.post("pushtest")[0].status_code, 400)  # nothing subscribed yet
        k = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        good = dict(ep="http://127.0.0.1:9/push/abc", k=b64(k), a=b64(b"0123456789abcdef"))
        self.assertEqual(a.post("pushsub", **dict(good, ep="https://evil.example/x"))[0].status_code, 400)
        self.assertEqual(a.post("pushsub", **dict(good, k=b64(b"short")))[0].status_code, 400)
        self.assertEqual(a.post("pushsub", **good)[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM pushsubs WHERE uid=?", self.uid("ann_n")), 1)
        self.assertEqual(a.post("pushtest")[1], {"ok": 1})
        self.assertEqual(a.post("pushoff", ep=good["ep"])[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM pushsubs WHERE uid=?", self.uid("ann_n")), 0)
        for i in range(12):  # only the newest 10 are kept
            a.post("pushsub", **dict(good, ep="http://127.0.0.1:9/push/%d" % i))
        self.assertEqual(self.val("SELECT COUNT(*) FROM pushsubs WHERE uid=?", self.uid("ann_n")), 10)


if __name__ == "__main__":
    unittest.main()
