"""
Storage for license keys.

Backend selection:
  - If DATABASE_URL is set (e.g. on DigitalOcean App Platform with an attached
    managed Postgres database), we use Postgres via psycopg3.
  - Otherwise we fall back to SQLite at SIM2SIM_DB (default ./sim2sim.db).
    This keeps local development and the existing test suite working unchanged.

Schema (identical across backends):
  licenses(
    key TEXT PRIMARY KEY,           -- LIC-XXXX-XXXX-XXXX-XXXX
    tier TEXT NOT NULL,             -- 'pro' | 'team'
    email TEXT NOT NULL,
    created_at TEXT NOT NULL,       -- ISO-8601 UTC
    stripe_session_id TEXT UNIQUE,  -- used for idempotency
    activated_at TEXT,              -- nullable; first activation timestamp
    activation_count INTEGER NOT NULL DEFAULT 0,
    revoked INTEGER NOT NULL DEFAULT 0
  )

Public API (unchanged):
  init_db(), reset_db(),
  find_by_stripe_session(session_id) -> Optional[Row],
  find_by_key(key)                  -> Optional[Row],
  insert_license(key, tier, email, created_at, stripe_session_id=None),
  record_activation(key, activated_at)

A "row" is anything that supports both row[index] and row["column_name"]
indexing — sqlite3.Row already does that natively; for Postgres we wrap
results in a small _DictRow helper that mimics the same interface.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Optional


_LOCK = threading.Lock()


# ── Backend detection ────────────────────────────────────────────────────────

def _database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def _use_postgres() -> bool:
    url = _database_url()
    return bool(url) and url.startswith(("postgres://", "postgresql://"))


def db_path() -> Path:
    """SQLite path — only meaningful when not using Postgres."""
    return Path(os.getenv("SIM2SIM_DB", "sim2sim.db"))


# ── SQLite schema ────────────────────────────────────────────────────────────

_SQLITE_SCHEMA = """
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

# ── Postgres schema ──────────────────────────────────────────────────────────
# Mostly identical, but Postgres prefers explicit types & doesn't need
# executescript().  We use TEXT throughout to match the SQLite shape.

# DigitalOcean managed Postgres revokes CREATE on the `public` schema from
# non-owner users (Postgres 15+ default).  We create and own our own schema
# named `sim2sim` and put the licenses table there.  The schema is also added
# to search_path so unqualified table references work everywhere.
_PG_SCHEMA_STATEMENTS = [
    "CREATE SCHEMA IF NOT EXISTS sim2sim",
    """
    CREATE TABLE IF NOT EXISTS sim2sim.licenses (
        key TEXT PRIMARY KEY,
        tier TEXT NOT NULL CHECK (tier IN ('pro', 'team')),
        email TEXT NOT NULL,
        created_at TEXT NOT NULL,
        stripe_session_id TEXT UNIQUE,
        activated_at TEXT,
        activation_count INTEGER NOT NULL DEFAULT 0,
        revoked INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_licenses_email ON sim2sim.licenses (email)",
    "CREATE INDEX IF NOT EXISTS idx_licenses_stripe ON sim2sim.licenses (stripe_session_id)",
]


# ── Row wrapper for Postgres ─────────────────────────────────────────────────


class _DictRow:
    """
    Minimal sqlite3.Row-compatible wrapper around a (columns, values) tuple.

    Supports row["col"], row[idx], dict-like .keys(), and truthy checks on
    nullable columns (which is what `if row["revoked"]:` needs).
    """
    __slots__ = ("_cols", "_vals", "_map")

    def __init__(self, cols: Iterable[str], vals: Iterable[Any]):
        self._cols = tuple(cols)
        self._vals = tuple(vals)
        self._map = {c: v for c, v in zip(self._cols, self._vals)}

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._map[key]

    def keys(self):
        return self._cols

    def __iter__(self):
        return iter(self._vals)

    def __repr__(self) -> str:  # pragma: no cover — debugging only
        return f"_DictRow({self._map!r})"


# ── Postgres helpers ─────────────────────────────────────────────────────────


def _pg_connect():
    """Open a fresh psycopg3 connection.  Imported lazily so tests that
    don't use Postgres don't need psycopg installed."""
    import psycopg  # type: ignore
    # DigitalOcean managed PG requires sslmode=require.  psycopg honours it
    # from the DSN if present; we don't force it here so local Postgres
    # without TLS still works.
    conn = psycopg.connect(_database_url(), autocommit=True)
    # Put our schema first on the search_path so unqualified references hit
    # `sim2sim.licenses` rather than nothing in `public`.
    with conn.cursor() as cur:
        cur.execute("SET search_path TO sim2sim, public")
    return conn


def _pg_fetch_one(sql: str, params: tuple) -> Optional[_DictRow]:
    with _pg_connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d.name for d in cur.description]
        return _DictRow(cols, row)


def _pg_execute(sql: str, params: tuple) -> None:
    with _pg_connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)


# ── SQLite helpers ───────────────────────────────────────────────────────────


def _sqlite_conn() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# Backward-compat: some older code/tests might reach in for get_conn().
def get_conn() -> sqlite3.Connection:
    """Legacy helper — SQLite only.  Postgres callers should use the
    backend-aware functions below."""
    return _sqlite_conn()


# ── Public API ───────────────────────────────────────────────────────────────


def init_db() -> None:
    """Create tables if they don't exist.  Safe to call repeatedly."""
    with _LOCK:
        if _use_postgres():
            with _pg_connect() as conn, conn.cursor() as cur:
                for stmt in _PG_SCHEMA_STATEMENTS:
                    cur.execute(stmt)
        else:
            conn = _sqlite_conn()
            try:
                conn.executescript(_SQLITE_SCHEMA)
            finally:
                conn.close()


def reset_db() -> None:
    """Drop and recreate.  Test-only helper."""
    with _LOCK:
        if _use_postgres():
            with _pg_connect() as conn, conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS sim2sim.licenses")
            init_db()
        else:
            path = db_path()
            if path.exists():
                path.unlink()
            init_db()


def find_by_stripe_session(session_id: str):
    if _use_postgres():
        return _pg_fetch_one(
            "SELECT * FROM sim2sim.licenses WHERE stripe_session_id = %s",
            (session_id,),
        )
    conn = _sqlite_conn()
    try:
        cur = conn.execute(
            "SELECT * FROM licenses WHERE stripe_session_id = ?",
            (session_id,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def find_by_key(key: str):
    if _use_postgres():
        return _pg_fetch_one(
            "SELECT * FROM sim2sim.licenses WHERE key = %s",
            (key,),
        )
    conn = _sqlite_conn()
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
    if _use_postgres():
        _pg_execute(
            "INSERT INTO sim2sim.licenses (key, tier, email, created_at, stripe_session_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (key, tier, email, created_at, stripe_session_id),
        )
        return
    conn = _sqlite_conn()
    try:
        conn.execute(
            "INSERT INTO licenses (key, tier, email, created_at, stripe_session_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, tier, email, created_at, stripe_session_id),
        )
    finally:
        conn.close()


def record_activation(key: str, activated_at: str) -> None:
    if _use_postgres():
        _pg_execute(
            "UPDATE sim2sim.licenses "
            "SET activation_count = activation_count + 1, "
            "    activated_at = COALESCE(activated_at, %s) "
            "WHERE key = %s",
            (activated_at, key),
        )
        return
    conn = _sqlite_conn()
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
