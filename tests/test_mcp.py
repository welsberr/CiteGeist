from __future__ import annotations

from citegeist.mcp import handle_request


def test_mcp_lists_tools() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert {"parse_bibtex", "render_bibtex", "extract_references", "search_database", "show_entry"} <= names


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
