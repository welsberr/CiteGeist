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
- CLI workflows for ingest, inspect, search, export, conflict review, bootstrap, graph traversal, expansion, OAI discovery/harvest, extraction, verification, and extraction-backend comparison;
- entry review-state tracking plus field-level provenance and conflict handling;
- plaintext reference extraction with a staged heuristic parser that preserves identifiers, year suffixes, volume/issue/pages, and thesis/report/web-style hints;
- optional extraction backends for AnyStyle and GROBID behind explicit backend selection, with shared normalization back into CiteGeist draft-entry conventions;
- backend comparison, summary, and threshold-check workflows for parser regression/evaluation;
- standalone verification/disambiguation output for free-text references and partial BibTeX with auditable match metadata;
- identifier-first metadata resolution plus title-search fallback across DOI, OpenAlex, DBLP, arXiv, and DataCite-backed flows;
- citation-graph expansion and topic-oriented bootstrap/expansion workflows;
- OAI-PMH repository discovery and harvesting for external corpus acquisition;
- tests for ingest, relation storage, and search.

In effect, Phases 1 and 2 are largely in place, and substantial parts of Phases 3, 4, and 6 already exist in usable form. The roadmap is now less about creating the first end-to-end path and more about improving quality, evaluation, and larger-corpus review discipline.

## Comparison Notes From Related Repos

The adjacent `TOA-Bib-Updater` and `VeriBib` repositories are useful prior art, but they contribute different things:

- `VeriBib` contributes a good pre-ingest verification pattern: inspect ambiguous strings or partial BibTeX, rank candidates from legal metadata sources, and emit explicit audit fields instead of silently trusting a single match.
- `TOA-Bib-Updater` contributes process discipline more than core data modeling: resumable long-running jobs, preserved source artifacts, and generated review outputs for manual inspection.

`citegeist` should absorb those ideas where they improve the main local research workflow:

1. keep verification and auditability in the core package, not just entry resolution after ingest;
2. keep resumable manifests and review exports for large acquisition workflows, especially example pipelines and batch imports;
3. avoid coupling the core model to brittle source-specific scraping logic.

## Source Notes

Reference-extraction planning in this repository currently draws on both external and internal prior art:

- External conceptual sources: GROBID, AnyStyle, and ParsCit are the main references for staged citation parsing, token/field separation, and gold-fixture-driven improvement.
- Internal code sources: the plaintext extractor should continue to reuse and consolidate heuristics already present in `citegeist.talkorigins` and `citegeist.expand` where those routines solve overlapping problems such as thesis/report classification, fragment cleanup, or citation-blob handling.

This project should acknowledge those influences in code comments and docs when parser behavior is intentionally adapted from them.

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

Status:
Largely complete. Remaining work here is mostly refinement: export fidelity on edge cases, review ergonomics, and better audit/report surfaces rather than missing core capability.

## Phase 2: Reference Extraction

Priority: P0

Goal:
Turn raw reference text into draft entries that can enter the main pipeline.

Tasks:

- add parsers for bibliography-section lines and plain-text reference lists;
- define a draft-entry schema for incomplete references with confidence markers;
- support ingestion of OCR- or PDF-derived plaintext bibliography sections;
- add normalization for author names, years, title casing, and page ranges;
- keep the parser staged internally so segmentation, field parsing, and later optional external backends remain separable;
- keep the local heuristic parser as the default path even if optional external backends are added later;
- support optional external parser adapters only behind explicit backend selection, so local workflows still work without Ruby/Java services;
- when adding external backends, normalize their outputs back into the same draft-entry conventions used by the local parser;
- prefer sentence-boundary venue detection over naive keyword splits so title text containing words like `report` is not truncated;
- repair partially extracted venue stubs such as `Occas.` or `Proc.` by reparsing the full raw reference line when the structured fields are obviously
 incomplete;
- preserve improved local draft parses even when remote enrichment remains unresolved, so later parser fixes can refresh stored BibTeX without requiring a successful metadata match;
- build gold-test fixtures from real, messy reference examples.

Why this is next:

- this addresses the project’s first unique bottleneck: getting rough references into structured form;
- enrichment is much more effective once draft references are normalized.

Exit criteria:

- a user can pass a plaintext bibliography section and receive draft BibTeX entries with unresolved fields clearly marked;
- tests cover common article, book, chapter, proceedings, report, and abbreviation-heavy legacy references.

