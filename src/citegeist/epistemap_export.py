from __future__ import annotations

import json
from pathlib import Path
from typing import Any


GRAPH_POLICY_ID = "citegeist_epistemap_graph_profile_v1"


def build_epistemap_graph_profile(store, *, topic: str | None = None) -> dict[str, Any]:
    entries = _entry_rows(store, topic=topic)
    entry_ids = {int(row["id"]) for row in entries}
    citation_keys = {str(row["citation_key"]) for row in entries}
    nodes = [_entry_node(row) for row in entries]
    edges = _relation_edges(store, entry_ids, citation_keys)
    topic_edges = _topic_edges(store, entry_ids, topic=topic)
    assessments = store.list_confidence_assessments()
    conflicts = _field_conflicts(store, entry_ids)
    return {
        "graph_kind": "citegeist_epistemap_profile",
        "schema_version": "1.0",
        "policy_id": GRAPH_POLICY_ID,
        "topic": topic or "",
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "edges": sorted([*edges, *topic_edges], key=lambda item: item["id"]),
        "confidence_assessments": sorted(assessments, key=lambda item: str(item["assessment_id"])),
        "identity_calibration_rows": store.identity_calibration_rows(),
        "conflicts": conflicts,
        "metadata": {
            "producer": "CiteGeist",
            "legacy_confidence_policy": "legacy scalar fields are retained only as compatibility aliases",
            "non_evidential_topology": [
                "citation edges describe bibliographic topology, not evidential support",
                "topic edges describe bibliography curation, not claim truth",
            ],
        },
    }


def write_epistemap_graph_profile(store, path: str | Path, *, topic: str | None = None) -> dict[str, Any]:
    payload = build_epistemap_graph_profile(store, topic=topic)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _entry_rows(store, *, topic: str | None) -> list[Any]:
    if topic:
        return store.connection.execute(
            """
            SELECT e.*
            FROM entries e
            JOIN entry_topics et ON et.entry_id = e.id
            JOIN topics t ON t.id = et.topic_id
            WHERE t.slug = ?
            ORDER BY e.citation_key
            """,
            (topic,),
        ).fetchall()
    return store.connection.execute("SELECT * FROM entries ORDER BY citation_key").fetchall()


def _entry_node(row) -> dict[str, Any]:
    return {
        "id": f"work::{row['citation_key']}",
        "type": "work",
        "citation_key": row["citation_key"],
        "entry_type": row["entry_type"],
        "title": row["title"] or "",
        "year": row["year"] or "",
        "review_status": row["review_status"],
        "identifiers": {
            key: row[key]
            for key in ("doi", "isbn", "url")
            if row[key]
        },
        "metadata": {
            "journal": row["journal"] or "",
            "booktitle": row["booktitle"] or "",
            "publisher": row["publisher"] or "",
            "keywords": row["keywords"] or "",
        },
    }


def _relation_edges(store, entry_ids: set[int], citation_keys: set[str]) -> list[dict[str, Any]]:
    if not entry_ids:
        return []
    placeholders = ",".join("?" for _ in entry_ids)
    rows = store.connection.execute(
        f"""
        SELECT r.source_entry_id, e.citation_key AS source_key, r.target_citation_key,
               r.relation_type, rp.source_label, rp.confidence, rp.recorded_at
        FROM relations r
        JOIN entries e ON e.id = r.source_entry_id
        LEFT JOIN relation_provenance rp
          ON rp.source_entry_id = r.source_entry_id
         AND rp.target_citation_key = r.target_citation_key
         AND rp.relation_type = r.relation_type
        WHERE r.source_entry_id IN ({placeholders})
        ORDER BY e.citation_key, r.relation_type, r.target_citation_key, rp.recorded_at
        """,
        tuple(sorted(entry_ids)),
    ).fetchall()
    edges = []
    for index, row in enumerate(rows, start=1):
        target_key = str(row["target_citation_key"])
        edges.append(
            {
                "id": f"citation::{row['source_key']}::{row['relation_type']}::{target_key}::{index}",
                "source": f"work::{row['source_key']}",
                "target": f"work::{target_key}",
                "type": str(row["relation_type"]),
                "target_in_export": target_key in citation_keys,
                "provenance": {
                    "source_label": row["source_label"] or "",
                    "recorded_at": row["recorded_at"] or "",
                    "legacy_confidence": row["confidence"],
                },
                "metadata": {
                    "not_evidential_support": True,
                    "not_source_reliability": True,
                },
            }
        )
    return edges


def _topic_edges(store, entry_ids: set[int], *, topic: str | None) -> list[dict[str, Any]]:
    if not entry_ids:
        return []
    placeholders = ",".join("?" for _ in entry_ids)
    params: list[Any] = [*sorted(entry_ids)]
    topic_clause = ""
    if topic:
        topic_clause = "AND t.slug = ?"
        params.append(topic)
    rows = store.connection.execute(
        f"""
        SELECT e.citation_key, t.slug, et.source_label, et.confidence
        FROM entry_topics et
        JOIN entries e ON e.id = et.entry_id
        JOIN topics t ON t.id = et.topic_id
        WHERE et.entry_id IN ({placeholders}) {topic_clause}
        ORDER BY t.slug, e.citation_key
        """,
        tuple(params),
    ).fetchall()
    return [
        {
            "id": f"topic::{row['slug']}::contains::{row['citation_key']}",
            "source": f"topic::{row['slug']}",
            "target": f"work::{row['citation_key']}",
            "type": "topic_membership",
            "provenance": {
                "source_label": row["source_label"],
                "legacy_confidence": row["confidence"],
            },
            "metadata": {
                "not_evidential_support": True,
                "topic_relevance_only": True,
            },
        }
        for row in rows
    ]


def _field_conflicts(store, entry_ids: set[int]) -> list[dict[str, Any]]:
    if not entry_ids:
        return []
    placeholders = ",".join("?" for _ in entry_ids)
    rows = store.connection.execute(
        f"""
        SELECT e.citation_key, fc.field_name, fc.current_value, fc.proposed_value,
               fc.source_type, fc.source_label, fc.status, fc.recorded_at
        FROM field_conflicts fc
        JOIN entries e ON e.id = fc.entry_id
        WHERE fc.entry_id IN ({placeholders})
        ORDER BY e.citation_key, fc.field_name, fc.recorded_at
        """,
        tuple(sorted(entry_ids)),
    ).fetchall()
    return [dict(row) for row in rows]
