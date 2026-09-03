# Smart Cascade decisions

Status: accepted ADR for the current implementation. The implementation source of truth is [`smart-cascade-flow.md`](smart-cascade-flow.md). Historical snapshots remain evidence only and are not rewritten.

## Decision

Smart Cascade is implemented as a Skill and Root production loop over native OMP tasks:

```text
user-authorized Root OMP session
  → native task(isolated=true) Leader
      → native task(isolated=true) Executor
```

The selected profile policy is:

```text
task.isolation.mode=auto
task.isolation.apply=false
task.isolation.merge=patch
```

OMP owns child task sessions, parent/child lineage, asynchronous execution, Agent Hub communication, native status, strict settlement, transcripts, temporary isolation, retained patch capture, and parked-session recovery. Smart Cascade owns the queue/DAG, logical slice and child labels, attempt/candidate decisions, patch validation and assembly, `PASS` / `REWORK` / `BLOCKED`, Git integration, and dependency advancement.

No separate Smart Cascade child-runtime interface, registry, lifecycle store, tombstone store, lease/fencing layer, or business state machine is part of the current design.

## Authority

- **Root** is the only production scheduler, slice technical acceptance authority, Git integration authority, and dependency-advancement owner.
- **Leader** owns one slice's execution strategy, child coordination, settlement validation, bounded serial patch assembly, and candidate evidence.
- **Executor** owns only one bounded implementation assignment inside native OMP isolation.
- **Advisor** is optional evidence for bounded analysis or independent review; Advisor `PASS` is not acceptance.
- **Autopilot** is an external supervisor for bootstrap, observation, intervention, recovery, escalation, and reporting. It is not a second scheduler or acceptance authority.
- **Herdr** is an optional Root process supervisor or transport fallback. It is not the Leader message bus or production database.

## Queue and production state

`.smart-cascade/queue.toml` contains static intent and hard boundaries only: stable slice IDs, dependencies, scope, and named acceptance goals. `checks` states what must hold once the slice is done, not which commands to run — a queue is written before the work exists, when the command set is not yet knowable, and some slices have no clean standalone test. The implementer chooses the verification and reports what it actually ran. It declares no file paths — each slice runs in its own worktree and the Leader assembles patches serially, so a write collision surfaces as rework at apply time rather than as a static conflict. It contains no child topology, runtime status, attempts, sessions, worktrees, candidates, decisions, or parallel flag; the Leader decides child decomposition at runtime.

Root reads the complete approved queue, computes the maximum safe ready frontier, and recomputes it after every accepted integration. OMP lifecycle status is observation and control evidence; candidate freeze and production decisions remain Root judgments.

The only planned Smart Cascade persistence outside normal OMP session/artifact handling is the minimal rework counting described by the implementation specification. It is not a lifecycle replica or second queue.

## Recovery evidence

The 2026-08-26 `IsolatedCrashProbe` smoke verified the required native OMP recovery behavior:

1. interrupting Root did not remove the isolated child session JSONL or isolated worktree;
2. Root resume rediscovered the original child as `parked` without automatically continuing execution;
3. a later Root continuation message allowed Hub to revive the original child identity;
4. revival continued the same child session JSONL and isolated worktree rather than spawning a replacement.

Therefore Root recovery is two-step: resume and re-observe, then explicitly continue/revive the original child when it still applies. If recovery is unavailable, Root redispatches honestly from the last verified candidate.

## Rejected routes

### Custom Pi plugin runtime

Rejected as a production prerequisite. The earlier proposal duplicated child-session construction, registry, lifecycle persistence, tombstones, and revival that native OMP already supplies for the current requirements.

A plugin is a future option only if requirements expand to a genuinely missing capability such as a host-independent runtime or cross-process ownership/fencing. Those are not current requirements.

### Borrowed-cwd adapter

Rejected as the OMP production path. The earlier adapter investigation remains historical evidence for an extension seam and its `CORE-CHANGE-REQUIRED` result; it does not block native `isolated=true` task execution.

### External Herdr Leader panes

Rejected as the routine production topology. External panes remain a process-level fallback, while Root→Leader→Executor production dispatch and messaging use native OMP task and Agent Hub.

## Scope

The current implementation scope is:

- [`smart-cascade-flow.md`](smart-cascade-flow.md);
- `sources/smart-cascade-skill`;
- `.smart-cascade/queue.toml` plus ignored project runtime state;
- `sources/smart-cascade-omp` role definitions, profile, and smoke.

The superseded Smart Cascade-owned runtime design, the OMP borrowed-cwd investigation, and the original general Judge→Planner→Advisor→Executor Skill are retained only in the maintainer's local archive. None of them is an authority source for this Root/Leader topology.
