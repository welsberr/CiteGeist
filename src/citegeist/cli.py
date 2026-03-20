from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path

from .batch import BatchBootstrapRunner, load_batch_jobs
from .bibtex import parse_bibtex, render_bibtex
from .bootstrap import Bootstrapper
from .examples.talkorigins import TalkOriginsScraper
from .expand import CrossrefExpander, OpenAlexExpander, TopicExpander
from .extract import extract_references
from .harvest import OaiPmhHarvester
from .resolve import MetadataResolver, merge_entries_with_conflicts
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
    search_parser.add_argument("--topic", help="Optional topic slug to filter search results")

    show_parser = subparsers.add_parser("show", help="Show one entry or list entries")
    show_parser.add_argument("citation_key", nargs="?", help="Citation key to show")
    show_parser.add_argument("--limit", type=int, default=20, help="Maximum entries when listing")
    show_parser.add_argument("--provenance", action="store_true", help="Include field provenance")
    show_parser.add_argument("--conflicts", action="store_true", help="Include field conflicts")

    export_parser = subparsers.add_parser("export", help="Export entries as BibTeX")
    export_parser.add_argument("citation_keys", nargs="*", help="Optional citation keys to export")
    export_parser.add_argument("--output", help="Write BibTeX to a file instead of stdout")

    status_parser = subparsers.add_parser("set-status", help="Set the review status for one entry")
    status_parser.add_argument("citation_key", help="Citation key to update")
    status_parser.add_argument("review_status", help="New review status")

    conflict_parser = subparsers.add_parser("resolve-conflicts", help="Update conflict review status for one field")
    conflict_parser.add_argument("citation_key", help="Citation key to update")
    conflict_parser.add_argument("field_name", help="Field name whose open conflicts should be updated")
    conflict_parser.add_argument("status", choices=["accepted", "rejected"], help="New conflict status")

    apply_conflict_parser = subparsers.add_parser(
        "apply-conflict",
        help="Accept the proposed value for the latest open conflict on a field",
    )
    apply_conflict_parser.add_argument("citation_key", help="Citation key to update")
    apply_conflict_parser.add_argument("field_name", help="Field name whose proposed value should be applied")

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
        choices=["crossref", "openalex"],
        default="crossref",
        help="External source used for graph expansion",
    )
    expand_parser.add_argument(
        "--relation",
        choices=["cites", "cited_by"],
        default="cites",
        help="Graph direction to expand for sources that support it",
    )
    expand_parser.add_argument("--limit", type=int, default=25, help="Maximum related works to fetch per seed")

    expand_topic_parser = subparsers.add_parser(
        "expand-topic",
        help="Expand one topic from its existing seed entries and assign only relevant discoveries back to that topic",
    )
    expand_topic_parser.add_argument("topic_slug", help="Topic slug to expand from")
    expand_topic_parser.add_argument(
        "--topic-phrase",
        help="Optional phrase used for relevance gating; defaults to the stored topic name",
    )
    expand_topic_parser.add_argument(
        "--source",
        choices=["crossref", "openalex"],
        default="openalex",
        help="External source used for topic expansion",
    )
    expand_topic_parser.add_argument(
        "--relation",
        choices=["cites", "cited_by"],
        default="cites",
        help="Graph direction to expand for sources that support it",
    )
    expand_topic_parser.add_argument("--seed-limit", type=int, default=25, help="Maximum topic seed entries to expand from")
    expand_topic_parser.add_argument("--per-seed-limit", type=int, default=25, help="Maximum discovered works to fetch per seed")
    expand_topic_parser.add_argument(
        "--seed-key",
        action="append",
        dest="seed_keys",
        help="Restrict expansion to one trusted seed entry; may be passed multiple times",
    )
    expand_topic_parser.add_argument(
        "--min-relevance",
        type=float,
        default=0.2,
        help="Minimum topic-term overlap score required to assign a discovered work back to the topic",
    )
    expand_topic_parser.add_argument(
        "--preview",
        action="store_true",
        help="Discover and score candidate expansions without writing entries, relations, or topic assignments",
    )

    set_topic_phrase_parser = subparsers.add_parser(
        "set-topic-phrase",
        help="Set or clear the stored expansion phrase for one topic",
    )
    set_topic_phrase_parser.add_argument("topic_slug", help="Topic slug to update")
    set_topic_phrase_parser.add_argument(
        "phrase",
        nargs="?",
        help="Expansion phrase to store; omit with --clear to remove it",
    )
    set_topic_phrase_parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the stored expansion phrase for this topic",
    )

    harvest_parser = subparsers.add_parser("harvest-oai", help="Harvest draft entries from an OAI-PMH repository")
    harvest_parser.add_argument("base_url", help="OAI-PMH base URL")
    harvest_parser.add_argument("--metadata-prefix", default="oai_dc", help="OAI-PMH metadataPrefix to harvest")
    harvest_parser.add_argument("--set", dest="set_spec", help="Optional OAI-PMH set spec")
    harvest_parser.add_argument("--from", dest="date_from", help="Optional OAI-PMH lower date bound")
    harvest_parser.add_argument("--until", dest="date_until", help="Optional OAI-PMH upper date bound")
    harvest_parser.add_argument("--limit", type=int, default=20, help="Maximum harvested records to ingest")
    harvest_parser.add_argument("--status", default="draft", help="Initial review status")

    discover_parser = subparsers.add_parser("discover-oai", help="Inspect OAI-PMH repository identity and sets")
    discover_parser.add_argument("base_url", help="OAI-PMH base URL")

    bootstrap_parser = subparsers.add_parser(
        "bootstrap",
        help="Start bibliography expansion from a seed BibTeX file, a topic phrase, or both",
    )
    bootstrap_parser.add_argument("--seed-bib", help="Optional seed BibTeX file")
    bootstrap_parser.add_argument("--topic", help="Optional topic phrase")
    bootstrap_parser.add_argument("--topic-slug", help="Optional stored topic slug for this bootstrap topic")
    bootstrap_parser.add_argument("--topic-name", help="Optional stored topic name for this bootstrap topic")
    bootstrap_parser.add_argument(
        "--store-topic-phrase",
        help="Optional stored expansion phrase to save with the bootstrap topic; defaults to --topic when topic metadata is provided",
    )
    bootstrap_parser.add_argument("--topic-limit", type=int, default=5, help="Maximum topic-search seed candidates")
    bootstrap_parser.add_argument(
        "--topic-commit-limit",
        type=int,
        help="Maximum ranked topic candidates to actually commit and expand",
    )
    bootstrap_parser.add_argument(
        "--no-expand",
        action="store_true",
        help="Do not run immediate graph expansion after seeding",
    )
    bootstrap_parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview ranked bootstrap candidates without writing to the database or expanding",
    )
    bootstrap_parser.add_argument("--status", default="draft", help="Initial review status for imported entries")

    batch_parser = subparsers.add_parser(
        "bootstrap-batch",
        help="Run multiple bootstrap jobs from a JSON specification file",
    )
    batch_parser.add_argument("input", help="Path to batch JSON file")

    talkorigins_parser = subparsers.add_parser(
        "example-talkorigins-scrape",
        aliases=["scrape-talkorigins"],
        help="Example workflow: scrape TalkOrigins into per-topic seed BibTeX files and a bootstrap-batch JSON file",
    )
    talkorigins_parser.add_argument(
        "output_dir",
        help="Directory where seed BibTeX files, manifest, and batch JSON should be written",
    )
    talkorigins_parser.add_argument(
        "--base-url",
        default="https://www.talkorigins.org/origins/biblio/",
        help="TalkOrigins bibliography index URL",
    )
    talkorigins_parser.add_argument("--limit-topics", type=int, help="Limit the number of scraped topic pages")
    talkorigins_parser.add_argument(
        "--limit-entries-per-topic",
        type=int,
        help="Limit the number of parsed references per topic page",
    )
    talkorigins_parser.add_argument(
        "--resolve-seeds",
        action="store_true",
        help="Attempt metadata resolution on parsed seed entries before writing BibTeX",
    )
    talkorigins_parser.add_argument(
        "--ingest",
        action="store_true",
        help="Also ingest the generated seed BibTeX into the configured database",
    )
    talkorigins_parser.add_argument(
        "--no-expand",
        action="store_true",
        help="Write generated batch jobs with graph expansion disabled",
    )
    talkorigins_parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Do not reuse saved TalkOrigins topic snapshots from a prior run",
    )
    talkorigins_parser.add_argument(
        "--topic-limit",
        type=int,
        default=5,
        help="Default bootstrap topic-search limit to include in generated jobs",
    )
    talkorigins_parser.add_argument(
        "--topic-commit-limit",
        type=int,
        help="Default bootstrap topic commit limit to include in generated jobs",
    )
    talkorigins_parser.add_argument("--status", default="draft", help="Review status for generated seed jobs")

    validate_talkorigins_parser = subparsers.add_parser(
        "example-talkorigins-validate",
        aliases=["validate-talkorigins"],
        help="Example workflow: validate a generated TalkOrigins manifest and report parse coverage and suspicious entries",
    )
    validate_talkorigins_parser.add_argument("manifest", help="Path to talkorigins_manifest.json")

    suggest_talkorigins_parser = subparsers.add_parser(
        "example-talkorigins-suggest-phrases",
        aliases=["suggest-talkorigins-phrases"],
        help="Example workflow: suggest stored topic expansion phrases from a TalkOrigins manifest",
    )
    suggest_talkorigins_parser.add_argument("manifest", help="Path to talkorigins_manifest.json")
    suggest_talkorigins_parser.add_argument("--topic", help="Optional topic slug to restrict suggestions")
    suggest_talkorigins_parser.add_argument("--limit", type=int, help="Maximum topics to include")
    suggest_talkorigins_parser.add_argument("--output", help="Write suggestions JSON to a file instead of stdout")

    apply_topic_phrases_parser = subparsers.add_parser(
        "apply-topic-phrases",
        help="Apply stored topic expansion phrases from a JSON suggestion or patch file",
    )
    apply_topic_phrases_parser.add_argument("input", help="Path to JSON file containing topic phrase records")

    stage_topic_phrases_parser = subparsers.add_parser(
        "stage-topic-phrases",
        help="Stage topic phrase suggestions from JSON for later review in the database",
    )
    stage_topic_phrases_parser.add_argument("input", help="Path to JSON file containing topic phrase records")

    review_topic_phrase_parser = subparsers.add_parser(
        "review-topic-phrase",
        help="Accept or reject one staged topic phrase suggestion",
    )
    review_topic_phrase_parser.add_argument("topic_slug", help="Topic slug to review")
    review_topic_phrase_parser.add_argument("status", choices=["accepted", "rejected"], help="Review decision")
    review_topic_phrase_parser.add_argument(
        "--notes",
        help="Optional review notes to store with the decision",
    )
    review_topic_phrase_parser.add_argument(
        "--phrase",
        help="Optional expansion phrase override to apply with the review decision",
    )

    review_topic_phrases_parser = subparsers.add_parser(
        "review-topic-phrases",
        help="Apply topic phrase review decisions in bulk from JSON",
    )
    review_topic_phrases_parser.add_argument("input", help="Path to JSON file containing topic phrase review records")

    duplicates_talkorigins_parser = subparsers.add_parser(
        "example-talkorigins-duplicates",
        aliases=["duplicates-talkorigins"],
        help="Example workflow: inspect duplicate clusters in a generated TalkOrigins manifest",
    )
    duplicates_talkorigins_parser.add_argument("manifest", help="Path to talkorigins_manifest.json")
    duplicates_talkorigins_parser.add_argument("--limit", type=int, default=20, help="Maximum clusters to show")
    duplicates_talkorigins_parser.add_argument(
        "--min-count",
        type=int,
        default=2,
        help="Minimum cluster size to include",
    )
    duplicates_talkorigins_parser.add_argument("--match", help="Optional text filter for duplicate clusters")
    duplicates_talkorigins_parser.add_argument("--topic", help="Optional topic slug to restrict inspection")
    duplicates_talkorigins_parser.add_argument(
        "--preview",
        action="store_true",
        help="Include the canonical merged entry that ingest-talkorigins would choose",
    )
    duplicates_talkorigins_parser.add_argument(
        "--weak-only",
        action="store_true",
        help="Show only clusters whose canonical preview still looks weak",
    )

    ingest_talkorigins_parser = subparsers.add_parser(
        "example-talkorigins-ingest",
        aliases=["ingest-talkorigins"],
        help="Example workflow: ingest a TalkOrigins manifest into the database with duplicate consolidation and topic membership",
    )
    ingest_talkorigins_parser.add_argument("manifest", help="Path to talkorigins_manifest.json")
    ingest_talkorigins_parser.add_argument("--status", default="draft", help="Review status for imported entries")
    ingest_talkorigins_parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable duplicate consolidation and import each parsed entry separately",
    )

    enrich_talkorigins_parser = subparsers.add_parser(
        "example-talkorigins-enrich",
        aliases=["enrich-talkorigins"],
        help="Example workflow: attempt metadata enrichment for weak TalkOrigins canonical entries",
    )
    enrich_talkorigins_parser.add_argument("manifest", help="Path to talkorigins_manifest.json")
    enrich_talkorigins_parser.add_argument("--limit", type=int, default=20, help="Maximum weak clusters to inspect")
    enrich_talkorigins_parser.add_argument(
        "--min-count",
        type=int,
        default=2,
        help="Minimum duplicate-cluster size to include",
    )
    enrich_talkorigins_parser.add_argument("--match", help="Optional text filter for weak canonical clusters")
    enrich_talkorigins_parser.add_argument("--topic", help="Optional topic slug to restrict enrichment")
    enrich_talkorigins_parser.add_argument(
        "--apply",
        action="store_true",
        help="Write successful enrichments back into the configured database",
    )
    enrich_talkorigins_parser.add_argument(
        "--allow-unsafe-search-matches",
        action="store_true",
        help="Allow low-trust title-search resolver matches for bounded experiments on copied databases",
    )
    enrich_talkorigins_parser.add_argument(
        "--status",
        default="enriched",
        help="Review status to set when applying successful enrichments",
    )

    review_talkorigins_parser = subparsers.add_parser(
        "example-talkorigins-review",
        aliases=["review-talkorigins"],
        help="Example workflow: export weak TalkOrigins clusters plus dry-run enrichment outcomes for manual review",
    )
    review_talkorigins_parser.add_argument("manifest", help="Path to talkorigins_manifest.json")
    review_talkorigins_parser.add_argument("--limit", type=int, default=20, help="Maximum weak clusters to export")
    review_talkorigins_parser.add_argument(
        "--min-count",
        type=int,
        default=2,
        help="Minimum duplicate-cluster size to include",
    )
    review_talkorigins_parser.add_argument("--match", help="Optional text filter for weak canonical clusters")
    review_talkorigins_parser.add_argument("--topic", help="Optional topic slug to restrict review export")
    review_talkorigins_parser.add_argument("--output", help="Write review export JSON to a file instead of stdout")

    apply_review_talkorigins_parser = subparsers.add_parser(
        "example-talkorigins-apply-corrections",
        aliases=["apply-talkorigins-corrections"],
        help="Example workflow: apply curated TalkOrigins review corrections to the consolidated database",
    )
    apply_review_talkorigins_parser.add_argument("manifest", help="Path to talkorigins_manifest.json")
    apply_review_talkorigins_parser.add_argument("corrections", help="Path to corrections JSON")
    apply_review_talkorigins_parser.add_argument(
        "--status",
        default="reviewed",
        help="Default review status to set on corrected entries",
    )

    topics_parser = subparsers.add_parser("topics", help="List known topics in the database")
    topics_parser.add_argument("--limit", type=int, default=100, help="Maximum number of topics to list")
    topics_parser.add_argument(
        "--phrase-review-status",
        choices=["unreviewed", "pending", "accepted", "rejected"],
        help="Restrict topics to one stored phrase review state",
    )

    topic_phrase_reviews_parser = subparsers.add_parser(
        "topic-phrase-reviews",
        help="List staged topic phrase suggestions and their review state",
    )
    topic_phrase_reviews_parser.add_argument("--limit", type=int, default=100, help="Maximum reviews to list")
    topic_phrase_reviews_parser.add_argument(
        "--phrase-review-status",
        choices=["unreviewed", "pending", "accepted", "rejected"],
        help="Restrict results to one stored phrase review state",
    )

    export_topic_phrase_reviews_parser = subparsers.add_parser(
        "export-topic-phrase-reviews",
        help="Export an editable JSON review template for staged topic phrase suggestions",
    )
    export_topic_phrase_reviews_parser.add_argument("--limit", type=int, default=100, help="Maximum reviews to export")
    export_topic_phrase_reviews_parser.add_argument(
        "--phrase-review-status",
        choices=["unreviewed", "pending", "accepted", "rejected"],
        default="pending",
        help="Restrict exported reviews to one stored phrase review state",
    )
    export_topic_phrase_reviews_parser.add_argument(
        "--output",
        help="Write the review template JSON to a file instead of stdout",
    )

    topic_entries_parser = subparsers.add_parser(
        "topic-entries",
        help="List entries assigned to one topic",
    )
    topic_entries_parser.add_argument("topic_slug", help="Topic slug to inspect")
    topic_entries_parser.add_argument("--limit", type=int, default=100, help="Maximum entries to list")

    export_topic_parser = subparsers.add_parser(
        "export-topic",
        help="Export one topic slice as BibTeX",
    )
    export_topic_parser.add_argument("topic_slug", help="Topic slug to export")
    export_topic_parser.add_argument("--output", help="Write BibTeX to a file instead of stdout")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    store = BibliographyStore(args.db)
    try:
        if args.command == "ingest":
            return _run_ingest(store, Path(args.input), args.status, args.source_label)
        if args.command == "search":
            return _run_search(store, args.query, args.limit, args.topic)
        if args.command == "show":
            return _run_show(store, args.citation_key, args.limit, args.provenance, args.conflicts)
        if args.command == "export":
            return _run_export(store, args.citation_keys, args.output)
        if args.command == "set-status":
            return _run_set_status(store, args.citation_key, args.review_status)
        if args.command == "resolve-conflicts":
            return _run_resolve_conflicts(store, args.citation_key, args.field_name, args.status)
        if args.command == "apply-conflict":
            return _run_apply_conflict(store, args.citation_key, args.field_name)
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
            return _run_expand(store, args.citation_keys, args.source, args.relation, args.limit)
        if args.command == "expand-topic":
            return _run_expand_topic(
                store,
                args.topic_slug,
                args.topic_phrase,
                args.source,
                args.relation,
                args.seed_limit,
                args.per_seed_limit,
                args.min_relevance,
                args.seed_keys,
                args.preview,
            )
        if args.command == "set-topic-phrase":
            return _run_set_topic_phrase(store, args.topic_slug, args.phrase, args.clear)
        if args.command == "harvest-oai":
            return _run_harvest_oai(
                store,
                args.base_url,
                args.metadata_prefix,
                args.set_spec,
                args.date_from,
                args.date_until,
                args.limit,
                args.status,
            )
        if args.command == "discover-oai":
            return _run_discover_oai(args.base_url)
        if args.command == "bootstrap":
            return _run_bootstrap(
                store,
                args.seed_bib,
                args.topic,
                args.topic_limit,
                args.topic_commit_limit,
                not args.no_expand,
                args.status,
                args.preview,
                args.topic_slug,
                args.topic_name,
                args.store_topic_phrase,
            )
        if args.command == "bootstrap-batch":
            return _run_bootstrap_batch(store, Path(args.input))
        if args.command in {"example-talkorigins-scrape", "scrape-talkorigins"}:
            return _run_scrape_talkorigins(
                store,
                args.base_url,
                Path(args.output_dir),
                args.limit_topics,
                args.limit_entries_per_topic,
                args.resolve_seeds,
                args.ingest,
                not args.no_expand,
                not args.no_resume,
                args.topic_limit,
                args.topic_commit_limit,
                args.status,
            )
        if args.command in {"example-talkorigins-validate", "validate-talkorigins"}:
            return _run_validate_talkorigins(Path(args.manifest))
        if args.command in {"example-talkorigins-suggest-phrases", "suggest-talkorigins-phrases"}:
            return _run_suggest_talkorigins_phrases(Path(args.manifest), args.topic, args.limit, args.output)
        if args.command == "apply-topic-phrases":
            return _run_apply_topic_phrases(store, Path(args.input))
        if args.command == "stage-topic-phrases":
            return _run_stage_topic_phrases(store, Path(args.input))
        if args.command == "review-topic-phrase":
            return _run_review_topic_phrase(store, args.topic_slug, args.status, args.notes, args.phrase)
        if args.command == "review-topic-phrases":
            return _run_review_topic_phrases(store, Path(args.input))
        if args.command in {"example-talkorigins-duplicates", "duplicates-talkorigins"}:
            return _run_duplicates_talkorigins(
                Path(args.manifest),
                args.limit,
                args.min_count,
                args.match,
                args.topic,
                args.preview,
                args.weak_only,
            )
        if args.command in {"example-talkorigins-ingest", "ingest-talkorigins"}:
            return _run_ingest_talkorigins(store, Path(args.manifest), args.status, not args.no_dedupe)
        if args.command in {"example-talkorigins-enrich", "enrich-talkorigins"}:
            return _run_enrich_talkorigins(
                store,
                Path(args.manifest),
                args.limit,
                args.min_count,
                args.match,
                args.topic,
                args.apply,
                args.status,
                args.allow_unsafe_search_matches,
            )
        if args.command in {"example-talkorigins-review", "review-talkorigins"}:
            return _run_review_talkorigins(
                store,
                Path(args.manifest),
                args.limit,
                args.min_count,
                args.match,
                args.topic,
                args.output,
            )
        if args.command in {"example-talkorigins-apply-corrections", "apply-talkorigins-corrections"}:
            return _run_apply_talkorigins_corrections(
                store,
                Path(args.manifest),
                Path(args.corrections),
                args.status,
            )
        if args.command == "topics":
            return _run_topics(store, args.limit, args.phrase_review_status)
        if args.command == "topic-phrase-reviews":
            return _run_topic_phrase_reviews(store, args.limit, args.phrase_review_status)
        if args.command == "export-topic-phrase-reviews":
            return _run_export_topic_phrase_reviews(store, args.limit, args.phrase_review_status, args.output)
        if args.command == "topic-entries":
            return _run_topic_entries(store, args.topic_slug, args.limit)
        if args.command == "export-topic":
            return _run_export_topic(store, args.topic_slug, args.output)
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


