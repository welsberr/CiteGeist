# CiteGeist topic-search hardening roadmap

Status: implementation-ready  
Prepared: 2026-08-05  
Primary area: SQLite FTS5 search, topic filtering, database selection, and schema lifecycle

## Objective

Make CiteGeist topic search safe and predictable for ordinary text, punctuation,
hyphenated topic slugs, old databases, empty databases, and databases whose FTS
index is stale or incompatible. A malformed search string must never surface a
raw SQLite exception to CLI, MCP, HTTP, or browser users.

This work hardens the existing SQLite design. It does not introduce semantic
search, replace SQLite, or redesign bibliographic ranking.

## Confirmed failure modes

### 1. Raw user text is parsed as FTS5 syntax

`BibliographyStore.search_text()` passes the query directly to `MATCH` in
`src/citegeist/storage.py`. Inputs such as `natural-selection` and
`human-evolution` are interpreted as FTS expressions and fail with errors such
as `sqlite3.OperationalError: no such column: selection`. Inputs such as `c++`
can produce an FTS5 syntax error.

The populated TalkOrigins database reproduces the problem:

```sh
.venv/bin/citegeist --db talkorigins.sqlite3 \
  search natural-selection --topic natural-selection --limit 1
```

The same topic filter works when the query is supplied as ordinary words:

```sh
.venv/bin/citegeist --db talkorigins.sqlite3 \
  search "natural selection" --topic natural-selection --limit 1
```

### 2. Search behavior depends silently on the selected database

The CLI, MCP adapter, and app server default to `library.sqlite3`. The local
`library.sqlite3` observed during diagnosis had zero entries and zero topics,
while `talkorigins.sqlite3` contained the intended corpus. The default database
also contained orphaned FTS and foreign-key rows. A caller can therefore receive
empty results or `Unknown topic` while believing it searched the populated
corpus.

### 3. Runtime and documented FTS schemas disagree

`docs/schema-current.sql` documents an external-content `entries_fts` table.
Runtime initialization creates a standalone `entry_text_fts` table with a
different name and columns. There is no explicit FTS schema version, validation,
or migration path.

### 4. Index health is not checked before search

SQLite database integrity can be `ok` while the FTS index contains records with
no matching entry or while foreign-key checks fail. Current initialization only
detects whether the SQLite build supports FTS5; it does not establish that the
existing CiteGeist FTS table has the expected schema or contents.

### 5. Error handling differs by interface

The CLI emits a traceback. MCP turns the exception into a generic tool error.
The HTTP bridge emits the raw exception string as a 400 response. None explains
whether the problem is query syntax, database selection, schema compatibility,
or index health.

## Required design decisions

The coding model should make these decisions explicitly before implementation:

1. Treat user queries as literal natural-language text by default.
2. Do not expose raw FTS5 query syntax through the ordinary `search` command.
3. If expert FTS syntax is desired later, add a separate opt-in mode rather than
   overloading the default.
4. Make runtime code the schema authority and generate or update schema
   documentation from that authority.
5. Never drop or rebuild an index automatically without an explicit command,
   backup guidance, and a dry-run or status step.

## Work package 1 — Safe query compilation

Priority: P0

### Tasks

- Add a small, private query compiler in `src/citegeist/storage.py`, or a focused
  module such as `src/citegeist/search.py`.
- Convert ordinary text into a valid literal FTS5 expression.
- Preserve Unicode text and useful tokenization while safely handling:
  hyphens, plus/minus signs, colons, parentheses, quotes, asterisks,
  apostrophes, slashes, and reserved words.
- Define behavior for blank or punctuation-only queries. Prefer a validation
  error over matching the entire corpus.
- Ensure topic slugs remain SQL parameters and are never included in the FTS
  expression.
- Catch `sqlite3.OperationalError` at the storage boundary only when it is an
  FTS query error; re-raise a typed CiteGeist search error with a safe message.
