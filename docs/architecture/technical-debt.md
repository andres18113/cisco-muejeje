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

## TD-CAPABILITY-001 — No product provider populates control-plane capability profiles

Status:
RESOLVED

Severity:
P0

Discovered:
Runtime R2-B (capability gate, hard precondition)

Description:

`ControlPlaneApplicator` gates every typed control-plane action on
`ControlPlaneCapabilityProfile`. Nothing in `src/` ever constructs one.

Measured on `feature/runtime-ripv2` @ `dc7046c`:

- `ControlPlaneCapabilityProfile(` appears in `src/` only as the class
  definition; all 13 constructions live in `tests/`;
- the only constructor is the classmethod `.supported()`, whose own
  `evidence_source` field is the literal string `"test fixture"`;
- no `ControlPlaneCapabilityDimension` value (`ripv2_config`,
  `ospfv2_config`, `eigrp_ipv4_config`, `stp_pvst_config`, `hsrp_config`)
  appears anywhere in `src/` outside the enum that declares it, so the
  capability snapshot store holds no control-plane evidence at all;
- there is no bridge from `DeviceCapabilities`, the model the real providers
  populate, to `ControlPlaneCapabilityProfile`.

Consequently `capabilities=None`, the production default of
`ControlPlaneApplicator.apply`, resolves every dimension to UNKNOWN.

Executed against the real applicator with a valid runtime inventory and a
runtime that would have accepted every mutation:

```text
2911:ripv2_config is unknown.
status = skipped   failure_code = capability_unknown   disposition = skipped
dispatched to runtime: nothing
```

Substituting a test profile built with `.supported()` dispatches both actions,
which isolates the capability gate as the cause.

This is not specific to RIPv2 and was not introduced by R2-A: OSPFv2, EIGRP,
STP and HSRP resolve UNKNOWN on the same model. The typed control-plane
application path has only ever been exercised with test-supplied profiles.

The gate itself behaves correctly. UNKNOWN stays UNKNOWN, nothing is
dispatched, and no claim is inflated. The debt is the missing evidence path,
not the gate.

Related:
`TD-HARDWARE-001` is the same family — capability evidence not reaching its
consumer — but concerns hardware selection rather than control-plane
dimensions.

Blocks now:
Yes. `RIPV2_PRODUCT_CAPABILITY_RESOLUTION = BLOCKED` stopped Runtime R2-B at
its declared hard precondition. Every live R2-B gate is unreachable without
injecting a fake SUPPORTED capability, which R2-B explicitly forbids.

Also blocks:
any live acceptance that applies typed control-plane actions, including the
university-topology scenario.

RESOLVE_BEFORE:
the next runtime ticket, before Runtime R2-B can be retried, and necessarily
before university-topology acceptance.

Closure criterion:

A production provider resolves `ControlPlaneCapabilityProfile` for a given
model from real catalog/runtime/probe evidence, with recorded provenance and
Packet Tracer version, and the control-plane application path consumes it
without a caller-supplied fixture. UNKNOWN must remain UNKNOWN when evidence is
absent: the closure is a real evidence path, never a default of SUPPORTED.

### Resolution

Resolved: 2026-08-11, stage "Resolve TD-CAPABILITY-001".

Commit subject:
`fix: wire control-plane capability evidence into product runtime`
on `feature/runtime-ripv2`.

Implementation path:

`infrastructure/catalog/control_plane_capabilities.py` mirrors the existing
`security_capabilities.py` catalog and returns
`dict[str, ControlPlaneCapabilityProfile]`. `ControlPlaneApplicator` gained a
`capability_provider` constructor parameter defaulting to that catalog, and
`apply()` now treats `capabilities=None` as "resolve authoritative evidence"
instead of "no evidence". An explicit mapping, including `{}`, is still
honoured verbatim so tests can isolate the gate.

The precedent for a use case importing an authoritative catalog is
`compile_configuration.py`, which already imports `link_mode_capability_for`
from the same package.

Evidence mapping:

