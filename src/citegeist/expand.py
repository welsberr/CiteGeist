from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from .bibtex import BibEntry, parse_bibtex
from .resolve import MetadataResolver, merge_entries
from .storage import BibliographyStore


@dataclass(slots=True)
class ExpansionResult:
    source_citation_key: str
    discovered_citation_key: str
    created_entry: bool
    relation_type: str
    source_label: str


@dataclass(slots=True)
class TopicExpansionResult:
    topic_slug: str
    source_citation_key: str
    discovered_citation_key: str
    discovered_title: str
    created_entry: bool
    relation_type: str
    source_label: str
    relevance_score: float
    meets_relevance_threshold: bool
    assigned_to_topic: bool


class CrossrefExpander:
    def __init__(self, resolver: MetadataResolver | None = None) -> None:
        self.resolver = resolver or MetadataResolver()

    def expand_entry_references(
        self,
        store: BibliographyStore,
        citation_key: str,
    ) -> list[ExpansionResult]:
        entry = store.get_entry(citation_key)
        if entry is None:
            return []

        doi = entry.get("doi")
        if not doi:
            return []

        payload = self.resolver.source_client.get_json(
            f"https://api.crossref.org/works/{doi}?mailto=welsberr@gmail.com"
        )
        references = payload.get("message", {}).get("reference", [])
        results: list[ExpansionResult] = []
        for index, reference in enumerate(references, start=1):
            discovered = self._reference_to_entry(reference, citation_key, index)
            created = False
            if store.get_entry(discovered.citation_key) is None:
                store.upsert_entry(
                    discovered,
                    raw_bibtex=None,
                    source_type="graph_expand",
                    source_label=f"crossref:references:{doi}",
                    review_status="draft",
                )
                store.connection.commit()
                created = True

            store.add_relation(
                citation_key,
                discovered.citation_key,
                "cites",
                source_type="graph_expand",
                source_label=f"crossref:references:{doi}",
                confidence=1.0 if reference.get("DOI") else 0.6,
            )
            results.append(
                ExpansionResult(
                    source_citation_key=citation_key,
                    discovered_citation_key=discovered.citation_key,
                    created_entry=created,
                    relation_type="cites",
                    source_label=f"crossref:references:{doi}",
                )
            )
        return results

    def _reference_to_entry(self, reference: dict, source_citation_key: str, ordinal: int) -> BibEntry:
        fallback = _crossref_reference_to_entry(reference, source_citation_key, ordinal)
        doi = reference.get("DOI") or ""
        if not doi:
            return fallback

        resolution = self.resolver.resolve_doi(doi)
        if resolution is None:
            resolution = self.resolver.resolve_datacite_doi(doi)
        if resolution is None:
            return fallback

        merged = merge_entries(resolution.entry, fallback)
        merged.fields["note"] = fallback.fields["note"]
        return BibEntry(
            entry_type=resolution.entry.entry_type or merged.entry_type,
            citation_key=fallback.citation_key,
            fields=merged.fields,
        )


