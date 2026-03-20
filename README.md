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

- a lightweight BibTeX parser for structured ingestion;
- a SQLite-backed bibliography store;
- normalized tables for entries, creators, identifiers, and citation relations;
- full-text-search-ready indexing over title, abstract, and fulltext when SQLite FTS5 is available;
- tests covering parsing, ingestion, relation storage, and search.

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
PYTHONPATH=src python3 - <<'PY'
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
pytest -q
```

## Planned Work

- parse references from raw prose, OCR, PDF text, and bibliography sections into draft BibTeX;
- add modern metadata resolvers for DOI, Crossref, DBLP, arXiv, and similar sources;
- track provenance and confidence for enriched fields;
- add graph expansion workflows over `cites` and `cited_by` edges;
- support acquisition pipelines for open-access theses, dissertations, preprints, and publisher metadata pages;
- add embeddings or pluggable semantic indexing beyond SQLite FTS.

## Naming

The name is intended to be short, distinct, and memorable:

- `cite` for citation work;
- `geist` for the organizing intelligence around the literature.
