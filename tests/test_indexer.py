"""Test the indexer against a synthetic file tree.

This file gives you one working test and a stub for the others. Writing tests
for search() as you implement it is a great forcing function — if it's hard
to test, the API is probably wrong.

Run with:  pytest tests/
"""
from __future__ import annotations

from pathlib import Path

import pytest

from finder_cli import db, indexer
from finder_cli.search import SearchQuery, get_stats, parse_duration, search


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    """Build a realistic-ish test file tree under pytest's tmp_path."""
    (tmp_path / "Downloads" / "slides").mkdir(parents=True)
    (tmp_path / "Downloads" / "node_modules").mkdir()  # should be skipped
    (tmp_path / "Documents" / "school").mkdir(parents=True)

    (tmp_path / "Downloads" / "slides" / "lecture1.pptx").write_text("x")
    (tmp_path / "Downloads" / "slides" / "lecture2.pptx").write_text("x")
    (tmp_path / "Downloads" / "random.pdf").write_text("x")
    (tmp_path / "Downloads" / "node_modules" / "junk.js").write_text("x")
    (tmp_path / "Documents" / "school" / "hw3.pdf").write_text("x")
    (tmp_path / "Documents" / "school" / "notes.txt").write_text("x")
    (tmp_path / "Documents" / "school" / "photo.heic").write_text("x")  # not in whitelist

    return tmp_path


def test_indexer_counts_files(sample_tree: Path, tmp_path: Path, monkeypatch):
    """Smoke test: indexer walks the tree and writes the right number of rows."""
    # Point the DB at a fresh location inside tmp_path so we don't clobber real data.
    test_db = tmp_path / "test_index.db"
    monkeypatch.setattr(db, "INDEX_DB", test_db)
    monkeypatch.setattr(indexer, "DEFAULT_ROOTS", [sample_tree])

    stats = indexer.index_roots()

    # Expected: 2 pptx + 2 pdf + 1 txt = 5 indexed.
    # .heic and junk.js inside node_modules should be skipped.
    assert stats.indexed == 5
    assert stats.errors == 0


def test_indexer_is_idempotent(sample_tree: Path, tmp_path: Path, monkeypatch):
    """Running reindex twice shouldn't create duplicate rows."""
    test_db = tmp_path / "test_index.db"
    monkeypatch.setattr(db, "INDEX_DB", test_db)
    monkeypatch.setattr(indexer, "DEFAULT_ROOTS", [sample_tree])

    indexer.index_roots()
    stats = indexer.index_roots()

    with db.get_connection(test_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    assert count == stats.indexed  # no duplicates


@pytest.fixture
def indexed_tree(sample_tree: Path, tmp_path: Path, monkeypatch) -> Path:
    """Indexed sample tree — shared setup for search tests."""
    test_db = tmp_path / "test_index.db"
    monkeypatch.setattr(db, "INDEX_DB", test_db)
    monkeypatch.setattr(indexer, "DEFAULT_ROOTS", [sample_tree])
    indexer.index_roots()
    return sample_tree


def test_search_by_term_returns_matching_files(indexed_tree: Path):
    results = search(SearchQuery(term="lecture"))
    names = sorted(r.filename for r in results)
    assert names == ["lecture1.pptx", "lecture2.pptx"]


def test_search_term_is_case_insensitive(indexed_tree: Path):
    results = search(SearchQuery(term="LECTURE"))
    assert len(results) == 2


def test_search_filters_by_extension(indexed_tree: Path):
    results = search(SearchQuery(extensions=[".pdf"]))
    assert len(results) == 2
    assert all(r.extension == ".pdf" for r in results)


def test_search_extension_accepts_bare_suffix(indexed_tree: Path):
    # normalize_extension should accept 'pdf' and '.PDF'
    results = search(SearchQuery(extensions=["pdf"]))
    assert len(results) == 2


def test_search_multiple_extensions(indexed_tree: Path):
    results = search(SearchQuery(extensions=[".pdf", ".pptx"]))
    exts = {r.extension for r in results}
    assert exts == {".pdf", ".pptx"}
    assert len(results) == 4


def test_search_parent_contains(indexed_tree: Path):
    results = search(SearchQuery(parent_contains="school"))
    assert len(results) == 2
    assert all("school" in r.path for r in results)


def test_search_respects_limit(indexed_tree: Path):
    results = search(SearchQuery(limit=2))
    assert len(results) == 2


def test_search_no_filters_returns_recent(indexed_tree: Path):
    results = search(SearchQuery())
    assert len(results) == 5
    # ORDER BY modified_at DESC
    times = [r.modified_at for r in results]
    assert times == sorted(times, reverse=True)


def test_search_modified_since_filters_old_files(indexed_tree: Path):
    import time
    future = time.time() + 1000
    assert search(SearchQuery(modified_since=future)) == []


def test_search_modified_before_filters_new_files(indexed_tree: Path):
    assert search(SearchQuery(modified_before=0)) == []


def test_search_empty_when_no_match(indexed_tree: Path):
    assert search(SearchQuery(term="nonexistent_xyz")) == []


def test_search_combined_filters(indexed_tree: Path):
    results = search(SearchQuery(term="hw", extensions=[".pdf"]))
    assert len(results) == 1
    assert results[0].filename == "hw3.pdf"


def test_get_stats_reports_counts(indexed_tree: Path):
    stats = get_stats()
    assert stats["total_files"] == 5
    assert stats["last_indexed_at"] is not None
    assert stats["db_size_bytes"] > 0


def test_get_stats_empty_index(tmp_path: Path, monkeypatch):
    test_db = tmp_path / "empty.db"
    monkeypatch.setattr(db, "INDEX_DB", test_db)
    db.init_db()
    stats = get_stats()
    assert stats["total_files"] == 0
    assert stats["last_indexed_at"] is None


def test_parse_duration_handles_suffixes():
    import time
    now = time.time()
    assert abs(parse_duration("7d") - (now - 7 * 86400)) < 1
    assert abs(parse_duration("2h") - (now - 2 * 3600)) < 1
    assert abs(parse_duration("30m") - (now - 30 * 60)) < 1
    assert abs(parse_duration("1w") - (now - 604800)) < 1


def test_parse_duration_rejects_garbage():
    with pytest.raises(ValueError):
        parse_duration("abcd")