class OpenAlexExpander:
    def __init__(self, resolver: MetadataResolver | None = None) -> None:
        self.resolver = resolver or MetadataResolver()

    def expand_entry(
        self,
        store: BibliographyStore,
        citation_key: str,
        relation_type: str = "cites",
        limit: int = 25,
    ) -> list[ExpansionResult]:
        entry = store.get_entry(citation_key)
        if entry is None:
            return []

        openalex_id = entry.get("openalex") or self._lookup_openalex_id(entry)
        if not openalex_id:
            return []
        if not entry.get("openalex"):
            bibtex = store.get_entry_bibtex(citation_key)
            if bibtex:
                seed_entry = parse_bibtex(bibtex)[0]
                seed_entry.fields["openalex"] = openalex_id
                store.replace_entry(
                    citation_key,
                    seed_entry,
                    source_type="resolver",
                    source_label=f"openalex:id:{openalex_id}",
                    review_status=str(entry.get("review_status") or "draft"),
                )

        filter_name = "cited_by" if relation_type == "cites" else "cites"
        query = urlencode({"filter": f"{filter_name}:{openalex_id}", "per-page": limit})
        payload = self.resolver.source_client.get_json(f"https://api.openalex.org/works?{query}")
        works = payload.get("results", [])

        results: list[ExpansionResult] = []
        for work in works:
            discovered = _openalex_work_to_entry(work)
            created = False
            if store.get_entry(discovered.citation_key) is None:
                store.upsert_entry(
                    discovered,
                    raw_bibtex=None,
                    source_type="graph_expand",
                    source_label=f"openalex:{relation_type}:{openalex_id}",
                    review_status="draft",
                )
                store.connection.commit()
                created = True

            if relation_type == "cites":
                source_key = citation_key
                target_key = discovered.citation_key
            else:
                source_key = discovered.citation_key
                target_key = citation_key

            store.add_relation(
                source_key,
                target_key,
                "cites",
                source_type="graph_expand",
                source_label=f"openalex:{relation_type}:{openalex_id}",
                confidence=0.9,
            )
            results.append(
                ExpansionResult(
                    source_citation_key=source_key,
                    discovered_citation_key=discovered.citation_key,
                    created_entry=created,
                    relation_type=relation_type,
                    source_label=f"openalex:{relation_type}:{openalex_id}",
                )
            )
        return results

    def _lookup_openalex_id(self, entry: dict[str, object]) -> str | None:
        doi = entry.get("doi")
        if not doi:
            return None
        query = urlencode({"filter": f"doi:https://doi.org/{doi}"})
        payload = self.resolver.source_client.get_json(f"https://api.openalex.org/works?{query}")
        results = payload.get("results", [])
        if not results:
            return None
        return _normalize_openalex_id(results[0].get("id", ""))


