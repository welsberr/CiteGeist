-- Migration: Multi-source bibliographic schema
-- Description: Add multi-source support with works, identifiers, source records, citations, and embeddings

-- ============================================================================
-- WORKS TABLE - Canonical metadata for works
-- ============================================================================
CREATE TABLE IF NOT EXISTS works (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id TEXT NOT NULL UNIQUE,
    title TEXT,
    abstract TEXT,
    publication_year INTEGER,
    publication_date TEXT,
    journal_name TEXT,
    publisher TEXT,
    volume TEXT,
    issue TEXT,
    pages TEXT,
    doi TEXT,
    pmid TEXT,
    pmcid TEXT,
    arxiv_id TEXT,
    dblp_key TEXT,
    openalex_id TEXT,
    isbn TEXT,
    issn TEXT,
    entry_type TEXT NOT NULL DEFAULT 'article',
    citation_count INTEGER DEFAULT 0,
    cited_by_count INTEGER DEFAULT 0,
    influential_citations INTEGER DEFAULT 0,
    is_open_access BOOLEAN DEFAULT 0,
    best_oa_url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- WORK IDENTIFIERS TABLE - Mapping scheme + value to works
-- ============================================================================
CREATE TABLE IF NOT EXISTS work_identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id TEXT NOT NULL,
    scheme TEXT NOT NULL,
    value TEXT NOT NULL,
    is_primary BOOLEAN DEFAULT 0,
    normalized_value TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(work_id, scheme, value),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
);

-- ============================================================================
-- SOURCE RECORDS TABLE - Raw API responses with provenance
-- ============================================================================
CREATE TABLE IF NOT EXISTS source_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_label TEXT NOT NULL,
    raw_data_json TEXT NOT NULL,
    raw_record_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(work_id, source_type, source_label),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
);

-- ============================================================================
-- CITATIONS TABLE - Citation graph with provenance
-- ============================================================================
CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_work_id TEXT NOT NULL,
    target_work_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_label TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    is_verified BOOLEAN DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_work_id, target_work_id, relation_type),
    FOREIGN KEY (source_work_id) REFERENCES works(id) ON DELETE CASCADE,
    FOREIGN KEY (target_work_id) REFERENCES works(id) ON DELETE CASCADE
);

-- ============================================================================
-- WORK EMBEDDINGS TABLE - Vector storage for semantic search
-- ============================================================================
CREATE TABLE IF NOT EXISTS work_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id TEXT NOT NULL,
    embedding TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT,
    dimension INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(work_id, model_name),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
);

-- ============================================================================
-- INDEXES - For performance optimization
-- ============================================================================
-- Work identifiers indexes
CREATE INDEX IF NOT EXISTS idx_work_identifiers_scheme ON work_identifiers(scheme);
CREATE INDEX IF NOT EXISTS idx_work_identifiers_value ON work_identifiers(value);
CREATE INDEX IF NOT EXISTS idx_work_identifiers_work_id ON work_identifiers(work_id);
CREATE INDEX IF NOT EXISTS idx_work_identifiers_normalized ON work_identifiers(normalized_value);

-- Source records indexes
CREATE INDEX IF NOT EXISTS idx_source_records_work_id ON source_records(work_id);
CREATE INDEX IF NOT EXISTS idx_source_records_source_type ON source_records(source_type);

-- Citations indexes
CREATE INDEX IF NOT EXISTS idx_citations_source_work ON citations(source_work_id);
CREATE INDEX IF NOT EXISTS idx_citations_target_work ON citations(target_work_id);
CREATE INDEX IF NOT EXISTS idx_citations_relation_type ON citations(relation_type);
CREATE INDEX IF NOT EXISTS idx_citations_source_type ON citations(source_type);

-- Works indexes
CREATE INDEX IF NOT EXISTS idx_works_doi ON works(doi);
CREATE INDEX IF NOT EXISTS idx_works_pmid ON works(pmid);
CREATE INDEX IF NOT EXISTS idx_works_pmcid ON works(pmcid);
CREATE INDEX IF NOT EXISTS idx_works_arxiv ON works(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_works_openalex ON works(openalex_id);
CREATE INDEX IF NOT EXISTS idx_works_is_open_access ON works(is_open_access);
CREATE INDEX IF NOT EXISTS idx_works_created_at ON works(created_at);

-- Embeddings indexes
CREATE INDEX IF NOT EXISTS idx_embeddings_work_id ON work_embeddings(work_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_model_name ON work_embeddings(model_name);

-- ============================================================================
-- PostgreSQL-specific extensions and vector indexing
-- ============================================================================
-- Note: The following are PostgreSQL-specific and should be run when using pgvector

-- Uncomment these when using PostgreSQL with pgvector extension:
-- CREATE EXTENSION IF NOT EXISTS vector;
-- CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON work_embeddings
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================================
-- TRIGGERS - For automatic timestamp updates
-- ============================================================================
-- Works table update trigger
CREATE TRIGGER IF NOT EXISTS works_updated_at
AFTER UPDATE ON works
FOR EACH ROW
WHEN (new.updated_at IS NULL)
BEGIN
    UPDATE works SET updated_at = CURRENT_TIMESTAMP WHERE id = old.id;
END;

-- Work identifiers update trigger
CREATE TRIGGER IF NOT EXISTS work_identifiers_updated_at
AFTER UPDATE ON work_identifiers
FOR EACH ROW
WHEN (new.created_at IS NULL)
BEGIN
    UPDATE work_identifiers SET created_at = CURRENT_TIMESTAMP WHERE id = old.id;
END;

-- ============================================================================
-- VIEWS - For simplified queries
-- ============================================================================
-- View to join works with their identifiers
CREATE VIEW IF NOT EXISTS works_with_identifiers AS
SELECT 
    w.id,
    w.work_id,
    w.title,
    w.abstract,
    w.publication_year,
    w.journal_name,
    w.publisher,
    w.doi,
    w.pmid,
    w.pmcid,
    w.arxiv_id,
    w.dblp_key,
    w.openalex_id,
    GROUP_CONCAT(DISTINCT wi.scheme || ':' || wi.value, ', ') AS identifiers
FROM works w
LEFT JOIN work_identifiers wi ON w.id = wi.work_id
GROUP BY w.id, w.work_id, w.title, w.abstract, w.publication_year, w.journal_name, w.publisher, w.doi, w.pmid, w.pmcid, w.arxiv_id, w.dblp_key, w.openalex_id;
