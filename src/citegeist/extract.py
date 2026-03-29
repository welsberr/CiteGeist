from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .bibtex import BibEntry, parse_bibtex

YEAR_PATTERN = re.compile(r"\b(?:1[6-9]|20|21)\d{2}[a-z]?\b", re.IGNORECASE)
YEAR_PAREN_PATTERN = re.compile(r"\((?:1[6-9]|20|21)\d{2}[a-z]?\)", re.IGNORECASE)
REF_START_PATTERN = re.compile(r"^(?:\[\d+\]|\d+\.|\(\d+\))\s*")
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
ARXIV_PATTERN = re.compile(r"\barXiv:\s*([A-Za-z0-9.\-]+)", re.IGNORECASE)
ISBN_PATTERN = re.compile(r"\bISBN(?:-1[03])?:?\s*([0-9Xx\-]{10,20})\b")
ISSN_PATTERN = re.compile(r"\bISSN:?\s*([0-9Xx\-]{8,12})\b", re.IGNORECASE)
VOLUME_ISSUE_PAGES_PATTERN = re.compile(
    r"(?P<volume>\d+)\s*(?:\((?P<number>[^)]+)\))?\s*[:;,]\s*(?P<pages>\d+\s*[-\u2013]\s*\d+)\b"
)
PAGES_PATTERN = re.compile(r"\bpp?\.\s*(?P<pages>\d+\s*[-\u2013]\s*\d+)\b", re.IGNORECASE)
TRAILING_PAGE_PATTERN = re.compile(r"[,;]\s*(?P<pages>\d+\s*[-\u2013]\s*\d+)\.?$")
REPORT_NUMBER_PATTERN = re.compile(r"\b(?:technical\s+report|report|working\s+paper|bulletin)\s+(?:no\.?|number)?\s*(?P<number>[A-Za-z0-9.\-]+)\b", re.IGNORECASE)
THESIS_MARKER_PATTERN = re.compile(
    r"\((?:master|doctoral).*?\)|phd dissertation|master'?s thesis|master’s thesis|doctoral dissertation",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ParsedReferenceParts:
    raw_line: str
    authors: str
    year: str
    title: str
    venue: str


@dataclass(slots=True)
class ExtractionComparisonRow:
    ordinal: int
    raw_reference: str
    entries: dict[str, dict[str, object]]
    differing_fields: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "raw_reference": self.raw_reference,
            "entries": self.entries,
            "differing_fields": self.differing_fields,
        }


@dataclass(slots=True)
class ExtractionComparisonSummary:
    backends: list[str]
    row_count: int
    rows_with_differences: int
    differing_field_counts: dict[str, int]
    backend_presence_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "backends": self.backends,
            "row_count": self.row_count,
            "rows_with_differences": self.rows_with_differences,
            "differing_field_counts": self.differing_field_counts,
            "backend_presence_counts": self.backend_presence_counts,
        }


@dataclass(slots=True)
class ExtractionComparisonCheckResult:
    passed: bool
    failures: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "failures": self.failures,
        }


class ReferenceExtractionBackend(Protocol):
    name: str

    def extract_references(self, text: str) -> list[BibEntry]:
        ...


@dataclass(slots=True)
class HeuristicReferenceExtractionBackend:
    name: str = "heuristic"

    def extract_references(self, text: str) -> list[BibEntry]:
        return _extract_references_heuristic(text)


