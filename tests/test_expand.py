from citegeist.expand import CrossrefExpander, _crossref_reference_to_entry
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
        expander.resolver._get_json = lambda _url: {  # type: ignore[method-assign]
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

        assert [result.discovered_citation_key for result in results] == [
            "doi101000exampleref",
            "ref2021unstructured2",
        ]
        discovered = store.get_entry("doi101000exampleref")
        assert discovered is not None
        assert discovered["review_status"] == "draft"
        assert store.get_relations("seed2024") == ["doi101000exampleref", "ref2021unstructured2"]
        relation_provenance = store.get_relation_provenance("seed2024")
        assert relation_provenance[0]["source_type"] == "graph_expand"
    finally:
        store.close()
