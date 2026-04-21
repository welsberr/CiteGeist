from __future__ import annotations

import argparse
import json
import os

from citegeist.bibtex import BibEntry
from citegeist.llm_verify import VerificationLlmClient, VerificationLlmConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run live LLM verify smoke checks against a local OpenAI-compatible endpoint")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("CITEGEIST_VERIFY_LLM_BASE_URL", "http://127.0.0.1:8800/v1"),
        help="OpenAI-compatible or Ollama base URL",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("CITEGEIST_VERIFY_LLM_MODEL", "general_assistant"),
        help="Model or route ID exposed by the local endpoint",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("CITEGEIST_VERIFY_LLM_API_KEY", "change-me-client-key"),
        help="Optional API key for the local endpoint",
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("CITEGEIST_VERIFY_LLM_PROVIDER", "auto"),
        choices=["auto", "openai", "ollama-native"],
        help="Endpoint protocol style",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = VerificationLlmClient()
    config = VerificationLlmConfig(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        provider=args.provider,
        role="both",
    )

    analysis = client.analyze_query(
        config,
        "Evans 1960",
        "marine mammals; bottlenose dolphin echolocation",
    )
    rerank = client.rerank_candidates(
        config,
        {"title": "", "authors": ["Evans"], "year": "1960", "venue": ""},
        "bottlenose dolphin echolocation",
        [
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
        ],
    )

    print(
        json.dumps(
            {
                "base_url": args.base_url,
                "model": args.model,
                "analysis": analysis,
                "rerank": rerank,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
