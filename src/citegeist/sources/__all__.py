"""Export all source plugins."""
from __future__ import annotations

from citegeist.sources.base import BibliographicSource, SourceRecord, CitationEdge
from citegeist.sources.catalog import SourceCatalogEntry, list_source_catalog, prioritized_source_keys
from citegeist.sources.registry import SourceRegistry, get_registry
from citegeist.sources.crossref import CrossRefSource
from citegeist.sources.europepmc import EuropePmcSource
from citegeist.sources.opencitations import OpenCitationsSource
from citegeist.sources.openlibrary import OpenLibrarySource
from citegeist.sources.semanticscholar import SemanticScholarSource
from citegeist.sources.unpaywall import UnpaywallSource

__all__ = [
    'BibliographicSource',
    'SourceRecord',
    'CitationEdge',
    'SourceCatalogEntry',
    'SourceRegistry',
    'get_registry',
    'list_source_catalog',
    'prioritized_source_keys',
    'CrossRefSource',
    'EuropePmcSource',
    'OpenCitationsSource',
    'OpenLibrarySource',
    'SemanticScholarSource',
    'UnpaywallSource',
]
