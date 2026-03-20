# CLI Examples

This guide gives example invocations for the `citegeist` CLI, including the major option combinations for each command.

Where a topic is named, this guide uses:

- topic phrase: `artificial life`
- topic slug: `artificial-life`
- topic name: `Artificial life`

Assume:

```bash
cd citegeist
export PYTHONPATH=src
```

## Global Option

Use a non-default database path:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 topics
```

## Ingest

Basic ingest:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 ingest references.bib
```

Set initial review status:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 ingest references.bib --status reviewed
```

Set a provenance label:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 ingest references.bib --source-label "examples/artificial-life/references.bib"
```

Use both ingest options together:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 ingest references.bib --status draft --source-label "manual-import:artificial-life"
```

## Search

Basic search:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 search "artificial life"
```

Limit the number of matches:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 search "artificial life" --limit 5
```

Restrict search to one topic slice:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 search "artificial life" --topic artificial-life
```

## Show

Show one entry:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 show langton1989artificial1
```

List entries:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 show --limit 10
```

Include provenance:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 show langton1989artificial1 --provenance
```

Include conflicts:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 show langton1989artificial1 --conflicts
```

Use both:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 show langton1989artificial1 --provenance --conflicts
```

## Export

Export the whole library:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 export
```

Export selected citation keys:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 export langton1989artificial1 bedau2003artificial2
```

Write BibTeX to a file:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 export --output artificial-life.bib
```

## Entry Review

Set review status:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 set-status langton1989artificial1 reviewed
```

Resolve field conflicts:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 resolve-conflicts langton1989artificial1 title accepted
```

Reject a conflict instead:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 resolve-conflicts langton1989artificial1 title rejected
```

Apply the latest proposed conflict value:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 apply-conflict langton1989artificial1 title
```

## Extract

Extract draft BibTeX from plaintext:

```bash
.venv/bin/python -m citegeist extract references.txt
```

Write extracted BibTeX to a file:

```bash
.venv/bin/python -m citegeist extract references.txt --output extracted-artificial-life.bib
```

## Resolve

Resolve one or more entries against remote metadata:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 resolve langton1989artificial1 bedau2003artificial2
```

## Graph Traversal

Basic traversal:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 graph langton1989artificial1
```

Use multiple relation filters:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 graph langton1989artificial1 --relation cites --relation cited_by
```

Set traversal depth:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 graph langton1989artificial1 --depth 2
```

Filter by target review status:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 graph langton1989artificial1 --review-status reviewed
```

Show only unresolved targets:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 graph langton1989artificial1 --missing-only
```

Render DOT instead of traversal rows:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 graph langton1989artificial1 --format dot
```

Render node/edge JSON for visualization:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 graph langton1989artificial1 --format json-graph
```

Write graph output to a file:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 graph langton1989artificial1 --depth 2 --format dot --output artificial-life.dot
```

## Graph Viewer

Render a standalone HTML page from a `json-graph` export:

```bash
.venv/bin/python -m citegeist graph-view artificial-life.json --output artificial-life.html
```

Set the HTML page title:

```bash
.venv/bin/python -m citegeist graph-view artificial-life.json --output artificial-life.html --title "Artificial Life Graph"
```

## Graph Expansion

Expand from one or more seed entries:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 expand langton1989artificial1
```

Choose the source:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 expand langton1989artificial1 --source openalex
```

Choose relation direction:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 expand langton1989artificial1 --source openalex --relation cited_by
```

Limit discoveries per seed:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 expand langton1989artificial1 --source openalex --limit 10
```

## Topic Expansion

Basic topic expansion from stored topic metadata:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 expand-topic artificial-life
```

Override the topic phrase:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 expand-topic artificial-life --topic-phrase "artificial life alife artificial organisms"
```

Choose source and relation:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 expand-topic artificial-life --source openalex --relation cited_by
```

Control seed and discovery limits:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 expand-topic artificial-life --seed-limit 10 --per-seed-limit 5
```

Restrict to trusted seed entries:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 expand-topic artificial-life --seed-key langton1989artificial1 --seed-key bedau2003artificial2
```

Raise or lower the topic assignment threshold:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 expand-topic artificial-life --min-relevance 0.3
```

Preview without writing:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 expand-topic artificial-life --preview
```

## Topic Phrase Storage

Set a stored topic phrase:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 set-topic-phrase artificial-life "artificial life alife artificial organisms complex systems evolution simulation"
```

Clear a stored topic phrase:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 set-topic-phrase artificial-life --clear
```

## OAI-PMH Harvesting

Inspect a repository:

```bash
.venv/bin/python -m citegeist discover-oai https://example.edu/oai
```

Harvest with default metadata prefix:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 harvest-oai https://example.edu/oai
```

Use an alternate metadata prefix:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 harvest-oai https://example.edu/oai --metadata-prefix mods
```

Restrict to a set:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 harvest-oai https://example.edu/oai --set artificial-life
```

Harvest a date range:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 harvest-oai https://example.edu/oai --from 2024-01-01 --until 2024-12-31
```

Limit harvested records and set review status:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 harvest-oai https://example.edu/oai --limit 10 --status draft
```

## Bootstrap

Seed from a BibTeX file:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 bootstrap --seed-bib artificial-life.bib
```

Seed from a topic phrase alone:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 bootstrap --topic "artificial life"
```

Use both a seed `.bib` and a topic phrase:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 bootstrap --seed-bib artificial-life.bib --topic "artificial life"
```

Store topic metadata while bootstrapping:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 \
  bootstrap \
  --topic "artificial life" \
  --topic-slug artificial-life \
  --topic-name "Artificial life" \
  --store-topic-phrase "artificial life alife artificial organisms complex systems evolution simulation"
