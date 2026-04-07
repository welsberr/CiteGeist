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
- staged plaintext reference extraction that now preserves more structured metadata from legacy references, including year suffixes, identifiers, volume/issue/pages, and thesis/report/web-style venue hints;
- a reference-extraction backend seam with the local `heuristic` parser as the default implementation, so optional external backends can be added later without changing the core extract workflow;
- standalone verification and disambiguation of free-text references or partial BibTeX into auditable BibTeX/JSON results with `x_status`, `x_confidence`, `x_source`, `x_query`, and alternate-candidate traces;
- identifier-first metadata resolution for DOI, PMID/PubMed, OpenAlex, DBLP, arXiv, and DataCite-backed entries, with OpenAlex/DataCite/PubMed title-search fallback;
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
- a browser-oriented literature explorer demo with a small HTTP bridge, static HTML/JS shell, and lightweight graph view in [examples/literature-explorer/README.md](./examples/literature-explorer/README.md);
- the TalkOrigins bibliography pipeline under [`citegeist.examples.talkorigins`](./src/citegeist/examples/talkorigins.py) with a usage guide in [examples/talkorigins/README.md](./examples/talkorigins/README.md).

The prioritized execution plan lives in [ROADMAP.md](./ROADMAP.md).

## Status Assessment

`citegeist` is no longer just a storage-and-export skeleton. It now covers the main early pipeline the project set out to make usable on one local machine:

1. ingest or extract rough references,
2. verify and improve them before trust is assumed,
3. normalize and store them with provenance,
4. expand outward through citation links,
5. review and export BibTeX again.

In practical terms, the strongest implemented areas are now:

- BibTeX-native local storage, review state, provenance tracking, and export;
- rough-reference handling through both heuristic extraction and standalone verification/disambiguation;
- conservative metadata enrichment and citation-graph expansion from scholarly APIs;
- fixture-backed parser and source-client workflows that keep improvement work auditable;
- a lightweight local demo surface for topic discovery, topic expansion, extraction, verification, and graph inspection in the browser without introducing a full web framework dependency.

The main gaps are no longer the basic pipeline. The main gaps are evaluation depth and researcher ergonomics: broader regression fixtures, clearer comparative quality measurement across parsers/resolvers, stronger review workflows for larger corpora, and a richer review UI than the current demonstration shell.

## Positioning

Compared with other bibliographic tooling, `citegeist` is strongest when bibliography work starts messy and needs to become structured:

- Against reference managers such as Zotero or JabRef, `citegeist` is currently weaker as a polished day-to-day library manager or sync-oriented desktop app, but stronger as a BibTeX-first command-line workbench for extraction, repair, provenance, and graph-oriented discovery.
- Against parser-focused tools such as AnyStyle, GROBID, or ParsCit-style systems, `citegeist` is not trying to outcompete them as a dedicated citation parser. Instead, it now uses their staged-parsing ideas and can optionally call external parsers while keeping a local default parser and a normalized BibTeX-oriented downstream workflow.
- Against verifier/disambiguator workflows like `VeriBib`, `citegeist` now covers the same high-value pre-ingest verification pattern, but places it inside a broader local pipeline that also stores results, resolves identifiers, expands citation graphs, and exports reviewed BibTeX.
- Against process-heavy corpus updaters like `TOA-Bib-Updater`, `citegeist` now adopts the useful operational pattern of staged artifacts and reviewable outputs, but keeps the core centered on reusable library/database primitives rather than one source-specific acquisition script.

The clearest differentiator at this point is integration. `citegeist` is becoming a local bibliography workbench that combines extraction, verification, enrichment, graph expansion, topic-aware review, and BibTeX export in one toolchain rather than treating those as unrelated utilities.

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
PYTHONPATH=src .venv/bin/python -m citegeist extract references.txt --backend heuristic --output draft.bib
PYTHONPATH=src .venv/bin/python -m citegeist compare-extract references.txt --backend heuristic --backend anystyle --output compare.json
PYTHONPATH=src .venv/bin/python -m citegeist compare-extract references.txt --backend heuristic --backend grobid --summary --output compare-summary.json
PYTHONPATH=src .venv/bin/python -m citegeist compare-extract references.txt --backend heuristic --backend grobid --summary --max-rows-with-differences 0 --output compare-check.json
PYTHONPATH=src .venv/bin/python -m citegeist verify --string '"Graph-first bibliography augmentation" Smith 2024' --context "citation graphs" --format json
PYTHONPATH=src .venv/bin/python -m citegeist verify --bib draft.bib --output verified.bib
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

BibTeX parse/render round-trips normalize simple escaped special characters such as `\_`, `\&`, and `\%` back to plain field values internally, then re-escape them on export. This prevents repeated commands such as `resolve` from turning a valid field like `discovered\_from = {...}` into `discovered\\_from = {...}` after rewriting an entry.

