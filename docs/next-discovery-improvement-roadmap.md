# Next roadmap: evidence-ready discovery and ranking

Status: implementation in progress; N1 recording and the first N2 label-join path are implemented.
Prepared: 17 October 2026.
Audience: CiteGeist maintainers, researchers, and bounded ranking-proposal agents.

## Purpose

The next step is to connect CiteGeist's development-only ranking experiment runner
to reproducible discovery records and human-reviewed relevance judgments. The current
runner proves that allowlisted configurations can be compared safely on a fixed
development pool. Its synthetic fixture does not show that any ranking is useful.

This plan turns the runner into a research workflow while keeping validation and
release decisions outside the proposal agent's reach. It implements the next
near-term priorities from the [discovery and improvement roadmap](discovery-research-and-improvement-roadmap.md).

## Current position

- `citegeist research` searches local and selected scholarly sources and returns
  candidates without writing them to the bibliography.
- `citegeist experiment-rank` compares up to 16 JSON weight proposals against a
  fixed development pool. It records lineage and hashes, makes no network or
  database calls, and cannot promote a configuration.
- The checked-in benchmark is synthetic plumbing data. There is no human-reviewed
  candidate pool, controlled validation set, or sealed holdout evidence yet.
- `citegeist research --record-pool` now writes a private, unlabelled discovery
  artifact. `label-template` and `prepare-rank-pool` bind complete binary
  relevance judgments to its exact bytes. The current workflow handles one
  recorded query per pool; task-set assembly, split design, and a reviewed rubric
  remain open work.
- The experiment ranker is separate from CiteGeist's production ranking. A proposal
  result cannot change ordinary search behavior.

## Operating principles

1. Candidate-pool generation, human labeling, proposal evaluation, validation, and
   adoption are separate steps with separate artifacts.
2. The proposal agent may read only an approved development pool and may write only
   proposal JSON and a private development receipt. It cannot execute candidate code.
3. Candidate IDs and the candidate set come from the recorded pool; proposals may
   change only the allowlisted numeric weights and their rationale/lineage.
4. Keep validation labels outside the proposal loop. A finalist receives one
   maintainer-controlled comparison, with aggregate results only.
5. Keep locked release labels separate until a one-shot release evaluation. Do not
   treat a development or validation win as general improvement.
6. Preserve unsuccessful trials. No result changes the production default without
   human review, an opt-in pilot, and a rollback path.
7. Store queries, labels, raw candidate metadata, and receipts in private locations
   unless an explicit review approves sanitized publication.

## Implementation stages

### N0 — Establish the task set and relevance rubric

Create a reviewed research-question set spanning known-item lookup, exploratory
literature discovery, methods questions, books/reports/datasets/documentation,
recent updates, and no-answer cases. Use a written rubric that separates relevance,
identity correctness, version/edition match, source authority, and evidence support.
Mark uncertain and unjudged candidates explicitly; do not treat lack of a known
answer as proof that no relevant source exists.

The existing research plan proposes an initial 60-task pilot split into 20
development, 20 validation, and 20 holdout tasks. Treat these counts as a starting
design to review against labeling cost and observed variation, not as a statistical
guarantee. Split by topic and related-work family to reduce leakage. Double-review
a subset and adjudicate disagreements.

**Deliverable:** versioned task IDs, rubric, source-type strata, split manifest, and
reviewer instructions. Development data can be shared with the proposal agent;
validation and holdout labels remain private.

**Exit condition:** reviewers can independently apply the rubric to examples and
resolve disagreements without relying on the proposed ranking score.

### N1 — Record discovery candidate pools

Add a read-only recording path to `citegeist research` that writes a versioned
candidate-pool artifact. Capture query and filters, corpus identity/snapshot where
available, selected providers, provider outcomes, retrieval timestamp, stable
candidate identity, source type, available title/abstract/year fields, provider
rank, and source provenance. Record no credentials or secret request parameters.
Preserve unresolved identity conflicts rather than forcing a merge.

Candidate recording must not add entries to SQLite. The artifact should be
deterministic for the same recorded results and configuration, except for explicit
timestamps and provider drift. Add an import/validation tool that checks the schema
before a researcher adds relevance labels.

**Deliverable:** candidate-pool schema and CLI output that can be reviewed, retained
privately, and reused by `experiment-rank` after label preparation.

**Exit condition:** replaying a recorded pool yields the same candidate IDs and
provider order; malformed, duplicate, or provenance-free records fail visibly.

