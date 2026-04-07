from citegeist import BibliographyStore
from citegeist.bootstrap import Bootstrapper
from citegeist.cli import main
from citegeist.expand import ExpansionResult


def test_bootstrap_from_seed_bib_only():
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        bootstrapper.crossref_expander.expand_entry_references = lambda _store, _key: []  # type: ignore[method-assign]
        bootstrapper.openalex_expander.expand_entry = lambda _store, _key, relation_type="cites", limit=5: []  # type: ignore[method-assign]

        results = bootstrapper.bootstrap(
            store,
            seed_bibtex="""
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
            expand=False,
        )

        assert [item.citation_key for item in results] == ["seed2024"]
        assert store.get_entry("seed2024") is not None
    finally:
        store.close()


def test_bootstrap_from_topic_only():
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        bootstrapper.resolver.search_openalex = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_pubmed = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_crossref = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_datacite = lambda topic, limit=5: [  # type: ignore[method-assign]
            __import__("citegeist").BibEntry(
                entry_type="article",
                citation_key="topic2024graph",
                fields={"title": "Graph Topic Result", "year": "2024"},
            )
        ]
        bootstrapper.crossref_expander.expand_entry_references = lambda _store, _key: []  # type: ignore[method-assign]
        bootstrapper.openalex_expander.expand_entry = lambda _store, _key, relation_type="cites", limit=5: []  # type: ignore[method-assign]

        results = bootstrapper.bootstrap(store, topic="graph topic", expand=False)

        assert [item.citation_key for item in results] == ["topic2024graph"]
        assert store.get_entry("topic2024graph") is not None
        assert results[0].score > 0
    finally:
        store.close()


def test_bootstrap_cli_accepts_seed_and_topic(tmp_path):
    seed_bib = tmp_path / "seed.bib"
    seed_bib.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )

    from unittest.mock import patch

    database = tmp_path / "library.sqlite3"
    with patch("citegeist.cli.Bootstrapper.bootstrap") as mocked_bootstrap:
        mocked_bootstrap.return_value = []
        exit_code = main(
            [
                "--db",
                str(database),
                "bootstrap",
                "--seed-bib",
                str(seed_bib),
                "--topic",
                "graph topic",
                "--no-expand",
            ]
        )

    assert exit_code == 0


def test_bootstrap_cli_preview_outputs_candidate_metadata(tmp_path, capsys):
    from unittest.mock import patch
    from citegeist.bootstrap import BootstrapResult

    database = tmp_path / "library.sqlite3"
    with patch("citegeist.cli.Bootstrapper.bootstrap") as mocked_bootstrap:
        mocked_bootstrap.return_value = [
            BootstrapResult(
                citation_key="openalexw123",
                origin="topic",
                created=True,
                score=4.0,
                title="Artificial Life and Adaptive Behavior",
                author="Langton, Christopher G.",
                year="1989",
                abstract="A foundational overview of artificial life systems.",
            )
        ]
        exit_code = main(
            [
                "--db",
                str(database),
                "bootstrap",
                "--topic",
                "artificial life",
                "--preview",
                "--topic-commit-limit",
                "50",
            ]
        )

    assert exit_code == 0
    payload = capsys.readouterr().out
    assert "Artificial Life and Adaptive Behavior" in payload
    assert "Langton, Christopher G." in payload
    assert "A foundational overview of artificial life systems." in payload


def test_bootstrap_ranks_and_deduplicates_topic_candidates():
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        from citegeist import BibEntry

        bootstrapper.resolver.search_openalex = lambda topic, limit=5: [  # type: ignore[method-assign]
            BibEntry(
                entry_type="article",
                citation_key="shared2024graph",
                fields={"title": "Graph Topic Ranking", "abstract": "graph topic graph"},
            )
        ]
        bootstrapper.resolver.search_pubmed = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_crossref = lambda topic, limit=5: [  # type: ignore[method-assign]
            BibEntry(
                entry_type="article",
                citation_key="shared2024graph",
                fields={"title": "Graph Topic Ranking", "abstract": "graph"},
            ),
            BibEntry(
                entry_type="article",
                citation_key="crossref2024other",
                fields={"title": "Less relevant paper"},
            ),
        ]
        bootstrapper.resolver.search_datacite = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.crossref_expander.expand_entry_references = lambda _store, _key: []  # type: ignore[method-assign]
        bootstrapper.openalex_expander.expand_entry = lambda _store, _key, relation_type="cites", limit=5: []  # type: ignore[method-assign]

        results = bootstrapper.bootstrap(store, topic="graph topic", expand=False, topic_limit=5)

        topic_results = [item for item in results if item.origin == "topic"]
        assert [item.citation_key for item in topic_results] == ["shared2024graph"]
    finally:
        store.close()


def test_bootstrap_preview_does_not_write_to_database():
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        from citegeist import BibEntry

        bootstrapper.resolver.search_openalex = lambda topic, limit=5: [  # type: ignore[method-assign]
            BibEntry(entry_type="article", citation_key="preview2024graph", fields={"title": "Preview Graph Topic"})
        ]
        bootstrapper.resolver.search_pubmed = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_crossref = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_datacite = lambda topic, limit=5: []  # type: ignore[method-assign]

        results = bootstrapper.bootstrap(store, topic="graph topic", expand=False, preview_only=True)

        assert [item.citation_key for item in results] == ["preview2024graph"]
        assert results[0].title == "Preview Graph Topic"
        assert store.get_entry("preview2024graph") is None
    finally:
        store.close()


def test_bootstrap_topic_commit_limit_restricts_persisted_candidates():
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        from citegeist import BibEntry

        bootstrapper.resolver.search_openalex = lambda topic, limit=5: [  # type: ignore[method-assign]
            BibEntry(entry_type="article", citation_key="rank1", fields={"title": "Graph Topic One"}),
            BibEntry(entry_type="article", citation_key="rank2", fields={"title": "Graph Topic Two"}),
        ]
        bootstrapper.resolver.search_pubmed = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_crossref = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_datacite = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.crossref_expander.expand_entry_references = lambda _store, _key: []  # type: ignore[method-assign]
        bootstrapper.openalex_expander.expand_entry = lambda _store, _key, relation_type="cites", limit=5: []  # type: ignore[method-assign]

        results = bootstrapper.bootstrap(
            store,
            topic="graph topic",
            expand=False,
            topic_limit=5,
            topic_commit_limit=1,
        )

        assert [item.citation_key for item in results if item.origin == "topic"] == ["rank1"]
        assert store.get_entry("rank1") is not None
        assert store.get_entry("rank2") is None
    finally:
        store.close()


def test_bootstrap_topic_candidates_are_attached_to_topic():
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        from citegeist import BibEntry

        bootstrapper.resolver.search_openalex = lambda topic, limit=5: [  # type: ignore[method-assign]
            BibEntry(
                entry_type="article",
                citation_key="topic2024graph",
                fields={"title": "Graph Topic Result", "year": "2024"},
            )
        ]
        bootstrapper.resolver.search_pubmed = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_crossref = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_datacite = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.crossref_expander.expand_entry_references = lambda _store, _key: []  # type: ignore[method-assign]
        bootstrapper.openalex_expander.expand_entry = lambda _store, _key, relation_type="cites", limit=5: []  # type: ignore[method-assign]

        bootstrapper.bootstrap(
            store,
            topic="graph topic",
            topic_slug="graph-topic",
            topic_name="Graph Topic",
            topic_phrase="graph topic methods",
            expand=False,
            topic_commit_limit=1,
        )

        topic = store.get_topic("graph-topic")
        assert topic is not None
        assert topic["entry_count"] == 1
        topic_entries = store.list_topic_entries("graph-topic")
        assert [item["citation_key"] for item in topic_entries] == ["topic2024graph"]
        assert topic_entries[0]["source_label"] == "topic:graph topic"
        assert topic_entries[0]["confidence"] > 0
    finally:
        store.close()


def test_bootstrap_topic_commit_requires_title_anchor():
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        from citegeist import BibEntry

        bootstrapper.resolver.search_openalex = lambda topic, limit=5: [  # type: ignore[method-assign]
            BibEntry(
                entry_type="article",
                citation_key="broad2024",
                fields={
                    "title": "The phylum Vertebrata: a case for zoological recognition",
                    "abstract": "Chordata includes Cephalochordata and Urochordata.",
                    "year": "2024",
                },
            ),
            BibEntry(
                entry_type="article",
                citation_key="anchored2024",
                fields={
                    "title": "Acraniates and amphioxus in comparative development",
                    "year": "2024",
                },
            ),
        ]
        bootstrapper.resolver.search_pubmed = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_crossref = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_datacite = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.crossref_expander.expand_entry_references = lambda _store, _key: []  # type: ignore[method-assign]
        bootstrapper.openalex_expander.expand_entry = lambda _store, _key, relation_type="cites", limit=5: []  # type: ignore[method-assign]

        results = bootstrapper.bootstrap(
            store,
            topic="acraniates cephalochordata amphioxus lancelet",
            topic_slug="acraniates",
            topic_name="Acraniates",
            expand=False,
            topic_commit_limit=5,
        )

        assert [item.citation_key for item in results] == ["anchored2024"]
        topic_entries = store.list_topic_entries("acraniates")
        assert [item["citation_key"] for item in topic_entries] == ["anchored2024"]
        assert store.get_entry("broad2024") is None
    finally:
        store.close()


def test_bootstrap_nonlegacy_both_mode_expands_both_relations():
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        calls: list[tuple[str, str, int]] = []

        bootstrapper.openalex_expander.expand_entry = lambda _store, key, relation_type="cites", limit=5: (  # type: ignore[method-assign]
            calls.append((key, relation_type, limit)) or []
        )

        bootstrapper.bootstrap(
            store,
            seed_bibtex="""
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
            expansion_mode="both",
            expand=True,
        )

        assert calls == [("seed2024", "cites", 5), ("seed2024", "cited_by", 5)]
    finally:
        store.close()


