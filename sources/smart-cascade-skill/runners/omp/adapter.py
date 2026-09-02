#!/usr/bin/env python3
"""Check the OMP Smart Cascade adapter against explicit inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

import yaml

sys.dont_write_bytecode = True
OMP_VERIFIED = ["config_projection", "profile_projection", "role_projection", "package_identity", "capability_declarations", "rpc_startup"]


class AdapterError(RuntimeError):
    pass


def fail(message: str) -> NoReturn:
    raise AdapterError(message)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_yaml(path: Path, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        fail(f"{label} is unreadable or invalid: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a mapping")
    return value


def resolve(base: Path, raw: str) -> Path:
    path = Path(os.path.expanduser(os.path.expandvars(raw)))
    return (path if path.is_absolute() else base / path).resolve()


def profile_location(value: str | None, default_name: str) -> tuple[Path, str]:
    if value is None:
        return (Path.home() / ".omp" / "profiles").resolve(), default_name
    expanded = Path(os.path.expanduser(os.path.expandvars(value)))
    if expanded.is_absolute() or "/" in value:
        profile = expanded.resolve()
        if not profile.name or profile.parent == profile:
            fail("OMP profile path is invalid")
        return profile.parent, profile.name
    if not value.strip() or value in {".", ".."}:
        fail("OMP profile name is invalid")
    return (Path.home() / ".omp" / "profiles").resolve(), value


def load_override(project_root: Path) -> tuple[Path, str] | None:
    path = project_root / ".smart-cascade" / "override.yaml"
    if not path.exists():
        return None
    document = read_yaml(path, "Smart Cascade project override")
    if set(document) != {"profile_name", "profiles_root"}:
        fail("Smart Cascade project override must contain only profile_name and profiles_root")
    name = document.get("profile_name")
    root = document.get("profiles_root")
    if not isinstance(name, str) or not name or not isinstance(root, str) or not root:
        fail("Smart Cascade project override profile selection is invalid")
    return Path(root).expanduser().resolve(), name


def save_override(project_root: Path, profiles_root: Path, profile_name: str) -> None:
    path = project_root / ".smart-cascade" / "override.yaml"
    write_atomic(path, yaml.safe_dump({"profile_name": profile_name, "profiles_root": str(profiles_root)}, sort_keys=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("--project-root", type=Path, required=True)
    check.add_argument("--config", type=Path)
    check.add_argument("--profile")
    check.add_argument("--omp-bin", type=Path, required=True)
    args = parser.parse_args()
    runner_root = Path(__file__).resolve().parent
    skill_root = runner_root.parents[1]
    project_root = args.project_root.resolve()
    config_path = (args.config.resolve() if args.config else runner_root / "runner-launch.yaml")
    omp_bin = args.omp_bin.resolve()
    if not project_root.is_dir() or not config_path.is_file() or not omp_bin.is_file() or not os.access(omp_bin, os.X_OK):
        fail("project, adapter config, and executable inputs must exist")
    config = read_yaml(config_path, "OMP adapter config")
    runner = config.get("runner")
    contract = config.get("dispatch_contract")
    root = config.get("root")
    roles = config.get("roles")
    if not isinstance(runner, dict) or runner.get("kind") != "omp" or not isinstance(contract, dict) or not isinstance(root, dict) or not isinstance(roles, dict):
        fail("OMP adapter config lacks runner, dispatch, root, or role projections")
    operation_paths = {key: resolve(runner_root if key != "interface" else skill_root, runner.get(key, "")) for key in ("adapter_check", "adapter_normalize", "interface")}
    if operation_paths["adapter_check"] != Path(__file__).resolve() or any(not path.is_file() for path in operation_paths.values()):
        fail("OMP runner operation paths are missing or do not select this adapter")
    default_profile_name = contract.get("profile_name")
    if not isinstance(default_profile_name, str) or not default_profile_name:
        fail("OMP adapter profile_name is missing")
    selected = profile_location(args.profile, default_profile_name) if args.profile is not None else load_override(project_root)
    if selected is None:
        profiles_root, profile_name = profile_location(None, default_profile_name)
    else:
        profiles_root, profile_name = selected
    installed_agent = profiles_root / profile_name / "agent"
    installed_config = installed_agent / "config.yml"
    # The installed profile is runtime authority. The skill owns only admission
    # expectations and role identities; it does not bundle the profile tree.
    installed = read_yaml(installed_config, "installed OMP profile")
    warnings: list[str] = []
    launch = root.get("launch_argv")
    if not isinstance(launch, list) or any(not isinstance(item, str) or not item for item in launch):
        fail("OMP Root launch_argv is invalid")
    profile_index = launch.index("--profile") if "--profile" in launch else -1
    if profile_index < 0 or profile_index + 1 >= len(launch):
        fail("OMP Root launch_argv does not select a profile")
    model_index = launch.index("--model") if "--model" in launch else -1
    if model_index < 0 or model_index + 1 >= len(launch) or launch[model_index + 1] != "@smart-cascade-root":
        fail("OMP Root launch_argv does not select the Root model role")
    # Subset check: the Smart Cascade roles the runner projects must exist and
    # point at the admitted models. Extra model roles are the project's business.
    required_roles = {
        "smart-cascade-root": root.get("model"),
        "smart-cascade-leader": roles.get("leader", {}).get("model") if isinstance(roles.get("leader"), dict) else None,
        "smart-cascade-advisor": roles.get("advisor", {}).get("model") if isinstance(roles.get("advisor"), dict) else None,
        "smart-cascade-semantic": roles.get("semantic_executor", {}).get("model") if isinstance(roles.get("semantic_executor"), dict) else None,
        "smart-cascade-escalated-semantic": roles.get("escalated_semantic_executor", {}).get("model") if isinstance(roles.get("escalated_semantic_executor"), dict) else None,
        "smart-cascade-mechanical": roles.get("mechanical_executor", {}).get("model") if isinstance(roles.get("mechanical_executor"), dict) else None,
    }
    installed_roles = installed.get("modelRoles")
    if not isinstance(installed_roles, dict):
        fail("installed OMP profile lacks modelRoles")
    missing_roles = sorted(name for name, model in required_roles.items() if installed_roles.get(name) != model)
    if missing_roles:
        fail(f"installed OMP profile model role projection is stale: {', '.join(missing_roles)}")
    if installed.get("async") != {"enabled": True}:
        fail("OMP profile must enable async")
    task = installed.get("task")
    if not isinstance(task, dict) or task.get("batch") is not True or task.get("maxRecursionDepth") != 2 or task.get("isolation") != {"mode": "auto", "apply": False, "merge": "patch"}:
        fail("OMP profile task/isolation projection is stale")
    role_paths = contract.get("roles")
    role_keys = {"leader", "advisor", "semantic_executor", "escalated_semantic_executor", "mechanical_executor"}
    if not isinstance(role_paths, dict) or set(role_paths) != role_keys or set(roles) != role_keys:
        fail("OMP adapter requires the complete production role set")
    production_names: set[str] = set()
    expected_spawns = ["smart-cascade-executor", "smart-cascade-escalated-executor", "smart-cascade-mechanical-executor"]
    for key in sorted(role_keys):
        raw = role_paths[key]
        projection = roles[key]
        if not isinstance(raw, str) or not raw or not isinstance(projection, dict):
            fail(f"OMP adapter role projection is invalid: {key}")
        source = resolve(runner_root, raw)
        installed_role = installed_agent / "agents" / source.name
        if not source.is_file():
            fail(f"Smart Cascade role definition is missing: {source.name}")
        if not installed_role.is_file():
            fail(f"installed OMP role is missing: {source.name}")
        if installed_role.read_bytes() != source.read_bytes():
            warnings.append(f"installed OMP role differs from the skill copy: {source.name}")
        text = installed_role.read_text(encoding="utf-8")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            fail(f"installed OMP role lacks frontmatter: {source.name}")
        frontmatter = yaml.safe_load(text[4:text.find("\n---\n", 4)])
        expected_model_role = projection.get("model_role")
        if not isinstance(frontmatter, dict) or frontmatter.get("name") != projection.get("agent"):
            fail(f"installed OMP role frontmatter differs from runner projection: {source.name}")
        if frontmatter.get("model") != f"@{expected_model_role}":
            warnings.append(f"installed OMP role model differs from runner projection: {source.name}")
        if frontmatter.get("thinkingLevel") != projection.get("thinking_level"):
            warnings.append(f"installed OMP role thinkingLevel differs from runner projection: {source.name}")
        if key == "leader" and frontmatter.get("spawns") != expected_spawns:
            warnings.append("installed OMP Leader spawn projection differs from runner projection")
        production_names.add(frontmatter["name"])
    project_agents = project_root / ".omp" / "agents"
    if project_agents.exists():
        if not project_agents.is_dir():
            fail("project .omp/agents path is not a directory")
        for shadow in sorted(project_agents.glob("*.md")):
            text = shadow.read_text(encoding="utf-8")
            if not text.startswith("---\n") or "\n---\n" not in text[4:]:
                continue
            frontmatter = yaml.safe_load(text[4:text.find("\n---\n", 4)])
            declared = frontmatter.get("name") if isinstance(frontmatter, dict) else None
            if declared in production_names:
                warnings.append(f"project agent shadows installed OMP adapter role {declared}; admission continues")
    package_root: Path | None = None
    for parent in (omp_bin.parent, *omp_bin.parents):
        metadata = parent / "package.json"
        if metadata.is_file() and json.loads(metadata.read_text(encoding="utf-8")).get("name") == "@oh-my-pi/pi-coding-agent":
            package_root = parent
            break
    if package_root is None:
        fail("OMP executable is not owned by @oh-my-pi/pi-coding-agent")
    metadata = json.loads((package_root / "package.json").read_text(encoding="utf-8"))
    version = metadata.get("version")
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", version if isinstance(version, str) else "")
    if match is None or tuple(map(int, match.groups())) < (18, 0, 0):
        fail(f"OMP version is outside supported >=18.0.0: {version}")
    bin_value = metadata.get("bin", {}).get("omp") if isinstance(metadata.get("bin"), dict) else None
    if not isinstance(bin_value, str) or (package_root / bin_value).resolve() != omp_bin:
        fail("OMP executable identity does not match package bin.omp")
    exports = metadata.get("exports")
    required_exports = {"./modes/rpc/*", "./task", "./task/*", "./tools/hub", "./tools/hub/*"}
    if not isinstance(exports, dict) or not required_exports <= set(exports):
        fail("OMP package lacks required RPC/task/Hub exports")
    declarations = {
        package_root / "dist/types/modes/rpc/rpc-types.d.ts": ["negotiate_protocol", "get_subagents", "get_subagent_messages", "supportedProtocolVersions", "interface RpcSubagentSnapshot", "sessionFile?", "progress?"],
        package_root / "dist/types/task/types.d.ts": ["interface SubagentLifecyclePayload", "interface AgentProgress", "modelRole?", "resolvedModel?", "schemaMode?", "isolated?"],
        package_root / "dist/types/tools/hub/types.d.ts": ["type HubOp", "interface CoordinationDetails", "receipts?: IrcDeliveryReceipt[]"],
    }
    for path, tokens in declarations.items():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            fail(f"OMP capability declaration is missing: {path}: {exc}")
        missing = [token for token in tokens if token not in text]
        if missing:
            fail(f"OMP capability declaration is stale: {path.name}: {', '.join(missing)}")
    declaration_digests = {str(path.relative_to(package_root)): digest(path) for path in declarations}
    operation_digests = {key: digest(path) for key, path in operation_paths.items()}
    reported = subprocess.run([str(omp_bin), "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10, check=False)
    if reported.returncode != 0 or reported.stdout.strip() != f"omp/{version}":
        fail("OMP executable version differs from package metadata")
    # The admission probe is a throwaway OMP process. It must not be mistaken for the
    # pane's real agent: the herdr extension claims pane ownership purely from inherited
    # HERDR_* env vars, so an un-scrubbed probe reports its own ephemeral session id and
    # strips lifecycle authority from the parent agent (which then appears stuck at idle).
    # Belt and braces: drop the env vars AND disable extension discovery.
    probe_env = {key: value for key, value in os.environ.items() if not key.startswith("HERDR_")}
    rpc = subprocess.run([str(omp_bin), "--mode", "rpc", "--no-session", "--no-extensions"], input='{"id":"smart-cascade-admission","type":"negotiate_protocol","protocolVersion":2}\n', text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False, env=probe_env)
    frames = []
    for line in rpc.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            frames.append(value)
    ready = next((frame for frame in frames if frame.get("type") == "ready"), None)
    negotiated = next((frame for frame in frames if frame.get("type") == "response" and frame.get("id") == "smart-cascade-admission"), None)
    if rpc.returncode != 0 or not isinstance(ready, dict) or 2 not in ready.get("supportedProtocolVersions", []) or not isinstance(negotiated, dict) or negotiated.get("success") is not True or negotiated.get("command") != "negotiate_protocol" or negotiated.get("data", {}).get("protocolVersion") != 2:
        fail("OMP executable failed bounded RPC protocol-v2 negotiation")
    role_digests = {source.name: digest(source) for source in sorted(resolve(runner_root, raw) for raw in role_paths.values())}
    receipt = {
        "schema_version": 1,
        "status": "ADAPTER_READY",
        "adapter": "omp",
        "config": str(config_path),
        "config_digest": digest(config_path),
        "profile_name": profile_name,
        "profile_root": str(profiles_root),
        "profile_config_digest": digest(installed_config),
        "role_digests": role_digests,
        "warnings": warnings,
        "omp_executable": str(omp_bin),
        "omp_executable_digest": digest(omp_bin),
        "omp_package_root": str(package_root),
        "operation_digests": operation_digests,
        "declaration_digests": declaration_digests,
        "omp_package_digest": digest(package_root / "package.json"),
        "omp_version": version,
        "rpc_protocol": 2,
        "verified": OMP_VERIFIED,
        "not_live_tested": ["dispatch", "hub_delivery", "strict_settlement", "recovery", "retained_patch_capture"],
    }
    if args.profile is not None:
        save_override(project_root, profiles_root, profile_name)
    print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AdapterError, OSError, json.JSONDecodeError, yaml.YAMLError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "adapter": "omp", "reason": str(exc)}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        raise SystemExit(1)
