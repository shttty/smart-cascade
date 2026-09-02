# Adapter identity and launch

Load this branch before starting, attaching to, replacing, or remotely controlling an inner agent.

## Adapter selection

Use Herdr first when the runner kind is supported and the official `herdr` Skill permits the caller context. Use SSH Unix-socket forwarding plus the official Herdr CLI for remote Herdr automation.

Use tmux/raw SSH/MCP only when Herdr cannot perform the required operation or the user explicitly selected another adapter. Record the concrete fallback reason. A transport change does not create a new logical lane or authorize cleanup.

## Identity and ownership

Verify the exact session/socket, pane, cwd, process, inner-agent kind, attempt name, worktree, branch, and controller/user ownership. Parse IDs from adapter responses; do not derive them from UI position or the currently focused pane.

If a session may be user-controlled, inspect only. Preserve useful wrong sessions by renaming/detaching when supported rather than killing them.

## Environment inheritance

The inner agent must inherit the environment required by its runner dependency. Verify through the same shell/wrapper that the real process will use:

```text
executable and version
credential presence without values
provider/model routing
cwd and project identity
runner-specific profile/config
```

For an Autopilot external controller, a task-scoped named Herdr session is an approved explicit adapter target even when the controller is not itself in a Herdr pane. Persist the exact name/socket, start that named server as a tracked background process, verify compatible server status, and pass the same explicit session selector on every later command. Do not touch or fall back to the user's default/focused session.

New Git worktrees commonly lack untracked dependency directories such as `node_modules`. Check the exact lane worktree before runner launch, install with the project's frozen package-manager command when required, record the result, and verify no tracked lockfile or source drift. Do not symlink another worktree's dependency directory or run package upgrade/audit-fix commands merely because installation prints vulnerability notices.

For Claude Code on an Anthropic-compatible custom endpoint, test the exact model spelling through the real CLI. A provider-qualified name may fail while the unqualified model ID succeeds. When role files use `opus`, `sonnet`, or `haiku`, verify the effective `ANTHROPIC_DEFAULT_*_MODEL` alias mapping before dispatch instead of rewriting role files after a launch spelling error.

Do not infer that `.zshrc`, `.bashrc`, login profiles, or service environments were loaded. Prefer a reviewed runner wrapper or explicit export-only env source. Shell startup noise such as prompt-theme or git-status initialization warnings is not proof of runner failure when the Herdr socket, pane, cwd, and runner lifecycle verify correctly.

For mounted/sshfs workspaces, distinguish local file visibility from the actual remote process environment.

## Runner launch configuration

For an Autopilot run, load the installed Smart Cascade Skill's selected runner
configuration (`runners/omp/runner-launch.yaml` for OMP) before preflight or
launch. It is the launch-parameter authority for Root model, effort/thinking,
permission mode, Smart Cascade role aliases, and native runner arguments.
Runner-format agent definitions and CLI arguments are executable projections
and must match it; do not duplicate or redefine the mapping in dispatch prose.

For non-Autopilot external supervision, precedence remains:

1. explicit user or task-scoped runner setting;
2. runner-native default.

After launch, verify the effective mode from the runner's live state when observable.

## Launch gate

Start only in an available shell pane or adapter-approved target. The launch is complete when the adapter identifies the expected inner agent in the intended pane/workspace and it is ready for input. Process existence alone is insufficient.
