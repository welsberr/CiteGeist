"""Bounded offline experiments for agent-proposed ranking configurations.

The candidate interface is JSON-only: it cannot execute proposal code, access a
database, call providers, modify labels, or promote a configuration. This first
stage accepts development pools only; validation and locked release holdouts are
deliberately not accepted by this command.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .eval_baseline import _score_case


SCHEMA_VERSION = 1
FEATURES = ("lexical", "seed_overlap", "provider_rank", "source_coverage")
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_CASES = 250
MAX_CANDIDATES_PER_CASE = 500
MAX_PROPOSALS = 16
TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
STOP_WORDS = {
    "about", "after", "also", "and", "are", "but", "can", "for", "from", "how",
    "into", "its", "may", "not", "our", "out", "over", "than", "that", "the",
    "their", "these", "this", "those", "through", "use", "using", "was", "were",
    "what", "when", "where", "which", "who", "with", "within", "without",
}


class RankingExperimentError(ValueError):
    """Raised for invalid, oversized, or unsafe experiment inputs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RankingExperimentError(message)


def _tokens(value: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(value.casefold()) if token not in STOP_WORDS}


def _validate_pool(pool: Any, label: str) -> dict[str, Any]:
    _require(isinstance(pool, dict), f"{label}: pool must be a JSON object")
    _require(pool.get("schema_version") == SCHEMA_VERSION, f"{label}: unsupported schema_version")
    _require(isinstance(pool.get("pool_id"), str) and pool["pool_id"], f"{label}: pool_id is required")
    cases = pool.get("cases")
    _require(isinstance(cases, list) and cases, f"{label}: cases must be a nonempty list")
    _require(len(cases) <= MAX_CASES, f"{label}: case limit is {MAX_CASES}")
    case_ids: set[str] = set()
    for case in cases:
        _require(isinstance(case, dict), f"{label}: each case must be an object")
        case_id = case.get("case_id")
        _require(isinstance(case_id, str) and case_id, f"{label}: case_id is required")
        _require(case_id not in case_ids, f"{label}: duplicate case_id {case_id!r}")
        case_ids.add(case_id)
        _require(isinstance(case.get("query"), str) and case["query"].strip(), f"{label}/{case_id}: query is required")
        relevant = case.get("relevant_ids")
        _require(isinstance(relevant, list) and all(isinstance(x, str) and x for x in relevant), f"{label}/{case_id}: relevant_ids must be strings")
        _require(len(set(relevant)) == len(relevant), f"{label}/{case_id}: relevant_ids must be unique")
        seed_texts = case.get("seed_texts", [])
        _require(isinstance(seed_texts, list) and all(isinstance(x, str) for x in seed_texts), f"{label}/{case_id}: seed_texts must be strings")
        candidates = case.get("candidates")
        _require(isinstance(candidates, list), f"{label}/{case_id}: candidates must be a list")
        _require(len(candidates) <= MAX_CANDIDATES_PER_CASE, f"{label}/{case_id}: candidate limit is {MAX_CANDIDATES_PER_CASE}")
        candidate_ids: set[str] = set()
        for candidate in candidates:
            _require(isinstance(candidate, dict) and isinstance(candidate.get("id"), str) and candidate["id"], f"{label}/{case_id}: each candidate needs an id")
            _require(candidate["id"] not in candidate_ids, f"{label}/{case_id}: duplicate candidate id {candidate['id']!r}")
            candidate_ids.add(candidate["id"])
            fields = candidate.get("fields", {})
            _require(isinstance(fields, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in fields.items()), f"{label}/{case_id}: candidate fields must map strings to strings")
            providers = candidate.get("providers", [])
            _require(isinstance(providers, list) and all(isinstance(p, str) and p for p in providers), f"{label}/{case_id}: providers must be strings")
            ranks = candidate.get("provider_ranks", {})
            _require(isinstance(ranks, dict), f"{label}/{case_id}: provider_ranks must be an object")
            _require(all(isinstance(p, str) and isinstance(rank, int) and not isinstance(rank, bool) and rank >= 1 for p, rank in ranks.items()), f"{label}/{case_id}: provider ranks must be positive integers")
    return pool


