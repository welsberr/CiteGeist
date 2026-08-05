from __future__ import annotations

import json
from unittest.mock import patch

from citegeist import BibEntry
from citegeist.mcp import handle_request
from citegeist.storage import BibliographyStore


def test_mcp_lists_tools() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert {
        "parse_bibtex",
        "render_bibtex",
        "extract_references",
        "search_database",
        "show_entry",
        "database_status",
        "search_topic",
        "expand_topic",
    } <= names


def test_mcp_parses_bibtex() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "parse_bibtex",
                "arguments": {
                    "text": "@article{darwin1859, title={Origin}, author={Darwin, Charles}, year={1859}}"
                },
            },
        }
    )
    if "error" in response:
        assert "pybtex is required" in response["error"]["message"]
        return
    text = response["result"]["content"][0]["text"]
    assert '"entry_count": 1' in text
    assert '"citation_key": "darwin1859"' in text


def test_mcp_reports_unknown_tool() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "missing", "arguments": {}},
        }
    )
    assert response["error"]["code"] == -32000
    assert "Unknown tool" in response["error"]["message"]


def test_mcp_reports_database_status(tmp_path) -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "database_status", "arguments": {"db": str(tmp_path / "library.sqlite3")}},
        }
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["health"] == "empty"


def test_mcp_searches_topic(tmp_path) -> None:
    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.upsert_entry(
            BibEntry(
                entry_type="article",
                citation_key="seed2024",
                fields={"title": "Graph Topic Seed", "year": "2024"},
            ),
            source_type="test",
            source_label="fixture",
            fulltext="graph networks biology",
        )
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_label="topic-seed",
        )
        store.connection.commit()
    finally:
        store.close()

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "search_topic",
                "arguments": {
                    "db": str(database),
                    "topic_slug": "graph-methods",
                    "query": "graph",
                },
            },
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["topic"]["slug"] == "graph-methods"
    assert payload["results"][0]["citation_key"] == "seed2024"


def test_mcp_searches_topic_with_hyphenated_query(tmp_path) -> None:
    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.upsert_entry(
            BibEntry(
                entry_type="article",
                citation_key="natural2024",
                fields={"title": "Natural Selection", "year": "2024"},
            ),
            source_type="test",
            source_label="fixture",
        )
        store.add_entry_topic(
            "natural2024",
            topic_slug="natural-selection",
            topic_name="Natural Selection",
            source_label="topic-seed",
        )
        store.connection.commit()
    finally:
        store.close()

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "search_topic",
                "arguments": {
                    "db": str(database),
                    "topic_slug": "natural-selection",
                    "query": "natural-selection",
                },
            },
        }
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["results"][0]["citation_key"] == "natural2024"


def test_mcp_reports_search_query_error_code():
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "search_database", "arguments": {"db": ":memory:", "query": "   "}},
        }
    )
    assert response["error"]["data"]["code"] == "search_query_error"


def test_mcp_expands_topic_with_preview_default(tmp_path) -> None:
    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.ensure_topic("graph-methods", "Graph Methods")
        store.connection.commit()
    finally:
        store.close()

    with patch("citegeist.mcp.LiteratureExplorerApi.expand_topic") as mocked_expand:
        mocked_expand.return_value = {
            "topic": {"slug": "graph-methods", "name": "Graph Methods"},
            "preview": True,
            "results": [],
            "entries": [],
            "run_meta": {},
        }
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "expand_topic",
                    "arguments": {
                        "db": str(database),
                        "topic_slug": "graph-methods",
                        "topic_phrase": "graph networks biology",
                        "seed_keys": ["seed2024"],
                    },
                },
            }
        )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["preview"] is True
    _, kwargs = mocked_expand.call_args
    assert kwargs["preview_only"] is True
    assert kwargs["topic_phrase"] == "graph networks biology"
    assert kwargs["seed_keys"] == ["seed2024"]
