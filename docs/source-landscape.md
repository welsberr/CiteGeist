# Open Bibliographic Source Landscape

This document answers the question that prompted the recent planning work: which additional open bibliographic sources are worth incorporating into CiteGeist, given the sources it already uses?

## Current Baseline

CiteGeist already has useful source coverage for a local BibTeX-first workflow:

- `Crossref`: DOI lookup, title search, and reference-list expansion.
- `OpenAlex`: work lookup, title/discovery search, and citation-graph expansion.
- `PubMed`: authoritative biomedical metadata lookup by PMID and title search fallback.
- `Europe PMC`: biomedical metadata/fulltext complement to PubMed.
- `Semantic Scholar`: broad cross-domain metadata with strong biological and physical sciences coverage.
- `DataCite`: DOI-backed dataset/report/non-article metadata.
- `DBLP`: strong computer-science metadata.
- `arXiv`: preprint metadata.
- `OAI-PMH`: repository harvesting for theses, dissertations, and institutional collections.

That means the immediate gap is no longer “get any scholarly metadata at all.” The immediate gap is to add the next highest-value open sources without destabilizing the existing ingest, review, and export pipeline.

## Recommended Priorities

### OpenCitations

Why:

- It directly improves open citation-edge coverage.
- It fits CiteGeist's graph-discovery workflow better than another generic metadata source.
- It complements OpenAlex rather than replacing it.

Expected role:

- DOI-to-citations lookup
- DOI-to-references lookup
- provenance for citation edges

Status:

- now integrated as a DOI-based citation/reference source in the source layer and graph expansion flow

Main risk:

- coverage is narrower than OpenAlex, so merge rules need to treat it as an additional edge source rather than a primary metadata authority.

### Unpaywall

Why:

- It solves a different problem from Crossref/OpenAlex: full-text access and OA status.
- It improves the “can I get the paper?” part of the workflow without forcing a storage redesign.

Expected role:

- DOI-to-best-open-access-link lookup
- OA status enrichment

Status:

- now integrated as an OA-link enrichment source with a dedicated `enrich-oa` CLI flow

Main risk:

- It should remain an access-link enrichment layer, not become entangled with identity resolution logic.

### Europe PMC

Why:

- It is valuable for biomedical and life-sciences use cases.
- It complements PubMed with richer open-access and citation-related information.

Expected role:

- domain-specific metadata enrichment
- biomedical search
- OA/full-text linkage

Status:

- now integrated as a biomedical resolver/search complement to `PubMed`

Main risk:

- this should remain a domain-specific source, not be treated as a universal resolver.

### Semantic Scholar

Pros:

- good graph and relevance signals
- useful for discovery quality

Status:

- now integrated as a broad resolver/search complement with good biological and physical sciences coverage

Main risk:

- rate limits and product-policy changes still matter more here than for the more explicitly open bibliographic sources

## Evaluate But Do Not Make Core Yet

### OpenAIRE

Pros:

- strong repository and OA/project linkage
- good for European repository acquisition

Cons:

- better suited to corpus acquisition than first-line metadata resolution

Recommendation:

- treat as an acquisition adapter, not an immediate resolver target

## What Not To Prioritize Right Now

### Database Redesign

The repository already has a working SQLite storage model and FTS-backed local workflow. A second schema track should not lead the next phase of work unless a concrete source integration is blocked on it.

### Vector Search

Optional semantic ranking may become useful later, but it was not the motivating question and does not need to be a prerequisite for source incorporation.

## Suggested Execution Order

1. Keep the source abstraction aligned with sources already in use.
2. Revisit `OpenAIRE` after the current source additions settle.
