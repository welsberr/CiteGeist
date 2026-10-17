"""Private, immutable discovery pools and strict development-label joins."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .research_discovery import DiscoveryReport
from .resolver.identifiers import entry_identifiers, extract_doi


SCHEMA_VERSION = 1
RUBRIC_VERSION = "binary-relevance-v1"
MAX_POOL_BYTES = 8 * 1024 * 1024
MAX_CANDIDATES_PER_CASE = 500
_FIELDS = (
    "title", "abstract", "year", "author", "keywords", "journal", "booktitle",
    "publisher", "doi", "isbn", "eprint", "archiveprefix", "pmid", "openalex",
    "openalex_id",
)
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*:.+$")


class DiscoveryPoolError(ValueError):
    """Raised for malformed, stale, or unsafe discovery-pool artifacts."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _candidate_id(result: Any) -> str:
    fields = result.entry.fields
    doi, arxiv = entry_identifiers(fields)
    if doi:
        return f"doi:{extract_doi(doi).casefold()}"
    if arxiv:
        return f"arxiv:{arxiv.casefold()}"
    for key, scheme, normalize in (
        ("pmid", "pmid", lambda value: value.strip()),
        ("openalex", "openalex", lambda value: value.strip().upper().removeprefix("https://openalex.org/")),
        ("openalex_id", "openalex", lambda value: value.strip().upper().removeprefix("https://openalex.org/")),
        ("isbn", "isbn", lambda value: re.sub(r"[^0-9Xx]", "", value).upper()),
    ):
        value = normalize(str(fields.get(key) or ""))
        if value:
            return f"{scheme}:{value.casefold() if scheme == 'isbn' else value}"
    provider = (result.providers or ["unknown"])[0].casefold()
    citation_key = " ".join(str(result.entry.citation_key or "").split()).casefold()
    if not citation_key:
        raise DiscoveryPoolError("candidate without a stable identifier or citation key")
    return f"{provider}:{citation_key}"


def build_candidate_pool(report: DiscoveryReport) -> dict[str, Any]:
    """Build an unlabelled deterministic pool from one completed discovery report."""
    if len(report.results) > MAX_CANDIDATES_PER_CASE:
        raise DiscoveryPoolError(f"candidate limit is {MAX_CANDIDATES_PER_CASE}")
    candidates = []
    seen: set[str] = set()
    for result in report.results:
        candidate_id = _candidate_id(result)
        if not _ID_RE.fullmatch(candidate_id):
            raise DiscoveryPoolError(f"invalid candidate identity: {candidate_id!r}")
        if candidate_id in seen:
            raise DiscoveryPoolError(f"duplicate candidate identity: {candidate_id}")
        seen.add(candidate_id)
        fields = {
            key: str(result.entry.fields[key]).strip()
            for key in _FIELDS
            if result.entry.fields.get(key) is not None and str(result.entry.fields[key]).strip()
        }
        candidates.append({
            "id": candidate_id,
            "entry_type": str(result.entry.entry_type or "misc").casefold(),
            "fields": fields,
            "providers": list(result.providers),
            "provider_ranks": dict(result.provider_ranks),
            "field_conflicts": {
                key: value for key, value in sorted(result.field_conflicts.items())
                if key in _FIELDS
            },
        })

    brief = report.brief
    case_config = {
        "query": brief.query,
        "sources": list(brief.sources),
        "per_source_limit": brief.per_source_limit,
        "topic_slug": brief.topic_slug,
    }
    statuses = [
        {
            "provider": item.provider,
            "status": item.status,
            "result_count": item.result_count,
            "error_class": (
                item.error.split(":", 1)[0]
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", item.error.split(":", 1)[0])
                else None
            ),
        }
        for item in report.sources
    ]
    content = {
        "schema_version": SCHEMA_VERSION,
        "request": case_config,
        "outcome": report.outcome,
        "source_statuses": statuses,
        "candidates": candidates,
    }
    pool_id = f"pool-{_sha256(_canonical_bytes(content))[:20]}"
    case_id = f"case-{_sha256(_canonical_bytes({'pool_id': pool_id, 'request': case_config}))[:20]}"
    run_id = f"run-{_sha256(_canonical_bytes({'pool_id': pool_id, 'retrieved_at': report.generated_at}))[:20]}"
    return {
        "schema_version": SCHEMA_VERSION,
        "pool_id": pool_id,
        "run_id": run_id,
        "retrieved_at": report.generated_at,
        "request": case_config,
        "outcome": report.outcome,
        "source_statuses": statuses,
        "candidate_inventory_sha256": _sha256(_canonical_bytes(candidates)),
        "cases": [{
            "case_id": case_id,
            "query": brief.query,
            "split": "unassigned",
            "candidates": candidates,
        }],
    }