Crossref reference expansion is intentionally conservative about weak discoveries. If a cited reference has no DOI and Crossref only exposes it as an unstructured citation blob, `expand --source crossref`, `expand-topic --source crossref`, and bootstrap flows now skip materializing that record unless the fallback metadata looks like a cleaner non-`misc` work such as conference proceedings. When Crossref does expose thesis or dissertation references only as unstructured text, citegeist now also tries to extract the actual work title instead of keeping the entire ProQuest-style citation blob in the `title` field. This reduces junk `@misc` entries and cleaner `@phdthesis` fallbacks whose `title` field is really a pasted citation string.

OpenAlex expansion is also conservative about noisy secondary records. Discoveries now prefer DOI-based citation keys when a DOI is present, which reduces parallel `doi...` and `openalex...` entries for the same work. OpenAlex abstract imports are sanitized to drop obvious webpage/export blobs, and DOI-less records are filtered when they look like venue-title stubs, generic container records, or weak review-like shadows of an already present book, chapter, proceedings paper, or dissertation with the same title. Both OpenAlex and Crossref discovery paths also normalize some malformed author strings from upstream metadata, including inverted-initial patterns such as `J., Fogel L.`, into stable BibTeX names like `Fogel, L. J.`. Preview mode uses the same admission rules as write-enabled expansion, so rejected candidates disappear before you commit them to the store.

For live-source development, prefer fixture-backed or cache-backed source clients so resolver and expansion work can be exercised repeatedly without re-hitting upstream APIs on every run.

## Adopted Ideas From Earlier Repos

`citegeist` now absorbs two useful patterns from adjacent bibliography tools while keeping them inside the main Python 3 package boundary:

- From `VeriBib`: a standalone `verify` workflow for ambiguous strings or rough BibTeX, with explicit confidence/status audit fields and alternate-candidate traces before you commit changes to the main library.
- From `TOA-Bib-Updater`: resumable, artifact-oriented corpus processing remains the preferred process model for large imports. In practice this already appears in the TalkOrigins example pipeline through saved manifests, review exports, duplicate reports, and staged topic-phrase review flows.

Those ideas are now implemented enough to matter operationally, not just directionally: `VeriBib`'s main contribution has become a core `verify` command, while `TOA-Bib-Updater`'s main contribution remains process shape and review artifacts rather than parser or storage internals.

## Parsing Sources

The plaintext-reference parser is still local and heuristic-first, but its current direction explicitly borrows ideas from earlier citation-parsing work:

- Conceptual influence: GROBID's staged parsing model and bibliographical-reference annotation guidance informed the split between reference-block segmentation, field extraction, and metadata recovery, especially for identifiers, year variants, and venue/page structure.
- Conceptual influence: AnyStyle and ParsCit informed the emphasis on treating reference parsing as a separable stage with gold-fixture-driven improvement rather than a one-pass punctuation split.
- In-repo code prior art: some of the newer heuristics were adapted from existing CiteGeist code in [`src/citegeist/talkorigins.py`](./src/citegeist/talkorigins.py) and [`src/citegeist/expand.py`](./src/citegeist/expand.py), particularly around entry-type guessing, fragment cleanup, and thesis/report handling for citation-like blobs.

External references used for the current parser direction:

- GROBID principles and parsing architecture: <https://grobid.readthedocs.io/en/latest/Principles/>
- GROBID bibliographical-reference annotation notes: <https://grobid.readthedocs.io/en/latest/training/Bibliographical-references/>
- AnyStyle project: <https://github.com/inukshuk/anystyle>
- ParsCit paper: <https://aclanthology.org/L08-1291/>

The built-in extraction backends are:

- `heuristic`: the default local parser, always available
- `anystyle`: an optional adapter around the AnyStyle CLI when `anystyle` is installed locally
- `grobid`: an optional adapter around a running GROBID service using `/api/processCitationList`

The backend interface exists so future GROBID- or other parser adapters can be registered without replacing the local parser or changing the CLI contract.

To compare backend output on the same plaintext references, use `compare-extract`. It aligns entries by ordinal/reference block and emits JSON with per-backend payloads plus a `differing_fields` summary for each row. Add `--summary` when you want a compact evaluation artifact with disagreement counts by field and backend presence counts instead of the full row-by-row payload. Add `--max-rows-with-differences` and/or `--max-field-difference-count` when you want CI-style failure thresholds; the command will emit the summary JSON and return a nonzero exit code if the limits are exceeded.

For regression-oriented parser work, keep a small curated plaintext fixture set and run `compare-extract` against multiple backends before changing heuristics. That makes backend disagreement explicit and gives you a stable review artifact for parser changes.

For the optional AnyStyle backend, install the CLI separately and then run:

```bash
PYTHONPATH=src .venv/bin/python -m citegeist extract references.txt --backend anystyle --output draft.bib
```

If the binary is not on `PATH`, set `CITEGEIST_ANYSTYLE_BIN=/path/to/anystyle`. If you want a custom AnyStyle parser model, set `CITEGEIST_ANYSTYLE_PARSER_MODEL=/path/to/model.mod`.

For the optional GROBID backend, start a GROBID service and then run:

```bash
PYTHONPATH=src .venv/bin/python -m citegeist extract references.txt --backend grobid --output draft.bib
```

By default CiteGeist targets `http://127.0.0.1:8070`. Override that with `CITEGEIST_GROBID_URL=http://host:port` if your service is elsewhere.

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
