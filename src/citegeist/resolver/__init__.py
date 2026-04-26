"""
Identifier resolution and normalization module.

Provides functions for extracting, normalizing, and resolving
bibliographic identifiers across multiple schemes.
"""
from __future__ import annotations

from citegeist.resolver.identifiers import (
    IdentifierExtractor,
    IdentifierNormalizer,
    IdentifierResolver,
    extract_identifiers,
    normalize_identifier,
    get_primary_identifier,
    resolve_identifiers,
)

__all__ = [
    'IdentifierExtractor',
    'IdentifierNormalizer',
    'IdentifierResolver',
    'extract_identifiers',
    'normalize_identifier',
    'get_primary_identifier',
    'resolve_identifiers',
]
