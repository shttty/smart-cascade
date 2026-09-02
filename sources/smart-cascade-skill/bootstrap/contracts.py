#!/usr/bin/env python3
"""Validate platform-neutral Smart Cascade packets and normalized runner results."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, NoReturn

sys.dont_write_bytecode = True


class ContractError(RuntimeError):
    pass


BLOCKER_STATUSES = {"BLOCKED", "BLOCKED_ENVIRONMENT", "BLOCKED_ARCHITECTURE"}
COMMON_PACKET_KEYS = {
    "role", "task_name", "slice_id", "attempt_id", "base", "write_set", "checks", "non_goals", "result_schema",
    "cumulative_patch", "rework_checklist", "rework_count",
}
PACKET_KEYS = {
    "leader": COMMON_PACKET_KEYS | {"scope", "dependencies"},
    "executor": COMMON_PACKET_KEYS | {"child_id", "postcondition"},
}
SETTLEMENT_KEYS = {
    "leader": {"status", "slice_id", "attempt_id", "execution_path", "children", "candidate_evidence", "preserved_attempts", "reason", "changed_paths"},
    "executor": {"status", "child_id", "slice_id", "attempt_id", "changed_paths", "checks", "evidence", "reason"},
}
RESULT_KEYS = {"schema_version", "status", "artifact", "settlement", "reason"}
SUPPORTED_SCHEMA_KEYS = {"type", "properties", "required", "additionalProperties", "oneOf", "const", "enum", "items"}
SUPPORTED_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


def fail(message: str) -> NoReturn:
    raise ContractError(message)


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{label} is unreadable or invalid JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def validator_module() -> Any:
    path = Path(__file__).with_name("validate-queue.py")
    spec = importlib.util.spec_from_file_location("smart_cascade_queue_validator", path)
    if spec is None or spec.loader is None:
        fail(f"cannot load queue validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def approved_slice(queue_path: Path, slice_id: str) -> dict[str, Any]:
    try:
        with queue_path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        fail(f"approved queue is unreadable or invalid TOML: {exc}")
    validator = validator_module()
    errors, _ = validator.validate_queue(document, str(queue_path))
    if errors:
        fail("approved queue is invalid")
    slices = document.get("slices") if isinstance(document, dict) else None
    matches = [item for item in slices if isinstance(item, dict) and item.get("id") == slice_id] if isinstance(slices, list) else []
    if len(matches) != 1:
        fail(f"leader packet slice_id is not one approved queue slice: {slice_id}")
    return matches[0]


def require_string(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f"{key} must be a non-empty string")
    return value


def require_strings(document: dict[str, Any], key: str, *, allow_empty: bool = False) -> list[str]:
    value = document.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value) or (not allow_empty and not value):
        qualifier = "possibly empty" if allow_empty else "non-empty"
        fail(f"{key} must be a {qualifier} array of non-empty strings")
    return value


def require_exact_keys(document: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(document) - allowed)
    if unknown:
        fail(f"{label} contains unknown fields: {', '.join(unknown)}")


def require_positive_int(document: dict[str, Any], key: str, *, maximum: int | None = None) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        fail(f"{key} must be a positive integer")
    if maximum is not None and value > maximum:
        fail(f"{key} must be no greater than {maximum}")
    return value


def contains_key(value: Any, target: str) -> bool:
    if isinstance(value, dict):
        return target in value or any(contains_key(item, target) for item in value.values())
    if isinstance(value, list):
        return any(contains_key(item, target) for item in value)
    return False


def require_object_schema_property(schema: dict[str, Any], key: str) -> dict[str, Any]:
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not isinstance(properties.get(key), dict):
        fail(f"result_schema.properties.{key} must be an object")
    return properties[key]


def schema_statuses(schema: dict[str, Any]) -> set[str]:
    status = schema.get("properties", {}).get("status") if isinstance(schema.get("properties"), dict) else None
    if not isinstance(status, dict):
        return set()
    if isinstance(status.get("const"), str):
        return {status["const"]}
    values = status.get("enum")
    return set(values) if isinstance(values, list) and all(isinstance(item, str) for item in values) else set()


def validate_schema_node(schema: dict[str, Any], path: str) -> None:
    unknown = sorted(set(schema) - SUPPORTED_SCHEMA_KEYS)
    if unknown:
        fail(f"{path} contains unsupported schema keys: {', '.join(unknown)}")
    kind = schema.get("type")
    if kind is not None and kind not in SUPPORTED_TYPES:
        fail(f"{path}.type is unsupported: {kind}")
    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            fail(f"{path}.properties must be an object")
        for key, child in properties.items():
            if not isinstance(key, str) or not isinstance(child, dict):
                fail(f"{path}.properties must contain schema objects")
            validate_schema_node(child, f"{path}.properties.{key}")
    required = schema.get("required")
    if required is not None and (not isinstance(required, list) or any(not isinstance(item, str) for item in required)):
        fail(f"{path}.required must be a string array")
    items = schema.get("items")
    if items is not None:
        if not isinstance(items, dict):
            fail(f"{path}.items must be a schema object")
        validate_schema_node(items, f"{path}.items")
    variants = schema.get("oneOf")
    if variants is not None:
        if not isinstance(variants, list) or not variants or any(not isinstance(item, dict) for item in variants):
            fail(f"{path}.oneOf must be a non-empty schema array")
        for index, variant in enumerate(variants):
            validate_schema_node(variant, f"{path}.oneOf[{index}]")


def schema_value_error(value: Any, schema: dict[str, Any], path: str) -> str | None:
    if "const" in schema and value != schema["const"]:
        return f"{path} differs from const"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} is outside enum"
    kind = schema.get("type")
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if kind in checks and not checks[kind](value):
        return f"{path} has wrong type"
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = sorted(set(required) - set(value))
        if missing:
            return f"{path} lacks fields: {', '.join(missing)}"
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                return f"{path} contains extra fields: {', '.join(extra)}"
        for key, child in properties.items():
            if key in value:
                error = schema_value_error(value[key], child, f"{path}.{key}")
                if error:
                    return error
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            error = schema_value_error(item, schema["items"], f"{path}[{index}]")
            if error:
                return error
    variants = schema.get("oneOf")
    if isinstance(variants, list):
        matched = sum(schema_value_error(value, variant, path) is None for variant in variants)
        if matched != 1:
            return f"{path} matched {matched} oneOf variants"
    return None


def validate_result_schema(schema: dict[str, Any], role: str) -> None:
    validate_schema_node(schema, "result_schema")
    root_properties = schema.get("properties")
    root_required = schema.get("required")
    if not isinstance(root_properties, dict) or not isinstance(root_required, list):
        fail("result_schema must define properties and a string required array")
    unknown = sorted(set(root_properties) - SETTLEMENT_KEYS[role])
    if unknown:
        fail(f"result_schema.properties contains unsupported {role} fields: {', '.join(unknown)}")
    expected_candidate = "READY_FOR_ROOT_REVIEW" if role == "leader" else "DONE"
    identity = {"slice_id", "attempt_id"} | ({"child_id"} if role == "executor" else set())
    candidate = {"execution_path", "children", "candidate_evidence", "preserved_attempts"} if role == "leader" else {"changed_paths", "checks", "evidence"}
    for key in {"status"} | identity | candidate:
        require_object_schema_property(schema, key)
    if role == "leader":
        evidence = require_object_schema_property(schema, "candidate_evidence")
        evidence_properties = evidence.get("properties")
        evidence_required = evidence.get("required")
        needed = {"base", "changed_paths", "checks", "evidence"}
        if evidence.get("type") != "object" or evidence.get("additionalProperties") is not False or not isinstance(evidence_properties, dict) or not isinstance(evidence_required, list) or not needed <= set(evidence_properties) or not needed <= set(evidence_required):
            fail("result_schema.properties.candidate_evidence must be a closed evidence schema")
    variants = schema.get("oneOf")
    if variants is None:
        if schema_statuses(schema) != {expected_candidate}:
            fail(f"result_schema without oneOf must allow only {expected_candidate}")
        missing = sorted(({"status"} | identity | candidate) - set(root_required))
        if missing:
            fail(f"result_schema.required lacks candidate fields: {', '.join(missing)}")
        return
    seen: set[str] = set()
    for index, variant in enumerate(variants):
        statuses = schema_statuses(variant)
        if not statuses or not statuses <= {expected_candidate} | BLOCKER_STATUSES:
            fail(f"result_schema.oneOf[{index}] has unsupported or missing status values")
        if seen & statuses:
            fail("result_schema.oneOf status variants must not overlap")
        seen.update(statuses)
        variant_required = variant.get("required", [])
        if not isinstance(variant_required, list):
            fail(f"result_schema.oneOf[{index}].required must be a string array")
        needed = {"status"} | identity | (candidate if expected_candidate in statuses else {"reason"})
        missing = sorted(needed - (set(root_required) | set(variant_required)))
        if missing:
            fail(f"result_schema.oneOf[{index}] lacks fields: {', '.join(missing)}")
    if expected_candidate not in seen:
        fail(f"result_schema.oneOf must include {expected_candidate}")
    if seen & BLOCKER_STATUSES and require_object_schema_property(schema, "reason").get("type") != "string":
        fail("result_schema.properties.reason must be a string schema when blockers are allowed")


def parse_name_status(raw: bytes, label: str) -> list[str]:
    fields = [field.decode("utf-8") for field in raw.split(b"\0") if field]
    paths: set[str] = set()
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        count = 2 if status[:1] in {"R", "C"} else 1
        if index + count > len(fields):
            fail(f"{label} name-status is malformed")
        paths.update(fields[index:index + count])
        index += count
    return sorted(paths)


def patch_bytes_paths(patch: bytes, base: str, repo_root: Path, label: str, *, baseline_patches: tuple[bytes, ...] = ()) -> list[str]:
    if not patch:
        fail(f"{label} is empty")
    with tempfile.TemporaryDirectory(prefix="smart-cascade-patch-") as raw:
        index = Path(raw) / "index"
        patch_path = Path(raw) / "candidate.patch"
        patch_path.write_bytes(patch)
        env = {**os.environ, "GIT_INDEX_FILE": str(index)}
        prepared = subprocess.run(["git", "read-tree", base], env=env, cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=False)
        if prepared.returncode != 0:
            fail(f"cannot prepare isolated patch index: {prepared.stderr.strip()}")
        for baseline_index, baseline_patch in enumerate(baseline_patches):
            baseline_path = Path(raw) / f"baseline-{baseline_index}.patch"
            baseline_path.write_bytes(baseline_patch)
            applied = subprocess.run(["git", "apply", "--cached", "--binary", str(baseline_path)], env=env, cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=False)
            if applied.returncode != 0:
                fail(f"{label} baseline is invalid for explicit base: {applied.stderr.strip()}")
        baseline_tree = subprocess.run(["git", "write-tree"], env=env, cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=False)
        if baseline_tree.returncode != 0:
            fail(f"cannot materialize {label} baseline: {baseline_tree.stderr.strip()}")
        applied = subprocess.run(["git", "apply", "--cached", "--binary", str(patch_path)], env=env, cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=False)
        if applied.returncode != 0:
            fail(f"{label} is invalid for explicit candidate: {applied.stderr.strip()}")
        result = subprocess.run(["git", "diff", "--cached", "--name-status", "-z", "--find-renames", baseline_tree.stdout.strip()], env=env, cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        if result.returncode != 0:
            fail(f"cannot inspect {label}: {result.stderr.decode(errors='replace').strip()}")
    return parse_name_status(result.stdout, label)


def patch_paths(path: Path, base: str, repo_root: Path, label: str = "candidate patch", *, baseline: Path | None = None) -> list[str]:
    if not path.is_file():
        fail(f"{label} is missing: {path}")
    baselines = (baseline.read_bytes(),) if baseline is not None else ()
    return patch_bytes_paths(path.read_bytes(), base, repo_root, label, baseline_patches=baselines)


def validate_artifact_scope(actual: list[str], write_set: list[str], label: str) -> None:
    validator = validator_module()
    unexpected = [path for path in actual if not any(validator.path_matches(item, path) for item in write_set)]
    if unexpected:
        fail(f"{label} escape write_set: {', '.join(unexpected)}")


def validate_packet(packet: dict[str, Any], role: str, repo_root: Path, queue_path: Path | None = None) -> dict[str, Any]:
    require_exact_keys(packet, PACKET_KEYS[role], f"{role} packet")
    if packet.get("role") != role:
        fail(f"packet role must be {role}")
    task_name = require_string(packet, "task_name")
    attempt_id = require_string(packet, "attempt_id")
    base = require_string(packet, "base")
    if len(base) != 40 or any(char not in "0123456789abcdef" for char in base):
        fail("base must be one full lowercase hexadecimal Git commit identity")
    resolved = subprocess.run(["git", "cat-file", "-e", f"{base}^{{commit}}"], cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=False)
    if resolved.returncode != 0:
        fail("base does not resolve to a commit in the production repository")
    write_set = require_strings(packet, "write_set")
    require_strings(packet, "checks")
    require_strings(packet, "non_goals", allow_empty=True)
    cumulative: Path | None = None
    cumulative_paths: list[str] = []
    if "cumulative_patch" in packet:
        cumulative = Path(require_string(packet, "cumulative_patch"))
        cumulative_paths = patch_paths(cumulative, base, repo_root, "cumulative patch")
    if "rework_checklist" in packet:
        require_strings(packet, "rework_checklist")
    if "rework_count" in packet:
        require_positive_int(packet, "rework_count")
    schema = packet.get("result_schema")
    if not isinstance(schema, dict) or schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        fail("result_schema must be a closed JSON object schema")
    validate_result_schema(schema, role)
    validator = validator_module()
    normalized: list[str] = []
    for index, raw in enumerate(write_set):
        path = validator.normalize_repo_path(raw, f"write_set[{index}]")
        if path is None or path != raw:
            fail(f"write_set[{index}] is not normalized")
        if path in normalized:
            fail(f"write_set[{index}] duplicates a normalized path")
        normalized.append(path)
    if cumulative_paths:
        validate_artifact_scope(cumulative_paths, normalized, "cumulative patch")
    slice_id = require_string(packet, "slice_id")
    if role == "leader":
        if queue_path is None:
            fail("leader packet validation requires --queue")
        scope = require_string(packet, "scope")
        dependencies = require_strings(packet, "dependencies", allow_empty=True)
        approved = approved_slice(queue_path.resolve(), slice_id)
        expected = {
            "scope": approved.get("scope"),
            "write_set": approved.get("write_set"),
            "dependencies": approved.get("depends_on"),
            "checks": approved.get("checks"),
        }
        observed = {"scope": scope, "write_set": write_set, "dependencies": dependencies, "checks": packet.get("checks")}
        if observed != expected:
            fail("leader packet does not exactly match its approved queue slice")
    else:
        require_string(packet, "child_id")
        require_string(packet, "postcondition")
    return {"task_name": task_name, "slice_id": slice_id, "attempt_id": attempt_id, "base": base, "write_set": normalized, "cumulative_patch": str(cumulative) if cumulative else None}


def normalized_artifact(result: dict[str, Any], packet_info: dict[str, Any], repo_root: Path) -> tuple[Path | None, list[str]]:
    artifact = result.get("artifact")
    if artifact is None:
        return None, []
    if not isinstance(artifact, dict) or set(artifact) != {"kind", "path"} or artifact.get("kind") != "git_patch":
        fail("normalized result artifact must be null or one git_patch object")
    path = Path(require_string(artifact, "path"))
    baseline = Path(packet_info["cumulative_patch"]) if packet_info["cumulative_patch"] else None
    return path, patch_paths(path, packet_info["base"], repo_root, baseline=baseline)


def validate_normalized_result(packet: dict[str, Any], result: dict[str, Any], role: str, repo_root: Path, queue_path: Path | None = None) -> dict[str, Any]:
    packet_info = validate_packet(packet, role, repo_root, queue_path)
    require_exact_keys(result, RESULT_KEYS, "normalized runner result")
    if result.get("schema_version") != 1:
        fail("normalized runner result schema_version must be 1")
    status = require_string(result, "status")
    if status not in {"completed", "failed"}:
        fail("normalized runner result status must be completed or failed")
    settlement = result.get("settlement")
    if not isinstance(settlement, dict):
        fail("normalized runner result settlement must be an object")
    if contains_key(settlement, "patchPath") or contains_key(settlement, "patch_path"):
        fail("runner settlement must not claim an artifact path")
    patch, actual = normalized_artifact(result, packet_info, repo_root)
    if status == "failed":
        reason = require_string(result, "reason")
        claimed_value = settlement.get("changed_paths")
        if role == "leader" and isinstance(settlement.get("candidate_evidence"), dict):
            claimed_value = settlement["candidate_evidence"].get("changed_paths")
        claimed = [] if claimed_value is None else claimed_value
        if not actual:
            if claimed != []:
                fail("failed runner result without artifact must not claim changed_paths")
            return {"status": "RESULT_FAILED_LOST", "role": role, "task_name": packet_info["task_name"], "reason": reason, "artifact_disposition": "lost_unmaterialized"}
        if claimed not in (None, []):
            if not isinstance(claimed, list) or any(not isinstance(item, str) or not item for item in claimed):
                fail("failed runner changed_paths must be an array of non-empty strings")
            if sorted(claimed) != actual:
                fail(f"failed runner changed_paths do not match artifact: claimed={sorted(claimed)} actual={actual}")
        validate_artifact_scope(actual, packet_info["write_set"], "failed runner artifact")
        return {"status": "RESULT_FAILED_ARTIFACT_PRESERVED", "role": role, "task_name": packet_info["task_name"], "reason": reason, "artifact_disposition": "preserved_not_candidate", "patch_path": str(patch), "changed_paths": actual}
    if result.get("reason") is not None:
        fail("completed normalized runner result must set reason to null")
    error = schema_value_error(settlement, packet["result_schema"], "settlement")
    if error:
        fail(f"runner settlement does not match supplied result_schema: {error}")
    business_status = require_string(settlement, "status")
    if settlement.get("attempt_id") != packet_info["attempt_id"] or settlement.get("slice_id") != packet_info["slice_id"]:
        fail("settlement attempt/slice identity does not match packet")
    if role == "executor" and settlement.get("child_id") != packet.get("child_id"):
        fail("settlement child identity does not match packet")
    if business_status in BLOCKER_STATUSES:
        reason = require_string(settlement, "reason")
        claimed = settlement.get("changed_paths", [])
        if not actual:
            if claimed != []:
                fail("blocker without artifact must not claim changed_paths")
            return {"status": "RESULT_BLOCKED", "role": role, "task_name": packet_info["task_name"], "reason": reason, "artifact_disposition": "none"}
        claimed_paths = require_strings(settlement, "changed_paths", allow_empty=True)
        if sorted(claimed_paths) != actual:
            fail(f"blocker changed_paths do not match artifact: claimed={sorted(claimed_paths)} actual={actual}")
        validate_artifact_scope(actual, packet_info["write_set"], "blocked artifact")
        return {"status": "RESULT_BLOCKED_ARTIFACT_PRESERVED", "role": role, "task_name": packet_info["task_name"], "reason": reason, "artifact_disposition": "preserved_not_candidate", "patch_path": str(patch), "changed_paths": actual}
    expected = "READY_FOR_ROOT_REVIEW" if role == "leader" else "DONE"
    if business_status != expected:
        fail(f"candidate settlement status must be {expected}")
    if patch is None:
        fail("completed candidate result lacks a git_patch artifact")
    if role == "executor":
        require_strings(settlement, "checks")
        require_string(settlement, "evidence")
        claimed = require_strings(settlement, "changed_paths", allow_empty=True)
    else:
        candidate = settlement.get("candidate_evidence")
        if not isinstance(candidate, dict):
            fail("leader candidate settlement lacks candidate_evidence")
        require_strings(candidate, "checks")
        require_string(candidate, "evidence")
        if require_string(candidate, "base") != packet_info["base"]:
            fail("leader candidate_evidence.base does not match packet base")
        claimed = require_strings(candidate, "changed_paths", allow_empty=True)
    if sorted(claimed) != actual:
        fail(f"settlement changed_paths do not match candidate patch: claimed={sorted(claimed)} actual={actual}")
    validate_artifact_scope(actual, packet_info["write_set"], "candidate patch")
    return {"status": "RESULT_VALID", "role": role, "task_name": packet_info["task_name"], "patch_path": str(patch), "changed_paths": actual}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    packet_parser = sub.add_parser("packet")
    packet_parser.add_argument("role", choices=("leader", "executor"))
    packet_parser.add_argument("packet", type=Path)
    packet_parser.add_argument("--queue", type=Path)
    result_parser = sub.add_parser("result")
    result_parser.add_argument("role", choices=("leader", "executor"))
    result_parser.add_argument("packet", type=Path)
    result_parser.add_argument("result", type=Path)
    result_parser.add_argument("--queue", type=Path)
    args = parser.parse_args()
    packet = load_json(args.packet, "packet")
    queue_path = args.queue.resolve() if args.queue is not None else None
    if args.command == "packet":
        output = {"status": "PACKET_VALID", "role": args.role, **validate_packet(packet, args.role, args.repo_root.resolve(), queue_path)}
    else:
        output = validate_normalized_result(packet, load_json(args.result, "normalized runner result"), args.role, args.repo_root.resolve(), queue_path)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
