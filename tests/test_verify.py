from __future__ import annotations

from citegeist.bibtex import BibEntry
from citegeist.llm_verify import VerificationLlmConfig, _loads_lenient_json
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


def test_verifier_uses_direct_pmid_resolution_for_bib_entries():
    verifier = BibliographyVerifier()
    verifier.resolver.resolve_pmid = lambda value: Resolution(  # type: ignore[method-assign]
        entry=BibEntry(
            entry_type="article",
            citation_key="pmid12345678",
            fields={
                "author": "Smith, Jane",
                "title": "Resolved PubMed Work",
                "year": "2024",
                "pmid": value,
            },
        ),
        source_type="resolver",
        source_label=f"pubmed:pmid:{value}",
    )

    result = verifier.verify_bib_entry(
        BibEntry(
            entry_type="misc",
            citation_key="seed2024",
            fields={"title": "Rough Work", "pmid": "12345678"},
        )
    )

    assert result.status == "exact"
    assert result.confidence == 1.0
    assert result.entry.fields["title"] == "Resolved PubMed Work"
    assert result.source_label == "pubmed:pmid:12345678"


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
    verifier.resolver.search_pubmed = lambda title, limit=5: []  # type: ignore[method-assign]

    result = verifier.verify_string('"Graph-first bibliography augmentation" Smith 2024')

    assert result.entry.citation_key == "goodmatch"
    assert result.status in {"high_confidence", "exact"}
    assert result.alternates[0].entry.citation_key == "weaker"
    payload = result.to_dict()
    assert payload["assessments"][0]["dimension"] == "identity_resolution"
    assert payload["assessments"][0]["rationale"] == "Bibliographic match score; not source reliability or claim support."
    assert payload["alternates"][0]["score"] == payload["assessments"][1]["value"]


def test_verification_result_to_bib_entry_contains_audit_fields():
    verifier = BibliographyVerifier()
    verifier.resolver.search_crossref = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_openalex = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_datacite = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_pubmed = lambda title, limit=5: []  # type: ignore[method-assign]

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


def test_verifier_llm_expand_only_fills_missing_fields():
    class _FakeLlmClient:
        def analyze_query(self, config, query, context):
            return {
                "title": "Expanded Title",
                "authors": ["Smith"],
                "year": "2024",
                "venue": "Journal of Tests",
                "keywords": ["echolocation", "marine"],
            }

        def rerank_candidates(self, config, query_fields, context, candidates):
            return None

    verifier = BibliographyVerifier(
        llm_config=VerificationLlmConfig(base_url="http://localhost:11434", model="qwen", role="expand"),
        llm_client=_FakeLlmClient(),
    )
    seen_titles: list[str] = []
    verifier.resolver.search_crossref = lambda title, limit=5: (seen_titles.append(title) or [])  # type: ignore[method-assign]
    verifier.resolver.search_openalex = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_datacite = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_pubmed = lambda title, limit=5: []  # type: ignore[method-assign]

    verifier.verify_string("Evans 1960", context="bottlenose dolphin echolocation")

    assert seen_titles == ["Expanded Title"]


def test_verifier_llm_rerank_only_breaks_score_ties():
    class _FakeLlmClient:
        def analyze_query(self, config, query, context):
            return None

        def rerank_candidates(self, config, query_fields, context, candidates):
            return [1, 0]

    verifier = BibliographyVerifier(
        llm_config=VerificationLlmConfig(base_url="http://localhost:11434", model="qwen", role="rerank"),
        llm_client=_FakeLlmClient(),
    )
    verifier.resolver.search_crossref = lambda title, limit=5: [  # type: ignore[method-assign]
        BibEntry(
            entry_type="article",
            citation_key="alpha",
            fields={"author": "Smith, Jane", "title": "Shared Match Primary", "year": "2024"},
        ),
        BibEntry(
            entry_type="article",
            citation_key="beta",
            fields={"author": "Smith, Jane", "title": "Shared Match Secondary", "year": "2024"},
        ),
    ]
    verifier.resolver.search_openalex = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_datacite = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_pubmed = lambda title, limit=5: []  # type: ignore[method-assign]

    result = verifier.verify_string('"Shared Match" Smith 2024')

    assert result.entry.citation_key == "beta"
    assert result.alternates[0].entry.citation_key == "alpha"


def test_verifier_llm_cannot_create_exact_without_verified_doi():
    class _FakeLlmClient:
        def analyze_query(self, config, query, context):
            return {"title": "Resolved Work", "authors": ["Smith"], "year": "2024", "venue": None, "keywords": []}

        def rerank_candidates(self, config, query_fields, context, candidates):
            return None

    verifier = BibliographyVerifier(
        llm_config=VerificationLlmConfig(base_url="http://localhost:11434", model="qwen", role="expand"),
        llm_client=_FakeLlmClient(),
    )
    verifier.resolver.search_crossref = lambda title, limit=5: [  # type: ignore[method-assign]
        BibEntry(
            entry_type="article",
            citation_key="candidate",
            fields={"author": "Smith, Jane", "title": "Resolved Work", "year": "2024"},
        )
    ]
    verifier.resolver.search_openalex = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_datacite = lambda title, limit=5: []  # type: ignore[method-assign]
    verifier.resolver.search_pubmed = lambda title, limit=5: []  # type: ignore[method-assign]

    result = verifier.verify_string("Smith 2024", context="citation graphs")

    assert result.status != "exact"


def test_llm_json_loader_accepts_fenced_payload():
    payload = '```json\n{"title":"Resolved Work","authors":["Smith"],"keywords":["graphs"]}\n```'

    result = _loads_lenient_json(payload)

    assert result["title"] == "Resolved Work"
