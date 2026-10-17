# CiteGeist discovery and improvement roadmap

Status: staged implementation; C5a development runner implemented, later validation gates remain proposed.
Prepared: 17 October 2026.
Audience: CiteGeist maintainer, implementing agents, and research reviewers.

CiteGeist should help a researcher find useful sources, understand their relevance,
and resume the investigation later. The next investment should establish a reliable
discovery workflow and the means to measure it. Once that foundation exists,
agents can propose and test improvements within a bounded experiment process.
Adoption should depend on independent evidence of usefulness.

Success means more useful, distinct references found per unit of researcher effort,
with accurate identity, visible uncertainty, and reproducible search coverage.
Entry counts, model confidence, citation popularity, and benchmark scores alone
are insufficient measures of success.

## Scope and existing commitments

This roadmap covers research literature and general references: articles, books,
chapters, reports, theses, datasets, documentation, and authoritative web material.
It extends the [main roadmap](../ROADMAP.md), reuses the
[source plan](../new-roadmap.md), and incorporates the
[process improvement plan](process-improvement-roadmap.md). Its initial releases
should improve everyday discovery while creating reusable research infrastructure.

The process plan's model validation, truthful identity reporting, provenance,
and mandatory source restrictions remain prerequisites for expanding model-assisted
use. Recheck those findings against current code before implementing fixes; do not
assume an older plan establishes the current defect state.

The [GroundRecall integration plan](groundrecall-unified-retrieval-integration-plan.md)
remains separately gated on its store-reconciliation work. CiteGeist discovery and
evaluation can proceed without that integration. CiteGeist retains authority over
bibliographic identity, field provenance, conflicts, and citation review. The
[existing operating model](AGENTIC_OS.md) continues to govern publication.

This plan does not authorize deployment, scheduled searches, model training,
unbounded experimentation, or changes to canonical memory. Those are separate
implementation and operating decisions.

## Observed starting point

The following observations come from the local working tree and read-only database
queries on 17 October 2026. They describe this checkout, including uncommitted work,
rather than a released or live-qualified version.

| Observation | Operational implication |
| --- | --- |
| `talkorigins.sqlite3` has 152,961 entries, 1,039 topics, 34,217 nonempty abstracts, and zero nonempty stored full-text fields. | Only 22.4% of entries have abstracts; targeted enrichment should accompany retrieval work. This does not establish whether documents exist elsewhere. |
| At the captured baseline, `library.sqlite3` had zero entries and topics; the database is local state and should be rechecked per run. | Every search needs visible corpus identity and an explicit empty-corpus outcome. |
| Topic bootstrap searches OpenAlex, PubMed, Crossref, and DataCite with fixed provider bonuses. | Available adapters and useful source types are not consistently exposed through discovery. |
| At the captured baseline, seed overlap used citation-key tokens against candidate titles. The current working tree also uses seed bibliographic content. | Seed titles, abstracts, and identifiers remain an opportunity for better relevance. |
| Bootstrap candidate consolidation uses citation keys. | Discovery needs explicit cross-provider identity reconciliation, including edition/version distinctions. |
| At the captured baseline, the core batch runner collected results in memory. The current working tree adds per-job receipts and resume. | Interruption recovery now has an initial implementation; interrupted-job and partial-run recovery still need qualification. |

Evidence locations: [bootstrap](../src/citegeist/bootstrap.py),
[storage](../src/citegeist/storage.py), [batch runner](../src/citegeist/batch.py),
[source catalog](../src/citegeist/sources/catalog.py), and
[general-material discovery](../src/citegeist/discovery.py).
FTS query compilation and database diagnostics already exist; reconcile the older
[search hardening plan](topic-search-hardening-roadmap.md) with these implementations
instead of rebuilding them. These observations are not a retrieval-quality benchmark.

## Capability roadmap