def _run_search(store: BibliographyStore, query: str, limit: int, topic_slug: str | None) -> int:
    for row in store.search_text(query, limit=limit, topic_slug=topic_slug):
        score = row.get("score", 0.0)
        print(f"{row['citation_key']}\t{row.get('year') or ''}\t{score:.3f}\t{row.get('title') or ''}")
    return 0


def _run_show(
    store: BibliographyStore,
    citation_key: str | None,
    limit: int,
    provenance: bool,
    conflicts: bool,
) -> int:
    if citation_key:
        entry = store.get_entry(citation_key)
        if entry is None:
            print(f"Entry not found: {citation_key}", file=sys.stderr)
            return 1
        if provenance:
            entry["field_provenance"] = store.get_field_provenance(citation_key)
        if conflicts:
            entry["field_conflicts"] = store.get_field_conflicts(citation_key)
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


def _run_resolve_conflicts(store: BibliographyStore, citation_key: str, field_name: str, status: str) -> int:
    count = store.set_conflict_status(citation_key, field_name, status)
    if count == 0:
        print(f"No open conflicts updated for {citation_key}:{field_name}", file=sys.stderr)
        return 1
    print(f"{citation_key}\t{field_name}\t{status}\t{count}")
    return 0


def _run_apply_conflict(store: BibliographyStore, citation_key: str, field_name: str) -> int:
    if not store.apply_conflict_value(citation_key, field_name):
        print(f"No open conflict applied for {citation_key}:{field_name}", file=sys.stderr)
        return 1
    print(f"{citation_key}\t{field_name}\tapplied")
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
        merged, conflicts = merge_entries_with_conflicts(current_entry, resolution.entry)
        store.replace_entry(
            citation_key,
            merged,
            source_type=resolution.source_type,
            source_label=resolution.source_label,
            review_status="enriched",
        )
        if conflicts:
            store.record_conflicts(
                citation_key,
                conflicts,
                source_type=resolution.source_type,
                source_label=resolution.source_label,
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


def _run_expand(
    store: BibliographyStore,
    citation_keys: list[str],
    source: str,
    relation: str,
    limit: int,
) -> int:
    if source == "crossref":
        expander = CrossrefExpander()
        expand_fn = lambda key: expander.expand_entry_references(store, key)
    elif source == "openalex":
        expander = OpenAlexExpander()
        expand_fn = lambda key: expander.expand_entry(store, key, relation_type=relation, limit=limit)
    else:
        print(f"Unsupported expansion source: {source}", file=sys.stderr)
        return 1

    all_results = []
    for citation_key in citation_keys:
        all_results.extend(expand_fn(citation_key))
    print(json.dumps([asdict(result) for result in all_results], indent=2))
    return 0


def _run_expand_topic(
    store: BibliographyStore,
    topic_slug: str,
    topic_phrase: str | None,
    source: str,
    relation: str,
    seed_limit: int,
    per_seed_limit: int,
    min_relevance: float,
    seed_keys: list[str] | None,
    preview: bool,
) -> int:
    expander = TopicExpander()
    stored_topic = store.get_topic(topic_slug)
    effective_phrase = topic_phrase
    if effective_phrase is None and stored_topic is not None:
        effective_phrase = str(stored_topic.get("expansion_phrase") or "") or None
    results = expander.expand_topic(
        store,
        topic_slug,
        topic_phrase=effective_phrase,
        source=source,
        relation_type=relation,
        seed_limit=seed_limit,
        per_seed_limit=per_seed_limit,
        min_relevance=min_relevance,
        seed_keys=seed_keys,
        preview_only=preview,
    )
    print(json.dumps([asdict(result) for result in results], indent=2))
    return 0


def _run_set_topic_phrase(
    store: BibliographyStore,
    topic_slug: str,
    phrase: str | None,
    clear: bool,
) -> int:
    if clear:
        phrase = None
    elif phrase is None:
        print("set-topic-phrase requires a phrase or --clear", file=sys.stderr)
        return 1
    if not store.set_topic_expansion_phrase(topic_slug, phrase):
        print(f"Topic not found: {topic_slug}", file=sys.stderr)
        return 1
    payload = store.get_topic(topic_slug)
    print(json.dumps(payload, indent=2))
    return 0


def _run_harvest_oai(
    store: BibliographyStore,
    base_url: str,
    metadata_prefix: str,
    set_spec: str | None,
    date_from: str | None,
    date_until: str | None,
    limit: int,
    review_status: str,
) -> int:
    harvester = OaiPmhHarvester()
    harvested = harvester.list_records(
        base_url,
        metadata_prefix=metadata_prefix,
        set_spec=set_spec,
        date_from=date_from,
        date_until=date_until,
        limit=limit,
    )
    for result in harvested:
        store.upsert_entry(
            result.entry,
            raw_bibtex=render_bibtex([result.entry]),
            source_type="harvest",
            source_label=f"oai:{result.base_url}",
            review_status=review_status,
        )
        print(result.entry.citation_key)
    store.connection.commit()
    return 0


def _run_discover_oai(base_url: str) -> int:
    harvester = OaiPmhHarvester()
    payload = {
        "identify": harvester.identify(base_url),
        "metadata_formats": [asdict(result) for result in harvester.list_metadata_formats(base_url)],
        "sets": [asdict(result) for result in harvester.list_sets(base_url)],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _run_bootstrap(
    store: BibliographyStore,
    seed_bib: str | None,
    topic: str | None,
    topic_limit: int,
    topic_commit_limit: int | None,
    expand: bool,
    review_status: str,
    preview: bool,
    topic_slug: str | None,
    topic_name: str | None,
    stored_topic_phrase: str | None,
) -> int:
    if not seed_bib and not topic:
        print("bootstrap requires --seed-bib, --topic, or both", file=sys.stderr)
        return 1

    seed_bibtex = Path(seed_bib).read_text(encoding="utf-8") if seed_bib else None
    bootstrapper = Bootstrapper()
    results = bootstrapper.bootstrap(
        store,
        seed_bibtex=seed_bibtex,
        topic=topic,
        topic_limit=topic_limit,
        topic_commit_limit=topic_commit_limit,
        expand=expand,
        review_status=review_status,
        preview_only=preview,
        topic_slug=topic_slug,
        topic_name=topic_name,
        topic_phrase=stored_topic_phrase,
    )
    print(json.dumps([asdict(result) for result in results], indent=2))
    return 0


def _run_bootstrap_batch(store: BibliographyStore, input_path: Path) -> int:
    jobs = load_batch_jobs(input_path)
    runner = BatchBootstrapRunner()
    results = runner.run(store, jobs)
    payload = []
    for job_result in results:
        payload.append(
            {
                "job_name": job_result.job_name,
                "result_count": job_result.result_count,
                "results": [asdict(item) for item in job_result.results],
            }
        )
    print(json.dumps(payload, indent=2))
    return 0


def _run_scrape_talkorigins(
    store: BibliographyStore,
    base_url: str,
    output_dir: Path,
    limit_topics: int | None,
    limit_entries_per_topic: int | None,
    resolve_seeds: bool,
    ingest: bool,
    expand: bool,
    resume: bool,
    topic_limit: int,
    topic_commit_limit: int | None,
    review_status: str,
) -> int:
    scraper = TalkOriginsScraper()
    export = scraper.scrape_to_directory(
        base_url=base_url,
        output_dir=output_dir,
        limit_topics=limit_topics,
        limit_entries_per_topic=limit_entries_per_topic,
        resolve_seeds=resolve_seeds,
        ingest_store=store if ingest else None,
        review_status=review_status,
        expand=expand,
        resume=resume,
        topic_limit=topic_limit,
        topic_commit_limit=topic_commit_limit,
    )
    print(json.dumps(asdict(export), indent=2))
    return 0


def _run_validate_talkorigins(manifest_path: Path) -> int:
    scraper = TalkOriginsScraper()
    report = scraper.validate_export(manifest_path)
    print(json.dumps(asdict(report), indent=2))
    return 0


def _run_suggest_talkorigins_phrases(
    manifest_path: Path,
    topic_slug: str | None,
    limit: int | None,
    output: str | None,
) -> int:
    scraper = TalkOriginsScraper()
    suggestions = scraper.suggest_topic_phrases(manifest_path, limit=limit, topic_slug=topic_slug)
    payload = json.dumps([asdict(item) for item in suggestions], indent=2)
    if output:
        Path(output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


def _run_apply_topic_phrases(store: BibliographyStore, input_path: Path) -> int:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("topics", [])
    else:
        items = payload
    if not isinstance(items, list):
        print("Topic phrase JSON must be a list or an object with a 'topics' list", file=sys.stderr)
        return 1

    results: list[dict[str, object]] = []
    exit_code = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "")
        phrase = item.get("suggested_phrase", item.get("phrase"))
        if not slug:
            continue
        if phrase is not None:
            phrase = str(phrase)
        applied = store.set_topic_expansion_phrase(slug, phrase)
        if not applied:
            exit_code = 1
        results.append(
            {
                "slug": slug,
                "expansion_phrase": phrase,
                "applied": applied,
            }
        )
    print(json.dumps(results, indent=2))
    return exit_code


def _run_stage_topic_phrases(store: BibliographyStore, input_path: Path) -> int:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("topics", payload.get("items", []))
    else:
        items = payload
    if not isinstance(items, list):
        print("Topic phrase JSON must be a list or an object with a 'topics' or 'items' list", file=sys.stderr)
        return 1

    results: list[dict[str, object]] = []
    exit_code = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "")
        phrase = item.get("suggested_phrase", item.get("phrase"))
        notes = item.get("review_notes")
        if not slug:
            continue
        if phrase is not None:
            phrase = str(phrase)
        if notes is not None:
            notes = str(notes)
        staged = store.stage_topic_phrase_suggestion(
            slug,
            suggested_phrase=phrase,
            review_status="pending",
            review_notes=notes,
        )
        if not staged:
            exit_code = 1
        results.append(
            {
                "slug": slug,
                "suggested_phrase": phrase,
                "phrase_review_status": "pending",
                "staged": staged,
            }
        )
    print(json.dumps(results, indent=2))
    return exit_code


def _run_review_topic_phrase(
    store: BibliographyStore,
    topic_slug: str,
    status: str,
    notes: str | None,
    phrase: str | None,
) -> int:
    if not store.review_topic_phrase_suggestion(
        topic_slug,
        review_status=status,
        review_notes=notes,
        applied_phrase=phrase,
    ):
        print(f"Topic not found: {topic_slug}", file=sys.stderr)
        return 1
    payload = store.get_topic(topic_slug)
    print(json.dumps(payload, indent=2))
    return 0


def _run_review_topic_phrases(store: BibliographyStore, input_path: Path) -> int:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("topics", payload.get("items", []))
    else:
        items = payload
    if not isinstance(items, list):
        print("Topic phrase review JSON must be a list or an object with a 'topics' or 'items' list", file=sys.stderr)
        return 1

    results: list[dict[str, object]] = []
    exit_code = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "")
        status = str(item.get("status") or item.get("phrase_review_status") or "")
        notes = item.get("review_notes")
        phrase = item.get("phrase", item.get("expansion_phrase"))
        if not slug or status not in {"accepted", "rejected"}:
            continue
        if notes is not None:
            notes = str(notes)
        if phrase is not None:
            phrase = str(phrase)
        reviewed = store.review_topic_phrase_suggestion(
            slug,
            review_status=status,
            review_notes=notes,
            applied_phrase=phrase,
        )
        if not reviewed:
            exit_code = 1
        results.append(
            {
                "slug": slug,
                "phrase_review_status": status,
                "expansion_phrase": phrase,
                "reviewed": reviewed,
            }
        )
    print(json.dumps(results, indent=2))
    return exit_code


