---
name: smart-cascade
description: "Tiered model orchestration for medium-to-complex tasks. Must be explicitly invoked via /smart-cascade — never auto-triggered. Executor handles simple work directly. Medium/plan tasks escalate to Planner for planning, Advisor for review, then split into atomic tasks dispatched to parallel Executor workers. Worker failures escalate via inline Planner advisor agents."
---

# Smart Cascade — Tiered Model Orchestration

Routes tasks across Executor → Planner → Advisor → Executor workers based on complexity.
Uses inline advisor agent calls for inter-layer escalation.

## Invocation

This skill must be **explicitly invoked** — it is never auto-triggered.

```
/smart-cascade "build a REST API for user auth"
/smart-cascade "refactor the payment module"
```

## Configuration

Override the default models by specifying them at invocation time:

```
/smart-cascade --advisor=opus --planner=sonnet --executor=haiku "your task"
```

Or persist your preferences in a config file at `smart-cascade.json` in the same directory as this skill file:

```json
{
  "advisor": "opus",
  "planner": "sonnet",
  "executor": "haiku"
}
```

Create or edit this file manually to set your preferred models without specifying them every time.

| Role | Parameter | Built-in Default | Purpose |
|---|---|---|---|
| **Advisor** | `--advisor` | `opus` | Deep review, risk analysis (Phase 2) |
| **Planner** | `--planner` | `sonnet` | Planning, refinement, escalation guidance (Phases 1, 3, 5, 5.5) |
| **Executor** | `--executor` | `haiku` | Atomic task execution (Phase 4 workers) |

**Resolution order (highest to lowest priority):**
1. CLI parameters passed at invocation (`--advisor=...`)
2. Config file at `~/.claude/smart-cascade.json`
3. Built-in defaults (`opus` / `sonnet` / `haiku`)

**Reading configuration:** At the start of every cascade, resolve the three model variables — `{ADVISOR_MODEL}`, `{PLANNER_MODEL}`, `{EXECUTOR_MODEL}` — by checking CLI params first, then reading `smart-cascade.json` in the same directory as this skill file if it exists, then falling back to built-in defaults. Any valid Claude model ID is accepted (e.g. `claude-opus-4-5`, `claude-sonnet-4-5`, `claude-haiku-4-5`).

## Phase 0: Complexity Gate

Assess the task before doing anything else. Route based on complexity:

| Complexity | Signals | Action |
|---|---|---|
| **Simple** | Single Q&A, one file, < 3 steps, no planning | Handle directly — skip cascade |
| **Medium** | Multi-file, feature impl, debugging, needs planning | Enter cascade at Phase 1 |
| **Plan** | Architecture, cross-service, requires task breakdown | Enter cascade at Phase 1 |

If simple: respond normally. Do NOT enter the cascade.

**Model-tier shortcut:**
- **Running as {EXECUTOR_MODEL}:** Dispatch {PLANNER_MODEL} subagent for Phase 1, then proceed normally.
- **Running as {PLANNER_MODEL}:** Skip Phase 1 subagent dispatch — plan directly as yourself. After planning, self-assess confidence and emit a `CONFIDENT:` or `UNCERTAIN:` signal (same format as Phase 1). Then proceed to Phase 2 using that signal for Path A/B routing.
- **Running as {ADVISOR_MODEL}:** Skip Phase 1 and Phase 2 entirely — plan directly as yourself, then proceed to Phase 3 for task split. Self-review has no value.

---

## Phase 1: Planner Planning

Spawn a {PLANNER_MODEL} subagent to attempt the task and self-assess confidence.

```yaml
Agent:
  description: "Planner planning and confidence assessment"
  model: "{PLANNER_MODEL}"
  prompt: |
    You are a planner-executor. Attempt to fully plan (and where applicable,
    implement) the following task. Think carefully about scope, risks, and approach.

    After your attempt, end your response with one of these confidence signals
    on its own line:
      CONFIDENT: <one sentence summary of your plan>
      UNCERTAIN: <one sentence describing what you're unsure about>

    Do not omit the confidence signal. It drives the next step.

    <task>
    {task from user}
    </task>

    <context>
    {compact handoff built from conversation history — task / situation / blocked_on / attempted / files_in_play}
    </context>
```

Capture the Planner's full response and the confidence signal separately.

