import json
import os
import hashlib

import pytest

from citegeist.bibtex import BibEntry
from citegeist.cli import main
from citegeist.discovery_pool import (
    DiscoveryPoolError,
    build_candidate_pool,
    build_judgment_template,
    prepare_rank_pool,
    write_private_json,
)
from citegeist.research_discovery import (
    DiscoveryReport,
    DiscoveryResult,
    DiscoverySourceStatus,
    ResearchBrief,
    _record_results,
)
from citegeist.storage import BibliographyStore


def _report(generated_at="2026-10-17T10:00:00+00:00"):
    return DiscoveryReport(
        brief=ResearchBrief("  ocean  acoustics ", sources=("crossref", "openalex"), per_source_limit=5),
        results=[
            DiscoveryResult(
                BibEntry("article", "RecordA", {"doi": "10.1234/ABC.1", "title": "Ocean acoustics", "abstract": "A result", "url": "https://private.example/?token=secret"}),
                providers=["crossref", "openalex"], provider_ranks={"crossref": 1, "openalex": 2},
            ),
            DiscoveryResult(
                BibEntry("article", "LocalKey", {"title": "Uncertain identity", "year": "2024"}),
                providers=["crossref"], provider_ranks={"crossref": 2},
            ),
        ],
        sources=[
            DiscoverySourceStatus("crossref", "returned", result_count=2),
            DiscoverySourceStatus("openalex", "unknown", result_count=0, error="token=must-not-be-recorded"),
        ],
        outcome="partial",
        generated_at=generated_at,
    )


def test_candidate_pool_is_stable_except_for_retrieval_run_and_omits_raw_errors():
    first = build_candidate_pool(_report())
    second = build_candidate_pool(_report("2026-10-18T10:00:00+00:00"))
    assert first["pool_id"] == second["pool_id"]
    assert first["run_id"] != second["run_id"]
    assert first["candidate_inventory_sha256"] == second["candidate_inventory_sha256"]
    assert first["cases"][0]["candidates"][0]["id"] == "doi:10.1234/abc.1"
    assert first["cases"][0]["candidates"][1]["id"] == "crossref:localkey"
    serialized = json.dumps(first)
    assert "must-not-be-recorded" not in serialized
    assert "private.example" not in serialized
    assert first["source_statuses"][1]["status"] == "unknown"


def test_cross_provider_metadata_conflict_is_preserved_for_review():
    merged = {}
    _record_results(merged, "crossref", [BibEntry("article", "A", {"doi": "10.1234/shared", "title": "First title"})])
    _record_results(merged, "openalex", [BibEntry("article", "B", {"doi": "10.1234/shared", "title": "Other title"})])
    assert len(merged) == 1
    assert merged["doi:10.1234/shared"].field_conflicts == {
        "title": {"crossref": "First title", "openalex": "Other title"}
    }


def _write_pool(tmp_path):
    pool = build_candidate_pool(_report())
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(json.dumps(pool, indent=2), encoding="utf-8")
    return pool_path


def test_judgment_template_binds_exact_pool_bytes_and_requires_complete_labels(tmp_path):
    pool_path = _write_pool(tmp_path)
    template = build_judgment_template(pool_path)
    assert template["pool_sha256"]
    assert template["rubric_version"] == "binary-relevance-v1"
    judgments_path = tmp_path / "judgments.json"
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    with pytest.raises(DiscoveryPoolError, match="every candidate"):
        prepare_rank_pool(pool_path, judgments_path)

    template["judgments"][0]["candidate_judgments"][0]["label"] = "relevant"
    template["judgments"][0]["candidate_judgments"][1]["label"] = "not_relevant"
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    development = prepare_rank_pool(pool_path, judgments_path)
    assert development["split"] == "development"
    assert development["cases"][0]["relevant_ids"] == ["doi:10.1234/abc.1"]
    assert development["cases"][0]["candidates"][0]["provider_ranks"] == {"crossref": 1, "openalex": 2}


def test_label_join_rejects_changed_bytes_unknown_ids_and_duplicate_labels(tmp_path):
    pool_path = _write_pool(tmp_path)
    template = build_judgment_template(pool_path)
    labels = template["judgments"][0]["candidate_judgments"]
    labels[0]["label"] = labels[1]["label"] = "not_relevant"
    judgments_path = tmp_path / "judgments.json"
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    with pool_path.open("a", encoding="utf-8") as stream:
        stream.write(" ")
    with pytest.raises(DiscoveryPoolError, match="exact candidate-pool bytes"):
        prepare_rank_pool(pool_path, judgments_path)

    pool_path.unlink()
    pool_path = _write_pool(tmp_path)
    template = build_judgment_template(pool_path)
    labels = template["judgments"][0]["candidate_judgments"]
    labels[0]["label"] = labels[1]["label"] = "not_relevant"
    labels[1]["candidate_id"] = labels[0]["candidate_id"]
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    with pytest.raises(DiscoveryPoolError, match="duplicate label"):
        prepare_rank_pool(pool_path, judgments_path)

    labels[1]["candidate_id"] = "made-up:id"
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    with pytest.raises(DiscoveryPoolError, match="label IDs do not match"):
        prepare_rank_pool(pool_path, judgments_path)


def test_private_writer_refuses_overwrite_and_uses_owner_only_permissions(tmp_path):
    output = tmp_path / "private" / "artifact.json"
    write_private_json(output, {"private": True})
    assert os.stat(output).st_mode & 0o777 == 0o600
    with pytest.raises(DiscoveryPoolError, match="already exists"):
        write_private_json(output, {"replacement": True})
    assert json.loads(output.read_text(encoding="utf-8")) == {"private": True}


def test_cli_creates_label_template_and_private_development_pool(tmp_path, capsys):
    pool_path = _write_pool(tmp_path)
    judgments_path = tmp_path / "judgments.json"
    dev_path = tmp_path / "dev.json"
    assert main(["label-template", "--pool", str(pool_path), "--output", str(judgments_path)]) == 0
    template = json.loads(judgments_path.read_text(encoding="utf-8"))
    for item in template["judgments"][0]["candidate_judgments"]:
        item["label"] = "not_relevant"
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    assert main(["prepare-rank-pool", "--pool", str(pool_path), "--judgments", str(judgments_path), "--output", str(dev_path)]) == 0
    assert json.loads(dev_path.read_text(encoding="utf-8"))["split"] == "development"
    assert capsys.readouterr().out.count('"automatic_promotion": false') == 2


def test_research_cli_records_pool_without_changing_sqlite(tmp_path, capsys):
    database = tmp_path / "library.sqlite3"
    store = BibliographyStore(database)
    try:
        store.ingest_bibtex("@article{ocean2024, title={Ocean acoustics}, doi={10.1234/ocean.1}}")
    finally:
        store.close()
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    pool_path = tmp_path / "private" / "pool.json"
    assert main([
        "--db", str(database), "research", "ocean acoustics", "--source", "local",
        "--record-pool", str(pool_path),
    ]) == 0
    capsys.readouterr()
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    assert pool["cases"][0]["candidates"][0]["id"] == "doi:10.1234/ocean.1"
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
