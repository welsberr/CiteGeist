from __future__ import annotations

import re
from dataclasses import dataclass

from .bibtex import BibEntry
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
