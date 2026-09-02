---
name: remote-coding-agent-operations
description: Control a coding agent on a remote Linux host over raw SSH/tmux when high-level MCP is unavailable, or when the user explicitly asks for manual session launch, prompt submission, environment diagnosis, or remote verification.
version: 2.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [remote, ssh, tmux, claude-code]
    related_skills: [external-agent-terminal-multiplexer-operations, autopilot, linux-personal-server-operations]
---

# Remote coding agent operations

Raw SSH/tmux fallback for `external-agent-terminal-multiplexer-operations`. This skill owns remote transport mechanics, not generic external-control semantics, production run queues, completion-doorbell policy, or multi-slice scheduling.

## Remote identity before control

Before any non-read remote action, reconcile the SSH host/user, absolute remote workspace, tmux pane cwd, repository identity, and session ownership. A local sshfs path is read evidence, not proof of the remote control target. If these facts disagree or ownership is unclear, remain read-only. If the verified remote root is dirty, create an isolated worktree only with explicit authorization.

## Remote loop

1. **Probe** — Through `zsh -lic`, verify repository/branch/status, Claude binary/version/auth, and provider/model environment.
   - Complete when the same login-shell path used by tmux can start the agent.
2. **Launch** — Create or select an explicitly named tmux session in the remote workspace. Preserve sessions that may be user-controlled.
   - Complete when pane cwd and process command line match the intended target.
3. **Submit** — Stream the prompt through SSH stdin into a tmux buffer, paste it, send Enter, then capture the pane.
   - Complete when the pane proves the prompt entered processing/history; visible unsubmitted text is not enough.
4. **Inspect** — Treat watcher/pane output as hints. Inspect actual git state, scope, tests, compile/static checks, and smoke.
   - Complete when parent Hermes reproduces the material result.
5. **Commit/cleanup** — Commit only after parent approval. Kill temporary sessions only when ownership is clear.

Load `references/raw-ssh-tmux.md` for exact fallback commands and the login-shell/submission pitfalls.

## Scope hygiene

Every task prompt states:

```text
allowed files
forbidden runtime artifacts
non-goals
acceptance commands
commit policy
```

Guard unrelated `runtime/` data, launcher scripts, manual payloads/probes, and lockfile churn. Run at minimum:

```bash
git status --short --branch
git diff --stat
git diff --check
```

Then run project-specific tests and a real-behaviour smoke.

## Routing

- Generic external controller → terminal multiplexer → inner agent supervision → `external-agent-terminal-multiplexer-operations`.
- Production Autopilot, run bundles, queue/state, or hierarchical slices → `autopilot`.
- Runner-specific syntax/environment/plugins → load the selected runner's official/project Skill.

## Completion criterion

Remote work is complete only when the submitted task is identifiable, changed files stay within scope, parent verification passes, and the resulting artifact is observable.
