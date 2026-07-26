from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3
from typing import Any


STANDARD_DIMENSIONS = {
    "extraction_fidelity",
    "identity_resolution",
    "grounding_strength",
    "source_reliability",
    "evidential_support",
    "reviewer_endorsement",
    "response_correctness",
    "evidence_coverage",
}


@dataclass(slots=True)
class AssessmentMethodRef:
    name: str
    version: str
    policy_id: str = ""


@dataclass(slots=True)
class ConfidenceInterval:
    level: float
    lower: float
    upper: float
    method: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.level <= 1.0:
            raise ValueError(f"interval level must be between 0 and 1: {self.level}")
        if not 0.0 <= self.lower <= 1.0 or not 0.0 <= self.upper <= 1.0:
            raise ValueError("interval bounds must be between 0 and 1")
        if self.lower > self.upper:
            raise ValueError("interval lower must be <= upper")


@dataclass(slots=True)
class ConfidenceAssessment:
    assessment_id: str
    subject_id: str
    dimension: str
    value: float | None
    method: AssessmentMethodRef
    schema_version: str = "1.0"
    band: str = "unknown"
    interval: ConfidenceInterval | None = None
    assessor_id: str = ""
    basis_record_ids: list[str] = field(default_factory=list)
    source_family_ids: list[str] = field(default_factory=list)
    basis_hash: str = ""
    rationale: str = ""
    valid_at: str = ""
    recorded_at: str = ""
    supersedes_assessment_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.dimension not in STANDARD_DIMENSIONS and ":" not in self.dimension:
            raise ValueError(f"unknown confidence dimension: {self.dimension}")
        if self.value is not None and not 0.0 <= self.value <= 1.0:
            raise ValueError(f"assessment value must be between 0 and 1: {self.value}")
        if self.value is None and self.band != "unknown":
            raise ValueError('band must be "unknown" when value is None')
        if not self.recorded_at:
            self.recorded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["method"] = asdict(self.method)
        if self.interval is not None:
            payload["interval"] = asdict(self.interval)
        return {key: value for key, value in payload.items() if value not in ("", None, [], {})}


