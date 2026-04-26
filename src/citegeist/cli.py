from __future__ import annotations

import argparse
from dataclasses import asdict
from html import escape as html_escape
import json
import sys
from pathlib import Path

from .batch import BatchBootstrapRunner, load_batch_jobs
from .bibtex import BibEntry, parse_bibtex, render_bibtex
from .bootstrap import Bootstrapper
from .examples.talkorigins import TalkOriginsScraper
from .expand import CrossrefExpander, OpenAlexExpander, TopicExpander, _expand_relation_types
from .extract import (
    available_extraction_backends,
    check_extraction_comparison_summary,
    compare_extraction_backends,
    extract_references,
    summarize_extraction_comparison,
)
from .harvest import OaiPmhHarvester
from .llm_verify import VerificationLlmConfig
from .resolve import MetadataResolver, merge_entries_with_conflicts
from .storage import BibliographyStore
from .verify import BibliographyVerifier, render_verification_results


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
    export_parser.add_argument(
        "--include-stubs",
        action="store_true",
        help="Include DOI-only placeholder records in broad exports",
    )

    sync_jabref_parser = subparsers.add_parser(
        "sync-jabref",
        help="Round-trip a JabRef-managed BibTeX file through CiteGeist ingest, enrichment, and export",
    )
    sync_jabref_parser.add_argument("input", help="BibTeX file managed in JabRef")
    sync_jabref_parser.add_argument("--output", help="Path to write the enriched BibTeX export")
    sync_jabref_parser.add_argument(
        "--in-place",
        action="store_true",
        help="Write the enriched BibTeX back to the input file instead of a separate output path",
    )
    sync_jabref_parser.add_argument("--status", default="draft", help="Initial review status for newly ingested entries")
    sync_jabref_parser.add_argument("--source-label", help="Provenance label for the ingest step")
    sync_jabref_parser.add_argument(
        "--no-resolve",
        action="store_true",
        help="Skip metadata resolution after ingest and only re-export the imported entries",
    )
    sync_jabref_parser.add_argument(
        "--annotate-review",
        action="store_true",
        help="Add CiteGeist review/status sidecar fields to the exported BibTeX for easier JabRef review",
    )

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
    extract_parser.add_argument(
        "--backend",
        choices=available_extraction_backends(),
        default="heuristic",
        help="Reference extraction backend to use",
    )
    extract_parser.add_argument("--output", help="Write extracted BibTeX to a file instead of stdout")

    compare_extract_parser = subparsers.add_parser(
        "compare-extract",
        help="Run multiple extraction backends on the same plaintext references and emit a JSON comparison",
    )
    compare_extract_parser.add_argument("input", help="Plaintext file containing bibliography-style references")
    compare_extract_parser.add_argument(
        "--backend",
        action="append",
        dest="backends",
        choices=available_extraction_backends(),
        help="Backend to include in the comparison; may be passed multiple times",
    )
    compare_extract_parser.add_argument(
        "--summary",
        action="store_true",
        help="Emit a compact JSON summary instead of row-by-row comparison output",
    )
    compare_extract_parser.add_argument(
        "--max-rows-with-differences",
        type=int,
        help="Fail with a nonzero exit code if rows_with_differences exceeds this value",
    )
    compare_extract_parser.add_argument(
        "--max-field-difference-count",
        type=int,
        help="Fail with a nonzero exit code if any field disagreement count exceeds this value",
    )
    compare_extract_parser.add_argument("--output", help="Write JSON comparison to a file instead of stdout")

    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify or disambiguate free-text references or BibTeX entries without modifying the database",
    )
    verify_group = verify_parser.add_mutually_exclusive_group(required=True)
    verify_group.add_argument("--string", help="Single free-text reference query")
    verify_group.add_argument("--list", dest="list_input", help="Path to a text file with one query per line")
    verify_group.add_argument("--bib", help="Path to a BibTeX file whose entries should be verified")
    verify_parser.add_argument("--context", default="", help="Optional topic context used for scoring")
    verify_parser.add_argument("--limit", type=int, default=5, help="Maximum candidates to inspect per input")
    verify_parser.add_argument("--llm", action="store_true", help="Enable optional local LLM assistance for verify")
    verify_parser.add_argument("--llm-base-url", help="OpenAI-compatible or Ollama base URL for local LLM assistance")
    verify_parser.add_argument("--llm-model", help="Model ID for local LLM assistance")
    verify_parser.add_argument("--llm-api-key", default="", help="Optional API key for the LLM endpoint")
    verify_parser.add_argument(
        "--llm-provider",
        choices=["auto", "openai", "ollama-native"],
        default="auto",
        help="LLM API style; auto treats `/v1` endpoints as OpenAI-compatible",
    )
    verify_parser.add_argument(
        "--llm-role",
        choices=["expand", "rerank", "both"],
        default="both",
        help="Use the local LLM for query-clue extraction, candidate reranking, or both",
    )
    verify_parser.add_argument(
        "--format",
        choices=["bibtex", "json"],
        default="bibtex",
        help="Output format for verification results",
    )
    verify_parser.add_argument("--output", help="Write verification results to a file instead of stdout")

    resolve_parser = subparsers.add_parser("resolve", help="Enrich stored entries from external metadata sources")
    resolve_parser.add_argument("citation_keys", nargs="+", help="Citation keys to enrich")

    enrich_oa_parser = subparsers.add_parser(
        "enrich-oa",
        help="Enrich DOI-bearing entries with Unpaywall OA link metadata",
    )
    enrich_oa_parser.add_argument("citation_keys", nargs="+", help="Citation keys to enrich")
    enrich_oa_parser.add_argument("--email", help="Email address required by the Unpaywall API")

    resolve_stubs_parser = subparsers.add_parser(
        "resolve-stubs",
        help="Find and enrich stub-like stored entries, optionally limited to DOI-bearing candidates",
    )
    resolve_stubs_parser.add_argument("--limit", type=int, default=25, help="Maximum candidate entries to inspect")
    resolve_stubs_parser.add_argument(
        "--doi-only",
        action="store_true",
        help="Only consider candidates that already have a DOI",
    )
    resolve_stubs_parser.add_argument(
        "--all-misc",
        action="store_true",
        help="Consider all stored @misc entries instead of only placeholder-like stub records",
    )
    resolve_stubs_parser.add_argument(
        "--topic",
        help="Optional topic slug to limit candidate selection",
    )
    resolve_stubs_parser.add_argument(
        "--preview",
        action="store_true",
        help="Show the selected candidate entries without resolving them",
    )

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
    graph_parser.add_argument(
        "--format",
        choices=["json", "dot", "json-graph"],
        default="json",
        help="Output format for traversed graph results",
    )
    graph_parser.add_argument(
        "--output",
        help="Write graph output to a file instead of stdout",
    )

    graph_view_parser = subparsers.add_parser(
        "graph-view",
        help="Render a self-contained HTML viewer from a json-graph export",
    )
    graph_view_parser.add_argument("input", help="Path to a graph JSON file exported with --format json-graph")
    graph_view_parser.add_argument("--output", required=True, help="Path to write the HTML viewer")
    graph_view_parser.add_argument("--title", default="CiteGeist Graph View", help="HTML page title")

    expand_parser = subparsers.add_parser("expand", help="Expand graph edges from external metadata sources")
    expand_parser.add_argument("citation_keys", nargs="+", help="Seed citation keys to expand")
    expand_parser.add_argument(
        "--source",
        choices=["crossref", "openalex", "opencitations"],
        default="crossref",
        help="Graph expansion source",
    )
    expand_parser.add_argument(
        "--relation",
        choices=["cites", "cited_by", "both"],
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
        choices=["crossref", "openalex", "opencitations"],
        default="openalex",
        help="Topic graph expansion source",
    )
    expand_topic_parser.add_argument(
        "--relation",
        choices=["cites", "cited_by", "both"],
        default="cites",
        help="Graph direction to expand for sources that support it",
    )
    expand_topic_parser.add_argument("--seed-limit", type=int, default=25, help="Maximum topic seed entries to expand from")
    expand_topic_parser.add_argument("--per-seed-limit", type=int, default=25, help="Maximum discovered works to fetch per seed")
    expand_topic_parser.add_argument("--rounds", type=int, default=1, help="Maximum recursive expansion rounds")
    expand_topic_parser.add_argument(
        "--recent-years",
        type=int,
        help="Treat discoveries within this many years of the current year as recent for termination heuristics",
    )
    expand_topic_parser.add_argument(
        "--target-recent-entries",
        type=int,
        help="Stop recursive topic expansion once this many recent discoveries have been found",
    )
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
        "--expansion-mode",
        choices=["legacy", "cites", "cited_by", "both"],
        default="legacy",
        help="Expansion policy after bootstrap seeding; legacy keeps Crossref refs plus OpenAlex cites",
    )
    bootstrap_parser.add_argument(
        "--expansion-rounds",
        type=int,
        default=1,
        help="Maximum recursive OpenAlex expansion rounds for non-legacy expansion modes",
    )
    bootstrap_parser.add_argument(
        "--recent-years",
        type=int,
        help="Treat discoveries within this many years of the current year as recent for termination heuristics",
    )
    bootstrap_parser.add_argument(
        "--target-recent-entries",
        type=int,
        help="Stop non-legacy expansion once this many recent discoveries have been found",
    )
    bootstrap_parser.add_argument(
        "--max-expanded-entries",
        type=int,
        help="Hard cap on unique discovered entries added during one bootstrap job",
    )
    bootstrap_parser.add_argument(
        "--max-expand-seconds",
        type=float,
        help="Wall-clock cap for one bootstrap job's expansion phase",
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
    talkorigins_parser.add_argument(
        "--expansion-mode",
        choices=["legacy", "cites", "cited_by", "both"],
        default="legacy",
        help="Expansion policy to write into generated bootstrap jobs",
    )
    talkorigins_parser.add_argument(
        "--expansion-rounds",
        type=int,
        default=1,
        help="Maximum recursive OpenAlex expansion rounds to write into generated jobs",
    )
    talkorigins_parser.add_argument(
        "--recent-years",
        type=int,
        help="Optional recent-discovery window to write into generated jobs",
    )
    talkorigins_parser.add_argument(
        "--target-recent-entries",
        type=int,
        help="Optional recent-discovery target to write into generated jobs",
    )
    talkorigins_parser.add_argument(
        "--max-expanded-entries",
        type=int,
        help="Optional hard cap on unique discovered entries per generated bootstrap job",
    )
    talkorigins_parser.add_argument(
        "--max-expand-seconds",
        type=float,
        help="Optional wall-clock cap to write into generated bootstrap jobs",
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
    export_topic_parser.add_argument(
        "--include-stubs",
        action="store_true",
        help="Include DOI-only placeholder records in the topic export",
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
            return _run_search(store, args.query, args.limit, args.topic)
        if args.command == "show":
            return _run_show(store, args.citation_key, args.limit, args.provenance, args.conflicts)
        if args.command == "export":
            return _run_export(store, args.citation_keys, args.output, args.include_stubs)
        if args.command == "sync-jabref":
            return _run_sync_jabref(
                store,
                Path(args.input),
                Path(args.output) if args.output else None,
                args.in_place,
                args.status,
                args.source_label,
                args.no_resolve,
                args.annotate_review,
            )
        if args.command == "set-status":
            return _run_set_status(store, args.citation_key, args.review_status)
        if args.command == "resolve-conflicts":
            return _run_resolve_conflicts(store, args.citation_key, args.field_name, args.status)
        if args.command == "apply-conflict":
            return _run_apply_conflict(store, args.citation_key, args.field_name)
        if args.command == "extract":
            return _run_extract(Path(args.input), args.backend, args.output)
        if args.command == "compare-extract":
            return _run_compare_extract(
                Path(args.input),
                args.backends,
                args.summary,
                args.max_rows_with_differences,
                args.max_field_difference_count,
                args.output,
            )
        if args.command == "verify":
            return _run_verify(
                args.string,
                args.list_input,
                args.bib,
                args.context,
                args.limit,
                args.format,
                args.output,
                llm_enabled=args.llm,
                llm_base_url=args.llm_base_url,
                llm_model=args.llm_model,
                llm_api_key=args.llm_api_key,
                llm_provider=args.llm_provider,
                llm_role=args.llm_role,
            )
        if args.command == "resolve":
            return _run_resolve(store, args.citation_keys)
        if args.command == "enrich-oa":
            return _run_enrich_oa(store, args.citation_keys, args.email)
        if args.command == "resolve-stubs":
            return _run_resolve_stubs(store, args.limit, args.doi_only, args.all_misc, args.topic, args.preview)
        if args.command == "graph":
            return _run_graph(
                store,
                args.citation_keys,
                args.relations,
                args.depth,
                args.review_status,
                args.missing_only,
                args.format,
                args.output,
            )
        if args.command == "graph-view":
            return _run_graph_view(Path(args.input), Path(args.output), args.title)
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
                args.rounds,
                args.recent_years,
                args.target_recent_entries,
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
                args.expansion_mode,
                args.expansion_rounds,
                args.recent_years,
                args.target_recent_entries,
                args.max_expanded_entries,
                args.max_expand_seconds,
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
                args.expansion_mode,
                args.expansion_rounds,
                args.recent_years,
                args.target_recent_entries,
                args.max_expanded_entries,
                args.max_expand_seconds,
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
            return _run_export_topic(store, args.topic_slug, args.output, args.include_stubs)
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


def _run_export(
    store: BibliographyStore,
    citation_keys: list[str],
    output: str | None,
    include_stubs: bool,
) -> int:
    explicit_keys = citation_keys or None
    rendered = store.export_bibtex(explicit_keys, include_stubs=include_stubs or explicit_keys is not None)
    if output:
        Path(output).write_text(rendered + ("\n" if rendered else ""), encoding="utf-8")
    else:
        if rendered:
            print(rendered)
    return 0


def _run_sync_jabref(
    store: BibliographyStore,
    input_path: Path,
    output_path: Path | None,
    in_place: bool,
    review_status: str,
    source_label: str | None,
    skip_resolve: bool,
    annotate_review: bool,
) -> int:
    if in_place:
        effective_output_path = input_path
    elif output_path is not None:
        effective_output_path = output_path
    else:
        print("sync-jabref requires --output or --in-place", file=sys.stderr)
        return 1

    text = input_path.read_text(encoding="utf-8")
    imported_keys = store.ingest_bibtex(
        text,
        source_label=source_label or str(input_path),
        review_status=review_status,
    )

    resolved_keys: list[str] = []
    failed_keys: list[str] = []
    if not skip_resolve:
        resolver = MetadataResolver()
        total = len(imported_keys)
        for index, citation_key in enumerate(imported_keys, start=1):
            _print_progress("sync-jabref resolving", index, total, citation_key)
            if _resolve_one(store, resolver, citation_key):
                resolved_keys.append(citation_key)
            else:
                failed_keys.append(citation_key)

    rendered = _render_jabref_sync_export(store, imported_keys, annotate_review=annotate_review)
    effective_output_path.write_text(rendered + ("\n" if rendered else ""), encoding="utf-8")
    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(effective_output_path),
                "imported_count": len(imported_keys),
                "resolved_count": len(resolved_keys),
                "failed_resolve_count": len(failed_keys),
                "skipped_resolution": skip_resolve,
                "annotated_review": annotate_review,
                "in_place": in_place,
                "citation_keys": imported_keys,
            },
            indent=2,
        )
    )
    return 0 if skip_resolve or not failed_keys else 1


