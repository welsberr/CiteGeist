from __future__ import annotations

import json
import sqlite3
from collections import deque
from collections import OrderedDict
from pathlib import Path

from .bibtex import BibEntry, parse_bibtex, render_bibtex

IDENTIFIER_FIELDS = ("doi", "isbn", "issn", "pmid", "arxiv", "dblp", "oai", "openalex", "url")
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
                review_status TEXT NOT NULL DEFAULT 'draft',
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

            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_url TEXT,
                expansion_phrase TEXT,
                suggested_phrase TEXT,
                phrase_review_status TEXT NOT NULL DEFAULT 'unreviewed',
                phrase_review_notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS entry_topics (
                entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                source_label TEXT NOT NULL,
                confidence REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (entry_id, topic_id)
            );

            CREATE TABLE IF NOT EXISTS field_provenance (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                field_name TEXT NOT NULL,
                field_value TEXT,
                source_type TEXT NOT NULL,
                source_label TEXT NOT NULL,
                operation TEXT NOT NULL,
                confidence REAL,
                recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS relation_provenance (
                id INTEGER PRIMARY KEY,
                source_entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                target_citation_key TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_label TEXT NOT NULL,
                confidence REAL,
                recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS field_conflicts (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                field_name TEXT NOT NULL,
                current_value TEXT,
                proposed_value TEXT,
                source_type TEXT NOT NULL,
                source_label TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        self._ensure_entry_columns()
        self._ensure_topic_columns()

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

    def ingest_bibtex(
        self,
        text: str,
        fulltext_by_key: dict[str, str] | None = None,
        source_label: str = "bibtex_import",
        review_status: str = "draft",
    ) -> list[str]:
        fulltext_by_key = fulltext_by_key or {}
        entries = parse_bibtex(text)
        keys: list[str] = []
        for entry in entries:
            fulltext = fulltext_by_key.get(entry.citation_key)
            self.upsert_entry(
                entry,
                fulltext=fulltext,
                raw_bibtex=_entry_to_bibtex(entry),
                source_type="bibtex",
                source_label=source_label,
                review_status=review_status,
            )
            keys.append(entry.citation_key)
        self.connection.commit()
        return keys

    def upsert_entry(
        self,
        entry: BibEntry,
        fulltext: str | None = None,
        raw_bibtex: str | None = None,
        source_type: str = "manual",
        source_label: str = "manual",
        review_status: str = "draft",
    ) -> int:
        row = self.connection.execute(
            """
            INSERT INTO entries (
                citation_key, entry_type, review_status, title, year, journal, booktitle, publisher,
                abstract, keywords, url, doi, isbn, fulltext, raw_bibtex, extra_fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(citation_key) DO UPDATE SET
                entry_type = excluded.entry_type,
                review_status = excluded.review_status,
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
                review_status,
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
                json.dumps(
                    {
                        k: v
                        for k, v in entry.fields.items()
                        if k not in CORE_ENTRY_FIELDS and k not in RELATION_FIELDS and k not in {"author", "editor"}
                    }
                ),
            ),
        ).fetchone()
        entry_id = int(row["id"])

        self._record_field_provenance(
            entry_id=entry_id,
            entry=entry,
            source_type=source_type,
            source_label=source_label,
            operation="upsert",
            fulltext=fulltext,
        )

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

    def search_text(self, query: str, limit: int = 10, topic_slug: str | None = None) -> list[dict[str, object]]:
        if self._fts5_enabled:
            if topic_slug:
                rows = self.connection.execute(
                    """
                    SELECT DISTINCT e.citation_key, e.title, e.year, bm25(entry_text_fts) AS score
                    FROM entry_text_fts
                    JOIN entries e ON e.citation_key = entry_text_fts.citation_key
                    JOIN entry_topics et ON et.entry_id = e.id
                    JOIN topics t ON t.id = et.topic_id
                    WHERE entry_text_fts MATCH ? AND t.slug = ?
                    ORDER BY score
                    LIMIT ?
                    """,
                    (query, topic_slug, limit),
                ).fetchall()
            else:
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
            if topic_slug:
                rows = self.connection.execute(
                    """
                    SELECT DISTINCT e.citation_key, e.title, e.year, 0.0 AS score
                    FROM entries e
                    JOIN entry_topics et ON et.entry_id = e.id
                    JOIN topics t ON t.id = et.topic_id
                    WHERE t.slug = ? AND (e.title LIKE ? OR e.abstract LIKE ? OR e.fulltext LIKE ?)
                    LIMIT ?
                    """,
                    (topic_slug, pattern, pattern, pattern, limit),
                ).fetchall()
            else:
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

    def traverse_graph(
        self,
        seed_keys: list[str],
        relation_types: list[str] | None = None,
        max_depth: int = 1,
        review_status: str | None = None,
        include_missing: bool = True,
    ) -> list[dict[str, object]]:
        relation_types = relation_types or ["cites"]
        allowed_relations = set(relation_types)
        visited: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque()

        for seed_key in seed_keys:
            queue.append((seed_key, 0))
            visited[seed_key] = 0

        results: list[dict[str, object]] = []
        while queue:
            citation_key, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for edge in self._iter_graph_edges(citation_key, allowed_relations):
                target_key = str(edge["target_citation_key"])
                target_entry = self.get_entry(target_key)
                target_status = target_entry.get("review_status") if target_entry else None

                if review_status is not None and target_status != review_status:
                    if target_entry is not None or not include_missing:
                        continue

                next_depth = depth + 1
                result = {
                    "source_citation_key": citation_key,
                    "target_citation_key": target_key,
                    "relation_type": str(edge["relation_type"]),
                    "depth": next_depth,
                    "target_exists": target_entry is not None,
                    "target_review_status": target_status,
                    "target_title": target_entry.get("title") if target_entry else None,
                }
                results.append(result)

                if target_entry is not None and (target_key not in visited or next_depth < visited[target_key]):
                    visited[target_key] = next_depth
                    queue.append((target_key, next_depth))

        results.sort(
            key=lambda row: (
                int(row["depth"]),
                str(row["relation_type"]),
                str(row["source_citation_key"]),
                str(row["target_citation_key"]),
            )
        )
        return results

    def get_entry(self, citation_key: str) -> dict[str, object] | None:
        row = self.connection.execute(
            "SELECT * FROM entries WHERE citation_key = ?",
            (citation_key,),
        ).fetchone()
        if row is None:
            return None
        payload = self._row_to_entry_dict(row)
        payload["topics"] = self.get_entry_topics(citation_key)
        return payload

    def find_entry_by_identifier(self, scheme: str, value: str) -> dict[str, object] | None:
        row = self.connection.execute(
            """
            SELECT e.*
            FROM identifiers i
            JOIN entries e ON e.id = i.entry_id
            WHERE i.scheme = ? AND i.value = ?
            LIMIT 1
            """,
            (scheme, value),
        ).fetchone()
        if row is None:
            return None
        payload = self._row_to_entry_dict(row)
        payload["topics"] = self.get_entry_topics(str(row["citation_key"]))
        return payload

    def find_entries_by_title(self, title: str) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM entries
            WHERE trim(lower(title)) = trim(lower(?))
            ORDER BY citation_key
            """,
            (title,),
        ).fetchall()
        payloads: list[dict[str, object]] = []
        for row in rows:
            payload = self._row_to_entry_dict(row)
            payload["topics"] = self.get_entry_topics(str(row["citation_key"]))
            payloads.append(payload)
        return payloads

    def list_entries(self, limit: int = 50) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT citation_key, entry_type, review_status, title, year
            FROM entries
            ORDER BY COALESCE(year, ''), citation_key
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_resolution_candidates(
        self,
        *,
        limit: int = 50,
        doi_only: bool = False,
        stub_only: bool = False,
        misc_only: bool = False,
        topic_slug: str | None = None,
    ) -> list[dict[str, object]]:
        clauses: list[str] = []
        params: list[object] = []
        joins = ""

        if topic_slug is not None:
            joins = """
            JOIN entry_topics et ON et.entry_id = e.id
            JOIN topics t ON t.id = et.topic_id
            """
            clauses.append("t.slug = ?")
            params.append(topic_slug)

        if doi_only:
            clauses.append("e.doi IS NOT NULL AND TRIM(e.doi) <> ''")

        if misc_only:
            clauses.append("e.entry_type = 'misc'")

        if stub_only:
            clauses.append(
                """
                (
                    e.title IS NULL
                    OR TRIM(e.title) = ''
                    OR LOWER(TRIM(e.title)) GLOB 'referenced work *'
                    OR LOWER(TRIM(e.title)) GLOB 'untitled*'
                    OR (
                        e.entry_type = 'misc'
                        AND (
                            e.abstract IS NULL
                            OR TRIM(e.abstract) = ''
                        )
                    )
                )
                """
            )

        where_clause = ""
        if clauses:
            where_clause = "WHERE " + " AND ".join(clauses)

        rows = self.connection.execute(
            f"""
            SELECT DISTINCT
                e.citation_key,
                e.entry_type,
                e.review_status,
                e.title,
                e.year,
                e.doi,
                e.abstract
            FROM entries e
            {joins}
            {where_clause}
            ORDER BY COALESCE(e.year, ''), e.citation_key
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def ensure_topic(
        self,
        slug: str,
        name: str,
        source_type: str = "manual",
        source_url: str | None = None,
        expansion_phrase: str | None = None,
        suggested_phrase: str | None = None,
        phrase_review_status: str | None = None,
        phrase_review_notes: str | None = None,
    ) -> int:
        row = self.connection.execute(
            """
            INSERT INTO topics (
                slug, name, source_type, source_url, expansion_phrase,
                suggested_phrase, phrase_review_status, phrase_review_notes
            )
            VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, 'unreviewed'), ?)
            ON CONFLICT(slug) DO UPDATE SET
                name = excluded.name,
                source_type = excluded.source_type,
                source_url = COALESCE(excluded.source_url, topics.source_url),
                expansion_phrase = COALESCE(excluded.expansion_phrase, topics.expansion_phrase),
                suggested_phrase = COALESCE(excluded.suggested_phrase, topics.suggested_phrase),
                phrase_review_status = COALESCE(excluded.phrase_review_status, topics.phrase_review_status),
                phrase_review_notes = COALESCE(excluded.phrase_review_notes, topics.phrase_review_notes),
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (
                slug,
                name,
                source_type,
                source_url,
                expansion_phrase,
                suggested_phrase,
                phrase_review_status,
                phrase_review_notes,
            ),
        ).fetchone()
        return int(row["id"])

    def add_entry_topic(
        self,
        citation_key: str,
        topic_slug: str,
        topic_name: str,
        source_type: str = "manual",
        source_url: str | None = None,
        source_label: str = "manual",
        confidence: float = 1.0,
        expansion_phrase: str | None = None,
    ) -> bool:
        entry_row = self.connection.execute(
            "SELECT id FROM entries WHERE citation_key = ?",
            (citation_key,),
        ).fetchone()
        if entry_row is None:
            return False

        topic_id = self.ensure_topic(
            topic_slug,
            topic_name,
            source_type=source_type,
            source_url=source_url,
            expansion_phrase=expansion_phrase,
        )
        self.connection.execute(
            """
            INSERT INTO entry_topics (entry_id, topic_id, source_label, confidence)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(entry_id, topic_id) DO UPDATE SET
                source_label = excluded.source_label,
                confidence = excluded.confidence
            """,
            (int(entry_row["id"]), topic_id, source_label, confidence),
        )
        return True

    def get_entry_topics(self, citation_key: str) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT t.slug, t.name, t.source_type, t.source_url, et.source_label, et.confidence
            FROM entry_topics et
            JOIN entries e ON e.id = et.entry_id
            JOIN topics t ON t.id = et.topic_id
            WHERE e.citation_key = ?
            ORDER BY t.name, t.slug
            """,
            (citation_key,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_topics(
        self,
        limit: int = 100,
        phrase_review_status: str | None = None,
    ) -> list[dict[str, object]]:
        where = ""
        params: list[object] = []
        if phrase_review_status is not None:
            where = "WHERE t.phrase_review_status = ?"
            params.append(phrase_review_status)
        params.append(limit)
        rows = self.connection.execute(
            f"""
            SELECT t.slug, t.name, t.source_type, t.source_url, t.expansion_phrase,
                   t.suggested_phrase, t.phrase_review_status, t.phrase_review_notes,
                   COUNT(et.entry_id) AS entry_count
            FROM topics t
            LEFT JOIN entry_topics et ON et.topic_id = t.id
            {where}
            GROUP BY t.id, t.slug, t.name, t.source_type, t.source_url, t.expansion_phrase,
                     t.suggested_phrase, t.phrase_review_status, t.phrase_review_notes
            ORDER BY t.name, t.slug
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def get_topic(self, slug: str) -> dict[str, object] | None:
        row = self.connection.execute(
            """
            SELECT t.slug, t.name, t.source_type, t.source_url, t.expansion_phrase,
                   t.suggested_phrase, t.phrase_review_status, t.phrase_review_notes,
                   COUNT(et.entry_id) AS entry_count
            FROM topics t
            LEFT JOIN entry_topics et ON et.topic_id = t.id
            WHERE t.slug = ?
            GROUP BY t.id, t.slug, t.name, t.source_type, t.source_url, t.expansion_phrase,
                     t.suggested_phrase, t.phrase_review_status, t.phrase_review_notes
            """,
            (slug,),
        ).fetchone()
        return dict(row) if row else None

    def list_topic_phrase_reviews(
        self,
        limit: int = 100,
        phrase_review_status: str | None = None,
    ) -> list[dict[str, object]]:
        where = "WHERE t.suggested_phrase IS NOT NULL"
        params: list[object] = []
        if phrase_review_status is not None:
            where += " AND t.phrase_review_status = ?"
            params.append(phrase_review_status)
        params.append(limit)
        rows = self.connection.execute(
            f"""
            SELECT t.slug, t.name, t.expansion_phrase, t.suggested_phrase,
                   t.phrase_review_status, t.phrase_review_notes,
                   COUNT(et.entry_id) AS entry_count
            FROM topics t
            LEFT JOIN entry_topics et ON et.topic_id = t.id
            {where}
            GROUP BY t.id, t.slug, t.name, t.expansion_phrase, t.suggested_phrase,
                     t.phrase_review_status, t.phrase_review_notes
            ORDER BY
                CASE t.phrase_review_status
                    WHEN 'pending' THEN 0
                    WHEN 'unreviewed' THEN 1
                    WHEN 'rejected' THEN 2
                    WHEN 'accepted' THEN 3
                    ELSE 4
                END,
                t.name,
                t.slug
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def set_topic_expansion_phrase(self, slug: str, expansion_phrase: str | None) -> bool:
        row = self.connection.execute(
            """
            UPDATE topics
            SET expansion_phrase = ?, updated_at = CURRENT_TIMESTAMP
            WHERE slug = ?
            RETURNING id
            """,
            (expansion_phrase, slug),
        ).fetchone()
        self.connection.commit()
        return row is not None

    def stage_topic_phrase_suggestion(
        self,
        slug: str,
        suggested_phrase: str | None,
        review_status: str = "pending",
        review_notes: str | None = None,
    ) -> bool:
        row = self.connection.execute(
            """
            UPDATE topics
            SET suggested_phrase = ?,
                phrase_review_status = ?,
                phrase_review_notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE slug = ?
            RETURNING id
            """,
            (suggested_phrase, review_status, review_notes, slug),
        ).fetchone()
        self.connection.commit()
        return row is not None

    def review_topic_phrase_suggestion(
        self,
        slug: str,
        review_status: str,
        review_notes: str | None = None,
        applied_phrase: str | None = None,
    ) -> bool:
        topic = self.get_topic(slug)
        if topic is None:
            return False

        suggested_phrase = topic.get("suggested_phrase")
        expansion_phrase = topic.get("expansion_phrase")
        stored_suggested_phrase = suggested_phrase
        if review_status == "accepted":
            expansion_phrase = applied_phrase if applied_phrase is not None else suggested_phrase
            stored_suggested_phrase = None
        elif applied_phrase is not None:
            expansion_phrase = applied_phrase

        row = self.connection.execute(
            """
            UPDATE topics
            SET expansion_phrase = ?,
                suggested_phrase = ?,
                phrase_review_status = ?,
                phrase_review_notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE slug = ?
            RETURNING id
            """,
            (expansion_phrase, stored_suggested_phrase, review_status, review_notes, slug),
        ).fetchone()
        self.connection.commit()
        return row is not None

    def list_topic_entries(self, topic_slug: str, limit: int = 100) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT e.citation_key, e.entry_type, e.review_status, e.title, e.year,
                   t.slug AS topic_slug, t.name AS topic_name, et.source_label, et.confidence
            FROM entry_topics et
            JOIN topics t ON t.id = et.topic_id
            JOIN entries e ON e.id = et.entry_id
            WHERE t.slug = ?
            ORDER BY COALESCE(e.year, ''), e.citation_key
            LIMIT ?
            """,
            (topic_slug, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def set_entry_status(self, citation_key: str, review_status: str) -> bool:
        row = self.connection.execute(
            """
            UPDATE entries
            SET review_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE citation_key = ?
            RETURNING id
            """,
            (review_status, citation_key),
        ).fetchone()
        self.connection.commit()
        return row is not None

    def replace_entry(
        self,
        citation_key: str,
        entry: BibEntry,
        source_type: str,
        source_label: str,
        review_status: str = "enriched",
    ) -> bool:
        existing = self.get_entry(citation_key)
        if existing is None:
            return False
        replacement = BibEntry(
            entry_type=entry.entry_type,
            citation_key=citation_key,
            fields=entry.fields,
        )
        self.upsert_entry(
            replacement,
            fulltext=existing.get("fulltext"),
            raw_bibtex=_entry_to_bibtex(replacement),
            source_type=source_type,
            source_label=source_label,
            review_status=review_status,
        )
        self.connection.commit()
        return True

    def record_conflicts(
        self,
        citation_key: str,
        conflicts: list[dict[str, str]],
        source_type: str,
        source_label: str,
    ) -> bool:
        row = self.connection.execute(
            "SELECT id FROM entries WHERE citation_key = ?",
            (citation_key,),
        ).fetchone()
        if row is None:
            return False

        entry_id = int(row["id"])
        for conflict in conflicts:
            self.connection.execute(
                """
                INSERT INTO field_conflicts (
                    entry_id, field_name, current_value, proposed_value, source_type, source_label, status
                ) VALUES (?, ?, ?, ?, ?, ?, 'open')
                """,
                (
                    entry_id,
                    conflict["field_name"],
                    conflict.get("current_value"),
                    conflict.get("proposed_value"),
                    source_type,
                    source_label,
                ),
            )
        self.connection.commit()
        return True

    def get_field_conflicts(self, citation_key: str, status: str | None = None) -> list[dict[str, object]]:
        where = ""
        params: list[object] = [citation_key]
        if status is not None:
            where = " AND fc.status = ?"
            params.append(status)

        rows = self.connection.execute(
            f"""
            SELECT fc.field_name, fc.current_value, fc.proposed_value, fc.source_type,
                   fc.source_label, fc.status, fc.recorded_at
            FROM field_conflicts fc
            JOIN entries e ON e.id = fc.entry_id
            WHERE e.citation_key = ?{where}
            ORDER BY fc.recorded_at, fc.id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def set_conflict_status(self, citation_key: str, field_name: str, status: str) -> int:
        row = self.connection.execute(
            "SELECT id FROM entries WHERE citation_key = ?",
            (citation_key,),
        ).fetchone()
        if row is None:
            return 0
        entry_id = int(row["id"])
        result = self.connection.execute(
            """
            UPDATE field_conflicts
            SET status = ?
            WHERE entry_id = ? AND field_name = ? AND status = 'open'
            """,
            (status, entry_id, field_name),
        )
        self.connection.commit()
        return result.rowcount

    def apply_conflict_value(self, citation_key: str, field_name: str) -> bool:
        row = self.connection.execute(
            """
            SELECT fc.id, fc.proposed_value, e.review_status
            FROM field_conflicts fc
            JOIN entries e ON e.id = fc.entry_id
            WHERE e.citation_key = ? AND fc.field_name = ? AND fc.status = 'open'
            ORDER BY fc.recorded_at DESC, fc.id DESC
            LIMIT 1
            """,
            (citation_key, field_name),
        ).fetchone()
        if row is None:
            return False

        entry = self._load_bib_entry(citation_key)
        if entry is None:
            return False

        proposed_value = str(row["proposed_value"] or "")
        entry.fields[field_name] = proposed_value
        self.upsert_entry(
            entry,
            raw_bibtex=_entry_to_bibtex(entry),
            source_type="manual_review",
            source_label=f"conflict_accept:{field_name}",
            review_status=str(row["review_status"] or "draft"),
        )
        self.connection.execute(
            "UPDATE field_conflicts SET status = 'accepted' WHERE id = ?",
            (int(row["id"]),),
        )
        self.connection.commit()
        return True

    def add_relation(
        self,
        source_citation_key: str,
        target_citation_key: str,
        relation_type: str,
        source_type: str,
        source_label: str,
        confidence: float = 1.0,
    ) -> bool:
        row = self.connection.execute(
            "SELECT id FROM entries WHERE citation_key = ?",
            (source_citation_key,),
        ).fetchone()
        if row is None:
            return False

        source_entry_id = int(row["id"])
        self.connection.execute(
            """
            INSERT OR IGNORE INTO relations (source_entry_id, target_citation_key, relation_type)
            VALUES (?, ?, ?)
            """,
            (source_entry_id, target_citation_key, relation_type),
        )
        self.connection.execute(
            """
            INSERT INTO relation_provenance (
                source_entry_id, target_citation_key, relation_type, source_type, source_label, confidence
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (source_entry_id, target_citation_key, relation_type, source_type, source_label, confidence),
        )
        self.connection.commit()
        return True

    def get_field_provenance(self, citation_key: str) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT fp.field_name, fp.field_value, fp.source_type, fp.source_label,
                   fp.operation, fp.confidence, fp.recorded_at
            FROM field_provenance fp
            JOIN entries e ON e.id = fp.entry_id
            WHERE e.citation_key = ?
            ORDER BY fp.recorded_at, fp.id
            """,
            (citation_key,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_relation_provenance(self, citation_key: str) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT rp.target_citation_key, rp.relation_type, rp.source_type, rp.source_label,
                   rp.confidence, rp.recorded_at
            FROM relation_provenance rp
            JOIN entries e ON e.id = rp.source_entry_id
            WHERE e.citation_key = ?
            ORDER BY rp.recorded_at, rp.id
            """,
            (citation_key,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_entry_bibtex(self, citation_key: str) -> str | None:
        entry = self._load_bib_entry(citation_key)
        if entry is None:
            return None
        return render_bibtex([entry])

    def get_bib_entry(self, citation_key: str) -> BibEntry | None:
        return self._load_bib_entry(citation_key)

    def export_bibtex(self, citation_keys: list[str] | None = None, include_stubs: bool | None = None) -> str:
        return self.export_bibtex_report(citation_keys, include_stubs=include_stubs)["bibtex"]

    def export_bibtex_report(
        self,
        citation_keys: list[str] | None = None,
        include_stubs: bool | None = None,
    ) -> dict[str, object]:
        explicit_keys = citation_keys is not None
        if include_stubs is None:
            include_stubs = explicit_keys
        if citation_keys is None:
            rows = self.connection.execute(
                "SELECT citation_key FROM entries ORDER BY COALESCE(year, ''), citation_key"
            ).fetchall()
            citation_keys = [str(row["citation_key"]) for row in rows]

        entries: list[BibEntry] = []
        for citation_key in citation_keys:
            entry = self._load_bib_entry(citation_key)
            if entry is not None:
                if not include_stubs and self._is_export_stub(entry):
                    continue
                entries.append(entry)
        chunks: list[str] = []
        skipped: list[dict[str, str]] = []
        for entry in entries:
            try:
                rendered = render_bibtex([entry]).strip()
            except Exception as exc:
                skipped.append(
                    {
                        "citation_key": entry.citation_key,
                        "error": str(exc),
                    }
                )
                continue
            if rendered:
                chunks.append(rendered)
        return {
            "bibtex": "\n\n".join(chunks).strip(),
            "requested_count": len(entries),
            "exported_count": len(chunks),
            "skipped": skipped,
        }

    def _detect_fts5(self) -> bool:
        try:
            self.connection.execute("CREATE VIRTUAL TABLE temp.fts_probe USING fts5(content)")
            self.connection.execute("DROP TABLE temp.fts_probe")
            return True
        except sqlite3.OperationalError:
            return False

    def _load_bib_entry(self, citation_key: str) -> BibEntry | None:
        row = self.connection.execute(
            """
            SELECT citation_key, entry_type, title, year, journal, booktitle, publisher,
                   abstract, keywords, url, doi, isbn, extra_fields_json
            FROM entries
            WHERE citation_key = ?
            """,
            (citation_key,),
        ).fetchone()
        if row is None:
            return None

        fields: OrderedDict[str, str] = OrderedDict()
        for role in ("author", "editor"):
            names = self._load_creator_names(citation_key, role)
            if names:
                fields[role] = " and ".join(names)

        for field_name in (
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
        ):
            value = row[field_name]
            if value:
                fields[field_name] = str(value)

        extra_fields = json.loads(row["extra_fields_json"])
        for field_name in sorted(extra_fields):
            if field_name in {"author", "editor"}:
                continue
            value = extra_fields[field_name]
            if value:
                fields[field_name] = str(value)

        for relation_type, field_name in (
            ("cites", "references"),
            ("cited_by", "cited_by"),
            ("crossref", "crossref"),
        ):
            values = self.get_relations(citation_key, relation_type)
            if values:
                fields[field_name] = ", ".join(values)

        return BibEntry(
            entry_type=str(row["entry_type"]),
            citation_key=str(row["citation_key"]),
            fields=dict(fields),
        )

    def _is_export_stub(self, entry: BibEntry) -> bool:
        title = " ".join(entry.fields.get("title", "").split()).strip().lower()
        doi = " ".join(entry.fields.get("doi", "").split()).strip()
        url = " ".join(entry.fields.get("url", "").split()).strip()
        has_author = bool(" ".join(entry.fields.get("author", "").split()).strip())
        has_abstract = bool(" ".join(entry.fields.get("abstract", "").split()).strip())
        has_journal = bool(" ".join(entry.fields.get("journal", "").split()).strip())
        has_booktitle = bool(" ".join(entry.fields.get("booktitle", "").split()).strip())
        if not doi:
            return False
        if title and not (title.startswith("referenced work ") or title.startswith("untitled")):
            return False
        return not any((has_author, has_abstract, has_journal, has_booktitle)) and (
            not url or url.startswith("https://doi.org/")
        )

    def _load_creator_names(self, citation_key: str, role: str) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT c.full_name
            FROM entry_creators ec
            JOIN entries e ON e.id = ec.entry_id
            JOIN creators c ON c.id = ec.creator_id
            WHERE e.citation_key = ? AND ec.role = ?
            ORDER BY ec.ordinal
            """,
            (citation_key, role),
        ).fetchall()
        return [str(row["full_name"]) for row in rows]

    def _row_to_entry_dict(self, row: sqlite3.Row) -> dict[str, object]:
        payload = dict(row)
        extra_fields = json.loads(str(payload.get("extra_fields_json") or "{}"))
        for key, value in extra_fields.items():
            payload.setdefault(key, value)
        return payload

    def _iter_graph_edges(self, citation_key: str, allowed_relations: set[str]) -> list[sqlite3.Row]:
        rows = self.connection.execute(
            """
            SELECT e.citation_key AS source_citation_key, r.target_citation_key, r.relation_type
            FROM relations r
            JOIN entries e ON e.id = r.source_entry_id
            WHERE e.citation_key = ? AND r.relation_type IN ({placeholders})
            ORDER BY r.relation_type, r.target_citation_key
            """.format(placeholders=",".join("?" for _ in allowed_relations)),
            (citation_key, *sorted(allowed_relations)),
        ).fetchall()

        reverse_rows = []
        if "cited_by" in allowed_relations:
            reverse_rows = self.connection.execute(
                """
                SELECT ? AS source_citation_key, e.citation_key AS target_citation_key, 'cited_by' AS relation_type
                FROM relations r
                JOIN entries e ON e.id = r.source_entry_id
                WHERE r.target_citation_key = ? AND r.relation_type = 'cites'
                ORDER BY e.citation_key
                """,
                (citation_key, citation_key),
            ).fetchall()

        seen: set[tuple[str, str]] = set()
        merged: list[sqlite3.Row] = []
        for row in list(rows) + list(reverse_rows):
            key = (str(row["relation_type"]), str(row["target_citation_key"]))
            if key not in seen:
                seen.add(key)
                merged.append(row)
        return merged

    def _ensure_entry_columns(self) -> None:
        columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(entries)").fetchall()
        }
        if "review_status" not in columns:
            self.connection.execute(
                "ALTER TABLE entries ADD COLUMN review_status TEXT NOT NULL DEFAULT 'draft'"
            )

    def _ensure_topic_columns(self) -> None:
        columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(topics)").fetchall()
        }
        if "expansion_phrase" not in columns:
            try:
                self.connection.execute("ALTER TABLE topics ADD COLUMN expansion_phrase TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        if "suggested_phrase" not in columns:
            try:
                self.connection.execute("ALTER TABLE topics ADD COLUMN suggested_phrase TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        if "phrase_review_status" not in columns:
            try:
                self.connection.execute(
                    "ALTER TABLE topics ADD COLUMN phrase_review_status TEXT NOT NULL DEFAULT 'unreviewed'"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        if "phrase_review_notes" not in columns:
            try:
                self.connection.execute("ALTER TABLE topics ADD COLUMN phrase_review_notes TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    def _record_field_provenance(
        self,
        entry_id: int,
        entry: BibEntry,
        source_type: str,
        source_label: str,
        operation: str,
        fulltext: str | None,
    ) -> None:
        field_items = list(entry.fields.items())
        if fulltext:
            field_items.append(("fulltext", fulltext))

        for field_name, field_value in field_items:
            self.connection.execute(
                """
                INSERT INTO field_provenance (
                    entry_id, field_name, field_value, source_type, source_label, operation, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (entry_id, field_name, field_value, source_type, source_label, operation, 1.0),
            )


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
    return render_bibtex([entry])
