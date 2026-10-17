"""Backward-compatible public facade for the canonical resolver identifiers."""

from .resolver.identifiers import entry_identifiers, extract_arxiv, extract_doi

__all__ = ["entry_identifiers", "extract_arxiv", "extract_doi"]
