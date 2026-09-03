#!/usr/bin/env python3
"""Deterministic platform-neutral Smart Cascade core and reference-adapter tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = SKILL_ROOT / "bootstrap"
CONTRACTS = BOOTSTRAP / "contracts.py"
FAKE = REPO_ROOT / "sources/smart-cascade-fake/adapter.py"
INITIALIZE = BOOTSTRAP / "initialize.py"

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "child_id": {"type": "string"},
        "slice_id": {"type": "string"},
        "attempt_id": {"type": "string"},
        "changed_paths": {"type": "array", "items": {"type": "string"}},
        "checks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["child_id", "slice_id", "attempt_id"],
    "oneOf": [
        {"properties": {"status": {"const": "DONE"}}, "required": ["status", "changed_paths", "checks", "evidence"]},
        {"properties": {"status": {"enum": ["BLOCKED", "BLOCKED_ENVIRONMENT", "BLOCKED_ARCHITECTURE"]}}, "required": ["status", "reason"]},
    ],
    "additionalProperties": False,
}


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, check=False)


def write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout.strip()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="smart-cascade-core-") as raw:
        root = Path(raw)
        project = root / "project"
        project.mkdir()
        shutil.copytree(SKILL_ROOT, root / "skill")
        shutil.copytree(REPO_ROOT / ".smart-cascade", project / ".smart-cascade")
        scrubbed_home = root / "home"
        scrubbed_home.mkdir()
        minimal_bin = root / "bin"
        minimal_bin.mkdir()
        for name in ("python3", "git"):
            source = shutil.which(name)
            assert source
            (minimal_bin / name).symlink_to(source)
        environment = {"HOME": str(scrubbed_home), "PATH": str(minimal_bin), "LANG": "C.UTF-8"}
        before_preflight = sorted(str(path.relative_to(project)) for path in project.rglob("*"))
        preflight = run([str(minimal_bin / "python3"), str(root / "skill/bootstrap/initialize.py"), "--project-root", str(project)], cwd=project, env=environment)
        assert preflight.returncode == 0 and json.loads(preflight.stdout)["created"] == [], preflight.stdout
        assert sorted(str(path.relative_to(project)) for path in project.rglob("*")) == before_preflight
        first = run([str(minimal_bin / "python3"), str(root / "skill/bootstrap/initialize.py"), "--project-root", str(project), "--create-state"], cwd=project, env=environment)
        assert first.returncode == 0, first.stdout
        first_receipt = json.loads(first.stdout)
        assert first_receipt["status"] == "CORE_READY" and sorted(first_receipt["created"]) == ["control/dispatches", "control/receipts", "state"]
        second = run([str(minimal_bin / "python3"), str(root / "skill/bootstrap/initialize.py"), "--project-root", str(project), "--create-state"], cwd=project, env=environment)
        assert second.returncode == 0 and json.loads(second.stdout)["created"] == [], second.stdout
        assert not (scrubbed_home / ".omp").exists()
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "test@example.invalid")
        git(repo, "config", "user.name", "Smart Cascade Test")
        (repo / "src").mkdir()
        (repo / "src/file.txt").write_text("before\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "base")
        base = git(repo, "rev-parse", "HEAD")
        (repo / "src/file.txt").write_text("after\n", encoding="utf-8")
        patch = root / "candidate.patch"
        patch.write_bytes(subprocess.run(["git", "diff", "--binary"], cwd=repo, stdout=subprocess.PIPE, check=True).stdout)
        git(repo, "checkout", "--", "src/file.txt")

        packet = {
            "role": "executor", "task_name": "ChildA", "slice_id": "slice-a", "child_id": "child-a", "attempt_id": "child-a-attempt-1", "base": base,
            "checks": ["read exact bytes"], "non_goals": [], "postcondition": "src/file.txt contains after", "result_schema": SCHEMA,
        }
        settlement = {"status": "DONE", "slice_id": "slice-a", "child_id": "child-a", "attempt_id": "child-a-attempt-1", "changed_paths": ["src/file.txt"], "checks": ["exact bytes: passed"], "evidence": "focused check passed"}
        packet_path = write(root / "packet.json", packet)
        settlement_path = write(root / "settlement.json", settlement)
        valid_packet = run([sys.executable, str(CONTRACTS), "--repo-root", str(repo), "packet", "executor", str(packet_path)], cwd=repo)
        assert valid_packet.returncode == 0, valid_packet.stdout
        assert json.loads(valid_packet.stdout)["status"] == "PACKET_VALID"

        leader_schema = {
            "type": "object",
            "properties": {
                "status": {"const": "READY_FOR_ROOT_REVIEW"},
                "slice_id": {"const": "slice-a"},
                "attempt_id": {"const": "leader-attempt-1"},
                "execution_path": {"enum": ["direct", "delegated", "mixed"]},
                "children": {"type": "array", "items": {"type": "string"}},
                "candidate_evidence": {
                    "type": "object",
                    "properties": {
                        "base": {"const": base},
                        "changed_paths": {"type": "array", "items": {"type": "string"}},
                        "checks": {"type": "array", "items": {"type": "string"}},
                        "evidence": {"type": "string"},
                    },
                    "required": ["base", "changed_paths", "checks", "evidence"],
                    "additionalProperties": False,
                },
                "preserved_attempts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "slice_id", "attempt_id", "execution_path", "children", "candidate_evidence", "preserved_attempts"],
            "additionalProperties": False,
        }
        leader_packet = {
            "role": "leader", "task_name": "LeaderA", "slice_id": "slice-a", "attempt_id": "leader-attempt-1", "base": base,
            "scope": "mutate src only",
            "dependencies": [], "checks": ["read exact bytes"], "non_goals": [], "result_schema": leader_schema,
        }
        queue_path = root / "queue.toml"
        queue_path.write_text('[[slices]]\nid = "slice-a"\ndepends_on = []\nscope = "mutate src only"\nchecks = ["read exact bytes"]\n', encoding="utf-8")
        leader_packet_path = write(root / "leader-packet.json", leader_packet)
        valid_leader_packet = run([sys.executable, str(CONTRACTS), "--repo-root", str(repo), "packet", "leader", str(leader_packet_path), "--queue", str(queue_path)], cwd=repo)
        assert valid_leader_packet.returncode == 0, valid_leader_packet.stdout
        assert json.loads(valid_leader_packet.stdout)["status"] == "PACKET_VALID"
        widened_leader = dict(leader_packet, scope="mutate src and everything else")
        rejected_widened = run([sys.executable, str(CONTRACTS), "--repo-root", str(repo), "packet", "leader", str(write(root / "widened-leader.json", widened_leader)), "--queue", str(queue_path)], cwd=repo)
        assert rejected_widened.returncode != 0 and "approved queue slice" in rejected_widened.stdout, rejected_widened.stdout

        check = run([sys.executable, str(FAKE), "check"], cwd=repo)
        assert check.returncode == 0 and json.loads(check.stdout) == {"schema_version": 1, "status": "ADAPTER_READY", "adapter": "fake"}, check.stdout
        completed = run([sys.executable, str(FAKE), "normalize", "--packet", str(packet_path), "--settlement", str(settlement_path), "--artifact", str(patch), "--outcome", "completed"], cwd=repo)
        assert completed.returncode == 0, completed.stdout
        result_path = write(root / "result.json", json.loads(completed.stdout))
        validated = run([sys.executable, str(CONTRACTS), "--repo-root", str(repo), "result", "executor", str(packet_path), str(result_path)], cwd=repo)
        assert validated.returncode == 0, validated.stdout
        assert json.loads(validated.stdout)["status"] == "RESULT_VALID"

        failed_preserved = run([sys.executable, str(FAKE), "normalize", "--packet", str(packet_path), "--settlement", str(settlement_path), "--artifact", str(patch), "--outcome", "failed-preserved"], cwd=repo)
        preserved_path = write(root / "failed-preserved.json", json.loads(failed_preserved.stdout))
        preserved = run([sys.executable, str(CONTRACTS), "--repo-root", str(repo), "result", "executor", str(packet_path), str(preserved_path)], cwd=repo)
        assert preserved.returncode == 0 and json.loads(preserved.stdout)["artifact_disposition"] == "preserved_not_candidate", preserved.stdout

        lost_settlement = write(root / "lost-settlement.json", {})
        failed_lost = run([sys.executable, str(FAKE), "normalize", "--packet", str(packet_path), "--settlement", str(lost_settlement), "--outcome", "failed-lost"], cwd=repo)
        lost_path = write(root / "failed-lost.json", json.loads(failed_lost.stdout))
        lost = run([sys.executable, str(CONTRACTS), "--repo-root", str(repo), "result", "executor", str(packet_path), str(lost_path)], cwd=repo)
        assert lost.returncode == 0 and json.loads(lost.stdout)["artifact_disposition"] == "lost_unmaterialized", lost.stdout

        runtime_packet = dict(packet, agent="omp-agent")
        rejected = run([sys.executable, str(CONTRACTS), "--repo-root", str(repo), "packet", "executor", str(write(root / "runtime-packet.json", runtime_packet))], cwd=repo)
        assert rejected.returncode != 0 and "unknown fields: agent" in rejected.stdout, rejected.stdout
        runtime_result = json.loads(completed.stdout)
        runtime_result["sessionFile"] = "/tmp/session.jsonl"
        rejected = run([sys.executable, str(CONTRACTS), "--repo-root", str(repo), "result", "executor", str(packet_path), str(write(root / "runtime-result.json", runtime_result))], cwd=repo)
        assert rejected.returncode != 0 and "unknown fields: sessionFile" in rejected.stdout, rejected.stdout

        bad_base = dict(packet, base="HEAD")
        rejected = run([sys.executable, str(CONTRACTS), "--repo-root", str(repo), "packet", "executor", str(write(root / "bad-base.json", bad_base))], cwd=repo)
        assert rejected.returncode != 0 and "full lowercase hexadecimal" in rejected.stdout, rejected.stdout

    subprocess.run([sys.executable, "-m", "py_compile", str(INITIALIZE), str(CONTRACTS), str(FAKE)], check=True)
    print('{"status":"CONTRACT_TESTS_PASSED"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