Work packages below describe the target capability and acceptance criteria. Some
initial slices now exist in this uncommitted working tree; implementation presence
does not mean the acceptance criteria or live behavior are qualified. Assign an
implementation owner and reviewer when each starts. Each package should produce a
reviewable change, focused verification, and evidence linked back here. Progress is
gated by outcomes rather than calendar estimates.

### C0 Establish a reproducible baseline

Create a small, versioned research-question set and a run receipt before changing
ranking. The current `eval_baseline` scorer and synthetic fixtures provide receipt
plumbing only; they are not a human-reviewed relevance baseline. A research run
should capture revision plus working-tree diff hash, database identity and snapshot,
query, filters, provider requests, candidate identities, timings, errors, and result
ordering. Record model, prompt, schema, and inference settings when applicable.

Expose empty corpus, no matches, unknown topic, partial retrieval, and provider
failure as separate outcomes. Add a read-only capability report for configured
sources, credentials present or missing without revealing them, and index health.
Reuse existing diagnostics, caches, and fixture infrastructure.

Acceptance: a fixed local/recorded-source query can be replayed with the same
candidate identities and ordering; the receipt explains any intentional variation.
A deliberately unavailable provider produces a visible partial or failed run.
Refresh applicable process-plan regressions before model-assisted experiments.

### C1 Provide one discovery contract

Accept a research brief containing question, intended use, seed references,
inclusions/exclusions, source types, language, date limits, and resource budget.
Keep plain topic input as a convenient default. Support local-only, external-only,
and combined search with explicit coverage reporting.

Route the brief through existing source capabilities. Make provider selection
inspectable and overridable. Apply mandatory restrictions before network calls;
reject unsupported requirements. Adapt existing resolver and plugin implementations
behind this contract rather than maintaining another independent provider stack.

Return candidates before admission to the bibliography. Each candidate needs its
original provider record, normalized identifiers, source type, retrieval time,
matched query, and separate identity and relevance states. Reconcile identities
across providers while preserving unresolved conflicts. Link preprints, published
versions, books, editions, and translations without merging them indiscriminately.

Acceptance: the same brief and result schema works through CLI and app/MCP adapters.
Fixtures cover an article, book edition, institutional report, dataset, and web
reference, including a duplicate and a forbidden route that is never called.
Unsupported source types are reported as coverage gaps. Legacy commands remain usable.

### C2 Improve ranking and researcher review

Replace citation-key seed overlap with seed content. Establish a lexical baseline
with explicit field weighting and a transparent combination of provider result lists.
Keep identity evidence separate from relevance scores; do not present an uncalibrated
ranking score as a probability. Preserve individual signals for later ablation.

Add a review queue with result excerpts, discovery reason, source type, version,
access status, and conflicts. Save research sessions with query revisions, candidate
decisions, and reasons such as relevant, wrong topic, wrong edition, duplicate,
background only, or already known. A relevance decision must not verify identity
or assert claim support. Reviewer corrections must remain reversible.

Acceptance: a researcher can find, inspect, accept or reject, and export a reviewed
subset, then resume without repeating decisions. Stable result IDs survive reranking.
The C0 benchmark compares old and new ranking; a quality claim requires evaluation,
even when the implementation passes functional tests.

### C3 Enrich references for evidence inspection

Acquire missing abstracts for active topics and promising candidates first. Then
add permitted document retrieval and text extraction with checksums, extraction
version, rights/access metadata, and page or section anchors. Track unavailable,
not attempted, extraction failed, and successfully extracted states separately.
Keep document content in a suitable artifact store with references from SQLite.

For general references, retain institutional authors, report numbers, editions,
versions, publication/update and retrieval dates, stable URLs, and dataset vintages.
Support document import and URL capture before investing in a broad web crawler.
Treat a webpage's identity and its authority for a specific question separately.

Provide passage-level inspection and candidate claim relationships, including
contradicting or limiting evidence. Label title-only, abstract-based, and full-text
judgments distinctly. Citation edges and model explanations cannot establish support.

