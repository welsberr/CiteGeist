from __future__ import annotations

import re

from .bibtex import BibEntry

YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


def extract_references(text: str) -> list[BibEntry]:
    entries: list[BibEntry] = []
    for index, line in enumerate(_iter_reference_lines(text), start=1):
        parsed = _parse_reference_line(line, index)
        if parsed is not None:
            entries.append(parsed)
    return entries


def render_extracted_bibtex(text: str) -> str:
    from .bibtex import render_bibtex

    return render_bibtex(extract_references(text))


def _iter_reference_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^\[\d+\]\s*", "", line)
        line = re.sub(r"^\d+\.\s*", "", line)
        line = re.sub(r"^\(\d+\)\s*", "", line)
        if len(line) < 20:
            continue
        lines.append(" ".join(line.split()))
    return lines


def _parse_reference_line(line: str, ordinal: int) -> BibEntry | None:
    year_match = YEAR_PATTERN.search(line)
    if year_match is None:
        return None

    year = year_match.group(0)
    author_part = line[: year_match.start()].strip(" .")
    remainder = line[year_match.end() :].strip(" .")
    if not author_part or not remainder:
        return None

    segments = [segment.strip(" .") for segment in remainder.split(".") if segment.strip(" .")]
    if not segments:
        return None

    title = segments[0]
    venue = segments[1] if len(segments) > 1 else ""

    authors = _normalize_authors(author_part)
    citation_key = _make_citation_key(authors, year, title, ordinal)
    entry_type = _guess_entry_type(venue)

    fields: dict[str, str] = {
        "author": authors,
        "year": year,
        "title": title,
        "note": f"extracted_reference = {{true}}; raw_reference = {{{line}}}",
    }
    if venue:
        if entry_type == "article":
            fields["journal"] = venue
        else:
            fields["booktitle"] = venue

    return BibEntry(entry_type=entry_type, citation_key=citation_key, fields=fields)


def _normalize_authors(author_part: str) -> str:
    normalized = author_part.replace(" & ", " and ")
    normalized = re.sub(r"\bet al\.$", "and others", normalized)
    normalized = re.sub(r"\s+and\s+", " and ", normalized)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    return normalized.strip(" .")


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
    if any(token in lowered for token in ("journal", "transactions", "review", "letters")):
        return "article"
    if any(token in lowered for token in ("proceedings", "conference", "workshop", "symposium")):
        return "inproceedings"
    return "misc"
