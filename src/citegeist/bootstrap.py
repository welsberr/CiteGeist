from __future__ import annotations

from dataclasses import dataclass
import re

from .bibtex import BibEntry, parse_bibtex
from .expand import CrossrefExpander, OpenAlexExpander
from .resolve import MetadataResolver
from .storage import BibliographyStore


@dataclass(slots=True)
class BootstrapResult:
    citation_key: str
    origin: str
    created: bool
    score: float = 0.0
    title: str = ""
    author: str = ""
    year: str = ""
    abstract: str = ""


class Bootstrapper:
    def __init__(
        self,
        resolver: MetadataResolver | None = None,
        crossref_expander: CrossrefExpander | None = None,
        openalex_expander: OpenAlexExpander | None = None,
    ) -> None:
        self.resolver = resolver or MetadataResolver()
        self.crossref_expander = crossref_expander or CrossrefExpander(self.resolver)
        self.openalex_expander = openalex_expander or OpenAlexExpander(self.resolver)

    def bootstrap(
        self,
        store: BibliographyStore,
        seed_bibtex: str | None = None,
        topic: str | None = None,
        topic_limit: int = 5,
        topic_commit_limit: int | None = None,
        expand: bool = True,
        review_status: str = "draft",
        preview_only: bool = False,
        topic_slug: str | None = None,
        topic_name: str | None = None,
        topic_phrase: str | None = None,
    ) -> list[BootstrapResult]:
        results: list[BootstrapResult] = []
        seed_keys: list[str] = []

        if seed_bibtex:
            for entry in parse_bibtex(seed_bibtex):
                created = store.get_entry(entry.citation_key) is None
                if not preview_only:
                    store.upsert_entry(
                        entry,
                        raw_bibtex=None,
                        source_type="bootstrap",
                        source_label="seed_bibtex",
                        review_status=review_status,
                    )
                    seed_keys.append(entry.citation_key)
                results.append(
                    BootstrapResult(
                        entry.citation_key,
                        "seed_bibtex",
                        created,
                        title=entry.fields.get("title", ""),
                        author=entry.fields.get("author", ""),
                        year=entry.fields.get("year", ""),
                        abstract=entry.fields.get("abstract", ""),
                    )
                )

        if topic:
            if not preview_only and (topic_slug or topic_name or topic_phrase):
                store.ensure_topic(
                    slug=topic_slug or _slugify(topic),
                    name=topic_name or topic,
                    source_type="bootstrap",
                    expansion_phrase=topic_phrase or topic,
                )
            candidate_limit = max(topic_limit, topic_commit_limit or 0)
            ranked_candidates = self._topic_candidates(topic, seed_keys, candidate_limit)
            if topic_commit_limit is not None:
                ranked_candidates = ranked_candidates[:topic_commit_limit]

            for entry, score in ranked_candidates:
                created = store.get_entry(entry.citation_key) is None
                if not preview_only:
                    store.upsert_entry(
                        entry,
                        raw_bibtex=None,
                        source_type="bootstrap",
                        source_label=f"topic:{topic}",
                        review_status=review_status,
                    )
                    seed_keys.append(entry.citation_key)
                results.append(
                    BootstrapResult(
                        entry.citation_key,
                        "topic",
                        created,
                        score=score,
                        title=entry.fields.get("title", ""),
                        author=entry.fields.get("author", ""),
                        year=entry.fields.get("year", ""),
                        abstract=entry.fields.get("abstract", ""),
                    )
                )

        if expand and not preview_only:
            expanded_keys = list(dict.fromkeys(seed_keys))
            for citation_key in expanded_keys:
                for item in self.crossref_expander.expand_entry_references(store, citation_key):
                    results.append(BootstrapResult(item.discovered_citation_key, "crossref_expand", item.created_entry))
                for item in self.openalex_expander.expand_entry(store, citation_key, relation_type="cites", limit=topic_limit):
                    results.append(BootstrapResult(item.discovered_citation_key, "openalex_expand", item.created_entry))

        store.connection.commit()
        return results

    def _topic_candidates(self, topic: str, seed_keys: list[str], limit: int) -> list[tuple[BibEntry, float]]:
        scored: dict[str, tuple[BibEntry, float]] = {}

        for source_name, base_score, entries in (
            ("openalex", 3.0, self.resolver.search_openalex(topic, limit=limit)),
            ("crossref", 2.0, self.resolver.search_crossref(topic, limit=limit)),
            ("datacite", 1.5, self.resolver.search_datacite(topic, limit=limit)),
        ):
            for entry in entries:
                score = base_score + _topic_relevance_score(entry, topic) + _seed_overlap_score(entry, seed_keys)
                existing = scored.get(entry.citation_key)
                if existing is None or score > existing[1]:
                    scored[entry.citation_key] = (entry, score)

        ranked = sorted(
            scored.values(),
            key=lambda item: (-item[1], item[0].citation_key),
        )
        return ranked[:limit]


def _topic_relevance_score(entry: BibEntry, topic: str) -> float:
    topic_terms = _tokenize(topic)
    title_terms = _tokenize(entry.fields.get("title", ""))
    abstract_terms = _tokenize(entry.fields.get("abstract", ""))
    overlap = len(topic_terms & (title_terms | abstract_terms))
    return float(overlap)


def _seed_overlap_score(entry: BibEntry, seed_keys: list[str]) -> float:
    if not seed_keys:
        return 0.0
    title_terms = _tokenize(entry.fields.get("title", ""))
    score = 0.0
    for seed_key in seed_keys:
        seed_terms = _tokenize(seed_key)
        if seed_terms & title_terms:
            score += 0.25
    return score


def _tokenize(value: str) -> set[str]:
    return {token for token in re.split(r"\W+", value.lower()) if token}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "topic"
