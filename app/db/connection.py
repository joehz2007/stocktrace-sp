import os
import sqlite3

from app.config import DATA_DIR

DEFAULT_DB_PATH = os.path.join(DATA_DIR, "stocktrace.db")
_SCHEMA = os.path.join(os.path.dirname(__file__), "schema.sql")


def connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    with open(_SCHEMA, encoding="utf-8") as f:
        ddl = f.read()
    conn = connect(db_path)
    try:
        conn.executescript(ddl)
        conn.commit()
    finally:
        conn.close()
