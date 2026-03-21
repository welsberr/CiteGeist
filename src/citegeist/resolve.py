from __future__ import annotations

import html
import re
import urllib.error
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
            resolved = self.resolve_datacite_doi(doi)
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
            resolved = self.search_crossref_best_match(
                title=title,
                author_text=entry.fields.get("author", ""),
                year=entry.fields.get("year", ""),
            )
            if resolved is not None:
                return resolved
            resolved = self.search_datacite_best_match(
                title=title,
                author_text=entry.fields.get("author", ""),
                year=entry.fields.get("year", ""),
            )
            if resolved is not None:
                return resolved
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
        payload = self._safe_get_json(f"https://api.crossref.org/works/{encoded}")
        if payload is None:
            return None
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
        payload = self._safe_get_json(f"https://api.crossref.org/works?{query}")
        if payload is None:
            return []
        items = payload.get("message", {}).get("items", [])
        return [_crossref_message_to_entry(item) for item in items]

    def search_crossref_best_match(
        self,
        title: str,
        author_text: str = "",
        year: str = "",
    ) -> Resolution | None:
        candidate = _select_best_title_match(
            self.search_crossref(title, limit=5),
            title=title,
            author_text=author_text,
            year=year,
        )
        if candidate is None:
            return None
        return Resolution(
            entry=candidate,
            source_type="resolver",
            source_label=f"crossref:search:{title}",
        )

    def resolve_dblp(self, dblp_key: str) -> Resolution | None:
        encoded_key = urllib.parse.quote(dblp_key, safe="/:")
        text = self._safe_get_text(f"https://dblp.org/rec/{encoded_key}.bib")
        if text is None:
            return None
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
        payload = self._safe_get_json(f"https://dblp.org/search/publ/api?{query}")
        if payload is None:
            return []
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
        root = self._safe_get_xml(f"https://export.arxiv.org/api/query?{query}")
        if root is None:
            return None
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
        payload = self._safe_get_json(f"https://api.openalex.org/works/{normalized_id}")
        if payload is None:
            return None
        if not payload:
            return None
        return Resolution(
            entry=_openalex_work_to_entry(payload),
            source_type="resolver",
            source_label=f"openalex:id:{normalized_id}",
        )

    def resolve_datacite_doi(self, doi: str) -> Resolution | None:
        encoded = urllib.parse.quote(doi, safe="")
        payload = self._safe_get_json(f"https://api.datacite.org/dois/{encoded}")
        if payload is None:
            return None
        data = payload.get("data", {})
        if not data:
            return None
        return Resolution(
            entry=_datacite_work_to_entry(data),
            source_type="resolver",
            source_label=f"datacite:doi:{doi}",
        )

    def search_datacite(self, title: str, limit: int = 5) -> list[BibEntry]:
        query = urllib.parse.urlencode({"query": title, "page[size]": limit})
        payload = self._safe_get_json(f"https://api.datacite.org/dois?{query}")
        if payload is None:
            return []
        return [_datacite_work_to_entry(item) for item in payload.get("data", [])]

    def search_datacite_best_match(
        self,
        title: str,
        author_text: str = "",
        year: str = "",
    ) -> Resolution | None:
        candidate = _select_best_title_match(
            self.search_datacite(title, limit=5),
            title=title,
            author_text=author_text,
            year=year,
        )
        if candidate is None:
            return None
        return Resolution(
            entry=candidate,
            source_type="resolver",
            source_label=f"datacite:search:{title}",
        )

    def search_openalex(self, title: str, limit: int = 5) -> list[BibEntry]:
        query = urllib.parse.urlencode({"search": title, "per-page": limit})
        payload = self._safe_get_json(f"https://api.openalex.org/works?{query}")
        if payload is None:
            return []
        return [_openalex_work_to_entry(item) for item in payload.get("results", [])]

    def _safe_get_json(self, url: str) -> dict | None:
        try:
            return self.source_client.get_json(url)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            return None

    def _safe_get_text(self, url: str) -> str | None:
        try:
            return self.source_client.get_text(url)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            return None

    def _safe_get_xml(self, url: str) -> ET.Element | None:
        try:
            return self.source_client.get_xml(url)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ET.ParseError, ValueError):
            return None

    def search_openalex_best_match(
        self,
        title: str,
        author_text: str = "",
        year: str = "",
    ) -> Resolution | None:
        candidate = _select_best_title_match(
            self.search_openalex(title, limit=5),
            title=title,
            author_text=author_text,
            year=year,
        )
        if candidate is None:
            return None
        return Resolution(
            entry=candidate,
            source_type="resolver",
            source_label=f"openalex:search:{title}",
        )

