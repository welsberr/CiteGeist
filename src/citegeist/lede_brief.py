"""CiteGeist adapter for provenance-aware scholarly lede-brief packages."""

from __future__ import annotations

from typing import Iterable

try:
    from ledebrief import BriefRequest, BriefResult, SourceDocument, create_brief
except ImportError as exc:  # optional integration
    raise ImportError(
        "CiteGeist's scholarly brief adapter requires the optional dependency; "
        "install with `pip install citegeist[scholarly-brief]`."
    ) from exc


def build_scholarly_brief(
    source: SourceDocument,
    *,
    scope: str = "abstract",
    required_unit_ids: Iterable[str] = (),
    mode: str = "complete-single",
    max_words: int | None = None,
) -> BriefResult:
    if scope not in {"abstract", "excerpt", "full-text"}:
        raise ValueError("scope must be abstract, excerpt, or full-text")
    enriched = source.model_copy(update={"metadata": {**source.metadata, "source_scope": scope}})
    result = create_brief(
        enriched,
        BriefRequest(
            mode=mode,  # type: ignore[arg-type]
            required_unit_ids=list(required_unit_ids),
            max_words=max_words,
            audience="researcher",
            preservation_profile="citegeist-scholarly",
        ),
    )
    result.metadata["source_scope"] = scope
    return result


def scholarly_review_requirements(result: BriefResult) -> list[str]:
    scope = str(result.metadata.get("source_scope", "unknown"))
    return [
        f"verify claims against the supplied {scope} scope; do not infer full-paper coverage",
        "preserve methods, limitations, uncertainty, attribution, and disagreement",
        "keep citation identity and evidential support as separate review decisions",
    ]
