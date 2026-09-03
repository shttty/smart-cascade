#!/usr/bin/env python3
"""Tests for the to-tickets -> queue converter.

The conversion is mechanical, so the tests pin the mechanics: field mapping,
dependency resolution, and — most importantly — that bad input is refused
instead of silently producing a partial queue.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

BOOTSTRAP = Path(__file__).resolve().parent.parent / "bootstrap"
TO_QUEUE = BOOTSTRAP / "to-queue.py"
VALIDATE = BOOTSTRAP / "validate-queue.py"

LOCAL_TICKET = """# {num}: {title}

**What to build:** {scope}

**Blocked by:** {blocked}

**Status:** ready-for-agent

{criteria}
"""

HEADING_TICKET = """# {num}: {title}

## What to build

{scope}

## Acceptance criteria

{criteria}

## Blocked by

- {blocked}
"""


def write_tickets(root: Path, tickets: list[tuple[str, str]]) -> Path:
    issues = root / "issues"
    issues.mkdir(parents=True, exist_ok=True)
    for name, body in tickets:
        (issues / name).write_text(body, encoding="utf-8")
    return issues


def run(issues: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TO_QUEUE), str(issues), *extra],
        capture_output=True,
        text=True,
    )


def test_local_template_maps_every_field() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        issues = write_tickets(
            Path(tmp),
            [
                (
                    "01-session-token-issuing.md",
                    LOCAL_TICKET.format(
                        num="01",
                        title="Session token issuing",
                        scope="A user who posts valid credentials receives a signed session token.",
                        blocked="None (can start immediately)",
                        criteria="- [ ] Valid credentials return a signed token\n- [ ] Invalid credentials return 401",
                    ),
                ),
                (
                    "02-token-refresh.md",
                    LOCAL_TICKET.format(
                        num="02",
                        title="Token refresh",
                        scope="An expiring token can be exchanged for a fresh one.",
                        blocked="01",
                        criteria="- [ ] An unexpired token yields a new token",
                    ),
                ),
            ],
        )
        result = run(issues)
        assert result.returncode == 0, result.stderr
        queue = tomllib.loads(result.stdout)

        first, second = queue["slices"]
        # The numeric filename prefix must not leak into the slice id.
        assert first["id"] == "session-token-issuing", first
        assert first["depends_on"] == [], first
        assert first["scope"].startswith("A user who posts valid credentials"), first
        # Acceptance criteria transfer verbatim as acceptance targets.
        assert first["checks"] == [
            "Valid credentials return a signed token",
            "Invalid credentials return 401",
        ], first

        # A numeric "Blocked by" reference resolves to the real slice id.
        assert second["id"] == "token-refresh", second
        assert second["depends_on"] == ["session-token-issuing"], second


def test_heading_template_is_accepted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        issues = write_tickets(
            Path(tmp),
            [
                (
                    "01-expand-schema.md",
                    HEADING_TICKET.format(
                        num="01",
                        title="Expand schema",
                        scope="Add the new column alongside the old one.",
                        criteria="- [ ] Both columns exist\n- [ ] Existing readers are unaffected",
                        blocked="None (can start immediately)",
                    ),
                ),
                (
                    "02-migrate-callers.md",
                    HEADING_TICKET.format(
                        num="02",
                        title="Migrate callers",
                        scope="Move every call site onto the new column.",
                        criteria="- [ ] No caller references the old column",
                        blocked="01: Expand schema",
                    ),
                ),
            ],
        )
        result = run(issues)
        assert result.returncode == 0, result.stderr
        queue = tomllib.loads(result.stdout)
        first, second = queue["slices"]
        assert first["id"] == "expand-schema", first
        assert first["checks"] == ["Both columns exist", "Existing readers are unaffected"], first
        # A "NN: Title" reference resolves by number as well as by slug.
        assert second["depends_on"] == ["expand-schema"], second


def test_none_blocker_does_not_scavenge_checkboxes() -> None:
    """A 'Blocked by: None' ticket must not adopt its acceptance boxes as edges."""
    with tempfile.TemporaryDirectory() as tmp:
        issues = write_tickets(
            Path(tmp),
            [
                (
                    "01-standalone.md",
                    LOCAL_TICKET.format(
                        num="01",
                        title="Standalone",
                        scope="Something self-contained.",
                        blocked="None",
                        criteria="- [ ] It works\n- [ ] It keeps working",
                    ),
                )
            ],
        )
        result = run(issues)
        assert result.returncode == 0, result.stderr
        slice_ = tomllib.loads(result.stdout)["slices"][0]
        assert slice_["depends_on"] == [], slice_
        assert slice_["checks"] == ["It works", "It keeps working"], slice_


def test_natural_language_acceptance_targets_survive() -> None:
    """checks are acceptance targets: prose must pass through untouched."""
    with tempfile.TemporaryDirectory() as tmp:
        issues = write_tickets(
            Path(tmp),
            [
                (
                    "01-rename-symbol.md",
                    LOCAL_TICKET.format(
                        num="01",
                        title="Rename internal symbol",
                        scope="Rename an internal symbol with no behaviour change.",
                        blocked="None",
                        criteria="- [ ] 重构后外部行为保持不变\n- [ ] 现有测试套件无回归",
                    ),
                )
            ],
        )
        out = Path(tmp) / "queue.toml"
        result = run(issues, "-o", str(out))
        assert result.returncode == 0, result.stderr
        slice_ = tomllib.loads(out.read_text(encoding="utf-8"))["slices"][0]
        assert slice_["checks"] == ["重构后外部行为保持不变", "现有测试套件无回归"], slice_

        # A refactor slice with no runnable command still passes validation.
        validated = subprocess.run(
            [sys.executable, str(VALIDATE), str(out)],
            capture_output=True,
            text=True,
        )
        assert validated.returncode == 0, validated.stdout + validated.stderr
        assert json.loads(validated.stdout)["status"] == "QUEUE_VALID", validated.stdout


def test_generated_queue_passes_validation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        issues = write_tickets(
            Path(tmp),
            [
                (
                    "01-first.md",
                    LOCAL_TICKET.format(
                        num="01",
                        title="First",
                        scope="The first slice.",
                        blocked="None",
                        criteria="- [ ] first works",
                    ),
                ),
                (
                    "02-second.md",
                    LOCAL_TICKET.format(
                        num="02",
                        title="Second",
                        scope="The second slice.",
                        blocked="01",
                        criteria="- [ ] second works",
                    ),
                ),
            ],
        )
        out = Path(tmp) / "queue.toml"
        result = run(issues, "-o", str(out))
        assert result.returncode == 0, result.stderr

        validated = subprocess.run(
            [sys.executable, str(VALIDATE), str(out)],
            capture_output=True,
            text=True,
        )
        assert validated.returncode == 0, validated.stdout + validated.stderr
        report = json.loads(validated.stdout)
        assert report["status"] == "QUEUE_VALID", report
        assert report["slice_count"] == 2, report


def test_dangling_blocker_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        issues = write_tickets(
            Path(tmp),
            [
                (
                    "01-only.md",
                    LOCAL_TICKET.format(
                        num="01",
                        title="Only",
                        scope="The only ticket.",
                        blocked="07",
                        criteria="- [ ] it works",
                    ),
                )
            ],
        )
        out = Path(tmp) / "queue.toml"
        result = run(issues, "-o", str(out))
        assert result.returncode == 1, result.stdout
        assert "unresolved blocker" in result.stderr, result.stderr
        # A refused conversion must not leave a partial queue behind.
        assert not out.exists(), "converter wrote a queue despite an unresolved edge"


def test_missing_acceptance_criteria_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        issues = write_tickets(
            Path(tmp),
            [("01-bare.md", "# 01: Bare\n\n**What to build:** Nothing verifiable.\n\n**Blocked by:** None\n")],
        )
        result = run(issues)
        assert result.returncode == 1, result.stdout
        assert "no acceptance criteria" in result.stderr, result.stderr


def test_cycle_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        issues = write_tickets(
            Path(tmp),
            [
                (
                    "01-a.md",
                    LOCAL_TICKET.format(
                        num="01", title="A", scope="A.", blocked="02", criteria="- [ ] a"
                    ),
                ),
                (
                    "02-b.md",
                    LOCAL_TICKET.format(
                        num="02", title="B", scope="B.", blocked="01", criteria="- [ ] b"
                    ),
                ),
            ],
        )
        result = run(issues)
        assert result.returncode == 1, result.stdout
        assert "dependency cycle" in result.stderr, result.stderr


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(json.dumps({"status": "TO_QUEUE_TESTS_PASSED", "tests": len(tests)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
