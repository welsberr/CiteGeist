from citegeist import BibliographyStore
from citegeist.app_api import LiteratureExplorerApi
from citegeist.bibtex import BibEntry
from citegeist.bootstrap import BootstrapResult
from citegeist.expand import ExpansionResult


class FakeBootstrapper:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def bootstrap(self, store, **kwargs):
        self.calls.append(dict(kwargs))
        if not kwargs.get("preview_only"):
            store.ensure_topic("graph-topic", "Graph Topic", source_type="bootstrap", expansion_phrase="graph topic")
            store.upsert_entry(
                BibEntry(
                    entry_type="article",
                    citation_key="topic2024graph",
                    fields={"title": "Graph Topic Result", "year": "2024"},
                ),
                source_type="bootstrap",
                source_label="topic:graph topic",
            )
            store.add_entry_topic(
                "topic2024graph",
                topic_slug="graph-topic",
                topic_name="Graph Topic",
                source_type="bootstrap",
                source_label="topic:graph topic",
                confidence=4.0,
            )
            store.connection.commit()
        return [
            BootstrapResult(
                citation_key="topic2024graph",
                origin="topic",
                created=True,
                score=4.0,
                title="Graph Topic Result",
                year="2024",
            )
        ]


class FakeTopicExpander:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def expand_topic(self, store, topic_slug, **kwargs):
        self.calls.append({"topic_slug": topic_slug, **kwargs})
        preview_only = kwargs.get("preview_only", False)
        if not preview_only:
            store.upsert_entry(
                BibEntry(
                    entry_type="article",
                    citation_key="discovered2025graph",
                    fields={"title": "Graph Exploration Result", "year": "2025"},
                ),
                source_type="graph_expand",
                source_label="openalex:cites:seed2024",
            )
            store.add_entry_topic(
                "discovered2025graph",
                topic_slug=topic_slug,
                topic_name="Graph Topic",
                source_type="topic_expand",
                source_label="openalex:cites:seed2024",
                confidence=0.8,
            )
            store.connection.commit()
        return [
            ExpansionResult(
                source_citation_key="seed2024",
                discovered_citation_key="discovered2025graph",
                created_entry=True,
                relation_type="cites",
                source_label="openalex:cites:seed2024",
            )
        ]


def test_literature_explorer_api_search_and_show_entry():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Graph Topic Result},
  year = {2024}
}
"""
        )
        store.add_entry_topic("seed2024", topic_slug="graph-topic", topic_name="Graph Topic", source_label="seed")
        api = LiteratureExplorerApi(store)

        search_payload = api.search("graph")
        assert search_payload["results"][0]["citation_key"] == "seed2024"

        entry_payload = api.show_entry("seed2024", include_bibtex=True)
        assert entry_payload is not None
        assert entry_payload["citation_key"] == "seed2024"
        assert entry_payload["topics"][0]["slug"] == "graph-topic"
        assert "@article{seed2024," in entry_payload["bibtex"]
    finally:
        store.close()


def test_literature_explorer_api_capabilities_distinguish_metadata_and_expansion_sources():
    store = BibliographyStore()
    try:
        api = LiteratureExplorerApi(store)

        payload = api.capabilities()

        assert payload["metadata_sources"] == ["crossref", "datacite", "openalex", "pubmed"]
        assert payload["topic_seed_sources"] == ["crossref", "datacite", "openalex", "pubmed"]
        assert payload["graph_expansion_sources"] == ["crossref", "openalex"]
        assert payload["topic_expansion_sources"] == ["crossref", "openalex"]
        assert payload["graph_relation_types"] == ["cites", "cited_by", "both"]
    finally:
        store.close()


def test_literature_explorer_api_bootstrap_returns_topic_payload():
    store = BibliographyStore()
    try:
        bootstrapper = FakeBootstrapper()
        api = LiteratureExplorerApi(store, bootstrapper=bootstrapper)
        payload = api.bootstrap(
            topic="graph topic",
            topic_slug="graph-topic",
            topic_name="Graph Topic",
            preview_only=False,
            expand=False,
            expansion_mode="both",
            expansion_rounds=3,
            recent_years=5,
            target_recent_entries=10,
            max_expanded_entries=120,
            max_expand_seconds=18.5,
        )

        assert payload["topic"]["slug"] == "graph-topic"
        assert payload["entries"][0]["citation_key"] == "topic2024graph"
        assert payload["results"][0]["citation_key"] == "topic2024graph"
        assert bootstrapper.calls[0]["expansion_mode"] == "both"
        assert bootstrapper.calls[0]["expansion_rounds"] == 3
        assert bootstrapper.calls[0]["recent_years"] == 5
        assert bootstrapper.calls[0]["target_recent_entries"] == 10
        assert bootstrapper.calls[0]["max_expanded_entries"] == 120
        assert bootstrapper.calls[0]["max_expand_seconds"] == 18.5
    finally:
        store.close()


def test_literature_explorer_api_exports_topic_bibtex():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Graph Seed},
  year = {2024}
}
"""
        )
        store.add_entry_topic("seed2024", topic_slug="graph-topic", topic_name="Graph Topic", source_label="seed")
        api = LiteratureExplorerApi(store)

        payload = api.export_topic_bibtex("graph-topic")

        assert payload is not None
        assert payload["topic"]["slug"] == "graph-topic"
        assert payload["entry_count"] == 1
        assert "@article{seed2024," in payload["bibtex"]
    finally:
        store.close()


