# citegeist

`citegeist` is a research-oriented bibliography workbench for building, expanding, and auditing BibTeX libraries.

The aim is not just to store citations. The aim is to help with the harder problem: finding, improving, connecting, and checking the literature around a topic while keeping BibTeX as a first-class output format.

## Repo Description

`citegeist` is a BibTeX-native research tool for citation extraction, metadata enrichment, citation-graph expansion, and semantic search over scholarly sources.

## Scope

The project is intended to support a workflow like this:

1. Start from rough references extracted from papers, notes, syllabi, or dissertations.
2. Convert them into draft BibTeX entries.
3. Enrich and correct those entries using external scholarly metadata sources.
4. Persist entries, identifiers, abstracts, and citation edges in a local database.
5. Traverse the citation graph outward to discover additional relevant works.
6. Search the local corpus semantically using abstracts and extracted full text.
7. Export verified results back into BibTeX for LaTeX use.

## Why A New Codebase

This repository starts cleanly rather than extending the older `bib/` toolkit directly.

The older toolkit is useful as prior art:

- it demonstrates identifier-driven metadata augmentation;
- it caches PDFs and extracted plaintext;
- it shows one workable model for bibliography growth.

But it is not the right long-term base:

- it is Python 2-era code;
- it is shell-script centric;
- it does not provide a normalized database for graph workflows;
- it is not structured as a reusable Python 3 library.

`citegeist` keeps the useful ideas and rebuilds the foundation around a cleaner Python 3 package boundary.

## Current Status

The initial repo includes:

- `pybtex`-backed BibTeX parsing and export in a repo-local virtual environment;
- a SQLite-backed bibliography store;
- a small CLI for ingest, search, inspection, and export;
- review-state tracking on entries, per-field ingest provenance, and field-level conflict review;
- plaintext reference extraction into draft BibTeX for numbered, APA-like, wrapped-line, and simple book-style references;
- identifier-first metadata resolution for DOI, OpenAlex, DBLP, arXiv, and DataCite-backed entries, with OpenAlex/DataCite title-search fallback;
- local citation-graph traversal over stored `cites`, `cited_by`, and `crossref` edges;
- Crossref- and OpenAlex-backed graph expansion that materializes draft related works and edge provenance;
- a dedicated source-client layer with fixture/cache support for live-source development;
- OAI-PMH Dublin Core harvesting for institutional repositories and thesis/dissertation sources;
- OAI-PMH repository discovery via `Identify`, `ListSets`, and `ListMetadataFormats` to target harvests more precisely;
- bibliography bootstrap workflows that can start from a seed `.bib`, a topic phrase, or both;
- batch bootstrap orchestration from JSON job files containing seed BibTeX paths, topic phrases, or both;
- normalized tables for entries, creators, identifiers, and citation relations;
- full-text-search-ready indexing over title, abstract, and fulltext when SQLite FTS5 is available;
- tests covering parsing, ingestion, relation storage, and search.

Example applications live alongside the core package rather than defining it. Current examples include:

- a comprehensive CLI cookbook in [examples/cli/README.md](./examples/cli/README.md);
- a topic-only bootstrap workflow for `artificial life` in [examples/artificial-life/README.md](./examples/artificial-life/README.md);
- the TalkOrigins bibliography pipeline under [`citegeist.examples.talkorigins`](./src/citegeist/examples/talkorigins.py) with a usage guide in [examples/talkorigins/README.md](./examples/talkorigins/README.md).

The prioritized execution plan lives in [ROADMAP.md](./ROADMAP.md).

## Layout

```text
citegeist/
  src/citegeist/
    bibtex.py
    examples/
    storage.py
  tests/
    test_storage.py
  pyproject.toml
```

## Quick Start

