import json
from pathlib import Path

from citegeist import (
    available_extraction_backends,
    check_extraction_comparison_summary,
    compare_extraction_backends,
    extract_references,
    parse_bibtex,
    register_extraction_backend,
    summarize_extraction_comparison,
)
from citegeist.bibtex import BibEntry
from citegeist.cli import main


SAMPLE_REFERENCES = """
[1] Smith, Jane and Doe, Alex. 2024. Graph-first bibliography augmentation. Journal of Research Systems.
[2] Miller, Sam. 2023. Semantic search for research corpora. Proceedings of the Retrieval Workshop.
"""

APA_AND_BOOK_REFERENCES = """
Brown, T., & Green, P. (2021). Retrieval methods for scholarly corpora. Journal of Information Retrieval.

Nguyen, An. Research Design for Literature Mapping. Example University Press, 2020.
"""

WRAPPED_REFERENCES = """
[1] Taylor, Ann. 2022. Multi-line reference extraction
for bibliography pipelines. Journal of Parsing Systems.
[2] Chen, Bo. 2021. Another entry. Proceedings of the Mining Workshop.
"""

RICH_REFERENCES = """
[1] Smith, Jane. 2024a. Graph-first bibliography augmentation. Journal of Research Systems 12(3): 45-67. doi:10.1000/example-doi.
[2] Doe, Alex. 2019. Evolutionary archives. PhD dissertation, Example University.
[3] Chen, Bo. 2018. Field methods update. Technical Report No. TR-2018-05, Example Research Lab.
[4] Nguyen, An. 2022. Project page. Retrieved from https://example.org/project-page.
"""

FIXTURE_REFERENCES = Path(__file__).with_name("fixtures").joinpath("extract_backend_fixture.txt").read_text(encoding="utf-8")


def register_fixture_alt_backend() -> None:
    class FixtureAltBackend:
        name = "fixture-alt"

        def extract_references(self, text: str) -> list[BibEntry]:
            return [
                BibEntry(
                    entry_type="article",
                    citation_key="smith2024graphfirst1",
                    fields={
                        "title": "Graph-first bibliography augmentation",
                        "year": "2024a",
                        "journal": "Journal of Research Systems",
                        "pages": "45--67",
                        "doi": "10.1000/example-doi",
                    },
                ),
                BibEntry(
                    entry_type="article",
                    citation_key="miller2023semantic2",
                    fields={
                        "title": "Semantic search for research corpora",
                        "year": "2023",
                        "journal": "Retrieval Workshop Journal",
                    },
                ),
                BibEntry(
                    entry_type="phdthesis",
                    citation_key="doe2019evolutionary3",
                    fields={
                        "title": "Evolutionary archives",
                        "year": "2019",
                        "school": "Example University",
                    },
                ),
                BibEntry(
                    entry_type="techreport",
                    citation_key="chen2018field4",
                    fields={
                        "title": "Field methods update",
                        "year": "2018",
                        "institution": "Example Research Lab",
                        "number": "TR-2018-05",
                    },
                ),
                BibEntry(
                    entry_type="misc",
                    citation_key="nguyen2022project5",
                    fields={
                        "title": "Project page",
                        "year": "2022",
                        "url": "https://example.org/project-page",
                    },
                ),
            ]

    register_extraction_backend(FixtureAltBackend())


def test_extract_references_builds_draft_entries():
    entries = extract_references(SAMPLE_REFERENCES)

    assert [entry.citation_key for entry in entries] == [
        "smith2024graphfirst1",
        "miller2023semantic2",
    ]
    assert entries[0].entry_type == "article"
    assert entries[0].fields["journal"] == "Journal of Research Systems"
    assert "extracted_by = {heuristic}" in entries[0].fields["note"]
    assert entries[1].entry_type == "inproceedings"
    assert entries[1].fields["booktitle"] == "Proceedings of the Retrieval Workshop"


