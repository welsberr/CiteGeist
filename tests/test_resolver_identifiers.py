"""Tests for identifier resolution and normalization."""
from __future__ import annotations

import pytest

from citegeist.resolver import (
    IdentifierExtractor,
    IdentifierNormalizer,
    IdentifierResolver,
    extract_identifiers,
    normalize_identifier,
    get_primary_identifier,
    resolve_identifiers,
)


class TestIdentifierExtractor:
    """Test IdentifierExtractor class."""
    
    def test_extract_from_entry(self):
        """Test extracting identifiers from entry fields."""
        fields = {
            'doi': '10.1234/example',
            'title': 'Test Title',
            'author': 'John Doe',
            'pmid': '123456',
        }
        
        identifiers = IdentifierExtractor.extract(fields)
        
        assert 'doi' in identifiers
        assert identifiers['doi'] == '10.1234/example'
        assert 'pmid' in identifiers
        assert identifiers['pmid'] == '123456'
        assert 'title' not in identifiers  # Title is not an identifier
    
    def test_extract_multiple_identifiers(self):
        """Test extracting multiple identifiers."""
        fields = {
            'doi': '10.1234/example',
            'pmid': '123456',
            'arxiv': '2310.12345',
            'isbn': '978-0-123456-78-9',
        }
        
        identifiers = IdentifierExtractor.extract(fields)
        
        assert len(identifiers) == 4
        assert identifiers['doi'] == '10.1234/example'
        assert identifiers['pmid'] == '123456'
        assert identifiers['arxiv'] == '2310.12345'
        assert identifiers['isbn'] == '978-0-123456-78-9'


class TestIdentifierNormalizer:
    """Test IdentifierNormalizer class."""
    
    def test_normalize_doi(self):
        """Test DOI normalization."""
        assert IdentifierNormalizer.normalize_doi('10.1234/EXAMPLE') == '10.1234/example'
        assert IdentifierNormalizer.normalize_doi('10.1234/test') == '10.1234/test'
        assert IdentifierNormalizer.normalize_doi('invalid') is None
    
    def test_normalize_pmid(self):
        """Test PMID normalization."""
        assert IdentifierNormalizer.normalize_pmid('12345') == '12345'
        assert IdentifierNormalizer.normalize_pmid('1234567') == '1234567'
        assert IdentifierNormalizer.normalize_pmid('invalid') is None
    
    def test_normalize_pmcid(self):
        """Test PMCID normalization."""
        assert IdentifierNormalizer.normalize_pmcid('PMC12345') == 'pmc12345'
        assert IdentifierNormalizer.normalize_pmcid('PMCabcdef') == 'pmcabcdef'
        assert IdentifierNormalizer.normalize_pmcid('invalid') is None
    
    def test_normalize_arxiv(self):
        """Test arXiv normalization."""
        assert IdentifierNormalizer.normalize_arxiv('2310.12345') == '2310.12345'
        assert IdentifierNormalizer.normalize_arxiv('2310.12345v1') == '2310.12345'
        assert IdentifierNormalizer.normalize_arxiv('INVALID') is None
    
    def test_normalize_orcid(self):
        """Test ORCID normalization."""
        assert IdentifierNormalizer.normalize_orcid('0000-0001-2345-6789') == '0000-0001-2345-6789'
        # ORCID with spaces is invalid according to the canonical format
        assert IdentifierNormalizer.normalize_orcid('0000 0001 2345 6789') is None
        assert IdentifierNormalizer.normalize_orcid('invalid') is None
    
    def test_normalize_identifier(self):
        """Test generic identifier normalization."""
        result = IdentifierNormalizer.normalize_identifier('doi', '10.1234/test')
        assert result == ('doi', '10.1234/test')
        
        result = IdentifierNormalizer.normalize_identifier('pmid', '12345')
        assert result == ('pmid', '12345')
        
        result = IdentifierNormalizer.normalize_identifier('invalid', 'value')
        assert result is None


class TestIdentifierResolver:
    """Test IdentifierResolver class."""
    
    def test_resolve_with_doi(self):
        """Test resolving with DOI."""
        fields = {'doi': '10.1234/example', 'title': 'Test Title'}
        
        resolved = IdentifierResolver.resolve(fields)
        
        assert len(resolved) >= 1
        doi_resolved = [r for r in resolved if r[0] == 'doi']
        assert len(doi_resolved) > 0
    
    def test_resolve_with_multiple_identifiers(self):
        """Test resolving with multiple identifiers."""
        fields = {
            'doi': '10.1234/example',
            'pmid': '12345',
            'arxiv': '2310.12345',
        }
        
        resolved = IdentifierResolver.resolve(fields)
        
        assert len(resolved) >= 2
        doi_resolved = [r for r in resolved if r[0] == 'doi']
        assert len(doi_resolved) > 0
    
    def test_resolve_without_identifiers(self):
        """Test resolving without identifiers."""
        fields = {'title': 'Test Title', 'author': 'John Doe'}
        
        resolved = IdentifierResolver.resolve(fields)
        
        # Should have at least title fingerprint
        assert len(resolved) >= 1
        title_resolved = [r for r in resolved if r[0] == 'title']
        assert len(title_resolved) > 0
    
    def test_get_primary_identifier(self):
        """Test getting primary identifier."""
        fields = {
            'doi': '10.1234/example',
            'pmid': '12345',
            'title': 'Test Title',
        }
        
        primary = IdentifierResolver.get_primary_identifier(fields)
        
        assert primary is not None
        # DOI should be first priority
        assert primary[0] == 'doi'
    
    def test_get_scheme_value(self):
        """Test getting specific scheme value."""
        fields = {
            'doi': '10.1234/example',
            'pmid': '12345',
        }
        
        doi = IdentifierResolver.get_scheme_value('doi', fields)
        assert doi == '10.1234/example'
        
        pmid = IdentifierResolver.get_scheme_value('pmid', fields)
        assert pmid == '12345'
        
        isbn = IdentifierResolver.get_scheme_value('isbn', fields)
        assert isbn is None


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_extract_identifiers(self):
        """Test extract_identifiers function."""
        fields = {'doi': '10.1234/example', 'pmid': '12345'}
        
        identifiers = extract_identifiers(fields)
        
        assert 'doi' in identifiers
        assert 'pmid' in identifiers
    
    def test_normalize_identifier(self):
        """Test normalize_identifier function."""
        result = normalize_identifier('doi', '10.1234/test')
        assert result == ('doi', '10.1234/test')
    
    def test_get_primary_identifier(self):
        """Test get_primary_identifier function."""
        fields = {'doi': '10.1234/example'}
        
        primary = get_primary_identifier(fields)
        
        assert primary == ('doi', '10.1234/example')
    
    def test_resolve_identifiers(self):
        """Test resolve_identifiers function."""
        fields = {'doi': '10.1234/example'}
        
        resolved = resolve_identifiers(fields)
        
        assert len(resolved) > 0