**Parsing the confidence signal:** Scan from the last line upward. Match the first line starting with `CONFIDENT:` or `UNCERTAIN:`. If neither is found within the last 10 lines, treat as UNCERTAIN with note: "confidence signal missing from Planner response".

---

## Phase 2: Advisor Consultation

Two paths based on the Planner's confidence signal.

### Path A — UNCERTAIN: Advisor Deep Solve

Build a compact handoff from the Planner's Phase 1 output, then spawn the Advisor directly:

```yaml
Agent:
  description: "Advisor deep solve — Planner uncertain"
  model: "{ADVISOR_MODEL}"
  prompt: |
    You are an advisor. Provide deep expert guidance only — no implementation.
    Think through trade-offs, risks, edge cases, and alternatives thoroughly.

    If the handoff below is insufficient to advise confidently, respond ONLY with:
      NEED_MORE_CONTEXT: <one sentence — exactly what is missing>
    Otherwise respond in this structure:
    1. **Assessment** — what's the situation
    2. **Recommendation** — what to do and why
    3. **Risks** — what could go wrong
    4. **Steps** — concrete next actions (these will be distilled for executors)

    <handoff>
    task: <one line — what the Planner was trying to plan>
    situation: <2-3 sentences from the Planner's Phase 1 attempt>
    blocked_on: <Planner's UNCERTAIN signal verbatim>
    attempted:
    - Planner Phase 1 attempt → {what the Planner tried and where it got uncertain}
    </handoff>
```

If the Advisor returns `NEED_MORE_CONTEXT`, append conversation excerpt and re-dispatch once. If still insufficient, proceed to Phase 3 with the Planner's Phase 1 output and note the gap.

### Path B — CONFIDENT: Advisor Light Review

Spawn a brief Advisor review pass:

```yaml
Agent:
  description: "Advisor light review of Planner plan"
  model: "{ADVISOR_MODEL}"
  prompt: |
    Briefly review the following plan. You are NOT implementing anything.
    Identify: gaps, risks, missed edge cases, or ordering issues.
    Be concise — this is a sanity check, not a deep audit.
    If the plan is solid, say so in one sentence and stop.

    <planner_plan>
    {Planner's full response from Phase 1}
    </planner_plan>

    Respond in this structure:
    - **Verdict**: SOLID | NEEDS_REVISION
    - **Issues** (if NEEDS_REVISION): bullet list, specific and actionable
    - **Suggestions**: optional, max 3 bullets
```

---

## Phase 3: Planner Refinement + Plan Split

Feed Advisor feedback back to the Planner, then split into atomic tasks.

**Refinement rounds based on Phase 2 outcome:**
- **Path B → SOLID** (or Phase 2 skipped): 0 refinement rounds — dispatch the Phase 3 agent for task split only (no refinement needed, but the split still requires a Planner pass).
- **Path B → NEEDS_REVISION**: 1 refinement round addressing the Advisor's specific issues, then task split.
- **Path A (Advisor Deep Solve)**: Always 1 refinement round — the Planner was uncertain and the Advisor provided substantive guidance that must be incorporated.
- If after 1 round the plan still has unresolved gaps, proceed to task split anyway with a gap note: `> *Refinement did not fully converge — proceeding with known gaps: {list}*`

**Model-tier shortcut:** If the orchestrator is already the {PLANNER_MODEL}, perform refinement and task split directly — do not dispatch a Planner subagent. This also applies to Phase 5 escalation advisors and Phase 5.5 integration checks: Planner orchestrators handle these inline rather than dispatching Planner subagents. Dispatch Planner subagents when running as {EXECUTOR_MODEL} or {ADVISOR_MODEL}.

