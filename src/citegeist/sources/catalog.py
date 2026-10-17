"""Open bibliographic source inventory and prioritization helpers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceCatalogEntry:
    key: str
    label: str
    category: str
    access: str
    capabilities: tuple[str, ...]
    strengths: str
    caveats: str
    current_status: str
    priority: str
    documentation_url: str = ""


_CATALOG: tuple[SourceCatalogEntry, ...] = (
    SourceCatalogEntry(
        key="crossref",
        label="Crossref",
        category="metadata",
        access="open API",
        capabilities=("doi_lookup", "title_search", "reference_lists"),
        strengths="Broad DOI coverage and good article-level metadata.",
        caveats="Citation coverage is incomplete and some references are unstructured blobs.",
        current_status="integrated",
        priority="now",
    ),
    SourceCatalogEntry(
        key="openalex",
        label="OpenAlex",
        category="metadata+graph",
        access="open API",
        capabilities=("work_lookup", "title_search", "citations", "cited_by", "topics"),
        strengths="Best current open source for citation graph expansion and work-level discovery.",
        caveats="Occasional noisy secondary records require conservative admission rules.",
        current_status="integrated",
        priority="now",
    ),
    SourceCatalogEntry(
        key="pubmed",
        label="PubMed / NCBI E-utilities",
        category="metadata",
        access="open API",
        capabilities=("pmid_lookup", "title_search", "biomedical_metadata"),
        strengths="High-value authoritative metadata for biomedical literature.",
        caveats="Domain-specific coverage outside biomedicine is limited.",
        current_status="integrated",
        priority="now",
    ),
    SourceCatalogEntry(
        key="datacite",
        label="DataCite",
        category="metadata",
        access="open API",
        capabilities=("doi_lookup", "title_search", "datasets"),
        strengths="Important for datasets, reports, and non-traditional DOI-bearing objects.",
        caveats="Less useful than Crossref/OpenAlex for mainstream article citation graphs.",
        current_status="integrated",
        priority="now",
    ),
    SourceCatalogEntry(
        key="dblp",
        label="DBLP",
        category="metadata",
        access="open API",
        capabilities=("key_lookup", "search", "computer_science"),
        strengths="Excellent computer-science coverage and clean bibliographic records.",
        caveats="Discipline-specific rather than general-purpose.",
        current_status="integrated",
        priority="selective",
    ),
    SourceCatalogEntry(
        key="arxiv",
        label="arXiv",
        category="metadata+fulltext",
        access="open API",
        capabilities=("id_lookup", "search", "preprints"),
        strengths="Useful for preprint-first fields and free full-text links.",
        caveats="Not a general citation graph source.",
        current_status="integrated",
        priority="selective",
    ),
    SourceCatalogEntry(
        key="open_citations",
        label="OpenCitations",
        category="graph",
        access="open API",
        capabilities=("doi_citations", "doi_references", "provenance"),
        strengths="Directly aligned with open citation-edge expansion.",
        caveats="Coverage is narrower than OpenAlex and needs merge discipline.",
        current_status="integrated",
        priority="now",
    ),
    SourceCatalogEntry(
        key="semantic_scholar",
        label="Semantic Scholar",
        category="metadata+graph",
        access="free API with limits",
        capabilities=("work_lookup", "search", "citations", "references"),
        strengths="Strong graph and relevance signals, especially for discovery workflows.",
        caveats="Not fully open data in the same sense as Crossref/OpenAlex/OpenCitations.",
        current_status="integrated",
        priority="now",
    ),
    SourceCatalogEntry(
        key="unpaywall",
        label="Unpaywall",
        category="access-links",
        access="open API",
        capabilities=("doi_fulltext_links", "oa_status"),
        strengths="Best open source for landing-page and OA-link enrichment.",
        caveats="Improves access, not bibliographic identity or graph completeness.",
        current_status="integrated",
        priority="now",
    ),
    SourceCatalogEntry(
        key="europe_pmc",
        label="Europe PMC",
        category="metadata+fulltext",
        access="open API",
        capabilities=("search", "citations", "fulltext_links", "biomedical"),
        strengths="Valuable biomedical complement to PubMed with richer open-access linkage.",
        caveats="Domain-specific and partially overlapping with PubMed/OpenAlex.",
        current_status="integrated",
        priority="now",
    ),
    SourceCatalogEntry(
        key="open_library",
        label="Open Library",
        category="metadata",
        access="open API",
        capabilities=("title_search", "book_metadata", "author_catalog", "isbn_hints"),
        strengths="Useful general-purpose open catalog coverage for books, monographs, and reference works.",
        caveats="Catalog metadata is not a citation graph and can be noisy for article-like titles.",
        current_status="integrated",
        priority="selective",
    ),
    SourceCatalogEntry(
        key="openaire",
        label="OpenAIRE",
        category="metadata+repository",
        access="open API",
        capabilities=("repository_metadata", "oa_links", "project_links"),
        strengths="Good for repository, project, and European OA discovery.",
        caveats="May be better treated as a corpus-acquisition adapter than a first-line resolver.",
        current_status="planned",
        priority="evaluate",
    ),
    SourceCatalogEntry(
        key="oai_pmh",
        label="OAI-PMH Repositories",
        category="repository",
        access="open protocol",
        capabilities=("repository_harvest", "set_discovery", "metadata_formats"),
        strengths="Already useful for theses, dissertations, and institutional repositories.",
        caveats="Heterogeneous metadata quality; not a single canonical bibliographic source.",
        current_status="integrated",
        priority="selective",
    ),
    SourceCatalogEntry('worldbank', 'World Bank Documents & Reports', 'government+economics', 'open API', ('report_search',), 'Development economics, policy reports and working papers.', 'Discovery returns unverified metadata; documents have their own rights.', 'integrated', 'next', 'https://documents.worldbank.org/en/publication/documents-reports/api'),
    SourceCatalogEntry('fred', 'FRED / ALFRED', 'economics+finance', 'personal API key', ('series_search',), 'Macroeconomics, labor, prices, rates, credit and financial series.', 'Requires FRED_API_KEY; series are data, not publications; preserve vintage and original producer.', 'integrated', 'next', 'https://fred.stlouisfed.org/docs/api/fred/'),
    SourceCatalogEntry('bls', 'Bureau of Labor Statistics', 'government+economics', 'public API; optional registration', ('series_lookup',), 'Employment, unemployment, wages, productivity and consumer prices.', 'API requires series IDs; not a literature or keyword search API. Adapter not yet implemented.', 'planned', 'next', 'https://www.bls.gov/developers/'),
    SourceCatalogEntry('osti', 'OSTI.GOV', 'government+repository', 'open API and OAI-PMH', ('reports', 'theses'), 'DOE-funded technical reports, datasets and theses/dissertations.', 'Domain coverage is energy and related sciences; dedicated adapter not yet implemented.', 'planned', 'next', 'https://www.osti.gov/api/v1/docs'),
    SourceCatalogEntry('reliefweb', 'ReliefWeb', 'ngo+government', 'API with application identification', ('reports',), 'Humanitarian NGO and government reports with source organizations.', 'Check application registration and quotas; original sources retain rights. Adapter not yet implemented.', 'planned', 'next', 'https://apidoc.reliefweb.int/'),
    SourceCatalogEntry('base', 'BASE repositories', 'theses+repository', 'OAI-PMH subject to access conditions', ('repository_harvest',), 'Institutional theses and dissertations; normalized thesis types.', 'Confirm access and supported metadata format before using harvest-oai; no dedicated adapter.', 'planned', 'next', 'https://oai.base-search.net/'),
    SourceCatalogEntry('repec', 'RePEc / IDEAS', 'economics+finance', 'distributed metadata and OAI-PMH', ('working_papers',), 'Economics working papers, journal articles and institution series.', 'Agree bulk reuse with providers; ReDIF/AMF need dedicated normalization.', 'planned', 'next', 'https://ideas.repec.org/getdata.html'),
)


def list_source_catalog() -> list[SourceCatalogEntry]:
    return list(_CATALOG)


def prioritized_source_keys() -> list[str]:
    order = {"now": 0, "next": 1, "selective": 2, "evaluate": 3}
    return [entry.key for entry in sorted(_CATALOG, key=lambda entry: (order[entry.priority], entry.label.lower()))]