```bash
cd citegeist
python3 -m virtualenv --always-copy .venv
.venv/bin/pip install -e .
.venv/bin/pip install pytest
mkdir -p .cache/citegeist
PYTHONPATH=src .venv/bin/python - <<'PY'
from citegeist import BibliographyStore

bib = """
@article{smith2024graphs,
  author = {Smith, Jane and Doe, Alex},
  title = {Graph-first bibliography augmentation},
  year = {2024},
  abstract = {We study citation graphs for literature discovery.},
  references = {miller2023search}
}

@inproceedings{miller2023search,
  author = {Miller, Sam},
  title = {Semantic search for research corpora},
  year = {2023},
  abstract = {Dense retrieval improves recall for academic search.}
}
"""

store = BibliographyStore("library.sqlite3")
store.ingest_bibtex(bib)
print(store.get_relations("smith2024graphs"))
print(store.search_text("semantic"))
store.close()
PY
.venv/bin/python -m pytest -q
```

Or use the CLI directly:

```bash
cd citegeist
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 ingest references.bib
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 search "semantic search"
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 search "origin" --topic abiogenesis
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 show --provenance --conflicts smith2024graphs
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 set-status smith2024graphs reviewed
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 resolve-conflicts smith2024graphs title accepted
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 apply-conflict smith2024graphs title
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 bootstrap --seed-bib seed.bib --topic "bayesian nonparametrics"
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 bootstrap --topic "bayesian nonparametrics" --preview --topic-commit-limit 5
PYTHONPATH=src .venv/bin/python -m citegeist extract references.txt --output draft.bib
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 resolve smith2024graphs
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 resolve-stubs --doi-only --preview --limit 25
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 resolve-stubs --doi-only --all-misc --limit 25
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 topics
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 topic-entries abiogenesis
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 export-topic abiogenesis --output abiogenesis.bib
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 graph smith2024graphs --relation cites --depth 2 --missing-only
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 graph smith2024graphs --relation cites --depth 2 --format json-graph
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 graph smith2024graphs --relation cites --depth 2 --format dot
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 graph smith2024graphs --relation cites --depth 2 --format dot --output graph.dot
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 graph smith2024graphs --relation cites --depth 2 --format json-graph --output graph.json
PYTHONPATH=src .venv/bin/python -m citegeist graph-view graph.json --output graph.html --title "CiteGeist Graph"
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 expand smith2024graphs --source crossref
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 expand smith2024graphs --source openalex --relation cited_by --limit 10
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 expand-topic abiogenesis --topic-phrase "abiogenesis origin chemistry" --source openalex --relation cites --seed-key seed2024 --min-relevance 0.3 --preview
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 set-topic-phrase abiogenesis "abiogenesis origin chemistry prebiotic"
PYTHONPATH=src .venv/bin/python -m citegeist discover-oai https://example.edu/oai
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 harvest-oai https://example.edu/oai --metadata-prefix mods --from 2024-01-01 --until 2024-12-31 --limit 10
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 export --output reviewed.bib
```

For a fuller option-by-option CLI cookbook, see [examples/cli/README.md](./examples/cli/README.md).

Broad BibTeX exports skip DOI-only placeholder records such as `Referenced work N` by default. Use `--include-stubs` on `export` or `export-topic` if you want those entries included anyway.

Long-running CLI commands report progress on `stderr` so `stdout` remains clean for JSON, BibTeX, or tabular output.

Crossref reference expansion is intentionally conservative about weak discoveries. If a cited reference has no DOI and Crossref only exposes it as an unstructured citation blob, `expand --source crossref`, `expand-topic --source crossref`, and bootstrap flows now skip materializing that record unless the fallback metadata looks like a cleaner non-`misc` work such as conference proceedings. This reduces junk `@misc` entries whose `title` field is really a pasted citation string.

For live-source development, prefer fixture-backed or cache-backed source clients so resolver and expansion work can be exercised repeatedly without re-hitting upstream APIs on every run.

## Example Application

- Use `stage-topic-phrases` to load those suggestions into the database as review items. Staging stores the candidate in `suggested_phrase` and marks the topic `pending` without changing the active `expansion_phrase`.

