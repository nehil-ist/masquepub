"""Work that happens on a timer instead of inside a request (PHP ran it after requests: backups, expired posts, tidy, stkgc, streak reminders).

Each job is a small class with a `name`, an `interval` (seconds between runs) and `run()`. The `Scheduler` runs them from one background
thread started by serve.py. A job that raises is logged and tried again at its next turn; it never stops the others."""
import json
import logging
import secrets
import threading
import time
from abc import ABC, abstractmethod
from functools import cached_property
from pathlib import Path

from .database import Database
from .security import RateLimiter

log = logging.getLogger("masque.background")
DAY = 86400


class BackgroundContext:
    """The parts of a request Context that jobs need (settings, database, file removal, limits), without a request."""

    def __init__(self, cfg, db: Database = None):
        self.cfg = cfg
        self.db = db or Database(cfg.db_path)

    @cached_property
    def media(self):
        from .media import Uploads
        return Uploads(self)

    @cached_property
    def limiter(self):
        return RateLimiter(self.db, None)  # count() and add() only; nobody is signed in

    @cached_property
    def prefs(self):
        from .notify import NotifyPrefs
        return NotifyPrefs(self.db)


class Job(ABC):
    name = ""
    interval = 60  # seconds between runs

    def __init__(self, ctx: BackgroundContext):
        self.ctx, self.cfg, self.db = ctx, ctx.cfg, ctx.db
        self.next_run = 0.0

    @abstractmethod
    def run(self): ...


class BackupService:
    """One consistent copy of the database (VACUUM INTO). Photos live in up/ and are not part of it."""

    def __init__(self, cfg, db: Database):
        self.cfg, self.db = cfg, db

    @property
    def folder(self) -> Path:
        return Path(self.cfg.data_dir) / "backups"

    def snapshot(self, path):
        self.db.execute("VACUUM INTO ?", (str(path),))


class BackupJob(Job):
    """A copy every BACKUP_HOURS, keeping the newest BACKUP_KEEP (BACKUP_KEEP=0 turns this off)."""
    name = "backup"
    interval = 600

    def run(self):
        keep, hours = self.cfg.backup_keep, self.cfg.backup_hours
        if keep <= 0:
            return
        svc = BackupService(self.cfg, self.db)
        folder = svc.folder
        marker = folder / ".last"
        if marker.exists() and marker.stat().st_mtime >= time.time() - hours * 3600:
            return
        folder.mkdir(parents=True, exist_ok=True)
        marker.touch()  # touched first, like PHP, so a failing backup is retried next period rather than every tick
        svc.snapshot(folder / ("app-%s.db" % time.strftime("%Y%m%d-%H%M%S", time.gmtime())))
        old = sorted(folder.glob("app-*.db"))
        for f in old[:max(0, len(old) - keep)]:
            try:
                f.unlink()
            except OSError:
                pass


class ExpiredPostsJob(Job):
    """Disappearing posts: anything past its expiry is deleted with its photos, likes and comments."""
    name = "expired-posts"
    interval = 60

    def run(self):
        from .actions.posts import PostFiles
        files = PostFiles(self.ctx)
        for pid in self.db.query("SELECT id FROM posts WHERE exp>0 AND exp<=? LIMIT 50", (int(time.time()),)).fetchall():
            files.delete_post(int(pid[0]))


class TidyJob(Job):
    """Removes rows that point at things that no longer exist (the request actions run this after their own deletes)."""
    name = "tidy"
    interval = 3600

    def run(self):
        from .tidy import Tidy
        Tidy(self.db).run()


class RoomSweepJob(Job):
    """Closes finished rooms and deletes their messages (PHP ran this inside the room actions)."""
    name = "rooms"
    interval = 60

    def run(self):
        from .rooms import Rooms
        Rooms(self.db).sweep()


