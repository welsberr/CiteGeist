"""Open Library source plugin."""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from citegeist.bibtex import BibEntry
from citegeist.sources.base import BibliographicSource
from citegeist.sources._old_sources_compat import SourceClient


class OpenLibrarySource(BibliographicSource):
    """Open Library source for broad book and monograph metadata."""

    SEARCH_URL = "https://openlibrary.org/search.json"
    WORK_URL = "https://openlibrary.org"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        user_agent = str(self.config.get("user_agent") or "citegeist/0.1 (local research tool)")
        self.source_client = self.config.get("source_client") or SourceClient(user_agent=user_agent)

    def lookup_by_doi(self, doi: str) -> Optional[BibEntry]:
        return None

    def lookup_by_title(self, title: str) -> Optional[BibEntry]:
        matches = self.search(title, limit=1)
        return matches[0] if matches else None

    def search(self, query: str, limit: int = 10) -> List[BibEntry]:
        title = " ".join(query.split())
        if not title:
            return []
        params = urllib.parse.urlencode({"title": title, "limit": max(1, limit), "fields": "*"})
        payload = self.source_client.try_get_json(f"{self.SEARCH_URL}?{params}")
        if not payload:
            return []
        docs = payload.get("docs", [])
        if not isinstance(docs, list):
            return []
        return [entry for record in docs if isinstance(record, dict) and (entry := self.normalize(record)) is not None]

    def normalize(self, record: Dict[str, Any]) -> Optional[BibEntry]:
        title = str(record.get("title") or "").strip()
        if not title:
            return None

        authors = self._join_list(record.get("author_name"))
        year = self._extract_year(record)
        publishers = self._join_list(record.get("publisher"))
        work_key = str(record.get("key") or "").strip()
        edition_keys = record.get("edition_key") or []
        isbn_values = record.get("isbn") or []

        fields: Dict[str, str] = {"title": title}
        if authors:
            fields["author"] = authors
        if year:
            fields["year"] = year
        if publishers:
            fields["publisher"] = publishers
        if work_key:
            fields["openlibrary_work"] = work_key
            fields["url"] = f"{self.WORK_URL}{work_key}"
        if isinstance(edition_keys, list) and edition_keys:
            fields["openlibrary_edition"] = str(edition_keys[0])
        if isinstance(isbn_values, list) and isbn_values:
            fields["isbn"] = str(isbn_values[0])

        return BibEntry(
            entry_type="book",
            citation_key=self._citation_key(work_key, authors, year, title),
            fields=fields,
        )

    def get_identifier_scheme(self) -> str:
        return "openlibrary"

    def _extract_year(self, record: Dict[str, Any]) -> str:
        first_publish_year = record.get("first_publish_year")
        if first_publish_year:
            return str(first_publish_year)
        publish_year = record.get("publish_year")
        if isinstance(publish_year, list) and publish_year:
            return str(publish_year[0])
        return ""

    def _join_list(self, value: Any) -> str:
        if not isinstance(value, list):
            return ""
        items = [str(item).strip() for item in value if str(item).strip()]
        return " and ".join(items)

    def _citation_key(self, work_key: str, authors: str, year: str, title: str) -> str:
        if work_key:
            return "ol" + "".join(ch for ch in work_key.lower() if ch.isalnum())
        family = authors.split(" and ")[0].split()[-1] if authors else "book"
        family = "".join(ch for ch in family.lower() if ch.isalnum()) or "book"
        first_word = "".join(ch for ch in (title.split()[0] if title.split() else "untitled").lower() if ch.isalnum())
        return f"{family}{year or 'nd'}{first_word or 'untitled'}"
