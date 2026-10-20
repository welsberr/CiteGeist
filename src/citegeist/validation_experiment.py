"""Maintainer-operated, aggregate-only one-shot ranking validation."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from .discovery_pool import (
    DiscoveryPoolError,
    _read_pool,
    candidate_inventory_fingerprint,
    write_private_json,
)
from .ranking_experiment import (
    RankingExperimentError,
    _rank_case,
    _score_case,
    _validate_pool,
)


class ValidationExperimentError(ValueError):
    """Raised for invalid validation registrations or protected inputs."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> tuple[Any, bytes]:
    raw = path.read_bytes()
    try:
        return json.loads(raw), raw
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationExperimentError(f"invalid UTF-8 JSON in {path}: {exc}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationExperimentError(message)


def _graded_ndcg(relevance_values: list[str], k: int) -> float | None:
    grade = {"not_relevant": 0, "background": 1, "useful": 2, "essential": 3}
    gains = [2 ** grade[value] - 1 for value in relevance_values]
    actual = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains[:k], start=1))
    ideal = sorted(gains, reverse=True)[:k]
    ideal_score = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal, start=1))
    return round(actual / ideal_score, 6) if ideal_score else None


def register_validation(
    development_receipt_path: Path,
    *,
    validation_pool_path: Path,
    minimum_precision_gain: float,
) -> dict[str, Any]:
    """Freeze the baseline, finalist, and acceptance threshold before validation."""
    receipt, raw = _load_json(development_receipt_path)
    _require(isinstance(receipt, dict), "development receipt must be an object")
    _require(receipt.get("schema_version") == 1, "unsupported development receipt schema")
    _require(receipt.get("experiment_type") == "offline-ranking-configuration", "receipt is not a development ranking experiment")
    try:
        validation_source_pool, validation_source_bytes = _read_pool(validation_pool_path)
    except DiscoveryPoolError as exc:
        raise ValidationExperimentError(f"invalid unlabelled validation pool: {exc}") from exc
    validation_pool_id = validation_source_pool.get("pool_id")
    _require(
        isinstance(validation_pool_id, str) and re.fullmatch(r"taskset-[a-f0-9]{20}", validation_pool_id),
        "validation pool ID must identify an assembled task set",
    )
    validation_cases = [case for case in validation_source_pool["cases"] if case.get("split") == "validation"]
    _require(bool(validation_cases), "candidate pool has no validation cases")
    _require(
        not any("relevant_ids" in case or "quality_judgments" in case for case in validation_source_pool["cases"]),
        "registration requires the unlabelled validation task set",
    )
    _require(
        isinstance(minimum_precision_gain, (int, float))
        and not isinstance(minimum_precision_gain, bool)
        and 0 <= minimum_precision_gain <= 1,
        "minimum_precision_gain must be in [0, 1]",
    )
    selection = receipt.get("selection")
    _require(isinstance(selection, dict), "development receipt has no selection")
    _require(selection.get("recommendation") == "research_candidate", "development receipt did not select a research candidate")
    _require(selection.get("automatic_promotion") is False, "development receipt must not claim automatic promotion")
    _require(selection.get("locked_holdout_used") is False, "development receipt must not use holdout data")
    finalist_id = selection.get("development_finalist_id")
    results = receipt.get("development_results")
    _require(isinstance(results, list), "development receipt has no development results")
    by_id = {item.get("proposal_id"): item for item in results if isinstance(item, dict)}
    _require(finalist_id in by_id and "baseline" in by_id, "receipt must include baseline and selected finalist")
    finalist = by_id[finalist_id]
    baseline = by_id["baseline"]
    _require(isinstance(finalist.get("weights"), dict) and isinstance(baseline.get("weights"), dict), "receipt configs are malformed")
    body = {
        "schema_version": 1,
        "registration_type": "single-finalist-validation",
        "validation_pool_id": validation_pool_id,
        "validation_source_pool_sha256": _sha256(validation_source_bytes),
        "validation_candidate_inventory_sha256": candidate_inventory_fingerprint(validation_cases),
        "development_receipt_sha256": _sha256(raw),
        "baseline": {"config_id": "baseline", "weights": baseline["weights"]},
        "finalist": {"config_id": finalist_id, "weights": finalist["weights"]},
        "minimum_precision_gain": float(minimum_precision_gain),
    }
    body["registration_id"] = f"registration-{_sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode())[:20]}"
    return body


