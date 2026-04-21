# TalkOrigins Example

This example shows how to use `citegeist` on a large legacy plaintext bibliography corpus.

It is intentionally positioned as an application of the core library, not as the main product surface.

## What It Demonstrates

- scraping a legacy bibliography index;
- normalizing repeated-author plaintext references;
- converting topic pages into per-topic seed BibTeX;
- generating batch bootstrap specs for downstream ingest and expansion;
- reconstructing cleaned plaintext and BibTeX topic pages for review;
- validating parse quality, duplicate clusters, and weak canonical entries;
- curating topic phrases and correction files before broader enrichment.

The example implementation lives under the Python namespace:

```python
from citegeist.examples.talkorigins import TalkOriginsScraper
```

The preferred CLI commands are example-scoped:

```bash
PYTHONPATH=src .venv/bin/python -m citegeist example-talkorigins-scrape talkorigins-out --limit-topics 5 --limit-entries-per-topic 20
PYTHONPATH=src .venv/bin/python -m citegeist --db talkorigins.sqlite3 bootstrap-batch talkorigins-out/talkorigins_jobs.json | tee talkorigins-bootstrap-results.json
PYTHONPATH=src .venv/bin/python -m citegeist example-talkorigins-validate talkorigins-out/talkorigins_manifest.json
PYTHONPATH=src .venv/bin/python -m citegeist example-talkorigins-duplicates talkorigins-out/talkorigins_manifest.json --limit 20 --preview --weak-only | tee talkorigins-duplicates-preview.json
PYTHONPATH=src .venv/bin/python -m citegeist example-talkorigins-suggest-phrases talkorigins-out/talkorigins_manifest.json --output topic-phrases.json
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 stage-topic-phrases topic-phrases.json
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 export-topic-phrase-reviews --output topic-phrase-review.json
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 review-topic-phrases topic-phrase-review.json
PYTHONPATH=src .venv/bin/python -m citegeist --db talkorigins.sqlite3 example-talkorigins-enrich talkorigins-out/talkorigins_manifest.json --limit 20
PYTHONPATH=src .venv/bin/python -m citegeist --db talkorigins.sqlite3 example-talkorigins-review talkorigins-out/talkorigins_manifest.json --output talkorigins-review.json
PYTHONPATH=src .venv/bin/python -m citegeist --db talkorigins.sqlite3 example-talkorigins-apply-corrections talkorigins-out/talkorigins_manifest.json talkorigins-corrections.json
PYTHONPATH=src .venv/bin/python -m citegeist --db talkorigins.sqlite3 example-talkorigins-ingest talkorigins-out/talkorigins_manifest.json
```

## Output Artifacts

The example scrape writes:

- `seeds/*.bib` per-topic seed BibTeX files;
- `plaintext/*.txt` cleaned GSA-style plaintext with repeated authors expanded;
- `site/topics/*.html` reconstructed topic pages with hide/show BibTeX blocks;
- `talkorigins_full.txt` and `talkorigins_full.bib` aggregate downloads;
- `snapshots/*.json` cached topic payloads so reruns can resume.

## Notes

- Long-running commands print progress to `stderr`, so JSON or tabular results on `stdout` can be safely captured with `tee` into named files such as `talkorigins-bootstrap-results.json`.
- The example-specific CLI names have compatibility aliases matching the older `scrape-talkorigins` style commands.
- Topic phrase staging, review, and export commands are generic `citegeist` functionality and are not specific to TalkOrigins.
