from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import json
import os
from pathlib import Path
from typing import Any

from .app_api import LiteratureExplorerApi
from .storage import BibliographyStore


class LiteratureExplorerAppServer:
    def __init__(self, api: LiteratureExplorerApi, *, api_token: str | None = None) -> None:
        self.api = api
        self.api_token = (api_token or "").strip() or None

    def dispatch(self, method: str, params: dict[str, Any] | None = None) -> Any:
        params = params or {}
        if method == "capabilities":
            return self.api.capabilities()
        if method == "search":
            return self.api.search(
                str(params.get("query") or ""),
                limit=int(params.get("limit", 20)),
                topic_slug=_optional_str(params.get("topic_slug")),
            )
        if method == "show_entry":
            return self.api.show_entry(
                str(params.get("citation_key") or ""),
                include_provenance=bool(params.get("include_provenance", False)),
                include_conflicts=bool(params.get("include_conflicts", False)),
                include_bibtex=bool(params.get("include_bibtex", False)),
            )
        if method == "list_topics":
            return self.api.list_topics(
                limit=int(params.get("limit", 100)),
                phrase_review_status=_optional_str(params.get("phrase_review_status")),
            )
        if method == "get_topic":
            return self.api.get_topic(
                str(params.get("topic_slug") or ""),
                entry_limit=int(params.get("entry_limit", 100)),
            )
        if method == "export_topic_bibtex":
            return self.api.export_topic_bibtex(
                str(params.get("topic_slug") or ""),
                include_stubs=bool(params.get("include_stubs", False)),
            )
        if method == "bootstrap":
            return self.api.bootstrap(
                seed_bibtex=_optional_str(params.get("seed_bibtex")),
                topic=_optional_str(params.get("topic")),
                topic_slug=_optional_str(params.get("topic_slug")),
                topic_name=_optional_str(params.get("topic_name")),
                topic_phrase=_optional_str(params.get("topic_phrase")),
                topic_limit=int(params.get("topic_limit", 5)),
                topic_commit_limit=_optional_int(params.get("topic_commit_limit")),
                expand=bool(params.get("expand", True)),
                preview_only=bool(params.get("preview_only", False)),
                review_status=str(params.get("review_status") or "draft"),
                expansion_mode=str(params.get("expansion_mode") or "legacy"),
                expansion_rounds=int(params.get("expansion_rounds", 1)),
                recent_years=_optional_int(params.get("recent_years")),
                target_recent_entries=_optional_int(params.get("target_recent_entries")),
                max_expanded_entries=_optional_int(params.get("max_expanded_entries")),
                max_expand_seconds=_optional_float(params.get("max_expand_seconds")),
            )
        if method == "expand_topic":
            return self.api.expand_topic(
                str(params.get("topic_slug") or ""),
                topic_phrase=_optional_str(params.get("topic_phrase")),
                source=str(params.get("source") or "openalex"),
                relation_type=str(params.get("relation_type") or "cites"),
                seed_limit=int(params.get("seed_limit", 25)),
                per_seed_limit=int(params.get("per_seed_limit", 25)),
                min_relevance=float(params.get("min_relevance", 0.2)),
                seed_keys=_string_list(params.get("seed_keys")),
                preview_only=bool(params.get("preview_only", False)),
                max_rounds=int(params.get("max_rounds", 1)),
                recent_years=_optional_int(params.get("recent_years")),
                target_recent_entries=_optional_int(params.get("target_recent_entries")),
            )
        if method == "extract_text":
            return self.api.extract_text(
                str(params.get("text") or ""),
                backend=str(params.get("backend") or "heuristic"),
            )
        if method == "verify_strings":
            return self.api.verify_strings(
                _string_list(params.get("values")),
                context=str(params.get("context") or ""),
                limit=int(params.get("limit", 5)),
            )
        if method == "verify_bibtex":
            return self.api.verify_bibtex(
                str(params.get("bibtex_text") or ""),
                context=str(params.get("context") or ""),
                limit=int(params.get("limit", 5)),
            )
        if method == "graph":
            return self.api.graph(
                _string_list(params.get("seed_keys")),
                relation_types=_string_list(params.get("relation_types")),
                depth=int(params.get("depth", 1)),
                review_status=_optional_str(params.get("review_status")),
                missing_only=bool(params.get("missing_only", False)),
            )
        raise KeyError(f"Unknown method: {method}")


def create_request_handler(server: LiteratureExplorerAppServer):
    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._write_cors_headers()
            self.end_headers()

        def do_POST(self) -> None:
            if self.path != "/call":
                self._write_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            if not _request_is_authorized(self.headers, server.api_token):
                self._write_unauthorized()
                return
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
                payload = json.loads(body.decode("utf-8") or "{}")
                method = str(payload.get("method") or "")
                params = payload.get("params") or {}
                if not isinstance(params, dict):
                    raise ValueError("params must be an object")
                result = server.dispatch(method, params)
                self._write_json({"ok": True, "result": result})
            except KeyError as exc:
                self._write_json({"ok": False, "error": str(exc)}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:  # pragma: no cover - defensive fallback
                self._write_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._write_json({"ok": True})
                return
            if self.path == "/capabilities":
                if not _request_is_authorized(self.headers, server.api_token):
                    self._write_unauthorized()
                    return
                self._write_json({"ok": True, "result": server.dispatch("capabilities", {})})
                return
            self._write_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self._write_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-API-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _write_unauthorized(self) -> None:
            body = json.dumps({"ok": False, "error": "unauthorized"}, indent=2).encode("utf-8")
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self._write_cors_headers()
            self.send_header("WWW-Authenticate", 'Bearer realm="citegeist"')
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a lightweight local HTTP bridge for the CiteGeist literature explorer demo")
    parser.add_argument("--db", default="library.sqlite3", help="SQLite database path")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8765, help="Bind port")
    parser.add_argument("--api-token", default=None, help="Optional bearer token required for API access")
    args = parser.parse_args(argv)

    store = BibliographyStore(Path(args.db))
    api = LiteratureExplorerApi(store)
    api_token = args.api_token or os.environ.get("CITEGEIST_API_TOKEN")
    server = LiteratureExplorerAppServer(api, api_token=api_token)
    httpd = HTTPServer((args.host, args.port), create_request_handler(server))
    try:
        print(f"CiteGeist explorer server listening on http://{args.host}:{args.port}")
        httpd.serve_forever()
    finally:
        httpd.server_close()
        store.close()
    return 0


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def _request_is_authorized(headers: Any, api_token: str | None) -> bool:
    if not api_token:
        return True
    bearer_value = _extract_bearer_token(headers)
    if bearer_value == api_token:
        return True
    header_token = headers.get("X-API-Token", "").strip() if headers else ""
    return header_token == api_token


def _extract_bearer_token(headers: Any) -> str | None:
    if not headers:
        return None
    authorization = headers.get("Authorization", "")
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    value = value.strip()
    return value or None


if __name__ == "__main__":
    raise SystemExit(main())