**Implementation note:** the first recorder is available as `research
--record-pool`. It preserves provider order/ranks and `unknown` outcomes, omits raw
provider error text and URLs, flags conflicting metadata, writes owner-readable
artifacts without overwriting, and opens an existing SQLite corpus read-only.
Candidate pool IDs are deterministic over request, outcomes, and inventory;
retrieval run IDs also include the timestamp. A local-corpus snapshot fingerprint
and multi-query pool assembler remain outstanding before N1 can be considered
complete.

### N2 — Prepare labels and development experiments

Build a small local review workflow or structured annotation file for decisions such
as relevant, background, wrong topic, wrong edition/version, duplicate, inaccessible,
and unjudged. Keep reviewer identity and notes private. Maintain a separate label
artifact so candidate records can be regenerated without silently replacing
judgments. The initial `label-template` / `prepare-rank-pool` implementation supports
binary relevant, not-relevant, and unjudged decisions only; unjudged blocks export.
The richer rubric, task-set assembly, reviewer disagreement handling, and graded
judgments are still required.

Create the development pool by joining reviewed labels to its fixed candidate pool.
Run `citegeist experiment-rank` with a declared baseline and a small set of
hypothesis-driven JSON configurations. Record all proposals, parent IDs, rationale,
input hashes, per-query metrics, and total trial count. The agent may iterate on
development data only; report selection effects and do not call the best score a
confirmed gain.

**Deliverable:** labeled development pool, baseline receipt, proposal receipts, and
a short experiment note describing what signal the candidate was intended to test.

**Exit condition:** the baseline is reproducible, relevance labels remain unchanged
by the runner, and the complete trial history is retained.

### N3 — Add maintainer-controlled validation

Create a separate validation command and execution boundary, using read-only mounts
or a separate operator account so the proposal process cannot read validation labels.
It accepts one preselected finalist and the baseline against the same fixed
validation candidate pool. Check that every ranked ID belongs to that pool and reject
duplicates or candidate additions. Return aggregate paired results and critical-check
status; keep per-query validation failures away from the proposal agent. The
maintainer records the tested finalist before opening validation labels.

Report useful-reference precision at the agreed cutoff, graded ranking quality,
known-relevant recall, no-answer false positives, source-type coverage, identity and
version errors, provider completeness, and reviewer time where available. Include
task-level uncertainty and costs. If validation is used to revise the proposal,
retire it from confirmatory use and create a new validation set.

**Deliverable:** versioned evaluator, protected validation artifact, aggregate-only
receipt, and a recorded decision to reject, revise, or send the finalist to the
locked evaluation gate.

**Exit condition:** failure-injection and access tests show the proposal process
cannot read validation labels, choose arbitrary candidate IDs, edit the evaluator,
or rerun against the same validation set after seeing its result.

### N4 — One-shot holdout and opt-in pilot

Only after a finalist passes validation should a maintainer run a one-shot holdout
comparison. Use a predeclared minimum useful effect and tolerated regressions. If
the candidate passes critical identity, provenance, abstention, source-coverage, and
no-answer checks, expose it behind an opt-in ranking profile. Keep the baseline as
the default during the pilot.

For the first 20 reviewed pilot sessions, inspect outcomes weekly or after each
five sessions, whichever comes first. Stop and roll back after a critical invariant
failure or a predeclared quality/cost regression. The holdout becomes development
data after its detailed results influence further tuning; replenish it before another
confirmatory release decision.

**Deliverable:** one-shot aggregate receipt, human adoption decision, opt-in profile,
monitoring record, and rollback instructions—or a documented decision to retain the
baseline.

## How results guide further work

- If useful candidates never enter the pool, improve query formulation, source
  routing, or corpus coverage before changing ranking weights.
- If candidate pools contain useful sources but the top results are weak, compare
  lexical, seed-overlap, provider-rank, and source-coverage signals one factor at a
  time.
- If the average improves but a source type, domain, or no-answer case regresses,
  keep the candidate scoped or reject it according to the predeclared tolerance.
- If review time does not improve, prioritize a persistent review queue and clearer
  source/version explanations over further score tuning.
- If outcomes are uncertain, keep the baseline and collect more independent tasks;
  do not tune repeatedly on validation or holdout labels.
- If no useful gain appears, retain the simpler baseline and preserve the negative
  result as evidence for the next hypothesis.

## Out of scope

This plan does not authorize executable-code self-modification, prompt rewriting,
model-weight training, automatic promotion, continuous background searches, public
publication of private experiment artifacts, or changes to canonical bibliography
records by the proposal agent. Those changes would require a separate design, threat
review, evaluation protocol, and explicit adoption decision.
