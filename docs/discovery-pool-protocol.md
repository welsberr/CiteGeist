# Discovery-pool recording and judgment protocol

`citegeist research` can write one bounded search as a private, unlabelled
candidate pool. This preserves what the selected sources returned so that later
ranking comparisons use a fixed candidate set rather than rerunning changing
provider searches.

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
bibliographic fields, and a candidate-inventory hash. It excludes raw provider
error strings, URLs, credentials, and request headers. Unknown provider outcomes
remain unknown. DOI, arXiv, PMID, OpenAlex, and ISBN identities are scheme
qualified; candidates without one retain a provider-qualified citation key. A
duplicate identity fails visibly. Conflicting values for retained fields are
recorded for review. A pool ID is deterministic over its request, outcomes, and
inventory; the run ID also includes retrieval time. Re-running a provider search
may produce a new pool. Replay means reusing the recorded bytes.

Make and complete a separate judgment artifact:

```sh
PYTHONPATH=src .venv/bin/python -m citegeist label-template \
  --pool /private/citegeist/pools/search-001.json \
  --output /private/citegeist/labels/search-001.json
```

The initial rubric is binary relevance: `relevant` or `not_relevant`. Templates
start as `unjudged`; every candidate must receive a judgment before export.
Unjudged candidates cannot silently become negatives. The judgment file records
the exact pool SHA-256 and rubric version. Store reviewer identity and notes
separately; do not add them to exported development pools. More detailed decisions
about topic fit, identity, edition, authority, and evidence support need a reviewed
rubric before being used as ranking targets.

Export the reviewed data into the schema accepted by `experiment-rank`:

```sh
PYTHONPATH=src .venv/bin/python -m citegeist prepare-rank-pool \
  --pool /private/citegeist/pools/search-001.json \
  --judgments /private/citegeist/labels/search-001.json \
  --output /private/citegeist/dev/search-001.json
```

The join rejects changed pool bytes, wrong pool IDs or rubric versions, duplicate,
missing, or extra case/candidate labels, and unsupported labels. It writes a new
private artifact with binary `relevant_ids` and provenance hashes. The ranking
runner separately checks that every relevant ID belongs to the fixed candidate
set. Prepared pools are development data only. Keep validation and holdout labels
outside the proposal process, and use a split manifest created before review.

The first recorder emits one case per search. A reviewed multi-query task-set
assembler, local corpus snapshot fingerprint, richer relevance dimensions,
adjudication workflow, and validation/holdout boundary are still future work. These
commands prepare evidence; they do not make the search system self-modify or
promote a ranking configuration.
