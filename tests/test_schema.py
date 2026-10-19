"""Schema tests: a Python-made database has the same tables, columns and indexes PHP makes, and old databases are upgraded."""
import shutil, sqlite3, subprocess, sys, tempfile, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from masque.database import Database
from masque.schema import Schema


def shape(path):
    c = sqlite3.connect(path)
    out = {}
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        out[t] = sorted((r[1], r[2].upper(), r[4], r[5]) for r in c.execute("PRAGMA table_info(%s)" % t))
    out["#idx"] = sorted(r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"))
    return out


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_fresh_and_twice(self):
        db = Database(self.d / "a.db")
        Schema(db).apply()
        Schema(db).apply()
        self.assertEqual(db.value("PRAGMA user_version"), 2)
        self.assertGreater(len(shape(self.d / "a.db")), 70)

    def test_old_database_gets_new_columns(self):
        c = sqlite3.connect(self.d / "o.db")
        c.execute("CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT UNIQUE COLLATE NOCASE,pw TEXT,bio TEXT DEFAULT '',em TEXT DEFAULT '',col TEXT DEFAULT '',cover TEXT DEFAULT '',ts INT)")
        c.execute("CREATE TABLE posts(id INTEGER PRIMARY KEY,uid INT,cap TEXT,img TEXT,ts INT)")
        c.execute("INSERT INTO users(name,pw,ts,) VALUES('x','y',1)".replace(",)", ")"))
        c.commit(); c.close()
        db = Database(self.d / "o.db")
        Schema(db).apply()
        cols = {r["name"] for r in db.all("PRAGMA table_info(users)")}
        self.assertTrue({"xp", "mail", "sus", "tcf"} <= cols)
        self.assertEqual(db.value("SELECT xp FROM users"), 0)
        self.assertEqual(db.value("PRAGMA user_version"), 0)  # not fresh: left alone


if __name__ == "__main__":
    unittest.main()
