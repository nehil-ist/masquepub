#!/usr/bin/env python3
"""Step 6: the background jobs (backups, expired posts, tidy, stkgc, streak reminders).   python3 -I tests/test_background.py -v
Needs no PHP: each job is run directly (Scheduler.tick() for the timing test)."""
import dataclasses
import sqlite3
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from masque import background as bg  # noqa: E402
from masque.notify import PushQueue  # noqa: E402
from tests.harness import OfflineCase  # noqa: E402

DAY = 86400


class BackgroundTest(OfflineCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctx = bg.BackgroundContext(cls.cfg)
        cls.ann, cls.ben = cls.user("ann_bg"), cls.user("ben_bg")
        cls.ann_id, cls.ben_id = cls.uid("ann_bg", cls), cls.uid("ben_bg", cls)

    @staticmethod
    def uid(name, cls=None):
        return cls.db.execute("SELECT id FROM users WHERE name=?", (name,)).fetchone()[0]

    def push_log(self, job):
        """Run job.run() with the push flush replaced by a recorder; returns what would have been sent."""
        sent = []
        def record(q):
            sent.extend(q._queue)
            q._queue = []
        with mock.patch.object(PushQueue, "flush", record):
            job.run()
        return sent

    def add_push(self, uid):
        self.db.execute("INSERT OR REPLACE INTO pushsubs(uid,ep,k,a,ts) VALUES(?,?,?,?,?)", (uid, "https://fcm.googleapis.com/x/%d" % uid, "bad", "bad", 1))

    # -- backups --
    def test_backup_makes_prunes_and_waits(self):
        cfg = dataclasses.replace(self.cfg, backup_keep=2, backup_hours=24)
        job = bg.BackupJob(bg.BackgroundContext(cfg))
        folder = self.tmp / "backups"
        folder.mkdir(exist_ok=True)
        for n in ("app-20200101-000000.db", "app-20200102-000000.db"):
            (folder / n).write_bytes(b"old")
        job.run()
        files = sorted(p.name for p in folder.glob("app-*.db"))
        self.assertEqual(len(files), 2)
        self.assertNotIn("app-20200101-000000.db", files)  # oldest pruned
        newest = folder / files[-1]
        self.assertEqual(sqlite3.connect(newest).execute("SELECT COUNT(*) FROM users").fetchone()[0], 2)
        job.run()  # within BACKUP_HOURS: nothing new
        self.assertEqual(sorted(p.name for p in folder.glob("app-*.db")), files)
        (folder / ".last").touch()
        import os
        os.utime(folder / ".last", (time.time() - 90000, time.time() - 90000))
        time.sleep(1.1)  # the file name has second resolution
        job.run()
        self.assertNotEqual(sorted(p.name for p in folder.glob("app-*.db")), files)

    def test_backup_off(self):
        cfg = dataclasses.replace(self.cfg, backup_keep=0)
        (self.tmp / "backups" / ".last").unlink(missing_ok=True)
        before = set((self.tmp / "backups").glob("app-*.db")) if (self.tmp / "backups").exists() else set()
        bg.BackupJob(bg.BackgroundContext(cfg)).run()
        after = set((self.tmp / "backups").glob("app-*.db")) if (self.tmp / "backups").exists() else set()
        self.assertEqual(before, after)

    # -- expired posts --
    def test_expired_posts_are_removed_with_everything(self):
        photo = "a" * 24 + ".png"
        (self.tmp / "up" / photo).write_bytes(b"x")
        now = int(time.time())
        self.db.execute("INSERT INTO posts(id,uid,cap,img,ts,exp) VALUES(9001,?,?,?,?,?)", (self.ann_id, "gone soon", photo, now - 100, now - 10))
        self.db.execute("INSERT INTO posts(id,uid,cap,ts,exp) VALUES(9002,?,?,?,?)", (self.ann_id, "still here", now - 100, now + 3600))
        self.db.execute("INSERT INTO posts(id,uid,cap,ts,exp) VALUES(9003,?,?,?,0)", (self.ann_id, "forever", now - 100))
        self.db.execute("INSERT INTO likes(uid,pid) VALUES(?,9001)", (self.ben_id,))
        self.db.execute("INSERT INTO comments(pid,uid,txt,ts) VALUES(9001,?,?,?)", (self.ben_id, "c", now))
        self.db.execute("INSERT INTO saves(uid,pid,ts) VALUES(?,9001,?)", (self.ben_id, now))
        bg.ExpiredPostsJob(self.ctx).run()
        self.assertEqual([r["id"] for r in self.sql("SELECT id FROM posts WHERE id IN (9001,9002,9003) ORDER BY id")], [9002, 9003])
        self.assertEqual(self.val("SELECT COUNT(*) FROM likes WHERE pid=9001"), 0)
        self.assertEqual(self.val("SELECT COUNT(*) FROM comments WHERE pid=9001"), 0)
        self.assertEqual(self.val("SELECT COUNT(*) FROM saves WHERE pid=9001"), 0)  # by tidy
        self.assertFalse((self.tmp / "up" / photo).exists())

    # -- tidy --
    def test_tidy_job(self):
        self.db.execute("INSERT INTO saves(uid,pid,ts) VALUES(?,424242,1)", (self.ann_id,))
        bg.TidyJob(self.ctx).run()
        self.assertEqual(self.val("SELECT COUNT(*) FROM saves WHERE pid=424242"), 0)

    # -- sticker clean-up --
    def test_stkgc(self):
        (self.tmp / "stk").mkdir(exist_ok=True)
        old = int(time.time()) - 2 * DAY
        for i in ("s1", "s2", "s3", "s4"):
            self.db.execute("INSERT INTO stkimg(id,sha,ext,sz,ts) VALUES(?,?,?,?,?)", (i, i, "png", 1, old))
            (self.tmp / "stk" / (i + ".png")).write_bytes(b"x")
        self.db.execute("INSERT INTO stkfav(uid,ref,ts) VALUES(?,?,?)", (self.ann_id, "i:s2", 1))  # a favourite
        self.db.execute("INSERT INTO messages(a,b,txt,ts) VALUES(?,?,?,?)", (self.ann_id, self.ben_id, ":sti:s3:", old))  # still in a chat
        self.db.execute("DELETE FROM site WHERE k='stkgc'")
        bg.StickerGcJob(self.ctx).run()
        left = {r["id"] for r in self.sql("SELECT id FROM stkimg WHERE id IN ('s1','s2','s3','s4')")}
        self.assertEqual(left, {"s2", "s3"})
        self.assertEqual(sorted(p.name for p in (self.tmp / "stk").glob("s?.png")), ["s2.png", "s3.png"])
        self.assertGreater(self.val("SELECT ts FROM stkimg WHERE id='s3'"), old)  # given another day
        # once a day: a second run does nothing even for new candidates
        self.db.execute("INSERT INTO stkimg(id,sha,ext,sz,ts) VALUES('s5','s5','png',1,?)", (old,))
        bg.StickerGcJob(self.ctx).run()
        self.assertEqual(self.val("SELECT COUNT(*) FROM stkimg WHERE id='s5'"), 1)

    # -- streak reminders --
    def at(self, hours_left, day):
        return mock.patch("time.time", return_value=(day + 1) * DAY - hours_left * 3600 + 5)

    def test_prompt_streak_reminder(self):
        d = 30000
        uid = self.uid("ann_bg", self)
        self.add_push(uid)
        for x in (d - 1, d - 2, d - 3):
            self.db.execute("INSERT OR IGNORE INTO pstreak(uid,day) VALUES(?,?)", (uid, x))
        job = bg.PromptStreakReminder(self.ctx)
        with self.at(5, d):  # more than 3 hours left: too early
            self.assertEqual(self.push_log(job), [])
        self.db.execute("DELETE FROM rl WHERE k='sweep:streak'")
        with self.at(2, d):
            sent = self.push_log(job)
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0][0], uid)
            self.assertIn("3-day streak ends in about 2 hours", sent[0][1])
            self.assertNotIn("ann_bg", sent[0][1])  # never a name
            self.assertEqual(self.val("SELECT COUNT(*) FROM streakping WHERE uid=? AND day=?", uid, d), 1)
            self.assertEqual(self.push_log(job), [])  # the 5-minute site-wide limit
            self.db.execute("DELETE FROM rl WHERE k='sweep:streak'")
            self.assertEqual(self.push_log(job), [])  # and one per person per day

    def test_prompt_streak_reminder_respects_quiet_hours_mute_and_answers(self):
        d = 30100
        uid = self.uid("ben_bg", self)
        self.add_push(uid)
        for x in (d - 1, d - 2):
            self.db.execute("INSERT OR IGNORE INTO pstreak(uid,day) VALUES(?,?)", (uid, x))
        job = bg.PromptStreakReminder(self.ctx)
        # quiet hours (all day): nothing sent and the person is NOT marked as reminded
        self.db.execute("INSERT OR REPLACE INTO nprefs(uid,muted,pop,qon,qfrom,qto,tz) VALUES(?,'',1,1,0,1439,0)", (uid,))
        with self.at(1, d):
            self.db.execute("DELETE FROM rl WHERE k='sweep:streak'")
            self.assertEqual(self.push_log(job), [])
            self.assertEqual(self.val("SELECT COUNT(*) FROM streakping WHERE uid=? AND day=?", uid, d), 0)
            # muted group: marked, not sent
            self.db.execute("UPDATE nprefs SET qon=0, muted='streak' WHERE uid=?", (uid,))
            self.db.execute("DELETE FROM rl WHERE k='sweep:streak'")
            self.assertEqual(self.push_log(job), [])
            self.assertEqual(self.val("SELECT COUNT(*) FROM streakping WHERE uid=? AND day=?", uid, d), 1)
        # already answered today: not a candidate
        d2 = d + 1
        for x in (d2, d2 - 1, d2 - 2):
            self.db.execute("INSERT OR IGNORE INTO pstreak(uid,day) VALUES(?,?)", (uid, x))
        self.db.execute("UPDATE nprefs SET muted='' WHERE uid=?", (uid,))
        with self.at(1, d2):
            self.db.execute("DELETE FROM rl WHERE k='sweep:streak'")
            self.assertEqual(self.push_log(job), [])

    def test_chat_streak_reminder(self):
        d = 30200
        a, b = self.uid("ann_bg", self), self.uid("ben_bg", self)
        self.add_push(a)
        self.db.execute("DELETE FROM nprefs WHERE uid=?", (a,))
        self.db.execute("DELETE FROM messages")
        for day in (d - 2, d - 1):  # both people wrote on both days, nothing yet today
            for frm, to in ((a, b), (b, a)):
                self.db.execute("INSERT INTO messages(a,b,txt,ts,fm,tm) VALUES(?,?,?,?,0,0)", (frm, to, "hi", day * DAY + 1000))
        job = bg.ChatStreakReminder(self.ctx)
        with self.at(2, d):
            self.db.execute("DELETE FROM rl WHERE k='sweep:cstreak'")
            sent = self.push_log(job)
            self.assertEqual([s[0] for s in sent], [a])  # ben has no push subscription
            self.assertIn("2-day chat streak ends in about 2 hours", sent[0][1])
            self.assertIn('"u":"./#/m"', sent[0][1])
            self.assertEqual(self.val("SELECT COUNT(*) FROM cstreakping WHERE uid=? AND day=?", a, d), 1)
            self.db.execute("DELETE FROM rl WHERE k='sweep:cstreak'")
            self.assertEqual(self.push_log(job), [])

    # -- scheduler --
    def test_scheduler_runs_due_jobs_and_survives_errors(self):
        calls = []

        class Good(bg.Job):
            name, interval = "good", 100

            def run(self):
                calls.append("good")

        class Bad(bg.Job):
            name, interval = "bad", 100

            def run(self):
                calls.append("bad")
                raise RuntimeError("boom")

        s = bg.Scheduler([Bad(self.ctx), Good(self.ctx)])
        with self.assertLogs("masque.background", "ERROR"):
            s.tick(1000)
        s.tick(1050)  # not due
        s.tick(1101)
        with self.assertLogs("masque.background", "ERROR"):
            s.tick(1101 + 100)
        self.assertEqual(calls, ["bad", "good"] * 3)

    def test_session_gc(self):
        import os
        folder = self.cfg.session_dir
        folder.mkdir(parents=True, exist_ok=True)
        old, new = folder / "sess_oldoldoldoldoldoldoldold", folder / "sess_newnewnewnewnewnewnewnew"
        for f in (old, new):
            f.write_text("x")
        t = time.time() - 31 * DAY
        os.utime(old, (t, t))
        bg.SessionGcJob(self.ctx).run()
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_default_jobs(self):
        names = [j.name for j in bg.default_jobs(self.ctx)]
        self.assertEqual(names, ["backup", "expired-posts", "tidy", "stkgc", "sessions", "rooms", "streak-reminder", "chat-streak-reminder"])


if __name__ == "__main__":
    unittest.main()