def _validate_registration(registration: Any) -> dict[str, Any]:
    _require(isinstance(registration, dict), "registration must be an object")
    fields = {
        "schema_version", "registration_type", "validation_pool_id", "validation_source_pool_sha256",
        "validation_candidate_inventory_sha256", "development_receipt_sha256", "baseline", "finalist",
        "minimum_precision_gain", "registration_id",
    }
    _require(set(registration) == fields, "registration contains missing or unsupported fields")
    _require(registration.get("schema_version") == 1, "unsupported registration schema")
    _require(registration.get("registration_type") == "single-finalist-validation", "unsupported registration type")
    _require(
        isinstance(registration.get("validation_pool_id"), str)
        and re.fullmatch(r"taskset-[a-f0-9]{20}", registration["validation_pool_id"]),
        "invalid registered validation pool ID",
    )
    _require(isinstance(registration.get("development_receipt_sha256"), str), "development receipt hash is required")
    _require(isinstance(registration.get("validation_source_pool_sha256"), str), "validation source-pool hash is required")
    _require(isinstance(registration.get("validation_candidate_inventory_sha256"), str), "validation candidate-inventory hash is required")
    _require(isinstance(registration.get("baseline"), dict) and isinstance(registration.get("finalist"), dict), "registered configs are required")
    threshold = registration.get("minimum_precision_gain")
    _require(isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and 0 <= threshold <= 1, "invalid precision-gain threshold")
    core = {key: registration[key] for key in registration if key != "registration_id"}
    expected_id = f"registration-{_sha256(json.dumps(core, sort_keys=True, separators=(',', ':')).encode())[:20]}"
    _require(registration.get("registration_id") == expected_id, "registration integrity check failed")
    return registration