def _validate_proposals(proposals: Any) -> list[dict[str, Any]]:
    _require(isinstance(proposals, dict), "proposals must be a JSON object")
    _require(set(proposals).issubset({"schema_version", "proposals"}), "proposals contain unsupported fields")
    _require(proposals.get("schema_version") == SCHEMA_VERSION, "unsupported proposal schema_version")
    items = proposals.get("proposals")
    _require(isinstance(items, list) and 1 <= len(items) <= MAX_PROPOSALS, f"proposals must contain 1 to {MAX_PROPOSALS} configurations")
    ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for item in items:
        _require(isinstance(item, dict), "each proposal must be an object")
        _require(set(item).issubset({"id", "parent_id", "weights", "rationale"}), "proposal contains unsupported fields; executable or ranking-control fields are forbidden")
        proposal_id = item.get("id")
        _require(isinstance(proposal_id, str) and proposal_id and len(proposal_id) <= 80, "each proposal needs an id of at most 80 characters")
        _require(proposal_id not in ids, f"duplicate proposal id {proposal_id!r}")
        ids.add(proposal_id)
        weights = item.get("weights")
        _require(isinstance(weights, dict) and set(weights).issubset(FEATURES), f"{proposal_id}: weights may use only {', '.join(FEATURES)}")
        normalized_weights: dict[str, float] = {}
        for feature in FEATURES:
            value = weights.get(feature, 0.0)
            _require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1, f"{proposal_id}: {feature} weight must be finite and in [0, 1]")
            normalized_weights[feature] = float(value)
        _require(sum(normalized_weights.values()) > 0, f"{proposal_id}: at least one weight must be positive")
        rationale = item.get("rationale", "")
        _require(isinstance(rationale, str) and rationale.strip() and len(rationale) <= 1000, f"{proposal_id}: rationale/hypothesis is required and must be at most 1000 characters")
        parent_id = item.get("parent_id", None if proposal_id == "baseline" else "baseline")
        _require(parent_id is None or isinstance(parent_id, str), f"{proposal_id}: parent_id must be a proposal ID or null")
        _require(parent_id != proposal_id, f"{proposal_id}: a proposal cannot be its own parent")
        normalized.append({"id": proposal_id, "parent_id": parent_id, "weights": normalized_weights, "rationale": rationale})
    _require("baseline" in ids, "proposals must include a configuration with id 'baseline'")
    _require(all(item["parent_id"] is None or item["parent_id"] in ids for item in normalized), "each parent_id must reference a proposal in this file")
    parents = {item["id"]: item["parent_id"] for item in normalized}
    _require(parents["baseline"] is None, "baseline parent_id must be null")
    for proposal_id in ids:
        visited: set[str] = set()
        cursor: str | None = proposal_id
        while cursor is not None:
            _require(cursor not in visited, f"proposal lineage contains a cycle at {cursor!r}")
            visited.add(cursor)
            cursor = parents[cursor]
    return normalized


def _candidate_features(case: dict[str, Any], candidate: dict[str, Any], max_rank: int) -> dict[str, float]:
    fields = candidate.get("fields", {})
    content = " ".join(fields.get(key, "") for key in ("title", "abstract", "keywords"))
    query_terms = _tokens(case["query"])
    content_terms = _tokens(content)
    lexical = len(query_terms & content_terms) / len(query_terms) if query_terms else 0.0
    seed_terms = _tokens(" ".join(case.get("seed_texts", [])))
    seed_overlap = len(seed_terms & content_terms) / len(seed_terms) if seed_terms else 0.0
    ranks = candidate.get("provider_ranks", {})
    provider_rank = sum(1.0 / rank for rank in ranks.values()) / len(ranks) if ranks else 0.0
    providers = set(candidate.get("providers", [])) | set(ranks)
    source_coverage = len(providers) / max_rank if max_rank else 0.0
    return {
        "lexical": lexical,
        "seed_overlap": seed_overlap,
        "provider_rank": provider_rank,
        "source_coverage": source_coverage,
    }


def _rank_case(case: dict[str, Any], weights: dict[str, float]) -> list[dict[str, Any]]:
    candidates = case["candidates"]
    max_rank = max((len(set(c.get("providers", [])) | set(c.get("provider_ranks", {}))) for c in candidates), default=0)
    denominator = sum(weights.values())
    ranked = []
    for original_index, candidate in enumerate(candidates):
        features = _candidate_features(case, candidate, max_rank)
        score = sum(weights[key] * features[key] for key in FEATURES) / denominator
        ranked.append((score, original_index, candidate))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]["id"]))
    return [item[2] for item in ranked]


def _evaluate_config(cases: list[dict[str, Any]], weights: dict[str, float], k: int) -> dict[str, Any]:
    per_case = []
    for case in cases:
        ranked = _rank_case(case, weights)
        metrics = _score_case(case["relevant_ids"], ranked, k)
        per_case.append({
            "case_id": case["case_id"],
            "metrics": metrics,
            "ranked_ids": metrics["candidate_ids"],
        })
    precision_values = [item["metrics"]["precision_at_k"] for item in per_case]
    return {
        "case_count": len(per_case),
        "mean_precision_at_k": round(sum(precision_values) / len(precision_values), 6) if precision_values else 0.0,
        "cases": per_case,
    }


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _repo_state(repo: Path) -> dict[str, str | None]:
    def git(*args: str) -> bytes | None:
        try:
            result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, timeout=5)
            return result.stdout
        except (OSError, subprocess.SubprocessError):
            return None

    revision = git("rev-parse", "HEAD")
    diff = git("diff", "--binary", "HEAD", "--")
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    return {
        "revision": revision.decode("ascii", errors="replace").strip() if revision else None,
        "tracked_worktree_diff_sha256": _sha256(diff) if diff is not None else None,
        "worktree_status_sha256": _sha256(status) if status is not None else None,
    }


