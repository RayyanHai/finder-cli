from __future__ import annotations

from pathlib import Path

from finder_cli.collect import symlink_results
from finder_cli.search import SearchResult


def test_basic_symlink_creation(tmp_path: Path) -> None:
    # Setup fake source files
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    file1 = src_dir / "hw3.pdf"
    file1.touch()
    
    results = [SearchResult(path=str(file1), filename="hw3.pdf", extension=".pdf", size_bytes=100, modified_at=0.0)]
    
    dest = tmp_path / "dest"
    
    count = symlink_results(results, dest)
    
    assert count == 1
    assert dest.exists()
    assert dest.is_dir()
    
    linked_file = dest / "hw3.pdf"
    assert linked_file.exists()
    assert linked_file.is_symlink()
    assert linked_file.resolve() == file1.resolve()


def test_clear_symlinks_on_next_run(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    file1 = src_dir / "a.txt"
    file1.touch()
    
    dest = tmp_path / "dest"
    dest.mkdir()
    
    # Create an old symlink in dest
    old_link = dest / "old.txt"
    old_link.symlink_to(file1)
    assert old_link.exists()
    
    results = [SearchResult(path=str(file1), filename="a.txt", extension=".txt", size_bytes=0, modified_at=0.0)]
    
    symlink_results(results, dest, clear=True)
    
    assert not old_link.exists()
    assert (dest / "a.txt").exists()


def test_clear_true_does_not_remove_regular_files(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    
    # Create a regular file in dest
    regular_file = dest / "important_data.txt"
    regular_file.write_text("don't delete me!")
    
    symlink_results([], dest, clear=True)
    
    assert regular_file.exists()
    assert regular_file.read_text() == "don't delete me!"


def test_filename_collision_handling(tmp_path: Path) -> None:
    # Set up src file structures that collide in filenames
    dir1 = tmp_path / "math"
    dir1.mkdir()
    file1 = dir1 / "hw.pdf"
    file1.touch()
    
    dir2 = tmp_path / "science"
    dir2.mkdir()
    file2 = dir2 / "hw.pdf"
    file2.touch()
    
    # Third collision with same parent dir name but different path
    dir3 = tmp_path / "other" / "science"
    dir3.mkdir(parents=True)
    file3 = dir3 / "hw.pdf"
    file3.touch()
    
    results = [
        SearchResult(path=str(file1), filename="hw.pdf", extension=".pdf", size_bytes=0, modified_at=0.0),
        SearchResult(path=str(file2), filename="hw.pdf", extension=".pdf", size_bytes=0, modified_at=0.0),
        SearchResult(path=str(file3), filename="hw.pdf", extension=".pdf", size_bytes=0, modified_at=0.0)
    ]
    
    dest = tmp_path / "dest"
    count = symlink_results(results, dest)
    
    assert count == 3
    links = [p.name for p in dest.iterdir()]
    assert "hw.pdf" in links
    assert "hw__science.pdf" in links
    assert "hw__other.pdf" in links  # It picked the next unique ancestor
    
    # 4th collision to force numeric fallback
    # pre-fill all of file2's ancestors' candidate names in dest
    for p in file2.resolve().parents:
        if p == p.parent:
            break
        candidate = f"hw__{p.name}.pdf"
        (dest / candidate).touch()

    results = [SearchResult(path=str(file2), filename="hw.pdf", extension=".pdf", size_bytes=0, modified_at=0.0)]
    symlink_results(results, dest, clear=False)
    links = [p.name for p in dest.iterdir()]
    assert "hw__2.pdf" in links
    
