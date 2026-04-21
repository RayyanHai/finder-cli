"""Command-line interface.

Typer builds the argparse setup from type hints, so adding a new flag is as
simple as adding a parameter to a function. Rich handles pretty output.

Three commands for Phase 1:
    finder-cli reindex              # rebuild the index
    finder-cli search <term> ...    # query the index
    finder-cli status               # show index stats

TODO markers below show what you need to fill in. The `reindex` command is
done as a reference — notice the pattern: parse args, call into a module,
render the result with Rich.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import collect, db, indexer, search as search_mod

app = typer.Typer(
    help="Fast local file search for macOS. Better than Spotlight for dev/student workflows.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def reindex(
    root: Optional[list[Path]] = typer.Option(
        None,
        "--root",
        "-r",
        help="Directory to index. Can be passed multiple times. Defaults to ~/Downloads, ~/Documents, ~/Desktop.",
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Nuke the DB and rebuild from scratch. Use if the index seems corrupt or stale.",
    ),
) -> None:
    """Rebuild the file index. Run this whenever you want fresh results."""
    roots = root if root else None
    if full:
        db.reset_db()
        console.print("[yellow]Reset index DB.[/]")
    with console.status("[bold cyan]Indexing files...[/]"):
        stats = indexer.index_roots(roots=roots)

    console.print(
        f"[green]✓[/] Indexed [bold]{stats.indexed:,}[/] files "
        f"in [bold]{stats.elapsed_sec:.2f}s[/] "
        f"([dim]{stats.scanned:,} scanned, {stats.skipped:,} skipped, "
        f"{stats.errors:,} errors[/])"
    )


@app.command()
def search(
    term: Optional[str] = typer.Argument(None, help="Text to match in filename."),
    type: Optional[list[str]] = typer.Option(
        None,
        "--type",
        "-t",
        help="File extension filter (pdf, pptx, etc). Can be passed multiple times.",
    ),
    modified_since: Optional[str] = typer.Option(
        None,
        "--since",
        help="Only files modified after this duration ago (e.g. '7d', '2h').",
    ),
    in_folder: Optional[str] = typer.Option(
        None,
        "--in",
        help="Only files under a folder whose path contains this substring.",
    ),
    limit: int = typer.Option(25, "--limit", "-n", help="Max results to show."),
    link_to: Optional[Path] = typer.Option(
        None,
        "--link-to",
        help="Folder to symlink search results into.",
    ),
    reveal: bool = typer.Option(
        False,
        "--reveal",
        help="Open results in Finder.",
    ),
) -> None:
    """Search the index. See `finder-cli search --help` for filter options."""
    exts = [search_mod.normalize_extension(e) for e in type] if type else None
    since_ts = search_mod.parse_duration(modified_since) if modified_since else None

    query = search_mod.SearchQuery(
        term=term,
        extensions=exts,
        modified_since=since_ts,
        parent_contains=in_folder,
        limit=limit,
    )
    results = search_mod.search(query)

    if not results:
        console.print("[yellow]No results.[/] Try broadening your query, "
                      "or run [bold]finder-cli status[/] to check if the index is stale.")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Filename")
    table.add_column("Folder", overflow="fold", max_width=50)
    table.add_column("Modified", justify="right")
    table.add_column("Size", justify="right")

    for r in results:
        folder = str(Path(r.path).parent)
        table.add_row(r.filename, folder, _humanize_age(r.modified_at), _humanize_size(r.size_bytes))

    console.print(table)
    console.print(f"[dim]{len(results)} result(s)[/]")

    if link_to:
        if len(results) > 10:
            if not typer.confirm(f"Link {len(results)} files to {link_to}?"):
                return
        
        created = collect.symlink_results(results, link_to)
        console.print(f"[green]✓[/] Linked {created} files to {link_to}")

    if reveal:
        if link_to:
            collect.reveal_in_finder([link_to])
        else:
            collect.reveal_in_finder([Path(r.path) for r in results])


@app.command()
def status() -> None:
    """Show index stats: how many files, when last updated."""
    stats = search_mod.get_stats()

    last = stats["last_indexed_at"]
    last_str = _humanize_age(last) if last else "never"

    table = Table(show_header=False, box=None)
    table.add_row("[bold]Total files[/]", f"{stats['total_files']:,}")
    table.add_row("[bold]Last indexed[/]", last_str)
    table.add_row("[bold]DB size[/]", _humanize_size(stats["db_size_bytes"]))
    table.add_row("[bold]DB path[/]", f"[dim]{stats['db_path']}[/]")

    console.print(table)


def _humanize_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"


def _humanize_age(ts: float) -> str:
    delta = max(0, time.time() - ts)
    for seconds, suffix in ((86400, "d"), (3600, "h"), (60, "m")):
        if delta >= seconds:
            return f"{int(delta // seconds)}{suffix} ago"
    return f"{int(delta)}s ago"


# Not a CLI command, just an entry point for `python -m finder_cli`.
def main() -> None:
    app()


if __name__ == "__main__":
    main()
