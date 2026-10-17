# CiteGeist process review and improvement roadmap

Reviewed 3 October 2026. This document preserves the findings from that review;
some implementation slices are now present in the working tree, but regression
qualification and remaining fixes are open. The original findings below describe
the reviewed revision and must be rechecked against current code before action.

## Working-tree update, 17 October 2026

The following first implementation slices are now present in the working tree:

- CG-FIX-1/2: clue and rank shape validation rejects malformed fields, duplicate
  keys, non-finite values, invalid indices, and trailing response text.
- CG-FIX-3: the LLM client records typed disabled, success, abstention, invalid,
  timeout, and provider-error outcomes and applies output-token limits. The
  outcome is now included in verification audit JSON; no input-token budget or
  full transport telemetry is implemented.
- CG-FIX-4/5: claim-support identity and support labels require resolver-backed
  evidence; verification JSON records bounded assistance provenance while
  BibTeX export omits that audit. The model client does not expose raw responses.
- CG-FIX-7: bootstrap batches can write atomic per-job receipts and resume after
  completed or interrupted work. Completed jobs are skipped; partial, failed, and
  interrupted jobs are retried. Recovery is at-least-once around the gap between
  database commit and receipt update; qualification against interruption fixtures
  remains outstanding. A larger capped run needs changed inputs and a new receipt.
- CG-FIX-8: mandatory unsupported route restrictions return before retrieval.

The batch runner records failures from seed-file reads and option conversion as
failed jobs. A completed receipt entry is restored only when its per-job input
hash matches the current job.

No regression tests were added or run in this implementation pass. Keep the
checkboxes below open until focused regressions pass and their evidence is linked.
The 3 October findings below describe the reviewed commit and should not be read
as a claim that the current working tree still has each original behavior.

## Decision

Repair model-output validation and evidence-status reporting before expanding
LLM assistance. Then measure whether assistance improves reference resolution
over the existing resolver. Preserve the deterministic bibliography workflow,
field provenance, conflict review, and explicit export process.

Start with **27B Q4 for bounded assistance**. Compare **Flash Q2 for batches**
and **Flash IQ3 as a challenger** after the correctness gates pass. These are
provisional task assignments, not citation-accuracy qualifications.

## Scope and evidence

The review inspected extraction/verification, claim-support reporting, model
clients, batch orchestration, source retries, tests, and existing plans at commit
`8d4b7996fab39be384be6f1acfbbdd55f6fc9756`. The checkout already contained a
ROADMAP edit and an untracked GroundRecall integration plan; both were preserved.
This was a bounded code review with offline probes, not a full repository audit
or a new model benchmark. No bibliography database or running service changed.

The existing foundations include identifier-first resolution, a heuristic
extraction default, optional external parsers, source caching and retries,
typed identity assessments, and reviewable candidate outputs. Build on them.

### Confirmed findings

| ID | Finding and evidence | Consequence |
|---|---|---|
| CG-F1 | In [llm_verify.py](../src/citegeist/llm_verify.py), an injected `authors: "Smith"` becomes five one-character authors; `authors: null` raises `TypeError`. Both were reproduced. | Parseable JSON is not sufficient input validation. |
| CG-F2 | The same client sends eight candidates but validates returned indices against the entire candidate list. With ten candidates, `[true, 1, 1, 9]` is accepted unchanged in an offline probe. Duplicate JSON keys also silently keep the last value. | Boolean, duplicate, and unseen-candidate ranks can enter scoring. |
| CG-F3 | An injected transport timeout becomes `None`. `_chat_json` catches every exception, while later normalization can still raise. The requests have a 60-second client timeout but no explicit output-token cap or structured response constraint. | An operator cannot distinguish disabled assistance, model abstention, invalid output, and transport failure from the result alone. |
| CG-F4 | [verify.py](../src/citegeist/verify.py) merges inferred clues into matching fields. Its serialized result lacks a dedicated record of original versus inferred clues, model response, validation outcome, and effect on ranking. | The returned metadata source does not explain the model's contribution to finding or scoring that source. |
| CG-F5 | In [bounded_claim_evidence_check](../src/citegeist/claim_support.py), a `not_found` result with source `none` and a placeholder key/title yields `source_identity: resolved`. Reproduced with a fake verifier. | The nested candidate status contradicts the unresolved outer result. Automatic promotion is still explicitly prohibited. |
| CG-F6 | LLM rank is a secondary sort key after numerical match score, intentionally covered by [test_verify.py](../tests/test_verify.py). | Reranking only resolves score ties; a broader model-ranking benefit has not been demonstrated. This is a policy choice, not itself a defect. |
| CG-F7 | [test_live_llm_verify.py](../tests/test_live_llm_verify.py) skips on unparseable/unavailable model results and checks broad output shape. [batch.py](../src/citegeist/batch.py) returns an in-memory sequence of job results without a durable per-job resume journal. | Qualification can remain inconclusive; interrupted batch recovery needs explicit design. These observations apply to the inspected paths, not every example pipeline. |

