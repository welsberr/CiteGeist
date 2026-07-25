# CiteGeist Roadmap: Sources-First Expansion

The unified confidence overhaul is in progress. Its audited cross-repository
status is maintained in Epistemap at
`docs/confidence-overhaul-implementation-status.md`; CiteGeist's typed
assessment table and dry-run migration function are a partial CG3
implementation, not a completed migration or release.

The next capability roadmap is
[docs/epistemap-knowledge-graph-roadmap.md](docs/epistemap-knowledge-graph-roadmap.md).
It preserves this sources-first direction: CiteGeist's SQLite bibliography
remains canonical, while Epistemap supplies a rebuildable graph projection for
portable traversal, diagnostics, temporal views, typed assessments, and
cross-repository interchange.

Implement the read-only graph profile/export/diagnostic phases before
claim-support assessment. Coordinate confidence migration with Epistemap,
GroundRecall, and Didactopus rather than creating another CiteGeist-specific
scalar confidence scheme.

## Purpose

The primary question is not “how do we redesign CiteGeist around a new storage engine?” The primary question is “which additional open bibliographic sources should CiteGeist incorporate next?”

This roadmap treats the current SQLite-based local workflow as the baseline and focuses on source evaluation, source integration order, and reviewable source behavior.

## Baseline

Already present in the repository:

- local BibTeX ingest, review, export, and graph traversal
- metadata resolution from `Crossref`, `PubMed`, `Europe PMC`, `OpenAlex`, `Semantic Scholar`, `DBLP`, `arXiv`, and `DataCite`
- citation-graph expansion using `Crossref` and `OpenAlex`
- repository harvesting via `OAI-PMH`

That means the next planning step is source prioritization, not another platform pivot.

## Phase 0: Reframe Scope

Goal:

Put source-incorporation decisions ahead of database and vector-search ambitions.

Tasks:

- [x] identify which source integrations already exist
- [x] separate “source expansion” work from “new database/vector stack” work
- [x] document the source landscape and recommended order

Deliverables:

- `/docs/source-landscape.md`
- `/src/citegeist/sources/catalog.py`

## Phase 1: Tighten The Source Layer

Goal:

Make the new source abstraction useful for the repository that already exists, rather than speculative infrastructure.

Tasks:

- [x] keep the compatibility bridge to the existing `SourceClient`
- [x] fix the initial `CrossRefSource` implementation so normalization works
- [x] make config-driven registry loading work for known concrete sources
- [x] add a code-backed source catalog for planning and prioritization

Deliverables:

- `/src/citegeist/sources/base.py`
- `/src/citegeist/sources/registry.py`
- `/src/citegeist/sources/crossref.py`
- `/src/citegeist/sources/catalog.py`

## Phase 2: Highest-Value Open Source Additions

Goal:

Incorporate the next open sources that materially improve the current workflow.

Priority order:

1. `OpenAIRE` only if repository-acquisition scope expands

Tasks:

- [x] add `OpenCitations` DOI-to-citation and DOI-to-reference lookup
- [x] merge `OpenCitations` edges into the existing graph-expansion workflow with provenance
- [x] add `Unpaywall` DOI-to-OA-link enrichment
- [x] expose OA-link enrichment in a dedicated CLI flow
- [x] add `Europe PMC` as a biomedical metadata/fulltext complement to `PubMed`
- [x] add `Semantic Scholar` as a broader scientific metadata complement across biological and physical sciences

Why these first:

- `OpenCitations` directly answers the open-citation-coverage gap
- `Unpaywall` now solves access-link enrichment without forcing a storage redesign
- `Europe PMC` now improves biomedical metadata and OA/fulltext coverage without changing the storage model
- `Semantic Scholar` now improves broader biological and physical sciences coverage without changing the storage model

## Phase 3: Evaluate Optional Sources, Do Not Commit Prematurely

Goal:

Assess sources that may be useful, but are not clearly the next source-first move.

Candidates:

- `OpenAIRE`

Tasks:

- [ ] document API limits, openness constraints, and integration risk
- [ ] decide whether each source belongs in core resolution, graph expansion, or corpus acquisition
- [ ] avoid adding sources that duplicate existing coverage without a clear payoff

## Deferred Work

These are valid future ideas, but they are not the current planning driver:

- a second database schema
- pgvector integration
- embedding-first search
- large-scale canonical-work reconstruction

The repository already has a working local storage/search path. Those ideas should only return to the front of the plan if a concrete source-integration need forces them there.

## Immediate Next Steps

1. Land the source inventory and source-layer cleanup.
2. Reassess whether `OpenAIRE` is worth adding for repository-acquisition breadth.