Only live evidence **attributed to a model** is encoded. The E9 live baseline
in `enterprise-control-plane.md` records STP, EtherChannel, HSRP, OSPF and
EIGRP results but names no device model, so none of them is claimed; inventing
that attribution is exactly what the mapping must not do.

- `2911` / `RIPV2_CONFIG` = SUPPORTED, from the R2-0 live qualification;
- `2911` / `ROUTING_PROCESS_STATE` = SUPPORTED, from the same live
  `show ip protocols` read-back, which demonstrates the observation channel on
  this model and build. It does not make OSPF or EIGRP observable: the runtime
  reads those with different queries and still requires its own fresh parse;
- every other dimension on every model = UNKNOWN, declared explicitly rather
  than omitted, so a new dimension must be classified instead of inheriting a
  default.

Live qualification:

One disposable 2911 on PT 9.0.1.0858, applied through the real product path
with no `capabilities` argument:

```text
2911:ripv2_config              -> supported
provenance                     -> R2-0 controlled live qualification (non-test)
action                         -> applied, failure_code none
RIP configuration dispatches   -> 1
read-back                      -> send/recv 2/2, auto-summary false,
                                  networks ['150.1.0.0'],
                                  passive ['GigabitEthernet0/0',
                                           'GigabitEthernet0/1']
typed verification             -> routing_process VERIFIED via
                                  fresh_show_ip_protocols, fresh evidence,
                                  all six compared fields verified
```

Cleanup left no probe residue.

Fail-closed behaviour is unchanged and regression-covered: an explicit empty
mapping still yields UNKNOWN, `CAPABILITY_UNKNOWN` and zero mutations, and
explicit UNSUPPORTED evidence yields `CAPABILITY_UNSUPPORTED` and zero
mutations.

### Scope closure — 2026-08-11

Two questions were left open by the resolution above and are now settled.

**Environment scope is enforced, not merely recorded.**

The first implementation stored `packet_tracer_version` on the profile as
metadata and never consulted it, so evidence qualified on any build. The gate
now applies the rule that
`capability_resolver._evidence_matches_version` already fixes for runtime and
probe evidence: reuse requires an **exact** version match.

`ControlPlaneApplicator.apply` filters resolved profiles through
`_profiles_in_environment_scope` against
`ConfigurationRuntimeContext.evidence_backend_version`, which is the existing
declared-environment mechanism and prefers the `EnvironmentFingerprint` when
one is present. No second version system was introduced.

- a profile that declares no version claims no scope and is preserved, which
  keeps caller-supplied profiles working unchanged;
- a profile that declares a version is dropped when the declared environment
  differs **or is absent**, and a dropped profile means the model has no
  profile, which the gate resolves as UNKNOWN.

Consequence for callers: the product path must now declare the environment it
is running against. The live qualification recorded above ran before this rule
existed and did not declare one; the environment was in fact `9.0.1.0858`, but
that run would today require the caller to say so. Counterfactuals for a newer
build, an older build, an undeclared environment and a malformed version are
regression-covered, and mutation checks confirm the rule is load-bearing.

**`ROUTING_PROCESS_STATE` is a device observation-channel gate.**

The contract was determined from structure and from runtime behaviour rather
than from what RIP verification needs:

- the enum splits *configuration* per protocol and mode — three STP config
  dimensions, three EtherChannel config dimensions, three routing config
  dimensions — but declares exactly **one** state dimension per family;
- both compiler branches, RIP and OSPF/EIGRP, request the same
  `ROUTING_PROCESS_STATE`, so it is protocol-independent by construction;
- narrowing by protocol or mode happens at observation time in the runtime and
  predates RIP: `mst_readback_unavailable`,
  `etherchannel_protocol_readback_unavailable`, `hsrp_role_readback_unavailable`
  and `eigrp_readback_unavailable` all narrow within a coarse state dimension.

So the dimension means "this device exposes routing-process state that a
registered query can observe", not "every routing protocol is observable". The
R2-0 live `show ip protocols` read on the qualified 2911 evidences exactly
that, and it cannot manufacture an OSPF or EIGRP claim: with the gate
SUPPORTED, an EIGRP routing-process expectation still returns UNOBSERVABLE with
`eigrp_readback_unavailable`, which is regression-covered.

