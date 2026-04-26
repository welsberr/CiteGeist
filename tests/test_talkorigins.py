from __future__ import annotations

import json
from pathlib import Path

from citegeist.batch import load_batch_jobs
from citegeist.bibtex import BibEntry
from citegeist.examples.talkorigins import TalkOriginsScraper, normalize_topic_entries
from citegeist.storage import BibliographyStore


INDEX_HTML = """
<html><body>
<a href="abiogenesis.html">Abiogenesis</a>
<a href="evolution.html">Evolution</a>
<a href="/origins/faqs.html">Browse</a>
</body></html>
"""

ABIOGENESIS_HTML = """
<html><body><pre>
Smith, J., 1998, First paper title: Journal of Origins, v. 10, p. 1-10.

---, 2001, Second paper title: Journal of Origins, v. 12, p. 20-30.
</pre></body></html>
"""

EVOLUTION_HTML = """
<html><body><pre>
Jones, A., and Roe, B.,
2003, Wrapped title across lines:
Proceedings of the Example Conference, p. 40-55.
</pre></body></html>
"""


class FakeSourceClient:
    def __init__(self, payloads: dict[str, str]) -> None:
        self.payloads = payloads

    def get_text(self, url: str) -> str:
        return self.payloads[url]


def test_normalize_topic_entries_carries_forward_repeated_authors():
    text = """
Smith, J., 1998, First paper title: Journal of Origins.

---, 2001, Second paper title: Journal of Origins.
"""

    entries = normalize_topic_entries(text)

    assert entries[1].startswith("Smith, J., 2001")


def test_talkorigins_scraper_writes_seed_bibs_and_jobs(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)

    assert export.topic_count == 2
    assert export.entry_count == 3

    jobs = json.loads(Path(export.jobs_path).read_text(encoding="utf-8"))
    assert jobs["jobs"][0]["name"] == "talkorigins:abiogenesis"
    assert Path(jobs["jobs"][0]["seed_bib"]).exists()

    manifest = json.loads(Path(export.manifest_path).read_text(encoding="utf-8"))
    assert manifest["seed_sets"][0]["parsed_entry_count"] == 2

    abiogenesis_bib = Path(export.seed_sets[0].seed_bib).read_text(encoding="utf-8")
    abiogenesis_plain = Path(export.seed_sets[0].plaintext_path).read_text(encoding="utf-8")
    abiogenesis_page = Path(export.seed_sets[0].page_path).read_text(encoding="utf-8")
    full_bib = Path(export.full_bib_path).read_text(encoding="utf-8")
    full_plain = Path(export.full_plaintext_path).read_text(encoding="utf-8")
    site_index = Path(export.site_index_path).read_text(encoding="utf-8")
    assert "@article{smith1998first1," in abiogenesis_bib
    assert 'author = "Smith, J"' in abiogenesis_bib
    assert "@article{smith2001second2," in abiogenesis_bib
    assert "Abiogenesis" in abiogenesis_plain
    assert "Show BibTeX" in abiogenesis_page
    assert "toggleBibtex" in abiogenesis_page
    assert "@article{smith1998first1," in full_bib
    assert "Evolution" in full_plain
    assert "Full BibTeX bibliography" in site_index


def test_talkorigins_parser_prefers_book_for_publisher_like_venues():
    scraper = TalkOriginsScraper(source_client=FakeSourceClient({}))

    entry = scraper.parse_reference_entry(
        "Rutten, M. G., 1971, The Origin of Life by Natural Causes: Amsterdam, London, New York, Elsevier.",
        1,
    )

    assert entry is not None
    assert entry.entry_type == "book"
    assert entry.fields["publisher"] == "Amsterdam, London, New York, Elsevier"


