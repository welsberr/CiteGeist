from citegeist.bibtex import BibEntry
from citegeist.claim_support import analyze_support_gaps
from citegeist.verify import VerificationMatch, VerificationResult


class FakeVerifier:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def verify_string(self, value: str, context: str = "", limit: int = 5) -> VerificationResult:
        self.queries.append(value)
        return VerificationResult(
            query=value,
            context=context,
            status="high_confidence",
            confidence=0.91,
            entry=BibEntry(
                entry_type="article",
                citation_key="new2020support",
                fields={
                    "title": "A Better Support Paper",
                    "author": "Smith, Jane",
                    "year": "2020",
                    "doi": "10.1000/new",
                    "journal": "Journal of Better Support",
                },
            ),
            source_label="openalex:search:A Better Support Paper",
            alternates=[
                VerificationMatch(
                    entry=BibEntry(
                        entry_type="article",
                        citation_key="cited1985",
                        fields={
                            "title": "Neural computation of decisions in optimization problems",
                            "author": "Hopfield, J. J. and Tank, D. W.",
                            "year": "1985",
                        },
                    ),
                    score=0.7,
                    source_label="crossref:search:Neural computation of decisions in optimization problems",
                )
            ],
            input_type="string",
            input_key=None,
        )


def test_analyze_support_gaps_filters_existing_reference_titles():
    verifier = FakeVerifier()
    text = """
Computational research touching on movement of agents spans many different fields. Movement may not be modeled at all, but simply assigned a cost value, as in work in artificial neural systems applied to the traveling salesman problem [1].

References

[[1]]Neural computation of decisions in optimization problems
J. J. Hopfield, David W. Tank
"""
    payload = analyze_support_gaps(text, verifier=verifier, max_claims=3, min_claim_chars=40)
    assert payload["claim_count"] == 1
    assert payload["suggestion_count"] == 1
    suggestion = payload["suggestions"][0]
    assert suggestion["existing_citation_markers"] == ["1"]
    assert suggestion["existing_reference_titles"] == ["Neural computation of decisions in optimization problems"]
    assert suggestion["suggested_references"][0]["title"] == "A Better Support Paper"
    assert suggestion["needs_support_score"] > 0
    assert suggestion["suggested_references"][0]["reason"].startswith("Top candidate match.")
    titles = [item["title"] for item in suggestion["suggested_references"]]
    assert "Neural computation of decisions in optimization problems" not in titles


def test_analyze_support_gaps_groups_adjacent_uncited_claim_sentences():
    verifier = FakeVerifier()
    text = """
Our research takes an approach at an intermediate level, seeking to elucidate how evolutionary processes can result in individual control of existing movement capabilities in order to intelligently exploit environmental resources. Instead, in looking at the evolution of intelligent behavior, our primary interest is in finding out by what means less capable agents give rise to those able to appropriately exploit prevailing conditions.
"""
    payload = analyze_support_gaps(text, verifier=verifier, max_claims=2, min_claim_chars=80)
    assert payload["claim_count"] == 1
    assert payload["suggestion_count"] == 1
    suggestion = payload["suggestions"][0]
    assert suggestion["existing_citation_markers"] == []
    assert "No existing inline citation markers detected" in suggestion["note"]
    assert "Instead, in looking at the evolution of intelligent behavior" in suggestion["claim_text"]
    assert suggestion["needs_support_score"] > 3.0
    assert len(verifier.queries) == 1
    assert verifier.queries[0] == suggestion["claim_text"]


def test_analyze_support_gaps_detects_author_year_citation_forms():
    verifier = FakeVerifier()
    text = """
Computational research touching on movement of agents spans many different fields. Given that a rich repertoire of behaviors in biological organisms concerns movement, exploring the use of movement by evolving agents can open up many research questions that are directly comparable to work within biological systems (Tang and Bennett 2010).
"""
    payload = analyze_support_gaps(text, verifier=verifier, max_claims=2, min_claim_chars=60)
    assert payload["claim_count"] == 1
    assert payload["suggestion_count"] == 1
    suggestion = payload["suggestions"][0]
    assert suggestion["existing_citation_markers"] == ["(Tang and Bennett 2010)"]
    assert suggestion["existing_reference_titles"] == []
    assert "no matching reference titles were parsed" in suggestion["note"].lower()