Acceptance: a reviewed excerpt can be traced to the exact retained document version
and location. A failed download cannot appear as inspected full text. A book edition,
changing web page, and revised dataset retain their distinct citation requirements.

### C4 Make acquisition resumable and bounded

Extend the batch runner with stable job IDs, input hashes, durable outcomes,
transaction-aware checkpoints, and explicit resume. Coordinate retry and rate limits
per provider; distinguish invalid requests, transient failures, and genuine emptiness.
Record cache age and provide explicit refresh behavior. Include source, model, prompt,
and schema revisions in relevant cache keys.

Bound graph expansion by requests, time, candidate count, and novelty. Report the
stop reason and unsearched scope. Use accepted seeds while allowing deliberate
searches for competing explanations and overlooked source types. Saved-search
updates remain opt-in and produce review candidates, not silent bibliography edits.

Acceptance: interrupt after a committed job and resume without duplicate writes or
lost decisions. Changed inputs invalidate inappropriate reuse. A rate-limited source
does not stop unrelated eligible work, and the overall result remains honestly partial.

### C5 Establish an isolated experiment runner

**C5a — bounded development proposals (implemented).** `citegeist experiment-rank`
accepts a fixed recorded candidate pool and at most 16 JSON ranking configurations.
Only allowlisted numeric weights are interpreted; proposals cannot supply candidate
IDs, executable code, evaluators, or labels. The runner uses no network or database,
records input hashes and repository revision, caps cases and candidates, preserves
all tried configurations in its receipt, and never promotes a result. Development
results are for generating hypotheses only. The command is not an OS-level sandbox;
use non-sensitive pools and a private output directory.

**C5b — controlled validation (next).** Create a separate reviewed validation pool
and a maintainer-operated comparison that evaluates one preselected finalist against
the baseline. Do not return per-case validation failures to the proposal agent or
allow it to revise candidates against the same validation labels. Record uncertainty,
cost, coverage, and critical invariant checks.

**C5c — sealed holdout and decision record (later).** Run a one-shot release check
under maintainer control against a separately held set. Validate every returned ID
against the immutable candidate pool and report gated aggregate results. Preserve the
previous configuration, pilot scope, monitoring window, and rollback reference.

Acceptance for C5a: a second development run reconstructs the same scores from the
same pool/configuration bytes; arbitrary IDs, executable proposal fields, malformed
weights, oversized inputs, and output overwrite are rejected. Validation and locked
holdout inputs are not accepted by the development command. Promotion remains a
separate human decision.

### Delivery order

1. C0 and a compact benchmark establish the baseline; repair confirmed process-plan
   blockers before expanding model assistance.
2. C1 and C2 deliver the first useful discovery-and-review release.
3. C4 supplies recovery before unattended or substantial enrichment work; C3 can
   begin with a small, manually initiated corpus pilot.
4. C5a supports controlled development proposals. R7 remains restricted to
   configuration-only proposals on recorded pools; validation and locked-holdout
   controls must pass before claiming generalization. Executable code, prompt, or
   model-weight self-modification is outside this roadmap's current authority.

Retain SQLite and BibTeX. Defer a database replacement, large vector service,
autonomous code evolution, and model fine-tuning until a measured bottleneck justifies
their cost. Documentation-only and offline evaluation work can proceed independently
of unavailable external services.

## Research plan

### Questions and benchmark design

Start with 60 reviewed tasks: 20 for development, 20 for validation and candidate
selection, and 20 held out for release decisions. This is a pilot, not enough to
establish small error rates or strong conclusions about every source type. Expand
the set based on observed variance and the effect size worth detecting.

Stratify tasks across known-item lookup, exploratory discovery, methods/evidence
questions, books and general references, recent updates, and ambiguous or no-answer
cases. Include domains outside TalkOrigins. Split by topic and related-work family
to reduce leakage through paraphrases or near-duplicate sources. Include missing
abstracts, wrong editions, highly cited distractors, contradictory evidence,
provider failures, and malicious instructions embedded in retrieved material.

