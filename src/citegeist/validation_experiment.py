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
    empty_relevance_cases = 0
    empty_relevance_top_k_returns = {"baseline": 0, "finalist": 0}
    answerability_case_counts = {"answerable": 0, "unanswerable": 0, "uncertain": 0, "unassessed": 0}
    unanswerable_top_k_returns = {"baseline": 0, "finalist": 0}
    selected_count = 0
    identity_bad = 0
    identity_unassessed = 0
    version_bad = 0
    version_unassessed = 0
    provenance_missing = 0
    source_types: dict[str, dict[str, int]] = {"baseline": {}, "finalist": {}}
    source_providers: dict[str, dict[str, int]] = {"baseline": {}, "finalist": {}}
    fixed_candidate_sets = True
    incomplete_graded_cases = 0
    relevance_grade_mismatches = 0

    for case in pool["cases"]:
        case_count += 1
        answerability = case.get("answerability", "unassessed")
        if not isinstance(answerability, str) or answerability not in answerability_case_counts:
            raise ValidationExperimentError(f"{case['case_id']}: invalid answerability label")
        answerability_case_counts[answerability] += 1
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
            if not case["relevant_ids"] and ranked_ids[:k]:
                empty_relevance_top_k_returns[config_name] += 1
            if answerability == "unanswerable" and ranked_ids[:k]:
                unanswerable_top_k_returns[config_name] += 1
        if not case["relevant_ids"]:
            empty_relevance_cases += 1
        if case_scores["finalist"] > case_scores["baseline"]:
            paired["finalist_wins"] += 1
        elif case_scores["finalist"] < case_scores["baseline"]:
            paired["baseline_wins"] += 1
        else:
            paired["ties"] += 1

        ranked = ranked_by_config["finalist"]
        candidate_by_id = {candidate["id"]: candidate for candidate in case["candidates"]}
        expected_ids = {candidate["id"] for candidate in case["candidates"]}
        for config_name in ("baseline", "finalist"):
            for candidate_id in ranked_by_config[config_name][:k]:
                kind = str(candidate_by_id[candidate_id].get("entry_type") or "unknown")
                source_types[config_name][kind] = source_types[config_name].get(kind, 0) + 1
                providers = set(candidate_by_id[candidate_id].get("providers", []))
                providers.update(candidate_by_id[candidate_id].get("provider_ranks", {}))
                for provider in providers or {"unknown"}:
                    source_providers[config_name][provider] = source_providers[config_name].get(provider, 0) + 1
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
            "empty_relevance_cases": empty_relevance_cases,
            "empty_relevance_top_k_returns": empty_relevance_top_k_returns,
            "answerability_case_counts": answerability_case_counts,
            "unanswerable_top_k_returns": unanswerable_top_k_returns,
            "finalist_top_k_count": selected_count,
            "selected_identity_errors": identity_bad,
            "selected_identity_unassessed_or_uncertain": identity_unassessed,
            "selected_version_errors": version_bad,
            "selected_version_unassessed_or_uncertain": version_unassessed,
            "selected_missing_provenance": provenance_missing,
            "selected_entry_types": {name: dict(sorted(values.items())) for name, values in source_types.items()},
            "selected_entry_type_coverage": {name: len(values) for name, values in source_types.items()},
            "selected_provider_coverage": {name: dict(sorted(values.items())) for name, values in source_providers.items()},
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