def test_bootstrap_recent_target_stops_recursive_openalex_expansion():
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        from citegeist import BibEntry

        store.upsert_entry(
            BibEntry(entry_type="article", citation_key="recent2026", fields={"title": "Recent discovery", "year": "2026"}),
            source_type="graph_expand",
            source_label="test",
            review_status="draft",
        )
        store.connection.commit()

        def fake_expand(_store, key, relation_type="cites", limit=5):
            if key == "seed2024":
                return [
                    ExpansionResult(
                        "seed2024",
                        "recent2026",
                        False,
                        relation_type,
                        f"openalex:{relation_type}:seed2024",
                    )
                ]
            return []

        bootstrapper.openalex_expander.expand_entry = fake_expand  # type: ignore[method-assign]

        results = bootstrapper.bootstrap(
            store,
            seed_bibtex="""
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
            expansion_mode="cites",
            expansion_rounds=3,
            recent_years=2,
            target_recent_entries=1,
            expand=True,
        )

        assert [item.origin for item in results][-1] == "openalex_expand:cites"
        assert [item.citation_key for item in results if item.origin.startswith("openalex_expand")] == ["recent2026"]
    finally:
        store.close()


def test_bootstrap_max_expanded_entries_caps_growth():
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        from citegeist import BibEntry

        store.upsert_entry(
            BibEntry(entry_type="article", citation_key="d1", fields={"title": "Discovery One", "year": "2024"}),
            source_type="graph_expand",
            source_label="test",
            review_status="draft",
        )
        store.upsert_entry(
            BibEntry(entry_type="article", citation_key="d2", fields={"title": "Discovery Two", "year": "2024"}),
            source_type="graph_expand",
            source_label="test",
            review_status="draft",
        )
        store.connection.commit()

        bootstrapper.openalex_expander.expand_entry = lambda _store, key, relation_type="cites", limit=5: (  # type: ignore[method-assign]
            [
                ExpansionResult(key, "d1", False, relation_type, f"openalex:{relation_type}:{key}"),
                ExpansionResult(key, "d2", False, relation_type, f"openalex:{relation_type}:{key}"),
            ]
            if key == "seed2024"
            else []
        )

        results = bootstrapper.bootstrap(
            store,
            seed_bibtex="""
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
            expansion_mode="cites",
            expand=True,
            max_expanded_entries=1,
        )

        assert [item.citation_key for item in results if item.origin.startswith("openalex_expand")] == ["d1"]
    finally:
        store.close()


