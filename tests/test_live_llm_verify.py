from __future__ import annotations

import os

import pytest

from citegeist.bibtex import BibEntry
from citegeist.llm_verify import VerificationLlmClient, VerificationLlmConfig


pytestmark = pytest.mark.live


def _live_llm_config() -> VerificationLlmConfig:
    return VerificationLlmConfig(
        base_url=os.environ.get("CITEGEIST_VERIFY_LLM_BASE_URL", "http://127.0.0.1:8800/v1"),
        model=os.environ.get("CITEGEIST_VERIFY_LLM_MODEL", "general_assistant"),
        api_key=os.environ.get("CITEGEIST_VERIFY_LLM_API_KEY", "change-me-client-key"),
        provider=os.environ.get("CITEGEIST_VERIFY_LLM_PROVIDER", "auto"),
        role="both",
    )


def test_live_llm_query_analysis_via_geniehive():
    client = VerificationLlmClient()
    result = client.analyze_query(
        _live_llm_config(),
        "Evans 1960",
        "marine mammals; bottlenose dolphin echolocation",
    )

    if result is None:
        pytest.skip("local GenieHive route did not return parseable JSON for query analysis")
    assert isinstance(result["authors"], list)
    assert isinstance(result["keywords"], list)


def test_live_llm_candidate_rerank_via_geniehive():
    client = VerificationLlmClient()
    candidates = [
        BibEntry(
            entry_type="article",
            citation_key="candidate_a",
            fields={
                "author": "Doe, Jane",
                "title": "General Marine Biology Survey",
                "year": "1960",
                "journal": "Marine Science",
            },
        ),
        BibEntry(
            entry_type="article",
            citation_key="candidate_b",
            fields={
                "author": "Evans, William",
                "title": "Echolocation by marine dolphins",
                "year": "1960",
                "journal": "Journal of the Acoustical Society",
            },
        ),
    ]

    result = client.rerank_candidates(
        _live_llm_config(),
        {
            "title": "",
            "authors": ["Evans"],
            "year": "1960",
            "venue": "",
        },
        "bottlenose dolphin echolocation",
        candidates,
    )

    if result is None:
        pytest.skip("local GenieHive route did not return parseable JSON for candidate reranking")
    assert result
    assert all(isinstance(index, int) for index in result)