def register_holdout(
    validation_receipt_path: Path,
    validation_registration_path: Path,
    *,
    holdout_pool_path: Path,
    minimum_precision_gain: float,
    maximum_recall_loss: float,
    maximum_empty_relevance_regression: int = 0,
    maximum_source_coverage_loss: int = 0,
    maximum_unanswerable_false_positive_regression: int = 0,
    maximum_unanswerable_false_positives: int = 0,
) -> dict[str, Any]:
    """Freeze a holdout comparison only after the registered finalist passed validation."""
    receipt, receipt_bytes = _load_json(validation_receipt_path)
    validation_registration, validation_registration_bytes = _load_json(validation_registration_path)
    validation_registration = _validate_registration(validation_registration)
    _require(isinstance(receipt, dict), "validation receipt must be an object")
    _require(receipt.get("schema_version") == 1, "unsupported validation receipt schema")
    _require(receipt.get("evaluation_type") == "single-finalist-validation", "receipt is not a validation evaluation")
    _require(receipt.get("decision") == "validation_candidate", "holdout requires a finalist that passed validation")
    _require(receipt.get("automatic_promotion") is False, "validation receipt must not claim automatic promotion")
    _require(receipt.get("holdout_used") is False, "validation receipt must not use holdout data")
    _require(receipt.get("registration_id") == validation_registration["registration_id"], "validation receipt does not match its registration")
    _require(receipt.get("registration_sha256") == _sha256(validation_registration_bytes), "validation registration bytes do not match the receipt")
    _require(receipt.get("validation_pool_id") == validation_registration["validation_pool_id"], "validation receipt pool does not match its registration")
    checks = receipt.get("critical_checks")
    _require(isinstance(checks, dict) and bool(checks) and all(value is True for value in checks.values()), "validation receipt has failed or missing critical checks")
    try:
        holdout_source, holdout_source_bytes = _read_pool(holdout_pool_path)
    except DiscoveryPoolError as exc:
        raise ValidationExperimentError(f"invalid unlabelled holdout pool: {exc}") from exc
    holdout_pool_id = holdout_source.get("pool_id")
    _require(
        isinstance(holdout_pool_id, str) and re.fullmatch(r"taskset-[a-f0-9]{20}", holdout_pool_id),
        "holdout pool ID must identify an assembled task set",
    )
    holdout_cases = [case for case in holdout_source["cases"] if case.get("split") == "holdout"]
    _require(bool(holdout_cases), "candidate pool has no holdout cases")
    _require(
        not any("relevant_ids" in case or "quality_judgments" in case for case in holdout_source["cases"]),
        "registration requires the unlabelled holdout task set",
    )
    _require(
        isinstance(minimum_precision_gain, (int, float))
        and not isinstance(minimum_precision_gain, bool)
        and 0 <= minimum_precision_gain <= 1,
        "minimum_precision_gain must be in [0, 1]",
    )
    _require(
        isinstance(maximum_recall_loss, (int, float))
        and not isinstance(maximum_recall_loss, bool)
        and 0 <= maximum_recall_loss <= 1,
        "maximum_recall_loss must be in [0, 1]",
    )
    _require(
        isinstance(maximum_empty_relevance_regression, int)
        and not isinstance(maximum_empty_relevance_regression, bool)
        and 0 <= maximum_empty_relevance_regression <= len(holdout_cases),
        "maximum_empty_relevance_regression must be from zero to the number of holdout cases",
    )
    _require(
        isinstance(maximum_unanswerable_false_positive_regression, int)
        and not isinstance(maximum_unanswerable_false_positive_regression, bool)
        and 0 <= maximum_unanswerable_false_positive_regression <= len(holdout_cases),
        "maximum_unanswerable_false_positive_regression must be from zero to the number of holdout cases",
    )
    _require(
        isinstance(maximum_unanswerable_false_positives, int)
        and not isinstance(maximum_unanswerable_false_positives, bool)
        and 0 <= maximum_unanswerable_false_positives <= len(holdout_cases),
        "maximum_unanswerable_false_positives must be from zero to the number of holdout cases",
    )
    _require(
        isinstance(maximum_source_coverage_loss, int)
        and not isinstance(maximum_source_coverage_loss, bool)
        and 0 <= maximum_source_coverage_loss <= len({
            provider
            for case in holdout_cases
            for candidate in case["candidates"]
            for provider in (set(candidate.get("providers", [])) | set(candidate.get("provider_ranks", {})))
        }),
        "maximum_source_coverage_loss must be from zero to the distinct holdout provider count",
    )
    body = {
        "schema_version": 1,
        "registration_type": "single-finalist-holdout",
        "holdout_pool_id": holdout_pool_id,
        "holdout_source_pool_sha256": _sha256(holdout_source_bytes),
        "holdout_candidate_inventory_sha256": candidate_inventory_fingerprint(holdout_cases),
        "validation_registration_id": validation_registration["registration_id"],
        "validation_receipt_sha256": _sha256(receipt_bytes),
        "baseline": validation_registration["baseline"],
        "finalist": validation_registration["finalist"],
        "minimum_precision_gain": float(minimum_precision_gain),
        "maximum_recall_loss": float(maximum_recall_loss),
        "maximum_empty_relevance_regression": maximum_empty_relevance_regression,
        "maximum_unanswerable_false_positive_regression": maximum_unanswerable_false_positive_regression,
        "maximum_unanswerable_false_positives": maximum_unanswerable_false_positives,
        "maximum_source_coverage_loss": maximum_source_coverage_loss,
    }
    body["registration_id"] = f"registration-{_sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode())[:20]}"
    return body


