#!/usr/bin/env python3
"""Compute Smart Cascade's maximum safe queue frontier without persisting runtime state."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tomllib
from pathlib import Path
from typing import Any, NoReturn


MAX_EXACT_FRONTIER = 20

class FrontierError(RuntimeError):
    pass


def fail(message: str) -> NoReturn:
    raise FrontierError(message)


def validator_module(script: Path) -> Any:
    spec = importlib.util.spec_from_file_location("smart_cascade_queue_validator", script)
    if spec is None or spec.loader is None:
        fail(f"cannot load queue validator: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def maximum_frontier(
    slices: list[dict[str, Any]],
    integrated: set[str],
    active: set[str],
    blocked: set[str],
    shared_resources: dict[str, set[str]],
) -> dict[str, Any]:
    by_id = {item["id"]: item for item in slices}
    known = set(by_id)
    for label, values in (("integrated", integrated), ("active", active), ("blocked", blocked)):
        unknown = sorted(values - known)
        if unknown:
            fail(f"unknown {label} slice IDs: {', '.join(unknown)}")
    if integrated & active or integrated & blocked or active & blocked:
        fail("integrated, active, and blocked slice sets must be disjoint")
    unknown_resources = sorted(set(shared_resources) - known)
    if unknown_resources:
        fail(f"unknown shared-resource slice IDs: {', '.join(unknown_resources)}")

    def resource_overlap(left: str, right: str) -> bool:
        return bool(shared_resources.get(left, set()) & shared_resources.get(right, set()))

    def conflicts(left: str, right: str) -> bool:
        return resource_overlap(left, right)

    dependency_ready = [
        item["id"]
        for item in slices
        if item["id"] not in integrated | active | blocked and set(item["depends_on"]) <= integrated
    ]
    eligible = [
        slice_id
        for slice_id in dependency_ready
        if not any(conflicts(slice_id, active_id) for active_id in active)
    ]
    if len(eligible) > MAX_EXACT_FRONTIER:
        fail(
            f"exact maximum frontier is limited to {MAX_EXACT_FRONTIER} dependency-ready slices; "
            "reduce the observed frontier or reason directly with equivalent safety evidence"
        )

    selected: list[str] = []

    def search(index: int, candidate: list[str]) -> None:
        nonlocal selected
        if len(candidate) + len(eligible) - index <= len(selected):
            return
        if index == len(eligible):
            selected = candidate.copy()
            return
        slice_id = eligible[index]
        if not any(conflicts(slice_id, chosen) for chosen in candidate):
            candidate.append(slice_id)
            search(index + 1, candidate)
            candidate.pop()
        search(index + 1, candidate)

    search(0, [])

    reasons: dict[str, str] = {}

    selected_set = set(selected)
    for item in slices:
        slice_id = item["id"]
        if slice_id in integrated:
            reasons[slice_id] = "integrated"
        elif slice_id in active:
            reasons[slice_id] = "active"
        elif slice_id in blocked:
            reasons[slice_id] = "blocked"
        else:
            missing = sorted(set(item["depends_on"]) - integrated)
            if missing:
                reasons[slice_id] = f"dependencies_not_integrated:{','.join(missing)}"
            elif slice_id not in selected_set:
                conflicting_active = sorted(active_id for active_id in active if conflicts(slice_id, active_id))
                conflicting_selected = sorted(chosen for chosen in selected if conflicts(slice_id, chosen))
                conflicts_with = conflicting_active or conflicting_selected
                reasons[slice_id] = f"shared_resource_overlap:{','.join(conflicts_with)}"

    return {
        "status": "FRONTIER_READY",
        "selected": list(selected),
        "dependency_ready": dependency_ready,
        "serialization_reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue", type=Path)
    parser.add_argument("--integrated", action="append", default=[])
    parser.add_argument("--active", action="append", default=[])
    parser.add_argument("--blocked", action="append", default=[])
    parser.add_argument(
        "--shared-resource",
        action="append",
        default=[],
        metavar="SLICE_ID=RESOURCE",
        help="observed mutable resource shared by a slice; repeat for multiple bindings",
    )
    args = parser.parse_args()

    validator_path = Path(__file__).with_name("validate-queue.py")
    validator = validator_module(validator_path)
    try:
        with args.queue.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        fail(f"cannot read queue: {exc}")
    errors, _ = validator.validate_queue(document, str(args.queue))
    if errors:
        fail(f"queue is invalid: {json.dumps(errors, ensure_ascii=False, sort_keys=True)}")
    resources: dict[str, set[str]] = {}
    for binding in args.shared_resource:
        slice_id, separator, resource = binding.partition("=")
        if not separator or not resource:
            fail("--shared-resource must be SLICE_ID=RESOURCE")
        resources.setdefault(slice_id, set()).add(resource)
    result = maximum_frontier(
        document["slices"], set(args.integrated), set(args.active), set(args.blocked), resources
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FrontierError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
