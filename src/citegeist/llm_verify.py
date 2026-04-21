from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .bibtex import BibEntry


DEFAULT_SYSTEM_PROMPT = (
    "You are a meticulous bibliography verification assistant. "
    "You never invent DOIs, page ranges, venues, or identifiers. "
    "You may only suggest missing clues from the provided input and context. "
    "When uncertain, return null or an empty list. "
    "Always respond with strict JSON matching the requested shape."
)


@dataclass(slots=True)
class VerificationLlmConfig:
    base_url: str
    model: str
    api_key: str = ""
    provider: str = "auto"
    role: str = "both"

    def enabled_for(self, capability: str) -> bool:
        return bool(self.base_url and self.model) and self.role in {capability, "both"}


class VerificationLlmClient:
    def __init__(
        self,
        *,
        timeout_s: int = 60,
        post_json: Callable[[str, dict[str, Any], dict[str, str], int], dict[str, Any]] | None = None,
    ) -> None:
        self.timeout_s = timeout_s
        self._post_json = post_json or _default_post_json

    def analyze_query(
        self,
        config: VerificationLlmConfig,
        free_text: str,
        context: str,
    ) -> dict[str, Any] | None:
        if not config.enabled_for("expand"):
            return None
        payload = {
            "task": "extract_bibliographic_clues",
            "input": {"free_text": free_text, "context": context},
            "rules": [
                "Never invent a DOI or identifier.",
                "Only fill clues that plausibly follow from the input and context.",
                "Return null for unknown scalar fields.",
            ],
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": ["string", "null"]},
                    "authors": {"type": "array", "items": {"type": "string"}},
                    "year": {"type": ["string", "null"]},
                    "venue": {"type": ["string", "null"]},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["authors", "keywords"],
            },
        }
        result = self._chat_json(config, payload)
        if not isinstance(result, dict):
            return None
        authors = [str(value).strip() for value in result.get("authors", []) if str(value).strip()]
        keywords = [str(value).strip() for value in result.get("keywords", []) if str(value).strip()]
        return {
            "title": _optional_string(result.get("title")),
            "authors": authors,
            "year": _optional_string(result.get("year")),
            "venue": _optional_string(result.get("venue")),
            "keywords": keywords,
        }

    def rerank_candidates(
        self,
        config: VerificationLlmConfig,
        query_fields: dict[str, object],
        context: str,
        candidates: list[BibEntry],
    ) -> list[int] | None:
        if not config.enabled_for("rerank") or not candidates:
            return None
        payload = {
            "task": "rerank_candidates",
            "instruction": (
                "Return a JSON array of candidate indices sorted best to worst. "
                "Do not invent metadata. Prefer candidates that better match the given clues."
            ),
            "input": {
                "query_fields": query_fields,
                "context": context,
                "candidates": [
                    {
                        "title": entry.fields.get("title", ""),
                        "authors": entry.fields.get("author", "").split(" and ") if entry.fields.get("author") else [],
                        "year": entry.fields.get("year", ""),
                        "venue": entry.fields.get("journal", "") or entry.fields.get("booktitle", ""),
                        "doi": entry.fields.get("doi", ""),
                    }
                    for entry in candidates[:8]
                ],
            },
        }
        result = self._chat_json(config, payload)
        if not isinstance(result, list):
            return None
        indices = [value for value in result if isinstance(value, int) and 0 <= value < len(candidates)]
        return indices or None

    def _chat_json(self, config: VerificationLlmConfig, payload: dict[str, Any]) -> Any:
        try:
            if _llm_mode(config.base_url, config.provider) == "openai":
                return self._chat_openai(config, payload)
            return self._chat_ollama_native(config, payload)
        except Exception:
            return None

    def _chat_openai(self, config: VerificationLlmConfig, payload: dict[str, Any]) -> Any:
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        body = {
            "model": config.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
        }
        data = self._post_json(
            config.base_url.rstrip("/") + "/chat/completions",
            body,
            headers,
            self.timeout_s,
        )
        content = data["choices"][0]["message"]["content"]
        return _loads_lenient_json(content)

    def _chat_ollama_native(self, config: VerificationLlmConfig, payload: dict[str, Any]) -> Any:
        base_url = config.base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        body = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            "options": {"temperature": 0},
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        data = self._post_json(
            base_url + "/api/chat",
            body,
            headers,
            self.timeout_s,
        )
        content = data["message"]["content"]
        return _loads_lenient_json(content)


def _default_post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout_s: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _llm_mode(base_url: str, provider: str) -> str:
    if provider == "openai":
        return "openai"
    if provider == "ollama-native":
        return "ollama-native"
    return "openai" if base_url.rstrip("/").endswith("/v1") else "ollama-native"


def _optional_string(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _loads_lenient_json(content: str) -> Any:
    try:
        return json.loads(content)
    except Exception:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", content, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    for opener, closer in (("{", "}"), ("[", "]")):
        start = content.find(opener)
        end = content.rfind(closer)
        if start != -1 and end != -1 and end > start:
            snippet = content[start : end + 1]
            try:
                return json.loads(snippet)
            except Exception:
                continue
    raise ValueError("Model response did not contain parseable JSON")
