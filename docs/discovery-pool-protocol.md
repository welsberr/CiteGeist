# Discovery-pool recording and judgment protocol

`citegeist research` can write one bounded search as a private, unlabelled
candidate pool. This preserves what the selected sources returned so later ranking
comparisons use a fixed candidate set rather than rerunning changing provider
searches. A local search also records a path-independent fingerprint of the
bibliographic entries visible in its SQLite snapshot.

Research questions, abstracts, local metadata, labels, and experiment receipts can
be sensitive. Choose a private location outside the repository. The commands
refuse to overwrite files and create artifacts with owner-only permissions. A
hash binds judgments to exact bytes; it does not anonymize query or candidate data.

Record a search explicitly:

```sh
PYTHONPATH=src .venv/bin/python -m citegeist research \
  "research question" --source local --source crossref \
  --record-pool /private/citegeist/pools/search-001.json
```

The pool stores the normalized request, retrieval timestamp, selected providers,
provider status and count, stable candidate IDs, provider ranks, selected
bibliographic fields, a local-corpus snapshot fingerprint when applicable, and a
candidate-inventory hash. It excludes raw provider error strings, URLs,
credentials, and request headers. Unknown provider outcomes remain unknown. DOI,
arXiv, PMID, OpenAlex, and ISBN identities are scheme qualified; candidates
without one retain a provider-qualified citation key. A duplicate identity fails
visibly. Conflicting values for retained fields are recorded for review. A pool
ID is deterministic over its request, outcomes, corpus fingerprint, and
inventory; the run ID also includes retrieval time. Re-running a provider search
may produce a new pool. Replay means reusing the recorded bytes.

Assemble several searches only after assigning their related-work families to
splits. The manifest must assign every case exactly once, and CiteGeist rejects a
topic family that crosses development, validation, and holdout:

```sh
PYTHONPATH=src .venv/bin/python -m citegeist assemble-pool \
  --pool /private/citegeist/pools/search-001.json \
  --pool /private/citegeist/pools/search-002.json \
  --splits /private/citegeist/task-splits.json \
  --output /private/citegeist/task-set.json
```

The split manifest has `schema_version: 1`, `rubric_version:
research-relevance-v3`, and an `assignments` list. Each item has a recorded
`case_id`, a `split` (`development`, `validation`, or `holdout`), and a
`topic_family`. Case IDs appear in each source pool's `cases` array. Assign
related questions together before exposing judgment templates to reviewers.

Make and complete a separate judgment artifact for one split at a time:

```sh
PYTHONPATH=src .venv/bin/python -m citegeist label-template \
  --pool /private/citegeist/task-set.json --split development --reviewer-id reviewer-a \
  --output /private/citegeist/labels/development.json
```

For double-reviewed work, create one template per reviewer using distinct private
reviewer codes. Have them label independently before comparing. The
[task-inventory and review protocol](research-task-inventory-and-review.md)
defines task strata, blinding, rubric guidance, and calibration. Use
`compare-reviews` to create an agreement/disagreement report with unresolved
decisions, then fill every disputed dimension and run `adjudicate-reviews`. The
adjudicated artifact preserves both source labels and their hashes; `prepare-rank-pool`
accepts it and carries that review provenance forward. The compare step never
averages judgments or silently resolves differences.

The rubric records relevance as `not_relevant`, `background`, `useful`, or
`essential`, plus separate identity correctness, version match, source authority,
and evidence support. Treat `useful` and `essential` as relevant for the current
binary ranking metrics; validation also reports graded nDCG from the four-level
judgment. `background` is contextual but not directly useful for answering the
task. Templates start with relevance `unjudged` and other dimensions `unassessed`;
every candidate must receive an explicit relevance decision before export.
Unjudged candidates cannot silently become negatives. The judgment file records
the exact pool SHA-256 and rubric version. Store reviewer identity and notes
separately; do not add them to exported development pools.

Export the reviewed data into the schema accepted by `experiment-rank`:

