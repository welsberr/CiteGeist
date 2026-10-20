import json
from pathlib import Path

import pytest

from citegeist.discovery_pool import build_judgment_template, prepare_rank_pool
from citegeist.cli import main
from citegeist.ranking_experiment import run_ranking_experiment
from citegeist.validation_experiment import (
    ValidationExperimentError,
    register_validation,
    run_validation_paths,
)
from test_discovery_pool import _write_pool


def _development_receipt(tmp_path):
    pool = {
        "schema_version": 1,
        "pool_id": "dev-pool",
        "split": "development",
        "cases": [{
            "case_id": "dev-case",
            "query": "marine echolocation navigation",
            "relevant_ids": ["relevant"],
            "seed_texts": ["dolphin echolocation navigation"],
            "candidates": [
                {"id": "noise", "fields": {"title": "Marine echolocation acoustics"}, "providers": ["crossref"], "provider_ranks": {"crossref": 1}},
                {"id": "relevant", "fields": {"title": "Dolphin echolocation navigation"}, "providers": ["openalex"], "provider_ranks": {"openalex": 2}},
            ],
        }],
    }
    proposals = {
        "schema_version": 1,
        "proposals": [
            {"id": "baseline", "rationale": "Declared lexical baseline", "weights": {"lexical": 1}},
            {"id": "seed-balanced", "rationale": "Test seed overlap", "weights": {"seed_overlap": 1}},
        ],
    }
    receipt = run_ranking_experiment(
        pool, proposals,
        development_bytes=json.dumps(pool).encode(),
        proposal_bytes=json.dumps(proposals).encode(),
        repo=Path(__file__).resolve().parents[1],
        k=1,
    )
    path = tmp_path / "development-receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return path


def _validation_pool(tmp_path):
    assembled_path = _write_pool(tmp_path, split="validation")
    template = build_judgment_template(assembled_path, split="validation", reviewer_id="validation-reviewer")
    for case in template["judgments"]:
        for candidate in case["candidate_judgments"]:
            candidate["relevance"] = "essential" if candidate["candidate_id"].startswith("doi:") else "not_relevant"
            candidate["identity_correct"] = "yes"
            candidate["version_match"] = "yes"
    labels_path = tmp_path / "validation-labels.json"
    labels_path.write_text(json.dumps(template), encoding="utf-8")
    validation = prepare_rank_pool(assembled_path, labels_path, split="validation")
    path = tmp_path / "validation.json"
    path.write_text(json.dumps(validation), encoding="utf-8")
    return assembled_path, path, validation["pool_id"]


def test_registers_one_finalist_before_aggregate_only_validation(tmp_path):
    development_receipt = _development_receipt(tmp_path)
    validation_source_path, validation_path, _validation_pool_id = _validation_pool(tmp_path)
    registration = register_validation(
        development_receipt,
        validation_pool_path=validation_source_path,
        minimum_precision_gain=0.0,
    )
    registration_path = tmp_path / "registration.json"
    registration_path.write_text(json.dumps(registration), encoding="utf-8")

    receipt, output_path = run_validation_paths(validation_path, registration_path, tmp_path / "validation-receipts", k=1)
    assert output_path.exists()
    assert receipt["decision"] == "validation_candidate"
    assert receipt["automatic_promotion"] is False
    assert receipt["holdout_used"] is False
    assert receipt["critical_checks"] == {
        "candidate_set_unchanged": True,
        "graded_relevance_complete": True,
        "binary_relevance_matches_grades": True,
        "selected_candidates_have_provenance": True,
        "selected_identity_correct": True,
        "selected_version_match_or_not_applicable": True,
    }
    assert "case_count" in receipt["aggregate"]
    assert receipt["aggregate"]["mean_graded_ndcg_at_k"]["finalist"] is not None
    assert "cases" not in receipt
    assert "ranked_ids" not in output_path.read_text(encoding="utf-8")
    with pytest.raises(ValidationExperimentError, match="already evaluated"):
        run_validation_paths(validation_path, registration_path, tmp_path / "validation-receipts", k=1)


