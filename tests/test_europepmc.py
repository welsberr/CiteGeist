from __future__ import annotations

from citegeist.resolve import MetadataResolver
from citegeist.sources import EuropePmcSource, SourceRegistry, list_source_catalog


def test_europepmc_source_normalizes_core_record() -> None:
    source = EuropePmcSource(config={})
    entry = source.normalize(
        {
            "id": "37158217",
            "source": "MED",
            "pmid": "37158217",
            "pmcid": "PMC10000001",
            "doi": "10.1000/example",
            "title": "Biomedical Example",
            "authorString": "Doe J, Roe A",
            "journalTitle": "Biomed Journal",
            "pubYear": "2024",
            "journalVolume": "16",
            "issue": "1",
            "pageInfo": "10-20",
            "abstractText": "Abstract text.",
            "isOpenAccess": "Y",
            "citedByCount": 12,
            "fullTextUrlList": {"fullTextUrl": [{"url": "https://europepmc.org/articles/PMC10000001?pdf=render"}]},
        }
    )

    assert entry is not None
    assert entry.fields["doi"] == "10.1000/example"
    assert entry.fields["pmid"] == "37158217"
    assert entry.fields["pmcid"] == "PMC10000001"
    assert entry.fields["journal"] == "Biomed Journal"
    assert entry.fields["url"] == "https://europepmc.org/articles/PMC10000001?pdf=render"
    assert entry.fields["is_oa"] == "true"


def test_europepmc_registry_and_catalog() -> None:
    registry = SourceRegistry()
    registry.from_config_dict(
        {
            "sources": {
                "europepmc": {
                    "source_type": "europepmc",
                    "enabled": True,
                }
            }
        }
    )
    source = registry.get("europepmc")
    assert isinstance(source, EuropePmcSource)

    catalog = {entry.key: entry for entry in list_source_catalog()}
    assert catalog["europe_pmc"].current_status == "integrated"
    assert catalog["europe_pmc"].priority == "now"


def test_metadata_resolver_uses_europepmc_doi_after_primary_lookups_fail() -> None:
    resolver = MetadataResolver()
    resolver.resolve_doi = lambda _doi: None  # type: ignore[method-assign]
    resolver.resolve_datacite_doi = lambda _doi: None  # type: ignore[method-assign]
    resolver.europepmc.lookup_by_doi = lambda _doi: resolver.europepmc.normalize(  # type: ignore[method-assign]
        {
            "id": "37158217",
            "source": "MED",
            "pmid": "37158217",
            "doi": "10.1000/example",
            "title": "Biomedical Example",
            "authorString": "Doe J, Roe A",
            "journalTitle": "Biomed Journal",
            "pubYear": "2024",
        }
    )

    from citegeist.bibtex import BibEntry

    result = resolver.resolve_entry(
        BibEntry(
            entry_type="article",
            citation_key="seed2024",
            fields={"doi": "10.1000/example", "title": "Biomedical Example"},
        )
    )

    assert result is not None
    assert result.source_label == "europepmc:doi:10.1000/example"
    assert result.entry.fields["pmid"] == "37158217"


def test_metadata_resolver_uses_europepmc_title_search_after_pubmed() -> None:
    resolver = MetadataResolver()
    resolver.search_crossref_best_match = lambda *args, **kwargs: None  # type: ignore[method-assign]
    resolver.search_datacite_best_match = lambda *args, **kwargs: None  # type: ignore[method-assign]
    resolver.search_openalex_best_match = lambda *args, **kwargs: None  # type: ignore[method-assign]
    resolver.search_pubmed_best_match = lambda *args, **kwargs: None  # type: ignore[method-assign]
    resolver.europepmc.search = lambda _title, limit=5: [  # type: ignore[method-assign]
        resolver.europepmc.normalize(
            {
                "id": "37158217",
                "source": "MED",
                "pmid": "37158217",
                "doi": "10.1000/example",
                "title": "Biomedical Example",
                "authorString": "Doe J, Roe A",
                "journalTitle": "Biomed Journal",
                "pubYear": "2024",
            }
        )
    ]

    from citegeist.bibtex import BibEntry

    result = resolver.resolve_entry(
        BibEntry(
            entry_type="article",
            citation_key="seed2024",
            fields={"title": "Biomedical Example", "author": "Doe J", "year": "2024"},
        )
    )

    assert result is not None
    assert result.source_label == "europepmc:search:Biomedical Example"