def test_talkorigins_parser_promotes_edited_volume_chapter_to_incollection():
    scraper = TalkOriginsScraper(source_client=FakeSourceClient({}))

    entry = scraper.parse_reference_entry(
        "Carpenter, C. R., 1958, Territoriality: A Review of Concepts and Problems, in Roe, A., and Simpson, G. G., eds., Behavior and Evolution: New Haven, Yale University Press, p. 224-250.",
        1,
    )

    assert entry is not None
    assert entry.entry_type == "incollection"
    assert entry.fields["title"] == "Territoriality: A Review of Concepts and Problems"
    assert entry.fields["editor"] == "Roe, A. and Simpson, G. G."
    assert entry.fields["booktitle"] == "Behavior and Evolution"
    assert "Yale University Press" in entry.fields["publisher"]


def test_talkorigins_scraper_resume_uses_saved_snapshot(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    first_export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path, limit_topics=1)
    snapshot_path = Path(first_export.seed_sets[0].snapshot_path)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["raw_entries"][0].startswith("Smith, J.")

    scraper_with_broken_page = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": "<html><body>broken</body></html>",
            }
        )
    )
    resumed_export = scraper_with_broken_page.scrape_to_directory(base_url=base_url, output_dir=tmp_path, limit_topics=1)

    assert resumed_export.entry_count == 2


def test_talkorigins_validation_reports_suspicious_entries(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path, limit_topics=1)
    seed_bib_path = Path(export.seed_sets[0].seed_bib)
    seed_bib_path.write_text(
        """
@article{bad1,
    author = "Example, A",
    year = "1999",
    title = "Bad Venue Classification",
    journal = "Elsevier"
}
""",
        encoding="utf-8",
    )

    report = scraper.validate_export(export.manifest_path)

    assert report.topic_count == 1
    assert report.entry_count == 2
    assert report.suspicious_entry_type_count >= 1
    assert report.suspicious_examples[0]["citation_key"] == "bad1"


def test_talkorigins_validation_does_not_flag_legitimate_incollection(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path, limit_topics=1)
    seed_bib_path = Path(export.seed_sets[0].seed_bib)
    seed_bib_path.write_text(
        """
@incollection{good1,
    author = "Example, A",
    editor = "Editor, E",
    year = "1999",
    title = "Good Chapter",
    booktitle = "Collected Essays",
    publisher = "New Haven, Yale University Press"
}
""",
        encoding="utf-8",
    )

    report = scraper.validate_export(export.manifest_path)

    assert all(item["citation_key"] != "good1" for item in report.suspicious_examples)