def evaluate_validation(
    validation_pool: Any,
    registration: Any,
    *,
    validation_bytes: bytes,
    registration_bytes: bytes,
    k: int = 10,
) -> dict[str, Any]:
    registration = _validate_registration(registration)
    _require(isinstance(k, int) and not isinstance(k, bool) and 1 <= k <= 20, "k must be an integer from 1 to 20")
    _require(isinstance(validation_pool, dict) and validation_pool.get("split") == "validation", "input must be a validation-split pool")
    try:
        pool = _validate_pool(validation_pool, "validation")
    except RankingExperimentError as exc:
        raise ValidationExperimentError(str(exc)) from exc
    _require(pool.get("pool_id") == registration["validation_pool_id"], "validation pool does not match pre-registration")
    _require(
        pool.get("source_pool_sha256") == registration["validation_source_pool_sha256"],
        "validation pool does not come from the pre-registered source-pool bytes",
    )
    _require(
        candidate_inventory_fingerprint(pool["cases"])
        == registration["validation_candidate_inventory_sha256"],
        "validation candidate inventory changed after pre-registration",
    )

    baseline = registration["baseline"]
    finalist = registration["finalist"]
    for config_name, config in (("baseline", baseline), ("finalist", finalist)):
        _require(set(config) == {"config_id", "weights"}, f"registered {config_name} config is malformed")
        _require(isinstance(config.get("config_id"), str) and config["config_id"], f"registered {config_name} config ID is required")
    _require(baseline["config_id"] == "baseline", "registered baseline ID must be 'baseline'")
    _require(finalist["config_id"] != "baseline", "finalist must differ from baseline")
    proposal_wrapper = {
        "schema_version": 1,
        "proposals": [
            {"id": "baseline", "parent_id": None, "rationale": "Registered validation baseline", "weights": baseline["weights"]},
            {"id": finalist["config_id"], "parent_id": "baseline", "rationale": "Pre-registered development finalist", "weights": finalist["weights"]},
        ],
    }
    try:
        from .ranking_experiment import _validate_proposals
        configs = _validate_proposals(proposal_wrapper)
    except RankingExperimentError as exc:
        raise ValidationExperimentError(f"registered ranking config is invalid: {exc}") from exc
    weights_by_id = {item["id"]: item["weights"] for item in configs}
    weights = {
        "baseline": weights_by_id[baseline["config_id"]],
        "finalist": weights_by_id[finalist["config_id"]],
    }

    case_count = 0
    precision: dict[str, list[float]] = {"baseline": [], "finalist": []}
    ndcg: dict[str, list[float]] = {"baseline": [], "finalist": []}
    recall: dict[str, list[float]] = {"baseline": [], "finalist": []}
    graded_ndcg: dict[str, list[float]] = {"baseline": [], "finalist": []}
    paired = {"finalist_wins": 0, "baseline_wins": 0, "ties": 0}
    selected_count = 0
    identity_bad = 0
    identity_unassessed = 0
    version_bad = 0
    version_unassessed = 0
    provenance_missing = 0
    source_types: dict[str, int] = {}
    fixed_candidate_sets = True
    incomplete_graded_cases = 0
    relevance_grade_mismatches = 0

    for case in pool["cases"]:
        case_count += 1
        case_scores: dict[str, float] = {}
        ranked_by_config: dict[str, list[str]] = {}
        for config_name in ("baseline", "finalist"):
            ranked_records = _rank_case(case, weights[config_name])
            ranked_ids = [candidate["id"] for candidate in ranked_records]
            ranked_by_config[config_name] = ranked_ids
            scored = _score_case(case["relevant_ids"], ranked_records, k)
            precision[config_name].append(scored["precision_at_k"])
            if scored["ndcg_at_k"] is not None:
                ndcg[config_name].append(scored["ndcg_at_k"])
            if scored["recall_at_k"] is not None:
                recall[config_name].append(scored["recall_at_k"])
            case_scores[config_name] = scored["precision_at_k"]
        if case_scores["finalist"] > case_scores["baseline"]:
            paired["finalist_wins"] += 1
        elif case_scores["finalist"] < case_scores["baseline"]:
            paired["baseline_wins"] += 1
        else:
            paired["ties"] += 1

        ranked = ranked_by_config["finalist"]
        candidate_by_id = {candidate["id"]: candidate for candidate in case["candidates"]}
        expected_ids = {candidate["id"] for candidate in case["candidates"]}
        if len(ranked) != len(set(ranked)) or set(ranked) != expected_ids:
            fixed_candidate_sets = False
        judgments = case.get("quality_judgments", {})
        grades: list[str] = []
        expected_relevant: set[str] = set()
        candidate_ids = {candidate["id"] for candidate in case["candidates"]}
        case_grade_complete = True
        if not isinstance(judgments, dict) or set(judgments) != candidate_ids:
            case_grade_complete = False
            judgments = judgments if isinstance(judgments, dict) else {}
        for candidate in case["candidates"]:
            dimensions = judgments.get(candidate["id"], {}) if isinstance(judgments, dict) else {}
            grade = dimensions.get("relevance") if isinstance(dimensions, dict) else None
            if not isinstance(grade, str) or grade not in {"not_relevant", "background", "useful", "essential"}:
                case_grade_complete = False
                continue
            grades.append(grade)
            if grade in {"useful", "essential"}:
                expected_relevant.add(candidate["id"])
        if case_grade_complete:
            if set(case["relevant_ids"]) != expected_relevant:
                relevance_grade_mismatches += 1
            grade_by_id = {candidate["id"]: judgments[candidate["id"]]["relevance"] for candidate in case["candidates"]}
            for config_name in ("baseline", "finalist"):
                score = _graded_ndcg([grade_by_id[candidate_id] for candidate_id in ranked_by_config[config_name]], k)
                if score is not None:
                    graded_ndcg[config_name].append(score)
        else:
            incomplete_graded_cases += 1
        for candidate_id in ranked[:k]:
            candidate = candidate_by_id[candidate_id]
            selected_count += 1
            if not candidate.get("providers"):
                provenance_missing += 1
            kind = str(candidate.get("entry_type") or "unknown")
            source_types[kind] = source_types.get(kind, 0) + 1
            dimensions = judgments.get(candidate_id, {}) if isinstance(judgments, dict) else {}
            if not isinstance(dimensions, dict):
                dimensions = {}
            identity = dimensions.get("identity_correct")
            version = dimensions.get("version_match")
            identity_bad += identity == "no"
            identity_unassessed += not isinstance(identity, str) or identity not in {"yes", "no"}
            version_bad += version == "no"
            version_unassessed += not isinstance(version, str) or version not in {"yes", "no", "not_applicable"}

    mean = lambda values: round(sum(values) / len(values), 6) if values else None
    baseline_precision = mean(precision["baseline"]) or 0.0
    finalist_precision = mean(precision["finalist"]) or 0.0
    precision_gain = round(finalist_precision - baseline_precision, 6)
    checks = {
        "candidate_set_unchanged": fixed_candidate_sets,
        "graded_relevance_complete": incomplete_graded_cases == 0,
        "binary_relevance_matches_grades": relevance_grade_mismatches == 0,
        "selected_candidates_have_provenance": provenance_missing == 0,
        "selected_identity_correct": identity_bad == 0 and identity_unassessed == 0,
        "selected_version_match_or_not_applicable": version_bad == 0 and version_unassessed == 0,
    }
    passed = all(checks.values()) and precision_gain >= registration["minimum_precision_gain"]
    return {
        "schema_version": 1,
        "evaluation_type": "single-finalist-validation",
        "registration_id": registration["registration_id"],
        "validation_pool_id": pool["pool_id"],
        "validation_pool_sha256": _sha256(validation_bytes),
        "registration_sha256": _sha256(registration_bytes),
        "cutoff_k": k,
        "aggregate": {
            "case_count": case_count,
            "mean_precision_at_k": {"baseline": baseline_precision, "finalist": finalist_precision, "paired_gain": precision_gain},
            "mean_ndcg_at_k": {"baseline": mean(ndcg["baseline"]), "finalist": mean(ndcg["finalist"])},
            "mean_recall_at_k": {"baseline": mean(recall["baseline"]), "finalist": mean(recall["finalist"])},
            "mean_graded_ndcg_at_k": {"baseline": mean(graded_ndcg["baseline"]), "finalist": mean(graded_ndcg["finalist"])},
            "incomplete_graded_relevance_cases": incomplete_graded_cases,
            "binary_relevance_grade_mismatches": relevance_grade_mismatches,
            "paired_precision_cases": paired,
            "finalist_top_k_count": selected_count,
            "selected_identity_errors": identity_bad,
            "selected_identity_unassessed_or_uncertain": identity_unassessed,
            "selected_version_errors": version_bad,
            "selected_version_unassessed_or_uncertain": version_unassessed,
            "selected_missing_provenance": provenance_missing,
            "selected_entry_types": dict(sorted(source_types.items())),
        },
        "critical_checks": checks,
        "minimum_precision_gain": registration["minimum_precision_gain"],
        "decision": "validation_candidate" if passed else "retain_baseline",
        "automatic_promotion": False,
        "holdout_used": False,
    }


