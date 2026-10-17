from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Literal

from .bibtex import BibEntry


DEFAULT_SYSTEM_PROMPT = (
    "You are a meticulous bibliography verification assistant. "
    "You never invent DOIs, page ranges, venues, or identifiers. "
    "You may only suggest missing clues from the provided input and context. "
    "When uncertain, return null or an empty list. "
    "Always respond with strict JSON matching the requested shape."
)

LlmOutcomeStatus = Literal[
    "disabled",
    "success",
    "abstained",
    "invalid_response",
    "timeout",
    "provider_error",
]


@dataclass(frozen=True, slots=True)
class VerificationLlmOutcome:
    """Typed diagnostic for the most recent clue or ranking operation."""

    operation: Literal["expand", "rerank"]
    status: LlmOutcomeStatus
    detail: str | None = None


class _InvalidModelResponse(ValueError):
    pass


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
        max_output_tokens: int = 512,
        post_json: Callable[[str, dict[str, Any], dict[str, str], int], dict[str, Any]] | None = None,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        self.timeout_s = timeout_s
        self.max_output_tokens = max_output_tokens
        self._post_json = post_json or _default_post_json
        self.last_outcome: VerificationLlmOutcome | None = None
        self.outcomes: dict[Literal["expand", "rerank"], VerificationLlmOutcome] = {}

    def _record_outcome(
        self,
        operation: Literal["expand", "rerank"],
        status: LlmOutcomeStatus,
        detail: str | None = None,
    ) -> None:
        outcome = VerificationLlmOutcome(operation, status, detail)
        self.last_outcome = outcome
        self.outcomes[operation] = outcome

    def analyze_query(
        self,
        config: VerificationLlmConfig,
        free_text: str,
        context: str,
    ) -> dict[str, Any] | None:
        if not config.enabled_for("expand"):
            self._record_outcome("expand", "disabled")
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
        try:
            result = self._chat_json(config, payload)
            clues = _validate_clues(result)
        except _InvalidModelResponse as exc:
            self._record_outcome("expand", "invalid_response", str(exc))
            return None
        except Exception as exc:
            self._record_outcome("expand", _failure_status(exc), _error_detail(exc))
            return None
        useful = bool(clues["title"] or clues["year"] or clues["venue"] or clues["authors"] or clues["keywords"])
        self._record_outcome("expand", "success" if useful else "abstained")
        return clues

    def rerank_candidates(
        self,
        config: VerificationLlmConfig,
        query_fields: dict[str, object],
        context: str,
        candidates: list[BibEntry],
    ) -> list[int] | None:
        if not config.enabled_for("rerank"):
            self._record_outcome("rerank", "disabled")
            return None
        if not candidates:
            self._record_outcome("rerank", "abstained", "No candidates were supplied.")
            return None
        submitted_count = min(len(candidates), 8)
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
        try:
            result = self._chat_json(config, payload)
            indices = _validate_ranking(result, submitted_count)
        except _InvalidModelResponse as exc:
            self._record_outcome("rerank", "invalid_response", str(exc))
            return None
        except Exception as exc:
            self._record_outcome("rerank", _failure_status(exc), _error_detail(exc))
            return None
        if not indices:
            self._record_outcome("rerank", "abstained")
            return None
        self._record_outcome("rerank", "success")
        return indices

    def _chat_json(self, config: VerificationLlmConfig, payload: dict[str, Any]) -> Any:
        if _llm_mode(config.base_url, config.provider) == "openai":
            return self._chat_openai(config, payload)
        return self._chat_ollama_native(config, payload)

    def _chat_openai(self, config: VerificationLlmConfig, payload: dict[str, Any]) -> Any:
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        body = {
            "model": config.model,
            "temperature": 0,
            "max_tokens": self.max_output_tokens,
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
        content = _extract_content(data, ("choices", 0, "message", "content"))
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
            "options": {"temperature": 0, "num_predict": self.max_output_tokens},
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
        content = _extract_content(data, ("message", "content"))
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


def _validate_clues(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _InvalidModelResponse("Expected a JSON object for bibliographic clues.")
    allowed = {"title", "authors", "year", "venue", "keywords"}
    if value.keys() - allowed:
        raise _InvalidModelResponse("Clue response contains unsupported fields.")
    for field in ("authors", "keywords"):
        if field not in value or not isinstance(value[field], list):
            raise _InvalidModelResponse(f"Clue field '{field}' must be a list of strings.")
        if any(not isinstance(item, str) for item in value[field]):
            raise _InvalidModelResponse(f"Clue field '{field}' must contain only strings.")
    for field in ("title", "year", "venue"):
        if field in value and value[field] is not None and not isinstance(value[field], str):
            raise _InvalidModelResponse(f"Clue field '{field}' must be a string or null.")
    normalized = {
        field: (value.get(field, "") or "").strip() or None
        for field in ("title", "year", "venue")
    }
    normalized["authors"] = [item.strip() for item in value["authors"] if item.strip()]
    normalized["keywords"] = [item.strip() for item in value["keywords"] if item.strip()]
    return normalized


def _validate_ranking(value: Any, submitted_count: int) -> list[int]:
    if not isinstance(value, list):
        raise _InvalidModelResponse("Expected a JSON array of candidate indices.")
    if any(isinstance(index, bool) or not isinstance(index, int) for index in value):
        raise _InvalidModelResponse("Candidate ranks must be integer indices.")
    if any(index < 0 or index >= submitted_count for index in value):
        raise _InvalidModelResponse("Candidate rank is outside the submitted candidate subset.")
    if len(value) != len(set(value)):
        raise _InvalidModelResponse("Candidate ranks must not contain duplicates.")
    return value


def _extract_content(data: Any, path: tuple[object, ...]) -> str:
    current = data
    try:
        for part in path:
            current = current[part]  # type: ignore[index]
    except (KeyError, IndexError, TypeError) as exc:
        raise _InvalidModelResponse("Provider response did not contain message content.") from exc
    if not isinstance(current, str) or not current.strip():
        raise _InvalidModelResponse("Provider returned empty or non-text message content.")
    return current


def _failure_status(exc: Exception) -> Literal["timeout", "provider_error"]:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, (TimeoutError, socket.timeout)):
        return "timeout"
    return "provider_error"


def _error_detail(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _loads_lenient_json(content: str) -> Any:
    if not isinstance(content, str):
        raise _InvalidModelResponse("Model response content must be text.")
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_object_pairs,
            parse_constant=_reject_non_finite,
        )
    except _InvalidModelResponse:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _InvalidModelResponse("Model response must contain exactly one complete JSON value.") from exc


def _unique_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidModelResponse(f"Model response contains duplicate JSON key '{key}'.")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> Any:
    raise _InvalidModelResponse(f"Model response contains non-finite number '{value}'.")
