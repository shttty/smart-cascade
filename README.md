# smart-cascade

**[中文](README-zh.md)** | English

A Claude Code skill for tiered model orchestration. Routes tasks across configurable Advisor → Planner → Executor layers based on complexity, with parallel worker dispatch and automatic escalation.

## How it works

```
Simple task  →  handle directly, skip cascade
Medium/Plan  →  Planner plans → Advisor reviews → split into atomic tasks → Executor workers (parallel)
                                                                              ↓ BLOCKED?
                                                                         Planner escalates → retry
```

## Installation

Copy the skill file into your Claude Code skills directory:

```bash
# Claude Code CLI (global)
cp SKILL.md ~/.claude/skills/smart-cascade.md

# Or project-local
cp SKILL.md .claude/skills/smart-cascade.md
```

Optionally copy the config file to the same directory:

```bash
cp smart-cascade.json ~/.claude/skills/smart-cascade.json
```

## Usage

```
/smart-cascade "build a REST API for user auth"
/smart-cascade "refactor the payment module"
```

This skill must be **explicitly invoked** — it is never auto-triggered.

## Configuration

### Option 1: CLI parameters (per-invocation)

```
/smart-cascade --advisor=opus --planner=sonnet --executor=haiku "your task"
```

### Option 2: Config file (persistent)

Edit `smart-cascade.json` in the same directory as the skill file:

```json
{
  "advisor": "opus",
  "planner": "sonnet",
  "executor": "haiku"
}
```

| Role | Default | Purpose |
|---|---|---|
| `advisor` | `opus` | Deep review and risk analysis (Phase 2) |
| `planner` | `sonnet` | Planning, refinement, escalation guidance |
| `executor` | `haiku` | Atomic task execution (parallel workers) |

**Priority:** CLI params > config file > built-in defaults

Any valid Claude model ID is accepted (e.g. `claude-opus-4-5`, `claude-sonnet-4-5`, `claude-haiku-4-5`).

## Phases

| Phase | What happens |
|---|---|
| 0 | Complexity gate — simple tasks skip the cascade entirely |
| 1 | Planner attempts the task and emits a confidence signal |
| 2 | Advisor deep-solves (UNCERTAIN) or light-reviews (CONFIDENT) |
| 3 | Planner refines the plan and splits into atomic tasks |
| 4 | Executor workers run in parallel waves (max 4 concurrent) |
| 5 | Blocked workers escalate to Planner for a single directive |
| 5.5 | Integration check across all completed tasks |
| 6 | Results collected and presented |

## Files

| File | Description |
|---|---|
| `SKILL.md` | English skill definition |
| `smart-cascade-zh.md` | Chinese skill definition |
| `smart-cascade.json` | User config (models) |

## License

MIT
