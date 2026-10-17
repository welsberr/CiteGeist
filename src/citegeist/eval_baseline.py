"""Deterministic, offline evaluation of recorded discovery runs.

This module deliberately has no dependency on CiteGeist's database, source
adapters, or model clients. It scores a recorded ordered candidate list against
a versioned JSON benchmark and writes a provenance receipt. It never changes the
input files or a production corpus and makes no network requests.

Run with::

    python -m citegeist.eval_baseline --benchmark PATH --run PATH --output PATH

The run file format is illustrated by ``tests/fixtures/discovery-run-v1.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
OUTCOMES = {"complete", "partial", "empty_corpus", "no_matches", "provider_failure", "inconclusive"}


class EvaluationInputError(ValueError):
    """Raised when a benchmark or recorded run does not match the v1 contract."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> tuple[Any, bytes]:
    raw = path.read_bytes()
    try:
        return json.loads(raw), raw
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationInputError(f"{path}: invalid UTF-8 JSON: {exc}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvaluationInputError(message)


def _validate_benchmark(benchmark: Any) -> dict[str, Any]:
    _require(isinstance(benchmark, dict), "benchmark must be a JSON object")
    _require(benchmark.get("schema_version") == SCHEMA_VERSION, "unsupported benchmark schema_version")
    _require(isinstance(benchmark.get("benchmark_id"), str) and benchmark["benchmark_id"], "benchmark_id is required")
    cases = benchmark.get("cases")
    _require(isinstance(cases, list) and cases, "benchmark cases must be a nonempty list")
    case_ids: set[str] = set()
    for case in cases:
        _require(isinstance(case, dict), "each benchmark case must be an object")
        case_id = case.get("case_id")
        _require(isinstance(case_id, str) and case_id, "each benchmark case needs a case_id")
        _require(case_id not in case_ids, f"duplicate benchmark case_id: {case_id}")
        case_ids.add(case_id)
        _require(isinstance(case.get("query"), str) and case["query"].strip(), f"{case_id}: query is required")
        relevant = case.get("relevant_ids")
        _require(isinstance(relevant, list) and all(isinstance(item, str) and item for item in relevant), f"{case_id}: relevant_ids must be strings")
        _require(len(set(relevant)) == len(relevant), f"{case_id}: relevant_ids must be unique")
        source_types = case.get("source_types", [])
        _require(isinstance(source_types, list) and all(isinstance(item, str) and item for item in source_types), f"{case_id}: source_types must be strings")
    return benchmark


def _validate_run(run: Any, benchmark: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(run, dict), "run must be a JSON object")
    _require(run.get("schema_version") == SCHEMA_VERSION, "unsupported run schema_version")
    _require(isinstance(run.get("run_id"), str) and run["run_id"], "run_id is required")
    corpus = run.get("corpus")
    _require(isinstance(corpus, dict) and isinstance(corpus.get("id"), str) and corpus["id"], "corpus.id is required")
    _require(isinstance(corpus.get("snapshot"), str) and corpus["snapshot"], "corpus.snapshot is required")
    cases = run.get("cases")
    _require(isinstance(cases, list), "run cases must be a list")
    expected_ids = {case["case_id"] for case in benchmark["cases"]}
    run_by_id: dict[str, dict[str, Any]] = {}
    for case in cases:
        _require(isinstance(case, dict), "each run case must be an object")
        case_id = case.get("case_id")
        _require(isinstance(case_id, str) and case_id, "each run case needs a case_id")
        _require(case_id in expected_ids, f"run includes unknown case_id: {case_id}")
        _require(case_id not in run_by_id, f"duplicate run case_id: {case_id}")
        outcome = case.get("outcome")
        _require(isinstance(outcome, str), f"{case_id}: outcome is required")
        _require(outcome in OUTCOMES, f"{case_id}: invalid outcome")
        candidates = case.get("candidates")
        _require(isinstance(candidates, list), f"{case_id}: candidates must be a list")
        candidate_ids: set[str] = set()
        for candidate in candidates:
            _require(isinstance(candidate, dict) and isinstance(candidate.get("id"), str) and candidate["id"], f"{case_id}: each candidate needs an id")
            _require(candidate["id"] not in candidate_ids, f"{case_id}: candidate IDs must be unique")
            candidate_ids.add(candidate["id"])
        providers = case.get("providers", [])
        _require(isinstance(providers, list), f"{case_id}: providers must be a list")
        if outcome == "empty_corpus":
            _require(not candidates, f"{case_id}: empty_corpus outcome requires no candidates")
            _require(corpus.get("entry_count") == 0, f"{case_id}: empty_corpus requires corpus.entry_count == 0")
        if outcome == "no_matches":
            _require(corpus.get("entry_count") != 0, f"{case_id}: no_matches requires a nonempty or unknown corpus")
        if outcome == "provider_failure":
            _require(not candidates, f"{case_id}: provider_failure outcome requires no candidates")
        run_by_id[case_id] = case
    _require(set(run_by_id) == expected_ids, "run must include exactly one outcome for every benchmark case")
    return {"by_id": run_by_id}


def _score_case(
    relevant_ids: list[str],
    candidates: list[dict[str, Any]],
    k: int,
    source_types: list[str] | None = None,
) -> dict[str, Any]:
    ranked = [candidate["id"] for candidate in candidates]
    relevant = set(relevant_ids)
    hits = [index for index, candidate_id in enumerate(ranked[:k], start=1) if candidate_id in relevant]
    precision = len(hits) / k if k else 0.0
    recall = len(hits) / len(relevant) if relevant else None
    reciprocal_rank = (1.0 / next((index for index, candidate_id in enumerate(ranked, start=1) if candidate_id in relevant), math.inf)) if relevant else None
    dcg = sum(1.0 / math.log2(rank + 1) for rank in hits)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    ndcg = dcg / idcg if idcg else None
    result = {
        "candidate_ids": ranked,
        "candidate_count": len(ranked),
        "relevant_found_at_k": len(hits),
        "precision_at_k": round(precision, 6),
        "recall_at_k": round(recall, 6) if recall is not None else None,
        "reciprocal_rank": round(reciprocal_rank, 6) if reciprocal_rank is not None else None,
        "ndcg_at_k": round(ndcg, 6) if ndcg is not None else None,
    }
    if source_types:
        found_types = sorted({
            str(candidate["source_type"])
            for candidate in candidates[:k]
            if isinstance(candidate.get("source_type"), str) and candidate["source_type"]
        })
        requested = set(source_types)
        result["requested_source_types"] = sorted(requested)
        result["found_source_types_at_k"] = found_types
        result["source_type_coverage_at_k"] = round(len(requested.intersection(found_types)) / len(requested), 6)
    return result


def _git_bytes(repo: Path, *args: str) -> bytes | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout


def _repository_provenance(repo: Path) -> dict[str, Any]:
    revision_bytes = _git_bytes(repo, "rev-parse", "HEAD")
    diff = _git_bytes(repo, "diff", "--binary", "HEAD", "--")
    status = _git_bytes(repo, "status", "--porcelain=v1", "--untracked-files=all")
    return {
        "revision": revision_bytes.decode("ascii", errors="replace").strip() if revision_bytes is not None else None,
        # Git's textual diff does not include untracked file contents; retain a
        # separate status digest so receipts do not imply otherwise.
        "tracked_worktree_diff_sha256": _sha256_bytes(diff) if diff is not None else None,
        "worktree_status_sha256": _sha256_bytes(status) if status is not None else None,
    }


def evaluate(benchmark: Any, run: Any, *, benchmark_bytes: bytes, run_bytes: bytes, repo: Path, k: int = 5) -> dict[str, Any]:
    """Create a stable JSON-serializable receipt for a recorded offline run."""
    _require(isinstance(k, int) and 1 <= k <= 100, "k must be an integer from 1 to 100")
    benchmark = _validate_benchmark(benchmark)
    validated_run = _validate_run(run, benchmark)
    by_id = validated_run["by_id"]
    outcomes: dict[str, int] = {}
    results = []
    for benchmark_case in benchmark["cases"]:
        recorded_case = by_id[benchmark_case["case_id"]]
        outcome = recorded_case["outcome"]
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        result = {
            "case_id": benchmark_case["case_id"],
            "outcome": outcome,
            "query": benchmark_case["query"],
            "providers": recorded_case.get("providers", []),
        }
        for field in ("filters", "timings_ms", "errors"):
            if field in recorded_case:
                result[field] = recorded_case[field]
        if outcome in {"complete", "partial", "no_matches"}:
            result["metrics"] = _score_case(
                benchmark_case["relevant_ids"],
                recorded_case["candidates"],
                k,
                benchmark_case.get("source_types", []),
            )
        else:
            result["metrics"] = None
        results.append(result)
    return {
        "receipt_schema_version": SCHEMA_VERSION,
        "benchmark_id": benchmark["benchmark_id"],
        "run_id": run["run_id"],
        "cutoff_k": k,
        "input_sha256": {
            "benchmark": _sha256_bytes(benchmark_bytes),
            "run": _sha256_bytes(run_bytes),
        },
        "provenance": {
            "corpus": run["corpus"],
            "run": run.get("provenance", {}),
            "repository": _repository_provenance(repo),
            "network_used_by_evaluator": False,
            "production_database_modified_by_evaluator": False,
        },
        "outcome_counts": dict(sorted(outcomes.items())),
        "results": results,
        "limitations": [
            "This receipt scores only the supplied recorded rankings; it does not run retrieval.",
            "Relevant IDs are benchmark labels, not a complete census of relevant literature.",
            "Queries and judgments are a small pilot and do not support broad quality claims.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score a recorded CiteGeist discovery run offline and write a provenance receipt.")
    parser.add_argument("--benchmark", required=True, type=Path, help="Versioned benchmark JSON")
    parser.add_argument("--run", required=True, type=Path, help="Recorded discovery run JSON")
    parser.add_argument("--output", required=True, type=Path, help="Receipt JSON output path")
    parser.add_argument("--k", type=int, default=5, help="Ranking cutoff (1-100; default: 5)")
    args = parser.parse_args(argv)
    try:
        if args.output.suffix.lower() != ".json":
            raise EvaluationInputError("receipt output must use a .json suffix")
        output_resolved = args.output.resolve()
        if output_resolved in {args.benchmark.resolve(), args.run.resolve()}:
            raise EvaluationInputError("receipt output must not overwrite the benchmark or run input")
        if args.output.exists():
            with args.output.open("rb") as existing:
                is_sqlite = existing.read(16) == b"SQLite format 3\x00"
            if is_sqlite:
                raise EvaluationInputError("refusing to overwrite a SQLite database with a receipt")
            raise EvaluationInputError("receipt output already exists; choose a new path to preserve prior evidence")
        benchmark, benchmark_bytes = _load_json(args.benchmark)
        run, run_bytes = _load_json(args.run)
        receipt = evaluate(
            benchmark,
            run,
            benchmark_bytes=benchmark_bytes,
            run_bytes=run_bytes,
            repo=Path(__file__).resolve().parents[2],
            k=args.k,
        )
        args.output.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    except (EvaluationInputError, OSError) as exc:
        print(f"citegeist-eval: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote offline evaluation receipt: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
