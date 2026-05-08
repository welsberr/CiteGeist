from __future__ import annotations

from dataclasses import dataclass
import re

from .verify import BibliographyVerifier


CLAIM_MARKER = "✅"
NUMERIC_CITATION_PATTERN = re.compile(r"\[(\d+)\]")
AUTHOR_YEAR_PAREN_PATTERN = re.compile(
    r"\(([A-Z][A-Za-z'’.-]+(?:\s+(?:and|&|et al\.?))?(?:\s+[A-Z][A-Za-z'’.-]+)*,?\s+\d{4}[a-z]?)\)"
)
AUTHOR_YEAR_INLINE_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z'’.-]+(?:\s+(?:and|&|et al\.?))?(?:\s+[A-Z][A-Za-z'’.-]+)*)\s*\((\d{4}[a-z]?)\)"
)
REFERENCE_ENTRY_PATTERN = re.compile(r"^\s*\[\[(\d+)\]\]\s*(.+)$", re.MULTILINE)
REFERENCE_BLOCK_PATTERN = re.compile(r"^\s*\[\[(\d+)\]\]\s*(.+?)(?=^\s*\[\[\d+\]\]|\Z)", re.MULTILINE | re.DOTALL)
SENTENCE_SPLIT_PATTERN = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"\[])')
SECTION_HEADER_PATTERN = re.compile(r"^(?:[IVX]+\.|[A-Z]\.)\s+[A-Z]")
CONTINUATION_START_PATTERN = re.compile(
    r"^(?:instead|rather|thus|therefore|however|moreover|further|furthermore|"
    r"because|given that|in most cases|for many purposes|these|this|such|it|they|"
    r"another|the same|that |those )",
    re.IGNORECASE,
)
CLAIM_SIGNAL_PATTERN = re.compile(
    r"\b(?:we|our|this|these|those|research|results?|findings?|analysis|approach|model(?:ing)?|"
    r"study|studies|work|movement|evolution(?:ary)?|agents?|organisms?|intelligence|behavior|"
    r"behaviour|environment(?:al)?|resource(?:s)?|strategy|strategies|generaliz(?:e|ation)|"
    r"suggest(?:s|ed)?|indicat(?:es|ed)|show(?:s|ed)?|demonstrat(?:e|es|ed)|permit(?:s|ted)?|"
    r"require(?:s|d)?|provide(?:s|d)?|span(?:s|ned)?|range(?:s|d)?|covers?|across|exploit(?:s|ed)?|"
    r"emerge(?:s|d)|evolved?|hypothesis|goal|question|capabilit(?:y|ies)|complex(?:ity)?|"
    r"resource peak|gradient ascent|optimal|random walk|turing-complete)\b",
    re.IGNORECASE,
)
NON_CLAIM_START_PATTERN = re.compile(
    r"^(?:abstract|introduction|methods|results|discussion|future work|conclusions?|references|"
    r"keywords?|fig\.|table\s|view\s+\d+|show\s+abstract|relevance:|optional|already cited|"
    r"new references found)",
    re.IGNORECASE,
)
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"[a-z0-9]{4,}")


@dataclass(slots=True)
class ClaimSupportSuggestion:
    claim_text: str
    existing_citation_markers: list[str]
    existing_reference_titles: list[str]
    suggested_references: list[dict[str, object]]
    needs_support_score: float
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "claim_text": self.claim_text,
            "existing_citation_markers": list(self.existing_citation_markers),
            "existing_reference_titles": list(self.existing_reference_titles),
            "suggested_references": list(self.suggested_references),
            "needs_support_score": round(float(self.needs_support_score), 3),
            "note": self.note,
        }


@dataclass(slots=True)
class ClaimCandidate:
    text: str
    citation_markers: list[str]
    needs_support_score: float


@dataclass(slots=True)
class ExistingReference:
    title: str
    doi: str = ""


