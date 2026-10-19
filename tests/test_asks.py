#!/usr/bin/env python3
"""Step 3e: anonymous questions.   python3 -I tests/test_asks.py -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.harness import OfflineCase  # noqa: E402


class AsksTest(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b, cls.c = cls.user("ann_q"), cls.user("ben_q"), cls.user("cy_q")

    def test_ask_list_delete_answer(self):
        a, b = self.a, self.b
        self.assertEqual(b.post("ask", to="ann_q", txt="  who are you? ")[1], {"ok": 1})
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE uid=? AND kind='ask' AND actor=?", self.uid("ann_q"), self.uid("ann_q")), 1)
        b.post("ask", to="ann_q", txt="second")  # still one unseen alert
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE uid=? AND kind='ask'", self.uid("ann_q")), 1)
        lst = a.post("asks")[1]["list"]
        self.assertEqual([x["txt"] for x in lst], ["second", "who are you?"])
        self.assertEqual(set(lst[0]), {"id", "txt", "ts"})  # sender never shown
        self.assertEqual(a.post("askdel", id=lst[0]["id"])[1], {"ok": 1})
        j = a.post("askans", id=lst[1]["id"], cap="a mask, naturally")[1]
        self.assertEqual((j["ok"], j["hold"]), (1, 0))
        row = self.sql("SELECT cap,aq,uid FROM posts WHERE id=?", j["id"])[0]
        self.assertEqual((row["cap"], row["aq"], row["uid"]), ("a mask, naturally", "who are you?", self.uid("ann_q")))
        self.assertEqual(self.val("SELECT COUNT(*) FROM notifs WHERE uid=? AND kind='answer'", self.uid("ben_q")), 1)
        self.assertEqual(a.post("asks")[1]["list"], [])
        self.assertEqual(a.post("askans", id=lst[1]["id"], cap="again")[0].status_code, 404)

    def test_rules(self):
        a, b, c = self.a, self.b, self.c
        self.assertEqual(c.post("ask", to="nobody_q", txt="hi")[0].status_code, 404)
        self.assertEqual(c.post("ask", to="cy_q", txt="hi")[0].status_code, 400)
        self.assertEqual(c.post("ask", to="ann_q", txt="  ")[0].status_code, 400)
        self.db.execute("UPDATE users SET priv=1 WHERE name='ben_q'")
        self.assertEqual(c.post("ask", to="ben_q", txt="hi")[0].status_code, 403)
        self.db.execute("UPDATE users SET priv=0,askon=0 WHERE name='ben_q'")
        self.assertEqual(c.post("ask", to="ben_q", txt="hi")[0].status_code, 403)
        self.db.execute("UPDATE users SET askon=1 WHERE name='ben_q'")
        for i in range(3):
            self.assertEqual(c.post("ask", to="ben_q", txt="q%d" % i)[0].status_code, 200)
        self.assertEqual(c.post("ask", to="ben_q", txt="q4")[0].status_code, 429)  # 3 a day to one person
        self.db.execute("INSERT INTO blocks(a,b) VALUES(?,?)", (self.uid("ben_q"), self.uid("ann_q")))
        self.assertEqual(a.post("ask", to="ben_q", txt="hi")[0].status_code, 404)


if __name__ == "__main__":
    unittest.main()
