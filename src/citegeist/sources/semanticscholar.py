"""Semantic Scholar source plugin."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from citegeist.bibtex import BibEntry
from citegeist.sources.base import BibliographicSource


class SemanticScholarSource(BibliographicSource):
    """Semantic Scholar source for broad scientific metadata coverage."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    DEFAULT_FIELDS = (
        "paperId,title,year,abstract,authors,externalIds,journal,venue,url,"
        "openAccessPdf,citationCount,publicationTypes"
    )

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = str(
            self.config.get("api_key")
            or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
            or ""
        ).strip()
        self.user_agent = str(self.config.get("user_agent") or "citegeist/0.1 (local research tool)")

    def lookup_by_doi(self, doi: str) -> Optional[BibEntry]:
        normalized = doi.strip()
        if not normalized:
            return None
        encoded = urllib.parse.quote(f"DOI:{normalized}", safe="")
        payload = self._get_json(f"{self.BASE_URL}/paper/{encoded}?fields={self.DEFAULT_FIELDS}")
        if not payload:
            return None
        return self.normalize(payload)

    def lookup_by_title(self, title: str) -> Optional[BibEntry]:
        matches = self.search(title, limit=1)
        return matches[0] if matches else None

    def search(self, query: str, limit: int = 10) -> List[BibEntry]:
        query_text = " ".join(query.split())
        if not query_text:
            return []
        params = urllib.parse.urlencode(
            {"query": query_text, "limit": max(1, limit), "fields": self.DEFAULT_FIELDS}
        )
        payload = self._get_json(f"{self.BASE_URL}/paper/search?{params}")
        if not payload:
            return []
        return [entry for row in payload.get("data", []) if (entry := self.normalize(row)) is not None]

    def normalize(self, record: Dict[str, Any]) -> Optional[BibEntry]:
        title = str(record.get("title") or "").strip()
        if not title:
            return None

        external_ids = record.get("externalIds") or {}
        doi = str(external_ids.get("DOI") or "").strip()
        authors = " and ".join(
            str(author.get("name") or "").strip()
            for author in record.get("authors", [])
            if str(author.get("name") or "").strip()
        )
        year = str(record.get("year") or "").strip()
        abstract = str(record.get("abstract") or "").strip()
        journal = record.get("journal") or {}
        journal_name = str(journal.get("name") or record.get("venue") or "").strip()
        open_access_pdf = record.get("openAccessPdf") or {}

        fields: Dict[str, str] = {"title": title}
        if doi:
            fields["doi"] = doi
        if paper_id := str(record.get("paperId") or "").strip():
            fields["semanticscholar_id"] = paper_id
        if year:
            fields["year"] = year
        if authors:
            fields["author"] = authors
        if abstract:
            fields["abstract"] = abstract
        if journal_name:
            if self._entry_type(record) == "inproceedings":
                fields["booktitle"] = journal_name
            else:
                fields["journal"] = journal_name
        if url := str(open_access_pdf.get("url") or record.get("url") or "").strip():
            fields["url"] = url
        if open_access_pdf:
            fields["is_oa"] = "true"
        if citation_count := record.get("citationCount"):
            fields["semanticscholar_citation_count"] = str(citation_count)

        citation_key = self._citation_key(doi, str(record.get("paperId") or ""), authors, year, title)
        return BibEntry(entry_type=self._entry_type(record), citation_key=citation_key, fields=fields)

    def get_fulltext_url(self, doi: str) -> Optional[str]:
        entry = self.lookup_by_doi(doi)
        if entry is None:
            return None
        return entry.fields.get("url")

    def get_identifier_scheme(self) -> str:
        return "doi"

    def _entry_type(self, record: Dict[str, Any]) -> str:
        publication_types = [str(item).lower() for item in (record.get("publicationTypes") or [])]
        if any("conference" in item for item in publication_types):
            return "inproceedings"
        if any("review" in item for item in publication_types):
            return "article"
        if record.get("journal") or record.get("venue"):
            return "article"
        return "misc"

    def _citation_key(self, doi: str, paper_id: str, authors: str, year: str, title: str) -> str:
        if doi:
            return "doi" + "".join(ch for ch in doi.lower() if ch.isalnum())
        if paper_id:
            return "s2" + "".join(ch for ch in paper_id.lower() if ch.isalnum())
        family = authors.split(" and ")[0].split()[-1] if authors else "ref"
        family = "".join(ch for ch in family.lower() if ch.isalnum()) or "ref"
        first_word = "".join(ch for ch in (title.split()[0] if title.split() else "untitled").lower() if ch.isalnum())
        return f"{family}{year or 'nd'}{first_word or 'untitled'}"

    def _get_json(self, url: str) -> Dict[str, Any] | None:
        headers = {"User-Agent": self.user_agent}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return None
