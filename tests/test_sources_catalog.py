from __future__ import annotations

from citegeist.sources import CrossRefSource, OpenCitationsSource, SourceRegistry, list_source_catalog, prioritized_source_keys


def test_catalog_prioritizes_existing_core_sources() -> None:
    keys = prioritized_source_keys()
    assert keys[:6] == ["crossref", "datacite", "europe_pmc", "openalex", "open_citations", "pubmed"]


def test_catalog_includes_open_citation_and_access_sources() -> None:
    catalog = {entry.key: entry for entry in list_source_catalog()}
    assert "open_citations" in catalog
    assert "unpaywall" in catalog
    assert catalog["open_citations"].priority == "now"
    assert "doi_citations" in catalog["open_citations"].capabilities


def test_registry_loads_known_source_from_config() -> None:
    registry = SourceRegistry()
    registry.from_config_dict(
        {
            "sources": {
                "crossref": {
                    "source_type": "crossref",
                    "enabled": True,
                }
            }
        }
    )

    source = registry.get("crossref")
    assert isinstance(source, CrossRefSource)


def test_registry_rejects_unknown_source_type() -> None:
    registry = SourceRegistry()
    try:
        registry.from_config_dict({"sources": {"mystery": {"source_type": "mystery"}}})
    except ValueError as exc:
        assert "Unknown source type" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown source type")


def test_registry_loads_opencitations_from_config() -> None:
    registry = SourceRegistry()
    registry.from_config_dict(
        {
            "sources": {
                "opencitations": {
                    "source_type": "opencitations",
                    "enabled": True,
                }
            }
        }
    )

    source = registry.get("opencitations")
    assert isinstance(source, OpenCitationsSource)
