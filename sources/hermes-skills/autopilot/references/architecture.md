# Architecture

## Authority topology

```text
Autopilot supervisor
  → Herdr-supervised Root OMP session
      → Leader subagents
          → Executor subagents
```

Autopilot owns bootstrap, observation, intervention, recovery, escalation, and final run reporting. Root owns the complete production run.

## Authority matrix

| Concern | Owner |
| --- | --- |
| Approved static queue, initial base, and run boundary | User/project contract; verified by Autopilot before startup |
| Herdr/coding-agent startup and nonce-bound Root initialization | Autopilot |
| Environment, queue, runner, and Root-identity bootstrap verification | Autopilot |
| Complete-DAG intake and incremental ready-frontier scheduling | Root |
| Large-slice logical attempt and retained-artifact lifecycle | Root |
| Leader and Advisor dispatch | Root |
| Slice execution strategy and child coordination | Leader |
| Bounded implementation | Assigned Executor |
| Child settlement and bounded assembly | Leader |
| Candidate freeze and Advisor selection | Root |
| Slice `PASS` / `REWORK` / `BLOCKED` | Root |
| Commit/integration order and dependency advancement | Root |
| Production worktree/artifact cleanup | Root or Leader that owns the attempt |
| Root/subagent lifecycle observation | Autopilot through Herdr and OMP RPC |
| Boundary intervention, recovery, and user escalation | Autopilot |
| Final run-level verification/report | Autopilot |

Autopilot may stop or steer an unsafe Root but does not take over normal scheduling, acceptance, or Git work.

## Identity

Stable production identity:

```text
project + run authorization
logical slice/child ID
parent and dependency relationship
ordered attempt lineage
base / inherited candidate
candidate identity and checks
commit/integration evidence
attempt disposition
```

A temporary OMP isolation directory or retained patch artifact belongs to an attempt. It is not the logical lane identity itself. OMP owns temporary isolation cleanup after patch capture and settlement; the retained artifact remains for parent validation and Root disposition.

Ephemeral evidence includes Herdr session/workspace/pane/process IDs, OMP agent/job IDs, transcripts, and provider/model identity. Replacing transport does not replace the logical slice.

## Parallelism

Root and Leader recompute the maximum safe ready frontier whenever a dependency milestone changes. Readiness requires:

1. accepted/integrated logical dependencies;
2. disjoint normalized write sets;
3. no conflicting shared mutable outputs;
4. an execution mode that gives every active writer a safe cwd/worktree.

A Root or child agent still being `working` does not block another newly ready slice. Overlapping writers are serialized or assigned to one writer.

## Native OMP isolation and patch retention

The OMP production path uses native asynchronous tasks with profile-wide `task.isolation.mode=auto`, `apply=false`, and `merge=patch`:

- Root→Leader and Leader→Executor writing tasks request `isolated=true`.
- OMP owns temporary isolation directories, retained patch artifacts, and cleanup of those temporary resources. The runtime does not apply a child patch to a parent checkout automatically.
- Hub and native async completion carry parent/child communication and settlement. Parents validate typed results, real changed paths, postconditions, and retained patch bytes before serially applying a verified child patch into their own isolated candidate.
- Root owns logical attempts, candidate validity, accepted patch application, commit/integration, and DAG advancement. Leader owns child validation and bounded serial assembly. Executor owns only its bounded write set.

For `REWORK`, rematerialize a new attempt from an explicit base, reapply and verify the last verified cumulative patch, then handle only the remaining findings. Logical slice and child identities remain stable across attempts. A temporary attempt with no retained patch may lose unmaterialized bytes; report that attempt and restart from the last verified candidate.

Dirty, ambiguous, or uncertain evidence is preserved until disposition is proven. Cleanup follows patch capture and verification; cleanup never substitutes for candidate validation or acceptance.


## Single-authority rule

Root is the only production scheduler, slice decision maker, and Git integration authority. Autopilot is the only external supervisor. OMP/Herdr lifecycle surfaces are transport and observation, not competing authorities.

The static queue contains no live state. A later durable Root recovery seam must record production facts without becoming a second queue or moving production authority to Autopilot.

