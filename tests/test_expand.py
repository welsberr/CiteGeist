import urllib.error

from citegeist.bibtex import BibEntry
from citegeist.expand import CrossrefExpander, _crossref_reference_to_entry
from citegeist.resolve import Resolution
from citegeist.storage import BibliographyStore


def test_crossref_reference_to_entry_prefers_doi_key():
    entry = _crossref_reference_to_entry(
        {
            "DOI": "10.1000/example-ref",
            "article-title": "Discovered Reference",
            "author": "Doe, Alex",
            "year": "2022",
            "journal-title": "Journal of Discovery",
        },
        "seed2024",
        1,
    )

    assert entry.citation_key == "doi101000exampleref"
    assert entry.fields["doi"] == "10.1000/example-ref"
    assert entry.fields["journal"] == "Journal of Discovery"


def test_crossref_expander_creates_draft_nodes_and_relations():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  doi = {10.1000/seed-doi}
}
"""
        )

        expander = CrossrefExpander()
        expander.resolver.source_client.get_json = lambda _url: {  # type: ignore[method-assign]
            "message": {
                "reference": [
                    {
                        "DOI": "10.1000/example-ref",
                        "article-title": "Discovered Reference",
                        "author": "Doe, Alex",
                        "year": "2022",
                        "journal-title": "Journal of Discovery",
                    },
                    {
                        "unstructured": "Unstructured reference string",
                        "year": "2021",
                    },
                ]
            }
        }

        results = expander.expand_entry_references(store, "seed2024")

        assert [result.discovered_citation_key for result in results] == ["doi101000exampleref"]
        discovered = store.get_entry("doi101000exampleref")
        assert discovered is not None
        assert discovered["review_status"] == "draft"
        assert store.get_relations("seed2024") == ["doi101000exampleref"]
        relation_provenance = store.get_relation_provenance("seed2024")
        assert relation_provenance[0]["source_type"] == "graph_expand"
    finally:
        store.close()


def test_crossref_expander_prefers_resolved_doi_metadata_for_discovered_refs():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  doi = {10.1000/seed-doi}
}
"""
        )

        expander = CrossrefExpander()
        expander.resolver.source_client.get_json = lambda _url: {  # type: ignore[method-assign]
            "message": {
                "reference": [
                    {
                        "DOI": "10.1117/12.512613",
                        "unstructured": "J. R. Koza ... Genetic Programming IV ... Springer ... 2005.",
                        "year": "2005",
                    }
                ]
            }
        }
        expander.resolver.resolve_doi = lambda doi: Resolution(  # type: ignore[method-assign]
            entry=BibEntry(
                entry_type="inproceedings",
                citation_key="koza2005genetic",
                fields={
                    "author": "Koza, J. R. and Keane, M. A.",
                    "title": "Genetic Programming IV: Routine Human-Competitive Machine Intelligence",
                    "year": "2005",
                    "booktitle": "Genetic and Evolutionary Computation Conference",
                    "doi": doi,
                    "url": f"https://doi.org/{doi}",
                },
            ),
            source_type="resolver",
            source_label=f"crossref:doi:{doi}",
        )  # type: ignore[return-value]

        results = expander.expand_entry_references(store, "seed2024")

        assert [result.discovered_citation_key for result in results] == ["doi10111712512613"]
        discovered = store.get_entry("doi10111712512613")
        assert discovered is not None
        assert discovered["entry_type"] == "inproceedings"
        assert discovered["title"] == "Genetic Programming IV: Routine Human-Competitive Machine Intelligence"
        assert discovered["booktitle"] == "Genetic and Evolutionary Computation Conference"
    finally:
        store.close()


def test_crossref_reference_to_entry_infers_non_misc_for_proceedings_like_text():
    entry = _crossref_reference_to_entry(
        {
            "DOI": "10.1117/12.512613",
            "unstructured": "Proceedings of the Artificial Life Workshop",
            "year": "2005",
        },
        "seed2024",
        1,
    )

    assert entry.entry_type == "inproceedings"


def test_crossref_expander_skips_citation_blob_without_identifier():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  doi = {10.1000/seed-doi}
}
"""
        )

        expander = CrossrefExpander()
        expander.resolver.source_client.get_json = lambda _url: {  # type: ignore[method-assign]
            "message": {
                "reference": [
                    {
                        "unstructured": (
                            "Abraham, J.K., Meir, E., Perry, J. (2009). "
                            "Addressing undergraduate student misconceptions. "
                            "https://example.org/article"
                        ),
                        "year": "2009",
                    }
                ]
            }
        }

        assert expander.expand_entry_references(store, "seed2024") == []
        assert store.get_relations("seed2024") == []
    finally:
        store.close()


def test_crossref_expander_keeps_simple_unstructured_title_without_identifier():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  doi = {10.1000/seed-doi}
}
"""
        )

        expander = CrossrefExpander()
        expander.resolver.source_client.get_json = lambda _url: {  # type: ignore[method-assign]
            "message": {
                "reference": [
                    {
                        "unstructured": "Proceedings of the Artificial Life Workshop",
                        "year": "2005",
                    }
                ]
            }
        }

        results = expander.expand_entry_references(store, "seed2024")

        assert [result.discovered_citation_key for result in results] == ["ref2005proceedings1"]
        discovered = store.get_entry("ref2005proceedings1")
        assert discovered is not None
        assert discovered["entry_type"] == "inproceedings"
    finally:
        store.close()


def test_crossref_reference_to_entry_extracts_title_from_thesis_citation_blob():
    entry = _crossref_reference_to_entry(
        {
            "unstructured": (
                "Johnson WR. Evolution in action in the classroom: Engaging students in scientific "
                "practices to develop a conceptual understanding of natural selection "
                "(Master’s thesis). ProQuest Dissertations and Theses database. "
                "(UMI No. 1517061). 2012."
            ),
            "year": "2012",
        },
        "seed2024",
        1,
    )

    assert entry.entry_type == "phdthesis"
    assert entry.fields["title"] == (
        "Evolution in action in the classroom: Engaging students in scientific "
        "practices to develop a conceptual understanding of natural selection"
    )


def test_crossref_reference_to_entry_normalizes_reversed_initial_author_name():
    entry = _crossref_reference_to_entry(
        {
            "author": "J., Fogel L.",
            "article-title": "Evolutionary Programming",
            "year": "1995",
        },
        "seed2024",
        1,
    )

    assert entry.fields["author"] == "Fogel, L. J."


def test_crossref_expander_returns_empty_on_fetch_error():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  doi = {10.1000/seed-doi}
}
"""
        )

        expander = CrossrefExpander()

        def raise_404(_url: str):
            raise urllib.error.HTTPError(_url, 404, "Not Found", hdrs=None, fp=None)

        expander.resolver.source_client._fetch_bytes = raise_404  # type: ignore[method-assign]

        assert expander.expand_entry_references(store, "seed2024") == []
    finally:
        store.close()
