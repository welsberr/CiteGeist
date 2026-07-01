# CiteGeist Multi-Source File Structure

**Date:** 2026-04-25

## Project Structure

```
CiteGeist/
├── db/
│   └── migrations/
│       └── 0001_multisource.sql           ✅ NEW - Multi-source schema
│
├── docs/
│   ├── architecture-current.md             ✅ NEW - Current architecture docs
│   ├── implementation-progress.md          ✅ NEW - Implementation progress tracker
│   ├── schema-current.sql                  ✅ NEW - Current schema SQL
│   └── file-structure.md                   ✅ NEW - This file
│
├── src/citegeist/
│   ├── sources/                            ✅ NEW - Source plugin architecture
│   │   ├── __init__.py                     ✅ NEW - Package exports
│   │   ├── __all__.py                      ✅ NEW - Public API
│   │   ├── base.py                         ✅ NEW - Base BibliographicSource class
│   │   ├── registry.py                     ✅ NEW - SourceRegistry implementation
│   │   ├── crossref.py                     ✅ NEW - CrossRef source plugin
│   │   └── _old_sources_compat.py          ✅ NEW - Backward compatibility
│   │
│   ├── resolver/                           ✅ NEW - Identifier resolution
│   │   ├── __init__.py                     ✅ NEW - Module exports
│   │   └── identifiers.py                  ✅ NEW - Extract, normalize, resolve
│   │
│   ├── db/                                 ✅ NEW - Database operations
│   │   └── __init__.py                     🚧 TO DO - Database client
│   │
│   ├── ... (existing files)
│   ├── sources.py                          📦 Existing - Old SourceClient
│   ├── resolve.py                          📦 Existing - MetadataResolver
│   └── storage.py                          📦 Existing - BibliographyStore
│
└── tests/
    ├── test_sources_plugin.py              ✅ NEW - Source plugin tests
    └── test_resolver_identifiers.py        ✅ NEW - Identifier tests
```

## Module Documentation

### New Modules

#### `src/citegeist/sources/`
Plugin architecture for bibliographic sources.

**Classes:**
- `BibliographicSource` - Abstract base class for source plugins
- `SourceRecord` - Raw source record dataclass
- `CitationEdge` - Citation relationship dataclass
- `SourceRegistry` - Manages source plugins

**Plugin:**
- `CrossRefSource` - CrossRef API implementation

#### `src/citegeist/resolver/`
Identifier extraction, normalization, and resolution.

**Classes:**
- `IdentifierExtractor` - Extract identifiers from entry fields
- `IdentifierNormalizer` - Normalize identifiers to canonical form
- `IdentifierResolver` - Resolve identifiers with lookup priority

**Functions:**
- `extract_identifiers()` - Quick identifier extraction
- `normalize_identifier()` - Quick normalization
- `get_primary_identifier()` - Get primary identifier
- `resolve_identifiers()` - Resolve all identifiers

#### `src/citegeist/db/`
Database operations (to be implemented).

**Planned:**
- Database client for works table
- Migration runner
- Query builders

#### `db/migrations/0001_multisource.sql`
Multi-source database schema migration.

**Tables:**
1. `works` - Canonical work metadata
2. `work_identifiers` - Multi-scheme identifiers
3. `source_records` - Raw API responses
4. `citations` - Citation graph
5. `work_embeddings` - Vector embeddings

### Existing Modules (Preserved)

- `src/citegeist/sources.py` - Old SourceClient (backward compatible)
- `src/citegeist/resolve.py` - Old MetadataResolver
- `src/citegeist/storage.py` - Old BibliographyStore

## Test Coverage

**New Tests:**
- `tests/test_sources_plugin.py` (7 tests)
- `tests/test_resolver_identifiers.py` (17 tests)

**Total:** 24 tests passing

## Dependencies

**New Dependencies Required:**
- No new Python packages (uses stdlib only)

**Planned Dependencies (Future phases):**
- `pgvector` - PostgreSQL vector extension
- `sentence-transformers` - Local embedding model
- `fastapi` - API framework
- `unpaywall` - OA link retrieval (if needed)

## Implementation Status

### Completed (100%)
- ✅ Phase 0: Baseline Audit
- ✅ Phase 1: Source Plugin Architecture
- ✅ Phase 2: Identifier Resolution Layer

### In Progress (50%)
- 🚧 Phase 3: Database Schema Upgrade

### Pending (0%)
- ⏳ Phase 4: High-Value Source Integrations
- ⏳ Phase 5: Merge & Deduplication Engine
- ⏳ Phase 6: Citation Graph Construction
- ⏳ Phase 7: Embedding Pipeline
- ⏳ Phase 8: Full-Text Retrieval Layer
- ⏳ Phase 9: API Layer
- ⏳ Phase 10: Ranking & Relevance
- ⏳ Phase 12: Observability & QA
- ⏳ Phase 13: Performance Optimization

## Quick Start

```python
# Register a source
from citegeist.sources import SourceRegistry, CrossRefSource

registry = SourceRegistry()
registry.register(CrossRefSource, name='crossref', config={})

# Get source instance
source = registry.get('crossref')
entry = source.lookup_by_doi('10.1234/example')

# Resolve identifiers
from citegeist.resolver import resolve_identifiers

fields = {'doi': '10.1234/example', 'title': 'Test'}
resolved = resolve_identifiers(fields)
# Returns [('doi', '10.1234/example'), ('title', 'test title')]
```

## Next Steps

1. ✅ Phase 0-2: Complete
2. 🚧 Phase 3: Implement Python interface for database operations
3. ⏳ Phase 4: Add Unpaywall, Semantic Scholar, OpenCitations integrations
4. ⏳ Phase 5: Build merge engine
