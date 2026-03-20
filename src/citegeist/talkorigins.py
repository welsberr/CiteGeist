"""TalkOrigins example implementation.

This module backs the example-facing namespace at ``citegeist.examples.talkorigins``.
New code should prefer importing from the examples namespace rather than treating
TalkOrigins support as part of the core top-level package surface.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .bibtex import BibEntry, render_bibtex
from .resolve import MetadataResolver, merge_entries, merge_entries_with_conflicts
from .sources import SourceClient
from .storage import BibliographyStore

YEAR_PATTERN = re.compile(r"\b(18|19|20)\d{2}\b")
REPEATED_AUTHOR_PATTERN = re.compile(r"^\s*[-_]{3,}\s*,?\s*")
WHITESPACE_PATTERN = re.compile(r"\s+")
TOPIC_PHRASE_STOPWORDS = {
    "about",
    "across",
    "after",
    "among",
    "analysis",
    "book",
    "books",
    "conference",
    "data",
    "edition",
    "effects",
    "example",
    "first",
    "from",
    "human",
    "humans",
    "journal",
    "method",
    "methods",
    "paper",
    "papers",
    "review",
    "science",
    "second",
    "studies",
    "study",
    "system",
    "their",
    "theory",
    "title",
    "using",
}


@dataclass(slots=True)
class TalkOriginsTopic:
    topic: str
    url: str
    raw_entries: list[str]


@dataclass(slots=True)
class TalkOriginsSeedSet:
    topic: str
    slug: str
    url: str
    raw_entry_count: int
    parsed_entry_count: int
    seed_bib: str
    plaintext_path: str = ""
    page_path: str = ""
    snapshot_path: str = ""


@dataclass(slots=True)
class TalkOriginsBatchExport:
    base_url: str
    output_dir: str
    topic_count: int
    entry_count: int
    jobs_path: str
    manifest_path: str
    seed_sets: list[TalkOriginsSeedSet]
    full_bib_path: str = ""
    full_plaintext_path: str = ""
    site_index_path: str = ""


@dataclass(slots=True)
class TalkOriginsValidationReport:
    manifest_path: str
    topic_count: int
    entry_count: int
    parsed_ratio: float
    missing_author_count: int
    missing_title_count: int
    missing_year_count: int
    suspicious_entry_type_count: int
    suspicious_examples: list[dict[str, str]]
    duplicate_cluster_count: int
    duplicate_entry_count: int
    duplicate_examples: list[dict[str, object]]


@dataclass(slots=True)
class TalkOriginsIngestReport:
    manifest_path: str
    topic_count: int
    raw_entry_count: int
    stored_entry_count: int
    duplicate_cluster_count: int
    duplicate_entry_count: int
    canonicalized_count: int


@dataclass(slots=True)
class TalkOriginsDuplicateCluster:
    key: str
    count: int
    items: list[dict[str, str]]
    canonical: dict[str, object] | None = None


@dataclass(slots=True)
class TalkOriginsEnrichmentResult:
    key: str
    citation_key: str
    weak_reasons_before: list[str]
    resolved: bool
    applied: bool
    source_label: str = ""
    weak_reasons_after: list[str] | None = None
    conflicts: list[dict[str, str]] | None = None
    error: str = ""


@dataclass(slots=True)
class TalkOriginsReviewExport:
    manifest_path: str
    item_count: int
    items: list[dict[str, object]]


@dataclass(slots=True)
class TalkOriginsCorrectionResult:
    key: str
    citation_key: str
    applied: bool
    error: str = ""


@dataclass(slots=True)
class TalkOriginsTopicPhraseSuggestion:
    slug: str
    topic: str
    entry_count: int
    suggested_phrase: str
    keywords: list[str]
    review_required: bool = False
    review_reasons: list[str] | None = None


class TalkOriginsScraper:
    def __init__(
        self,
        source_client: SourceClient | None = None,
        resolver: MetadataResolver | None = None,
    ) -> None:
        self.source_client = source_client or SourceClient()
        self.resolver = resolver or MetadataResolver(source_client=self.source_client)

    def scrape_to_directory(
        self,
        base_url: str,
        output_dir: str | Path,
        limit_topics: int | None = None,
        limit_entries_per_topic: int | None = None,
        resolve_seeds: bool = False,
        ingest_store: BibliographyStore | None = None,
        review_status: str = "draft",
        expand: bool = False,
        topic_limit: int = 5,
        topic_commit_limit: int | None = None,
        resume: bool = True,
    ) -> TalkOriginsBatchExport:
        output_root = Path(output_dir)
        seeds_dir = output_root / "seeds"
        plaintext_dir = output_root / "plaintext"
        snapshots_dir = output_root / "snapshots"
        site_dir = output_root / "site"
        topics_dir = site_dir / "topics"
        seeds_dir.mkdir(parents=True, exist_ok=True)
        plaintext_dir.mkdir(parents=True, exist_ok=True)
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        topics_dir.mkdir(parents=True, exist_ok=True)

        seed_sets: list[TalkOriginsSeedSet] = []
        total_entries = 0
        jobs: list[dict[str, object]] = []
        full_entries: list[BibEntry] = []
        full_plaintext_blocks: list[str] = []

        for topic in self.scrape_topics(
            base_url,
            snapshots_dir=snapshots_dir,
            limit_topics=limit_topics,
            resume=resume,
        ):
            raw_entries = topic.raw_entries[:limit_entries_per_topic] if limit_entries_per_topic else topic.raw_entries
            entry_pairs = [
                (raw_entry, self.parse_reference_entry(raw_entry, index + 1))
                for index, raw_entry in enumerate(raw_entries)
            ]
            parsed_entries = [entry for _, entry in entry_pairs if entry is not None]
            if resolve_seeds:
                parsed_entries = [self._augment_entry(entry) for entry in parsed_entries]
            if parsed_entries:
                augmented_iter = iter(parsed_entries)
                entry_pairs = [
                    (raw_entry, next(augmented_iter) if parsed_entry is not None else None)
                    for raw_entry, parsed_entry in entry_pairs
                ]

            slug = _slugify(topic.topic)
            seed_path = (seeds_dir / f"{slug}.bib").resolve()
            plaintext_path = (plaintext_dir / f"{slug}.txt").resolve()
            page_path = (topics_dir / f"{slug}.html").resolve()
            snapshot_path = (snapshots_dir / f"{slug}.json").resolve()
            rendered = render_bibtex(parsed_entries) if parsed_entries else ""
            seed_path.write_text(rendered + ("\n" if rendered else ""), encoding="utf-8")
            plaintext_path.write_text(_render_plaintext_topic(topic.topic, raw_entries), encoding="utf-8")
            page_path.write_text(
                _render_topic_page(topic.topic, entry_pairs, seed_path.name),
                encoding="utf-8",
            )

            if ingest_store is not None and parsed_entries:
                ingest_store.ingest_bibtex(
                    rendered,
                    source_label=topic.url,
                    review_status=review_status,
                )
                for entry in parsed_entries:
                    ingest_store.add_entry_topic(
                        entry.citation_key,
                        topic_slug=slug,
                        topic_name=topic.topic,
                        source_type="talkorigins",
                        source_url=topic.url,
                        source_label=topic.url,
                    )
                ingest_store.connection.commit()

            seed_set = TalkOriginsSeedSet(
                topic=topic.topic,
                slug=slug,
                url=topic.url,
                raw_entry_count=len(raw_entries),
                parsed_entry_count=len(parsed_entries),
                seed_bib=str(seed_path),
                plaintext_path=str(plaintext_path),
                page_path=str(page_path),
                snapshot_path=str(snapshot_path),
            )
            seed_sets.append(seed_set)
            total_entries += len(parsed_entries)
            full_entries.extend(parsed_entries)
            full_plaintext_blocks.append(_render_plaintext_topic(topic.topic, raw_entries).rstrip())
            jobs.append(
                {
                    "name": f"talkorigins:{slug}",
                    "topic": topic.topic,
                    "topic_slug": slug,
                    "topic_name": topic.topic,
                    "topic_phrase": topic.topic,
                    "seed_bib": str(seed_path),
                    "expand": expand,
                    "status": review_status,
                    "topic_limit": topic_limit,
                    "topic_commit_limit": topic_commit_limit,
                }
            )

        output_root.mkdir(parents=True, exist_ok=True)
        manifest_path = (output_root / "talkorigins_manifest.json").resolve()
        jobs_path = (output_root / "talkorigins_jobs.json").resolve()
        full_bib_path = (output_root / "talkorigins_full.bib").resolve()
        full_plaintext_path = (output_root / "talkorigins_full.txt").resolve()
        site_index_path = (site_dir / "index.html").resolve()
        full_bib_path.write_text(render_bibtex(full_entries) + ("\n" if full_entries else ""), encoding="utf-8")
        full_plaintext_path.write_text("\n\n".join(block for block in full_plaintext_blocks if block) + "\n", encoding="utf-8")
        site_index_path.write_text(
            _render_site_index(seed_sets, Path(full_bib_path).name, Path(full_plaintext_path).name),
            encoding="utf-8",
        )
        manifest_payload = {
            "base_url": base_url,
            "resume": resume,
            "seed_sets": [asdict(item) for item in seed_sets],
            "full_bib_path": str(full_bib_path),
            "full_plaintext_path": str(full_plaintext_path),
            "site_index_path": str(site_index_path),
        }
        manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        jobs_path.write_text(json.dumps({"jobs": jobs}, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        return TalkOriginsBatchExport(
            base_url=base_url,
            output_dir=str(output_root.resolve()),
            topic_count=len(seed_sets),
            entry_count=total_entries,
            jobs_path=str(jobs_path),
            manifest_path=str(manifest_path),
            seed_sets=seed_sets,
            full_bib_path=str(full_bib_path),
            full_plaintext_path=str(full_plaintext_path),
            site_index_path=str(site_index_path),
        )

    def validate_export(self, manifest_path: str | Path) -> TalkOriginsValidationReport:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        seed_sets = manifest.get("seed_sets", [])

        topic_count = len(seed_sets)
        raw_total = sum(int(item.get("raw_entry_count", 0)) for item in seed_sets)
        parsed_total = sum(int(item.get("parsed_entry_count", 0)) for item in seed_sets)
        missing_author_count = 0
        missing_title_count = 0
        missing_year_count = 0
        suspicious_entry_type_count = 0
        suspicious_examples: list[dict[str, str]] = []
        duplicate_groups: dict[str, list[dict[str, str]]] = {}

        for seed_set in seed_sets:
            seed_bib = seed_set.get("seed_bib")
            if not isinstance(seed_bib, str) or not seed_bib:
                continue
            path = Path(seed_bib)
            if not path.exists():
                continue
            entries = parse_bib_file(path)
            for entry in entries:
                if not entry.fields.get("author"):
                    missing_author_count += 1
                if not entry.fields.get("title"):
                    missing_title_count += 1
                if not entry.fields.get("year"):
                    missing_year_count += 1
                if _is_suspicious_entry_type(entry):
                    suspicious_entry_type_count += 1
                    if len(suspicious_examples) < 20:
                        suspicious_examples.append(
                            {
                                "citation_key": entry.citation_key,
                                "entry_type": entry.entry_type,
                                "title": entry.fields.get("title", ""),
                                "journal": entry.fields.get("journal", ""),
                                "publisher": entry.fields.get("publisher", ""),
                                "howpublished": entry.fields.get("howpublished", ""),
                            }
                        )
                duplicate_key = _duplicate_key(entry)
                if duplicate_key:
                    duplicate_groups.setdefault(duplicate_key, []).append(
                        {
                            "citation_key": entry.citation_key,
                            "title": entry.fields.get("title", ""),
                            "author": entry.fields.get("author", ""),
                            "year": entry.fields.get("year", ""),
                            "seed_bib": str(path),
                        }
                    )

        parsed_ratio = (parsed_total / raw_total) if raw_total else 0.0
        duplicate_examples: list[dict[str, object]] = []
        duplicate_cluster_count = 0
        duplicate_entry_count = 0
        for group_key, items in sorted(duplicate_groups.items()):
            if len(items) < 2:
                continue
            duplicate_cluster_count += 1
            duplicate_entry_count += len(items)
            if len(duplicate_examples) < 20:
                duplicate_examples.append(
                    {
                        "key": group_key,
                        "count": len(items),
                        "items": items[:5],
                    }
                )
        return TalkOriginsValidationReport(
            manifest_path=str(Path(manifest_path).resolve()),
            topic_count=topic_count,
            entry_count=parsed_total,
            parsed_ratio=parsed_ratio,
            missing_author_count=missing_author_count,
            missing_title_count=missing_title_count,
            missing_year_count=missing_year_count,
            suspicious_entry_type_count=suspicious_entry_type_count,
            suspicious_examples=suspicious_examples,
            duplicate_cluster_count=duplicate_cluster_count,
            duplicate_entry_count=duplicate_entry_count,
            duplicate_examples=duplicate_examples,
        )

    def suggest_topic_phrases(
        self,
        manifest_path: str | Path,
        limit: int | None = None,
        topic_slug: str | None = None,
    ) -> list[TalkOriginsTopicPhraseSuggestion]:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        seed_sets = manifest.get("seed_sets", [])
        suggestions: list[TalkOriginsTopicPhraseSuggestion] = []

        for seed_set in seed_sets:
            current_topic_slug = str(seed_set.get("slug") or _slugify(str(seed_set.get("topic") or "")))
            if topic_slug and current_topic_slug != topic_slug:
                continue
            seed_bib = seed_set.get("seed_bib")
            if not isinstance(seed_bib, str) or not seed_bib:
                continue
            path = Path(seed_bib)
            if not path.exists():
                continue
            entries = parse_bib_file(path)
            topic_name = str(seed_set.get("topic") or current_topic_slug)
            keywords = _suggest_topic_keywords(entries, topic_name)
            review_reasons = _topic_phrase_review_reasons(entries, keywords)
            suggestions.append(
                TalkOriginsTopicPhraseSuggestion(
                    slug=current_topic_slug,
                    topic=topic_name,
                    entry_count=len(entries),
                    suggested_phrase=" ".join([topic_name, *keywords]).strip(),
                    keywords=keywords,
                    review_required=bool(review_reasons),
                    review_reasons=review_reasons,
                )
            )

        suggestions.sort(key=lambda item: (item.topic.casefold(), item.slug))
        if limit is not None:
            suggestions = suggestions[:limit]
        return suggestions

    def inspect_duplicate_clusters(
        self,
        manifest_path: str | Path,
        limit: int = 20,
        min_count: int = 2,
        match: str | None = None,
        topic_slug: str | None = None,
        preview_canonical: bool = False,
        weak_only: bool = False,
    ) -> list[TalkOriginsDuplicateCluster]:
        duplicate_groups, grouped_entries = _collect_duplicate_groups(
            manifest_path,
            match=match,
            topic_slug=topic_slug,
        )

        clusters: list[TalkOriginsDuplicateCluster] = []
        for group_key, items in sorted(duplicate_groups.items()):
            if len(items) < min_count:
                continue
            canonical_payload = None
            if preview_canonical:
                canonical = _build_canonical_preview(grouped_entries[group_key])
                weak_reasons = _canonical_weaknesses(canonical)
                if weak_only and not weak_reasons:
                    continue
                canonical_payload = {
                    "citation_key": canonical.citation_key,
                    "entry_type": canonical.entry_type,
                    "field_count": len([value for value in canonical.fields.values() if value]),
                    "fields": dict(sorted(canonical.fields.items())),
                    "weak_reasons": weak_reasons,
                }
            elif weak_only:
                canonical = _build_canonical_preview(grouped_entries[group_key])
                if not _canonical_weaknesses(canonical):
                    continue
            clusters.append(
                TalkOriginsDuplicateCluster(
                    key=group_key,
                    count=len(items),
                    items=sorted(
                        items,
                        key=lambda item: (
                            item.get("topic_slug", ""),
                            item.get("year", ""),
                            item.get("citation_key", ""),
                        ),
                    ),
                    canonical=canonical_payload,
                )
            )
        return clusters[:limit]

    def enrich_weak_canonicals(
        self,
        manifest_path: str | Path,
        store: BibliographyStore,
        limit: int = 20,
        min_count: int = 2,
        match: str | None = None,
        topic_slug: str | None = None,
        apply: bool = False,
        review_status: str = "enriched",
        allow_unsafe_matches: bool = False,
    ) -> list[TalkOriginsEnrichmentResult]:
        duplicate_groups, grouped_entries = _collect_duplicate_groups(
            manifest_path,
            match=match,
            topic_slug=topic_slug,
        )
        results: list[TalkOriginsEnrichmentResult] = []

        for group_key, items in sorted(duplicate_groups.items()):
            if len(items) < min_count:
                continue
            canonical = _build_canonical_preview(grouped_entries[group_key])
            weak_reasons_before = _canonical_weaknesses(canonical)
            if not weak_reasons_before:
                continue
            resolution = None
            error = ""
            try:
                resolution = self.resolver.resolve_entry(canonical)
            except Exception as exc:
                error = str(exc)

            result = TalkOriginsEnrichmentResult(
                key=group_key,
                citation_key=canonical.citation_key,
                weak_reasons_before=weak_reasons_before,
                resolved=resolution is not None,
                applied=False,
                source_label=resolution.source_label if resolution is not None else "",
                error=error,
            )

            if resolution is not None:
                if not allow_unsafe_matches and not _is_safe_enrichment_match(canonical, resolution):
                    result.resolved = False
                    result.source_label = resolution.source_label
                    result.error = "unsafe resolver match"
                    results.append(result)
                    if len(results) >= limit:
                        break
                    continue
                merged, conflicts = merge_entries_with_conflicts(canonical, resolution.entry)
                if canonical.entry_type == "misc" and resolution.entry.entry_type != "misc":
                    merged = BibEntry(
                        entry_type=resolution.entry.entry_type,
                        citation_key=merged.citation_key,
                        fields=merged.fields,
                    )
                result.conflicts = conflicts
                result.weak_reasons_after = _canonical_weaknesses(merged)
                if apply:
                    store_key = _find_store_citation_key(store, canonical)
                    if store_key:
                        store.replace_entry(
                            store_key,
                            merged,
                            source_type=resolution.source_type,
                            source_label=resolution.source_label,
                            review_status=review_status,
                        )
                        if conflicts:
                            store.record_conflicts(
                                store_key,
                                conflicts,
                                source_type=resolution.source_type,
                                source_label=resolution.source_label,
                            )
                        result.citation_key = store_key
                        result.applied = True
            results.append(result)
            if len(results) >= limit:
                break

        if apply:
            store.connection.commit()
        return results

    def build_review_export(
        self,
        manifest_path: str | Path,
        store: BibliographyStore,
        limit: int = 20,
        min_count: int = 2,
        match: str | None = None,
        topic_slug: str | None = None,
    ) -> TalkOriginsReviewExport:
        clusters = self.inspect_duplicate_clusters(
            manifest_path,
            limit=limit,
            min_count=min_count,
            match=match,
            topic_slug=topic_slug,
            preview_canonical=True,
            weak_only=True,
        )
        enrichment_results = self.enrich_weak_canonicals(
            manifest_path,
            store,
            limit=limit,
            min_count=min_count,
            match=match,
            topic_slug=topic_slug,
            apply=False,
        )
        by_key = {result.key: result for result in enrichment_results}
        items: list[dict[str, object]] = []
        for cluster in clusters:
            result = by_key.get(cluster.key)
            payload = {
                "key": cluster.key,
                "count": cluster.count,
                "items": cluster.items,
                "canonical": cluster.canonical,
                "enrichment": asdict(result) if result is not None else None,
            }
            items.append(payload)
        return TalkOriginsReviewExport(
            manifest_path=str(Path(manifest_path).resolve()),
            item_count=len(items),
            items=items,
        )

    def apply_review_corrections(
        self,
        manifest_path: str | Path,
        corrections_path: str | Path,
        store: BibliographyStore,
        default_review_status: str = "reviewed",
    ) -> list[TalkOriginsCorrectionResult]:
        duplicate_groups, grouped_entries = _collect_duplicate_groups(manifest_path)
        payload = json.loads(Path(corrections_path).read_text(encoding="utf-8"))
        correction_items = payload.get("corrections", [])
        results: list[TalkOriginsCorrectionResult] = []

        for item in correction_items:
            key = str(item.get("key") or "")
            if not key:
                results.append(TalkOriginsCorrectionResult(key="", citation_key="", applied=False, error="missing key"))
                continue
            entries = grouped_entries.get(key)
            if not entries:
                results.append(TalkOriginsCorrectionResult(key=key, citation_key="", applied=False, error="unknown key"))
                continue

            canonical = _build_canonical_preview(entries)
            store_key = _find_store_citation_key(store, canonical)
            if not store_key:
                results.append(TalkOriginsCorrectionResult(key=key, citation_key=canonical.citation_key, applied=False, error="entry not found in store"))
                continue

            corrected = BibEntry(
                entry_type=str(item.get("entry_type") or canonical.entry_type),
                citation_key=store_key,
                fields=dict(canonical.fields),
            )
            override_fields = item.get("fields", {})
            if isinstance(override_fields, dict):
                for field_name, value in override_fields.items():
                    if value is None:
                        corrected.fields.pop(str(field_name), None)
                    else:
                        corrected.fields[str(field_name)] = str(value)

            review_status = str(item.get("review_status") or default_review_status)
            store.replace_entry(
                store_key,
                corrected,
                source_type="manual_review",
                source_label=f"talkorigins_corrections:{Path(corrections_path).resolve()}",
                review_status=review_status,
            )
            results.append(TalkOriginsCorrectionResult(key=key, citation_key=store_key, applied=True))

        store.connection.commit()
        return results

    def ingest_export(
        self,
        manifest_path: str | Path,
        store: BibliographyStore,
        review_status: str = "draft",
        dedupe: bool = True,
    ) -> TalkOriginsIngestReport:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        seed_sets = manifest.get("seed_sets", [])
        topic_count = len(seed_sets)
        raw_entry_count = sum(int(item.get("parsed_entry_count", 0)) for item in seed_sets)

        grouped: dict[str, list[tuple[dict[str, object], BibEntry]]] = {}
        canonicalized_count = 0
        duplicate_entry_count = 0

        for seed_set in seed_sets:
            seed_bib = seed_set.get("seed_bib")
            if not isinstance(seed_bib, str) or not seed_bib:
                continue
            entries = parse_bib_file(seed_bib)
            for entry in entries:
                group_key = _duplicate_key(entry) if dedupe else entry.citation_key
                if not group_key:
                    group_key = entry.citation_key
                grouped.setdefault(group_key, []).append((seed_set, entry))

        stored_entry_count = 0
        duplicate_cluster_count = 0
        source_label = str(Path(manifest_path).resolve())
        key_owners: dict[str, str] = {}
        existing_rows = store.connection.execute("SELECT citation_key FROM entries").fetchall()
        for row in existing_rows:
            key_owners[str(row["citation_key"])] = "__existing__"

        for group_key, items in grouped.items():
            if len(items) > 1:
                duplicate_cluster_count += 1
                duplicate_entry_count += len(items)

            canonical = _select_canonical_entry([entry for _, entry in items])
            for _, duplicate in items:
                if duplicate.citation_key != canonical.citation_key:
                    canonical = merge_entries(canonical, duplicate)
                    canonicalized_count += 1
            canonical = _assign_canonical_key(canonical, group_key, key_owners)

            store.upsert_entry(
                canonical,
                raw_bibtex=render_bibtex([canonical]),
                source_type="talkorigins",
                source_label=source_label,
                review_status=review_status,
            )
            stored_entry_count += 1

            seen_topics: set[str] = set()
            for seed_set, _ in items:
                topic_slug = str(seed_set.get("slug") or _slugify(str(seed_set.get("topic") or "")))
                if topic_slug in seen_topics:
                    continue
                seen_topics.add(topic_slug)
                store.add_entry_topic(
                    canonical.citation_key,
                    topic_slug=topic_slug,
                    topic_name=str(seed_set.get("topic") or topic_slug),
                    source_type="talkorigins",
                    source_url=str(seed_set.get("url") or ""),
                    source_label=source_label,
                )

        store.connection.commit()
        return TalkOriginsIngestReport(
            manifest_path=str(Path(manifest_path).resolve()),
            topic_count=topic_count,
            raw_entry_count=raw_entry_count,
            stored_entry_count=stored_entry_count,
            duplicate_cluster_count=duplicate_cluster_count,
            duplicate_entry_count=duplicate_entry_count,
            canonicalized_count=canonicalized_count,
        )

    def scrape_topics(
        self,
        base_url: str,
        snapshots_dir: Path | None = None,
        limit_topics: int | None = None,
        resume: bool = True,
    ) -> list[TalkOriginsTopic]:
        index_html = self.source_client.get_text(base_url)
        parser = _TopicIndexParser(base_url)
        parser.feed(index_html)

        topics: list[TalkOriginsTopic] = []
        for link in parser.topic_links[:limit_topics]:
            slug = _slugify(link["topic"])
            snapshot_path = snapshots_dir / f"{slug}.json" if snapshots_dir is not None else None
            snapshot = _load_snapshot(snapshot_path) if resume and snapshot_path is not None else None
            if snapshot is not None:
                raw_entries = list(snapshot.get("raw_entries", []))
            else:
                page_html = self.source_client.get_text(link["url"])
                topic_parser = _TopicPageParser()
                topic_parser.feed(page_html)
                raw_entries = normalize_topic_entries(topic_parser.preformatted_text())
                if snapshot_path is not None:
                    snapshot_payload = {
                        "topic": link["topic"],
                        "url": link["url"],
                        "raw_entries": raw_entries,
                    }
                    snapshot_path.write_text(json.dumps(snapshot_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            topics.append(TalkOriginsTopic(topic=link["topic"], url=link["url"], raw_entries=raw_entries))
        return topics

    def parse_reference_entry(self, raw_entry: str, ordinal: int) -> BibEntry | None:
        year_match = YEAR_PATTERN.search(raw_entry)
        if year_match is None:
            return None

        year = year_match.group(0)
        author_part = raw_entry[: year_match.start()].strip(" ,.;:")
        remainder = raw_entry[year_match.end() :].strip(" ,.;:")
        if not author_part or not remainder:
            return None

        title, venue = _split_title_and_venue(remainder)
        if not title:
            return None

        authors = _normalize_gsa_authors(author_part)
        citation_key = _make_citation_key(authors, year, title, ordinal)
        entry_type = _guess_entry_type(remainder)
        fields = {
            "author": authors,
            "year": year,
            "title": title,
            "note": f"talkorigins_source = {{true}}; raw_reference = {{{raw_entry}}}",
        }
        if entry_type == "book":
            normalized = _normalize_incollection_candidate(title, venue)
            if normalized is not None:
                title = normalized["title"]
                fields["title"] = title
                entry_type = "incollection"
                if normalized.get("editor"):
                    fields["editor"] = normalized["editor"]
                if normalized.get("booktitle"):
                    fields["booktitle"] = normalized["booktitle"]
                if normalized.get("publisher"):
                    fields["publisher"] = normalized["publisher"]
                venue = ""
        if venue:
            if entry_type == "article":
                fields["journal"] = venue
            elif entry_type == "inproceedings":
                fields["booktitle"] = venue
            elif entry_type == "incollection":
                fields["booktitle"] = venue
            elif entry_type in {"book", "phdthesis", "mastersthesis"}:
                fields["publisher"] = venue
            else:
                fields["howpublished"] = venue

        return BibEntry(entry_type=entry_type, citation_key=citation_key, fields=fields)

    def _augment_entry(self, entry: BibEntry) -> BibEntry:
        try:
            resolution = self.resolver.resolve_entry(entry)
        except Exception:
            return entry
        if resolution is None:
            return entry
        return merge_entries(entry, resolution.entry)


def normalize_topic_entries(text: str) -> list[str]:
    entries: list[str] = []
    previous_authors = ""
    current: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                entry_text = " ".join(current)
                normalized = _normalize_repeated_authors(entry_text, previous_authors)
                entries.append(normalized)
                previous_authors = _extract_author_prefix(normalized) or previous_authors
                current = []
            continue
        current.append(WHITESPACE_PATTERN.sub(" ", line))

    if current:
        entry_text = " ".join(current)
        normalized = _normalize_repeated_authors(entry_text, previous_authors)
        entries.append(normalized)

    return entries


def _normalize_repeated_authors(entry_text: str, previous_authors: str) -> str:
    if previous_authors and REPEATED_AUTHOR_PATTERN.match(entry_text):
        return REPEATED_AUTHOR_PATTERN.sub(f"{previous_authors}, ", entry_text, count=1)
    return entry_text


def _extract_author_prefix(entry_text: str) -> str:
    year_match = YEAR_PATTERN.search(entry_text)
    if year_match is None:
        return ""
    return entry_text[: year_match.start()].strip(" ,;:")


def _split_title_and_venue(remainder: str) -> tuple[str, str]:
    if ": " in remainder:
        title, venue = remainder.split(": ", 1)
        return _clean_fragment(title), _clean_fragment(venue)

    parts = [part.strip() for part in remainder.split(". ") if part.strip()]
    if not parts:
        return "", ""
    title = parts[0]
    venue = ". ".join(parts[1:]) if len(parts) > 1 else ""
    return _clean_fragment(title), _clean_fragment(venue)


def _normalize_gsa_authors(author_part: str) -> str:
    cleaned = WHITESPACE_PATTERN.sub(" ", author_part.replace("&", " and ")).strip(" ,;:")
    if " and " in cleaned and "," not in cleaned:
        return cleaned

    fragments = [fragment.strip() for fragment in cleaned.split(",") if fragment.strip()]
    if len(fragments) < 2:
        return cleaned

    authors: list[str] = []
    index = 0
    while index + 1 < len(fragments):
        family = re.sub(r"^(and)\s+", "", fragments[index], flags=re.IGNORECASE).strip()
        given = re.sub(r"^(and)\s+", "", fragments[index + 1], flags=re.IGNORECASE).strip()
        if family and given:
            authors.append(f"{family}, {given}")
        index += 2

    if index < len(fragments):
        trailing = re.sub(r"^(and)\s+", "", fragments[index], flags=re.IGNORECASE).strip()
        if trailing:
            authors.append(trailing)

    return " and ".join(authors) if authors else cleaned


def _make_citation_key(authors: str, year: str, title: str, ordinal: int) -> str:
    first_author = authors.split(" and ")[0]
    family = first_author.split(",", 1)[0] if "," in first_author else first_author.split()[-1]
    family = re.sub(r"[^A-Za-z0-9]+", "", family).lower() or "ref"
    first_word = re.sub(r"[^A-Za-z0-9]+", "", title.split()[0]).lower() if title.split() else "untitled"
    first_word = first_word or "untitled"
    return f"{family}{year}{first_word}{ordinal}"


def _guess_entry_type(text: str) -> str:
    lowered = text.lower()
    if "ph.d" in lowered or "dissertation" in lowered or "thesis" in lowered:
        return "phdthesis"
    if any(
        token in lowered
        for token in (
            "press",
            "publisher",
            "publications",
            "publication",
            "elsevier",
            "springer",
            "wiley",
            "university",
            "books",
        )
    ):
        return "book"
    if any(token in lowered for token in ("proceedings", "conference", "symposium", "workshop")):
        return "inproceedings"
    if any(token in lowered for token in ("journal", "review", "letters", "quarterly", "science", "nature")):
        return "article"
    return "misc"


def _clean_fragment(value: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", value.strip(" .;:,\"'"))


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.lower()).strip("-")
    return slug or "topic"


def _normalize_incollection_candidate(title: str, venue: str) -> dict[str, str] | None:
    lowered = venue.lower()
    if ", in " not in lowered:
        return None

    split_index = lowered.find(", in ")
    prefix = _clean_fragment(venue[:split_index])
    container = venue[split_index + len(", in ") :].strip()
    if not container:
        return None

    editor_match = re.match(r"^(?P<editors>.+?),\s+eds?\.,\s+(?P<rest>.+)$", container, flags=re.IGNORECASE)
    if editor_match is None:
        return None

    editor_text = _normalize_gsa_authors(editor_match.group("editors"))
    rest = editor_match.group("rest").strip()
    if ": " in rest:
        booktitle, publisher = rest.split(": ", 1)
    else:
        booktitle, publisher = rest, ""

    normalized_title = title
    if prefix:
        normalized_title = _clean_fragment(f"{title}: {prefix}")

    payload = {
        "title": normalized_title,
        "editor": editor_text,
        "booktitle": _clean_fragment(booktitle),
    }
    if publisher:
        payload["publisher"] = _clean_fragment(publisher)
    return payload


def _load_snapshot(path: Path | None) -> dict[str, object] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def parse_bib_file(path: str | Path) -> list[BibEntry]:
    from .bibtex import parse_bibtex

    return parse_bibtex(Path(path).read_text(encoding="utf-8"))


def _render_plaintext_topic(topic: str, raw_entries: list[str]) -> str:
    body = "\n\n".join(raw_entries)
    return f"{topic}\n\n{body}\n" if body else f"{topic}\n"


def _render_topic_page(topic: str, entry_pairs: list[tuple[str, BibEntry | None]], seed_filename: str) -> str:
    entry_blocks: list[str] = []
    for index, (raw_entry, parsed_entry) in enumerate(entry_pairs, start=1):
        bibtex_block = ""
        if parsed_entry is not None:
            bibtex_block = render_bibtex([parsed_entry])
        safe_plain = _html_escape(raw_entry)
        safe_bibtex = _html_escape(bibtex_block)
        entry_blocks.append(
            "\n".join(
                [
                    '<article class="entry">',
                    f'  <div class="gsa-entry">{safe_plain}</div>',
                    f'  <button type="button" class="toggle" onclick="toggleBibtex(\'bibtex-{index}\')">Show BibTeX</button>',
                    f'  <div id="bibtex-{index}" class="bibtex hidden"><pre>{safe_bibtex}</pre></div>',
                    "</article>",
                ]
            )
        )

    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8" />',
            f"  <title>{_html_escape(topic)} bibliography</title>",
            "  <style>",
            "    body { font-family: Georgia, serif; margin: 2rem auto; max-width: 900px; line-height: 1.5; }",
            "    .entry { margin: 0 0 1.5rem 0; padding-bottom: 1rem; border-bottom: 1px solid #ccc; }",
            "    .gsa-entry { white-space: pre-wrap; }",
            "    .bibtex.hidden { display: none; }",
            "    .toggle { margin-top: 0.5rem; }",
            "    pre { background: #f6f3eb; padding: 0.75rem; overflow-x: auto; }",
            "  </style>",
            "  <script>",
            "    function toggleBibtex(id) {",
            "      const element = document.getElementById(id);",
            "      if (!element) { return; }",
            "      element.classList.toggle('hidden');",
            "    }",
            "  </script>",
            "</head>",
            "<body>",
            f"  <h1>{_html_escape(topic)}</h1>",
            f'  <p><a href="../index.html">Back to index</a> | <a href="../../seeds/{_html_escape(seed_filename)}">Seed BibTeX</a></p>',
            *entry_blocks,
            "</body>",
            "</html>",
        ]
    ) + "\n"


def _render_site_index(seed_sets: list[TalkOriginsSeedSet], full_bib_name: str, full_plaintext_name: str) -> str:
    items = [
        f'    <li><a href="topics/{_html_escape(item.slug)}.html">{_html_escape(item.topic)}</a> '
        f'({item.parsed_entry_count} entries)</li>'
        for item in seed_sets
    ]
    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8" />',
            "  <title>TalkOrigins bibliography reconstruction</title>",
            "  <style>body { font-family: Georgia, serif; margin: 2rem auto; max-width: 900px; line-height: 1.5; }</style>",
            "</head>",
            "<body>",
            "  <h1>TalkOrigins bibliography reconstruction</h1>",
            "  <p>Downloads:</p>",
            "  <ul>",
            f'    <li><a href="../{_html_escape(full_plaintext_name)}">Full plaintext bibliography</a></li>',
            f'    <li><a href="../{_html_escape(full_bib_name)}">Full BibTeX bibliography</a></li>',
            "  </ul>",
            "  <h2>Topics</h2>",
            "  <ul>",
            *items,
            "  </ul>",
            "</body>",
            "</html>",
        ]
    ) + "\n"


def _html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _collect_duplicate_groups(
    manifest_path: str | Path,
    match: str | None = None,
    topic_slug: str | None = None,
) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[BibEntry]]]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    seed_sets = manifest.get("seed_sets", [])
    match_text = match.casefold() if match else None
    duplicate_groups: dict[str, list[dict[str, str]]] = {}
    grouped_entries: dict[str, list[BibEntry]] = {}

    for seed_set in seed_sets:
        seed_bib = seed_set.get("seed_bib")
        if not isinstance(seed_bib, str) or not seed_bib:
            continue
        current_topic_slug = str(seed_set.get("slug") or _slugify(str(seed_set.get("topic") or "")))
        if topic_slug and current_topic_slug != topic_slug:
            continue
        path = Path(seed_bib)
        if not path.exists():
            continue
        for entry in parse_bib_file(path):
            duplicate_key = _duplicate_key(entry)
            if not duplicate_key:
                continue
            item = {
                "citation_key": entry.citation_key,
                "title": entry.fields.get("title", ""),
                "author": entry.fields.get("author", ""),
                "year": entry.fields.get("year", ""),
                "seed_bib": str(path),
                "topic": str(seed_set.get("topic") or ""),
                "topic_slug": current_topic_slug,
            }
            if match_text and not _duplicate_item_matches(item, duplicate_key, match_text):
                continue
            duplicate_groups.setdefault(duplicate_key, []).append(item)
            grouped_entries.setdefault(duplicate_key, []).append(entry)

    return duplicate_groups, grouped_entries


def _duplicate_key(entry: BibEntry) -> str:
    author = _normalize_duplicate_text(entry.fields.get("author", ""))
    title = _normalize_duplicate_text(entry.fields.get("title", ""))
    year = entry.fields.get("year", "").strip()
    if not author or not title or not year:
        return ""
    first_author = author.split(" and ")[0]
    return f"{first_author}|{year}|{title}"


def _duplicate_item_matches(item: dict[str, str], duplicate_key: str, match_text: str) -> bool:
    haystacks = (
        duplicate_key,
        item.get("citation_key", ""),
        item.get("title", ""),
        item.get("author", ""),
        item.get("year", ""),
        item.get("topic", ""),
        item.get("topic_slug", ""),
        item.get("seed_bib", ""),
    )
    return any(match_text in value.casefold() for value in haystacks if value)


def _normalize_duplicate_text(value: str) -> str:
    normalized = value.lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _topic_phrase_tokens(value: str) -> list[str]:
    return [
        token
        for token in _normalize_duplicate_text(value).split()
        if len(token) >= 4 and token not in TOPIC_PHRASE_STOPWORDS
    ]


def _suggest_topic_keywords(entries: list[BibEntry], topic_name: str, max_keywords: int = 4) -> list[str]:
    topic_terms = set(_topic_phrase_tokens(topic_name))
    counts: Counter[str] = Counter()
    for entry in entries:
        for term in set(_topic_phrase_tokens(entry.fields.get("title", ""))):
            if term in topic_terms:
                continue
            counts[term] += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if len(entries) <= 1:
        max_keywords = min(max_keywords, 1)
    elif len(entries) <= 3:
        max_keywords = min(max_keywords, 2)
    filtered = [(term, count) for term, count in ranked if count >= 2]
    selected = filtered if filtered else ranked[:max_keywords]
    return [term for term, _ in selected[:max_keywords]]


def _topic_phrase_review_reasons(entries: list[BibEntry], keywords: list[str]) -> list[str]:
    reasons: list[str] = []
    if len(entries) <= 1:
        reasons.append("single_entry_topic")
    elif len(entries) <= 3:
        reasons.append("small_topic")
    if not keywords:
        reasons.append("no_keyword_signal")
    elif len(keywords) == 1:
        reasons.append("thin_keyword_signal")
    if any(_looks_noisy_keyword(keyword) for keyword in keywords):
        reasons.append("noisy_keywords")
    return reasons


def _looks_noisy_keyword(keyword: str) -> bool:
    if len(keyword) <= 3:
        return True
    if any(char.isdigit() for char in keyword):
        return True
    noisy_tokens = {"boundry", "colloquium", "edition", "history", "idea", "central", "bearing", "time"}
    return keyword in noisy_tokens


def _select_canonical_entry(entries: list[BibEntry]) -> BibEntry:
    return max(
        entries,
        key=lambda entry: (
            _entry_richness(entry),
            -len(entry.citation_key),
            entry.citation_key,
        ),
    )


def _build_canonical_preview(entries: list[BibEntry]) -> BibEntry:
    canonical = _select_canonical_entry(entries)
    for duplicate in entries:
        if duplicate.citation_key != canonical.citation_key:
            canonical = merge_entries(canonical, duplicate)
    return canonical


def _canonical_weaknesses(entry: BibEntry) -> list[str]:
    reasons: list[str] = []
    if entry.entry_type == "misc":
        reasons.append("entry_type:misc")
    if not entry.fields.get("doi"):
        reasons.append("missing:doi")
    if _entry_richness(entry) < 6:
        reasons.append("low_field_richness")
    if entry.entry_type in {"article", "inproceedings", "incollection"} and not (
        entry.fields.get("journal") or entry.fields.get("booktitle")
    ):
        reasons.append("missing:venue")
    return reasons


def _find_store_citation_key(store: BibliographyStore, entry: BibEntry) -> str | None:
    if store.get_entry(entry.citation_key) is not None:
        return entry.citation_key

    first_author = entry.fields.get("author", "").split(" and ")[0].strip()
    row = store.connection.execute(
        """
        SELECT e.citation_key
        FROM entries e
        LEFT JOIN entry_creators ec
          ON ec.entry_id = e.id AND ec.role = 'author' AND ec.ordinal = 1
        LEFT JOIN creators c
          ON c.id = ec.creator_id
        WHERE COALESCE(e.title, '') = ?
          AND COALESCE(e.year, '') = ?
          AND COALESCE(c.full_name, '') = ?
        ORDER BY e.citation_key
        LIMIT 1
        """,
        (
            entry.fields.get("title", ""),
            entry.fields.get("year", ""),
            first_author,
        ),
    ).fetchone()
    if row is None:
        return None
    return str(row["citation_key"])


def _is_safe_enrichment_match(base: BibEntry, resolution: object) -> bool:
    source_label = getattr(resolution, "source_label", "")
    resolved_entry = getattr(resolution, "entry", None)
    if not isinstance(source_label, str) or resolved_entry is None:
        return False
    if ":search:" not in source_label:
        return True

    base_title = _normalize_duplicate_text(base.fields.get("title", ""))
    resolved_title = _normalize_duplicate_text(resolved_entry.fields.get("title", ""))
    if not base_title or base_title != resolved_title:
        return False

    base_year = (base.fields.get("year") or "").strip()
    resolved_year = (resolved_entry.fields.get("year") or "").strip()
    if base_year and resolved_year and base_year == resolved_year:
        return True

    base_author = _normalize_duplicate_text(base.fields.get("author", ""))
    resolved_author = _normalize_duplicate_text(resolved_entry.fields.get("author", ""))
    if not base_author or not resolved_author:
        return False
    base_first = base_author.split(" and ")[0].split()[0]
    resolved_first = resolved_author.split(" and ")[0].split()[0]
    return bool(base_first and resolved_first and base_first == resolved_first)


def _entry_richness(entry: BibEntry) -> int:
    score = 0
    for field_name, value in entry.fields.items():
        if value:
            score += 3 if field_name in {"doi", "url", "abstract", "publisher", "journal", "booktitle", "editor"} else 1
    return score


def _assign_canonical_key(entry: BibEntry, group_key: str, key_owners: dict[str, str]) -> BibEntry:
    base_key = entry.citation_key
    owner = key_owners.get(base_key)
    if owner is None or owner == group_key:
        key_owners[base_key] = group_key
        return entry

    suffix = hashlib.sha1(group_key.encode("utf-8")).hexdigest()[:8]
    candidate = f"{base_key}_{suffix}"
    counter = 2
    while candidate in key_owners and key_owners[candidate] != group_key:
        candidate = f"{base_key}_{suffix}_{counter}"
        counter += 1
    key_owners[candidate] = group_key
    return BibEntry(entry_type=entry.entry_type, citation_key=candidate, fields=dict(entry.fields))


def _is_suspicious_entry_type(entry: BibEntry) -> bool:
    journal = entry.fields.get("journal", "").lower()
    publisher = entry.fields.get("publisher", "").lower()
    howpublished = entry.fields.get("howpublished", "").lower()
    if entry.entry_type == "article" and any(
        token in journal
        for token in ("elsevier", "springer", "press", "publications", "publisher", "university")
    ):
        return True
    if entry.entry_type == "misc" and any(
        token in howpublished
        for token in ("journal", "review", "letters", "proceedings", "conference", "symposium")
    ):
        return True
    if entry.entry_type == "book" and any(
        token in publisher for token in ("journal", "review", "letters", "proceedings", "conference")
    ) and not any(
        token in publisher for token in ("press", "academic", "elsevier", "springer", "wiley", "university")
    ):
        return True
    if entry.entry_type == "incollection" and not entry.fields.get("booktitle"):
        return True
    return False


class _TopicIndexParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.base_prefix = base_url if base_url.endswith("/") else base_url + "/"
        self.topic_links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self._seen_urls: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not href or href.startswith("#"):
            return
        self._current_href = urljoin(self.base_url, href)
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current_href is None:
            return
        topic = WHITESPACE_PATTERN.sub(" ", "".join(self._current_text)).strip()
        href = self._current_href
        self._current_href = None
        self._current_text = []
        if not topic or href in self._seen_urls:
            return
        parsed = urlparse(href)
        base_parsed = urlparse(self.base_prefix)
        if parsed.netloc and base_parsed.netloc and parsed.netloc != base_parsed.netloc:
            return
        if not href.startswith(self.base_prefix):
            return
        if href.rstrip("/").endswith("biblio") or href.endswith("origins.html"):
            return
        self._seen_urls.add(href)
        self.topic_links.append({"topic": topic, "url": href})


class _TopicPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._bibliography_depth = 0
        self._in_pre = False
        self._in_paragraph = False
        self._current_paragraph: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "div" and "bibliography" in (attributes.get("class") or "").split():
            self._bibliography_depth += 1
            return
        if tag == "pre":
            self._in_pre = True
            return
        if self._bibliography_depth and tag == "p":
            self._in_paragraph = True
            self._current_paragraph = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._bibliography_depth:
            self._bibliography_depth -= 1
            return
        if tag == "p" and self._in_paragraph:
            text = "".join(self._current_paragraph).strip()
            if text:
                self._parts.append(text)
                self._parts.append("\n\n")
            self._current_paragraph = []
            self._in_paragraph = False
            return
        if tag == "pre":
            self._in_pre = False
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._bibliography_depth and self._in_paragraph:
            self._current_paragraph.append(data)
        elif self._in_pre:
            self._parts.append(data)

    def preformatted_text(self) -> str:
        return "".join(self._parts)