def _read_pool(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if len(raw) > MAX_POOL_BYTES:
        raise DiscoveryPoolError(f"candidate pool exceeds {MAX_POOL_BYTES}-byte limit")
    try:
        pool = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryPoolError(f"invalid UTF-8 JSON in candidate pool: {exc}") from exc
    if not isinstance(pool, dict) or pool.get("schema_version") != SCHEMA_VERSION:
        raise DiscoveryPoolError("unsupported candidate pool schema")
    if not isinstance(pool.get("pool_id"), str) or not pool["pool_id"]:
        raise DiscoveryPoolError("candidate pool needs pool_id")
    cases = pool.get("cases")
    if not isinstance(cases, list) or not cases:
        raise DiscoveryPoolError("candidate pool needs cases")
    case_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not case["case_id"]:
            raise DiscoveryPoolError("each case needs case_id")
        if case["case_id"] in case_ids:
            raise DiscoveryPoolError("duplicate case_id")
        case_ids.add(case["case_id"])
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            raise DiscoveryPoolError(f"{case['case_id']}: query is required")
        candidates = case.get("candidates")
        if not isinstance(candidates, list):
            raise DiscoveryPoolError(f"{case['case_id']}: candidates must be a list")
        ids: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str) or not _ID_RE.fullmatch(candidate["id"]):
                raise DiscoveryPoolError(f"{case['case_id']}: invalid candidate ID")
            if candidate["id"] in ids:
                raise DiscoveryPoolError(f"{case['case_id']}: duplicate candidate ID {candidate['id']}")
            ids.add(candidate["id"])
            if len(ids) > MAX_CANDIDATES_PER_CASE:
                raise DiscoveryPoolError(f"{case['case_id']}: candidate limit is {MAX_CANDIDATES_PER_CASE}")
            providers = candidate.get("providers")
            ranks = candidate.get("provider_ranks")
            fields = candidate.get("fields", {})
            if not isinstance(providers, list) or not providers or not all(isinstance(provider, str) and provider for provider in providers):
                raise DiscoveryPoolError(f"{case['case_id']}/{candidate['id']}: provenance is required")
            if not isinstance(ranks, dict) or not all(
                isinstance(provider, str) and isinstance(rank, int) and not isinstance(rank, bool) and rank >= 1
                for provider, rank in ranks.items()
            ):
                raise DiscoveryPoolError(f"{case['case_id']}/{candidate['id']}: provider ranks are invalid")
            if not isinstance(fields, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in fields.items()):
                raise DiscoveryPoolError(f"{case['case_id']}/{candidate['id']}: fields must map strings to strings")
    return pool, raw


def build_judgment_template(pool_path: Path) -> dict[str, Any]:
    pool, raw = _read_pool(pool_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "pool_id": pool["pool_id"],
        "pool_sha256": _sha256(raw),
        "rubric_version": RUBRIC_VERSION,
        "judgments": [
            {"case_id": case["case_id"], "candidate_judgments": [
                {"candidate_id": candidate["id"], "label": "unjudged"}
                for candidate in case["candidates"]
            ]}
            for case in pool["cases"]
        ],
    }


