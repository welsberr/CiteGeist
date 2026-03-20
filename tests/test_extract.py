from citegeist import extract_references, parse_bibtex
from citegeist.cli import main


SAMPLE_REFERENCES = """
[1] Smith, Jane and Doe, Alex. 2024. Graph-first bibliography augmentation. Journal of Research Systems.
[2] Miller, Sam. 2023. Semantic search for research corpora. Proceedings of the Retrieval Workshop.
"""


def test_extract_references_builds_draft_entries():
    entries = extract_references(SAMPLE_REFERENCES)

    assert [entry.citation_key for entry in entries] == [
        "smith2024graphfirst1",
        "miller2023semantic2",
    ]
    assert entries[0].entry_type == "article"
    assert entries[0].fields["journal"] == "Journal of Research Systems"
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
