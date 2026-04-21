# finder-cli

> Fast, local, AI-ready file search for macOS — built because Spotlight doesn't cut it for dev and student workflows.

`finder-cli` is a command-line tool that indexes your files into a local SQLite database and lets you search by filename, extension, folder, and recency — in milliseconds. I plan to grow it as I have more time. Phase 1 is pure metadata search, Phase 2 adds full-text content indexing, Phase 3 layers on semantic search and natural-language queries powered by embeddings.

```bash
$ finder-cli search "pigeonhole" --type pdf --since 30d
┌────────────────────────────┬────────────────────────────┬──────────┬────────┐
│ Filename                   │ Folder                     │ Modified │   Size │
├────────────────────────────┼────────────────────────────┼──────────┼────────┤
│ CS311_HW3_solutions.pdf    │ ~/Documents/school/cs311   │ 2d ago   │ 412 KB │
│ pigeonhole_proofs.pdf      │ ~/Downloads                │ 5d ago   │ 180 KB │
└────────────────────────────┴────────────────────────────┴──────────┴────────┘
```

## Why this exists

macOS Spotlight is opinionated in ways that hurt technical users. It hides dotfiles, buries recent downloads under apps and contacts, and offers no way to say "give me every PDF I touched in the last week from my school folder." I was losing ~5 minutes a day digging through Finder for files I knew were *somewhere*.

I find macOS Spotlight and the other ways to find files to be very confusing and annoying to use. Sometimes I want to just get files with a certain name or filetype, get them all in one place, and put them where I need to. Like when I'm adding downloaded problem set solutions to a NotebookLM to study them, I have to manually search usually so I created this tool to automate that process.

## Features

**Phase 1 (current)**
- Recursive indexing of arbitrary root directories, with a configurable skip-list (`node_modules`, `.git`, `Library`, etc.)
- SQLite-backed index — no daemon, no server, `~/.finder-cli/index.db` is the whole database
- Substring, extension, and date-range filters composable from the CLI
- Stage results via symlinks (`--link-to`) for easy batch processing (e.g. uploading batch context to an AI tool), and open them directly in macOS Finder (`--reveal`)
- Idempotent reindex — run it as often as you want, safe by default
- Pretty terminal output via [Rich](https://github.com/Textualize/rich)
  
> **Note**: Symlinks created by `--link-to` reflect the filesystem state at the time of collection. If the original files are moved or deleted later, the links will break.

Example Staging Workflow (e.g. for bulk AI tool ingestion):
```bash
finder-cli search "discrete math" --type pdf --link-to ~/ai-staging --reveal
```

**Phase 2 (planned)**
- Full-text search over file *contents* (PDFs, Word, Powerpoint, plain text) using SQLite FTS5
- Incremental reindexing via `mtime` comparison — only reparse files that changed

**Phase 3 (planned)**
- Semantic search with local embeddings (`sentence-transformers`) — "graph coloring homework" matches `CS311_HW4_final.pdf` even though none of those words appear in the filename
- Natural-language queries (`finder-cli ask "my slides about RAG from last week"`) via an LLM that translates intent into structured filters

**Phase 4 (stretch)**
- macOS menu bar app wrapping the Python core

## Architecture

```
┌─────────────┐       ┌─────────────┐       ┌──────────────┐
│   CLI       │──────▶│  Search     │──────▶│   SQLite     │
│  (typer)    │       │  (SQL gen)  │       │  + FTS5      │
└─────────────┘       └─────────────┘       └──────▲───────┘
                                                   │
┌─────────────┐       ┌─────────────┐              │
│   Filesystem│──────▶│  Indexer    │──────────────┘
│   (scandir) │       │  (batched)  │
└─────────────┘       └─────────────┘
```

Module responsibilities:
- `config.py` — paths, ignore lists, size caps. One place to tune the whole tool.
- `db.py` — SQLite schema, connection context manager, schema versioning.
- `indexer.py` — walks the filesystem, extracts metadata, batches inserts.
- `search.py` — builds parameterized SQL from structured query objects, returns typed results.
- `cli.py` — Typer app that binds CLI flags to search/index operations.

## Design decisions worth calling out

- **SQLite over anything fancier.** Zero setup, single file, fast enough for millions of rows. FTS5 is built in for Phase 2. A heavier choice (Postgres, Elasticsearch) would be overkill for a local-first tool and would kill the "install and go" UX.
- **`os.scandir` over `pathlib.iterdir`.** `scandir` returns `DirEntry` objects with cached stat info. On a 50k-file tree, the difference is roughly 10× indexing speed.
- **Batched inserts with `INSERT ... ON CONFLICT DO UPDATE`.** Makes reindex idempotent and ~100× faster than one-at-a-time inserts.
- **Structured query objects, not query strings.** `search.py` takes a `SearchQuery` dataclass, not a natural-language string. Keeps the search layer testable and makes the Phase 3 NL layer a thin translator on top, not a rewrite.
- **Schema versioning from day one.** `SCHEMA_VERSION` in `db.py` lets the index survive future changes without manual intervention.

## Install & run

```bash
# clone + install
git clone https://github.com/YOUR_USERNAME/finder-cli.git
cd finder-cli
pip install -e .

# build the index (first run takes ~10s per 10k files)
finder-cli reindex

# search
finder-cli search "cs311" --type pdf
finder-cli search "lecture" --type pptx --since 7d
finder-cli search --in school --since 1d

# index stats
finder-cli status
```

## Roadmap

- [x] Phase 1: metadata indexing + CLI
- [ ] Phase 2: content extraction + FTS5
- [ ] Phase 3: embeddings + NL queries
- [ ] Phase 4: menu bar app
- [ ] Rewrite indexer hot path in Go for a 10× speedup (stretch)

## License

MIT
