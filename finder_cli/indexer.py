"""Filesystem indexer.

Walks a directory tree, extracts metadata for each interesting file, and
upserts rows into the SQLite index. This is the one module I'm giving you
fully implemented — it's mostly plumbing (os.walk + stat + SQL) and getting
the details right matters (symlink loops, permission errors, etc.). The
interesting algorithmic work is in search.py.

Design notes:
- We use os.scandir (not pathlib.Path.iterdir) because it's significantly
  faster: scandir returns DirEntry objects that cache stat info.
- We INSERT OR REPLACE on conflict because path is UNIQUE. This makes reindex
  idempotent — run it as many times as you want, result is the same.
- We batch inserts in chunks. Doing one INSERT per file is 10-100x slower
  than batching, on a 10k-file tree the difference is real.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .config import (
    DEFAULT_ROOTS,
    IGNORED_DIR_NAMES,
    INTERESTING_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
)
from .db import get_connection, init_db

# Insert batch size. 500 is a sweet spot — large enough to amortize SQLite's
# per-transaction overhead, small enough that a crash doesn't lose much work.
BATCH_SIZE = 500


@dataclass
class IndexStats:
    """Summary of what an indexing run did. Used by the CLI to print a report."""
    scanned: int = 0      # files we looked at
    indexed: int = 0      # files we actually wrote to the DB
    skipped: int = 0      # files filtered out (wrong ext, too big, etc.)
    errors: int = 0       # permission denied, broken symlinks, etc.
    elapsed_sec: float = 0.0


def _should_index_file(entry: os.DirEntry) -> bool:
    """Filter: is this file worth indexing?

    Rules:
    - Must be a regular file (not symlink, not device, etc.)
    - Extension must be in our whitelist
    - Under our size cap
    """
    try:
        if not entry.is_file(follow_symlinks=False):
            return False
        ext = Path(entry.name).suffix.lower()
        if ext not in INTERESTING_EXTENSIONS:
            return False
        if entry.stat(follow_symlinks=False).st_size > MAX_FILE_SIZE_BYTES:
            return False
        return True
    except OSError:
        # Permission denied, broken symlink, etc. Caller counts this as an error.
        return False


def _walk_tree(root: Path) -> Iterator[os.DirEntry]:
    """Yield DirEntry objects for every file under `root`, pruning ignored dirs.

    Using a manual stack rather than os.walk because os.walk doesn't give us
    DirEntry objects with cached stat — we'd have to stat every file again.

    We prune ignored directories aggressively: skipping node_modules once
    saves thousands of stat calls.
    """
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in IGNORED_DIR_NAMES or entry.name.startswith("."):
                            continue
                        stack.append(Path(entry.path))
                    else:
                        yield entry
        except (PermissionError, FileNotFoundError):
            # Silently skip dirs we can't read. Could bubble this up as an
            # error count if you want to report it.
            continue


def _entry_to_row(entry: os.DirEntry, now: float) -> tuple:
    """Convert a DirEntry into the tuple we'll INSERT into `files`."""
    stat = entry.stat(follow_symlinks=False)
    path = entry.path
    name = entry.name
    ext = Path(name).suffix.lower() or None
    parent = str(Path(path).parent)

    # macOS exposes st_birthtime (actual creation time). On Linux it falls
    # back to st_ctime which is "change time" — close enough for this tool.
    created = getattr(stat, "st_birthtime", stat.st_ctime)

    return (
        path,               # path
        name.lower(),       # filename (for matching)
        name,               # filename_raw (for display)
        ext,                # extension
        parent,             # parent_dir
        stat.st_size,       # size_bytes
        created,            # created_at
        stat.st_mtime,      # modified_at
        now,                # indexed_at
    )


UPSERT_SQL = """
INSERT INTO files
    (path, filename, filename_raw, extension, parent_dir,
     size_bytes, created_at, modified_at, indexed_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(path) DO UPDATE SET
    filename     = excluded.filename,
    filename_raw = excluded.filename_raw,
    extension    = excluded.extension,
    parent_dir   = excluded.parent_dir,
    size_bytes   = excluded.size_bytes,
    created_at   = excluded.created_at,
    modified_at  = excluded.modified_at,
    indexed_at   = excluded.indexed_at
"""


def index_roots(
    roots: Iterable[Path] | None = None,
    progress_callback=None,
) -> IndexStats:
    """Index every interesting file under each root directory.

    Args:
        roots: directories to scan. Defaults to DEFAULT_ROOTS from config.
        progress_callback: optional fn(scanned_count) called every BATCH_SIZE
            files. Lets the CLI show a live progress bar.

    Returns IndexStats. Call this from `finder-cli reindex`.
    """
    roots = list(roots) if roots else DEFAULT_ROOTS
    init_db()
    stats = IndexStats()
    start = time.perf_counter()
    now = time.time()

    batch: list[tuple] = []

    with get_connection() as conn:
        for root in roots:
            if not root.exists():
                continue
            for entry in _walk_tree(root):
                stats.scanned += 1
                try:
                    if not _should_index_file(entry):
                        stats.skipped += 1
                        continue
                    batch.append(_entry_to_row(entry, now))
                    stats.indexed += 1

                    if len(batch) >= BATCH_SIZE:
                        conn.executemany(UPSERT_SQL, batch)
                        batch.clear()
                        if progress_callback:
                            progress_callback(stats.scanned)
                except OSError:
                    stats.errors += 1

        # Flush the final partial batch.
        if batch:
            conn.executemany(UPSERT_SQL, batch)

    stats.elapsed_sec = time.perf_counter() - start
    return stats
