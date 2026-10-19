"""Anonymous questions: ask, asks, askdel, askans (PHP: case 'ask', 'asks', 'askdel', 'askans')."""
from ..php import php_trim
from .base import Action, Context, Reply, registry


@registry.register
class Ask(Action):
    """?a=ask: send an anonymous question (the sender is stored, but never shown to the owner)."""
    name = "ask"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        ctx.limits.lim("ask:%d" % m["id"], 10, 3600, m, 3, 3600)
        txt = php_trim(ctx.form("txt")[:200])
        o = db.one("SELECT id,askon,priv FROM users WHERE name=?", (php_trim(ctx.form("to")),))
        if not o or ctx.rel.blocked(m["id"], o["id"]):
            return Reply.error("No such user.", 404)
        if int(o["id"]) == int(m["id"]):
            return Reply.error("You can't send a question to yourself.", 400)
        if not int(o["askon"]):
            return Reply.error("This person is not taking anonymous questions.", 403)
        if int(o["priv"]) and not ctx.rel.friends(m["id"], o["id"]):
            return Reply.error("Only friends can send questions to a private account.", 403)
        if txt == "":
            return Reply.error("Write a question first.", 400)
        key = "askto:%d:%d" % (m["id"], o["id"])
        if not ctx.users.is_admin(m) and ctx.limiter.count(key, 86400) >= 3:
            return Reply.error("You have already sent this person a few questions today. Try again tomorrow.", 429)
        if int(db.value("SELECT COUNT(*) FROM asks WHERE uid=? AND hid=0", (o["id"],), 0)) >= 100:
            return Reply.error("This person's question box is full right now.", 429)
        ctx.limiter.add(key)
        now = ctx.now
        db.execute("INSERT INTO asks(uid,frm,txt,ts) VALUES(?,?,?,?)", (o["id"], m["id"], txt, now))
        # The alert names the owner as its own actor, so nothing about the sender is stored in it. One unseen alert at a time.
        if not ctx.notes.muted(o["id"], "asks") and not db.value("SELECT 1 FROM notifs WHERE uid=? AND kind='ask' AND seen=0", (o["id"],)):
            db.execute("INSERT INTO notifs(uid,kind,actor,pid,ts) VALUES(?,?,?,?,?)", (o["id"], "ask", o["id"], 0, now))
        return Reply({"ok": 1})


@registry.register
class Asks(Action):
    """?a=asks: my question box."""
    name = "asks"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        return Reply({"list": ctx.db.all("SELECT id,txt,ts FROM asks WHERE uid=? AND hid=0 ORDER BY id DESC LIMIT 100", (m["id"],))})


@registry.register
class AskDelete(Action):
    """?a=askdel"""
    name = "askdel"

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        ctx.db.execute("DELETE FROM asks WHERE id=? AND uid=? AND hid=0", (ctx.int_form("id"), m["id"]))
        return Reply({"ok": 1})


@registry.register
class AskAnswer(Action):
    """?a=askans: answer a question with a post (the question text is saved on the post; the question is removed)."""
    name = "askans"

    def handle(self, ctx: Context) -> Reply:
        db = ctx.db
        m = ctx.users.need()
        ctx.limits.lim("post:%d" % m["id"], 20, 600, m, 5, 3600)
        qid = ctx.int_form("id")
        cap = php_trim(ctx.form("cap")[:300])
        ctx.limits.nolinks(m, cap)
        a = db.one("SELECT txt,frm FROM asks WHERE id=? AND uid=? AND hid=0", (qid, m["id"]))
        if not a:
            return Reply.error("That question is gone.", 404)
        if cap == "":
            return Reply.error("Write an answer first.", 400)
        img = ctx.media.save_img(ctx.file("img"))  # an answer can come with one photo
        with db.transaction():
            cur = db.query("INSERT INTO posts(uid,cap,img,ts,anon,bg,aq,hg) VALUES(?,?,?,?,0,0,?,0)", (m["id"], cap, img, ctx.now, a["txt"]))
            pid = int(cur.lastrowid)
            if img:
                db.execute("INSERT INTO postimgs(pid,pos,img,alt) VALUES(?,?,?,?)", (pid, 0, img, ""))
            db.execute("DELETE FROM asks WHERE id=?", (qid,))
        ctx.tags.set(pid, cap)
        held = ctx.words.apply("post", pid, cap, m)
        if not held:
            ctx.mentions.in_post(pid, cap, m["id"], "", 0, 0)
            ctx.tags.notify_followers(pid, cap, m["id"], 0)
            ctx.notes.note(int(a["frm"]), "answer", m["id"], pid)
        return Reply({"ok": 1, "id": pid, "hold": held})
