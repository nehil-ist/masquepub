"""Crash and not-found answers (run: python3 -I tests/test_errors.py)."""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["DATA_DIR"] = tempfile.mkdtemp()

from masque.app import create_app  # noqa: E402
from masque.config import Config  # noqa: E402
from masque.database import Database  # noqa: E402
from masque.schema import Schema  # noqa: E402


class ErrorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = Config.from_env()
        Schema(Database(cfg.db_path)).apply()
        cls.app = create_app(cfg)
        cls.app.add_url_rule("/boom", "boom", lambda: 1 / 0)
        cls.app.config["PROPAGATE_EXCEPTIONS"] = False

    def test_crash_is_json(self):
        r = self.app.test_client().get("/boom")
        self.assertEqual((r.status_code, json.loads(r.data)), (500, {"e": "Server error. Please try again."}))

    def test_unknown_action(self):
        r = self.app.test_client().get("/?a=nosuch")
        self.assertEqual((r.status_code, json.loads(r.data)), (404, {"e": "Not found."}))


if __name__ == "__main__":
    unittest.main()
