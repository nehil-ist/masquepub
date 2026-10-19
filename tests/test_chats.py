#!/usr/bin/env python3
"""Step 3c, direct chats: inbox, thread, typing, send, msearch, editm, delm, react, rxwho, pinm, setpn, setbg, mreq.

    python3 -I tests/test_chats.py -v      (offline checks, then the PHP-versus-Python comparison when php is installed)
"""
import io
import shutil
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.harness import OfflineCase  # noqa: E402

HEART = "\u2764\ufe0f"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0000003010100c9fe92ef0000000049454e44ae426082")


class ChatsOffline(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b, cls.c = cls.user("ann_c"), cls.user("ben_c"), cls.user("cy_c")

    def setUp(self):
        for t in ("messages", "dmstate", "dmpref", "mreact", "mreq", "mblocks", "masks", "blocks", "friends", "typing", "gmessages", "gmembers", "gchats", "attlog"):
            self.db.execute("DELETE FROM " + t)
        self.db.execute("UPDATE users SET dm='everyone'")
        self.db.execute("UPDATE users SET dm='' WHERE dm IS NULL")

    def masque(self, who, name):
        self.db.execute("INSERT INTO masks(uid,name,ts) VALUES(?,?,?)", (self.uid(who), name, 1))

    def test_python_owns_these_actions(self):
        from masque.actions import load_all
        mine = {"inbox", "thread", "typing", "send", "msearch", "editm", "delm", "react", "rxwho", "pinm", "setpn", "setbg", "mreq"}
        self.assertEqual(mine - set(load_all().names()), set())

    def test_send_thread_and_inbox(self):
        a, b = self.a, self.b
        self.assertEqual(a.post("send", to="ben_c", txt="  hello  ")[1], {"ok": 1})
        self.assertEqual(a.post("send", to="ben_c", txt="")[0].status_code, 400)
        self.assertEqual(a.post("send", to="ann_c", txt="me")[0].status_code, 400)
        self.assertEqual(a.post("send", to="nobody_c", txt="x")[0].status_code, 404)
        inbox = b.post("inbox")[1]
        self.assertEqual([(c["name"], c["txt"], c["un"], c["mine"], c["mk"], c["ms"], c["st"]) for c in inbox["chats"]], [("ann_c", "hello", 1, 0, 0, 0, "off")])
        self.assertEqual(inbox["inb"], 1)
        j = b.get("a=thread&u=ann_c")[1]
        self.assertEqual([(x["txt"], x["mine"], x["rx"], x["rq"]) for x in j["msgs"]], [("hello", 0, [], None)])
        self.assertEqual((j["u"]["name"], j["u"]["mk"], j["u"]["pn"], j["u"]["bg"], j["as"], j["mb"]), ("ann_c", 0, "", "", 0, 0))
        self.assertNotIn("id", j["u"])
        self.assertEqual(b.post("inbox")[1]["chats"][0]["un"], 0)  # opening the chat marked it read
        self.assertEqual(a.get("a=thread&u=nobody_c")[0].status_code, 404)

    def test_reply_edit_delete(self):
        a, b = self.a, self.b
        a.post("send", to="ben_c", txt="one")
        mid = self.val("SELECT id FROM messages")
        b.post("send", to="ann_c", txt="two", rp=str(mid))
        self.assertEqual(b.post("send", to="ann_c", txt="x", rp="9999")[1]["e"], "The message you are replying to is gone.")
        msgs = a.get("a=thread&u=ben_c")[1]["msgs"]
        self.assertEqual(msgs[1]["rq"]["t"], "one")
        self.assertEqual(msgs[1]["rq"]["mine"], 1)
        r = a.post("editm", id=str(mid), txt="one!")[1]
        self.assertEqual(r["txt"], "one!")
        self.assertEqual(b.post("editm", id=str(mid), txt="hack")[0].status_code, 404)  # not yours
        self.assertEqual(a.post("editm", id=str(mid), txt="")[0].status_code, 400)
        self.assertEqual(a.post("editm", id=str(mid), txt=":gi:abcdefgh:")[0].status_code, 400)
        a.post("delm", id=str(mid))
        self.assertEqual(self.val("SELECT COUNT(*) FROM messages"), 1)
        self.assertEqual(b.get("a=thread&u=ann_c")[1]["msgs"][0]["rq"], {"id": mid, "gone": 1})

    def test_send_rules(self):
        a, b, c = self.a, self.b, self.c
        self.db.execute("INSERT INTO blocks(a,b) VALUES(?,?)", (self.uid("ben_c"), self.uid("ann_c")))
        self.assertEqual(a.post("send", to="ben_c", txt="hi")[0].status_code, 403)
        self.db.execute("DELETE FROM blocks")
        self.db.execute("UPDATE users SET dm='friends' WHERE name='cy_c'")
        self.assertEqual(a.post("send", to="cy_c", txt="hi")[1]["e"], "This person only accepts messages from friends.")
        self.db.execute("INSERT INTO friends(a,b,st,ts) VALUES(?,?,1,1)", (self.uid("ann_c"), self.uid("cy_c")))
        self.assertEqual(a.post("send", to="cy_c", txt="hi")[1], {"ok": 1})
        self.assertEqual(a.post("send", to="ben_c", txt="x", **{"as": "mask"})[1]["e"], "You do not have a Masque.")

    def test_masque_requests(self):
        a, b = self.a, self.b
        self.masque("ben_c", "Phantom")
        self.assertEqual(a.post("send", to="Phantom", txt="who are you")[1], {"ok": 1})
        ben = b.post("inbox")[1]
        self.assertEqual(ben["chats"], [])  # held until accepted
        self.assertEqual([(r["name"], r["mk"], r["cnt"], r["txt"]) for r in ben["reqs"]], [("ann_c", 0, 1, "who are you")])
        self.assertEqual(b.post("mreq", u="nobody_c", act="accept")[0].status_code, 404)
        self.assertEqual(b.post("mreq", u="ann_c", pm="0", act="accept")[1], {"ok": 1})  # accepts ann's request: the message was to ben's Masque
        self.assertEqual(self.sql("SELECT st FROM mreq")[0]["st"], 1)
        self.db.execute("UPDATE masks SET inb=0")
        self.assertEqual(self.c.post("send", to="Phantom", txt="hi")[1]["e"], "This Masque is not accepting new messages.")
        self.assertEqual(a.post("send", to="Phantom", txt="again")[1]["e"], "This Masque is not accepting new messages.")  # ann writing first does not count
        self.db.execute("INSERT INTO messages(a,b,txt,ts,fm,tm) VALUES(?,?,?,?,1,0)", (self.uid("ben_c"), self.uid("ann_c"), "the Masque wrote first", 5))
        self.assertEqual(a.post("send", to="Phantom", txt="again")[1], {"ok": 1})  # the Masque already spoke to ann, so she may answer
        self.db.execute("INSERT INTO mblocks(a,kid) VALUES(?,?)", (self.uid("ben_c"), self.val("SELECT id FROM masks")))

    def test_mask_sender_hides_account_rules(self):
        a, b = self.a, self.b
        self.masque("ann_c", "Wraith")
        self.db.execute("UPDATE users SET dm='friends' WHERE name='ben_c'")
        self.assertEqual(a.post("send", to="ben_c", txt="x", **{"as": "mask"})[1]["e"], "This person only accepts messages from friends.")
        self.db.execute("UPDATE users SET dm='' WHERE name='ben_c'")
        self.db.execute("INSERT INTO blocks(a,b) VALUES(?,?)", (self.uid("ben_c"), self.uid("ann_c")))
        self.assertEqual(a.post("send", to="ben_c", txt="x", **{"as": "mask"})[1], {"ok": 1})  # account blocks never apply to a Masque sender
        self.db.execute("INSERT INTO mblocks(a,kid) VALUES(?,?)", (self.uid("ben_c"), self.val("SELECT id FROM masks")))
        self.assertEqual(a.post("send", to="ben_c", txt="x", **{"as": "mask"})[1]["e"], "You cannot message this person.")

    def test_react_and_pin(self):
        a, b = self.a, self.b
        a.post("send", to="ben_c", txt="one")
        mid = str(self.val("SELECT id FROM messages"))
        self.assertEqual(b.post("react", id=mid, e=HEART)[1], {"rx": [{"e": HEART, "n": 1, "me": 1}]})
        self.assertEqual(a.post("react", id=mid, e="\U0001f525")[1]["rx"][0]["n"], 1)
        self.assertEqual(len(a.post("react", id=mid, e="\U0001f525")[1]["rx"]), 1)  # same emoji again takes it back
        self.assertEqual(b.post("react", id=mid, e="x")[0].status_code, 400)
        self.assertEqual(self.c.post("react", id=mid, e=HEART)[0].status_code, 404)
        self.assertEqual(a.post("pinm", id=mid)[1]["pin"] > 0, True)
        self.assertEqual([p["t"] for p in b.get("a=thread&u=ann_c")[1]["pins"]], ["one"])
        self.assertEqual(b.post("pinm", id=mid)[1], {"pin": 0})
        for n in range(5):
            a.post("send", to="ben_c", txt="m%d" % n)
        for r in self.sql("SELECT id FROM messages"):
            a.post("pinm", id=str(r["id"]))
        self.assertEqual(self.val("SELECT COUNT(*) FROM messages WHERE pin>0"), 5)
        extra = a.post("send", to="ben_c", txt="extra")
        self.assertEqual(a.post("pinm", id=str(self.val("SELECT MAX(id) FROM messages")))[1]["e"], "You can pin up to 5 messages. Unpin one first.")

    def test_nickname_background_and_search(self):
        a = self.a
        a.post("send", to="ben_c", txt="100% sure_thing")
        a.post("send", to="ben_c", txt="plain")
        self.assertEqual(a.post("setpn", u="ben_c", nick="  Big   Ben  ")[1], {"pn": "Big Ben"})
        self.assertEqual(a.post("setpn", u="ann_c", nick="me")[0].status_code, 404)
        self.assertEqual(a.post("setbg", u="ben_c", bg="sky")[1], {"bg": "sky"})
        self.assertEqual(a.post("setbg", u="ben_c", bg="nope")[0].status_code, 400)
        j = a.get("a=thread&u=ben_c")[1]
        self.assertEqual((j["u"]["pn"], j["u"]["bg"]), ("Big Ben", "sky"))
        self.assertEqual(a.post("inbox")[1]["chats"][0]["pn"], "Big Ben")
        self.assertEqual([x["txt"] for x in a.get("a=msearch&u=ben_c&q=100%25")[1]["res"]], ["100% sure_thing"])
        self.assertEqual(a.get("a=msearch&u=ben_c&q=%25%25")[1]["res"], [])  # wildcards are literal
        self.assertEqual(a.get("a=msearch&u=ben_c&q=p")[1], {"res": []})  # too short
        self.assertEqual(a.get("a=msearch&u=nobody_c&q=plain")[0].status_code, 404)
        a.post("cdel", u="ben_c")
        self.assertEqual(a.get("a=msearch&u=ben_c&q=plain")[1]["res"], [])  # deleted-for-me history is not searched

    def test_castle_backgrounds_close_after_the_event(self):
        a = self.a
        a.post("send", to="ben_c", txt="x")
        import os
        os.environ["CASTLE_END"] = "1"
        try:
            self.assertEqual(a.post("setbg", u="ben_c", bg="castle")[0].status_code, 403)
            self.db.execute("INSERT INTO dmpref(uid,oid,ps,bg) VALUES(?,?,0,'castle')", (self.uid("ann_c"), self.uid("ben_c")))
            self.assertEqual(a.post("setbg", u="ben_c", bg="castle")[1], {"bg": "castle"})  # keeping what you already have is fine
            self.assertEqual(a.post("setbg", u="ben_c", bg="castlepaint")[0].status_code, 403)
            self.assertEqual(a.post("setbg", u="ben_c", bg="")[1], {"bg": ""})
        finally:
            del os.environ["CASTLE_END"]

    def test_typing_and_around(self):
        a, b = self.a, self.b
        self.assertEqual(a.post("typing", to="ben_c")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM typing"), 1)
        self.assertEqual(b.get("a=live&k=d&u=ann_c")[1]["ty"], 1)
        self.assertEqual(a.post("typing", to="ben_c", off="1")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM typing"), 0)
        self.assertEqual(a.post("typing", to="nobody_c")[1], {"ok": 0})
        self.assertEqual(a.post("typing", k="g", gid="77")[1], {"ok": 0})  # not a member
        for n in range(120):
            self.db.execute("INSERT INTO messages(a,b,txt,ts) VALUES(?,?,?,?)", (self.uid("ann_c"), self.uid("ben_c"), "m%d" % n, 1000 + n))
        first = self.val("SELECT MIN(id) FROM messages")
        j = b.get("a=thread&u=ann_c")[1]["msgs"]
        self.assertEqual((len(j), j[-1]["txt"]), (100, "m119"))
        j = b.get("a=thread&u=ann_c&around=%d" % (first + 10))[1]["msgs"]
        self.assertEqual(j[-1]["id"], first + 50)

    def test_attachment_and_sticker(self):
        a = self.a
        r, j = a.post("send", to="ben_c", txt="", files={"img": (io.BytesIO(PNG), "p.png")})
        self.assertEqual(j, {"ok": 1})
        img = self.val("SELECT img FROM messages")
        self.assertRegex(img, r"^[a-f0-9]{24}\.png$")
        self.assertTrue((self.tmp / "up" / img).exists())
        mid = str(self.val("SELECT id FROM messages"))
        self.assertEqual(a.post("send", to="ben_c", txt=":sti:0123456789abcdef:")[1]["e"], "That sticker is no longer available.")
        self.assertEqual(a.post("send", to="ben_c", txt=":stk:wave:")[1], {"ok": 1})
        a.post("delm", id=mid)
        self.assertFalse((self.tmp / "up" / img).exists())

    def test_rxwho_names_masques_not_accounts(self):
        a, b = self.a, self.b
        ai, bi = self.uid("ann_c"), self.uid("ben_c")
        self.masque("ben_c", "Phantom")
        self.db.execute("INSERT INTO gchats(id,name,owner,ts) VALUES(1,'g',?,1)", (ai,))
        self.db.execute("INSERT INTO gmembers(gid,uid,pm) VALUES(1,?,0),(1,?,1)", (ai, bi))
        self.db.execute("INSERT INTO gmessages(id,gid,uid,txt,ts) VALUES(1,1,?, 'hi',1)", (ai,))
        self.db.execute("INSERT INTO mreact(k,mid,uid,e) VALUES('g',1,?,?),('g',1,?,?)", (ai, HEART, bi, HEART))
        j = a.get("a=rxwho&id=1")[1]["rx"]
        self.assertEqual([(w["name"], w["mk"], w["me"]) for w in j[0]["w"]], [("ann_c", 0, 1), ("Phantom", 1, 0)])
        self.assertEqual(self.c.get("a=rxwho&id=1")[0].status_code, 404)  # not a member


if __name__ == "__main__":
    unittest.main()
