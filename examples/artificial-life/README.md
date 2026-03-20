# Artificial Life Topic-Seeding Example

This example shows the smallest useful `citegeist` workflow that starts from a topic phrase alone.

The seed phrase is:

```text
artificial life
```

## What It Demonstrates

- topic-only bootstrap without a seed `.bib`;
- previewing ranked candidate seed entries before writing anything;
- storing a curated topic slug, topic name, and expansion phrase in the database;
- running later topic-aware expansion from that stored phrase.

## Preview First

Use a preview run to inspect the best candidate seed entries without changing the database:

```bash
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 \
  bootstrap \
  --topic "artificial life" \
  --topic-slug artificial-life \
  --topic-name "Artificial life" \
  --store-topic-phrase "artificial life alife artificial organisms complex systems evolution simulation" \
  --topic-limit 10 \
  --topic-commit-limit 5 \
  --preview
```

That returns ranked candidates gathered through the configured resolver/search stack.

## Commit The Topic Seeds

Once the preview looks reasonable, run the same bootstrap without `--preview`:

```bash
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 \
  bootstrap \
  --topic "artificial life" \
  --topic-slug artificial-life \
  --topic-name "Artificial life" \
  --store-topic-phrase "artificial life alife artificial organisms complex systems evolution simulation" \
  --topic-limit 10 \
  --topic-commit-limit 5
```

That does three things:

1. finds topic-relevant seed entries;
2. stores them in the bibliography database;
3. creates or updates the `artificial-life` topic row with the curated expansion phrase.

## Inspect The Result

```bash
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 topics
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 topic-entries artificial-life
```

If you want to adjust the stored phrase later:

```bash
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 \
  set-topic-phrase artificial-life "artificial life alife artificial organisms autonomous agents evolution simulation"
```

## Optional Batch Form

The same topic-only seed can be expressed as a batch job:

```json
[
  {
    "name": "artificial-life-topic-seed",
    "topic": "artificial life",
    "topic_slug": "artificial-life",
    "topic_name": "Artificial life",
    "topic_phrase": "artificial life alife artificial organisms complex systems evolution simulation",
    "topic_limit": 10,
    "topic_commit_limit": 5,
    "expand": false
  }
]
```

Run it with:

```bash
PYTHONPATH=src .venv/bin/python -m citegeist --db library.sqlite3 bootstrap-batch artificial-life.json
```

## Notes

- This example is intentionally generic and corpus-independent.
- The exact candidate set depends on live source availability and resolver behavior.
- Prefer preview mode before committing topic-only seeds, because topic phrases are noisier than curated seed `.bib` inputs.