- Keep the non-FTS `LIKE` fallback behavior compatible.

### Tests

Extend `tests/test_storage.py` with parameterized cases for:

- `natural-selection`
- `human-evolution`
- `c++`
- `title: evolution`
- `"quoted phrase"`
- `O'Brien`
- `alpha/beta`
- `()` and punctuation-only input
- Unicode punctuation and non-ASCII terms
- the same cases with `topic_slug` filtering

Add a regression assertion that no case emits a raw `sqlite3.OperationalError`.

### Acceptance criteria

- The confirmed `natural-selection` reproduction succeeds.
- Literal punctuation cannot be interpreted as an FTS column selector or
  operator.
- Ranking still uses `bm25(entry_text_fts)` when FTS5 is healthy.
- Existing plain-word search tests continue to pass.

## Work package 2 — Consistent public errors

Priority: P0

### Tasks

- Introduce typed exceptions such as `SearchQueryError`,
  `SearchIndexError`, and `DatabaseSelectionError`.
- CLI: print a concise message to stderr and return a documented nonzero exit
  code without a traceback for expected user errors.
- MCP: return an actionable error that distinguishes unknown topic, invalid
  query, unavailable FTS, and unhealthy index.
- HTTP bridge: return a stable error object containing a machine-readable code
  and human-readable message. Do not return raw SQLite details by default.
- Browser demo: display the stable message and retain the user's query for
  correction.

### Tests

- Add CLI tests in `tests/test_cli.py` for safe punctuation and clean failures.
- Add MCP tests in `tests/test_mcp.py` for hyphenated topic searches and error
  codes.
- Add app-server tests covering HTTP status and response shape.

### Acceptance criteria

- The same invalid request has equivalent meaning across all interfaces.
- Expected search errors never print a Python traceback or raw SQL.

## Work package 3 — Explicit database identity and selection

Priority: P1

### Tasks

- Add a read-only database summary method reporting path, entry count, topic
  count, topic-membership count, FTS availability, FTS row count, and schema
  version.
- Add a `citegeist db-status` command that prints this summary and exits
  nonzero when required tables are missing or integrity checks fail.
- On CLI startup, include the resolved database path in verbose or diagnostic
  output.
- In the app server, expose database identity and corpus counts through
  capabilities or health details without leaking sensitive paths unless local
  diagnostic mode is enabled.
- Document that TalkOrigins commands require `--db talkorigins.sqlite3` unless
  configuration explicitly selects that database.
- Consider an environment/config default such as `CITEGEIST_DB`; define a clear
  precedence order: command option, environment/config, then local default.
- Do not silently switch from an empty database to another database.

### Tests

- Test option/environment/default precedence.
- Test a valid empty database separately from a populated database.
- Test that an unknown topic error includes the selected database identity or
  a safe hint to run `db-status`.

### Acceptance criteria

- A user can determine which corpus was searched without inspecting source
  code.
- Empty-corpus behavior is distinguishable from zero search matches.

## Work package 4 — One authoritative FTS schema

Priority: P1

### Tasks

- Choose the supported schema after reviewing performance and update behavior:
  the runtime standalone `entry_text_fts` design or a deliberate
  external-content design.
- Record an application schema version in a metadata table.
- Add an expected FTS signature: table name, indexed columns, content mode, and
  tokenizer options.
- Validate the existing virtual table definition from `sqlite_master` before
  enabling FTS search.
- Update `docs/schema-current.sql` to match runtime behavior, preferably from a
  shared schema source rather than duplicated handwritten SQL.
- Add fixtures representing:
  current schema, documented legacy schema, missing FTS table, malformed FTS
  table, and SQLite without FTS5.

### Acceptance criteria

- Opening a legacy or incompatible database produces a diagnostic, not an
  accidental empty index.
- Documentation and runtime schema tests cannot drift unnoticed.

## Work package 5 — Index audit and explicit rebuild

