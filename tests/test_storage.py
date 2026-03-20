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


def test_store_export_skips_doi_only_stub_by_default():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@misc{stubdoi,
  title = {Referenced work 6},
  doi = {10.1200/JCO.2002.04.117},
  url = {https://doi.org/10.1200/JCO.2002.04.117}
}

@article{realentry,
  author = {Smith, Jane},
  title = {Real Entry},
  year = {2024},
  doi = {10.1000/real}
}
"""
        )

        exported = store.export_bibtex()
        assert "@article{realentry," in exported
        assert "@misc{stubdoi," not in exported

        explicit = store.export_bibtex(["stubdoi"])
        assert "@misc{stubdoi," in explicit

        with_stubs = store.export_bibtex(include_stubs=True)
        assert "@misc{stubdoi," in with_stubs
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


def test_store_records_and_updates_field_conflicts():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
"""
        )
        ok = store.record_conflicts(
            "seed2024",
            [
                {
                    "field_name": "title",
                    "current_value": "Seed Paper",
                    "proposed_value": "Resolved Seed Paper",
                }
            ],
            source_type="resolver",
            source_label="crossref:doi:10.1000/seed",
        )
        assert ok is True
        conflicts = store.get_field_conflicts("seed2024")
        assert conflicts[0]["field_name"] == "title"
        assert conflicts[0]["status"] == "open"
        assert store.set_conflict_status("seed2024", "title", "accepted") == 1
        updated = store.get_field_conflicts("seed2024", status="accepted")
        assert len(updated) == 1
    finally:
        store.close()


def test_store_can_apply_latest_conflict_value():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
"""
        )
        store.record_conflicts(
            "seed2024",
            [
                {
                    "field_name": "title",
                    "current_value": "Seed Paper",
                    "proposed_value": "Resolved Seed Paper",
                }
            ],
            source_type="resolver",
            source_label="crossref:doi:10.1000/seed",
        )

        assert store.apply_conflict_value("seed2024", "title") is True
        entry = store.get_entry("seed2024")
        assert entry is not None
        assert entry["title"] == "Resolved Seed Paper"
        accepted = store.get_field_conflicts("seed2024", status="accepted")
        assert len(accepted) == 1
    finally:
        store.close()


def test_store_supports_entry_topic_membership():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
"""
        )

        assert store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        ) is True
        assert store.add_entry_topic(
            "seed2024",
            topic_slug="semantic-search",
            topic_name="Semantic Search",
            source_type="talkorigins",
            source_url="https://example.org/topics/semantic-search",
            source_label="topic-seed",
        ) is True

        entry = store.get_entry("seed2024")
        assert entry is not None
        assert [topic["slug"] for topic in entry["topics"]] == ["graph-methods", "semantic-search"]

        topics = store.list_topics()
        assert [topic["slug"] for topic in topics] == ["graph-methods", "semantic-search"]
        assert topics[0]["entry_count"] == 1
        topic = store.get_topic("graph-methods")
        assert topic is not None
        assert topic["name"] == "Graph Methods"
        assert topic["expansion_phrase"] is None
        topic_entries = store.list_topic_entries("graph-methods")
        assert topic_entries[0]["citation_key"] == "seed2024"
    finally:
        store.close()


def test_store_can_set_topic_expansion_phrase():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
"""
        )
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        )
        assert store.set_topic_expansion_phrase("graph-methods", "graph networks biology") is True

        topic = store.get_topic("graph-methods")
        assert topic is not None
        assert topic["expansion_phrase"] == "graph networks biology"
        assert topic["phrase_review_status"] == "unreviewed"
        topics = store.list_topics()
        assert topics[0]["expansion_phrase"] == "graph networks biology"
    finally:
        store.close()


def test_store_lists_stub_resolution_candidates():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@misc{stubdoi,
  title = {Referenced work 6},
  doi = {10.1200/JCO.2002.04.117},
  url = {https://doi.org/10.1200/JCO.2002.04.117}
}

@article{complete,
  author = {Smith, Jane},
  title = {Complete Record},
  year = {2024},
  doi = {10.1000/complete}
}
"""
        )
        store.add_entry_topic(
            "stubdoi",
            topic_slug="artificial-life",
            topic_name="Artificial life",
            source_label="test",
        )

        candidates = store.list_resolution_candidates(limit=10, doi_only=True, stub_only=True)
        assert [row["citation_key"] for row in candidates] == ["stubdoi"]

        topic_candidates = store.list_resolution_candidates(
            limit=10,
            doi_only=True,
            stub_only=True,
            topic_slug="artificial-life",
        )
        assert [row["citation_key"] for row in topic_candidates] == ["stubdoi"]
    finally:
        store.close()


