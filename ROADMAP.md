# Roadmap

This roadmap prioritizes a usable local research workflow over breadth of integrations.

The first objective is not to support every metadata source. The first objective is to make one end-to-end path work reliably:

1. ingest draft references,
2. normalize and store them,
3. enrich them,
4. traverse citation links,
5. export reviewed BibTeX.

## Prioritization Principles

- prioritize steps that make the system usable by a single researcher on a local machine;
- prioritize deterministic infrastructure before network integrations;
- keep every stage inspectable and auditable;
- treat verification and provenance as core features, not cleanup work;
- defer heavy semantic infrastructure until the local corpus model is stable.

## Current Baseline

Completed:

- lightweight BibTeX parsing;
- SQLite storage for entries, creators, identifiers, and relations;
- local text search using SQLite FTS5 when available;
- tests for ingest, relation storage, and search.

## Phase 1: Core Ingestion And Export

Priority: P0

Goal:
Make `citegeist` useful as a local BibTeX workbench even before online enrichment is added.

Tasks:

- add BibTeX export from the normalized database back into stable, readable BibTeX;
- add a small CLI for `ingest`, `show`, `search`, and `export`;
- store field provenance metadata alongside imported and edited fields;
- add schema support for entry status such as `draft`, `enriched`, `reviewed`, and `exported`;
- add fixture-driven tests for round-tripping BibTeX through ingest and export.

Why this comes first:

- without export, the project is not yet useful in a LaTeX workflow;
- without a CLI, the package is a library demo rather than a tool;
- without provenance and state, later enrichment work becomes hard to audit.

Exit criteria:

- a user can ingest a `.bib` file, inspect entries, search locally, and export a reviewed `.bib`;
- round-trip tests show no unexpected field loss for supported entry types.

## Phase 2: Reference Extraction

Priority: P0

Goal:
Turn raw reference text into draft entries that can enter the main pipeline.

Tasks:

- add parsers for bibliography-section lines and plain-text reference lists;
- define a draft-entry schema for incomplete references with confidence markers;
- support ingestion of OCR- or PDF-derived plaintext bibliography sections;
- add normalization for author names, years, title casing, and page ranges;
- prefer sentence-boundary venue detection over naive keyword splits so title text containing words like `report` is not truncated;
- repair partially extracted venue stubs such as `Occas.` or `Proc.` by reparsing the full raw reference line when the structured fields are obviously incomplete;
- preserve improved local draft parses even when remote enrichment remains unresolved, so later parser fixes can refresh stored BibTeX without requiring a successful metadata match;
- build gold-test fixtures from real, messy reference examples.

Why this is next:

- this addresses the project’s first unique bottleneck: getting rough references into structured form;
- enrichment is much more effective once draft references are normalized.

Exit criteria:

- a user can pass a plaintext bibliography section and receive draft BibTeX entries with unresolved fields clearly marked;
- tests cover common article, book, chapter, proceedings, report, and abbreviation-heavy legacy references.

## Phase 3: Metadata Enrichment

Priority: P1

Goal:
Resolve draft or partial entries against external scholarly sources and merge improved metadata safely.

Tasks:

- define a resolver interface with deterministic merge rules;
- implement first-party resolvers for DOI/Crossref, DBLP, and arXiv;
- add identifier-first resolution, then title/author/year fallback search;
- store merge provenance per field and resolution attempt logs;
- flag conflicts rather than silently overwriting disputed values.

Why this is P1 rather than the first phase:

- enrichment quality depends on the ingestion and provenance model being correct first;
- it is easier to test deterministic merge behavior once local workflows already exist.

Exit criteria:

- an incomplete entry can be enriched from at least one authoritative source;
- conflicting fields remain visible for review instead of being lost.

## Phase 4: Citation Graph Expansion

Priority: P1

Goal:
Use citation edges as a discovery engine rather than just metadata storage.

Tasks:

- support explicit `cites` and `cited_by` edge ingestion with source provenance;
- add graph expansion commands starting from one or more seed entries;
- track edge discovery source, timestamp, and confidence;
- add filters for depth, source type, year range, and reviewed status;
- expose unresolved nodes so the user can decide what to enrich next.

Why this matters:

- this is central to literature discovery rather than mere bibliography cleanup;
- it turns the database into a research navigation tool.

Exit criteria:

- starting from one or more seed entries, a user can expand outward through citation edges and persist newly discovered nodes;
- graph traversal results can be exported as BibTeX candidates for review.

## Phase 5: Search And Ranking

Priority: P2

Goal:
Improve discovery quality inside the local corpus.

Tasks:

- refine FTS ranking across title, abstract, keywords, and fulltext;
- add saved search queries and result filters;
- add optional embedding-backed semantic search behind a pluggable interface;
- support hybrid ranking that combines lexical matching, identifiers, and citation proximity;
- add benchmarking fixtures for retrieval quality on a few research topics.

Why this is later:

- FTS is already enough to support early workflows;
- embedding infrastructure is expensive and should wait until the corpus schema stabilizes.

Exit criteria:

- local search is useful on realistic corpora without requiring external services;
- semantic indexing is optional and does not displace the simpler local search path.

## Phase 6: Corpus Acquisition Pipelines

Priority: P2

Goal:
Broaden source acquisition without mixing that complexity into the core model.

Tasks:

- add source adapters for open-access theses and dissertation repositories;
- add support for harvesting publisher citation pages and preprint metadata pages;
- define per-source import provenance and rate-limit behavior;
- separate source-specific scraping logic from normalized entry storage;
- add regression fixtures for representative public sources.

Why this is later:

- acquisition breadth is useful, but only after the core ingest/enrich/review loop is solid;
- source adapters are brittle and should sit on top of a stable model.

Exit criteria:

- new public corpora can be imported through adapters without changing the storage core;
- imported entries retain their source provenance and can be reviewed like any other entry.

## Suggested Next Three Tasks

1. Add a CLI module with `ingest`, `search`, `show`, and `export`.
2. Implement BibTeX export from the normalized store.
3. Add provenance tables and entry review status fields.

These three tasks complete the first usable local workflow and should be treated as the immediate sprint.
