#!/usr/bin/env python3
"""Focused tests for the platform-neutral Smart Cascade packet helper."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from smart_cascade_dispatch import (
    MARKER,
    DispatchContractError,
    build_bundle,
    metadata,
    worktree_snapshot,
    write_atomic,
)

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
RUNNER_CONFIG = SKILL_ROOT / "runners/omp/runner-launch.yaml"
SCRIPT = SCRIPT_DIR / "smart_cascade_dispatch.py"


def git(project: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=project, check=True, stdout=subprocess.DEVNULL)


def expect_failure(config: Path, packet: Path, project: Path, message: str) -> None:
    try:
        build_bundle(config, packet, project)
    except DispatchContractError as exc:
        assert message in str(exc), str(exc)
    else:
        raise AssertionError(f"expected failure containing {message!r}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="smart-cascade-dispatch-") as raw:
        root = Path(raw)
        project = root / "project"
        project.mkdir()
        git(project, "init", "-q")
        git(project, "config", "user.email", "test@example.invalid")
        git(project, "config", "user.name", "Smart Cascade Test")
        tracked = project / "tracked.txt"
        tracked.write_text("base\n", encoding="utf-8")
        git(project, "add", "tracked.txt")
        git(project, "commit", "-qm", "initial")

        assert worktree_snapshot(project).paths == ()
        tracked.write_text("worktree\n", encoding="utf-8")
        staged = project / "staged.txt"
        staged.write_text("staged\n", encoding="utf-8")
        git(project, "add", "staged.txt")
        untracked = project / "untracked.txt"
        untracked.write_text("untracked\n", encoding="utf-8")
        ignored_runtime = project / ".smart-cascade/control/ignored.txt"
        ignored_runtime.parent.mkdir(parents=True)
        ignored_runtime.write_text("runtime\n", encoding="utf-8")

        snapshot = worktree_snapshot(project)
        assert snapshot.paths == ("staged.txt", "tracked.txt", "untracked.txt"), snapshot.paths
        before = snapshot.sha256
        untracked.write_text("changed\n", encoding="utf-8")
        assert worktree_snapshot(project).sha256 != before

        packet = root / "packet.md"
        packet.write_text("# Root task\n", encoding="utf-8")
        bundle = build_bundle(RUNNER_CONFIG, packet, project)
        raw_bundle = bundle.text.encode("utf-8")
        assert MARKER in bundle.text
        assert bundle.sha256 == "sha256:" + hashlib.sha256(raw_bundle).hexdigest()
        assert bundle.bytes == len(raw_bundle)
        assert bundle.root_workflow.path == SKILL_ROOT / "bootstrap/root-init.md"
        assert bundle.runner_interface.path == SKILL_ROOT / "bootstrap/runner-interface.json"

        output = root / "nested/prepared.md"
        write_atomic(output, bundle.text)
        assert output.read_text(encoding="utf-8") == bundle.text
        receipt = metadata(bundle, output)
        assert receipt["status"] == "prepared"
        assert receipt["packet_digest"] == bundle.sha256

        cli_packet = root / "cli-packet.md"
        cli_packet.write_text("# CLI task\n", encoding="utf-8")
        cli_output = root / "cli-output.md"
        cli = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--project-root",
                str(project),
                "--runner-config",
                str(RUNNER_CONFIG),
                "--dispatch-file",
                str(cli_packet),
                "--output",
                str(cli_output),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
            check=False,
        )
        assert cli.returncode == 0, cli.stdout
        assert json.loads(cli.stdout)["status"] == "prepared"
        assert MARKER in cli_output.read_text(encoding="utf-8")

        config = yaml.safe_load(RUNNER_CONFIG.read_text(encoding="utf-8"))
        config["runner"].pop("kind")
        broken = root / "broken.yaml"
        broken.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        expect_failure(broken, packet, project, "lacks runner kind")

        config = yaml.safe_load(RUNNER_CONFIG.read_text(encoding="utf-8"))
        config["dispatch_contract"]["process_reference"] = "bootstrap/missing.md"
        missing = root / "missing.yaml"
        missing.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        expect_failure(missing, packet, project, "root_workflow is missing")

        duplicate = root / "duplicate.md"
        duplicate.write_text(f"<!-- {MARKER} -->\n", encoding="utf-8")
        expect_failure(RUNNER_CONFIG, duplicate, project, "already contains")

    subprocess.run([sys.executable, "-m", "py_compile", str(SCRIPT)], check=True)
    print('{"status":"DISPATCH_CONTRACT_TESTS_PASSED"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
