# Literature Explorer Demo

This example describes a thin UI-facing API layer for a browser-based `literature explorer` demo.

The intended split is:

- Python owns SQLite, BibTeX parsing, resolver calls, topic bootstrap, topic expansion, and provenance-aware storage.
- A small app-facing adapter returns stable JSON payloads.
- A browser-side JavaScript object calls that adapter and renders HTML5/CSS views.

The Python-side adapter now exists as:

```python
from citegeist import BibliographyStore, LiteratureExplorerApi

store = BibliographyStore("library.sqlite3")
api = LiteratureExplorerApi(store)
```

The lightest runnable bridge is now the bundled standard-library HTTP server:

```bash
PYTHONPATH=src .venv/bin/python -m citegeist.app_server --db library.sqlite3 --host 127.0.0.1 --port 8765
```

or, after installation:

```bash
citegeist-explorer-server --db library.sqlite3 --host 127.0.0.1 --port 8765
```

## UI-Facing Operations

The adapter exposes JSON-serializable methods suitable for a local web bridge:

- `capabilities()`
- `search(query, limit=20, topic_slug=None)`
- `show_entry(citation_key, include_provenance=False, include_conflicts=False, include_bibtex=False)`
- `list_topics(limit=100, phrase_review_status=None)`
- `get_topic(topic_slug, entry_limit=100)`
- `bootstrap(...)`
- `expand_topic(...)`
- `extract_text(text, backend="heuristic")`
- `verify_strings(values, context="", limit=5)`
- `verify_bibtex(bibtex_text, context="", limit=5)`
- `graph(seed_keys, relation_types=None, depth=1, review_status=None, missing_only=False)`

The `capabilities()` payload also distinguishes between broader metadata/search sources and narrower graph-expansion sources:

- metadata and topic seeding currently use `crossref`, `datacite`, `openalex`, and `pubmed`
- topic graph expansion currently uses `crossref` and `openalex`

## Browser Contract

A demo app can expose a browser object like:

```js
window.citegeist = {
  search(query, opts) {},
  showEntry(citationKey, opts) {},
  listTopics(opts) {},
  getTopic(topicSlug, opts) {},
  bootstrap(opts) {},
  expandTopic(topicSlug, opts) {},
  extractText(text, opts) {},
  verifyStrings(values, opts) {},
  verifyBibtex(bibtexText, opts) {},
  graph(seedKeys, opts) {}
}
```

The bundled JS helper now supports a minimal fetch bridge:

```js
import {
  createHttpBridge,
  createLiteratureExplorerClient,
} from "./literature-explorer.js";

const bridge = createHttpBridge("http://127.0.0.1:8765");
const citegeist = createLiteratureExplorerClient(bridge);
```

That browser object can be backed by:

- a local HTTP bridge;
- an Electron/Tauri preload bridge;
- Pyodide-style in-process Python, if the dependency/runtime tradeoffs are acceptable.

The bundled lightweight choice is the local HTTP bridge because it adds no new runtime dependency beyond the Python standard library.

## Minimal Run Path

1. Start the local explorer bridge:

```bash
PYTHONPATH=src .venv/bin/python -m citegeist.app_server --db library.sqlite3 --host 127.0.0.1 --port 8765
```

2. Serve the example directory statically from another terminal:

```bash
cd examples/literature-explorer
python3 -m http.server 8000
```

3. Open:

```text
http://127.0.0.1:8000/index.html
```

The demo shell in `index.html` is intentionally narrow. It is meant to prove that the app-facing API is sufficient to drive topic bootstrap, topic expansion, search, extraction, verification, and entry inspection from a browser without introducing a frontend framework.

## Demo Scope

This is sufficient to drive a demonstration app that can:

- start from a topic phrase and preview bootstrap candidates;
- commit a bounded topic corpus into the local store;
- inspect topic members, confidence scores, and entry metadata;
- preview or apply topic expansion;
- inspect one entry with BibTeX/provenance details;
- run rough-reference extraction and verification;
- render local citation neighborhoods from `graph()` JSON payloads.

For a first demo, the strongest path is topic exploration rather than generic reference-manager behavior.
