import json
import sqlite3
import uuid
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
                    request_id TEXT UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                    kind TEXT NOT NULL, data TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE INDEX IF NOT EXISTS events_session ON events(session_id, id);
                CREATE UNIQUE INDEX IF NOT EXISTS active_repository ON sessions(repository)
                    WHERE status IN ('queued','running','awaiting_approval','executing');
                CREATE TABLE IF NOT EXISTS reservations (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT NOT NULL,
                    amount_micro INTEGER NOT NULL CHECK(amount_micro >= 0),
                    status TEXT NOT NULL DEFAULT 'held');
            """)
        path.chmod(0o600)

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

    def session(self, session_id, user_id=None):
        with self.connect() as db:
            # Workers already hold a trusted session ID; HTTP callers pass the authenticated owner.
            row = db.execute("SELECT * FROM sessions WHERE id=?" + (" AND user_id=?" if user_id is not None else ""),
                             (session_id, user_id) if user_id is not None else (session_id,)).fetchone()
            if not row:
                raise LookupError("Session not found")
            actions = db.execute("SELECT * FROM actions WHERE session_id=? ORDER BY rowid", (session_id,))
            result = {**dict(row), "state": json.loads(row["state"]),
                      "actions": [{**dict(action), "payload": json.loads(action["payload"])} for action in actions]}
        # The snapshot includes all bounded events, not only the first replay page.
        result["events"] = []
        while True:
            page = self.events(session_id, result["events"][-1]["id"] if result["events"] else 0)
            result["events"].extend(page)
            if len(page) < 100:
                break
        return result

    def sessions(self, user_id="local"):
        with self.connect() as db:
            rows = db.execute("SELECT id FROM sessions WHERE user_id=? ORDER BY rowid DESC LIMIT 30", (user_id,))
            ids = [row["id"] for row in rows]
        return [self.session(session_id, user_id) for session_id in ids]

    def create_session(self, repository, task, mode="optimized", user_id="local", request_id=None):
        session_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if request_id:
                existing = db.execute("SELECT id FROM sessions WHERE request_id=? AND user_id=?",
                                      (request_id, user_id)).fetchone()
                if existing:
                    return existing["id"], False
            try:
                db.execute("INSERT INTO sessions(id,user_id,repository,task,status,state,request_id) "
                           "VALUES (?,?,?,?, 'queued',?,?)",
                           (session_id, user_id, repository, task, json.dumps({"mode": mode}), request_id))
            except sqlite3.IntegrityError as exc:
                raise ValueError("This repository already has an active session") from exc
        self.event(session_id, "status", {"message": "Task queued", "status": "queued"})
        return session_id, True

    def update(self, session_id, status=None, **state):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state,status FROM sessions WHERE id=?", (session_id,)).fetchone()
            current = json.loads(row["state"])
            current.update(state)
            db.execute("UPDATE sessions SET state=?,status=? WHERE id=?",
                       (json.dumps(current), status or row["status"], session_id))
        if status:
            self.event(session_id, "status", {"message": status.replace("_", " ").capitalize(), "status": status})

    def claim(self, session_id):
        with self.connect() as db:
            changed = db.execute("UPDATE sessions SET status='running' WHERE id=? AND status='queued'",
                                 (session_id,)).rowcount
        return bool(changed)

    def propose(self, session_id, kind, payload):
        action_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO actions(id,session_id,kind,payload) VALUES(?,?,?,?)",
                       (action_id, session_id, kind, json.dumps(payload)))
            db.execute("UPDATE sessions SET status='awaiting_approval' WHERE id=?", (session_id,))
        self.event(session_id, "action", {"message": f"Review required: {kind}", "action_id": action_id})
        return action_id

    def decide(self, session_id, action_id, approve):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row or row["status"] != "awaiting_approval":
                raise ValueError("Session is not awaiting approval")
            changed = db.execute("UPDATE actions SET status=? WHERE id=? AND session_id=? AND status='pending'",
                                 ("approved" if approve else "rejected", action_id, session_id)).rowcount
            if not changed:
                raise ValueError("Action is already resolved or does not belong to this session")
            db.execute("UPDATE sessions SET status=? WHERE id=?", ("queued" if approve else "rejected", session_id))
        self.event(session_id, "status", {"message": "Exact action approved" if approve else "Action rejected; nothing executed"})

    def resume(self, session_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM actions WHERE session_id=? AND status IN ('executing','uncertain')",
                          (session_id,)).fetchone():
                raise ValueError("An interrupted action has an unknown outcome; inspect it before starting a new task")
            try:
                changed = db.execute("UPDATE sessions SET status='queued' WHERE id=? AND status IN "
                                     "('blocked','failed','interrupted')", (session_id,)).rowcount
            except sqlite3.IntegrityError as exc:
                raise ValueError("Another session is active for this repository") from exc
            if not changed:
                raise ValueError("Session cannot be resumed from its current state")
        self.event(session_id, "status", {"message": "Saved session queued to resume"})

    def recover(self):
        with self.connect() as db:
            rows = db.execute("SELECT id FROM sessions WHERE status IN ('queued','running','executing')").fetchall()
            db.execute("UPDATE actions SET status='uncertain' WHERE status='executing'")
            db.execute("UPDATE sessions SET status='interrupted' WHERE status IN ('queued','running','executing')")
        for row in rows:
            self.event(row["id"], "status", {"message": "Backend restarted; inspect and resume saved session"})

    def user(self, user_id="local"):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            reserved = db.execute("SELECT COALESCE(SUM(amount_micro),0) FROM reservations "
                                  "WHERE user_id=? AND status='held'", (user_id,)).fetchone()[0]
        return {**dict(row), "reserved_micro": reserved}

    def configure_users(self, users):
        tokens = [config.get("token") for config in users.values()]
        if len(tokens) != len(set(tokens)):
            raise ValueError("Each local profile requires a different access token")
        with self.connect() as db:
            for user_id, config in users.items():
                if not config.get("token") or type(config.get("limit_micro")) is not int or config["limit_micro"] < 0:
                    raise ValueError("Each local profile requires a token and non-negative integer limit_micro")
                db.execute("INSERT INTO users(id,limit_micro) VALUES(?,?) ON CONFLICT(id) "
                           "DO UPDATE SET limit_micro=excluded.limit_micro", (user_id, config["limit_micro"]))
