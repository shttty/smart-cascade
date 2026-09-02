# Digests

The current static queue is TOML, not JSON. The queue validator checks parsed structure and reports the exact source path; it does not silently rewrite comments or formatting.

## Queue digest

The startup receipt and run-level authorization hash the exact UTF-8 bytes of the approved `.smart-cascade/queue.toml` file:

- UTF-8 without BOM;
- LF line endings;
- no implicit normalization or reformatting;
- SHA-256 stored as `sha256:<64 lowercase hex>`.

A changed comment or formatting byte therefore invalidates the startup gate and creates a new approved queue input. Do not infer semantic equivalence from a parser round-trip.

## Candidate identity

Candidate identity remains a separate runtime concern. A production owner must bind candidate evidence to:

```text
stable slice/child ID and attempt_id
base or inherited candidate identity
sorted changed paths
raw postimage bytes and file modes
named checks and their real results
```

Runner names, panes, sessions, transcripts, and prompt output are evidence, not candidate identity.

## Invalidation

A changed postimage creates a new candidate identity and invalidates candidate-dependent review and checks. `REWORK` preserves the same logical slice/child identity while rematerializing a native OMP isolated attempt from the last verified cumulative patch. The new attempt applies and verifies that patch against an explicit base, then handles only the remaining findings. Temporary isolation is cleaned after patch capture; retained artifact and lineage remain until disposition.