The bounded evidence adapter also reports `source_routes_enforced: false`.
That is useful honesty, but callers requiring restricted routes need rejection
before retrieval rather than a restriction recorded only after the call.

### Baseline checks

From the repository root:

```bash
.venv/bin/python -m pytest -q tests/test_verify.py tests/test_claim_support.py tests/test_batch.py
```

Result: **22 passed, 9 deprecation warnings, 3.43 seconds**. The adversarial
probes above exercised gaps outside those tests. Passing this subset establishes
neither whole-repository health nor real-model citation accuracy.

## Delivery sequence

### Additional issue fixes and regression checks

All items below are **open**. They turn the additional review findings into
specific fixes within CG-1–CG-5. Close an item only after its regression check
passes and the implementation and test evidence are linked here.

- [ ] **CG-FIX-1 — malformed clue fields (P0; CG-F1; CG-1).** Validate the
  response before normalizing it. Reject string/null authors and keywords with
  an `invalid_response` outcome; allow empty lists and explicitly nullable
  scalar fields. In `tests/test_verify.py`, replay `authors: "Smith"` and
  `authors: null`: neither may create character authors or raise an uncaught
  exception, and the resolver-only fallback must remain available.
- [ ] **CG-FIX-2 — invalid rankings and ambiguous JSON (P0; CG-F2; CG-1).**
  Validate ranks against the exact submitted candidate subset, exclude booleans,
  and reject duplicate ranks and duplicate JSON keys. Add a ten-candidate fixture
  where only eight are sent: `[true, 1, 1, 9]` must be rejected as a whole.
  Retain a valid partial-order fixture with deterministic handling of omissions.
- [ ] **CG-FIX-3 — silent inference failures (P0; CG-F3; CG-1).** Carry typed
  outcomes through the client, verifier, and CLI result. Apply validation inside
  the same bounded error-handling path as transport. Inject timeout, malformed
  content, and empty output; each must produce a distinct auditable result and
  never appear as successful assistance. Check configured token and time limits
  in captured requests for both supported transports.
- [ ] **CG-FIX-4 — misleading source identity (P0; CG-F5; CG-2).** Require
  resolver-backed identity evidence before emitting `source_identity: resolved`.
  In `tests/test_claim_support.py`, replay a `not_found` placeholder with a key,
  title, score zero, and source `none`; identity and support must remain
  unresolved. Pair it with an actual resolved-source fixture so the correction
  preserves valid identity results.
- [ ] **CG-FIX-5 — missing assistance provenance (P0; CG-F4; CG-2).** Add a
  versioned audit record separating supplied fields, inferred hints, validation,
  and rank effects. Verify serialization preserves the original query and
  records fallback use, while public BibTeX omits private response text. Keep
  the existing tie-breaking policy and record whether a model changed ordering.
- [ ] **CG-FIX-6 — inconclusive qualification reported too loosely (P1;
  CG-F7; CG-3/CG-5).** Give qualification runs explicit complete, failed, and
  incomplete outcomes. A configured but unavailable model or invalid response
  must prevent qualification success; optional connectivity smoke tests may
  still skip. Test the distinction without a live service.
