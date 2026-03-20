from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from .bibtex import BibEntry, parse_bibtex
from .resolve import MetadataResolver
from .storage import BibliographyStore


@dataclass(slots=True)
class ExpansionResult:
    source_citation_key: str
    discovered_citation_key: str
    created_entry: bool
    relation_type: str
    source_label: str


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
            discovered = _crossref_reference_to_entry(reference, citation_key, index)
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
    entry_type = "article" if journal_title else "misc"
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
