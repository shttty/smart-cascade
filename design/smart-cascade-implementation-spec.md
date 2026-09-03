# Implement Smart Cascade on native OMP

Triage: `ready-for-agent` (repository-local; no issue tracker is configured)

Authority: [`smart-cascade-flow.md`](smart-cascade-flow.md) is the implementation source of truth. [`decisions.md`](decisions.md) records the accepted architecture and rejected routes. This spec translates those decisions into an implementation-ready feature contract without replacing them.

## Problem Statement

Smart Cascade has an accepted production model, role definitions, bootstrap/control-plane material, and a real native OMP smoke, but it does not yet have one complete production implementation that a user can invoke from the current Agent session.

The current control plane still contains the retired staged-dispatch path. The active workflow is spread across design documents, Autopilot references, Root initialization material, OMP role prompts, queue validation, and smoke code. An implementation agent can therefore mistake historical Pi-plugin or borrowed-cwd investigations for required production work, duplicate native OMP lifecycle behavior, or stop after wiring only one layer.

The user needs a Smart Cascade Skill that consumes an approved static queue, asks before beginning, turns the current OMP session into Root, uses native isolated OMP subagents for Leader and Executor work, validates retained patches and settlements, advances the dependency frontier, preserves only minimal rework counters, and resumes interrupted child sessions without inventing another runtime or lifecycle state machine.

## Solution

Implement Smart Cascade as a platform-neutral Skill/Root production loop with native OMP as the first runner adapter.

The user prepares or approves a static top-level queue, establishes a Git checkpoint, invokes Smart Cascade in the current Agent session, reviews the queue/base/runtime boundary, and explicitly authorizes the run. The current session then becomes Root.

Root owns the complete DAG, maximum safe ready frontier, logical attempts, candidate validity, technical slice acceptance, accepted patch application, Git integration, dependency advancement, and cleanup. Root starts isolated Leader tasks through native OMP. Each Leader dynamically decomposes its slice into bounded patch assignments, starts isolated Executor tasks when useful, validates each child settlement and authoritative retained patch, serially assembles verified child patches in its own isolated candidate, and returns one candidate/evidence settlement to Root.

The OMP adapter remains the runtime owner for task sessions, parent/child lineage, asynchronous execution, Agent Hub communication, native task status, strict settlement, transcripts, temporary isolation, retained patch capture, and parked-session recovery. Smart Cascade core receives only closed business packets and normalized runner results; it adds no child registry, lifecycle store, tombstone store, lease/fencing mechanism, plugin runtime, or parallel child state machine.

Only slice-level and child-level rework counts are persisted by core. All other runtime facts remain in the approved queue/configuration, runner-native evidence, retained patches, Git state, and explicit handoff messages.

## User Stories

