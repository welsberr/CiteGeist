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


def test_store_records_provenance_and_review_status():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(SAMPLE_BIB, source_label="fixtures/sample.bib", review_status="draft")

        entry = store.get_entry("smith2024graphs")
        assert entry is not None
        assert entry["review_status"] == "draft"

        provenance = store.get_field_provenance("smith2024graphs")
        assert provenance
        assert provenance[0]["source_type"] == "bibtex"
        assert provenance[0]["source_label"] == "fixtures/sample.bib"

        assert store.set_entry_status("smith2024graphs", "reviewed") is True
        updated = store.get_entry("smith2024graphs")
        assert updated is not None
        assert updated["review_status"] == "reviewed"
    finally:
        store.close()


def test_store_traverses_graph_and_surfaces_missing_targets():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  references = {known2023, missing2022}
}

@article{known2023,
  author = {Known, Bob},
  title = {Known Paper},
  year = {2023},
  references = {leaf2021}
}

@article{leaf2021,
  author = {Leaf, Carol},
  title = {Leaf Paper},
  year = {2021}
}
""",
            review_status="reviewed",
        )

        rows = store.traverse_graph(["seed2024"], relation_types=["cites"], max_depth=2)

        assert [row["target_citation_key"] for row in rows] == [
            "known2023",
            "missing2022",
            "leaf2021",
        ]
        assert rows[1]["target_exists"] is False
        assert rows[2]["depth"] == 2
    finally:
        store.close()
