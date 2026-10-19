"""Prompt streaks and chat streaks, worked out from rows already stored (PHP: streak_calc, cs_run, cs_dm, cs_group)."""
import math
import time

FREEZE_PRICE = 40  # Sigils per saved day (PHP FZ_PRICE)


class Streaks:
    """Prompt streaks. A day counts when you answered the prompt (table pstreak) or saved it with a streak freeze (table sfreeze).
    A frozen day keeps the chain unbroken but is not itself counted, so the streak number is always answered days.
    Streak days are UTC days, the same day the prompt changes on. A streak is alive while its newest covered day is today or yesterday.
    offer = the most recent gap of 1 to 3 missed days (all within the last 3 days) that sits right after a run of at least 3 answered days."""

    def __init__(self, db):
        self.db = db

    def calc(self, uid, d=None) -> dict:
        d = int(time.time()) // 86400 if d is None else int(d)
        ans = [int(r[0]) for r in self.db.query("SELECT day FROM pstreak WHERE uid=? ORDER BY day DESC LIMIT 1000", (uid,)).fetchall()]
        fzd = [int(r[0]) for r in self.db.query("SELECT day FROM sfreeze WHERE uid=? ORDER BY day DESC LIMIT 400", (uid,)).fetchall()]
        A, F = set(ans), set(fzd)
        allv = sorted(set(ans) | set(fzd), reverse=True)
        runs = []  # newest first: [top day, bottom day, answered days in it]
        prev = None
        for x in allv:
            if prev is not None and x == prev - 1:
                runs[-1][1] = x
                if x in A:
                    runs[-1][2] += 1
            else:
                runs.append([x, x, 1 if x in A else 0])
            prev = x
        best = max([r[2] for r in runs] or [0])
        cur = runs[0][2] if runs and runs[0][0] >= d - 1 else 0
        offer = None
        if runs:
            x = y = cnt = join = None
            if runs[0][0] < d - 1:
                x, y, cnt, join = d, runs[0][0], runs[0][2], 0
            elif len(runs) > 1:
                x, y, cnt, join = runs[0][1], runs[1][0], runs[1][2], runs[0][2]
            if x is not None:
                gap = x - y - 1
                if 1 <= gap <= 3 and y >= d - 4 and cnt >= 3:
                    offer = {"days": list(range(y + 1, x)), "n": gap, "price": FREEZE_PRICE * gap, "was": cnt, "after": cnt + join}
        wk = [1 if (d - j) in A else (2 if (d - j) in F else 0) for j in range(6, -1, -1)]
        return {"cur": cur, "best": best, "wk": wk, "icy": 1 if (cur > 0 and d not in A and (d - 1) in F) else 0, "offer": offer}


class ChatStreaks:
    """Chat streaks. Direct chat: a day counts when BOTH people sent something. Group: a day counts when enough different members wrote."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def need(members) -> int:
        members = max(1, int(members))
        return min(members, min(3, max(2, math.ceil(members / 2))))

    @staticmethod
    def run(days, now) -> dict:
        td = now // 86400
        if not days or int(days[0]) < td - 1:
            return {"n": 0, "dn": 0, "lf": 0}
        n = 1
        for k in range(1, len(days)):
            if int(days[k]) != int(days[k - 1]) - 1:
                break
            n += 1
        dn = 1 if int(days[0]) == td else 0
        return {"n": n, "dn": dn, "lf": 0 if dn else (td + 1) * 86400 - now}

    def direct(self, me, ms, oid, ps) -> dict:
        days = [int(r[0]) for r in self.db.query(
            "SELECT CAST(ts/86400 AS INTEGER) d FROM messages WHERE (a=? AND fm=? AND b=? AND tm=?) OR (a=? AND fm=? AND b=? AND tm=?) "
            "GROUP BY d HAVING SUM(a=?)>0 AND SUM(a!=?)>0 ORDER BY d DESC LIMIT 400",
            (me, ms, oid, ps, oid, ps, me, ms, me, me)).fetchall()]
        return self.run(days, int(time.time()))

    def group(self, gid) -> dict:
        now = int(time.time())
        mem = int(self.db.value("SELECT COUNT(*) FROM gmembers WHERE gid=?", (gid,), 0))
        need = self.need(mem)
        days = [int(r[0]) for r in self.db.query(
            "SELECT CAST(ts/86400 AS INTEGER) d FROM gmessages WHERE gid=? GROUP BY d HAVING COUNT(DISTINCT uid)>=? ORDER BY d DESC LIMIT 400",
            (gid, need)).fetchall()]
        r = self.run(days, now)
        r["nd"] = need
        r["tc"] = int(self.db.value("SELECT COUNT(DISTINCT uid) FROM gmessages WHERE gid=? AND ts>=?", (gid, now // 86400 * 86400), 0))
        return r
