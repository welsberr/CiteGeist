"""
Backward compatibility module for old sources module.

This module re-exports the old SourceClient class for compatibility.
"""
from pathlib import Path
import importlib.util

from .base import BibliographicSource, SourceRecord, CitationEdge
from .registry import SourceRegistry, get_registry
from .crossref import CrossRefSource

# Load the old sources.py module from the citegeist package root
_OLD_SOURCES_PATH = Path(__file__).resolve().parents[1] / "sources.py"
spec = importlib.util.spec_from_file_location(
    "citegeist.sources_old",
    _OLD_SOURCES_PATH
)
if spec and spec.loader:
    old_sources = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old_sources)
    SourceClient = old_sources.SourceClient
else:
    # Fallback if old sources.py doesn't exist
    SourceClient = None
