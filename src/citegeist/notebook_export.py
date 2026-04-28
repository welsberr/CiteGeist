from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .storage import BibliographyStore


def export_notebook_topic_bundle(
    store_dir: str | Path,
    topic_slug: str,
    out_dir: str | Path,
    *,
    include_stubs: bool = False,
) -> dict[str, Any]:
    store = BibliographyStore(store_dir)
    try:
        topic = store.get_topic(topic_slug)
        if topic is None:
            raise KeyError(f"Topic not found: {topic_slug}")
        entries = store.list_topic_entries(topic_slug, limit=100000)
        citation_keys = [row["citation_key"] for row in entries]
        bibtex_report = store.export_bibtex_report(citation_keys, include_stubs=include_stubs)
    finally:
        store.close()

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    bibliography_path = target / "notebook_topic_bibliography.bib"
    bibliography_text = bibtex_report["bibtex"]
    bibliography_path.write_text(bibliography_text + ("\n" if bibliography_text else ""), encoding="utf-8")

    bundle = {
        "bundle_kind": "notebook_topic_bibliography_bundle",
        "topic": topic,
        "entry_count": len(entries),
        "exported_count": bibtex_report["exported_count"],
        "include_stubs": include_stubs,
        "skipped": bibtex_report["skipped"],
        "citation_keys": citation_keys,
        "bibliography_path": str(bibliography_path),
    }
    bundle_path = target / "notebook_topic_bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    return {
        "bundle_path": str(bundle_path),
        "bibliography_path": str(bibliography_path),
        "bundle": bundle,
    }
