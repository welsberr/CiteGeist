from citegeist.bibtex import BibEntry
from citegeist.expand import (
    ExpansionResult,
    TopicExpander,
    _meets_topic_assignment_threshold,
    _topic_relevance_score,
)
from citegeist.storage import BibliographyStore


class FakeOpenAlexExpander:
    def __init__(self, results: list[ExpansionResult] | dict[str, list[ExpansionResult]]) -> None:
        self.results = results
        self.calls: list[tuple[str, str, int]] = []

    def expand_entry(self, store, citation_key, relation_type="cites", limit=25):
        self.calls.append((citation_key, relation_type, limit))
        if isinstance(self.results, dict):
            return list(self.results.get(citation_key, []))
        return list(self.results)


def test_topic_expander_assigns_relevant_discoveries_back_to_topic():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Abiogenesis Seed Paper},
  year = {2024}
}
"""
        )
        store.add_entry_topic(
            "seed2024",
            topic_slug="abiogenesis",
            topic_name="Abiogenesis",
            source_type="talkorigins",
            source_url="https://example.org/topics/abiogenesis",
            source_label="seed",
        )
        store.upsert_entry(
            BibEntry(
                entry_type="article",
                citation_key="discovered1",
                fields={
                    "title": "Abiogenesis and origin chemistry",
                    "abstract": "A study of abiogenesis pathways.",
                    "year": "2025",
                },
            ),
            source_type="graph_expand",
            source_label="test",
            review_status="draft",
        )
        store.upsert_entry(
            BibEntry(
                entry_type="article",
                citation_key="discovered2",
                fields={
                    "title": "Galaxy formation dynamics",
                    "abstract": "Nothing about the topic.",
                    "year": "2025",
                },
            ),
            source_type="graph_expand",
            source_label="test",
            review_status="draft",
        )
        store.connection.commit()

        expander = TopicExpander(
            openalex_expander=FakeOpenAlexExpander(
                [
                    ExpansionResult("seed2024", "discovered1", False, "cites", "openalex:cites:seed2024"),
                    ExpansionResult("seed2024", "discovered2", False, "cites", "openalex:cites:seed2024"),
                ]
            )
        )

        results = expander.expand_topic(
            store,
            "abiogenesis",
            topic_phrase="abiogenesis origin chemistry",
            min_relevance=0.34,
        )

        assert len(results) == 2
        assigned = {item.discovered_citation_key: item.assigned_to_topic for item in results}
        assert assigned["discovered1"] is True
        assert assigned["discovered2"] is False
        topics = store.get_entry_topics("discovered1")
        assert topics[0]["slug"] == "abiogenesis"
        assert store.get_entry_topics("discovered2") == []
    finally:
        store.close()


def test_topic_expander_can_restrict_to_allowed_seed_keys():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Abiogenesis Seed Paper},
  year = {2024}
}

@article{seed2023,
  author = {Seed, Bob},
  title = {Abiogenesis Historical Seed},
  year = {2023}
}
"""
        )
        for citation_key in ("seed2024", "seed2023"):
            store.add_entry_topic(
                citation_key,
                topic_slug="abiogenesis",
                topic_name="Abiogenesis",
                source_type="talkorigins",
                source_url="https://example.org/topics/abiogenesis",
                source_label="seed",
            )
        store.upsert_entry(
            BibEntry(
                entry_type="article",
                citation_key="discovered1",
                fields={
                    "title": "Abiogenesis origin chemistry",
                    "abstract": "A study of abiogenesis chemistry.",
                    "year": "2025",
                },
            ),
            source_type="graph_expand",
            source_label="test",
            review_status="draft",
        )
        store.connection.commit()

        expander = TopicExpander(
            openalex_expander=FakeOpenAlexExpander(
                {"seed2023": [ExpansionResult("seed2023", "discovered1", False, "cites", "openalex:cites:seed2023")]}
            )
        )

        results = expander.expand_topic(
            store,
            "abiogenesis",
            topic_phrase="abiogenesis origin chemistry",
            seed_keys=["seed2024"],
        )

        assert results == []
        assert store.get_entry_topics("discovered1") == []
    finally:
        store.close()


