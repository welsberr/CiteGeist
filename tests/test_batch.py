from pathlib import Path

from citegeist.batch import BatchBootstrapRunner, load_batch_jobs
from citegeist.cli import main
from citegeist.storage import BibliographyStore


def test_load_batch_jobs_accepts_object_with_jobs(tmp_path: Path):
    path = tmp_path / "jobs.json"
    path.write_text(
        """
{
  "jobs": [
    {"name": "topic-only", "topic": "graph topic"},
    {"name": "seed-only", "seed_bib": "seed.bib"}
  ]
}
""",
        encoding="utf-8",
    )

    jobs = load_batch_jobs(path)

    assert jobs[0]["name"] == "topic-only"
    assert jobs[1]["seed_bib"] == str((tmp_path / "seed.bib").resolve())


def test_batch_runner_executes_multiple_jobs(tmp_path: Path):
    seed_bib = tmp_path / "seed.bib"
    seed_bib.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    jobs = [
        {"name": "seed-job", "seed_bib": str(seed_bib), "expand": False},
        {"name": "topic-job", "topic": "graph topic", "expand": False, "preview": True},
    ]

    runner = BatchBootstrapRunner()
    from citegeist import BibEntry

    runner.bootstrapper.resolver.search_openalex = lambda topic, limit=5: [  # type: ignore[method-assign]
        BibEntry(entry_type="article", citation_key="topic2024graph", fields={"title": "Graph Topic Result"})
    ]
    runner.bootstrapper.resolver.search_crossref = lambda topic, limit=5: []  # type: ignore[method-assign]
    runner.bootstrapper.resolver.search_datacite = lambda topic, limit=5: []  # type: ignore[method-assign]

    store = BibliographyStore()
    try:
        results = runner.run(store, jobs)
        assert [job.job_name for job in results] == ["seed-job", "topic-job"]
        assert results[0].result_count == 1
        assert results[1].results[0].citation_key == "topic2024graph"
        assert store.get_entry("seed2024") is not None
        assert store.get_entry("topic2024graph") is None
    finally:
        store.close()


def test_batch_runner_can_store_topic_phrase_metadata():
    jobs = [
        {
            "name": "topic-job",
            "topic": "graph topic",
            "topic_slug": "graph-methods",
            "topic_name": "Graph Methods",
            "topic_phrase": "graph networks biology",
            "expand": False,
            "preview": False,
        }
    ]

    runner = BatchBootstrapRunner()
    from citegeist import BibEntry

    runner.bootstrapper.resolver.search_openalex = lambda topic, limit=5: [  # type: ignore[method-assign]
        BibEntry(entry_type="article", citation_key="topic2024graph", fields={"title": "Graph Topic Result"})
    ]
    runner.bootstrapper.resolver.search_crossref = lambda topic, limit=5: []  # type: ignore[method-assign]
    runner.bootstrapper.resolver.search_datacite = lambda topic, limit=5: []  # type: ignore[method-assign]

    store = BibliographyStore()
    try:
        runner.run(store, jobs)
        topic = store.get_topic("graph-methods")
        assert topic is not None
        assert topic["name"] == "Graph Methods"
        assert topic["expansion_phrase"] == "graph networks biology"
    finally:
        store.close()


def test_bootstrap_batch_cli_runs_json_jobs(tmp_path: Path):
    seed_bib = tmp_path / "seed.bib"
    seed_bib.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    batch_json = tmp_path / "jobs.json"
    batch_json.write_text(
        f"""
[
  {{"name": "seed-job", "seed_bib": "{seed_bib}", "expand": false}},
  {{"name": "topic-job", "topic": "graph topic", "expand": false, "preview": true}}
]
""",
        encoding="utf-8",
    )

    from unittest.mock import patch

    database = tmp_path / "library.sqlite3"
    with patch("citegeist.cli.BatchBootstrapRunner.run") as mocked_run:
        mocked_run.return_value = []
        exit_code = main(["--db", str(database), "bootstrap-batch", str(batch_json)])

    assert exit_code == 0


def test_batch_runner_passes_new_expansion_settings(tmp_path: Path):
    jobs = [
        {
            "name": "topic-job",
            "topic": "graph topic",
            "expand": True,
            "expansion_mode": "both",
            "expansion_rounds": 3,
            "recent_years": 5,
            "target_recent_entries": 12,
        }
    ]

    runner = BatchBootstrapRunner()
    store = BibliographyStore()
    try:
        captured: dict[str, object] = {}

        def fake_bootstrap(_store, **kwargs):
            captured.update(kwargs)
            return []

        runner.bootstrapper.bootstrap = fake_bootstrap  # type: ignore[method-assign]
        runner.run(store, jobs)

        assert captured["expansion_mode"] == "both"
        assert captured["expansion_rounds"] == 3
        assert captured["recent_years"] == 5
        assert captured["target_recent_entries"] == 12
        assert captured["max_expanded_entries"] is None
    finally:
        store.close()


def test_batch_runner_passes_max_expanded_entries(tmp_path: Path):
    jobs = [
        {
            "name": "topic-job",
            "topic": "graph topic",
            "expand": True,
            "expansion_mode": "cites",
            "max_expanded_entries": 25,
        }
    ]

    runner = BatchBootstrapRunner()
    store = BibliographyStore()
    try:
        captured: dict[str, object] = {}

        def fake_bootstrap(_store, **kwargs):
            captured.update(kwargs)
            return []

        runner.bootstrapper.bootstrap = fake_bootstrap  # type: ignore[method-assign]
        runner.run(store, jobs)

        assert captured["max_expanded_entries"] == 25
    finally:
        store.close()


def test_batch_runner_passes_max_expand_seconds(tmp_path: Path):
    jobs = [
        {
            "name": "topic-job",
            "topic": "graph topic",
            "expand": True,
            "expansion_mode": "legacy",
            "max_expand_seconds": 12.5,
        }
    ]

    runner = BatchBootstrapRunner()
    store = BibliographyStore()
    try:
        captured: dict[str, object] = {}

        def fake_bootstrap(_store, **kwargs):
            captured.update(kwargs)
            return []

        runner.bootstrapper.bootstrap = fake_bootstrap  # type: ignore[method-assign]
        runner.run(store, jobs)

        assert captured["max_expand_seconds"] == 12.5
    finally:
        store.close()
