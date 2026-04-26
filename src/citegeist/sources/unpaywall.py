"""Unpaywall source plugin."""
from __future__ import annotations

import os
import urllib.parse
from typing import Any, Dict, Optional

from citegeist.bibtex import BibEntry
from citegeist.sources._old_sources_compat import SourceClient
from citegeist.sources.base import BibliographicSource


class UnpaywallSource(BibliographicSource):
    """Unpaywall source for DOI-based OA link enrichment."""

    BASE_URL = "https://api.unpaywall.org/v2"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        user_agent = self.config.get("user_agent", "citegeist/0.1 (local research tool)")
        self.source_client = self.config.get("source_client") or SourceClient(user_agent=user_agent)
        self.email = str(
            self.config.get("email")
            or os.environ.get("UNPAYWALL_EMAIL")
            or os.environ.get("NCBI_EMAIL")
            or ""
        ).strip()

    def lookup_by_doi(self, doi: str) -> Optional[BibEntry]:
        payload = self.lookup_oa_record(doi)
        if not payload:
            return None
        return self.normalize(payload)

    def lookup_by_title(self, title: str) -> Optional[BibEntry]:
        return None

    def search(self, query: str, limit: int = 10) -> list[BibEntry]:
        return []

    def normalize(self, record: Dict[str, Any]) -> Optional[BibEntry]:
        doi = str(record.get("doi") or "").strip()
        title = str(record.get("title") or "").strip() or (doi and f"OA record for DOI {doi}")
        if not doi or not title:
            return None

        fields: Dict[str, str] = {
            "title": title,
            "doi": doi,
        }
        if year := str(record.get("year") or "").strip():
            fields["year"] = year
        if landing_url := self._best_landing_url(record):
            fields["url"] = landing_url
            fields["best_oa_url"] = landing_url
        if pdf_url := self._best_pdf_url(record):
            fields["best_oa_pdf_url"] = pdf_url
        if oa_status := str(record.get("oa_status") or "").strip():
            fields["oa_status"] = oa_status
        if license_name := self._best_license(record):
            fields["oa_license"] = license_name
        if host_type := self._best_host_type(record):
            fields["oa_host_type"] = host_type
        if version := self._best_version(record):
            fields["oa_version"] = version
        if evidence := self._best_evidence(record):
            fields["oa_evidence"] = evidence
        if record.get("is_oa") is not None:
            fields["is_oa"] = "true" if bool(record.get("is_oa")) else "false"

        citation_key = "doi" + "".join(ch for ch in doi.lower() if ch.isalnum())
        return BibEntry(entry_type="misc", citation_key=citation_key, fields=fields)

    def get_fulltext_url(self, doi: str) -> Optional[str]:
        payload = self.lookup_oa_record(doi)
        if not payload:
            return None
        return self._best_pdf_url(payload) or self._best_landing_url(payload)

    def get_identifier_scheme(self) -> str:
        return "doi"

    def is_available(self) -> bool:
        return self.enabled and bool(self.email)

    def lookup_oa_record(self, doi: str) -> Dict[str, Any] | None:
        normalized = doi.strip()
        if not normalized or not self.email:
            return None
        encoded = urllib.parse.quote(normalized, safe="")
        query = urllib.parse.urlencode({"email": self.email})
        return self.source_client.try_get_json(f"{self.BASE_URL}/{encoded}?{query}")

    def _best_landing_url(self, payload: Dict[str, Any]) -> str:
        location = payload.get("best_oa_location") or {}
        return str(location.get("url") or location.get("url_for_landing_page") or "").strip()

    def _best_pdf_url(self, payload: Dict[str, Any]) -> str:
        location = payload.get("best_oa_location") or {}
        return str(location.get("url_for_pdf") or "").strip()

    def _best_license(self, payload: Dict[str, Any]) -> str:
        location = payload.get("best_oa_location") or {}
        return str(location.get("license") or "").strip()

    def _best_host_type(self, payload: Dict[str, Any]) -> str:
        location = payload.get("best_oa_location") or {}
        return str(location.get("host_type") or "").strip()

    def _best_version(self, payload: Dict[str, Any]) -> str:
        location = payload.get("best_oa_location") or {}
        return str(location.get("version") or "").strip()

    def _best_evidence(self, payload: Dict[str, Any]) -> str:
        location = payload.get("best_oa_location") or {}
        return str(location.get("evidence") or "").strip()
