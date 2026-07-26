# Epistemap Knowledge-Graph Roadmap For CiteGeist

**Status:** in progress; confidence phase CG3 has W5 migration CLI coverage
locally and other phases retain their phase-specific status below
**Primary implementation repository:** CiteGeist
**Shared dependency:** Epistemap
**Interacting repositories:** GroundRecall and Didactopus
**Audience:** coding agents implementing one bounded phase at a time

## Executive Assessment

CiteGeist is already a graph system:

- works and stable identifiers form bibliographic entities;
- `cites`, `cited_by`, and `crossref` relations form a citation graph;
- topics form a second relation layer;
- field and relation provenance record where metadata came from;
- review states distinguish draft from reviewed entries;
- graph expansion discovers related works;
- claim-support analysis creates candidate bibliography work orders;
- OKF export already carries works, topics, citation links, provenance, and
  conflicts into GroundRecall and Didactopus workflows.

Epistemap can make those graph operations portable, inspectable, temporal, and
consistent with the rest of the repository ecosystem. It should not replace
CiteGeist's SQLite store or become a truth-ranking engine.

Confidence migration status:

- `confidence-migrate` now supports dry-run reports by default.
- `confidence-migrate --apply --backup BACKUP --report REPORT.json` applies the
  migration transactionally after creating or reusing an explicit backup.
- `confidence-restore BACKUP --report REPORT.json` restores the SQLite database
  from a migration backup.
- Typed assessment storage preserves the portable interval shape.
- Support-gap priority and query-scoped retrieval scores remain reported as
  non-confidence fields rather than migrated assessments.

The most useful integration is:

1. project selected CiteGeist records into a derived Epistemap `GraphBundle`;
2. run traversal, diagnostics, temporal, provenance, and assessment operations
   on that projection;
3. return review and discovery results to CiteGeist as proposals or reports;
4. export reviewed graph bundles to GroundRecall and Didactopus without
   weakening repository ownership boundaries.

## Expected Benefits

### Explainable Literature Discovery

Epistemap neighborhoods, bounded subgraphs, paths, ancestors, and descendants
can explain how a discovered work relates to seed works. CiteGeist can expose
the exact path and source API rather than only a ranked result.

Benefits:

- auditable multi-hop expansion;
- visible seed-to-candidate paths;
- easier comparison of discovery sources;
- reproducible literature-review boundaries;
- better review of bridge works and isolated subliteratures.

Graph centrality or bridge status is a discovery signal, not an assessment of
truth, quality, or importance.

### Citation-Graph Quality Control

Epistemap QA and diagnostics can detect:

- missing endpoints and unresolved stubs;
- duplicate node identities;
- citation edges lacking provenance;
- disconnected topic components;
- suspicious direction or inverse-edge inconsistencies;
- publication-date anomalies;
- graph expansion dominated by one source or source family.

Citation cycles are not automatically errors. Versioning, preprints,
corrections, bad metadata, and same-year publication ambiguity require a
diagnostic rather than unconditional rejection.

### Provenance And Source Reconciliation

Crossref, OpenAlex, OpenCitations, Semantic Scholar, and imported BibTeX may
report the same field or citation relation. An Epistemap projection can retain
each observation while deduplicating the underlying bibliographic assertion.

This supports:

- agreement and disagreement reports by source;
- visible source-family dependence;
- field-conflict review;
- replayable graph construction;
- confidence assessments tied to their producing method rather than stored as
  unexplained floats.

### Temporal Literature Views

Publication, correction, retraction, and observation times can support:

- literature graphs as known by a historical cutoff;
- detection of citations that appear to predate the cited work;
- distinction between publication time and API retrieval time;
- identification of evidence that was not yet available for an earlier claim;
- review of superseded metadata and corrected or retracted works.

Temporal slicing does not imply that older work is less credible.

### Claim-Support Review

CiteGeist can represent a claim, source slot, and candidate work in the same
portable graph without claiming that bibliographic proximity proves support.

Useful relation states include:

- `candidate_support`;
- `reviewed_supports`;
- `reviewed_challenges`;
- `background_for`;
- `methods_source_for`;
- `data_source_for`;
- `corrects`;
- `retracts`;
- `needs_source`.

Only a reviewed relation with a source anchor may become
`reviewed_supports` or `reviewed_challenges`. Citation, topical similarity,
abstract overlap, and graph distance may generate candidates but not reviewed
support.

### Ecosystem Interchange

- GroundRecall can import bibliographic identities, reviewed source anchors,
  contradictions, corrections, and source-slot resolutions without treating
  abstracts as promoted claims.
