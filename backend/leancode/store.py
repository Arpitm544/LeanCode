import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, limit_micro INTEGER NOT NULL CHECK(limit_micro >= 0),
                    spent_micro INTEGER NOT NULL DEFAULT 0 CHECK(spent_micro >= 0));
                INSERT OR IGNORE INTO users(id, limit_micro) VALUES ('local', 1000000);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, repository TEXT NOT NULL,
                    task TEXT NOT NULL, status TEXT NOT NULL, state TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                    kind TEXT NOT NULL, data TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE INDEX IF NOT EXISTS events_session ON events(session_id, id);
                CREATE TABLE IF NOT EXISTS reservations (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT NOT NULL,
                    amount_micro INTEGER NOT NULL CHECK(amount_micro >= 0),
                    status TEXT NOT NULL DEFAULT 'held');
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def event(self, session_id, kind, data):
        with self.connect() as db:
            db.execute("INSERT INTO events(session_id, kind, data) VALUES (?, ?, ?)",
                       (session_id, kind, json.dumps(data)))

    def events(self, session_id, after=0):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events WHERE session_id=? AND id>? ORDER BY id LIMIT 100",
                              (session_id, after)).fetchall()
        return [{**dict(row), "data": json.loads(row["data"])} for row in rows]
