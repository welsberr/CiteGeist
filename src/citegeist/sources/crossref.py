"""
CrossRef source plugin.

CrossRef provides metadata for DOIs for scholarly works.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.parse
from typing import Any, Dict, List, Optional

from citegeist.bibtex import BibEntry
from citegeist.sources.base import BibliographicSource


class CrossRefSource(BibliographicSource):
    """CrossRef source for DOI-based metadata lookup."""
    
    BASE_URL = "https://api.crossref.org"
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize CrossRef source.
        
        Args:
            config: Configuration with optional 'api_key'
        """
        super().__init__(config)
        self.api_key = self.config.get('api_key', '')
        self.user_agent = self.config.get(
            'user_agent',
            'citegeist/0.1 (local research tool)',
        )
    
    def lookup_by_doi(self, doi: str) -> Optional[BibEntry]:
        """Look up a work by DOI.
        
        Args:
            doi: Digital Object Identifier
            
        Returns:
            BibEntry if found, None otherwise
        """
        if not doi:
            return None
        
        encoded = urllib.parse.quote(doi, safe="")
        url = f"{self.BASE_URL}/works/{encoded}"
        headers = {'User-Agent': self.user_agent}
        if self.api_key:
            headers['X-Api-Key'] = self.api_key
        
        try:
            req = urllib.request.Request(url, headers=headers)
            response = urllib.request.urlopen(req)
            data = response.read().decode('utf-8')
            payload = json.loads(data)
            return self._normalize_crossref(payload)
        except Exception:
            return None
    
    def lookup_by_title(self, title: str) -> Optional[BibEntry]:
        """CrossRef doesn't support title-only lookup.
        
        Returns None as this is not a supported operation.
        """
        return None
    
    def search(self, query: str, limit: int = 10) -> List[BibEntry]:
        """Search CrossRef for works.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            List of matching BibEntry objects
        """
        if not query:
            return []
        
        encoded_query = urllib.parse.quote(query, safe="")
        url = f"{self.BASE_URL}/works?query={encoded_query}&rows={limit}"
        headers = {'User-Agent': self.user_agent}
        if self.api_key:
            headers['X-Api-Key'] = self.api_key
        
        try:
            req = urllib.request.Request(url, headers=headers)
            response = urllib.request.urlopen(req)
            data = response.read().decode('utf-8')
            payload = json.loads(data)
            items = payload.get('message', {}).get('items', [])
            return [entry for item in items if (entry := self._normalize_crossref(item)) is not None]
        except Exception:
            return []
    
    def normalize(self, record: Dict[str, Any]) -> Optional[BibEntry]:
        """Normalize a raw CrossRef record to a BibEntry.
        
        Args:
            record: Raw record from CrossRef API
            
        Returns:
            BibEntry if normalization succeeds
        """
        return self._normalize_crossref(record)
    
    def get_identifier_scheme(self) -> str:
        """Return 'doi' as the identifier scheme."""
        return 'doi'
    
    def _normalize_crossref(self, payload: Dict[str, Any]) -> Optional[BibEntry]:
        """Normalize a CrossRef payload to a BibEntry.
        
        Args:
            payload: Raw JSON payload from CrossRef
            
        Returns:
            BibEntry object
        """
        message = payload.get('message', payload)
        if not message:
            return None
        
        # Extract basic fields
        doi = str(message.get('DOI', ''))
        title = ' '.join(message.get('title', [])) if message.get('title') else ''
        author_data = message.get('author', [])
        year = self._extract_year(message)
        
        # Format authors
        authors = []
        for author in author_data:
            given = str(author.get('given', ''))
            family = str(author.get('family', ''))
            if given and family:
                authors.append(f"{given} {family}")
            elif family:
                authors.append(family)
        
        # Get publisher
        publisher = str(message.get('publisher', ''))
        
        # Get journal info
        container_title = message.get('container-title', [])
        journal = container_title[0] if container_title else ''
        
        # Get URL
        url = str(message.get('URL', ''))
        
        # Get abstract
        abstract = self._extract_abstract(message.get('abstract'))
        
        # Map to BibEntry
        fields: Dict[str, str] = {}
        if title:
            fields['title'] = title
        if authors:
            fields['author'] = ' and '.join(authors)
        if year:
            fields['year'] = year
        if doi:
            fields['doi'] = doi
        if journal:
            fields['journal'] = journal
        if publisher:
            fields['publisher'] = publisher
        if url:
            fields['url'] = url
        if abstract:
            fields['abstract'] = abstract
        
        citation_key = f"{authors[0] if authors else 'crossref'}_{year or 'n.d.'}_{title or doi}"
        
        return BibEntry(
            entry_type='article',
            citation_key=citation_key,
            fields=fields
        )

    def _extract_year(self, message: Dict[str, Any]) -> str:
        for field_name in ('published-print', 'published-online', 'issued', 'created'):
            year = self._extract_year_from_date_parts(message.get(field_name, {}))
            if year:
                return year
        return ''

    def _extract_year_from_date_parts(self, field: Dict[str, Any]) -> str:
        date_parts = field.get('date-parts', [])
        if not date_parts:
            return ''
        first_part = date_parts[0]
        if not first_part:
            return ''
        year = first_part[0]
        return str(year) if year else ''

    def _extract_abstract(self, raw_abstract: Any) -> str:
        if isinstance(raw_abstract, str):
            return raw_abstract.strip()
        if isinstance(raw_abstract, list):
            for item in raw_abstract:
                if isinstance(item, dict):
                    text = str(item.get('value', '')).strip()
                    if text:
                        return text
                elif isinstance(item, str) and item.strip():
                    return item.strip()
        return ''