- [ ] **CG-FIX-7 — interrupted core batches (P2; CG-F7; CG-4).** Persist job
  outcomes and resume from committed work. Inject failure after one completed
  job, restart, and assert that completed writes are not duplicated and failed
  jobs remain visible. Include input-change cache invalidation in the fixture.
- [ ] **CG-FIX-8 — unenforced required source restrictions (P0; CG-2).**
  Reject unsupported mandatory route restrictions before retrieval, or enforce
  them through the resolver. Use a resolver spy to prove a forbidden route is
  never called; recording `source_routes_enforced: false` alone cannot satisfy
  a mandatory restriction.

P0 means required before expanding model-assisted use; P1 means required for a
reviewed application pilot; P2 means operational improvement after that pilot.
Each package should be a reviewable change with its own evidence. Implementation
owners should be assigned when work starts; no delivery dates are committed here.

### CG-1 — validate model responses and expose failures (P0)

Addresses CG-F1–F3. No dependency on a new model or GroundRecall integration.

- Define versioned clue and ranking schemas. Require lists of strings for
  authors/keywords and explicit nullable scalar types. Reject wrong shapes
  instead of coercing them into plausible metadata.
- Parse one complete JSON value, optionally one complete Markdown fence.
  Reject duplicate keys, non-finite numbers, trailing prose, and truncated data.
  Validate fields after parsing, and retain the original response for inspection.
- Require unique integer ranks excluding booleans and bounded by the candidates
  actually sent. Define whether a valid partial ordering is permitted; append
  omitted candidates deterministically without accepting invented indices.
- Request constrained JSON when supported, with a declared fallback for providers
  lacking that capability. Keep independent validation in every path.
- Add explicit token/input budgets, timeout configuration, and typed outcomes:
  disabled, success, abstained, invalid response, timeout, and provider error.
  Preserve resolver-only fallback, but report when and why it occurred.
- Keep Needle out of automatic bibliographic-field repair. It may generate a
  separately reviewed proposal, never silently rewrite the original response.

**Acceptance:** deterministic tests cover both transports, malformed fields,
duplicate keys, non-finite numbers, booleans/duplicates/out-of-range ranks,
empty responses, truncation, and timeout. Every failure produces a visible
outcome without crashing verification or claiming model success. A failed model
call still permits a clearly labeled resolver-only result.

### CG-2 — correct evidence status and preserve model provenance (P0)

Addresses CG-F4–F5. The identity-status repair can start alongside CG-1;
model diagnostics depend on CG-1's outcome contract.

- Derive source identity from an actual resolver result and its provenance.
  A generated key or nonempty title must not turn a placeholder into a resolved
  work. Preserve negative search results distinctly from provider failure.
- Keep identity match, topical relevance, and claim support as separate fields.
  A match-score threshold may identify a review candidate; it cannot establish
  support without a source passage and a reviewed relationship to the claim.
- For required source-route restrictions, enforce them at the resolver boundary
  or return an explicit unsupported-policy result before fetching.
- Record original query fields, model-proposed fields, accepted/rejected changes,
  candidate IDs, score/rank effects, model identity, prompt/schema version,
  validation outcome, and timings. Keep private raw responses outside public
  BibTeX output; exports can carry an audit-record identifier.
- Preserve existing explicit fields and conflicts. Ensure inferred clues do not
  increase confidence as though they were independent source observations.

**Acceptance:** a no-match fixture stays unresolved at every nested level;
source failure and genuine empty search remain distinguishable. A round-trip
audit explains each accepted hint and rank change. Required route restrictions
cannot be bypassed by the adapter. No new path promotes candidates automatically.

### CG-3 — qualify assistance on real bibliography tasks (P1)

Depends on CG-1–CG-2. Use the existing parser comparisons and verifier tests as
the starting point.

1. Assemble a versioned, reviewed corpus: at least 60 references spanning exact
   identifiers, abbreviated/OCR references, ambiguous authors/years, similar
   titles, books/chapters, and unresolved or contradictory cases. Reserve at
   least 20 unseen cases before prompt tuning. These are initial screen sizes,
   not evidence of a population error rate.
2. Freeze resolver responses for paired comparisons. Run resolver-only, expand,
   rerank, and both roles separately. Use the same candidates and input budgets
   when comparing Q4, Q2, and IQ3. Evaluate live-source drift separately.