1. As a Smart Cascade user, I want to invoke the workflow from my current Agent session, so that I do not have to create or discover another Root session.
2. As a Smart Cascade user, I want the workflow to require an existing approved static queue, so that implementation does not silently redesign my task decomposition.
3. As a Smart Cascade user, I want queue validation to fail closed before production work, so that malformed or over-broad slices do not enter the run.
4. As a Smart Cascade user, I want to see the queue, Git baseline, execution profile, and production boundary before work starts, so that authorization is explicit and informed.
5. As a Smart Cascade user, I want the workflow to ask for confirmation before starting production dispatch, so that invoking the Skill is not itself authorization to mutate the repository.
6. As a Smart Cascade user, I want one run-level authorization for the complete approved queue, so that Autopilot does not release slices one at a time.
7. As a Smart Cascade user, I want the current session to remain the Root coordinator, so that conversation context and production authority stay in one place.
8. As a Smart Cascade user, I want Herdr to remain optional, so that the workflow can run without coupling production logic to one terminal supervisor.
9. As a Smart Cascade user, I want Autopilot to supervise rather than schedule production work, so that there is only one production coordinator.
10. As Root, I want to read the complete queue after authorization, so that I can reason about the whole dependency graph.
11. As Root, I want to compute the maximum safe ready frontier, so that every independent slice can begin without waiting for unrelated active work.
12. As Root, I want dependency readiness and observed shared mutable resources to constrain dispatch, so that parallelism remains safe.
13. As Root, I want every serialization decision to have a concrete reason, so that reduced concurrency is explainable rather than habitual.
14. As Root, I want to start one native asynchronous isolated Leader task for each ready slice, so that production implementation is delegated without external Leader panes.
15. As Root, I want each Leader business packet to carry the logical slice, attempt, base/candidate, scope, dependencies, checks, non-goals, and strict result schema, while runtime correlation/isolation/model fields remain in the selected adapter invocation, so that the core contract stays bounded and runner-neutral.
16. As Root, I want native OMP to create and own Leader isolation, so that Smart Cascade does not implement worktree lifecycle machinery.
17. As Root, I want to process whichever Leader message, blocker, or settlement arrives first, so that one slow slice does not stall independent progress.
18. As Root, I want Hub lifecycle and completion events treated as doorbells only, so that transport status cannot accidentally accept a candidate.
19. As Root, I want to validate the Leader identity, attempt lineage, settlement, authoritative retained patch, changed paths, postconditions, checks, and active-writer evidence, so that acceptance is grounded in real artifacts.
20. As Root, I want to run or reproduce the queue's final checks against an exact verification candidate, so that Leader self-report is never the final technical verdict.
21. As Root, I want `PASS` to apply and verify the accepted retained patch before commit/integration, so that production Git reflects the exact reviewed candidate.
22. As Root, I want dependency milestones recomputed immediately after accepted integration, so that newly ready slices can begin at once.
23. As Root, I want `BLOCKED` to freeze only the affected dependency chain, so that independent ready work continues.
24. As Root, I want `REWORK` to address an exact remaining checklist under stable logical identity, so that agents do not rediscover already accepted work.
25. As Root, I want a new attempt to start from an explicit base and the last verified cumulative patch, so that candidate provenance remains honest.
26. As Root, I want a failed temporary attempt with no retained patch reported as lost unmaterialized work, so that absence of an artifact is not disguised as preservation.
27. As Root, I want to request an Advisor only when bounded analysis or independent review is useful, so that review is risk-shaped rather than mandatory ceremony.
28. As Root, I want Advisor `PASS` to remain evidence rather than acceptance, so that production authority is not split.
29. As Root, I want final Git commit/integration and cleanup to remain Root-only operations, so that child roles cannot silently promote their own work.
30. As a Leader, I want to read the actual code before deciding child decomposition, so that child assignments follow real patch seams rather than preset functional categories.
31. As a Leader, I want to split independent non-overlapping patches aggressively, including patches in the same file, so that parallel implementation is not lost to speculative conflict fear.
32. As a Leader, I want to merge child scopes only after a real conflict, overlapping hunk, combined-check failure, or unresolved assembly decision, so that one failure does not collapse the whole slice into one writer.
33. As a Leader, I want to start every writing Executor through native OMP with `isolated=true`, so that each child writes only its own temporary isolation.
34. As a Leader, I want the selected profile to use automatic isolation, no automatic parent apply, and patch retention, so that parent mutation is deliberate and verifiable.
35. As a Leader, I want Hub messages to be concise plain prose with correlation labels, so that runtime communication remains readable and does not become a shadow status protocol.
36. As a Leader, I want strict structured output only at task settlement, so that completion data is machine-checkable without forcing all runtime messaging into JSON envelopes.
37. As a Leader, I want authoritative patch paths and merge details to come from native task results rather than child claims, so that a child cannot fabricate runtime-owned evidence.
38. As a Leader, I want to validate every child settlement, changed path, check, postcondition, and retained patch byte before assembly, so that unverified child output never enters the candidate.
39. As a Leader, I want to apply verified child patches serially into my isolated candidate, so that assembly has one writer and deterministic order.
40. As a Leader, I want cumulative candidate checks after assembly, so that individually valid patches cannot hide integration failures.
41. As a Leader, I want independent ready children to continue when one child blocks, so that a local failure does not halt the entire slice.
42. As a Leader, I want to issue precise child REWORK under stable logical identity, so that the next attempt handles only remaining defects.
43. As a Leader, I want child-level rework counts to survive runner, model, attempt, and session replacement, so that repeated failure cannot reset escalation history.
44. As a Leader, I want every third child REWORK to suggest an escalated semantic Executor, so that capability escalation is predictable without automatically creating an Advisor.
45. As a Leader, I want semantic and mechanical Executors to remain separate roles, so that deterministic postimage work does not receive unnecessary semantic freedom.
46. As a Leader, I want a mechanical ambiguity to become a blocker and be reassigned to a semantic Executor, so that a mechanical runner does not guess.
47. As a Leader, I want to return one strict candidate/evidence settlement to Root, so that Root can freeze and verify one bounded result.
48. As an Executor, I want one explicit child identity, attempt, base, postcondition, checks, and output schema in the core packet, while runtime correlation and isolation remain adapter concerns, so that my assignment is bounded without coupling core to OMP.
49. As an Executor, I want to write only inside native OMP isolation, so that I cannot mutate my parent candidate directly.
50. As an Executor, I want to write only inside my own isolated worktree, so that my boundary is enforced by isolation rather than by a declared path list.
51. As an Executor, I want to run focused verification proving the named acceptance goals, so that bounded child work does not turn into an unplanned full-project workflow.
52. As an Executor, I want to leave production commit and integration to Root, so that a child cannot bypass parent validation.
53. As an Executor, I want to return strict settlement evidence without claiming the runtime-owned patch path, so that responsibilities remain truthful.
54. As an Advisor, I want to review one exact frozen candidate, so that findings cannot drift across changing bytes.
55. As an Advisor, I want to remain read-only and return evidence rather than fixes, so that review and implementation authority do not collapse together.
56. As an Advisor, I want to block on candidate drift or unsafe verification, so that a clean verdict is never issued against uncertain evidence.
57. As Autopilot, I want to bootstrap and authorize Root exactly once for the approved run, so that I do not become a second slice scheduler.
58. As Autopilot, I want read-only lifecycle, progress, transcript, Git, and blocker evidence, so that I can supervise without owning production state.
59. As Autopilot, I want to intervene only on stalls, boundary violations, transport identity loss, unrecoverable runtime capability loss, or explicit external decisions, so that healthy Root operation remains autonomous.
60. As Autopilot, I want final completion to require Root decisions, accepted Git evidence, checks, cleanup dispositions, and residual blockers, so that process exit or child completion is never mistaken for delivery.
61. As a recovering Root, I want resume to rediscover an interrupted child as parked without automatically continuing it, so that no stale work resumes before I re-observe the run.
62. As a recovering Root, I want an explicit continuation message to revive the original child identity, so that recoverable context is reused instead of replaced.
63. As a recovering Root, I want revival to continue the same child session and isolation when native OMP can recover them, so that the child keeps its real context and artifact lineage.
64. As a recovering Root, I want to inspect the current candidate and task applicability before revival, so that recovery is a decision rather than an automatic side effect.
65. As a recovering Root, I want an unrecoverable child reported honestly, so that missing context is not presented as restored.
66. As a recovering Root, I want to redispatch from the last verified candidate when recovery is unavailable, so that the run can continue without a second lifecycle database.
67. As a Smart Cascade maintainer, I want only rework counts persisted in Smart Cascade state, so that persistence does not duplicate OMP lifecycle or the static queue.
68. As a Smart Cascade maintainer, I want separate Root slice counters and Leader child counters, so that each authority writes only its own minimal state.
69. As a Smart Cascade maintainer, I want state updates performed through explicit slice and child command namespaces, so that callers cannot select a state level by accidental argument count.
70. As a Smart Cascade maintainer, I want state writes to use atomic replacement, so that interruption cannot leave malformed counter files.
71. As a Smart Cascade maintainer, I want escalation actions emitted by the increment command rather than stored as durable state, so that the persisted model remains one integer.
72. As a Smart Cascade maintainer, I want role prompts and runner mappings to enforce role capability, so that no new runtime authority module is required.
73. As a Smart Cascade maintainer, I want historical plugin and borrowed-cwd investigations kept outside the active contract, so that implementation agents do not revive rejected architecture.
74. As a Smart Cascade maintainer, I want the native OMP smoke to remain disposable and production-profile independent, so that runtime behavior can be verified without risking real projects.
75. As a Smart Cascade maintainer, I want failures and cleanup outcomes to be explicit in test output, so that smoke success cannot hide leaked isolation or partial execution.