def run_ranking_experiment(
    development: Any,
    proposals: Any,
    *,
    development_bytes: bytes,
    proposal_bytes: bytes,
    repo: Path,
    k: int = 10,
) -> dict[str, Any]:
    """Compare allowlisted configs on a fixed development candidate pool."""
    _require(isinstance(k, int) and not isinstance(k, bool) and 1 <= k <= 20, "k must be an integer from 1 to 20")
    development = _validate_pool(development, "development")
    configs = _validate_proposals(proposals)
    baseline = next(item for item in configs if item["id"] == "baseline")

    development_results = [
        {"proposal_id": item["id"], "parent_id": item["parent_id"], "rationale": item["rationale"], "weights": item["weights"],
         "evaluation": _evaluate_config(development["cases"], item["weights"], k)}
        for item in configs
    ]
    baseline_dev = next(item for item in development_results if item["proposal_id"] == "baseline")
    # Stable tie break: baseline wins ties; otherwise proposal ID order is fixed.
    development_results.sort(key=lambda item: (
        -item["evaluation"]["mean_precision_at_k"],
        item["proposal_id"] != "baseline",
        item["proposal_id"],
    ))
    finalist = development_results[0]
    dev_gain = finalist["evaluation"]["mean_precision_at_k"] - baseline_dev["evaluation"]["mean_precision_at_k"]
    recommendation = "research_candidate" if finalist["proposal_id"] != "baseline" and dev_gain > 0 else "retain_baseline"
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_type": "offline-ranking-configuration",
        "experiment_id": str(development.get("experiment_id") or development["pool_id"]),
        "cutoff_k": k,
        "inputs": {
            "development_pool_id": development["pool_id"],
            "development_sha256": _sha256(development_bytes),
            "proposals_sha256": _sha256(proposal_bytes),
        },
        "repository": _repo_state(repo),
        "budget": {"max_proposals": MAX_PROPOSALS, "proposals_evaluated": len(configs), "network_calls": 0, "database_writes": 0},
        "selection": {
            "baseline_proposal_id": "baseline",
            "development_finalist_id": finalist["proposal_id"],
            "development_precision_gain": round(dev_gain, 6),
            "recommendation": recommendation,
            "automatic_promotion": False,
            "locked_holdout_used": False,
            "next_step": "independent_validation_required" if recommendation == "research_candidate" else "none",
        },
        "development_results": development_results,
        "limitations": [
            "This experiment ranks only the supplied recorded candidate pools; it does not run discovery.",
            "Lexical and provider signals are heuristics, and these scores are not probabilities.",
            "Development results select hypotheses only and are not independent evidence of generalization.",
            "A reviewer must evaluate a finalist on a separately controlled validation pool before any pilot.",
            "This tool does not sandbox filesystem access; use only non-sensitive development data and a private output path.",
            "A human must review the receipt and explicitly adopt or reject any configuration.",
        ],
    }


def _read_json(path: Path) -> tuple[Any, bytes]:
    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise RankingExperimentError(f"input exceeds the {MAX_INPUT_BYTES}-byte limit: {path}")
    try:
        return json.loads(raw), raw
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RankingExperimentError(f"invalid UTF-8 JSON in {path}: {exc}") from exc


def run_paths(development_path: Path, proposals_path: Path, output_path: Path, *, k: int) -> dict[str, Any]:
    """Read bounded inputs and write a new receipt without overwriting evidence."""
    input_paths = {path.resolve() for path in (development_path, proposals_path)}
    _require(len(input_paths) == 2, "development pool and proposals must be separate files")
    _require(output_path.resolve() not in input_paths, "receipt output must not overwrite an input")
    _require(not output_path.exists(), f"receipt output already exists: {output_path}")
    development, development_bytes = _read_json(development_path)
    proposals, proposal_bytes = _read_json(proposals_path)
    receipt = run_ranking_experiment(
        development, proposals,
        development_bytes=development_bytes,
        proposal_bytes=proposal_bytes,
        repo=Path(__file__).resolve().parents[2],
        k=k,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and fails if another process created
        # the destination after the initial existence check.
        os.link(temporary_name, output_path)
    except FileExistsError as exc:
        raise RankingExperimentError(f"receipt output already exists: {output_path}") from exc
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return receipt
