"""Stage search results as symlinks and/or reveal them in Finder.

The motivating workflow: search for "all my discrete-math PDFs from the last
month", funnel the hits into a single folder as symlinks, then drag that
folder into an AI tool (or any tool that takes a directory). Symlinks mean
we don't duplicate bytes and the originals stay where they live.

Why symlinks and not copies: Many batch-ingestion tools typically read bytes
once at upload. A copy would double disk usage; a symlink is ~0 cost and
keeps "truth" in one place. The tradeoff is that broken-link-on-move is a
thing — documented at the CLI layer.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Union

from .search import SearchResult

PathLike = Union[str, Path]


def symlink_results(
    results: list[SearchResult],
    dest: Path,
    clear: bool = True,
) -> int:
    """Materialize `results` as symlinks under `dest`.

    Collisions (two results with the same basename) are disambiguated by
    walking up the source path and appending ancestor directory names —
    `hw3.pdf` from `.../school/hw3.pdf` becomes `hw3__school.pdf` if the
    bare name is taken. Numeric suffixes are a last resort.

    `clear=True` wipes prior symlinks only — real files in `dest` are left
    alone so a misconfigured run can't nuke user data.
    """
    dest.mkdir(parents=True, exist_ok=True)
    if clear:
        _clear_symlinks(dest)

    created = 0
    for r in results:
        src = Path(r.path).resolve()
        link_path = dest / _pick_unique_name(Path(r.filename), src, dest)
        link_path.symlink_to(src)
        created += 1
    return created


def reveal_in_finder(paths: list[PathLike]) -> None:
    """Open each `paths` entry in Finder (macOS `open -R`).

    More than 10 paths → open the first path's parent directory instead.
    A screenful of Finder windows is worse than none.

    `check=False`: on non-macOS systems `open -R` may not exist; we prefer
    a silent no-op to a crash mid-workflow.
    """
    if not paths:
        return
    if len(paths) > 10:
        parent = Path(paths[0]).parent
        subprocess.run(["open", str(parent)], check=False)
        return
    for p in paths:
        subprocess.run(["open", "-R", str(p)], check=False)


def _clear_symlinks(dest: Path) -> None:
    for entry in dest.iterdir():
        if entry.is_symlink():
            entry.unlink()


def _pick_unique_name(filename: Path, src: Path, dest: Path) -> str:
    """Find a non-colliding name for `filename` in `dest`.

    Walks src's ancestors to build `stem__ancestor.ext`, then falls back to
    `stem__N.ext`. Order matters: ancestor-based names are more informative
    than numeric suffixes when the user later eyeballs the staging dir.
    """
    if not (dest / filename.name).exists():
        return filename.name

    stem, suffix = filename.stem, filename.suffix
    for ancestor in src.parents:
        if ancestor == ancestor.parent:
            break
        candidate = f"{stem}__{ancestor.name}{suffix}"
        if not (dest / candidate).exists():
            return candidate

    n = 2
    while (dest / f"{stem}__{n}{suffix}").exists():
        n += 1
    return f"{stem}__{n}{suffix}"