## Implementation Decisions

- The implementation source of truth remains the accepted Smart Cascade flow. This issue-style spec supplies implementation requirements and test intent but does not create a competing authority document.
- Smart Cascade is a Skill invoked in the current Agent session. Invocation performs preflight and asks for explicit run authorization; the current session becomes Root after authorization.
- Queue creation and task planning are upstream concerns. Smart Cascade consumes an existing mechanically valid static queue and does not automatically create, repair, or redesign it.
- The queue contains only stable top-level slice intent and hard boundaries. Runtime status, attempts, sessions, artifacts, candidates, decisions, and concurrency flags remain outside the queue.
- Root owns the complete production DAG and recomputes the maximum safe ready frontier after every accepted integration. Running transport state is not a global scheduling lock.
- The production topology is Root → Leader → Executor through native asynchronous OMP tasks. External Herdr Leader panes are not the routine production path.
- Every writing Root→Leader and Leader→Executor task requests native OMP isolation. The selected profile uses automatic isolation, disables automatic parent apply, and retains changes as patches.
- The selected runner adapter owns task sessions, lineage, communication, native status/settlement evidence, temporary isolation, artifact capture, cleanup, and recovery. The core owns only platform-neutral scheduling, business packets/results, candidate validation, decisions, Git integration, and dependency advancement.
- Smart Cascade owns logical slice/child labels, ordered attempts, candidate validity, patch validation, patch assembly, acceptance, REWORK, Git integration, and dependency advancement.
- Smart Cascade does not introduce a child registry, lifecycle store, tombstone store, lease, fencing token, plugin runtime, durable mailbox, or independent child state machine.
- Hub is the native runtime communication surface. Messages are plain prose and carry concise slice, attempt, and nonce labels when correlation is needed. Hub messages do not encode an authoritative business state protocol.
- Task completion uses strict structured output. Authoritative retained patch paths and merge details come from native task results, not child-authored fields.
- Public OMP evidence is deliberately layered. Lifecycle/RPC/native progress proves identity, agent source, model role/resolved model, observed task spawn call ID, and parent/child `sessionFile` lineage through lifecycle/RPC or the native transcript session tree; retained patch paths and child prose are not lineage sources. The native rendered `<task-result>` envelope proves its own status, strict-schema business settlement from `<output>`, and retained patch location from `<merge-summary>`. Retained artifact bytes plus Git prove the exact base, applicability, assembly, parent non-mutation, and deliberate apply. The public async seam is not required to expose or reconstruct OMP's internal `SingleResult` object.
- Root dispatches one Leader per safely ready slice. Leader dynamically decomposes that slice after reading the current code and dispatches bounded Executors along independent patch seams.
- Independent patches may target the same file when there is no known logical dependency and expected hunks do not overlap. Conflict evidence, not fear of conflict, causes later scope merging.
- Executors never create production commits, manipulate worktrees, apply their own patch to a parent, broaden scope, or create replacement logical identities.
- Leader validates child settlement and authoritative patch artifacts, then applies verified child patches serially in its own isolated candidate. Leader runs cumulative checks before settlement.
- Root validates the Leader settlement and retained patch. When final checks would mutate or pollute the production checkout, Root evaluates the patch against a disposable verification candidate derived from an explicit base.
- Root alone decides slice `PASS`, `REWORK`, or `BLOCKED`, applies accepted patches, performs production Git commit/integration, advances dependency milestones, and records cleanup disposition.
- Advisor is optional and read-only. Advisor output is evidence; it is not a mandatory gate and cannot replace Root acceptance.
- REWORK retains stable logical identity. A new attempt uses an explicit base and replays the last verified cumulative patch before handling only the remaining checklist.
- An attempt with no retained artifact has no claim to preserved unmaterialized bytes. The parent records the loss and restarts from the last verified candidate. A blocked or failed native job/lifecycle/provider disposition with an independently validated retained patch may be preserved as `preserved_not_candidate`: it cannot advance dependencies, be applied, or be treated as `PASS` without a later independently validated candidate. Public async evidence uses lifecycle/RPC/native progress, native rendered task envelopes, retained artifacts, and Git; it does not require or reconstruct the unexposed internal `SingleResult` fields.
- Rework persistence is intentionally minimal. One Root-owned counter file stores slice-level counts; one Leader-owned counter file per slice stores child-level counts. These entries are counters, not live topology.
- Rework counters increment atomically through explicit slice and child command namespaces. At multiples of three, the command emits an escalation suggestion without persisting an escalation state.
- Slice escalation suggests an Advisor. Child escalation first selects a stronger semantic Executor. Mechanical Executors are used only for decided deterministic postimages.
- Root recovery is two-step. Root resumes and re-observes the run first; it then explicitly continues/revives an applicable parked child. Root resume alone does not automatically continue child execution.
- If native OMP can recover the child, the original identity, session, and isolation are reused. If it cannot, Root redispatches from the last verified candidate and reports the lost context.
- Autopilot remains an optional external supervisor for bootstrap, observation, intervention, recovery, escalation, and reporting. It does not compute the ready frontier, dispatch production children, decide routine slice outcomes, or perform production Git actions.
- Herdr remains an optional Root process supervisor/transport. Smart Cascade does not launch or discover Herdr sessions as part of Skill invocation.
- Implementation should replace or retire the staged one-slice release behavior rather than layering the new Root loop on top of it.
- Existing role definitions, bootstrap materials, queue validator, Autopilot references, and native OMP smoke should be reused and reconciled instead of duplicated.
- Current historical Pi-plugin and borrowed-cwd adapter material remains investigation evidence only and must not be treated as an implementation prerequisite.

