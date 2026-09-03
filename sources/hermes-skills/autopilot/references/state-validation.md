# Runtime state validation boundary

The old Autopilot-owned `run/state.json` validator is retired. Do not revive `controller_managed`, `persistent_root_coordinator`, one-slice release, or Autopilot Git-authority fields.

The current implemented validator covers only the static queue:

```bash
python3 ~/.omp/skills/smart-cascade/bootstrap/validate-queue.py .smart-cascade/queue.toml
```
A future production-state validator belongs to Root's recovery seam and must verify:

- stable logical slice/child identity and dependency milestones;
- ordered attempt lineage and parent candidate/base;
- native OMP `isolated=true` task mode and retained patch artifact identity;
- child task-scope assignments and worktree confinement;
- Hub prose settlement correlation using slice/attempt/nonce labels where needed;
- Leader/Executor settlement and bounded serial assembly;
- candidate freeze, Advisor/acceptance-target verification evidence, and Root decision;
- accepted patch application, commit/integration identity, and dependency advancement;
- cleanup or preserved-blocker disposition.

Autopilot may verify signed/readable outputs for supervision and final reporting, but it is not the production-state writer or a second validator-owned scheduler.

Historical JSON state remains archive evidence only.
