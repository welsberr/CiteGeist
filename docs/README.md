# CiteGeist Source Planning Documentation

Welcome to the source-planning documentation for CiteGeist.

## Quick Overview

The immediate planning question is which additional open bibliographic sources should be incorporated next.

This documentation therefore emphasizes:

- the current source baseline already present in the repository
- the next highest-value open sources to add
- a smaller, more realistic source-layer abstraction
- explicit deferral of unrelated database/vector ambitions

## Documentation Files

### Planning and Status
- **[discovery-research-and-improvement-roadmap.md](./discovery-research-and-improvement-roadmap.md)** - operational discovery capabilities, research experiments, adoption criteria, and bounded agent self-improvement
- **[AGENTIC_OS.md](./AGENTIC_OS.md)** - roles, review boundaries, and operating rules for bounded ranking experiments
- **[ranking-experiment-protocol.md](./ranking-experiment-protocol.md)** - JSON-only agent proposals, bounded offline evaluation, and promotion gates
- **[process-improvement-roadmap.md](./process-improvement-roadmap.md)** - verification correctness, model provenance, evaluation, and recoverable-work priorities
- **[lede-brief-integration-roadmap.md](./lede-brief-integration-roadmap.md)** - gated optional scholarly brief integration
- **[groundrecall-unified-retrieval-integration-plan.md](./groundrecall-unified-retrieval-integration-plan.md)** - separately gated cross-repository retrieval pilot
- **[epistemap-knowledge-graph-roadmap.md](./epistemap-knowledge-graph-roadmap.md)** - provenance-aware graph operations and cross-repository integration plan
- **[topic-search-hardening-roadmap.md](./topic-search-hardening-roadmap.md)** - implementation-ready plan for safe FTS5 queries, database diagnostics, schema lifecycle, and index recovery
- **[source-landscape.md](./source-landscape.md)** - recommended next open bibliographic sources
- **[implementation-progress.md](./implementation-progress.md)** - sources-first progress tracker
- **[phase-completion.md](./phase-completion.md)** - short status summary
- **[file-structure.md](./file-structure.md)** - file structure and module notes

### Existing Architecture References
- **[architecture-current.md](./architecture-current.md)** - current architecture overview
- **[schema-current.sql](./schema-current.sql)** - existing database schema

## Current Status

### Current Baseline
1. Crossref, OpenAlex, PubMed, Europe PMC, Semantic Scholar, DataCite, DBLP, arXiv, and OAI-PMH are already in play.
2. OpenCitations and Unpaywall are now integrated as source-layer additions.
3. The SQLite-based local workflow remains the baseline.
4. Notebook-ready topic bibliography bundles can now be exported with `export-notebook-topic` for downstream `Didactopus`/Notebook use.

### Recommended Next Sources
1. OpenAIRE only if repository-acquisition scope expands

### Explicitly Deferred
1. Database redesign
2. pgvector / embedding-first work

## Source Layer

The source-layer code now provides:

- `BibliographicSource` as the common interface
- `SourceRegistry` for known concrete source classes
- `CrossRefSource` as the repaired first concrete plugin
- `OpenCitationsSource` plus DOI-based graph expansion
- `UnpaywallSource` plus DOI-based OA-link enrichment
- `EuropePmcSource` plus biomedical resolver/search support
- `SemanticScholarSource` plus broader biological/physical sciences resolver/search support
- a source catalog with current status and priority order
- compatibility with the existing `SourceClient`-based resolver and expander code

## Quick Start

The initial read-only research contract can be used from the CLI. Local search is
the default; specify each external source explicitly. Candidate results are returned
for review and are not written into the bibliography:

```bash
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 research \
  "methods for evaluating artificial life" --source local --source openalex --source crossref
```

The JSON report includes per-source outcome counts, candidate records, provider
rank/provenance, and a complete/partial/empty-corpus/no-match/provider-failure/
inconclusive outcome. Some legacy
resolver methods still collapse certain transport failures into empty results;
those cases are marked inconclusive rather than as confirmed no-match results.

`citegeist discover` is a separate BibTeX-oriented command for World Bank and FRED
material. `citegeist research` returns a read-only candidate JSON report from the
local corpus and explicitly selected scholarly adapters; neither command verifies
whether a result supports a particular claim.

The bounded `citegeist experiment-rank` development loop compares JSON-only
ranking weights against a fixed recorded candidate pool. It does not use validation
or holdout labels. See the [experiment protocol](./ranking-experiment-protocol.md)
before preparing a pool or proposal file.

```python
from citegeist.sources import (
    CrossRefSource,
    EuropePmcSource,
    OpenCitationsSource,
    SemanticScholarSource,
    SourceRegistry,
    UnpaywallSource,
    list_source_catalog,
    prioritized_source_keys,
)

registry = SourceRegistry()
registry.register(CrossRefSource, name="crossref", config={})
registry.register(EuropePmcSource, name="europepmc", config={})
registry.register(OpenCitationsSource, name="opencitations", config={})
registry.register(SemanticScholarSource, name="semanticscholar", config={})
registry.register(UnpaywallSource, name="unpaywall", config={"email": "you@example.org"})

source = registry.get("crossref")
catalog = list_source_catalog()
priority = prioritized_source_keys()
```

## Tests

Relevant tests for the refocused source work:

- `tests/test_sources_plugin.py`
- `tests/test_sources_catalog.py`

The existing broader repository test suite should continue to pass as the source-layer changes are integrated.

## Next Steps

1. Begin the Epistemap integration with graph-profile fixtures and a
   deterministic read-only export.
2. Decide whether `OpenAIRE` is worth adding for repository-acquisition breadth.
3. Keep database/vector redesign work deferred unless a source need forces it.

## License

Same as the CiteGeist project.

---

**Last Updated:** 2026-04-25
**Status:** Sources-first plan in effect
