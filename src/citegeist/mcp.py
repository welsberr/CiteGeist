from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .bibtex import BibEntry, parse_bibtex, render_bibtex
from .extract import extract_references
from .app_api import LiteratureExplorerApi
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


def _search_topic(arguments: dict[str, Any]) -> dict[str, Any]:
    topic_slug = arguments.get("topic_slug") or arguments.get("topic")
    if not topic_slug:
        raise ValueError("topic_slug is required")
    limit = int(arguments.get("limit", arguments.get("entry_limit", 20)))
    query = str(arguments.get("query") or "").strip()
    store = BibliographyStore(arguments.get("db", "library.sqlite3"))
    try:
        topic = store.get_topic(topic_slug)
        if topic is None:
            raise ValueError(f"Unknown topic: {topic_slug}")
        payload: dict[str, Any] = {
            "topic": topic,
            "query": query or None,
        }
        if query:
            payload["results"] = store.search_text(query, limit=limit, topic_slug=topic_slug)
        else:
            payload["entries"] = store.list_topic_entries(topic_slug, limit=limit)
    finally:
        store.close()
    return _json_text(payload)


def _expand_topic(arguments: dict[str, Any]) -> dict[str, Any]:
    topic_slug = arguments.get("topic_slug") or arguments.get("topic")
    if not topic_slug:
        raise ValueError("topic_slug is required")
    store = BibliographyStore(arguments.get("db", "library.sqlite3"))
    try:
        api = LiteratureExplorerApi(store)
        payload = api.expand_topic(
            topic_slug,
            topic_phrase=arguments.get("topic_phrase"),
            source=arguments.get("source", "openalex"),
            relation_type=arguments.get("relation_type", arguments.get("relation", "cites")),
            seed_limit=int(arguments.get("seed_limit", 25)),
            per_seed_limit=int(arguments.get("per_seed_limit", 25)),
            min_relevance=float(arguments.get("min_relevance", 0.2)),
            seed_keys=arguments.get("seed_keys"),
            preview_only=bool(arguments.get("preview_only", True)),
            max_rounds=int(arguments.get("max_rounds", arguments.get("rounds", 1))),
            recent_years=arguments.get("recent_years"),
            target_recent_entries=arguments.get("target_recent_entries"),
        )
        if payload is None:
            raise ValueError(f"Unknown topic: {topic_slug}")
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
    "search_topic": {
        "description": "Search or list entries assigned to one CiteGeist topic.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db": {"type": "string"},
                "topic_slug": {"type": "string"},
                "topic": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
        "handler": _search_topic,
    },
    "expand_topic": {
        "description": "Expand one CiteGeist topic from seed entries and assign relevant discoveries back to that topic.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db": {"type": "string"},
                "topic_slug": {"type": "string"},
                "topic": {"type": "string"},
                "topic_phrase": {"type": "string"},
                "source": {"type": "string", "default": "openalex"},
                "relation_type": {"type": "string", "default": "cites"},
                "relation": {"type": "string"},
                "seed_limit": {"type": "integer", "default": 25},
                "per_seed_limit": {"type": "integer", "default": 25},
                "min_relevance": {"type": "number", "default": 0.2},
                "seed_keys": {"type": "array", "items": {"type": "string"}},
                "preview_only": {"type": "boolean", "default": True},
                "max_rounds": {"type": "integer", "default": 1},
                "rounds": {"type": "integer"},
                "recent_years": {"type": "integer"},
                "target_recent_entries": {"type": "integer"},
            },
        },
        "handler": _expand_topic,
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
