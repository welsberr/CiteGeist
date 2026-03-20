from __future__ import annotations

import re

from .bibtex import BibEntry

YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
YEAR_PAREN_PATTERN = re.compile(r"\((19|20)\d{2}\)")
REF_START_PATTERN = re.compile(r"^(?:\[\d+\]|\d+\.|\(\d+\))\s*")


def extract_references(text: str) -> list[BibEntry]:
    entries: list[BibEntry] = []
    for index, line in enumerate(_iter_reference_blocks(text), start=1):
        parsed = _parse_reference_line(line, index)
        if parsed is not None:
            entries.append(parsed)
    return entries


def render_extracted_bibtex(text: str) -> str:
    from .bibtex import render_bibtex

    return render_bibtex(extract_references(text))


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

    title = _clean_title(segments[0])
    venue = segments[1] if len(segments) > 1 else ""
    authors = _normalize_authors(author_part)
    return _build_entry(line, ordinal, authors, year, title, venue)


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

    citation_key = _make_citation_key(authors, year_match.group(0), title, ordinal)
    return BibEntry(
        entry_type="book",
        citation_key=citation_key,
        fields={
            "author": authors,
            "year": year_match.group(0),
            "title": title,
            "publisher": publisher,
            "note": f"extracted_reference = {{true}}; raw_reference = {{{line}}}",
        },
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

    segments = _segments_after_year(remainder)
    if not segments:
        return None

    title = _clean_title(segments[0])
    venue = segments[1] if len(segments) > 1 else ""
    authors = _normalize_authors(author_part)
    return _build_entry(line, ordinal, authors, year, title, venue)


def _normalize_authors(author_part: str) -> str:
    normalized = author_part.replace(" & ", " and ")
    normalized = re.sub(r"\bet al\.?$", "and others", normalized)
    normalized = re.sub(r"\s+and\s+", " and ", normalized)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    return normalized.strip(" .")


def _segments_after_year(remainder: str) -> list[str]:
    return [segment.strip(" .") for segment in remainder.split(". ") if segment.strip(" .")]


def _clean_title(title: str) -> str:
    cleaned = title.strip(" .\"'")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _build_entry(
    raw_line: str,
    ordinal: int,
    authors: str,
    year: str,
    title: str,
    venue: str,
) -> BibEntry:
    citation_key = _make_citation_key(authors, year, title, ordinal)
    entry_type = _guess_entry_type(venue)

    fields: dict[str, str] = {
        "author": authors,
        "year": year,
        "title": title,
        "note": f"extracted_reference = {{true}}; raw_reference = {{{raw_line}}}",
    }
    if venue:
        if entry_type == "article":
            fields["journal"] = venue
        elif entry_type == "inproceedings":
            fields["booktitle"] = venue
        else:
            fields["howpublished"] = venue

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
    if any(token in lowered for token in ("journal", "transactions", "review", "letters")):
        return "article"
    if any(token in lowered for token in ("proceedings", "conference", "workshop", "symposium")):
        return "inproceedings"
    if any(token in lowered for token in ("press", "publisher", "university")):
        return "book"
    return "misc"