`ROUTING_PROCESS_STATE` therefore stays SUPPORTED for the 2911 on evidence, not
on convenience.

---

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

## TD-RUNTIME-002 — `terminal_is_idle` is blinded by a trailing asynchronous syslog

Status:
RESOLVED

Severity:
P1

Discovered:
Runtime R2-0 (RIPv2 live replay qualification)

Description:

`terminal_is_idle` decides that a console has returned control by checking
that the rendered output ends with a prompt.

After `configureIosDevice` completes, IOS emits the asynchronous notice:

```text
Router>
%SYS-5-CONFIG_I: Configured from console by console
```

The syslog line lands **after** the prompt, so the buffer no longer ends with
one and the check returns False indefinitely. Measured during R2-0: still
False at t+35s, with the tail unchanged.

Runtime Safety R1-E already applied the equivalent correction to
`first_echo_line`, which skips recognisable `%FACILITY-severity-MNEMONIC:`
lines. `terminal_is_idle` never received that treatment.

Consequence:

`TypedPingExecutor` uses `IDLE_GUARD_JS`, whose JavaScript check has the same
shape. A typed ping issued after a configuration change on the same device can
be refused with `prompt_not_ready_command_in_flight` even though the CLI has
returned control.

Not affected:

`ControlledIosExecutor` registered queries, which use `getPrompt()` rather
than the output tail and are immune to a trailing syslog line.

Blocks now:
No. R2-0 completed by using `getPrompt()` readiness, the same signal the
hardened IOS executor already uses.

RESOLVE_BEFORE:
typed RIPv2 behavioural verification, because that step pings immediately
after configuring, and at latest E9.5 final closure.

Closure criterion:

Idle detection ignores recognisable asynchronous IOS syslog lines when
deciding whether the console returned control, in both the Python helper and
the JavaScript guard, with a deterministic regression covering a syslog line
arriving after the prompt.

### Resolution

Resolved: 2026-08-11, stage "Resolve TD-RUNTIME-002".

Commit subject:
`fix: tolerate trailing IOS syslog in idle detection`
on `feature/runtime-ripv2`.

What changed:

Both `terminal_is_idle` and `IDLE_GUARD_JS` now discard trailing lines that
match the recognisable `%FACILITY-severity-MNEMONIC:` shape before looking for
the prompt. The rule is the one `first_echo_line` already used; no second
syslog regex was introduced.

Evidence:

- deterministic regressions for prompt only, prompt plus `CONFIG_I`, prompt
  plus `LINK`, several consecutive notices, and the exact tail recorded live
  during R2-0;
- negative regressions holding the R1 guarantees: pager behind a notice,
  command in flight, arbitrary trailing text, `% Invalid input`, partial
  prompt, and syslog with no prompt behind it;
- a `TypedPingExecutor` regression proving the retry barrier is passed after a
  configuration notice;
- live confirmation on disposable `__MCP_PROBE_R2_IDLE_R1` (2911, PT
  9.0.1.0858): tail `Router>` followed by `%SYS-5-CONFIG_I`, with the Python
  helper and the in-Packet-Tracer JavaScript guard both reporting ready and no
  pager. Cleanup left no `__MCP_PROBE_R2_*` residue.

---

## TD-RUNTIME-003 — RIPv2 read-back is qualified against one live output shape

Status:
RESOLVED

Severity:
P2

Discovered:
Runtime R2-A (typed RIPv2 implementation)

Description:

`parse_show_ip_protocols_rip` and the RIPv2 configuration verification are
validated against the exact `show ip protocols` output captured during R2-0:
one router, one routing protocol, no IPv4-addressed RIP interface, and no
pagination.

Two shapes are implemented and unit-tested but never observed live in Packet
Tracer:

1. a device running RIP alongside another routing protocol, where
   `show ip protocols` emits several `Routing Protocol is "..."` blocks and the
   RIP block must be read in isolation;
