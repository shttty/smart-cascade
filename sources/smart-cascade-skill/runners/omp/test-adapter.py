#!/usr/bin/env python3
"""Deterministic OMP adapter admission and transcript-normalization tests."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

RUNNER_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = RUNNER_ROOT.parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]
ADAPTER = RUNNER_ROOT / "adapter.py"
NORMALIZE = RUNNER_ROOT / "normalize.py"
CONFIG_SOURCE = RUNNER_ROOT / "runner-launch.yaml"
PROFILE_SOURCE = REPO_ROOT / "sources/smart-cascade-omp/agent"
ROLE_SOURCE = RUNNER_ROOT / "roles"


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, check=False)


def write_fake_omp(package: Path, version: str = "18.0.4", *, rpc: bool = True) -> Path:
    executable = package / "dist/cli.js"
    executable.parent.mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({
        "name": "@oh-my-pi/pi-coding-agent", "version": version, "bin": {"omp": "dist/cli.js"},
        "exports": {"./modes/rpc/*": {}, "./task": {}, "./task/*": {}, "./tools/hub": {}, "./tools/hub/*": {}},
    }), encoding="utf-8")
    declarations = {
        "dist/types/modes/rpc/rpc-types.d.ts": "negotiate_protocol get_subagents get_subagent_messages supportedProtocolVersions interface RpcSubagentSnapshot sessionFile? progress?",
        "dist/types/task/types.d.ts": "interface SubagentLifecyclePayload interface AgentProgress modelRole? resolvedModel? schemaMode? isolated?",
        "dist/types/tools/hub/types.d.ts": "type HubOp interface CoordinationDetails receipts?: IrcDeliveryReceipt[]",
    }
    for relative, content in declarations.items():
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    response = "" if not rpc else "printf '%s\\n' '{\"type\":\"ready\",\"supportedProtocolVersions\":[1,2]}' '{\"id\":\"smart-cascade-admission\",\"type\":\"response\",\"command\":\"negotiate_protocol\",\"success\":true,\"data\":{\"protocolVersion\":2}}'"
    executable.write_text(f"#!/usr/bin/env bash\nif [[ $1 == --version ]]; then printf '%s\\n' 'omp/{version}'; exit; fi\n{response}\n", encoding="utf-8")
    executable.chmod(0o755)
    return executable


def check_adapter(project: Path, profiles: Path, config: Path, omp: Path, env: dict[str, str], profile: str | None = None) -> subprocess.CompletedProcess[str]:
    command = [
        str(ADAPTER), "check",
        "--project-root", str(project),
        "--config", str(config),
        "--omp-bin", str(omp),
    ]
    if profile is not None:
        command.extend(["--profile", profile])
    return run(*command, env=env)


def rewrite_yaml(path: Path, mutate: object) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict) and callable(mutate)
    mutate(document)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def role_frontmatter(name: str) -> str:
    return f"---\nname: {name}\n---\n\nProject override.\n"


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def packet_marker(packet: dict[str, object]) -> str:
    return "SMART_CASCADE_PACKET_SHA256 sha256:" + __import__("hashlib").sha256(canonical(packet).encode("utf-8")).hexdigest()


def rendered(runtime_id: str, agent: str, settlement: dict[str, object], patch: Path) -> str:
    return f'<task-result id="{runtime_id}" agent="{agent}" status="completed" duration="1s">\n<output>\n{json.dumps(settlement, separators=(",", ":"))}\n</output>\n<merge-summary>\nIsolation: changes captured at `{patch}` (apply=false). Not applied.\n</merge-summary>\n</task-result>\n\n{runtime_id} is now idle — message it via `hub` to follow up; transcript at history://{runtime_id}'


def rendered_without_patch(runtime_id: str, agent: str, settlement: dict[str, object], *, status: str = "completed") -> str:
    return f'<task-result id="{runtime_id}" agent="{agent}" status="{status}" duration="1s">\n<output>\n{json.dumps(settlement, separators=(",", ":"))}\n</output>\n<merge-summary>\nIsolation: no changes captured.\n</merge-summary>\n</task-result>'


def write_transcript(root: Path, runtime_id: str, result_text: str, packet: dict[str, object], *, agent: str = "smart-cascade-executor", model_role: str = "smart-cascade-semantic", resolved_model: str = "clp/gpt-5.6-luna:xhigh") -> Path:
    parent = root / "LeaderA.jsonl"
    call = "call-a"
    entries = [
        {"type": "session", "id": "leader-session", "timestamp": "2026-08-27T00:00:00Z", "cwd": str(root)},
        {"type": "message", "timestamp": "2026-08-27T00:00:01Z", "message": {"role": "assistant", "content": [{"type": "toolCall", "id": call, "name": "task", "arguments": {"name": "ChildA", "agent": agent, "task": f"bounded assignment\n{packet_marker(packet)}", "isolated": True, "schemaMode": "strict", "outputSchema": packet["result_schema"]}}]}},
        {"type": "message", "message": {"role": "toolResult", "toolCallId": call, "toolName": "task", "details": {"progress": [{"id": runtime_id, "agent": agent, "agentSource": "user", "modelRole": model_role, "status": "pending"}]}}},
        {"type": "message", "message": {"role": "assistant", "content": [{"type": "toolCall", "id": "hub-a", "name": "hub", "arguments": {"op": "wait", "ids": [runtime_id]}}]}},
        {"type": "message", "message": {"role": "toolResult", "toolCallId": "hub-a", "toolName": "hub", "details": {"op": "wait", "jobs": [{"id": runtime_id, "type": "task", "status": "completed", "resolvedModel": resolved_model, "resultText": result_text}]}}},
    ]
    parent.write_text("\n".join(json.dumps(item) for item in entries) + "\n", encoding="utf-8")
    child_dir = parent.with_suffix("")
    child_dir.mkdir()
    (child_dir / f"{runtime_id}.jsonl").write_text("\n".join(json.dumps(item) for item in [
        {"type": "session", "id": "child-session", "timestamp": "2026-08-27T00:00:02Z", "cwd": str(root / "isolation")},
        {"type": "session_init", "agent": agent},
    ]) + "\n", encoding="utf-8")
    return parent


def install_profile(destination: Path) -> None:
    """Project a profile the way deploy.sh does: profile config plus OMP runner roles."""
    shutil.copytree(PROFILE_SOURCE, destination)
    (destination / "agents").mkdir(exist_ok=True)
    for role in ROLE_SOURCE.glob("*.md"):
        shutil.copy2(role, destination / "agents" / role.name)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="smart-cascade-omp-adapter-") as raw:
        root = Path(raw)
        project = root / "project"
        project.mkdir()
        config = yaml.safe_load(CONFIG_SOURCE.read_text(encoding="utf-8"))
        config["runner"]["adapter_check"] = str(ADAPTER)
        config["runner"]["adapter_normalize"] = str(NORMALIZE)
        interface = root / "runner-interface.json"
        interface.write_text("{}", encoding="utf-8")
        config["runner"]["interface"] = str(interface)
        config_path = project / "runner.yaml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        profiles = root / "profiles"
        installed = profiles / "smart-cascade-omp/agent"
        installed.parent.mkdir(parents=True)
        install_profile(installed)
        omp = write_fake_omp(root / "package")
        adapter_env = __import__("os").environ.copy()
        checked = check_adapter(project, profiles, config_path, omp, adapter_env, str(profiles / "smart-cascade-omp"))
        assert checked.returncode == 0, checked.stdout
        receipt = json.loads(checked.stdout)
        assert receipt["status"] == "ADAPTER_READY" and receipt["profile_config_digest"].startswith("sha256:") and receipt["role_digests"] and receipt["warnings"] == []

        override = yaml.safe_load((project / ".smart-cascade/override.yaml").read_text(encoding="utf-8"))
        assert override == {"profile_name": "smart-cascade-omp", "profiles_root": str(profiles.resolve())}
        alternate = profiles / "alternate/agent"
        alternate.parent.mkdir(parents=True)
        install_profile(alternate)
        selected_alternate = check_adapter(project, profiles, config_path, omp, adapter_env, str(profiles / "alternate"))
        assert selected_alternate.returncode == 0 and json.loads(selected_alternate.stdout)["profile_name"] == "alternate", selected_alternate.stdout
        persisted_alternate = check_adapter(project, profiles, config_path, omp, adapter_env)
        persisted_receipt = json.loads(persisted_alternate.stdout)
        assert persisted_alternate.returncode == 0 and persisted_receipt["profile_name"] == "alternate" and persisted_receipt["profile_root"] == str(profiles.resolve()), persisted_alternate.stdout
        selected_default = check_adapter(project, profiles, config_path, omp, adapter_env, str(profiles / "smart-cascade-omp"))
        assert selected_default.returncode == 0, selected_default.stdout
        malformed_override = project / ".smart-cascade/override.yaml"
        malformed_override.write_text("profile_name: smart-cascade-omp\nextra: false\n", encoding="utf-8")
        rejected_override = check_adapter(project, profiles, config_path, omp, adapter_env)
        assert rejected_override.returncode != 0 and "override must contain only" in rejected_override.stdout, rejected_override.stdout
        malformed_override.write_text(yaml.safe_dump(override, sort_keys=False), encoding="utf-8")
        newer = check_adapter(project, profiles, config_path, write_fake_omp(root / "newer", "19.0.0"), adapter_env)
        assert newer.returncode == 0, newer.stdout
        older = check_adapter(project, profiles, config_path, write_fake_omp(root / "older", "17.9.9"), adapter_env)
        assert older.returncode != 0 and "supported >=18.0.0" in older.stdout, older.stdout

        custom_role = installed / "agents/smart-cascade-executor.md"
        custom_role.write_text(custom_role.read_text(encoding="utf-8") + "\nProject-specific executor rule.\n", encoding="utf-8")
        customized_role = check_adapter(project, profiles, config_path, omp, adapter_env)
        customized_role_receipt = json.loads(customized_role.stdout)
        assert customized_role.returncode == 0 and customized_role_receipt["status"] == "ADAPTER_READY" and any("role differs" in warning for warning in customized_role_receipt["warnings"]), customized_role.stdout
        shutil.copy2(ROLE_SOURCE / "smart-cascade-executor.md", custom_role)

        leader_role = installed / "agents/smart-cascade-leader.md"
        leader_text = leader_role.read_text(encoding="utf-8")
        leader_role.write_text(leader_text.replace('model: "@smart-cascade-leader"', 'model: "@project-leader"').replace("thinkingLevel: medium", "thinkingLevel: high").replace("spawns: [smart-cascade-executor, smart-cascade-escalated-executor, smart-cascade-mechanical-executor]", "spawns: [smart-cascade-executor]"), encoding="utf-8")
        customized_frontmatter = check_adapter(project, profiles, config_path, omp, adapter_env)
        customized_frontmatter_receipt = json.loads(customized_frontmatter.stdout)
        assert customized_frontmatter.returncode == 0 and sum("runner projection" in warning for warning in customized_frontmatter_receipt["warnings"]) >= 3, customized_frontmatter.stdout
        shutil.copy2(ROLE_SOURCE / "smart-cascade-leader.md", leader_role)

        missing_role = installed / "agents/smart-cascade-mechanical-executor.md"
        missing_role.unlink()
        rejected_missing_role = check_adapter(project, profiles, config_path, omp, adapter_env)
        assert rejected_missing_role.returncode != 0 and "role is missing" in rejected_missing_role.stdout, rejected_missing_role.stdout
        shutil.copy2(ROLE_SOURCE / "smart-cascade-mechanical-executor.md", missing_role)

        installed_config = installed / "config.yml"
        rewrite_yaml(installed_config, lambda document: document["modelRoles"].update({"project-extra-role": "project/model"}))
        extra_model_role = check_adapter(project, profiles, config_path, omp, adapter_env)
        assert extra_model_role.returncode == 0 and json.loads(extra_model_role.stdout)["status"] == "ADAPTER_READY", extra_model_role.stdout
        rewrite_yaml(installed_config, lambda document: document["modelRoles"].pop("smart-cascade-advisor"))
        rejected_missing_model = check_adapter(project, profiles, config_path, omp, adapter_env)
        assert rejected_missing_model.returncode != 0 and "model role projection is stale" in rejected_missing_model.stdout, rejected_missing_model.stdout
        shutil.copy2(PROFILE_SOURCE / "config.yml", installed_config)

        project_agents = project / ".omp/agents"
        project_agents.mkdir(parents=True)
        (project_agents / "shadow.md").write_text(role_frontmatter("smart-cascade-leader"), encoding="utf-8")
        shadowed = check_adapter(project, profiles, config_path, omp, adapter_env)
        shadowed_receipt = json.loads(shadowed.stdout)
        assert shadowed.returncode == 0 and shadowed_receipt["status"] == "ADAPTER_READY" and any("shadows" in warning for warning in shadowed_receipt["warnings"]), shadowed.stdout
        shutil.rmtree(project / ".omp")

        rewrite_yaml(installed_config, lambda document: document["task"]["isolation"].update({"apply": True}))
        rejected_apply = check_adapter(project, profiles, config_path, omp, adapter_env)
        assert rejected_apply.returncode != 0 and "task/isolation projection is stale" in rejected_apply.stdout, rejected_apply.stdout
        shutil.copy2(PROFILE_SOURCE / "config.yml", installed_config)

        patch = root / "candidate.patch"
        patch.write_text("patch bytes", encoding="utf-8")
        packet = root / "packet.json"
        packet_value = {"task_name": "ChildA", "result_schema": {"type": "object"}}
        packet.write_text(json.dumps(packet_value), encoding="utf-8")
        settlement = {"status": "DONE"}
        runtime_id = "LeaderA.ChildA"
        parent = write_transcript(root, runtime_id, rendered(runtime_id, "smart-cascade-executor", settlement, patch), packet_value)
        normalized = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(parent), "--runtime-id", runtime_id, "executor", str(packet))
        assert normalized.returncode == 0, normalized.stdout
        batch_root = root / "batch"
        batch_root.mkdir()
        batch_parent = batch_root / "LeaderA.jsonl"
        batch_entries = [json.loads(line) for line in parent.read_text(encoding="utf-8").splitlines()]
        flat_args = batch_entries[1]["message"]["content"][0]["arguments"]
        batch_entries[1]["message"]["content"][0]["arguments"] = {"context": "shared", "tasks": [flat_args]}
        batch_parent.write_text("\n".join(json.dumps(item) for item in batch_entries) + "\n", encoding="utf-8")
        shutil.copytree(parent.with_suffix(""), batch_parent.with_suffix(""))
        normalized_batch = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(batch_parent), "--runtime-id", runtime_id, "executor", str(packet))
        assert normalized_batch.returncode == 0, normalized_batch.stdout
        result = json.loads(normalized.stdout)
        assert result["status"] == "completed" and result["settlement"] == settlement and result["artifact"]["path"] == str(patch.resolve())

        rework_root = root / "rework"
        rework_root.mkdir()
        rework_parent = rework_root / "LeaderA.jsonl"
        rework_entries = [json.loads(line) for line in parent.read_text(encoding="utf-8").splitlines()]
        stale_call = json.loads(json.dumps(rework_entries[1]))
        stale_call["timestamp"] = "2026-08-27T00:00:00.500Z"
        stale_args = stale_call["message"]["content"][0]["arguments"]
        stale_args["outputSchema"] = {"type": "string"}
        stale_args["task"] = "old attempt without current digest"
        rework_entries.insert(1, stale_call)
        rework_parent.write_text("\n".join(json.dumps(item) for item in rework_entries) + "\n", encoding="utf-8")
        shutil.copytree(parent.with_suffix(""), rework_parent.with_suffix(""))
        normalized_rework = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(rework_parent), "--runtime-id", runtime_id, "executor", str(packet))
        assert normalized_rework.returncode == 0, normalized_rework.stdout

        leader_rework_root = root / "leader-rework"
        leader_rework_root.mkdir()
        leader_runtime_id = "ChildA-10"
        leader_rework_parent = write_transcript(leader_rework_root, leader_runtime_id, rendered(leader_runtime_id, "smart-cascade-leader", settlement, patch), packet_value, agent="smart-cascade-leader", model_role="smart-cascade-leader", resolved_model="clp/gpt-5.6-sol:medium")
        normalized_leader_rework = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(leader_rework_parent), "--runtime-id", leader_runtime_id, "leader", str(packet))
        assert normalized_leader_rework.returncode == 0, normalized_leader_rework.stdout

        stale_packet = root / "stale-packet.json"
        stale_packet.write_text(json.dumps({"task_name": "OtherChild", "result_schema": {"type": "object"}}), encoding="utf-8")
        rejected_stale = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(parent), "--runtime-id", runtime_id, "executor", str(stale_packet))
        assert rejected_stale.returncode != 0 and ("task invocation" in rejected_stale.stdout or "runtime identity" in rejected_stale.stdout), rejected_stale.stdout
        wrong_schema_root = root / "wrong-schema"
        wrong_schema_root.mkdir()
        wrong_schema_parent = wrong_schema_root / "LeaderA.jsonl"
        wrong_schema_entries = [json.loads(line) for line in parent.read_text(encoding="utf-8").splitlines()]
        wrong_schema_entries[1]["message"]["content"][0]["arguments"]["outputSchema"] = {"type": "string"}
        wrong_schema_parent.write_text("\n".join(json.dumps(item) for item in wrong_schema_entries) + "\n", encoding="utf-8")
        shutil.copytree(parent.with_suffix(""), wrong_schema_parent.with_suffix(""))
        rejected_schema = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(wrong_schema_parent), "--runtime-id", runtime_id, "executor", str(packet))
        assert rejected_schema.returncode != 0 and "matching task invocation" in rejected_schema.stdout, rejected_schema.stdout

        wrong_assignment_root = root / "wrong-assignment"
        wrong_assignment_root.mkdir()
        wrong_assignment_parent = wrong_assignment_root / "LeaderA.jsonl"
        wrong_assignment_entries = [json.loads(line) for line in parent.read_text(encoding="utf-8").splitlines()]
        wrong_assignment_entries[1]["message"]["content"][0]["arguments"]["task"] = "unbound assignment"
        wrong_assignment_parent.write_text("\n".join(json.dumps(item) for item in wrong_assignment_entries) + "\n", encoding="utf-8")
        shutil.copytree(parent.with_suffix(""), wrong_assignment_parent.with_suffix(""))
        rejected_assignment = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(wrong_assignment_parent), "--runtime-id", runtime_id, "executor", str(packet))
        assert rejected_assignment.returncode != 0 and "matching task invocation" in rejected_assignment.stdout, rejected_assignment.stdout

        wrong_runtime = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(parent), "--runtime-id", "LeaderA.OtherChild", "executor", str(packet))
        assert wrong_runtime.returncode != 0 and ("spawn receipt" in wrong_runtime.stdout or "runtime lineage" in wrong_runtime.stdout or "runtime identity" in wrong_runtime.stdout), wrong_runtime.stdout
        unbound = root / "unbound"
        unbound.mkdir()
        unbound_parent = unbound / "LeaderA.jsonl"
        unbound_entries = [json.loads(line) for line in parent.read_text(encoding="utf-8").splitlines()]
        unbound_entries[-1]["message"].pop("toolCallId")
        unbound_parent.write_text("\n".join(json.dumps(item) for item in unbound_entries) + "\n", encoding="utf-8")
        shutil.copytree(parent.with_suffix(""), unbound_parent.with_suffix(""))
        rejected_unbound = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(unbound_parent), "--runtime-id", runtime_id, "executor", str(packet))
        assert rejected_unbound.returncode != 0 and "bound terminal" in rejected_unbound.stdout, rejected_unbound.stdout

        failed_root = root / "failed"
        failed_root.mkdir()
        failed_parent = write_transcript(failed_root, runtime_id, rendered(runtime_id, "smart-cascade-executor", settlement, patch), packet_value)
        failed_entries = [json.loads(line) for line in failed_parent.read_text(encoding="utf-8").splitlines()]
        failed_job = failed_entries[-1]["message"]["details"]["jobs"][0]
        failed_job["status"] = "failed"
        failed_job.pop("resultText")
        failed_job["errorText"] = "provider unavailable"
        failed_parent.write_text("\n".join(json.dumps(item) for item in failed_entries) + "\n", encoding="utf-8")
        normalized_failed = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(failed_parent), "--runtime-id", runtime_id, "executor", str(packet))
        assert normalized_failed.returncode == 0 and json.loads(normalized_failed.stdout) == {"artifact": None, "reason": "provider unavailable", "schema_version": 1, "settlement": {}, "status": "failed"}, normalized_failed.stdout

        failed_patch_root = root / "failed-patch"
        failed_patch_root.mkdir()
        failed_patch_parent = write_transcript(failed_patch_root, runtime_id, rendered(runtime_id, "smart-cascade-executor", settlement, patch), packet_value)
        failed_patch_entries = [json.loads(line) for line in failed_patch_parent.read_text(encoding="utf-8").splitlines()]
        failed_patch_job = failed_patch_entries[-1]["message"]["details"]["jobs"][0]
        failed_patch_job["status"] = "failed"
        failed_patch_job["errorText"] = rendered(runtime_id, "smart-cascade-executor", settlement, patch).replace('status="completed"', 'status="failed (exit 1)"').split("\n\n" + runtime_id + " is now idle", 1)[0]
        failed_patch_job.pop("resultText")
        failed_patch_parent.write_text("\n".join(json.dumps(item) for item in failed_patch_entries) + "\n", encoding="utf-8")
        normalized_failed_patch = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(failed_patch_parent), "--runtime-id", runtime_id, "executor", str(packet))
        failed_patch_result = json.loads(normalized_failed_patch.stdout)
        assert normalized_failed_patch.returncode == 0 and failed_patch_result["status"] == "failed" and failed_patch_result["artifact"]["path"] == str(patch.resolve()), normalized_failed_patch.stdout

        blocker_root = root / "blocker"
        blocker_root.mkdir()
        blocker_settlement = {"status": "BLOCKED", "child_id": "child-a", "slice_id": "slice-a", "attempt_id": "attempt-a", "reason": "dependency unavailable"}
        blocker_parent = write_transcript(blocker_root, runtime_id, rendered_without_patch(runtime_id, "smart-cascade-executor", blocker_settlement), packet_value)
        blocker_entries = [json.loads(line) for line in blocker_parent.read_text(encoding="utf-8").splitlines()]
        blocker_entries[-1]["message"]["details"]["jobs"][0]["resultText"] = rendered_without_patch(runtime_id, "smart-cascade-executor", blocker_settlement)
        blocker_parent.write_text("\n".join(json.dumps(item) for item in blocker_entries) + "\n", encoding="utf-8")
        normalized_blocker = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(blocker_parent), "--runtime-id", runtime_id, "executor", str(packet))
        blocker_result = json.loads(normalized_blocker.stdout)
        assert normalized_blocker.returncode == 0 and blocker_result == {"artifact": None, "reason": None, "schema_version": 1, "settlement": blocker_settlement, "status": "completed"}, normalized_blocker.stdout
        conflicting = root / "conflicting"
        conflicting.mkdir()
        conflicting_parent = conflicting / "LeaderA.jsonl"
        conflict_entry = {"type": "message", "message": {"role": "toolResult", "toolCallId": "hub-a", "toolName": "hub", "details": {"op": "wait", "jobs": [{"id": runtime_id, "type": "task", "status": "failed", "resolvedModel": "clp/gpt-5.6-luna:xhigh", "errorText": "failed"}]}}}
        conflicting_parent.write_text(parent.read_text(encoding="utf-8") + json.dumps(conflict_entry) + "\n", encoding="utf-8")
        shutil.copytree(parent.with_suffix(""), conflicting_parent.with_suffix(""))
        rejected_conflict = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(conflicting_parent), "--runtime-id", runtime_id, "executor", str(packet))
        assert rejected_conflict.returncode != 0 and "conflicting terminal" in rejected_conflict.stdout, rejected_conflict.stdout
        repeated = root / "repeated"
        repeated.mkdir()
        repeated_parent = repeated / "LeaderA.jsonl"
        repeated_job = {"id": runtime_id, "type": "task", "status": "completed", "label": runtime_id, "durationMs": 9999, "resolvedModel": "clp/gpt-5.6-luna:xhigh", "resultText": rendered(runtime_id, "smart-cascade-executor", settlement, patch)}
        repeated_entry = {"type": "message", "message": {"role": "toolResult", "toolCallId": "hub-a", "toolName": "hub", "details": {"op": "wait", "jobs": [repeated_job]}}}
        repeated_parent.write_text(parent.read_text(encoding="utf-8") + json.dumps(repeated_entry) + "\n", encoding="utf-8")
        shutil.copytree(parent.with_suffix(""), repeated_parent.with_suffix(""))
        accepted_repeat = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(repeated_parent), "--runtime-id", runtime_id, "executor", str(packet))
        assert accepted_repeat.returncode == 0, accepted_repeat.stdout

        stale_session = root / "stale-session"
        stale_session.mkdir()
        stale_parent = stale_session / "LeaderA.jsonl"
        stale_parent.write_text(parent.read_text(encoding="utf-8"), encoding="utf-8")
        shutil.copytree(parent.with_suffix(""), stale_parent.with_suffix(""))
        child_file = stale_parent.with_suffix("") / f"{runtime_id}.jsonl"
        child_entries = [json.loads(line) for line in child_file.read_text(encoding="utf-8").splitlines()]
        child_entries[0]["cwd"] = str(root)
        child_file.write_text("\n".join(json.dumps(item) for item in child_entries) + "\n", encoding="utf-8")
        rejected_stale_session = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(stale_parent), "--runtime-id", runtime_id, "executor", str(packet))
        assert rejected_stale_session.returncode != 0 and "not isolated" in rejected_stale_session.stdout, rejected_stale_session.stdout
        stale_time = root / "stale-time"
        stale_time.mkdir()
        stale_time_parent = stale_time / "LeaderA.jsonl"
        stale_time_parent.write_text(parent.read_text(encoding="utf-8"), encoding="utf-8")
        shutil.copytree(parent.with_suffix(""), stale_time_parent.with_suffix(""))
        stale_time_child = stale_time_parent.with_suffix("") / f"{runtime_id}.jsonl"
        stale_time_entries = [json.loads(line) for line in stale_time_child.read_text(encoding="utf-8").splitlines()]
        stale_time_entries[0]["timestamp"] = "2026-08-26T23:59:59Z"
        stale_time_child.write_text("\n".join(json.dumps(item) for item in stale_time_entries) + "\n", encoding="utf-8")
        rejected_stale_time = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(stale_time_parent), "--runtime-id", runtime_id, "executor", str(packet))
        assert rejected_stale_time.returncode != 0 and "predates" in rejected_stale_time.stdout, rejected_stale_time.stdout
        forged_root = root / "forged"
        forged_root.mkdir()
        forged = forged_root / "LeaderA.jsonl"
        forged.write_text(parent.read_text(encoding="utf-8").replace(str(patch), str(root / "forged.patch")), encoding="utf-8")
        shutil.copytree(parent.with_suffix(""), forged.with_suffix(""))
        rejected_forged = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(forged), "--runtime-id", runtime_id, "executor", str(packet))
        assert rejected_forged.returncode != 0 and "retained patch" in rejected_forged.stdout, rejected_forged.stdout

        prompt_root = root / "prompt-only"
        prompt_root.mkdir()
        prompt_only = prompt_root / "LeaderA.jsonl"
        prompt_only.write_text(json.dumps({"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": rendered(runtime_id, "smart-cascade-executor", settlement, patch)}]}}) + "\n", encoding="utf-8")
        rejected_prompt = run(str(NORMALIZE), "--config", str(config_path), "--parent-transcript", str(prompt_only), "--runtime-id", runtime_id, "executor", str(packet))
        assert rejected_prompt.returncode != 0 and "task invocation" in rejected_prompt.stdout, rejected_prompt.stdout

    subprocess.run([sys.executable, "-m", "py_compile", str(ADAPTER), str(NORMALIZE)], check=True)
    print('{"status":"OMP_ADAPTER_TESTS_PASSED"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
