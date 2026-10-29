"""Tenant-isolated SQLite storage for the local pilot. PostgreSQL is a production upgrade."""
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS organizations (
  id TEXT PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS principals (
  key_hash TEXT PRIMARY KEY, org_id TEXT NOT NULL, name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('owner','editor','viewer')),
  FOREIGN KEY(org_id) REFERENCES organizations(id)
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, title TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('open','done')), priority TEXT NOT NULL,
  source TEXT NOT NULL, created_at TEXT NOT NULL,
  FOREIGN KEY(org_id) REFERENCES organizations(id)
);
CREATE INDEX IF NOT EXISTS idx_tasks_org_created ON tasks(org_id,created_at);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, integration_id TEXT NOT NULL,
  external_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
  created_at TEXT NOT NULL, UNIQUE(org_id,integration_id,external_id),
  FOREIGN KEY(org_id) REFERENCES organizations(id)
);
CREATE INDEX IF NOT EXISTS idx_events_org_created ON events(org_id,created_at);
CREATE TABLE IF NOT EXISTS integrations (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
  cursor INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY(org_id) REFERENCES organizations(id)
);
CREATE TABLE IF NOT EXISTS audit (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, actor TEXT NOT NULL,
  tool TEXT NOT NULL, outcome TEXT NOT NULL, detail TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_org_created ON audit(org_id,created_at);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, actor TEXT NOT NULL,
  tool TEXT NOT NULL, arguments TEXT NOT NULL, status TEXT NOT NULL,
  reviewed_by TEXT, created_at TEXT NOT NULL
);
"""

def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_key(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=10000")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def add_org(self, org_id: str, name: str):
        with self.connect() as con:
            con.execute("INSERT OR IGNORE INTO organizations(id,name) VALUES(?,?)", (org_id, name))

    def add_key(self, org_id: str, name: str, role: str, key: str):
        if role not in {"owner", "editor", "viewer"}:
            raise ValueError("invalid role")
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO principals VALUES(?,?,?,?)",
                        (hash_key(key), org_id, name, role))

    def identity(self, key: str):
        if not key:
            return None
        with self.connect() as con:
            row = con.execute("SELECT org_id,name,role FROM principals WHERE key_hash=?",
                              (hash_key(key),)).fetchone()
            return dict(row) if row else None