def test_bootstrap_max_expand_seconds_stops_legacy_expansion(monkeypatch):
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        ticks = iter([0.0, 0.0, 2.0, 2.0, 2.0])
        monkeypatch.setattr("citegeist.bootstrap.time.monotonic", lambda: next(ticks))
        calls: list[str] = []

        bootstrapper.crossref_expander.expand_entry_references = lambda _store, key: (calls.append(f"crossref:{key}") or [])  # type: ignore[method-assign]
        bootstrapper.openalex_expander.expand_entry = lambda _store, key, relation_type="cites", limit=5: (calls.append(f"openalex:{key}") or [])  # type: ignore[method-assign]

        bootstrapper.bootstrap(
            store,
            seed_bibtex="""
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}

@article{seed2023,
  author = {Seed, Bob},
  title = {Older Seed},
  year = {2023}
}
""",
            expansion_mode="legacy",
            expand=True,
            max_expand_seconds=1.0,
        )

        assert len(calls) <= 2
    finally:
        store.close()


def test_bootstrap_preview_uses_topic_commit_limit_when_larger_than_topic_limit():
    store = BibliographyStore()
    try:
        bootstrapper = Bootstrapper()
        from citegeist import BibEntry

        bootstrapper.resolver.search_openalex = lambda topic, limit=5: [  # type: ignore[method-assign]
            BibEntry(
                entry_type="article",
                citation_key=f"rank{index}",
                fields={
                    "title": f"Preview Topic Result {index}",
                    "author": f"Author, {index}",
                    "year": f"20{index:02d}",
                    "abstract": f"Abstract {index}",
                },
            )
            for index in range(1, 8)
        ][:limit]
        bootstrapper.resolver.search_pubmed = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_crossref = lambda topic, limit=5: []  # type: ignore[method-assign]
        bootstrapper.resolver.search_datacite = lambda topic, limit=5: []  # type: ignore[method-assign]

        results = bootstrapper.bootstrap(
            store,
            topic="graph topic",
            expand=False,
            preview_only=True,
            topic_limit=5,
            topic_commit_limit=7,
        )

        assert [item.citation_key for item in results] == [
            "rank1",
            "rank2",
            "rank3",
            "rank4",
            "rank5",
            "rank6",
            "rank7",
        ]
        assert results[0].author == "Author, 1"
        assert results[0].year == "2001"
        assert results[0].abstract == "Abstract 1"
    finally:
        store.close()
