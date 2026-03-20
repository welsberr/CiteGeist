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
