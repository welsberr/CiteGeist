from __future__ import annotations

from dataclasses import dataclass
from io import StringIO

try:
    from pybtex.database import BibliographyData, Entry, Person, parse_string
    from pybtex.bibtex.exceptions import BibTeXError
    from pybtex.database.output.bibtex import Writer
except ImportError:  # pragma: no cover - exercised only outside the configured venv
    BibTeXError = None
    BibliographyData = Entry = Person = Writer = None
    parse_string = None


@dataclass(slots=True)
class BibEntry:
    entry_type: str
    citation_key: str
    fields: dict[str, str]


def parse_bibtex(text: str) -> list[BibEntry]:
    _require_pybtex()
    bibliography = parse_string(text, bib_format="bibtex")
    entries: list[BibEntry] = []
    for citation_key, entry in bibliography.entries.items():
        fields = {key: _normalize_parsed_bibtex_value(value) for key, value in entry.fields.items()}
        for role, persons in entry.persons.items():
            fields[role] = " and ".join(str(person) for person in persons)
        entries.append(
            BibEntry(
                entry_type=entry.type,
                citation_key=citation_key,
                fields=fields,
            )
        )
    return entries


def render_bibtex(entries: list[BibEntry]) -> str:
    _require_pybtex()
    bibliography_entries = {}
    for entry in entries:
        fields = {
            key: _sanitize_bibtex_value(value)
            for key, value in entry.fields.items()
            if key not in {"author", "editor"}
        }
        persons = {}
        for role in ("author", "editor"):
            raw_names = entry.fields.get(role)
            if raw_names:
                persons[role] = [Person(name.strip()) for name in raw_names.split(" and ") if name.strip()]
        bibliography_entries[entry.citation_key] = Entry(entry.entry_type, fields=fields, persons=persons)

    buffer = StringIO()
    try:
        Writer().write_stream(BibliographyData(entries=bibliography_entries), buffer)
    except BibTeXError:
        conservative_entries = {}
        for entry in entries:
            fields = {
                key: _flatten_bibtex_braces(value)
                for key, value in entry.fields.items()
                if key not in {"author", "editor"}
            }
            persons = {}
            for role in ("author", "editor"):
                raw_names = entry.fields.get(role)
                if raw_names:
                    persons[role] = [Person(name.strip()) for name in raw_names.split(" and ") if name.strip()]
            conservative_entries[entry.citation_key] = Entry(entry.entry_type, fields=fields, persons=persons)
        buffer = StringIO()
        Writer().write_stream(BibliographyData(entries=conservative_entries), buffer)
    return buffer.getvalue().strip()


def _require_pybtex() -> None:
    if parse_string is None or Writer is None:
        raise RuntimeError(
            "pybtex is required. Use the repo-local virtual environment under .venv/ for citegeist commands."
        )


def _sanitize_bibtex_value(value: str) -> str:
    depth = 0
    parts: list[str] = []
    for char in value:
        if char == "{":
            depth += 1
            parts.append(char)
            continue
        if char == "}":
            if depth == 0:
                parts.append(")")
            else:
                depth -= 1
                parts.append(char)
            continue
        parts.append(char)
    if depth > 0:
        open_count = depth
        normalized = []
        for char in parts:
            if char == "{" and open_count > 0:
                normalized.append("(")
                open_count -= 1
            else:
                normalized.append(char)
        return "".join(normalized)
    return "".join(parts)


def _flatten_bibtex_braces(value: str) -> str:
    return value.replace("{", "(").replace("}", ")")


def _normalize_parsed_bibtex_value(value: str) -> str:
    return (
        value.replace(r"\_", "_")
        .replace(r"\&", "&")
        .replace(r"\%", "%")
        .replace(r"\$", "$")
        .replace(r"\#", "#")
    )
