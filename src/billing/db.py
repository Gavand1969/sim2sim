"""
SQLite storage for license keys.

Schema:
  licenses(
    key TEXT PRIMARY KEY,           -- LIC-XXXX-XXXX-XXXX-XXXX
    tier TEXT NOT NULL,             -- 'pro' | 'team'
    email TEXT NOT NULL,
    created_at TEXT NOT NULL,       -- ISO-8601 UTC
    stripe_session_id TEXT,         -- nullable, used for idempotency
    activated_at TEXT,              -- nullable; first activation timestamp
    activation_count INTEGER NOT NULL DEFAULT 0,
    revoked INTEGER NOT NULL DEFAULT 0
  )

Notes:
  - We don't bind to a machine ID — license keys are paste-anywhere, and we
    just bump activation_count for analytics.
  - The database file path is taken from the SIM2SIM_DB env var, defaulting
    to ./sim2sim.db.  Tests override via the env var.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional

_LOCK = threading.Lock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS licenses (
    key TEXT PRIMARY KEY,
    tier TEXT NOT NULL CHECK (tier IN ('pro', 'team')),
    email TEXT NOT NULL,
    created_at TEXT NOT NULL,
    stripe_session_id TEXT UNIQUE,
    activated_at TEXT,
    activation_count INTEGER NOT NULL DEFAULT 0,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_licenses_email ON licenses (email);
CREATE INDEX IF NOT EXISTS idx_licenses_stripe ON licenses (stripe_session_id);
"""


def db_path() -> Path:
    return Path(os.getenv("SIM2SIM_DB", "sim2sim.db"))


def get_conn() -> sqlite3.Connection:
    """Return a new SQLite connection with sensible pragmas."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """Create tables if they don't exist.  Safe to call repeatedly."""
    with _LOCK:
        conn = get_conn()
        try:
            conn.executescript(_SCHEMA)
        finally:
            conn.close()


def reset_db() -> None:
    """Drop and recreate.  Test-only helper."""
    with _LOCK:
        path = db_path()
        if path.exists():
            path.unlink()
        init_db()


def find_by_stripe_session(session_id: str) -> Optional[sqlite3.Row]:
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT * FROM licenses WHERE stripe_session_id = ?",
            (session_id,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def find_by_key(key: str) -> Optional[sqlite3.Row]:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM licenses WHERE key = ?", (key,))
        return cur.fetchone()
    finally:
        conn.close()


def insert_license(
    key: str,
    tier: str,
    email: str,
    created_at: str,
    stripe_session_id: Optional[str] = None,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO licenses (key, tier, email, created_at, stripe_session_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, tier, email, created_at, stripe_session_id),
        )
    finally:
        conn.close()


def record_activation(key: str, activated_at: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE licenses "
            "SET activation_count = activation_count + 1, "
            "    activated_at = COALESCE(activated_at, ?) "
            "WHERE key = ?",
            (activated_at, key),
        )
    finally:
        conn.close()
