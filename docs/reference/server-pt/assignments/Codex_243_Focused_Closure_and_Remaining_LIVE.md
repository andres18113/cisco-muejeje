# Close the amendment's four boundaries, then execute its remaining scopes

Repository: `andres18113/cisco-muejeje`
Reviewed candidate: `243ddc8ba12a89f3a7132adca4abb74ff40e5064`
Reviewed tree: `f16efe87c8d22209be0f0359179fa8e434b97f5c`
Branch: `feature/server-pt-s3-dhcp`; governed sibling checkout: `Cisco-MCP-s3`.
Review disposition: **REQUIRES_CHANGES**, not acceptance of the candidate.

This is a focused review addendum to
`SERVER-PT-D02-Q3-Q1-AUTOFIX-01-AMENDMENT-01`. It completes existing requirements;
it does not start a new campaign or reset its counters. Deliver one combined
code-and-evidence handoff. Do not return for approval of routine implementation,
testing, publication, process launch or other steps already delegated below.

## 1. Authority, goal and boundaries

Read the active checkout's AGENTS.md and engineering standard, its maintained
Server-PT brief, and the archived `Codex_Continuation_A1_Q3_Q1_S1b.md`. Read the
stable contracts and affected symbols as needed, not the whole historical corpus.
Confirm checkout, full HEAD/tree, ancestry and authoritative main. The reviewed
CI resolved main to `6263344e31ba3b0de6539d652f2cd06fc73a3562`; re-resolve it.
Preserve unrelated edits and every other worktree. Use the checkout's own venv.

Goal: preserve the delivered coexistence/readiness/shared-content design, finish
its integration and uncertainty boundaries, then obtain the remaining native
observations. No alternate service subsystem, scheduler framework, transport,
protocol, .pts, public capability override, event framework or main merge.

Keep the exact measured vendor-default policy; no deletion, rename, reset or
rewrite of that pool. Keep M-DHCP-3 omitted and product event paths gated. Keep
HTTP/HTTPS shared-content conflict rejection, HTTPS-only operation without an
HTTP enable, no secret-bearing file transport and all capability limits.

Update the current brief with a proportional delta BEFORE behavior edits.
Separate the runner corrections from S1b integration in reviewable commits.
No new general architecture investigation or separate ceremonial acceptance docs.

## 2. F1 — shared-content ownership must survive service admission

Evidence at the reviewed SHA:
- `service_compiler.py::_bind_shared_web_content` merges the content action under
  HTTP when present and unions the enables of every sharing service.
- `apply_enterprise_services.py::_service_eligibility` and `_plan_for` still group
  and filter actions by their single `service_id` only.
- The real default catalog can exclude optional HTTPS while retaining HTTP.

Consequences: retaining HTTP leaves its shared content action dependent on a
removed HTTPS enable. Retaining only HTTPS can remove the shared writer itself.
The existing optional-service test compiles an unrelated NTP service; it does
not exercise the admitted execution projection of these cases.

Correct the shared-resource ownership and dependencies through the actual
admission/projection/application path. A resource shared by two requested
protocols does not require the excluded protocol's listener to be enabled.
Select an admissible writer for the admitted services, or refuse a genuinely
unavailable required operation before effects. Do not drop missing dependencies
blindly, authorize by provenance metadata, duplicate page writes, silently
promote capabilities or report content applied without its writer.

Keep plan/source/selected-execution identity explicit. Preserve conflict rules
for incompatible stated contents; no last-writer-wins. Preserve the HTTP-only
compatibility contract and retained-result provenance. Do not expand support to
arbitrary page creation or unmeasured backends.

Acceptance through real composition, product use case, applicators and store:
- required HTTP + optional capability-unknown HTTPS: HTTP remains executable,
  optional HTTPS remains reported, no dangling dependencies and one page write;
- eligible HTTPS with excluded optional HTTP: an admissible HTTPS writer or an
  honest pre-effect capability refusal, never a silently missing writer;
- both eligible and equal content: one writer, both markers represented;
- conflicting content: zero E5/E6 effects;
- HTTPS-only: no HTTP listener enable;
- unknown shared-writer operation: cannot be bypassed by another service's key;
- per-service outcomes, retained rows and serialization preserve the binding.

## 3. F2 — readiness must be timely and precede the activation it protects

