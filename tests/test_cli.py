from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from citegeist.cli import main
from citegeist.examples.talkorigins import (
    TalkOriginsBatchExport,
    TalkOriginsCorrectionResult,
    TalkOriginsDuplicateCluster,
    TalkOriginsEnrichmentResult,
    TalkOriginsIngestReport,
    TalkOriginsReviewExport,
    TalkOriginsTopicPhraseSuggestion,
    TalkOriginsValidationReport,
)


SAMPLE_BIB = """
@article{smith2024graphs,
  author = {Smith, Jane and Doe, Alex},
  title = {Graph-first bibliography augmentation},
  year = {2024},
  abstract = {We study citation graphs for literature discovery.},
  references = {miller2023search}
}

@inproceedings{miller2023search,
  author = {Miller, Sam},
  title = {Semantic search for research corpora},
  year = {2023},
  abstract = {Dense retrieval improves recall for academic search.}
}
"""


def run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    database = tmp_path / "library.sqlite3"
    env = {"PYTHONPATH": "src"}
    return subprocess.run(
        [sys.executable, "-m", "citegeist", "--db", str(database), *args],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_ingest_show_search_and_export(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(SAMPLE_BIB, encoding="utf-8")

    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0
    assert "smith2024graphs" in ingest.stdout

    show = run_cli(tmp_path, "show", "smith2024graphs")
    assert show.returncode == 0
    payload = json.loads(show.stdout)
    assert payload["citation_key"] == "smith2024graphs"

    search = run_cli(tmp_path, "search", "semantic")
    assert search.returncode == 0
    assert "miller2023search" in search.stdout

    export_path = tmp_path / "exported.bib"
    export_result = run_cli(tmp_path, "export", "--output", str(export_path))
    assert export_result.returncode == 0
    exported = export_path.read_text(encoding="utf-8")
    assert "@article{smith2024graphs," in exported


def test_cli_export_skips_stub_entries_by_default_but_can_include_them(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@misc{stubdoi,
  title = {Referenced work 6},
  doi = {10.1200/JCO.2002.04.117},
  url = {https://doi.org/10.1200/JCO.2002.04.117}
}

@article{realentry,
  author = {Smith, Jane},
  title = {Real Entry},
  year = {2024},
  doi = {10.1000/real}
}
""",
        encoding="utf-8",
    )

    assert run_cli(tmp_path, "ingest", str(bib_path)).returncode == 0

    default_export = run_cli(tmp_path, "export")
    assert default_export.returncode == 0
    assert "@article{realentry," in default_export.stdout
    assert "@misc{stubdoi," not in default_export.stdout

    explicit_export = run_cli(tmp_path, "export", "stubdoi")
    assert explicit_export.returncode == 0
    assert "@misc{stubdoi," in explicit_export.stdout

    include_export = run_cli(tmp_path, "export", "--include-stubs")
    assert include_export.returncode == 0
    assert "@misc{stubdoi," in include_export.stdout


def test_cli_provenance_and_status_updates(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(SAMPLE_BIB, encoding="utf-8")

    ingest = run_cli(
        tmp_path,
        "ingest",
        "--status",
        "draft",
        "--source-label",
        "tests/input.bib",
        str(bib_path),
    )
    assert ingest.returncode == 0

    show = run_cli(tmp_path, "show", "--provenance", "smith2024graphs")
    assert show.returncode == 0
    payload = json.loads(show.stdout)
    assert payload["review_status"] == "draft"
    assert payload["field_provenance"][0]["source_label"] == "tests/input.bib"

    status = run_cli(tmp_path, "set-status", "smith2024graphs", "reviewed")
    assert status.returncode == 0
    assert "reviewed" in status.stdout


def test_cli_resolve_updates_entry(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{smith2024graphs,
  author = {Smith, Jane},
  title = {Graph-first bibliography augmentation},
  year = {2024},
  doi = {10.1000/example-doi}
}
""",
        encoding="utf-8",
    )

    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.bibtex import BibEntry
    from citegeist.resolve import Resolution

    database = tmp_path / "library.sqlite3"

    with patch("citegeist.cli.MetadataResolver.resolve_entry") as mocked_resolve:
        mocked_resolve.return_value = Resolution(
            entry=BibEntry(
                entry_type="article",
                citation_key="resolvedkey",
                fields={
                    "author": "Smith, Jane",
                    "title": "Resolved Graph-first bibliography augmentation",
                    "year": "2024",
                    "doi": "10.1000/example-doi",
                    "journal": "Journal of Graph Studies",
                },
            ),
            source_type="resolver",
            source_label="crossref:doi:10.1000/example-doi",
        )
        exit_code = main(
            [
                "--db",
                str(database),
                "resolve",
                "smith2024graphs",
            ]
        )

    assert exit_code == 0
    show = run_cli(tmp_path, "show", "--conflicts", "smith2024graphs")
    assert show.returncode == 0
    payload = json.loads(show.stdout)
    assert payload["field_conflicts"][0]["field_name"] == "title"


def test_cli_resolve_stubs_preview_lists_doi_stub_candidates(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@misc{stubdoi,
  title = {Referenced work 6},
  doi = {10.1200/JCO.2002.04.117},
  url = {https://doi.org/10.1200/JCO.2002.04.117}
}

@article{complete,
  author = {Smith, Jane},
  title = {Complete Record},
  year = {2024},
  doi = {10.1000/complete}
}
""",
        encoding="utf-8",
    )
    assert run_cli(tmp_path, "ingest", str(bib_path)).returncode == 0

    result = run_cli(tmp_path, "resolve-stubs", "--doi-only", "--preview", "--limit", "10")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert [row["citation_key"] for row in payload] == ["stubdoi"]
    assert payload[0]["title"] == "Referenced work 6"


def test_cli_resolve_stubs_enriches_matching_candidates(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@misc{stubdoi,
  title = {Referenced work 6},
  doi = {10.1200/JCO.2002.04.117},
  url = {https://doi.org/10.1200/JCO.2002.04.117}
}
""",
        encoding="utf-8",
    )
    assert run_cli(tmp_path, "ingest", str(bib_path)).returncode == 0

    from citegeist.bibtex import BibEntry
    from citegeist.resolve import Resolution

    database = tmp_path / "library.sqlite3"

    with patch("citegeist.cli.MetadataResolver.resolve_entry") as mocked_resolve:
        mocked_resolve.return_value = Resolution(
            entry=BibEntry(
                entry_type="article",
                citation_key="resolvedkey",
                fields={
                    "author": "Doe, Alex",
                    "title": "Resolved Work",
                    "year": "2002",
                    "doi": "10.1200/JCO.2002.04.117",
                    "journal": "Journal of Clinical Oncology",
                },
            ),
            source_type="resolver",
            source_label="crossref:doi:10.1200/JCO.2002.04.117",
        )
        exit_code = main(
            [
                "--db",
                str(database),
                "resolve-stubs",
                "--doi-only",
                "--limit",
                "10",
            ]
        )

    assert exit_code == 0
    show = run_cli(tmp_path, "show", "stubdoi")
    payload = json.loads(show.stdout)
    assert payload["title"] == "Resolved Work"
    assert payload["review_status"] == "enriched"


def test_cli_resolve_conflicts_updates_status(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{smith2024graphs,
  author = {Smith, Jane},
  title = {Graph-first bibliography augmentation},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.record_conflicts(
            "smith2024graphs",
            [
                {
                    "field_name": "title",
                    "current_value": "Graph-first bibliography augmentation",
                    "proposed_value": "Resolved title",
                }
            ],
            source_type="resolver",
            source_label="openalex:search:Graph-first bibliography augmentation",
        )
    finally:
        store.close()

    result = run_cli(tmp_path, "resolve-conflicts", "smith2024graphs", "title", "accepted")
    assert result.returncode == 0
    assert "accepted" in result.stdout


def test_cli_apply_conflict_updates_entry_value(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{smith2024graphs,
  author = {Smith, Jane},
  title = {Graph-first bibliography augmentation},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.record_conflicts(
            "smith2024graphs",
            [
                {
                    "field_name": "title",
                    "current_value": "Graph-first bibliography augmentation",
                    "proposed_value": "Resolved Graph-first bibliography augmentation",
                }
            ],
            source_type="resolver",
            source_label="openalex:search:Graph-first bibliography augmentation",
        )
    finally:
        store.close()

    result = run_cli(tmp_path, "apply-conflict", "smith2024graphs", "title")
    assert result.returncode == 0
    assert "applied" in result.stdout

    show = run_cli(tmp_path, "show", "smith2024graphs")
    payload = json.loads(show.stdout)
    assert payload["title"] == "Resolved Graph-first bibliography augmentation"


def test_cli_discover_oai_outputs_identity_and_sets():
    from unittest.mock import patch
    from citegeist.harvest import OaiMetadataFormat, OaiSet

    with patch("citegeist.cli.OaiPmhHarvester.identify") as mocked_identify, patch(
        "citegeist.cli.OaiPmhHarvester.list_sets"
    ) as mocked_sets, patch("citegeist.cli.OaiPmhHarvester.list_metadata_formats") as mocked_formats:
        mocked_identify.return_value = {
            "repositoryName": "Example Repository",
            "granularity": "YYYY-MM-DD",
        }
        mocked_formats.return_value = [
            OaiMetadataFormat(
                metadata_prefix="oai_dc",
                schema="http://www.openarchives.org/OAI/2.0/oai_dc.xsd",
                metadata_namespace="http://www.openarchives.org/OAI/2.0/oai_dc/",
            )
        ]
        mocked_sets.return_value = [
            OaiSet(set_spec="theses", set_name="Theses", set_description="Graduate theses")
        ]
        exit_code = main(["discover-oai", "https://example.edu/oai"])

    assert exit_code == 0


def test_cli_bootstrap_preview_mode(tmp_path):
    from unittest.mock import patch

    database = tmp_path / "library.sqlite3"
    with patch("citegeist.cli.Bootstrapper.bootstrap") as mocked_bootstrap:
        mocked_bootstrap.return_value = []
        exit_code = main(
            [
                "--db",
                str(database),
                "bootstrap",
                "--topic",
                "graph topic",
                "--preview",
                "--topic-commit-limit",
                "2",
            ]
        )

    assert exit_code == 0
    _, kwargs = mocked_bootstrap.call_args
    assert kwargs["preview_only"] is True
    assert kwargs["topic_commit_limit"] == 2


def test_cli_bootstrap_accepts_stored_topic_metadata(tmp_path):
    from unittest.mock import patch

    database = tmp_path / "library.sqlite3"
    with patch("citegeist.cli.Bootstrapper.bootstrap") as mocked_bootstrap:
        mocked_bootstrap.return_value = []
        exit_code = main(
            [
                "--db",
                str(database),
                "bootstrap",
                "--topic",
                "graph topic",
                "--topic-slug",
                "graph-methods",
                "--topic-name",
                "Graph Methods",
                "--store-topic-phrase",
                "graph networks biology",
            ]
        )

    assert exit_code == 0
    _, kwargs = mocked_bootstrap.call_args
    assert kwargs["topic_slug"] == "graph-methods"
    assert kwargs["topic_name"] == "Graph Methods"
    assert kwargs["topic_phrase"] == "graph networks biology"


def test_cli_scrape_talkorigins_accepts_output_dir(tmp_path):
    from unittest.mock import patch

    database = tmp_path / "library.sqlite3"
    with patch("citegeist.cli.TalkOriginsScraper.scrape_to_directory") as mocked_scrape:
        mocked_scrape.return_value = TalkOriginsBatchExport(
            base_url="https://www.talkorigins.org/origins/biblio/",
            output_dir=str(tmp_path),
            topic_count=1,
            entry_count=2,
            jobs_path=str(tmp_path / "jobs.json"),
            manifest_path=str(tmp_path / "manifest.json"),
            seed_sets=[],
        )
        exit_code = main(
            [
                "--db",
                str(database),
                "example-talkorigins-scrape",
                str(tmp_path / "talkorigins-out"),
                "--limit-topics",
                "3",
                "--limit-entries-per-topic",
                "10",
                "--no-resume",
                "--no-expand",
            ]
        )

    assert exit_code == 0


def test_cli_validate_talkorigins_accepts_manifest(tmp_path):
    from unittest.mock import patch

    manifest = tmp_path / "talkorigins_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    with patch("citegeist.cli.TalkOriginsScraper.validate_export") as mocked_validate:
        mocked_validate.return_value = TalkOriginsValidationReport(
            manifest_path=str(manifest),
            topic_count=1,
            entry_count=2,
            parsed_ratio=1.0,
            missing_author_count=0,
            missing_title_count=0,
            missing_year_count=0,
            suspicious_entry_type_count=0,
            suspicious_examples=[],
            duplicate_cluster_count=0,
            duplicate_entry_count=0,
            duplicate_examples=[],
        )
        exit_code = main(["example-talkorigins-validate", str(manifest)])

    assert exit_code == 0


def test_cli_suggest_talkorigins_phrases_writes_output(tmp_path):
    from unittest.mock import patch

    manifest = tmp_path / "talkorigins_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    output = tmp_path / "phrases.json"
    with patch("citegeist.cli.TalkOriginsScraper.suggest_topic_phrases") as mocked_suggest:
        mocked_suggest.return_value = [
            TalkOriginsTopicPhraseSuggestion(
                slug="abiogenesis",
                topic="Abiogenesis",
                entry_count=2,
                suggested_phrase="Abiogenesis prebiotic chemistry ribozyme",
                keywords=["prebiotic", "chemistry", "ribozyme"],
                review_required=True,
                review_reasons=["small_topic"],
            )
        ]
        exit_code = main(
            [
                "example-talkorigins-suggest-phrases",
                str(manifest),
                "--topic",
                "abiogenesis",
                "--output",
                str(output),
            ]
        )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[0]["slug"] == "abiogenesis"


def test_cli_duplicates_talkorigins_accepts_manifest(tmp_path):
    from unittest.mock import patch

    manifest = tmp_path / "talkorigins_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    with patch("citegeist.cli.TalkOriginsScraper.inspect_duplicate_clusters") as mocked_duplicates:
        mocked_duplicates.return_value = [
            TalkOriginsDuplicateCluster(
                key="smith|1999|duplicate paper",
                count=2,
                items=[
                    {
                        "citation_key": "dup1",
                        "title": "Duplicate Paper",
                        "author": "Smith, Jane",
                        "year": "1999",
                        "seed_bib": "a.bib",
                        "topic": "Abiogenesis",
                        "topic_slug": "abiogenesis",
                    }
                ],
                canonical={
                    "citation_key": "dup1",
                    "entry_type": "article",
                    "field_count": 3,
                    "fields": {"title": "Duplicate Paper"},
                    "weak_reasons": [],
                },
            )
        ]
        exit_code = main(
            [
                "example-talkorigins-duplicates",
                str(manifest),
                "--topic",
                "abiogenesis",
                "--match",
                "duplicate",
                "--preview",
                "--weak-only",
            ]
        )

    assert exit_code == 0


def test_cli_ingest_talkorigins_accepts_manifest(tmp_path):
    from unittest.mock import patch

    database = tmp_path / "library.sqlite3"
    manifest = tmp_path / "talkorigins_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    with patch("citegeist.cli.TalkOriginsScraper.ingest_export") as mocked_ingest:
        mocked_ingest.return_value = TalkOriginsIngestReport(
            manifest_path=str(manifest),
            topic_count=1,
            raw_entry_count=2,
            stored_entry_count=1,
            duplicate_cluster_count=1,
            duplicate_entry_count=2,
            canonicalized_count=1,
        )
        exit_code = main(["--db", str(database), "example-talkorigins-ingest", str(manifest)])

    assert exit_code == 0


def test_cli_enrich_talkorigins_accepts_manifest(tmp_path):
    from unittest.mock import patch

    database = tmp_path / "library.sqlite3"
    manifest = tmp_path / "talkorigins_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    with patch("citegeist.cli.TalkOriginsScraper.enrich_weak_canonicals") as mocked_enrich:
        mocked_enrich.return_value = [
            TalkOriginsEnrichmentResult(
                key="smith|1999|duplicate paper",
                citation_key="dup1",
                weak_reasons_before=["missing:doi"],
                resolved=True,
                applied=False,
                source_label="crossref:search:Duplicate Paper",
                weak_reasons_after=[],
                conflicts=[],
                error="",
            )
        ]
        exit_code = main(
            [
                "--db",
                str(database),
                "example-talkorigins-enrich",
                str(manifest),
                "--limit",
                "5",
                "--apply",
                "--allow-unsafe-search-matches",
            ]
        )

    assert exit_code == 0


def test_cli_review_talkorigins_writes_output(tmp_path):
    from unittest.mock import patch

    database = tmp_path / "library.sqlite3"
    manifest = tmp_path / "talkorigins_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    output = tmp_path / "review.json"
    with patch("citegeist.cli.TalkOriginsScraper.build_review_export") as mocked_review:
        mocked_review.return_value = TalkOriginsReviewExport(
            manifest_path=str(manifest),
            item_count=1,
            items=[{"key": "smith|1999|duplicate paper", "canonical": {}, "enrichment": {}}],
        )
        exit_code = main(
            [
                "--db",
                str(database),
                "example-talkorigins-review",
                str(manifest),
                "--output",
                str(output),
            ]
        )

    assert exit_code == 0
    assert output.exists()


def test_cli_apply_talkorigins_corrections_accepts_files(tmp_path):
    from unittest.mock import patch

    database = tmp_path / "library.sqlite3"
    manifest = tmp_path / "talkorigins_manifest.json"
    corrections = tmp_path / "corrections.json"
    manifest.write_text("{}", encoding="utf-8")
    corrections.write_text('{"corrections": []}', encoding="utf-8")
    with patch("citegeist.cli.TalkOriginsScraper.apply_review_corrections") as mocked_apply:
        mocked_apply.return_value = [
            TalkOriginsCorrectionResult(
                key="smith|1999|duplicate paper",
                citation_key="dup1",
                applied=True,
                error="",
            )
        ]
        exit_code = main(
            [
                "--db",
                str(database),
                "example-talkorigins-apply-corrections",
                str(manifest),
                str(corrections),
            ]
        )

    assert exit_code == 0


def test_cli_topics_and_topic_entries(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        )
        store.connection.commit()
    finally:
        store.close()

    topics = run_cli(tmp_path, "topics")
    assert topics.returncode == 0
    topics_payload = json.loads(topics.stdout)
    assert topics_payload[0]["slug"] == "graph-methods"

    topic_entries = run_cli(tmp_path, "topic-entries", "graph-methods")
    assert topic_entries.returncode == 0
    topic_payload = json.loads(topic_entries.stdout)
    assert topic_payload["topic"]["slug"] == "graph-methods"
    assert topic_payload["entries"][0]["citation_key"] == "seed2024"


def test_cli_can_set_topic_phrase(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        )
        store.connection.commit()
    finally:
        store.close()

    result = run_cli(tmp_path, "set-topic-phrase", "graph-methods", "graph networks biology")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["expansion_phrase"] == "graph networks biology"


def test_cli_can_apply_topic_phrases_from_json(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        )
        store.connection.commit()
    finally:
        store.close()

    phrases_path = tmp_path / "phrases.json"
    phrases_path.write_text(
        json.dumps(
            [
                {
                    "slug": "graph-methods",
                    "suggested_phrase": "graph networks biology",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "apply-topic-phrases", str(phrases_path))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload[0]["applied"] is True

    check = run_cli(tmp_path, "topics")
    topics_payload = json.loads(check.stdout)
    assert topics_payload[0]["expansion_phrase"] == "graph networks biology"


def test_cli_can_stage_topic_phrases_from_json(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        )
        store.connection.commit()
    finally:
        store.close()

    phrases_path = tmp_path / "phrases.json"
    phrases_path.write_text(
        json.dumps(
            [
                {
                    "slug": "graph-methods",
                    "suggested_phrase": "graph networks biology",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "stage-topic-phrases", str(phrases_path))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload[0]["staged"] is True
    assert payload[0]["phrase_review_status"] == "pending"

    check = run_cli(tmp_path, "topics")
    topics_payload = json.loads(check.stdout)
    assert topics_payload[0]["suggested_phrase"] == "graph networks biology"
    assert topics_payload[0]["expansion_phrase"] is None
    assert topics_payload[0]["phrase_review_status"] == "pending"


def test_cli_can_review_topic_phrase(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        )
        store.stage_topic_phrase_suggestion("graph-methods", "graph networks biology")
    finally:
        store.close()

    result = run_cli(
        tmp_path,
        "review-topic-phrase",
        "graph-methods",
        "accepted",
        "--notes",
        "curated and approved",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["suggested_phrase"] is None
    assert payload["expansion_phrase"] == "graph networks biology"
    assert payload["phrase_review_status"] == "accepted"
    assert payload["phrase_review_notes"] == "curated and approved"


def test_cli_topics_can_filter_by_phrase_review_status(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        )
        store.ensure_topic("abiogenesis", "Abiogenesis")
        store.stage_topic_phrase_suggestion("graph-methods", "graph networks biology")
        store.stage_topic_phrase_suggestion("abiogenesis", "abiogenesis life origin")
        store.review_topic_phrase_suggestion("abiogenesis", "accepted")
    finally:
        store.close()

    result = run_cli(tmp_path, "topics", "--phrase-review-status", "pending")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert [topic["slug"] for topic in payload] == ["graph-methods"]


def test_cli_can_list_topic_phrase_reviews(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        )
        store.ensure_topic("abiogenesis", "Abiogenesis")
        store.stage_topic_phrase_suggestion("graph-methods", "graph networks biology")
        store.stage_topic_phrase_suggestion("abiogenesis", "abiogenesis life origin")
        store.review_topic_phrase_suggestion("abiogenesis", "accepted")
    finally:
        store.close()

    result = run_cli(tmp_path, "topic-phrase-reviews", "--phrase-review-status", "pending")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert [review["slug"] for review in payload] == ["graph-methods"]
    assert payload[0]["suggested_phrase"] == "graph networks biology"
    assert payload[0]["phrase_review_status"] == "pending"


def test_cli_can_review_topic_phrases_in_bulk(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        )
        store.ensure_topic("abiogenesis", "Abiogenesis")
        store.stage_topic_phrase_suggestion("graph-methods", "graph networks biology")
        store.stage_topic_phrase_suggestion("abiogenesis", "abiogenesis life origin")
    finally:
        store.close()

    review_path = tmp_path / "phrase-review.json"
    review_path.write_text(
        json.dumps(
            [
                {
                    "slug": "graph-methods",
                    "status": "accepted",
                    "review_notes": "good phrase",
                },
                {
                    "slug": "abiogenesis",
                    "status": "rejected",
                    "review_notes": "too sparse",
                },
            ]
        ),
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "review-topic-phrases", str(review_path))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload[0]["reviewed"] is True
    assert payload[1]["reviewed"] is True

    pending_result = run_cli(tmp_path, "topic-phrase-reviews", "--phrase-review-status", "pending")
    assert pending_result.returncode == 0
    assert json.loads(pending_result.stdout) == []

    rejected_result = run_cli(tmp_path, "topic-phrase-reviews", "--phrase-review-status", "rejected")
    assert rejected_result.returncode == 0
    rejected_payload = json.loads(rejected_result.stdout)
    assert [review["slug"] for review in rejected_payload] == ["abiogenesis"]

    topics_result = run_cli(tmp_path, "topics", "--phrase-review-status", "accepted")
    assert topics_result.returncode == 0
    topics_payload = json.loads(topics_result.stdout)
    assert [topic["slug"] for topic in topics_payload] == ["graph-methods"]


def test_cli_can_export_topic_phrase_review_template(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        )
        store.stage_topic_phrase_suggestion("graph-methods", "graph networks biology")
    finally:
        store.close()

    output_path = tmp_path / "topic-phrase-review.json"
    result = run_cli(
        tmp_path,
        "export-topic-phrase-reviews",
        "--output",
        str(output_path),
    )
    assert result.returncode == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert [item["slug"] for item in payload] == ["graph-methods"]
    assert payload[0]["current_expansion_phrase"] is None
    assert payload[0]["suggested_phrase"] == "graph networks biology"
    assert payload[0]["current_status"] == "pending"
    assert payload[0]["status"] == ""
    assert payload[0]["phrase"] == "graph networks biology"


def test_cli_export_topic(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.add_entry_topic(
            "seed2024",
            topic_slug="graph-methods",
            topic_name="Graph Methods",
            source_type="talkorigins",
            source_url="https://example.org/topics/graph-methods",
            source_label="topic-seed",
        )
        store.connection.commit()
    finally:
        store.close()

    export_path = tmp_path / "graph-methods.bib"
    result = run_cli(tmp_path, "export-topic", "graph-methods", "--output", str(export_path))
    assert result.returncode == 0
    exported = export_path.read_text(encoding="utf-8")
    assert "@article{seed2024," in exported


def test_cli_export_topic_skips_stub_entries_by_default(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@misc{stubdoi,
  title = {Referenced work 6},
  doi = {10.1200/JCO.2002.04.117},
  url = {https://doi.org/10.1200/JCO.2002.04.117}
}

@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024}
}
""",
        encoding="utf-8",
    )
    assert run_cli(tmp_path, "ingest", str(bib_path)).returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        for citation_key in ("stubdoi", "seed2024"):
            store.add_entry_topic(
                citation_key,
                topic_slug="graph-methods",
                topic_name="Graph Methods",
                source_label="topic-seed",
            )
        store.connection.commit()
    finally:
        store.close()

    default_export = run_cli(tmp_path, "export-topic", "graph-methods")
    assert default_export.returncode == 0
    assert "@article{seed2024," in default_export.stdout
    assert "@misc{stubdoi," not in default_export.stdout

    include_export = run_cli(tmp_path, "export-topic", "graph-methods", "--include-stubs")
    assert include_export.returncode == 0
    assert "@misc{stubdoi," in include_export.stdout


def test_cli_search_can_filter_by_topic(tmp_path: Path):
    bib_path = tmp_path / "input.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Graph Methods for Biology},
  year = {2024},
  abstract = {A graph methods paper.}
}

@article{other2023,
  author = {Other, Bob},
  title = {Graph Methods for Chemistry},
  year = {2023},
  abstract = {Another graph methods paper.}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.storage import BibliographyStore

    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.add_entry_topic(
            "seed2024",
            topic_slug="biology",
            topic_name="Biology",
            source_type="talkorigins",
            source_url="https://example.org/topics/biology",
            source_label="topic-seed",
        )
        store.add_entry_topic(
            "other2023",
            topic_slug="chemistry",
            topic_name="Chemistry",
            source_type="talkorigins",
            source_url="https://example.org/topics/chemistry",
            source_label="topic-seed",
        )
        store.connection.commit()
    finally:
        store.close()

    search = run_cli(tmp_path, "search", "graph", "--topic", "biology")
    assert search.returncode == 0
    assert "seed2024" in search.stdout
    assert "other2023" not in search.stdout


def test_cli_graph_outputs_missing_targets(tmp_path: Path):
    bib_path = tmp_path / "graph.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  references = {known2023, missing2022}
}

@article{known2023,
  author = {Known, Bob},
  title = {Known Paper},
  year = {2023}
}
""",
        encoding="utf-8",
    )

    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    graph = run_cli(tmp_path, "graph", "seed2024", "--missing-only")
    assert graph.returncode == 0
    payload = json.loads(graph.stdout)
    assert len(payload) == 1
    assert payload[0]["target_citation_key"] == "missing2022"
    assert payload[0]["target_exists"] is False


def test_cli_graph_can_render_dot_output(tmp_path: Path):
    bib_path = tmp_path / "graph.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  references = {known2023, missing2022}
}

@article{known2023,
  author = {Known, Bob},
  title = {Known Paper},
  year = {2023}
}
""",
        encoding="utf-8",
    )

    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    graph = run_cli(tmp_path, "graph", "seed2024", "--format", "dot")
    assert graph.returncode == 0
    assert "digraph citegeist {" in graph.stdout
    assert '"seed2024" [label="seed2024\\\\nSeed Paper\\\\n[draft]"' in graph.stdout
    assert '"seed2024" -> "known2023" [label="cites d=1"]' in graph.stdout
    assert '"seed2024" -> "missing2022" [label="cites d=1"]' in graph.stdout


def test_cli_graph_can_write_dot_output_to_file(tmp_path: Path):
    bib_path = tmp_path / "graph.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  references = {known2023}
}

@article{known2023,
  author = {Known, Bob},
  title = {Known Paper},
  year = {2023}
}
""",
        encoding="utf-8",
    )

    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    output_path = tmp_path / "graph.dot"
    graph = run_cli(tmp_path, "graph", "seed2024", "--format", "dot", "--output", str(output_path))
    assert graph.returncode == 0
    assert graph.stdout == ""
    rendered = output_path.read_text(encoding="utf-8")
    assert "digraph citegeist {" in rendered
    assert '"seed2024" -> "known2023" [label="cites d=1"]' in rendered


def test_cli_graph_can_render_json_graph_output(tmp_path: Path):
    bib_path = tmp_path / "graph.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  references = {known2023, missing2022}
}

@article{known2023,
  author = {Known, Bob},
  title = {Known Paper},
  year = {2023}
}
""",
        encoding="utf-8",
    )

    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    graph = run_cli(tmp_path, "graph", "seed2024", "--format", "json-graph")
    assert graph.returncode == 0
    payload = json.loads(graph.stdout)
    assert [node["id"] for node in payload["nodes"]] == ["known2023", "missing2022", "seed2024"]
    assert payload["nodes"][2]["is_seed"] is True
    assert payload["edges"][0]["source"] == "seed2024"
    assert payload["edges"][0]["target"] == "known2023"
    assert payload["edges"][1]["target_exists"] is False


def test_cli_graph_can_write_json_graph_output_to_file(tmp_path: Path):
    bib_path = tmp_path / "graph.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  references = {known2023}
}

@article{known2023,
  author = {Known, Bob},
  title = {Known Paper},
  year = {2023}
}
""",
        encoding="utf-8",
    )

    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    output_path = tmp_path / "graph.json"
    graph = run_cli(tmp_path, "graph", "seed2024", "--format", "json-graph", "--output", str(output_path))
    assert graph.returncode == 0
    assert graph.stdout == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert [edge["target"] for edge in payload["edges"]] == ["known2023"]


def test_cli_graph_view_renders_html_from_json_graph(tmp_path: Path):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "seed2024",
                        "label": "seed2024",
                        "title": "Seed Paper",
                        "review_status": "draft",
                        "target_exists": True,
                        "is_seed": True,
                    },
                    {
                        "id": "known2023",
                        "label": "known2023",
                        "title": "Known Paper",
                        "review_status": "reviewed",
                        "target_exists": True,
                        "is_seed": False,
                    },
                ],
                "edges": [
                    {
                        "id": "edge-1",
                        "source": "seed2024",
                        "target": "known2023",
                        "relation_type": "cites",
                        "depth": 1,
                        "target_exists": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "graph.html"
    result = run_cli(
        tmp_path,
        "graph-view",
        str(graph_path),
        "--output",
        str(output_path),
        "--title",
        "Graph Demo",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    html = output_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "<title>Graph Demo</title>" in html
    assert '"seed2024"' in html
    assert '"known2023"' in html


def test_cli_expand_with_mocked_crossref(tmp_path: Path):
    bib_path = tmp_path / "expand.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  doi = {10.1000/seed-doi}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.expand import ExpansionResult

    with patch("citegeist.cli.CrossrefExpander.expand_entry_references") as mocked_expand:
        mocked_expand.return_value = [
            ExpansionResult(
                source_citation_key="seed2024",
                discovered_citation_key="doi101000exampleref",
                created_entry=True,
                relation_type="cites",
                source_label="crossref:references:10.1000/seed-doi",
            )
        ]
        database = tmp_path / "library.sqlite3"
        exit_code = main(["--db", str(database), "expand", "seed2024"])

    assert exit_code == 0


def test_cli_expand_with_mocked_openalex(tmp_path: Path):
    bib_path = tmp_path / "expand-openalex.bib"
    bib_path.write_text(
        """
@article{seed2024,
  author = {Seed, Alice},
  title = {Seed Paper},
  year = {2024},
  doi = {10.1000/seed-doi}
}
""",
        encoding="utf-8",
    )
    ingest = run_cli(tmp_path, "ingest", str(bib_path))
    assert ingest.returncode == 0

    from citegeist.expand import ExpansionResult

    with patch("citegeist.cli.OpenAlexExpander.expand_entry") as mocked_expand:
        mocked_expand.return_value = [
            ExpansionResult(
                source_citation_key="seed2024",
                discovered_citation_key="openalexw12345",
                created_entry=True,
                relation_type="cites",
                source_label="openalex:cites:WSEED",
            )
        ]
        database = tmp_path / "library.sqlite3"
        exit_code = main(
            ["--db", str(database), "expand", "seed2024", "--source", "openalex", "--relation", "cites"]
        )

    assert exit_code == 0


def test_cli_expand_topic_with_mocked_expander(tmp_path: Path):
    from citegeist.expand import TopicExpansionResult

    with patch("citegeist.cli.TopicExpander.expand_topic") as mocked_expand:
        mocked_expand.return_value = [
            TopicExpansionResult(
                topic_slug="abiogenesis",
                source_citation_key="seed2024",
                discovered_citation_key="discovered1",
                discovered_title="Abiogenesis origin chemistry",
                created_entry=True,
                relation_type="cites",
                source_label="openalex:cites:seed2024",
                relevance_score=0.67,
                meets_relevance_threshold=True,
                assigned_to_topic=True,
            )
        ]
        database = tmp_path / "library.sqlite3"
        exit_code = main(
            [
                "--db",
                str(database),
                "expand-topic",
                "abiogenesis",
                "--topic-phrase",
                "abiogenesis origin chemistry",
                "--seed-key",
                "seed2024",
                "--min-relevance",
                "0.3",
                "--preview",
            ]
        )

    assert exit_code == 0
    _, kwargs = mocked_expand.call_args
    assert kwargs["preview_only"] is True