class TopicExpander:
    def __init__(
        self,
        crossref_expander: CrossrefExpander | None = None,
        openalex_expander: OpenAlexExpander | None = None,
    ) -> None:
        self.crossref_expander = crossref_expander or CrossrefExpander()
        self.openalex_expander = openalex_expander or OpenAlexExpander()

    def expand_topic(
        self,
        store: BibliographyStore,
        topic_slug: str,
        topic_phrase: str | None = None,
        source: str = "openalex",
        relation_type: str = "cites",
        seed_limit: int = 25,
        per_seed_limit: int = 25,
        min_relevance: float = 0.2,
        seed_keys: list[str] | None = None,
        preview_only: bool = False,
    ) -> list[TopicExpansionResult]:
        topic = store.get_topic(topic_slug)
        if topic is None:
            return []

        phrase = (topic_phrase or str(topic.get("name") or topic_slug)).strip()
        seeds = store.list_topic_entries(topic_slug, limit=seed_limit)
        if seed_keys:
            allowed = set(seed_keys)
            seeds = [seed for seed in seeds if str(seed["citation_key"]) in allowed]
        results: list[TopicExpansionResult] = []

        for seed in seeds:
            seed_key = str(seed["citation_key"])
            if preview_only:
                discovered_rows = self._preview_discoveries(
                    store,
                    seed_key,
                    source=source,
                    relation_type=relation_type,
                    limit=per_seed_limit,
                )
            else:
                discovered_rows = self._materialized_discoveries(
                    store,
                    seed_key,
                    source=source,
                    relation_type=relation_type,
                    limit=per_seed_limit,
                )

            for row, target_entry in discovered_rows:
                score = _topic_relevance_score(phrase, target_entry)
                meets_threshold = _meets_topic_assignment_threshold(
                    phrase,
                    target_entry,
                    min_relevance=min_relevance,
                    relevance_score=score,
                )
                assigned = False
                if not preview_only and meets_threshold and target_entry is not None:
                    assigned = store.add_entry_topic(
                        row.discovered_citation_key,
                        topic_slug=topic_slug,
                        topic_name=str(topic.get("name") or topic_slug),
                        source_type="topic_expand",
                        source_url=str(topic.get("source_url") or ""),
                        source_label=f"{source}:{relation_type}:{seed_key}",
                        confidence=score,
                    )
                results.append(
                    TopicExpansionResult(
                        topic_slug=topic_slug,
                        source_citation_key=row.source_citation_key,
                        discovered_citation_key=row.discovered_citation_key,
                        discovered_title=str(target_entry.get("title") or ""),
                        created_entry=row.created_entry,
                        relation_type=row.relation_type,
                        source_label=row.source_label,
                        relevance_score=score,
                        meets_relevance_threshold=meets_threshold,
                        assigned_to_topic=assigned,
                    )
                )
        store.connection.commit()
        return results

    def _materialized_discoveries(
        self,
        store: BibliographyStore,
        citation_key: str,
        source: str,
        relation_type: str,
        limit: int,
    ) -> list[tuple[ExpansionResult, dict[str, object] | None]]:
        if source == "crossref":
            expansion_rows = self.crossref_expander.expand_entry_references(store, citation_key)
        else:
            expansion_rows = self.openalex_expander.expand_entry(
                store,
                citation_key,
                relation_type=relation_type,
                limit=limit,
            )
        return [(row, store.get_entry(row.discovered_citation_key)) for row in expansion_rows]

    def _preview_discoveries(
        self,
        store: BibliographyStore,
        citation_key: str,
        source: str,
        relation_type: str,
        limit: int,
    ) -> list[tuple[ExpansionResult, dict[str, object]]]:
        if source == "crossref":
            return self._preview_crossref_discoveries(store, citation_key, limit)
        return self._preview_openalex_discoveries(store, citation_key, relation_type, limit)

    def _preview_crossref_discoveries(
        self,
        store: BibliographyStore,
        citation_key: str,
        limit: int,
    ) -> list[tuple[ExpansionResult, dict[str, object]]]:
        entry = store.get_entry(citation_key)
        if entry is None or not entry.get("doi"):
            return []
        doi = str(entry["doi"])
        payload = self.crossref_expander.resolver.source_client.get_json(
            f"https://api.crossref.org/works/{doi}?mailto=welsberr@gmail.com"
        )
        references = payload.get("message", {}).get("reference", [])[:limit]
        rows: list[tuple[ExpansionResult, dict[str, object]]] = []
        for index, reference in enumerate(references, start=1):
            discovered = self.crossref_expander._reference_to_entry(reference, citation_key, index)
            rows.append(
                (
                    ExpansionResult(
                        source_citation_key=citation_key,
                        discovered_citation_key=discovered.citation_key,
                        created_entry=store.get_entry(discovered.citation_key) is None,
                        relation_type="cites",
                        source_label=f"crossref:references:{doi}",
                    ),
                    dict(discovered.fields),
                )
            )
        return rows

    def _preview_openalex_discoveries(
        self,
        store: BibliographyStore,
        citation_key: str,
        relation_type: str,
        limit: int,
    ) -> list[tuple[ExpansionResult, dict[str, object]]]:
        entry = store.get_entry(citation_key)
        if entry is None:
            return []
        openalex_id = entry.get("openalex") or self.openalex_expander._lookup_openalex_id(entry)
        if not openalex_id:
            return []
        filter_name = "cited_by" if relation_type == "cites" else "cites"
        query = urlencode({"filter": f"{filter_name}:{openalex_id}", "per-page": limit})
        payload = self.openalex_expander.resolver.source_client.get_json(f"https://api.openalex.org/works?{query}")
        works = payload.get("results", [])
        rows: list[tuple[ExpansionResult, dict[str, object]]] = []
        for work in works:
            discovered = _openalex_work_to_entry(work)
            source_key = citation_key if relation_type == "cites" else discovered.citation_key
            rows.append(
                (
                    ExpansionResult(
                        source_citation_key=source_key,
                        discovered_citation_key=discovered.citation_key,
                        created_entry=store.get_entry(discovered.citation_key) is None,
                        relation_type=relation_type,
                        source_label=f"openalex:{relation_type}:{openalex_id}",
                    ),
                    dict(discovered.fields),
                )
            )
        return rows


def _crossref_reference_to_entry(reference: dict, source_citation_key: str, ordinal: int) -> BibEntry:
    title = (
        reference.get("article-title")
        or reference.get("volume-title")
        or reference.get("journal-title")
        or reference.get("unstructured")
        or f"Referenced work {ordinal}"
    )
    year = str(reference.get("year") or "")
    author = reference.get("author") or ""
    doi = reference.get("DOI") or ""
    journal_title = reference.get("journal-title") or ""

    fields: dict[str, str] = {
        "title": _normalize_text(title),
        "note": f"discovered_from = {{{source_citation_key}}}",
    }
    if year:
        fields["year"] = year
    if author:
        fields["author"] = _normalize_text(author)
    if doi:
        fields["doi"] = doi
        fields["url"] = f"https://doi.org/{doi}"
    if journal_title:
        fields["journal"] = _normalize_text(journal_title)

    citation_key = _reference_citation_key(reference, title, year, ordinal)
    entry_type = _crossref_reference_entry_type(reference, title, journal_title)
    return BibEntry(entry_type=entry_type, citation_key=citation_key, fields=fields)


