"""Run a local ranking-proposal command with development-only filesystem access."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .discovery_pool import DiscoveryPoolError, write_private_json
from .ranking_experiment import MAX_INPUT_BYTES, RankingExperimentError, _validate_pool, _validate_proposals

try:
    import resource
except ImportError:  # pragma: no cover - resource is POSIX-only
    resource = None


class ProposalSandboxError(ValueError):
    """Raised when the isolated proposal workflow cannot be safely completed."""


MAX_TIMEOUT_SECONDS = 900
MAX_LOG_BYTES = 1024 * 1024


def _sandbox_limits(timeout_seconds: int) -> None:
    if resource is None:
        raise ProposalSandboxError("resource limits require a POSIX host")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_INPUT_BYTES, MAX_INPUT_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    cpu_seconds = timeout_seconds + 1
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))


def run_proposal_sandbox(
    development_path: Path,
    output_path: Path,
    command: list[str],
    *,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Run a local proposal generator with only a read-only dev pool and output mount.

    The sandbox has no network namespace route, home directory, project checkout,
    validation files, database, or inherited environment. The child receives the
    two artifact paths through fixed environment variables.
    """
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ProposalSandboxError(f"timeout_seconds must be from 1 to {MAX_TIMEOUT_SECONDS}")
    if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
        raise ProposalSandboxError("an executable command and arguments are required")
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise ProposalSandboxError("bubblewrap (bwrap) is required for proposal isolation")

    development_path = development_path.resolve(strict=True)
    output_path = output_path.resolve()
    if not development_path.is_file():
        raise ProposalSandboxError("development pool must be a regular file")
    if output_path.exists():
        raise ProposalSandboxError(f"proposal output already exists: {output_path}")
    if development_path == output_path:
        raise ProposalSandboxError("proposal output must not overwrite the development pool")
    try:
        if development_path.stat().st_size > MAX_INPUT_BYTES:
            raise ProposalSandboxError(f"development pool exceeds {MAX_INPUT_BYTES}-byte limit")
        development_bytes = development_path.read_bytes()
        if len(development_bytes) > MAX_INPUT_BYTES:
            raise ProposalSandboxError(f"development pool exceeds {MAX_INPUT_BYTES}-byte limit")
        development_pool = json.loads(development_bytes)
        _validate_pool(development_pool, "development")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RankingExperimentError) as exc:
        raise ProposalSandboxError(f"invalid development pool: {exc}") from exc
    if development_pool.get("split") not in (None, "development"):
        raise ProposalSandboxError("proposal sandbox accepts development pools only")

    with tempfile.TemporaryDirectory(prefix="citegeist-proposal-") as staging_name:
        staging_root = Path(staging_name)
        staging_root.chmod(0o700)
        staging = staging_root / "output"
        staging.mkdir(mode=0o700)
        output_file = staging / "proposals.json"
        sandbox_development = staging_root / "development.json"
        filtered_pool = {
            "schema_version": 1,
            "pool_id": development_pool["pool_id"],
            "split": "development",
            "cases": [
                {
                    "case_id": case["case_id"],
                    "query": case["query"],
                    "relevant_ids": case["relevant_ids"],
                    "seed_texts": case.get("seed_texts", []),
                    "candidates": [
                        {
                            "id": candidate["id"],
                            "fields": {key: candidate.get("fields", {}).get(key, "") for key in ("title", "abstract", "keywords") if candidate.get("fields", {}).get(key)},
                            "providers": candidate.get("providers", []),
                            "provider_ranks": candidate.get("provider_ranks", {}),
                        }
                        for candidate in case["candidates"]
                    ],
                }
                for case in development_pool["cases"]
            ],
        }
        with sandbox_development.open("x", encoding="utf-8") as stream:
            json.dump(filtered_pool, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        sandbox_development.chmod(0o400)
        runtime_paths = [Path("/usr"), Path("/lib"), Path("/lib64")]
        args = [
            bwrap,
            "--die-with-parent",
            "--new-session",
            "--unshare-all",
            "--tmpfs", "/",
            "--dir", "/tmp",
            "--dir", "/workspace",
            "--dir", "/input",
            "--dir", "/output",
            "--dir", "/etc",
        ]
        for runtime in runtime_paths:
            if runtime.exists():
                args.extend(["--ro-bind", str(runtime), str(runtime)])
        ld_cache = Path("/etc/ld.so.cache")
        if ld_cache.exists():
            args.extend(["--ro-bind", str(ld_cache), str(ld_cache)])
        args.extend([
            "--proc", "/proc",
            "--dev", "/dev",
            "--ro-bind", str(sandbox_development), "/input/development.json",
            "--bind", str(staging), "/output",
            "--chdir", "/workspace",
            "--clearenv",
            "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
            "--setenv", "HOME", "/nonexistent",
            "--setenv", "PYTHONNOUSERSITE", "1",
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
            "--setenv", "CITEGEIST_DEVELOPMENT_POOL", "/input/development.json",
            "--setenv", "CITEGEIST_PROPOSAL_OUTPUT", "/output/proposals.json",
            "--",
            *command,
        ])
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            try:
                completed = subprocess.run(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    timeout=timeout_seconds,
                    check=False,
                    close_fds=True,
                    preexec_fn=lambda: _sandbox_limits(timeout_seconds),
                )
            except subprocess.TimeoutExpired as exc:
                raise ProposalSandboxError(f"proposal command exceeded {timeout_seconds} seconds") from exc
            except OSError as exc:
                raise ProposalSandboxError(f"could not start isolated proposal command: {exc}") from exc
            stdout.seek(0, os.SEEK_END)
            stderr.seek(0, os.SEEK_END)
            if stdout.tell() > MAX_LOG_BYTES or stderr.tell() > MAX_LOG_BYTES:
                raise ProposalSandboxError(f"proposal command logs exceed {MAX_LOG_BYTES}-byte limit")
            stdout.seek(0)
            stderr.seek(0)
            out_text = stdout.read().decode("utf-8", errors="replace")
            err_text = stderr.read().decode("utf-8", errors="replace")
        if completed.returncode != 0:
            detail = err_text[-2000:].strip() or out_text[-1000:].strip() or f"exit code {completed.returncode}"
            raise ProposalSandboxError(f"isolated proposal command failed: {detail}")
        entries = list(staging.iterdir())
        if entries != [output_file] or output_file.is_symlink() or not output_file.is_file():
            raise ProposalSandboxError("sandbox must produce only proposals.json")
        if output_file.stat().st_size > MAX_INPUT_BYTES:
            raise ProposalSandboxError(f"proposal output exceeds {MAX_INPUT_BYTES}-byte limit")
        try:
            proposals = json.loads(output_file.read_bytes())
            normalized = _validate_proposals(proposals)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, RankingExperimentError) as exc:
            raise ProposalSandboxError(f"sandbox output is not an allowed proposal artifact: {exc}") from exc
        value = {"schema_version": 1, "proposals": normalized}
        try:
            write_private_json(output_path, value)
        except DiscoveryPoolError as exc:
            raise ProposalSandboxError(str(exc)) from exc
    return {
        "output": str(output_path),
        "development_pool_id": development_pool["pool_id"],
        "proposal_count": len(value["proposals"]),
        "network_disabled": True,
        "automatic_promotion": False,
    }
