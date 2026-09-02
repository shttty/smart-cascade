#!/usr/bin/env python3
"""Focused tests for Smart Cascade's minimal rework counters."""

from __future__ import annotations

import concurrent.futures
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "bootstrap/state.py"


def run(state_dir: Path | None, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if state_dir is None:
        env.pop("SMART_CASCADE_STATE_DIR", None)
    else:
        env["SMART_CASCADE_STATE_DIR"] = str(state_dir)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        timeout=10,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="smart-cascade-state-") as raw:
        state = Path(raw)
        assert run(state, "slice", "get", "slice-a").stdout.strip() == "slice-a rework=0"
        assert run(state, "child", "get", "slice-a", "child-a").stdout.strip() == "slice-a/child-a rework=0"

        for count in range(1, 10):
            result = run(state, "slice", "rework", "slice-a")
            assert result.returncode == 0, result.stdout
            action = "suggest_advisor" if count % 3 == 0 else "continue"
            assert result.stdout.strip() == f"slice-a rework={count} action={action}"

        for count in range(1, 7):
            result = run(state, "child", "rework", "slice-a", "child-a")
            assert result.returncode == 0, result.stdout
            action = "upgrade_executor" if count % 3 == 0 else "continue"
            assert result.stdout.strip() == f"slice-a/child-a rework={count} action={action}"

        root_state = (state / "state.toml").read_text(encoding="utf-8")
        child_state = (state / "slice-a/state.toml").read_text(encoding="utf-8")
        assert 'rework = 9' in root_state and "action" not in root_state and "children" not in root_state
        assert 'rework = 6' in child_state and "action" not in child_state and "slices" not in child_state

        other = run(state, "child", "rework", "slice-a", "child-b")
        assert other.returncode == 0 and "rework=1" in other.stdout
        assert run(state, "child", "get", "slice-a", "child-a").stdout.strip().endswith("rework=6")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            concurrent_results = list(pool.map(lambda _: run(state, "child", "rework", "slice-a", "child-c"), range(24)))
        assert all(result.returncode == 0 for result in concurrent_results)
        assert run(state, "child", "get", "slice-a", "child-c").stdout.strip().endswith("rework=24")

        repo = state / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Smart Cascade Test"], cwd=repo, check=True)
        (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
        worktree = state / "worktree"
        subprocess.run(["git", "worktree", "add", "-q", "--detach", str(worktree)], cwd=repo, check=True)
        persistent = run(None, "child", "rework", "slice-persistent", "child-a", cwd=worktree)
        assert persistent.returncode == 0, persistent.stdout
        production_state = repo / ".smart-cascade/state/slice-persistent/state.toml"
        assert production_state.is_file()
        assert not (worktree / ".smart-cascade/state").exists()

        malformed = state / "bad" / "state.toml"
        malformed.parent.mkdir()
        malformed.write_text('[children."child-a"]\nrework = "six"\n', encoding="utf-8")
        failed = run(state, "child", "get", "bad", "child-a")
        assert failed.returncode != 0 and "malformed state file" in failed.stdout

        invalid = run(state, "slice", "get", "../escape")
        assert invalid.returncode != 0 and "stable ID" in invalid.stdout

    subprocess.run([sys.executable, "-m", "py_compile", str(SCRIPT)], check=True)
    print('{"status":"STATE_TESTS_PASSED"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
