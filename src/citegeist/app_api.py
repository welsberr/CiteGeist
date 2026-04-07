from __future__ import annotations

from dataclasses import asdict

from .bibtex import BibEntry, parse_bibtex, render_bibtex
from .bootstrap import Bootstrapper
from .expand import TopicExpander
from .extract import extract_references
from .storage import BibliographyStore
from .verify import BibliographyVerifier

METADATA_SOURCES = ["crossref", "datacite", "openalex", "pubmed"]
GRAPH_EXPANSION_SOURCES = ["crossref", "openalex"]
GRAPH_RELATION_TYPES = ["cites", "cited_by", "both"]


class LiteratureExplorerApi:
    """JSON-serializable adapter layer for browser or local UI bridges."""

    def __init__(
        self,
        store: BibliographyStore,
        *,
        bootstrapper: Bootstrapper | None = None,
        topic_expander: TopicExpander | None = None,
        verifier: BibliographyVerifier | None = None,
    ) -> None:
        self.store = store
        self.bootstrapper = bootstrapper or Bootstrapper()
        self.topic_expander = topic_expander or TopicExpander()
        self.verifier = verifier or BibliographyVerifier()

    def capabilities(self) -> dict[str, object]:
        return {
            "operations": [
                "search",
                "show_entry",
                "list_topics",
                "get_topic",
                "export_topic_bibtex",
                "bootstrap",
                "expand_topic",
                "extract_text",
                "verify_strings",
                "graph",
            ],
            "preview_operations": ["bootstrap", "expand_topic"],
            "metadata_sources": list(METADATA_SOURCES),
            "topic_seed_sources": list(METADATA_SOURCES),
            "graph_expansion_sources": list(GRAPH_EXPANSION_SOURCES),
            "topic_expansion_sources": list(GRAPH_EXPANSION_SOURCES),
            "graph_relation_types": list(GRAPH_RELATION_TYPES),
        }

    def search(self, query: str, *, limit: int = 20, topic_slug: str | None = None) -> dict[str, object]:
        return {
            "query": query,
            "topic_slug": topic_slug,
            "results": self.store.search_text(query, limit=limit, topic_slug=topic_slug),
        }

    def show_entry(
        self,
        citation_key: str,
        *,
        include_provenance: bool = False,
        include_conflicts: bool = False,
        include_bibtex: bool = False,
    ) -> dict[str, object] | None:
        entry = self.store.get_entry(citation_key)
        if entry is None:
            return None
        payload = dict(entry)
        if include_provenance:
            payload["provenance"] = self.store.get_field_provenance(citation_key)
        if include_conflicts:
            payload["conflicts"] = self.store.get_conflicts(citation_key)
        if include_bibtex:
            payload["bibtex"] = self.store.get_entry_bibtex(citation_key)
        return payload

    def list_topics(self, *, limit: int = 100, phrase_review_status: str | None = None) -> dict[str, object]:
        return {"topics": self.store.list_topics(limit=limit, phrase_review_status=phrase_review_status)}

    def get_topic(self, topic_slug: str, *, entry_limit: int = 100) -> dict[str, object] | None:
        topic = self.store.get_topic(topic_slug)
        if topic is None:
            return None
        return {
            "topic": topic,
            "entries": self.store.list_topic_entries(topic_slug, limit=entry_limit),
        }

    def export_topic_bibtex(self, topic_slug: str, *, include_stubs: bool = False) -> dict[str, object] | None:
        topic = self.store.get_topic(topic_slug)
        if topic is None:
            return None
        entries = self.store.list_topic_entries(topic_slug, limit=100000)
        citation_keys = [row["citation_key"] for row in entries]
        export = self.store.export_bibtex_report(citation_keys, include_stubs=include_stubs)
        return {
            "topic": topic,
            "entry_count": len(citation_keys),
            "exported_count": export["exported_count"],
            "include_stubs": include_stubs,
            "skipped": export["skipped"],
            "bibtex": export["bibtex"],
        }

    def bootstrap(
        self,
        *,
        seed_bibtex: str | None = None,
        topic: str | None = None,
        topic_slug: str | None = None,
        topic_name: str | None = None,
        topic_phrase: str | None = None,
        topic_limit: int = 5,
        topic_commit_limit: int | None = None,
        expand: bool = True,
        preview_only: bool = False,
        review_status: str = "draft",
        expansion_mode: str = "legacy",
        expansion_rounds: int = 1,
        recent_years: int | None = None,
        target_recent_entries: int | None = None,
        max_expanded_entries: int | None = None,
        max_expand_seconds: float | None = None,
    ) -> dict[str, object]:
        results = self.bootstrapper.bootstrap(
            self.store,
            seed_bibtex=seed_bibtex,
            topic=topic,
            topic_limit=topic_limit,
            topic_commit_limit=topic_commit_limit,
            expand=expand,
            review_status=review_status,
            preview_only=preview_only,
            topic_slug=topic_slug,
            topic_name=topic_name,
            topic_phrase=topic_phrase,
            expansion_mode=expansion_mode,
            expansion_rounds=expansion_rounds,
            recent_years=recent_years,
            target_recent_entries=target_recent_entries,
            max_expanded_entries=max_expanded_entries,
            max_expand_seconds=max_expand_seconds,
        )
        effective_slug = topic_slug
        if effective_slug is None and topic:
            effective_slug = _slugify(topic)
        payload: dict[str, object] = {
            "preview": preview_only,
            "results": [asdict(result) for result in results],
            "run_meta": dict(getattr(self.bootstrapper, "last_run_meta", {}) or {}),
        }
        if effective_slug is not None:
            payload["topic"] = self.store.get_topic(effective_slug)
            payload["entries"] = self.store.list_topic_entries(effective_slug, limit=200)
        return payload

    def expand_topic(
        self,
        topic_slug: str,
        *,
        topic_phrase: str | None = None,
        source: str = "openalex",
        relation_type: str = "cites",
        seed_limit: int = 25,
        per_seed_limit: int = 25,
        min_relevance: float = 0.2,
        seed_keys: list[str] | None = None,
        preview_only: bool = False,
        max_rounds: int = 1,
        recent_years: int | None = None,
        target_recent_entries: int | None = None,
    ) -> dict[str, object] | None:
        topic = self.store.get_topic(topic_slug)
        if topic is None:
            return None
        results = self.topic_expander.expand_topic(
            self.store,
            topic_slug,
            topic_phrase=topic_phrase,
            source=source,
            relation_type=relation_type,
            seed_limit=seed_limit,
            per_seed_limit=per_seed_limit,
            min_relevance=min_relevance,
            seed_keys=seed_keys,
            preview_only=preview_only,
            max_rounds=max_rounds,
            recent_years=recent_years,
            target_recent_entries=target_recent_entries,
        )
        return {
            "topic": self.store.get_topic(topic_slug),
            "preview": preview_only,
            "results": [asdict(result) for result in results],
            "entries": self.store.list_topic_entries(topic_slug, limit=200),
            "run_meta": dict(getattr(self.topic_expander, "last_run_meta", {}) or {}),
        }

    def extract_text(self, text: str, *, backend: str = "heuristic") -> dict[str, object]:
        entries = extract_references(text, backend=backend)
        return {
            "backend": backend,
            "entries": [_entry_payload(entry) for entry in entries],
            "bibtex": render_bibtex(entries),
        }

    def verify_strings(self, values: list[str], *, context: str = "", limit: int = 5) -> dict[str, object]:
        results = self.verifier.verify_strings(values, context=context, limit=limit)
        return {
            "context": context,
            "results": [_verification_payload(result) for result in results],
        }

    def verify_bibtex(self, bibtex_text: str, *, context: str = "", limit: int = 5) -> dict[str, object]:
        entries = parse_bibtex(bibtex_text)
        results = [self.verifier.verify_bib_entry(entry, context=context, limit=limit) for entry in entries]
        return {
            "context": context,
            "results": [_verification_payload(result) for result in results],
        }

    def graph(
        self,
        seed_keys: list[str],
        *,
        relation_types: list[str] | None = None,
        depth: int = 1,
        review_status: str | None = None,
        missing_only: bool = False,
    ) -> dict[str, object]:
        rows = self.store.traverse_graph(
            seed_keys,
            relation_types=relation_types or ["cites"],
            max_depth=depth,
            review_status=review_status,
            include_missing=True,
        )
        if missing_only:
            rows = [row for row in rows if not row["target_exists"]]
        return _graph_payload(self.store, seed_keys, rows)


