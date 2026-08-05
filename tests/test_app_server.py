from types import SimpleNamespace

from citegeist import BibliographyStore
from citegeist.app_api import LiteratureExplorerApi
from citegeist.bibtex import BibEntry
from citegeist.bootstrap import BootstrapResult
from citegeist.app_server import (
    LiteratureExplorerAppServer,
    _extract_bearer_token,
    _request_is_authorized,
    create_request_handler,
)
from citegeist.verify import VerificationMatch, VerificationResult


class FakeBootstrapper:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def bootstrap(self, store, **kwargs):
        self.calls.append(dict(kwargs))
        return [
            BootstrapResult(
                citation_key="graph2026topic",
                origin="topic",
                created=True,
                score=4.0,
                title="Graph Topic Result",
                year="2026",
            )
        ]


class FakeVerifier:
    def verify_strings(self, values, context="", limit=5):
        return []

    def verify_string(self, value: str, context: str = "", limit: int = 5):
        return VerificationResult(
            query=value,
            context=context,
            status="high_confidence",
            confidence=0.88,
            entry=BibEntry(
                entry_type="article",
                citation_key="support2024",
                fields={"title": "Support Paper", "year": "2024"},
            ),
            source_label="openalex:search:Support Paper",
            alternates=[
                VerificationMatch(
                    entry=BibEntry(
                        entry_type="article",
                        citation_key="alt2023",
                        fields={"title": "Alternate Support", "year": "2023"},
                    ),
                    score=0.66,
                    source_label="crossref:search:Alternate Support",
                )
            ],
            input_type="string",
            input_key=None,
        )


def test_literature_explorer_app_server_dispatch_search():
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
        server = LiteratureExplorerAppServer(LiteratureExplorerApi(store))

        payload = server.dispatch("search", {"query": "graph", "limit": 5})

        assert payload["results"][0]["citation_key"] == "seed2024"
    finally:
        store.close()


def test_literature_explorer_app_server_dispatch_database_status():
    store = BibliographyStore()
    try:
        payload = LiteratureExplorerAppServer(LiteratureExplorerApi(store)).dispatch("database_status")
        assert payload["health"] == "empty"
    finally:
        store.close()


def test_literature_explorer_app_server_dispatch_exports_topic_bibtex():
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
        server = LiteratureExplorerAppServer(LiteratureExplorerApi(store))

        payload = server.dispatch("export_topic_bibtex", {"topic_slug": "graph-topic"})

        assert payload["entry_count"] == 1
        assert "@article{seed2024," in payload["bibtex"]
    finally:
        store.close()


def test_literature_explorer_app_server_dispatch_expand_topic_with_new_controls():
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
        server = LiteratureExplorerAppServer(LiteratureExplorerApi(store))

        payload = server.dispatch(
            "expand_topic",
            {
                "topic_slug": "graph-topic",
                "relation_type": "both",
                "max_rounds": 3,
                "recent_years": 5,
                "target_recent_entries": 10,
                "preview_only": True,
            },
        )

        assert payload["preview"] is True
        assert "results" in payload
    finally:
        store.close()


def test_literature_explorer_app_server_dispatch_bootstrap_with_new_caps():
    store = BibliographyStore()
    try:
        bootstrapper = FakeBootstrapper()
        server = LiteratureExplorerAppServer(LiteratureExplorerApi(store, bootstrapper=bootstrapper))

        payload = server.dispatch(
            "bootstrap",
            {
                "topic": "graph topic",
                "topic_slug": "graph-topic",
                "topic_name": "Graph Topic",
                "preview_only": True,
                "expand": False,
                "expansion_mode": "cites",
                "expansion_rounds": 2,
                "recent_years": 5,
                "target_recent_entries": 4,
                "max_expanded_entries": 75,
                "max_expand_seconds": 12.5,
            },
        )

        assert payload["preview"] is True
        assert "results" in payload
        assert bootstrapper.calls[0]["expansion_mode"] == "cites"
        assert bootstrapper.calls[0]["max_expanded_entries"] == 75
        assert bootstrapper.calls[0]["max_expand_seconds"] == 12.5
    finally:
        store.close()


def test_literature_explorer_app_server_dispatch_support_claims():
    store = BibliographyStore()
    try:
        server = LiteratureExplorerAppServer(LiteratureExplorerApi(store, verifier=FakeVerifier()))

        payload = server.dispatch(
            "support_claims",
            {
                "text": """
Long claim text about agents evolving intelligent movement strategies in multiple computational settings without enough direct support [1].

References

[[1]]Earlier Cited Paper
""",
                "context": "artificial life",
                "limit": 3,
                "max_claims": 2,
                "min_claim_chars": 40,
            },
        )

        assert payload["context"] == "artificial life"
        assert payload["suggestion_count"] == 1
        assert payload["suggestions"][0]["suggested_references"][0]["citation_key"] == "support2024"
    finally:
        store.close()


def test_literature_explorer_http_handler_class_can_be_created():
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
        app_server = LiteratureExplorerAppServer(LiteratureExplorerApi(store))
        handler = create_request_handler(app_server)

        assert handler is not None
        assert issubclass(handler, object)
    finally:
        store.close()


def test_request_authorization_accepts_bearer_and_header_token():
    headers = SimpleNamespace(
        get=lambda key, default="": {
            "Authorization": "Bearer secret-token",
            "X-API-Token": "secret-token",
        }.get(key, default)
    )

    assert _extract_bearer_token(headers) == "secret-token"
    assert _request_is_authorized(headers, "secret-token") is True


def test_request_authorization_rejects_missing_or_wrong_token():
    missing_headers = SimpleNamespace(get=lambda key, default="": default)
    wrong_headers = SimpleNamespace(
        get=lambda key, default="": {
            "Authorization": "Bearer wrong-token",
            "X-API-Token": "",
        }.get(key, default)
    )

    assert _request_is_authorized(missing_headers, "secret-token") is False
    assert _request_is_authorized(wrong_headers, "secret-token") is False
    assert _request_is_authorized(missing_headers, None) is True
