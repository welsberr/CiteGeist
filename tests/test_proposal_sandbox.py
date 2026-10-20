import json
import shutil
from pathlib import Path

import pytest

from citegeist.proposal_sandbox import ProposalSandboxError, run_proposal_sandbox
from citegeist.cli import main


def _development_pool(path: Path) -> None:
    path.write_text(json.dumps({
        "schema_version": 1,
        "pool_id": "development-only",
        "split": "development",
        "secret_validation_labels": ["must not be mounted"],
        "cases": [{
            "case_id": "dev-1",
            "query": "find useful marine research",
            "relevant_ids": ["work:1"],
            "seed_texts": ["marine research"],
            "hidden_validation_field": "must not reach the child",
            "candidates": [{
                "id": "work:1",
                "fields": {"title": "Marine research", "private_review_note": "omit this"},
                "providers": ["crossref"],
                "provider_ranks": {"crossref": 1},
                "hidden_validation_metadata": "omit this too",
            }],
        }],
    }), encoding="utf-8")


def test_local_proposal_process_cannot_read_unmounted_files_or_environment(tmp_path, monkeypatch):
    if not shutil.which("bwrap"):
        pytest.skip("bubblewrap is not installed")
    development = tmp_path / "development.json"
    _development_pool(development)
    secret = tmp_path / "validation-labels.json"
    secret.write_text('{"answer":"secret"}', encoding="utf-8")
    monkeypatch.setenv("CITEGEIST_TEST_PRIVATE_TOKEN", "must-not-be-inherited")
    output = tmp_path / "proposals.json"
    host_network_namespace = Path("/proc/self/ns/net").stat().st_ino
    code = r'''
import json, os, pathlib, sys
pool = json.loads(pathlib.Path(os.environ["CITEGEIST_DEVELOPMENT_POOL"]).read_text())
assert "CITEGEIST_TEST_PRIVATE_TOKEN" not in os.environ
assert pathlib.Path("/proc/self/ns/net").stat().st_ino != int(sys.argv[2])
assert "secret_validation_labels" not in pool
case = pool["cases"][0]
assert "hidden_validation_field" not in case
assert "private_review_note" not in case["candidates"][0]["fields"]
assert "hidden_validation_metadata" not in case["candidates"][0]
try:
    pathlib.Path(sys.argv[1]).read_text()
except (FileNotFoundError, PermissionError):
    pass
else:
    raise SystemExit("host validation file was readable")
pathlib.Path(os.environ["CITEGEIST_PROPOSAL_OUTPUT"]).write_text(json.dumps({
    "schema_version": 1,
    "proposals": [{
        "id": "baseline", "parent_id": None,
        "rationale": "unchanged baseline", "weights": {"lexical": 1.0}
    }]
}))
'''
    try:
        result = run_proposal_sandbox(
            development,
            output,
            ["/usr/bin/python3", "-c", code, str(secret), str(host_network_namespace)],
            timeout_seconds=30,
        )
    except ProposalSandboxError as exc:
        if "Operation not permitted" in str(exc) or "Failed to create NETLINK_ROUTE socket" in str(exc):
            pytest.skip(f"host does not permit bubblewrap namespaces: {exc}")
        raise
    assert result["network_disabled"] is True
    assert result["automatic_promotion"] is False
    proposal = json.loads(output.read_text(encoding="utf-8"))
    assert proposal["proposals"][0]["id"] == "baseline"
    assert output.stat().st_mode & 0o777 == 0o600


def test_proposal_sandbox_rejects_non_development_pool_before_spawning(tmp_path):
    development = tmp_path / "not-development.json"
    development.write_text(json.dumps({
        "schema_version": 1,
        "pool_id": "validation",
        "split": "validation",
        "cases": [{"case_id": "case-1", "query": "query", "relevant_ids": [], "candidates": []}],
    }), encoding="utf-8")
    with pytest.raises(ProposalSandboxError, match="development pools only"):
        run_proposal_sandbox(development, tmp_path / "output.json", ["/usr/bin/true"])


def test_cli_runs_isolated_proposal_command_and_publishes_validated_json(tmp_path, capsys):
    if not shutil.which("bwrap"):
        pytest.skip("bubblewrap is not installed")
    development = tmp_path / "development.json"
    _development_pool(development)
    output = tmp_path / "proposals.json"
    code = r'''import json, os, pathlib
pathlib.Path(os.environ["CITEGEIST_PROPOSAL_OUTPUT"]).write_text(json.dumps({
    "schema_version": 1,
    "proposals": [{"id":"baseline", "parent_id":None, "rationale":"baseline", "weights":{"lexical":1.0}}]
}))'''
    code_result = main([
        "sandbox-proposal", "--development", str(development), "--output", str(output),
        "--timeout", "30", "--", "/usr/bin/python3", "-c", code,
    ])
    captured = capsys.readouterr()
    if code_result == 2 and ("Operation not permitted" in captured.err or "NETLINK_ROUTE" in captured.err):
        pytest.skip(f"host does not permit bubblewrap namespaces: {captured.err}")
    assert code_result == 0, captured.err
    response = json.loads(captured.out)
    assert response["network_disabled"] is True
    assert json.loads(output.read_text(encoding="utf-8"))["proposals"][0]["id"] == "baseline"
