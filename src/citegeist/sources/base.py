"""
Base interface for bibliographic sources.

This module defines the abstract base class that all source plugins must implement.
Plugins can register themselves with the SourceRegistry for dynamic loading.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from citegeist.bibtex import BibEntry


@dataclass(slots=True)
class SourceRecord:
    """Represents a raw record from a source API."""
    raw: Dict[str, Any]
    source_type: str
    source_label: str
    timestamp: str
    confidence: float


@dataclass(slots=True)
class CitationEdge:
    """Represents a citation relationship."""
    source_work_id: str
    target_work_id: str
    relation_type: str  # "cites" or "cited_by"
    source_type: str
    source_label: str
    confidence: float


class BibliographicSource(ABC):
    """Abstract base class for bibliographic data sources.
    
    All source plugins must inherit from this class and implement the required methods.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the source with optional configuration.
        
        Args:
            config: Source-specific configuration dictionary
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        self.source_type = self.config.get('source_type', self.__class__.__name__)
    
    @abstractmethod
    def lookup_by_doi(self, doi: str) -> Optional[BibEntry]:
        """Look up a work by DOI.
        
        Args:
            doi: Digital Object Identifier
            
        Returns:
            BibEntry if found, None otherwise
        """
        pass
    
    @abstractmethod
    def lookup_by_title(self, title: str) -> Optional[BibEntry]:
        """Look up a work by title.
        
        Args:
            title: Work title
            
        Returns:
            BibEntry if found, None otherwise
        """
        pass
    
    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[BibEntry]:
        """Search for works matching the query.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            List of matching BibEntry objects
        """
        pass
    
    @abstractmethod
    def normalize(self, record: Dict[str, Any]) -> Optional[BibEntry]:
        """Normalize a raw API record to a canonical BibEntry.
        
        Args:
            record: Raw record from source API
            
        Returns:
            BibEntry if normalization succeeds, None otherwise
        """
        pass
    
    def get_citations(self, work_id: str, relation_type: str = 'cites', limit: int = 10) -> List[CitationEdge]:
        """Get citations for a work.
        
        Args:
            work_id: Work identifier (DOI, PMID, etc.)
            relation_type: Type of relation ('cites' or 'cited_by')
            limit: Maximum number of results
            
        Returns:
            List of CitationEdge objects
        """
        return []
    
    def get_related(self, work_id: str, limit: int = 10) -> List[BibEntry]:
        """Get works related to a work.
        
        Args:
            work_id: Work identifier
            limit: Maximum number of results
            
        Returns:
            List of related BibEntry objects
        """
        return []
    
    def get_fulltext_url(self, doi: str) -> Optional[str]:
        """Get full-text URL for a work.
        
        Args:
            doi: Digital Object Identifier
            
        Returns:
            Full-text URL if available, None otherwise
        """
        return None
    
    def get_embedding(self, work_id: str) -> Optional[List[float]]:
        """Get embedding vector for a work.
        
        Args:
            work_id: Work identifier
            
        Returns:
            Embedding vector if available, None otherwise
        """
        return None
    
    def get_identifier_scheme(self) -> str:
        """Get the identifier scheme used by this source.
        
        Returns:
            Identifier scheme (e.g., 'doi', 'pmid', 'openalex')
        """
        return self.source_type.lower()
    
    def record_source_metadata(self, entry: BibEntry, operation: str = 'ingest') -> SourceRecord:
        """Create a source record for provenance tracking.
        
        Args:
            entry: The BibEntry to record
            operation: Operation type (e.g., 'ingest', 'enrich')
            
        Returns:
            SourceRecord with metadata
        """
        return SourceRecord(
            raw=self._entry_to_dict(entry),
            source_type=self.source_type,
            source_label=f"{self.source_type}:{self.config.get('name', self.__class__.__name__)}",
            timestamp='',
            confidence=1.0
        )
    
    def _entry_to_dict(self, entry: BibEntry) -> Dict[str, Any]:
        """Convert BibEntry to dictionary for source records."""
        return {
            'entry_type': entry.entry_type,
            'citation_key': entry.citation_key,
            'fields': entry.fields
        }
    
    def is_available(self) -> bool:
        """Check if the source is available and enabled.
        
        Returns:
            True if enabled and available, False otherwise
        """
        return self.enabled
