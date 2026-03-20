from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .storage import BibliographyStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="citegeist")
    parser.add_argument("--db", default="library.sqlite3", help="Path to the SQLite database")

    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest BibTeX into the database")
    ingest_parser.add_argument("input", help="BibTeX file to ingest")

    search_parser = subparsers.add_parser("search", help="Search titles, abstracts, and fulltext")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=10, help="Maximum number of results")

    show_parser = subparsers.add_parser("show", help="Show one entry or list entries")
    show_parser.add_argument("citation_key", nargs="?", help="Citation key to show")
    show_parser.add_argument("--limit", type=int, default=20, help="Maximum entries when listing")

    export_parser = subparsers.add_parser("export", help="Export entries as BibTeX")
    export_parser.add_argument("citation_keys", nargs="*", help="Optional citation keys to export")
    export_parser.add_argument("--output", help="Write BibTeX to a file instead of stdout")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    store = BibliographyStore(args.db)
    try:
        if args.command == "ingest":
            return _run_ingest(store, Path(args.input))
        if args.command == "search":
            return _run_search(store, args.query, args.limit)
        if args.command == "show":
            return _run_show(store, args.citation_key, args.limit)
        if args.command == "export":
            return _run_export(store, args.citation_keys, args.output)
    finally:
        store.close()

    parser.error(f"Unknown command: {args.command}")
    return 2


def _run_ingest(store: BibliographyStore, input_path: Path) -> int:
    text = input_path.read_text(encoding="utf-8")
    keys = store.ingest_bibtex(text)
    for key in keys:
        print(key)
    return 0


def _run_search(store: BibliographyStore, query: str, limit: int) -> int:
    for row in store.search_text(query, limit=limit):
        score = row.get("score", 0.0)
        print(f"{row['citation_key']}\t{row.get('year') or ''}\t{score:.3f}\t{row.get('title') or ''}")
    return 0


def _run_show(store: BibliographyStore, citation_key: str | None, limit: int) -> int:
    if citation_key:
        entry = store.get_entry(citation_key)
        if entry is None:
            print(f"Entry not found: {citation_key}", file=sys.stderr)
            return 1
        print(json.dumps(entry, indent=2, sort_keys=True))
        return 0

    print(json.dumps(store.list_entries(limit=limit), indent=2))
    return 0


def _run_export(store: BibliographyStore, citation_keys: list[str], output: str | None) -> int:
    rendered = store.export_bibtex(citation_keys or None)
    if output:
        Path(output).write_text(rendered + ("\n" if rendered else ""), encoding="utf-8")
    else:
        if rendered:
            print(rendered)
    return 0
