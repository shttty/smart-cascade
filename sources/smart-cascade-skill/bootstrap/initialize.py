#!/usr/bin/env python3
"""Initialize and validate platform-neutral Smart Cascade core state."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

sys.dont_write_bytecode = True


class InitializationError(RuntimeError):
    pass


def fail(message: str) -> NoReturn:
    raise InitializationError(message)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{label} is unreadable or invalid JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--create-state", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    bootstrap = Path(__file__).resolve().parent
    manifest_path = bootstrap / "manifest.json"
    queue_path = project_root / ".smart-cascade" / "queue.toml"
    if not project_root.is_dir() or not bootstrap.is_dir():
        fail("project root or Smart Cascade bootstrap directory is missing")

    manifest = load_json(manifest_path, "core manifest")
    if set(manifest) != {"schema_version", "kind", "files", "state_directories", "candidate_artifact_kinds", "decisions"}:
        fail("core manifest must be one closed contract object")
    if manifest.get("schema_version") != 1 or manifest.get("kind") != "smart-cascade-core":
        fail("core manifest identity is invalid")
    required_files = manifest.get("files")
    state_directories = manifest.get("state_directories")
    if not isinstance(required_files, list) or any(not isinstance(item, str) or not item for item in required_files) or len(required_files) != len(set(required_files)):
        fail("core manifest files must be unique non-empty strings")
    for relative in required_files:
        resolved = (bootstrap / relative).resolve()
        if not resolved.is_relative_to(bootstrap):
            fail(f"core manifest file escapes bootstrap directory: {relative}")
    if not isinstance(state_directories, list) or not state_directories or any(not isinstance(item, str) or not item or Path(item).is_absolute() or ".." in Path(item).parts for item in state_directories) or len(state_directories) != len(set(state_directories)):
        fail("core manifest state directories must be unique project-relative paths")
    artifact_kinds = manifest.get("candidate_artifact_kinds")
    decisions = manifest.get("decisions")
    if not isinstance(artifact_kinds, list) or "git_patch" not in artifact_kinds or any(not isinstance(item, str) or not item for item in artifact_kinds):
        fail("core manifest must support git_patch candidate artifacts")
    if not isinstance(decisions, list) or decisions != ["PASS", "REWORK", "BLOCKED"]:
        fail("core manifest decision contract is invalid")
    for relative in required_files:
        path = (bootstrap / relative).resolve()
        if not path.is_file():
            fail(f"core file is missing: {relative}")

    queue = subprocess.run(
        [sys.executable, str(bootstrap / "validate-queue.py"), str(queue_path)],
        cwd=project_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    try:
        queue_result = json.loads(queue.stdout)
    except json.JSONDecodeError:
        fail("queue validator returned invalid JSON")
    if queue.returncode != 0 or not isinstance(queue_result, dict) or queue_result.get("status") != "QUEUE_VALID":
        fail(f"static queue validation failed: {queue.stdout.strip()}")

    state_root = project_root / ".smart-cascade"
    created: list[str] = []
    if args.create_state:
        for relative in state_directories:
            path = state_root / relative
            if not path.exists():
                path.mkdir(parents=True)
                created.append(relative)
            elif not path.is_dir():
                fail(f"core state path is not a directory: {relative}")
    else:
        for relative in state_directories:
            path = state_root / relative
            if path.exists() and not path.is_dir():
                fail(f"core state path is not a directory: {relative}")
    interface_path = bootstrap / "runner-interface.json"
    interface = load_json(interface_path, "runner interface")
    if set(interface) != {"schema_version", "kind", "operations", "runtime_control", "normalized_result"}:
        fail("runner interface must be one closed contract object")
    if interface.get("schema_version") != 1 or interface.get("kind") != "smart-cascade-runner-interface":
        fail("runner interface identity is invalid")
    operations = interface.get("operations")
    if not isinstance(operations, list) or not {"check", "normalize"} <= set(operations) or any(not isinstance(item, str) or not item for item in operations) or len(operations) != len(set(operations)) or interface.get("runtime_control") != "adapter_native":
        fail("runner interface must provide check and normalize through adapter-native control")
    normalized = interface.get("normalized_result")
    if not isinstance(normalized, dict) or set(normalized) != {"schema_version", "statuses", "artifact_kinds"} or normalized.get("schema_version") != 1:
        fail("runner interface normalized result shape is invalid")
    statuses = normalized.get("statuses")
    normalized_artifacts = normalized.get("artifact_kinds")
    if not isinstance(statuses, list) or not {"completed", "failed"} <= set(statuses) or any(not isinstance(item, str) or not item for item in statuses) or len(statuses) != len(set(statuses)):
        fail("runner interface normalized result statuses are invalid")
    if not isinstance(normalized_artifacts, list) or "git_patch" not in normalized_artifacts or any(not isinstance(item, str) or not item for item in normalized_artifacts):
        fail("runner interface normalized result artifacts are invalid")
    print(json.dumps({
        "status": "CORE_READY",
        "project_root": str(project_root),
        "manifest_digest": digest(manifest_path),
        "queue_digest": digest(queue_path),
        "runner_interface_digest": digest(interface_path),
        "queue_validation": queue_result,
        "created": created,
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InitializationError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        raise SystemExit(1)
