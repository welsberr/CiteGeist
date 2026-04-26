"""
Identifier resolution and normalization module.

This module provides functions for extracting, normalizing, and resolving
bibliographic identifiers across multiple schemes (DOI, PMID, arXiv, ORCID, etc.).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


# Identifier scheme patterns
DOI_PATTERN = re.compile(
    r'^10\.\d{4,9}/\S+$',
    re.IGNORECASE
)

PMID_PATTERN = re.compile(r'^\d{5,7}$')

PMCID_PATTERN = re.compile(
    r'^PMC\d+$|^PMC[0-9a-f]+$', 
    re.IGNORECASE
)

ARXIV_PATTERN = re.compile(
    r'^\d{4}\.\d{4,5}(v\d+)?$',
    re.IGNORECASE
)

ORCID_PATTERN = re.compile(
    r'^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$',
    re.IGNORECASE
)

ROR_PATTERN = re.compile(
    r'^https?://ror\.org/[0-9A-Z]{4,10}$'
)

DBLP_PATTERN = re.compile(
    r'^[a-zA-Z0-9_]+:[a-zA-Z0-9_]+$', 
    re.IGNORECASE
)

OPENALEX_PATTERN = re.compile(
    r'^W[0-9]{4}-[A-F0-9]{4}$',
    re.IGNORECASE
)


class IdentifierExtractor:
    """Extract identifiers from BibEntry fields."""
    
    @staticmethod
    def extract(entry_fields: Dict[str, str]) -> Dict[str, str]:
        """Extract all identifier schemes from entry fields.
        
        Args:
            entry_fields: Dictionary of entry fields
            
        Returns:
            Dictionary mapping scheme names to values
        """
        identifiers = {}
        
        # DOI
        if doi := entry_fields.get('doi'):
            identifiers['doi'] = doi
        
        # PMID
        if pmid := entry_fields.get('pmid'):
            identifiers['pmid'] = pmid
        
        # PMCID
        if pmcid := entry_fields.get('pmcid'):
            identifiers['pmcid'] = pmcid
        
        # arXiv
        if arxiv := entry_fields.get('arxiv'):
            identifiers['arxiv'] = arxiv
        
        # DBLP
        if dblp := entry_fields.get('dblp'):
            identifiers['dblp'] = dblp
        
        # OpenAlex
        if openalex := entry_fields.get('openalex'):
            identifiers['openalex'] = openalex
        
        # ISBN
        if isbn := entry_fields.get('isbn'):
            identifiers['isbn'] = isbn
        
        # ISSN
        if issn := entry_fields.get('issn'):
            identifiers['issn'] = issn
        
        return identifiers


class IdentifierNormalizer:
    """Normalize identifiers to canonical form."""
    
    @staticmethod
    def normalize_doi(doi: str) -> Optional[str]:
        """Normalize DOI to lowercase.
        
        Args:
            doi: DOI string
            
        Returns:
            Lowercase DOI, or None if invalid
        """
        if not doi:
            return None
        normalized = doi.strip().lower()
        if DOI_PATTERN.match(normalized):
            return normalized
        return None
    
    @staticmethod
    def normalize_pmid(pmid: str) -> Optional[str]:
        """Normalize PMID to string.
        
        Args:
            pmid: PMID string
            
        Returns:
            PMID string, or None if invalid
        """
        if not pmid:
            return None
        pmid_str = str(pmid).strip()
        if PMID_PATTERN.match(pmid_str):
            return pmid_str
        return None
    
    @staticmethod
    def normalize_pmcid(pmcid: str) -> Optional[str]:
        """Normalize PMCID to lowercase.
        
        Args:
            pmcid: PMCID string
            
        Returns:
            Lowercase PMCID, or None if invalid
        """
        if not pmcid:
            return None
        normalized = pmcid.strip().lower()
        if PMCID_PATTERN.match(normalized):
            return normalized
        return None
    
    @staticmethod
    def normalize_arxiv(arxiv: str) -> Optional[str]:
        """Normalize arXiv ID.
        
        Args:
            arxiv: arXiv ID string
            
        Returns:
            Normalized arXiv ID, or None if invalid
        """
        if not arxiv:
            return None
        # Remove 'v' and version suffix if present
        normalized = arxiv.strip().lower()
        if 'v' in normalized:
            normalized = normalized.split('v')[0]
        if ARXIV_PATTERN.match(normalized):
            return normalized
        return None
    
    @staticmethod
    def normalize_orcid(orcid: str) -> Optional[str]:
        """Normalize ORCID to canonical format.
        
        Args:
            orcid: ORCID string
            
        Returns:
            Normalized ORCID (XXXX-XXXX-XXXX-XXX0), or None if invalid
        """
        if not orcid:
            return None
        orcid = orcid.strip().upper().replace(' ', '')
        if ORCID_PATTERN.match(orcid):
            return orcid
        return None
    
    @staticmethod
    def normalize_ror(ror_url: str) -> Optional[str]:
        """Normalize ROR URL to identifier.
        
        Args:
            ror_url: ROR URL string
            
        Returns:
            ROR identifier, or None if invalid
        """
        if not ror_url:
            return None
        ror_id = ror_url.strip().lower()
        if ROR_PATTERN.match(ror_id):
            return ror_id
        return None
    
    @staticmethod
    def normalize_dblp(dblp_key: str) -> Optional[str]:
        """Normalize DBLP key.
        
        Args:
            dblp_key: DBLP key string
            
        Returns:
            DBLP key, or None if invalid
        """
        if not dblp_key:
            return None
        dblp = dblp_key.strip()
        if DBLP_PATTERN.match(dblp):
            return dblp
        return None
    
    @staticmethod
    def normalize_openalex(openalex_id: str) -> Optional[str]:
        """Normalize OpenAlex ID.
        
        Args:
            openalex_id: OpenAlex ID string
            
        Returns:
            OpenAlex ID, or None if invalid
        """
        if not openalex_id:
            return None
        openalex = openalex_id.strip().upper()
        if OPENALEX_PATTERN.match(openalex):
            return openalex
        return None
    
    @staticmethod
    def normalize_identifier(scheme: str, value: str) -> Optional[Tuple[str, str]]:
        """Normalize an identifier.
        
        Args:
            scheme: Identifier scheme name
            value: Identifier value
            
        Returns:
            Tuple of (scheme, normalized_value), or None if invalid
        """
        scheme = scheme.lower()
        
        normalizers = {
            'doi': IdentifierNormalizer.normalize_doi,
            'pmid': IdentifierNormalizer.normalize_pmid,
            'pmcid': IdentifierNormalizer.normalize_pmcid,
            'arxiv': IdentifierNormalizer.normalize_arxiv,
            'orcid': IdentifierNormalizer.normalize_orcid,
            'ror': IdentifierNormalizer.normalize_ror,
            'dblp': IdentifierNormalizer.normalize_dblp,
            'openalex': IdentifierNormalizer.normalize_openalex,
        }
        
        normalizer = normalizers.get(scheme)
        if normalizer:
            normalized = normalizer(value)
            if normalized:
                return (scheme, normalized)
        return None


class IdentifierResolver:
    """Resolve identifiers across multiple schemes."""
    
    # Lookup priority: schemes should be checked in this order
    LOOKUP_PRIORITY = [
        ('doi', IdentifierNormalizer.normalize_doi),
        ('pmid', IdentifierNormalizer.normalize_pmid),
        ('pmcid', IdentifierNormalizer.normalize_pmcid),
        ('arxiv', IdentifierNormalizer.normalize_arxiv),
        ('dblp', IdentifierNormalizer.normalize_dblp),
        ('openalex', IdentifierNormalizer.normalize_openalex),
    ]
    
    @staticmethod
    def resolve(entry_fields: Dict[str, str]) -> List[Tuple[str, str]]:
        """Resolve identifiers from entry fields.
        
        Args:
            entry_fields: Dictionary of entry fields
            
        Returns:
            List of (scheme, normalized_value) tuples in priority order
        """
        identifiers = IdentifierExtractor.extract(entry_fields)
        resolved = []
        
        for scheme, value in identifiers.items():
            if normalized := IdentifierNormalizer.normalize_identifier(scheme, value):
                resolved.append(normalized)
        
        # Add title fingerprint as fallback
        if title := entry_fields.get('title'):
            fingerprint = IdentifierResolver._create_title_fingerprint(title)
            if fingerprint:
                resolved.append(('title', fingerprint))
        
        return resolved
    
    @staticmethod
    def _create_title_fingerprint(title: str) -> Optional[str]:
        """Create a fingerprint from title for fallback lookup.
        
        Args:
            title: Work title
            
        Returns:
            Fingerprint string
        """
        if not title:
            return None
        
        # Remove common words, punctuation, and normalize
        words = title.lower()
        words = re.sub(r'[^\w\s]', ' ', words)  # Remove punctuation
        words = re.sub(r'\s+', ' ', words)  # Normalize whitespace
        words = words.strip()
        
        return words
    
    @staticmethod
    def get_primary_identifier(entry_fields: Dict[str, str]) -> Optional[Tuple[str, str]]:
        """Get the primary identifier (first in priority order).
        
        Args:
            entry_fields: Dictionary of entry fields
            
        Returns:
            Tuple of (scheme, value), or None if no identifier found
        """
        resolved = IdentifierResolver.resolve(entry_fields)
        
        for scheme, _ in IdentifierResolver.LOOKUP_PRIORITY:
            # Find this scheme in resolved identifiers
            for rscheme, rvalue in resolved:
                if rscheme == scheme:
                    return (rscheme, rvalue)
        
        return None
    
    @staticmethod
    def get_scheme_value(scheme: str, entry_fields: Dict[str, str]) -> Optional[str]:
        """Get a specific identifier value from entry fields.
        
        Args:
            scheme: Identifier scheme name
            entry_fields: Dictionary of entry fields
            
        Returns:
            Identifier value, or None if not found
        """
        if value := entry_fields.get(scheme):
            if normalized := IdentifierNormalizer.normalize_identifier(scheme, value):
                return normalized[1]
        return None


# Convenience functions
def extract_identifiers(entry_fields: Dict[str, str]) -> Dict[str, str]:
    """Extract all identifiers from entry fields.
    
    Args:
        entry_fields: Dictionary of entry fields
        
    Returns:
        Dictionary mapping scheme names to values
    """
    return IdentifierExtractor.extract(entry_fields)


def normalize_identifier(scheme: str, value: str) -> Optional[Tuple[str, str]]:
    """Normalize an identifier.
    
    Args:
        scheme: Identifier scheme name
        value: Identifier value
        
    Returns:
        Tuple of (scheme, normalized_value), or None if invalid
    """
    return IdentifierNormalizer.normalize_identifier(scheme, value)


def get_primary_identifier(entry_fields: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """Get the primary identifier.
    
    Args:
        entry_fields: Dictionary of entry fields
        
    Returns:
        Tuple of (scheme, value), or None if no identifier found
    """
    return IdentifierResolver.get_primary_identifier(entry_fields)


def resolve_identifiers(entry_fields: Dict[str, str]) -> List[Tuple[str, str]]:
    """Resolve identifiers from entry fields.
    
    Args:
        entry_fields: Dictionary of entry fields
        
    Returns:
        List of (scheme, value) tuples
    """
    return IdentifierResolver.resolve(entry_fields)
