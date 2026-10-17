# Bounded ranking experiment protocol

`citegeist experiment-rank` is the first implementation step for agent-proposed
ranking changes. It evaluates numeric configurations against a fixed, recorded
development candidate pool. It does not discover candidates, call models or
providers, read a bibliography database, or change the default ranker.

The proposal agent receives an approved development pool and may submit at most
16 configurations. Each configuration contains a parent ID, short rationale, and
weights for `lexical`, `seed_overlap`, `provider_rank`, and `source_coverage`. Candidate IDs,
labels, code, prompts, evaluator settings, and permissions cannot be supplied as
proposal fields. Text features are derived deterministically from candidate title,
abstract, keywords, query, seed text, provider identities, and provider ranks.

Run from the repository with a development pool and a proposal JSON file:

```sh
PYTHONPATH=src .venv/bin/python -m citegeist experiment-rank \
  --development /private/citegeist/dev-pool.json \
  --proposals /private/citegeist/proposals.json \
  --output /private/citegeist/run-001.json \
  --k 10
```

The command writes a new receipt and refuses to overwrite an existing file or any
input. It validates unique case/candidate IDs, numeric weight bounds, input size,
case count, candidate count, and trial count. The receipt includes hashes of input
bytes and repository state, every tested configuration and its parent lineage, ranked IDs, per-case
development scores, the selected development finalist, and an explicit statement
that no automatic promotion or locked holdout evaluation occurred.

Example proposal file:

```json
{
  "schema_version": 1,
  "proposals": [
    {
      "id": "baseline",
      "parent_id": null,
      "rationale": "Current lexical-first comparison.",
      "weights": {"lexical": 1.0}
    },
    {
      "id": "seed-balanced",
      "parent_id": "baseline",
      "rationale": "Test whether seed-title overlap improves the first result.",
      "weights": {"lexical": 0.6, "seed_overlap": 0.4}
    }
  ]
}
```

Each pool uses `schema_version: 1`, a unique `pool_id`, and cases containing
`case_id`, `query`, `relevant_ids`, optional `seed_texts`, and a fixed candidate
list. Candidate records contain an `id`, optional BibTeX-like `fields`, `providers`,
and positive-integer `provider_ranks`. See
[`tests/test_ranking_experiment.py`](../tests/test_ranking_experiment.py) for a
small synthetic example. That fixture verifies runner mechanics only; it is not
quality evidence.

This command is intentionally a development tool, not a sandbox against a malicious
or unrestricted process. Its output includes query-level development metrics and
should remain private. Use only non-sensitive development data and store both inputs
and receipts outside public or production paths. Do not pass validation or locked
holdout labels into this command. A promising development result is a hypothesis;
the next step is a separately controlled, maintainer-operated validation. Code,
prompt, model-weight, permission, and evaluation-rule changes are outside the
proposal format. Adoption always requires human review and an explicit rollback plan.
