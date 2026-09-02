#!/usr/bin/env python3
"""Parse one authoritative OMP parent transcript into a runner-neutral result."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn
import hashlib

import yaml

sys.dont_write_bytecode = True
MAX_TRANSCRIPT_BYTES = 16 * 1024 * 1024
TASK_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")
RESULT_RE = re.compile(
    r'^<task-result id="([^"]+)" agent="([^"]+)" status="([^"]+)" duration="[^"]+">\n'
    r'(?:<meta lines="\d+" size="[^"\n]+" />\n)?(?:<abort-reason>[\s\S]*?</abort-reason>\n)?'
    r'<output>\n([\s\S]*?)\n</output>\n'
    r'<merge-summary>\n(Isolation: changes captured at `([^`]+)` \(apply=false\)\. Not applied\.|Isolation: no changes captured\.)\n'
    r'</merge-summary>\n</task-result>$'
)


class NormalizeError(RuntimeError):
    pass


def fail(message: str) -> NoReturn:
    raise NormalizeError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{label} is unreadable or invalid JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def packet_digest(packet: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(packet).encode("utf-8")).hexdigest()


def read_entries(path: Path) -> list[dict[str, Any]]:
    try:
        if not path.is_file() or path.stat().st_size > MAX_TRANSCRIPT_BYTES:
            fail("OMP parent transcript is missing or exceeds the evidence limit")
        entries: list[dict[str, Any]] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                fail(f"OMP parent transcript entry {index} is not an object")
            entries.append(value)
        return entries
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"OMP parent transcript is unreadable or invalid JSONL: {exc}")


def message(entry: dict[str, Any]) -> dict[str, Any]:
    value = entry.get("message") if entry.get("type") == "message" else entry
    return value if isinstance(value, dict) else {}


def projections(config_path: Path, role: str) -> list[tuple[str, str, str]]:
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        fail(f"OMP adapter config is unreadable or invalid: {exc}")
    roles = config.get("roles") if isinstance(config, dict) else None
    if not isinstance(roles, dict):
        fail("OMP adapter config lacks role projections")
    keys = ("leader",) if role == "leader" else ("semantic_executor", "escalated_semantic_executor", "mechanical_executor")
    result: list[tuple[str, str, str]] = []
    for key in keys:
        projection = roles.get(key)
        if not isinstance(projection, dict):
            continue
        values = (projection.get("agent"), projection.get("model_role"), projection.get("model"))
        if all(isinstance(value, str) and value for value in values):
            result.append(values)  # type: ignore[arg-type]
    if not result:
        fail("OMP adapter config lacks task role projection")
    return result


def invocation(entries: list[dict[str, Any]], task_name: str, allowed_agents: set[str], packet: dict[str, Any]) -> tuple[str, str, dict[str, Any], str]:
    matches: list[tuple[str, str, dict[str, Any], str]] = []
    expected_marker = f"SMART_CASCADE_PACKET_SHA256 {packet_digest(packet)}"
    expected_schema = canonical_json(packet.get("result_schema"))
    for entry in entries:
        current = message(entry)
        if current.get("role") != "assistant" or not isinstance(current.get("content"), list):
            continue
        for item in current["content"]:
            if not isinstance(item, dict) or item.get("type") != "toolCall" or item.get("name") != "task" or not isinstance(item.get("id"), str):
                continue
            outer = item.get("arguments")
            timestamp = entry.get("timestamp")
            if not isinstance(outer, dict) or not isinstance(timestamp, str):
                continue
            candidates = outer.get("tasks") if isinstance(outer.get("tasks"), list) else [outer]
            for args in candidates:
                if not isinstance(args, dict) or args.get("name") != task_name or args.get("agent") not in allowed_agents:
                    continue
                output_schema = args.get("outputSchema")
                if isinstance(output_schema, str):
                    try:
                        output_schema = json.loads(output_schema)
                    except json.JSONDecodeError:
                        continue
                if canonical_json(output_schema) != expected_schema:
                    continue
                assignment = args.get("task")
                if not isinstance(assignment, str) or expected_marker not in assignment:
                    continue
                matches.append((item["id"], args["agent"], args, timestamp))
    if len(matches) != 1:
        fail("OMP transcript must contain exactly one matching task invocation")
    return matches[0]


def spawn_metadata(entries: list[dict[str, Any]], tool_call_id: str, runtime_id: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for entry in entries:
        current = message(entry)
        if current.get("role") != "toolResult" or current.get("toolName") != "task" or current.get("toolCallId") != tool_call_id:
            continue
        details = current.get("details")
        progress = details.get("progress") if isinstance(details, dict) else None
        if isinstance(progress, list):
            matches.extend(item for item in progress if isinstance(item, dict) and item.get("id") == runtime_id)
    if len(matches) != 1:
        fail("OMP transcript lacks one matching native task spawn receipt")
    return matches[0]


def terminal_job(entries: list[dict[str, Any]], runtime_id: str) -> dict[str, Any]:
    hub_calls: dict[str, dict[str, Any]] = {}
    matches: list[dict[str, Any]] = []
    for entry in entries:
        current = message(entry)
        if current.get("role") == "assistant" and isinstance(current.get("content"), list):
            for item in current["content"]:
                if isinstance(item, dict) and item.get("type") == "toolCall" and item.get("name") == "hub" and isinstance(item.get("id"), str) and isinstance(item.get("arguments"), dict):
                    hub_calls[item["id"]] = item["arguments"]
            continue
        if current.get("role") != "toolResult" or current.get("toolName") != "hub" or not isinstance(current.get("toolCallId"), str):
            continue
        details = current.get("details")
        args = hub_calls.get(current["toolCallId"])
        if not isinstance(details, dict) or not isinstance(args, dict) or details.get("op") != args.get("op") or args.get("op") not in {"wait", "jobs", "cancel"}:
            continue
        if args.get("op") in {"wait", "cancel"} and isinstance(args.get("ids"), list) and runtime_id not in args["ids"]:
            continue
        jobs = details.get("jobs")
        if isinstance(jobs, list):
            matches.extend(job for job in jobs if isinstance(job, dict) and job.get("id") == runtime_id and job.get("type") == "task" and job.get("status") in {"completed", "failed", "cancelled"})
    if not matches:
        fail("OMP transcript lacks a bound terminal native task job receipt")
    canonical = {
        json.dumps({key: match.get(key) for key in ("status", "resolvedModel", "resultText", "errorText")}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for match in matches
    }
    if len(canonical) != 1:
        fail("OMP transcript contains conflicting terminal task receipts")
    return matches[-1]


def rendered_result(text: str, runtime_id: str, expected_agent: str) -> tuple[str, dict[str, Any], Path | None]:
    close = text.find("</task-result>")
    if close < 0 or text.find("<task-result ", 1) != -1 or close != text.rfind("</task-result>"):
        fail("OMP rendered task result frame is ambiguous")
    frame = text[: close + len("</task-result>")]
    for tag in ("<output>", "</output>", "<merge-summary>", "</merge-summary>"):
        if frame.count(tag) != 1:
            fail("OMP rendered task result delimiters are ambiguous")
    if "<preview" in frame:
        fail("OMP rendered task result is truncated")
    match = RESULT_RE.fullmatch(frame)
    if match is None or match[1] != runtime_id or match[2] != expected_agent:
        fail("OMP rendered task result identity does not match the dispatch")
    try:
        settlement = json.loads(match[4])
    except json.JSONDecodeError as exc:
        if match[3] == "completed":
            fail(f"OMP task settlement is invalid JSON: {exc}")
        settlement = {}
    if not isinstance(settlement, dict):
        if match[3] == "completed":
            fail("OMP task settlement must be an object")
        settlement = {}
    patch = Path(match[6]).resolve() if match[6] is not None else None
    return match[3], settlement, patch


def parsed_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        fail(f"OMP {label} timestamp is missing")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(f"OMP {label} timestamp is invalid")


def validate_session(parent: Path, runtime_id: str, agent: str, invocation_timestamp: str) -> None:
    parent_entries = read_entries(parent)
    parent_headers = [entry for entry in parent_entries if entry.get("type") == "session"]
    child = parent.with_suffix("") / f"{runtime_id}.jsonl"
    entries = read_entries(child)
    headers = [entry for entry in entries if entry.get("type") == "session"]
    inits = [entry for entry in entries if entry.get("type") == "session_init"]
    if len(parent_headers) != 1 or len(headers) != 1 or len(inits) != 1 or inits[0].get("agent") != agent or headers[0].get("id") == parent_headers[0].get("id"):
        fail("OMP native child session tree does not match the dispatch")
    parent_cwd = parent_headers[0].get("cwd")
    child_cwd = headers[0].get("cwd")
    if not isinstance(parent_cwd, str) or not parent_cwd or not isinstance(child_cwd, str) or not child_cwd or Path(child_cwd).resolve() == Path(parent_cwd).resolve():
        fail("OMP native child session is not isolated from its parent")
    if parsed_timestamp(headers[0].get("timestamp"), "child session") < parsed_timestamp(invocation_timestamp, "task invocation"):
        fail("OMP native child session predates its task invocation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().with_name("runner-launch.yaml"))
    parser.add_argument("--parent-transcript", type=Path, required=True)
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("role", choices=("leader", "executor"))
    parser.add_argument("packet", type=Path)
    args = parser.parse_args()

    packet = load(args.packet, "packet")
    task_name = packet.get("task_name")
    if not isinstance(task_name, str) or not TASK_NAME_RE.fullmatch(task_name):
        fail("core packet task_name is invalid")
    configured = projections(args.config.resolve(), args.role)
    by_agent = {agent: (model_role, model) for agent, model_role, model in configured}
    parent = args.parent_transcript.resolve()
    if args.role == "leader" and ("." in args.runtime_id or re.fullmatch(re.escape(task_name) + r"(?:-(?:[2-9]|[1-9][0-9]+))?", args.runtime_id) is None):
        fail("OMP Leader runtime identity does not match the task name")
    if args.role == "executor":
        local_runtime = args.runtime_id.rsplit(".", 1)[-1]
        if re.fullmatch(re.escape(task_name) + r"(?:-(?:[2-9]|[1-9][0-9]+))?", local_runtime) is None:
            fail("OMP Executor runtime identity does not match task name")
        if "." in args.runtime_id and parent.name != f"{args.runtime_id.rsplit('.', 1)[0]}.jsonl":
            fail("OMP Executor parent transcript does not match runtime lineage")
    entries = read_entries(parent)
    tool_call_id, agent, task_args, invocation_timestamp = invocation(entries, task_name, set(by_agent), packet)
    if task_args.get("isolated") is not True or task_args.get("schemaMode") != "strict":
        fail("OMP task invocation lacks isolated=true strict structured output")
    spawn = spawn_metadata(entries, tool_call_id, args.runtime_id)
    expected_role, expected_model = by_agent[agent]
    if spawn.get("agent") != agent or spawn.get("agentSource") != "user" or spawn.get("modelRole") != expected_role:
        fail("OMP native task spawn provenance does not match the admitted projection")
    job = terminal_job(entries, args.runtime_id)
    resolved_model = job.get("resolvedModel")
    if not isinstance(resolved_model, str) or not (resolved_model == expected_model or resolved_model.startswith(expected_model + ":")):
        fail("OMP terminal task model does not match the admitted projection")
    validate_session(parent, args.runtime_id, agent, invocation_timestamp)
    job_status = job["status"]
    text = job.get("resultText") if job_status == "completed" else job.get("errorText")
    if not isinstance(text, str):
        reason = "OMP task failed without a rendered result" if job_status != "completed" else "OMP completed task lacks a rendered result"
        if job_status == "completed":
            fail(reason)
        print(json.dumps({"schema_version": 1, "status": "failed", "artifact": None, "settlement": {}, "reason": reason}, ensure_ascii=False, sort_keys=True))
        return 0
    if job_status != "completed" and not text.startswith("<task-result "):
        print(json.dumps({"schema_version": 1, "status": "failed", "artifact": None, "settlement": {}, "reason": text.strip() or f"OMP task {job_status}"}, ensure_ascii=False, sort_keys=True))
        return 0
    envelope_status, settlement, patch = rendered_result(text, args.runtime_id, agent)
    if job_status != "completed" or envelope_status != "completed":
        artifact = {"kind": "git_patch", "path": str(patch)} if patch is not None and patch.is_file() else None
        reason = f"OMP task {job_status}: {envelope_status}"
        print(json.dumps({"schema_version": 1, "status": "failed", "artifact": artifact, "settlement": settlement, "reason": reason}, ensure_ascii=False, sort_keys=True))
        return 0
    if patch is None:
        print(json.dumps({"schema_version": 1, "status": "completed", "artifact": None, "settlement": settlement, "reason": None}, ensure_ascii=False, sort_keys=True))
        return 0
    if not patch.is_file():
        fail("OMP settled task retained patch artifact is missing")
    print(json.dumps({"schema_version": 1, "status": "completed", "artifact": {"kind": "git_patch", "path": str(patch)}, "settlement": settlement, "reason": None}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (NormalizeError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "adapter": "omp", "reason": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
