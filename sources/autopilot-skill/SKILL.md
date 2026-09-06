---
name: autopilot
description: "Use when supervising a Smart Cascade run: bootstrap and verify Root, observe lifecycle/progress, intervene or recover on drift/stall/blockers, and verify/report run completion without becoming the production scheduler."
version: 0.6.0
author: Iris Rinne
platforms: [linux, macos]
---

# Autopilot

Autopilot is the external supervisor for one Smart Cascade run. Root is the sole production coordinator and owns the complete DAG, ready-frontier scheduling, Leader/Advisor coordination, slice decisions, commits, integration, and cleanup.

Read before controlling a run:

- [`references/architecture.md`](references/architecture.md)
- [`references/run-contract.md`](references/run-contract.md)
- [`references/state-machine.md`](references/state-machine.md)
- [`references/queue-validation.md`](references/queue-validation.md)
- [`references/state-validation.md`](references/state-validation.md)
- [`references/hierarchical-lanes.md`](references/hierarchical-lanes.md)
- [`references/smart-cascade-flow.md`](references/smart-cascade-flow.md)

Supervision settings — which profile Root is initialized under, which verifier agent to start, observation interval, commit-dialog answer — live in [`autopilot-config.yaml`](autopilot-config.yaml). Read the effective values from there instead of hardcoding them, and change a default by editing that file. Precedence is an explicit user or frozen-run override, then that file, then the Skill default.

Before any Herdr command, load the installed `herdr` skill and follow its current syntax and environment boundary. Herdr owns Root terminal transport and process observation. OMP owns native subagent communication and child lifecycle. Neither transport owns production authority.

## Run bootstrap

1. Verify the exact project, approved `.smart-cascade/queue.toml`, selected Smart Cascade Skill runner config, Root identity, and initial Git base. The project root comes from the user's invocation; `project` in [`autopilot-config.yaml`](autopilot-config.yaml) supplies the profile Root is initialized under, the runner kind, and the queue path within that project.
2. When the user chooses external supervision, use the installed `herdr` skill to create and control the explicitly owned Root session, then initialize Root with the installed Smart Cascade Skill contract.
3. Run the installed runner adapter's `check` operation, passing `project.profile` as `--profile` when it is set, and retain its exact `ADAPTER_READY` receipt. The adapter resolves and persists the profile selection into the project's own `.smart-cascade/override.yaml`; it stays the single source of truth for which profile a project runs under, so never write that file directly and never launch under a profile the receipt did not confirm. After the user's one explicit run-level authorization, send the complete approved queue boundary to Root through the installed `herdr` skill.
4. Arm read-only progress observation and immediate Root/subagent lifecycle or blocker doorbells. [`scripts/agent-watch.sh`](scripts/agent-watch.sh) is the reference watcher, with four modes: `selftest` (verify every observation source), `status` (one snapshot), `heartbeat` (sleep one interval, then compare an output fingerprint against the previous round), and `guard` (block on `herdr agent wait` and exit on any settled or anomalous state). It hardcodes no session, pane, agent name, or repository: pass `--session/--repo/--minutes`, or let it discover the busiest agent-bearing pane itself. Both `heartbeat` and `guard` exit on wake, so run them as ordinary notifying background jobs and let exit notification return control to the supervisor — never as a detached service that can only message the user.

   Three observation rules are load-bearing, each learned from a real false report:
   - Agent names are not stable targets. A named agent reverts to anonymous after a reconnect, and the `omp` in `agent list` is a type, not a name. Always resolve a pane id and target that.
   - `agent_status` lies. OMP sits at `idle` while running tools, and a throwaway child process that inherits `HERDR_*` can poison the pane's session reference and pin the status permanently. Judge progress by monotonic quantities — session transcript bytes, context percentage, pane revision — and by real Git output.
   - An empty pane read is *observation unavailable*, never *no activity*. Report it as a defect and keep watching.
5. Record bootstrap/control evidence without creating a mutable production queue. Direct user invocation through the `smart-cascade` Skill uses the current OMP session as Root and does not require Autopilot or Herdr.

## Dispatching

A runner CLI's failure output does not prove a prompt was not delivered. `agent_prompt_stalled` and `timeout` both occur *after* the text has already entered the session, so resending on that evidence double-writes the instruction. Read the pane instead: the prompt is visible there. If it arrived, do not resend whatever the CLI reported; if it plainly did not, resend the unchanged text; if it appears twice, tell Root it landed twice and to treat it as one, and let the run continue.

Dispatch only to the exact resolved pane, and never send new work to an agent already `working`.

## Authority

Autopilot may:

