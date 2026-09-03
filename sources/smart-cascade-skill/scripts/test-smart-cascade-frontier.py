#!/usr/bin/env python3
"""Deterministic checks for the Smart Cascade queue frontier."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bootstrap" / "frontier.py"

QUEUE = """
[[slices]]
id = "foundation"
depends_on = []
scope = "foundation"
checks = ["true"]

[[slices]]
id = "independent"
depends_on = []
scope = "independent"
checks = ["true"]

[[slices]]
id = "overlap-a"
depends_on = []
scope = "overlap a"
checks = ["true"]

[[slices]]
id = "overlap-b"
depends_on = []
scope = "overlap b"
checks = ["true"]

[[slices]]
id = "dependent"
depends_on = ["foundation"]
scope = "dependent"
checks = ["true"]
"""


def run(queue: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(queue), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="smart-cascade-frontier-") as raw:
        queue = Path(raw) / "queue.toml"
        queue.write_text(QUEUE, encoding="utf-8")

        # Without declared shared resources every dependency-ready slice runs in
        # parallel; worktree isolation, not a static path declaration, is what
        # keeps concurrent slices from colliding.
        initial = run(queue)
        assert initial.returncode == 0, initial.stdout
        payload = json.loads(initial.stdout)
        assert payload["selected"] == ["foundation", "independent", "overlap-a", "overlap-b"], payload
        assert payload["serialization_reasons"]["dependent"] == "dependencies_not_integrated:foundation"

        running = json.loads(run(queue, "--active", "independent").stdout)
        assert running["selected"] == ["foundation", "overlap-a", "overlap-b"], running

        advanced = json.loads(run(queue, "--integrated", "foundation", "--active", "independent").stdout)
        assert advanced["selected"] == ["overlap-a", "overlap-b", "dependent"], advanced

        # A declared shared mutable resource is the only remaining static reason
        # to serialize two dependency-ready slices.
        shared = json.loads(run(
            queue,
            "--shared-resource", "independent=git-index",
            "--shared-resource", "foundation=git-index",
        ).stdout)
        assert "foundation" in shared["selected"]
        assert "independent" not in shared["selected"]
        assert shared["serialization_reasons"]["independent"] == "shared_resource_overlap:foundation"

        shared_active = json.loads(run(
            queue,
            "--active", "independent",
            "--shared-resource", "independent=coverage-dir",
            "--shared-resource", "dependent=coverage-dir",
            "--integrated", "foundation",
        ).stdout)
        assert "dependent" not in shared_active["selected"]
        assert shared_active["serialization_reasons"]["dependent"] == "shared_resource_overlap:independent"

        # The maximum independent set still picks the two slices that avoid the
        # shared resource over the single slice that claims it.
        exact_queue = Path(raw) / "exact.toml"
        exact_queue.write_text("""
[[slices]]
id = "wide"
depends_on = []
scope = "wide conflict"
checks = ["true"]

[[slices]]
id = "narrow-a"
depends_on = []
scope = "narrow a"
checks = ["true"]

[[slices]]
id = "narrow-b"
depends_on = []
scope = "narrow b"
checks = ["true"]
""", encoding="utf-8")
        exact = json.loads(run(
            exact_queue,
            "--shared-resource", "wide=resource-a",
            "--shared-resource", "wide=resource-b",
            "--shared-resource", "narrow-a=resource-a",
            "--shared-resource", "narrow-b=resource-b",
        ).stdout)
        assert exact["selected"] == ["narrow-a", "narrow-b"], exact

        large_queue = Path(raw) / "large.toml"
        large_queue.write_text("\n".join(
            f'[[slices]]\nid = "slice-{index}"\ndepends_on = []\nscope = "slice {index}"\nchecks = ["true"]\n'
            for index in range(21)
        ), encoding="utf-8")
        bounded = run(large_queue)
        assert bounded.returncode != 0 and "exact maximum frontier is limited to 20" in bounded.stdout

        blocked = json.loads(run(queue, "--blocked", "foundation").stdout)
        assert "independent" in blocked["selected"] and "overlap-a" in blocked["selected"]
        assert blocked["serialization_reasons"]["dependent"] == "dependencies_not_integrated:foundation"

        invalid = run(queue, "--active", "missing")
        assert invalid.returncode != 0 and "unknown active slice IDs" in invalid.stdout

        # A queue that still declares the retired write_set field is rejected
        # rather than silently ignored.
        legacy_queue = Path(raw) / "legacy.toml"
        legacy_queue.write_text(
            '[[slices]]\nid = "legacy"\ndepends_on = []\nscope = "legacy"\nwrite_set = ["src/**"]\nchecks = ["true"]\n',
            encoding="utf-8",
        )
        legacy = run(legacy_queue)
        assert legacy.returncode != 0 and "write_set" in legacy.stdout, legacy.stdout

    subprocess.run([sys.executable, "-m", "py_compile", str(SCRIPT)], check=True)
    print('{"status":"FRONTIER_TESTS_PASSED"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
