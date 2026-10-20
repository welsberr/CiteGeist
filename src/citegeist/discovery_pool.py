"""Private, immutable discovery pools and strict development-label joins."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from .research_discovery import DiscoveryReport
from .resolver.identifiers import entry_identifiers, extract_doi


SCHEMA_VERSION = 1
RUBRIC_VERSION = "research-relevance-v3"
SPLITS = ("development", "validation", "holdout")
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


def candidate_inventory_fingerprint(cases: list[dict[str, Any]]) -> str:
    """Hash fixed case/candidate content while excluding human judgments."""
    inventory = [
        {
            "case_id": case["case_id"],
            "query": case["query"],
            "split": case.get("split", "unassigned"),
            "topic_family": case.get("topic_family"),
            "candidates": case["candidates"],
        }
        for case in cases
    ]
    return _sha256(_canonical_bytes(inventory))


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


def build_candidate_pool(
    report: DiscoveryReport,
    *,
    local_corpus_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        "local_corpus_snapshot": local_corpus_snapshot if "local" in brief.sources else None,
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
        "local_corpus_snapshot": local_corpus_snapshot if "local" in brief.sources else None,
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
    if len(cases) > 250:
        raise DiscoveryPoolError("candidate pool exceeds 250-case limit")
    case_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not case["case_id"]:
            raise DiscoveryPoolError("each case needs case_id")
        if case["case_id"] in case_ids:
            raise DiscoveryPoolError("duplicate case_id")
        case_ids.add(case["case_id"])
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            raise DiscoveryPoolError(f"{case['case_id']}: query is required")
        split = case.get("split", "unassigned")
        if not isinstance(split, str) or split not in {*SPLITS, "unassigned"}:
            raise DiscoveryPoolError(f"{case['case_id']}: unsupported split")
        if split != "unassigned" and (not isinstance(case.get("topic_family"), str) or not case["topic_family"].strip()):
            raise DiscoveryPoolError(f"{case['case_id']}: assigned split requires topic_family")
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


def assemble_candidate_pools(pool_paths: list[Path], split_manifest_path: Path) -> dict[str, Any]:
    """Combine recorded searches after a topic-family split is assigned."""
    if not pool_paths:
        raise DiscoveryPoolError("at least one candidate pool is required")
    source_pools: list[dict[str, Any]] = []
    source_hashes: list[str] = []
    cases: list[dict[str, Any]] = []
    seen_cases: set[str] = set()
    for path in pool_paths:
        pool, raw = _read_pool(path)
        source_pools.append(pool)
        source_hashes.append(_sha256(raw))
        for case in pool["cases"]:
            if case["case_id"] in seen_cases:
                raise DiscoveryPoolError(f"duplicate case_id across source pools: {case['case_id']}")
            seen_cases.add(case["case_id"])
            cases.append(deepcopy(case))
    if len(cases) > 250:
        raise DiscoveryPoolError("assembled pool exceeds 250-case limit")
    try:
        manifest_bytes = split_manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryPoolError(f"cannot read split manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise DiscoveryPoolError("unsupported split-manifest schema")
    if set(manifest) != {"schema_version", "rubric_version", "assignments"}:
        raise DiscoveryPoolError("split manifest contains unsupported fields")
    if manifest.get("rubric_version") != RUBRIC_VERSION:
        raise DiscoveryPoolError(f"rubric_version must be {RUBRIC_VERSION}")
    assignments = manifest.get("assignments")
    if not isinstance(assignments, list):
        raise DiscoveryPoolError("split manifest assignments must be a list")
    by_case: dict[str, dict[str, str]] = {}
    family_splits: dict[str, str] = {}
    for assignment in assignments:
        if not isinstance(assignment, dict) or set(assignment) != {"case_id", "split", "topic_family"}:
            raise DiscoveryPoolError("each split assignment needs case_id, split, and topic_family")
        case_id = assignment["case_id"]
        split = assignment["split"]
        family = assignment["topic_family"]
        if not isinstance(case_id, str) or not case_id:
            raise DiscoveryPoolError("split assignment case_id is required")
        if case_id in by_case:
            raise DiscoveryPoolError(f"duplicate split assignment for {case_id}")
        if not isinstance(split, str) or split not in SPLITS or not isinstance(family, str) or not family.strip():
            raise DiscoveryPoolError(f"{case_id}: split and topic_family are invalid")
        family = " ".join(family.split()).casefold()
        prior_split = family_splits.setdefault(family, split)
        if prior_split != split:
            raise DiscoveryPoolError(f"topic family {family!r} crosses data splits")
        by_case[case_id] = {"split": split, "topic_family": family}
    if set(by_case) != seen_cases:
        raise DiscoveryPoolError("split manifest must assign every case exactly once")
    for case in cases:
        case.update(by_case[case["case_id"]])
    provenance = {"source_pool_sha256s": source_hashes, "split_manifest_sha256": _sha256(manifest_bytes)}
    pool_id = f"taskset-{_sha256(_canonical_bytes(provenance))[:20]}"
    return {
        "schema_version": SCHEMA_VERSION,
        "pool_id": pool_id,
        "assembled_from": [pool["pool_id"] for pool in source_pools],
        **provenance,
        "candidate_inventory_sha256": candidate_inventory_fingerprint(cases),
        "split_candidate_inventory_sha256": {
            split: candidate_inventory_fingerprint([case for case in cases if case["split"] == split])
            for split in SPLITS
        },
        "cases": cases,
    }


_JUDGMENT_DIMENSIONS = {
    "relevance": {"not_relevant", "background", "useful", "essential", "unjudged"},
    "identity_correct": {"yes", "no", "uncertain", "unassessed"},
    "version_match": {"yes", "no", "not_applicable", "uncertain", "unassessed"},
    "source_authority": {"strong", "adequate", "weak", "uncertain", "unassessed"},
    "evidence_support": {"direct", "indirect", "none", "uncertain", "unassessed"},
}
_CASE_JUDGMENT_DIMENSIONS = {"answerability": {"answerable", "unanswerable", "uncertain", "unassessed"}}
_ALL_JUDGMENT_DIMENSIONS = {**_JUDGMENT_DIMENSIONS, **_CASE_JUDGMENT_DIMENSIONS}
_CASE_JUDGMENT_ID = "@case"


def build_judgment_template(pool_path: Path, *, split: str, reviewer_id: str) -> dict[str, Any]:
    pool, raw = _read_pool(pool_path)
    if split not in SPLITS:
        raise DiscoveryPoolError(f"split must be one of {', '.join(SPLITS)}")
    reviewer_id = " ".join(reviewer_id.split()) if isinstance(reviewer_id, str) else ""
    if not reviewer_id or len(reviewer_id) > 120:
        raise DiscoveryPoolError("reviewer_id must be a non-empty private reviewer code of at most 120 characters")
    cases = [case for case in pool["cases"] if case.get("split") == split]
    if not cases:
        raise DiscoveryPoolError(f"candidate pool has no cases assigned to {split}")
    return {
        "schema_version": SCHEMA_VERSION,
        "pool_id": pool["pool_id"],
        "pool_sha256": _sha256(raw),
        "rubric_version": RUBRIC_VERSION,
        "split": split,
        "reviewer_id": reviewer_id,
        "judgments": [
            {"case_id": case["case_id"], "answerability": "unassessed", "candidate_judgments": [
                {"candidate_id": candidate["id"], **{
                    dimension: ("unjudged" if dimension == "relevance" else "unassessed")
                    for dimension in _JUDGMENT_DIMENSIONS
                }}
                for candidate in case["candidates"]
            ]}
            for case in cases
        ],
    }


def compare_reviews(pool_path: Path, first_path: Path, second_path: Path) -> dict[str, Any]:
    """Compare two independent, complete review files without resolving disagreements."""
    first, first_raw = _read_review(first_path)
    second, second_raw = _read_review(second_path)
    pool, pool_raw = _read_pool(pool_path)
    for key in ("pool_id", "pool_sha256", "rubric_version", "split"):
        if first[key] != second[key]:
            raise DiscoveryPoolError(f"independent reviews disagree on {key}")
    if first["reviewer_id"] == second["reviewer_id"]:
        raise DiscoveryPoolError("double review requires two distinct reviewer_id values")
    if first["pool_id"] != pool["pool_id"] or first["pool_sha256"] != _sha256(pool_raw):
        raise DiscoveryPoolError("reviews do not match the exact candidate-pool bytes")
    expected_cases = [case for case in pool["cases"] if case.get("split") == first["split"]]
    expected_labels = {
        (case["case_id"], candidate["id"], dimension)
        for case in expected_cases
        for candidate in case["candidates"]
        for dimension in _JUDGMENT_DIMENSIONS
    }
    expected_labels.update((case["case_id"], _CASE_JUDGMENT_ID, "answerability") for case in expected_cases)
    left = _flatten_review(first)
    right = _flatten_review(second)
    if left.keys() != expected_labels or right.keys() != expected_labels:
        raise DiscoveryPoolError("each independent review must cover every candidate and dimension in the fixed pool split")
    if any(value == "unjudged" for (case_id, candidate_id, dimension), value in left.items() if dimension == "relevance"):
        raise DiscoveryPoolError("each reviewer must complete relevance labels before comparison")
    if any(value == "unassessed" for (case_id, candidate_id, dimension), value in left.items() if dimension == "answerability"):
        raise DiscoveryPoolError("each reviewer must assess answerability for every case before comparison")
    agreements = []
    disagreements = []
    for key in sorted(left):
        case_id, candidate_id, dimension = key
        record = {
            "case_id": case_id,
            "candidate_id": candidate_id,
            "dimension": dimension,
            "first": left[key],
            "second": right[key],
        }
        (agreements if left[key] == right[key] else disagreements).append(record)
    return {
        "schema_version": SCHEMA_VERSION,
        "pool_id": first["pool_id"],
        "pool_sha256": first["pool_sha256"],
        "rubric_version": first["rubric_version"],
        "split": first["split"],
        "reviewers": [first["reviewer_id"], second["reviewer_id"]],
        "review_sha256s": [_sha256(first_raw), _sha256(second_raw)],
        "agreement_count": len(agreements),
        "disagreement_count": len(disagreements),
        "agreements": agreements,
        "disagreements": disagreements,
        "decisions": [
            {"case_id": item["case_id"], "candidate_id": item["candidate_id"], "dimension": item["dimension"], "decision": "unresolved"}
            for item in disagreements
        ],
    }


def adjudicate_reviews(pool_path: Path, first_path: Path, second_path: Path, adjudication_path: Path, *, adjudicator_id: str) -> dict[str, Any]:
    """Apply explicit adjudicator choices to every disagreement, preserving both source reviews."""
    comparison = compare_reviews(pool_path, first_path, second_path)
    adjudication = _read_json_artifact(adjudication_path, "adjudication")
    reviewer_ids = comparison["reviewers"]
    reviewer_id = " ".join(adjudicator_id.split()) if isinstance(adjudicator_id, str) else ""
    if not reviewer_id or len(reviewer_id) > 120 or reviewer_id in reviewer_ids:
        raise DiscoveryPoolError("adjudicator_id must be a distinct, non-empty private reviewer code")
    expected = {"schema_version", "pool_id", "pool_sha256", "rubric_version", "split", "reviewers", "review_sha256s", "agreement_count", "disagreement_count", "agreements", "disagreements", "decisions"}
    if set(adjudication) != expected or any(adjudication.get(key) != comparison[key] for key in expected - {"decisions"}):
        raise DiscoveryPoolError("adjudication artifact does not match the current independent reviews")
    decisions = adjudication.get("decisions")
    disputed = {(item["case_id"], item["candidate_id"], item["dimension"]): item for item in comparison["disagreements"]}
    if not isinstance(decisions, list) or len(decisions) != len(disputed):
        raise DiscoveryPoolError("adjudication must explicitly resolve every disagreement exactly once")
    resolved: dict[tuple[str, str, str], str] = {}
    for item in decisions:
        if not isinstance(item, dict) or set(item) != {"case_id", "candidate_id", "dimension", "decision"}:
            raise DiscoveryPoolError("each adjudication decision needs case_id, candidate_id, dimension, and decision")
        if not all(isinstance(item[field], str) for field in ("case_id", "candidate_id", "dimension", "decision")):
            raise DiscoveryPoolError("adjudication decision fields must be strings")
        key = (item["case_id"], item["candidate_id"], item["dimension"])
        original = disputed.get(key)
        if original is None or key in resolved:
            raise DiscoveryPoolError("adjudication contains an extra or duplicate decision")
        if item["decision"] == "unresolved":
            raise DiscoveryPoolError("adjudication must explicitly resolve every disagreement")
        if item["decision"] not in _ALL_JUDGMENT_DIMENSIONS[item["dimension"]] - {"unjudged", "unassessed"}:
            raise DiscoveryPoolError(f"adjudication decision is not a completed {item['dimension']} value")
        resolved[key] = item["decision"]
    first, _ = _read_review(first_path)
    labels = _flatten_review(first)
    for key, decision in resolved.items():
        labels[key] = decision
    judgments = deepcopy(first)
    for case in judgments["judgments"]:
        case["answerability"] = labels[(case["case_id"], _CASE_JUDGMENT_ID, "answerability")]
        for candidate in case["candidate_judgments"]:
            for dimension in _JUDGMENT_DIMENSIONS:
                candidate[dimension] = labels[(case["case_id"], candidate["candidate_id"], dimension)]
    judgments.pop("reviewer_id", None)
    judgments["review_provenance"] = {
        "reviewers": reviewer_ids,
        "adjudicator_id": reviewer_id,
        "review_sha256s": comparison["review_sha256s"],
        "adjudication_sha256": _sha256(adjudication_path.read_bytes()),
        "disagreements": comparison["disagreements"],
        "decisions": decisions,
    }
    return judgments


def _read_json_artifact(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryPoolError(f"cannot read {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise DiscoveryPoolError(f"{label} artifact must be a JSON object")
    return value


def _read_review(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryPoolError(f"invalid review JSON: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise DiscoveryPoolError("unsupported review schema")
    required = {"schema_version", "pool_id", "pool_sha256", "rubric_version", "split", "reviewer_id", "judgments"}
    if set(value) != required or not isinstance(value.get("reviewer_id"), str) or not value["reviewer_id"].strip():
        raise DiscoveryPoolError("review artifact needs the supported schema and reviewer_id")
    _flatten_review(value)
    return value, raw


def _flatten_review(review: dict[str, Any]) -> dict[tuple[str, str, str], str]:
    flattened = {}
    cases = review.get("judgments")
    if not isinstance(cases, list):
        raise DiscoveryPoolError("review judgments must be a list")
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"case_id", "answerability", "candidate_judgments"} or not isinstance(case.get("case_id"), str):
            raise DiscoveryPoolError("review case records must contain case_id, answerability, and candidate_judgments")
        answerability = case.get("answerability")
        if not isinstance(answerability, str) or answerability not in _CASE_JUDGMENT_DIMENSIONS["answerability"]:
            raise DiscoveryPoolError(f"{case['case_id']}: invalid answerability")
        flattened[(case["case_id"], _CASE_JUDGMENT_ID, "answerability")] = answerability
        if not isinstance(case["candidate_judgments"], list):
            raise DiscoveryPoolError(f"{case['case_id']}: candidate_judgments must be a list")
        for candidate in case["candidate_judgments"]:
            expected = {"candidate_id", *_JUDGMENT_DIMENSIONS}
            if not isinstance(candidate, dict) or set(candidate) != expected or not isinstance(candidate.get("candidate_id"), str):
                raise DiscoveryPoolError(f"{case['case_id']}: malformed candidate judgment")
            for dimension, values in _JUDGMENT_DIMENSIONS.items():
                label = candidate[dimension]
                if not isinstance(label, str) or label not in values:
                    raise DiscoveryPoolError(f"{case['case_id']}/{candidate['candidate_id']}: invalid {dimension}")
                flattened[(case["case_id"], candidate["candidate_id"], dimension)] = label
    expected_count = sum(len(case["candidate_judgments"]) * len(_JUDGMENT_DIMENSIONS) + 1 for case in cases)
    if len(flattened) != expected_count:
        raise DiscoveryPoolError("review contains duplicate case/candidate/dimension labels")
    return flattened


def prepare_rank_pool(pool_path: Path, judgments_path: Path, *, split: str) -> dict[str, Any]:
    pool, raw = _read_pool(pool_path)
    if split not in SPLITS:
        raise DiscoveryPoolError(f"split must be one of {', '.join(SPLITS)}")
    try:
        judgment_bytes = judgments_path.read_bytes()
        judgments = json.loads(judgment_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryPoolError(f"cannot read judgment JSON: {exc}") from exc
    if not isinstance(judgments, dict) or judgments.get("schema_version") != SCHEMA_VERSION:
        raise DiscoveryPoolError("unsupported judgment schema")
    allowed_keys = {"schema_version", "pool_id", "pool_sha256", "rubric_version", "split", "judgments", "reviewer_id", "review_provenance"}
    if not {"schema_version", "pool_id", "pool_sha256", "rubric_version", "split", "judgments"}.issubset(judgments) or set(judgments) - allowed_keys:
        raise DiscoveryPoolError("judgment artifact contains unsupported fields")
    if judgments.get("pool_id") != pool["pool_id"] or judgments.get("pool_sha256") != _sha256(raw):
        raise DiscoveryPoolError("judgments do not match the exact candidate-pool bytes")
    if judgments.get("rubric_version") != RUBRIC_VERSION:
        raise DiscoveryPoolError(f"rubric_version must be {RUBRIC_VERSION}")
    if judgments.get("split") != split:
        raise DiscoveryPoolError("requested split does not match judgment artifact")
    if "reviewer_id" in judgments and (not isinstance(judgments["reviewer_id"], str) or not judgments["reviewer_id"].strip()):
        raise DiscoveryPoolError("reviewer_id must be a non-empty private reviewer code")
    provenance = judgments.get("review_provenance")
    if provenance is not None:
        required_provenance = {"reviewers", "adjudicator_id", "review_sha256s", "adjudication_sha256", "disagreements", "decisions"}
        if not isinstance(provenance, dict) or set(provenance) != required_provenance:
            raise DiscoveryPoolError("review_provenance has an unsupported schema")
        reviewers = provenance["reviewers"]
        hashes = provenance["review_sha256s"]
        if (
            not isinstance(reviewers, list) or len(reviewers) != 2
            or not all(isinstance(item, str) and item.strip() for item in reviewers)
            or len(set(reviewers)) != 2
            or not isinstance(provenance["adjudicator_id"], str)
            or not provenance["adjudicator_id"].strip()
            or provenance["adjudicator_id"] in reviewers
            or not isinstance(hashes, list) or len(hashes) != 2
            or not all(isinstance(item, str) and re.fullmatch(r"[a-f0-9]{64}", item) for item in hashes)
            or not isinstance(provenance["adjudication_sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", provenance["adjudication_sha256"])
            or not isinstance(provenance["disagreements"], list)
            or not isinstance(provenance["decisions"], list)
            or len(provenance["disagreements"]) != len(provenance["decisions"])
        ):
            raise DiscoveryPoolError("review_provenance values are invalid")
        expected_decisions = {}
        for disagreement in provenance["disagreements"]:
            if not isinstance(disagreement, dict) or set(disagreement) != {"case_id", "candidate_id", "dimension", "first", "second"}:
                raise DiscoveryPoolError("review_provenance contains a malformed disagreement")
            dimension = disagreement["dimension"]
            if (
                not isinstance(dimension, str) or dimension not in _ALL_JUDGMENT_DIMENSIONS
                or not isinstance(disagreement["first"], str)
                or not isinstance(disagreement["second"], str)
                or disagreement["first"] not in _ALL_JUDGMENT_DIMENSIONS[dimension]
                or disagreement["second"] not in _ALL_JUDGMENT_DIMENSIONS[dimension]
                or disagreement["first"] == disagreement["second"]
            ):
                raise DiscoveryPoolError("review_provenance disagreement labels are invalid")
            expected_decisions[(disagreement["case_id"], disagreement["candidate_id"], dimension)] = None
        for decision in provenance["decisions"]:
            if not isinstance(decision, dict) or set(decision) != {"case_id", "candidate_id", "dimension", "decision"}:
                raise DiscoveryPoolError("review_provenance contains a malformed decision")
            key = (decision["case_id"], decision["candidate_id"], decision["dimension"])
            dimension = decision["dimension"]
            if (
                key not in expected_decisions or expected_decisions[key] is not None
                or not isinstance(dimension, str) or not isinstance(decision["decision"], str)
                or decision["decision"] not in _ALL_JUDGMENT_DIMENSIONS.get(dimension, set()) - {"unjudged", "unassessed"}
            ):
                raise DiscoveryPoolError("review_provenance decisions do not resolve its disagreements")
            expected_decisions[key] = decision["decision"]
        if any(value is None for value in expected_decisions.values()):
            raise DiscoveryPoolError("review_provenance has an unresolved disagreement")
    pool_cases = [case for case in pool["cases"] if case.get("split") == split]
    if not pool_cases:
        raise DiscoveryPoolError(f"candidate pool has no cases assigned to {split}")
    if provenance is not None:
        valid_review_keys = {
            (case["case_id"], candidate["id"], dimension)
            for case in pool_cases for candidate in case["candidates"] for dimension in _JUDGMENT_DIMENSIONS
        }
        valid_review_keys.update((case["case_id"], _CASE_JUDGMENT_ID, "answerability") for case in pool_cases)
        if any((item["case_id"], item["candidate_id"], item["dimension"]) not in valid_review_keys for item in provenance["disagreements"]):
            raise DiscoveryPoolError("review_provenance refers to an item outside the fixed pool split")
    cases = judgments.get("judgments")
    if not isinstance(cases, list) or len(cases) != len(pool_cases):
        raise DiscoveryPoolError("judgments must contain exactly one record per case")
    judgment_by_case: dict[str, dict[str, Any]] = {}
    for item in cases:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            raise DiscoveryPoolError("each judgment record needs case_id")
        if set(item) != {"case_id", "answerability", "candidate_judgments"}:
            raise DiscoveryPoolError(f"{item.get('case_id', 'judgment')}: unsupported judgment fields")
        if item["case_id"] in judgment_by_case:
            raise DiscoveryPoolError(f"duplicate judgment case_id {item['case_id']}")
        if not isinstance(item["answerability"], str) or item["answerability"] not in _CASE_JUDGMENT_DIMENSIONS["answerability"]:
            raise DiscoveryPoolError(f"{item['case_id']}: invalid answerability")
        judgment_by_case[item["case_id"]] = item
    if set(judgment_by_case) != {case["case_id"] for case in pool_cases}:
        raise DiscoveryPoolError("judgment case IDs do not match the requested pool split")

    dev_cases = []
    adjudicated_values = {
        (decision["case_id"], decision["candidate_id"], decision["dimension"]): decision["decision"]
        for decision in (provenance["decisions"] if provenance is not None else [])
    }
    for case in pool_cases:
        item = judgment_by_case[case["case_id"]]
        raw_labels = item.get("candidate_judgments")
        if not isinstance(raw_labels, list):
            raise DiscoveryPoolError(f"{case['case_id']}: candidate_judgments must be a list")
        by_id: dict[str, str] = {}
        for judgment in raw_labels:
            if not isinstance(judgment, dict) or not isinstance(judgment.get("candidate_id"), str):
                raise DiscoveryPoolError(f"{case['case_id']}: each judgment needs candidate_id")
            expected_keys = {"candidate_id", *_JUDGMENT_DIMENSIONS}
            if set(judgment) != expected_keys:
                raise DiscoveryPoolError(f"{case['case_id']}: unsupported candidate judgment fields")
            candidate_id = judgment["candidate_id"]
            if candidate_id in by_id:
                raise DiscoveryPoolError(f"{case['case_id']}: duplicate label for {candidate_id}")
            dimensions = {dimension: judgment[dimension] for dimension in _JUDGMENT_DIMENSIONS}
            for dimension, values in _JUDGMENT_DIMENSIONS.items():
                if not isinstance(dimensions[dimension], str) or dimensions[dimension] not in values:
                    raise DiscoveryPoolError(f"{case['case_id']}/{candidate_id}: invalid {dimension}")
                adjudicated = adjudicated_values.get((case["case_id"], candidate_id, dimension))
                if adjudicated is not None and dimensions[dimension] != adjudicated:
                    raise DiscoveryPoolError(f"{case['case_id']}/{candidate_id}: judgment does not match adjudication")
            by_id[candidate_id] = dimensions
        candidate_ids = {candidate["id"] for candidate in case["candidates"]}
        if set(by_id) != candidate_ids:
            raise DiscoveryPoolError(f"{case['case_id']}: label IDs do not match candidate IDs")
        if any(value["relevance"] == "unjudged" for value in by_id.values()):
            raise DiscoveryPoolError(f"{case['case_id']}: every candidate needs a relevance judgment")
        answerability = item.get("answerability")
        if not isinstance(answerability, str) or answerability not in _CASE_JUDGMENT_DIMENSIONS["answerability"] - {"unassessed"}:
            raise DiscoveryPoolError(f"{case['case_id']}: answerability must be assessed before preparing a ranking pool")
        adjudicated_answerability = adjudicated_values.get((case["case_id"], _CASE_JUDGMENT_ID, "answerability"))
        if adjudicated_answerability is not None and answerability != adjudicated_answerability:
            raise DiscoveryPoolError(f"{case['case_id']}: answerability does not match adjudication")
        dev_cases.append({
            "case_id": case["case_id"],
            "query": case["query"],
            "split": split,
            "topic_family": case.get("topic_family"),
            "answerability": answerability,
            "relevant_ids": sorted(candidate_id for candidate_id, dimensions in by_id.items() if dimensions["relevance"] in {"useful", "essential"}),
            "candidates": case["candidates"],
            "quality_judgments": {candidate_id: value for candidate_id, value in sorted(by_id.items())},
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "pool_id": pool["pool_id"],
        "source_pool_sha256": _sha256(raw),
        "candidate_inventory_sha256": candidate_inventory_fingerprint(pool_cases),
        "judgment_sha256": _sha256(judgment_bytes),
        "review_provenance": judgments.get("review_provenance"),
        "rubric_version": RUBRIC_VERSION,
        "split": split,
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