```yaml
Agent:
  description: "Planner refinement and task split"
  model: "{PLANNER_MODEL}"
  prompt: |
    You have an initial plan. {If advisor_feedback is present: "An advisor has
    reviewed it — address their feedback before splitting." Otherwise:
    "No advisor review was performed — proceed directly to task split."}

    <initial_plan>
    {Phase 1 plan — from Planner subagent, or from the orchestrator itself if it planned directly}
    </initial_plan>

    {Include this block ONLY if Advisor feedback exists:}
    <advisor_feedback>
    {Advisor Phase 2 response}
    </advisor_feedback>

    Output your refined plan, then end with a task list in this exact JSON format
    (use JSON, not YAML — it parses more reliably):

    TASK_LIST_START
    [
      {
        "id": "T1",
        "title": "one line title",
        "description": "2-3 sentences: what to do, not how",
        "inputs": "files, data, or results this task depends on",
        "outputs": "what this task produces",
        "acceptance": "one-line: how to verify it's done correctly",
        "depends_on": []
      },
      {
        "id": "T2",
        ...
      }
    ]
    TASK_LIST_END

    Rules for task list:
    - Each task must be executable by a single model in one pass
    - No task should require architectural decisions — those are resolved in the plan
    - Maximize parallelism: only add depends_on when strictly necessary
    - 3-8 tasks typical; more than 10 is a signal the plan needs more refinement
```

**Parsing the task list:** Extract text between `TASK_LIST_START` and `TASK_LIST_END` markers. Parse as JSON. If JSON parsing fails, attempt lenient parsing (strip trailing commas, fix unquoted keys). If still fails, ask the Planner to re-emit the task list only.

---

## Phase 4: Executor Parallel Dispatch

Dispatch tasks in **waves** based on the dependency graph:

1. **Wave 0:** All tasks with empty `depends_on` — dispatch in parallel.
2. **Wait** for Wave 0 to complete.
3. **Wave 1:** All tasks whose `depends_on` are now satisfied — dispatch in parallel.
4. **Repeat** until all tasks are dispatched.

If a circular dependency is detected, surface to user immediately — the task split is broken.

**Concurrency limit:** Dispatch at most **4 workers in parallel** per wave. If a wave has more than 4 ready tasks, queue the remainder and dispatch as slots free up.

Each task gets its own Executor worker agent:

```yaml
Agent:
  description: "Executor worker — {task.id}: {task.title}"
  model: "{EXECUTOR_MODEL}"
  prompt: |
    You are an executor. Complete exactly the task below. Do not deviate from scope.
    Do not make architectural decisions — if you encounter one, report BLOCKED.

    <task>
    id: {task.id}
    title: {task.title}
    description: {task.description}
    inputs: {task.inputs}
    outputs: {task.outputs}
    acceptance: {task.acceptance}
    </task>

    <predecessor_outputs>
    {For each task in depends_on that is now DONE, include:
      - {dep.id}: {dep.DONE summary}
    If depends_on is empty, omit this block entirely.}
    </predecessor_outputs>

    <plan_context>
    {Planner's refined plan summary — omit full task list}
    </plan_context>

    End your response with one of:
      DONE: <one line summary of what was produced>
      BLOCKED: <one sentence — specific blocker, not vague>
```

Track worker states: `pending | running | done | blocked | failed`.
As dependencies are satisfied, dispatch queued tasks.

---

## Phase 5: Worker Escalation

When a worker reports `BLOCKED`:

**Classify the blocker first:**

| Blocker type | Signal | Action |
|---|---|---|
| **Environment** | Missing dependency, permission denied, command not found | Auto-fix (install, chmod, etc.) — does NOT count as an escalation attempt |
| **Logic/Design** | Architectural question, ambiguous requirement, conflicting constraints | Escalate to Planner |
| **Unknown** | Anything else | Escalate to Planner |

For environment blockers, attempt auto-fix then re-dispatch the same task. **Max 2 auto-fix attempts per task** — if the environment issue persists after 2 tries, escalate as a logic/design blocker (counts toward the three-strike limit).

For logic/design blockers, the escalation chain is:

**Strike 1 — Planner solo:**

1. Build a compact handoff for the blocker:
   - `task`: the blocked task title
   - `situation`: plan context + what the worker attempted
   - `blocked_on`: worker's BLOCKED message verbatim
   - `attempted`: worker's partial output (if any)
   - `files_in_play`: task inputs/outputs

2. Spawn Planner escalation advisor:

   ```yaml
   Agent:
     description: "Planner escalation advisor — task {task.id} blocked (attempt 1)"
     model: "{PLANNER_MODEL}"
     prompt: |
       An Executor is blocked on a task. Provide a single actionable directive
       to unblock it. Do NOT provide analysis, alternatives, or reasoning —
       output one concrete instruction the executor can follow immediately.
       If you are not confident in a solution, end with: UNCERTAIN: <one sentence why>

       <handoff>
       task: {task.title}
       situation: {plan_context summary — 2 sentences max}
       blocked_on: {worker's BLOCKED message verbatim}
       attempted: {worker's partial output if any}
       files_in_play: {task inputs/outputs}
       </handoff>

       Output format (strictly):
       DIRECTIVE: <one sentence — exactly what the Executor worker should do next>
   ```

