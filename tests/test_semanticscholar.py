from __future__ import annotations

from citegeist.resolve import MetadataResolver
from citegeist.sources import SemanticScholarSource, SourceRegistry, list_source_catalog


def test_semanticscholar_source_normalizes_record() -> None:
    source = SemanticScholarSource(config={})
    entry = source.normalize(
        {
            "paperId": "abcdef123456",
            "title": "Physics Example",
            "year": 2024,
            "abstract": "Abstract text.",
            "authors": [{"name": "Jane Doe"}, {"name": "Alex Roe"}],
            "externalIds": {"DOI": "10.1000/physics"},
            "journal": {"name": "Physical Review Example"},
            "openAccessPdf": {"url": "https://example.org/paper.pdf"},
            "citationCount": 42,
            "publicationTypes": ["JournalArticle"],
        }
    )

    assert entry is not None
    assert entry.fields["doi"] == "10.1000/physics"
    assert entry.fields["author"] == "Jane Doe and Alex Roe"
    assert entry.fields["journal"] == "Physical Review Example"
    assert entry.fields["url"] == "https://example.org/paper.pdf"
    assert entry.fields["is_oa"] == "true"
    assert entry.fields["semanticscholar_citation_count"] == "42"


def test_semanticscholar_registry_and_catalog() -> None:
    registry = SourceRegistry()
    registry.from_config_dict(
        {
            "sources": {
                "semanticscholar": {
                    "source_type": "semanticscholar",
                    "enabled": True,
                }
            }
        }
    )
    source = registry.get("semanticscholar")
    assert isinstance(source, SemanticScholarSource)

    catalog = {entry.key: entry for entry in list_source_catalog()}
    assert catalog["semantic_scholar"].current_status == "integrated"
    assert catalog["semantic_scholar"].priority == "now"


def test_metadata_resolver_uses_semanticscholar_doi_after_other_lookups_fail() -> None:
    resolver = MetadataResolver()
    resolver.resolve_doi = lambda _doi: None  # type: ignore[method-assign]
    resolver.resolve_datacite_doi = lambda _doi: None  # type: ignore[method-assign]
    resolver.resolve_europepmc_doi = lambda _doi: None  # type: ignore[method-assign]
    resolver.semanticscholar.lookup_by_doi = lambda _doi: resolver.semanticscholar.normalize(  # type: ignore[method-assign]
        {
            "paperId": "abcdef123456",
            "title": "Physics Example",
            "year": 2024,
            "authors": [{"name": "Jane Doe"}],
            "externalIds": {"DOI": "10.1000/physics"},
            "journal": {"name": "Physical Review Example"},
            "publicationTypes": ["JournalArticle"],
        }
    )

    from citegeist.bibtex import BibEntry

    result = resolver.resolve_entry(
        BibEntry(
            entry_type="article",
            citation_key="seed2024",
            fields={"doi": "10.1000/physics", "title": "Physics Example"},
        )
    )

    assert result is not None
    assert result.source_label == "semanticscholar:doi:10.1000/physics"
    assert result.entry.fields["journal"] == "Physical Review Example"


def test_metadata_resolver_uses_semanticscholar_title_search_after_other_searches_fail() -> None:
    resolver = MetadataResolver()
    resolver.search_crossref_best_match = lambda *args, **kwargs: None  # type: ignore[method-assign]
    resolver.search_datacite_best_match = lambda *args, **kwargs: None  # type: ignore[method-assign]
    resolver.search_openalex_best_match = lambda *args, **kwargs: None  # type: ignore[method-assign]
    resolver.search_pubmed_best_match = lambda *args, **kwargs: None  # type: ignore[method-assign]
    resolver.search_europepmc_best_match = lambda *args, **kwargs: None  # type: ignore[method-assign]
    resolver.semanticscholar.search = lambda _title, limit=5: [  # type: ignore[method-assign]
        resolver.semanticscholar.normalize(
            {
                "paperId": "abcdef123456",
                "title": "Physics Example",
                "year": 2024,
                "authors": [{"name": "Jane Doe"}],
                "externalIds": {"DOI": "10.1000/physics"},
                "journal": {"name": "Physical Review Example"},
                "publicationTypes": ["JournalArticle"],
            }
        )
    ]

    from citegeist.bibtex import BibEntry

    result = resolver.resolve_entry(
        BibEntry(
            entry_type="article",
            citation_key="seed2024",
            fields={"title": "Physics Example", "author": "Jane Doe", "year": "2024"},
        )
    )

    assert result is not None
    assert result.source_label == "semanticscholar:search:Physics Example"
