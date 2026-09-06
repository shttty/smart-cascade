#!/usr/bin/env python3
"""Deterministic OMP adapter installation-admission tests."""

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
ADAPTER = RUNNER_ROOT / "adapter.py"
CONFIG_SOURCE = RUNNER_ROOT / "runner-launch.yaml"
ROLE_SOURCE = RUNNER_ROOT / "roles"
MODEL_ROLES = {
    "smart-cascade-root": "example/model-root",
    "smart-cascade-leader": "example/model-leader",
    "smart-cascade-advisor": "example/model-advisor",
    "smart-cascade-semantic": "example/model-semantic",
    "smart-cascade-escalated-semantic": "example/model-escalated",
    "smart-cascade-mechanical": "example/model-mechanical",
}


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, check=False)


def write_fake_omp(package: Path, version: str = "18.0.4") -> Path:
    executable = package / "dist/cli.js"
    executable.parent.mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({
        "name": "@oh-my-pi/pi-coding-agent", "version": version, "bin": {"omp": "dist/cli.js"},
    }), encoding="utf-8")
    executable.write_text(f"#!/usr/bin/env bash\nif [[ $1 == --version ]]; then printf '%s\\n' 'omp/{version}'; exit; fi\n", encoding="utf-8")
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




def write_profile_config(path: Path) -> None:
    profile = {
        "modelRoles": dict(MODEL_ROLES),
        "async": {"enabled": True},
        "task": {
            "batch": True,
            "maxRecursionDepth": 2,
            "isolation": {"mode": "auto", "apply": False, "merge": "patch"},
        },
    }
    path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")


def install_profile(destination: Path) -> None:
    """Create a minimal user-owned profile, then project Smart Cascade roles."""
    destination.mkdir(parents=True)
    (destination / "agents").mkdir()
    write_profile_config(destination / "config.yml")
    for role in ROLE_SOURCE.glob("*.md"):
        shutil.copy2(role, destination / "agents" / role.name)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="smart-cascade-omp-adapter-") as raw:
        root = Path(raw)
        project = root / "project"
        project.mkdir()
        config = yaml.safe_load(CONFIG_SOURCE.read_text(encoding="utf-8"))
        config["runner"]["adapter_check"] = str(ADAPTER)
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
        assert receipt["status"] == "ADAPTER_READY" and receipt["profile_name"] == "smart-cascade-omp" and receipt["warnings"] == []

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
        assert rejected_missing_model.returncode != 0 and "lacks required model roles" in rejected_missing_model.stdout, rejected_missing_model.stdout
        write_profile_config(installed_config)

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
        write_profile_config(installed_config)
    subprocess.run([sys.executable, "-m", "py_compile", str(ADAPTER)], check=True)
    print('{"status":"OMP_ADAPTER_TESTS_PASSED"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
