# Smart Cascade production flow

## Sources of truth
1. Approved static queue: `.smart-cascade/queue.toml`.
2. Bootstrap contract: the installed Smart Cascade Skill's `bootstrap/root-init.md` and `bootstrap/manifest.json`.
3. Selected OMP role definitions and profile isolation policy.
4. Autopilot control evidence and Root/Leader production facts; persistence is limited to receipts, candidate artifacts, Git facts, and minimal slice/child rework counters.

`archive/snapshots/` is historical evidence only.

## Topology

```text
Root OMP session
  → native OMP Leader subagents
      → bounded Executor subagents

Herdr      optional Root transport / process observation
Autopilot  optional external supervision
```

Root owns the complete DAG, slice attempts, acceptance, commits, integration, dependency advancement, and cleanup, and completes that loop without a supervisor resident on the dispatch path. When the user chooses external supervision, Autopilot bootstraps, observes, intervenes, recovers, escalates, and reports; direct invocation of the `smart-cascade` Skill uses the current OMP session as Root and requires neither Autopilot nor Herdr.

## Static queue

`.smart-cascade/queue.toml` contains stable `id`, `depends_on`, `scope`, normalized `write_set`, and named `checks`. It has no runtime state or parallel flag.

After run authorization, Root reads the complete queue and computes the maximum safe ready frontier. Root recomputes it after every accepted integration; unrelated active Leaders do not delay newly ready work.

## Maximum safe parallelism

A slice/child is dispatchable only when:

1. logical dependencies are accepted and integrated;
2. normalized write sets are disjoint from active writers;
3. shared mutable resources are disjoint, including lockfiles, generated outputs, snapshots, databases, build/coverage directories, fixtures, and Git index operations;
4. every writer has a safe execution cwd/worktree.

Record a concrete serialization reason when the frontier is narrower than dependency readiness.

## Root production loop

1. Select every safely ready slice.
2. Spawn one native asynchronous OMP Leader task per slice with `isolated=true`.
3. Process whichever Leader Hub message or typed settlement arrives first.
4. Verify the exact retained patch artifact, changed paths, postconditions, checks, and typed result.
5. Freeze a candidate only after proving no active writer can mutate it.
6. Obtain Advisor evidence when the acceptance risk requires it.
7. Decide `PASS`, `REWORK`, or `BLOCKED`.
8. On `PASS`, apply the accepted patch, commit/integrate, verify the result, mark dependencies satisfied, and recompute the frontier.
9. On `REWORK`, rematerialize from an explicit base, reapply/verify the last cumulative patch, and handle only remaining findings.
10. On `BLOCKED`, preserve evidence and continue independent ready work.

Root coordinates; it does not replace Leader as the product-change implementer.

## Native task isolation and patch retention

Root→Leader and Leader→Executor writing tasks request `isolated=true`. The profile-wide policy is `task.isolation.mode=auto`, `apply=false`, `merge=patch`. OMP owns temporary isolation directories, captures retained patch artifacts, and cleans those temporary resources; it does not automatically apply patches to parent checkouts.

Hub is the runtime communication bus for parent/child messages and completion. A parent validates the child result, real changed paths, postconditions, and retained patch, then serially applies each verified child patch into its own isolated candidate. Root owns logical attempts, candidate validity, accepted patch application, commit/integration, and DAG advancement; Leader owns child validation and bounded assembly; Executor owns only the bounded write set.

For `REWORK`, a new attempt applies and verifies the last cumulative patch against an explicit base before addressing the exact remaining checklist. Logical identities remain stable. If an abrupt temporary attempt emits no patch, report the lost partial attempt and restart from the last verified candidate.

External Herdr Leader panes and any borrowed-cwd adapter are not the OMP production path. No Smart Cascade plugin runtime is required for the native OMP path.

## Leader authority

Leader chooses direct, delegated, or mixed execution within its approved isolated candidate and queue write set. Leader verifies child results and performs bounded one-writer assembly.


## Child packet

```text
logical child_id
parent_slice_id
attempt_id and parent candidate/base
exact cwd/worktree or isolation mode
allowed paths / normalized write set
inputs and non-goals
postconditions or deterministic postimage
named checks
REWORK checklist, when applicable
terminal result / output schema
```

Executors implement only the packet. They do not own worktree lifecycle, commit, merge, push, widen scope, or create replacement identities.

## Candidate and Advisor

A lifecycle event is a doorbell only. Root freezes the candidate. Advisor reviews one Root-frozen candidate and returns evidence. Advisor `PASS` is not acceptance; Root decides and performs the production Git action.

## Escalation

```text
Executor blocker
  → Leader diagnoses/reworks/escalates

Leader blocker or cross-child conflict
  → Root grants/serializes/reworks/blocks

Root external boundary blocker
  → Autopilot supervises and escalates to the user when needed
```