def _render_jabref_sync_export(
    store: BibliographyStore,
    citation_keys: list[str],
    *,
    annotate_review: bool,
) -> str:
    entries: list[BibEntry] = []
    for citation_key in citation_keys:
        entry = store.get_bib_entry(citation_key)
        if entry is None:
            continue
        if annotate_review:
            entry = _annotated_jabref_entry(store, entry)
        entries.append(entry)
    return render_bibtex(entries) if entries else ""


def _annotated_jabref_entry(store: BibliographyStore, entry: BibEntry) -> BibEntry:
    row = store.get_entry(entry.citation_key) or {}
    annotated = BibEntry(
        entry_type=entry.entry_type,
        citation_key=entry.citation_key,
        fields=dict(entry.fields),
    )
    review_status = str(row.get("review_status") or "")
    if review_status:
        annotated.fields["x_citegeist_review_status"] = review_status
    open_conflicts = store.get_field_conflicts(entry.citation_key, status="open")
    if open_conflicts:
        annotated.fields["x_citegeist_open_conflicts"] = str(len(open_conflicts))
        annotated.fields["x_citegeist_conflict_fields"] = ", ".join(
            sorted({str(conflict.get("field_name") or "") for conflict in open_conflicts if conflict.get("field_name")})
        )
    provenance = store.get_field_provenance(entry.citation_key)
    if provenance:
        annotated.fields["x_citegeist_last_source"] = str(provenance[-1].get("source_label") or "")
    return annotated


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