def merge_entries(base: BibEntry, resolved: BibEntry) -> BibEntry:
    merged, _ = merge_entries_with_conflicts(base, resolved)
    return merged


def merge_entries_with_conflicts(base: BibEntry, resolved: BibEntry) -> tuple[BibEntry, list[dict[str, str]]]:
    merged_fields = dict(base.fields)
    conflicts: list[dict[str, str]] = []
    for key, value in resolved.fields.items():
        if not value:
            continue
        current_value = merged_fields.get(key, "")
        if _is_placeholder_value(key, current_value) and current_value != value:
            merged_fields[key] = value
            continue
        if current_value and current_value != value:
            conflicts.append(
                {
                    "field_name": key,
                    "current_value": current_value,
                    "proposed_value": value,
                }
            )
            continue
        if key not in merged_fields or not merged_fields[key]:
            merged_fields[key] = value
    return (
        BibEntry(
            entry_type=_merged_entry_type(base.entry_type, resolved.entry_type),
            citation_key=base.citation_key,
            fields=merged_fields,
        ),
        conflicts,
    )


def _is_placeholder_value(field_name: str, value: str) -> bool:
    normalized = " ".join((value or "").split()).strip()
    if not normalized:
        return True
    lowered = normalized.lower()
    if field_name == "title":
        return bool(re.fullmatch(r"referenced work \d+", lowered)) or lowered.startswith("untitled")
    return False


def _merged_entry_type(base_entry_type: str, resolved_entry_type: str) -> str:
    if base_entry_type == "misc" and resolved_entry_type and resolved_entry_type != "misc":
        return resolved_entry_type
    return base_entry_type or resolved_entry_type


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
    normalized_author_text = " ".join((author_text or "").split())
    first_author = normalized_author_text.split(" and ")[0].strip() if normalized_author_text else ""
    if "," in first_author:
        family_name = first_author.split(",")[0].strip()
    elif first_author:
        author_tokens = first_author.split()
        family_name = author_tokens[-1] if author_tokens else ""
    else:
        family_name = ""
    family_name = "".join(ch for ch in family_name.lower() if ch.isalnum()) or "ref"
    first_word = "".join(ch for ch in title.split()[0].lower() if ch.isalnum()) if title.split() else "untitled"
    return f"{family_name}{year}{first_word}"


def _openalex_work_to_entry(work: dict) -> BibEntry:
    title = _normalize_text(work.get("display_name", "") or "Untitled work")
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
        abstract_text = _openalex_abstract_text(abstract)
        if abstract_text:
            fields["abstract"] = abstract_text
    if source:
        if work_type == "article":
            fields["journal"] = source
        else:
            fields["booktitle"] = source

    citation_key = _openalex_citation_key(doi, openalex_id, authors, year, title)
    return BibEntry(entry_type=_openalex_type_to_bibtype(work_type), citation_key=citation_key, fields=fields)


def _openalex_author_name(authorship: dict) -> str:
    author = authorship.get("author") or {}
    return _normalize_person_display_name(str(author.get("display_name", "")))


def _openalex_abstract_text(inverted_index: dict) -> str:
    positions: dict[int, str] = {}
    for word, indexes in inverted_index.items():
        for index in indexes:
            positions[int(index)] = word
    text = _normalize_text(" ".join(word for _, word in sorted(positions.items())))
    return "" if _looks_like_openalex_page_blob(text) else text


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


def _normalize_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", html.unescape(value))
    return " ".join(without_tags.split())


def _normalize_person_display_name(value: str) -> str:
    normalized = _normalize_text(value)
    if "," not in normalized:
        return normalized

    left, right = [part.strip() for part in normalized.split(",", 1)]
    if not (_looks_like_initial_block(left) and right):
        return normalized

    right_tokens = right.split()
    trailing_initials: list[str] = []
    while right_tokens and _looks_like_initial_block(right_tokens[-1]):
        trailing_initials.insert(0, right_tokens.pop())
    if not right_tokens:
        return normalized

    family = " ".join(right_tokens).strip()
    given_parts = [
        _initial_block_to_given_names(" ".join(trailing_initials)),
        _initial_block_to_given_names(left),
    ]
    given = " ".join(part for part in given_parts if part).strip()
    return f"{family}, {given}" if given else family


def _looks_like_initial_block(value: str) -> bool:
    letters = re.sub(r"[^A-Za-z]+", "", value)
    return 0 < len(letters) <= 4 and letters.upper() == letters


def _initial_block_to_given_names(value: str) -> str:
    letters = re.findall(r"[A-Za-z]", value)
    return " ".join(f"{letter.upper()}." for letter in letters)


