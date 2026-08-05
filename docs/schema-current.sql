-- CiteGeist Current Schema (SQLite)

-- Schema metadata
CREATE TABLE IF NOT EXISTS citegeist_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Entries table
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    citation_key TEXT NOT NULL UNIQUE,
    entry_type TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'draft',
    title TEXT,
    year TEXT,
    journal TEXT,
    booktitle TEXT,
    publisher TEXT,
    abstract TEXT,
    keywords TEXT,
    url TEXT,
    doi TEXT,
    isbn TEXT,
    fulltext TEXT,
    raw_bibtex TEXT,
    extra_fields_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Creators table
CREATE TABLE IF NOT EXISTS creators (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL UNIQUE,
    family_name TEXT,
    given_names TEXT
);

-- Entry-Creators relationship
CREATE TABLE IF NOT EXISTS entry_creators (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    creator_id INTEGER NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (entry_id, role, ordinal)
);

-- Identifiers table
CREATE TABLE IF NOT EXISTS identifiers (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    scheme TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (scheme, value)
);

-- Relations table (citation graph)
CREATE TABLE IF NOT EXISTS relations (
    source_entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    target_citation_key TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    PRIMARY KEY (source_entry_id, target_citation_key, relation_type)
);

-- Topics table
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT,
    expansion_phrase TEXT,
    suggested_phrase TEXT,
    phrase_review_status TEXT NOT NULL DEFAULT 'unreviewed',
    phrase_review_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Entry-Topics relationship
CREATE TABLE IF NOT EXISTS entry_topics (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    source_label TEXT NOT NULL,
    confidence REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entry_id, topic_id)
);

-- Field Provenance table
CREATE TABLE IF NOT EXISTS field_provenance (
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    field_value TEXT,
    source_type TEXT NOT NULL,
    source_label TEXT NOT NULL,
    operation TEXT NOT NULL,
    confidence REAL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Relation Provenance table
CREATE TABLE IF NOT EXISTS relation_provenance (
    id INTEGER PRIMARY KEY,
    source_entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    target_citation_key TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_label TEXT NOT NULL,
    confidence REAL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Full-text Search (FTS5)
-- This standalone index is maintained by BibliographyStore.upsert_entry.
-- Do not substitute an external-content entries_fts table without updating the
-- runtime storage code and index lifecycle together.
CREATE VIRTUAL TABLE IF NOT EXISTS entry_text_fts USING fts5(
    citation_key UNINDEXED,
    title,
    abstract,
    fulltext
);
