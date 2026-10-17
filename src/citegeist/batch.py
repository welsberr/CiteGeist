from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .bootstrap import BootstrapResult, Bootstrapper
from .storage import BibliographyStore


@dataclass(slots=True)
class BatchJobResult:
    job_name: str
    result_count: int
    results: list[BootstrapResult]


def load_batch_jobs(path: str | Path) -> list[dict]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        jobs = payload.get("jobs", [])
    else:
        jobs = payload
    if not isinstance(jobs, list):
        raise ValueError("Batch JSON must be a list of jobs or an object with a 'jobs' list")
    normalized_jobs: list[dict] = []
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("Each batch job must be an object")
        normalized = dict(job)
        seed_bib = normalized.get("seed_bib")
        if isinstance(seed_bib, str) and seed_bib:
            seed_path = Path(seed_bib)
            if not seed_path.is_absolute():
                normalized["seed_bib"] = str((path.parent / seed_path).resolve())
        normalized_jobs.append(normalized)
    return normalized_jobs


class BatchBootstrapRunner:
    def __init__(self, bootstrapper: Bootstrapper | None = None) -> None:
        self.bootstrapper = bootstrapper or Bootstrapper()

    def run(
        self,
        store: BibliographyStore,
        jobs: list[dict],
        receipt_path: str | Path | None = None,
        resume: bool = False,
    ) -> list[BatchJobResult]:
        """Run jobs, optionally checkpointing recoverable per-job outcomes.

        A completed job is skipped on resume only when the input and selected
        database path match the receipt. A job interrupted after its database
        commit but before its receipt update may run again; bootstrap writes are
        designed to be repeatable, so recovery is at-least-once.
        """
        receipt = Path(receipt_path) if receipt_path is not None else None
        if resume and receipt is None:
            raise ValueError("--resume requires a receipt path")
        if len({str(job.get("name") or f"job_{i}") for i, job in enumerate(jobs, 1)}) != len(jobs):
            raise ValueError("Batch job names must be unique when receipts are enabled")
        input_hash = _jobs_hash(jobs)
        state: dict[str, object] = {
            "schema_version": 1,
            "input_sha256": input_hash,
            "database_path": str(Path(store.path).resolve()) if store.path != ":memory:" else ":memory:",
            "jobs": {},
        }
        if receipt and resume:
            if not receipt.exists():
                raise ValueError(f"Batch receipt does not exist: {receipt}")
            previous = json.loads(receipt.read_text(encoding="utf-8"))
            if not isinstance(previous, dict):
                raise ValueError("Batch receipt must contain a JSON object")
            if previous.get("schema_version") != 1 or previous.get("input_sha256") != input_hash:
                raise ValueError("Batch receipt does not match the current jobs or receipt schema")
            if previous.get("database_path") != state["database_path"]:
                raise ValueError("Batch receipt was created for a different database path")
            if not isinstance(previous.get("jobs"), dict):
                raise ValueError("Batch receipt jobs must be a JSON object")
            state = previous
        elif receipt and receipt.exists():
            raise ValueError(f"Batch receipt already exists; pass --resume to continue: {receipt}")

        if receipt:
            _write_receipt(receipt, state)
        results: list[BatchJobResult] = []
        recorded_jobs = state["jobs"]
        assert isinstance(recorded_jobs, dict)
        for index, job in enumerate(jobs, start=1):
            name = str(job.get("name") or f"job_{index}")
            job_input_hash = _job_hash(job)
            previous_job = recorded_jobs.get(name)
            if isinstance(previous_job, dict) and previous_job.get("input_sha256") != job_input_hash:
                raise ValueError(f"Batch receipt input hash does not match job {name!r}")
            if isinstance(previous_job, dict) and previous_job.get("status") == "completed":
                results_payload = previous_job.get("results", [])
                if not isinstance(results_payload, list) or not all(isinstance(item, dict) for item in results_payload):
                    raise ValueError(f"Batch receipt results for job {name!r} must be a list of objects")
                restored = [BootstrapResult(**item) for item in results_payload]
                results.append(BatchJobResult(name, len(restored), restored))
                continue
            recorded_jobs[name] = {"status": "running", "input_sha256": job_input_hash}
            if receipt:
                _write_receipt(receipt, state)
            try:
                seed_bib = job.get("seed_bib")
                topic = job.get("topic")
                topic_limit = int(job.get("topic_limit", 5))
                topic_commit_limit = job.get("topic_commit_limit")
                expand = bool(job.get("expand", True))
                review_status = str(job.get("status", "draft"))
                preview = bool(job.get("preview", False))
                topic_slug = job.get("topic_slug")
                topic_name = job.get("topic_name")
                topic_phrase = job.get("topic_phrase")
                expansion_mode = str(job.get("expansion_mode", "legacy"))
                expansion_rounds = int(job.get("expansion_rounds", 1))
                recent_years = job.get("recent_years")
                target_recent_entries = job.get("target_recent_entries")
                max_expanded_entries = job.get("max_expanded_entries")
                max_expand_seconds = job.get("max_expand_seconds")
                seed_bibtex = Path(seed_bib).read_text(encoding="utf-8") if seed_bib else None
                job_results = self.bootstrapper.bootstrap(
                    store,
                    seed_bibtex=seed_bibtex,
                    topic=topic,
                    topic_limit=topic_limit,
                    topic_commit_limit=int(topic_commit_limit) if topic_commit_limit is not None else None,
                    expand=expand,
                    review_status=review_status,
                    preview_only=preview,
                    topic_slug=str(topic_slug) if topic_slug else None,
                    topic_name=str(topic_name) if topic_name else None,
                    topic_phrase=str(topic_phrase) if topic_phrase else None,
                    expansion_mode=expansion_mode,
                    expansion_rounds=expansion_rounds,
                    recent_years=int(recent_years) if recent_years is not None else None,
                    target_recent_entries=int(target_recent_entries) if target_recent_entries is not None else None,
                    max_expanded_entries=int(max_expanded_entries) if max_expanded_entries is not None else None,
                    max_expand_seconds=float(max_expand_seconds) if max_expand_seconds is not None else None,
                )
            except Exception as exc:
                recorded_jobs[name] = {
                    "status": "failed",
                    "input_sha256": job_input_hash,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                if receipt:
                    _write_receipt(receipt, state)
                raise
            results.append(BatchJobResult(name, len(job_results), job_results))
            run_meta = dict(self.bootstrapper.last_run_meta)
            stop_reason = str(run_meta.get("stop_reason", "completed"))
            status = "partial" if stop_reason not in {"completed", "frontier_exhausted"} else "completed"
            recorded_jobs[name] = {
                "status": status,
                "input_sha256": job_input_hash,
                "run_meta": run_meta,
                "results": [asdict(item) for item in job_results],
            }
            if receipt:
                _write_receipt(receipt, state)
        return results


def _job_hash(job: dict) -> str:
    normalized = dict(job)
    seed_bib = normalized.get("seed_bib")
    if isinstance(seed_bib, str) and seed_bib:
        seed_path = Path(seed_bib)
        normalized["seed_bib_sha256"] = hashlib.sha256(seed_path.read_bytes()).hexdigest()
        normalized.pop("seed_bib")
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _jobs_hash(jobs: list[dict]) -> str:
    return hashlib.sha256(json.dumps([_job_hash(job) for job in jobs], separators=(",", ":")).encode()).hexdigest()


def _write_receipt(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
