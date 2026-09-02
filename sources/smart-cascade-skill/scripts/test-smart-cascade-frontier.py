#!/usr/bin/env python3
"""Focused tests for maximum-safe Smart Cascade frontier selection."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "bootstrap/frontier.py"

QUEUE = """
[[slices]]
id = "foundation"
depends_on = []
scope = "foundation"
write_set = ["src/foundation/**"]
checks = ["true"]

[[slices]]
id = "independent"
depends_on = []
scope = "independent"
write_set = ["src/independent/**"]
checks = ["true"]

[[slices]]
id = "overlap-a"
depends_on = []
scope = "overlap a"
write_set = ["src/shared/**"]
checks = ["true"]

[[slices]]
id = "overlap-b"
depends_on = []
scope = "overlap b"
write_set = ["src/shared/file.ts"]
checks = ["true"]

[[slices]]
id = "dependent"
depends_on = ["foundation"]
scope = "dependent"
write_set = ["src/dependent/**"]
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

        initial = run(queue)
        assert initial.returncode == 0, initial.stdout
        payload = json.loads(initial.stdout)
        assert payload["selected"] == ["foundation", "independent", "overlap-a"]
        assert payload["serialization_reasons"]["overlap-b"] == "write_set_overlap:overlap-a"
        assert payload["serialization_reasons"]["dependent"] == "dependencies_not_integrated:foundation"

        running = json.loads(run(queue, "--active", "independent").stdout)
        assert running["selected"] == ["foundation", "overlap-a"]

        advanced = json.loads(run(queue, "--integrated", "foundation", "--active", "independent").stdout)
        assert advanced["selected"] == ["overlap-a", "dependent"]

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

        exact_queue = Path(raw) / "exact.toml"
        exact_queue.write_text("""
[[slices]]
id = "wide"
depends_on = []
scope = "wide conflict"
write_set = ["src/a/**", "src/b/**"]
checks = ["true"]

[[slices]]
id = "narrow-a"
depends_on = []
scope = "narrow a"
write_set = ["src/a/**"]
checks = ["true"]

[[slices]]
id = "narrow-b"
depends_on = []
scope = "narrow b"
write_set = ["src/b/**"]
checks = ["true"]
""", encoding="utf-8")
        exact = json.loads(run(exact_queue).stdout)
        assert exact["selected"] == ["narrow-a", "narrow-b"]

        large_queue = Path(raw) / "large.toml"
        large_queue.write_text("\n".join(
            f'[[slices]]\nid = "slice-{index}"\ndepends_on = []\nscope = "slice {index}"\nwrite_set = ["src/{index}/**"]\nchecks = ["true"]\n'
            for index in range(21)
        ), encoding="utf-8")
        bounded = run(large_queue)
        assert bounded.returncode != 0 and "exact maximum frontier is limited to 20" in bounded.stdout

        blocked = json.loads(run(queue, "--blocked", "foundation").stdout)
        assert "independent" in blocked["selected"] and "overlap-a" in blocked["selected"]
        assert blocked["serialization_reasons"]["dependent"] == "dependencies_not_integrated:foundation"

        invalid = run(queue, "--active", "missing")
        assert invalid.returncode != 0 and "unknown active slice IDs" in invalid.stdout

    subprocess.run([sys.executable, "-m", "py_compile", str(SCRIPT)], check=True)
    print('{"status":"FRONTIER_TESTS_PASSED"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
