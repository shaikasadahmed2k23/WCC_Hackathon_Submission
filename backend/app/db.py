"""SQLite access layer. One connection per request, schema created on startup."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL, title TEXT, clearance INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, workspace TEXT,
  departing_user_id INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL, kind TEXT NOT NULL, uri TEXT, uploaded_by INTEGER,
  sensitivity INTEGER NOT NULL DEFAULT 0, doc_date TEXT, redactions TEXT NOT NULL DEFAULT '{}',
  size INTEGER NOT NULL DEFAULT 0, content_hash TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL, text TEXT NOT NULL, location TEXT, ts TEXT, speaker TEXT,
  sensitivity INTEGER NOT NULL DEFAULT 0, flags TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS claims(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id),
  type TEXT NOT NULL, subtype TEXT, statement TEXT NOT NULL, owner TEXT, due TEXT, severity TEXT,
  origin TEXT NOT NULL, extractor TEXT, review_status TEXT NOT NULL DEFAULT 'pending',
  reviewed_by INTEGER, clearance INTEGER NOT NULL DEFAULT 0, event_date TEXT,
  fingerprint TEXT, recurring INTEGER NOT NULL DEFAULT 0, vclass TEXT, vvalue TEXT,
  answer TEXT, answered_by INTEGER, answered_at TEXT, original_statement TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim_evidence(
  id INTEGER PRIMARY KEY, claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  quote TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS conflicts(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, claim_a INTEGER NOT NULL, claim_b INTEGER NOT NULL,
  vclass TEXT, reason TEXT, status TEXT NOT NULL DEFAULT 'open', resolution TEXT, note TEXT,
  resolved_by INTEGER, resolved_at TEXT, fp_a TEXT, fp_b TEXT
);
CREATE TABLE IF NOT EXISTS versions(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, number INTEGER NOT NULL, status TEXT NOT NULL,
  note TEXT, created_by INTEGER, approved_by INTEGER, created_at TEXT NOT NULL, snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shares(
  id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  shared_by INTEGER, shared_at TEXT NOT NULL, acknowledged_at TEXT, UNIQUE(version_id, user_id)
);
CREATE TABLE IF NOT EXISTS access_requests(
  id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, user_id INTEGER NOT NULL, reason TEXT,
  status TEXT NOT NULL DEFAULT 'pending', decided_by INTEGER, decided_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS grants(
  id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, user_id INTEGER NOT NULL, clearance INTEGER NOT NULL,
  UNIQUE(version_id, user_id)
);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, actor_id INTEGER, actor_name TEXT, action TEXT NOT NULL,
  object TEXT, detail TEXT, project_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_claims_project ON claims(project_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON claim_evidence(claim_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db():
    """FastAPI dependency."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def audit(db, actor, action, obj="", detail="", project_id=None):
    db.execute(
        "INSERT INTO audit(ts,actor_id,actor_name,action,object,detail,project_id) VALUES(?,?,?,?,?,?,?)",
        (now(), actor["id"] if actor else None, actor["name"] if actor else "system", action, obj, detail, project_id),
    )


def rows(cur):
    return [dict(r) for r in cur.fetchall()]


def jload(s, default=None):
    try:
        return json.loads(s)
    except Exception:
        return default