For exploratory questions, pool candidates from all compared systems, hide system
identity and order, and review against a written relevance rubric. Mark unjudged
results as unjudged rather than irrelevant. Report recall of known relevant sources
as a lower-bound coverage measure; a pooled list is not the entire relevant literature.
Double-review a stratified subset and adjudicate disagreements. Record reviewer time.

Use deterministic checks for identifiers, provenance, forbidden calls, and state
changes. Human review determines usefulness and passage support. Model graders may
assist triage after calibration against human judgments, but cannot alone qualify
identity, support, or a production change.

### Experiment sequence

| Experiment | Hypothesis and comparison | What the result informs |
| --- | --- | --- |
| R1 Ranking | Seed-content matching and rank fusion improve useful top-ten results over fixed provider bonuses. Hold the candidate pool fixed. | Adopt simpler ranking first; diagnose retrieval separately if relevant works never enter the pool. |
| R2 Source routing | Task-specific routing finds additional useful source types within the same request budget. Compare fixed sources, routed sources, and a budget-matched broad search. | Add adapters only where they supply marginal accepted references or fill documented gaps. |
| R3 Enrichment | Abstract acquisition improves ranking and review efficiency; passage access improves evidence assessment. Compare matched records before/after enrichment. | Prioritize acquisition by measured benefit; distinguish newly retrieved documents from better interpretation of existing candidates. |
| R4 Semantic retrieval | Semantic candidates or reranking recover relevant works missed by lexical search. Compare lexical-only, semantic-only, and hybrid on fixed snapshots. | Adopt local or external semantic components only for demonstrated quality/cost benefits; record external query exposure and reproducibility limits. |
| R5 Iterative discovery | Bounded citation expansion and query reformulation improve coverage beyond a single search. Match total calls and elapsed budgets. | Determine useful depth, stopping rules, and whether agent planning adds value beyond scripted iteration. |
| R6 Feedback | Reviewed session feedback improves later related tasks without suppressing new perspectives. Use chronological splits and opt-in session data. | Establish scope and expiry for preferences; avoid treating clicks or acceptance as universal truth. |
| R7 Agent-proposed ranking configuration | Agent-proposed allowlisted ranking weights improve fixed-pool development results over the baseline and manual proposals under equal trial budgets. | C5a tests proposal plumbing only; C5b/C5c decide whether a candidate generalizes and merits an opt-in pilot. No executable code, prompt, or model-weight mutation. |

R1 and R2 follow C0–C2. R3 follows C3; R4 can begin on abstracts without full text.
R5 requires C4. R6 requires accumulated reviewed sessions. R7's development stage
requires C5a; any adoption claim requires C5b/C5c and human-reviewed labels. Change
one major factor at a time; subsequently test interactions and remove components to
establish which ones caused a benefit.

### Measurements and run protocol

Use useful distinct references in the first ten results as the default primary
discovery metric. Also report graded ranking quality, known-relevant recall at a
fixed candidate budget, duplicate/false-merge rates, coverage by source type,
identity errors, unsupported support assertions, and appropriate abstention.
For usability studies, measure elapsed review time per accepted useful reference
and time to the first useful result. An accepted reference is not necessarily true
or supportive; those judgments have their own rubric.

Measure latency distributions, provider requests, tokens, monetary cost when known,
cache hit rate, and partial-run frequency. Record full end-to-end costs, including
candidate generation and optimization, rather than inference cost alone.

Before each experiment, freeze its hypothesis, primary metric, comparator, minimum
useful effect, tolerated regressions, resource ceiling, and analysis plan. Proposed
pilot targets are one additional useful reference per ten results, or a 20% reduction
in median review time with no material relevance loss. These are project choices
to assess against baseline variance, not established scientific thresholds.

