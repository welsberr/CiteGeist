# GroundRecall Unified Retrieval: CiteGeist Companion Plan

Status: draft for review; blocked on GroundRecall UPR-0 store reconciliation.

## Purpose

CiteGeist should provide a demanding literature-work pilot for GroundRecall's
unified prior-work retrieval. CiteGeist remains authoritative for bibliographic
identity, field provenance, conflicts, and review state; GroundRecall retrieves
selected repository knowledge and derived context without taking over the
bibliography database.

The controlling roadmap is GroundRecall's
[`unified-prior-work-retrieval-roadmap.md`](../../GroundRecall/docs/unified-prior-work-retrieval-roadmap.md).
This plan is subordinate to CiteGeist's quality, review, and discovery roadmap.

## Authority Boundary

- CiteGeist SQLite data and reviewed exports remain the bibliography authority.
- Registered CiteGeist documentation and commit summaries remain repo-owned
  read-only corpora.
- Citation and topical edges are discovery context, not claim support, source
  quality, or truth.
- Resolver match score, extraction fidelity, topic relevance, graph topology,
  and GroundRecall retrieval relevance remain separate dimensions.

## Work Packages

### C-UR1: Documentation and query fixture

- Register selected architecture, roadmap, extraction, verification, and graph
  integration documentation at pinned Git revisions.
- Build public synthetic questions involving aliases, DOI/title/author identity,
  prior resolver decisions, parser limitations, and current roadmap state.
- Include near-duplicate works, title variants, retractions/corrections,
  superseded decisions, and irrelevant but highly cited sources.

Acceptance: retrieval identifies the relevant prior work while preserving path,
revision, status, and conflicts.

### C-UR2: Literature discovery context

- Define a read-only adapter that can place bounded CiteGeist entry and relation
  references in GroundRecall's `graph_context` group.
- Require explicit database identity, query basis, entry IDs, relation
  provenance, review state, and generation time.
- Return references rather than silently copying mutable bibliographic records
  into GroundRecall's canonical store.

Acceptance: a bundle can explain why a work is related without asserting that a
citation supports a claim or changing CiteGeist review state.

### C-UR3: Retrieval evaluation

- Evaluate known-item recall for DOI, title, author, and alias queries;
  prior-decision recall; bridge-literature discovery; source-swamp resistance;
  and bundle retention after candidate generation.
- Compare lexical-only and GroundRecall local-hybrid retrieval. CiteGeist's own
  optional semantic-search roadmap remains independently governed.
- Preserve immutable receipts and separate public fixtures from opt-in private
  research-query replay.

Acceptance: held-out results improve without external embeddings, authority
confusion, or automatic bibliography mutation.

## Dependencies and Non-Goals

- No code work before GroundRecall UPR-0 passes.
- C-UR1 follows GroundRecall's registry/evaluation contract; C-UR2 follows the
  evidence-bundle schema; C-UR3 follows the local-hybrid implementation.
- This plan does not replace CiteGeist search, duplicate resolution, metadata
  enrichment, review, or graph expansion.