def test_validation_requires_matching_pool_and_predeclared_finalist(tmp_path):
    development_receipt = _development_receipt(tmp_path)
    validation_source_path, validation_path, _validation_pool_id = _validation_pool(tmp_path)
    registration = register_validation(
        development_receipt,
        validation_pool_path=validation_source_path,
        minimum_precision_gain=0.0,
    )
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["split"] = "holdout"
    with pytest.raises(ValidationExperimentError, match="validation-split"):
        from citegeist.validation_experiment import evaluate_validation
        evaluate_validation(validation, registration, validation_bytes=b"pool", registration_bytes=b"reg")

    registration["minimum_precision_gain"] = 0.2
    with pytest.raises(ValidationExperimentError, match="integrity check"):
        from citegeist.validation_experiment import _validate_registration
        _validate_registration(registration)

    registration = register_validation(
        development_receipt,
        validation_pool_path=validation_source_path,
        minimum_precision_gain=0.0,
    )
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["cases"][0]["candidates"][0]["fields"]["title"] = "Changed after registration"
    from citegeist.validation_experiment import evaluate_validation
    with pytest.raises(ValidationExperimentError, match="candidate inventory changed"):
        evaluate_validation(validation, registration, validation_bytes=b"pool", registration_bytes=b"reg")


def test_validation_fails_critical_identity_check(tmp_path):
    development_receipt = _development_receipt(tmp_path)
    validation_source_path, validation_path, _validation_pool_id = _validation_pool(tmp_path)
    registration = register_validation(
        development_receipt,
        validation_pool_path=validation_source_path,
        minimum_precision_gain=0.0,
    )
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    first_case = validation["cases"][0]
    first_case["quality_judgments"][first_case["candidates"][0]["id"]]["identity_correct"] = "no"
    from citegeist.validation_experiment import evaluate_validation
    result = evaluate_validation(validation, registration, validation_bytes=b"pool", registration_bytes=b"reg", k=1)
    assert result["critical_checks"]["selected_identity_correct"] is False
    assert result["decision"] == "retain_baseline"


def test_validation_rejects_binary_and_graded_relevance_disagreement(tmp_path):
    development_receipt = _development_receipt(tmp_path)
    validation_source_path, validation_path, _validation_pool_id = _validation_pool(tmp_path)
    registration = register_validation(
        development_receipt,
        validation_pool_path=validation_source_path,
        minimum_precision_gain=0.0,
    )
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["cases"][0]["relevant_ids"] = []
    from citegeist.validation_experiment import evaluate_validation
    result = evaluate_validation(validation, registration, validation_bytes=b"pool", registration_bytes=b"reg", k=1)
    assert result["critical_checks"]["binary_relevance_matches_grades"] is False
    assert result["decision"] == "retain_baseline"


def test_cli_registers_and_runs_one_shot_validation(tmp_path, capsys):
    development_receipt = _development_receipt(tmp_path)
    validation_source_path, validation_path, validation_pool_id = _validation_pool(tmp_path)
    registration_path = tmp_path / "registration.json"
    assert main([
        "register-validation", "--development-receipt", str(development_receipt),
        "--validation-pool", str(validation_source_path), "--minimum-precision-gain", "0",
        "--output", str(registration_path),
    ]) == 0
    capsys.readouterr()
    output_dir = tmp_path / "validation-receipts"
    assert main([
        "validate-rank", "--validation", str(validation_path),
        "--registration", str(registration_path), "--output-dir", str(output_dir), "--k", "1",
    ]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["decision"] == "validation_candidate"
    assert Path(response["receipt"]).exists()
    assert main([
        "validate-rank", "--validation", str(validation_path),
        "--registration", str(registration_path), "--output-dir", str(output_dir), "--k", "1",
    ]) == 2
    assert "already evaluated" in capsys.readouterr().err
