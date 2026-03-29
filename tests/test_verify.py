from __future__ import annotations

from citegeist.bibtex import BibEntry
from citegeist.resolve import Resolution
from citegeist.verify import BibliographyVerifier


def test_verifier_uses_direct_doi_resolution_for_bib_entries():
    verifier = BibliographyVerifier()
    verifier.resolver.resolve_doi = lambda value: Resolution(  # type: ignore[method-assign]
        entry=BibEntry(
            entry_type="article",
            citation_key="doi101000example",
            fields={
                "author": "Smith, Jane",
                "title": "Resolved Work",
                "year": "2024",
                "doi": value,
            },
        ),
        source_type="resolver",
        source_label=f"crossref:doi:{value}",
    )

    result = verifier.verify_bib_entry(
        BibEntry(
            entry_type="misc",
            citation_key="seed2024",
            fields={"title": "Rough Work", "doi": "10.1000/example"},
        )
    )

    assert result.status == "exact"
    assert result.confidence == 1.0
    assert result.entry.fields["title"] == "Resolved Work"
    assert result.source_label == "crossref:doi:10.1000/example"


def test_verifier_scores_and_sorts_search_candidates():
    verifier = BibliographyVerifier()
    verifier.resolver.search_crossref = lambda title, limit=5: [  # type: ignore[method-assign]
        BibEntry(
            entry_type="article",
            citation_key="goodmatch",
            fields={
                "author": "Smith, Jane",
                "title": "Graph-first bibliography augmentation",
                "year": "2024",
                "doi": "10.1000/good",
            },
        ),
        BibEntry(
            entry_type="article",
            citation_key="weaker",
            fields={
                "author": "Doe, Alex",
                "title": "Graph search methods",
                "year": "2023",
            },
        ),
    ]
    verifier.resolver.search_openalex = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_datacite = lambda title, limit=5: []  # type: ignore[method-assign]

    result = verifier.verify_string('"Graph-first bibliography augmentation" Smith 2024')

    assert result.entry.citation_key == "goodmatch"
    assert result.status in {"high_confidence", "exact"}
    assert result.alternates[0].entry.citation_key == "weaker"


def test_verification_result_to_bib_entry_contains_audit_fields():
    verifier = BibliographyVerifier()
    verifier.resolver.search_crossref = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_openalex = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_datacite = lambda title, limit=5: []  # type: ignore[method-assign]

    result = verifier._verify_query(  # type: ignore[attr-defined]
        {"title": "Missing Work", "authors": [], "year": "", "venue": ""},
        query="Missing Work",
        context="",
        limit=1,
        input_type="string",
    )

    bib_entry = result.to_bib_entry()

    assert bib_entry.fields["x_status"] == "not_found"
    assert bib_entry.fields["x_query"] == "Missing Work"
