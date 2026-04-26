# CiteGeist Current Architecture

## Overview
CiteGeist is currently designed as a local BibTeX-native tooling system with:
- BibTeX parsing and storage
- Local text search (FTS5)
- Entry provenance tracking
- Citation graph traversal
- Topic-based expansion

## Core Modules

### Source Management
- **sources.py**: `SourceClient` class for HTTP requests with caching and retry logic
  - Base HTTP client with JSON/XML/text support
  - Built-in retry with exponential backoff
  - Cache directory support

### Metadata Resolution
- **resolve.py**: `MetadataResolver` class for entry resolution
  - DOI → CrossRef lookup
  - PMID → PubMed lookup
  - arXiv, DBLP, OpenAlex lookup
  - Title search fallback with best-match selection
  - DataCite integration
  - Returns `Resolution` objects with provenance

### Storage
- **storage.py**: `BibliographyStore` class (SQLite)
  - Tables: entries, creators, entry_creators, identifiers, relations, topics, entry_topics, field_provenance, relation_provenance
  - FTS5 text search integration
  - Field-level provenance tracking
  - Citation graph support (cites, cited_by edges)

### BibTeX Processing
- **bibtex.py**: BibEntry dataclass and parsing/rendering
  - BibTeX → BibEntry conversion
  - BibEntry → BibTeX rendering
  - Citation key generation

### CLI and Server
- **cli.py**: Command-line interface
- **app_server.py**: Local HTTP server for UI/JSON API
- **app_api.py**: JSON API adapter surface

### Expansion and Discovery
- **expand.py**: Citation graph expansion workflows
- **extract.py**: Plaintext reference extraction
- **bootstrap.py**: Topic bootstrap and expansion

## Current State Summary

**Completed/Usable:**
- BibTeX parsing and storage
- Identifier-based resolution (DOI, PMID, arXiv, DBLP, OpenAlex)
- Title search with best-match selection
- Citation graph traversal and expansion
- Field provenance tracking
- Local search with FTS5
- Topic-based discovery workflows

**Not Yet Implemented (from new roadmap):**
- Plugin-based source architecture
- Multi-source record merging
- PGVector embeddings
- Full-text OA link retrieval
- Semantic Scholar integration
- OpenCitations integration
- Unified API endpoints for multi-source queries

## Data Flow

1. **Ingest**: BibTeX file → parse → store in entries table
2. **Resolve**: Entry → resolve_doi/resolve_pmid/resolve_arxiv → fetch metadata → merge with existing
3. **Expand**: Start from entry → traverse citation edges → discover new entries
4. **Search**: Query FTS5 index → retrieve relevant entries
5. **Export**: Entries → render BibTeX → output file

## Database Schema

SQLite-based storage with:
- Normalized entry fields
- Creator relationships
- Identifier mapping
- Citation relations
- Topic associations
- Field provenance metadata
