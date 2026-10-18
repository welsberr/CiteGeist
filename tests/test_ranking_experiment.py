import json
from pathlib import Path

import pytest

from citegeist.ranking_experiment import RankingExperimentError, run_paths, run_ranking_experiment
from citegeist.cli import main


def _pool(pool_id="dev"):
    return {
        "schema_version": 1,
        "pool_id": pool_id,
        "cases": [
            {
                "case_id": f"{pool_id}-case-1",
                "query": "marine echolocation",
                "seed_texts": ["dolphin echolocation navigation"],
                "relevant_ids": ["relevant"],
                "candidates": [
                    {
                        "id": "distractor",
                        "fields": {"title": "Marine echolocation acoustics"},
                        "providers": ["crossref"],
                        "provider_ranks": {"crossref": 1},
                    },
                    {
                        "id": "relevant",
                        "fields": {"title": "Dolphin echolocation navigation"},
                        "providers": ["openalex"],
                        "provider_ranks": {"openalex": 2},
                    },
                ],
            },
            {
                "case_id": f"{pool_id}-case-2",
                "query": "unanswerable question",
                "relevant_ids": [],
                "candidates": [],
            },
        ],
    }


def _proposals():
    return {
        "schema_version": 1,
        "proposals": [
            {"id": "baseline", "rationale": "Lexical-only baseline", "weights": {"lexical": 1}},
            {"id": "seed-balanced", "rationale": "Test seed overlap", "weights": {"seed_overlap": 1}},
        ],
    }


def _run():
    pool = _pool()
    proposals = _proposals()
    return run_ranking_experiment(
        pool,
        proposals,
        development_bytes=json.dumps(pool, sort_keys=True).encode(),
        proposal_bytes=json.dumps(proposals, sort_keys=True).encode(),
        repo=Path(__file__).resolve().parents[1],
        k=1,
    )


def test_experiment_selects_better_development_proposal_without_promotion():
    receipt = _run()
    assert receipt["selection"]["development_finalist_id"] == "seed-balanced"
    assert receipt["selection"]["development_precision_gain"] == 0.5
    assert receipt["selection"]["recommendation"] == "research_candidate"
    assert receipt["selection"]["automatic_promotion"] is False
    assert receipt["selection"]["locked_holdout_used"] is False
    assert receipt["budget"]["network_calls"] == 0
    assert receipt["budget"]["database_writes"] == 0


def test_proposals_reject_executable_fields():
    proposals = _proposals()
    proposals["proposals"][1]["python"] = "print('run me')"
    with pytest.raises(RankingExperimentError, match="unsupported fields"):
        run_ranking_experiment(
            _pool(), proposals, development_bytes=b"pool", proposal_bytes=b"proposal",
            repo=Path.cwd(), k=1,
        )


def test_candidate_set_cannot_change_between_proposals():
    proposals = _proposals()
    proposals["proposals"][1]["candidate_ids"] = ["made-up-id"]
    with pytest.raises(RankingExperimentError, match="unsupported fields"):
        run_ranking_experiment(
            _pool(), proposals, development_bytes=b"pool", proposal_bytes=b"proposal",
            repo=Path.cwd(), k=1,
        )


def test_proposal_lineage_must_be_acyclic():
    proposals = _proposals()
    proposals["proposals"][1]["parent_id"] = "cycle"
    proposals["proposals"].append({
        "id": "cycle", "parent_id": "seed-balanced", "rationale": "Cycle test",
        "weights": {"lexical": 1},
    })
    with pytest.raises(RankingExperimentError, match="lineage contains a cycle"):
        run_ranking_experiment(
            _pool(), proposals, development_bytes=b"pool", proposal_bytes=b"proposal",
            repo=Path.cwd(), k=1,
        )


def test_experiment_refuses_to_overwrite_inputs_or_receipts(tmp_path):
    development = tmp_path / "development.json"
    proposals = tmp_path / "proposals.json"
    output = tmp_path / "receipt.json"
    development.write_text(json.dumps(_pool()), encoding="utf-8")
    proposals.write_text(json.dumps(_proposals()), encoding="utf-8")
    output.write_text("prior receipt", encoding="utf-8")
    with pytest.raises(RankingExperimentError, match="already exists"):
        run_paths(development, proposals, output, k=1)


def test_development_pool_ids_must_be_unique():
    pool = _pool()
    pool["cases"][1]["case_id"] = pool["cases"][0]["case_id"]
    proposals = _proposals()
    with pytest.raises(RankingExperimentError, match="duplicate case_id"):
        run_ranking_experiment(
            pool, proposals, development_bytes=b"pool", proposal_bytes=b"proposal",
            repo=Path.cwd(), k=1,
        )


def test_relevant_ids_must_belong_to_fixed_candidate_set():
    pool = _pool()
    pool["cases"][0]["relevant_ids"] = ["not-in-pool"]
    proposals = _proposals()
    with pytest.raises(RankingExperimentError, match="fixed candidate set"):
        run_ranking_experiment(
            pool, proposals, development_bytes=b"pool", proposal_bytes=b"proposal",
            repo=Path.cwd(), k=1,
        )


def test_experiment_runner_refuses_validation_and_holdout_splits():
    proposals = _proposals()
    for split in ("validation", "holdout"):
        pool = _pool(split)
        pool["split"] = split
        with pytest.raises(RankingExperimentError, match="development pools only"):
            run_ranking_experiment(
                pool, proposals, development_bytes=b"pool", proposal_bytes=b"proposal",
                repo=Path.cwd(), k=1,
            )


def test_cli_writes_private_receipt_from_json_proposals(tmp_path, capsys):
    development = tmp_path / "development.json"
    proposals = tmp_path / "proposals.json"
    output = tmp_path / "receipt.json"
    development.write_text(json.dumps(_pool()), encoding="utf-8")
    proposals.write_text(json.dumps(_proposals()), encoding="utf-8")

    assert main([
        "experiment-rank", "--development", str(development),
        "--proposals", str(proposals), "--output", str(output), "--k", "1",
    ]) == 0
    assert output.exists()
    response = json.loads(capsys.readouterr().out)
    assert response["recommendation"] == "research_candidate"
    assert response["automatic_promotion"] is False
