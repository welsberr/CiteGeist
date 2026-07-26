# CiteGeist Sources-First Progress

**Last Updated:** 2026-07-25

This document tracks the refocused plan for source incorporation. The working question is which additional open bibliographic sources CiteGeist should integrate next, not whether it needs a new storage platform first.

---

## Phase 0: Scope Reframe ✅ COMPLETE

**Status:** Completed

**Deliverables:**
- ✅ `/docs/source-landscape.md` - source inventory and recommendation document
- ✅ `/src/citegeist/sources/catalog.py` - code-backed source catalog

**Completed:**
- Identified which source integrations already exist in the repository
- Split source-expansion planning from database/vector-search ambitions
- Prioritized open-source additions by workflow value

---

## Phase 1: Source Layer Tightening ✅ COMPLETE

**Status:** Completed

**Deliverables:**
- ✅ `/src/citegeist/sources/base.py` - Base `BibliographicSource` interface
- ✅ `/src/citegeist/sources/registry.py` - Registry for known concrete sources
- ✅ `/src/citegeist/sources/crossref.py` - Repaired CrossRef source implementation
- ✅ `/src/citegeist/sources/catalog.py` - Open-source inventory
- ✅ `/src/citegeist/sources/__init__.py` - Package initialization
- ✅ `/tests/test_sources_plugin.py` - Source plugin tests
- ✅ `/tests/test_sources_catalog.py` - Source catalog and registry tests

**Completed:**
- ✅ Created `BibliographicSource` abstract base class
- ✅ Repaired `SourceRegistry` so config-backed loading resolves real source classes
- ✅ Fixed `CrossRefSource` normalization for direct lookup and search-style payloads
- ✅ Replaced path-specific compatibility loading with repo-relative loading
- ✅ Added a source catalog that captures current status and next-priority sources

**Features:**
- Abstract interface for source plugins
- Registry for known source discovery and instantiation
- Config-driven enable/disable for known source types
- Source prioritization metadata
- Compatibility with the existing `SourceClient`-based resolver/expander code

---

## Current Integrated Sources ✅ AVAILABLE

- `Crossref`
- `OpenAlex`
- `OpenCitations`
- `Unpaywall`
- `PubMed`
- `Europe PMC`
- `Semantic Scholar`
- `DataCite`
- `DBLP`
- `arXiv`
- `OAI-PMH`

These are already sufficient for a credible local enrichment-and-discovery workflow. The next work should complement them rather than restart infrastructure underneath them.

---

## Phase 2: Next Source Additions 🚧 IN PROGRESS

**Status:** In Progress

**Priority Order:**
1. `OpenAIRE` only if repository-acquisition scope expands

**Completed Deliverables:**
- ✅ OpenCitations adapter for DOI citation/reference lookup
- ✅ OpenCitations graph expansion support in CLI and topic expansion flows
- ✅ Unpaywall adapter for DOI OA-link enrichment
- ✅ `enrich-oa` CLI flow for applying OA metadata to stored entries
- ✅ Europe PMC biomedical resolver/search integration
- ✅ Semantic Scholar broad-science resolver/search integration

**Planned Deliverables:**
- ⏳ Decide whether repository-acquisition breadth needs another dedicated source

**Rationale:**
- `OpenCitations` now improves open citation-edge coverage
- `Unpaywall` now improves access-link enrichment
- `Europe PMC` now improves biomedical metadata and OA/fulltext coverage
- `Semantic Scholar` now improves broader biological and physical sciences coverage
- neither requires a new database architecture to become useful

---

## Phase 3: Optional Source Evaluation ⏳ PLANNED

**Status:** Planned

- `OpenAIRE`

**Decision Rule:**
- add them only if they solve a concrete discovery or acquisition gap that current open sources do not already cover well

---

## Explicitly Deferred

- second-schema redesign work
- pgvector integration
- embedding-first retrieval
- broad canonical-work reconstruction

## Unified Confidence Work

**Status:** Partial and unreleased

The local working tree now contains a versioned assessment table, typed
bibliographic identity assessments, a dry-run-first migration function, and
OKF assessment rendering. This is not a completed CG3 migration: the CLI
surface, backup/rollback, portable interval storage, reviewed match outcomes,
calibration, and Epistemap graph export remain. See Epistemap
`docs/confidence-overhaul-implementation-status.md` for the audited
cross-repository phase matrix.

---

## Summary

**Completed:** scope reframe and source-layer cleanup
**Planned next:** `OpenAIRE` reevaluation
**Deferred:** database/vector expansion work not required by the source question
