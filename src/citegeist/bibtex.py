from __future__ import annotations

from dataclasses import dataclass
from io import StringIO

try:
    from pybtex.database import BibliographyData, Entry, Person, parse_string
    from pybtex.database.output.bibtex import Writer
except ImportError:  # pragma: no cover - exercised only outside the configured venv
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
        fields = dict(entry.fields.items())
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
        fields = {key: value for key, value in entry.fields.items() if key not in {"author", "editor"}}
        persons = {}
        for role in ("author", "editor"):
            raw_names = entry.fields.get(role)
            if raw_names:
                persons[role] = [Person(name.strip()) for name in raw_names.split(" and ") if name.strip()]
        bibliography_entries[entry.citation_key] = Entry(entry.entry_type, fields=fields, persons=persons)

    buffer = StringIO()
    Writer().write_stream(BibliographyData(entries=bibliography_entries), buffer)
    return buffer.getvalue().strip()


def _require_pybtex() -> None:
    if parse_string is None or Writer is None:
        raise RuntimeError(
            "pybtex is required. Use the repo-local virtual environment under .venv/ for citegeist commands."
        )
