from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path

from .bibtex import parse_bibtex, render_bibtex
from .expand import CrossrefExpander
from .extract import extract_references
from .resolve import MetadataResolver, merge_entries
from .storage import BibliographyStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="citegeist")
    parser.add_argument("--db", default="library.sqlite3", help="Path to the SQLite database")

    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest BibTeX into the database")
    ingest_parser.add_argument("input", help="BibTeX file to ingest")
    ingest_parser.add_argument("--status", default="draft", help="Initial review status")
    ingest_parser.add_argument("--source-label", help="Provenance label for this ingest run")

    search_parser = subparsers.add_parser("search", help="Search titles, abstracts, and fulltext")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=10, help="Maximum number of results")

    show_parser = subparsers.add_parser("show", help="Show one entry or list entries")
    show_parser.add_argument("citation_key", nargs="?", help="Citation key to show")
    show_parser.add_argument("--limit", type=int, default=20, help="Maximum entries when listing")
    show_parser.add_argument("--provenance", action="store_true", help="Include field provenance")

    export_parser = subparsers.add_parser("export", help="Export entries as BibTeX")
    export_parser.add_argument("citation_keys", nargs="*", help="Optional citation keys to export")
    export_parser.add_argument("--output", help="Write BibTeX to a file instead of stdout")

    status_parser = subparsers.add_parser("set-status", help="Set the review status for one entry")
    status_parser.add_argument("citation_key", help="Citation key to update")
    status_parser.add_argument("review_status", help="New review status")

    extract_parser = subparsers.add_parser("extract", help="Extract draft BibTeX from plaintext references")
    extract_parser.add_argument("input", help="Plaintext file containing bibliography-style references")
    extract_parser.add_argument("--output", help="Write extracted BibTeX to a file instead of stdout")

    resolve_parser = subparsers.add_parser("resolve", help="Enrich stored entries from external metadata sources")
    resolve_parser.add_argument("citation_keys", nargs="+", help="Citation keys to enrich")

    graph_parser = subparsers.add_parser("graph", help="Traverse citation relations from one or more seed entries")
    graph_parser.add_argument("citation_keys", nargs="+", help="Seed citation keys")
    graph_parser.add_argument(
        "--relation",
        action="append",
        dest="relations",
        choices=["cites", "cited_by", "crossref"],
        help="Relation type to traverse; may be passed multiple times",
    )
    graph_parser.add_argument("--depth", type=int, default=1, help="Maximum traversal depth")
    graph_parser.add_argument("--review-status", help="Filter results by target review status")
    graph_parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Show only unresolved target nodes that are not yet present in the database",
    )

    expand_parser = subparsers.add_parser("expand", help="Expand graph edges from external metadata sources")
    expand_parser.add_argument("citation_keys", nargs="+", help="Seed citation keys to expand")
    expand_parser.add_argument(
        "--source",
        choices=["crossref"],
        default="crossref",
        help="External source used for graph expansion",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    store = BibliographyStore(args.db)
    try:
        if args.command == "ingest":
            return _run_ingest(store, Path(args.input), args.status, args.source_label)
        if args.command == "search":
            return _run_search(store, args.query, args.limit)
        if args.command == "show":
            return _run_show(store, args.citation_key, args.limit, args.provenance)
        if args.command == "export":
            return _run_export(store, args.citation_keys, args.output)
        if args.command == "set-status":
            return _run_set_status(store, args.citation_key, args.review_status)
        if args.command == "extract":
            return _run_extract(Path(args.input), args.output)
        if args.command == "resolve":
            return _run_resolve(store, args.citation_keys)
        if args.command == "graph":
            return _run_graph(
                store,
                args.citation_keys,
                args.relations,
                args.depth,
                args.review_status,
                args.missing_only,
            )
        if args.command == "expand":
            return _run_expand(store, args.citation_keys, args.source)
    finally:
        store.close()

    parser.error(f"Unknown command: {args.command}")
    return 2


def _run_ingest(
    store: BibliographyStore,
    input_path: Path,
    review_status: str,
    source_label: str | None,
) -> int:
    text = input_path.read_text(encoding="utf-8")
    keys = store.ingest_bibtex(
        text,
        source_label=source_label or str(input_path),
        review_status=review_status,
    )
    for key in keys:
        print(key)
    return 0


def _run_search(store: BibliographyStore, query: str, limit: int) -> int:
    for row in store.search_text(query, limit=limit):
        score = row.get("score", 0.0)
        print(f"{row['citation_key']}\t{row.get('year') or ''}\t{score:.3f}\t{row.get('title') or ''}")
    return 0


def _run_show(store: BibliographyStore, citation_key: str | None, limit: int, provenance: bool) -> int:
    if citation_key:
        entry = store.get_entry(citation_key)
        if entry is None:
            print(f"Entry not found: {citation_key}", file=sys.stderr)
            return 1
        if provenance:
            entry["field_provenance"] = store.get_field_provenance(citation_key)
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


def _run_set_status(store: BibliographyStore, citation_key: str, review_status: str) -> int:
    if not store.set_entry_status(citation_key, review_status):
        print(f"Entry not found: {citation_key}", file=sys.stderr)
        return 1
    print(f"{citation_key}\t{review_status}")
    return 0


def _run_extract(input_path: Path, output: str | None) -> int:
    text = input_path.read_text(encoding="utf-8")
    entries = extract_references(text)
    rendered = render_bibtex(entries)
    if output:
        Path(output).write_text(rendered + ("\n" if rendered else ""), encoding="utf-8")
    else:
        if rendered:
            print(rendered)
    return 0


def _run_resolve(store: BibliographyStore, citation_keys: list[str]) -> int:
    resolver = MetadataResolver()
    exit_code = 0
    for citation_key in citation_keys:
        existing = store.get_entry(citation_key)
        if existing is None:
            print(f"Entry not found: {citation_key}", file=sys.stderr)
            exit_code = 1
            continue
        bibtex = store.get_entry_bibtex(citation_key)
        if not bibtex:
            print(f"Entry not renderable: {citation_key}", file=sys.stderr)
            exit_code = 1
            continue
        current_entry = parse_bibtex(bibtex)[0]
        resolution = resolver.resolve_entry(current_entry)
        if resolution is None:
            print(f"No resolver match: {citation_key}", file=sys.stderr)
            exit_code = 1
            continue
        merged = merge_entries(current_entry, resolution.entry)
        store.replace_entry(
            citation_key,
            merged,
            source_type=resolution.source_type,
            source_label=resolution.source_label,
            review_status="enriched",
        )
        print(f"{citation_key}\t{resolution.source_label}")
    return exit_code


def _run_graph(
    store: BibliographyStore,
    citation_keys: list[str],
    relations: list[str] | None,
    depth: int,
    review_status: str | None,
    missing_only: bool,
) -> int:
    rows = store.traverse_graph(
        citation_keys,
        relation_types=relations or ["cites"],
        max_depth=depth,
        review_status=review_status,
        include_missing=True,
    )
    if missing_only:
        rows = [row for row in rows if not row["target_exists"]]
    print(json.dumps(rows, indent=2))
    return 0


def _run_expand(store: BibliographyStore, citation_keys: list[str], source: str) -> int:
    if source != "crossref":
        print(f"Unsupported expansion source: {source}", file=sys.stderr)
        return 1

    expander = CrossrefExpander()
    all_results = []
    for citation_key in citation_keys:
        all_results.extend(expander.expand_entry_references(store, citation_key))
    print(json.dumps([asdict(result) for result in all_results], indent=2))
    return 0
