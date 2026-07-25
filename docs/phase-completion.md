# Sources-First Status

**Current Focus:** identify and prioritize the next open bibliographic sources to add, using the existing SQLite-based workflow as the baseline.

---

## Phase Matrix

| Phase | Title | Status | Outcome |
|-------|-------|--------|---------|
| **0** | Scope Reframe | ✅ Complete | Planning now answers the source question directly |
| **1** | Source Layer Tightening | ✅ Complete | Registry, CrossRef plugin, compatibility seam, and source catalog repaired |
| **2** | Next Open Source Additions | 🚧 In Progress | OpenCitations, Unpaywall, Europe PMC, and Semantic Scholar integrated |
| **3** | Optional Source Evaluation | ⏳ Planned | OpenAIRE evaluated later if acquisition breadth matters |
| **D** | Database / Vector Expansion | ⏸ Deferred | Not required for the current source-incorporation decision |

---

## Test Coverage Summary

```
✅ test_sources_plugin.py
✅ test_sources_catalog.py
✅ full suite: 290 passed, 5 skipped on 2026-07-25
```

---

## Key Artifacts

### Documentation
```
docs/
├── source-landscape.md          ✅ Source inventory and recommendations
├── implementation-progress.md   ✅ Sources-first progress tracker
└── phase-completion.md          ✅ Short status summary
```

### Source Layer
```
src/citegeist/sources/
├── base.py                      ✅ Base source interface
├── catalog.py                   ✅ Source inventory in code
├── registry.py                  ✅ Registry for known source classes
├── crossref.py                  ✅ Repaired CrossRef plugin
└── _old_sources_compat.py       ✅ Repo-relative compatibility bridge
```

### Tests
```
tests/
├── test_sources_plugin.py       ✅ Source plugin tests
└── test_sources_catalog.py      ✅ Source catalog/registry tests
```

---

## Key Features Implemented

- ✅ Source catalog covering current and candidate open sources
- ✅ Config-driven registry loading for known real source classes
- ✅ CrossRef normalization that works for both single-record and search-result payloads
- ✅ Compatibility bridge that no longer depends on one checkout path
- ✅ OpenCitations DOI-based graph expansion with CLI support
- ✅ Unpaywall OA-link enrichment with CLI support
- ✅ Europe PMC biomedical resolver/search support
- ✅ Semantic Scholar broad-science resolver/search support

---

## Next Milestones

### Immediate
1. Decide whether repository-acquisition scope justifies `OpenAIRE`
2. Keep the OA-enrichment flow aligned with review/export needs
3. Keep graph-source scope disciplined as broader coverage grows

### Later
1. Evaluate `OpenAIRE`
2. Revisit database/vector work only if a concrete source need demands it

### Unified confidence migration

The working tree contains a partial typed-assessment implementation. It is not
a completed migration or release. The CLI migration command, backup/rollback,
portable interval storage, reviewed identity outcomes/calibration, and
Epistemap graph export remain. The audited phase matrix is in Epistemap
`docs/confidence-overhaul-implementation-status.md`.

---

## Success Metrics

### Completed
- ✅ Planning now matches the actual source question
- ✅ Source-layer defects from the first pass have been corrected
- ✅ OpenCitations is now a working integrated source
- ✅ Unpaywall is now a working integrated source
- ✅ Europe PMC is now a working integrated source
- ✅ Semantic Scholar is now a working integrated source
- ✅ The next source priorities are explicit

### Planned
- ⏳ Better source selection discipline before adding more integrations

---

## Recommendations

1. Treat the current SQLite/FTS workflow as the baseline, not as a blocker.
2. Add source integrations only when they materially improve bibliographic coverage, citation coverage, or open-access linkage.
3. Keep database/vector work explicitly subordinate to source-incorporation needs.

---

**Last Updated:** 2026-07-25
**Status:** Sources-first plan in effect
**Confidence:** High
