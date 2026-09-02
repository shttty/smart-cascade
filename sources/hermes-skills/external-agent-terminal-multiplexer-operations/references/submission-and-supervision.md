# Submission and supervision

Load this branch when sending work, steering an active agent, answering a block, or observing progress.

## Bounded packet

Every packet names:

```text
target attempt and lane/worktree
scope and allowed files
non-goals
acceptance commands
commit policy
reporting/blocker contract
```

The runner dependency may add runner-specific syntax or controls. It may not expand lane authority.

## Submission proof

Pasted or echoed text is not proof of submission. Require an observed lifecycle transition, advancing state sequence, or transcript/history entry.

If a complete packet remains in the input editor, send one logical Enter and recheck. Do not resend the packet until the editor is empty and no transition occurred. Long prompts and bracketed-paste handling belong to the selected adapter.

## Co-control

If the user may be typing in the same agent/pane, do not clear input, send control keys, or submit a prompt without coordination. User input and controller input can interleave.

When the inner agent is already working, use the adapter's steering mechanism rather than launching a replacement attempt. Inspect before answering blocked questions or approvals; do not blindly press defaults.

## Progress observation

Use semantic adapter state first, then foreground process, current bottom-buffer output, Git/worktree state, and artifacts. Historical pane text contains stale busy and completion markers.

An active full-screen agent may keep its history in the terminal alternate screen. If Herdr rejects `recent` or `recent-unwrapped` while the agent is working, use one bounded `visible` read for the current marker, child dispatch, blocker, or progress signal; retry unwrapped history only after settle. The read limitation is not a runner failure and never authorizes duplicate submission.

Resolve `agent_supervision.progress_observation.enabled` and `agent_supervision.progress_observation.interval_minutes` from injected Skill config. `enabled: false` means no periodic timer. When enabled, use the configured positive integer minute interval; missing or invalid values fall back to 30 minutes. Compute seconds at execution time rather than embedding a fixed `sleep` value.

A configured bounded progress timer is read-only. It may re-arm itself when work remains healthy; it never submits prompts, retries work, changes adapters, or declares completion. Disabling it does not disable the task-scoped completion/blocker waiter.

## Supervision gate

Supervision is armed only after submission is proven and a task-scoped completion rail exists. Never arm a settled waiter against untouched pre-dispatch idle state; it can wake immediately and create false completion.
