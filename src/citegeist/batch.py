from __future__ import annotations

import json
from dataclasses import dataclass
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

    def run(self, store: BibliographyStore, jobs: list[dict]) -> list[BatchJobResult]:
        results: list[BatchJobResult] = []
        for index, job in enumerate(jobs, start=1):
            seed_bib = job.get("seed_bib")
            topic = job.get("topic")
            topic_limit = int(job.get("topic_limit", 5))
            topic_commit_limit = job.get("topic_commit_limit")
            expand = bool(job.get("expand", True))
            review_status = str(job.get("status", "draft"))
            preview = bool(job.get("preview", False))
            name = str(job.get("name") or f"job_{index}")
            topic_slug = job.get("topic_slug")
            topic_name = job.get("topic_name")
            topic_phrase = job.get("topic_phrase")
            expansion_mode = str(job.get("expansion_mode", "legacy"))
            expansion_rounds = int(job.get("expansion_rounds", 1))
            recent_years = job.get("recent_years")
            target_recent_entries = job.get("target_recent_entries")
            max_expanded_entries = job.get("max_expanded_entries")
            max_expand_seconds = job.get("max_expand_seconds")

            seed_bibtex = None
            if seed_bib:
                seed_bibtex = Path(seed_bib).read_text(encoding="utf-8")

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
            results.append(BatchJobResult(name, len(job_results), job_results))
        return results