3. If Planner emits `UNCERTAIN`, proceed to **Strike 2 — Planner + Advisor** immediately (do not re-dispatch the worker yet).
4. Otherwise extract the `DIRECTIVE` and re-dispatch the worker.

**Strike 2 — Planner + Advisor (triggered when Planner is uncertain OR worker is BLOCKED again after Strike 1):**

1. Spawn Advisor to deep-solve the blocker:

   ```yaml
   Agent:
     description: "Advisor deep solve — task {task.id} blocked (attempt 2)"
     model: "{ADVISOR_MODEL}"
     prompt: |
       A Planner is unable to resolve a worker blocker. Provide deep expert guidance.
       Think through the root cause, risks, and the single best resolution path.

       <handoff>
       task: {task.title}
       situation: {plan_context summary — 2 sentences max}
       blocked_on: {worker's BLOCKED message verbatim}
       planner_uncertain: {Planner's UNCERTAIN signal if present, else "Planner gave directive but worker remained blocked"}
       files_in_play: {task inputs/outputs}
       </handoff>

       Respond in this structure:
       1. **Root cause** — why is this blocked
       2. **Resolution** — the single best path forward
       3. **Directive** — one concrete instruction for the executor
   ```

2. Planner distills Advisor's `Directive` into a single-sentence `DIRECTIVE` (never pass raw Advisor output to the Executor).
3. Re-dispatch the worker with the distilled directive.

**Strike 3 — surface to user:**

If the worker reports `BLOCKED` after Strike 2 → surface to user directly. Three strikes total (Strike 1 → Strike 2 → Strike 3 = notify user).

**When a task reaches `failed` state (three strikes exhausted):**
1. Log the final blocker and surface it to the user with the task details.
2. Mark all tasks that transitively depend on the failed task as `failed` — they cannot proceed.
3. Continue dispatching any remaining tasks that do NOT depend on the failed task.
4. Do not wait for user input — proceed to Phase 5.5/6 with partial results once all remaining tasks reach a terminal state.

---

## Phase 5.5: Integration Check

**Skip this phase if fewer than 2 tasks reached `done` state** — a single completed task has nothing to check against.

Before collecting results, run a lightweight Planner pass to verify cross-task consistency:

```yaml
Agent:
  description: "Planner integration check"
  model: "{PLANNER_MODEL}"
  prompt: |
    Review the outputs of all completed worker tasks for cross-task consistency.
    Check for: file conflicts, contradictory changes, missing glue code,
    interface mismatches between tasks that depend on each other.

    <task_outputs>
    {For each completed task:
      - {task.id}: {task.title} → {DONE summary}
      - Files touched: {list of files modified/created}
    }
    </task_outputs>

    Respond with one of:
      CONSISTENT: <one sentence confirmation>
      CONFLICTS: <bullet list of specific conflicts that need resolution>
```

If `CONFLICTS`: attempt auto-resolution for simple cases (e.g., merge ordering). For non-trivial conflicts, surface to user with the conflict list before proceeding to Phase 6.

---

## Phase 6: Result Collection

Once all workers reach a terminal state (`done` or `failed`):

1. Aggregate outputs in task order (T1, T2, ... Tn).
2. Present a summary to the user:

```
## Cascade Complete

Plan: {one-line summary from Planner}
Tasks: {N} completed | {M} escalated | {K} failed
Integration: {CONSISTENT | "N conflicts resolved" | "N conflicts surfaced to user" | "skipped (<2 done tasks)" | "skipped (agent failed)"}

### Results
{task outputs in order}

### Notes
{any escalations, fallbacks, integration conflicts, or partial failures}

### Failed Tasks (if any)
{For each failed task: task id, title, final BLOCKED message, and list of downstream tasks that were skipped}
```

---

## Budget & Cancellation