class StickerGcJob(Job):
    """Sticker pictures nobody kept (not a favourite, not in any chat message) are deleted a day after they were sent. At most once a day."""
    name = "stkgc"
    interval = 3600

    def run(self):
        db, now = self.db, int(time.time())
        if int(db.value("SELECT v FROM site WHERE k='stkgc'", (), 0) or 0) > now - DAY:
            return
        db.execute("INSERT OR REPLACE INTO site(k,v) VALUES('stkgc',?)", (str(now),))
        rows = db.all("SELECT id,ext FROM stkimg WHERE ts<? AND 'i:'||id NOT IN (SELECT ref FROM stkfav) ORDER BY ts LIMIT 100", (now - DAY,))
        if not rows:
            return
        tx = [":sti:%s:" % r["id"] for r in rows]
        marks = ",".join("?" * len(tx))
        used = {r[0] for t in ("messages", "gmessages") for r in db.query("SELECT DISTINCT txt FROM %s WHERE txt IN (%s)" % (t, marks), tx).fetchall()}
        for r in rows:
            if ":sti:%s:" % r["id"] in used:
                db.execute("UPDATE stkimg SET ts=? WHERE id=?", (now, r["id"]))
                continue
            db.execute("DELETE FROM stkimg WHERE id=?", (r["id"],))
            try:
                (Path(self.cfg.data_dir) / "stk" / ("%s.%s" % (r["id"], r["ext"]))).unlink()
            except OSError:
                pass