- create/control the explicitly owned Herdr Root session;
- initialize Root and verify environment, queue, runner, and identity evidence;
- issue the run-level authorization packet;
- observe Root plus OMP subagent lifecycle/progress/transcript evidence;
- start a separate verifier pane and dispatch verification work to it, then review its retained output read-only;
- inspect approved repository/worktree evidence read-only;
- steer, interrupt, or recover Root after a stall, boundary violation, lost transport identity, or explicit blocker;
- escalate architecture/product/authorization decisions to the user;
- verify and report final run-level completion.

### Answering runner UI dialogs

When the user has explicitly delegated routine acceptance for a run (typically so the
run can proceed while they are away), Autopilot may answer runner-native approval or
question dialogs on their behalf instead of stopping the run. This overrides the base
`herdr` skill's "ask the user before answering it" for the delegated run only.

Answer directly: tool-permission prompts, continue/confirm dialogs, and runner UI noise
unrelated to production (telemetry, feedback, update nags, crash-report offers).

Still escalate, never answer: changes to the approved queue, Git base, or approved scope;
architecture or product-boundary decisions; anything with an external side effect
(publishing, pushing, deleting production data); anything outside the approved scope.

Root's post-acceptance `commit` / `keep as candidate` dialog is answerable under this
delegation, because Root has already made the acceptance decision the dialog reports —
what remains is recording it. Answer it per `commit_boundary` in
[`autopilot-config.yaml`](autopilot-config.yaml): recommend that file's
`recommendation`, and auto-select it once `auto_select_after_seconds` passes with no
manual choice. Setting `answer: ask` puts every such dialog back to the user. Log which
option was taken and whether it was explicit or auto-selected. This covers the local
commit only; pushing, merging, and integration remain external side effects that escalate.

Answering that dialog does not relax the tier obligation above. If the higher-tier
entry points were not run, the boundary is already violated and the dialog is not the
place to fix it — hold and steer Root instead.

Capture pane evidence BEFORE answering, and append one line per answer to a run-scoped
proxy-answer log recording timestamp, what the dialog asked, what was chosen, and the
evidence path. An answer without retained evidence is a boundary violation.

Absent explicit delegation, inspect the dialog and ask the user.

Autopilot does not:

- compute or release the ready frontier;
- dispatch Leaders or Executors;
- choose direct/delegated/mixed execution;
- decide routine slice `PASS`, `REWORK`, or `BLOCKED`;
- commit, merge, integrate, or order production commits;
- create, remove, or clean production worktrees;
- write production status into the static queue;
- invent a second scheduler, queue, child registry, mailbox, or acceptance state machine.

A boundary violation permits supervision action, not takeover. Stop or steer Root, preserve evidence, and resume through Root after the issue is resolved.

## Supervision loop

1. **Identify** — verify project, run authorization, the approved queue and runner config, Root identity, initial base, and current Herdr/OMP evidence.
2. **Observe** — inspect real lifecycle/progress evidence. Periodic progress is read-only; completion/blocker events are doorbells only.
3. **Reconcile** — on uncertainty, inspect the exact Root/session identity and production evidence before steering or retrying. A timeout or lost response does not prove absence.
4. **Intervene** only when Root is stalled, repeatedly inspecting without dispatching, violating the approved boundary, losing required runtime capability, or requesting an external decision.
5. **Recover** the same run identity where safe. Do not replace logical slices merely because a runner or worktree attempt failed.
6. **Report** final run completion only after Root supplies verifiable slice decisions, accepted commit/integration evidence, declared acceptance targets with credible reported verification, cleanup dispositions, and remaining blockers/residual risk.

## Working Root

`working` is activity evidence, not a DAG lock. Normal Root scheduling proceeds inside the Root session. Low-volume supervisory input may use the selected runner's steering or follow-up mechanism; a settled Root may receive a normal prompt.

## Candidate and Git evidence

Root owns candidate freeze, Advisor selection, slice acceptance, REWORK, commit/integration, dependency advancement, and cleanup. Autopilot may verify those facts for supervision/reporting, but its observation does not create a second verdict.

Never call runner `done`, child `completed`, prompt wait success, inactivity, or a clean terminal accepted or integrated. Require Root's typed production evidence plus real Git/worktree verification.

### Higher-tier verification before any commit

`checks` declare verifiable acceptance targets, not a predeclared command list; they may be natural-language outcomes or commands already known when the queue is written. The framework only passes these texts through. After implementation, the Leader/Executor determines the appropriate verification methods, runs them, and reports the actual commands and results in the settlement `checks` field. Slice `checks` are the floor. Before the commit boundary, the project's own higher-tier verification entry points — end-to-end, smoke, integration, contract, and equivalents — must be enumerated from the project's manifest and every one whose preconditions the environment already satisfies must actually be run. A queue whose `checks` name only the unit-test command does not narrow this obligation, and a green unit-test suite never substitutes for an unrun tier.

