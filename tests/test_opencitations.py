from __future__ import annotations

from citegeist.expand import OpenCitationsExpander
from citegeist.sources import OpenCitationsSource
from citegeist.storage import BibliographyStore


def test_opencitations_source_normalizes_metadata_row() -> None:
    source = OpenCitationsSource(config={})
    entry = source.normalize(
        {
            "id": "doi:10.1000/example openalex:W1234567890 omid:br/06123",
            "title": "Example Work",
            "author": "Doe, Jane [omid:ra/1]; Roe, Alex [omid:ra/2]",
            "pub_date": "2024-05",
            "venue": "Journal of Examples [issn:1234-5678]",
            "volume": "12",
            "issue": "3",
            "page": "10-20",
            "type": "journal article",
            "publisher": "Example Press [crossref:123]",
        }
    )

    assert entry is not None
    assert entry.fields["doi"] == "10.1000/example"
    assert entry.fields["openalex"] == "W1234567890"
    assert entry.fields["author"] == "Doe, Jane and Roe, Alex"
    assert entry.fields["journal"] == "Journal of Examples"
    assert entry.fields["publisher"] == "Example Press"
    assert entry.fields["year"] == "2024"


def test_opencitations_source_builds_edges_for_references() -> None:
    source = OpenCitationsSource(config={})
    source.source_client.get_json = lambda _url: [  # type: ignore[method-assign]
        {
            "oci": "1-2",
            "citing": "omid:br/1 doi:10.1000/source",
            "cited": "omid:br/2 doi:10.1000/target",
            "creation": "2024-01-01",
        }
    ]

    edges = source.get_citations("10.1000/source", relation_type="cites", limit=10)
    assert len(edges) == 1
    assert edges[0].source_work_id == "doi:10.1000/source"
    assert edges[0].target_work_id == "doi:10.1000/target"


def test_opencitations_expander_creates_reference_nodes_and_relations() -> None:
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  doi = {10.1000/source}
}
"""
        )

        expander = OpenCitationsExpander()
        expander.source.source_client.get_json = lambda url: [  # type: ignore[method-assign]
            {
                "oci": "1-2",
                "citing": "omid:br/1 doi:10.1000/source",
                "cited": "omid:br/2 doi:10.1000/target",
                "creation": "2024-01-01",
            }
        ] if "/references/" in url else [
            {
                "id": "doi:10.1000/target omid:br/2",
                "title": "Target Work",
                "author": "Doe, Jane [omid:ra/1]",
                "pub_date": "2023",
                "venue": "Journal of Targets [issn:1111-1111]",
                "type": "journal article",
            }
        ]
        expander.resolver.resolve_doi = lambda _doi: None  # type: ignore[method-assign]
        expander.resolver.resolve_datacite_doi = lambda _doi: None  # type: ignore[method-assign]

        results = expander.expand_entry(store, "seed2024", relation_type="cites", limit=10)

        assert [item.discovered_citation_key for item in results] == ["doi101000target"]
        discovered = store.get_entry("doi101000target")
        assert discovered is not None
        assert discovered["title"] == "Target Work"
        assert store.get_relations("seed2024") == ["doi101000target"]
    finally:
        store.close()


def test_opencitations_expander_supports_cited_by_direction() -> None:
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  doi = {10.1000/seed}
}
"""
        )

        expander = OpenCitationsExpander()
        expander.source.source_client.get_json = lambda url: [  # type: ignore[method-assign]
            {
                "oci": "2-1",
                "citing": "omid:br/2 doi:10.1000/citing",
                "cited": "omid:br/1 doi:10.1000/seed",
                "creation": "2024-01-01",
            }
        ] if "/citations/" in url else [
            {
                "id": "doi:10.1000/citing omid:br/2",
                "title": "Citing Work",
                "author": "Doe, Jane [omid:ra/1]",
                "pub_date": "2025",
                "venue": "Journal of Citers [issn:1111-1111]",
                "type": "journal article",
            }
        ]
        expander.resolver.resolve_doi = lambda _doi: None  # type: ignore[method-assign]
        expander.resolver.resolve_datacite_doi = lambda _doi: None  # type: ignore[method-assign]

        results = expander.expand_entry(store, "seed2024", relation_type="cited_by", limit=10)

        assert [item.discovered_citation_key for item in results] == ["doi101000citing"]
        assert store.get_relations("doi101000citing") == ["seed2024"]
    finally:
        store.close()