def band_for_value(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 0.2:
        return "very_low"
    if value < 0.4:
        return "low"
    if value < 0.7:
        return "moderate"
    if value < 0.9:
        return "high"
    return "very_high"


def identity_resolution_assessment(
    *,
    subject_id: str,
    score: float | None,
    source_label: str,
    basis_record_ids: list[str],
) -> ConfidenceAssessment:
    return ConfidenceAssessment(
        assessment_id=f"{subject_id}::identity_resolution::{source_label}",
        subject_id=subject_id,
        dimension="identity_resolution",
        value=score,
        band=band_for_value(score),
        method=AssessmentMethodRef(
            name="citegeist_bibliography_verifier",
            version="1.0",
            policy_id="citegeist_identity_resolution_v1",
        ),
        basis_record_ids=basis_record_ids,
        rationale="Bibliographic match score; not source reliability or claim support.",
    )


MIGRATION_VERSION = "citegeist_confidence_migration_v1"


def migrate_legacy_confidence_assessments(
    store,
    *,
    apply: bool = False,
    backup_path: str | Path | None = None,
) -> dict[str, Any]:
    """Map CiteGeist legacy confidence columns into typed assessments.

    The migration is dry-run by default and idempotent when applied. It maps
    only fields whose semantics are declared in the confidence-overhaul
    roadmap; support-gap priority and query-scoped retrieval scores are not
    migrated as confidence.
    """

    candidates: list[ConfidenceAssessment] = []
    candidates.extend(_field_provenance_assessments(store))
    candidates.extend(_relation_provenance_assessments(store))
    candidates.extend(_topic_membership_assessments(store))
    report = {
        "report_kind": "citegeist_confidence_migration_report",
        "schema_version": "1.0",
        "migration_version": MIGRATION_VERSION,
        "apply": apply,
        "backup_path": str(backup_path) if backup_path is not None else "",
        "candidate_count": len(candidates),
        "assessment_ids": [item.assessment_id for item in candidates],
        "source_rows": [
            item.metadata.get("source_row", {})
            for item in candidates
            if item.metadata.get("source_row")
        ],
        "ambiguous_legacy_fields": [
            {
                "field": "claim_support.needs_support_score",
                "reason": "support-gap priority is not confidence",
            },
            {
                "field": "expansion.relevance_score",
                "reason": "query-scoped retrieval telemetry is not durable confidence",
            },
        ],
    }
    if apply:
        if backup_path is None:
            raise ValueError("apply requires an explicit backup_path")
        create_confidence_migration_backup(store, backup_path)
        try:
            store.connection.execute("BEGIN")
            for assessment in candidates:
                store.upsert_confidence_assessment(assessment, commit=False)
            store.record_confidence_migration_event(
                migration_version=MIGRATION_VERSION,
                backup_path=str(backup_path),
                report=report,
                commit=False,
            )
            store.connection.commit()
        except Exception:
            store.connection.rollback()
            raise
    return report


def create_confidence_migration_backup(store, backup_path: str | Path) -> str:
    if store.path == ":memory:":
        raise ValueError("cannot create a filesystem backup for an in-memory database")
    backup = Path(backup_path)
    backup.parent.mkdir(parents=True, exist_ok=True)
    if backup.exists():
        return str(backup)
    destination = sqlite3.connect(str(backup))
    try:
        store.connection.backup(destination)
    finally:
        destination.close()
    return str(backup)


def restore_confidence_migration_backup(database_path: str | Path, backup_path: str | Path) -> dict[str, Any]:
    database = Path(database_path)
    backup = Path(backup_path)
    if not backup.exists():
        raise FileNotFoundError(str(backup))
    shutil.copy2(backup, database)
    return {
        "report_kind": "citegeist_confidence_restore_report",
        "database_path": str(database),
        "backup_path": str(backup),
        "restored": True,
    }


def _field_provenance_assessments(store) -> list[ConfidenceAssessment]:
    rows = store.connection.execute(
        """
        SELECT fp.id, e.citation_key, fp.field_name, fp.source_label, fp.confidence, fp.recorded_at
        FROM field_provenance fp
        JOIN entries e ON e.id = fp.entry_id
        WHERE fp.confidence IS NOT NULL
        ORDER BY fp.id
        """
    ).fetchall()
    method = AssessmentMethodRef(
        name="citegeist_field_provenance_migration",
        version="1.0",
        policy_id="citegeist_confidence_migration_v1",
    )
    return [
        ConfidenceAssessment(
            assessment_id=f"field_provenance::{row['id']}::extraction_fidelity",
            subject_id=f"work::{row['citation_key']}",
            dimension="extraction_fidelity",
            value=float(row["confidence"]),
            band=band_for_value(float(row["confidence"])),
            method=method,
            basis_record_ids=[f"field_provenance::{row['id']}"],
            rationale=f"Field `{row['field_name']}` migrated from legacy field_provenance confidence.",
            recorded_at=str(row["recorded_at"]),
            metadata={
                "field_name": row["field_name"],
                "source_label": row["source_label"],
                "source_row": {"table": "field_provenance", "id": row["id"]},
                "migration_version": MIGRATION_VERSION,
            },
        )
        for row in rows
    ]


def _relation_provenance_assessments(store) -> list[ConfidenceAssessment]:
    rows = store.connection.execute(
        """
        SELECT rp.id, e.citation_key, rp.target_citation_key, rp.relation_type,
               rp.source_label, rp.confidence, rp.recorded_at
        FROM relation_provenance rp
        JOIN entries e ON e.id = rp.source_entry_id
        WHERE rp.confidence IS NOT NULL
        ORDER BY rp.id
        """
    ).fetchall()
    method = AssessmentMethodRef(
        name="citegeist_relation_provenance_migration",
        version="1.0",
        policy_id="citegeist_confidence_migration_v1",
    )
    return [
        ConfidenceAssessment(
            assessment_id=f"relation_provenance::{row['id']}::grounding_strength",
            subject_id=f"relation::{row['citation_key']}::{row['relation_type']}::{row['target_citation_key']}",
            dimension="grounding_strength",
            value=float(row["confidence"]),
            band=band_for_value(float(row["confidence"])),
            method=method,
            basis_record_ids=[f"relation_provenance::{row['id']}"],
            rationale="Relation provenance confidence migrated as grounding strength, not claim support.",
            recorded_at=str(row["recorded_at"]),
            metadata={
                "source_label": row["source_label"],
                "source_row": {"table": "relation_provenance", "id": row["id"]},
                "migration_version": MIGRATION_VERSION,
            },
        )
        for row in rows
    ]


def _topic_membership_assessments(store) -> list[ConfidenceAssessment]:
    rows = store.connection.execute(
        """
        SELECT e.citation_key, t.slug, et.source_label, et.confidence, et.created_at
        FROM entry_topics et
        JOIN entries e ON e.id = et.entry_id
        JOIN topics t ON t.id = et.topic_id
        WHERE et.confidence IS NOT NULL
        ORDER BY e.citation_key, t.slug
        """
    ).fetchall()
    method = AssessmentMethodRef(
        name="citegeist_topic_membership_migration",
        version="1.0",
        policy_id="citegeist_confidence_migration_v1",
    )
    return [
        ConfidenceAssessment(
            assessment_id=f"topic_membership::{row['citation_key']}::{row['slug']}::topic_relevance",
            subject_id=f"work::{row['citation_key']}",
            dimension="citegeist:topic_relevance",
            value=float(row["confidence"]),
            band=band_for_value(float(row["confidence"])),
            method=method,
            basis_record_ids=[f"topic::{row['slug']}"],
            rationale="Topic membership confidence migrated as CiteGeist topic relevance.",
            recorded_at=str(row["created_at"]),
            metadata={
                "topic_slug": row["slug"],
                "source_label": row["source_label"],
                "source_row": {
                    "table": "entry_topics",
                    "citation_key": row["citation_key"],
                    "topic_slug": row["slug"],
                },
                "migration_version": MIGRATION_VERSION,
            },
        )
        for row in rows
    ]