def _run_duplicates_talkorigins(
    manifest_path: Path,
    limit: int,
    min_count: int,
    match: str | None,
    topic_slug: str | None,
    preview: bool,
    weak_only: bool,
) -> int:
    scraper = TalkOriginsScraper()
    clusters = scraper.inspect_duplicate_clusters(
        manifest_path,
        limit=limit,
        min_count=min_count,
        match=match,
        topic_slug=topic_slug,
        preview_canonical=preview,
        weak_only=weak_only,
    )
    print(json.dumps([asdict(cluster) for cluster in clusters], indent=2))
    return 0


def _run_ingest_talkorigins(
    store: BibliographyStore,
    manifest_path: Path,
    review_status: str,
    dedupe: bool,
) -> int:
    scraper = TalkOriginsScraper()
    report = scraper.ingest_export(
        manifest_path,
        store,
        review_status=review_status,
        dedupe=dedupe,
    )
    print(json.dumps(asdict(report), indent=2))
    return 0


def _run_enrich_talkorigins(
    store: BibliographyStore,
    manifest_path: Path,
    limit: int,
    min_count: int,
    match: str | None,
    topic_slug: str | None,
    apply: bool,
    review_status: str,
    allow_unsafe_matches: bool,
) -> int:
    scraper = TalkOriginsScraper()
    results = scraper.enrich_weak_canonicals(
        manifest_path,
        store,
        limit=limit,
        min_count=min_count,
        match=match,
        topic_slug=topic_slug,
        apply=apply,
        review_status=review_status,
        allow_unsafe_matches=allow_unsafe_matches,
    )
    print(json.dumps([asdict(result) for result in results], indent=2))
    return 0