def _validate_holdout_registration(registration: Any) -> dict[str, Any]:
    _require(isinstance(registration, dict), "holdout registration must be an object")
    fields = {
        "schema_version", "registration_type", "holdout_pool_id", "holdout_source_pool_sha256",
        "holdout_candidate_inventory_sha256", "validation_registration_id", "validation_receipt_sha256",
        "baseline", "finalist", "minimum_precision_gain", "maximum_recall_loss",
        "maximum_empty_relevance_regression", "maximum_source_coverage_loss",
        "maximum_unanswerable_false_positive_regression", "maximum_unanswerable_false_positives", "registration_id",
    }
    _require(set(registration) == fields, "holdout registration contains missing or unsupported fields")
    _require(registration.get("schema_version") == 1, "unsupported holdout registration schema")
    _require(registration.get("registration_type") == "single-finalist-holdout", "unsupported holdout registration type")
    _require(
        isinstance(registration.get("holdout_pool_id"), str)
        and re.fullmatch(r"taskset-[a-f0-9]{20}", registration["holdout_pool_id"]),
        "invalid registered holdout pool ID",
    )
    for field in ("holdout_source_pool_sha256", "holdout_candidate_inventory_sha256", "validation_receipt_sha256"):
        _require(isinstance(registration.get(field), str) and re.fullmatch(r"[a-f0-9]{64}", registration[field]), f"{field} must be a SHA-256 hash")
    _require(
        isinstance(registration.get("validation_registration_id"), str)
        and re.fullmatch(r"registration-[a-f0-9]{20}", registration["validation_registration_id"]),
        "validation_registration_id is invalid",
    )
    _require(isinstance(registration.get("baseline"), dict) and isinstance(registration.get("finalist"), dict), "registered configs are required")
    for field in ("minimum_precision_gain", "maximum_recall_loss"):
        value = registration.get(field)
        _require(isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1, f"invalid {field}")
    regression = registration.get("maximum_empty_relevance_regression")
    _require(isinstance(regression, int) and not isinstance(regression, bool) and regression >= 0, "invalid maximum_empty_relevance_regression")
    unanswerable_regression = registration.get("maximum_unanswerable_false_positive_regression")
    _require(
        isinstance(unanswerable_regression, int) and not isinstance(unanswerable_regression, bool) and unanswerable_regression >= 0,
        "invalid maximum_unanswerable_false_positive_regression",
    )
    unanswerable_false_positives = registration.get("maximum_unanswerable_false_positives")
    _require(
        isinstance(unanswerable_false_positives, int)
        and not isinstance(unanswerable_false_positives, bool)
        and unanswerable_false_positives >= 0,
        "invalid maximum_unanswerable_false_positives",
    )
    coverage_loss = registration.get("maximum_source_coverage_loss")
    _require(isinstance(coverage_loss, int) and not isinstance(coverage_loss, bool) and coverage_loss >= 0, "invalid maximum_source_coverage_loss")
    core = {key: registration[key] for key in registration if key != "registration_id"}
    expected_id = f"registration-{_sha256(json.dumps(core, sort_keys=True, separators=(',', ':')).encode())[:20]}"
    _require(registration.get("registration_id") == expected_id, "holdout registration integrity check failed")
    return registration


