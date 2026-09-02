#!/usr/bin/env python3
"""Deterministic reference adapter for the Smart Cascade runner seam."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NoReturn

sys.dont_write_bytecode = True


class FakeRunnerError(RuntimeError):
    pass


def fail(message: str) -> NoReturn:
    raise FakeRunnerError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{label} is unreadable or invalid JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    run = sub.add_parser("normalize")
    run.add_argument("--packet", type=Path, required=True)
    run.add_argument("--settlement", type=Path, required=True)
    run.add_argument("--artifact", type=Path)
    run.add_argument("--outcome", choices=("completed", "failed-preserved", "failed-lost"), required=True)
    run.add_argument("--reason", default="deterministic fake runner failure")
    args = parser.parse_args()
    if args.command == "check":
        print(json.dumps({"schema_version": 1, "status": "ADAPTER_READY", "adapter": "fake"}, separators=(",", ":")))
        return 0
    load(args.packet, "packet")
    settlement = load(args.settlement, "settlement")
    if args.outcome in {"completed", "failed-preserved"}:
        if args.artifact is None or not args.artifact.is_file():
            fail("selected fake outcome requires one artifact file")
        artifact: dict[str, str] | None = {"kind": "git_patch", "path": str(args.artifact.resolve())}
    else:
        if args.artifact is not None:
            fail("failed-lost must not receive an artifact")
        artifact = None
    result = {
        "schema_version": 1,
        "status": "completed" if args.outcome == "completed" else "failed",
        "artifact": artifact,
        "settlement": settlement,
        "reason": None if args.outcome == "completed" else args.reason,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FakeRunnerError as exc:
        print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "adapter": "fake", "reason": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
