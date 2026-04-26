from __future__ import annotations

from citegeist.bibtex import BibEntry
from citegeist.resolve import MetadataResolver
from citegeist.sources import OpenLibrarySource, SourceRegistry, list_source_catalog


class FakeSourceClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def try_get_json(self, _url: str) -> dict[str, object]:
        return dict(self.payload)


def test_openlibrary_source_normalizes_book_record() -> None:
    source = OpenLibrarySource(config={"source_client": FakeSourceClient({})})
    entry = source.normalize(
        {
            "title": "The Nature of the Stratigraphic Record",
            "author_name": ["D. V. Ager"],
            "first_publish_year": 1973,
            "publisher": ["Macmillan"],
            "key": "/works/OL82563W",
            "edition_key": ["OL12345M"],
            "isbn": ["9781234567890"],
        }
    )

    assert entry is not None
    assert entry.entry_type == "book"
    assert entry.fields["title"] == "The Nature of the Stratigraphic Record"
    assert entry.fields["author"] == "D. V. Ager"
    assert entry.fields["year"] == "1973"
    assert entry.fields["publisher"] == "Macmillan"
    assert entry.fields["openlibrary_work"] == "/works/OL82563W"
    assert entry.fields["openlibrary_edition"] == "OL12345M"
    assert entry.fields["isbn"] == "9781234567890"


def test_openlibrary_registry_and_catalog() -> None:
    registry = SourceRegistry()
    registry.from_config_dict(
        {
            "sources": {
                "openlibrary": {
                    "source_type": "openlibrary",
                    "enabled": True,
                }
            }
        }
    )
    source = registry.get("openlibrary")
    assert isinstance(source, OpenLibrarySource)

    catalog = {entry.key: entry for entry in list_source_catalog()}
    assert catalog["open_library"].current_status == "integrated"
    assert "book_metadata" in catalog["open_library"].capabilities


def test_metadata_resolver_uses_openlibrary_after_other_searches_fail() -> None:
    resolver = MetadataResolver()
    resolver.search_crossref = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_datacite = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_openalex = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_pubmed = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_europepmc = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_semanticscholar = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_openlibrary = lambda _title, limit=5: [  # type: ignore[method-assign]
        BibEntry(
            entry_type="book",
            citation_key="olworks123",
            fields={
                "title": "The Nature of the Stratigraphic Record",
                "author": "D. V. Ager",
                "year": "1973",
                "openlibrary_work": "/works/OL82563W",
            },
        )
    ]

    result = resolver.resolve_entry(
        BibEntry(
            entry_type="book",
            citation_key="seed1973",
            fields={"title": "The Nature of the Stratigraphic Record", "author": "D. V. Ager", "year": "1973"},
        )
    )

    assert result is not None
    assert result.source_label == "openlibrary:search:The Nature of the Stratigraphic Record"


def test_metadata_resolver_trace_records_fallback_attempts() -> None:
    resolver = MetadataResolver()
    resolver.search_crossref = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_datacite = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_openalex = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_pubmed = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_europepmc = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_semanticscholar = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_openlibrary = lambda _title, limit=5: [  # type: ignore[method-assign]
        BibEntry(
            entry_type="book",
            citation_key="olworks123",
            fields={"title": "Example Book", "author": "Author, A", "year": "1980"},
        )
    ]

    outcome = resolver.resolve_entry_with_trace(
        BibEntry(
            entry_type="book",
            citation_key="seed1980",
            fields={"title": "Example Book", "author": "Author, A", "year": "1980"},
        )
    )

    assert outcome.resolution is not None
    assert outcome.resolution.source_label == "openlibrary:search:Example Book"
    assert [attempt.source_name for attempt in outcome.attempts[-2:]] == ["semanticscholar", "openlibrary"]
    assert outcome.attempts[-1].matched is True
    assert outcome.attempts[-1].candidate_count == 1


def test_metadata_resolver_uses_fuzzy_catalog_match_for_book_titles() -> None:
    resolver = MetadataResolver()
    resolver.search_crossref = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_datacite = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_openalex = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_pubmed = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_europepmc = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_semanticscholar = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_openlibrary = lambda _title, limit=5: [  # type: ignore[method-assign]
        BibEntry(
            entry_type="book",
            citation_key="olworks123",
            fields={
                "title": "The nature of the stratigraphical record",
                "author": "D. V. Ager",
                "year": "1973",
                "openlibrary_work": "/works/OL82563W",
            },
        )
    ]

    result = resolver.resolve_entry(
        BibEntry(
            entry_type="book",
            citation_key="seed1973",
            fields={"title": "The Nature of the Stratigraphic Record", "author": "D. V. Ager", "year": "1973"},
        )
    )

    assert result is not None
    assert result.source_label == "openlibrary:search:The Nature of the Stratigraphic Record"


def test_metadata_resolver_skips_openlibrary_for_article_like_entries() -> None:
    resolver = MetadataResolver()
    resolver.search_crossref = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_datacite = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_openalex = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_pubmed = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_europepmc = lambda _title, limit=5: []  # type: ignore[method-assign]
    resolver.search_semanticscholar = lambda _title, limit=5: []  # type: ignore[method-assign]
    called = {"openlibrary": False}

    def fake_openlibrary(_title: str, limit: int = 5) -> list[BibEntry]:
        called["openlibrary"] = True
        return []

    resolver.search_openlibrary = fake_openlibrary  # type: ignore[method-assign]
    outcome = resolver.resolve_entry_with_trace(
        BibEntry(
            entry_type="article",
            citation_key="seed1977",
            fields={
                "title": "Fast locomotion of some African ungulates",
                "author": "Alexander, R. M.",
                "year": "1977",
                "journal": "Journal of Zoology",
            },
        )
    )

    assert outcome.resolution is None
    assert called["openlibrary"] is False
    assert all(attempt.source_name != "openlibrary" for attempt in outcome.attempts)