def analyze_support_gaps(
    text: str,
    *,
    verifier: BibliographyVerifier | None = None,
    context: str = "",
    limit: int = 5,
    max_claims: int = 8,
    min_claim_chars: int = 90,
) -> dict[str, object]:
    verifier = verifier or BibliographyVerifier()
    existing_references = _extract_existing_references(text)
    existing_titles_normalized = {
        _normalize_title(reference.title)
        for reference in existing_references.values()
        if reference.title
    }
    existing_dois_normalized = {
        _normalize_doi(reference.doi)
        for reference in existing_references.values()
        if reference.doi
    }
    claims = _extract_claim_candidates(text, max_claims=max_claims, min_claim_chars=min_claim_chars)

    suggestions: list[ClaimSupportSuggestion] = []
    for claim in claims:
        referenced_titles = [
            existing_references[marker].title
            for marker in claim.citation_markers
            if marker in existing_references and existing_references[marker].title
        ]
        verification = verifier.verify_string(claim.text, context=context, limit=limit)
        candidates = [verification.entry, *[alt.entry for alt in verification.alternates]]
        sources = [verification.source_label, *[alt.source_label for alt in verification.alternates]]
        scores = [verification.confidence, *[alt.score for alt in verification.alternates]]

        rendered: list[dict[str, object]] = []
        seen_titles: set[str] = set()
        seen_dois: set[str] = set()
        seen_keys: set[str] = set()
        for entry, source_label, score in zip(candidates, sources, scores):
            title = str(entry.fields.get("title") or "").strip()
            doi = str(entry.fields.get("doi") or "").strip()
            normalized_title = _normalize_title(title)
            normalized_doi = _normalize_doi(doi)
            citation_key = str(entry.citation_key or "").strip()
            normalized_key = citation_key.lower()
            if not title:
                continue
            if normalized_title in existing_titles_normalized or normalized_title in seen_titles:
                continue
            if normalized_doi and (normalized_doi in existing_dois_normalized or normalized_doi in seen_dois):
                continue
            if normalized_key and normalized_key in seen_keys:
                continue
            seen_titles.add(normalized_title)
            if normalized_doi:
                seen_dois.add(normalized_doi)
            if normalized_key:
                seen_keys.add(normalized_key)
            rendered.append(
                {
                    "citation_key": citation_key,
                    "entry_type": entry.entry_type,
                    "title": title,
                    "authors": str(entry.fields.get("author") or ""),
                    "year": str(entry.fields.get("year") or ""),
                    "doi": doi,
                    "journal": str(entry.fields.get("journal") or entry.fields.get("booktitle") or ""),
                    "source_label": source_label,
                    "score": round(float(score), 4),
                    "reason": _build_reference_reason(
                        claim.text,
                        title=title,
                        journal=str(entry.fields.get("journal") or entry.fields.get("booktitle") or ""),
                        source_label=source_label,
                        is_primary=entry is verification.entry,
                    ),
                }
            )

        if rendered:
            suggestions.append(
                ClaimSupportSuggestion(
                    claim_text=claim.text,
                    existing_citation_markers=claim.citation_markers,
                    existing_reference_titles=referenced_titles,
                    suggested_references=rendered,
                    needs_support_score=claim.needs_support_score,
                    note=_build_note(claim.citation_markers, referenced_titles),
                )
            )

    suggestions.sort(
        key=lambda item: (
            item.needs_support_score,
            len(item.suggested_references),
            len(item.claim_text),
        ),
        reverse=True,
    )

    return {
        "claim_count": len(claims),
        "existing_reference_count": len(existing_references),
        "suggestion_count": len(suggestions),
        "suggestions": [item.to_dict() for item in suggestions],
    }


def _extract_claim_candidates(text: str, *, max_claims: int, min_claim_chars: int) -> list[ClaimCandidate]:
    body = text.partition("References")[0] if "References" in text else text
    sentences = _prepare_sentences(body)
    claims: list[ClaimCandidate] = []
    index = 0
    while index < len(sentences):
        current = sentences[index]
        if not _is_claim_like(current, min_claim_chars=min_claim_chars):
            index += 1
            continue
        parts = [current]
        index += 1
        while index < len(sentences) and _should_merge_continuation(parts[-1], sentences[index], min_claim_chars=min_claim_chars):
            parts.append(sentences[index])
            index += 1
        claim_text = " ".join(parts).strip()
        if len(claim_text) < min_claim_chars:
            continue
        claims.append(
            ClaimCandidate(
                text=claim_text,
                citation_markers=_extract_citation_markers(claim_text),
                needs_support_score=_score_claim_need(claim_text),
            )
        )
        if len(claims) >= max_claims:
            break
    return claims


def _prepare_sentences(body: str) -> list[str]:
    cleaned_body = body.replace(CLAIM_MARKER, " ").replace("✅", " ")
    cleaned_body = re.sub(r"\s+", " ", cleaned_body)
    sentences: list[str] = []
    for sentence in SENTENCE_SPLIT_PATTERN.split(cleaned_body):
        cleaned = sentence.strip()
        if not cleaned:
            continue
        if cleaned.upper() == cleaned and len(cleaned) > 24:
            continue
        if NON_CLAIM_START_PATTERN.match(cleaned):
            continue
        if SECTION_HEADER_PATTERN.match(cleaned):
            continue
        sentences.append(cleaned)
    return sentences


