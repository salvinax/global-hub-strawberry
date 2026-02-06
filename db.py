# db.py
# instead of saving locally using jsonl files we are instead using sqlite
# better for threads/cleaner
import sqlite3
from contextlib import contextmanager

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS sensor_samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,          -- epoch seconds (UTC)
  payload TEXT NOT NULL,        -- JSON string
  uploaded INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS node_packets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  node_id TEXT,
  payload TEXT NOT NULL,
  uploaded INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sensor_uploaded_ts ON sensor_samples(uploaded, ts);
CREATE INDEX IF NOT EXISTS idx_node_uploaded_ts   ON node_packets(uploaded, ts);
"""

@contextmanager
def db_connect(path: str):
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)  # autocommit
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        yield conn
    finally:
        conn.close()

def init_db(path: str):
    with db_connect(path) as conn:
        for stmt in SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s + ";")
