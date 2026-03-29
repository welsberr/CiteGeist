from citegeist import BibliographyStore
from citegeist.app_api import LiteratureExplorerApi
from citegeist.app_server import LiteratureExplorerAppServer, create_request_handler


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
