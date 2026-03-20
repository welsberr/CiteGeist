from citegeist import BibliographyStore, parse_bibtex


SAMPLE_BIB = """
@article{smith2024graphs,
  author = {Smith, Jane and Doe, Alex},
  title = {Graph-first bibliography augmentation},
  year = {2024},
  doi = {10.1000/graph.2024.1},
  abstract = {We study citation graphs for literature discovery.},
  references = {miller2023search}
}

@inproceedings{miller2023search,
  author = {Miller, Sam},
  title = {Semantic search for research corpora},
  year = {2023},
  abstract = {Dense retrieval improves recall for academic search.}
}
"""


def test_parse_bibtex_extracts_entries_and_fields():
    entries = parse_bibtex(SAMPLE_BIB)

    assert [entry.citation_key for entry in entries] == ["smith2024graphs", "miller2023search"]
    assert entries[0].fields["title"] == "Graph-first bibliography augmentation"
    assert entries[0].fields["references"] == "miller2023search"


def test_store_ingests_entries_relations_and_search_text():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            SAMPLE_BIB,
            fulltext_by_key={
                "smith2024graphs": "This paper links citation graphs with semantic search over abstracts."
            },
        )

        entry = store.get_entry("smith2024graphs")
        assert entry is not None
        assert entry["doi"] == "10.1000/graph.2024.1"

        assert store.get_relations("smith2024graphs") == ["miller2023search"]

        results = store.search_text("semantic")
        assert [row["citation_key"] for row in results][:2] == [
            "miller2023search",
            "smith2024graphs",
        ]
    finally:
        store.close()


def test_store_exports_bibtex_from_normalized_rows():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(SAMPLE_BIB)

        exported = store.export_bibtex()
        parsed = {entry.citation_key: entry for entry in parse_bibtex(exported)}

        assert "@article{smith2024graphs," in exported
        assert "@inproceedings{miller2023search," in exported
        assert parsed["smith2024graphs"].fields["author"] == "Smith, Jane and Doe, Alex"
        assert parsed["smith2024graphs"].fields["references"] == "miller2023search"
    finally:
        store.close()