def test_store_can_stage_and_review_topic_phrase_suggestion():
    store = BibliographyStore()
    try:
        store.ensure_topic("graph-methods", "Graph Methods")

        assert store.stage_topic_phrase_suggestion(
            "graph-methods",
            "graph networks biology",
            review_notes="generated from local titles",
        ) is True

        staged = store.get_topic("graph-methods")
        assert staged is not None
        assert staged["suggested_phrase"] == "graph networks biology"
        assert staged["expansion_phrase"] is None
        assert staged["phrase_review_status"] == "pending"
        assert staged["phrase_review_notes"] == "generated from local titles"

        assert store.review_topic_phrase_suggestion(
            "graph-methods",
            "accepted",
            review_notes="looks good",
        ) is True

        reviewed = store.get_topic("graph-methods")
        assert reviewed is not None
        assert reviewed["suggested_phrase"] is None
        assert reviewed["expansion_phrase"] == "graph networks biology"
        assert reviewed["phrase_review_status"] == "accepted"
        assert reviewed["phrase_review_notes"] == "looks good"
    finally:
        store.close()


def test_store_can_filter_topics_by_phrase_review_status():
    store = BibliographyStore()
    try:
        store.ensure_topic("graph-methods", "Graph Methods")
        store.ensure_topic("abiogenesis", "Abiogenesis")
        store.stage_topic_phrase_suggestion("graph-methods", "graph networks biology")
        store.stage_topic_phrase_suggestion("abiogenesis", "abiogenesis life origin")
        store.review_topic_phrase_suggestion("abiogenesis", "accepted")

        pending_topics = store.list_topics(phrase_review_status="pending")
        accepted_topics = store.list_topics(phrase_review_status="accepted")

        assert [topic["slug"] for topic in pending_topics] == ["graph-methods"]
        assert [topic["slug"] for topic in accepted_topics] == ["abiogenesis"]
    finally:
        store.close()


def test_store_can_list_topic_phrase_reviews():
    store = BibliographyStore()
    try:
        store.ensure_topic("graph-methods", "Graph Methods")
        store.ensure_topic("abiogenesis", "Abiogenesis")
        store.ensure_topic("plain-topic", "Plain Topic")
        store.stage_topic_phrase_suggestion("graph-methods", "graph networks biology")
        store.stage_topic_phrase_suggestion("abiogenesis", "abiogenesis life origin")
        store.review_topic_phrase_suggestion("abiogenesis", "accepted")

        reviews = store.list_topic_phrase_reviews()
        pending_reviews = store.list_topic_phrase_reviews(phrase_review_status="pending")

        assert [review["slug"] for review in reviews] == ["graph-methods"]
        assert reviews[0]["suggested_phrase"] == "graph networks biology"
        assert reviews[0]["phrase_review_status"] == "pending"
        assert [review["slug"] for review in pending_reviews] == ["graph-methods"]
    finally:
        store.close()


def test_store_rejected_topic_phrase_stays_in_review_queue():
    store = BibliographyStore()
    try:
        store.ensure_topic("graph-methods", "Graph Methods")
        store.stage_topic_phrase_suggestion("graph-methods", "graph networks biology")

        assert store.review_topic_phrase_suggestion(
            "graph-methods",
            "rejected",
            review_notes="too broad",
        ) is True

        topic = store.get_topic("graph-methods")
        assert topic is not None
        assert topic["suggested_phrase"] == "graph networks biology"
        assert topic["expansion_phrase"] is None
        assert topic["phrase_review_status"] == "rejected"

        reviews = store.list_topic_phrase_reviews()
        assert [review["slug"] for review in reviews] == ["graph-methods"]
        assert reviews[0]["phrase_review_status"] == "rejected"
    finally:
        store.close()


def test_store_search_text_can_filter_by_topic():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Graph Methods for Biology},
  year = {2024},
  abstract = {A graph methods paper.}
}

@article{other2023,
  author = {Other, Bob},
  title = {Graph Methods for Chemistry},
  year = {2023},
  abstract = {Another graph methods paper.}
}
"""
        )

        store.add_entry_topic(
            "seed2024",
            topic_slug="biology",
            topic_name="Biology",
            source_type="talkorigins",
            source_url="https://example.org/topics/biology",
            source_label="topic-seed",
        )
        store.add_entry_topic(
            "other2023",
            topic_slug="chemistry",
            topic_name="Chemistry",
            source_type="talkorigins",
            source_url="https://example.org/topics/chemistry",
            source_label="topic-seed",
        )
        store.connection.commit()

        results = store.search_text("graph", topic_slug="biology")

        assert [row["citation_key"] for row in results] == ["seed2024"]
    finally:
        store.close()
