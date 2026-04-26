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

1. Decide whether `OpenAIRE` is worth adding for repository-acquisition breadth.
2. Keep database/vector redesign work deferred unless a source need forces it.

## License

Same as the CiteGeist project.

---

**Last Updated:** 2026-04-25
**Status:** Sources-first plan in effect
