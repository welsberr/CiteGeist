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
- review-state tracking on entries and per-field ingest provenance;
- first-pass plaintext reference extraction into draft BibTeX;
- identifier-first metadata resolution for DOI, DBLP, and arXiv-backed entries;
- local citation-graph traversal over stored `cites`, `cited_by`, and `crossref` edges;
- Crossref-backed graph expansion that materializes draft referenced works and edge provenance;
- normalized tables for entries, creators, identifiers, and citation relations;
- full-text-search-ready indexing over title, abstract, and fulltext when SQLite FTS5 is available;
- tests covering parsing, ingestion, relation storage, and search.

The prioritized execution plan lives in [ROADMAP.md](./ROADMAP.md).

## Layout

```text
citegeist/
  src/citegeist/
    bibtex.py
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
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 show --provenance smith2024graphs
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 set-status smith2024graphs reviewed
PYTHONPATH=src .venv/bin/python -m citegeist extract references.txt --output draft.bib
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 resolve smith2024graphs
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 graph smith2024graphs --relation cites --depth 2 --missing-only
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 expand smith2024graphs --source crossref
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 export --output reviewed.bib
```

## Near-Term Priorities

- stronger plaintext extraction coverage for more citation styles;
- richer graph expansion from additional external citation sources.

See [ROADMAP.md](./ROADMAP.md) for the prioritized phase plan and rationale.

## Naming

The name is intended to be short, distinct, and memorable:

- `cite` for citation work;
- `geist` for the organizing intelligence around the literature.