def test_talkorigins_validation_reports_duplicate_clusters(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@article{dup1,
    author = "Smith, Jane",
    year = "1999",
    title = "Duplicate Paper",
    journal = "Journal A"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text(
        """
@article{dup2,
    author = "Smith, Jane",
    year = "1999",
    title = "Duplicate Paper",
    journal = "Journal B"
}
""",
        encoding="utf-8",
    )

    report = scraper.validate_export(export.manifest_path)

    assert report.duplicate_cluster_count >= 1
    assert report.duplicate_entry_count >= 2
    assert report.duplicate_examples[0]["items"][0]["citation_key"] in {"dup1", "dup2"}


def test_talkorigins_can_suggest_topic_phrases(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path, limit_topics=1)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@article{bio1,
    author = "Smith, Jane",
    year = "1999",
    title = "Prebiotic chemistry and ribozyme catalysis",
    journal = "Origins"
}

@article{bio2,
    author = "Smith, Jane",
    year = "2001",
    title = "Ribozyme networks in prebiotic chemistry",
    journal = "Origins"
}
""",
        encoding="utf-8",
    )

    suggestions = scraper.suggest_topic_phrases(export.manifest_path)

    assert len(suggestions) == 1
    assert suggestions[0].slug == "abiogenesis"
    assert suggestions[0].suggested_phrase.startswith("Abiogenesis ")
    assert "chemistry" in suggestions[0].keywords
    assert "prebiotic" in suggestions[0].keywords
    assert suggestions[0].review_required is True
    assert "small_topic" in (suggestions[0].review_reasons or [])
    assert "noisy_keywords" not in (suggestions[0].review_reasons or [])


def test_talkorigins_duplicate_inspection_filters_by_topic_and_match(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@article{dup1,
    author = "Smith, Jane",
    year = "1999",
    title = "Duplicate Paper",
    journal = "Journal A"
}

@article{dup2,
    author = "Smith, Jane",
    year = "1999",
    title = "Duplicate Paper",
    journal = "Journal B"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text(
        """
@article{other1,
    author = "Jones, Alex",
    year = "2001",
    title = "Other Topic Paper",
    journal = "Journal C"
}
""",
        encoding="utf-8",
    )

    clusters = scraper.inspect_duplicate_clusters(
        export.manifest_path,
        topic_slug="abiogenesis",
        match="duplicate",
    )

    assert len(clusters) == 1
    assert clusters[0].count == 2
    assert all(item["topic_slug"] == "abiogenesis" for item in clusters[0].items)


def test_talkorigins_duplicate_inspection_can_preview_canonical_choice(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@article{dup1,
    author = "Smith, Jane",
    year = "1999",
    title = "Duplicate Paper",
    journal = "Journal A"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text(
        """
@article{dup2,
    author = "Smith, Jane",
    year = "1999",
    title = "Duplicate Paper",
    journal = "Journal B",
    doi = "10.1000/dup"
}
""",
        encoding="utf-8",
    )

    clusters = scraper.inspect_duplicate_clusters(export.manifest_path, preview_canonical=True)

    assert len(clusters) == 1
    assert clusters[0].canonical is not None
    assert clusters[0].canonical["citation_key"] == "dup2"
    assert clusters[0].canonical["fields"]["doi"] == "10.1000/dup"
    assert clusters[0].canonical["weak_reasons"] == []


def test_talkorigins_duplicate_inspection_can_filter_to_weak_canonicals(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@misc{weak1,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate"
}

@misc{weak2,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate",
    note = "Copied from legacy source"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text(
        """
@article{strong1,
    author = "Jones, Alex",
    year = "2001",
    title = "Strong Duplicate",
    journal = "Journal B",
    doi = "10.1000/strong"
}

@article{strong2,
    author = "Jones, Alex",
    year = "2001",
    title = "Strong Duplicate",
    journal = "Journal B"
}
""",
        encoding="utf-8",
    )

    clusters = scraper.inspect_duplicate_clusters(
        export.manifest_path,
        preview_canonical=True,
        weak_only=True,
    )

    assert len(clusters) == 1
    assert clusters[0].canonical is not None
    assert clusters[0].canonical["citation_key"] == "weak2"
    assert "entry_type:misc" in clusters[0].canonical["weak_reasons"]
    assert "missing:doi" in clusters[0].canonical["weak_reasons"]


def test_talkorigins_enrich_weak_canonicals_can_preview_resolution(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@misc{weak1,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate"
}

@misc{weak2,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate",
    note = "Copied from legacy source"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text("", encoding="utf-8")

    from citegeist.resolve import Resolution

    scraper.resolver.resolve_entry = lambda entry: Resolution(  # type: ignore[method-assign]
        entry=BibEntry(
            entry_type="article",
            citation_key="resolved",
            fields={
                "author": entry.fields["author"],
                "title": entry.fields["title"],
                "year": entry.fields["year"],
                "doi": "10.1000/weak",
                "journal": "Journal of Better Metadata",
            },
        ),
        source_type="resolver",
        source_label="crossref:search:Weak Duplicate",
    )

    store = BibliographyStore()
    try:
        results = scraper.enrich_weak_canonicals(export.manifest_path, store, apply=False)
    finally:
        store.close()

    assert len(results) == 1
    assert results[0].resolved is True
    assert results[0].applied is False
    assert results[0].weak_reasons_after == []


def test_talkorigins_enrich_weak_canonicals_includes_resolution_attempts(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@misc{weak1,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate"
}

@misc{weak2,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate",
    note = "Copied from legacy source"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text("", encoding="utf-8")

    from citegeist.resolve import Resolution, ResolutionAttempt, ResolutionOutcome

    scraper.resolver.resolve_entry_with_trace = lambda entry: ResolutionOutcome(  # type: ignore[method-assign]
        resolution=Resolution(
            entry=BibEntry(
                entry_type="article",
                citation_key="resolved",
                fields={
                    "author": entry.fields["author"],
                    "title": entry.fields["title"],
                    "year": entry.fields["year"],
                    "doi": "10.1000/weak",
                    "journal": "Journal of Better Metadata",
                },
            ),
            source_type="resolver",
            source_label="crossref:search:Weak Duplicate",
        ),
        attempts=[
            ResolutionAttempt(
                source_name="crossref",
                strategy="title_search",
                query_value="Weak Duplicate",
                matched=True,
                candidate_count=1,
                source_label="crossref:search:Weak Duplicate",
            )
        ],
    )

    store = BibliographyStore()
    try:
        results = scraper.enrich_weak_canonicals(export.manifest_path, store, apply=False)
    finally:
        store.close()

    assert len(results) == 1
    assert results[0].resolution_attempts == [
        {
            "source_name": "crossref",
            "strategy": "title_search",
            "query_value": "Weak Duplicate",
            "matched": True,
            "candidate_count": 1,
            "source_label": "crossref:search:Weak Duplicate",
            "error": "",
        }
    ]


def test_talkorigins_enrich_weak_canonicals_can_apply_to_store(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@misc{weak2,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text(
        """
@misc{weak1,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate",
    note = "Copied from legacy source"
}
""",
        encoding="utf-8",
    )

    from citegeist.resolve import Resolution

    scraper.resolver.resolve_entry = lambda entry: Resolution(  # type: ignore[method-assign]
        entry=BibEntry(
            entry_type="article",
            citation_key="resolved",
            fields={
                "author": entry.fields["author"],
                "title": entry.fields["title"],
                "year": entry.fields["year"],
                "doi": "10.1000/weak",
                "journal": "Journal of Better Metadata",
            },
        ),
        source_type="resolver",
        source_label="crossref:search:Weak Duplicate",
    )

    store = BibliographyStore()
    try:
        scraper.ingest_export(export.manifest_path, store, dedupe=False)
        results = scraper.enrich_weak_canonicals(export.manifest_path, store, apply=True)

        assert len(results) == 1
        assert results[0].applied is True
        entry = store.get_entry(results[0].citation_key)
        assert entry is not None
        assert entry["doi"] == "10.1000/weak"
        assert entry["journal"] == "Journal of Better Metadata"
        assert entry["review_status"] == "enriched"
    finally:
        store.close()


def test_talkorigins_enrich_weak_canonicals_rejects_unsafe_search_match(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@misc{weak2,
    author = "Adams, D",
    year = "1987",
    title = "The bigger they are, the harder they fall"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text(
        """
@misc{weak1,
    author = "Adams, D",
    year = "1987",
    title = "The bigger they are, the harder they fall",
    note = "Copied from legacy source"
}
""",
        encoding="utf-8",
    )

    from citegeist.resolve import Resolution

    scraper.resolver.resolve_entry = lambda entry: Resolution(  # type: ignore[method-assign]
        entry=BibEntry(
            entry_type="misc",
            citation_key="resolved",
            fields={
                "author": "Kulik, Dean",
                "title": "The Nexus Recursive Harmonic Framework: Reality as Unbounded, Observerless Computation (SILR / RHA / CST) Ver 2",
                "year": "2026",
                "doi": "10.9999/not-a-match",
            },
        ),
        source_type="resolver",
        source_label="datacite:search:The bigger they are, the harder they fall",
    )

    store = BibliographyStore()
    try:
        scraper.ingest_export(export.manifest_path, store, dedupe=False)
        results = scraper.enrich_weak_canonicals(export.manifest_path, store, apply=True)

        assert len(results) == 1
        assert results[0].resolved is False
        assert results[0].applied is False
        assert results[0].error == "unsafe resolver match"
        entry = store.get_entry("weak2") or store.get_entry("weak1")
        assert entry is not None
        assert entry["doi"] is None
    finally:
        store.close()


def test_talkorigins_enrich_weak_canonicals_can_allow_unsafe_search_match(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@misc{weak2,
    author = "Adams, D",
    year = "1987",
    title = "The bigger they are, the harder they fall"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text(
        """
@misc{weak1,
    author = "Adams, D",
    year = "1987",
    title = "The bigger they are, the harder they fall",
    note = "Copied from legacy source"
}
""",
        encoding="utf-8",
    )

    from citegeist.resolve import Resolution

    scraper.resolver.resolve_entry = lambda entry: Resolution(  # type: ignore[method-assign]
        entry=BibEntry(
            entry_type="misc",
            citation_key="resolved",
            fields={
                "author": "Kulik, Dean",
                "title": "The Nexus Recursive Harmonic Framework: Reality as Unbounded, Observerless Computation (SILR / RHA / CST) Ver 2",
                "year": "2026",
                "doi": "10.9999/not-a-match",
            },
        ),
        source_type="resolver",
        source_label="datacite:search:The bigger they are, the harder they fall",
    )

    store = BibliographyStore()
    try:
        scraper.ingest_export(export.manifest_path, store, dedupe=False)
        results = scraper.enrich_weak_canonicals(
            export.manifest_path,
            store,
            apply=True,
            allow_unsafe_matches=True,
        )

        assert len(results) == 1
        assert results[0].resolved is True
        assert results[0].applied is True
        entry = store.get_entry(results[0].citation_key)
        assert entry is not None
        assert entry["doi"] == "10.9999/not-a-match"
    finally:
        store.close()


def test_talkorigins_build_review_export_combines_cluster_and_enrichment(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@misc{weak1,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate"
}

@misc{weak2,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate",
    note = "Copied from legacy source"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text("", encoding="utf-8")

    from citegeist.resolve import Resolution

    scraper.resolver.resolve_entry = lambda entry: Resolution(  # type: ignore[method-assign]
        entry=BibEntry(
            entry_type="article",
            citation_key="resolved",
            fields={
                "author": entry.fields["author"],
                "title": entry.fields["title"],
                "year": entry.fields["year"],
                "doi": "10.1000/weak",
                "journal": "Journal of Better Metadata",
            },
        ),
        source_type="resolver",
        source_label="crossref:search:Weak Duplicate",
    )

    store = BibliographyStore()
    try:
        review = scraper.build_review_export(export.manifest_path, store)
    finally:
        store.close()

    assert review.item_count == 1
    assert review.items[0]["canonical"]["citation_key"] == "weak2"
    assert review.items[0]["enrichment"]["resolved"] is True
    assert review.items[0]["enrichment"]["applied"] is False
    assert review.items[0]["enrichment"]["resolution_attempts"] == []


def test_talkorigins_apply_review_corrections_updates_store_entry(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@misc{weak1,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate"
}

@misc{weak2,
    author = "Smith, Jane",
    year = "1999",
    title = "Weak Duplicate",
    note = "Copied from legacy source"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text("", encoding="utf-8")

    corrections_path = tmp_path / "corrections.json"
    corrections_path.write_text(
        json.dumps(
            {
                "corrections": [
                    {
                        "key": "smith jane|1999|weak duplicate",
                        "entry_type": "article",
                        "review_status": "reviewed",
                        "fields": {
                            "journal": "Journal of Better Metadata",
                            "doi": "10.1000/weak",
                            "note": None,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    store = BibliographyStore()
    try:
        scraper.ingest_export(export.manifest_path, store, dedupe=True)
        results = scraper.apply_review_corrections(export.manifest_path, corrections_path, store)

        assert len(results) == 1
        assert results[0].applied is True
        entry = store.get_entry(results[0].citation_key)
        assert entry is not None
        assert entry["entry_type"] == "article"
        assert entry["journal"] == "Journal of Better Metadata"
        assert entry["doi"] == "10.1000/weak"
        assert entry["review_status"] == "reviewed"
        assert entry.get("note") is None
    finally:
        store.close()


def test_talkorigins_scraper_assigns_topics_when_ingesting(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
            }
        )
    )

    store = BibliographyStore()
    try:
        export = scraper.scrape_to_directory(
            base_url=base_url,
            output_dir=tmp_path,
            limit_topics=1,
            ingest_store=store,
        )

        assert export.entry_count == 2
        entry = store.get_entry("smith1998first1")
        assert entry is not None
        assert entry["topics"][0]["slug"] == "abiogenesis"
        assert entry["topics"][0]["name"] == "Abiogenesis"
        assert store.list_topics()[0]["slug"] == "abiogenesis"
    finally:
        store.close()


def test_talkorigins_ingest_export_consolidates_duplicates_into_one_entry(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@article{dup1,
    author = "Smith, Jane",
    year = "1999",
    title = "Duplicate Paper",
    journal = "Journal A"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text(
        """
@article{dup2,
    author = "Smith, Jane",
    year = "1999",
    title = "Duplicate Paper",
    journal = "Journal B",
    doi = "10.1000/dup"
}
""",
        encoding="utf-8",
    )

    store = BibliographyStore()
    try:
        report = scraper.ingest_export(export.manifest_path, store)

        assert report.duplicate_cluster_count >= 1
        assert report.stored_entry_count == 1
        assert report.canonicalized_count >= 1
        entry = store.get_entry("dup2")
        assert entry is not None
        assert entry["doi"] == "10.1000/dup"
        assert [topic["slug"] for topic in entry["topics"]] == ["abiogenesis", "evolution"]
    finally:
        store.close()


def test_talkorigins_ingest_export_avoids_canonical_key_collisions(tmp_path: Path):
    base_url = "https://www.talkorigins.org/origins/biblio/"
    scraper = TalkOriginsScraper(
        source_client=FakeSourceClient(
            {
                base_url: INDEX_HTML,
                f"{base_url}abiogenesis.html": ABIOGENESIS_HTML,
                f"{base_url}evolution.html": EVOLUTION_HTML,
            }
        )
    )

    export = scraper.scrape_to_directory(base_url=base_url, output_dir=tmp_path)
    Path(export.seed_sets[0].seed_bib).write_text(
        """
@article{sharedkey,
    author = "Smith, Jane",
    year = "1999",
    title = "First Paper",
    journal = "Journal A"
}
""",
        encoding="utf-8",
    )
    Path(export.seed_sets[1].seed_bib).write_text(
        """
@article{sharedkey,
    author = "Jones, Alex",
    year = "2001",
    title = "Second Paper",
    journal = "Journal B"
}
""",
        encoding="utf-8",
    )

    store = BibliographyStore()
    try:
        report = scraper.ingest_export(export.manifest_path, store)

        assert report.stored_entry_count == 2
        entries = store.list_entries(limit=10)
        assert len(entries) == 2
        assert len({entry["citation_key"] for entry in entries}) == 2
    finally:
        store.close()


def test_load_batch_jobs_resolves_relative_seed_paths(tmp_path: Path):
    seed_bib = tmp_path / "seeds" / "topic.bib"
    seed_bib.parent.mkdir(parents=True)
    seed_bib.write_text("", encoding="utf-8")

    jobs_json = tmp_path / "jobs.json"
    jobs_json.write_text(
        """
{
  "jobs": [
    {"name": "relative-job", "seed_bib": "seeds/topic.bib", "topic": "Abiogenesis"}
  ]
}
""",
        encoding="utf-8",
    )

    jobs = load_batch_jobs(jobs_json)

    assert jobs[0]["seed_bib"] == str(seed_bib.resolve())