def test_literature_explorer_api_topic_export_skips_malformed_creator_entries():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{good2024,
  author = {Seed, Alice},
  title = {Usable Entry},
  year = {2024}
}

@article{bad2024,
  author = {Normal, Person},
  title = {Broken Entry},
  year = {2024}
}
"""
        )
        store.add_entry_topic("good2024", topic_slug="graph-topic", topic_name="Graph Topic", source_label="seed")
        store.add_entry_topic("bad2024", topic_slug="graph-topic", topic_name="Graph Topic", source_label="seed")
        store.connection.execute(
            """
            UPDATE creators
            SET full_name = 'Franck, Jean-Louis, Georges, MALIGE'
            WHERE full_name = 'Normal, Person'
            """
        )
        store.connection.commit()
        api = LiteratureExplorerApi(store)

        payload = api.export_topic_bibtex("graph-topic")

        assert payload is not None
        assert payload["entry_count"] == 2
        assert payload["exported_count"] == 1
        assert "@article{good2024," in payload["bibtex"]
        assert "@article{bad2024," not in payload["bibtex"]
        assert payload["skipped"][0]["citation_key"] == "bad2024"
        assert "Too many commas" in payload["skipped"][0]["error"]
    finally:
        store.close()


def test_literature_explorer_api_expand_topic_returns_updated_entries():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Graph Seed},
  year = {2024}
}
"""
        )
        store.add_entry_topic("seed2024", topic_slug="graph-topic", topic_name="Graph Topic", source_label="seed")
        topic_expander = FakeTopicExpander()
        api = LiteratureExplorerApi(store, topic_expander=topic_expander)

        payload = api.expand_topic(
            "graph-topic",
            preview_only=False,
            relation_type="both",
            max_rounds=3,
            recent_years=5,
            target_recent_entries=10,
        )

        assert payload is not None
        assert payload["results"][0]["discovered_citation_key"] == "discovered2025graph"
        assert any(item["citation_key"] == "discovered2025graph" for item in payload["entries"])
        assert topic_expander.calls[0]["relation_type"] == "both"
        assert topic_expander.calls[0]["max_rounds"] == 3
        assert topic_expander.calls[0]["recent_years"] == 5
        assert topic_expander.calls[0]["target_recent_entries"] == 10
    finally:
        store.close()


def test_literature_explorer_api_extract_verify_and_graph_payloads():
    store = BibliographyStore()
    try:
        store.ingest_bibtex(
            """
@article{seed2024,
  author = {Seed, Alice},
  title = {Graph Seed},
  year = {2024},
  references = {child2025}
}

@article{child2025,
  author = {Child, Bob},
  title = {Graph Child},
  year = {2025}
}
"""
        )
        api = LiteratureExplorerApi(store)

        extract_payload = api.extract_text("Smith, J., 2024, Graph Topic Result: Journal of Graph Studies, v. 1, p. 1-10.")
        assert extract_payload["entries"]
        assert extract_payload["entries"][0]["citation_key"]

        verify_payload = api.verify_strings(["\"Graph Topic Result\" Smith 2024"], limit=1)
        assert "results" in verify_payload
        assert verify_payload["results"][0]["query"]

        graph_payload = api.graph(["seed2024"], depth=1)
        assert [node["id"] for node in graph_payload["nodes"]] == ["child2025", "seed2024"]
        assert graph_payload["edges"][0]["source"] == "seed2024"
        assert graph_payload["edges"][0]["target"] == "child2025"
    finally:
        store.close()
