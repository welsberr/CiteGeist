from citegeist import extract_references, parse_bibtex
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
