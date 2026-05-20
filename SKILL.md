---
name: smart-cascade
description: "Tiered model orchestration for medium-to-complex tasks. Must be explicitly invoked via /smart-cascade — never auto-triggered. Judge receives all tasks: simple tasks are handled directly, complex tasks are handed off to Planner. Planner plans with Advisor review, then splits into atomic tasks dispatched to parallel Executor workers. Worker failures escalate via Planner→Advisor chain."
---

# Smart Cascade — Tiered Model Orchestration

Routes tasks across Judge → Planner → Advisor → Executor workers based on complexity.
Uses dedicated subagents with physical tool isolation per role.

## Invocation

This skill must be **explicitly invoked** — it is never auto-triggered.

```
/smart-cascade "build a REST API for user auth"
/smart-cascade "refactor the payment module"
/smart-cascade --force-cascade "create project scaffold"
```

## Agents

Smart Cascade uses four dedicated subagent types. Install them alongside this skill:

```bash
cp agents/*.md ~/.claude/agents/
# or project-local:
cp agents/*.md .claude/agents/
```

| Agent | File | Model | Tools | Role |
|---|---|---|---|---|
| `smart-cascade-judge` | `agents/smart-cascade-judge.md` | sonnet | all | Entry point — complexity gate |
| `smart-cascade-planner` | `agents/smart-cascade-planner.md` | sonnet | Read, Grep, Glob, WebSearch, WebFetch | Planning only — no file writes |
| `smart-cascade-advisor` | `agents/smart-cascade-advisor.md` | opus | Read, Grep, Glob, WebSearch, WebFetch | Advisory only — no execution |
| `smart-cascade-executor` | `agents/smart-cascade-executor.md` | haiku | all | Atomic task execution |

To change a model tier, edit the `model:` field in the corresponding agent file.

**Flags:**

| Flag | Effect |
|---|---|
| `--force-cascade` | Skip Simple path — force all tasks through full Phase 1-4 cascade regardless of Judge complexity assessment. Use when every task must pass Planner + Advisor + Executor chain (e.g. security-sensitive work, superpowers plan execution). |

**If an agent fails to dispatch** (model unavailable, API error), stop immediately and surface to user:

```
ERROR: smart-cascade-{role} agent failed to start.
The {haiku|sonnet|opus} model tier may be unavailable.

To fix, edit the agent file and set a different model:
  ~/.claude/agents/smart-cascade-{role}.md  (global)
  .claude/agents/smart-cascade-{role}.md    (project)

Or set the relevant environment variable to override the model tier:
  ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME   — for smart-cascade-executor
  ANTHROPIC_DEFAULT_SONNET_MODEL_NAME  — for smart-cascade-judge, smart-cascade-planner
  ANTHROPIC_DEFAULT_OPUS_MODEL_NAME    — for smart-cascade-advisor

Do not retry or fall back to a different agent. Cascade aborted.
```

---

## Phase 0: Complexity Gate

Dispatch `smart-cascade-judge` with the task and `--force-cascade` flag status.

The Judge assesses complexity and routes:

| Complexity | Signals | Action |
|---|---|---|
| **Simple** | Single Q&A, one file, < 3 steps, no planning | Judge handles directly — skip cascade |
| **Medium** | Multi-file, feature impl, debugging, needs planning | Judge dispatches `smart-cascade-planner` |
| **Plan** | Architecture, cross-service, requires task breakdown | Judge dispatches `smart-cascade-planner` |

**`--force-cascade` override:** If set, Judge skips Simple path — dispatches `smart-cascade-planner` regardless of complexity.

If simple (and `--force-cascade` not set): Judge executes directly — no further subagents.
If medium/plan (or `--force-cascade` set): Judge dispatches `smart-cascade-planner` and steps back.

---

## Phase 1: Planner Planning

`smart-cascade-planner` receives the task and produces a plan with a confidence signal.

Prompt the planner with:

```yaml
Agent:
  subagent_type: "smart-cascade-planner"
  description: "Planner planning and confidence assessment"
  prompt: |
    <task>
    {task from user}
    </task>

    <context>
    {compact handoff — task / situation / blocked_on / attempted / files_in_play}
    </context>

    End your response with one of:
      CONFIDENT: <one sentence summary of your plan>
      UNCERTAIN: <one sentence describing what you're unsure about>
```

Capture the full response and confidence signal separately.

**Parsing the confidence signal:** Scan from the last line upward. Match the first line starting with `CONFIDENT:` or `UNCERTAIN:`. If neither found within the last 10 lines, treat as UNCERTAIN: "confidence signal missing".