`_await_readiness` checks elapsed time before `read()`, but the probe uses its
fixed 10-second timeout. It accepts a ready sample before checking elapsed time
again. With three 10-second reads and two 2-second waits it accepts at 34 seconds,
although the local deadline is 30. Stage reserve protection is not a substitute
for this narrower deadline.

Also `_run_q3` currently performs E5's SetEndpointDhcp and server setup before
its readiness gate in Q3_DHCP. The amendment required readiness before client
activation, not merely before the later explicit AcquireDhcpLease call. Do not
assert that setDhcpFlag automatically sends a particular packet: its placement
is the contract issue regardless of that unmeasured side effect.

Keep one reusable gate. Cap each dispatched read by the minimum of its normal
timeout, local remaining deadline and the stage allowance outside reserve.
Record late observations but do not let them authorize effects after expiry.
Check readiness before the first DHCP-client activation it is intended to
protect. Reuse a valid sample only while the relevant topology/state remains
unchanged; no hidden extra polling. If a native prerequisite makes that ordering
impossible, report the specific contract conflict instead of fabricating ready.

Acceptance with the real coordinator and injected clock/transport:
- initially ready, delayed ready within deadline, persistent down;
- a read beginning shortly before deadline and completing afterward grants no
  permission, and receives an appropriately reduced timeout;
- <=4 reads, <=30-second gate, no reserve borrowing and no unconditional sleep;
- not-ready Q3 causes zero SetEndpointDhcp/client-activation and dhcpRun calls;
- no Q1 background client is created before readiness;
- readiness failure remains distinct from service failure and cleanup proceeds.

## 4. F3 — later default snapshots must be valid observations too

Initial baseline admission is strict; `default_pool_snapshot` is not. It trusts
`reading.observed`, silently drops non-mapping rows, ignores the source error,
truncation and count, and `default_pool_differences` collapses duplicate names
into dict entries. An error after reading the default, a duplicate row or a
truncated inventory can consequently look unchanged.

Validate each post-setup/pre-cleanup snapshot before deriving preservation:
exact subject/interface, coherent found/process facts, error category, bounded
complete inventory, count/cardinality, unique names and typed pool fields.
Account for the intended newly-created pool without treating it as a mutation
of the pre-existing default. Preserve the raw bounded reading and its original
cause. A valid positive prefix may remain observed, but it cannot establish
complete preservation when the rest is unknown.

Do not confuse an unobserved comparison with a proved changed default. Both
withdraw permission for subsequent experimental effects, with different causes.
Retain the final snapshot even after a stop when its read is permitted within
the protected finalization allowance. No extra mutation or pool normalization.

Acceptance: complete equal control, actual changed field, extra/duplicate pool,
wrong subject, count mismatch, malformed row/field, truncated inventory and
error after a valid prefix. Verify original evidence survives persistence,
unknown does not become unchanged, and no later effect occurs when preservation
cannot be established. Preserve the legacy archive bytes.

## 5. F4 — classify the complete execution result; do not replay setup setters

Two points in the current Q3 path need one coherent closure:

A. `_q3_service_result_cause` examines only actions with `attempted is True`.
A legitimate unresolved transport result with `attempted=None` and
ACCEPTANCE_UNKNOWN/NOT_OBSERVED passes that check if there is no contradictory
verification. It can authorize the same-claim guard control. The E5 helper also
uses a partial raw-field test and set membership rather than accounting for the
full decided result and exact result multiplicity.

Use the existing validated mutation decisions/snapshots, classified statuses,
identity and effect-uncertainty semantics for the whole governed result before
any next effect. Do not reconstruct input facts from output status or write a
second decision table. Keep legitimate legacy rows and endpoint PARTIAL with
sufficient exact core evidence; missing/duplicate results, unresolved effect,
real runtime exceptions and contradictory readbacks must not grant permission.

B. Q3_SETUP calls `service_runtime.apply_actions(server_actions)`, then Q3_DHCP
passes the full service plan to `ServiceApplicator.apply`. The wrapper delegates
and that applicator initializes an empty result set: the server setters are
scheduled again. This contradicts amendment section 4C, not merely an aesthetic
preference about the pipeline.

