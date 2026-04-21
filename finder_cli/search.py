"""Search over the file index.

THIS IS THE MODULE YOU WRITE. The indexer is done; now we query the data it
built. Implementing this well is where you'll learn the most — it's all about
composing SQL WHERE clauses from user-supplied filters, then ranking results.

Read through the TODOs in order. The function signatures are fixed (the CLI
imports them by name), but the implementations are yours.

Hints:
- Build up a list of WHERE clause fragments and a list of params, then join
  them with ' AND '. This pattern scales cleanly as you add filters.
- Parameterize EVERY user input. Never f-string a value into SQL — that's
  SQL injection waiting to happen, even for a local tool.
- For fuzzy filename matching in phase 1, start with `LIKE '%term%'`. It's
  crude but it works. Upgrade to FTS5 in Phase 2.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .db import get_connection


@dataclass
class SearchResult:
    """One hit from a search. The CLI renders these as a table."""
    path: str
    filename: str          # display name (raw casing)
    extension: Optional[str]
    size_bytes: int
    modified_at: float     # unix ts
    score: float = 0.0     # ranking score — unused in phase 1, matters in phase 3


@dataclass
class SearchQuery:
    """What the user asked for. Populated by the CLI from command-line flags."""
    term: Optional[str] = None                 # substring to match in filename
    extensions: Optional[list[str]] = None     # e.g. ['.pdf', '.pptx'] — match ANY
    modified_since: Optional[float] = None     # unix ts — only files modified AFTER this
    modified_before: Optional[float] = None    # unix ts
    parent_contains: Optional[str] = None      # substring to match in parent_dir path
    limit: int = 25


def search(query: SearchQuery) -> list[SearchResult]:
    """Run a search against the index.

    TODO (you):
      1. Build WHERE clauses from the non-None fields on `query`.
         - term       -> filename LIKE ?     (remember to lowercase + wrap in %%)
         - extensions -> extension IN (...)  (careful: need right number of ?'s)
         - modified_since / _before -> modified_at > ? / < ?
         - parent_contains -> parent_dir LIKE ?
      2. If there are no filters at all, decide what to do. Return empty?
         Return most recent N files? (I'd return recent — more useful.)
      3. ORDER BY modified_at DESC (most recent first) for Phase 1.
         Phase 3 will use a real ranking score.
      4. LIMIT by query.limit.
      5. Convert rows to SearchResult objects and return.

    Common pitfall: the `IN (...)` clause needs exactly as many `?` placeholders
    as there are items. Use ','.join(['?'] * len(extensions)).
    """

    where: list[str] = []
    params: list = []

    if query.term:
        # SQLite LIKE folds case for ASCII only — "résumé" won't match "RÉSUMÉ".
        # Good enough for Phase 1; revisit with ICU or unicodedata if needed.
        where.append("filename LIKE ?")
        params.append(f"%{query.term.lower()}%")

    if query.extensions:
        exts = [normalize_extension(e) for e in query.extensions]
        placeholders = ",".join(["?"] * len(exts))
        where.append(f"extension IN ({placeholders})")
        params.extend(exts)

    if query.modified_since is not None:
        where.append("modified_at > ?")
        params.append(query.modified_since)

    if query.modified_before is not None:
        where.append("modified_at < ?")
        params.append(query.modified_before)

    if query.parent_contains:
        where.append("parent_dir LIKE ?")
        params.append(f"%{query.parent_contains}%")

    sql = (
        "SELECT path, filename_raw, extension, size_bytes, modified_at "
        "FROM files"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY modified_at DESC LIMIT ?"
    params.append(query.limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        SearchResult(
            path=r["path"],
            filename=r["filename_raw"],
            extension=r["extension"],
            size_bytes=r["size_bytes"],
            modified_at=r["modified_at"],
        )
        for r in rows
    ]


def get_stats() -> dict:
    """Summary info about the index: file count, last-indexed time, DB size.

    TODO (you): SELECT COUNT(*), MAX(indexed_at) from `files`.
    Return as a dict the CLI can render. This powers `finder-cli status`.
    """
    from .config import INDEX_DB

    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, MAX(indexed_at) AS last_indexed FROM files"
        ).fetchone()

    db_size = INDEX_DB.stat().st_size if INDEX_DB.exists() else 0

    return {
        "total_files": row["total"] or 0,
        "last_indexed_at": row["last_indexed"],
        "db_size_bytes": db_size,
        "db_path": str(INDEX_DB),
    }


# ---------------------------------------------------------------------------
# Helpers you might find useful when implementing search()
# ---------------------------------------------------------------------------

def parse_duration(s: str) -> float:
    """Parse strings like '7d', '2h', '30m' into seconds.

    Used by the CLI to turn `--modified-since 7d` into a timestamp filter.
    Returns a unix timestamp = now - duration.
    """

    for suffix, multiplier in [('s', 1), ('m', 60), ('h', 3600), ('d', 86400), ('w', 604800)]:
        if s.endswith(suffix):
            try:
                value = float(s[:-len(suffix)])
            except ValueError:  
                raise ValueError(f"Invalid duration value: {s}")
            return time.time() - value * multiplier
    raise ValueError(f"Invalid duration: {s!r} (expected e.g. '7d', '2h', '30m')")

def normalize_extension(ext: str) -> str:
    """Accept 'pdf' or '.pdf' or '.PDF' and return '.pdf'.

    Makes the CLI forgiving — users shouldn't have to remember the dot.
    """
    ext = ext.lower().strip()
    if not ext.startswith("."):
        ext = "." + ext
    return ext
