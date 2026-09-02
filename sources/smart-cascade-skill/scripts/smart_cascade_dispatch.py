#!/usr/bin/env python3
"""Attach the current Smart Cascade contract to one Root packet.

This helper is control-plane transport evidence. It does not read or mutate a
run/state.json file and it does not create or own production worktrees.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

sys.dont_write_bytecode = True

import yaml

MARKER = "SMART_CASCADE_DISPATCH_CONTRACT_V3"


class DispatchContractError(RuntimeError):
    """Raised when the selected source contract cannot be verified."""


@dataclass(frozen=True)
class ResourceIdentity:
    role: str
    path: Path
    sha256: str
    bytes: int
    declared_name: str | None = None


@dataclass(frozen=True)
class DispatchBundle:
    text: str
    sha256: str
    bytes: int
    root_workflow: ResourceIdentity
    runner_interface: ResourceIdentity

@dataclass(frozen=True)
class WorktreeSnapshot:
    sha256: str
    paths: tuple[str, ...]


def _git_bytes(project_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=project_root, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=30, check=False,
    )
    if result.returncode != 0:
        fail(f"blocked_environment: cannot inspect worktree snapshot: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def _excluded_snapshot_path(raw: bytes) -> bool:
    return raw in {b".smart-cascade/control", b".smart-cascade/state", b".smart-cascade/override.yaml"} or raw.startswith(
        (b".smart-cascade/control/", b".smart-cascade/state/")
    )


def _hash_field(digest: Any, label: bytes, value: bytes) -> None:
    digest.update(len(label).to_bytes(4, "big"))
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _hash_worktree_node(digest: Any, path: Path, relative: bytes = b"") -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        _hash_field(digest, b"node", relative + b"\0missing")
        return
    except OSError as exc:
        fail(f"blocked_environment: cannot stat worktree snapshot path {path}: {exc}")
    mode = stat.S_IMODE(info.st_mode).to_bytes(4, "big")
    if stat.S_ISREG(info.st_mode):
        _hash_field(digest, b"node", relative + b"\0file\0" + mode)
        try:
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    _hash_field(digest, b"bytes", chunk)
        except OSError as exc:
            fail(f"blocked_environment: cannot read worktree snapshot path {path}: {exc}")
        return
    if stat.S_ISLNK(info.st_mode):
        try:
            target = os.fsencode(os.readlink(path))
        except OSError as exc:
            fail(f"blocked_environment: cannot read worktree snapshot symlink {path}: {exc}")
        _hash_field(digest, b"node", relative + b"\0symlink\0" + mode + b"\0" + target)
        return
    if stat.S_ISDIR(info.st_mode):
        _hash_field(digest, b"node", relative + b"\0directory\0" + mode)
        try:
            entries = sorted(path.iterdir(), key=lambda item: os.fsencode(item.name))
        except OSError as exc:
            fail(f"blocked_environment: cannot list worktree snapshot directory {path}: {exc}")
        for child in entries:
            if child.name == ".git":
                continue
            child_name = os.fsencode(child.name)
            _hash_worktree_node(digest, child, relative + b"/" + child_name)
        return
    fail(f"blocked_environment: worktree snapshot path has unsupported file type: {path}")


def worktree_snapshot(project_root: Path) -> WorktreeSnapshot:
    project_root = project_root.resolve()
    changed: set[bytes] = set()
    for args in (
        ("diff", "--name-only", "-z", "--no-renames", "--cached", "HEAD", "--"),
        ("diff", "--name-only", "-z", "--no-renames", "--"),
        ("ls-files", "--others", "-z", "--"),
    ):
        changed.update(path for path in _git_bytes(project_root, *args).split(b"\0") if path and not _excluded_snapshot_path(path))

    index: dict[bytes, list[bytes]] = {}
    for record in _git_bytes(project_root, "ls-files", "--stage", "-z", "--").split(b"\0"):
        if not record or b"\t" not in record:
            continue
        metadata, path = record.split(b"\t", 1)
        if path in changed:
            index.setdefault(path, []).append(metadata)

    digest = hashlib.sha256()
    _hash_field(digest, b"schema", b"smart-cascade-worktree-snapshot-v1")
    for raw_path in sorted(changed):
        _hash_field(digest, b"path", raw_path)
        for metadata in sorted(index.get(raw_path, [])):
            _hash_field(digest, b"index", metadata)
        _hash_worktree_node(digest, project_root / os.fsdecode(raw_path))
    return WorktreeSnapshot(
        sha256="sha256:" + digest.hexdigest(),
        paths=tuple(os.fsdecode(path) for path in sorted(changed)),
    )


def fail(message: str) -> NoReturn:
    raise DispatchContractError(message)


def digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def read_regular(path: Path, label: str) -> bytes:
    if not path.is_file():
        fail(f"blocked_environment: {label} is missing or not a regular file: {path}")
    return path.read_bytes()


def declared_agent_name(raw: bytes) -> str | None:
    text = raw.decode("utf-8", errors="strict")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    match = re.search(r"(?m)^name:\s*([^\s#]+)\s*$", text[4:end])
    return match.group(1) if match else None


def resolve_path(value: Any, label: str, base: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        fail(f"blocked_environment: dispatch_contract.{label} must be a non-empty path")
    expanded = Path(os.path.expandvars(os.path.expanduser(value)))
    return (expanded if expanded.is_absolute() else base / expanded).resolve()


def identity(role: str, path: Path, expected_name: str | None = None) -> ResourceIdentity:
    raw = read_regular(path, role)
    declared = declared_agent_name(raw) if expected_name is not None else None
    if expected_name is not None and declared != expected_name:
        fail(f"blocked_environment: {role} declares agent name {declared!r}, expected {expected_name!r}: {path}")
    return ResourceIdentity(role=role, path=path, sha256=digest_bytes(raw), bytes=len(raw), declared_name=declared)


def load_config(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"blocked_environment: runner config is missing: {path}")
    if not isinstance(loaded, dict):
        fail("blocked_environment: runner config root must be a mapping")
    return loaded


def build_bundle(config_path: Path, dispatch_path: Path, project_root: Path | None = None) -> DispatchBundle:
    config_path = config_path.resolve()
    dispatch_path = dispatch_path.resolve()
    project_root = (project_root or Path.cwd()).resolve()
    skill_root = Path(__file__).resolve().parent.parent
    config = load_config(config_path)
    runner = config.get("runner")
    if not isinstance(runner, dict) or not isinstance(runner.get("kind"), str) or not runner["kind"]:
        fail("blocked_environment: runner config lacks runner kind")
    contract = config.get("dispatch_contract")
    if not isinstance(contract, dict):
        fail("blocked_environment: runner config lacks dispatch_contract")
    root_workflow = identity("root_workflow", resolve_path(contract.get("process_reference"), "process_reference", skill_root))
    runner_interface = identity("runner_interface", resolve_path(runner.get("interface"), "runner.interface", skill_root))
    original = read_regular(dispatch_path, "Root dispatch packet").decode("utf-8", errors="strict").strip()
    if not original:
        fail(f"Root dispatch packet is empty: {dispatch_path}")
    if MARKER in original:
        fail("Root dispatch packet already contains an attached Smart Cascade contract")

    manifest = {
        "schema_version": 3,
        "marker": MARKER,
        "runner_kind": runner["kind"],
        "root_workflow": {"path": str(root_workflow.path), "sha256": root_workflow.sha256, "bytes": root_workflow.bytes},
        "runner_interface": {"path": str(runner_interface.path), "sha256": runner_interface.sha256, "bytes": runner_interface.bytes},
    }
    attachment = (
        f"<!-- {MARKER} -->\n"
        "# Smart Cascade dispatch attachment\n\n"
        "Before any production action, read the exact `root_workflow.path` and `runner_interface.path` below. "
        "Verify their bytes against the recorded SHA-256 values. They define the platform-neutral Root authority and runner seam. "
        "If either resource is unreadable or its digest differs, stop as `BLOCKED_ENVIRONMENT`. The selected runner config and its adapter receipt define only runtime projection; Root remains the sole scheduler, acceptance authority, and production Git owner.\n\n"
        "```json\n" + json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n```"
    )
    text = original + "\n\n---\n\n" + attachment + "\n"
    raw = text.encode("utf-8")
    return DispatchBundle(
        text=text,
        sha256=digest_bytes(raw),
        bytes=len(raw),
        root_workflow=root_workflow,
        runner_interface=runner_interface,
    )


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def metadata(bundle: DispatchBundle, output_path: Path) -> dict[str, Any]:
    return {
        "kind": "root_dispatch_prepared",
        "status": "prepared",
        "packet_path": str(output_path),
        "packet_digest": bundle.sha256,
        "packet_bytes": bundle.bytes,
        "root_workflow": {"path": str(bundle.root_workflow.path), "sha256": bundle.root_workflow.sha256, "bytes": bundle.root_workflow.bytes},
        "runner_interface": {"path": str(bundle.runner_interface.path), "sha256": bundle.runner_interface.sha256, "bytes": bundle.runner_interface.bytes},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--runner-config", required=True)
    parser.add_argument("--dispatch-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    bundle = build_bundle(
        Path(args.runner_config),
        Path(args.dispatch_file),
        Path(args.project_root) if args.project_root else None,
    )
    output = Path(args.output).resolve()
    write_atomic(output, bundle.text)
    print(json.dumps(metadata(bundle, output), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DispatchContractError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, separators=(",", ":")))
        raise SystemExit(1)
