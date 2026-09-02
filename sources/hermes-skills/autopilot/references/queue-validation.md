# Queue validation

The current queue is a static TOML definition of top-level large slices. Validate it before production, but do not mutate it as part of runtime scheduling.

## Validator

Run:

```bash
python3 ~/.omp/skills/smart-cascade/bootstrap/validate-queue.py .smart-cascade/queue.toml
```

The validator is zero-dependency Python and uses the standard-library `tomllib` parser. It reports a deterministic JSON result and exits non-zero on invalid input.

## Required shape

The document may contain only:

```toml
[[slices]]
id = "stable-logical-slug"
depends_on = []
scope = "..."
write_set = ["src/**"]
checks = ["python3 -m pytest tests/unit"]

```

Required slice fields are `id`, `depends_on`, `scope`, `write_set`, and `checks`. The Leader decides child decomposition at runtime; the queue declares no child topology. The following are invalid queue fields:

```text
schema_version
queue_id
status
title
execution_class
execution_classes
attempts
worktree
runner
candidate
execution_mode
git_authority
root_coordinator
```

Those belong nowhere in this static queue. Root/Leader report production facts and Autopilot records control-plane evidence; the durable runtime seam that joins those domains remains a later design point.

## Checks

The validator must:

1. require a TOML table with a non-empty `slices` array;
2. require unique human-readable slug IDs;
3. require dependencies to refer to existing slices and reject self/cyclic edges;
4. require `scope` to be a non-empty string;
5. require a non-empty `write_set` and validate every entry as a normalized repository-relative path;
6. require a non-empty `checks` list whose entries are non-empty strings;
7. reject unknown fields, old execution-mode fields, and any declared child topology;
8. report write-set overlap between concurrently eligible top-level slices;
9. leave scheduling to Root and never add a `parallel` flag.

`depends_on` is a logical prerequisite, not a promise that slices can run concurrently. Root must also account for shared mutable resources such as lockfiles, generated outputs, snapshots, databases, build directories, common fixtures, and the Git index.

## Path grammar

A write-set entry is either one normalized repo-relative path or a directory prefix ending in `/**`.

Reject absolute paths, empty segments, `.`, `..`, backslashes, NULs, trailing `/`, and glob syntax other than a final `/**`. Normalize separators before overlap checks. Separate worktrees do not make overlapping writes safe.

## Ownership

Autopilot validates the approved boundary, uses the installed `herdr` skill for optional Root startup and control, obtains one explicit `ADAPTER_READY` receipt from the selected runner adapter, and sends the complete queue boundary after one run-level authorization. Root reads the complete queue, computes the incremental top-level ready frontier, decides slice outcomes, and advances dependencies after accepted integration. Leader computes child frontiers. No role writes live status into the TOML file.
