import pytest

pytest.importorskip("ledebrief")

from citegeist.lede_brief import build_scholarly_brief, scholarly_review_requirements
from ledebrief import SourceDocument


def test_scholarly_adapter_records_source_scope():
    result = build_scholarly_brief(SourceDocument(source_id="paper", text="The abstract reports a bounded result."), scope="abstract")
    assert result.metadata["source_scope"] == "abstract"
    assert any("full-paper" in item for item in scholarly_review_requirements(result))


def test_scholarly_adapter_rejects_unknown_scope():
    try:
        build_scholarly_brief(SourceDocument(source_id="paper", text="text"), scope="citation")
    except ValueError as exc:
        assert "scope" in str(exc)
    else:
        raise AssertionError("unknown source scope should fail")
