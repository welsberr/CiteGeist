"""
Bibliographic source plugins.

This package provides a plugin architecture for integrating multiple
bibliographic data sources (CrossRef, PubMed, Semantic Scholar, etc.).
"""

# Import old sources module for backward compatibility
from . import _old_sources_compat

# Import new plugin architecture
from citegeist.sources.base import BibliographicSource, SourceRecord, CitationEdge
from citegeist.sources.catalog import SourceCatalogEntry, list_source_catalog, prioritized_source_keys
from citegeist.sources.registry import SourceRegistry, get_registry
from citegeist.sources.crossref import CrossRefSource
from citegeist.sources.europepmc import EuropePmcSource
from citegeist.sources.opencitations import OpenCitationsSource
from citegeist.sources.openlibrary import OpenLibrarySource
from citegeist.sources.semanticscholar import SemanticScholarSource
from citegeist.sources.unpaywall import UnpaywallSource

# Re-export old classes for compatibility
__all__ = [
    # New plugin architecture
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
    # Old API (for backward compatibility)
    'SourceClient',
]

# Backward compatibility - make SourceClient available from this module
SourceClient = _old_sources_compat.SourceClient