Execute each setup mutation once in the governed flow. Use a real staged product
application/retained-result contract, or a minimal explicit exact-identity reuse
boundary if the existing API does not offer one. Retention must preserve the
original typed input/results and mark actual calls honestly; it must not create
fabricated VERIFIED/ACCEPTED observations or conceal a native redispatch.
Read-only verification may remain fresh. Do not replace the product runtime
with copied qualification setters. Keep current public interfaces unchanged.

Acceptance over the real applicator/coordinator:
- a runtime losing acknowledgement before it can report attempted=True blocks
  the guard and subsequent effects, while bounded evidence/cleanup continues;
- missing/duplicate governed results and contradictory verification stop;
- validate actual native setter call counts across setup plus product phase;
- the same-claim negative control runs only after its prerequisite is established;
- persistence and journal retain original rows and the uncertainty after roundtrip;
- revised budget arithmetic counts actual reads/writes, never cached rows as calls.

## 6. Verification and scope containment

The accompanying audit_fragments.py contains transcribed countermodels, NOT
repository tests or complete product executions. Convert the cases to causal
regressions on the real code. Do not copy those algorithms as your oracle.
RED where applicable -> causal fix -> focused -> affected/coexistence -> full
suite -> namespace/docs/whitespace -> commit -> clean exact-SHA delivery gate
-> fast-forward feature publication -> exact-successor-SHA CI. No force push.

Do not run `ruff check --fix src` or format whole directories. Enumerate the
explicit touched paths first. Apply formatting/lint only to those files and
review their diff. A clean tree and a count of gated files do not independently
prove that an accidental mass edit was perfectly restored; check the actual
candidate delta and protected-path identities. No new global policy needed.

Before LIVE, update the concise record with the four closures, test evidence,
SHA/tree and recalculated worst-case budgets. No further implementation-plan
approval is required inside this contract. If an actual material change is
needed, stop and identify it; do not reduce observability or safety to proceed.

## 7. Existing remaining LIVE scopes and lifecycle permission

The absence of a running Packet Tracer process is NOT a missing authorization.
After section 6 is satisfied, you are already permitted to launch the installed
reviewed Packet Tracer into a dedicated empty workspace. Do not return merely
asking the user to open it. Establish the correct executable and process/session
identity using the existing approved lifecycle procedure. An actual interactive
login/license/permission obstruction or an unidentifiable foreign document is
an external blocker; record that specific obstacle rather than guessing.

Use the existing campaign and amendment identity, append this review addendum's
hash and materialize immutable authorizations with the new full SHA/tree:

| Scope | Remaining ordinal | Channel/build | Maximum |
|---|---|---|---|
| Q3 amended coexistence/readiness | 3 of 3 | file / 9.0.1.0858 | one invocation, 60 ops /1200 s; reserve >=11 ops /180 s |
| Q1 amended readiness | 2 of 2 | file / 9.0.1.0858 | one invocation, 60 ops /600 s; reserve >=10 ops /120 s |

All actual engine work, readiness polling and finalization are charged. Keep
M-DHCP-3 and the existing DNS omissions. No Q0, Q2, Q1b, pool removal,
dhcpRelease, claim reset/deletion, capability promotion or main merge.

No counter resets or extra LIVE retries. New process/session/nonce per stage;
no old request re-execution. A correct terminal INCONCLUSIVE is legitimate, not
an autofix target to turn into SUPPORTED. Preserve originals and append ledger
records; never relabel old cleanup or attribute old runs to the new SHA.

You may gracefully close/reopen the positively identified disposable process.
A missing process may be created; this is part of the delegated preparation.
Force termination is limited to the proven owned hung disposable process under
the original safeguards. No wildcard kill, foreign mailbox deletion or discard
of an unknown/unsaved user topology. Verify PID, creation time, executable and
old consumer exit. Heartbeat is liveness, not exclusivity proof by itself.
Q1 may follow a stopped Q3 only when its artifacts are secured and the shared
isolation/safety condition is cleared in a fresh instance.

## 8. One final handoff

Return one READY_FOR_REVIEW package with the successor SHA/tree and exact CI,
brief F1..F4 closures, actual native call-count tests, both attempt identities,
original records/stdout/stderr/exit codes/manifests, ledger extension, default
snapshots, readiness timing and typed causes. State separately offline support,
observed LIVE outcomes, remaining unknowns and non-executed work. Include one
small table, not another history dump. Self-review is not independent acceptance.
