from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .bibtex import BibEntry, parse_bibtex

IDENTIFIER_FIELDS = ("doi", "isbn", "issn", "pmid", "arxiv", "dblp", "oai", "url")
RELATION_FIELDS = {
    "references": "cites",
    "cites": "cites",
    "cited_by": "cited_by",
    "crossref": "crossref",
}
CORE_ENTRY_FIELDS = {
    "title",
    "year",
    "journal",
    "booktitle",
    "publisher",
    "abstract",
    "keywords",
    "url",
    "doi",
    "isbn",
}


class BibliographyStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._fts5_enabled = self._detect_fts5()
        self.initialize()

    def close(self) -> None:
        self.connection.close()

    def initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY,
                citation_key TEXT NOT NULL UNIQUE,
                entry_type TEXT NOT NULL,
                title TEXT,
                year TEXT,
                journal TEXT,
                booktitle TEXT,
                publisher TEXT,
                abstract TEXT,
                keywords TEXT,
                url TEXT,
                doi TEXT,
                isbn TEXT,
                fulltext TEXT,
                raw_bibtex TEXT,
                extra_fields_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS creators (
                id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL UNIQUE,
                family_name TEXT,
                given_names TEXT
            );

            CREATE TABLE IF NOT EXISTS entry_creators (
                entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                creator_id INTEGER NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                PRIMARY KEY (entry_id, role, ordinal)
            );

            CREATE TABLE IF NOT EXISTS identifiers (
                entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                scheme TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (scheme, value)
            );

            CREATE TABLE IF NOT EXISTS relations (
                source_entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                target_citation_key TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                PRIMARY KEY (source_entry_id, target_citation_key, relation_type)
            );
            """
        )

        if self._fts5_enabled:
            self.connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS entry_text_fts
                USING fts5(
                    citation_key UNINDEXED,
                    title,
                    abstract,
                    fulltext
                )
                """
            )
        self.connection.commit()

    def ingest_bibtex(self, text: str, fulltext_by_key: dict[str, str] | None = None) -> list[str]:
        fulltext_by_key = fulltext_by_key or {}
        entries = parse_bibtex(text)
        keys: list[str] = []
        for entry in entries:
            fulltext = fulltext_by_key.get(entry.citation_key)
            self.upsert_entry(entry, fulltext=fulltext, raw_bibtex=_entry_to_bibtex(entry))
            keys.append(entry.citation_key)
        self.connection.commit()
        return keys

    def upsert_entry(self, entry: BibEntry, fulltext: str | None = None, raw_bibtex: str | None = None) -> int:
        row = self.connection.execute(
            """
            INSERT INTO entries (
                citation_key, entry_type, title, year, journal, booktitle, publisher,
                abstract, keywords, url, doi, isbn, fulltext, raw_bibtex, extra_fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(citation_key) DO UPDATE SET
                entry_type = excluded.entry_type,
                title = excluded.title,
                year = excluded.year,
                journal = excluded.journal,
                booktitle = excluded.booktitle,
                publisher = excluded.publisher,
                abstract = excluded.abstract,
                keywords = excluded.keywords,
                url = excluded.url,
                doi = excluded.doi,
                isbn = excluded.isbn,
                fulltext = COALESCE(excluded.fulltext, entries.fulltext),
                raw_bibtex = COALESCE(excluded.raw_bibtex, entries.raw_bibtex),
                extra_fields_json = excluded.extra_fields_json,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (
                entry.citation_key,
                entry.entry_type,
                entry.fields.get("title"),
                entry.fields.get("year"),
                entry.fields.get("journal"),
                entry.fields.get("booktitle"),
                entry.fields.get("publisher"),
                entry.fields.get("abstract"),
                entry.fields.get("keywords"),
                entry.fields.get("url"),
                entry.fields.get("doi"),
                entry.fields.get("isbn"),
                fulltext,
                raw_bibtex,
                json.dumps({k: v for k, v in entry.fields.items() if k not in CORE_ENTRY_FIELDS and k not in RELATION_FIELDS}),
            ),
        ).fetchone()
        entry_id = int(row["id"])

        self.connection.execute("DELETE FROM entry_creators WHERE entry_id = ?", (entry_id,))
        for role in ("author", "editor"):
            names = _split_names(entry.fields.get(role, ""))
            for ordinal, name in enumerate(names, start=1):
                creator = _split_person_name(name)
                creator_row = self.connection.execute(
                    """
                    INSERT INTO creators (full_name, family_name, given_names)
                    VALUES (?, ?, ?)
                    ON CONFLICT(full_name) DO UPDATE SET
                        family_name = COALESCE(excluded.family_name, creators.family_name),
                        given_names = COALESCE(excluded.given_names, creators.given_names)
                    RETURNING id
                    """,
                    (creator["full_name"], creator["family_name"], creator["given_names"]),
                ).fetchone()
                self.connection.execute(
                    """
                    INSERT INTO entry_creators (entry_id, creator_id, role, ordinal)
                    VALUES (?, ?, ?, ?)
                    """,
                    (entry_id, int(creator_row["id"]), role, ordinal),
                )

        self.connection.execute("DELETE FROM identifiers WHERE entry_id = ?", (entry_id,))
        for scheme in IDENTIFIER_FIELDS:
            value = entry.fields.get(scheme)
            if value:
                self.connection.execute(
                    "INSERT OR REPLACE INTO identifiers (entry_id, scheme, value) VALUES (?, ?, ?)",
                    (entry_id, scheme, value),
                )

        self.connection.execute("DELETE FROM relations WHERE source_entry_id = ?", (entry_id,))
        for field_name, relation_type in RELATION_FIELDS.items():
            values = _split_relation_values(entry.fields.get(field_name, ""))
            for target_key in values:
                self.connection.execute(
                    """
                    INSERT OR IGNORE INTO relations (source_entry_id, target_citation_key, relation_type)
                    VALUES (?, ?, ?)
                    """,
                    (entry_id, target_key, relation_type),
                )

        if self._fts5_enabled:
            self.connection.execute("DELETE FROM entry_text_fts WHERE citation_key = ?", (entry.citation_key,))
            self.connection.execute(
                """
                INSERT INTO entry_text_fts (citation_key, title, abstract, fulltext)
                VALUES (?, ?, ?, ?)
                """,
                (entry.citation_key, entry.fields.get("title", ""), entry.fields.get("abstract", ""), fulltext or ""),
            )

        return entry_id

    def search_text(self, query: str, limit: int = 10) -> list[dict[str, object]]:
        if self._fts5_enabled:
            rows = self.connection.execute(
                """
                SELECT e.citation_key, e.title, e.year, bm25(entry_text_fts) AS score
                FROM entry_text_fts
                JOIN entries e ON e.citation_key = entry_text_fts.citation_key
                WHERE entry_text_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        else:
            pattern = f"%{query}%"
            rows = self.connection.execute(
                """
                SELECT citation_key, title, year, 0.0 AS score
                FROM entries
                WHERE title LIKE ? OR abstract LIKE ? OR fulltext LIKE ?
                LIMIT ?
                """,
                (pattern, pattern, pattern, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_relations(self, citation_key: str, relation_type: str = "cites") -> list[str]:
        rows = self.connection.execute(
            """
            SELECT r.target_citation_key
            FROM relations r
            JOIN entries e ON e.id = r.source_entry_id
            WHERE e.citation_key = ? AND r.relation_type = ?
            ORDER BY r.target_citation_key
            """,
            (citation_key, relation_type),
        ).fetchall()
        return [str(row["target_citation_key"]) for row in rows]

    def get_entry(self, citation_key: str) -> dict[str, object] | None:
        row = self.connection.execute(
            "SELECT * FROM entries WHERE citation_key = ?",
            (citation_key,),
        ).fetchone()
        return dict(row) if row else None

    def _detect_fts5(self) -> bool:
        try:
            self.connection.execute("CREATE VIRTUAL TABLE temp.fts_probe USING fts5(content)")
            self.connection.execute("DROP TABLE temp.fts_probe")
            return True
        except sqlite3.OperationalError:
            return False


def _split_names(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(" and ") if part.strip()]


def _split_person_name(name: str) -> dict[str, str | None]:
    if "," in name:
        family_name, given_names = [part.strip() for part in name.split(",", 1)]
    else:
        parts = name.split()
        family_name = parts[-1] if parts else ""
        given_names = " ".join(parts[:-1]) if len(parts) > 1 else None
    return {
        "full_name": name.strip(),
        "family_name": family_name or None,
        "given_names": given_names or None,
    }


def _split_relation_values(value: str) -> list[str]:
    if not value:
        return []
    normalized = value.replace("\n", ",").replace(";", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def _entry_to_bibtex(entry: BibEntry) -> str:
    lines = [f"@{entry.entry_type}{{{entry.citation_key},"]
    for key, value in entry.fields.items():
        lines.append(f"  {key} = {{{value}}},")
    lines.append("}")
    return "\n".join(lines)