2. a `show ip protocols` long enough to trigger the IOS pager.

Current containment:

- the parser scopes the RIP block between `Routing Protocol is` headers, so a
  neighbouring block cannot contribute networks, passive interfaces, or the
  auto-summary flag;
- a read-back flagged `truncated_by_pager` is reported UNOBSERVABLE rather than
  FAILED, so a hidden line cannot be mistaken for a missing network statement;
- both behaviours are covered by deterministic regressions and by mutation
  checks that fail when either guard is removed.

Blocks now:
No. The offline typed implementation and its verification do not depend on
either shape, and neither shape can silently produce a false VERIFIED.

RESOLVE_BEFORE:
R2-B live behavioural verification, and at latest E9.5 final closure.

Closure criterion:

Observe both shapes on a disposable Packet Tracer device and confirm that the
parser reads the RIP block correctly beside another protocol, and that a
paginated read-back is reported UNOBSERVABLE rather than FAILED. Then either
promote the fixture to live-captured evidence or correct the parser.

### Deadline status — 2026-08-11

The deadline is **active but not yet violated**, and the milestone is
unchanged.

The RESOLVE_BEFORE milestone is R2-B *completion*. R2-B did not complete: it
stopped at its hard precondition, because the product capability gate resolved
`2911:ripv2_config` to UNKNOWN and skipped every typed RIPv2 action
(`TD-CAPABILITY-001`, since resolved). R2-B therefore never reached a live
stage, and its own rules forbade both bypassing the gate with raw IOS and
injecting a fake capability.

The two output shapes were not qualified live. Neither a live result nor
NOT_REPRODUCED is claimed for them: no probe was run.

This debt MUST be resolved when R2-B resumes.

### Resolution

Resolved: 2026-08-11, stage "R2-B phase 3 — live read-back qualification".

Commit subject:
`test: qualify RIPv2 protocol readback shapes live`
on `feature/runtime-ripv2`.

Environment: PT `9.0.1.0858`, declared through
`ConfigurationRuntimeContext.evidence_backend_version` so the capability
evidence applied. RIP was applied through the real product path
(`ControlPlaneApplicator` → typed renderer → `configureIosDevice`), one
deliberate dispatch. Disposable devices only, named `MCP-PROBE-R2B-*` per the
naming contract in `TD-RUNTIME-004`.

**Shape 2 — paginated read-back: reproduced, fail-closed confirmed.**

Adding any second routing process makes `show ip protocols` exceed the pager
window on this build. The production read-back reported:

```text
truncated_by_pager = True
verification       = UNOBSERVABLE, evidence rip_readback_truncated
fresh_evidence     = False
```

Not a false VERIFIED, and not a false FAILED from the cut-off fields. This is
the contract the debt required.

**Shape 1 — RIP beside another protocol: qualified against a real capture.**

Three measured properties of PT 9.0.1.0858 constrain how this shape can be
observed at all, and each was established by a failed attempt rather than
assumed:

- the EIGRP block alone fills the ~24-line pager window;
- protocol blocks print with EIGRP before RIP, so RIP falls outside that
  window;
- `terminal length 0` dispatches successfully on the command line and Packet
  Tracer **ignores it**; a static route produces no second protocol block.

So a single production read can never expose the RIP block while a second
protocol exists on this build — which is exactly Shape 2, already fail-closed.
The full output was therefore reconstructed by walking the pager, and the
production parser was qualified against that real capture:

```text
protocol blocks : ['Routing Protocol is "eigrp  100 "',
                   'Routing Protocol is "rip"']
parsed RIP      : version 2/2, auto-summary false,
                  networks ['150.1.0.0'],
                  passive ['GigabitEthernet0/0']
```

The EIGRP block carried its own `Routing for Networks: 10.0.0.0` and
`Passive Interface(s): GigabitEthernet0/1`, printed before RIP. Neither leaked:
ten leakage checks passed, including exact network and passive-interface sets.