def evaluate_holdout(
    holdout_pool: Any,
    registration: Any,
    *,
    holdout_bytes: bytes,
    registration_bytes: bytes,
    k: int = 10,
) -> dict[str, Any]:
    """Evaluate a registered finalist once and return aggregate-only holdout evidence."""
    registration = _validate_holdout_registration(registration)
    _require(isinstance(k, int) and not isinstance(k, bool) and 1 <= k <= 20, "k must be an integer from 1 to 20")
    _require(isinstance(holdout_pool, dict) and holdout_pool.get("split") == "holdout", "input must be a holdout-split pool")
    try:
        pool = _validate_pool(holdout_pool, "holdout")
    except RankingExperimentError as exc:
        raise ValidationExperimentError(str(exc)) from exc
    if any(
        not isinstance(case.get("answerability"), str)
        or case["answerability"] not in {"answerable", "unanswerable", "uncertain"}
        for case in pool["cases"]
    ):
        raise ValidationExperimentError("holdout requires an explicit answerability judgment for every case")
    _require(pool.get("pool_id") == registration["holdout_pool_id"], "holdout pool does not match pre-registration")
    _require(pool.get("source_pool_sha256") == registration["holdout_source_pool_sha256"], "holdout pool does not come from the pre-registered source-pool bytes")
    _require(
        candidate_inventory_fingerprint(pool["cases"]) == registration["holdout_candidate_inventory_sha256"],
        "holdout candidate inventory changed after pre-registration",
    )
    # The validation evaluator owns the shared ranking and critical-check logic. This
    # private adapter changes only the stage binding; holdout fields remain separately
    # registered and are restored in the public receipt below.
    proxy = {
        "schema_version": 1,
        "registration_type": "single-finalist-validation",
        "validation_pool_id": registration["holdout_pool_id"],
        "validation_source_pool_sha256": registration["holdout_source_pool_sha256"],
        "validation_candidate_inventory_sha256": registration["holdout_candidate_inventory_sha256"],
        "development_receipt_sha256": registration["validation_receipt_sha256"],
        "baseline": registration["baseline"],
        "finalist": registration["finalist"],
        "minimum_precision_gain": registration["minimum_precision_gain"],
    }
    proxy["registration_id"] = f"registration-{_sha256(json.dumps(proxy, sort_keys=True, separators=(',', ':')).encode())[:20]}"
    proxy_pool = dict(pool)
    proxy_pool["split"] = "validation"
    result = evaluate_validation(
        proxy_pool,
        proxy,
        validation_bytes=holdout_bytes,
        registration_bytes=registration_bytes,
        k=k,
    )
    aggregate = result["aggregate"]
    baseline_recall = aggregate["mean_recall_at_k"]["baseline"]
    finalist_recall = aggregate["mean_recall_at_k"]["finalist"]
    recall_gain = None if baseline_recall is None or finalist_recall is None else round(finalist_recall - baseline_recall, 6)
    empty_counts = aggregate["empty_relevance_top_k_returns"]
    empty_regression = empty_counts["finalist"] - empty_counts["baseline"]
    unanswerable_counts = aggregate["unanswerable_top_k_returns"]
    unanswerable_regression = unanswerable_counts["finalist"] - unanswerable_counts["baseline"]
    selected_providers = aggregate["selected_provider_coverage"]
    source_coverage_loss = len(set(selected_providers["baseline"]) - set(selected_providers["finalist"]))
    holdout_checks = {
        **result["critical_checks"],
        "recall_loss_within_tolerance": recall_gain is not None and recall_gain >= -registration["maximum_recall_loss"],
        "empty_relevance_regression_within_tolerance": empty_regression <= registration["maximum_empty_relevance_regression"],
        "unanswerable_false_positive_regression_within_tolerance": (
            unanswerable_regression <= registration["maximum_unanswerable_false_positive_regression"]
        ),
        "unanswerable_false_positives_within_tolerance": (
            unanswerable_counts["finalist"] <= registration["maximum_unanswerable_false_positives"]
        ),
        "source_coverage_within_tolerance": source_coverage_loss <= registration["maximum_source_coverage_loss"],
    }
    passed = (
        all(holdout_checks.values())
        and aggregate["mean_precision_at_k"]["paired_gain"] >= registration["minimum_precision_gain"]
    )
    result.pop("validation_pool_id", None)
    result.pop("validation_pool_sha256", None)
    result.update({
        "evaluation_type": "single-finalist-holdout",
        "registration_id": registration["registration_id"],
        "holdout_pool_id": pool["pool_id"],
        "holdout_pool_sha256": _sha256(holdout_bytes),
        "holdout_source_pool_sha256": registration["holdout_source_pool_sha256"],
        "holdout_candidate_inventory_sha256": registration["holdout_candidate_inventory_sha256"],
        "validation_registration_id": registration["validation_registration_id"],
        "validation_receipt_sha256": registration["validation_receipt_sha256"],
        "holdout_used": True,
        "thresholds": {
            "minimum_precision_gain": registration["minimum_precision_gain"],
            "maximum_recall_loss": registration["maximum_recall_loss"],
            "maximum_empty_relevance_regression": registration["maximum_empty_relevance_regression"],
            "maximum_unanswerable_false_positive_regression": registration["maximum_unanswerable_false_positive_regression"],
            "maximum_unanswerable_false_positives": registration["maximum_unanswerable_false_positives"],
            "maximum_source_coverage_loss": registration["maximum_source_coverage_loss"],
        },
        "critical_checks": holdout_checks,
        "aggregate": {
            **aggregate,
            "mean_recall_at_k": {**aggregate["mean_recall_at_k"], "paired_gain": recall_gain},
            "empty_relevance_top_k_returns": {**empty_counts, "paired_regression": empty_regression},
            "unanswerable_case_count": aggregate["answerability_case_counts"]["unanswerable"],
            "unanswerable_top_k_returns": {**unanswerable_counts, "paired_regression": unanswerable_regression},
            "source_provider_coverage": {
                "baseline_provider_count": len(selected_providers["baseline"]),
                "finalist_provider_count": len(selected_providers["finalist"]),
                "baseline_providers_lost": source_coverage_loss,
            },
        },
        "decision": "holdout_candidate" if passed else "retain_baseline",
        "automatic_promotion": False,
    })
    return result


