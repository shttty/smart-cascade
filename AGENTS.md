# Smart Cascade

Multi-agent orchestration: a Root coordinator schedules slices from an approved
queue, dispatches Leaders and Executors through the host runner, and integrates
verified work into production Git. `sources/smart-cascade-skill/` is the core;
`runners/<runner>/` holds everything platform-specific; `sources/autopilot-skill/`
is an optional external supervisor.

## Don't rebuild what the host already does

The runner owns subagent dispatch, background execution, correlation between a
dispatch and its result, messaging, lifecycle, isolation, and result delivery.
Use those directly. Under OMP that means native `task` with `isolated=true`,
Hub messaging, and `outputSchema` for structured results.

This project deleted roughly 2500 lines that existed to restate what the runner
already reported: canonicalized packets bound by SHA-256 markers, a transcript
parser that re-derived agent provenance and session lineage, a contract
validator that adjudicated result schemas, an RPC handshake that probed OMP's
private type declarations, and a dispatch marker counted in session files.
None of it is coming back.

Before adding anything, ask which it is:

- **A tool the agent calls** — queue parsing, ready-frontier computation, atomic
  rework counters, one-time installation checks. These are fine; they do work
  the agent would otherwise do by hand.
- **A layer that confirms the agent** — verifying a result belongs to its
  dispatch, re-deriving what the runner reported, requiring a serialized packet
  or receipt format, or asking anyone to prove something already visible.
  These do not belong here.

Two specific smells, both previously removed:

- Hashing something with no consumer. If nothing compares the digest later, it
  is decoration.
- Forbidding a thing nobody does. A rule against adding envelopes is itself the
  kind of line worth cutting.

## Acceptance rests on the work

Read a child's result as the runner delivers it. Then verify the work: apply the
retained patch to a clean checkout of the exact base, inspect the real diff and
changed paths, and run the verification the acceptance targets call for. A
completion notice, a progress event, or a self-report is never acceptance.

Root alone decides `PASS` / `REWORK` / `BLOCKED`, applies accepted patches, and
owns production Git. Writing work runs in the runner's isolated workspace with
`apply=false`, so candidate changes never reach the production worktree on their
own.

Slice `checks` are a floor, not a command list. Before any commit boundary,
enumerate the project's own higher-tier entry points — e2e, smoke, integration,
contract — and run every one whose preconditions the environment satisfies.
Report each as passed, failed, or not-runnable-with-reason; a missing
precondition is named, never silently treated as a pass.

## Core stays platform-neutral

`bootstrap/` and `SKILL.md` describe responsibilities, boundaries, and required
effects. Tool names, dispatch mechanics, and evidence formats live in
`runners/<runner>/`. Adding a second runner must not touch the queue, frontier,
state, or Root workflow.

## Verification

Deterministic suites, no provider needed:

```bash
python3 sources/smart-cascade-skill/runners/omp/test-adapter.py
python3 sources/smart-cascade-skill/scripts/test-smart-cascade-frontier.py
python3 sources/smart-cascade-skill/scripts/test-smart-cascade-state.py
python3 sources/smart-cascade-skill/scripts/test-to-queue.py
SMART_CASCADE_PROJECT_ROOT=$PWD bash sources/smart-cascade-skill/bootstrap/init-environment.sh
bun run sources/smart-cascade-omp/smoke/run.ts --self-test-evidence
bun run sources/smart-cascade-omp/smoke/recovery.ts --self-test-evidence
```

The full smoke runs (`run.ts`, `recovery.ts` without `--self-test-evidence`)
need a real OMP runtime and provider. A provider outage is not a core failure —
report it as unrunnable rather than as a pass or a defect.

`archive/` is history, not active product. Never install from the repository
root; it will pick up a stale copy of the skill.
