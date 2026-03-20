from xml.etree import ElementTree as ET

from citegeist.bibtex import BibEntry
from citegeist.resolve import (
    MetadataResolver,
    _arxiv_atom_entry_to_bib,
    _crossref_message_to_entry,
    _openalex_work_to_entry,
    merge_entries,
)


def test_crossref_message_to_entry_maps_basic_fields():
    entry = _crossref_message_to_entry(
        {
            "type": "journal-article",
            "title": ["Graph-first bibliography augmentation"],
            "DOI": "10.1000/example-doi",
            "URL": "https://doi.org/10.1000/example-doi",
            "container-title": ["Journal of Graph Studies"],
            "author": [{"family": "Smith", "given": "Jane"}],
            "issued": {"date-parts": [[2024, 5, 1]]},
        }
    )

    assert entry.entry_type == "article"
    assert entry.fields["author"] == "Smith, Jane"
    assert entry.fields["journal"] == "Journal of Graph Studies"
    assert entry.fields["year"] == "2024"


def test_arxiv_atom_entry_to_bib_maps_basic_fields():
    xml = ET.fromstring(
        """
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title>Semantic search for research corpora</title>
  <summary>Dense retrieval improves recall.</summary>
  <published>2023-01-15T00:00:00Z</published>
  <author><name>Miller, Sam</name></author>
  <arxiv:doi>10.1000/arxiv-example</arxiv:doi>
</entry>
"""
    )
    entry = _arxiv_atom_entry_to_bib(xml, "2301.12345")
    assert entry.fields["author"] == "Miller, Sam"
    assert entry.fields["arxiv"] == "2301.12345"
    assert entry.fields["doi"] == "10.1000/arxiv-example"


def test_merge_entries_prefers_existing_values_and_adds_missing_fields():
    base = BibEntry(
        entry_type="article",
        citation_key="smith2024graphs",
        fields={"title": "Graph-first bibliography augmentation", "doi": "10.1000/example-doi"},
    )
    resolved = BibEntry(
        entry_type="article",
        citation_key="otherkey",
        fields={"title": "Different title", "journal": "Journal of Graph Studies"},
    )

    merged = merge_entries(base, resolved)

    assert merged.fields["title"] == "Graph-first bibliography augmentation"
    assert merged.fields["journal"] == "Journal of Graph Studies"


def test_resolver_tries_doi_before_dblp():
    resolver = MetadataResolver()
    calls: list[tuple[str, str]] = []

    def fake_doi(value: str):
        calls.append(("doi", value))
        return None

    def fake_dblp(value: str):
        calls.append(("dblp", value))
        return None

    resolver.resolve_doi = fake_doi  # type: ignore[method-assign]
    resolver.resolve_dblp = fake_dblp  # type: ignore[method-assign]

    resolver.resolve_entry(
        BibEntry(
            entry_type="article",
            citation_key="smith2024graphs",
            fields={"doi": "10.1000/example-doi", "dblp": "conf/test/Smith24"},
        )
    )

    assert calls == [("doi", "10.1000/example-doi"), ("dblp", "conf/test/Smith24")]


def test_openalex_work_to_entry_maps_basic_fields():
    entry = _openalex_work_to_entry(
        {
            "id": "https://openalex.org/W12345",
            "doi": "https://doi.org/10.1000/example-openalex",
            "display_name": "OpenAlex Resolved Work",
            "publication_year": 2022,
            "type": "article",
            "authorships": [{"author": {"display_name": "Jane Smith"}}],
            "primary_location": {"source": {"display_name": "Journal of Open Graphs"}},
            "abstract_inverted_index": {"OpenAlex": [0], "resolved": [1]},
        }
    )

    assert entry.citation_key == "openalexw12345"
    assert entry.fields["openalex"] == "W12345"
    assert entry.fields["doi"] == "10.1000/example-openalex"
    assert entry.fields["journal"] == "Journal of Open Graphs"
    assert entry.fields["abstract"] == "OpenAlex resolved"


def test_resolver_can_resolve_openalex_id():
    resolver = MetadataResolver()
    resolver.source_client.get_json = lambda _url: {  # type: ignore[method-assign]
        "id": "https://openalex.org/W12345",
        "display_name": "OpenAlex Resolved Work",
        "publication_year": 2022,
        "type": "article",
        "authorships": [{"author": {"display_name": "Jane Smith"}}],
    }

    resolution = resolver.resolve_openalex("W12345")

    assert resolution is not None
    assert resolution.source_label == "openalex:id:W12345"
    assert resolution.entry.fields["openalex"] == "W12345"


def test_resolver_falls_back_to_openalex_title_search():
    resolver = MetadataResolver()
    resolver.search_openalex = lambda title, limit=5: [  # type: ignore[method-assign]
        _openalex_work_to_entry(
            {
                "id": "https://openalex.org/W12345",
                "display_name": title,
                "publication_year": 2022,
                "type": "article",
                "authorships": [{"author": {"display_name": "Jane Smith"}}],
            }
        )
    ]

    resolution = resolver.resolve_entry(
        BibEntry(
            entry_type="article",
            citation_key="smith2022openalex",
            fields={"title": "OpenAlex Resolved Work", "author": "Jane Smith", "year": "2022"},
        )
    )

    assert resolution is not None
    assert resolution.source_label == "openalex:search:OpenAlex Resolved Work"
    assert resolution.entry.fields["openalex"] == "W12345"
