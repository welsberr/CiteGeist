"""Tests for the source plugin architecture."""
from __future__ import annotations

import pytest

from citegeist.sources import BibliographicSource, SourceRegistry, CrossRefSource


class MockSource(BibliographicSource):
    """Mock source for testing."""
    
    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.lookup_calls = []
    
    def lookup_by_doi(self, doi: str) -> None:
        """Return None to indicate not found."""
        self.lookup_calls.append(('doi', doi))
        return None
    
    def lookup_by_title(self, title: str) -> None:
        """Return None to indicate not found."""
        self.lookup_calls.append(('title', title))
        return None
    
    def search(self, query: str, limit: int = 10) -> list:
        return []
    
    def normalize(self, record: dict) -> None:
        return None


def test_source_base_interface():
    """Test that BibliographicSource base class works."""
    source = MockSource()
    assert source.is_available()
    assert source.get_identifier_scheme() == 'mocksource'
    assert source.get_fulltext_url('doi:test') is None
    assert source.get_embedding('doi:test') is None


def test_mock_source():
    """Test that mock source implements interface correctly."""
    source = MockSource()
    source.lookup_by_doi('10.1234/test')
    source.lookup_by_title('Test Title')
    
    assert source.lookup_calls == [
        ('doi', '10.1234/test'),
        ('title', 'Test Title')
    ]


def test_source_registry():
    """Test source registry functionality."""
    registry = SourceRegistry()
    
    # Register a source
    registry.register(MockSource, name='mock_source', config={'enabled': True})
    
    # List sources
    sources = registry.list_sources()
    assert 'mock_source' in sources
    
    # Get source instance
    source = registry.get('mock_source')
    assert source is not None
    assert isinstance(source, MockSource)
    assert source.is_available()


def test_source_registry_disabled():
    """Test that disabled sources are not returned."""
    registry = SourceRegistry()
    
    registry.register(
        MockSource,
        name='disabled_source',
        config={'enabled': False}
    )
    
    sources = registry.list_sources()
    assert 'disabled_source' in sources
    
    # Getting disabled source should return None
    source = registry.get('disabled_source')
    assert source is None


def test_crossref_source():
    """Test CrossRef source plugin."""
    registry = SourceRegistry()
    registry.register(CrossRefSource, name='crossref', config={})
    
    source = registry.get('crossref')
    assert source is not None
    assert source.is_available()
    assert source.get_identifier_scheme() == 'doi'
    
    entry = source.normalize(
        {
            'message': {
                'DOI': '10.1234/example',
                'title': ['Test Title'],
                'author': [{'given': 'Jane', 'family': 'Doe'}],
                'published-print': {'date-parts': [[2024]]},
                'container-title': ['Journal of Tests'],
                'publisher': 'Test Publisher',
                'URL': 'https://doi.org/10.1234/example',
                'abstract': '<jats:p>Example abstract</jats:p>',
            }
        }
    )

    assert entry is not None
    assert entry.fields['doi'] == '10.1234/example'
    assert entry.fields['title'] == 'Test Title'
    assert entry.fields['year'] == '2024'
    assert entry.fields['journal'] == 'Journal of Tests'


def test_crossref_search_item_normalization():
    source = CrossRefSource()

    entry = source.normalize(
        {
            'DOI': '10.1234/example',
            'title': ['Search Result'],
            'author': [{'family': 'Doe'}],
            'issued': {'date-parts': [[2023]]},
        }
    )

    assert entry is not None
    assert entry.fields['doi'] == '10.1234/example'
    assert entry.fields['year'] == '2023'


def test_source_record():
    """Test SourceRecord dataclass."""
    from citegeist.sources import SourceRecord
    
    record = SourceRecord(
        raw={'test': 'data'},
        source_type='test',
        source_label='test_source',
        timestamp='2024-01-01',
        confidence=1.0
    )
    
    assert record.source_type == 'test'
    assert record.source_label == 'test_source'
    assert record.confidence == 1.0
    assert record.raw == {'test': 'data'}


def test_citation_edge():
    """Test CitationEdge dataclass."""
    from citegeist.sources import CitationEdge
    
    edge = CitationEdge(
        source_work_id='doi:10.1234',
        target_work_id='doi:10.5678',
        relation_type='cites',
        source_type='crossref',
        source_label='crossref:test',
        confidence=0.9
    )
    
    assert edge.relation_type == 'cites'
    assert edge.confidence == 0.9