Use paired task comparisons and uncertainty intervals, with the task as the unit
of analysis. Repeat stochastic trials under pinned settings; three initial repeats
can reveal instability but are not a universal sample-size rule. Report all task
and trial counts, failures, and per-domain results. Record every candidate tested;
do not hide selection across many attempts behind a single favorable score.

Keep recorded-source experiments separate from live-provider checks. The former
isolate system changes; the latter test current access, coverage, and drift. Missing
providers or models make required qualification incomplete. They must not be counted
as successful skips. Compare cache-warm and cache-cold performance separately.

## How results determine the next step

| Evidence | Decision |
| --- | --- |
| Practical gain, uncertainty supports improvement, critical checks pass, costs within budget | Move to an opt-in pilot, then consider changing the default after reviewing pilot evidence. |
| Gain is confined to a domain or task type | Adopt as a scoped profile and preserve the baseline elsewhere. |
| Faster or cheaper with demonstrated non-inferior quality | Consider adoption using a predeclared non-inferiority margin; failure to detect a difference is insufficient. |
| Promising average but uncertain or inconsistent results | Keep experimental; collect targeted additional tasks or simplify the candidate. Do not declare success. |
| Better ranking but poor candidate recall | Invest in query formulation, coverage, or routing before further reranking. |
| Better offline score but no researcher benefit | Examine rubric and workflow; prefer the simpler system until usefulness is demonstrated. |
| Critical identity, provenance, support, restriction, or evaluation-integrity failure | Reject promotion, diagnose, and add a reviewed regression case. Average gains cannot compensate. |
| No useful gain or excessive cost | Retain the baseline and record the negative result; revisit only with a new hypothesis or changed conditions. |

A release evaluation uses the locked holdout only after candidate selection. Once
its detailed failures are used for development, retire those cases from the locked
set and replenish it. Preserve a separate long-lived regression suite. General
default changes require broader evidence than a small domain pilot.

For every adoption, retain the previous version, affected configuration, migration
and rollback procedure, expected benefit, monitoring window, and responsible owner.
Start with an opt-in comparison that cannot mutate reviewed records. During the first
20 reviewed pilot sessions, inspect failures weekly or after each five sessions,
whichever occurs first. Any critical invariant failure stops the pilot; quality or
cost regression beyond the predeclared tolerance triggers rollback and investigation.
These are proposed initial operating limits, adjustable before a pilot begins.

## Guidelines for bounded agent self-improvement

For this project, self-improvement initially means agents using recorded failures
to propose changes to queries, prompts, routing rules, or ranking configuration.
It does not imply model-weight training or permission to change their own authority.

The operating loop is:

**Observe → propose a hypothesis → make an isolated candidate → evaluate → review
the evidence → pilot → adopt or reject → monitor.**

Apply the following project rules:

1. **Separate the proposer from the acceptance mechanism.** An agent may diagnose
   and implement candidate changes. The evaluator and release criteria are protected
   from that candidate. A second model is useful criticism, not guaranteed independence.
2. **Protect evidence and objectives.** The optimizing agent cannot edit locked
   labels, scoring rules, provenance requirements, permissions, or review thresholds.
   Proposed changes to those controls receive a separate review and evaluation version.
3. **Keep experimentation reversible.** Allowlisted files, disposable databases,
   fixed tool permissions, bounded network access, and an external budget/termination
   mechanism constrain each run. Ordinary authorized local work does not require
   repeated approval; promotion authority is defined before the experiment starts.
4. **Prevent circular learning.** Self-generated reflections and citations remain
   hypotheses until checked against independent evidence. Repetition across agent
   outputs is not corroboration. Retrieved text is data, never an instruction to alter
   tools, evaluation, or permissions.
5. **Preserve lineage and failures.** Record parent candidate, change, rationale,
   inputs, outputs, evaluation, costs, and disposition. Do not delete unfavorable runs
   or rewrite historical receipts. Keep private queries and raw traces out of public
   artifacts; use explicit, sanitized export lists.
