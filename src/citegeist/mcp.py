from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .bibtex import BibEntry, parse_bibtex, render_bibtex
from .extract import extract_references
from .storage import BibliographyStore


SERVER_INFO = {"name": "citegeist-mcp", "version": "0.1.0"}


def _json_text(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}


def _parse_bibtex(arguments: dict[str, Any]) -> dict[str, Any]:
    if "text" in arguments:
        text = arguments["text"]
    else:
        text = Path(arguments["path"]).read_text(encoding="utf-8")
    entries = parse_bibtex(text)
    return _json_text(
        {
            "entry_count": len(entries),
            "entries": [
                {
                    "entry_type": entry.entry_type,
                    "citation_key": entry.citation_key,
                    "fields": entry.fields,
                }
                for entry in entries
            ],
        }
    )


def _render_bibtex(arguments: dict[str, Any]) -> dict[str, Any]:
    entries = [
        BibEntry(
            entry_type=item["entry_type"],
            citation_key=item["citation_key"],
            fields=dict(item.get("fields", {})),
        )
        for item in arguments.get("entries", [])
    ]
    return {"content": [{"type": "text", "text": render_bibtex(entries)}]}


def _extract_references(arguments: dict[str, Any]) -> dict[str, Any]:
    if "text" in arguments:
        text = arguments["text"]
    else:
        text = Path(arguments["path"]).read_text(encoding="utf-8")
    entries = extract_references(text, backend_name=arguments.get("backend", "heuristic"))
    return _json_text(
        {
            "entry_count": len(entries),
            "entries": [
                {
                    "entry_type": entry.entry_type,
                    "citation_key": entry.citation_key,
                    "fields": entry.fields,
                }
                for entry in entries
            ],
        }
    )


def _search_database(arguments: dict[str, Any]) -> dict[str, Any]:
    store = BibliographyStore(arguments.get("db", "library.sqlite3"))
    try:
        payload = {
            "results": store.search_text(
                arguments["query"],
                limit=int(arguments.get("limit", 10)),
                topic_slug=arguments.get("topic"),
            )
        }
    finally:
        store.close()
    return _json_text(payload)


def _show_entry(arguments: dict[str, Any]) -> dict[str, Any]:
    store = BibliographyStore(arguments.get("db", "library.sqlite3"))
    try:
        if arguments.get("citation_key"):
            payload = store.get_entry(arguments["citation_key"])
        else:
            payload = {"entries": store.list_entries(limit=int(arguments.get("limit", 20)))}
    finally:
        store.close()
    return _json_text(payload)


TOOLS: dict[str, dict[str, Any]] = {
    "parse_bibtex": {
        "description": "Parse BibTeX text or a BibTeX file into structured entries.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "path": {"type": "string"}},
        },
        "handler": _parse_bibtex,
    },
    "render_bibtex": {
        "description": "Render structured BibTeX entries back to BibTeX.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entry_type": {"type": "string"},
                            "citation_key": {"type": "string"},
                            "fields": {"type": "object"},
                        },
                        "required": ["entry_type", "citation_key", "fields"],
                    },
                }
            },
            "required": ["entries"],
        },
        "handler": _render_bibtex,
    },
    "extract_references": {
        "description": "Extract draft BibTeX entries from plaintext references.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "path": {"type": "string"},
                "backend": {"type": "string", "default": "heuristic"},
            },
        },
        "handler": _extract_references,
    },
    "search_database": {
        "description": "Search a local CiteGeist SQLite bibliography database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
                "topic": {"type": "string"},
            },
            "required": ["query"],
        },
        "handler": _search_database,
    },
    "show_entry": {
        "description": "Show one CiteGeist entry or list entries from a local database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db": {"type": "string"},
                "citation_key": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
        "handler": _show_entry,
    },
}


def list_tools() -> list[dict[str, Any]]:
    return [
        {key: value for key, value in tool.items() if key != "handler"} | {"name": name}
        for name, tool in TOOLS.items()
    ]


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    try:
        if method == "initialize":
            result = {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            result = {"tools": list_tools()}
        elif method == "tools/call":
            name = params.get("name")
            tool = TOOLS.get(name)
            if tool is None:
                raise ValueError(f"Unknown tool: {name}")
            handler: Callable[[dict[str, Any]], dict[str, Any]] = tool["handler"]
            result = handler(params.get("arguments") or {})
        else:
            raise ValueError(f"Unsupported method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def serve(input_stream=sys.stdin, output_stream=sys.stdout) -> None:
    for line in input_stream:
        if not line.strip():
            continue
        response = handle_request(json.loads(line))
        if response is not None:
            output_stream.write(json.dumps(response) + "\n")
            output_stream.flush()


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
