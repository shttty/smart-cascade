---
name: external-agent-terminal-multiplexer-operations
description: "Use when an external controller agent must start, prompt, inspect, supervise, recover, or hand off an inner coding agent running inside Herdr, tmux, or another terminal multiplexer."
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [external-controller, coding-agent, multiplexer, herdr, tmux, supervision]
    related_skills: [herdr, autopilot, remote-coding-agent-operations]
    config:
      - key: agent_supervision.progress_observation.enabled
        description: "Enable periodic read-only progress observation for long-running inner-agent work. Completion and blocker notifications remain immediate."
        default: true
        prompt: "Enable periodic progress observation for long-running agent work?"
      - key: agent_supervision.progress_observation.interval_minutes
        description: "Minutes between read-only progress observations when enabled."
        default: 30
        prompt: "Progress observation interval in minutes"
---

# External agent → terminal multiplexer → inner agent operations

This Skill governs an external controller agent operating an inner agent through a terminal multiplexer. It is runner-neutral and project-neutral.

## Authority layers

```text
project production contract  logical identity, attempts, worktrees, scope, acceptance
runner dependency            runner-specific CLI, environment, plugins, protocol
multiplexer adapter          process/session/pane control and semantic observation
this Skill                   safe external control, supervision, handoff, recovery
```

Herdr is the preferred multiplexer adapter when supported and permitted by the official `herdr` Skill. Tmux/raw SSH/MCP are explicit fallback adapters. Claude Code, OMP, Codex, Pi, and future tools are replaceable inner-agent kinds.

## Resolve before control

Record and reconcile:

```text
controller identity
adapter + session/socket
inner-agent kind + runner dependency
attempt/agent name
workspace + pane
absolute lane worktree + branch
run/lane identity when present
ownership: controller / user / unknown
pre-dispatch lifecycle sequence or equivalent marker
```

Workspace/model alone are insufficient. When ownership or target identity is unclear, remain read-only.

## Branches

- Adapter/session topology, environment inheritance, runner launch, or remote transport → `references/adapter-and-launch.md`.
- Prompt submission, steering, co-control, progress observation, or blocked questions → `references/submission-and-supervision.md`.
- Completion signals, waiter lifecycle, parent handoff, stale input, or post-completion mutations → `references/completion-and-handoff.md`.
- Parent verification, live smoke, takeover, recovery, and cleanup → `references/verification-and-recovery.md`.

## Hard rules

- Load the inner runner's official/project dependency before launch; this Skill does not invent runner syntax.
- Multiplexer state and transcript are evidence, not lane/worktree authority.
- Never replace, kill, clear, or type into a user-controlled or ambiguously owned session.
- A prompt submission, settled state, waiter exit, or runner summary is not acceptance.
- Preserve dirty worktrees and useful artifacts until integrated or explicitly abandoned.
- The external controller performs final run-level verification and reports real results; the parent production authority performs candidate acceptance and Git actions.

## Progress-observation configuration

Hermes injects these non-secret Skill settings from `config.yaml`:

```text
agent_supervision.progress_observation.enabled
agent_supervision.progress_observation.interval_minutes
```

- `enabled: false` disables only the periodic observation timer.
- The task-scoped completion/blocker waiter remains immediate and must not be disabled by this setting.
- When enabled, accept a positive integer minute interval. Missing or invalid values fall back to 30 minutes.
- Compute the timer duration at execution time and arm one bounded timer only while the target is still working.

Users may change the settings without editing this Skill:

```bash
hermes config set skills.config.agent_supervision.progress_observation.enabled false
hermes config set skills.config.agent_supervision.progress_observation.interval_minutes 45
```

## Completion criterion

External operation is complete only when target identity is proven, the submitted task is identifiable, the inner agent can no longer unexpectedly mutate the accepted baseline, parent verification passes, and cleanup respects ownership.
