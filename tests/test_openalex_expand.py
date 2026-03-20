from citegeist.expand import OpenAlexExpander, _openalex_work_to_entry
from citegeist.storage import BibliographyStore


def test_openalex_work_to_entry_maps_basic_fields():
    entry = _openalex_work_to_entry(
        {
            "id": "https://openalex.org/W12345",
            "doi": "https://doi.org/10.1000/example-openalex",
            "display_name": "OpenAlex Discovered Work",
            "publication_year": 2022,
            "type": "article",
            "authorships": [{"author": {"display_name": "Jane Smith"}}],
            "primary_location": {"source": {"display_name": "Journal of Graph Discovery"}},
            "abstract_inverted_index": {"Graph": [0], "discovery": [1]},
        }
    )

    assert entry.citation_key == "openalexw12345"
    assert entry.fields["openalex"] == "W12345"
    assert entry.fields["doi"] == "10.1000/example-openalex"
    assert entry.fields["journal"] == "Journal of Graph Discovery"
    assert entry.fields["abstract"] == "Graph discovery"


def test_openalex_expander_adds_outgoing_and_incoming_edges():
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
        expander = OpenAlexExpander()
        payloads = iter(
            [
                {
                    "results": [
                        {
                            "id": "https://openalex.org/WSEED",
                        }
                    ]
                },
                {
                    "results": [
                        {
                            "id": "https://openalex.org/WDISCOVERED",
                            "display_name": "Referenced OpenAlex Work",
                            "publication_year": 2021,
                            "type": "article",
                            "authorships": [{"author": {"display_name": "Bob Known"}}],
                            "primary_location": {"source": {"display_name": "OpenAlex Journal"}},
                        }
                    ]
                },
                {
                    "results": [
                        {
                            "id": "https://openalex.org/WCITING",
                            "display_name": "Citing OpenAlex Work",
                            "publication_year": 2025,
                            "type": "article",
                            "authorships": [{"author": {"display_name": "Carol Citing"}}],
                        }
                    ]
                },
            ]
        )
        expander.resolver.source_client.get_json = lambda _url: next(payloads)  # type: ignore[method-assign]

        outgoing = expander.expand_entry(store, "seed2024", relation_type="cites", limit=5)
        incoming = expander.expand_entry(store, "seed2024", relation_type="cited_by", limit=5)

        assert outgoing[0].discovered_citation_key == "openalexwdiscovered"
        assert incoming[0].source_citation_key == "openalexwciting"
        assert "openalexwdiscovered" in store.get_relations("seed2024", "cites")
        assert "seed2024" in store.get_relations("openalexwciting", "cites")
    finally:
        store.close()