The capture is persisted as
`_PT_9_0_1_0858_SHOW_IP_PROTOCOLS_EIGRP_THEN_RIP` in
`tests/test_typed_ripv2_control_plane.py`, replacing the synthetic two-protocol
fixture with live evidence. It also pins that one real output carries both
indentation styles: EIGRP with spaces, RIP with TAB.

No source changed. The parser needed no correction.

Residual limit, recorded rather than glossed: on this build a device running
RIP alongside another routing protocol is **UNOBSERVABLE** through the product
read-back, because the pager truncates before RIP is reachable and cannot be
disabled. That is safe — it never yields a wrong answer — but it is a real
observability ceiling for multi-protocol devices, and a future stage that needs
RIP state on such a device will have to page through or find another query.

---

## TD-RUNTIME-004 — The typed renderer rejects the project's probe naming convention

Status:
RESOLVED

Severity:
P2

Discovered:
Resolve TD-CAPABILITY-001 (live qualification)

Description:

Every controlled probe in this project is named `__MCP_PROBE_*`, and the
standing safety rule is that only resources with that prefix may be created and
deleted.

> **Correction, added at resolution.** The second clause was never true of the
> code: no production path has ever selected devices by prefix, and deletion is
> by exact caller-supplied name. The original wording is preserved above because
> it is what this debt was opened against.

The trusted control-plane renderer validates device names with
`_SAFE_DEVICE = ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`, which requires an
alphanumeric first character. Measured directly:

```text
__MCP_PROBE_CAP_R1   -> rejected: Invalid compiled device name
MCP-PROBE-CAP-R1     -> accepted
```

A typed control-plane action therefore cannot be rendered for a device that
follows the project's own probe convention. Earlier live stages never hit this
because R2-0 dispatched through `configure_ios` rather than the typed renderer.

Current containment:

The TD-CAPABILITY-001 live qualification used `MCP-PROBE-CAP-R1`, which is
still unmistakably a probe and was the only device created or deleted. The
safety intent — never touch user topology, delete only what was created — was
fully preserved, and cleanup left no residue.

Blocks now:
No. It did not block the live qualification.

Blocks:
any future live control-plane probe that expects the `__MCP_PROBE_*` prefix to
work end to end through the typed path, which includes R2-B as its ticket is
currently written.

RESOLVE_BEFORE:
R2-B resumption.

Closure criterion:

Reconcile the two rules deliberately: either the probe convention adopts a
prefix the renderer accepts and the standing safety rule is restated, or
`_SAFE_DEVICE` is widened with an explicit justification that it still rejects
the injection-shaped names it was written to reject. Whichever is chosen, a
regression must pin it.

### Resolution

Resolved: 2026-08-11, stage "TD-RUNTIME-004 scoped probe naming contract".

Commit subject:
`fix: define renderer-safe typed probe naming`
on `feature/runtime-ripv2`.

**The resolution is a scoped naming-contract clarification, not a renderer
relaxation.** `_SAFE_DEVICE` is byte-for-byte unchanged, and a regression pins
both that fact and the continued rejection of `__MCP_PROBE_CAP_R1` through the
typed path.

What the audit established:

- no production code anywhere selects devices by either prefix; deletion is by
  exact caller-supplied name and is idempotent on absence, so cleanup
  correctness needs a unique remembered name, never a prefix;
- isolation is proven by whole-workspace inventory fingerprint diff, in which
  names are opaque values. There is no probe-versus-user discrimination step:
  the session deletes exactly the names it created and requires the workspace
  fingerprint to converge back. The one model-based rule, `_BACKEND_MANAGED_MODELS`,
  excludes a backend-created Power Distribution Device from the fingerprint so
  restoration stays decidable; it is not a probe classifier;
- the two prefixes therefore serve human and QA recognition, not enforcement;
- the conflict was never two rules governing the same objects. Capability
  discovery probes are created through `lwAddDevice` and observed with
  registered queries, and never reach the typed renderer. A probe that must be
  rendered by a trusted renderer is a newer population that neither rule
  anticipated.

The contract now declared:

| Prefix | Created by | Traverses trusted renderers |
| --- | --- | --- |
| `__MCP_PROBE_*` | capability discovery | No |
| `MCP-PROBE-*` | disposable probes on a typed path | Yes |