6. **Optimize usefulness under constraints.** Never reward citation count alone,
   verbosity, unsupported certainty, or avoiding difficult cases. Include failure
   denominators, abstention quality, diversity of useful evidence, and researcher effort.
7. **Require transfer evidence.** A tuned prompt must succeed on unseen tasks and
   plausible source failures. A benchmark gain does not establish general reasoning
   improvement or justify broader autonomy.
8. **Increase autonomy in stages.** Begin with automatic diagnosis and proposals;
   then allow bounded sandbox trials. Keep default changes with the maintainer or
   an explicitly delegated release policy. Code self-modification and weight updates
   need their own scoped research plan and evidence before adoption.

Practical role boundaries are simple: the maintainer sets objectives and release
policy; an experiment agent proposes candidates; an isolated runner produces receipts;
a reviewer checks evidence and researcher usefulness. One person may fill multiple
roles, but the optimizing process must not gain write access to its own acceptance
controls. No multi-agent architecture is required for these separations.

## External guidance and research basis

There is useful guidance, but no single cited source establishes a complete standard
for safe, effective self-improvement in a bibliography agent. The rules above are
CiteGeist design recommendations informed by these distinct kinds of evidence.

- **Operational governance:** The [NIST AI Risk Management Framework core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)
  organizes work around Govern, Map, Measure, and Manage, including monitoring and
  feedback. Use it to assign responsibility and make evaluation and response ongoing.
  It is voluntary general guidance, not a self-improvement algorithm or certification.
- **Agent evaluation practice:** Anthropic's [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
  describes combining code, model, and human grading and evaluating agent outcomes
  alongside execution traces. This supports a mixed evaluation strategy; it does not
  validate CiteGeist's particular metrics or adoption thresholds.
- **Prompt optimization research:** [GEPA, version 2](https://arxiv.org/abs/2507.19457v2)
  proposes using execution traces and language-based reflection to generate and test
  prompt updates. This motivates R7's narrow prompt/configuration experiment. Its
  reported task results are not evidence of better bibliographic discovery here.
- **Code self-improvement research:** [Darwin Gödel Machine, version 3](https://arxiv.org/abs/2505.22954v3)
  studies iterative agent-code modification evaluated on coding benchmarks, with
  sandboxing and human oversight. It motivates preserving candidate lineage and
  testing alternatives, but supplies no guarantee that unrestricted changes improve
  research quality or remain appropriate outside its experiments.

Sources checked on 17 October 2026. External empirical results motivate hypotheses;
only local, task-relevant evaluation can justify CiteGeist adoption.

## First implementation handoff

The repository contains C0 receipt plumbing, a minimal C1 read-only brief/report,
a seed-content ranking slice, C4 initial batch receipts, and now C5a's bounded
configuration experiment runner. The current synthetic benchmark is not empirical
relevance evidence. Next, create manually reviewed development pools and separately
controlled validation labels, exercise rejection/budget cases, and improve provider
failure visibility. Keep the GroundRecall pilot separately gated. No executable
code self-modification, model training, automatic promotion, or persistent memory
mutation is part of this handoff. Each handoff should identify changed files, checks
performed, evidence location, unresolved issues, and the next decision it enables.

Before launching any experiment, fill in this compact record:

```text
Question and hypothesis:
Owner and reviewer:
Baseline revision, working-tree hash, and corpus snapshot:
Candidate changes and permitted write locations:
Development, validation, and locked evaluation versions:
Primary metric, minimum useful effect, and tolerated regressions:
Critical checks and forbidden state changes:
Trial count, resource ceiling, and stopping rule:
Private artifacts and sanitized report destination:
Result, uncertainty, subgroup effects, failures, and total cost:
Decision, scope, pilot monitoring, and rollback reference:
```

Preserve negative and incomplete findings. The programme succeeds when its evidence
helps choose the next useful change, including a decision to keep the current system.