def run_holdout_paths(
    holdout_path: Path,
    registration_path: Path,
    output_dir: Path,
    *,
    k: int = 10,
) -> tuple[dict[str, Any], Path]:
    holdout, holdout_bytes = _load_json(holdout_path)
    registration, registration_bytes = _load_json(registration_path)
    if not isinstance(holdout, dict) or not isinstance(holdout.get("pool_id"), str):
        raise ValidationExperimentError("holdout pool is malformed")
    _validate_holdout_registration(registration)
    if holdout.get("pool_id") != registration["holdout_pool_id"]:
        raise ValidationExperimentError("holdout pool does not match pre-registration")
    output_path = output_dir / f"holdout-{holdout['pool_id']}.json"
    if output_path.exists():
        raise ValidationExperimentError(f"holdout set already evaluated in this output directory: {holdout['pool_id']}")
    result = evaluate_holdout(
        holdout,
        registration,
        holdout_bytes=holdout_bytes,
        registration_bytes=registration_bytes,
        k=k,
    )
    _claim_holdout_once(holdout_path, registration, holdout_bytes, registration_bytes)
    try:
        write_private_json(output_path, result)
    except DiscoveryPoolError as exc:
        raise ValidationExperimentError(str(exc)) from exc
    return result, output_path


def _claim_holdout_once(
    holdout_path: Path,
    registration: dict[str, Any],
    holdout_bytes: bytes,
    registration_bytes: bytes,
) -> Path:
    """Persist a pool-scoped one-shot holdout claim beside the protected pool."""
    marker = holdout_path.resolve().parent / f".holdout-{registration['holdout_pool_id']}.consumed.json"
    content = {
        "schema_version": 1,
        "registration_id": registration["registration_id"],
        "holdout_pool_id": registration["holdout_pool_id"],
        "registration_sha256": _sha256(registration_bytes),
        "holdout_pool_sha256": _sha256(holdout_bytes),
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(marker, flags, 0o600)
    except FileExistsError as exc:
        raise ValidationExperimentError(f"holdout registration already consumed for task set {registration['holdout_pool_id']}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(content, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return marker