## Testing Decisions

- Tests exercise external behavior at the highest useful seam. The primary acceptance seam is a user-authorized Root run using native OMP task isolation, not a custom runtime wrapper or mocked child registry.
- The existing disposable native OMP smoke is the prior art for the runtime seam. Extend or replace it only when necessary to exercise the full production Root prompt and role definitions; keep the same disposable repository, throw-away profile, structured report, and production-profile isolation.
- The end-to-end native OMP acceptance smoke must prove Root → isolated Leader → isolated Executor; lifecycle/RPC/native progress identity and lineage; plain-prose Hub communication; strict business settlements from native rendered task envelopes; authoritative Executor and Leader retained patches from envelope merge summaries; no parent mutation before explicit apply; Leader serial assembly; Root verification; deliberate accepted apply; and native isolation cleanup.
- A dedicated real-interruption recovery smoke must prove that interrupting Root preserves the child session and isolation artifact; Root resume rediscovers the child as parked without automatic execution; explicit continuation revives the original child identity; and revival appends to the same child session and uses the same isolation rather than spawning a replacement.
- Recovery tests must distinguish recoverable and unrecoverable children. The unrecoverable path must report missing context and redispatch from the last verified candidate without claiming revival.
- Queue validation tests remain deterministic script tests. They cover required fields, stable unique IDs, dependency validity, cycles, forbidden runtime and child-topology fields, and rejection rather than automatic repair.
- Rework counter tests remain deterministic script tests. They cover explicit slice/child command namespaces, initial zero behavior, atomic increment, persistence, the third/sixth/ninth escalation cadence, non-persistence of action fields, separation of Root and Leader-owned files, and malformed-state failure.
- Bootstrap and authorization tests cover one immutable initialization receipt, one run-level authorization, exact queue/base identity, refusal to begin production during initialization, and retirement of per-slice release behavior.
- Root scheduling tests use bounded fixtures to prove maximum-safe-frontier behavior: newly ready work starts immediately after its dependencies integrate, unrelated running Leaders do not block it, slices sharing a declared mutable resource serialize, and blockers freeze only affected chains.
- Leader decomposition tests focus on observable dispatch and assembly behavior rather than internal plans. Independent child patches may be dispatched concurrently; verified patches are applied serially; actual conflicts cause only the affected child scopes to merge on REWORK.
- Core packet/result tests validate platform-neutral identity, explicit base, checks, bounded role-specific business schemas, normalized artifact bytes, and dispositions. Separate OMP adapter tests validate admitted agent provenance, model projection, observed task spawn call ID, `sessionFile` lineage, native rendered `<task-result>` status/output/merge-summary evidence, and retained patch extraction. They reject runtime fields in core packets/results, missing lineage, patch-path or prose-derived lineage, stale identity, unexpected paths, child-authored patch paths, prompt-only markers, invalid envelopes, and unverified patches.
- Candidate acceptance tests prove that lifecycle or settlement alone does not produce `PASS`; Root must verify exact bytes, paths, checks, scope, and no-active-writer evidence before apply/integration.
- Advisor tests prove read-only behavior, candidate identity gating, optional invocation, evidence-only `PASS`, and blocking on candidate drift or unsafe verification.
- Autopilot tests prove that supervision can observe and intervene without dispatching Leaders/Executors, accepting slices, writing production state, or performing Git integration.
- Cleanup tests verify outcomes rather than merely issuing cleanup commands. Temporary isolation is absent or empty after native cleanup, retained evidence remains available for parent disposition where required, and failures report leaked resources explicitly.
- Tests must include untracked files when reviewing repository scope and documentation effects.
- No test should require a Smart Cascade plugin runtime, child lifecycle database, lease/fencing mechanism, or second scheduler. A test requiring one of those indicates the implementation has crossed the approved architecture boundary.