def _run_extract(input_path: Path, backend: str, output: str | None) -> int:
    text = input_path.read_text(encoding="utf-8")
    entries = extract_references(text, backend=backend)
    rendered = render_bibtex(entries)
    if output:
        Path(output).write_text(rendered + ("\n" if rendered else ""), encoding="utf-8")
    else:
        if rendered:
            print(rendered)
    return 0


def _run_compare_extract(
    input_path: Path,
    backends: list[str] | None,
    summary: bool,
    max_rows_with_differences: int | None,
    max_field_difference_count: int | None,
    output: str | None,
) -> int:
    text = input_path.read_text(encoding="utf-8")
    rows = compare_extraction_backends(text, backends=backends)
    payload: object
    exit_code = 0
    if summary:
        summary_payload = summarize_extraction_comparison(rows)
        payload = summary_payload.to_dict()
        if max_rows_with_differences is not None or max_field_difference_count is not None:
            check = check_extraction_comparison_summary(
                summary_payload,
                max_rows_with_differences=max_rows_with_differences,
                max_field_difference_count=max_field_difference_count,
            )
            payload = {
                "summary": payload,
                "check": check.to_dict(),
            }
            if not check.passed:
                exit_code = 1
    else:
        payload = [row.to_dict() for row in rows]
    rendered = json.dumps(payload, indent=2)
    if output:
        Path(output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return exit_code


def _run_verify(
    string_input: str | None,
    list_input: str | None,
    bib_input: str | None,
    context: str,
    limit: int,
    output_format: str,
    output: str | None,
    *,
    llm_enabled: bool = False,
    llm_base_url: str | None = None,
    llm_model: str | None = None,
    llm_api_key: str = "",
    llm_provider: str = "auto",
    llm_role: str = "both",
) -> int:
    llm_config = None
    if llm_enabled:
        if not llm_base_url or not llm_model:
            print("--llm requires --llm-base-url and --llm-model", file=sys.stderr)
            return 1
        llm_config = VerificationLlmConfig(
            base_url=llm_base_url,
            model=llm_model,
            api_key=llm_api_key,
            provider=llm_provider,
            role=llm_role,
        )
    verifier = BibliographyVerifier(llm_config=llm_config)
    if string_input is not None:
        results = [verifier.verify_string(string_input, context=context, limit=limit)]
    elif list_input is not None:
        values = [line.strip() for line in Path(list_input).read_text(encoding="utf-8").splitlines() if line.strip()]
        results = verifier.verify_strings(values, context=context, limit=limit)
    elif bib_input is not None:
        results = verifier.verify_bib_file(bib_input, context=context, limit=limit)
    else:
        print("verify requires one input source", file=sys.stderr)
        return 1

    rendered = render_verification_results(results, output_format)
    if output:
        Path(output).write_text(rendered + ("\n" if rendered and not rendered.endswith("\n") else ""), encoding="utf-8")
    else:
        if rendered:
            print(rendered)
    return 0


def _print_progress(label: str, index: int, total: int, detail: str | None = None) -> None:
    message = f"[{index}/{total}] {label}"
    if detail:
        message = f"{message}: {detail}"
    print(message, file=sys.stderr, flush=True)


def _print_phase(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _run_resolve(store: BibliographyStore, citation_keys: list[str]) -> int:
    resolver = MetadataResolver()
    exit_code = 0
    total = len(citation_keys)
    for index, citation_key in enumerate(citation_keys, start=1):
        _print_progress("resolving", index, total, citation_key)
        if not _resolve_one(store, resolver, citation_key):
            exit_code = 1
    return exit_code


def _run_enrich_oa(store: BibliographyStore, citation_keys: list[str], email: str | None) -> int:
    from .sources import UnpaywallSource

    source = UnpaywallSource(config={"email": email} if email else {})
    if not source.is_available():
        print("Unpaywall enrichment requires --email or UNPAYWALL_EMAIL", file=sys.stderr)
        return 1

    results: list[dict[str, object]] = []
    total = len(citation_keys)
    for index, citation_key in enumerate(citation_keys, start=1):
        _print_progress("enriching OA", index, total, citation_key)
        existing = store.get_entry(citation_key)
        if existing is None:
            results.append({"citation_key": citation_key, "status": "missing"})
            continue
        doi = str(existing.get("doi") or "").strip()
        if not doi:
            results.append({"citation_key": citation_key, "status": "no_doi"})
            continue

        enriched = source.lookup_by_doi(doi)
        if enriched is None:
            results.append({"citation_key": citation_key, "status": "no_record", "doi": doi})
            continue

        merged_fields: dict[str, str] = {}
        for key, value in existing.items():
            if isinstance(value, str):
                merged_fields[key] = value
        merged_fields.update(enriched.fields)

        for field_name in ("title", "year", "author", "journal", "booktitle", "publisher", "abstract", "keywords"):
            existing_value = str(existing.get(field_name) or "").strip()
            if existing_value:
                merged_fields[field_name] = existing_value

        replacement = BibEntry(
            entry_type=str(existing.get("entry_type") or "misc"),
            citation_key=citation_key,
            fields=merged_fields,
        )
        store.replace_entry(
            citation_key,
            replacement,
            source_type="oa_enrich",
            source_label=f"unpaywall:doi:{doi}",
            review_status=str(existing.get("review_status") or "enriched"),
        )
        updated = store.get_entry(citation_key) or {}
        results.append(
            {
                "citation_key": citation_key,
                "status": "enriched",
                "doi": doi,
                "is_oa": updated.get("is_oa"),
                "oa_status": updated.get("oa_status"),
                "best_oa_url": updated.get("best_oa_url"),
                "best_oa_pdf_url": updated.get("best_oa_pdf_url"),
            }
        )

    print(json.dumps(results, indent=2))
    return 0


def _resolve_one(store: BibliographyStore, resolver: MetadataResolver, citation_key: str) -> bool:
    existing = store.get_entry(citation_key)
    if existing is None:
        print(f"Entry not found: {citation_key}", file=sys.stderr)
        return False
    bibtex = store.get_entry_bibtex(citation_key)
    if not bibtex:
        print(f"Entry not renderable: {citation_key}", file=sys.stderr)
        return False
    current_entry = parse_bibtex(bibtex)[0]
    resolution = resolver.resolve_entry(current_entry)
    if resolution is None:
        print(f"No resolver match: {citation_key}", file=sys.stderr)
        return False
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
    return True


def _run_resolve_stubs(
    store: BibliographyStore,
    limit: int,
    doi_only: bool,
    all_misc: bool,
    topic_slug: str | None,
    preview: bool,
) -> int:
    candidates = store.list_resolution_candidates(
        limit=limit,
        doi_only=doi_only,
        stub_only=not all_misc,
        misc_only=all_misc,
        topic_slug=topic_slug,
    )
    if preview:
        print(json.dumps(candidates, indent=2))
        return 0

    resolver = MetadataResolver()
    exit_code = 0
    total = len(candidates)
    for index, candidate in enumerate(candidates, start=1):
        _print_progress("resolving candidate", index, total, str(candidate["citation_key"]))
        if not _resolve_one(store, resolver, str(candidate["citation_key"])):
            exit_code = 1
    return exit_code


def _run_graph(
    store: BibliographyStore,
    citation_keys: list[str],
    relations: list[str] | None,
    depth: int,
    review_status: str | None,
    missing_only: bool,
    output_format: str,
    output: str | None,
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
    rendered: str
    if output_format == "dot":
        rendered = _render_graph_dot(store, citation_keys, rows)
    elif output_format == "json-graph":
        rendered = json.dumps(_render_graph_json(store, citation_keys, rows), indent=2)
    else:
        rendered = json.dumps(rows, indent=2)
    if output:
        Path(output).write_text(rendered + ("\n" if rendered and not rendered.endswith("\n") else ""), encoding="utf-8")
    else:
        print(rendered)
    return 0


def _run_graph_view(input_path: Path, output_path: Path, title: str) -> int:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list) or not isinstance(payload.get("edges"), list):
        print("graph-view expects a json-graph payload with 'nodes' and 'edges'", file=sys.stderr)
        return 1
    output_path.write_text(_render_graph_html(payload, title), encoding="utf-8")
    return 0


def _render_graph_dot(
    store: BibliographyStore,
    seed_keys: list[str],
    rows: list[dict[str, object]],
) -> str:
    node_payloads = _collect_graph_nodes(store, seed_keys, rows)

    lines = ["digraph citegeist {", "  rankdir=LR;"]
    for citation_key, payload in sorted(node_payloads.items()):
        attributes = {
            "label": _graph_node_label(payload),
            "shape": "doublecircle" if payload.get("is_seed") else "ellipse",
        }
        if not payload.get("target_exists"):
            attributes["style"] = "dashed"
            attributes["color"] = "gray50"
        elif payload.get("review_status") == "reviewed":
            attributes["color"] = "forestgreen"
        elif payload.get("review_status") == "draft":
            attributes["color"] = "goldenrod"
        attr_string = ", ".join(f'{key}="{_dot_escape(str(value))}"' for key, value in attributes.items())
        lines.append(f'  "{_dot_escape(citation_key)}" [{attr_string}];')

    for row in rows:
        source_key = _dot_escape(str(row["source_citation_key"]))
        target_key = _dot_escape(str(row["target_citation_key"]))
        relation_type = _dot_escape(str(row["relation_type"]))
        depth_value = _dot_escape(str(row["depth"]))
        lines.append(
            f'  "{source_key}" -> "{target_key}" [label="{relation_type} d={depth_value}"];'
        )
    lines.append("}")
    return "\n".join(lines)


def _render_graph_json(
    store: BibliographyStore,
    seed_keys: list[str],
    rows: list[dict[str, object]],
) -> dict[str, object]:
    node_payloads = _collect_graph_nodes(store, seed_keys, rows)
    nodes = []
    for citation_key, payload in sorted(node_payloads.items()):
        nodes.append(
            {
                "id": citation_key,
                "label": citation_key,
                "title": payload.get("title"),
                "review_status": payload.get("review_status"),
                "target_exists": payload.get("target_exists"),
                "is_seed": payload.get("is_seed"),
            }
        )
    edges = []
    for index, row in enumerate(rows, start=1):
        edges.append(
            {
                "id": f"edge-{index}",
                "source": str(row["source_citation_key"]),
                "target": str(row["target_citation_key"]),
                "relation_type": str(row["relation_type"]),
                "depth": int(row["depth"]),
                "target_exists": bool(row["target_exists"]),
            }
        )
    return {"nodes": nodes, "edges": edges}


def _render_graph_html(payload: dict[str, object], title: str) -> str:
    graph_json = json.dumps(payload)
    safe_title = html_escape(title)
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f4f0e8;
      --panel: rgba(255, 255, 255, 0.82);
      --text: #1e1c18;
      --muted: #6e675c;
      --edge: #948b80;
      --seed: #9e3b2f;
      --reviewed: #2f6b3d;
      --draft: #b07d18;
      --missing: #8f8a83;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, #efe4d2, transparent 30%),
        radial-gradient(circle at bottom right, #ddd4c6, transparent 28%),
        var(--bg);
    }}
    .shell {{
      display: grid;
      grid-template-columns: 320px 1fr;
      min-height: 100vh;
    }}
    .sidebar {{
      padding: 1.25rem;
      border-right: 1px solid rgba(0, 0, 0, 0.08);
      background: var(--panel);
      backdrop-filter: blur(12px);
    }}
    .sidebar h1 {{
      margin: 0 0 0.5rem 0;
      font-size: 1.25rem;
    }}
    .sidebar p {{
      margin: 0 0 1rem 0;
      color: var(--muted);
      line-height: 1.4;
    }}
    .legend {{
      display: grid;
      gap: 0.5rem;
      margin-top: 1rem;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.95rem;
    }}
    .swatch {{
      width: 0.85rem;
      height: 0.85rem;
      border-radius: 999px;
      border: 1px solid rgba(0, 0, 0, 0.15);
    }}
    .viewer {{
      position: relative;
      overflow: hidden;
    }}
    svg {{
      width: 100%;
      height: 100vh;
      display: block;
    }}
    .edge {{
      stroke: var(--edge);
      stroke-width: 1.5;
      opacity: 0.8;
    }}
    .node {{
      stroke: rgba(0, 0, 0, 0.2);
      stroke-width: 1.5;
    }}
    .label {{
      font-size: 12px;
      fill: var(--text);
      pointer-events: none;
    }}
    .meta {{
      font-size: 0.92rem;
      color: var(--muted);
      margin-top: 1rem;
      display: grid;
      gap: 0.35rem;
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <h1>{title}</h1>
      <p>Offline graph viewer for CiteGeist <code>json-graph</code> exports.</p>
      <div class="meta">
        <div id="node-count"></div>
        <div id="edge-count"></div>
      </div>
      <div class="legend">
        <div class="legend-item"><span class="swatch" style="background: var(--seed)"></span>Seed node</div>
        <div class="legend-item"><span class="swatch" style="background: var(--reviewed)"></span>Reviewed node</div>
        <div class="legend-item"><span class="swatch" style="background: var(--draft)"></span>Draft node</div>
        <div class="legend-item"><span class="swatch" style="background: var(--missing)"></span>Missing node</div>
      </div>
      <div class="meta">
        <div>Tip: zoom in the browser and use the exported JSON for Cytoscape or D3 if you need richer interaction.</div>
      </div>
    </aside>
    <main class="viewer">
      <svg viewBox="0 0 1200 900" role="img" aria-label="Citation graph">
        <g id="edges"></g>
        <g id="nodes"></g>
        <g id="labels"></g>
      </svg>
    </main>
  </div>
  <script>
    const graph = {graph_json};
    const width = 1200;
    const height = 900;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.max(180, Math.min(width, height) * 0.34);
    const nodes = [...graph.nodes].sort((a, b) => String(a.id).localeCompare(String(b.id)));
    const edges = graph.edges;
    const byId = new Map();

    nodes.forEach((node, index) => {{
      const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1) - Math.PI / 2;
      const x = centerX + Math.cos(angle) * radius;
      const y = centerY + Math.sin(angle) * radius;
      const enriched = {{ ...node, x, y }};
      byId.set(node.id, enriched);
    }});

    document.getElementById("node-count").textContent = `${{nodes.length}} nodes`;
    document.getElementById("edge-count").textContent = `${{edges.length}} edges`;

    const edgeLayer = document.getElementById("edges");
    const nodeLayer = document.getElementById("nodes");
    const labelLayer = document.getElementById("labels");

    function nodeColor(node) {{
      if (!node.target_exists) return "var(--missing)";
      if (node.is_seed) return "var(--seed)";
      if (node.review_status === "reviewed") return "var(--reviewed)";
      return "var(--draft)";
    }}

    edges.forEach((edge) => {{
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (!source || !target) return;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("class", "edge");
      line.setAttribute("x1", source.x);
      line.setAttribute("y1", source.y);
      line.setAttribute("x2", target.x);
      line.setAttribute("y2", target.y);
      line.setAttribute("data-relation", edge.relation_type);
      edgeLayer.appendChild(line);
    }});

    [...byId.values()].forEach((node) => {{
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("class", "node");
      circle.setAttribute("cx", node.x);
      circle.setAttribute("cy", node.y);
      circle.setAttribute("r", node.is_seed ? 11 : 9);
      circle.setAttribute("fill", nodeColor(node));
      circle.setAttribute("data-title", node.title || "");
      nodeLayer.appendChild(circle);

      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("class", "label");
      label.setAttribute("x", node.x + 14);
      label.setAttribute("y", node.y + 4);
      label.textContent = node.title ? `${{node.id}}: ${{node.title}}` : node.id;
      labelLayer.appendChild(label);
    }});
  </script>
</body>
</html>
""".format(title=safe_title, graph_json=graph_json)


def _collect_graph_nodes(
    store: BibliographyStore,
    seed_keys: list[str],
    rows: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    node_payloads: dict[str, dict[str, object]] = {}
    entry_cache: dict[str, dict[str, object] | None] = {}

    def get_entry(citation_key: str) -> dict[str, object] | None:
        if citation_key not in entry_cache:
            entry_cache[citation_key] = store.get_entry(citation_key)
        return entry_cache[citation_key]

    for seed_key in seed_keys:
        entry = get_entry(seed_key)
        node_payloads[seed_key] = {
            "citation_key": seed_key,
            "title": entry.get("title") if entry else None,
            "review_status": entry.get("review_status") if entry else None,
            "target_exists": entry is not None,
            "is_seed": True,
        }

    for row in rows:
        source_key = str(row["source_citation_key"])
        target_key = str(row["target_citation_key"])
        source_entry = get_entry(source_key)
        node_payloads.setdefault(
            source_key,
            {
                "citation_key": source_key,
                "title": source_entry.get("title") if source_entry else None,
                "review_status": source_entry.get("review_status") if source_entry else None,
                "target_exists": source_entry is not None,
                "is_seed": source_key in seed_keys,
            },
        )
        node_payloads[target_key] = {
            "citation_key": target_key,
            "title": row.get("target_title"),
            "review_status": row.get("target_review_status"),
            "target_exists": bool(row.get("target_exists")),
            "is_seed": target_key in seed_keys,
        }
    return node_payloads


def _graph_node_label(payload: dict[str, object]) -> str:
    citation_key = str(payload.get("citation_key") or "")
    title = str(payload.get("title") or "").strip()
    review_status = str(payload.get("review_status") or "").strip()
    parts = [citation_key]
    if title:
        parts.append(title)
    if review_status:
        parts.append(f"[{review_status}]")
    return "\\n".join(parts)


def _dot_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


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
        expand_fn = lambda key: [
            item
            for relation_name in _expand_relation_types(relation)
            for item in expander.expand_entry(store, key, relation_type=relation_name, limit=limit)
        ]
    elif source == "opencitations":
        from .expand import OpenCitationsExpander

        expander = OpenCitationsExpander()
        expand_fn = lambda key: [
            item
            for relation_name in _expand_relation_types(relation)
            for item in expander.expand_entry(store, key, relation_type=relation_name, limit=limit)
        ]
    else:
        print(f"Unsupported expansion source: {source}", file=sys.stderr)
        return 1

    all_results = []
    total = len(citation_keys)
    for index, citation_key in enumerate(citation_keys, start=1):
        _print_progress("expanding seed", index, total, citation_key)
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
    rounds: int,
    recent_years: int | None,
    target_recent_entries: int | None,
) -> int:
    expander = TopicExpander()
    _print_phase(f"Loading topic expansion for {topic_slug}")
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
        max_rounds=rounds,
        recent_years=recent_years,
        target_recent_entries=target_recent_entries,
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
    _print_phase(f"Harvesting OAI-PMH records from {base_url}")
    harvested = harvester.list_records(
        base_url,
        metadata_prefix=metadata_prefix,
        set_spec=set_spec,
        date_from=date_from,
        date_until=date_until,
        limit=limit,
    )
    total = len(harvested)
    for index, result in enumerate(harvested, start=1):
        _print_progress("ingesting harvested record", index, total, result.entry.citation_key)
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
    _print_phase(f"Inspecting OAI-PMH repository {base_url}")
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
    expansion_mode: str,
    expansion_rounds: int,
    recent_years: int | None,
    target_recent_entries: int | None,
    max_expanded_entries: int | None,
    max_expand_seconds: float | None,
) -> int:
    if not seed_bib and not topic:
        print("bootstrap requires --seed-bib, --topic, or both", file=sys.stderr)
        return 1

    _print_phase("Running bootstrap")
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
        expansion_mode=expansion_mode,
        expansion_rounds=expansion_rounds,
        recent_years=recent_years,
        target_recent_entries=target_recent_entries,
        max_expanded_entries=max_expanded_entries,
        max_expand_seconds=max_expand_seconds,
    )
    print(json.dumps([asdict(result) for result in results], indent=2))
    return 0


def _run_bootstrap_batch(store: BibliographyStore, input_path: Path) -> int:
    jobs = load_batch_jobs(input_path)
    runner = BatchBootstrapRunner()
    _print_phase(f"Running bootstrap batch with {len(jobs)} jobs")
    results = runner.run(store, jobs)
    payload = []
    total = len(results)
    for index, job_result in enumerate(results, start=1):
        _print_progress("completed bootstrap job", index, total, job_result.job_name)
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
    expansion_mode: str,
    expansion_rounds: int,
    recent_years: int | None,
    target_recent_entries: int | None,
    max_expanded_entries: int | None,
    max_expand_seconds: float | None,
    review_status: str,
) -> int:
    scraper = TalkOriginsScraper()
    _print_phase(f"Scraping TalkOrigins example corpus from {base_url}")
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
        expansion_mode=expansion_mode,
        expansion_rounds=expansion_rounds,
        recent_years=recent_years,
        target_recent_entries=target_recent_entries,
        max_expanded_entries=max_expanded_entries,
        max_expand_seconds=max_expand_seconds,
    )
    print(json.dumps(asdict(export), indent=2))
    return 0


def _run_validate_talkorigins(manifest_path: Path) -> int:
    scraper = TalkOriginsScraper()
    _print_phase(f"Validating TalkOrigins manifest {manifest_path}")
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
    _print_phase(f"Generating TalkOrigins topic phrase suggestions from {manifest_path}")
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
    total = len(items)
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "")
        phrase = item.get("suggested_phrase", item.get("phrase"))
        if not slug:
            continue
        if phrase is not None:
            phrase = str(phrase)
        applied = store.set_topic_expansion_phrase(slug, phrase)
        _print_progress("applying topic phrase", index, total, slug or "<missing-slug>")
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
    total = len(items)
    for index, item in enumerate(items, start=1):
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
        _print_progress("staging topic phrase", index, total, slug or "<missing-slug>")
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
    total = len(items)
    for index, item in enumerate(items, start=1):
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
        _print_progress("reviewing topic phrase", index, total, slug or "<missing-slug>")
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
    _print_phase(f"Inspecting TalkOrigins duplicate clusters from {manifest_path}")
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
    _print_phase(f"Ingesting TalkOrigins export from {manifest_path}")
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
    _print_phase(f"Enriching weak TalkOrigins canonicals from {manifest_path}")
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
    _print_phase(f"Building TalkOrigins review export from {manifest_path}")
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
    _print_phase(f"Applying TalkOrigins corrections from {corrections_path}")
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


def _run_export_topic(store: BibliographyStore, topic_slug: str, output: str | None, include_stubs: bool) -> int:
    topic = store.get_topic(topic_slug)
    if topic is None:
        print(f"Topic not found: {topic_slug}", file=sys.stderr)
        return 1
    citation_keys = [row["citation_key"] for row in store.list_topic_entries(topic_slug, limit=100000)]
    rendered = store.export_bibtex(citation_keys, include_stubs=include_stubs)
    if output:
        Path(output).write_text(rendered + ("\n" if rendered else ""), encoding="utf-8")
    else:
        if rendered:
            print(rendered)
    return 0