def test_extract_cli_writes_bibtex(tmp_path):
    input_path = tmp_path / "references.txt"
    output_path = tmp_path / "draft.bib"
    input_path.write_text(SAMPLE_REFERENCES, encoding="utf-8")

    exit_code = main(["extract", str(input_path), "--output", str(output_path)])
    assert exit_code == 0

    exported = output_path.read_text(encoding="utf-8")
    parsed = {entry.citation_key: entry for entry in parse_bibtex(exported)}
    assert parsed["smith2024graphfirst1"].fields["journal"] == "Journal of Research Systems"
    assert parsed["miller2023semantic2"].fields["booktitle"] == "Proceedings of the Retrieval Workshop"


def test_extract_references_supports_apa_and_book_styles():
    entries = extract_references(APA_AND_BOOK_REFERENCES)

    assert [entry.entry_type for entry in entries] == ["article", "book"]
    assert entries[0].fields["journal"] == "Journal of Information Retrieval"
    assert entries[0].fields["author"] == "Brown, T., and Green, P"
    assert entries[1].fields["publisher"] == "Example University Press"
    assert entries[1].fields["title"] == "Research Design for Literature Mapping"


def test_extract_references_joins_wrapped_reference_lines():
    entries = extract_references(WRAPPED_REFERENCES)

    assert len(entries) == 2
    assert entries[0].fields["title"] == "Multi-line reference extraction for bibliography pipelines"
    assert entries[0].fields["journal"] == "Journal of Parsing Systems"


def test_extract_references_preserves_year_suffix_ids_and_pages():
    entries = extract_references(RICH_REFERENCES)

    article = entries[0]
    assert article.fields["year"] == "2024a"
    assert article.fields["doi"] == "10.1000/example-doi"
    assert article.fields["url"] == "https://doi.org/10.1000/example-doi"
    assert article.fields["journal"] == "Journal of Research Systems"
    assert article.fields["volume"] == "12"
    assert article.fields["number"] == "3"
    assert article.fields["pages"] == "45--67"


def test_extract_references_supports_thesis_report_and_web_entries():
    entries = extract_references(RICH_REFERENCES)

    thesis = entries[1]
    report = entries[2]
    webpage = entries[3]

    assert thesis.entry_type == "phdthesis"
    assert thesis.fields["school"] == "Example University"

    assert report.entry_type == "techreport"
    assert report.fields["institution"] == "Example Research Lab"
    assert report.fields["number"] == "TR-2018-05"
    assert report.fields["type"] == "Technical Report"

    assert webpage.entry_type == "misc"
    assert webpage.fields["url"] == "https://example.org/project-page"
    assert webpage.fields["howpublished"] == "Retrieved from https://example.org/project-page"


def test_extract_references_supports_registered_backend():
    class StaticBackend:
        name = "static-test"

        def extract_references(self, text: str) -> list[BibEntry]:
            return [
                BibEntry(
                    entry_type="misc",
                    citation_key="static2024example1",
                    fields={"title": text.strip(), "year": "2024"},
                )
            ]

    register_extraction_backend(StaticBackend())

    entries = extract_references("Custom backend input", backend="static-test")

    assert entries[0].citation_key == "static2024example1"
    assert "static-test" in available_extraction_backends()


def test_extract_references_rejects_unknown_backend():
    try:
        extract_references("anything", backend="missing-backend")
    except ValueError as exc:
        assert "Unknown extraction backend" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown backend")


def test_extract_cli_accepts_backend_flag(tmp_path):
    input_path = tmp_path / "references.txt"
    output_path = tmp_path / "draft.bib"
    input_path.write_text(SAMPLE_REFERENCES, encoding="utf-8")

    exit_code = main(["extract", str(input_path), "--backend", "heuristic", "--output", str(output_path)])

    assert exit_code == 0
    exported = output_path.read_text(encoding="utf-8")
    assert "@article{smith2024graphfirst1," in exported


