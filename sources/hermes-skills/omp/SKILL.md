---
name: omp
description: "Use when interrupting or steering a live OMP agent turn."
version: 0.1.0
author: Xue Ruo
license: MIT
metadata:
  hermes:
    tags: [omp, interrupt, herdr]
    related_skills: [herdr, external-agent-terminal-multiplexer-operations, autopilot]
---

# OMP interactive control

## When to Use

Use when the inner agent is OMP and you need to start, steer, or stop a live turn. OMP supports multiple selectable profiles; choose and record the profile required by the task. Herdr owns pane/session transport; OMP owns the turn interrupt.

## Interrupt a live turn

When OMP is generating or executing the current turn, interrupt with **Esc**.

Via Herdr:

```bash
herdr --session <name> agent send-keys <agent-or-pane> esc
```

Then verify `agent get` is `idle` or `done` before sending more work.

## Completion criterion

The turn is interrupted only after OMP leaves `working`. A successful `send-keys` is not enough.

## Pitfall

`Ctrl-C` is a shell/process control fallback. It is not the normal OMP turn interrupt. It can leave the OMP process `working` while the current generation continues.

Do not kill the OMP process, close the pane, or restart the Herdr session just to stop one turn.
