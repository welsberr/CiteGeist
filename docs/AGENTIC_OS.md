# CiteGeist AgentOS Entry Point

Last reviewed: 2026-06-27

This repository follows the host-level AgentOS configuration at
`/home/netuser/.agentos`.

Overlay: `citegeist`

Default roles:

- `grounded-research-assistant`
- `repository-engineer`

Required checks:

- `factual-review`
- `public-release`
- `stale-context-audit`

Private by default:

- Unresolved citation candidates.
- Local source paths.
- Draft bibliographies before review.

Public release rule:

- Public citations must resolve to real sources with checked metadata and noted
  uncertainty.

Before publishing citation-derived records, verify source identity, metadata,
and uncertainty notes.

## Bounded ranking experiments

The maintainer owns objectives, benchmark labels, evaluator code, and adoption
decisions. A ranking-proposal agent may inspect an approved development pool and
submit JSON ranking configurations to `citegeist experiment-rank`. The runner accepts
only allowlisted numeric ranking settings (weights and an optional bounded
abstention threshold) and is read-only with respect to the database and
external sources. It writes a new provenance receipt to the requested private path.

The proposal agent must not edit the candidate pool, labels, evaluator, source
permissions, or release rules during a trial. Development scores select hypotheses;
they do not establish generalization. A local proposal executable can be started
through `citegeist sandbox-proposal`, which exposes a sanitized development pool and
one proposal output file inside a network-disabled bubblewrap namespace. It strips
inherited environment variables and does not mount the home directory, repository,
database, validation files, or holdout files. The process may propose numeric JSON
ranking settings only; the trusted maintainer runs the evaluator and controls adoption.

This boundary applies to that child process. It does not constrain an AI tool whose
orchestrator runs outside the namespace, and it is not a substitute for separate OS
accounts or protected mounts for validation and holdout. Validation and locked
holdout data stay outside the proposal loop until a maintainer-controlled evaluation
exists. No configuration is promoted automatically. Candidate pools and receipts
can contain private queries and must not be committed or published without review.