def _run_review_talkorigins(
    store: BibliographyStore,
    manifest_path: Path,
    limit: int,
    min_count: int,
    match: str | None,
    topic_slug: str | None,
    output: str | None,
) -> int:
    scraper = TalkOriginsScraper()
    review = scraper.build_review_export(
        manifest_path,
        store,
        limit=limit,
        min_count=min_count,
        match=match,
        topic_slug=topic_slug,
    )
    payload = json.dumps(asdict(review), indent=2)
    if output:
        Path(output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


def _run_apply_talkorigins_corrections(
    store: BibliographyStore,
    manifest_path: Path,
    corrections_path: Path,
    review_status: str,
) -> int:
    scraper = TalkOriginsScraper()
    results = scraper.apply_review_corrections(
        manifest_path,
        corrections_path,
        store,
        default_review_status=review_status,
    )
    print(json.dumps([asdict(result) for result in results], indent=2))
    return 0


def _run_topics(store: BibliographyStore, limit: int, phrase_review_status: str | None) -> int:
    print(json.dumps(store.list_topics(limit=limit, phrase_review_status=phrase_review_status), indent=2))
    return 0


def _run_topic_phrase_reviews(store: BibliographyStore, limit: int, phrase_review_status: str | None) -> int:
    print(json.dumps(store.list_topic_phrase_reviews(limit=limit, phrase_review_status=phrase_review_status), indent=2))
    return 0


def _run_export_topic_phrase_reviews(
    store: BibliographyStore,
    limit: int,
    phrase_review_status: str | None,
    output: str | None,
) -> int:
    items = store.list_topic_phrase_reviews(limit=limit, phrase_review_status=phrase_review_status)
    payload = [
        {
            "slug": item["slug"],
            "topic": item["name"],
            "current_expansion_phrase": item.get("expansion_phrase"),
            "suggested_phrase": item.get("suggested_phrase"),
            "current_status": item.get("phrase_review_status"),
            "review_notes": item.get("phrase_review_notes"),
            "status": "",
            "phrase": item.get("suggested_phrase"),
        }
        for item in items
    ]
    rendered = json.dumps(payload, indent=2)
    if output:
        Path(output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


def _run_topic_entries(store: BibliographyStore, topic_slug: str, limit: int) -> int:
    topic = store.get_topic(topic_slug)
    if topic is None:
        print(f"Topic not found: {topic_slug}", file=sys.stderr)
        return 1
    payload = {
        "topic": topic,
        "entries": store.list_topic_entries(topic_slug, limit=limit),
    }
    print(json.dumps(payload, indent=2))
    return 0


def _run_export_topic(store: BibliographyStore, topic_slug: str, output: str | None) -> int:
    topic = store.get_topic(topic_slug)
    if topic is None:
        print(f"Topic not found: {topic_slug}", file=sys.stderr)
        return 1
    citation_keys = [row["citation_key"] for row in store.list_topic_entries(topic_slug, limit=100000)]
    rendered = store.export_bibtex(citation_keys)
    if output:
        Path(output).write_text(rendered + ("\n" if rendered else ""), encoding="utf-8")
    else:
        if rendered:
            print(rendered)
    return 0
