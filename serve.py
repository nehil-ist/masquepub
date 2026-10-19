#!/usr/bin/env python3
"""Start Masque: the database layout, the background jobs and the Python server on $PORT."""
import signal
import sys

from masque.app import create_app
from masque.background import build_scheduler
from masque.config import Config
from masque.database import Database
from masque.schema import Schema


def main():
    cfg = Config.from_env()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.ensure_folders()
    Schema(Database(cfg.db_path)).apply()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    app = create_app(cfg)
    if cfg.background:
        build_scheduler(cfg).start()  # backups, expired posts, tidy, stkgc, streak reminders (BACKGROUND=off to disable)
    try:
        from waitress import serve  # threaded, production-grade, pure Python
        serve(app, host="0.0.0.0", port=cfg.port, threads=16, max_request_body_size=cfg.post_max + 1024 * 1024)
    except ImportError:
        print("waitress not installed: using Werkzeug's server (fine for testing, not for production)", file=sys.stderr)
        from werkzeug.serving import run_simple
        run_simple("0.0.0.0", cfg.port, app, threaded=True)


if __name__ == "__main__":
    main()
