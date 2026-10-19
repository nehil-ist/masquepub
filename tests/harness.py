"""Shared test tools for the step-3 tests: an offline Masque (Python only, database built from masque/schema.py) and browsers to drive it."""
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from flask import Response  # noqa: E402
from masque.app import create_app  # noqa: E402
from masque.config import Config  # noqa: E402
from tests import offline_schema  # noqa: E402


class Browser:
    """One visitor: keeps its cookie, remembers its CSRF token."""
    counter = 0

    def __init__(self, app):
        self.c = app.test_client()
        Browser.counter += 1
        self.ip = "10.1.%d.%d" % divmod(Browser.counter, 250)
        self.csrf = ""

    def get(self, qs):
        r = self.c.get("/?" + qs, headers={"X-Real-IP": self.ip})
        return r, json.loads(r.data)

    def post(self, action, files=None, **form):
        data = dict(form)
        if files:
            data.update(files)
        r = self.c.post("/?a=" + action, data=data, headers={"X-CSRF": self.csrf, "X-Real-IP": self.ip},
                        content_type="multipart/form-data" if files else None)
        return r, json.loads(r.data)

    def me(self):
        r, j = self.get("a=me")
        self.csrf = j["csrf"]
        return j

    def signup(self, name, pw="password123"):
        self.me()
        r, j = self.post("signup", name=name, pw=pw)
        assert r.status_code == 200, j
        return j


class OfflineCase(unittest.TestCase):
    ADMIN = "testadmin"

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        (cls.tmp / "sessions").mkdir()
        (cls.tmp / "up").mkdir()
        offline_schema.build(cls.tmp / "app.db")
        cls.cfg = Config(root=ROOT, data_dir=cls.tmp, admin_users=(cls.ADMIN,), admin_user=cls.ADMIN, admin_password="adminpass123",
                         mail_key="test-mail-key-0123456789")
        cls.app = create_app(cls.cfg)
        cls.db = sqlite3.connect(cls.tmp / "app.db", isolation_level=None)
        cls.db.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def sql(self, q, *a):
        return [dict(r) for r in self.db.execute(q, a).fetchall()]

    def val(self, q, *a):
        r = self.db.execute(q, a).fetchone()
        return r[0] if r else None

    @classmethod
    def user(cls, name):
        b = Browser(cls.app)
        b.signup(name)
        cls.db.execute("UPDATE users SET ts=ts-2000000 WHERE name=?", (name,))  # not a "new" account any more (no first-day limits)
        return b

    def uid(self, name):
        return self.val("SELECT id FROM users WHERE name=?", name)