@dataclass(slots=True)
class AnystyleCliReferenceExtractionBackend:
    name: str = "anystyle"
    command: str | None = None
    parser_model: str | None = None

    def extract_references(self, text: str) -> list[BibEntry]:
        command = self.command or os.getenv("CITEGEIST_ANYSTYLE_BIN", "anystyle")
        parser_model = self.parser_model or os.getenv("CITEGEIST_ANYSTYLE_PARSER_MODEL")
        if shutil.which(command) is None:
            raise RuntimeError(
                "The 'anystyle' extraction backend requires the AnyStyle CLI to be installed and on PATH. "
                "Set CITEGEIST_ANYSTYLE_BIN if the binary is elsewhere."
            )

        blocks = _iter_reference_blocks(text)
        if not blocks:
            return []

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
            handle.write("\n".join(blocks) + "\n")
            input_path = handle.name

        args = [command, "--stdout", "-f", "json"]
        if parser_model:
            args.extend(["-P", parser_model])
        args.extend(["parse", input_path])

        try:
            result = subprocess.run(args, capture_output=True, text=True, check=False)
        finally:
            try:
                os.unlink(input_path)
            except OSError:
                pass

        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "unknown AnyStyle error"
            raise RuntimeError(f"AnyStyle extraction failed: {message}")

        payload = json.loads(result.stdout or "[]")
        if not isinstance(payload, list):
            raise RuntimeError("AnyStyle extraction returned an unexpected payload")
        return [_anystyle_item_to_entry(item, index) for index, item in enumerate(payload, start=1)]