def _entry_payload(entry: BibEntry) -> dict[str, object]:
    return {
        "citation_key": entry.citation_key,
        "entry_type": entry.entry_type,
        "fields": dict(entry.fields),
    }


def _verification_payload(result: object) -> dict[str, object]:
    payload = asdict(result)
    payload["entry"] = _entry_payload(result.entry)  # type: ignore[attr-defined]
    payload["alternates"] = [
        {
            **asdict(match),
            "entry": _entry_payload(match.entry),
        }
        for match in result.alternates  # type: ignore[attr-defined]
    ]
    return payload


def _graph_payload(store: BibliographyStore, seed_keys: list[str], rows: list[dict[str, object]]) -> dict[str, object]:
    nodes: dict[str, dict[str, object]] = {}

    def ensure_node(citation_key: str, *, fallback_title: str | None = None, target_exists: bool = True) -> None:
        if citation_key in nodes:
            return
        entry = store.get_entry(citation_key)
        nodes[citation_key] = {
            "id": citation_key,
            "label": citation_key,
            "title": (entry or {}).get("title") or fallback_title,
            "review_status": (entry or {}).get("review_status"),
            "target_exists": entry is not None if entry is not None else target_exists,
            "is_seed": citation_key in seed_keys,
        }

    for seed_key in seed_keys:
        ensure_node(seed_key)

    edges = []
    for index, row in enumerate(rows, start=1):
        source_key = str(row["source_citation_key"])
        target_key = str(row["target_citation_key"])
        ensure_node(source_key)
        ensure_node(
            target_key,
            fallback_title=str(row.get("target_title") or "") or None,
            target_exists=bool(row.get("target_exists")),
        )
        edges.append(
            {
                "id": f"edge-{index}",
                "source": source_key,
                "target": target_key,
                "relation_type": str(row["relation_type"]),
                "depth": int(row["depth"]),
                "target_exists": bool(row["target_exists"]),
            }
        )

    return {
        "nodes": sorted(nodes.values(), key=lambda item: str(item["id"])),
        "edges": edges,
    }


def _slugify(value: str) -> str:
    return "-".join(part for part in "".join(ch.lower() if ch.isalnum() else "-" for ch in value).split("-") if part) or "topic"
