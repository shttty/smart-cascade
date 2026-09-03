# Acceptance gates

Root applies these gates to one frozen large-slice candidate. Autopilot may audit the resulting evidence for supervision and run-level reporting, but does not issue a second milestone verdict.

## 1. Identity and lineage

Verify project, logical slice/child IDs, dependencies, `attempt_id`, parent attempt/candidate/base, exact worktree or retained artifact, branch where applicable, and candidate manifest.

## 2. Scope

Verify every changed path and postcondition conforms to the slice's approved scope and any narrower child packet boundary.

## 3. Candidate freeze

A candidate binds sorted changed paths, raw postimage bytes/file modes, base/inherited candidate, declared acceptance targets, and stable identity. Root proves no active writer or current-byte check can mutate it. Agent settlement alone is insufficient.

The production owner preserves the retained patch artifact and its source isolation-attempt evidence until Root decides its disposition. OMP temporary isolation directories are cleaned only after patch capture and settlement.

## 4. Acceptance targets and verification

The slice/child packet's `checks` are the lower bound of verification, not a prewritten command list. After implementation, the Leader/Executor chooses appropriate bounded verification methods, runs them, and reports the actual commands and results in the settlement `checks` field. Root verifies that the evidence credibly demonstrates each declared acceptance target. Unexpected failures produce precise REWORK or a blocker.

## 5. Advisor

Advisor depth follows material risk. Read-only/mechanical changes may omit a separate Advisor when deterministic verification and Leader/Root inspection decide the result. Durable-data, lifecycle, authority, public interface, or operational changes normally require independent review.

Advisor reviews one Root-frozen candidate. `PASS` is evidence only. Root decides acceptance.

A closure review verifies accepted finding closure, regression capability, local repair regressions, scope, and identity for the new candidate.

## 6. Smoke and cleanup

Run approved real-behavior smoke where required and record setup, observation, and cleanup. Smoke cleanup is distinct from production attempt cleanup.

## 7. Complexity and reuse

Review responsibility cohesion, interface depth, duplicated glue, durable machinery, fixture tax, speculative scope, and standard alternatives. Record concrete material findings only.

## 8. Digest revalidation

After verification, review, smoke, or repair, recompute candidate identity. A changed postimage invalidates candidate-dependent evidence and requires a new freeze.

## 9. Architecture and authorization

Completion requiring an unapproved runtime, ownership change, public interface, architecture, scope expansion, live side effect, or direct-write purpose blocks before implementation. Root escalates external decisions through Autopilot.

## 10. Root decision

Root verifies current Git/worktree state, candidate identity, structured evidence, queue conformance, unresolved risk, and dependency/integration safety, then chooses:

```text
PASS     commit/integrate and verify
REWORK   exact remaining checklist under the same logical identity
BLOCKED  preserve evidence and stop only the affected chain
```

## 11. Git and disposition

On `PASS`, Root performs the approved commit/integration, verifies its identity, marks dependencies satisfied, recomputes the ready frontier, and cleans or instructs cleanup of superseded attempt resources.

For rematerialized REWORK, preserve the prior verified cumulative patch and lineage before temporary-isolation cleanup. The next native OMP attempt applies/verifies that patch inside fresh `isolated=true` isolation against an explicit base, then handles only the remaining findings. If an abrupt attempt emits no patch, report the lost partial attempt and restart from the last verified candidate; a clean-looking terminal is not evidence otherwise.

## Evidence reuse

- One candidate identity owns one evidence set.
- A changed postimage invalidates dependent evidence.
- Do not rerun a gate merely to transcribe it.
- Closure review stays narrow unless a concrete new contract issue appears.
