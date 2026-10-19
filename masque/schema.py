"""The database tables (PHP: the CREATE TABLE / ALTER TABLE lines at the top of index.php).

TABLES and INDEXES below were dumped from a database PHP had just created (user_version 2), so they are the final shape of every table.
`Schema.apply()` is safe to run on every start: it creates what is missing, adds columns an older database lacks, and applies the one data fix PHP ran each start.
Databases made before PHP's user_version 1 and 2 clean-ups must have been opened by the PHP version once (they have been, on any live site).
"""
import sqlite3

TABLES = [
    "CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT UNIQUE COLLATE NOCASE,pw TEXT,bio TEXT DEFAULT '',em TEXT DEFAULT '🦊',col TEXT DEFAULT '#6b3fa0',cover TEXT DEFAULT '',ts INT, avatar TEXT DEFAULT '', cy INT DEFAULT 50, dm TEXT DEFAULT 'all', priv INT DEFAULT 0, nick TEXT DEFAULT '', ncts INT DEFAULT 0, sv INT DEFAULT 0, rc TEXT DEFAULT '', mail TEXT DEFAULT '', sus INT DEFAULT 0, askon INT DEFAULT 1, la INT DEFAULT 0, pst TEXT DEFAULT '', idl INT DEFAULT 0, tbg TEXT DEFAULT '', tbp TEXT DEFAULT '', tcd TEXT DEFAULT '', tfn TEXT DEFAULT '', tas TEXT DEFAULT '', taf TEXT DEFAULT '', tpl TEXT DEFAULT '', tcf TEXT DEFAULT '', stx TEXT DEFAULT '', stts INT DEFAULT 0, xp INT DEFAULT 0, askp TEXT DEFAULT '', pin INT DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY,uid INT,cap TEXT,img TEXT,ts INT, ed INT DEFAULT 0, anon INT DEFAULT 0, bg INT DEFAULT 0, aq TEXT DEFAULT '', hg INT DEFAULT 1, qp INT DEFAULT 0, pd INT DEFAULT 0, mid INT DEFAULT 0, sens INT DEFAULT 0, hold INT DEFAULT 0, vis INT DEFAULT 0, exp INT DEFAULT 0)",
    'CREATE TABLE IF NOT EXISTS likes(pid INT,uid INT,PRIMARY KEY(pid,uid))',
    'CREATE TABLE IF NOT EXISTS tries(ip TEXT,ts INT)',
    'CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY,pid INT,uid INT,txt TEXT,ts INT,ed INT DEFAULT 0, par INT DEFAULT 0, hold INT DEFAULT 0, mid INT DEFAULT 0)',
    "CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,a INT,b INT,txt TEXT,ts INT,ed INT DEFAULT 0,seen INT DEFAULT 0, img TEXT DEFAULT '', fm INT DEFAULT 0, tm INT DEFAULT 0, rp INT DEFAULT 0, pin INT DEFAULT 0)",
    'CREATE TABLE IF NOT EXISTS friends(a INT,b INT,st INT DEFAULT 0,ts INT,PRIMARY KEY(a,b))',
    'CREATE TABLE IF NOT EXISTS blocks(a INT,b INT,PRIMARY KEY(a,b))',
    'CREATE TABLE IF NOT EXISTS follows(a INT,b INT,ts INT,PRIMARY KEY(a,b))',
    'CREATE TABLE IF NOT EXISTS clikes(cid INT,uid INT,PRIMARY KEY(cid,uid))',
    'CREATE TABLE IF NOT EXISTS posttags(pid INT,tag TEXT,PRIMARY KEY(pid,tag))',
    'CREATE TABLE IF NOT EXISTS notifs(id INTEGER PRIMARY KEY,uid INT,kind TEXT,actor INT,pid INT DEFAULT 0,ts INT,seen INT DEFAULT 0, mid INT DEFAULT 0)',
    'CREATE TABLE IF NOT EXISTS tagfollows(uid INT,tag TEXT,PRIMARY KEY(uid,tag))',
    'CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY,uid INT,kind TEXT,tid INT,why TEXT,ts INT)',
    'CREATE TABLE IF NOT EXISTS badwords(w TEXT PRIMARY KEY,hold INT DEFAULT 0)',
    'CREATE TABLE IF NOT EXISTS polls(pid INT,pos INT,txt TEXT,n INT DEFAULT 0,PRIMARY KEY(pid,pos))',
    'CREATE TABLE IF NOT EXISTS pollvoted(pid INT,uid INT,PRIMARY KEY(pid,uid))',
    'CREATE TABLE IF NOT EXISTS pollrx(pid INT,h TEXT,PRIMARY KEY(pid,h))',
    'CREATE TABLE IF NOT EXISTS pollmeta(pid INT PRIMARY KEY,ends INT DEFAULT 0,multi INT DEFAULT 0)',
    'CREATE TABLE IF NOT EXISTS pstreak(uid INT,day INT,PRIMARY KEY(uid,day))',
    'CREATE TABLE IF NOT EXISTS mreveals(uid INT,fid INT,ts INT,PRIMARY KEY(uid,fid))',
    'CREATE TABLE IF NOT EXISTS typing(uid INT,oid INT DEFAULT 0,fm INT DEFAULT 0,tm INT DEFAULT 0,gid INT DEFAULT 0,ts INT,PRIMARY KEY(uid,oid,fm,tm,gid))',
    "CREATE TABLE IF NOT EXISTS dmpref(uid INT,oid INT,ps INT DEFAULT 0,nick TEXT DEFAULT '', bg TEXT DEFAULT '',PRIMARY KEY(uid,oid,ps))",
    'CREATE TABLE IF NOT EXISTS dmstate(uid INT,oid INT,ps INT DEFAULT 0,ms INT DEFAULT 0,mute INT DEFAULT 0,clr INT DEFAULT 0,PRIMARY KEY(uid,oid,ps,ms))',
    'CREATE TABLE IF NOT EXISTS mblocks(a INT,kid INT,PRIMARY KEY(a,kid))',
    'CREATE TABLE IF NOT EXISTS mreq(owner INT,peer INT,pm INT,st INT,PRIMARY KEY(owner,peer,pm))',
    'CREATE TABLE IF NOT EXISTS dislikes(pid INT,uid INT,PRIMARY KEY(pid,uid))',
    'CREATE TABLE IF NOT EXISTS cdislikes(cid INT,uid INT,PRIMARY KEY(cid,uid))',
    "CREATE TABLE IF NOT EXISTS masks(id INTEGER PRIMARY KEY,uid INT UNIQUE,name TEXT UNIQUE COLLATE NOCASE,bio TEXT DEFAULT '',avatar TEXT DEFAULT '',ts INT,inb INT DEFAULT 1)",
    'CREATE TABLE IF NOT EXISTS asks(id INTEGER PRIMARY KEY,uid INT,frm INT,txt TEXT,ts INT,hid INT DEFAULT 0)',
    "CREATE TABLE IF NOT EXISTS gchats(id INTEGER PRIMARY KEY,name TEXT,owner INT,ts INT, avatar TEXT DEFAULT '', bg TEXT DEFAULT '')",
    'CREATE TABLE IF NOT EXISTS gmembers(gid INT,uid INT,rd INT DEFAULT 0, since INT DEFAULT 0, mute INT DEFAULT 0, pm INT DEFAULT 0,PRIMARY KEY(gid,uid))',
    "CREATE TABLE IF NOT EXISTS gmessages(id INTEGER PRIMARY KEY,gid INT,uid INT,txt TEXT,ts INT,ed INT DEFAULT 0,img TEXT DEFAULT '', pm INT DEFAULT 0, rp INT DEFAULT 0, pin INT DEFAULT 0)",
    'CREATE TABLE IF NOT EXISTS ginvites(id INTEGER PRIMARY KEY,gid INT,uid INT,inv INT,ts INT, pm INT DEFAULT 0,UNIQUE(gid,uid))',
    'CREATE TABLE IF NOT EXISTS glinks(gid INTEGER PRIMARY KEY,code TEXT UNIQUE,ts INT)',
    "CREATE TABLE IF NOT EXISTS gevents(id INTEGER PRIMARY KEY,gid INT,uid INT,kind TEXT,tid INT DEFAULT 0,arg TEXT DEFAULT '',ts INT, pm INT DEFAULT 0, tpm INT DEFAULT 0)",
    'CREATE TABLE IF NOT EXISTS gmasks(gid INT,uid INT,PRIMARY KEY(gid,uid))',
    'CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY,name TEXT,theme TEXT,owner INT,ts INT,exp INT,closed INT DEFAULT 0)',
    'CREATE TABLE IF NOT EXISTS rmsgs(id INTEGER PRIMARY KEY,rid INT,uid INT,txt TEXT,ts INT)',
    'CREATE TABLE IF NOT EXISTS rpres(rid INT,uid INT,ts INT,PRIMARY KEY(rid,uid))',
    'CREATE TABLE IF NOT EXISTS rvotes(mid INT,uid INT,v INT,PRIMARY KEY(mid,uid))',
    'CREATE TABLE IF NOT EXISTS rrep(uid INTEGER PRIMARY KEY,up INT DEFAULT 0,down INT DEFAULT 0)',
    'CREATE TABLE IF NOT EXISTS mreact(k TEXT,mid INT,uid INT,e TEXT,PRIMARY KEY(k,mid,uid))',
    "CREATE TABLE IF NOT EXISTS postimgs(pid INT,pos INT,img TEXT, alt TEXT DEFAULT '',PRIMARY KEY(pid,pos))",
    'CREATE TABLE IF NOT EXISTS pend(img TEXT PRIMARY KEY,uid INT,ts INT)',
    'CREATE TABLE IF NOT EXISTS gone(h TEXT PRIMARY KEY,uid INT)',
    'CREATE TABLE IF NOT EXISTS oldnames(h TEXT PRIMARY KEY,uid INT,ts INT)',
    'CREATE TABLE IF NOT EXISTS rl(k TEXT,ts INT)',
    'CREATE TABLE IF NOT EXISTS alog(id INTEGER PRIMARY KEY,aid INT,act TEXT,tgt TEXT,ts INT)',
    'CREATE TABLE IF NOT EXISTS attlog(uid INT,ts INT,sz INT)',
    'CREATE TABLE IF NOT EXISTS saves(uid INT,pid INT,ts INT,PRIMARY KEY(uid,pid))',
    'CREATE TABLE IF NOT EXISTS postviews(pid INT,uid INT,ts INT,PRIMARY KEY(pid,uid))',
    "CREATE TABLE IF NOT EXISTS nprefs(uid INTEGER PRIMARY KEY,muted TEXT DEFAULT '',pop INT DEFAULT 1,qon INT DEFAULT 0,qfrom INT DEFAULT 1320,qto INT DEFAULT 420,tz INT DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS mutes(uid INT,kind TEXT,val TEXT,lbl TEXT DEFAULT '',PRIMARY KEY(uid,kind,val))",
    "CREATE TABLE IF NOT EXISTS devices(n INTEGER PRIMARY KEY,tok TEXT UNIQUE,uid INT,label TEXT DEFAULT '',ts INT,last INT,sv INT DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS appeals(id INTEGER PRIMARY KEY,uid INT,txt TEXT,ts INT,st INT DEFAULT 0,note TEXT DEFAULT '',rts INT DEFAULT 0,rby INT DEFAULT 0)",
    'CREATE TABLE IF NOT EXISTS pushsubs(id INTEGER PRIMARY KEY,uid INT,ep TEXT UNIQUE,k TEXT,a TEXT,ts INT)',
    'CREATE TABLE IF NOT EXISTS pedits(id INTEGER PRIMARY KEY,pid INT,cap TEXT,ts INT)',
    'CREATE TABLE IF NOT EXISTS streakping(uid INT,day INT,PRIMARY KEY(uid,day))',
    'CREATE TABLE IF NOT EXISTS cstreakping(uid INT,day INT,PRIMARY KEY(uid,day))',
    'CREATE TABLE IF NOT EXISTS site(k TEXT PRIMARY KEY,v TEXT)',
    'CREATE TABLE IF NOT EXISTS sigadj(uid INT,amt INT,by INT,ts INT)',
    'CREATE TABLE IF NOT EXISTS sfreeze(uid INT,day INT,price INT,ts INT,PRIMARY KEY(uid,day))',
    'CREATE TABLE IF NOT EXISTS shop(uid INT,k TEXT,id TEXT,price INT,ts INT,PRIMARY KEY(uid,k,id))',
    'CREATE TABLE IF NOT EXISTS ugrants(uid INT,k TEXT,id TEXT,by INT,ts INT,PRIMARY KEY(uid,k,id))',
    "CREATE TABLE IF NOT EXISTS gifts(id INTEGER PRIMARY KEY,uid INT,by INT,ts INT,msg TEXT DEFAULT '',opened INT DEFAULT 0)",
    'CREATE TABLE IF NOT EXISTS gitems(gid INT,k TEXT,id TEXT)',
    "CREATE TABLE IF NOT EXISTS lpv(h TEXT PRIMARY KEY,t TEXT,d TEXT,s TEXT,ts INT,ok INT, i TEXT DEFAULT '')",
    "CREATE TABLE IF NOT EXISTS mailtok(h TEXT PRIMARY KEY,uid INT,kind TEXT,val TEXT DEFAULT '',exp INT)",
    'CREATE TABLE IF NOT EXISTS stkimg(id TEXT PRIMARY KEY,sha TEXT UNIQUE,ext TEXT,sz INT,ts INT)',
    'CREATE TABLE IF NOT EXISTS stkfav(uid INT,ref TEXT,ts INT,PRIMARY KEY(uid,ref))',
]

