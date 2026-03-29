from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .bibtex import BibEntry, parse_bibtex, render_bibtex
from .resolve import MetadataResolver, Resolution


@dataclass(slots=True)
class VerificationMatch:
    entry: BibEntry
    score: float
    source_label: str


@dataclass(slots=True)
class VerificationResult:
    query: str
    context: str
    status: str
    confidence: float
    entry: BibEntry
    source_label: str
    alternates: list[VerificationMatch]
    input_type: str
    input_key: str | None = None

    def to_bib_entry(self) -> BibEntry:
        fields = dict(self.entry.fields)
        fields["x_status"] = self.status
        fields["x_confidence"] = f"{self.confidence:.2f}"
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
        return {
            "query": self.query,
            "context": self.context,
            "input_type": self.input_type,
            "input_key": self.input_key,
            "status": self.status,
            "confidence": round(self.confidence, 4),
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
    def __init__(self, resolver: MetadataResolver | None = None) -> None:
        self.resolver = resolver or MetadataResolver()

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
                    confidence=1.0,
                    entry=direct.entry,
                    source_label=direct.source_label,
                    alternates=[],
                    input_type=input_type,
                    input_key=input_key,
                )

        candidate_limit = max(1, limit)
        candidates = self._collect_candidates(
            title=str(query_fields.get("title", "")),
            query=query,
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
        scored.sort(
            key=lambda item: (
                -item.score,
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
                confidence=0.0,
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
            confidence=best.score,
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