class SessionGcJob(Job):
    """Sign-in session files untouched for 30 days are deleted (PHP's session.gc_maxlifetime did this). Every save rewrites the file, so its age is time since last use."""
    name = "sessions"
    interval = 3600
    MAX_AGE = 30 * DAY

    def run(self):
        folder, cutoff = self.cfg.session_dir, time.time() - self.MAX_AGE
        if not folder.is_dir():
            return
        for f in folder.glob("sess_*"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass  # in use or already gone


class StreakReminder(Job, ABC):
    """Streak days are UTC days, so a streak that is alive but not answered today ends at the next 00:00 UTC.
    In the last 3 hours of that day, anyone with push on and a streak of 2+ days gets ONE generic push per day (never a name).
    The sweep runs at most once every 5 minutes site-wide (the `rl` table, shared with PHP). Quiet hours are respected by NOT marking the
    person as reminded while they are quiet, so they get it when quiet hours end if the day is not over yet. Muted group "streak" = off."""
    interval = 300
    sweep_key = ""
    ping_table = ""

    def __init__(self, ctx):
        super().__init__(ctx)
        from .notify import PushQueue
        self.push = PushQueue(ctx.db, ctx.cfg, ctx.prefs)

    def run(self):
        self.ctx.prefs.forget()  # settings change between sweeps
        now = int(time.time())
        d = now // DAY
        left = (d + 1) * DAY - now
        if left > 3 * 3600 or left < 60:
            return
        lim = self.ctx.limiter
        if lim.count(self.sweep_key, 300) >= 1:
            return
        lim.add(self.sweep_key)
        hrs = -(-left // 3600)
        when = "in less than an hour" if hrs <= 1 else "in about %d hours" % hrs
        for uid in self.candidates(d):
            if self.ctx.prefs.quiet(uid):
                continue  # still waiting: try again on the next sweep
            self.db.execute("INSERT OR IGNORE INTO %s VALUES(?,?)" % self.ping_table, (uid, d))
            if self.ctx.prefs.muted(uid, "streak"):
                continue
            n = self.streak_length(uid, d)
            if n >= 2:
                text, url = self.message(n, when)
                self.push.send(uid, "Masque", text, url, "%s-%d" % (self.tag, d))
        if secrets.randbelow(40) == 0:
            self.db.execute("DELETE FROM %s WHERE day<?" % self.ping_table, (d - 3,))
        self.push.flush()

    @abstractmethod
    def candidates(self, d: int) -> list:
        """User ids whose streak ends today and who have not been reminded yet."""

    @abstractmethod
    def streak_length(self, uid: int, d: int) -> int: ...

    @abstractmethod
    def message(self, n: int, when: str): ...


class PromptStreakReminder(StreakReminder):
    name = "streak-reminder"
    sweep_key, ping_table, tag = "sweep:streak", "streakping", "streak"

    def candidates(self, d):
        rows = self.db.query(
            "SELECT y.uid FROM (SELECT uid FROM pstreak WHERE day=? UNION SELECT uid FROM sfreeze WHERE day=?) y "
            "WHERE y.uid IN (SELECT uid FROM pushsubs) "
            "AND y.uid NOT IN (SELECT uid FROM pstreak WHERE day=?) "
            "AND y.uid NOT IN (SELECT uid FROM sfreeze WHERE day=?) "
            "AND y.uid NOT IN (SELECT uid FROM streakping WHERE day=?) LIMIT 300",
            (d - 1, d - 1, d, d, d)).fetchall()
        return [int(r[0]) for r in rows]

    def streak_length(self, uid, d):
        from .streaks import Streaks
        return int(Streaks(self.db).calc(uid, d)["cur"])

    def message(self, n, when):
        return "Your %d-day streak ends %s. Answer today's prompt to keep it going." % (n, when), "./"


class ChatStreakReminder(StreakReminder):
    """Same window, quiet hours and switch, for direct-chat streaks (a day counts when BOTH people wrote). One push per person per UTC day,
    showing the longest streak at risk; never says which chat. Group chats are not included."""
    name = "chat-streak-reminder"
    sweep_key, ping_table, tag = "sweep:cstreak", "cstreakping", "cstreak"

    _best = {}

    def candidates(self, d):
        from .streaks import ChatStreaks
        chats = ChatStreaks(self.db)
        since = (d - 2) * DAY
        rows = self.db.query(
            "WITH bd AS ("
            " SELECT DISTINCT m1.a AS a, m1.fm AS fm, m1.b AS b, m1.tm AS tm, CAST(m1.ts/86400 AS INTEGER) AS d"
            " FROM messages m1"
            " JOIN messages m2 ON m2.a=m1.b AND m2.fm=m1.tm AND m2.b=m1.a AND m2.tm=m1.fm AND CAST(m2.ts/86400 AS INTEGER)=CAST(m1.ts/86400 AS INTEGER)"
            " WHERE m1.ts>=? AND m2.ts>=?) "
            "SELECT DISTINCT y.a, y.fm, y.b, y.tm FROM bd y WHERE y.d=? "
            "AND y.a IN (SELECT uid FROM pushsubs) "
            "AND y.a NOT IN (SELECT uid FROM cstreakping WHERE day=?) "
            "AND EXISTS (SELECT 1 FROM bd z WHERE z.a=y.a AND z.fm=y.fm AND z.b=y.b AND z.tm=y.tm AND z.d=?) "
            "AND NOT EXISTS (SELECT 1 FROM bd t WHERE t.a=y.a AND t.fm=y.fm AND t.b=y.b AND t.tm=y.tm AND t.d=?) LIMIT 600",
            (since, since, d - 1, d, d - 2, d)).fetchall()
        best, seen = {}, {}
        for r in rows:
            u = int(r["a"])
            seen[u] = seen.get(u, 0) + 1
            if seen[u] > 5:
                continue  # a handful of chats per person is plenty to find the longest
            c = chats.direct(u, int(r["fm"]), int(r["b"]), int(r["tm"]))
            if not c["dn"] and c["n"] >= 2:
                best[u] = max(best.get(u, 0), int(c["n"]))
        self._best = best
        return list(best)

    def streak_length(self, uid, d):
        return self._best.get(uid, 0)

    def message(self, n, when):
        return "Your %d-day chat streak ends %s. Send a message to keep it going." % (n, when), "./#/m"


class Scheduler:
    """Runs jobs when they are due, from one daemon thread. `tick()` does one pass (tests call it directly)."""

    def __init__(self, jobs, pause: float = 15.0, ready=None):
        self.jobs, self.pause = list(jobs), pause
        self.ready = ready or (lambda: True)  # PHP makes the database on its first run, so wait for it
        self._stop = threading.Event()
        self._thread = None

    def tick(self, now: float = None):
        now = time.monotonic() if now is None else now
        for job in self.jobs:
            if now < job.next_run:
                continue
            job.next_run = now + job.interval
            try:
                job.run()
            except Exception:
                log.exception("background job %s failed", job.name)

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="masque-background", daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            if self.ready():
                self.tick()
            self._stop.wait(self.pause)


def default_jobs(ctx: BackgroundContext):
    return [BackupJob(ctx), ExpiredPostsJob(ctx), TidyJob(ctx), StickerGcJob(ctx), SessionGcJob(ctx), RoomSweepJob(ctx), PromptStreakReminder(ctx), ChatStreakReminder(ctx)]


def build_scheduler(cfg) -> Scheduler:
    return Scheduler(default_jobs(BackgroundContext(cfg)), ready=cfg.db_path.exists)