def _reference_citation_key(reference: dict, title: str, year: str, ordinal: int) -> str:
    if doi := reference.get("DOI"):
        suffix = re.sub(r"[^A-Za-z0-9]+", "", doi).lower()
        return f"doi{suffix}"

    author = reference.get("author") or "ref"
    family = author.split(",")[0].split()[-1]
    family = re.sub(r"[^A-Za-z0-9]+", "", family).lower() or "ref"
    first_word = re.sub(r"[^A-Za-z0-9]+", "", title.split()[0]).lower() if title.split() else "untitled"
    return f"{family}{year or 'nd'}{first_word}{ordinal}"


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _crossref_reference_entry_type(reference: dict, title: str, journal_title: str) -> str:
    if journal_title:
        return "article"
    combined = " ".join(
        str(reference.get(field) or "")
        for field in ("article-title", "volume-title", "journal-title", "series-title", "unstructured")
    ).casefold()
    if any(token in combined for token in ("conference", "proceedings", "symposium", "workshop")):
        return "inproceedings"
    if any(token in combined for token in ("thesis", "dissertation")):
        return "phdthesis"
    if reference.get("volume-title"):
        return "incollection"
    if any(token in combined for token in ("press", "publisher", "edition")):
        return "book"
    return "misc"


def _topic_relevance_score(topic_phrase: str, entry: dict[str, object] | None) -> float:
    if entry is None:
        return 0.0
    topic_terms = _expanded_keyword_terms(topic_phrase)
    if not topic_terms:
        return 0.0
    title_terms = _expanded_keyword_terms(str(entry.get("title") or ""))
    abstract_terms = _expanded_keyword_terms(str(entry.get("abstract") or ""))
    keyword_terms = _expanded_keyword_terms(str(entry.get("keywords") or ""))
    venue_terms = _expanded_keyword_terms(" ".join(str(entry.get(field) or "") for field in ("journal", "booktitle")))

    score = 0.0
    score += 0.6 * _term_overlap_ratio(topic_terms, title_terms)
    score += 0.25 * _term_overlap_ratio(topic_terms, abstract_terms)
    score += 0.1 * _term_overlap_ratio(topic_terms, keyword_terms)
    score += 0.05 * _term_overlap_ratio(topic_terms, venue_terms)

    phrase = _normalize_text(topic_phrase.casefold())
    title = _normalize_text(str(entry.get("title") or "").casefold())
    if phrase and title and phrase in title:
        score = max(score, 0.75)

    return min(score, 1.0)


def _meets_topic_assignment_threshold(
    topic_phrase: str,
    entry: dict[str, object] | None,
    min_relevance: float,
    relevance_score: float | None = None,
) -> bool:
    if entry is None:
        return False
    score = relevance_score if relevance_score is not None else _topic_relevance_score(topic_phrase, entry)
    if score < min_relevance:
        return False
    title_anchor = _title_topic_anchor_ratio(topic_phrase, str(entry.get("title") or ""))
    return title_anchor >= 0.2


def _keyword_terms(text: str) -> set[str]:
    return {
        _normalize_keyword(term)
        for term in re.findall(r"[A-Za-z0-9]+", text.casefold())
        if len(term) >= 4
    }


def _expanded_keyword_terms(text: str) -> set[str]:
    terms = _keyword_terms(text)
    expanded = set(terms)
    for term in terms:
        expanded.update(_related_topic_terms(term))
    return expanded


def _title_topic_anchor_ratio(topic_phrase: str, title: str) -> float:
    normalized_phrase = _normalize_text(topic_phrase.casefold())
    normalized_title = _normalize_text(title.casefold())
    if normalized_phrase and normalized_title and normalized_phrase in normalized_title:
        return 1.0

    topic_terms = _core_topic_terms(topic_phrase)
    title_terms = _keyword_terms(title)
    if not topic_terms or not title_terms:
        return 0.0
    overlap = topic_terms & title_terms
    if overlap:
        return max(0.25, len(overlap) / len(topic_terms))
    return 0.0


def _core_topic_terms(topic_phrase: str) -> set[str]:
    generic_terms = {"evolution", "origin", "origins", "science", "study", "studies"}
    return {term for term in _keyword_terms(topic_phrase) if term not in generic_terms}


