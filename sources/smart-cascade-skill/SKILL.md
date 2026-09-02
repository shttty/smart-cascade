---
name: smart-cascade
description: Run an approved Smart Cascade queue from the current session through a selected runner adapter.
disable-model-invocation: true
---

# Smart Cascade

Use only on explicit user invocation. Install the platform-neutral core with one or more selected `runners/<name>/` directories; unselected runners are intentionally absent. The installer defaults to `omp`, the only current production runner, to preserve existing installs. Its OMP profile selector accepts the same name-or-full-directory forms as adapter `--profile`, defaults to `smart-cascade-omp`, and installs/drift-checks that exact target. Under the OMP runner, the current OMP session becomes the prospective Root only after the user gives an explicit yes at the run-level confirmation boundary. Each runner directory contains its adapter, normalization, launch configuration, and runner-format subagent definitions; adding another runner must not change the core.

## Preflight

1. Read the approved project flow/spec and `<project>/.smart-cascade/queue.toml`, then `bootstrap/root-init.md`, `bootstrap/runner-interface.json`, `runners/omp/roles/*.md`, and `runners/omp/runner-launch.yaml`.
2. Run `SMART_CASCADE_PROJECT_ROOT=<project> bash bootstrap/init-environment.sh` and require `CORE_READY`. This preflight is read-only; verify its complete tracked/untracked snapshot remains unchanged.
3. Run the OMP adapter check:

```text
python3 runners/omp/adapter.py check \
  --project-root <project> \
  --omp-bin <omp-executable> \
  [--config <runner-launch.yaml>] \
  [--profile <name-or-full-profile-path>]
```

`--config` defaults to `runners/omp/runner-launch.yaml`. `--profile` accepts a profile name under `~/.omp/profiles` or a full profile directory. A successful explicit selection is persisted in `<project>/.smart-cascade/override.yaml`; later checks reuse it. Without an override, `dispatch_contract.profile_name` is the default. Require `ADAPTER_READY` and retain the exact receipt. A missing/mismatched profile, mandatory isolation/async/batch boundary, executable/package identity, role identity, adapter operation, capability declaration, or RPC negotiation is `BLOCKED_ENVIRONMENT`.
4. Verify the exact Git base and complete tracked/untracked worktree snapshot. Present the queue/write-set/check summary plus the adapter receipt. Ask exactly one run-level confirmation. Invocation is not authorization.

After the explicit yes and before production dispatch, run `SMART_CASCADE_PROJECT_ROOT=<project> SMART_CASCADE_CREATE_STATE=1 bash bootstrap/init-environment.sh` once to create the ignored receipt/counter directories. Recheck that the approved queue, base, and preauthorization snapshot boundary have not drifted; only these declared runtime directories may be new.
## Production projection

After confirmation, follow the core Root workflow. For OMP, native task/Hub/RPC are the adapter control surface; `runners/omp/adapter.py check` performs admission and `runners/omp/normalize.py` validates authoritative runtime evidence. Correctness is decided at the runtime candidate gate, not by a second pre-dispatch revalidation layer:
- bind each core packet to its native invocation by canonicalizing the complete packet as UTF-8 JSON with recursively sorted object keys and separators `,` and `:`, then including `SMART_CASCADE_PACKET_SHA256 sha256:<lowercase-sha256>` in the task assignment, with the packet's exact `result_schema` as `outputSchema`. This binding is adapter-owned; `bootstrap/root-init.md` deliberately leaves it to the runner;
- dispatch Root→Leader→Executor through native isolated `task` with the installed role definitions and strict output schema; the admitted production profile uses batch task arguments (`context` plus `tasks[]`), even when the ready frontier contains one item;
- use plain-prose Hub messages for coordination;
- treat lifecycle/RPC/native progress and task-result frames only as adapter-native evidence;
- validate agent provenance, admitted model projection, invocation strictness/isolation, observed task call ID, parent/child session lineage, terminal job receipt, native `<task-result>` settlement, `<merge-summary>` patch path, and retained patch existence directly from the authoritative parent transcript inside the OMP adapter;
- run `python3 runners/omp/normalize.py --config <config> --parent-transcript <authoritative-parent.jsonl> --runtime-id <exact-native-id> <role> <packet>` to parse that transcript and produce the runner-neutral result; do not author a parallel evidence JSON file;
- pass only that normalized result to `python3 bootstrap/contracts.py result ...` for business settlement, patch bytes, Git base, write-set, and candidate validation.

Never pass OMP session, model, Hub, lifecycle, task-envelope, or profile fields into core packets/results.

## OMP recovery

On Root resume, use OMP Hub/list and public session evidence to observe parked children. Resume alone must not continue them. Explicitly revive the original identity when applicable and normalize the resulting evidence. If unavailable, report the failed delivery and redispatch from the last verified candidate. Do not persist live topology.

## Decisions and final report

Root alone decides `PASS`, `REWORK`, or `BLOCKED`, applies accepted patches, performs production Git integration, advances dependencies, and reports exact adapter/core evidence, cleanup, recovery, blockers, and residual risks. Runner settlement alone is not completion.

Slice `checks` are the floor, not the ceiling. Whoever holds commit authority must, before the commit boundary, enumerate the project's own higher-tier verification entry points — end-to-end, smoke, integration, contract, and equivalents — and run every one whose preconditions the current environment already satisfies. Discover them from the project's own manifest rather than assuming a fixed command set; a queue whose `checks` name only the unit-test command does not narrow this obligation.

Report each such entry point as passed, failed, or not-runnable-with-reason. A missing precondition (absent service, unset environment variable) is `not runnable` and must be named; it is never silently equivalent to passing, and a green unit-test suite never stands in for an unrun tier. Failures at these tiers block the commit boundary exactly as a failed `check` does.

After the final accepted candidate passes Root verification, present exactly one commit boundary before production Git integration. Offer committing the accepted candidate as the recommended default and retaining it as an uncommitted worktree candidate as the alternative. Record in the run receipt which option was taken and whether the user chose it explicitly or the runner auto-selected the default. Never present this boundary before verification, and never commit a candidate that failed verification.
