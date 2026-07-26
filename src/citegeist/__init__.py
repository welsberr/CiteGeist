from .app_api import LiteratureExplorerApi
from .batch import BatchBootstrapRunner, BatchJobResult, load_batch_jobs
from .bibtex import BibEntry, parse_bibtex
from .bootstrap import BootstrapResult, Bootstrapper
from .confidence import (
    AssessmentMethodRef,
    ConfidenceAssessment,
    band_for_value,
    identity_resolution_assessment,
    migrate_legacy_confidence_assessments,
)
from .confidence import AssessmentMethodRef, ConfidenceAssessment, identity_resolution_assessment
from .expand import CrossrefExpander, OpenAlexExpander, OpenCitationsExpander
from .extract import (
    available_extraction_backends,
    check_extraction_comparison_summary,
    compare_extraction_backends,
    extract_references,
    get_extraction_backend,
    register_extraction_backend,
    summarize_extraction_comparison,
)
from .harvest import OaiMetadataFormat, OaiPmhHarvester, OaiSet
from .llm_verify import VerificationLlmClient, VerificationLlmConfig
from .resolve import MetadataResolver, merge_entries, merge_entries_with_conflicts
from .sources import SourceClient
from .sources import EuropePmcSource
from .sources import OpenLibrarySource
from .sources import SemanticScholarSource
from .sources import UnpaywallSource
from .storage import BibliographyStore
from .verify import BibliographyVerifier, VerificationResult, VerificationMatch

__all__ = [
    "BibEntry",
    "AssessmentMethodRef",
    "BatchBootstrapRunner",
    "BatchJobResult",
    "AssessmentMethodRef",
    "BibliographyStore",
    "BibliographyVerifier",
    "BootstrapResult",
    "Bootstrapper",
    "CrossrefExpander",
    "ConfidenceAssessment",
    "ConfidenceAssessment",
    "LiteratureExplorerApi",
    "MetadataResolver",
    "OpenAlexExpander",
    "OpenCitationsExpander",
    "OaiPmhHarvester",
    "OaiMetadataFormat",
    "OaiSet",
    "SourceClient",
    "EuropePmcSource",
    "OpenLibrarySource",
    "SemanticScholarSource",
    "UnpaywallSource",
    "VerificationLlmClient",
    "VerificationLlmConfig",
    "VerificationMatch",
    "VerificationResult",
    "available_extraction_backends",
    "band_for_value",
    "check_extraction_comparison_summary",
    "compare_extraction_backends",
    "extract_references",
    "get_extraction_backend",
    "identity_resolution_assessment",
    "identity_resolution_assessment",
    "load_batch_jobs",
    "merge_entries",
    "merge_entries_with_conflicts",
    "migrate_legacy_confidence_assessments",
    "parse_bibtex",
    "register_extraction_backend",
    "summarize_extraction_comparison",
]
