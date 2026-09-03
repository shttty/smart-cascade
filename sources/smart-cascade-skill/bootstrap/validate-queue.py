#!/usr/bin/env python3
"""Validate the static Smart Cascade TOML queue.

This validator deliberately knows nothing about runtime status, attempts,
runner identities, or worktree lifecycle. Those facts belong to production
owners, not to `.smart-cascade/queue.toml`.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, TypeGuard

SLICE_KEYS = {
    "id",
    "depends_on",
    "scope",
    "checks",
}
ROOT_KEYS = {"slices"}
FORBIDDEN_KEYS = {
    "schema_version",
    "queue_id",
    "status",
    "title",
    "execution_class",
    "execution_classes",
    "attempts",
    "worktree",
    "runner",
    "candidate",
    "execution_mode",
    "git_authority",
    "root_coordinator",
    "write_set",
}
ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def is_string_list(value: Any) -> TypeGuard[list[str]]:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def normalize_repo_path(raw: Any, path: str, *, prefix_only: bool = False) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    if "\x00" in raw or "\\" in raw:
        return None
    if raw.startswith("/") or raw.endswith("/"):
        return None

    is_prefix = raw.endswith("/**")
    if is_prefix:
        raw = raw[:-3]
    elif prefix_only:
        return None

    # The only permitted glob syntax is the terminal `/**` directory prefix.
    if any(char in raw for char in "*?[]{}"):
        return None
    if not raw or raw.startswith("/"):
        return None
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    normalized = posixpath.normpath("/".join(parts))
    if normalized != "/".join(parts):
        return None
    return normalized + "/**" if is_prefix else normalized


def path_matches(left: str, right: str) -> bool:
    """Return whether two normalized exact/prefix entries overlap."""
    left_prefix = left.endswith("/**")
    right_prefix = right.endswith("/**")
    left_base = left[:-3] if left_prefix else left
    right_base = right[:-3] if right_prefix else right
    if left_base == right_base:
        return True
    if left_prefix and (right_base == left_base or right_base.startswith(left_base + "/")):
        return True
    if right_prefix and (left_base == right_base or left_base.startswith(right_base + "/")):
        return True
    return False


def path_contains(container: str, child: str) -> bool:
    """Return whether a normalized parent prefix contains a child prefix."""
    if not container.endswith("/**") or not child.endswith("/**"):
        return False
    container_base = container[:-3]
    child_base = child[:-3]
    return child_base == container_base or child_base.startswith(container_base + "/")


def reaches(graph: dict[str, set[str]], start: str, target: str) -> bool:
    pending = list(graph.get(start, set()))
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(graph.get(current, set()))
    return False


def validate_queue(document: Any, source: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    notices: list[dict[str, str]] = []
    if not isinstance(document, dict):
        return [error("$", "queue must be a TOML table")], notices

    unknown_root = set(document) - ROOT_KEYS - FORBIDDEN_KEYS
    for key in sorted(unknown_root):
        errors.append(error(key, "unknown top-level field"))
    forbidden_root = sorted(set(document) & FORBIDDEN_KEYS)
    for key in forbidden_root:
        errors.append(error(key, "runtime or legacy field is not allowed in static queue"))

    slices = document.get("slices")
    if not isinstance(slices, list) or not slices:
        errors.append(error("slices", "must be a non-empty array of tables"))
        return errors, notices

    ids: set[str] = set()
    dependencies: dict[str, set[str]] = {}

    for index, item in enumerate(slices):
        prefix = f"slices[{index}]"
        if not isinstance(item, dict):
            errors.append(error(prefix, "must be a TOML table"))
            continue

        unknown = set(item) - SLICE_KEYS - FORBIDDEN_KEYS
        for key in sorted(unknown):
            errors.append(error(f"{prefix}.{key}", "unknown slice field"))
        forbidden = sorted(set(item) & FORBIDDEN_KEYS)
        for key in forbidden:
            errors.append(error(f"{prefix}.{key}", "runtime or legacy field is not allowed in static queue"))

        slice_id = item.get("id")
        if not isinstance(slice_id, str) or not ID_RE.fullmatch(slice_id):
            errors.append(error(f"{prefix}.id", "must be a lowercase kebab-case stable ID"))
            slice_id = f"<invalid-{index}>"
        elif slice_id in ids:
            errors.append(error(f"{prefix}.id", f"duplicate slice ID: {slice_id}"))
        ids.add(slice_id)

        deps = item.get("depends_on")
        if not is_string_list(deps):
            errors.append(error(f"{prefix}.depends_on", "must be an array of strings"))
            deps_list: list[str] = []
        else:
            deps_list = deps
        dependencies[slice_id] = set(deps_list)

        scope = item.get("scope")
        if not isinstance(scope, str) or not scope.strip():
            errors.append(error(f"{prefix}.scope", "must be a non-empty string"))

        checks = item.get("checks")
        if not is_string_list(checks) or not checks or any(not check.strip() for check in checks):
            errors.append(error(f"{prefix}.checks", "must be a non-empty array of non-empty strings"))

    for slice_id, deps in dependencies.items():
        if slice_id.startswith("<invalid-"):
            continue
        for dependency in sorted(deps):
            if dependency not in ids:
                errors.append(error(f"slices[{slice_id}].depends_on", f"unknown dependency: {dependency}"))
        if slice_id in deps:
            errors.append(error(f"slices[{slice_id}].depends_on", "slice cannot depend on itself"))

    for slice_id in sorted(ids):
        if slice_id.startswith("<invalid-"):
            continue
        if reaches(dependencies, slice_id, slice_id):
            errors.append(error(f"slices[{slice_id}].depends_on", "dependency cycle detected"))

    return errors, notices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue", type=Path)
    args = parser.parse_args()

    try:
        with args.queue.open("rb") as handle:
            document = tomllib.load(handle)
    except FileNotFoundError:
        result = {"status": "BLOCKED", "errors": [error(str(args.queue), "file not found")], "notices": []}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    except (OSError, tomllib.TOMLDecodeError) as exc:
        result = {"status": "BLOCKED", "errors": [error(str(args.queue), f"invalid TOML: {exc}")], "notices": []}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1

    errors, notices = validate_queue(document, str(args.queue))
    result = {
        "status": "BLOCKED" if errors else "QUEUE_VALID",
        "queue": str(args.queue),
        "slice_count": len(document.get("slices", [])) if isinstance(document, dict) and isinstance(document.get("slices"), list) else 0,
        "errors": errors,
        "notices": notices,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