```

Control topic-search candidate count:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 bootstrap --topic "artificial life" --topic-limit 10
```

Control how many topic candidates are actually committed:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 bootstrap --topic "artificial life" --topic-commit-limit 5
```

Disable immediate expansion:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 bootstrap --topic "artificial life" --no-expand
```

Preview without writing:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 bootstrap --topic "artificial life" --preview
```

Set review status for imported entries:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 bootstrap --topic "artificial life" --status reviewed
```

## Batch Bootstrap

Run a JSON batch file:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 bootstrap-batch artificial-life.json
```

## Topic Phrase Review Workflow

Apply topic phrases directly:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 apply-topic-phrases topic-phrases.json
```

Stage topic phrase suggestions:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 stage-topic-phrases topic-phrases.json
```

Review one staged phrase:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 review-topic-phrase artificial-life accepted
```

Add notes while reviewing:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 review-topic-phrase artificial-life accepted --notes "good fit for topic expansion"
```

Override the accepted phrase while reviewing:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 review-topic-phrase artificial-life accepted --phrase "artificial life alife artificial organisms autonomous agents"
```

Apply review decisions in bulk:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 review-topic-phrases topic-phrase-review.json
```

List staged phrase reviews:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 topic-phrase-reviews
```

Filter review rows by status:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 topic-phrase-reviews --phrase-review-status pending
```

Export an editable review template:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 export-topic-phrase-reviews
```

Limit exported review rows:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 export-topic-phrase-reviews --limit 10
```

Filter exported rows by status:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 export-topic-phrase-reviews --phrase-review-status rejected
```

Write the review template to a file:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 export-topic-phrase-reviews --output topic-phrase-review.json
```

## Topic Inspection

List topics:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 topics
```

Limit topic rows:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 topics --limit 20
```

Filter topics by phrase review status:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 topics --phrase-review-status pending
```

List entries for a topic:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 topic-entries artificial-life
```

Limit topic entries:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 topic-entries artificial-life --limit 25
```

Export one topic slice as BibTeX:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 export-topic artificial-life
```

Write the topic slice to a file:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 export-topic artificial-life --output artificial-life-topic.bib
```

## TalkOrigins Example Commands

Scrape the example corpus:

```bash
.venv/bin/python -m citegeist example-talkorigins-scrape talkorigins-out
```

Override the source URL:

```bash
.venv/bin/python -m citegeist example-talkorigins-scrape talkorigins-out --base-url https://www.talkorigins.org/origins/biblio/
```

Limit topics and entries:

```bash
.venv/bin/python -m citegeist example-talkorigins-scrape talkorigins-out --limit-topics 5 --limit-entries-per-topic 20
```

Resolve seeds, ingest immediately, and keep expansion disabled:

```bash
.venv/bin/python -m citegeist --db library.sqlite3 example-talkorigins-scrape talkorigins-out --resolve-seeds --ingest --no-expand
```

Disable snapshot reuse:

```bash
.venv/bin/python -m citegeist example-talkorigins-scrape talkorigins-out --no-resume
```

Control generated bootstrap defaults:

```bash
.venv/bin/python -m citegeist example-talkorigins-scrape talkorigins-out --topic-limit 10 --topic-commit-limit 5 --status draft
```

Validate the generated manifest:

```bash
.venv/bin/python -m citegeist example-talkorigins-validate talkorigins-out/talkorigins_manifest.json
```

Suggest phrases from the corpus:

```bash
.venv/bin/python -m citegeist example-talkorigins-suggest-phrases talkorigins-out/talkorigins_manifest.json --topic abiogenesis --limit 10 --output topic-phrases.json
```

Inspect duplicate clusters:

```bash
.venv/bin/python -m citegeist example-talkorigins-duplicates talkorigins-out/talkorigins_manifest.json --limit 20 --min-count 2 --match origin --topic abiogenesis --preview --weak-only
```

Ingest the reconstructed corpus:

```bash
.venv/bin/python -m citegeist --db talkorigins.sqlite3 example-talkorigins-ingest talkorigins-out/talkorigins_manifest.json --status draft
```

Disable deduplication during example ingest:

```bash
.venv/bin/python -m citegeist --db talkorigins.sqlite3 example-talkorigins-ingest talkorigins-out/talkorigins_manifest.json --no-dedupe
```

Enrich weak canonical entries:

```bash
.venv/bin/python -m citegeist --db talkorigins.sqlite3 example-talkorigins-enrich talkorigins-out/talkorigins_manifest.json --limit 20 --min-count 2 --match origin --topic abiogenesis --status enriched
```

Apply enrichment and allow unsafe search matches for experiments:

```bash
.venv/bin/python -m citegeist --db talkorigins-copy.sqlite3 example-talkorigins-enrich talkorigins-out/talkorigins_manifest.json --apply --allow-unsafe-search-matches
```

Export a review artifact:

```bash
.venv/bin/python -m citegeist --db talkorigins.sqlite3 example-talkorigins-review talkorigins-out/talkorigins_manifest.json --limit 20 --min-count 2 --match origin --topic abiogenesis --output talkorigins-review.json
```

Apply curated corrections:

```bash
.venv/bin/python -m citegeist --db talkorigins.sqlite3 example-talkorigins-apply-corrections talkorigins-out/talkorigins_manifest.json talkorigins-corrections.json --status reviewed
```

## Notes

- Some commands depend on live source access.
- For topic-oriented examples, use preview mode before committing changes when possible.
- The older TalkOrigins alias commands remain available, but the example-prefixed names are the preferred surface.
