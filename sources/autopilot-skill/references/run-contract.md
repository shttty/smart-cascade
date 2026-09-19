# Run contract

## Run-level control

Autopilot establishes one authorized Root run:

```text
verify project / queue / initial base / runner config
  → use the installed herdr skill to start and initialize Root
  → verify CORE_READY and record the selected runner/profile
  → receive one explicit authorization for the complete approved queue
  → observe and supervise until Root reports run completion or a blocker
```
Autopilot does not release one slice at a time. It uses the installed `herdr` skill for the optional external Root session and sends the complete approved queue boundary only after one explicit authorization. Root then owns the full DAG and ready-frontier scheduling; runtime candidates pass the normal patch, settlement, acceptance-target, verification, and integration gates.

## Root production loop

```text
read complete static queue
  → compute maximum safe ready frontier
  → dispatch Leaders
  → process the first child message/settlement available
  → freeze and verify candidate
  → Root decides PASS / REWORK / BLOCKED
  → PASS: commit/integrate, satisfy dependency, recompute frontier
  → REWORK: continue or rematerialize the same logical slice attempt lineage
  → BLOCKED: freeze only the affected chain
```

Root may continue scheduling while other Leaders run. `working` is not a global scheduler lock.

## Runtime facts

Control evidence owned by Autopilot:

- Herdr/Root startup identity;
- initialization and environment receipts;
- the approved queue, runner config, and initial Git base;
- progress observations and lifecycle/blocker doorbells;
- supervision interventions and recovery actions;
- final run-level verification/report.

Production facts owned by Root/Leader:

- stable slice/child IDs and dependencies;
- ordered attempt lineage;
- retained artifact identity;
- child task-scope assignments and worktree confinement;
- child settlement and assembly;
- candidate freeze and acceptance-target verification;
- conditional Root-invoked Advisor blocker evidence for an explicitly `BLOCKED` task or slice;
- PASS/REWORK/BLOCKED decisions;
- commit/integration and dependency advancement;
- cleanup disposition.

A future durable seam must preserve this split. It must not make Autopilot a production writer or duplicate the static queue.

## Attempt continuity

- Logical slice/child identity survives runner and isolation-attempt replacement.
- Each attempt records its parent attempt/candidate and explicit base.
- Native OMP task isolation retains a verified cumulative patch artifact while `apply=false` prevents automatic mutation of the parent checkout. Temporary isolation directories are cleaned by OMP only after patch capture/settlement.
- `REWORK` rematerializes a new `attempt_id`, reapplies and verifies the last cumulative patch against an explicit base, then handles only the remaining findings. Base drift requires affected acceptance targets to be reverified and an explicit Root rebase/serialization decision on conflict.
- No fresh attempt may conceal an ambiguous dispatch, missing artifact, or unresolved candidate.

## Root→Leader and Leader→Executor runtime

Root and Leader use native asynchronous OMP tasks with `isolated=true`. The profile-wide policy is `task.isolation.enabled=true`, `isolation.backend=auto`, `apply=false`, `merge=patch`. Hub supplies parent/child messages and completion; parents validate child results and serially apply verified child patches into their own isolated candidate. Herdr-supervised external panes are not the OMP production path.

## Candidate and acceptance

A lifecycle event is a doorbell only. Root freezes one exact candidate and verifies real bytes, acceptance targets, reported verification, and scope. An ordinary single `REWORK`, acceptance, review, independent verification, risk inspection, or uncertainty does not directly invoke Advisor. If the slice rework counter returns `action=require_advisor`, Root first marks that slice `BLOCKED`, preserves the relevant evidence, and invokes Advisor for blocker diagnosis or unblocking assistance; a candidate is required only when that blocker concerns candidate bytes.

```text
PASS     commit/integrate and advance dependencies
REWORK   exact checklist under the same logical identity
BLOCKED  preserve evidence and stop only the affected chain
```

Advisor output is read-only evidence. Root alone decides the outcome, and Advisor findings cannot grant scope, permissions, or production authorization. Autopilot may inspect these facts for supervision or final reporting but does not issue a second verdict.

## Stop conditions

Root stops a chain for a real dependency, overlap, environment, architecture, smoke, authorization, or user boundary. Independent ready work continues.

Autopilot intervenes for wrong identity/boundary, transport ambiguity, sustained no-progress inspection loops, unrecoverable runtime capability loss, or user direction.
