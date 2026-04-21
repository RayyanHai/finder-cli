"""Configuration: where we store the index, what to skip, sensible defaults.

Keeping this in one place means you change ignore rules or paths once, not
hunting through the codebase.
"""
from __future__ import annotations

from pathlib import Path

# Where the SQLite index lives. Hidden dir in the user's home keeps it out of
# the way but discoverable. If you ever want to blow it away, it's one command.
INDEX_DIR = Path.home() / ".finder-cli"
INDEX_DB = INDEX_DIR / "index.db"

# Default roots to index. The user can override via `--root` on the CLI.
# We stick to user-owned folders; indexing /System or /Library is a waste.
DEFAULT_ROOTS = [
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "Desktop",
]

# Folder names to skip entirely. These are either huge, full of junk, or
# both. Add to this list as you notice noise in your results.
IGNORED_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "Library",          # macOS user Library is huge and mostly useless to search
    ".Trash",
    ".DS_Store",
    "dist",
    "build",
    ".next",
    ".cache",
}

# File extensions we consider "interesting" for a student/dev workflow.
# Empty set means "index everything" — but you probably don't want to index
# every .pyc and .log file. Start narrow, widen as needed.
INTERESTING_EXTENSIONS = {
    # Docs & notes
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
    ".md", ".txt", ".rtf",
    # Code
    ".py", ".java", ".js", ".ts", ".tsx", ".jsx",
    ".c", ".cpp", ".h", ".hpp", ".go", ".rs",
    ".html", ".css", ".json", ".yaml", ".yml",
    # Media (metadata only for now)
    ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mov",
    # Archives
    ".zip", ".tar", ".gz",
}

# Skip files larger than this during indexing. Phase 1 is metadata only so
# size doesn't matter much, but this guards against indexing huge binaries
# by accident. Tune upward when you add content extraction.
MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB
