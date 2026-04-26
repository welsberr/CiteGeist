"""OpenCitations source plugin."""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from citegeist.bibtex import BibEntry
from citegeist.sources.base import BibliographicSource, CitationEdge
from citegeist.sources._old_sources_compat import SourceClient


class OpenCitationsSource(BibliographicSource):
    """OpenCitations source for DOI metadata and citation edges."""

    INDEX_BASE_URL = "https://api.opencitations.net/index/v2"
    META_BASE_URL = "https://api.opencitations.net/meta/v1"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        user_agent = self.config.get("user_agent", "citegeist/0.1 (local research tool)")
        self.source_client = self.config.get("source_client") or SourceClient(user_agent=user_agent)

    def lookup_by_doi(self, doi: str) -> Optional[BibEntry]:
        normalized = self._normalize_doi_pid(doi)
        if not normalized:
            return None
        rows = self.source_client.try_get_json(f"{self.META_BASE_URL}/metadata/{normalized}")
        if not rows:
            return None
        return self.normalize(rows[0])

    def lookup_by_title(self, title: str) -> Optional[BibEntry]:
        return None

    def search(self, query: str, limit: int = 10) -> List[BibEntry]:
        return []

    def normalize(self, record: Dict[str, Any]) -> Optional[BibEntry]:
        ids = str(record.get("id") or "")
        title = str(record.get("title") or "").strip()
        if not ids or not title:
            return None

        doi = self._extract_id_value(ids, "doi")
        openalex = self._extract_id_value(ids, "openalex")
        year = self._extract_year(str(record.get("pub_date") or ""))
        authors = self._normalize_author_field(str(record.get("author") or ""))
        venue, venue_ids = self._parse_venue_field(str(record.get("venue") or ""))
        entry_type = self._map_entry_type(str(record.get("type") or ""))

        fields: Dict[str, str] = {"title": title}
        if doi:
            fields["doi"] = doi
            fields["url"] = f"https://doi.org/{doi}"
        if openalex:
            fields["openalex"] = openalex
        if year:
            fields["year"] = year
        if authors:
            fields["author"] = authors
        if venue:
            if entry_type == "article":
                fields["journal"] = venue
            else:
                fields["booktitle"] = venue
        if volume := str(record.get("volume") or "").strip():
            fields["volume"] = volume
        if issue := str(record.get("issue") or "").strip():
            fields["number"] = issue
        if pages := str(record.get("page") or "").strip():
            fields["pages"] = pages
        if publisher := self._strip_bracketed_ids(str(record.get("publisher") or "")):
            fields["publisher"] = publisher
        if venue_ids:
            fields["note"] = f"opencitations_venue_ids = {{{venue_ids}}}"

        citation_key = self._citation_key(doi, openalex, authors, year, title)
        return BibEntry(entry_type=entry_type, citation_key=citation_key, fields=fields)

    def get_citations(self, work_id: str, relation_type: str = "cites", limit: int = 10) -> List[CitationEdge]:
        normalized = self._normalize_doi_pid(work_id)
        if not normalized:
            return []
        path = "references" if relation_type == "cites" else "citations"
        rows = self.source_client.try_get_json(f"{self.INDEX_BASE_URL}/{path}/{normalized}")
        if not rows:
            return []

        edges: List[CitationEdge] = []
        for row in rows[:limit]:
            citing = self._extract_id_value(str(row.get("citing") or ""), "doi")
            cited = self._extract_id_value(str(row.get("cited") or ""), "doi")
            if not citing or not cited:
                continue
            if relation_type == "cites":
                source_work_id, target_work_id = citing, cited
            else:
                source_work_id, target_work_id = citing, cited
            edges.append(
                CitationEdge(
                    source_work_id=f"doi:{source_work_id}",
                    target_work_id=f"doi:{target_work_id}",
                    relation_type="cites",
                    source_type="opencitations",
                    source_label=f"opencitations:{path}:{normalized}",
                    confidence=0.85,
                )
            )
        return edges

    def get_identifier_scheme(self) -> str:
        return "doi"

    def _normalize_doi_pid(self, value: str) -> str:
        doi = value.strip()
        if not doi:
            return ""
        if doi.lower().startswith("doi:"):
            doi = doi[4:]
        return f"doi:{doi}"

    def _extract_id_value(self, identifiers: str, scheme: str) -> str:
        prefix = f"{scheme}:"
        for token in identifiers.split():
            if token.startswith(prefix):
                return token[len(prefix):]
        return ""

    def _extract_year(self, pub_date: str) -> str:
        pub_date = pub_date.strip()
        if len(pub_date) >= 4 and pub_date[:4].isdigit():
            return pub_date[:4]
        return ""

    def _normalize_author_field(self, raw_authors: str) -> str:
        authors: List[str] = []
        for part in raw_authors.split(";"):
            cleaned = self._strip_bracketed_ids(part)
            cleaned = " ".join(cleaned.split())
            if cleaned:
                authors.append(cleaned)
        return " and ".join(authors)

    def _parse_venue_field(self, raw_venue: str) -> tuple[str, str]:
        raw_venue = raw_venue.strip()
        if not raw_venue:
            return "", ""
        if "[" not in raw_venue:
            return raw_venue, ""
        title, _, remainder = raw_venue.partition("[")
        return title.strip(), remainder.rstrip("] ").strip()

    def _strip_bracketed_ids(self, value: str) -> str:
        return value.split("[", 1)[0].strip()

    def _map_entry_type(self, raw_type: str) -> str:
        lowered = raw_type.casefold()
        if lowered == "journal article":
            return "article"
        if lowered == "book":
            return "book"
        if lowered == "book chapter":
            return "incollection"
        if lowered in {"proceedings article", "conference paper"}:
            return "inproceedings"
        if "thesis" in lowered or "dissertation" in lowered:
            return "phdthesis"
        return "misc"

    def _citation_key(self, doi: str, openalex: str, authors: str, year: str, title: str) -> str:
        if doi:
            return "doi" + "".join(ch for ch in doi.lower() if ch.isalnum())
        if openalex:
            return "openalex" + "".join(ch for ch in openalex.lower() if ch.isalnum())
        family = authors.split(" and ")[0].split(",")[0].split()[-1] if authors else "ref"
        family = "".join(ch for ch in family.lower() if ch.isalnum()) or "ref"
        first_word = "".join(ch for ch in (title.split()[0] if title.split() else "untitled").lower() if ch.isalnum())
        return f"{family}{year or 'nd'}{first_word or 'untitled'}"
