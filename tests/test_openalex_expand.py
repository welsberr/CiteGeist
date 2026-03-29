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

    assert entry.citation_key == "doi101000exampleopenalex"
    assert entry.fields["openalex"] == "W12345"
    assert entry.fields["doi"] == "10.1000/example-openalex"
    assert entry.fields["journal"] == "Journal of Graph Discovery"
    assert entry.fields["abstract"] == "Graph discovery"


def test_openalex_work_to_entry_uses_journal_metadata_for_non_article_work_type():
    entry = _openalex_work_to_entry(
        {
            "id": "https://openalex.org/W12345",
            "doi": "https://doi.org/10.1000/example-openalex",
            "display_name": "OpenAlex Journal-hosted Work",
            "publication_year": 2022,
            "type": "reference-entry",
            "authorships": [{"author": {"display_name": "Jane Smith"}}],
            "primary_location": {"source": {"display_name": "Journal of Graph Discovery", "type": "journal"}},
        }
    )

    assert entry.entry_type == "article"
    assert entry.fields["journal"] == "Journal of Graph Discovery"
    assert "booktitle" not in entry.fields


def test_openalex_work_to_entry_preserves_spacing_when_stripping_markup():
    entry = _openalex_work_to_entry(
        {
            "id": "https://openalex.org/W12345",
            "display_name": "The Oral Papilla of the Lancelet Larva (<i>Branchiostoma lanceolatum</i>)",
            "publication_year": 2022,
            "type": "article",
        }
    )

    assert entry.fields["title"] == "The Oral Papilla of the Lancelet Larva (Branchiostoma lanceolatum)"


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
                            "doi": "https://doi.org/10.1000/discovered-openalex",
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

        assert outgoing[0].discovered_citation_key == "doi101000discoveredopenalex"
        assert incoming[0].source_citation_key == "openalexwciting"
        assert "doi101000discoveredopenalex" in store.get_relations("seed2024", "cites")
        assert "seed2024" in store.get_relations("openalexwciting", "cites")
    finally:
        store.close()


def test_openalex_work_to_entry_drops_page_blob_abstract():
    entry = _openalex_work_to_entry(
        {
            "id": "https://openalex.org/W12345",
            "display_name": "Noisy OpenAlex Work",
            "publication_year": 2022,
            "type": "article",
            "abstract_inverted_index": {
                "Research": [0],
                "Article|": [1],
                "Download": [2],
                "citation": [3],
                "file": [4],
                "This": [5],
                "content": [6],
                "is": [7],
                "only": [8],
                "available": [9],
                "via": [10],
                "PDF": [11],
            },
        }
    )

    assert "abstract" not in entry.fields


def test_openalex_expander_reuses_existing_doi_entry():
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

@article{doi101000discoveredopenalex,
  author = {Existing, Bob},
  title = {Referenced OpenAlex Work},
  year = {2021},
  doi = {10.1000/discovered-openalex}
}
"""
        )
        expander = OpenAlexExpander()
        payloads = iter(
            [
                {"results": [{"id": "https://openalex.org/WSEED"}]},
                {
                    "results": [
                        {
                            "id": "https://openalex.org/WDISCOVERED",
                            "doi": "https://doi.org/10.1000/discovered-openalex",
                            "display_name": "Referenced OpenAlex Work",
                            "publication_year": 2021,
                            "type": "article",
                            "authorships": [{"author": {"display_name": "Bob Known"}}],
                            "primary_location": {"source": {"display_name": "OpenAlex Journal"}},
                        }
                    ]
                },
            ]
        )
        expander.resolver.source_client.get_json = lambda _url: next(payloads)  # type: ignore[method-assign]

        results = expander.expand_entry(store, "seed2024", relation_type="cites", limit=5)

        assert [result.discovered_citation_key for result in results] == ["doi101000discoveredopenalex"]
        assert results[0].created_entry is False
        assert store.get_entry("openalexwdiscovered") is None
        assert "doi101000discoveredopenalex" in store.get_relations("seed2024", "cites")
    finally:
        store.close()


def test_openalex_expander_skips_generic_container_title_without_doi():
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
                {"results": [{"id": "https://openalex.org/WSEED"}]},
                {
                    "results": [
                        {
                            "id": "https://openalex.org/WBAD",
                            "display_name": "Blood",
                            "publication_year": 2011,
                            "type": "article",
                            "primary_location": {"source": {"display_name": "Blood"}},
                        }
                    ]
                },
            ]
        )
        expander.resolver.source_client.get_json = lambda _url: next(payloads)  # type: ignore[method-assign]

        assert expander.expand_entry(store, "seed2024", relation_type="cites", limit=5) == []
        assert store.get_relations("seed2024", "cites") == []
    finally:
        store.close()


def test_openalex_expander_skips_review_like_article_shadowing_existing_book():
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

@book{darwin1859origin,
  author = {Darwin, Charles},
  title = {On the Origin of Species by Means of Natural Selection},
  year = {1859}
}
"""
        )
        expander = OpenAlexExpander()
        payloads = iter(
            [
                {"results": [{"id": "https://openalex.org/WSEED"}]},
                {
                    "results": [
                        {
                            "id": "https://openalex.org/WREVIEWLIKE",
                            "display_name": "On the Origin of Species by Means of Natural Selection",
                            "publication_year": 1953,
                            "type": "article",
                            "authorships": [{"author": {"display_name": "R. L. Livezey"}}],
                            "primary_location": {"source": {"display_name": "The American Midland Naturalist"}},
                        }
                    ]
                },
            ]
        )
        expander.resolver.source_client.get_json = lambda _url: next(payloads)  # type: ignore[method-assign]

        assert expander.expand_entry(store, "seed2024", relation_type="cites", limit=5) == []
        assert store.get_entry("openalexwreviewlike") is None
        assert store.get_relations("seed2024", "cites") == []
    finally:
        store.close()


def test_openalex_expander_keeps_same_title_article_when_it_has_an_abstract():
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

@book{darwin1859origin,
  author = {Darwin, Charles},
  title = {On the Origin of Species by Means of Natural Selection},
  year = {1859}
}
"""
        )
        expander = OpenAlexExpander()
        payloads = iter(
            [
                {"results": [{"id": "https://openalex.org/WSEED"}]},
                {
                    "results": [
                        {
                            "id": "https://openalex.org/WKEPT",
                            "display_name": "On the Origin of Species by Means of Natural Selection",
                            "publication_year": 1953,
                            "type": "article",
                            "authorships": [{"author": {"display_name": "R. L. Livezey"}}],
                            "primary_location": {"source": {"display_name": "The American Midland Naturalist"}},
                            "abstract_inverted_index": {"Legitimate": [0], "analysis": [1]},
                        }
                    ]
                },
            ]
        )
        expander.resolver.source_client.get_json = lambda _url: next(payloads)  # type: ignore[method-assign]

        results = expander.expand_entry(store, "seed2024", relation_type="cites", limit=5)

        assert [result.discovered_citation_key for result in results] == ["openalexwkept"]
        assert "openalexwkept" in store.get_relations("seed2024", "cites")
    finally:
        store.close()