def _openalex_citation_key(doi: str, openalex_id: str, authors: str, year: str, title: str) -> str:
    if doi:
        suffix = re.sub(r"[^A-Za-z0-9]+", "", doi).lower()
        return f"doi{suffix}"
    if openalex_id:
        return f"openalex{re.sub(r'[^A-Za-z0-9]+', '', openalex_id).lower()}"
    return _make_resolution_key(authors or "openalex", year or "n.d.", title or "untitled")


def _looks_like_openalex_page_blob(text: str) -> bool:
    lowered = text.casefold()
    blob_markers = (
        "research article|",
        "download citation file",
        "this content is only available via pdf",
        "get citation alerts",
        "views icon",
        "toolbar search",
        "publisher site get access",
        "authors info & claims",
        "publication history",
        "copyright ",
    )
    return len(text) > 60 and any(marker in lowered for marker in blob_markers)


def _normalize_match_text(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"\W+", " ", lowered)
    return " ".join(lowered.split())


def _select_best_title_match(
    candidates: list[BibEntry],
    title: str,
    author_text: str = "",
    year: str = "",
) -> BibEntry | None:
    if not candidates:
        return None

    title_norm = _normalize_match_text(title)
    author_tokens = _author_match_tokens(author_text)
    year_text = str(year or "").strip()

    for candidate in candidates:
        candidate_title = _normalize_match_text(candidate.fields.get("title", ""))
        if candidate_title != title_norm:
            continue
        candidate_year = str(candidate.fields.get("year", "") or "").strip()
        if year_text and candidate_year and year_text != candidate_year:
            continue
        if author_tokens and not _candidate_matches_author_tokens(candidate, author_tokens):
            continue
        return candidate
    return None


def _author_match_tokens(author_text: str) -> set[str]:
    normalized = _normalize_match_text(author_text)
    if not normalized:
        return set()
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 2 and token not in {"and", "et", "al"}
    }
    return tokens


def _candidate_matches_author_tokens(candidate: BibEntry, author_tokens: set[str]) -> bool:
    candidate_author = _normalize_match_text(candidate.fields.get("author", ""))
    if not candidate_author:
        return False
    candidate_tokens = set(re.findall(r"[a-z0-9]+", candidate_author))
    return bool(author_tokens & candidate_tokens)


def _datacite_work_to_entry(data: dict) -> BibEntry:
    attributes = data.get("attributes", {})
    doi = str(attributes.get("doi") or "")
    titles = attributes.get("titles") or []
    creators = attributes.get("creators") or []
    descriptions = attributes.get("descriptions") or []
    publisher = str(attributes.get("publisher") or "")
    year = str(attributes.get("publicationYear") or "")
    url = str(attributes.get("url") or "")
    types = attributes.get("types") or {}

    title = titles[0].get("title", "") if titles else ""
    author_names = " and ".join(_datacite_creator_name(creator) for creator in creators if _datacite_creator_name(creator))
    abstract = _datacite_abstract(descriptions)
    entry_type = _datacite_type_to_bibtype(str(types.get("resourceTypeGeneral") or ""))

    fields: dict[str, str] = {}
    if title:
        fields["title"] = title
    if author_names:
        fields["author"] = author_names
    if year:
        fields["year"] = year
    if doi:
        fields["doi"] = doi
    if url:
        fields["url"] = url
    elif doi:
        fields["url"] = f"https://doi.org/{doi}"
    if publisher:
        fields["publisher"] = publisher
    if abstract:
        fields["abstract"] = abstract

    citation_key = _make_resolution_key(author_names or "datacite", year or "n.d.", title or doi or "untitled")
    return BibEntry(entry_type=entry_type, citation_key=citation_key, fields=fields)


def _datacite_creator_name(creator: dict) -> str:
    family = str(creator.get("familyName") or "")
    given = str(creator.get("givenName") or "")
    if family and given:
        return f"{family}, {given}"
    return str(creator.get("name") or family or given)


def _datacite_abstract(descriptions: list[dict]) -> str:
    for description in descriptions:
        if str(description.get("descriptionType") or "").lower() == "abstract":
            return str(description.get("description") or "")
    return ""


def _datacite_type_to_bibtype(resource_type: str) -> str:
    lowered = resource_type.lower()
    mapping = {
        "audiovisual": "misc",
        "book": "book",
        "bookchapter": "incollection",
        "collection": "misc",
        "computationalnotebook": "misc",
        "conferencepaper": "inproceedings",
        "dataset": "misc",
        "dissertation": "phdthesis",
        "image": "misc",
        "journalarticle": "article",
        "model": "misc",
        "report": "techreport",
        "software": "misc",
        "text": "misc",
    }
    return mapping.get(lowered, "misc")
