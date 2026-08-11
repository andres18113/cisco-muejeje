# Technical Debt Ledger

This document tracks confirmed technical debt and contained backend
limitations that remain relevant to the MCP-Packet-Tracer architecture.

It is not a generic TODO list.

Every OPEN debt item must have:

- an identifier;
- severity;
- current status;
- evidence/reason;
- what it blocks;
- a mandatory RESOLVE_BEFORE milestone;
- an explicit closure criterion.

A debt item may be deferred only when it does not invalidate a correctness
gate required by the current milestone.

"Backlog someday" is not an acceptable disposition.

## Severity

### P0

Current correctness/safety blocker.

P0 debt must be resolved before continuing the affected milestone.

### P1

Correctness, evidence, runtime, or architectural debt that can be temporarily
contained but must be resolved before its declared milestone.

### P2

Non-critical contained debt with a mandatory future resolution milestone.

### BACKEND_LIMITATION

A limitation caused by Packet Tracer or the deployed bridge/backend that may
not be removable with the currently available primitives.

Closure does not necessarily require eliminating the limitation.

It requires:

- accurate classification;
- safe containment;
- no false claims;
- an explicit architectural boundary.

## Status

- OPEN
- CONTAINED
- BACKEND_LIMITATION
- RESOLVED
- DEFERRED_TO_DECLARED_MILESTONE

## Debt policy

When new debt is discovered:

1. Determine whether it invalidates a correctness gate of the current task.
2. If yes, it blocks the task.
3. If no, record it with a mandatory resolution milestone.
4. Do not expand the current task solely because unrelated debt exists.
5. Revisit debts at the mandatory checkpoints defined below.

A debt item must never lose its RESOLVE_BEFORE milestone merely because later
work is more interesting.

---

# Mandatory Debt Checkpoints

## DEBT CHECKPOINT 1

When:

After typed RIPv2 is implemented and verified.

Purpose:

Review runtime, transport, routing, evidence, and control-plane debt before
the university topology becomes an acceptance scenario.

## DEBT CHECKPOINT 2

When:

After the university topology passes its routing/failure/recovery acceptance
scenario and before returning to E9.5 Stage 3A4.

Purpose:

Resolve or deliberately reschedule newly exposed runtime/control-plane debt.

## DEBT CHECKPOINT 3 — HARD

When:

Before declaring E9.5 CLOSED.

Requirements:

- P0 open debt: 0
- P1 correctness/evidence debt that affects E9.5 claims: 0
- UNKNOWN states that invalidate final E9.5 claims: 0
- debt that blocks E10: 0

A backend limitation may remain only when its containment and claim ceiling
are explicit.

---

# Open Debt

## TD-RUNTIME-001 — Post-cleanup result DirtyState may be stale

Status:
OPEN

Severity:
P1

Discovered:
Runtime Safety R1 final closure

Description:

`execution_journal.cleanup_status` can become `CompensationStatus.SUCCEEDED`
while a previously materialized execution result still carries
`DirtyState.UNKNOWN`.

The result appears to preserve a snapshot taken before the later cleanup
transition.

Current impact:

Does not affect:

- command dispatch integrity;
- RIPv2 replay qualification;
- initial typed RIPv2 implementation.

It may affect later consumers that reason about final post-cleanup state,
especially Acceptance, Diagnosis, Compensation, or Autofix.

Blocks now:
No.

RESOLVE_BEFORE:
Acceptance/Diagnosis/Autofix work and, at latest, E9.5 final closure.

Closure criterion:

Determine explicitly whether `result.dirty_state` is intended to represent:

1. historical state at result materialization time; or
2. final journal state after cleanup.

Then make implementation, naming, documentation, and tests consistent with
that contract.

---

## TD-HARDWARE-001 — Capability-to-hardware reconciliation remains partial

Status:
OPEN

Severity:
P1

Discovered:
E9.5 Stage 3A3-E

Description:

Runtime capability evidence does not yet fully drive hardware selection.

Known example:

- ProbeCapabilityProvider can make 3560 multilayer capability SUPPORTED;
- 3650 has multilayer runtime evidence but current capability-to-selector
  mapping does not fully reconcile it into dynamic hardware selection.

The pinned E9.5 regression reference remains valid and does not depend on
dynamic selection.

Blocks now:
No for the pinned reference topology.

Blocks claims of:
fully dynamic capability-driven hardware selection.

RESOLVE_BEFORE:
E9.5 final closure.

Closure criterion:

Capability evidence used by the enterprise resolver must reconcile
deterministically into eligible physical hardware without model-string
special casing, while UNKNOWN remains UNKNOWN.

---

## TD-TRANSPORT-001 — FileBridge does not provide exactly-once or at-most-once execution

Status:
BACKEND_LIMITATION

Severity:
BACKEND_LIMITATION

Discovered:
Runtime Safety R1-B through R1-F

Description:

The deployed Script Engine protocol can re-evaluate a request when:

- the request was evaluated;
- a response was written;
- deletion of the request file fails;
- the request remains discoverable on later bridge ticks.

The current deployed `.pts` does not expose a claim marker or transactional
request lifecycle sufficient to prove exactly-once or at-most-once
execution.

Current containment:

- no false cancellation claims;
- no blind retry for ambiguous operations;
- typed product paths require verification/readback where applicable;
- replay-sensitive operation families are classified separately;
- raw paths do not satisfy typed mutation contracts.

Blocks now:
No for RIPv2 qualification, provided RIPv2 proves replay-safe under the
current transport and follows its predeclared no-blind-retry/readback
contract.

RESOLVE_BEFORE:
E9.5 final closure.

Closure criterion:

Either:

A. backend protocol gains stronger execution semantics;

or

B. the limitation remains explicitly classified and every E9.5 product
mutation family is safely contained with no claim stronger than the
available evidence.

---

## TD-SECURITY-001 — ACL/NAT replay safety is not proven

Status:
OPEN

Severity:
P1

Discovered:
Runtime Safety R1-E

Description:

Numbered ACL generation is structurally additive:

`access-list N permit/deny ...`

The normal ACL generator does not automatically prepend:

`no access-list N`

The reset exists in a separate removal path.

This establishes:

- STRUCTURALLY_ADDITIVE
- REPLAY_SAFETY_NOT_PROVEN
- TREAT_AS_REPLAY_UNSAFE_FOR_PRODUCT_SAFETY

It does NOT establish that Packet Tracer definitely stores duplicate ACEs;
that behavior has not been measured live.

NAT paths that depend on those ACL bodies inherit the same conservative
classification.

Blocks now:
No for RIPv2.

RESOLVE_BEFORE:
next security/NAT mutation hardening work and, at latest, E9.5 final closure.

Closure criterion:

Controlled disposable PT reproduction of repeated identical ACL/NAT
application, followed by direct readback and behavioral verification.

Then classify the operation family from evidence.

---

## TD-VOICE-001 — `create cnf-files` replay behavior is unknown

Status:
OPEN

Severity:
P2

Discovered:
Runtime Safety R1-E

Description:

The typed voice path contains:

`telephony-service create cnf-files`

This is an imperative operation whose behavior under duplicate execution has
not been measured.

Current classification:
UNKNOWN.

Blocks now:
No for RIPv2.

RESOLVE_BEFORE:
next voice hardening/acceptance pass and, at latest, E9.5 final closure.

Closure criterion:

Controlled disposable voice runtime probe determines whether repeated
execution is:

- replay-safe;
- produces additional side effects;
- or remains unobservable.

Update the product containment rule accordingly.

---

## TD-PUBLIC-001 — Raw fire-and-forget tool remains publicly invokable

Status:
DEFERRED_TO_DECLARED_MILESTONE

Severity:
P2

Discovered:
Runtime Safety R1-D/R1-E

Description:

`pt_send_raw(wait_result=False)` remains publicly invokable.

It is proven to be separate from:

- RuntimeActionMutation;
- typed `configure_ios`;
- ActionExecutionStatus;
- normal typed enterprise mutation contracts.

Therefore it cannot masquerade as a successful typed enterprise mutation.

However, its public exposure is not yet governed by the future reduced
enterprise MCP surface.

Blocks now:
No.

RESOLVE_BEFORE:
Skills/public MCP facade phase.

Closure criterion:

Public-surface governance explicitly limits arbitrary raw IOS/JS to the
controlled developer/capability-investigation boundary and prevents it from
being treated as a normal enterprise operation.

---

# Planned Work That Is Not Technical Debt

The following are planned capabilities and must not be mislabeled as debt:

- typed RIPv2 support;
- typed PC tracert/traceroute support if later scheduled;
- Stage 3A4;
- future AcceptanceEngine;
- future Diagnosis/Autofix;
- future reduced public enterprise MCP facade.

Missing planned functionality is not automatically technical debt.

---

# Resolution Log

Move an item here only when its closure criterion has been satisfied.

Do not delete historical debt entries.