Status:
Substantially complete for the current heuristic-first strategy. The remaining work is quality-focused: larger curated fixtures, sharper benchmark discipline, and continued parser refinement rather than creating the extraction path from scratch.

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

Status:
Partially complete. Resolver and merge behavior are already useful, especially for identifier-first flows, but provenance-rich resolution logs, comparative resolver evaluation, and more deliberate review tooling still need attention.

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

Status:
Partially complete and already usable. The main next-step work is better scoring, filtering, and review surfaces for large discovery sets rather than basic graph traversal.

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

Status:
Early but serviceable. SQLite FTS covers the basic local-search path, but retrieval benchmarking, saved search workflows, and optional semantic ranking remain future work.

Note:
The new `support-claims` feature is an early bridge from bibliography work into
claim-oriented literature assistance. Its current scope is intentionally narrow:
segment citation-bearing claim sentences from a text excerpt, parse already
listed references when possible, and suggest additional candidate support using
the existing verifier/resolver stack. The next quality steps are better claim
segmentation, stronger deduping against already-used sources, and UI review
surfaces for per-claim suggestions.

Note:
The repository now has a small app-facing JSON adapter surface, a lightweight local HTTP bridge, and a static literature-explorer demo shell. That is enough for a browser or desktop-web shell to drive topic discovery, topic expansion, extraction, verification, entry inspection, and lightweight graph exploration against one local database. It is still a demo boundary rather than a full multi-user application or long-running service architecture.

Near-term follow-up for this demo surface:
- add stronger candidate-review interactions for bootstrap and expansion results;
- improve graph review beyond the current lightweight SVG overview;
- keep payload contracts stable enough that the demo can double as an evaluation harness for parser and discovery changes.

## MCP Adapter Surface

Priority: P1

Goal:
Expose CiteGeist's local bibliography workbench through Model Context Protocol
(MCP) tools so assistants can help with source discovery and review without
bypassing bibliographic provenance or review state.

Initial tools:

- `citegeist.search`: scoped search over local entries, identifiers, creators,
  topics, and relation metadata;
- `citegeist.verify_reference`: verify a raw reference string or partial
  BibTeX entry using the existing resolver stack and return ranked candidates
  with match scores and provenance;
- `citegeist.extract_references`: parse a bibliography section into draft
  entries with parser provenance and extraction assessments;
- `citegeist.expand_topic`: run bounded topic/citation expansion and return
  reviewable candidate works, not auto-accepted entries;
- `citegeist.export_bundle`: export reviewed BibTeX, CSL-JSON, OKF, or
  Epistemap-compatible graph bundles when explicitly requested.

Design constraints:

- MCP is an adapter over the existing CLI/library/database contract; it must
  not replace the SQLite canonical store.
- Tool calls that contact external metadata services must expose source label,
  query basis, timestamp, rate-limit behavior, and unresolved/conflict state.
- Verification `match_score`, extraction fidelity, topic relevance, and graph
  topology remain separate assessment dimensions.
- MCP tools may propose enrichment or relation changes, but reviewed status
  changes require an explicit review operation.
- Export tools must preserve CiteGeist IDs and provenance so GroundRecall and
  Didactopus can import reviewed source trails without treating citation
  topology as claim truth.

Acceptance criteria:

- versioned MCP schemas and golden response fixtures exist for search,
  reference verification, extraction, topic expansion, and export;
- MCP smoke tests cover offline/local-only behavior and at least one
  network-enabled resolver path behind explicit configuration;
- review-state and conflict metadata match CLI output for the same operations;
- documentation includes safe assistant-use guidance for source suggestions,
  unresolved references, and conflicting metadata.

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

Status:
Partially complete. OAI acquisition and the TalkOrigins example already demonstrate the pattern, but the general adapter surface and review/report discipline across more sources still need expansion.

## Suggested Next Three Tasks

1. Expand evaluation fixtures and benchmarking for extraction and verification so backend disagreement, parser regressions, and resolver quality can be measured on a broader real-world corpus.
2. Strengthen review and audit workflows for enrichment/graph expansion, especially around provenance logs, candidate summaries, and larger batch-review artifacts.
3. Improve discovery quality inside topic and corpus workflows through better ranking/filtering, more deliberate topic assignment criteria, and retrieval benchmarks that compare lexical and future semantic approaches.

These three tasks should be treated as the immediate sprint because the basic workflow now exists; the bottleneck has shifted to quality measurement, reviewability, and discovery precision.