- Didactopus can expose reviewed reading paths, contrary sources, and
  evidence-status labels without turning citation counts into mastery or truth.
- Epistemap can evaluate graph structure and assessment readiness without
  becoming the bibliography or memory authority.

## Repository Boundaries

| Concern | Authority |
|---|---|
| Bibliographic metadata, identifiers, citation relations, source API provenance | CiteGeist |
| Portable graph schemas, traversal, diagnostics, temporal and assessment operations | Epistemap |
| Claims, observations, review, promotion, supersession, and durable memory | GroundRecall |
| Learner state, pedagogy, mastery, and source presentation | Didactopus |

Rules:

- CiteGeist remains canonical for bibliography records.
- The Epistemap graph is a rebuildable projection.
- GroundRecall must not rewrite CiteGeist bibliographic identity silently.
- CiteGeist must not promote GroundRecall claims.
- Didactopus must not infer source truth from citation-graph structure.
- Cross-repository changes travel through versioned bundles, not shared mutable
  databases or imports from hard-coded sibling paths.

## Target Graph Profile

Use profile name `citegeist.bibliography.v1`.

### Node Types

Initial required nodes:

- `work`: article, book, chapter, preprint, dataset, or other bibliographic
  work;
- `topic`: a reviewed or provisional CiteGeist topic.

Optional nodes introduced by later phases:

- `claim`: a GroundRecall or local claim candidate;
- `source_slot`: a bibliography work order requiring reviewed sources;
- `person`: only when person-level graph operations have a demonstrated use;
- `venue`: only when venue-level analysis has a demonstrated use.

Do not make every metadata field a graph node. Field observations belong in
provenance and assessment records unless a concrete query requires otherwise.

### Stable IDs

Derive work node IDs in this order:

1. normalized DOI;
2. PMID;
3. arXiv ID;
4. OpenAlex ID;
5. CiteGeist citation key scoped by store ID.

Example:

```text
work:doi:10.1234/example
work:pmid:12345678
work:citegeist:STORE_ID:CITATION_KEY
topic:citegeist:TOPIC_SLUG
```

Identity upgrades must create an explicit `same_as` or identity-migration
record. They must not silently change an existing node ID.

### Edge Types

Initial:

- `cites`;
- `member_of_topic`;
- `same_as`.

Derived inverses such as `cited_by` should normally be computed from `cites`
rather than serialized as independent evidence. Preserve a separately observed
`cited_by` API response as provenance on the canonical citation assertion.

Later reviewed claim edges:

- `candidate_support`;
- `reviewed_supports`;
- `reviewed_challenges`;
- `background_for`;
- `methods_source_for`;
- `data_source_for`;
- `needs_source`;
- `corrects`;
- `retracts`.

### Provenance

Each bibliographic assertion should be reconstructible from:

- CiteGeist store and record identifier;
- source type and source label;
- source API and operation;
- request/query identifier when available;
- retrieval or observation time;
- raw response artifact or stable hash when retained;
- supporting CiteGeist provenance row IDs;
- review status;
- extraction/identity assessment IDs;
- schema and exporter versions.

### Temporal Fields

Keep distinct:

- `published_at`: asserted publication date;
- `available_at`: first public availability when known;
- `observed_at`: when CiteGeist obtained the assertion;
- `retrieved_at`: when an external source was queried;
- `reviewed_at`: when a person accepted an assertion;
- `corrected_at` and `retracted_at`: later lifecycle events.

Do not substitute a year-only publication value for a precise timestamp.
Preserve precision metadata.

## Confidence And Assessment Integration

This roadmap depends on Epistemap's
`docs/confidence-overhaul-roadmap.md`.

The evidence-backed phase audit is maintained in Epistemap at
`docs/confidence-overhaul-implementation-status.md`. CiteGeist CITE1/CG3 is
partial until the CLI migration surface, rollback/backup behavior, reviewed
identity outcomes and calibration, portable interval storage, and graph-export
integration are complete.

CiteGeist currently uses generic confidence values for several different
semantics. Migrate them as follows:

| Current surface | Target meaning |
|---|---|
| `VerificationResult.confidence` | `identity_resolution` assessment or `match_score` compatibility field |
| Alternate candidate score | identity-resolution candidate score |
| `field_provenance.confidence` | `extraction_fidelity` or namespaced `citegeist:metadata_field_match` |
| `relation_provenance.confidence` | `extraction_fidelity` or `grounding_strength` |
| `entry_topics.confidence` | namespaced `citegeist:topic_relevance` |
| `needs_support_score` | `support_gap_priority`, not confidence |
| graph expansion score | query-scoped discovery ranking, not durable confidence |

