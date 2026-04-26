"""Europe PMC source plugin."""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, Optional

from citegeist.bibtex import BibEntry
from citegeist.sources._old_sources_compat import SourceClient
from citegeist.sources.base import BibliographicSource


class EuropePmcSource(BibliographicSource):
    """Europe PMC source for biomedical metadata and OA/fulltext links."""

    BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        user_agent = self.config.get("user_agent", "citegeist/0.1 (local research tool)")
        self.source_client = self.config.get("source_client") or SourceClient(user_agent=user_agent)

    def lookup_by_doi(self, doi: str) -> Optional[BibEntry]:
        normalized = doi.strip()
        if not normalized:
            return None
        query = f'DOI:"{normalized}"'
        row = self._search_one(query)
        return self.normalize(row) if row else None

    def lookup_by_title(self, title: str) -> Optional[BibEntry]:
        query_text = " ".join(title.split())
        if not query_text:
            return None
        query = f'TITLE:"{query_text}"'
        row = self._search_one(query)
        return self.normalize(row) if row else None

    def search(self, query: str, limit: int = 10) -> list[BibEntry]:
        query_text = " ".join(query.split())
        if not query_text:
            return []
        payload = self._search_payload(f'TITLE:"{query_text}"', max(1, limit))
        results = payload.get("resultList", {}).get("result", []) if payload else []
        return [entry for row in results if (entry := self.normalize(row)) is not None]

    def normalize(self, record: Dict[str, Any]) -> Optional[BibEntry]:
        title = str(record.get("title") or "").strip()
        if not title:
            return None

        doi = str(record.get("doi") or "").strip()
        pmid = str(record.get("pmid") or record.get("id") or "").strip() if str(record.get("source") or "") == "MED" else str(record.get("pmid") or "").strip()
        pmcid = str(record.get("pmcid") or "").strip()
        year = str(record.get("pubYear") or "").strip()
        author_text = self._normalize_author_string(str(record.get("authorString") or "").strip())
        journal_title = str(record.get("journalTitle") or "").strip()
        abstract = str(record.get("abstractText") or "").strip()

        fields: Dict[str, str] = {"title": title}
        if doi:
            fields["doi"] = doi
        if pmid:
            fields["pmid"] = pmid
        if pmcid:
            fields["pmcid"] = pmcid
        if year:
            fields["year"] = year
        if author_text:
            fields["author"] = author_text
        if journal_title:
            fields["journal"] = journal_title
        if volume := str(record.get("journalVolume") or "").strip():
            fields["volume"] = volume
        if issue := str(record.get("issue") or "").strip():
            fields["number"] = issue
        if pages := str(record.get("pageInfo") or "").strip():
            fields["pages"] = pages
        if abstract:
            fields["abstract"] = abstract
        if fulltext_url := self._fulltext_url(record):
            fields["url"] = fulltext_url
        elif article_url := self._article_url(record):
            fields["url"] = article_url
        if str(record.get("isOpenAccess") or "").strip():
            fields["is_oa"] = "true" if str(record.get("isOpenAccess")).upper() == "Y" else "false"
        if cited_by := str(record.get("citedByCount") or "").strip():
            fields["europepmc_cited_by_count"] = cited_by
        if source := str(record.get("source") or "").strip():
            fields["europepmc_source"] = source

        citation_key = self._citation_key(doi, pmid, author_text, year, title)
        return BibEntry(entry_type="article", citation_key=citation_key, fields=fields)

    def get_fulltext_url(self, doi: str) -> Optional[str]:
        normalized = doi.strip()
        if not normalized:
            return None
        payload = self._search_payload(f'DOI:"{normalized}"', 1)
        results = payload.get("resultList", {}).get("result", []) if payload else []
        if not results:
            return None
        return self._fulltext_url(results[0]) or self._article_url(results[0])

    def get_identifier_scheme(self) -> str:
        return "doi"

    def _search_one(self, query: str) -> Dict[str, Any] | None:
        payload = self._search_payload(query, 1)
        results = payload.get("resultList", {}).get("result", []) if payload else []
        return results[0] if results else None

    def _search_payload(self, query: str, page_size: int) -> Dict[str, Any] | None:
        params = {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": max(1, page_size),
        }
        return self.source_client.try_get_json(f"{self.BASE_URL}?{urllib.parse.urlencode(params)}")

    def _fulltext_url(self, record: Dict[str, Any]) -> str:
        candidates = record.get("fullTextUrlList", {})
        if isinstance(candidates, dict):
            urls = candidates.get("fullTextUrl", [])
            if isinstance(urls, dict):
                urls = [urls]
            if isinstance(urls, list):
                for item in urls:
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url") or "").strip()
                    if url:
                        return url
        return ""

    def _article_url(self, record: Dict[str, Any]) -> str:
        source = str(record.get("source") or "").strip()
        identifier = str(record.get("id") or "").strip()
        if source and identifier:
            return f"https://europepmc.org/article/{source}/{identifier}"
        return ""

    def _normalize_author_string(self, value: str) -> str:
        if not value:
            return ""
        authors = [part.strip().rstrip(".") for part in value.split(",") if part.strip()]
        return " and ".join(authors)

    def _citation_key(self, doi: str, pmid: str, author_text: str, year: str, title: str) -> str:
        if doi:
            return "doi" + "".join(ch for ch in doi.lower() if ch.isalnum())
        if pmid:
            return f"pmid{pmid}"
        family = author_text.split(" and ")[0].split()[-1] if author_text else "ref"
        family = "".join(ch for ch in family.lower() if ch.isalnum()) or "ref"
        first_word = "".join(ch for ch in (title.split()[0] if title.split() else "untitled").lower() if ch.isalnum())
        return f"{family}{year or 'nd'}{first_word or 'untitled'}"