def run_validation_paths(
    validation_path: Path,
    registration_path: Path,
    output_dir: Path,
    *,
    k: int = 10,
) -> tuple[dict[str, Any], Path]:
    validation, validation_bytes = _load_json(validation_path)
    registration, registration_bytes = _load_json(registration_path)
    if not isinstance(validation, dict) or not isinstance(validation.get("pool_id"), str):
        raise ValidationExperimentError("validation pool is malformed")
    _validate_registration(registration)
    if validation.get("pool_id") != registration["validation_pool_id"]:
        raise ValidationExperimentError("validation pool does not match pre-registration")
    output_path = output_dir / f"validation-{validation['pool_id']}.json"
    if output_path.exists():
        raise ValidationExperimentError(f"validation set already evaluated in this output directory: {validation['pool_id']}")
    result = evaluate_validation(
        validation,
        registration,
        validation_bytes=validation_bytes,
        registration_bytes=registration_bytes,
        k=k,
    )
    _claim_validation_once(validation_path, registration, validation_bytes, registration_bytes)
    try:
        write_private_json(output_path, result)
    except DiscoveryPoolError as exc:
        raise ValidationExperimentError(str(exc)) from exc
    return result, output_path


def _claim_validation_once(
    validation_path: Path,
    registration: dict[str, Any],
    validation_bytes: bytes,
    registration_bytes: bytes,
) -> Path:
    """Persist a pool-scoped one-shot claim independent of receipt location."""
    marker = validation_path.resolve().parent / f".validation-{registration['validation_pool_id']}.consumed.json"
    content = {
        "schema_version": 1,
        "registration_id": registration["registration_id"],
        "validation_pool_id": registration["validation_pool_id"],
        "registration_sha256": _sha256(registration_bytes),
        "validation_pool_sha256": _sha256(validation_bytes),
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(marker, flags, 0o600)
    except FileExistsError as exc:
        raise ValidationExperimentError(
            f"validation registration already consumed for task set {registration['validation_pool_id']}"
        ) from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(content, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return marker