INDEXES = [
    'CREATE INDEX IF NOT EXISTS cpid ON comments(pid)',
    'CREATE INDEX IF NOT EXISTS mab ON messages(a,b)',
    'CREATE INDEX IF NOT EXISTS mbi ON messages(b,id)',
    'CREATE INDEX IF NOT EXISTS follows_b ON follows(b)',
    'CREATE INDEX IF NOT EXISTS ptag ON posttags(tag)',
    'CREATE INDEX IF NOT EXISTS nuid ON notifs(uid,seen)',
    'CREATE INDEX IF NOT EXISTS posts_exp ON posts(exp)',
    'CREATE INDEX IF NOT EXISTS asks_uid ON asks(uid,id)',
    'CREATE INDEX IF NOT EXISTS gevents_g ON gevents(gid,id)',
    'CREATE INDEX IF NOT EXISTS rmsgs_r ON rmsgs(rid,id)',
    'CREATE INDEX IF NOT EXISTS postimgs_img ON postimgs(img)',
    'CREATE INDEX IF NOT EXISTS cuid ON comments(uid,ts)',
    'CREATE INDEX IF NOT EXISTS rlk ON rl(k,ts)',
    'CREATE INDEX IF NOT EXISTS attlogu ON attlog(uid,ts)',
    'CREATE INDEX IF NOT EXISTS saves_pid ON saves(pid)',
    'CREATE INDEX IF NOT EXISTS postviews_u ON postviews(uid,ts)',
    'CREATE INDEX IF NOT EXISTS likes_uid ON likes(uid)',
    'CREATE INDEX IF NOT EXISTS devices_uid ON devices(uid)',
    'CREATE INDEX IF NOT EXISTS appeals_uid ON appeals(uid,id)',
    'CREATE INDEX IF NOT EXISTS pushsubs_uid ON pushsubs(uid)',
    'CREATE INDEX IF NOT EXISTS pedits_pid ON pedits(pid)',
]


class Schema:
    """Creates and upgrades the tables."""
    VERSION = 2

    def __init__(self, db):
        self.db = db

    def apply(self):
        q = self.db.query
        q("PRAGMA journal_mode=WAL")
        fresh = self.db.value("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'") is None
        for sql in TABLES:
            q(sql)
        self._add_missing_columns()
        for sql in INDEXES:
            q(sql)
        q("UPDATE users SET tcf='thorns' WHERE tcf='vines'")  # the old Vines banner frame became Thorns
        if fresh:
            q("PRAGMA user_version=%d" % self.VERSION)

    def _add_missing_columns(self):
        ref = sqlite3.connect(":memory:")
        for sql in TABLES:
            ref.execute(sql)
        for (table,) in ref.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            have = {r[1] for r in self.db.query("PRAGMA table_info(%s)" % table).fetchall()}
            for _cid, name, typ, _nn, dflt, _pk in ref.execute("PRAGMA table_info(%s)" % table).fetchall():
                if name not in have:
                    self.db.query("ALTER TABLE %s ADD COLUMN %s %s%s" % (table, name, typ, "" if dflt is None else " DEFAULT " + str(dflt)))
