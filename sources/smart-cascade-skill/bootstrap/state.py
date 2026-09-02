#!/usr/bin/env python3
"""Atomically read and increment Smart Cascade rework counters."""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import NoReturn

ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class StateError(RuntimeError):
    pass


def fail(message: str) -> NoReturn:
    raise StateError(message)


def state_root() -> Path:
    configured = os.environ.get("SMART_CASCADE_STATE_DIR")
    if configured:
        return Path(configured).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        fail("SMART_CASCADE_STATE_DIR is unset and the production Git common directory is unavailable")
    common_dir = Path(result.stdout.strip()).resolve()
    if not common_dir.is_dir():
        fail(f"production Git common directory is unavailable: {common_dir}")
    return common_dir.parent / ".smart-cascade" / "state"


def validate_id(value: str, label: str) -> str:
    if not ID_RE.fullmatch(value):
        fail(f"{label} must be a lowercase kebab-case stable ID")
    return value


def state_path(namespace: str, slice_id: str) -> Path:
    root = state_root()
    return root / "state.toml" if namespace == "slice" else root / slice_id / "state.toml"


def load(path: Path, table_name: str) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        fail(f"malformed state file {path}: {exc}")
    if set(document) != {table_name} or not isinstance(document[table_name], dict):
        fail(f"malformed state file {path}: expected only [{table_name}.*] tables")
    result: dict[str, int] = {}
    for key, value in document[table_name].items():
        if not isinstance(key, str) or not ID_RE.fullmatch(key):
            fail(f"malformed state file {path}: invalid ID {key!r}")
        if not isinstance(value, dict) or set(value) != {"rework"}:
            fail(f"malformed state file {path}: {table_name}.{key} must contain only rework")
        count = value["rework"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            fail(f"malformed state file {path}: {table_name}.{key}.rework must be a non-negative integer")
        result[key] = count
    return result


def render(table_name: str, counters: dict[str, int]) -> str:
    lines: list[str] = []
    for key in sorted(counters):
        lines.extend((f'[{table_name}."{key}"]', f"rework = {counters[key]}", ""))
    return "\n".join(lines)


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def execute(namespace: str, command: str, slice_id: str, child_id: str | None) -> str:
    validate_id(slice_id, "slice-id")
    table_name = "slices" if namespace == "slice" else "children"
    key = slice_id if namespace == "slice" else validate_id(child_id or "", "child-id")
    path = state_path(namespace, slice_id)
    label = slice_id if namespace == "slice" else f"{slice_id}/{key}"
    if command == "get":
        return f"{label} rework={load(path, table_name).get(key, 0)}"

    path.parent.mkdir(parents=True, exist_ok=True)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        counters = load(path, table_name)
        current = counters.get(key, 0) + 1
        counters[key] = current
        write_atomic(path, render(table_name, counters))
    finally:
        fcntl.flock(directory_fd, fcntl.LOCK_UN)
        os.close(directory_fd)
    action = "continue"
    if current % 3 == 0:
        action = "suggest_advisor" if namespace == "slice" else "upgrade_executor"
    return f"{label} rework={current} action={action}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="namespace", required=True)
    for namespace in ("slice", "child"):
        sub = subparsers.add_parser(namespace)
        sub.add_argument("command", choices=("get", "rework"))
        sub.add_argument("slice_id")
        if namespace == "child":
            sub.add_argument("child_id")
    args = parser.parse_args()
    print(execute(args.namespace, args.command, args.slice_id, getattr(args, "child_id", None)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StateError as exc:
        print(f"state error: {exc}", file=sys.stderr)
        raise SystemExit(1)
