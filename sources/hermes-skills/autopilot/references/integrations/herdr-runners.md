## Herdr and runner integration

Load the installed Smart Cascade Skill's selected runner configuration (`runners/omp/runner-launch.yaml` for OMP) before preflight or launch. Root native argv is an opaque argument vector passed unchanged to the selected adapter. Runner-specific models, effort, permissions, plugins, role-file schemas, and protocol remain runner configuration rather than Smart Cascade queue semantics.

Before Herdr commands, load the installed `herdr` skill. Its workflow and current CLI/schema define transport capability and syntax. This file defines project ownership only.

## Primary role

Herdr supervises the Root coding-agent process:

- explicit session/workspace/pane/agent targeting;
- Root process startup and prompt/steering transport;
- Root lifecycle observation and terminal reads;
- recovery evidence when the Root process or transport becomes uncertain.

Herdr does not schedule slices, dispatch routine Leaders, decide candidates, commit/integrate, or own production worktrees.

The preferred production topology keeps Leaders and Executors as native OMP subagents under Root. OMP hub supplies parent/child messaging and wait-any; OMP RPC exposes subagent lifecycle/progress/transcripts to the external supervisor.

## Targeting

- Retain one explicit Herdr session selector for the Root attempt.
- Use an exact Root agent name or pane ID; never rely on focus/sidebar order.
- Record session/workspace/pane/process and native OMP session identity as ephemeral evidence.
- Reconcile identity before retrying after timeout or lost response.

## Root startup and control

Autopilot uses the installed `herdr` skill for Root startup, initialization, prompts, observation, and recovery. It runs the selected runner adapter's `check` operation before the user's one run-level authorization. Runtime correctness remains Root's candidate-validation responsibility; Autopilot has no parallel bootstrap or authorization script.

A settled Root may receive a normal prompt. A working Root may receive low-volume supervisory steering/follow-up. `working` selects the transport mode; it is not a DAG-readiness blocker and does not require a durable release inbox at the expected concurrency.

## Lifecycle evidence

Autopilot uses:

- read-only periodic progress observation;
- immediate Root lifecycle/blocker doorbells;
- OMP RPC subagent lifecycle/progress/transcript observation when available.

Herdr states mean only transport activity:

| Herdr state | Meaning |
| --- | --- |
| `working` | Root attempt is active |
| `idle` | Root is settled and ready for input |
| `done` | settled unseen-work evidence |
| `blocked` | runner requires approval/input |
| `unknown` | classification uncertainty |

No Herdr or OMP lifecycle state means candidate frozen, accepted, integrated, or cleaned. Root establishes and records those production facts.

## External Leader-pane fallback

External Herdr Leader panes are a transport fallback only, not the OMP production path. The OMP track uses native asynchronous tasks with `isolated=true`; do not substitute a borrowed cwd or adapter for native task isolation.

## Worktree and attempt identity

- Root owns logical attempts, candidate validity, accepted patch application, commit/integration disposition, and DAG advancement.
- Leader owns child validation and bounded serial assembly in its own isolated candidate.
- Executors work only within their supplied isolated worktree and task scope; they do not own lifecycle, patch application, commit, merge, or cleanup.
- OMP owns temporary isolation directories, patch capture, and cleanup after settlement. `apply=false` prevents automatic parent mutation and `merge=patch` retains the artifact.
- Hub carries plain-prose parent/child communication and completion context, with explicit slice, attempt, and nonce labels when needed; strict structured output belongs to task completion.

`REWORK` rematerializes a new `attempt_id` from the last verified cumulative patch and explicit base, applies/verifies that patch, and handles only remaining findings. A new attempt does not erase ambiguous or dirty predecessor evidence.

## Failure handling

On timeout, prompt error, target loss, or lost response:

1. inspect the exact Root agent/pane and native session;
2. inspect the unchanged control marker and current production evidence;
3. continue the existing attempt when delivery is proved;
4. retry unchanged control input only when absence is proved;
5. otherwise preserve ambiguity and stop supervision from issuing duplicate control.

A Herdr error authorizes neither a replacement logical slice nor a production Git/worktree action.
