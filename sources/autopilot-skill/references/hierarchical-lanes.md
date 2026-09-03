# Hierarchical lanes

## Authority

```text
Autopilot supervisor → Root → Leader → Executor
```

- Root owns complete-DAG scheduling, large-slice attempt lifecycle, slice decisions, commits/integration, dependency advancement, and cleanup.
- Leader owns one slice's execution strategy, child attempt lifecycle, child settlement, and bounded assembly.
- Executors perform bounded implementation within their assigned worktree and task scope.
- Autopilot observes and intervenes on external control or boundary failures; it does not accept slices or perform production Git actions.

## Scheduling

Root and Leader dispatch the maximum safe frontier after every dependency milestone change. `working` agent state is not a global scheduling lock.

Dispatch requires satisfied dependencies and an isolated worktree for each active writer. Serialize only for declared shared mutable resource overlap or dependencies not yet integrated, and record the reason.

## Logical identity and attempts

- One slice or child has one stable logical identity.
- Each execution has an ordered `attempt_id` and explicit parent base/candidate.
- Native OMP isolation uses `isolated=true` with profile-wide `task.isolation.mode=auto`, `apply=false`, and `merge=patch`; OMP retains the patch artifact while temporary isolation is cleaned after capture.
- A parent validates child settlement and serially applies each verified child patch into its own isolated candidate.
- `REWORK` rematerializes a new attempt, reapplies and verifies the last cumulative patch against an explicit base, and follows only the remaining checklist.
- A new attempt never erases unresolved predecessor evidence. If no patch is emitted, report lost unmaterialized bytes and restart from the last verified candidate.


## Child packets

Each packet contains:

```text
child_id
parent_slice_id
attempt_id and parent candidate/base
isolated=true and profile patch-retention policy
assigned worktree / task scope
inputs and non-goals
execution role
postconditions / deterministic postimage
named acceptance targets (`checks`)
REWORK checklist
strict structured task-completion output schema
```

Runtime coordination through Hub is plain prose, not JSON status objects. Include explicit slice, attempt, and nonce labels when needed to correlate messages. Strict structured output is required only when the task settles.

Use Mechanical Executor only for a decided deterministic postimage. Use semantic Executor for implementation or diagnosis.

## Child settlement and assembly

1. Executor sends plain-prose settlement context through Hub and returns the strict structured task-completion result with its retained patch artifact.
2. Leader verifies real artifact bytes, diff, paths, postconditions, and reported verification against the acceptance targets.
3. Leader accepts the child for bounded assembly or issues precise REWORK under the same logical identity.
4. REWORK rematerializes from the last verified cumulative patch and explicit base.
5. Leader serially applies verified child patches into its isolated candidate under a matching Root grant.
6. Leader returns one candidate/evidence handoff to Root.
7. Root freezes, reviews, decides, applies the accepted patch, and integrates the slice.

## Blockers

A blocker freezes only its affected chain. Continue independent ready work. Architecture, product, queue-boundary, task-scope, shared-resource, or external authorization changes escalate to Root and then Autopilot/user when outside the run boundary.

No role creates a fresh logical identity merely to make progress look healthy.
