#!/usr/bin/env python3
"""Step 3a: feed, posts, comments, likes, polls, pins, saves, tags, mutes, notification settings.   python3 -I tests/test_posts.py -v"""
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image  # noqa: E402
from tests.harness import OfflineCase  # noqa: E402


def png():
    b = io.BytesIO()
    Image.new("RGB", (6, 6), (200, 10, 10)).save(b, "PNG")
    b.seek(0)
    return b


class PostsTest(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b, cls.c = cls.user("ann_p"), cls.user("ben_p"), cls.user("cy_p")

    def test_post_feed_like_comment(self):
        a, b = self.a, self.b
        r, j = a.post("post", cap="hello #World @ben_p")
        self.assertEqual((r.status_code, j), (200, {"ok": 1, "hold": 0}))
        pid = self.val("SELECT MAX(id) FROM posts")
        self.assertEqual(self.sql("SELECT tag FROM posttags WHERE pid=?", pid), [{"tag": "world"}])
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE uid=? AND kind='mention'", self.uid("ben_p")), 1)
        r, j = b.get("a=feed")
        self.assertEqual(j["posts"][0]["cap"], "hello #World @ben_p")
        self.assertEqual(j["posts"][0]["name"], "ann_p")
        self.assertNotIn("uid", j["posts"][0])
        self.assertEqual(j["posts"][0]["own"], 0)
        # like and unlike
        self.assertEqual(b.post("like", id=pid)[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM likes WHERE pid=?", pid), 1)
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE uid=? AND kind='like'", self.uid("ann_p")), 1)
        self.assertEqual(b.get("a=feed")[1]["posts"][0]["me"], 1)
        b.post("like", id=pid)
        self.assertEqual(self.val("SELECT COUNT(*) FROM likes WHERE pid=?", pid), 0)
        # comment, reply, list
        j = b.post("comment", pid=pid, txt="nice one")[1]
        self.assertEqual(j["ok"], 1)
        cid = j["id"]
        self.assertEqual(a.post("comment", pid=pid, txt="thanks", par=cid)[1]["ok"], 1)
        j = a.get("a=comments&pid=%d" % pid)[1]
        self.assertEqual([c["txt"] for c in j["comments"]], ["nice one", "thanks"])
        self.assertEqual((j["owner"], j["comments"][1]["par"], j["comments"][0]["mine"]), (1, cid, 0))
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE uid=? AND kind='comment'", self.uid("ann_p")), 1)
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE uid=? AND kind='reply'", self.uid("ben_p")), 1)
        # edit / like / delete a comment
        self.assertEqual(b.post("editc", id=cid, txt="nicer one")[1]["txt"], "nicer one")
        a.post("clike", id=cid)
        self.assertEqual(self.val("SELECT COUNT(*) FROM clikes WHERE cid=?", cid), 1)
        self.assertEqual(a.post("delc", id=cid)[1], {"ok": 1})  # post owner may delete
        self.assertEqual(self.val("SELECT COUNT(*) FROM comments WHERE pid=?", pid), 0)  # the reply goes with it (tidy)

    def test_photo_post_and_edit(self):
        a = self.a
        r, j = a.post("pup", files={"img": (png(), "x.png")})
        self.assertEqual(r.status_code, 200)
        name = j["img"]
        self.assertTrue((self.tmp / "up" / name).exists())
        self.assertEqual(a.post("post", cap="pic", imgs=json.dumps([name]), alts=json.dumps({name: "a red square"}))[1]["ok"], 1)
        pid = self.val("SELECT MAX(id) FROM posts")
        p = a.get("a=feed&id=%d" % pid)[1]["posts"][0]
        self.assertEqual((p["imgs"], p["alts"], p["img"]), ([name], ["a red square"], name))
        j = a.post("edit", id=pid, cap="pic edited", vis=1)[1]
        self.assertEqual((j["cap"], j["vis"]), ("pic edited", 1))
        self.assertEqual(self.val("SELECT cap FROM pedits WHERE pid=?", pid), "pic")
        h = a.get("a=pedhist&id=%d" % pid)[1]
        self.assertEqual((h["cur"]["cap"], [v["cap"] for v in h["v"]], h["own"]), ("pic edited", ["pic"], 1))
        self.assertEqual(a.post("pedclear", id=pid)[1], {"ok": 1})
        self.assertEqual(a.post("del", id=pid)[1], {"ok": 1})
        self.assertFalse((self.tmp / "up" / name).exists())

    def test_visibility(self):
        a, b = self.a, self.b
        a.post("post", cap="only me post", vis=2)
        pid = self.val("SELECT MAX(id) FROM posts")
        self.assertNotIn(pid, [p["id"] for p in b.get("a=feed")[1]["posts"]])
        self.assertEqual(b.post("like", id=pid)[0].status_code, 404)
        self.assertIn(pid, [p["id"] for p in a.get("a=feed")[1]["posts"]])

    def test_poll(self):
        a, b = self.a, self.b
        self.assertEqual(a.post("post", cap="Pick one", poll=json.dumps(["x", "y"]))[1]["ok"], 1)
        pid = self.val("SELECT MAX(id) FROM posts")
        p = b.get("a=feed&id=%d" % pid)[1]["posts"][0]
        self.assertEqual((p["poll"]["o"], p["poll"]["n"], p["poll"]["v"]), (["x", "y"], None, 0))
        tok = "a" * 32
        self.assertEqual(b.post("pvote", id=pid, opt=1, t=tok)[1], {"poll": {"v": 1, "n": [0, 1]}})
        self.assertEqual(b.post("pvote", id=pid, opt=0, t=tok)[1], {"poll": {"v": 1, "n": [0, 1]}})  # second vote is ignored
        self.assertEqual(b.post("pchange", id=pid, **{"from": 1}, opt=0, ot=tok, t="b" * 32)[1], {"poll": {"v": 1, "n": [1, 0]}})
        self.assertEqual(b.post("pchange", id=pid, **{"from": 0}, opt=-1, ot="b" * 32)[1], {"poll": {"v": 0, "n": None}})
        self.assertEqual(self.c.post("pvote", id=pid, opt=0)[1]["poll"]["n"], [1, 0])
        self.assertEqual(b.post("pres", id=pid)[0].status_code, 409)

    def test_saves_views_tags_pins(self):
        a, b = self.a, self.b
        a.post("post", cap="save me #tagz")
        pid = self.val("SELECT MAX(id) FROM posts")
        self.assertEqual(b.post("save", id=pid)[1], {"on": 1})
        self.assertEqual([p["id"] for p in b.get("a=feed&sv=1")[1]["posts"]], [pid])
        self.assertEqual(b.post("save", id=pid)[1], {"on": 0})
        self.assertEqual(b.post("view", ids="%d,%d,0" % (pid, pid))[1], {"ok": 1, "n": 1})
        self.assertEqual(a.post("view", ids=str(pid))[1]["n"], 0)
        self.assertEqual(b.post("tagfollow", tag="TagZ")[1], {"tf": 1})
        self.assertEqual(b.get("a=feed&t=tagz")[1]["tf"], 1)
        self.assertEqual(b.post("tagfollow", tag="bad tag!")[0].status_code, 400)
        self.assertIn("tagz", [t["tag"] for t in b.get("a=tags")[1]["tags"]])
        self.assertEqual(a.post("pin", id=pid)[1], {"ok": 1})
        self.assertEqual(self.val("SELECT pin FROM users WHERE name='ann_p'"), pid)
        self.assertEqual(a.get("a=feed&u=ann_p")[1]["posts"][0]["pinned"], 1)
        self.assertEqual(a.post("pin", id=pid, on="0")[1], {"ok": 1})
        self.assertEqual(b.get("a=feed&s=save+me")[1]["posts"][0]["id"], pid)
        n = b.get("a=feed&cnt=1&after=0")[1]["n"]
        self.assertGreater(n, 0)

    def test_prompt_thread_and_for_you(self):
        c = self.c
        j = c.post("post", cap="my answer", pd=1)[1]
        self.assertEqual(j["ok"], 1)
        self.assertEqual(c.post("post", cap="again", pd=1)[1]["e"], "You already answered today's prompt.")
        feed = c.get("a=feed")[1]
        self.assertTrue(feed["threads"] and feed["threads"][0]["done"] == 1)
        self.assertNotIn("my answer", [p["cap"] for p in feed["posts"]])
        fy = c.get("a=feed&fy=1")[1]
        self.assertIn("posts", fy)
        self.assertEqual(c.get("a=feed&pd=%d" % feed["threads"][0]["day"])[1]["posts"][0]["cap"], "my answer")

    def test_mutes_and_np(self):
        a, b = self.user("dee_p"), self.b
        a.post("post", cap="mute test")
        pid = self.val("SELECT MAX(id) FROM posts")
        cid = b.post("comment", pid=pid, txt="spam spam")[1]["id"]
        self.assertEqual(a.post("mutec", id=cid)[1], {"ok": 1})
        self.assertEqual(a.get("a=comments&pid=%d" % pid)[1]["hid"], 1)
        self.assertEqual(a.get("a=mutes")[1]["users"][0]["name"], "ben_p")
        a.post("unmute", kind="u", v=str(self.uid("ben_p")))
        self.assertEqual(a.get("a=mutes")[1]["users"], [])
        self.assertEqual(a.post("muteword", w="  Foo  Bar ")[1], {"ok": 1, "w": "foo bar"})
        self.assertEqual(a.get("a=mutes")[1]["words"], ["foo bar"])
        self.assertEqual(a.post("setnp", muted="sigils,bogus,tags", qon=1, qfrom=100)[1], {"ok": 1})
        self.assertEqual(a.get("a=np")[1], {"muted": ["sigils", "tags"], "pop": 1, "qon": 1, "qfrom": 100, "qto": 420})

    def test_masque_post_hides_account(self):
        a, b = self.a, self.b
        self.assertEqual(a.post("post", cap="as masque", **{"as": "mask"})[1]["e"], "Create your Masque first.")


if __name__ == "__main__":
    unittest.main()