def prepare_rank_pool(pool_path: Path, judgments_path: Path) -> dict[str, Any]:
    pool, raw = _read_pool(pool_path)
    try:
        judgment_bytes = judgments_path.read_bytes()
        judgments = json.loads(judgment_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryPoolError(f"cannot read judgment JSON: {exc}") from exc
    if not isinstance(judgments, dict) or judgments.get("schema_version") != SCHEMA_VERSION:
        raise DiscoveryPoolError("unsupported judgment schema")
    if set(judgments) != {"schema_version", "pool_id", "pool_sha256", "rubric_version", "judgments"}:
        raise DiscoveryPoolError("judgment artifact contains unsupported fields")
    if judgments.get("pool_id") != pool["pool_id"] or judgments.get("pool_sha256") != _sha256(raw):
        raise DiscoveryPoolError("judgments do not match the exact candidate-pool bytes")
    if judgments.get("rubric_version") != RUBRIC_VERSION:
        raise DiscoveryPoolError(f"rubric_version must be {RUBRIC_VERSION}")
    cases = judgments.get("judgments")
    if not isinstance(cases, list) or len(cases) != len(pool["cases"]):
        raise DiscoveryPoolError("judgments must contain exactly one record per case")
    judgment_by_case: dict[str, dict[str, Any]] = {}
    for item in cases:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            raise DiscoveryPoolError("each judgment record needs case_id")
        if set(item) != {"case_id", "candidate_judgments"}:
            raise DiscoveryPoolError(f"{item.get('case_id', 'judgment')}: unsupported judgment fields")
        if item["case_id"] in judgment_by_case:
            raise DiscoveryPoolError(f"duplicate judgment case_id {item['case_id']}")
        judgment_by_case[item["case_id"]] = item
    if set(judgment_by_case) != {case["case_id"] for case in pool["cases"]}:
        raise DiscoveryPoolError("judgment case IDs do not match candidate pool")

    dev_cases = []
    for case in pool["cases"]:
        item = judgment_by_case[case["case_id"]]
        raw_labels = item.get("candidate_judgments")
        if not isinstance(raw_labels, list):
            raise DiscoveryPoolError(f"{case['case_id']}: candidate_judgments must be a list")
        by_id: dict[str, str] = {}
        for judgment in raw_labels:
            if not isinstance(judgment, dict) or not isinstance(judgment.get("candidate_id"), str):
                raise DiscoveryPoolError(f"{case['case_id']}: each judgment needs candidate_id")
            if set(judgment) != {"candidate_id", "label"}:
                raise DiscoveryPoolError(f"{case['case_id']}: unsupported candidate judgment fields")
            candidate_id = judgment["candidate_id"]
            if candidate_id in by_id:
                raise DiscoveryPoolError(f"{case['case_id']}: duplicate label for {candidate_id}")
            label = judgment.get("label")
            if not isinstance(label, str) or label not in {"relevant", "not_relevant", "unjudged"}:
                raise DiscoveryPoolError(f"{case['case_id']}/{candidate_id}: unsupported label")
            by_id[candidate_id] = label
        candidate_ids = {candidate["id"] for candidate in case["candidates"]}
        if set(by_id) != candidate_ids:
            raise DiscoveryPoolError(f"{case['case_id']}: label IDs do not match candidate IDs")
        if "unjudged" in by_id.values():
            raise DiscoveryPoolError(f"{case['case_id']}: every candidate needs a relevance judgment")
        dev_cases.append({
            "case_id": case["case_id"],
            "query": case["query"],
            "relevant_ids": sorted(candidate_id for candidate_id, label in by_id.items() if label == "relevant"),
            "candidates": case["candidates"],
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "pool_id": pool["pool_id"],
        "source_pool_sha256": _sha256(raw),
        "judgment_sha256": _sha256(judgment_bytes),
        "rubric_version": RUBRIC_VERSION,
        "split": "development",
        "cases": dev_cases,
    }


def write_private_json(path: Path, value: Any) -> None:
    """Atomically publish a new owner-readable JSON artifact; never overwrite."""
    path = path.resolve()
    missing: list[Path] = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_name, path)
    except FileExistsError as exc:
        raise DiscoveryPoolError(f"output already exists: {path}") from exc
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
