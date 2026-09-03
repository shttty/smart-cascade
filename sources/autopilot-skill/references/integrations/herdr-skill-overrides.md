# Autopilot overrides for the installed Herdr skill

This file contains the deliberate Autopilot-specific overrides to the installed `herdr` skill. It is a delta, not a copy of the Herdr operating manual.

## Authority and scope

The installed `herdr --skill`, `herdr --help`, and relevant subcommand help remain authoritative for Herdr command syntax, lifecycle states, prompt submission, readiness, blocked dialogs, reads, and errors.

Autopilot overrides exactly one policy gate: an explicitly authorized Autopilot controller may operate a task-scoped Herdr session from outside a Herdr-managed pane. The installed skill's general `HERDR_ENV=1` requirement remains the default for ordinary/ad-hoc Herdr use.

This override applies only when all of these facts are established:

- the `autopilot` workflow is loaded for a concrete run;
- the run selects Herdr as its control adapter;
- the controller owns or is explicitly authorized to control the target run;
- one exact named session or private/forwarded socket is selected for the run;
- target identity and ownership are unambiguous.

If any fact is missing, remain read-only and resolve it before control.

## External-controller branch

The controller may bind the official Herdr CLI with exactly one task-scoped selector:

```text
HERDR_SESSION=<name>
```

or:

```text
HERDR_SOCKET_PATH=<path>
```

For every command in the logical attempt:

1. retain the same explicit session/socket selector;
2. persist the selector and returned workspace, pane, and agent IDs as runner evidence;
3. use exact IDs or a unique live agent name returned by Herdr;
4. never use `--current`, omitted targets, UI focus, sidebar order, or guessed topology;
5. never set `HERDR_ENV=1` manually;
6. keep official Herdr command semantics unchanged, including `agent prompt`, readiness, lifecycle waiting, blocked-dialog handling, and errors.

A newly owned run may create one unique named session, start its server as a tracked process, verify server version/protocol, and then reuse that selector. An existing session may be controlled only when its ownership and intended run are proven.

## Boundaries

This override does not:

- authorize control of user-owned or ambiguously owned sessions;
- replace Herdr's prompt or key encoding with custom terminal input;
- permit blind retry after a timeout or `agent_prompt_stalled`;
- turn tmux, raw SSH, hooks, transcript watchers, or another multiplexer into an automatic fallback;
- change Herdr lifecycle meanings or make runner state authoritative for Git or acceptance.

On ambiguous submission, reconcile the exact agent, pane, transcript marker, run state, and worktree before retrying. Preserve official Herdr failures as runner evidence.

## Upstream refresh

After updating Herdr:

1. regenerate the local official skill from `herdr --skill`;
2. inspect upstream behavior changes;
3. update Autopilot integration references only where the official behavior changed;
4. keep this file limited to deliberate local policy deltas.

Do not reinsert this override into the generated `herdr/SKILL.md`.
