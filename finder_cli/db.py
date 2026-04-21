"""SQLite schema & connection helpers.

Why SQLite: zero setup, single-file, fast for this scale (hundreds of thousands
of files no problem), and FTS5 is built in for Phase 2 content search. For a
local-first tool it's almost always the right choice over Postgres/etc.

Why a separate module: keeps schema definition in one readable place, and makes
it easy to swap the backend later (e.g., DuckDB if you want columnar queries).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import INDEX_DB, INDEX_DIR

# Bumped when the schema changes in a breaking way. If this doesn't match
# what's in the DB, we nuke and rebuild. Simple migration story for a
# personal tool — don't need Alembic here.
SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT    NOT NULL UNIQUE,   -- absolute path, the natural key
    filename     TEXT    NOT NULL,          -- basename, lowercased for matching
    filename_raw TEXT    NOT NULL,          -- basename with original casing (for display)
    extension    TEXT,                      -- '.pdf', lowercased, nullable for extensionless files
    parent_dir   TEXT    NOT NULL,          -- absolute path of containing dir
    size_bytes   INTEGER NOT NULL,
    created_at   REAL    NOT NULL,          -- unix timestamp (float, from stat.st_birthtime)
    modified_at  REAL    NOT NULL,          -- unix timestamp
    indexed_at   REAL    NOT NULL           -- when WE saw this file — used for incremental reindex later
);

-- These indexes are what make search fast. Without them, filtering by
-- extension or recency does a full table scan.
CREATE INDEX IF NOT EXISTS idx_files_filename     ON files(filename);
CREATE INDEX IF NOT EXISTS idx_files_extension    ON files(extension);
CREATE INDEX IF NOT EXISTS idx_files_modified_at  ON files(modified_at);
CREATE INDEX IF NOT EXISTS idx_files_parent_dir   ON files(parent_dir);
"""


def _ensure_index_dir() -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with sensible defaults.

    - WAL mode lets the indexer write while search reads (future-proofing for
      when indexing runs in the background).
    - Row factory gives us dict-like access (row['filename'] instead of row[1]).
    - Foreign keys on because we'll add related tables in Phase 2.
    """
    _ensure_index_dir()
    path = db_path or INDEX_DB
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    """Create tables if they don't exist. Safe to call repeatedly."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        # Record the schema version so future migrations have something to check.
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))


def reset_db(db_path: Path | None = None) -> None:
    """Delete the DB file entirely. Used by `finder-cli reindex --full`."""
    path = db_path or INDEX_DB
    if path.exists():
        path.unlink()
    init_db(db_path)
