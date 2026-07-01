# Library Argument Ingestion

CiteGeist provides the citation-resolution and source-support layer for Library
argument ingestion.

## Role

CiteGeist should connect argument elements to candidate bibliographic works,
open-access locations, and support gaps. It should not decide that a source
proves a claim without review.

## Inputs

Useful inputs include:

- doclift chunks with `role` and `analysis_hints`;
- citation-bearing spans from Library documents;
- GroundRecall draft propositions, premises, critiques, and evidence requests;
- site-review questions from SciSiteForge workbenches.

## Outputs

Recommended outputs include:

- resolved work candidates with confidence and source API provenance;
- citation anchors attached to argument elements;
- support-gap reports for unsupported propositions;
- candidate contrary or contextual sources;
- citations for fallacy taxonomy definitions and reviewed examples;
- citation and bibliographic evidence for explicit influence, later reuse, or
  silent-borrowing candidates;
- BibTeX and CSL exports for reviewed records.

Claim-support suggestions remain draft until a reviewer confirms that the cited
work actually supports the specific proposition or premise.

Lineage suggestions also remain draft. CiteGeist can show that two works share
citations, phrases, examples, or publication paths, but review must decide
whether that supports citation, borrowing, response, or independent recurrence.

## Study-Aid Source Support

Study-aid views should expose their source-support state. CiteGeist can help by
resolving citations for:

- at-a-glance source metadata;
- glossary definitions;
- worked examples;
- critique and evidence cards;
- practice-question answer keys;
- further reading.

The support state should distinguish "cited by the aid", "supports the answer",
"background reading", "contrary source", and "needs review".
