# smart-cascade

**[中文](README-zh.md)** | English

A Claude Code skill for tiered model orchestration. Routes tasks across configurable Judge → Planner → Advisor → Executor layers based on complexity, with parallel worker dispatch and automatic escalation.

## How it works

```mermaid
flowchart TD
    USER([👤 User Input]) --> JUDGE

    subgraph LAYER1["⚖️ Judge Layer — Entry Point"]
        JUDGE[Judge\nAll tasks enter here]
        DETECT{Complexity\nDetection}
        JUDGE --> DETECT
    end

    DETECT -- "Simple — Judge\nhandles directly" --> DONE([✅ Reply directly])
    DETECT -- "Medium / Plan\nhands off to Planner" --> PLANNER_START

    subgraph LAYER2["🔵 Planner Layer — Planning & Coordination"]
        PLANNER_START[Spawn Planner Subagent]
        PLANNER_TRY[Planner attempts task]
        PLANNER_CHECK{Confident?}
        PLANNER_START --> PLANNER_TRY
        PLANNER_TRY --> PLANNER_CHECK
    end

    PLANNER_CHECK -- "UNCERTAIN — asks Advisor" --> ADVISOR_SOLVE
    PLANNER_CHECK -- "CONFIDENT — light review" --> ADVISOR_REVIEW

    subgraph LAYER3["🟣 Advisor Layer — Deep Reasoning"]
        ADVISOR_SOLVE[Advisor Deep Solve\nPlanner was stuck — Advisor unblocks]
        ADVISOR_REVIEW[Advisor Light Review\nPlanner was confident — sanity check]
    end

    ADVISOR_SOLVE --> MERGE
    ADVISOR_REVIEW --> MERGE

    MERGE([Advisor feedback merged]) --> PLANNER_REFINE

    subgraph LAYER2B["🔵 Planner Refinement"]
        PLANNER_REFINE[Planner refines plan\nbased on Advisor feedback]
        PLANNER_SPLIT[Planner splits plan\ninto atomic task list]
        PLANNER_REFINE --> PLANNER_SPLIT
    end

    PLANNER_SPLIT --> DISPATCH

    DISPATCH([Task Dispatch]) --> T1 & T2 & T3

    subgraph LAYER4["🟢 Executor Parallel Workers"]
        T1[Executor Worker 1\nAtomic Task A]
        T2[Executor Worker 2\nAtomic Task B]
        T3[Executor Worker N\nAtomic Task ...]

        T1_CHECK{Done?}
        T2_CHECK{Done?}
        T3_CHECK{Done?}

        T1 --> T1_CHECK
        T2 --> T2_CHECK
        T3 --> T3_CHECK
    end

    T1_CHECK -- "✅ DONE" --> COLLECT
    T2_CHECK -- "✅ DONE" --> COLLECT
    T3_CHECK -- "✅ DONE" --> COLLECT

    T1_CHECK -- "❌ BLOCKED" --> ESC1_P
    T2_CHECK -- "❌ BLOCKED" --> ESC2_P
    T3_CHECK -- "❌ BLOCKED" --> ESC3_P

    subgraph ESC_LAYER["🔵🟣 Escalation — Planner → Advisor if needed"]
        ESC1_P[Strike 1: Planner\nattempts directive]
        ESC1_U{Planner\nconfident?}
        ESC1_A[Strike 2: Advisor\ndeep solve]
        ESC1_P --> ESC1_U
        ESC1_U -- "UNCERTAIN or\nstill BLOCKED" --> ESC1_A
        ESC1_A -- "Planner distills\ndirective" --> ESC1_U

        ESC2_P[Strike 1: Planner\nattempts directive]
        ESC2_U{Planner\nconfident?}
        ESC2_A[Strike 2: Advisor\ndeep solve]
        ESC2_P --> ESC2_U
        ESC2_U -- "UNCERTAIN or\nstill BLOCKED" --> ESC2_A
        ESC2_A -- "Planner distills\ndirective" --> ESC2_U

        ESC3_P[Strike 1: Planner\nattempts directive]
        ESC3_U{Planner\nconfident?}
        ESC3_A[Strike 2: Advisor\ndeep solve]
        ESC3_P --> ESC3_U
        ESC3_U -- "UNCERTAIN or\nstill BLOCKED" --> ESC3_A
        ESC3_A -- "Planner distills\ndirective" --> ESC3_U
    end

    ESC1_U -- "DIRECTIVE" --> T1
    ESC2_U -- "DIRECTIVE" --> T2
    ESC3_U -- "DIRECTIVE" --> T3

    COLLECT([📦 Collect all results]) --> FINAL([✅ Final Output])

    classDef judge fill:#2a1a1a,stroke:#f97316,color:#fed7aa
    classDef executor fill:#1a3a2a,stroke:#4ade80,color:#86efac
    classDef planner fill:#1a2a3a,stroke:#38bdf8,color:#7dd3fc
    classDef advisor fill:#2a1a3a,stroke:#a78bfa,color:#c4b5fd
    classDef terminal fill:#1e2130,stroke:#64748b,color:#94a3b8
    classDef merge fill:#2a2a1a,stroke:#fbbf24,color:#fde68a

    class JUDGE judge
    class T1,T2,T3 executor
    class PLANNER_START,PLANNER_TRY,PLANNER_REFINE,PLANNER_SPLIT,ESC1_P,ESC2_P,ESC3_P planner
    class ADVISOR_SOLVE,ADVISOR_REVIEW,ESC1_A,ESC2_A,ESC3_A advisor
    class DONE,FINAL terminal
    class MERGE,DISPATCH,COLLECT merge
```

## Why smart-cascade

**Advisor feedback loop**
The Planner ↔ Advisor interaction is iterative. After the Advisor responds, the Planner re-evaluates its confidence. If still UNCERTAIN, it loops back to the Advisor. This continues until the Planner can move forward. The same loop applies per-worker during execution when a worker gets blocked.

## Installation

Copy the skill files into your Claude Code skills directory:

```bash
# Global (available in all projects)
mkdir -p ~/.claude/skills/smart-cascade
cp SKILL.md ~/.claude/skills/smart-cascade/
cp smart-cascade.json ~/.claude/skills/smart-cascade/

# Or project-local
mkdir -p .claude/skills/smart-cascade
cp SKILL.md .claude/skills/smart-cascade/
cp smart-cascade.json .claude/skills/smart-cascade/
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
/smart-cascade --judge=sonnet --advisor=opus --planner=sonnet --executor=haiku "your task"
```

### Option 2: Config file (persistent)

Edit `smart-cascade.json` in the same directory as the skill file:

```json
{
  "judge": "sonnet",
  "advisor": "opus",
  "planner": "sonnet",
  "executor": "haiku"
}
```

| Role | Default | Purpose |
|---|---|---|
| `judge` | `sonnet` | Entry point — complexity detection, simple task execution, handoff to Planner |
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
| `docs/smart-cascade-zh.md` | Chinese skill definition |
| `docs/model-routing-workflow.html` | Interactive routing workflow diagram |
| `smart-cascade.json` | User config (models) |

## License

MIT
