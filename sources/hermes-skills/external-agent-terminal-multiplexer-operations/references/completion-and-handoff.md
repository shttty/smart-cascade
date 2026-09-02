# Completion and parent handoff

Load this branch when the inner agent appears idle/done, a watcher fires, or the parent is preparing to verify/commit/continue.

## Completion evidence

Adapter `idle`, `done`, `blocked`, waiter exit, prompt glyph, or quiet output are evidence—not acceptance. For Smart Cascade, Herdr is authoritative for the supervised Root process while OMP's native registry/RPC is authoritative for Root-owned subagent lifecycle. Neither lifecycle surface decides candidate freeze or acceptance.

## Task-scoped watcher lifecycle

Tie watchers to exact adapter/session, attempt, lane target, and run identity. Replacing any of those invalidates old watchers. Retire stale watchers before dispatching a replacement attempt.

Pane scans and elapsed time are not completion mechanisms. A vendor event or semantic waiter wakes the controller; parent verification follows.

## Safe handoff

Before the parent commits or dispatches the next task:

1. prove the active task settled or explicitly park/interrupt it;
2. inspect `git status --short`, including untracked files;
3. review the intended baseline and run named checks;
4. ensure queued input cannot execute accidentally;
5. commit/integrate only under the parent project's authority;
6. immediately recheck repo and runner state.

If the inner agent resumes old work after handoff, preserve or remove only confirmed old-task mutations, rerun affected checks, and keep ghost changes out of the next slice.

## Handoff gate

Handoff is complete only when the inner agent can no longer unexpectedly mutate the accepted baseline and the next instruction cannot trigger stale queued input.