def test_topic_expander_preview_discovers_without_writing():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Abiogenesis Seed Paper},
  year = {2024}
}
"""
        )
        store.add_entry_topic(
            "seed2024",
            topic_slug="abiogenesis",
            topic_name="Abiogenesis",
            source_type="talkorigins",
            source_url="https://example.org/topics/abiogenesis",
            source_label="seed",
        )
        store.connection.commit()

        expander = TopicExpander()
        expander._preview_discoveries = lambda *_args, **_kwargs: [  # type: ignore[method-assign]
            (
                ExpansionResult(
                    "seed2024",
                    "preview1",
                    True,
                    "cites",
                    "openalex:cites:seed2024",
                ),
                {
                    "title": "Abiogenesis origin chemistry",
                    "abstract": "A study of abiogenesis chemistry.",
                    "year": "2025",
                },
            )
        ]

        results = expander.expand_topic(
            store,
            "abiogenesis",
            topic_phrase="abiogenesis origin chemistry",
            min_relevance=0.3,
            preview_only=True,
        )

        assert len(results) == 1
        assert results[0].discovered_citation_key == "preview1"
        assert results[0].meets_relevance_threshold is True
        assert results[0].assigned_to_topic is False
        assert results[0].created_entry is True
        assert store.get_entry("preview1") is None
        assert store.get_entry_topics("preview1") == []
    finally:
        store.close()


def test_topic_expander_relation_type_both_uses_both_openalex_directions():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Abiogenesis Seed Paper},
  year = {2024}
}
"""
        )
        store.add_entry_topic(
            "seed2024",
            topic_slug="abiogenesis",
            topic_name="Abiogenesis",
            source_type="talkorigins",
            source_url="https://example.org/topics/abiogenesis",
            source_label="seed",
        )
        fake_expander = FakeOpenAlexExpander([])
        expander = TopicExpander(openalex_expander=fake_expander)

        expander.expand_topic(store, "abiogenesis", relation_type="both")

        assert [relation for _seed, relation, _limit in fake_expander.calls] == ["cites", "cited_by"]
    finally:
        store.close()


def test_topic_expander_stops_once_recent_target_is_reached():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Abiogenesis Seed Paper},
  year = {2024}
}
"""
        )
        store.add_entry_topic(
            "seed2024",
            topic_slug="abiogenesis",
            topic_name="Abiogenesis",
            source_type="talkorigins",
            source_url="https://example.org/topics/abiogenesis",
            source_label="seed",
        )
        store.upsert_entry(
            BibEntry(
                entry_type="article",
                citation_key="recent1",
                fields={"title": "Abiogenesis pathways", "abstract": "abiogenesis", "year": "2026"},
            ),
            source_type="graph_expand",
            source_label="test",
            review_status="draft",
        )
        store.upsert_entry(
            BibEntry(
                entry_type="article",
                citation_key="recent2",
                fields={"title": "Abiogenesis chemistry", "abstract": "abiogenesis", "year": "2025"},
            ),
            source_type="graph_expand",
            source_label="test",
            review_status="draft",
        )
        store.connection.commit()

        fake_expander = FakeOpenAlexExpander(
            {
                "seed2024": [ExpansionResult("seed2024", "recent1", False, "cites", "openalex:cites:seed2024")],
                "recent1": [ExpansionResult("recent1", "recent2", False, "cites", "openalex:cites:recent1")],
            }
        )
        expander = TopicExpander(openalex_expander=fake_expander)

        results = expander.expand_topic(
            store,
            "abiogenesis",
            topic_phrase="abiogenesis chemistry",
            max_rounds=3,
            recent_years=2,
            target_recent_entries=1,
        )

        assert [item.discovered_citation_key for item in results] == ["recent1"]
        assert fake_expander.calls == [("seed2024", "cites", 25)]
    finally:
        store.close()


def test_topic_relevance_score_expands_human_evolution_terms():
    score = _topic_relevance_score(
        "human evolution",
        {
            "title": "Body size and proportions in early hominids",
            "abstract": "A fossil and paleolithic perspective on primate ancestry.",
            "journal": "Science",
        },
    )

    assert score >= 0.15


def test_topic_assignment_requires_title_anchor():
    entry = {
        "title": "Phylogenies and the Comparative Method",
        "abstract": "A comparative framework for primate and hominid evolution.",
        "journal": "Systematic Zoology",
    }

    score = _topic_relevance_score("human evolution", entry)

    assert score >= 0.15
    assert _meets_topic_assignment_threshold("human evolution", entry, min_relevance=0.15, relevance_score=score) is False
