from __future__ import annotations

import argparse
import json
import os

from citegeist import MetadataResolver, SourceClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run live smoke checks against scholarly metadata sources")
    parser.add_argument(
        "--cache-dir",
        default=os.environ.get("CITEGEIST_SOURCE_CACHE", ".cache/citegeist"),
        help="Directory for cached live-source responses",
    )
    parser.add_argument(
        "--fixtures-dir",
        default=os.environ.get("CITEGEIST_SOURCE_FIXTURES"),
        help="Optional fixture directory to read before live network calls",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = SourceClient(cache_dir=args.cache_dir, fixtures_dir=args.fixtures_dir)
    resolver = MetadataResolver(source_client=client)

    checks = {
        "crossref_doi": resolver.resolve_doi("10.1038/nphys1170"),
        "arxiv_id": resolver.resolve_arxiv("1706.03762"),
        "openalex_search": resolver.search_openalex_best_match(
            title="Attention Is All You Need",
            author_text="Ashish Vaswani",
            year="2017",
        ),
    }

    payload = {}
    for name, resolution in checks.items():
        payload[name] = None
        if resolution is not None:
            payload[name] = {
                "source_label": resolution.source_label,
                "title": resolution.entry.fields.get("title"),
                "year": resolution.entry.fields.get("year"),
                "doi": resolution.entry.fields.get("doi"),
                "openalex": resolution.entry.fields.get("openalex"),
                "arxiv": resolution.entry.fields.get("arxiv"),
            }

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