Recorded in `e95-stabilization.md`, which previously claimed a single universal
namespace, and in `docs/qa/capability-probes.md`, whose residue check now
covers both.

Not changed, deliberately: the `capability_discovery.py` generator, its
`__MCP_PROBE_*` output, `_SAFE_DEVICE`, the `__MCP_E4_TEST_*` test namespace,
and every historical run record.

Evidence:

- capability discovery still emits `__MCP_PROBE_*`, proven by running the real
  use case and reading the names the runtime was asked to create;
- `MCP-PROBE-*` is accepted by both the typed control-plane renderer and the
  fault renderer. This is renderer-level only: the regressions call
  `render_action` and `render_scenario` and inspect the returned payloads.
  Nothing is dispatched and Packet Tracer is not involved;
- ten hostile shapes still reject — newline, leading and trailing space,
  carriage return, semicolon, quote, leading hyphen, leading dot, empty, and
  over-length;
- deletion is exact-name for four unrelated name shapes, with no prefix scan in
  the emitted script;
- five mutations were run against these regressions during this stage —
  widening `_SAFE_DEVICE`, renaming the discovery generator, switching deletion
  to a prefix scan, and reverting each of the two documents — and all five
  failed the suite. The prefix-scan mutation is caught by the emitted-script
  assertions, which reject `startsWith` and `indexOf` in the deletion script.

Known limits of this closure, recorded rather than glossed:

- `MCP-PROBE-*` has no producer in `src/`. Nothing in production emits or
  requires it, because a typed-path probe is created by an operator harness,
  not by the product. The contract is a declared convention with a regression
  that pins renderer compatibility, not an enforced invariant;
- two scoped statements naming only `__MCP_PROBE_*` remain outside the two
  edited documents, and both are still literally true of capability discovery:
  the `pt_probe_capabilities` docstring in `tool_registry.py` and
  `packet-tracer-capability-discovery.md`. Neither is covered by a regression.

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

- **TD-RUNTIME-003** — resolved 2026-08-11. Both remaining read-back shapes now
  have live evidence on PT 9.0.1.0858. A paginated `show ip protocols` is
  reported UNOBSERVABLE via `rip_readback_truncated`, never a false VERIFIED or
  FAILED. The two-protocol shape was captured live by walking the pager and the
  production parser reads only the RIP block from it, excluding the EIGRP
  block's own networks and passive interfaces; that capture replaces the
  synthetic fixture. No source changed. The entry above is kept in full and
  records the residual observability ceiling. The prior "deadline status" note
  remains as written.
- **TD-RUNTIME-004** — resolved 2026-08-11. Two disposable namespaces are now
  declared explicitly: `__MCP_PROBE_*` for capability discovery, which never
  reaches a trusted renderer, and `MCP-PROBE-*` for probes that do. The
  resolution is a naming-contract clarification, not a renderer relaxation:
  `_SAFE_DEVICE` is unchanged and still refuses the discovery prefix through
  the typed path. Cleanup remains exact-name and prefix-independent. The entry
  above is kept in full.
- **TD-CAPABILITY-001** — resolved 2026-08-11. A control-plane capability
  catalog now derives `ControlPlaneCapabilityProfile` from live evidence
  attributed to a model, and `ControlPlaneApplicator` resolves it by default
  instead of treating an absent argument as "no evidence". Only RIPv2
  configuration and routing-process state on the 2911 carry live evidence;
  every other dimension is explicitly UNKNOWN. Confirmed by one disposable live
  qualification with a single deliberate dispatch and a verified read-back. The
  entry above is kept in full.
- **TD-RUNTIME-002** — resolved 2026-08-11. Idle detection now discards
  trailing recognisable IOS syslog lines before looking for the prompt, in both
  the Python helper and the in-Packet-Tracer JavaScript guard, reusing the rule
  `first_echo_line` already applied. Confirmed by deterministic regressions and
  by one live disposable reproduction. The entry above is kept in full.
