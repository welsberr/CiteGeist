from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .bibtex import BibEntry, parse_bibtex


@dataclass(slots=True)
class Resolution:
    entry: BibEntry
    source_type: str
    source_label: str


class MetadataResolver:
    def __init__(self, user_agent: str = "citegeist/0.1 (local research tool)") -> None:
        self.user_agent = user_agent

    def resolve_entry(self, entry: BibEntry) -> Resolution | None:
        if doi := entry.fields.get("doi"):
            resolved = self.resolve_doi(doi)
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

        return None

    def resolve_doi(self, doi: str) -> Resolution | None:
        encoded = urllib.parse.quote(doi, safe="")
        payload = self._get_json(f"https://api.crossref.org/works/{encoded}")
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
        payload = self._get_json(f"https://api.crossref.org/works?{query}")
        items = payload.get("message", {}).get("items", [])
        return [_crossref_message_to_entry(item) for item in items]

    def resolve_dblp(self, dblp_key: str) -> Resolution | None:
        encoded_key = urllib.parse.quote(dblp_key, safe="/:")
        text = self._get_text(f"https://dblp.org/rec/{encoded_key}.bib")
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
        payload = self._get_json(f"https://dblp.org/search/publ/api?{query}")
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
        root = self._get_xml(f"https://export.arxiv.org/api/query?{query}")
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", namespace)
        if entry is None:
            return None
        return Resolution(
            entry=_arxiv_atom_entry_to_bib(entry, arxiv_id),
            source_type="resolver",
            source_label=f"arxiv:id:{arxiv_id}",
        )

    def _get_json(self, url: str) -> dict:
        with urllib.request.urlopen(self._request(url)) as response:
            return json.load(response)

    def _get_text(self, url: str) -> str:
        with urllib.request.urlopen(self._request(url)) as response:
            return response.read().decode("utf-8")

    def _get_xml(self, url: str) -> ET.Element:
        with urllib.request.urlopen(self._request(url)) as response:
            return ET.fromstring(response.read())

    def _request(self, url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
            },
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