---

## Phase 2: Advisor Consultation

Two paths based on the Planner's confidence signal.

### Path A — UNCERTAIN: Advisor Deep Solve

```yaml
Agent:
  subagent_type: "smart-cascade-advisor"
  description: "Advisor deep solve — Planner uncertain"
  prompt: |
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

```yaml
Agent:
  subagent_type: "smart-cascade-advisor"
  description: "Advisor light review of Planner plan"
  prompt: |
    <planner_plan>
    {Planner's full response from Phase 1}
    </planner_plan>
```

---

## Phase 3: Planner Refinement + Plan Split

```yaml
Agent:
  subagent_type: "smart-cascade-planner"
  description: "Planner refinement and task split"
  prompt: |
    <initial_plan>
    {Phase 1 plan}
    </initial_plan>

    {Include ONLY if Advisor feedback exists:}
    <advisor_feedback>
    {Advisor Phase 2 response}
    </advisor_feedback>

    Output refined plan, then end with task list:

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
      }
    ]
    TASK_LIST_END
```

**Refinement rounds:**
- Path B → SOLID (or Phase 2 skipped): 0 rounds — task split only.
- Path B → NEEDS_REVISION: 1 round addressing Advisor issues, then split.
- Path A (Deep Solve): always 1 round.
- If gaps remain after 1 round: proceed with gap note `> *Refinement did not fully converge — known gaps: {list}*`

**Parsing the task list:** Extract between `TASK_LIST_START` / `TASK_LIST_END`. Parse as JSON. If fails, attempt lenient parse (strip trailing commas, fix unquoted keys). If still fails, re-prompt Planner to re-emit task list only.

---

## Phase 4: Executor Parallel Dispatch

Dispatch tasks in **waves** based on dependency graph:

1. **Wave 0:** All tasks with empty `depends_on` — dispatch in parallel.
2. Wait for Wave 0 to complete.
3. **Wave N:** All tasks whose `depends_on` are now satisfied — dispatch in parallel.
4. Repeat until all tasks dispatched.

If circular dependency detected: surface to user immediately — task split is broken.

**Concurrency limit:** Max 4 workers per wave. Queue remainder, dispatch as slots free.

```yaml
Agent:
  subagent_type: "smart-cascade-executor"
  description: "Executor worker — {task.id}: {task.title}"
  prompt: |
    <task>
    id: {task.id}
    title: {task.title}
    description: {task.description}
    inputs: {task.inputs}
    outputs: {task.outputs}
    acceptance: {task.acceptance}
    </task>

    <predecessor_outputs>
    {For each dep in depends_on that is DONE:
      - {dep.id}: {dep.DONE summary}
    Omit if depends_on is empty.}
    </predecessor_outputs>

    <plan_context>
    {Planner's refined plan summary — omit full task list}
    </plan_context>
```

Track worker states: `pending | running | done | blocked | failed`.

---

## Phase 5: Worker Escalation

When a worker reports `BLOCKED`:

**Classify first:**

| Blocker type | Signal | Action |
|---|---|---|
| **Environment** | Missing dep, permission denied, command not found | Auto-fix (install, chmod) — does NOT count as escalation |
| **Logic/Design** | Architectural question, ambiguous requirement | Escalate to Planner |
| **Unknown** | Anything else | Escalate to Planner |

Environment blockers: auto-fix then re-dispatch. **Max 2 auto-fix attempts** — if persists, escalate as logic/design (counts toward three-strike limit).

**Strike 1 — Planner solo:**

```yaml
Agent:
  subagent_type: "smart-cascade-planner"
  description: "Planner escalation — task {task.id} blocked (attempt 1)"
  prompt: |
    <handoff>
    task: {task.title}
    situation: {plan_context — 2 sentences max}
    blocked_on: {worker's BLOCKED message verbatim}
    attempted: {worker's partial output if any}
    files_in_play: {task inputs/outputs}
    </handoff>

    Output format (strictly):
    DIRECTIVE: <one sentence — exactly what the Executor should do next>

    If uncertain: UNCERTAIN: <one sentence why>
```

If Planner emits `UNCERTAIN` → proceed to Strike 2 immediately (do not re-dispatch worker).
Otherwise extract `DIRECTIVE` and re-dispatch worker.

**Strike 2 — Planner + Advisor:**

```yaml
Agent:
  subagent_type: "smart-cascade-advisor"
  description: "Advisor deep solve — task {task.id} blocked (attempt 2)"
  prompt: |
    <handoff>
    task: {task.title}
    situation: {plan_context — 2 sentences max}
    blocked_on: {worker's BLOCKED message verbatim}
    planner_uncertain: {Planner's UNCERTAIN signal, or "Planner gave directive but worker remained blocked"}
    files_in_play: {task inputs/outputs}
    </handoff>
```

Planner distills Advisor's Directive into single-sentence `DIRECTIVE`. Re-dispatch worker.

**Strike 3 — surface to user.** Three strikes total.

**When task reaches `failed`:**
1. Log final blocker, surface to user.
2. Mark all transitively dependent tasks as `failed`.
3. Continue dispatching tasks that do NOT depend on failed task.
4. Proceed to Phase 5.5/6 with partial results.

---

## Phase 5.5: Integration Check

**Skip if fewer than 2 tasks reached `done`.**

```yaml
Agent:
  subagent_type: "smart-cascade-planner"
  description: "Planner integration check"
  prompt: |
    <task_outputs>
    {For each completed task:
      - {task.id}: {task.title} → {DONE summary}
      - Files touched: {list}
    }
    </task_outputs>

    Respond with:
      CONSISTENT: <one sentence>
      CONFLICTS: <bullet list of specific conflicts>
```

If `CONFLICTS`: auto-resolve simple cases. Non-trivial → surface to user before Phase 6.

---

## Phase 6: Result Collection

```
## Cascade Complete

Plan: {one-line summary from Planner}
Tasks: {N} completed | {M} escalated | {K} failed
Integration: {CONSISTENT | "N conflicts resolved" | "N conflicts surfaced to user" | "skipped (<2 done tasks)"}

### Results
{task outputs in order}

### Notes
{any escalations, integration conflicts, or partial failures}

### Failed Tasks (if any)
{task id, title, final BLOCKED message, downstream tasks skipped}
```

---

## Budget & Cancellation

**Token budget estimate:**
- Phase 1 (Planner): ~2-4k tokens
- Phase 2 (Advisor): ~1-3k tokens
- Phase 3 (Planner refinement): ~2-4k tokens
- Phase 4 (Executor workers): ~1-8k tokens × N tasks
- Phase 5 (escalations): ~1-2k tokens per escalation
- Phase 5.5 (integration): ~1-2k tokens

Warn user if estimated total exceeds **50k tokens**. Require explicit confirmation above **100k tokens**.

**Cancellation:** At any phase boundary, check for user cancellation signal. If cancelled:
- Collect partial results from completed phases
- Note: `> *Cascade cancelled at Phase {N}. Partial results below.*`
- Do not dispatch further agents

---

## Error Handling

**No silent fallbacks.** If any agent fails to start or crashes, stop and surface to user immediately with the error message template from the Configuration section above.

This applies to all roles: Judge, Planner, Advisor, Executor, escalation agents, integration check.

The only exception: if an Advisor returns `NEED_MORE_CONTEXT`, re-dispatch once with additional context. If still insufficient, proceed to Phase 3 with a gap note — this is a content issue, not an agent failure.

---

## Rules

- Gate first: Judge assesses every task — simple tasks never enter the cascade.
- Confidence signal is mandatory: if Planner omits it, treat as UNCERTAIN.
- Parallel by default: dispatch all independent tasks simultaneously.
- Atomic tasks only: if a task requires a decision, it's not atomic — refine the split.
- Three escalations max per task: BLOCKED → Planner (Strike 1) → retry → BLOCKED again or Planner uncertain → Planner + Advisor (Strike 2) → retry → BLOCKED again → surface to user (Strike 3).
- All agents may invoke the user's installed skills (e.g. `/tdd`, `/code-review`). **Exception: never invoke `/smart-cascade` itself** — recursive cascade is forbidden.
- **Judge is the entry point.** All tasks enter through the Judge.
- **Planner plans, never executes.** Tool isolation is enforced by the agent definition — Planner has no Write/Edit/Bash access.
- **Advisor advises, never executes.** Tool isolation is enforced by the agent definition — Advisor has no Write/Edit/Bash access. If both Executor and Planner are unavailable, surface to user directly.
- **Pass directives down, summaries up.**
  - Down (→ Executor): action directives only — what to do and acceptance criteria. No trade-off analyses, advisor reasoning, or alternatives.
  - Up (→ Planner/Advisor): compact summaries — what happened and what failed.
  - Never pass raw Advisor output to Executor. Planner must distill to a single directive first.
  - Escalation guidance to Executor = one directive, not a full analysis.
