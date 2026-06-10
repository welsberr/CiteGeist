# Reasoning Scaffold Source Slots

CiteGeist should treat scaffold source slots as bibliography work orders. A source slot names a claim family that needs reviewed sources before a Notebook page, Didactopus activity, or other educational artifact presents the source trail as grounded.

## Source Slot Workflow

1. Read the scaffold record and identify the claim that needs support.
2. Use `candidate_queries` as starting points, not as accepted citations.
3. Resolve each slot to reviewed sources with stable metadata: title, authors, year, venue, DOI or durable URL when available, and relevance note.
4. Mark unresolved or weak support explicitly instead of filling the slot with a convenient citation.
5. Return enough provenance for Notebook and Didactopus to show why the source belongs in the trail.

Resolved slots should feed back into scaffold artifacts in a way that
preserves review status and rationale. The goal is not just to "fill a field"
but to improve the grounded source trail that Notebook and Didactopus expose to
readers and learners.

## Preferred Slot Shape

```json
{
  "slot": "genetic-drift-foundations",
  "needed_for": "Drift, population size, fixation, and sampling effects",
  "candidate_queries": [
    "Wright 1931 evolution in Mendelian populations genetic drift"
  ],
  "review_status": "pending"
}
```

When resolved, CiteGeist should add or export reviewed bibliography records rather than silently replacing the slot text.

## Reference Fixture

The first scaffold with pending source slots is:

- `/home/netuser/dev/evo-edu.org/notebook/concepts/allele-frequency-change.scaffold.json`

Its slots cover Hardy-Weinberg expectations, drift foundations, and selection foundations.
