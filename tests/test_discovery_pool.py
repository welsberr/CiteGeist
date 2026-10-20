import json
import os
import hashlib

import pytest

from citegeist.bibtex import BibEntry
from citegeist.cli import main
from citegeist.discovery_pool import (
    DiscoveryPoolError,
    assemble_candidate_pools,
    adjudicate_reviews,
    build_candidate_pool,
    build_judgment_template,
    compare_reviews,
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


def test_pool_assembly_requires_exact_topic_family_split_assignments(tmp_path):
    first_path = tmp_path / "first.json"
    first_path.write_text(json.dumps(build_candidate_pool(_report())), encoding="utf-8")
    second_report = _report()
    second_report.brief = ResearchBrief("bird navigation methods", sources=("crossref", "openalex"), per_source_limit=5)
    second_path = tmp_path / "second.json"
    second_path.write_text(json.dumps(build_candidate_pool(second_report)), encoding="utf-8")
    first_case = json.loads(first_path.read_text())["cases"][0]["case_id"]
    second_case = json.loads(second_path.read_text())["cases"][0]["case_id"]
    manifest_path = tmp_path / "splits.json"
    manifest = {
        "schema_version": 1,
        "rubric_version": "research-relevance-v2",
        "assignments": [
            {"case_id": first_case, "split": "development", "topic_family": "navigation"},
            {"case_id": second_case, "split": "holdout", "topic_family": "navigation"},
        ],
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DiscoveryPoolError, match="crosses data splits"):
        assemble_candidate_pools([first_path, second_path], manifest_path)

    manifest["assignments"][1]["topic_family"] = "bird migration"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assembled = assemble_candidate_pools([first_path, second_path], manifest_path)
    assert {case["split"] for case in assembled["cases"]} == {"development", "holdout"}
    assert len(assembled["source_pool_sha256s"]) == 2


def _write_pool(tmp_path, *, split="development"):
    raw_path = tmp_path / "raw-pool.json"
    raw_path.write_text(json.dumps(build_candidate_pool(_report()), indent=2), encoding="utf-8")
    raw_pool = json.loads(raw_path.read_text(encoding="utf-8"))
    split_path = tmp_path / "split-manifest.json"
    split_path.write_text(json.dumps({
        "schema_version": 1,
        "rubric_version": "research-relevance-v2",
        "assignments": [{
            "case_id": case["case_id"], "split": split, "topic_family": "marine acoustics",
        } for case in raw_pool["cases"]],
    }), encoding="utf-8")
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(json.dumps(assemble_candidate_pools([raw_path], split_path), indent=2), encoding="utf-8")
    return pool_path


def test_judgment_template_binds_exact_pool_bytes_and_requires_complete_labels(tmp_path):
    pool_path = _write_pool(tmp_path)
    template = build_judgment_template(pool_path, split="development", reviewer_id="reviewer-a")
    assert template["pool_sha256"]
    assert template["rubric_version"] == "research-relevance-v2"
    judgments_path = tmp_path / "judgments.json"
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    with pytest.raises(DiscoveryPoolError, match="every candidate"):
        prepare_rank_pool(pool_path, judgments_path, split="development")

    template["judgments"][0]["candidate_judgments"][0]["relevance"] = "useful"
    template["judgments"][0]["candidate_judgments"][1]["relevance"] = "not_relevant"
    template["judgments"][0]["candidate_judgments"][0]["identity_correct"] = "yes"
    template["judgments"][0]["candidate_judgments"][0]["version_match"] = "yes"
    template["judgments"][0]["candidate_judgments"][0]["source_authority"] = "strong"
    template["judgments"][0]["candidate_judgments"][0]["evidence_support"] = "direct"
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    development = prepare_rank_pool(pool_path, judgments_path, split="development")
    assert development["split"] == "development"
    assert development["cases"][0]["relevant_ids"] == ["doi:10.1234/abc.1"]
    assert development["cases"][0]["candidates"][0]["provider_ranks"] == {"crossref": 1, "openalex": 2}
    assert development["cases"][0]["quality_judgments"]["doi:10.1234/abc.1"]["source_authority"] == "strong"


def test_label_join_rejects_changed_bytes_unknown_ids_and_duplicate_labels(tmp_path):
    pool_path = _write_pool(tmp_path)
    template = build_judgment_template(pool_path, split="development", reviewer_id="reviewer-a")
    labels = template["judgments"][0]["candidate_judgments"]
    labels[0]["relevance"] = labels[1]["relevance"] = "not_relevant"
    judgments_path = tmp_path / "judgments.json"
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    with pool_path.open("a", encoding="utf-8") as stream:
        stream.write(" ")
    with pytest.raises(DiscoveryPoolError, match="exact candidate-pool bytes"):
        prepare_rank_pool(pool_path, judgments_path, split="development")

    pool_path.unlink()
    pool_path = _write_pool(tmp_path)
    template = build_judgment_template(pool_path, split="development", reviewer_id="reviewer-a")
    labels = template["judgments"][0]["candidate_judgments"]
    labels[0]["relevance"] = labels[1]["relevance"] = "not_relevant"
    labels[1]["candidate_id"] = labels[0]["candidate_id"]
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    with pytest.raises(DiscoveryPoolError, match="duplicate label"):
        prepare_rank_pool(pool_path, judgments_path, split="development")

    labels[1]["candidate_id"] = "made-up:id"
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    with pytest.raises(DiscoveryPoolError, match="label IDs do not match"):
        prepare_rank_pool(pool_path, judgments_path, split="development")


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
    assert main(["label-template", "--pool", str(pool_path), "--split", "development", "--reviewer-id", "reviewer-a", "--output", str(judgments_path)]) == 0
    template = json.loads(judgments_path.read_text(encoding="utf-8"))
    for item in template["judgments"][0]["candidate_judgments"]:
        item["relevance"] = "not_relevant"
    judgments_path.write_text(json.dumps(template), encoding="utf-8")
    assert main(["prepare-rank-pool", "--pool", str(pool_path), "--judgments", str(judgments_path), "--split", "development", "--output", str(dev_path)]) == 0
    assert json.loads(dev_path.read_text(encoding="utf-8"))["split"] == "development"
    assert capsys.readouterr().out.count('"automatic_promotion": false') == 2


def test_independent_reviews_require_explicit_adjudication_and_preserve_disagreement(tmp_path):
    pool_path = _write_pool(tmp_path)
    first = build_judgment_template(pool_path, split="development", reviewer_id="reviewer-a")
    second = build_judgment_template(pool_path, split="development", reviewer_id="reviewer-b")
    for item in first["judgments"][0]["candidate_judgments"]:
        item.update(relevance="not_relevant", identity_correct="yes", version_match="yes", source_authority="adequate", evidence_support="direct")
    for item in second["judgments"][0]["candidate_judgments"]:
        item.update(relevance="not_relevant", identity_correct="yes", version_match="yes", source_authority="adequate", evidence_support="direct")
    first["judgments"][0]["candidate_judgments"][0]["relevance"] = "useful"
    second["judgments"][0]["candidate_judgments"][0]["relevance"] = "essential"
    first_path, second_path = tmp_path / "first.json", tmp_path / "second.json"
    first_path.write_text(json.dumps(first), encoding="utf-8")
    second_path.write_text(json.dumps(second), encoding="utf-8")

    comparison = compare_reviews(pool_path, first_path, second_path)
    assert comparison["agreement_count"] == 9
    assert comparison["disagreement_count"] == 1
    assert comparison["disagreements"][0]["first"] == "useful"
    adjudication_path = tmp_path / "adjudication.json"
    adjudication_path.write_text(json.dumps(comparison), encoding="utf-8")
    with pytest.raises(DiscoveryPoolError, match="explicitly resolve"):
        adjudicate_reviews(pool_path, first_path, second_path, adjudication_path, adjudicator_id="adjudicator")

    comparison["decisions"][0]["decision"] = "essential"
    adjudication_path.write_text(json.dumps(comparison), encoding="utf-8")
    reviewed = adjudicate_reviews(pool_path, first_path, second_path, adjudication_path, adjudicator_id="adjudicator")
    reviewed_path = tmp_path / "reviewed.json"
    reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
    prepared = prepare_rank_pool(pool_path, reviewed_path, split="development")
    assert prepared["cases"][0]["relevant_ids"] == ["doi:10.1234/abc.1"]
    provenance = prepared["review_provenance"]
    assert provenance["adjudicator_id"] == "adjudicator"
    assert provenance["disagreements"][0]["second"] == "essential"


def test_double_review_rejects_same_reviewer_and_incomplete_coverage(tmp_path):
    pool_path = _write_pool(tmp_path)
    first = build_judgment_template(pool_path, split="development", reviewer_id="same")
    second = build_judgment_template(pool_path, split="development", reviewer_id="same")
    first_path, second_path = tmp_path / "first.json", tmp_path / "second.json"
    first_path.write_text(json.dumps(first), encoding="utf-8")
    second_path.write_text(json.dumps(second), encoding="utf-8")
    with pytest.raises(DiscoveryPoolError, match="distinct reviewer_id"):
        compare_reviews(pool_path, first_path, second_path)


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
    assert pool["local_corpus_snapshot"]["entry_count"] == 1
    assert pool["local_corpus_snapshot"]["sha256"]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
