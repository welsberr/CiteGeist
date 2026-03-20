from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from citegeist.cli import main


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
                    "title": "Graph-first bibliography augmentation",
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