Add `identity_resolution` to the portable Epistemap confidence dimensions. It
answers whether an observed reference or result identifies the same
bibliographic work. It does not assess whether the work is correct.

No Bayesian support estimate should be calculated from citation counts.
Bayesian evidential support is appropriate only for explicit claim-support or
challenge relations with reviewed anchors and a declared evidence policy.

## Unified Delivery Sequence

The sequence below is normative across the four repositories.

### CG0: Contract, Inventory, And Golden Fixtures

**Repository:** CiteGeist
**Dependencies:** none

Tasks:

1. Inventory every citation, topic, provenance, review, score, and confidence
   field.
2. Add golden fixtures covering:
   - DOI-resolved works;
   - citation-key-only works;
   - unresolved citation targets;
   - duplicate citation assertions from two APIs;
   - conflicting metadata;
   - topics and topic confidence;
   - corrections or retractions where fixture data permits;
   - claim-support candidates.
3. Define `citegeist.bibliography.v1` in a machine-readable profile document.
4. Record baseline CiteGeist, Epistemap, GroundRecall adapter, and Didactopus
   OKF tests.

Expected files:

- `docs/epistemap-knowledge-graph-roadmap.md`
- `docs/citegeist-bibliography-graph-profile.json`
- `tests/fixtures/epistemap/`
- `tests/test_epistemap_profile.py`

Acceptance criteria:

- every current relation and confidence field has a declared semantic owner;
- fixtures preserve unresolved and conflicting data rather than cleaning it
  silently;
- the profile defines stable IDs and direction for every initial edge.

### E-CG1: Epistemap Bibliography Profile Support

**Repository:** Epistemap
**Dependencies:** confidence overhaul E1 and CiteGeist CG0

Tasks:

1. Confirm generic `Node`, `Edge`, provenance, assessment, and temporal models
   can represent the profile without bibliography-specific core classes.
2. Add reusable validation hooks for:
   - required node/edge provenance;
   - declared edge direction;
   - identity aliases;
   - date precision;
   - derived inverse relations.
3. Extend graph QA so a profile can declare that `cited_by` is the derived
   inverse of `cites`.
4. Add a diagnostic for source-family concentration and duplicate evidence
   assertions.
5. Keep CiteGeist-specific profile policy outside Epistemap core.

Acceptance criteria:

- Epistemap requires no CiteGeist import;
- the CiteGeist fixture validates through generic profile hooks;
- inverse and duplicate assertions remain traceable to all observations;
- no graph diagnostic labels a highly cited work as more truthful.

### CG1: Deterministic Epistemap Export

**Repository:** CiteGeist
**Dependencies:** CG0 and E-CG1

Tasks:

1. Add Epistemap as an optional `graph` dependency initially.
2. Implement `src/citegeist/epistemap_export.py`.
3. Add:

   ```text
   citegeist --db DB export-epistemap OUT.json
   citegeist --db DB export-epistemap OUT.json --topic TOPIC
   citegeist --db DB export-epistemap OUT.json --seed KEY --hops 2
   ```

4. Export deterministic node, edge, provenance, assessment, and manifest
   ordering.
5. Write an adjacent assessment/profile manifest.
6. Preserve stubs and conflicts when requested; identify them explicitly.
7. Keep SQLite canonical and export read-only.

Acceptance criteria:

- identical database state produces byte-stable normalized JSON except for an
  explicitly excluded generation timestamp;
- every citation edge has at least one provenance reference;
- DOI normalization produces stable IDs;
- observed inverse relations deduplicate to one citation assertion with
  multiple provenance observations;
- export requires no network access.

### CG2: Graph Inspection And Explainable Discovery

**Repository:** CiteGeist
**Dependencies:** CG1

Tasks:

1. Add:

   ```text
   citegeist --db DB graph-inspect
   citegeist --db DB graph-inspect --topic TOPIC
   citegeist --db DB graph-query KEY --hops 2
   citegeist --db DB graph-path SOURCE TARGET
   ```

2. Use Epistemap neighborhood, bounded subgraph, path, components, bridge, and
   QA operations.
3. Return source paths and provenance for discovery candidates.
4. Label bridge, degree, component, and path values as structural discovery
   signals.
5. Add JSON output first; Markdown summary may follow.

Acceptance criteria:

- query output explains every returned work through a graph path;
- review status and provenance accompany candidates;
- missing endpoints and source concentration appear in QA;
- no structural metric is emitted under a field named confidence, reliability,
  quality, or truth.

