from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .bibtex import BibEntry, parse_bibtex
from .sources import SourceClient


@dataclass(slots=True)
class Resolution:
    entry: BibEntry
    source_type: str
    source_label: str


class MetadataResolver:
    def __init__(
        self,
        user_agent: str = "citegeist/0.1 (local research tool)",
        source_client: SourceClient | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.source_client = source_client or SourceClient(user_agent=user_agent)

    def resolve_entry(self, entry: BibEntry) -> Resolution | None:
        if doi := entry.fields.get("doi"):
            resolved = self.resolve_doi(doi)
            if resolved is not None:
                return resolved

        if openalex_id := entry.fields.get("openalex"):
            resolved = self.resolve_openalex(openalex_id)
            if resolved is not None:
                return resolved

        if dblp_key := entry.fields.get("dblp"):
            resolved = self.resolve_dblp(dblp_key)
            if resolved is not None:
                return resolved

        if arxiv_id := entry.fields.get("arxiv"):
            resolved = self.resolve_arxiv(arxiv_id)
            if resolved is not None:
                return resolved

        if title := entry.fields.get("title"):
            resolved = self.search_openalex_best_match(
                title=title,
                author_text=entry.fields.get("author", ""),
                year=entry.fields.get("year", ""),
            )
            if resolved is not None:
                return resolved

        return None

    def resolve_doi(self, doi: str) -> Resolution | None:
        encoded = urllib.parse.quote(doi, safe="")
        payload = self.source_client.get_json(f"https://api.crossref.org/works/{encoded}")
        message = payload.get("message", {})
        if not message:
            return None
        return Resolution(
            entry=_crossref_message_to_entry(message),
            source_type="resolver",
            source_label=f"crossref:doi:{doi}",
        )

    def search_crossref(self, title: str, limit: int = 5) -> list[BibEntry]:
        query = urllib.parse.urlencode({"query.title": title, "rows": limit})
        payload = self.source_client.get_json(f"https://api.crossref.org/works?{query}")
        items = payload.get("message", {}).get("items", [])
        return [_crossref_message_to_entry(item) for item in items]

    def resolve_dblp(self, dblp_key: str) -> Resolution | None:
        encoded_key = urllib.parse.quote(dblp_key, safe="/:")
        text = self.source_client.get_text(f"https://dblp.org/rec/{encoded_key}.bib")
        entries = parse_bibtex(text)
        if not entries:
            return None
        return Resolution(
            entry=entries[0],
            source_type="resolver",
            source_label=f"dblp:key:{dblp_key}",
        )

    def search_dblp(self, query_text: str, limit: int = 5) -> list[BibEntry]:
        query = urllib.parse.urlencode({"q": query_text, "format": "json", "h": limit})
        payload = self.source_client.get_json(f"https://dblp.org/search/publ/api?{query}")
        hits = payload.get("result", {}).get("hits", {}).get("hit", [])
        if isinstance(hits, dict):
            hits = [hits]

        results: list[BibEntry] = []
        for hit in hits:
            info = hit.get("info", {})
            dblp_key = info.get("key")
            if dblp_key:
                resolved = self.resolve_dblp(dblp_key)
                if resolved is not None:
                    results.append(resolved.entry)
        return results

    def resolve_arxiv(self, arxiv_id: str) -> Resolution | None:
        query = urllib.parse.urlencode({"id_list": arxiv_id})
        root = self.source_client.get_xml(f"https://export.arxiv.org/api/query?{query}")
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", namespace)
        if entry is None:
            return None
        return Resolution(
            entry=_arxiv_atom_entry_to_bib(entry, arxiv_id),
            source_type="resolver",
            source_label=f"arxiv:id:{arxiv_id}",
        )

    def resolve_openalex(self, openalex_id: str) -> Resolution | None:
        normalized_id = _normalize_openalex_id(openalex_id)
        payload = self.source_client.get_json(f"https://api.openalex.org/works/{normalized_id}")
        if not payload:
            return None
        return Resolution(
            entry=_openalex_work_to_entry(payload),
            source_type="resolver",
            source_label=f"openalex:id:{normalized_id}",
        )

    def search_openalex(self, title: str, limit: int = 5) -> list[BibEntry]:
        query = urllib.parse.urlencode({"search": title, "per-page": limit})
        payload = self.source_client.get_json(f"https://api.openalex.org/works?{query}")
        return [_openalex_work_to_entry(item) for item in payload.get("results", [])]

    def search_openalex_best_match(
        self,
        title: str,
        author_text: str = "",
        year: str = "",
    ) -> Resolution | None:
        candidates = self.search_openalex(title, limit=5)
        if not candidates:
            return None

        title_norm = _normalize_match_text(title)
        author_norm = _normalize_match_text(author_text)
        for candidate in candidates:
            candidate_title = _normalize_match_text(candidate.fields.get("title", ""))
            candidate_author = _normalize_match_text(candidate.fields.get("author", ""))
            candidate_year = candidate.fields.get("year", "")
            if candidate_title == title_norm:
                if author_norm and candidate_author and author_norm.split(" and ")[0] not in candidate_author:
                    continue
                if year and candidate_year and year != candidate_year:
                    continue
                return Resolution(
                    entry=candidate,
                    source_type="resolver",
                    source_label=f"openalex:search:{title}",
                )

        return Resolution(
            entry=candidates[0],
            source_type="resolver",
            source_label=f"openalex:search:{title}",
        )

def merge_entries(base: BibEntry, resolved: BibEntry) -> BibEntry:
    merged_fields = dict(base.fields)
    for key, value in resolved.fields.items():
        if value and (key not in merged_fields or not merged_fields[key]):
            merged_fields[key] = value
    return BibEntry(
        entry_type=base.entry_type or resolved.entry_type,
        citation_key=base.citation_key,
        fields=merged_fields,
    )


def _crossref_message_to_entry(message: dict) -> BibEntry:
    entry_type = _crossref_type_to_bibtype(message.get("type", "article"))
    title_values = message.get("title", [])
    title = title_values[0] if title_values else ""
    year = _extract_crossref_year(message)
    authors = " and ".join(_crossref_person_to_name(person) for person in message.get("author", []))
    venue = ""
    if container_title := message.get("container-title", []):
        venue = container_title[0]

    fields: dict[str, str] = {}
    if authors:
        fields["author"] = authors
    if title:
        fields["title"] = title
    if year:
        fields["year"] = year
    if doi := message.get("DOI"):
        fields["doi"] = doi
    if url := message.get("URL"):
        fields["url"] = url
    if abstract := message.get("abstract"):
        fields["abstract"] = abstract
    if venue:
        if entry_type == "article":
            fields["journal"] = venue
        else:
            fields["booktitle"] = venue
    if volume := message.get("volume"):
        fields["volume"] = str(volume)
    if issue := message.get("issue"):
        fields["number"] = str(issue)
    if pages := message.get("page"):
        fields["pages"] = str(pages)

    citation_key = _make_resolution_key(fields.get("author", "crossref"), year or "n.d.", title or "untitled")
    return BibEntry(entry_type=entry_type, citation_key=citation_key, fields=fields)


def _arxiv_atom_entry_to_bib(node: ET.Element, arxiv_id: str) -> BibEntry:
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    title = _node_text(node.find("atom:title", ns))
    summary = _node_text(node.find("atom:summary", ns))
    published = _node_text(node.find("atom:published", ns))
    year = published[:4] if published else ""
    authors = " and ".join(
        _node_text(author.find("atom:name", ns)) for author in node.findall("atom:author", ns)
    )
    doi = _node_text(node.find("arxiv:doi", ns))

    fields: dict[str, str] = {
        "title": title,
        "author": authors,
        "year": year,
        "arxiv": arxiv_id,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
    }
    if summary:
        fields["abstract"] = summary
    if doi:
        fields["doi"] = doi
    return BibEntry(entry_type="article", citation_key=f"arxiv{arxiv_id.replace('.', '').replace('/', '')}", fields=fields)


def _crossref_type_to_bibtype(crossref_type: str) -> str:
    mapping = {
        "journal-article": "article",
        "proceedings-article": "inproceedings",
        "book-chapter": "incollection",
        "book": "book",
        "proceedings": "proceedings",
    }
    return mapping.get(crossref_type, "misc")


def _extract_crossref_year(message: dict) -> str:
    for field_name in ("published-print", "published-online", "issued", "created"):
        date_parts = message.get(field_name, {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            return str(date_parts[0][0])
    return ""


def _crossref_person_to_name(person: dict) -> str:
    family = person.get("family", "")
    given = person.get("given", "")
    if family and given:
        return f"{family}, {given}"
    return family or given


def _node_text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return " ".join(node.text.split())


def _make_resolution_key(author_text: str, year: str, title: str) -> str:
    first_author = author_text.split(" and ")[0]
    family_name = first_author.split(",")[0] if "," in first_author else first_author.split()[-1]
    family_name = "".join(ch for ch in family_name.lower() if ch.isalnum()) or "ref"
    first_word = "".join(ch for ch in title.split()[0].lower() if ch.isalnum()) if title.split() else "untitled"
    return f"{family_name}{year}{first_word}"


def _openalex_work_to_entry(work: dict) -> BibEntry:
    title = work.get("display_name", "") or "Untitled work"
    year = str(work.get("publication_year") or "")
    doi = _normalize_openalex_doi(work.get("doi"))
    openalex_id = _normalize_openalex_id(work.get("id", ""))
    authors = " and ".join(_openalex_author_name(item) for item in work.get("authorships", []))
    source = ((work.get("primary_location") or {}).get("source") or {}).get("display_name", "")
    work_type = work.get("type", "")

    fields: dict[str, str] = {}
    if authors:
        fields["author"] = authors
    if title:
        fields["title"] = title
    if year:
        fields["year"] = year
    if doi:
        fields["doi"] = doi
        fields["url"] = f"https://doi.org/{doi}"
    if openalex_id:
        fields["openalex"] = openalex_id
        fields.setdefault("url", f"https://openalex.org/{openalex_id}")
    if abstract := work.get("abstract_inverted_index"):
        fields["abstract"] = _openalex_abstract_text(abstract)
    if source:
        if work_type == "article":
            fields["journal"] = source
        else:
            fields["booktitle"] = source

    citation_key = f"openalex{re.sub(r'[^A-Za-z0-9]+', '', openalex_id).lower()}" if openalex_id else _make_resolution_key(authors or "openalex", year or "n.d.", title or "untitled")
    return BibEntry(entry_type=_openalex_type_to_bibtype(work_type), citation_key=citation_key, fields=fields)


def _openalex_author_name(authorship: dict) -> str:
    author = authorship.get("author") or {}
    return " ".join(str(author.get("display_name", "")).split())


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


def _normalize_match_text(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"\W+", " ", lowered)
    return " ".join(lowered.split())