## Out of Scope

- Creating, repairing, or semantically redesigning the static queue.
- Replacing upstream planning, ticketing, or refactor-planning workflows.
- A Smart Cascade-owned Pi plugin or host-independent child runtime.
- A duplicate child registry, lifecycle store, transcript store, tombstone store, lease, fencing token, owner epoch, durable mailbox, or parallel business state machine.
- Borrowed-cwd task injection or changes to OMP core for cwd override.
- Worktree repurpose detection or rejection of an old child after a path has been reassigned to a different owner.
- Multiple competing production owners, hostile same-user agents, multi-tenant access control, or cross-host child ownership.
- External Herdr Leader/Executor panes as the normal production topology.
- Autopilot acting as a second scheduler, per-slice releaser, routine acceptance authority, production writer, or Git integrator.
- Automatic Advisor creation or mandatory Advisor review for every slice.
- A mandatory completion webhook or Root dependency on external notification delivery.
- Model/provider/effort choices embedded in queue semantics; runner profiles own those mappings.
- Reimplementing OMP task isolation, Agent Hub, structured settlement, transcript persistence, patch retention, cleanup, or park/revive behavior.
- Rewriting historical snapshots or deleting investigation artifacts solely to make the active tree look simpler.
- Publishing this spec to an issue tracker in the current step. The repository has no configured remote or tracker target.

## Further Notes

- Repository-local triage is `ready-for-agent`. This is not a remote issue label; tracker publication remains pending until a target repository is configured.
- The accepted native OMP recovery behavior was verified on 2026-08-26 with `IsolatedCrashProbe`. Temporary test artifacts were cleaned after the smoke.
- The existing native OMP smoke already proves the core isolation, Hub, settlement, retained-patch, deliberate-apply, and cleanup path. The implementation should deepen this seam into the production Root/Leader contract rather than build parallel lower-level tests around a hypothetical runtime module.
- The current control-plane tests belong to the retired staged dispatch contract and must be migrated or replaced where they assert per-slice Autopilot release behavior.
- Historical plugin/borrowed-cwd findings remain useful for explaining rejected routes, but active implementation prompts should point to the current flow and ADR first.
- After implementation, tracker publication can copy this document into an issue and apply the real `ready-for-agent` label without changing the implementation contract.