def _is_claim_like(sentence: str, *, min_claim_chars: int) -> bool:
    if len(sentence) < max(45, min_claim_chars // 2):
        return False
    if sentence.startswith("[["):
        return False
    if NUMERIC_CITATION_PATTERN.search(sentence):
        return True
    if AUTHOR_YEAR_PAREN_PATTERN.search(sentence) or AUTHOR_YEAR_INLINE_PATTERN.search(sentence):
        return True
    if CLAIM_SIGNAL_PATTERN.search(sentence) and (len(sentence) >= min_claim_chars or sentence.count(",") >= 1):
        return True
    return False


def _should_merge_continuation(current: str, next_sentence: str, *, min_claim_chars: int) -> bool:
    if len(current) >= max(min_claim_chars * 3, 320):
        return False
    if not _is_claim_like(next_sentence, min_claim_chars=max(45, min_claim_chars // 2)):
        return False
    if CONTINUATION_START_PATTERN.match(next_sentence):
        return True
    current_markers = _extract_citation_markers(current)
    next_markers = _extract_citation_markers(next_sentence)
    if next_markers and not current_markers:
        return True
    if current_markers and len(next_sentence) < max(min_claim_chars, 180):
        return True
    return False


def _extract_existing_references(text: str) -> dict[str, ExistingReference]:
    if "References" not in text:
        return {}
    _, _, tail = text.partition("References")
    references: dict[str, ExistingReference] = {}
    for match in REFERENCE_BLOCK_PATTERN.finditer(tail):
        marker = match.group(1)
        block = match.group(2).strip()
        first_line = block.splitlines()[0].strip() if block else ""
        doi_match = DOI_PATTERN.search(block)
        references[marker] = ExistingReference(
            title=first_line,
            doi=doi_match.group(0) if doi_match else "",
        )
    return references


def _extract_citation_markers(text: str) -> list[str]:
    markers: list[str] = []
    seen: set[str] = set()
    for match in NUMERIC_CITATION_PATTERN.finditer(text):
        marker = match.group(1)
        if marker not in seen:
            seen.add(marker)
            markers.append(marker)
    for match in AUTHOR_YEAR_PAREN_PATTERN.finditer(text):
        marker = f"({match.group(1)})"
        if marker not in seen:
            seen.add(marker)
            markers.append(marker)
    for match in AUTHOR_YEAR_INLINE_PATTERN.finditer(text):
        marker = f"{match.group(1)} ({match.group(2)})"
        if marker not in seen:
            seen.add(marker)
            markers.append(marker)
    return markers


def _score_claim_need(text: str) -> float:
    score = 0.0
    markers = _extract_citation_markers(text)
    length = len(text)
    signal_count = len(CLAIM_SIGNAL_PATTERN.findall(text))

    if not markers:
        score += 3.0
    else:
        score += max(0.25, 1.5 - min(len(markers), 3) * 0.35)
        if any(marker.isdigit() for marker in markers):
            score += 0.35

    if length >= 220:
        score += 1.25
    elif length >= 140:
        score += 0.85
    elif length >= 90:
        score += 0.45

    score += min(signal_count, 6) * 0.25

    if "," in text:
        score += 0.2
    if any(token in text.lower() for token in ("suggest", "indicate", "show", "demonstrate", "require", "because")):
        score += 0.3

    return score


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _normalize_doi(value: str) -> str:
    return value.strip().lower()


def _build_reference_reason(
    claim_text: str,
    *,
    title: str,
    journal: str,
    source_label: str,
    is_primary: bool,
) -> str:
    claim_terms = _meaningful_tokens(claim_text)
    title_terms = _meaningful_tokens(title)
    journal_terms = _meaningful_tokens(journal)
    overlap = sorted(claim_terms & title_terms)
    overlap_preview = ", ".join(overlap[:3])

    reasons: list[str] = []
    reasons.append("Top candidate match." if is_primary else "Alternate candidate retained after verification.")
    if overlap_preview:
        reasons.append(f"Shares claim terms: {overlap_preview}.")
    elif claim_terms & journal_terms:
        reasons.append("Venue terms overlap with the claim topic.")
    elif source_label.startswith("openalex:search:"):
        reasons.append("Returned from topic-oriented OpenAlex search for this claim.")
    elif source_label.startswith("crossref:search:"):
        reasons.append("Returned from Crossref search for this claim.")
    else:
        reasons.append("Returned by the bibliography verifier for this claim.")
    return " ".join(reasons)


def _meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(value.lower())
        if token not in {"this", "that", "with", "from", "their", "there", "into", "about", "through", "using"}
    }


def _build_note(markers: list[str], titles: list[str]) -> str | None:
    if not markers:
        return "No existing inline citation markers detected for this claim."
    if titles:
        return f"Existing citations detected: {', '.join(_render_marker(marker) for marker in markers)}."
    return (
        "Inline citation markers detected "
        f"({', '.join(_render_marker(marker) for marker in markers)}), but no matching reference titles were parsed."
    )


def _render_marker(marker: str) -> str:
    if marker.isdigit():
        return f"[{marker}]"
    return marker
