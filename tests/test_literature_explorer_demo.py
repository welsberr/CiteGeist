from pathlib import Path


def test_literature_explorer_demo_exposes_claim_support_panel():
    root = Path(__file__).resolve().parents[1]
    html = (root / "examples" / "literature-explorer" / "index.html").read_text(encoding="utf-8")
    js = (root / "examples" / "literature-explorer" / "literature-explorer.js").read_text(encoding="utf-8")

    assert 'id="claim-support-button"' in html
    assert 'id="claim-support-output"' in html
    assert "Needs Support" in html
    assert "supportClaims(text, options = {})" in js
    assert 'bridge.call("support_claims"' in js