def test_extract_references_anystyle_backend_maps_json(monkeypatch):
    import citegeist.extract as extract_module

    monkeypatch.setattr(extract_module.shutil, "which", lambda command: "/usr/bin/anystyle")

    class Result:
        returncode = 0
        stdout = """
[
  {
    "author": [{"family": "Smith", "given": "Jane"}],
    "date": ["2024"],
    "title": ["Graph-first bibliography augmentation"],
    "journal": ["Journal of Research Systems"],
    "volume": ["12"],
    "issue": ["3"],
    "pages": ["45-67"],
    "doi": ["10.1000/example-doi"],
    "type": "article"
  }
]
"""
        stderr = ""

    monkeypatch.setattr(extract_module.subprocess, "run", lambda *args, **kwargs: Result())

    entries = extract_references(SAMPLE_REFERENCES, backend="anystyle")

    assert len(entries) == 1
    assert entries[0].entry_type == "article"
    assert entries[0].fields["author"] == "Smith, Jane"
    assert entries[0].fields["journal"] == "Journal of Research Systems"
    assert entries[0].fields["pages"] == "45--67"
    assert entries[0].fields["doi"] == "10.1000/example-doi"
    assert entries[0].fields["url"] == "https://doi.org/10.1000/example-doi"
    assert "extracted_by = {anystyle}" in entries[0].fields["note"]
    assert "raw_reference = {Smith, Jane and Doe, Alex. 2024. Graph-first bibliography augmentation. Journal of Research Systems.}" in entries[0].fields["note"]


def test_extract_references_anystyle_backend_reports_missing_binary(monkeypatch):
    import citegeist.extract as extract_module

    monkeypatch.setattr(extract_module.shutil, "which", lambda command: None)

    try:
        extract_references(SAMPLE_REFERENCES, backend="anystyle")
    except RuntimeError as exc:
        assert "requires the AnyStyle CLI" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when anystyle is unavailable")


def test_extract_references_grobid_backend_maps_bibtex(monkeypatch):
    import citegeist.extract as extract_module

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b"""
@article{-1,
  author = {Smith, Jane},
  title = {Graph-first bibliography augmentation},
  journal = {Journal of Research Systems},
  year = {2024},
  pages = {45--67},
  volume = {12},
  number = {3},
  doi = {10.1000/example-doi}
}
"""

    monkeypatch.setattr(extract_module.urllib.request, "urlopen", lambda request, timeout=30: FakeResponse())

    entries = extract_references(SAMPLE_REFERENCES, backend="grobid")

    assert len(entries) == 1
    assert entries[0].citation_key == "smith2024graphfirst1"
    assert entries[0].fields["doi"] == "10.1000/example-doi"
    assert entries[0].fields["url"] == "https://doi.org/10.1000/example-doi"
    assert "extracted_by = {grobid}" in entries[0].fields["note"]


