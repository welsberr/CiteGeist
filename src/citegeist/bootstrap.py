from __future__ import annotations

from dataclasses import dataclass
import random
import re
import time

from .bibtex import BibEntry, parse_bibtex
from .expand import (
    CrossrefExpander,
    OpenAlexExpander,
    _entry_is_recent,
    _expand_relation_types,
    _meets_topic_assignment_threshold as _expand_meets_topic_assignment_threshold,
    _topic_relevance_score as _expand_topic_relevance_score,
)
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
        self.last_run_meta: dict[str, object] = {}

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
        expansion_mode: str = "legacy",
        expansion_rounds: int = 1,
        recent_years: int | None = None,
        target_recent_entries: int | None = None,
        max_expanded_entries: int | None = None,
        max_expand_seconds: float | None = None,
    ) -> list[BootstrapResult]:
        self.last_run_meta = {
            "stop_reason": "completed",
            "expansion_mode": expansion_mode,
            "preview_only": preview_only,
            "recent_years": recent_years,
            "target_recent_entries": target_recent_entries,
            "max_expanded_entries": max_expanded_entries,
            "max_expand_seconds": max_expand_seconds,
            "recent_hits": 0,
            "recent_topic_hits": 0,
            "expanded_discoveries": 0,
        }
        results: list[BootstrapResult] = []
        seed_keys: list[str] = []
        effective_topic_slug = topic_slug or (_slugify(topic) if topic else None)
        effective_topic_name = topic_name or topic

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
                    if effective_topic_slug and effective_topic_name:
                        store.add_entry_topic(
                            entry.citation_key,
                            topic_slug=effective_topic_slug,
                            topic_name=effective_topic_name,
                            source_type="bootstrap",
                            source_label="seed_bibtex",
                            confidence=1.0,
                            expansion_phrase=topic_phrase or topic,
                        )
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
                    slug=effective_topic_slug or _slugify(topic),
                    name=effective_topic_name or topic,
                    source_type="bootstrap",
                    expansion_phrase=topic_phrase or topic,
                )
            candidate_limit = max(topic_limit, topic_commit_limit or 0)
            ranked_candidates = self._topic_candidates(topic, seed_keys, candidate_limit)
            if not preview_only:
                ranked_candidates = [
                    (entry, score)
                    for entry, score in ranked_candidates
                    if _meets_topic_commit_threshold(entry, topic)
                ]
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
                    if effective_topic_slug and effective_topic_name:
                        store.add_entry_topic(
                            entry.citation_key,
                            topic_slug=effective_topic_slug,
                            topic_name=effective_topic_name,
                            source_type="bootstrap",
                            source_label=f"topic:{topic}",
                            confidence=score,
                            expansion_phrase=topic_phrase or topic,
                        )
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
            expanded_discoveries: set[str] = set()
            deadline = time.monotonic() + max_expand_seconds if max_expand_seconds is not None else None
            if expansion_mode == "legacy":
                random.shuffle(expanded_keys)
                for citation_key in expanded_keys:
                    if _deadline_reached(deadline):
                        store.connection.commit()
                        return results
                    for item in self.crossref_expander.expand_entry_references(store, citation_key):
                        results.append(BootstrapResult(item.discovered_citation_key, "crossref_expand", item.created_entry))
                        expanded_discoveries.add(item.discovered_citation_key)
                        if max_expanded_entries is not None and len(expanded_discoveries) >= max_expanded_entries:
                            self.last_run_meta.update({
                                "stop_reason": "max_expanded_entries",
                                "expanded_discoveries": len(expanded_discoveries),
                            })
                            store.connection.commit()
                            return results
                        if _deadline_reached(deadline):
                            self.last_run_meta.update({
                                "stop_reason": "max_expand_seconds",
                                "expanded_discoveries": len(expanded_discoveries),
                            })
                            store.connection.commit()
                            return results
                    for item in self.openalex_expander.expand_entry(
                        store,
                        citation_key,
                        relation_type="cites",
                        limit=topic_limit,
                    ):
                        results.append(BootstrapResult(item.discovered_citation_key, "openalex_expand", item.created_entry))
                        expanded_discoveries.add(item.discovered_citation_key)
                        if max_expanded_entries is not None and len(expanded_discoveries) >= max_expanded_entries:
                            self.last_run_meta.update({
                                "stop_reason": "max_expanded_entries",
                                "expanded_discoveries": len(expanded_discoveries),
                            })
                            store.connection.commit()
                            return results
                        if _deadline_reached(deadline):
                            self.last_run_meta.update({
                                "stop_reason": "max_expand_seconds",
                                "expanded_discoveries": len(expanded_discoveries),
                            })
                            store.connection.commit()
                            return results
            else:
                results.extend(
                    self._bootstrap_openalex_expansion(
                        store,
                        expanded_keys,
                        relation_type=expansion_mode,
                        limit=topic_limit,
                        max_rounds=expansion_rounds,
                        topic_slug=effective_topic_slug,
                        topic_name=effective_topic_name,
                        topic_phrase=topic_phrase or topic,
                        recent_years=recent_years,
                        target_recent_entries=target_recent_entries,
                        max_expanded_entries=max_expanded_entries,
                        deadline=deadline,
                    )
                )

        self.last_run_meta.setdefault("stop_reason", "completed")
        store.connection.commit()
        return results

    def _bootstrap_openalex_expansion(
        self,
        store: BibliographyStore,
        seed_keys: list[str],
        relation_type: str,
        limit: int,
        max_rounds: int,
        topic_slug: str | None,
        topic_name: str | None,
        topic_phrase: str | None,
        recent_years: int | None,
        target_recent_entries: int | None,
        max_expanded_entries: int | None,
        deadline: float | None,
    ) -> list[BootstrapResult]:
        results: list[BootstrapResult] = []
        frontier = list(dict.fromkeys(seed_keys))
        seen_seeds: set[str] = set()
        recent_hits: set[str] = set()
        recent_topic_hits: set[str] = set()
        expanded_discoveries: set[str] = set()

        for _round in range(max(1, max_rounds)):
            if not frontier:
                break
            if _deadline_reached(deadline):
                self.last_run_meta.update({
                    "stop_reason": "max_expand_seconds",
                    "recent_hits": len(recent_hits),
                    "recent_topic_hits": len(recent_topic_hits),
                    "expanded_discoveries": len(expanded_discoveries),
                })
                return results
            next_frontier: list[str] = []
            for citation_key in frontier:
                if citation_key in seen_seeds:
                    continue
                seen_seeds.add(citation_key)
                if _deadline_reached(deadline):
                    self.last_run_meta.update({
                        "stop_reason": "max_expand_seconds",
                        "recent_hits": len(recent_hits),
                        "recent_topic_hits": len(recent_topic_hits),
                        "expanded_discoveries": len(expanded_discoveries),
                    })
                    return results
                for relation_name in _expand_relation_types(relation_type):
                    if _deadline_reached(deadline):
                        self.last_run_meta.update({
                            "stop_reason": "max_expand_seconds",
                            "recent_hits": len(recent_hits),
                            "recent_topic_hits": len(recent_topic_hits),
                            "expanded_discoveries": len(expanded_discoveries),
                        })
                        return results
                    for item in self.openalex_expander.expand_entry(
                        store,
                        citation_key,
                        relation_type=relation_name,
                        limit=limit,
                    ):
                        discovered_key = item.discovered_citation_key
                        entry = store.get_entry(discovered_key)
                        if _entry_is_recent(entry, recent_years):
                            recent_hits.add(discovered_key)
                        if topic_slug and topic_name and topic_phrase and entry is not None:
                            score = _expand_topic_relevance_score(topic_phrase, entry)
                            if _expand_meets_topic_assignment_threshold(
                                topic_phrase,
                                entry,
                                min_relevance=0.2,
                                relevance_score=score,
                            ):
                                store.add_entry_topic(
                                    discovered_key,
                                    topic_slug=topic_slug,
                                    topic_name=topic_name,
                                    source_type="bootstrap_expand",
                                    source_label=f"openalex:{relation_name}:{citation_key}",
                                    confidence=score,
                                    expansion_phrase=topic_phrase,
                                )
                                if _entry_is_recent(entry, recent_years) and score >= 0.5:
                                    recent_topic_hits.add(discovered_key)
                        results.append(BootstrapResult(discovered_key, f"openalex_expand:{relation_name}", item.created_entry))
                        expanded_discoveries.add(discovered_key)
                        if discovered_key not in seen_seeds:
                            next_frontier.append(discovered_key)
                        if max_expanded_entries is not None and len(expanded_discoveries) >= max_expanded_entries:
                            self.last_run_meta.update({
                                "stop_reason": "max_expanded_entries",
                                "recent_hits": len(recent_hits),
                                "recent_topic_hits": len(recent_topic_hits),
                                "expanded_discoveries": len(expanded_discoveries),
                            })
                            return results
                        if target_recent_entries is not None and len(recent_topic_hits) >= target_recent_entries:
                            self.last_run_meta.update({
                                "stop_reason": "target_recent_entries",
                                "recent_hits": len(recent_hits),
                                "recent_topic_hits": len(recent_topic_hits),
                                "expanded_discoveries": len(expanded_discoveries),
                            })
                            return results
                        if _deadline_reached(deadline):
                            self.last_run_meta.update({
                                "stop_reason": "max_expand_seconds",
                                "recent_hits": len(recent_hits),
                                "recent_topic_hits": len(recent_topic_hits),
                                "expanded_discoveries": len(expanded_discoveries),
                            })
                            return results
            frontier = list(dict.fromkeys(next_frontier))
        self.last_run_meta.update({
            "stop_reason": "frontier_exhausted",
            "recent_hits": len(recent_hits),
            "recent_topic_hits": len(recent_topic_hits),
            "expanded_discoveries": len(expanded_discoveries),
        })
        return results


def _deadline_reached(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline

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


def _core_topic_terms(value: str) -> set[str]:
    generic_terms = {"evolution", "origin", "origins", "science", "study", "studies"}
    return {token for token in _tokenize(value) if token not in generic_terms}


def _meets_topic_commit_threshold(entry: BibEntry, topic: str) -> bool:
    title = entry.fields.get("title", "")
    if not title:
        return False
    normalized_topic = " ".join(topic.casefold().split())
    normalized_title = " ".join(title.casefold().split())
    if normalized_topic and normalized_topic in normalized_title:
        return True

    topic_terms = _core_topic_terms(topic)
    if not topic_terms:
        return False
    title_terms = _tokenize(title)
    overlap = topic_terms & title_terms
    if not overlap:
        return False
    return max(0.25, len(overlap) / len(topic_terms)) >= 0.2


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "topic"
