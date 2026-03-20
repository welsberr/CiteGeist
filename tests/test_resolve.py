from xml.etree import ElementTree as ET

from citegeist.bibtex import BibEntry, render_bibtex
from citegeist.resolve import (
    MetadataResolver,
    _arxiv_atom_entry_to_bib,
    _crossref_message_to_entry,
    _datacite_work_to_entry,
    _openalex_work_to_entry,
    merge_entries_with_conflicts,
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


def test_crossref_message_to_entry_handles_missing_author_without_crashing():
    entry = _crossref_message_to_entry(
        {
            "type": "journal-article",
            "title": ["Avida and digital evolution"],
            "container-title": ["Artificial Life"],
            "issued": {"date-parts": [[2003, 1, 1]]},
            "author": [{"family": "", "given": ""}],
        }
    )

    assert entry.citation_key == "crossref2003avida"
    assert entry.fields["title"] == "Avida and digital evolution"
    assert entry.fields["year"] == "2003"


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


def test_merge_entries_with_conflicts_records_disagreements():
    base = BibEntry(
        entry_type="article",
        citation_key="smith2024graphs",
        fields={"title": "Existing Title", "journal": "Current Journal"},
    )
    resolved = BibEntry(
        entry_type="article",
        citation_key="resolved",
        fields={"title": "Resolved Title", "journal": "Current Journal", "year": "2024"},
    )

    merged, conflicts = merge_entries_with_conflicts(base, resolved)

    assert merged.fields["title"] == "Existing Title"
    assert merged.fields["year"] == "2024"
    assert conflicts == [
        {
            "field_name": "title",
            "current_value": "Existing Title",
            "proposed_value": "Resolved Title",
        }
    ]


def test_merge_entries_replaces_placeholder_titles_without_conflict():
    base = BibEntry(
        entry_type="misc",
        citation_key="stubdoi",
        fields={"title": "Referenced work 6", "doi": "10.1200/JCO.2002.04.117"},
    )
    resolved = BibEntry(
        entry_type="article",
        citation_key="resolved",
        fields={"title": "Resolved Work", "journal": "Journal of Clinical Oncology"},
    )

    merged, conflicts = merge_entries_with_conflicts(base, resolved)

    assert merged.fields["title"] == "Resolved Work"
    assert merged.fields["journal"] == "Journal of Clinical Oncology"
    assert conflicts == []


def test_resolver_tries_doi_before_dblp():
    resolver = MetadataResolver()
    calls: list[tuple[str, str]] = []

    def fake_doi(value: str):
        calls.append(("doi", value))
        return None

    def fake_dblp(value: str):
        calls.append(("dblp", value))
        return None

    def fake_datacite(value: str):
        calls.append(("datacite", value))
        return None

    resolver.resolve_doi = fake_doi  # type: ignore[method-assign]
    resolver.resolve_datacite_doi = fake_datacite  # type: ignore[method-assign]
    resolver.resolve_dblp = fake_dblp  # type: ignore[method-assign]

    resolver.resolve_entry(
        BibEntry(
            entry_type="article",
            citation_key="smith2024graphs",
            fields={"doi": "10.1000/example-doi", "dblp": "conf/test/Smith24"},
        )
    )

    assert calls == [
        ("doi", "10.1000/example-doi"),
        ("datacite", "10.1000/example-doi"),
        ("dblp", "conf/test/Smith24"),
    ]


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
    resolver.search_datacite = lambda title, limit=5: []  # type: ignore[method-assign]
    resolver.search_crossref = lambda title, limit=5: []  # type: ignore[method-assign]
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


def test_resolver_prefers_exact_crossref_title_match_before_datacite():
    resolver = MetadataResolver()
    resolver.search_crossref = lambda title, limit=5: [  # type: ignore[method-assign]
        _crossref_message_to_entry(
            {
                "type": "journal-article",
                "title": [title],
                "DOI": "10.1126/science.1090005",
                "container-title": ["Science"],
                "author": [
                    {"family": "King", "given": "Mary-Claire"},
                    {"family": "Wilson", "given": "A. C."},
                ],
                "issued": {"date-parts": [[1975, 4, 11]]},
            }
        )
    ]
    resolver.search_datacite = lambda title, limit=5: [  # type: ignore[method-assign]
        _datacite_work_to_entry(
            {
                "attributes": {
                    "doi": "10.5061/dryad.v6wwpzh17",
                    "titles": [
                        {
                            "title": "Conserved patterns and locomotor-related evolutionary constraints in the hominoid vertebral column"
                        }
                    ],
                    "creators": [
                        {"familyName": "Villamil", "givenName": "Catalina I."},
                        {"familyName": "Middleton", "givenName": "Emily R."},
                    ],
                    "publicationYear": 2024,
                    "types": {"resourceTypeGeneral": "Dataset"},
                }
            }
        )
    ]

    resolution = resolver.resolve_entry(
        BibEntry(
            entry_type="article",
            citation_key="king1975evolution2",
            fields={
                "title": "Evolution at two levels in humans and chimpanzees",
                "author": "King, M. C. and Wilson, A. C.",
                "year": "1975",
            },
        )
    )

    assert resolution is not None
    assert resolution.source_label == "crossref:search:Evolution at two levels in humans and chimpanzees"
    assert resolution.entry.fields["doi"] == "10.1126/science.1090005"


def test_resolver_rejects_mismatched_title_search_candidates():
    resolver = MetadataResolver()
    resolver.search_crossref = lambda title, limit=5: []  # type: ignore[method-assign]
    resolver.search_datacite = lambda title, limit=5: [  # type: ignore[method-assign]
        _datacite_work_to_entry(
            {
                "attributes": {
                    "doi": "10.5061/dryad.v6wwpzh17",
                    "titles": [
                        {
                            "title": "Conserved patterns and locomotor-related evolutionary constraints in the hominoid vertebral column"
                        }
                    ],
                    "creators": [
                        {"familyName": "Villamil", "givenName": "Catalina I."},
                    ],
                    "publicationYear": 2024,
                    "types": {"resourceTypeGeneral": "Dataset"},
                }
            }
        )
    ]
    resolver.search_openalex = lambda title, limit=5: [  # type: ignore[method-assign]
        _openalex_work_to_entry(
            {
                "id": "https://openalex.org/W2033360601",
                "display_name": "Immunological relatedness of glucose 6-phosphate dehydrogenases from vertebrate and invertebrate species.",
                "publication_year": 1978,
                "type": "article",
                "authorships": [
                    {"author": {"display_name": "Yoshikazu Sado"}},
                    {"author": {"display_name": "Samuel H. Hori"}},
                ],
                "doi": "https://doi.org/10.1266/jjg.53.91",
            }
        )
    ]

    resolution = resolver.resolve_entry(
        BibEntry(
            entry_type="article",
            citation_key="sarich1967immunological1",
            fields={
                "title": "Immunological Time Scale for Homonid Evolution",
                "author": "Sarich, V. and Wilson, A.",
                "year": "1967",
            },
        )
    )

    assert resolution is None


def test_datacite_work_to_entry_maps_basic_fields():
    entry = _datacite_work_to_entry(
        {
            "attributes": {
                "doi": "10.1000/datacite-example",
                "titles": [{"title": "Repository Dissertation Record"}],
                "creators": [{"familyName": "Doe", "givenName": "Jane"}],
                "publicationYear": 2021,
                "publisher": "Example University",
                "url": "https://example.edu/record/123",
                "types": {"resourceTypeGeneral": "Dissertation"},
                "descriptions": [
                    {
                        "descriptionType": "Abstract",
                        "description": "An abstract from DataCite.",
                    }
                ],
            }
        }
    )

    assert entry.entry_type == "phdthesis"
    assert entry.fields["doi"] == "10.1000/datacite-example"
    assert entry.fields["author"] == "Doe, Jane"
    assert entry.fields["publisher"] == "Example University"
    assert entry.fields["abstract"] == "An abstract from DataCite."


def test_resolver_can_resolve_datacite_doi():
    resolver = MetadataResolver()
    resolver.source_client.get_json = lambda _url: {  # type: ignore[method-assign]
        "data": {
            "attributes": {
                "doi": "10.1000/datacite-example",
                "titles": [{"title": "Repository Dissertation Record"}],
                "creators": [{"familyName": "Doe", "givenName": "Jane"}],
                "publicationYear": 2021,
                "types": {"resourceTypeGeneral": "Dissertation"},
            }
        }
    }

    resolution = resolver.resolve_datacite_doi("10.1000/datacite-example")

    assert resolution is not None
    assert resolution.source_label == "datacite:doi:10.1000/datacite-example"
    assert resolution.entry.entry_type == "phdthesis"


def test_resolver_can_fall_back_to_datacite_title_search():
    resolver = MetadataResolver()
    resolver.search_crossref = lambda title, limit=5: []  # type: ignore[method-assign]
    resolver.search_datacite = lambda title, limit=5: [  # type: ignore[method-assign]
        _datacite_work_to_entry(
            {
                "attributes": {
                    "doi": "10.1000/datacite-example",
                    "titles": [{"title": title}],
                    "creators": [{"familyName": "Doe", "givenName": "Jane"}],
                    "publicationYear": 2021,
                    "types": {"resourceTypeGeneral": "Dissertation"},
                }
            }
        )
    ]
    resolver.search_openalex = lambda title, limit=5: []  # type: ignore[method-assign]

    resolution = resolver.resolve_entry(
        BibEntry(
            entry_type="misc",
            citation_key="draft1",
            fields={"title": "Repository Dissertation Record", "author": "Doe, Jane", "year": "2021"},
        )
    )

    assert resolution is not None
    assert resolution.source_label == "datacite:search:Repository Dissertation Record"
    assert resolution.entry.fields["doi"] == "10.1000/datacite-example"


def test_render_bibtex_tolerates_unmatched_braces_in_field_values():
    rendered = render_bibtex(
        [
            BibEntry(
                entry_type="misc",
                citation_key="broken2026",
                fields={
                    "author": "Broken, Example",
                    "title": "Unmatched { braces } example } tail",
                    "year": "2026",
                    "note": "Open { brace only",
                },
            )
        ]
    )

    assert "@misc{broken2026," in rendered
    assert "Unmatched { braces } example ) tail" in rendered
    assert "Open ( brace only" in rendered
