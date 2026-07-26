from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
import warnings

from .bibtex import BibEntry, parse_bibtex, render_bibtex
from .confidence import identity_resolution_assessment
from .llm_verify import VerificationLlmClient, VerificationLlmConfig
from .resolve import MetadataResolver, Resolution


@dataclass(slots=True)
class VerificationMatch:
    entry: BibEntry
    score: float
    source_label: str


@dataclass(slots=True, init=False)
class VerificationResult:
    query: str
    context: str
    status: str
    match_score: float
    entry: BibEntry
    source_label: str
    alternates: list[VerificationMatch]
    input_type: str
    input_key: str | None = None

    def __init__(
        self,
        *,
        query: str,
        context: str,
        status: str,
        entry: BibEntry,
        source_label: str,
        alternates: list[VerificationMatch],
        input_type: str,
        input_key: str | None = None,
        match_score: float | None = None,
        confidence: float | None = None,
    ) -> None:
        if match_score is None:
            if confidence is None:
                raise TypeError("VerificationResult requires match_score")
            warnings.warn(
                "VerificationResult(confidence=...) is deprecated; use match_score.",
                DeprecationWarning,
                stacklevel=2,
            )
            match_score = confidence
        self.query = query
        self.context = context
        self.status = status
        self.match_score = match_score
        self.entry = entry
        self.source_label = source_label
        self.alternates = alternates
        self.input_type = input_type
        self.input_key = input_key

    @property
    def confidence(self) -> float:
        warnings.warn(
            "VerificationResult.confidence is deprecated; use match_score.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.match_score

    def to_bib_entry(self) -> BibEntry:
        fields = dict(self.entry.fields)
        fields["x_status"] = self.status
        fields["x_match_score"] = f"{self.match_score:.2f}"
        fields["x_confidence"] = f"{self.match_score:.2f}"
        fields["x_source"] = self.source_label
        fields["x_query"] = self.query
        fields["x_context"] = self.context
        if self.input_type == "bib" and self.input_key:
            fields["x_input_key"] = self.input_key
        if self.alternates:
            fields["x_alternates"] = " || ".join(
                _serialize_alternate(match) for match in self.alternates
            )
        return BibEntry(
            entry_type=self.entry.entry_type,
            citation_key=self.entry.citation_key,
            fields=fields,
        )

    def to_dict(self) -> dict[str, object]:
        subject_id = f"citegeist:verification:{self.input_key or self.entry.citation_key or self.query}"
        assessments = [
            identity_resolution_assessment(
                subject_id=subject_id,
                score=self.match_score,
                source_label=self.source_label,
                basis_record_ids=[self.input_key or self.query],
            ).to_dict()
        ]
        assessments.extend(
            identity_resolution_assessment(
                subject_id=f"{subject_id}:alternate:{match.entry.citation_key}",
                score=match.score,
                source_label=match.source_label,
                basis_record_ids=[self.input_key or self.query],
            ).to_dict()
            for match in self.alternates
        )
        return {
            "query": self.query,
            "context": self.context,
            "input_type": self.input_type,
            "input_key": self.input_key,
            "status": self.status,
            "match_score": round(self.match_score, 4),
            "confidence": round(self.match_score, 4),
            "assessments": assessments,
            "source_label": self.source_label,
            "entry": {
                "citation_key": self.entry.citation_key,
                "entry_type": self.entry.entry_type,
                "fields": dict(self.entry.fields),
            },
            "alternates": [
                {
                    "citation_key": match.entry.citation_key,
                    "entry_type": match.entry.entry_type,
                    "score": round(match.score, 4),
                    "source_label": match.source_label,
                    "fields": dict(match.entry.fields),
                }
                for match in self.alternates
            ],
        }


class BibliographyVerifier:
    def __init__(
        self,
        resolver: MetadataResolver | None = None,
        *,
        llm_config: VerificationLlmConfig | None = None,
        llm_client: VerificationLlmClient | None = None,
    ) -> None:
        self.resolver = resolver or MetadataResolver()
        self.llm_config = llm_config
        self.llm_client = llm_client or VerificationLlmClient()

    def verify_string(self, value: str, context: str = "", limit: int = 5) -> VerificationResult:
        query_fields = _fields_from_string(value)
        return self._verify_query(
            query_fields,
            query=value,
            context=context,
            limit=limit,
            input_type="string",
        )

    def verify_bib_entry(self, entry: BibEntry, context: str = "", limit: int = 5) -> VerificationResult:
        query = " ".join(
            part
            for part in (
                entry.fields.get("doi", ""),
                entry.fields.get("title", ""),
                entry.fields.get("author", ""),
                entry.fields.get("year", ""),
            )
            if part
        ).strip()
        query_fields = {
            "title": entry.fields.get("title", ""),
            "authors": _split_authors(entry.fields.get("author", "")),
            "year": entry.fields.get("year", ""),
            "venue": entry.fields.get("journal", "") or entry.fields.get("booktitle", ""),
        }
        return self._verify_query(
            query_fields,
            query=query or entry.citation_key,
            context=context,
            limit=limit,
            input_type="bib",
            input_key=entry.citation_key,
            source_entry=entry,
        )

    def verify_strings(self, values: list[str], context: str = "", limit: int = 5) -> list[VerificationResult]:
        return [self.verify_string(value, context=context, limit=limit) for value in values if value.strip()]

    def verify_bib_file(self, path: str | Path, context: str = "", limit: int = 5) -> list[VerificationResult]:
        entries = parse_bibtex(Path(path).read_text(encoding="utf-8"))
        return [self.verify_bib_entry(entry, context=context, limit=limit) for entry in entries]

    def _verify_query(
        self,
        query_fields: dict[str, object],
        *,
        query: str,
        context: str,
        limit: int,
        input_type: str,
        input_key: str | None = None,
        source_entry: BibEntry | None = None,
    ) -> VerificationResult:
        if source_entry is not None and source_entry.fields.get("doi"):
            direct = self.resolver.resolve_doi(source_entry.fields["doi"]) or self.resolver.resolve_datacite_doi(
                source_entry.fields["doi"]
            )
            if direct is not None:
                return VerificationResult(
                    query=query,
                    context=context,
                    status="exact",
                    match_score=1.0,
                    entry=direct.entry,
                    source_label=direct.source_label,
                    alternates=[],
                    input_type=input_type,
                    input_key=input_key,
                )
        if source_entry is not None and source_entry.fields.get("pmid"):
            direct = self.resolver.resolve_pmid(source_entry.fields["pmid"])
            if direct is not None:
                return VerificationResult(
                    query=query,
                    context=context,
                    status="exact",
                    match_score=1.0,
                    entry=direct.entry,
                    source_label=direct.source_label,
                    alternates=[],
                    input_type=input_type,
                    input_key=input_key,
                )

        query_fields = _clone_query_fields(query_fields)
        search_query = query
        if self.llm_config is not None:
            hints = self.llm_client.analyze_query(self.llm_config, query, context)
            if hints:
                _apply_llm_hints(query_fields, hints)
                search_query = _build_search_query(search_query, hints)

        candidate_limit = max(1, limit)
        candidates = self._collect_candidates(
            title=str(query_fields.get("title", "")),
            query=search_query,
            limit=candidate_limit,
        )
        scored = [
            VerificationMatch(
                entry=entry,
                score=_score_candidate(query_fields, context, entry),
                source_label=source_label,
            )
            for entry, source_label in candidates
        ]
        llm_ranks = _compute_llm_ranks(
            self.llm_client.rerank_candidates(
                self.llm_config,
                query_fields,
                context,
                [match.entry for match in scored],
            )
            if self.llm_config is not None
            else None,
            scored,
        )
        scored.sort(
            key=lambda item: (
                -item.score,
                llm_ranks.get(item.entry.citation_key, len(scored)),
                item.entry.fields.get("year", ""),
                item.entry.citation_key,
            )
        )

        best = scored[0] if scored else None
        if best is None:
            fallback_entry = source_entry or _placeholder_entry(query_fields, query, input_key)
            return VerificationResult(
                query=query,
                context=context,
                status="not_found",
                match_score=0.0,
                entry=fallback_entry,
                source_label="none",
                alternates=[],
                input_type=input_type,
                input_key=input_key,
            )

        status = _status_from_match(best)
        return VerificationResult(
            query=query,
            context=context,
            status=status,
            match_score=best.score,
            entry=best.entry,
            source_label=best.source_label,
            alternates=scored[1: min(len(scored), 4)],
            input_type=input_type,
            input_key=input_key,
        )

    def _collect_candidates(self, *, title: str, query: str, limit: int) -> list[tuple[BibEntry, str]]:
        candidates: list[tuple[BibEntry, str]] = []
        seen: set[str] = set()
        search_title = title or query

        for source_name, source_entries in (
            ("crossref", self.resolver.search_crossref(search_title, limit=limit)),
            ("openalex", self.resolver.search_openalex(search_title, limit=limit)),
            ("datacite", self.resolver.search_datacite(search_title, limit=limit)),
            ("pubmed", self.resolver.search_pubmed(search_title, limit=limit)),
        ):
            for entry in source_entries:
                signature = _candidate_signature(entry)
                if signature in seen:
                    continue
                seen.add(signature)
                candidates.append((entry, f"{source_name}:search:{search_title}"))
        return candidates


def render_verification_results(results: list[VerificationResult], output_format: str) -> str:
    if output_format == "json":
        return json.dumps([result.to_dict() for result in results], indent=2)
    return render_bibtex([result.to_bib_entry() for result in results])


def _fields_from_string(value: str) -> dict[str, object]:
    year_match = re.search(r"\b(1[6-9]\d{2}|20\d{2}|21\d{2})\b", value)
    year = year_match.group(1) if year_match else ""
    quoted_title = re.search(r"[\"“”‘’'`](.+?)[\"“”‘’'`]", value)
    title = quoted_title.group(1).strip() if quoted_title else ""
    author_source = value
    if quoted_title:
        author_source = author_source.replace(quoted_title.group(0), " ")
    if year:
        author_source = author_source.replace(year, " ")
    author_tokens = [token.strip(",.;:") for token in author_source.split() if token.strip(",.;:")]
    authors: list[str] = [author_tokens[0]] if author_tokens else []
    return {"title": title, "authors": authors, "year": year, "venue": ""}


def _clone_query_fields(query_fields: dict[str, object]) -> dict[str, object]:
    cloned = dict(query_fields)
    authors = cloned.get("authors", [])
    cloned["authors"] = list(authors) if isinstance(authors, list) else []
    return cloned


def _apply_llm_hints(query_fields: dict[str, object], hints: dict[str, object]) -> None:
    if not str(query_fields.get("title", "")).strip() and hints.get("title"):
        query_fields["title"] = str(hints["title"])
    if not query_fields.get("authors") and hints.get("authors"):
        query_fields["authors"] = [str(author) for author in hints["authors"] if str(author).strip()]
    if not str(query_fields.get("year", "")).strip() and hints.get("year"):
        query_fields["year"] = str(hints["year"])
    if not str(query_fields.get("venue", "")).strip() and hints.get("venue"):
        query_fields["venue"] = str(hints["venue"])


def _build_search_query(query: str, hints: dict[str, object]) -> str:
    keywords = [str(value).strip() for value in hints.get("keywords", []) if str(value).strip()]
    if not keywords:
        return query
    return " ".join(part for part in [query, " ".join(keywords[:5])] if part).strip()


def _score_candidate(query_fields: dict[str, object], context: str, entry: BibEntry) -> float:
    score = 0.0
    query_title = _tokenize(str(query_fields.get("title", "")))
    candidate_title = _tokenize(entry.fields.get("title", ""))
    if query_title:
        overlap = len(query_title & candidate_title) / max(1, len(query_title))
        if overlap >= 0.9:
            score += 0.55
        elif overlap >= 0.7:
            score += 0.40
        elif overlap >= 0.5:
            score += 0.20

    query_authors = [author for author in query_fields.get("authors", []) if author]
    if query_authors:
        query_surname = _surname(query_authors[0])
        candidate_surname = _surname(_split_authors(entry.fields.get("author", ""))[0]) if entry.fields.get("author") else ""
        if query_surname and query_surname == candidate_surname:
            score += 0.25

    query_year = str(query_fields.get("year", "")).strip()
    candidate_year = entry.fields.get("year", "").strip()
    if query_year and candidate_year:
        if query_year == candidate_year:
            score += 0.15
        else:
            try:
                delta = abs(int(query_year) - int(candidate_year))
                if delta == 1:
                    score += 0.07
            except ValueError:
                pass

    query_venue = str(query_fields.get("venue", "")).strip()
    candidate_venue = entry.fields.get("journal", "").strip() or entry.fields.get("booktitle", "").strip()
    if query_venue and candidate_venue and _normalize(query_venue) == _normalize(candidate_venue):
        score += 0.05

    if context:
        context_tokens = _tokenize(context)
        abstract_tokens = _tokenize(entry.fields.get("abstract", ""))
        if context_tokens & abstract_tokens:
            score += 0.05

    return min(score, 1.0)


def _status_from_match(match: VerificationMatch) -> str:
    if match.entry.fields.get("doi") and match.score >= 0.95:
        return "exact"
    if match.score >= 0.75:
        return "high_confidence"
    return "ambiguous"


def _split_authors(value: str) -> list[str]:
    return [part.strip() for part in value.split(" and ") if part.strip()]


def _surname(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if "," in text:
        return text.split(",", 1)[0].strip().lower()
    return text.split()[-1].strip().lower()


def _tokenize(value: str) -> set[str]:
    return {token for token in re.split(r"\W+", value.lower()) if token}


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _serialize_alternate(match: VerificationMatch) -> str:
    authors = _split_authors(match.entry.fields.get("author", ""))
    first_author = authors[0] if authors else ""
    return "|".join(
        (
            match.entry.fields.get("doi", ""),
            match.entry.fields.get("title", ""),
            first_author,
            match.entry.fields.get("year", ""),
            f"{match.score:.2f}",
        )
    )


def _candidate_signature(entry: BibEntry) -> str:
    return "|".join(
        (
            entry.fields.get("doi", "").lower(),
            _normalize(entry.fields.get("title", "")),
            entry.fields.get("year", ""),
        )
    )


def _placeholder_entry(query_fields: dict[str, object], query: str, input_key: str | None) -> BibEntry:
    title = str(query_fields.get("title", "")) or query
    authors = query_fields.get("authors", [])
    year = str(query_fields.get("year", ""))
    citation_key = input_key or _slugify_key(title or query)
    fields = {"title": title}
    if authors:
        fields["author"] = " and ".join(str(author) for author in authors)
    if year:
        fields["year"] = year
    return BibEntry(entry_type="misc", citation_key=citation_key, fields=fields)


def _slugify_key(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "", value.lower())
    return slug[:40] or "verification"


def _compute_llm_ranks(order: list[int] | None, matches: list[VerificationMatch]) -> dict[str, int]:
    if not order:
        return {}
    ranks: dict[str, int] = {}
    for rank, index in enumerate(order):
        if 0 <= index < len(matches):
            ranks[matches[index].entry.citation_key] = rank
    return ranks
