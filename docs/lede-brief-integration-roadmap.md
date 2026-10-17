# Lede-brief scholarly integration roadmap

Status: proposed, all stages pending. Prepared 2026-10-04.

Distribution preparation: CiteGeist metadata now requires
`citegeist[scholarly-brief]` installs the optional `lede-brief>=0.1.0a2,<0.2`;
its patch version is `0.1.2`. Use the repository
`.venv` plus local editable sibling installs for development until the shared
package is published.

Use shared lede-brief packages to create reviewed paper briefs, comparison
dossiers and literature collections with traceable conceptual coverage. Follow
the [coordinating design](../../GroundRecall/docs/lede-brief-design-and-roadmap.md)
and [Epistemap foundation plan](../../Epistemap/docs/lede-brief-foundations-roadmap.md).
Links assume sibling checkouts until release documentation is published.

CiteGeist remains authoritative for bibliographic identity, source/version
provenance, conflicts, review states and BibTeX export. The shared library handles
transformation and semantic-review orchestration; Epistemap supplies neutral
graph operations. CiteGeist can consume those packages without GroundRecall.
Its current bounded claim-support candidates remain suggestions for review.

| Stage | Deliverable | Acceptance |
| --- | --- | --- |
| CLB-0 | Scholarly preservation profile and reviewed paper/comparison fixtures | Methods, population, quantities, limitations, uncertainty, attribution and disagreement are inventoried; input scope distinguishes abstract, excerpt and full text. |
| CLB-1 | Read-only adapter exporting stable work/source-version references and accessible source spans to the shared library | DOI/BibTeX identity and provenance survive; missing or inaccessible sections are coverage gaps; no automatic bibliography mutation or citation acceptance. |
| CLB-2 | Reviewed per-paper and multi-paper brief collections | Every synthesis assertion has source mappings and qualifications; disagreements and corrections remain visible; citation edges are never automatically converted to support edges. |
| CLB-3 | Scholarly evaluation and installed compatibility fixture | Independent checks catch attribution swaps, abstract-only overclaims, changed methods, retractions/corrections and unsupported synthesis; report preparation-inclusive costs and coverage limits. |

CLB-0 follows LB-0/ELB-0 contracts. CLB-1/CLB-2 consume shared LB-1 through LB-3
and tested ELB operations; CLB-3 contributes to LB-5/ELB-3. Introduce optional
dependencies with pinned compatibility when implementing the adapter; do not
assume Epistemap is already an installed CiteGeist dependency.

Keep corpus completeness distinct from conceptual coverage of the supplied
sources. A brief covering every accessible abstract does not cover the full
papers or the entire literature. Relatedness, source identity, extraction
fidelity and reviewed evidential support remain separate assessments. A source
correction invalidates dependent briefs without automatically changing BibTeX
review decisions.

Preserve acquisition/access restrictions in derived packages. Public summaries
must not reveal restricted content. Reuse the validation/provenance/evaluation
gates in the [process improvement roadmap](process-improvement-roadmap.md).
Offline lede-brief fixtures can proceed independently; actual GroundRecall
unified-retrieval integration remains subject to its existing UPR-0 gate.
