from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bibtex import render_bibtex
from .storage import BibliographyStore


def export_okf_bundle(
    store: BibliographyStore,
    out_dir: str | Path,
    *,
    topic_slug: str | None = None,
    citation_keys: list[str] | None = None,
    include_stubs: bool = False,
) -> dict[str, Any]:
    if topic_slug and citation_keys:
        raise ValueError("topic_slug and citation_keys are mutually exclusive")

    topic: dict[str, object] | None = None
    if topic_slug:
        topic = store.get_topic(topic_slug)
        if topic is None:
            raise KeyError(f"Topic not found: {topic_slug}")
        selected_keys = [str(row["citation_key"]) for row in store.list_topic_entries(topic_slug, limit=100000)]
    elif citation_keys is not None:
        selected_keys = citation_keys
    else:
        selected_keys = [str(row["citation_key"]) for row in store.list_entries(limit=100000)]

    work_entries = []
    for citation_key in selected_keys:
        entry = store.get_bib_entry(citation_key)
        if entry is None:
            continue
        if not include_stubs and store._is_export_stub(entry):
            continue
        work_entries.append(entry)

    target = Path(out_dir)
    works_dir = target / "works"
    topics_dir = target / "topics"
    target.mkdir(parents=True, exist_ok=True)
    works_dir.mkdir(parents=True, exist_ok=True)
    if topic is not None:
        topics_dir.mkdir(parents=True, exist_ok=True)

    exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    work_paths: dict[str, str] = {}
    for entry in work_entries:
        work_paths[entry.citation_key] = f"works/{_safe_filename(entry.citation_key)}.md"

    for entry in work_entries:
        page = _render_work_page(store, entry.citation_key, work_paths, exported_at)
        (target / work_paths[entry.citation_key]).write_text(page, encoding="utf-8")

    bibliography_text = render_bibtex(work_entries).strip()
    bibliography_path = target / "bibliography.bib"
    bibliography_path.write_text(bibliography_text + ("\n" if bibliography_text else ""), encoding="utf-8")

    topic_path = None
    if topic is not None:
        topic_path = f"topics/{_safe_filename(str(topic['slug']))}.md"
        (target / topic_path).write_text(_render_topic_page(topic, work_entries, work_paths, exported_at), encoding="utf-8")

    manifest = {
        "bundle_kind": "citegeist_okf_bundle",
        "okf_profile": "citegeist.work.topic.v1",
        "exported_at": exported_at,
        "topic": topic,
        "include_stubs": include_stubs,
        "work_count": len(work_entries),
        "citation_keys": [entry.citation_key for entry in work_entries],
        "paths": {
            "index": "index.md",
            "log": "log.md",
            "bibliography": "bibliography.bib",
            "topic": topic_path,
            "works": work_paths,
        },
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (target / "index.md").write_text(_render_index(topic, work_entries, work_paths, exported_at), encoding="utf-8")
    (target / "log.md").write_text(_render_log(exported_at, topic, work_entries), encoding="utf-8")

    return {
        "bundle_path": str(target / "manifest.json"),
        "index_path": str(target / "index.md"),
        "bibliography_path": str(bibliography_path),
        "work_count": len(work_entries),
        "citation_keys": [entry.citation_key for entry in work_entries],
    }


def _render_work_page(
    store: BibliographyStore,
    citation_key: str,
    work_paths: dict[str, str],
    exported_at: str,
) -> str:
    entry = store.get_bib_entry(citation_key)
    details = store.get_entry(citation_key)
    if entry is None or details is None:
        raise KeyError(f"Entry not found: {citation_key}")

    title = entry.fields.get("title") or citation_key
    authors = _split_people(entry.fields.get("author", ""))
    editors = _split_people(entry.fields.get("editor", ""))
    topics = details.get("topics") or []
    relations = {
        relation_type: store.get_relations(citation_key, relation_type)
        for relation_type in ("cites", "cited_by", "crossref")
    }
    provenance = store.get_field_provenance(citation_key)
    relation_provenance = store.get_relation_provenance(citation_key)
    conflicts = store.get_field_conflicts(citation_key)

    frontmatter = _frontmatter(
        {
            "okf_type": "citegeist.work",
            "citation_key": citation_key,
            "entry_type": entry.entry_type,
            "review_status": details.get("review_status"),
            "title": title,
            "year": entry.fields.get("year"),
            "doi": entry.fields.get("doi"),
            "url": entry.fields.get("url"),
            "authors": authors,
            "editors": editors,
            "topic_slugs": [str(topic["slug"]) for topic in topics if topic.get("slug")],
            "exported_at": exported_at,
        }
    )

    lines = [frontmatter, f"# {title}", ""]
    lines.extend(_metadata_lines(entry.fields))
    if entry.fields.get("abstract"):
        lines.extend(["", "## Abstract", "", str(entry.fields["abstract"]).strip()])
    if topics:
        lines.extend(["", "## Topics", ""])
        for topic in topics:
            lines.append(f"- {topic.get('name') or topic.get('slug')} (`{topic.get('slug')}`)")
    lines.extend(["", "## Citation Graph", ""])
    for relation_type, targets in relations.items():
        if not targets:
            continue
        lines.append(f"### {relation_type}")
        for target in targets:
            target_path = work_paths.get(target)
            if target_path:
                lines.append(f"- [{target}]({_relative_link(work_paths[citation_key], target_path)})")
            else:
                lines.append(f"- `{target}`")
        lines.append("")
    if not any(relations.values()):
        lines.append("No citation relations recorded.")

    lines.extend(["", "## Provenance", ""])
    lines.extend(_table(provenance, ["field_name", "source_type", "source_label", "operation", "confidence", "recorded_at"]))
    if relation_provenance:
        lines.extend(["", "### Relation Provenance", ""])
        lines.extend(
            _table(
                relation_provenance,
                ["target_citation_key", "relation_type", "source_type", "source_label", "confidence", "recorded_at"],
            )
        )
    if conflicts:
        lines.extend(["", "## Field Conflicts", ""])
        lines.extend(_table(conflicts, ["field_name", "current_value", "proposed_value", "source_label", "status", "recorded_at"]))

    lines.extend(["", "## BibTeX", "", "```bibtex", render_bibtex([entry]).strip(), "```", ""])
    return "\n".join(lines)


def _render_topic_page(
    topic: dict[str, object],
    entries: list[Any],
    work_paths: dict[str, str],
    exported_at: str,
) -> str:
    frontmatter = _frontmatter(
        {
            "okf_type": "citegeist.topic",
            "slug": topic.get("slug"),
            "name": topic.get("name"),
            "source_type": topic.get("source_type"),
            "source_url": topic.get("source_url"),
            "expansion_phrase": topic.get("expansion_phrase"),
            "phrase_review_status": topic.get("phrase_review_status"),
            "work_count": len(entries),
            "exported_at": exported_at,
        }
    )
    lines = [frontmatter, f"# {topic.get('name') or topic.get('slug')}", ""]
    if topic.get("source_url"):
        lines.append(f"Source: {topic['source_url']}")
        lines.append("")
    if topic.get("expansion_phrase"):
        lines.append(f"Expansion phrase: `{topic['expansion_phrase']}`")
        lines.append("")
    lines.extend(["## Works", ""])
    for entry in entries:
        title = entry.fields.get("title") or entry.citation_key
        lines.append(f"- [{title}](../{work_paths[entry.citation_key]}) (`{entry.citation_key}`)")
    lines.append("")
    return "\n".join(lines)


def _render_index(
    topic: dict[str, object] | None,
    entries: list[Any],
    work_paths: dict[str, str],
    exported_at: str,
) -> str:
    title = f"CiteGeist OKF Bundle: {topic['name']}" if topic else "CiteGeist OKF Bundle"
    frontmatter = _frontmatter(
        {
            "okf_type": "citegeist.index",
            "bundle_kind": "citegeist_okf_bundle",
            "topic_slug": topic.get("slug") if topic else None,
            "work_count": len(entries),
            "exported_at": exported_at,
        }
    )
    lines = [frontmatter, f"# {title}", ""]
    lines.append("This bundle is a portable CiteGeist knowledge export: Markdown work pages, citation links, provenance, and BibTeX.")
    lines.extend(["", "## Bundle Files", "", "- [Bibliography](bibliography.bib)", "- [Export Log](log.md)", "- [Manifest](manifest.json)"])
    if topic:
        lines.append(f"- [Topic Page](topics/{_safe_filename(str(topic['slug']))}.md)")
    lines.extend(["", "## Works", ""])
    for entry in entries:
        title = entry.fields.get("title") or entry.citation_key
        year = entry.fields.get("year")
        suffix = f", {year}" if year else ""
        lines.append(f"- [{title}]({work_paths[entry.citation_key]}) (`{entry.citation_key}`{suffix})")
    lines.append("")
    return "\n".join(lines)


def _render_log(exported_at: str, topic: dict[str, object] | None, entries: list[Any]) -> str:
    frontmatter = _frontmatter(
        {
            "okf_type": "citegeist.log",
            "exported_at": exported_at,
            "topic_slug": topic.get("slug") if topic else None,
            "work_count": len(entries),
        }
    )
    lines = [frontmatter, "# Export Log", "", f"- Exported at: `{exported_at}`"]
    if topic:
        lines.append(f"- Topic: `{topic['slug']}`")
    lines.append(f"- Work pages: {len(entries)}")
    lines.append("")
    return "\n".join(lines)


def _frontmatter(values: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in values.items():
        if value is None or value == []:
            continue
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _metadata_lines(fields: dict[str, str]) -> list[str]:
    selected = ["author", "editor", "year", "journal", "booktitle", "publisher", "doi", "url", "isbn", "keywords"]
    rows = [{"field": field, "value": fields[field]} for field in selected if fields.get(field)]
    if not rows:
        return []
    return ["## Metadata", "", *_table(rows, ["field", "value"])]


def _table(rows: list[dict[str, object]], columns: list[str]) -> list[str]:
    if not rows:
        return ["No records."]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_cell(row.get(column)) for column in columns) + " |")
    return lines


def _markdown_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("|", "\\|")


def _split_people(value: str) -> list[str]:
    return [part.strip() for part in value.split(" and ") if part.strip()]


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return safe or "item"


def _relative_link(source_path: str, target_path: str) -> str:
    return str(Path(target_path).relative_to(Path(source_path).parent)) if "/" in source_path else target_path