### CG3: Typed Assessment And Database Migration

**Repository:** CiteGeist
**Dependencies:** Epistemap confidence E1 and CG0

Tasks:

1. Add a versioned assessment table capable of storing the portable Epistemap
   assessment shape and namespaced CiteGeist dimensions.
2. Bound new numeric assessments and represent missing as null.
3. Add:

   ```text
   citegeist --db DB confidence-migrate --report REPORT.json
   citegeist --db DB confidence-migrate --apply --report REPORT.json
   ```

4. Make dry-run the default and migration idempotent.
5. Preserve legacy scalar columns through the compatibility window.
6. Rename `VerificationResult.confidence` to `match_score`, retaining a
   deprecated read-only alias.
7. Rename `needs_support_score` to `support_gap_priority`, retaining a
   serialized compatibility alias for one release.
8. Record method, version, source, basis IDs, and rationale for all newly
   generated assessments.

Acceptance criteria:

- missing and explicit zero remain distinct;
- out-of-range, NaN, and infinite values fail;
- legacy rows are reported but never guessed into a dimension;
- verification match scores cannot be mistaken for source reliability;
- rollback and pre-migration backup procedures are tested.

### CG4: Provenance Reconciliation And Graph QA

**Repository:** CiteGeist
**Dependencies:** CG1 and CG3

Tasks:

1. Assign stable assertion IDs to metadata fields and citation relations.
2. Attach multiple source observations to a single assertion.
3. Add source-family identity for APIs that may reproduce upstream data.
4. Report agreement, conflict, source concentration, unresolved identity, and
   missing provenance.
5. Feed existing field conflicts into graph QA.
6. Add review proposals for conflicts; do not auto-select a winner from source
   count or confidence.

Acceptance criteria:

- the same citation reported by three APIs remains one assertion with three
  observations;
- correlated observations are visible as one source family when known;
- conflict resolution records the reviewer, rationale, and assertions seen;
- rejected assertions remain auditable.

### CG5: Temporal Citation Operations

**Repository:** CiteGeist
**Dependencies:** CG1 and Epistemap temporal operations

Tasks:

1. Normalize publication and availability dates with precision metadata.
2. Map retrieval, observation, review, correction, and retraction times.
3. Add:

   ```text
   citegeist --db DB graph-query KEY --as-of DATE
   citegeist --db DB graph-inspect --temporal
   ```

4. Diagnose:
   - citations apparently preceding cited publication;
   - undated assertions;
   - metadata observed only after the requested cutoff;
   - corrected or retracted works still presented as current.
5. Preserve historical graph reconstruction.

Acceptance criteria:

- `as_of` excludes assertions not then available without deleting them;
- year-only dates remain year precision;
- anachronisms are review findings, not automatic deletion;
- correction and retraction history remains visible.

### CG6: Claim And Source-Slot Graph

**Repositories:** CiteGeist and GroundRecall
**Dependencies:** CG3, CG4, and GroundRecall confidence G3

Tasks in CiteGeist:

1. Accept versioned claim/source-slot input with stable GroundRecall IDs.
2. Emit candidate relations from search, citation paths, topic relevance, and
   metadata matching.
3. Require a source anchor—page, section, quotation, or reviewed abstract
   statement—for reviewed support/challenge.
4. Add a review payload showing claim, candidate work, anchor, relation type,
   bibliographic verification, provenance, and contrary candidates.
5. Export decisions as append-only relation assessments.

Tasks in GroundRecall:

1. Preserve CiteGeist work IDs and assessment IDs during import.
2. Import bibliographic metadata and abstracts as observations, not as promoted
   claims that the abstract is correct.
3. Map only reviewed source relations to GroundRecall support/challenge
   candidates.
4. Keep GroundRecall promotion separate from CiteGeist bibliography review.
5. Resolve source slots through explicit records rather than replacing slot
   text silently.

Acceptance criteria:

- a citation edge alone cannot become `reviewed_supports`;
- every reviewed support/challenge relation names an anchor and reviewer;
- contrary and background relations remain distinct from support;
- round-trip export/import preserves both repository IDs and provenance.

### CG7: OKF And Consumer Interchange

**Repositories:** CiteGeist, GroundRecall, and Didactopus
**Dependencies:** CG1, CG3, and CG6

Tasks:

1. Define an OKF v2 extension containing:
   - `epistemap_graph.json`;
   - graph profile and assessment manifest;
   - typed assessment records;
   - temporal fields;
   - unresolved conflicts and stubs;
   - reviewed claim/source-slot relations when present.
