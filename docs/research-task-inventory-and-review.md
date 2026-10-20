# Research task inventory and review protocol

This protocol turns recorded CiteGeist searches into a reviewed benchmark while
keeping labels separate from candidate generation. It is a curation and review
procedure, not evidence that a particular ranking is useful. Keep task inventories,
queries, candidate pools, reviewer codes, labels, and receipts in private storage.

## Curate the tasks before reviewing candidates

Create one task record for each information need. Assign stable, opaque `case_id`
and `topic_family` values, then assign the family to development, validation, or
holdout before any candidate labels are collected. A task inventory should include:

```json
{
  "schema_version": 1,
  "inventory_id": "citegeist-pilot-2026-01",
  "rubric_version": "research-relevance-v2",
  "tasks": [
    {
      "case_id": "case-example-001",
      "query": "REPLACE WITH A REAL, REVIEWED INFORMATION NEED",
      "task_type": "known_item",
      "topic_family": "example-family",
      "split": "development",
      "expected_answerability": "answerable",
      "reference_seeds": [],
      "curation_note": "REPLACE; keep identifying notes private"
    }
  ]
}
```

The example is a schema illustration only; it is not a benchmark task. Do not
populate the research set with model-generated questions or labels and treat those
as human evidence. Researchers should contribute real information needs sampled
from their work, and a curator should remove duplicates, combine paraphrases, and
write the intended use clearly enough that two reviewers can apply the rubric.
Keep any known-answer references as private reference notes, not as hints shown to
ranking agents.

Tag tasks across these strata: known-item lookup; exploratory literature discovery;
methods or evidence questions; books and editions; reports and theses; datasets;
documentation or authoritative web references; recent or version-sensitive
updates; and genuinely unanswerable or deliberately out-of-scope questions. A task
may have multiple tags. Track expected answerability as `answerable`,
`no_answer_expected`, or `uncertain`; this is a curator hypothesis, not a label
that forces reviewers to find a source. Include source-type requirements and
exclusions in the task brief where the researcher actually has them.

The 60-task / 20-per-split proposal in the roadmap is a cost-planning pilot, not a
power calculation. Start with a smaller feasibility round if necessary, measure
review time and disagreement, then decide whether to expand. Split by topic family,
project, or closely related question so paraphrases and shared reference lists
cannot cross partitions. Keep holdout tasks and their labels out of development and
validation review until a one-shot release evaluation is authorized by the
maintainer.

For each task, run and record the intended source routes with `citegeist research
--record-pool`. Assemble the recorded pools only after the split manifest is
reviewed. Record incomplete providers and no-result outcomes faithfully; a failed
provider is not evidence that no relevant work exists. Freeze the pool bytes before
labeling. If the query, sources, candidate set, or split changes, issue a new pool
and repeat review rather than editing a labeled task set in place.

## Independent review

Create one template per reviewer. Give reviewers the same task brief and fixed
candidate set, but keep them blind to each other's labels, ranking scores, and the
proposed configuration. Candidate display order should be randomized per reviewer
where the review interface permits it. Hide provider rank and model-generated
relevance explanations. Show enough bibliographic evidence to assess identity,
version, authority, and relevance, including source provenance and access limits.
If a reviewer cannot inspect enough evidence, use `uncertain` or `unassessed`; do
not infer relevance from title similarity alone.

```sh
citegeist label-template --pool /private/task-set.json --split development \
  --reviewer-id reviewer-a --output /private/review-a.json
citegeist label-template --pool /private/task-set.json --split development \
  --reviewer-id reviewer-b --output /private/review-b.json
```

Use private reviewer codes instead of names in machine artifacts. Keep free-text
rationales in a separate private file keyed by case and candidate. Reviewers should
apply the dimensions independently:

| Dimension | Guidance |
| --- | --- |
| `relevance` | `essential` directly satisfies the need; `useful` materially helps; `background` gives context but does not answer it; `not_relevant` does not help. Use `unjudged` only while work is incomplete. |
| `identity_correct` | Does the record identify the intended work or resource? A similar title is not enough. Use `uncertain` when identifiers or metadata conflict. |
| `version_match` | Does the cited edition, preprint/published version, dataset vintage, or documentation version fit the task? Use `not_applicable` when no meaningful version distinction exists. |
| `source_authority` | Is this source credible for this specific task? Authority is contextual; popularity and provider rank do not establish it. |
| `evidence_support` | Does inspected content directly support, indirectly inform, or fail to support the task? A title or abstract alone may justify relevance but not direct evidence support. |

Relevance is not identity verification, evidence support, or a claim that a source
is correct. Record uncertainty instead of forcing a binary answer. A `no_answer`
task can still have useful sources that clarify the gap; do not label every result
negative merely because a curator expects no single answer. Conversely, absence of
a known answer is not proof that retrieval found nothing useful.

## Compare and adjudicate

Compare the two completed files only after both reviewers finish:

```sh
citegeist compare-reviews --pool /private/task-set.json \
  --first /private/review-a.json \
  --second /private/review-b.json --output /private/comparison.json
```

The comparison records every dimension-level agreement and disagreement plus both
review hashes. It does not average grades or resolve conflicts. A third reviewer or
designated adjudicator should inspect the disputed candidate and rationale, consult
the task brief and source evidence, and replace `unresolved` in every item in the
`decisions` array with an allowed, completed label. Keep the original comparison
and reviews immutable.

```sh
citegeist adjudicate-reviews --pool /private/task-set.json \
  --first /private/review-a.json \
  --second /private/review-b.json --adjudication /private/comparison.json \
  --adjudicator-id adjudicator-a --output /private/adjudicated.json
citegeist prepare-rank-pool --pool /private/task-set.json \
  --split development --judgments /private/adjudicated.json \
  --output /private/development.json
```

Adjudication requires a decision for each disagreement, rejects extra decisions,
and retains both original values, reviewer codes, reviewer hashes, adjudicator
code, and adjudication hash in the private judgment provenance. Agreements remain
unchanged. Do not resolve a disagreement by majority vote or silently drop it.
If evidence cannot settle it, choose an explicit `uncertain` value for dimensions
that allow it, or document the case as unresolved and exclude it from a metric
under a predeclared rule. Any exclusions must be counted and reported.

Before using the workflow for a benchmark, run a calibration session on separate
practice cases. Discuss where the rubric is unclear, revise it with a new rubric
version, and then have reviewers label the benchmark independently. Report exact
agreement by dimension and the disagreement/adjudication rate. If reporting a
chance-corrected statistic, state its assumptions and prevalence sensitivity;
do not treat one agreement coefficient as a quality score. Retain task-level
uncertainty for diagnosis, but provide the proposal process only the split it is
authorized to use.

## How findings change the next experiment

Review results first identify data or retrieval problems, not permission for an
agent to rewrite itself. If reviewers disagree often about task intent, improve
task wording and calibration before comparing rankers. If identity or edition
errors dominate, work on entity resolution and version handling before tuning
relevance weights. If relevant references are absent from candidate pools, improve
query construction, source routing, and coverage before ranking. If references are
present but consistently buried, define one ranking hypothesis and test it on
development. If uncertainty is concentrated in evidence support, add inspectable
abstracts or document passages rather than making stronger relevance claims.

Keep negative and mixed outcomes. A development gain is a hypothesis; validation
can reject it, and holdout can support only a bounded adoption decision. Any
validation set used to change a proposal is spent for confirmation and must be
replaced before a later confirmatory claim. No result changes production defaults
without maintainer review, an opt-in pilot, and a rollback path.