def test_extract_references_grobid_backend_reports_http_errors(monkeypatch):
    import citegeist.extract as extract_module

    def raise_http(request, timeout=30):
        raise extract_module.urllib.error.HTTPError(
            url=request.full_url,
            code=503,
            msg="Busy",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(extract_module.urllib.request, "urlopen", raise_http)

    try:
        extract_references(SAMPLE_REFERENCES, backend="grobid")
    except RuntimeError as exc:
        assert "GROBID extraction failed with HTTP 503" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when grobid returns HTTP error")


def test_compare_extraction_backends_reports_field_differences():
    class CompareA:
        name = "compare-a"

        def extract_references(self, text: str) -> list[BibEntry]:
            return [
                BibEntry(
                    entry_type="article",
                    citation_key="a1",
                    fields={"title": "Shared Title", "year": "2024", "journal": "Journal A"},
                )
            ]

    class CompareB:
        name = "compare-b"

        def extract_references(self, text: str) -> list[BibEntry]:
            return [
                BibEntry(
                    entry_type="inproceedings",
                    citation_key="b1",
                    fields={"title": "Shared Title", "year": "2024", "booktitle": "Proceedings B"},
                )
            ]

    register_extraction_backend(CompareA())
    register_extraction_backend(CompareB())

    rows = compare_extraction_backends(SAMPLE_REFERENCES, backends=["compare-a", "compare-b"])

    assert rows[0].ordinal == 1
    assert "entry_type" in rows[0].differing_fields
    assert "journal" in rows[0].differing_fields
    assert "booktitle" in rows[0].differing_fields
    assert rows[0].entries["compare-a"]["fields"]["journal"] == "Journal A"
    assert rows[0].entries["compare-b"]["fields"]["booktitle"] == "Proceedings B"


def test_compare_extract_cli_writes_json(tmp_path):
    input_path = tmp_path / "references.txt"
    output_path = tmp_path / "compare.json"
    input_path.write_text(SAMPLE_REFERENCES, encoding="utf-8")

    exit_code = main(
        [
            "compare-extract",
            str(input_path),
            "--backend",
            "heuristic",
            "--backend",
            "heuristic",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload[0]["ordinal"] == 1
    assert payload[0]["entries"]["heuristic"]["present"] is True


def test_compare_extraction_backends_fixture_reports_expected_disagreement():
    register_fixture_alt_backend()

    rows = compare_extraction_backends(FIXTURE_REFERENCES, backends=["heuristic", "fixture-alt"])

    assert len(rows) == 5
    assert "author" in rows[0].differing_fields
    assert "volume" in rows[0].differing_fields
    assert "number" in rows[0].differing_fields
    assert "entry_type" in rows[1].differing_fields
    assert "journal" in rows[1].differing_fields
    assert "booktitle" in rows[1].differing_fields
    assert "howpublished" in rows[4].differing_fields


def test_compare_extract_cli_fixture_json_contains_all_rows(tmp_path):
    input_path = tmp_path / "fixture.txt"
    output_path = tmp_path / "compare.json"
    input_path.write_text(FIXTURE_REFERENCES, encoding="utf-8")

    exit_code = main(["compare-extract", str(input_path), "--backend", "heuristic", "--output", str(output_path)])

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(payload) == 5
    assert payload[2]["entries"]["heuristic"]["entry_type"] == "phdthesis"


def test_summarize_extraction_comparison_counts_differences():
    rows = compare_extraction_backends(FIXTURE_REFERENCES, backends=["heuristic", "heuristic"])

    summary = summarize_extraction_comparison(rows)

    assert summary.row_count == 5
    assert summary.rows_with_differences == 0
    assert summary.backend_presence_counts["heuristic"] == 5
    assert summary.differing_field_counts == {}


def test_compare_extract_cli_summary_writes_counts(tmp_path):
    input_path = tmp_path / "fixture.txt"
    output_path = tmp_path / "summary.json"
    input_path.write_text(FIXTURE_REFERENCES, encoding="utf-8")

    exit_code = main(
        [
            "compare-extract",
            str(input_path),
            "--backend",
            "heuristic",
            "--backend",
            "heuristic",
            "--summary",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["row_count"] == 5
    assert payload["rows_with_differences"] == 0
    assert payload["backend_presence_counts"]["heuristic"] == 5


def test_check_extraction_comparison_summary_reports_failure():
    register_fixture_alt_backend()
    rows = compare_extraction_backends(FIXTURE_REFERENCES, backends=["heuristic", "fixture-alt"])
    summary = summarize_extraction_comparison(rows)

    check = check_extraction_comparison_summary(summary, max_rows_with_differences=0)

    assert check.passed is False
    assert "rows_with_differences" in check.failures[0]


def test_compare_extract_cli_summary_threshold_passes(tmp_path):
    input_path = tmp_path / "fixture.txt"
    output_path = tmp_path / "summary-pass.json"
    input_path.write_text(FIXTURE_REFERENCES, encoding="utf-8")

    exit_code = main(
        [
            "compare-extract",
            str(input_path),
            "--backend",
            "heuristic",
            "--backend",
            "heuristic",
            "--summary",
            "--max-rows-with-differences",
            "0",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["check"]["passed"] is True


def test_compare_extract_cli_summary_threshold_fails(tmp_path):
    register_fixture_alt_backend()
    input_path = tmp_path / "fixture.txt"
    output_path = tmp_path / "summary-fail.json"
    input_path.write_text(FIXTURE_REFERENCES, encoding="utf-8")

    exit_code = main(
        [
            "compare-extract",
            str(input_path),
            "--backend",
            "heuristic",
            "--backend",
            "fixture-alt",
            "--summary",
            "--max-rows-with-differences",
            "0",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["check"]["passed"] is False
    assert payload["summary"]["rows_with_differences"] > 0
