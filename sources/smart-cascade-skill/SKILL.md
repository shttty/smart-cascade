---
name: smart-cascade
description: Generate an approved Smart Cascade queue from to-tickets output, then run it from the current session through a selected runner.
disable-model-invocation: true
---

# Smart Cascade

Use only on explicit user invocation. Install this self-contained Skill through the Skills CLI or copy its complete directory to a directory discovered by the target agent. OMP is the only current runner; configure an existing user-owned OMP profile before running. The current session becomes the prospective Root only after the user gives an explicit yes at the run-level confirmation boundary. Each runner directory contains its admission check, launch configuration, and runner-format subagent definitions; adding another runner must not change the core.

## Queue preparation

1. Require the invocation argument to name exactly one `to-tickets` issues directory. Resolve a relative path from the current project root. Do not discover, infer, or silently select a different ticket set.
2. Run `python3 bootstrap/to-queue.py <issues-directory> -o <temporary-queue>` and then `python3 bootstrap/validate-queue.py <temporary-queue>`. Any parse, dependency, cycle, or validation failure stops before production work.
3. Target `<project>/.smart-cascade/queue.toml`. If it does not exist, install the generated queue. If it is byte-identical, reuse it. If it differs, show the diff and ask whether to replace it; never overwrite an existing queue without an explicit yes.
4. Queue generation prepares the run input only. It does not authorize dispatch. Present the generated queue in the run-level confirmation below.

## Preflight

`ponytail` is optional. Use it when the target session discovers it; otherwise skip it and continue without installing it or blocking admission/dispatch. OMP role `autoloadSkills` resolves only discovered skills and skips missing names.

1. Read the approved project flow/spec and `<project>/.smart-cascade/queue.toml`, then `bootstrap/root-init.md`, `runners/omp/roles/*.md`, and `runners/omp/runner-launch.yaml`.
2. Run `SMART_CASCADE_PROJECT_ROOT=<project> bash bootstrap/init-environment.sh` and require `CORE_READY`. This preflight is read-only.
3. Check that the OMP installation can host the Smart Cascade roles:

```text
python3 runners/omp/adapter.py check \
  --project-root <project> \
  --omp-bin <omp-executable> \
  [--config <runner-launch.yaml>] \
  [--profile <name-or-full-profile-path>]
```

`--config` defaults to `runners/omp/runner-launch.yaml`. `--profile` accepts a profile name under `~/.omp/profiles` or a full profile directory; a successful explicit selection is persisted in `<project>/.smart-cascade/override.yaml` and later checks reuse it. Without an override the adapter uses OMP's default profile. This is one-time installation admission — it confirms the profile, model roles, isolation policy, and OMP version, and says nothing about any later dispatch. A missing or misconfigured profile, role, or executable is `BLOCKED_ENVIRONMENT`.

4. Verify the exact Git base and worktree state. Present the queue and acceptance-target summary. Ask exactly one run-level confirmation. Invocation is not authorization.

After the explicit yes and before production dispatch, run `SMART_CASCADE_PROJECT_ROOT=<project> SMART_CASCADE_CREATE_STATE=1 bash bootstrap/init-environment.sh` once to create the ignored receipt/counter directories. Recheck that the approved queue and base have not drifted.

## Production

After confirmation, follow the core Root workflow in `bootstrap/root-init.md`.

Delegation, background execution, inter-agent communication, child lifecycle, and result delivery belong to the host runner. Under OMP that means native isolated `task` dispatch and Hub messaging; use them directly.

Writing work runs in the runner's isolated workspace with the profile's patch-retention policy, so candidate changes never enter the production worktree on their own. Root applies an accepted candidate deliberately.

Verify the work rather than the paperwork. Read the child's result, then inspect the real diff against the exact base and assigned scope, and run the verification the acceptance targets call for. A child's claim of success is not acceptance.

## Recovery

On Root resume, use the runner's own facilities to observe children that were already running. Resume alone must not continue them. Continue an existing child explicitly where the runner supports it; otherwise report the lost context honestly and redispatch from the last verified candidate. Do not persist live topology.

## Decisions and final report

Root alone decides `PASS`, `REWORK`, or `BLOCKED`, applies accepted patches, performs production Git integration, advances dependencies, and reports exact evidence, cleanup, recovery, blockers, and residual risks. A child's completion alone is not completion.

Slice `checks` are acceptance targets, not a prewritten command list. They state what must be true when the slice is complete and may be natural-language goals or commands already known at queue time. The implementing Leader or Executor chooses how to verify those targets after the work, and reports the commands actually run. Slice `checks` are the floor, not the ceiling: whoever holds commit authority must, before the commit boundary, enumerate the project's own higher-tier verification entry points — end-to-end, smoke, integration, contract, and equivalents — and run every one whose preconditions the current environment already satisfies. Discover them from the project's own manifest rather than assuming a fixed command set; checks that name only the unit-test goal do not narrow this obligation.

Report each such entry point as passed, failed, or not-runnable-with-reason. A missing precondition (absent service, unset environment variable) is `not runnable` and must be named; it is never silently equivalent to passing, and a green unit-test suite never stands in for an unrun tier. Failures at these tiers block the commit boundary exactly as an unmet acceptance target does.

After the final accepted candidate passes Root verification, present exactly one commit boundary before production Git integration. Offer committing the accepted candidate as the recommended default and retaining it as an uncommitted worktree candidate as the alternative. Record in the run receipt which option was taken and whether the user chose it explicitly or the runner auto-selected the default. Never present this boundary before verification, and never commit a candidate that failed verification.