```sh
PYTHONPATH=src .venv/bin/python -m citegeist prepare-rank-pool \
  --pool /private/citegeist/task-set.json --split development \
  --judgments /private/citegeist/labels/development.json \
  --output /private/citegeist/dev/development.json
```

The join rejects changed pool bytes, wrong pool IDs or rubric versions, duplicate,
missing, or extra case/candidate labels, and unsupported judgments. It writes a
new private artifact with binary `relevant_ids`, the selected split, orthogonal
quality judgments, and provenance hashes. The development runner rejects
validation and holdout pools and checks that every relevant ID belongs to the
fixed candidate set. Judgment templates include a case-level answerability label.
Keep validation and holdout labels outside the proposal process.

After development selects a finalist, the maintainer can register it against one
validation task set and a minimum useful effect before opening validation labels:

```sh
PYTHONPATH=src .venv/bin/python -m citegeist register-validation \
  --development-receipt /private/citegeist/dev/experiment-001.json \
  --validation-pool /private/citegeist/task-set.json \
  --minimum-precision-gain 0.05 \
  --output /private/citegeist/validation/registration.json

PYTHONPATH=src .venv/bin/python -m citegeist validate-rank \
  --validation /private/citegeist/validation/validation-pool.json \
  --registration /private/citegeist/validation/registration.json \
  --output-dir /private/citegeist/validation/receipts
```

Registration reads the unlabelled assembled task set and freezes the development
receipt's baseline, single finalist, exact validation-source bytes, candidate
inventory, and minimum effect before labels are prepared. The validation evaluator
accepts only that registration and a validation-split pool,
checks the declared precision threshold plus selected-result identity, version,
provenance, and graded relevance, then writes aggregate metrics without
query-level results. A private consumption marker beside the validation pool
refuses a second evaluation of that pool even if a different receipt output
directory or registration copy is used. A result may justify a separately reviewed
holdout proposal; it does not change defaults. This is an operator workflow, not
an OS-level security boundary. The maintainer must keep validation files and the
marker directory unreadable to proposal agents and register the finalist before
opening labels. A process with the same file access can bypass this convention by
copying the pool or removing the marker.

After a passing validation receipt, the maintainer may register a single holdout
comparison before preparing/opening holdout labels:

```sh
PYTHONPATH=src .venv/bin/python -m citegeist register-holdout \
  --validation-receipt /private/citegeist/validation/receipts/validation-taskset.json \
  --validation-registration /private/citegeist/validation/registration.json \
  --holdout-pool /private/citegeist/holdout-task-set.json \
  --minimum-precision-gain 0.05 \
  --maximum-recall-loss 0.02 \
  --maximum-empty-relevance-regression 0 \
  --maximum-unanswerable-false-positive-regression 0 \
  --maximum-unanswerable-false-positives 0 \
  --maximum-source-coverage-loss 0 \
  --output /private/citegeist/holdout/registration.json

PYTHONPATH=src .venv/bin/python -m citegeist evaluate-holdout \
  --holdout /private/citegeist/holdout/prepared-pool.json \
  --registration /private/citegeist/holdout/registration.json \
  --output-dir /private/citegeist/holdout/receipts
```

The recorder, task-set assembler, local-corpus fingerprint, split-bound judgments,
expanded rubric, double-review comparison/adjudication workflow, aggregate-only
validation evaluator, and one-shot holdout evaluator are implemented. `register-holdout`
requires a passing validation receipt and freezes quality and coverage tolerances;
`evaluate-holdout` writes only aggregate results and a pool-scoped consumption marker.
No human-reviewed task set or labels are checked in. External access isolation and
operator protection of the holdout labels and marker remain necessary. Reviewers now
record answerability per case and the evaluator counts top-k results returned for
explicitly unanswerable cases. The ranker has no abstention threshold, so a strict
false-positive gate will retain the baseline until a separate abstention policy is
tested. These commands prepare evidence; they do not make the search system
self-modify or promote a ranking configuration.