**Token budget:** Before entering the cascade, estimate cost:
- Phase 1 (Planner planning): ~2-4k tokens
- Phase 2 (Advisor review): ~1-3k tokens
- Phase 3 (Planner refinement): ~2-4k tokens
- Phase 4 (Executor workers): ~1-2k tokens (config/docs) to ~4-8k tokens (code generation) × N tasks
- Phase 5 (escalations): ~1-2k tokens per escalation
- Phase 5.5 (integration check): ~1-2k tokens

If the estimated total exceeds **50k tokens**, warn the user before proceeding. For tasks estimated above **100k tokens**, require explicit user confirmation.

**Cancellation:** At any phase boundary (between phases, not mid-agent), check if the user has signaled cancellation. If so:
- Collect any partial results from completed phases
- Present what's available with note: `> *Cascade cancelled at Phase {N}. Partial results below.*`
- Do not dispatch further agents

---

## Fallback Rules

- **Planner agent fails (Phase 1)** → run Phase 1 again once. If fails again → handle task directly with current model, warn user.
- **Planner agent fails (Phase 3)** → retry once. If fails again → orchestrator attempts task split directly using the Phase 1 plan and any available Advisor feedback. Note: `> *Phase 3 agent failed — orchestrator performing task split directly.*`
- **Advisor agent fails** → skip Phase 2, proceed to Phase 3 with the Planner's Phase 1 output unchanged. Note: `> *Advisor review skipped ({reason}) — proceeding with unreviewed plan.*`
- **Executor worker fails (crash, not BLOCKED)** → retry once. If fails again → Planner temporarily acts as worker to execute the task directly, noting: `> *Executor crashed on task {id} — Planner executing as temporary worker.*` Report in Phase 6 summary.
- **Planner escalation agent fails (Phase 5)** → Planner handles the blocked task directly as temporary worker, notes: `> *Escalation agent failed — Planner executing task {id} directly.*`
- **Integration check agent fails (Phase 5.5)** → skip integration check, proceed to Phase 6. Note: `> *Integration check skipped ({reason}) — results may have cross-task inconsistencies.*`

---

## Rules

- Gate first: never enter the cascade for simple tasks.
- Confidence signal is mandatory: if the Planner omits it, treat as UNCERTAIN.
- Parallel by default: dispatch all independent tasks simultaneously.
- Atomic tasks only: if a task requires a decision, it's not atomic — refine the split.
- Three escalations max per task: BLOCKED → Planner (Strike 1) → retry → if BLOCKED again or Planner uncertain → Planner + Advisor (Strike 2) → retry → if BLOCKED again → surface to user (Strike 3).
- Escalation is always inline agent calls — no external skill dependencies.
- **Planner plans, never executes.** The Planner's role is planning, refinement, and escalation guidance only. It must not directly execute tasks assigned to Executor workers — not even partially. Explicit exceptions (these are last-resort fallbacks, not normal flow):
  - Executor worker crashes twice on the same task → Planner executes as temporary worker, noting: `> *Executor crashed on task {id} — Planner executing as temporary worker.*`
  - Escalation agent fails → Planner executes the blocked task directly, noting: `> *Escalation agent failed — Planner executing task {id} directly.*`
  - Executor is confirmed unavailable (API error, model down) → Planner executes as last resort, noting: `> *Executor unavailable — Planner executing task {id} as fallback.*`
- **Advisor advises, never executes.** The Advisor's role is review and deep analysis only. It must not execute tasks under any circumstance, including when the Executor is unavailable. If both Executor and Planner are unavailable, surface the task to the user directly.
- **Pass directives down, summaries up.** Information must be distilled at each layer boundary before passing:
  - **Down (→ Executor):** action directives only — *what* to do and *acceptance criteria*. Never pass trade-off analyses, alternative approaches, risk assessments, or advisor reasoning. The Executor cannot leverage this and it wastes tokens.
  - **Up (→ Planner/Advisor):** compact summaries — *what happened* and *what failed*. Not verbose logs or full output.
  - **Never pass raw advisor output to executor tiers.** The Planner must distill the Advisor's analysis into a concrete action directive before it reaches the Executor. Advisor reasoning is for the Planner's consumption only.
  - **Escalation guidance to Executor = one directive.** When re-dispatching a blocked task, the `escalation_guidance` must be a single actionable instruction, not a full Planner analysis.