3. Report correct top identity, candidate recall, false matches, abstention,
   unsupported field suggestions, field preservation, schema failure, and wall
   time per correct result. Report how often reranking actually changes output.
4. Preserve tie-breaking as the default. Consider wider advisory reranking only
   if held-out results justify it; report its score separately from resolver
   identity evidence and retain conflicts for review.
5. Separate optional live connectivity smoke tests from qualification. Missing
   services can make a smoke test skip; a qualification run with missing outputs
   must be marked incomplete, never successful.

**Acceptance:** publish all case denominators and failures, pin model/runtime/
prompt/corpus hashes, and retain raw private responses. No critical fixture may
silently accept invented identifiers or promote a false source identity. Adopt
assistance only where paired results show useful accuracy, review-time, or speed
benefit without an unexplained increase in false matches. Otherwise keep it opt-in.

### CG-4 — make batches recoverable and affordable (P2)

Depends on CG-1–CG-2; throughput tuning follows CG-3.

- Extend the core batch runner with stable job IDs, input hashes, durable
  pending/running/completed/failed outcomes, atomic receipts, and explicit resume.
  Design recovery around database transaction boundaries and idempotent writes.
- Reuse existing source retries/cache. Add model-call retry limits and avoid
  retrying malformed output indefinitely. Cache model results only with matching
  input, model revision, prompt, schema, and inference settings.
- Measure cold load, hash-verification time, queue wait, prompt processing,
  decode, metadata retrieval, and validation separately. Start with one slot;
  batch by resident model rather than repeatedly loading different weights.
- Present review summaries of changed fields, unresolved cases, fallback use,
  and conflicts. Track accepted corrections per reviewer minute.

**Acceptance:** interrupt after one committed job, resume without duplicated
entries or lost review state, and retry only eligible jobs. Changed inputs or
schemas invalidate cached results. Receipts identify partial completion.

### CG-5 — keep examples, checks, and plans aligned (P1, ongoing)

- Add an automated offline CI entry point using the existing tests; no GitHub
  workflow was present in the inspected checkout. Keep live-source tests opt-in.
- Add executable provider examples for local llama.cpp and Ollama with explicit
  URL conventions, supported capabilities, failure outcomes, and output budgets.
- Add CLI/library contract fixtures for JSON validation and evidence status.
  Coordinate wider MCP/export coverage with the existing main roadmap.
- Give this roadmap's packages links to their eventual changes and evidence.
  Distinguish code completion, passing fixtures, live qualification, and adoption.

**Acceptance:** a fresh supported environment can run the offline checks; every
advertised provider example either reaches its intended transport or fails
explicitly. Model absence cannot be reported as successful qualification.

## Coordination and first changes

The first three priorities were **CG-1 response validation**, **CG-2 identity
status repair**, then **CG-2 audit records plus CG-3 frozen evaluation fixtures**.
Initial slices now exist in the working tree; close each item only with regression
evidence and explicit qualification status. Remaining work can proceed while
GroundRecall's separate store-reconciliation gate remains unresolved.

The [main roadmap](../ROADMAP.md) remains the project entry point. This plan
refines its existing quality and audit priorities. It complements the
[sources-first plan](../new-roadmap.md),
[graph integration plan](epistemap-knowledge-graph-roadmap.md), and
[GroundRecall companion plan](groundrecall-unified-retrieval-integration-plan.md).
Preserve their authority and confidence-migration boundaries.

Coordinate a versioned citation handoff with Didactopus: source/fragment anchors,
draft citation IDs, resolved work IDs when available, per-field provenance,
identity/relevance/support states, errors, and review disposition. CiteGeist
owns bibliographic identity; Didactopus owns educational use and learner evidence.
Contract fixtures should include unresolved references and conflicting editions.

For deployment, retain the preferred model registry and pinned llama.cpp build.
Use Laya only for an evaluated advisory labeling task. Keep deterministic JSON
validation mandatory; Needle remains experimental. Gorlim requires full weight
hash verification before launch. Host reliability and task quality are separate
acceptance questions.