def _term_overlap_ratio(topic_terms: set[str], candidate_terms: set[str]) -> float:
    if not topic_terms or not candidate_terms:
        return 0.0
    return len(topic_terms & candidate_terms) / len(topic_terms)


def _normalize_keyword(term: str) -> str:
    normalized = term.casefold()
    for suffix in ("isms", "ists", "ation", "ment", "ings", "ness", "isms", "ism", "ist", "ing", "ers", "er", "ies", "ied", "ed", "es", "s"):
        if len(normalized) > len(suffix) + 3 and normalized.endswith(suffix):
            if suffix in {"ies", "ied"}:
                return normalized[: -len(suffix)] + "y"
            return normalized[: -len(suffix)]
    return normalized


def _related_topic_terms(term: str) -> set[str]:
    related_groups = (
        {"human", "hominid", "hominin", "homo"},
        {"chimpanzee", "chimp", "pan", "ape", "apes", "primate"},
        {"primate", "primate", "ape", "apes", "hominid", "hominin"},
        {"evolution", "evolutionary", "phylogeny", "phylogen", "ancestor", "ancestral"},
        {"origin", "origins", "abiogenesis", "prebiotic"},
        {"morphometry", "morphology", "cranial", "dental", "skeletal", "body"},
        {"paleolithic", "paleoanthropology", "paleoanthropological", "pleistocene", "fossil"},
    )
    for group in related_groups:
        if term in group:
            return group - {term}
    return set()


def _openalex_work_to_entry(work: dict) -> BibEntry:
    title = _normalize_text(work.get("display_name", "") or "Untitled work")
    year = str(work.get("publication_year") or "")
    doi = _normalize_openalex_doi(work.get("doi"))
    openalex_id = _normalize_openalex_id(work.get("id", ""))
    authors = " and ".join(_openalex_author_name(item) for item in work.get("authorships", []))
    source = ((work.get("primary_location") or {}).get("source") or {}).get("display_name", "")
    work_type = work.get("type", "")

    fields: dict[str, str] = {"title": title}
    if year:
        fields["year"] = year
    if authors:
        fields["author"] = authors
    if doi:
        fields["doi"] = doi
        fields["url"] = f"https://doi.org/{doi}"
    if openalex_id:
        fields["openalex"] = openalex_id
    if abstract := work.get("abstract_inverted_index"):
        fields["abstract"] = _openalex_abstract_text(abstract)
    if source:
        if work_type == "article":
            fields["journal"] = source
        else:
            fields["booktitle"] = source

    citation_key = _openalex_citation_key(openalex_id, authors, year, title)
    entry_type = _openalex_type_to_bibtype(work_type)
    return BibEntry(entry_type=entry_type, citation_key=citation_key, fields=fields)


def _openalex_author_name(authorship: dict) -> str:
    author = authorship.get("author") or {}
    name = author.get("display_name", "")
    return _normalize_text(name)


def _openalex_abstract_text(inverted_index: dict) -> str:
    positions: dict[int, str] = {}
    for word, indexes in inverted_index.items():
        for index in indexes:
            positions[int(index)] = word
    return " ".join(word for _, word in sorted(positions.items()))


def _openalex_type_to_bibtype(work_type: str) -> str:
    mapping = {
        "article": "article",
        "book": "book",
        "book-chapter": "incollection",
        "dissertation": "phdthesis",
        "proceedings-article": "inproceedings",
    }
    return mapping.get(work_type, "misc")


def _openalex_citation_key(openalex_id: str, authors: str, year: str, title: str) -> str:
    if openalex_id:
        return f"openalex{re.sub(r'[^A-Za-z0-9]+', '', openalex_id).lower()}"
    author = authors.split(" and ")[0] if authors else "ref"
    family = re.sub(r"[^A-Za-z0-9]+", "", author.split()[-1]).lower() or "ref"
    first_word = re.sub(r"[^A-Za-z0-9]+", "", title.split()[0]).lower() if title.split() else "untitled"
    return f"{family}{year or 'nd'}{first_word}"


def _normalize_openalex_id(value: str) -> str:
    if not value:
        return ""
    return value.rsplit("/", 1)[-1]


def _normalize_openalex_doi(value: str | None) -> str:
    if not value:
        return ""
    if value.startswith("https://doi.org/"):
        return value[len("https://doi.org/") :]
    return value