Verification follows commit authority:

- **Root commits** (the normal path) — Root runs these tiers itself and reports each as passed, failed, or not-runnable-with-reason. Autopilot verifies that this happened and that the reported results are real; a commit boundary reached without it is a boundary violation, so hold the boundary and steer Root rather than waving it through.
- **A dedicated verifier agent cross-checks** — where the run wants an independent reading of those tiers, start a separate pane and dispatch a verifier agent to run them. Autopilot keeps its role: it dispatches, monitors, and reviews the artifacts read-only. It does not run project verification commands itself, and it never commits.

A missing precondition is `not runnable` and must be named, never silently treated as passing. Failures at these tiers block the commit boundary exactly as an unmet acceptance target does — never commit past them. Blocking the boundary is not stopping the run: route the failure back to Root as a `REWORK` finding and let it proceed.

### The verifier agent

The verifier exists because a runner grading its own homework is weak evidence — the same misreading that let a tier go unrun tends to survive into the report about it. Giving verification its own pane and its own agent means the tiers get executed by something that did not write the code and has no stake in the slice passing.

Start it in a pane of its own and dispatch to it like any other target. Which agent starts, and how it launches, come from `verifier` in [`autopilot-config.yaml`](autopilot-config.yaml); do not hardcode a runner, model, or profile here. `verifier.enabled: false` skips the cross-check and leaves Root's own reporting as the only reading. Point it at the worktree under verification and require it to report every higher-tier entry point as passed, failed, or not-runnable-with-reason, with the command and its real output retained.

Its verdict is evidence for the commit boundary, not a slice decision. `PASS`/`REWORK` stays with Root.

When the verifier and Root disagree, or a tier comes back failing, the run does not stop — it routes. Weigh the two reports on their evidence rather than their source: which one names the exact entry point, retains the real command output, and accounts for preconditions. A report that shows the failing output outweighs one that asserts a pass without it, and a `not runnable` with a named missing precondition is neither a pass nor a contradiction.

Then hand the assessment back to Root as the finding for a `REWORK`, and say which reading the evidence favours and why. Root decides the disposition and may pull in an Advisor where the disagreement is substantive rather than mechanical. That assessment is input to Root's decision, never a second verdict: Autopilot does not re-run the tiers to break the tie, does not overturn a slice decision, and does not commit on the strength of its own reading.

Escalate to the user only for what Root genuinely cannot absorb — architecture or product-boundary changes, scope beyond the approved queue, or an external side effect. A failing tier, a disputed report, and a repeated `REWORK` are all ordinary run traffic; route them through Root and keep going.

## Native OMP task boundary

The OMP production path is native asynchronous task dispatch, not a borrowed-worktree adapter:

- Root→Leader and Leader→Executor writing tasks request `isolated=true`.
- The selected profile-wide isolation policy is `task.isolation.mode=auto`, `apply=false`, and `merge=patch`.
- Hub carries plain-prose runtime messages, with explicit slice, attempt, and nonce labels when needed for correlation; it is not a JSON status-object channel. Strict structured output belongs to task completion. Parents validate the prose handoff against real artifact bytes and the retained patch before serial application.

For `REWORK`, Root or Leader rematerializes a new attempt from an explicit base, reapplies the last verified cumulative patch, verifies that replay, and handles only the remaining findings. Logical slice and child identities remain stable across attempts. A failed temporary attempt with no retained artifact is reported honestly and restarts from the last verified candidate; a validated retained artifact from a blocker is preserved as evidence only and never promoted to `PASS`.

Herdr supervises the Root process and provides external observation only. It does not replace native OMP task dispatch, Hub communication, patch retention, or production authority.

The executable Root seams belong to the installed Smart Cascade Skill: `bootstrap/frontier.py` computes a bounded maximum-safe frontier without persisting topology; `bootstrap/state.py` atomically owns only slice/child rework counters. Root reads child results as the runner delivers them and verifies the work itself against the real diff and the acceptance targets. Autopilot may inspect receipts but never invokes these seams to schedule or accept production work.

## Stop and escalation conditions

Intervene or escalate for:

- wrong project/Root/run identity or changed approved queue/base;
- unresolved transport ambiguity;
- Root inspection loops or loss of production progress;
- architecture, product boundary, approved-scope, permission, or live-side-effect decisions outside the approved run;
- unrecoverable runtime/plugin capability failure;
- user direction.

Independent production chains remain Root's responsibility. Autopilot does not serialize healthy work merely because one chain blocks.

Nothing else stops the run. A failing tier, a verifier disagreeing with Root, and a repeated `REWORK` are the run working as intended — assess the evidence, route it back to Root, and continue. Stopping is for the conditions above, where continuing would mean guessing at something Root has no way to resolve.