2. Keep existing OKF v1 consumers working.
3. Update GroundRecall's `citegeist_okf` adapter.
4. Update Didactopus's `citegeist_okf` source-corpus conversion.
5. Remove hard-coded sibling source-path loading from the long-term interface;
   use package dependencies, subprocess contracts, or versioned bundles.

Acceptance criteria:

- v1 fixtures remain readable;
- v2 round trips preserve exact work, edge, assessment, and provenance IDs;
- GroundRecall does not synthesize confidence from missing values;
- Didactopus labels abstracts as source text and reviewed relations separately;
- installed-package tests do not depend on sibling working trees.

### CG8: Evaluation And Release

**Repositories:** all four
**Dependencies:** CG2–CG7

Evaluate:

- graph export fidelity;
- duplicate assertion detection;
- missing-provenance detection;
- identity-resolution calibration;
- current versus historical graph accuracy;
- source-slot resolution precision and reviewer burden;
- candidate-support precision before review;
- retrieval coverage and novelty;
- downstream GroundRecall provenance completeness;
- Didactopus source-trail correctness.

Required comparisons:

1. current CiteGeist traversal;
2. Epistemap projection with ordinary traversal;
3. provenance-aware and deduplicated traversal;
4. temporal traversal;
5. claim candidate generation without and with graph context.

Do not use citation count, degree, posterior support, or source reputation as a
ground-truth quality label.

Acceptance criteria:

- evaluation fixtures and scripts are public where licensing permits;
- claims of benefit are tied to measured discovery, QA, provenance, temporal,
  or review outcomes;
- Epistemap is released before consumers update pinned dependencies;
- all integrations pass against installed package versions.

## Unified Cross-Repository Dependency Order

```text
Confidence C0/E1
       │
       ├── CiteGeist CG0 ── Epistemap E-CG1 ── CiteGeist CG1/CG2
       │
       ├── GroundRecall G1/G2
       │
       └── Didactopus D1/D2
                    │
Confidence E2/E3 ──┼── CiteGeist CG3/CG4/CG5
                    │
GroundRecall G3/G4 ┴── CiteGeist CG6
                              │
                     CG7 consumer interchange
                              │
                     CG8 evaluation/release
```

Do not begin CG6 claim-support assessment before the typed confidence and
reviewer-assessment foundations exist. Structural graph export and diagnostics
in CG1–CG2 can proceed earlier because they are read-only projections.

## Testing Commands

### CiteGeist

```bash
pytest -q
```

With local Epistemap during development:

```bash
PYTHONPATH=src:/home/netuser/bin/Epistemap/src pytest -q
```

### Epistemap

```bash
pytest -q
```

### GroundRecall

```bash
PYTHONPATH=src:/home/netuser/bin/Epistemap/src pytest -q
```

### Didactopus

```bash
PYTHONPATH=src:/home/netuser/bin/Epistemap/src pytest -q
```

Before release, repeat consumer tests in clean environments with declared
packages installed and sibling source paths removed.

## Coding-Agent Rules

For each phase:

1. Read repository instructions and inspect all affected working trees.
2. Preserve unrelated modifications and generated research artifacts.
3. Write failing tests before behavior changes.
4. Keep SQLite canonical and Epistemap projections rebuildable.
5. Make migrations dry-run first, idempotent, and accompanied by reports.
6. Do not infer semantics for a legacy confidence field.
7. Do not transform citation relations into claim-support relations.
8. Do not automatically resolve metadata conflicts by score or source count.
9. Version schemas, exporters, assessment methods, and weighting policies.
10. Test installed-package boundaries before completing an integration phase.
11. Report files changed, migrations, compatibility behavior, tests, ambiguous
    legacy data, and the next unblocked phase.

## Non-Goals

- Replacing CiteGeist's SQLite database with a graph database.
- Treating citation count or graph centrality as source quality.
- Inferring claim truth from citation topology.
- Applying Bayesian support to ordinary citation edges.
- Automatically promoting candidate sources.
- Creating person and venue graphs without a concrete query.
- Introducing embeddings before graph/provenance baselines are measured.
- Sharing a mutable canonical store across repositories.

## Definition Of Done

The integration is complete when:

- CiteGeist can export a deterministic, provenance-complete Epistemap graph;
- graph discovery results explain their paths and source observations;
- duplicate and conflicting assertions remain auditable;
- historical graph slices preserve date precision and correction history;
- confidence meanings are typed under the unified confidence roadmap;
- claim support requires reviewed anchors rather than citation proximity;
- GroundRecall and Didactopus consume versioned bundles without authority
  confusion;
- cross-repository fixtures pass against installed package releases.
