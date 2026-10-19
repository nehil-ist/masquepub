"""Builds an empty Masque database from masque/schema.py (no PHP needed)."""
from pathlib import Path

from masque.database import Database
from masque.schema import Schema


def build(db_path):
    Schema(Database(Path(db_path))).apply()
