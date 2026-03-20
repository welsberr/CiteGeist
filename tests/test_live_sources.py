from __future__ import annotations

import os

import pytest

from citegeist import MetadataResolver, SourceClient


pytestmark = pytest.mark.live


def _live_client() -> SourceClient:
    cache_dir = os.environ.get("CITEGEIST_SOURCE_CACHE", ".cache/citegeist")
    return SourceClient(
        cache_dir=cache_dir,
        fixtures_dir=os.environ.get("CITEGEIST_SOURCE_FIXTURES"),
    )


def test_live_crossref_doi_resolution():
    resolver = MetadataResolver(source_client=_live_client())

    resolution = resolver.resolve_doi("10.1038/nphys1170")

    assert resolution is not None
    assert resolution.entry.fields.get("doi") == "10.1038/nphys1170"
    assert resolution.entry.fields.get("title")


def test_live_arxiv_resolution():
    resolver = MetadataResolver(source_client=_live_client())

    resolution = resolver.resolve_arxiv("1706.03762")

    assert resolution is not None
    assert resolution.entry.fields.get("arxiv") == "1706.03762"
    assert resolution.entry.fields.get("title")


def test_live_openalex_title_search():
    resolver = MetadataResolver(source_client=_live_client())

    resolution = resolver.search_openalex_best_match(
        title="Attention Is All You Need",
        author_text="Ashish Vaswani",
        year="2017",
    )

    assert resolution is not None
    assert resolution.entry.fields.get("title")
    assert resolution.entry.fields.get("openalex")