@dataclass(slots=True)
class GrobidReferenceExtractionBackend:
    name: str = "grobid"
    base_url: str | None = None
    consolidate_citations: int = 0
    include_raw_citations: int = 1

    def extract_references(self, text: str) -> list[BibEntry]:
        blocks = _iter_reference_blocks(text)
        if not blocks:
            return []

        base_url = (self.base_url or os.getenv("CITEGEIST_GROBID_URL", "http://127.0.0.1:8070")).rstrip("/")
        payload = urllib.parse.urlencode(
            {
                "citations": blocks,
                "consolidateCitations": str(self.consolidate_citations),
                "includeRawCitations": str(self.include_raw_citations),
            },
            doseq=True,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/api/processCitationList",
            data=payload,
            headers={
                "Accept": "application/x-bibtex",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read()
            if isinstance(error_body, bytes):
                detail = error_body.decode("utf-8", errors="replace").strip()
            else:
                detail = str(error_body or "").strip()
            raise RuntimeError(f"GROBID extraction failed with HTTP {exc.code}: {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GROBID extraction failed: {exc.reason}") from exc

        if not body.strip():
            return []

        try:
            entries = parse_bibtex(body)
        except Exception as exc:
            raise RuntimeError("GROBID extraction returned invalid BibTeX output") from exc

        for index, entry in enumerate(entries, start=1):
            if entry.citation_key in {"-1", "1", ""}:
                entry.citation_key = _make_citation_key(
                    entry.fields.get("author", "ref"),
                    entry.fields.get("year", "nd"),
                    entry.fields.get("title", "untitled"),
                    index,
                )
        return entries


_EXTRACTION_BACKENDS: dict[str, ReferenceExtractionBackend] = {
    "heuristic": HeuristicReferenceExtractionBackend(),
    "anystyle": AnystyleCliReferenceExtractionBackend(),
    "grobid": GrobidReferenceExtractionBackend(),
}


def available_extraction_backends() -> list[str]:
    return sorted(_EXTRACTION_BACKENDS)


def get_extraction_backend(name: str = "heuristic") -> ReferenceExtractionBackend:
    try:
        return _EXTRACTION_BACKENDS[name]
    except KeyError as exc:
        choices = ", ".join(available_extraction_backends())
        raise ValueError(f"Unknown extraction backend: {name}. Available backends: {choices}") from exc


def register_extraction_backend(backend: ReferenceExtractionBackend) -> None:
    _EXTRACTION_BACKENDS[backend.name] = backend


def extract_references(text: str, backend: str = "heuristic") -> list[BibEntry]:
    backend_impl = get_extraction_backend(backend)
    entries = backend_impl.extract_references(text)
    raw_references = _iter_reference_blocks(text)
    return _normalize_extracted_entries(entries, raw_references, backend_impl.name)


def render_extracted_bibtex(text: str, backend: str = "heuristic") -> str:
    from .bibtex import render_bibtex

    return render_bibtex(extract_references(text, backend=backend))


def compare_extraction_backends(text: str, backends: list[str] | None = None) -> list[ExtractionComparisonRow]:
    selected = backends or available_extraction_backends()
    raw_references = _iter_reference_blocks(text)
    extracted_by_backend = {backend: extract_references(text, backend=backend) for backend in selected}

    rows: list[ExtractionComparisonRow] = []
    max_count = max([len(raw_references), *(len(entries) for entries in extracted_by_backend.values())], default=0)
    for index in range(max_count):
        entries_payload: dict[str, dict[str, object]] = {}
        all_field_names: set[str] = set()
        for backend in selected:
            entry = extracted_by_backend[backend][index] if index < len(extracted_by_backend[backend]) else None
            payload = _entry_to_comparison_payload(entry)
            entries_payload[backend] = payload
            all_field_names.update(str(field_name) for field_name in payload.get("fields", {}))

        differing_fields: list[str] = []
        entry_type_values = {str(entries_payload[backend].get("entry_type") or "") for backend in selected}
        if len(entry_type_values) > 1:
            differing_fields.append("entry_type")
        for field_name in sorted(all_field_names):
            values = {
                str(entries_payload[backend].get("fields", {}).get(field_name, "<missing>"))
                for backend in selected
            }
            if len(values) > 1:
                differing_fields.append(field_name)
        rows.append(
            ExtractionComparisonRow(
                ordinal=index + 1,
                raw_reference=raw_references[index] if index < len(raw_references) else "",
                entries=entries_payload,
                differing_fields=differing_fields,
            )
        )
    return rows


def summarize_extraction_comparison(rows: list[ExtractionComparisonRow]) -> ExtractionComparisonSummary:
    backend_names = sorted({backend for row in rows for backend in row.entries})
    differing_field_counts: dict[str, int] = {}
    backend_presence_counts: dict[str, int] = {backend: 0 for backend in backend_names}
    rows_with_differences = 0

    for row in rows:
        if row.differing_fields:
            rows_with_differences += 1
        for field_name in row.differing_fields:
            differing_field_counts[field_name] = differing_field_counts.get(field_name, 0) + 1
        for backend, payload in row.entries.items():
            if payload.get("present"):
                backend_presence_counts[backend] = backend_presence_counts.get(backend, 0) + 1

    return ExtractionComparisonSummary(
        backends=backend_names,
        row_count=len(rows),
        rows_with_differences=rows_with_differences,
        differing_field_counts=dict(sorted(differing_field_counts.items())),
        backend_presence_counts=dict(sorted(backend_presence_counts.items())),
    )


def check_extraction_comparison_summary(
    summary: ExtractionComparisonSummary,
    *,
    max_rows_with_differences: int | None = None,
    max_field_difference_count: int | None = None,
) -> ExtractionComparisonCheckResult:
    failures: list[str] = []
    if max_rows_with_differences is not None and summary.rows_with_differences > max_rows_with_differences:
        failures.append(
            f"rows_with_differences {summary.rows_with_differences} exceeds limit {max_rows_with_differences}"
        )
    if max_field_difference_count is not None:
        for field_name, count in summary.differing_field_counts.items():
            if count > max_field_difference_count:
                failures.append(
                    f"field '{field_name}' difference count {count} exceeds limit {max_field_difference_count}"
                )
    return ExtractionComparisonCheckResult(passed=not failures, failures=failures)


def _extract_references_heuristic(text: str) -> list[BibEntry]:
    entries: list[BibEntry] = []
    for index, line in enumerate(_iter_reference_blocks(text), start=1):
        parsed = _parse_reference_line(line, index)
        if parsed is not None:
            entries.append(parsed)
    return entries


def _entry_to_comparison_payload(entry: BibEntry | None) -> dict[str, object]:
    if entry is None:
        return {"present": False, "citation_key": None, "entry_type": None, "fields": {}}
    return {
        "present": True,
        "citation_key": entry.citation_key,
        "entry_type": entry.entry_type,
        "fields": dict(entry.fields),
    }


def _normalize_extracted_entries(
    entries: list[BibEntry],
    raw_references: list[str],
    backend_name: str,
) -> list[BibEntry]:
    normalized_entries: list[BibEntry] = []
    for index, entry in enumerate(entries):
        raw_reference = raw_references[index] if index < len(raw_references) else ""
        normalized_entries.append(_normalize_extracted_entry(entry, backend_name, raw_reference))
    return normalized_entries


def _normalize_extracted_entry(entry: BibEntry, backend_name: str, raw_reference: str) -> BibEntry:
    fields = dict(entry.fields)

    for key in (
        "title",
        "journal",
        "booktitle",
        "publisher",
        "school",
        "institution",
        "howpublished",
        "address",
    ):
        if fields.get(key):
            fields[key] = _clean_title(fields[key])

    if year := fields.get("year"):
        if match := YEAR_PATTERN.search(year):
            fields["year"] = match.group(0)

    if pages := fields.get("pages"):
        fields["pages"] = _normalize_pages(pages)

    if doi := fields.get("doi"):
        normalized_doi = doi.strip().rstrip(".,;)")
        fields["doi"] = normalized_doi
        fields["url"] = f"https://doi.org/{normalized_doi}"
    elif url := fields.get("url"):
        fields["url"] = url.strip().rstrip(".,;)")

    fields["note"] = _merge_extraction_note(fields.get("note", ""), backend_name, raw_reference)
    return BibEntry(entry_type=entry.entry_type, citation_key=entry.citation_key, fields=fields)


def _merge_extraction_note(existing: str, backend_name: str, raw_reference: str) -> str:
    parts: list[str] = []
    existing_clean = existing.strip()
    if existing_clean:
        parts.append(existing_clean)
    lowered = existing_clean.casefold()
    if "extracted_reference" not in lowered:
        parts.append("extracted_reference = {true}")
    if "extracted_by" not in lowered:
        parts.append(f"extracted_by = {{{backend_name}}}")
    if raw_reference and "raw_reference" not in lowered:
        parts.append(f"raw_reference = {{{raw_reference}}}")
    return "; ".join(parts)


def _anystyle_item_to_entry(item: object, ordinal: int) -> BibEntry:
    if not isinstance(item, dict):
        raise RuntimeError("AnyStyle extraction item is not an object")

    title = _clean_title(_first_text(item.get("title")))
    authors = _anystyle_people_to_names(item.get("author"))
    year = _extract_year_from_values(item.get("date"))
    entry_type = _map_anystyle_type(_first_text(item.get("type")))
    citation_key = _make_citation_key(authors or "ref", year or "nd", title or "untitled", ordinal)

    fields: dict[str, str] = {
        "note": "extracted_reference = {true}; extracted_by = {anystyle}",
    }
    if authors:
        fields["author"] = authors
    if year:
        fields["year"] = year
    if title:
        fields["title"] = title

    if editors := _anystyle_people_to_names(item.get("editor")):
        fields["editor"] = editors
    if publisher := _first_text(item.get("publisher")):
        fields["publisher"] = publisher
    if location := _first_text(item.get("location")):
        fields["address"] = location
    if pages := _first_text(item.get("pages")):
        fields["pages"] = _normalize_pages(pages)
    if volume := _first_text(item.get("volume")):
        fields["volume"] = volume
    if number := _first_text(item.get("issue")) or _first_text(item.get("number")):
        fields["number"] = number
    if doi := _first_text(item.get("doi")):
        fields["doi"] = doi
        fields["url"] = f"https://doi.org/{doi}"
    elif url := _first_text(item.get("url")):
        fields["url"] = url

    container = _first_text(item.get("journal")) or _first_text(item.get("container-title"))
    if not container and entry_type in {"book", "phdthesis", "mastersthesis", "techreport"}:
        container = _first_text(item.get("organization")) or _first_text(item.get("institution")) or _first_text(item.get("school"))

    if container:
        if entry_type == "article":
            fields["journal"] = container
        elif entry_type in {"inproceedings", "incollection"}:
            fields["booktitle"] = container
        elif entry_type == "techreport":
            fields["institution"] = container
        elif entry_type in {"phdthesis", "mastersthesis"}:
            fields["school"] = container
        elif entry_type == "book" and "publisher" not in fields:
            fields["publisher"] = container
        else:
            fields["howpublished"] = container

    return BibEntry(entry_type=entry_type, citation_key=citation_key, fields=fields)


def _iter_reference_blocks(text: str) -> list[str]:
    lines: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                lines.append(" ".join(current))
                current = []
            continue
        starts_new = bool(REF_START_PATTERN.match(line))
        line = REF_START_PATTERN.sub("", line)
        normalized = " ".join(line.split())
        if len(normalized) < 20:
            continue
        if starts_new and current:
            lines.append(" ".join(current))
            current = [normalized]
        else:
            current.append(normalized)
    if current:
        lines.append(" ".join(current))
    return lines


def _parse_reference_line(line: str, ordinal: int) -> BibEntry | None:
    for parser in (_parse_apa_style_reference, _parse_publisher_style_reference, _parse_plain_year_reference):
        parsed = parser(line, ordinal)
        if parsed is not None:
            return parsed
    return None


def _parse_apa_style_reference(line: str, ordinal: int) -> BibEntry | None:
    year_match = YEAR_PAREN_PATTERN.search(line)
    if year_match is None:
        return None

    year = year_match.group(0).strip("()")
    author_part = line[: year_match.start()].strip(" .")
    remainder = line[year_match.end() :].strip(" .")
    if not author_part or not remainder:
        return None

    segments = _segments_after_year(remainder)
    if not segments:
        return None

    parts = _make_reference_parts(line, author_part, year, remainder)
    if parts is None:
        return None
    return _build_entry(parts, ordinal)


def _parse_publisher_style_reference(line: str, ordinal: int) -> BibEntry | None:
    year_match = YEAR_PATTERN.search(line)
    if year_match is None:
        return None

    prefix = line[: year_match.start()].strip(" .,;")
    if "." not in prefix:
        return None

    head, publisher = prefix.rsplit(".", 1)
    if "." not in head:
        return None
    author_part, title = head.split(".", 1)

    authors = _normalize_authors(author_part)
    title = _clean_title(title)
    publisher = publisher.strip(" .,;")
    if not authors or not title or not publisher:
        return None

    year = year_match.group(0)
    citation_key = _make_citation_key(authors, year, title, ordinal)
    identifiers = _extract_identifier_fields(line)
    metadata = _parse_venue_metadata(publisher)
    entry_type = str(metadata.get("entry_type") or _guess_entry_type(publisher))
    if entry_type not in {"book", "phdthesis", "mastersthesis", "techreport"}:
        entry_type = "book"
    fields: dict[str, str] = {
        "author": authors,
        "year": year,
        "title": title,
        "note": f"extracted_reference = {{true}}; raw_reference = {{{line}}}",
        **identifiers,
    }
    if entry_type == "book":
        fields["publisher"] = str(metadata.get("venue") or publisher)
    elif entry_type in {"phdthesis", "mastersthesis"}:
        fields["school"] = str(metadata.get("venue") or publisher)
    else:
        fields["institution"] = str(metadata.get("venue") or publisher)
    for key in ("number", "type", "series"):
        value = metadata.get(key)
        if value:
            fields[key] = str(value)
    return BibEntry(
        entry_type=entry_type,
        citation_key=citation_key,
        fields=fields,
    )


def _parse_plain_year_reference(line: str, ordinal: int) -> BibEntry | None:
    year_match = YEAR_PATTERN.search(line)
    if year_match is None:
        return None

    year = year_match.group(0)
    author_part = line[: year_match.start()].strip(" .")
    remainder = line[year_match.end() :].strip(" .")
    if not author_part or not remainder:
        return None

    parts = _make_reference_parts(line, author_part, year, remainder)
    if parts is None:
        return None
    return _build_entry(parts, ordinal)


def _normalize_authors(author_part: str) -> str:
    normalized = author_part.replace(" & ", " and ")
    normalized = re.sub(r"\bet al\.?$", "and others", normalized)
    normalized = re.sub(r"\s+and\s+", " and ", normalized)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    return normalized.strip(" .")


def _segments_after_year(remainder: str) -> list[str]:
    return [segment.strip(" .") for segment in remainder.split(". ") if segment.strip(" .")]


def _split_title_and_venue(remainder: str, *, prefer_colon: bool = False) -> tuple[str, str]:
    if prefer_colon and ": " in remainder:
        title, venue = remainder.split(": ", 1)
        return _clean_title(title), _clean_title(venue)

    segments = _segments_after_year(remainder)
    if not segments:
        return "", ""
    title = _clean_title(segments[0])
    venue = ". ".join(segments[1:]) if len(segments) > 1 else ""
    return title, _clean_title(venue) if venue else ""


def _clean_title(title: str) -> str:
    cleaned = title.strip(" .,;:\"'")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _make_reference_parts(raw_line: str, author_part: str, year: str, remainder: str) -> ParsedReferenceParts | None:
    title, venue = _split_title_and_venue(remainder)
    authors = _normalize_authors(author_part)
    if not authors or not title:
        return None
    return ParsedReferenceParts(
        raw_line=raw_line,
        authors=authors,
        year=year,
        title=title,
        venue=venue,
    )


def _build_entry(parts: ParsedReferenceParts, ordinal: int) -> BibEntry:
    citation_key = _make_citation_key(parts.authors, parts.year, parts.title, ordinal)
    entry_type = _guess_entry_type(parts.venue)
    metadata = _parse_venue_metadata(parts.venue)
    if metadata.get("entry_type"):
        entry_type = str(metadata["entry_type"])

    fields: dict[str, str] = {
        "author": parts.authors,
        "year": parts.year,
        "title": parts.title,
        "note": f"extracted_reference = {{true}}; raw_reference = {{{parts.raw_line}}}",
    }
    fields.update(_extract_identifier_fields(parts.raw_line))
    if metadata.get("venue"):
        venue_value = str(metadata["venue"])
        if entry_type == "article":
            fields["journal"] = venue_value
        elif entry_type in {"inproceedings", "incollection"}:
            fields["booktitle"] = venue_value
        elif entry_type == "book":
            fields["publisher"] = venue_value
        elif entry_type in {"phdthesis", "mastersthesis"}:
            fields["school"] = venue_value
        elif entry_type == "techreport":
            fields["institution"] = venue_value
        else:
            fields["howpublished"] = venue_value
    for key in ("volume", "number", "pages", "publisher", "institution", "school", "type", "series"):
        value = metadata.get(key)
        if value:
            fields[key] = str(value)

    return BibEntry(entry_type=entry_type, citation_key=citation_key, fields=fields)


def _make_citation_key(authors: str, year: str, title: str, ordinal: int) -> str:
    first_author = authors.split(" and ")[0]
    family_name = first_author.split(",")[0] if "," in first_author else first_author.split()[-1]
    family_name = re.sub(r"[^A-Za-z0-9]+", "", family_name).lower() or "ref"

    first_word = re.sub(r"[^A-Za-z0-9]+", "", title.split()[0]).lower() if title.split() else "untitled"
    if not first_word:
        first_word = "untitled"
    return f"{family_name}{year}{first_word}{ordinal}"


def _guess_entry_type(venue: str) -> str:
    lowered = venue.lower()
    if "master" in lowered and "thesis" in lowered:
        return "mastersthesis"
    if any(token in lowered for token in ("ph.d", "phd", "doctoral dissertation", "doctor's thesis", "thesis", "dissertation")):
        return "phdthesis"
    if any(token in lowered for token in ("technical report", "tech report", "report no", "working paper", "bulletin")):
        return "techreport"
    if any(token in lowered for token in ("retrieved from", "available at", "accessed", "http://", "https://", "www.")):
        return "misc"
    if any(token in lowered for token in ("journal", "transactions", "review", "letters")):
        return "article"
    if any(token in lowered for token in ("proceedings", "conference", "workshop", "symposium")):
        return "inproceedings"
    if any(token in lowered for token in ("press", "publisher", "publications", "springer", "wiley", "elsevier", "university")):
        return "book"
    return "misc"


def _extract_identifier_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    if doi_match := DOI_PATTERN.search(text):
        doi = doi_match.group(0).rstrip(".,;)")
        fields["doi"] = doi
        fields["url"] = f"https://doi.org/{doi}"
    elif url_match := URL_PATTERN.search(text):
        fields["url"] = url_match.group(0).rstrip(".,;)")
    if arxiv_match := ARXIV_PATTERN.search(text):
        fields["arxiv"] = arxiv_match.group(1).rstrip(".,;)")
    if isbn_match := ISBN_PATTERN.search(text):
        fields["isbn"] = isbn_match.group(1).strip()
    if issn_match := ISSN_PATTERN.search(text):
        fields["issn"] = issn_match.group(1).strip()
    return fields


def _looks_like_citation_blob(text: str) -> bool:
    lowered = text.casefold()
    if any(token in lowered for token in ("http://", "https://", "www.", " accessed ", " url ")):
        return True
    if any(token in lowered for token in ("supporting material", "grant", "poll results", "prescribing information")):
        return True
    if text.count(",") >= 3 or text.count(";") >= 2:
        return True
    if re.search(r"\(\d{4}[a-z]?\)", text, flags=re.IGNORECASE):
        return True
    if re.search(r"\b[A-Z]\.[ ]?[A-Z]?\.", text):
        return True
    return False


def _extract_thesis_like_title(text: str) -> str:
    normalized = _clean_title(" ".join(text.split()))
    if not normalized:
        return ""

    match = THESIS_MARKER_PATTERN.search(normalized)
    if match is not None:
        normalized = normalized[: match.start()].strip(" .")
    for marker in (" ProQuest", " UMI No.", " Dissertation Abstracts", " University Microfilms"):
        if marker in normalized:
            normalized = normalized.split(marker, 1)[0].strip(" .")
    if match is not None and ". " in normalized:
        normalized = normalized.split(". ", 1)[1].strip()
    return normalized.strip(" .")


def _parse_venue_metadata(venue: str) -> dict[str, str]:
    if not venue:
        return {}

    # These recovery heuristics intentionally mirror patterns already used in
    # citegeist.talkorigins / citegeist.expand and were scoped using GROBID-like
    # staged parsing concerns: preserve identifiers, venue fragments, and page structure.
    normalized = venue.strip(" .")
    metadata: dict[str, str] = {"venue": normalized}
    entry_type = _guess_entry_type(normalized)
    metadata["entry_type"] = entry_type

    lowered = normalized.lower()
    if entry_type == "misc" and ("retrieved from" in lowered or "available at" in lowered):
        metadata["venue"] = _clean_title(normalized)

    if volume_match := VOLUME_ISSUE_PAGES_PATTERN.search(normalized):
        metadata["volume"] = volume_match.group("volume").strip()
        if volume_match.group("number"):
            metadata["number"] = volume_match.group("number").strip()
        metadata["pages"] = _normalize_pages(volume_match.group("pages"))
        venue_prefix = normalized[: volume_match.start()].strip(" ,;:.")
        if venue_prefix:
            metadata["venue"] = venue_prefix
    elif pages_match := PAGES_PATTERN.search(normalized):
        metadata["pages"] = _normalize_pages(pages_match.group("pages"))
        venue_prefix = normalized[: pages_match.start()].strip(" ,;:.")
        if venue_prefix:
            metadata["venue"] = venue_prefix
    elif trailing_pages_match := TRAILING_PAGE_PATTERN.search(normalized):
        metadata["pages"] = _normalize_pages(trailing_pages_match.group("pages"))
        venue_prefix = normalized[: trailing_pages_match.start()].strip(" ,;:.")
        if venue_prefix:
            metadata["venue"] = venue_prefix

    if entry_type == "techreport":
        if report_match := REPORT_NUMBER_PATTERN.search(normalized):
            metadata["number"] = report_match.group("number").strip()
            metadata["type"] = "Technical Report"
        institution = _strip_report_prefix(metadata.get("venue", normalized))
        if institution:
            metadata["venue"] = institution
    elif entry_type in {"phdthesis", "mastersthesis"}:
        school = _strip_thesis_prefix(metadata.get("venue", normalized))
        if school:
            metadata["venue"] = school
    return metadata


def _normalize_pages(value: str) -> str:
    compact = re.sub(r"\s*[\u2013-]+\s*", "--", value.strip())
    return re.sub(r"-{3,}", "--", compact)


def _strip_report_prefix(value: str) -> str:
    cleaned = re.sub(r"\b(?:technical\s+report|tech report|report|working\s+paper|bulletin)\b", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:no\.?|number)\s*[A-Za-z0-9.\-]+\b", "", cleaned, flags=re.IGNORECASE)
    return _clean_title(cleaned)


def _strip_thesis_prefix(value: str) -> str:
    cleaned = re.sub(r"\b(?:ph\.?d\.?|doctoral|doctor's|master'?s)\s+(?:dissertation|thesis)\b", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\((?:master|doctoral).*?\)\s*", "", cleaned, flags=re.IGNORECASE)
    return _clean_title(cleaned)


def _first_text(value: object) -> str:
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
        return ""
    if isinstance(value, dict):
        for key in ("literal", "value", "text", "name"):
            text = _first_text(value.get(key))
            if text:
                return text
        return ""
    if value is None:
        return ""
    return _clean_title(str(value))


def _extract_year_from_values(value: object) -> str:
    text = _first_text(value)
    match = YEAR_PATTERN.search(text)
    return match.group(0) if match is not None else ""


def _anystyle_people_to_names(value: object) -> str:
    if not isinstance(value, list):
        return ""
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            family = _first_text(item.get("family"))
            given = _first_text(item.get("given"))
            literal = _first_text(item.get("literal"))
            if family and given:
                names.append(f"{family}, {given}")
            elif literal:
                names.append(literal)
            elif family:
                names.append(family)
        else:
            text = _first_text(item)
            if text:
                names.append(text)
    return " and ".join(name for name in names if name)


def _map_anystyle_type(value: str) -> str:
    lowered = value.casefold()
    if lowered in {"article", "journal_article", "article-journal"}:
        return "article"
    if lowered in {"chapter", "incollection"}:
        return "incollection"
    if lowered in {"paper-conference", "inproceedings", "proceedings"}:
        return "inproceedings"
    if lowered in {"thesis", "phdthesis", "dissertation"}:
        return "phdthesis"
    if lowered in {"mastersthesis", "master-thesis"}:
        return "mastersthesis"
    if lowered in {"report", "techreport"}:
        return "techreport"
    if lowered == "book":
        return "book"
    return "misc"
