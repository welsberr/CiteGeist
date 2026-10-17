"""Read-only, question-led discovery over CiteGeist's existing text search APIs.

This module records which adapters returned, failed, or could not run. A
successful adapter call is not evidence that its index is complete, and the
resolver's legacy safe-search methods can turn some transport errors into an
empty result without exposing the underlying error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from .bibtex import BibEntry
from .resolver.identifiers import entry_identifiers
from .resolve import MetadataResolver
from .storage import BibliographyStore


DISCOVERY_SOURCES = (
    "local",
    "openalex",
    "pubmed",
    "crossref",
    "datacite",
    "europepmc",
    "semanticscholar",
    "dblp",
    "openlibrary",
)

SourceStatusValue = Literal["returned", "error", "unavailable", "unknown"]
DiscoveryOutcome = Literal["complete", "partial", "empty_corpus", "no_matches", "provider_failure", "inconclusive"]


@dataclass(frozen=True, slots=True)
class ResearchBrief:
    """Validated input contract for a bounded discovery request."""

    query: str
    # External searches are opt-in: constructing a brief must not silently
    # trigger network requests.
    sources: tuple[str, ...] = ("local",)
    per_source_limit: int = 10
    topic_slug: str | None = None

    def __post_init__(self) -> None:
        query = " ".join(str(self.query or "").split())
        if not query:
            raise ValueError("ResearchBrief query must contain non-whitespace text")
        if len(query) > 1000:
            raise ValueError("ResearchBrief query must be at most 1000 characters")
        object.__setattr__(self, "query", query)

        sources = tuple(dict.fromkeys(str(source).strip().casefold() for source in self.sources))
        if not sources:
            raise ValueError("ResearchBrief must select at least one source")
        unsupported = [source for source in sources if source not in DISCOVERY_SOURCES]
        if unsupported:
            raise ValueError(f"Unsupported discovery source(s): {', '.join(unsupported)}")
        object.__setattr__(self, "sources", sources)

        if isinstance(self.per_source_limit, bool) or not 1 <= self.per_source_limit <= 100:
            raise ValueError("ResearchBrief per_source_limit must be between 1 and 100")
        topic_slug = " ".join(str(self.topic_slug or "").split()) or None
        object.__setattr__(self, "topic_slug", topic_slug)


@dataclass(slots=True)
class DiscoverySourceStatus:
    provider: str
    status: SourceStatusValue
    result_count: int = 0
    error: str = ""


@dataclass(slots=True)
class DiscoveryResult:
    """A candidate and the adapters that returned it; not a verified citation."""

    entry: BibEntry
    providers: list[str] = field(default_factory=list)
    provider_ranks: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class DiscoveryReport:
    brief: ResearchBrief
    results: list[DiscoveryResult]
    sources: list[DiscoverySourceStatus]
    outcome: DiscoveryOutcome
    generated_at: str


def discover_references(
    brief: ResearchBrief,
    *,
    store: BibliographyStore | None = None,
    resolver: MetadataResolver | None = None,
) -> DiscoveryReport:
    """Search selected existing adapters and return candidates without storing them."""
    resolver = resolver or MetadataResolver()
    outcomes: list[DiscoverySourceStatus] = []
    merged: dict[str, DiscoveryResult] = {}

    for provider in brief.sources:
        if provider == "local":
            if store is None:
                outcomes.append(DiscoverySourceStatus(provider, "unavailable", error="No local bibliography store was supplied"))
                continue
            try:
                rows = store.search_text(brief.query, limit=brief.per_source_limit, topic_slug=brief.topic_slug)
                entries = []
                for row in rows:
                    citation_key = str(row.get("citation_key", ""))
                    payload = store.get_entry(citation_key) if citation_key else None
                    if payload is None:
                        continue
                    fields = {
                        key: str(value)
                        for key, value in payload.items()
                        if key not in {"id", "citation_key", "entry_type", "review_status", "topics", "extra_fields_json"}
                        and value is not None
                        and str(value)
                    }
                    entries.append(BibEntry(
                        entry_type=str(payload.get("entry_type") or "misc"),
                        citation_key=citation_key,
                        fields=fields,
                    ))
                _record_results(merged, provider, entries)
                outcomes.append(DiscoverySourceStatus(provider, "returned", result_count=len(entries)))
            except Exception as exc:
                outcomes.append(DiscoverySourceStatus(provider, "error", error=f"{type(exc).__name__}: {exc}"))
            continue

        method_name = f"search_{provider}"
        method = getattr(resolver, method_name, None)
        if not callable(method):
            outcomes.append(DiscoverySourceStatus(provider, "unavailable", error=f"Resolver has no {method_name} method"))
            continue
        try:
            entries = method(brief.query, limit=brief.per_source_limit)
            _record_results(merged, provider, entries)
            if entries:
                outcomes.append(DiscoverySourceStatus(provider, "returned", result_count=len(entries)))
            else:
                outcomes.append(DiscoverySourceStatus(
                    provider,
                    "unknown",
                    error="Resolver returned no results; legacy search may hide transport failures.",
                ))
        except Exception as exc:
            outcomes.append(DiscoverySourceStatus(provider, "error", error=f"{type(exc).__name__}: {exc}"))

    failures = [item for item in outcomes if item.status in {"error", "unavailable"}]
    unknowns = [item for item in outcomes if item.status == "unknown"]
    if merged:
        outcome: DiscoveryOutcome = "partial" if failures or unknowns else "complete"
    elif failures:
        outcome = "provider_failure"
    elif unknowns:
        outcome = "inconclusive"
    elif store is not None and "local" in brief.sources and int(store.database_summary()["entries"]) == 0:
        outcome = "empty_corpus"
    else:
        outcome = "no_matches"

    return DiscoveryReport(
        brief=brief,
        results=list(merged.values()),
        sources=outcomes,
        outcome=outcome,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _record_results(
    merged: dict[str, DiscoveryResult],
    provider: str,
    entries: list[BibEntry],
) -> None:
    for rank, entry in enumerate(entries, start=1):
        key = entry.citation_key.strip()
        if not key:
            continue
        fields = entry.fields
        doi, arxiv = entry_identifiers(fields)
        stable_id = next((
            (scheme, str(fields.get(field) or "").strip().casefold())
            for scheme, field in (
                ("openalex", "openalex"), ("openalex", "openalex_id"),
                ("pmid", "pmid"), ("isbn", "isbn"),
            )
            if str(fields.get(field) or "").strip()
        ), None)
        if arxiv:
            stable_id = ("arxiv", arxiv.casefold())
        # Citation keys are not globally stable identifiers. Merge across
        # providers only on an explicit shared identifier; otherwise retain
        # provenance-qualified candidates for human review.
        identity = f"doi:{doi.casefold()}" if doi else (
            f"{stable_id[0]}:{stable_id[1]}" if stable_id else f"{provider}:{key}"
        )
        result = merged.get(identity)
        if result is None:
            result = DiscoveryResult(entry=entry)
            merged[identity] = result
        if provider not in result.providers:
            result.providers.append(provider)
        result.provider_ranks[provider] = rank
