from __future__ import annotations

from citegeist.cli import _run_enrich_oa
from citegeist.sources import SourceRegistry, UnpaywallSource, list_source_catalog, prioritized_source_keys
from citegeist.storage import BibliographyStore


def test_unpaywall_source_normalizes_oa_record() -> None:
    source = UnpaywallSource(config={"email": "tester@example.org"})
    entry = source.normalize(
        {
            "doi": "10.1000/example",
            "title": "Example Article",
            "year": 2024,
            "is_oa": True,
            "oa_status": "gold",
            "best_oa_location": {
                "url": "https://example.org/article",
                "url_for_pdf": "https://example.org/article.pdf",
                "license": "cc-by",
                "host_type": "publisher",
                "version": "publishedVersion",
                "evidence": "open (via free pdf)",
            },
        }
    )

    assert entry is not None
    assert entry.fields["doi"] == "10.1000/example"
    assert entry.fields["best_oa_url"] == "https://example.org/article"
    assert entry.fields["best_oa_pdf_url"] == "https://example.org/article.pdf"
    assert entry.fields["oa_status"] == "gold"
    assert entry.fields["oa_license"] == "cc-by"
    assert entry.fields["is_oa"] == "true"


def test_unpaywall_registry_and_catalog() -> None:
    registry = SourceRegistry()
    registry.from_config_dict(
        {
            "sources": {
                "unpaywall": {
                    "source_type": "unpaywall",
                    "enabled": True,
                    "email": "tester@example.org",
                }
            }
        }
    )
    source = registry.get("unpaywall")
    assert isinstance(source, UnpaywallSource)

    catalog = {entry.key: entry for entry in list_source_catalog()}
    assert catalog["unpaywall"].current_status == "integrated"
    assert catalog["unpaywall"].priority == "now"
    assert "unpaywall" in prioritized_source_keys()


def test_run_enrich_oa_updates_entry() -> None:
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  doi = {10.1000/example}
}
"""
        )

        original_lookup = UnpaywallSource.lookup_by_doi

        def fake_lookup(self: UnpaywallSource, doi: str):
            return self.normalize(
                {
                    "doi": doi,
                    "title": "Seed Paper",
                    "year": 2024,
                    "is_oa": True,
                    "oa_status": "green",
                    "best_oa_location": {
                        "url": "https://repository.example.org/seed",
                        "url_for_pdf": "https://repository.example.org/seed.pdf",
                        "license": "cc-by",
                        "host_type": "repository",
                        "version": "acceptedVersion",
                        "evidence": "oa repository",
                    },
                }
            )

        UnpaywallSource.lookup_by_doi = fake_lookup  # type: ignore[method-assign]
        try:
            assert _run_enrich_oa(store, ["seed2024"], "tester@example.org") == 0
        finally:
            UnpaywallSource.lookup_by_doi = original_lookup  # type: ignore[method-assign]

        entry = store.get_entry("seed2024")
        assert entry is not None
        assert entry["best_oa_url"] == "https://repository.example.org/seed"
        assert entry["best_oa_pdf_url"] == "https://repository.example.org/seed.pdf"
        assert entry["oa_status"] == "green"
        assert entry["oa_host_type"] == "repository"
        provenance = store.get_field_provenance("seed2024")
        assert any(item["source_type"] == "oa_enrich" for item in provenance)
    finally:
        store.close()


def test_run_enrich_oa_requires_email() -> None:
    store = BibliographyStore()
    try:
        assert _run_enrich_oa(store, ["missing"], None) == 1
    finally:
        store.close()
