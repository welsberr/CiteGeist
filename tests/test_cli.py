from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


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
