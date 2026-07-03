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