Priority: P1

### Tasks

- Add read-only checks for:
  SQLite `integrity_check`, `foreign_key_check`, FTS5 integrity check, entry/FTS
  count comparison, and FTS rows lacking a matching citation key.
- Add `citegeist search-index status --db ...`.
- Add `citegeist search-index rebuild --db ...` as an explicit write command.
- Rebuild within a transaction from `entries`; document disk-space and locking
  expectations for large databases.
- Before rebuild, recommend or optionally create a timestamped SQLite backup.
- Refuse rebuild when the core `entries` table or schema is not valid.
- Never attempt to repair unrelated orphaned relational rows as part of FTS
  rebuilding.

### Tests

- Healthy index.
- Missing rows, extra/orphaned rows, and incompatible schema.
- Interrupted rebuild rolls back cleanly.
- Rebuild restores search results and row-count agreement.

### Acceptance criteria

- Status is read-only and safe on the 500+ MB TalkOrigins database.
- Rebuild is explicit, transactional, and recoverable.

## Work package 6 — Corpus-level regression verification

Priority: P2

### Tasks

- Create a compact checked-in fixture with several hyphenated topic slugs and
  punctuation-heavy titles; do not check in a production database.
- Add an optional integration test that runs against a caller-supplied database
  path.
- Exercise storage, CLI, MCP, HTTP bridge, and browser-client request shape.
- Benchmark common topic-filtered searches before and after query compilation.
- Verify that safe literal compilation does not materially degrade useful
  multiword ranking.

### Acceptance criteria

- Unit tests require no network and no production database.
- Optional TalkOrigins smoke checks pass for at least `natural-selection`,
  `human-evolution`, `abiogenesis`, and one punctuation-heavy query.

## Suggested implementation sequence

1. Add failing regression tests for raw punctuation and hyphens.
2. Implement literal query compilation and typed errors.
3. Normalize CLI, MCP, HTTP, and browser error handling.
4. Add database identity and `db-status` diagnostics.
5. Establish schema metadata and reconcile `schema-current.sql`.
6. Add read-only index audit.
7. Add explicit backed-up rebuild support.
8. Run corpus-level smoke and performance checks.
9. Update README, architecture documentation, and release notes.

Each work package should be committed separately. Do not combine query escaping
with database rebuilding in one change.

## Validation commands

The coding model should adapt command names if the implementation changes them,
but complete at least the following checks:

```sh
.venv/bin/pytest -q tests/test_storage.py tests/test_cli.py tests/test_mcp.py
.venv/bin/pytest -q
.venv/bin/citegeist --db talkorigins.sqlite3 search \
  natural-selection --topic natural-selection --limit 3
.venv/bin/citegeist --db talkorigins.sqlite3 search \
  "natural selection" --topic natural-selection --limit 3
.venv/bin/citegeist --db talkorigins.sqlite3 db-status
.venv/bin/citegeist --db talkorigins.sqlite3 search-index status
```

For the production-sized database, run only read-only status and search commands
until a backup path and explicit rebuild authorization are provided.

## Definition of done

- Hyphenated and punctuation-heavy natural-language searches work across all
  supported interfaces.
- No ordinary search input can produce a raw SQLite/FTS traceback.
- Users can see which database and corpus they searched.
- Empty corpus, unknown topic, zero matches, invalid query, unsupported FTS,
  incompatible schema, and unhealthy index are distinct states.
- Runtime and documented schemas agree and are versioned.
- Index audit is read-only; rebuild is explicit and recoverable.
- Unit, interface, and optional corpus smoke tests pass.
- User documentation includes safe examples and troubleshooting guidance.

## Non-goals

- Embedding or vector search.
- Replacing SQLite.
- Redesigning topic relevance scoring.
- Automatically selecting a database based on its size or contents.
- Automatically deleting, replacing, or rebuilding a user's database.
- Repairing general relational-data corruption as a side effect of search work.
