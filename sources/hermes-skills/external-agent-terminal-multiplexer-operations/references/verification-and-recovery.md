# Parent verification, takeover, and recovery

Load this branch after a completion signal, when the inner agent stalls/fails, or when real services must be exercised.

## Fixed-baseline verification

The external controller verifies the real target:

```text
session/process/attempt identity
git status including untracked files
changed-file scope and focused diff
targeted checks
full deterministic suite when required
static/type/syntax checks
approved real-behaviour smoke
artifact cleanup and residual risk
```

A review based only on `git diff` hides untracked files. Runner prose and adapter summaries are never the sole evidence.

For sshfs, mounted views, or remote projects, material tests and service smoke run in the actual runtime repository/environment. Local file visibility proves only that files changed.

## Recovery

On runner/API/transport failure:

1. freeze and preserve the current diff and artifacts;
2. inspect adapter, process, session, and repo state;
3. recover or replace the inner-agent process against the same logical lane/worktree;
4. assign a fresh attempt identity and watchers;
5. pass a bounded continuation packet from durable project state;
6. verify the post-recovery baseline before resuming.

Runner exit does not authorize worktree deletion. A clean no-result attempt may be removed; a dirty attempt remains until integrated or explicitly abandoned.

## Takeover and live smoke

If the inner agent stalls on an external service or repetitive gate:

- park only the inner agent after preserving its work;
- keep useful service/test processes alive;
- inspect existing scripts, redacted config, health, ports, and logs;
- drive the smallest known-good real path directly;
- verify nested/per-target results, not only HTTP status or outer success;
- report layered verdicts.

Raw transcripts, credentials, private paths, and full model/tool payloads remain in ignored/temp artifacts. Commit only concise redacted evidence when required.

## Recovery gate

Recovery/acceptance is complete only when the exact baseline is reproducible, real behaviour is exercised or a concrete `not_smokeable_reason` exists, sensitive artifacts are contained, and the parent authority issues the verdict.