- Use `export-topic-phrase-reviews` to write an editable JSON template directly from the database for the currently staged suggestions. That gives you a round-trip path from DB review queue to file edits and back into `review-topic-phrases`.
- Use `review-topic-phrase` to accept or reject one staged suggestion in place. Accepting a suggestion copies it into `expansion_phrase` and clears it from the staged review queue; rejecting it preserves the staged suggestion together with its review state.
- Use `review-topic-phrases` when you want to apply many accept/reject decisions from one JSON file. Each item should carry `slug`, `status`, and optional `phrase` / `review_notes`.
- Use `apply-topic-phrases` when you want a direct patch path instead of the staged review flow. It accepts either the raw suggestion list or an object with a `topics` list, and will apply `suggested_phrase` or `phrase` to matching topic slugs immediately.
- Use `topic-phrase-reviews --phrase-review-status pending` when you want a compact audit view of unresolved staged suggestions, including both the current live phrase and the pending replacement.
- Use `enrich-talkorigins` when you want to target those weak canonical entries for resolver-based metadata upgrades before retrying graph expansion on imported topic slices.
- Use `review-talkorigins` when you want one JSON review artifact that combines weak canonical clusters with dry-run enrichment outcomes for manual cleanup.
- Use `expand-topic` when you already have both a topic phrase and a curated topic seed set in the database: it expands outward from the topic’s existing entries, then only assigns discovered works back to that topic if they clear a topic-relevance threshold. Write-enabled assignment is stricter than preview ranking: a candidate must clear the score threshold and show a non-generic title anchor to the topic phrase, so broad methods papers do not get attached just because their abstracts or related terms overlap. On large noisy topics, prefer `--seed-key` to restrict the run to just the trusted seed entries you want to expand from, and use `--preview` first to inspect discovered candidates and relevance scores before writing anything.

- Use `set-topic-phrase` to store a curated expansion phrase on the topic itself. When a stored phrase exists, `expand-topic` will use it automatically if you do not pass `--topic-phrase`. Batch bootstrap jobs can also set `topic_slug`, `topic_name`, and `topic_phrase` so curated topic metadata is created as part of the run.
- Use `topics --phrase-review-status pending` when you want to audit only topics whose staged phrase suggestions still need review.
- `--allow-unsafe-search-matches` exists only for bounded experiments on copied databases when you explicitly want to relax trust to exercise downstream expansion behavior.

The TalkOrigins corpus pipeline remains in the repository as an example application rather than a core package surface. Use the example-scoped Python namespace:

```python
from citegeist.examples.talkorigins import TalkOriginsScraper
```

and the example-scoped CLI commands:

```bash
PYTHONPATH=src .venv/bin/python -m citegeist example-talkorigins-scrape talkorigins-out --limit-topics 5 --limit-entries-per-topic 20
PYTHONPATH=src .venv/bin/python -m citegeist example-talkorigins-validate talkorigins-out/talkorigins_manifest.json
PYTHONPATH=src .venv/bin/python -m citegeist example-talkorigins-duplicates talkorigins-out/talkorigins_manifest.json --limit 20 --preview --weak-only
```

The older `scrape-talkorigins`-style command names remain available as compatibility aliases. The full example workflow and reconstruction notes live in [examples/talkorigins/README.md](./examples/talkorigins/README.md).

For a smaller example that starts from a topic phrase alone, see [examples/artificial-life/README.md](./examples/artificial-life/README.md).

Correction files are simple JSON:

```json
{
  "corrections": [
    {
      "key": "smith jane|1999|weak duplicate",
      "entry_type": "article",
      "review_status": "reviewed",
      "fields": {
        "journal": "Journal of Better Metadata",
        "doi": "10.1000/weak",
        "note": null
      }
    }
  ]
}
```

`fields` values overwrite the canonical entry for that duplicate-cluster key. Set a field to `null` to remove it.

Live-source workflow:

```bash
cd citegeist
export CITEGEIST_SOURCE_CACHE=.cache/citegeist
export CITEGEIST_LIVE_TESTS=1
PYTHONPATH=src .venv/bin/python -m pytest -m live -q
PYTHONPATH=src .venv/bin/python scripts/live_smoke.py
```

By default, live tests are skipped. They only run when `CITEGEIST_LIVE_TESTS=1` is set.

Convenience targets:

```bash
make test
make test-live
make live-smoke
```

## Near-Term Priorities

- source adapters beyond OAI-PMH for additional non-DOI scholarly ecosystems.

See [ROADMAP.md](./ROADMAP.md) for the prioritized phase plan and rationale.

## Naming

The name is intended to be short, distinct, and memorable:

- `cite` for citation work;
- `geist` for the organizing intelligence around the literature.