def test_analyze_support_gaps_ranks_less_cited_claims_first():
    verifier = FakeVerifier()
    text = """
Movement may not be modeled at all, but simply assigned a cost value, as in work in artificial neural systems applied to the traveling salesman problem [1]. Our research takes an approach at an intermediate level, seeking to elucidate how evolutionary processes can result in individual control of existing movement capabilities in order to intelligently exploit environmental resources. Instead, in looking at the evolution of intelligent behavior, our primary interest is in finding out by what means less capable agents give rise to those able to appropriately exploit prevailing conditions.

References

[[1]]Neural computation of decisions in optimization problems
"""
    payload = analyze_support_gaps(text, verifier=verifier, max_claims=3, min_claim_chars=40)
    assert payload["suggestion_count"] == 2
    first, second = payload["suggestions"]
    assert first["existing_citation_markers"] == []
    assert second["existing_citation_markers"] == ["1"]
    assert first["needs_support_score"] > second["needs_support_score"]


def test_analyze_support_gaps_filters_existing_reference_dois():
    class DoiVerifier(FakeVerifier):
        def verify_string(self, value: str, context: str = "", limit: int = 5) -> VerificationResult:
            self.queries.append(value)
            return VerificationResult(
                query=value,
                context=context,
                status="high_confidence",
                confidence=0.91,
                entry=BibEntry(
                    entry_type="article",
                    citation_key="dup2020support",
                    fields={
                        "title": "A Better Support Paper Retitled",
                        "author": "Smith, Jane",
                        "year": "2020",
                        "doi": "10.1000/existing",
                        "journal": "Journal of Better Support",
                    },
                ),
                source_label="openalex:search:A Better Support Paper Retitled",
                alternates=[
                    VerificationMatch(
                        entry=BibEntry(
                            entry_type="article",
                            citation_key="novel2021support",
                            fields={
                                "title": "A Different Support Paper",
                                "author": "Doe, Alex",
                                "year": "2021",
                                "doi": "10.1000/new-distinct",
                            },
                        ),
                        score=0.7,
                        source_label="crossref:search:A Different Support Paper",
                    )
                ],
                input_type="string",
                input_key=None,
            )

    verifier = DoiVerifier()
    text = """
Computational research touching on movement of agents spans many different fields. Movement may not be modeled at all, but simply assigned a cost value, as in work in artificial neural systems applied to the traveling salesman problem [1].

References

[[1]]Existing cited paper
doi: 10.1000/existing
"""
    payload = analyze_support_gaps(text, verifier=verifier, max_claims=3, min_claim_chars=40)
    assert payload["suggestion_count"] == 1
    suggested_titles = [item["title"] for item in payload["suggestions"][0]["suggested_references"]]
    assert "A Better Support Paper Retitled" not in suggested_titles
    assert "A Different Support Paper" in suggested_titles


def test_analyze_support_gaps_includes_reason_for_alternate_candidates():
    verifier = FakeVerifier()
    text = """
Computational research touching on movement of agents spans many different fields. Movement strategies in artificial life systems can improve resource exploitation under selection pressures [1].

References

[[1]]Earlier Cited Paper
"""
    payload = analyze_support_gaps(text, verifier=verifier, max_claims=3, min_claim_chars=40)
    suggestion = payload["suggestions"][0]
    assert len(suggestion["suggested_references"]) == 2
    primary, alternate = suggestion["suggested_references"]
    assert "Top candidate match." in primary["reason"]
    assert "Alternate candidate retained after verification." in alternate["reason"]
