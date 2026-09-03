# Runtime state-machine boundary
The retired Autopilot-owned JSON state machine and per-slice release loop are historical context only; the implemented OMP track uses one run-level authorization and native task isolation.

## Control state

```text
not_started
  → root_starting
  → root_initialized
  → environment_ready
  → run_authorized
  → supervising
  → run_complete | blocked_external | recovery_required
```

Autopilot owns these control transitions. They do not encode slice scheduling or acceptance.

## Production state

Root owns the production transitions:

```text
slice pending
  → ready
  → attempt_active
  → candidate_frozen
  → accepted | rework | blocked

accepted
  → integrated
  → dependencies_recomputed
  → cleaned

rework
  → new attempt materialized in native OMP isolation from the last verified candidate patch
```

Leader/Executor lifecycle states are evidence inside an attempt. Agent `working`, `idle`, `done`, `blocked`, child `completed`, and process exit never establish candidate freeze or acceptance by themselves.

## Incremental frontier

Every accepted integration changes dependency milestones and triggers a new ready-frontier computation immediately. Root does not wait for unrelated active slices to settle.

## Attempt lineage

A logical slice remains stable across attempts. Each new attempt binds:

- `attempt_id`;
- parent attempt/candidate, when any;
- explicit base or inherited candidate identity;
- native OMP isolation mode and retained patch artifact;
- assignment and REWORK checklist;
- terminal result and disposition.

Temporary isolation is cleaned only after patch capture and settlement. Parent validation and serial patch application remain explicit production steps.

## Durable seam

A later Root recovery mechanism may persist these facts, but it must not become a second queue or transfer production decisions to Autopilot. The current OMP run uses native isolation artifacts and Root-owned production facts; recovery durability is a separate seam.
