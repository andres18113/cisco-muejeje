# Server-PT continuation A1: observed default-pool coexistence, readiness and S1b

## Assignment and authority

Continue in `Cisco-MCP-s3`, branch `feature/server-pt-s3-dhcp`, from
`c0307ca4b9a44fc8513812207e89bb89469ca595`, tree
`407760ff64900de0c42fd4da0b9812ab33292c92`. Preserve the worktree and its own
`.venv`. Re-resolve the published branch and authoritative `cisco/main`; stop
on unexpected divergence or another writer, never overwrite their work.
Read this checkout's `AGENTS.md` and `docs/engineering/standards.md`.

Deliver one integrated package: implement the decisions below, verify them,
then use only the remaining two campaign slots. Do not return another general
plan or request permission for routine in-scope steps. Risk remains L. Record
a proportional design delta before behavior changes and return
`READY_FOR_REVIEW`, never self-approval.

This is amendment `SERVER-PT-D02-Q3-Q1-AUTOFIX-01-AMENDMENT-01`. When supplied by
the operator as the assignment, it authorizes these specific contract changes,
S1b offline, fast-forward publication of this feature branch for exact-SHA CI,
and the bounded successor attempts in section 7. It does not authorize new
attempts outside the original totals, retrospective approval or automatic
capability promotion. The original campaign and work order stay immutable.

## 1. Evidence already accepted within its scope

Input ZIP: `SERVER-PT-D02-Q3-Q1-AUTOFIX-01.zip`, 127800 bytes, SHA-256
`1b71018ac383db84fa3ba64e58fa5a020e180e0d0b0d37cd2120e5d4e75dfa2f`.
Its 80 files total 318993 bytes; 62 manifest checks and all three ledger links
were independently validated. The original Windows before/after filesystem
snapshot was not available to the reviewer; do not imply it was reproduced.

| Record | Exact hash / accepted scope |
|---|---|
| Q3 ordinal 1, `71fc1aa`, run `2026-09-19T21-55-45Z-1efec675` | `c3aa5707a2d864cf9ab2ab3658e99788fad81f04c6657d448032a6119a4166a6`; process binding absent, stage stopped |
| Q3 ordinal 2, `c0307ca`, run `2026-09-19T22-52-28Z-6d12894c` | `b303bd9dea2749c763ec53bac72b6f737cc695ed499da84b8ea965937f38d79b`; `DhcpServerMain` resolves; disabled process plus native pool observed; no product setters or acquisition |
| Q1 ordinal 1, `c0307ca`, run `2026-09-19T23-00-53Z-b17240ad` | `7f7a4d91f4bf359a6cc56aa6ccb8a12d8fc08b5aabe9bfca6871c07e554a54cf`; bidirectional visibility for existing `index.html`, distinct handles, shared content; listener behavior inconclusive |

Q3's MAC/mode rows prove the actual sampled getters (including false mode and
`0.0.0.0` address/mask), not successful true-mode bootstrap or DHCP acquisition.
Q1 did not execute the HTTPS positive or either negative after its HTTP
positive failed. Down-before/up-after ports suggest a readiness issue; they do
not establish the unique cause of the timeout or the exact port state at `go`.

The three records retain clean semantic restoration and their explicit PDD
exception. Q3 ordinal 1's process-exit observation remains unconfirmed at its
original deadline. Later process disappearance must not rewrite that artifact.

## 2. TD-Q3-DEFAULT-01 — qualification-only, non-destructive coexistence

Authorize an experiment with the intended pool alongside the *observed native
default*, not a general claim that arbitrary pools are compatible. Two pools in
one process do not by themselves mean two independent DHCP servers, but the
native pool-selection behavior is unqualified.

Replace the Q3 runner's blanket empty-pool requirement with a typed admission
policy limited to this disposable fixture, exact build `9.0.1.0858` and fixed
file channel. Admit either a coherently observed empty disabled process or one
complete, exact observed native row under a disabled process:

```json
{"name":"serverPool","network":"0.0.0.0","mask":"0.0.0.0","gateway":"0.0.0.0","dns":"0.0.0.0","start":"0.0.0.0","end":"0.0.2.0","max":512}
```

Require the owned newly created Server-PT, exact `FastEthernet0`, true subject
identity, actual boolean `enabled=false`, complete bounded inventory, no error,
no duplicate/extra pool and absence of `MCP_E6Q_DHCP`. A matching name alone is
not authority. Unknown/malformed/incomplete baselines still refuse.

Keep `serverPool` untouched: no delete, rename, reset, rewriting its options,
replacement, per-pool-disable invention or special GUI workaround. Process-wide
enabling is part of the authorized experiment and may also activate native
behavior; do not describe the default as remaining disabled or inert afterward.
Do not infer harmlessness from the numeric allocation range or the zero mask.

Snapshot the default's observed configuration before E5, after setup and before
cleanup, using bounded reads. Preserve all snapshots and any differences.
An unexpected default change, extra pool, conflicting assignment or unresolved
effect stops subsequent experimental effects; never automatically learn and
whitelist a new default. Public admission/capability records remain unchanged.

Use the existing intended pool `MCP_E6Q_DHCP`, one address `192.0.2.100`, capacity
one, exact existing fixtures and exclusions. Observe intended-pool attribution
and the two clients separately. An intended-pool row is not sole-authority or
same-run acquisition proof. A timeout on client 2 is not pool exhaustion.
Unknown table termination remains unknown; preserve positive prefix evidence.
Do not require or claim the default lease table is empty without a qualified
end-of-table predicate.

Tests: real native-default fixture and empty control admit; arbitrary DEFAULT,
changed fields, enabled process, extra/duplicate pool, malformed types and
truncation refuse before effects; default configuration remains unchanged;
selection of an incompatible/default address contradicts, not succeeds.
The stub must not hard-code intended-pool selection as a proven native fact.

## 3. TD-READY-01 — bounded precondition before network attempts

Add a reusable qualification readiness check, not another transport or executor.
For the exact six fixture ports, retain raw typed `found`, `linked`, `port_up`,
`protocol_up`, port/device identity and safe error facts. Admit network attempts
only from a fresh complete reading with the required link/protocol booleans
true. Missing, invalid and false are distinct. Do not use `!!` to manufacture a
valid native boolean. These fields prove readiness of the measured links, not
STP forwarding, reachability or HTTP success.

Use at most four aggregate read attempts and a 30-second monotonic readiness
deadline, capped by the stage's unspent time and finalization reserve; stop at
the first complete ready sample. No unconditional sleep, busy loop or extended
fetch deadline. Record the read count, elapsed time, first/last observations and
precise failure reason. No background client or requested DHCP acquisition is
created/dispatched before its readiness gate passes.

Q1: gate before its initial positive, preserve same-mode positive prerequisites,
owned-client release and the immediate contradiction stop. A failure to become
ready is a readiness result, not evidence that HTTP/HTTPS is broken. Do not
retry a started fetch within the same experiment. Q3: gate the physical path
before activating DHCP clients; preserve the distinction from their addressing.
Recheck after a topology change; do not invent topology changes to obtain up.

Tests through real coordinator/generated probes: initially ready, delayed up,
persistent down, wrong/missing port, nonboolean return, late budget exhaustion,
persistence failure, actual absence of prohibited client calls, proper cleanup.

## 4. Q3 continuation safety — fix the active path; defer unsafe event probing

The path after the old baseline gate was not reached by either LIVE Q3 record.
Do not treat those stops as qualification of later code.

A. In `_run_q3`, classify the complete E5 result and derived exact foundations
before any E6 server mutation. Currently the setup assessment occurs only after
E6. Reuse the domain's mutation/contradiction semantics, not a new subset of
raw-field tests. Check subsequent effect results before further experimental
mutations and before the intentional same-claim guard control. Missing rows,
unknown dispatch/results, exceptions and contradictory foundations cannot grant
permission. Stage stop rules do not justify weakening product semantics for
independent work elsewhere. Preserve primary/cleanup causes and real records.

Persistence already calls `OperationLedger.close_effects` from `_Run.transition`;
retain and test that protection. Do not claim that the old code dispatched after
a failed record write merely because its control flow reached another wrapper.

B. M-DHCP-3 is explicitly **OMITTED / NOT_EVALUATED in the amended Q3 profile**,
reason `qualification_event_source_and_release_not_qualified`. It is not marked
supported and is not silently removed. No private DHCP event registrations or
unregistrations execute in the remaining Q3 slot. Reallocate its measured
operation allowance to readiness and native-default preservation, not to extra
acquisitions. Update the stage definition, executable path, scope record and
budget tests together. Keep R-EVT-05 production gating unchanged.

Reason for this bounded deferral: `register_dhcp_observers` currently subscribes
on `d.getPort(...)`, while Cisco documents `dhcpSucceed/dhcpFailed` on
`DhcpClientProcess`. The stub currently emits those events as `HostPort`, masking
that mismatch. Also `_q3_event_assessment` calls detachment observed from an
unregister attempt with no exception; `_q3_record_observer_releases` then omits
that unresolved resource. An attempt is not observed detachment. These paths
must remain unreachable in this profile until a separately reviewed event
change fixes source identity, correlation and release evidence. Do not build a
new event framework now. Add a regression proving this amended profile registers
zero observers. Retain a precise deferred note, not a generic silent skip.

C. Do not repeat server mutations merely to reconstruct a plan already applied
by setup. Reuse real coordinator/applicator stages and established results where
their contracts permit; never inject fabricated VERIFIED rows or replace the
product runtime with copied probes. Distinguish native primitive samples from
integrated product evidence. Any setup uncertainty blocks the next effect.

## 5. S1b — implement the measured shared-content branch, offline

This amendment also authorizes S1b offline from the accepted Q1 page sample.
Choose `shared_content`, not an invented independent HTTPS page store. The
measured sample covers existing `index.html`, Server-PT, build `9.0.1.0858`, file
channel at `c0307ca`; it does not demonstrate arbitrary page creation or protocol
isolation. The repaired Q1 is not a prerequisite to start this offline block.

Reuse E6 and its current content writer where the typed contract permits. Bind
one content payload and marker to the canonical server/page. HTTP+HTTPS requests
for the same shared page must agree; incompatible content refuses before E5,
not last-writer-wins. Do not mutate the runtime while discovering this conflict.
HTTPS-only content setup must not require enabling the HTTP listener. Preserve
pre/post reads, effect footprints, exact client HTTPS mode and per-client rows.
No duplicated large content in both actions/records purely for representation.

Add only the metadata/contracts needed to express shared ownership and its
source record. Keep the four-argument MCP surface. Resolve capabilities on the
actual model/operation; add replay coverage only for an actually new family.
Default new application/verification support remains UNKNOWN/UNMEASURED; probe
metadata must not set behavioral readiness READY. A Q1 run at a commit that also
contains S1b still is not Q1b if it exercises only the probe path.

Acceptance: same shared payload, conflicting payload refusal with zero effects,
HTTPS-only with HTTP off, no duplicate content mutation, fresh marker/HTTPS-mode
and no-marker negatives, optional-service coexistence, record round trip,
unknown-build/capability refusal and unchanged existing HTTP path. Use real
composition/compiler/runtime/store boundaries; only external seams are faked.
No Q1b or promotion is authorized here.

## 6. Budget and verification before contact

Recompute actual worst-case bridge calls, inner native loops, polling and time
for both amended stages. Q3 remains 60/1200 with at least its existing
11-operation/180-second finalization reserve; Q1 remains 60/600 with at least
10/120. Its old required trace was 53; readiness must be included, not charged
to unlogged preparation. Reuse bounded aggregate *read* snapshots when coherent;
do not bundle mutations just to evade accounting. No per-operation loop is
unbounded. Do not raise ceilings, borrow reserve or silently omit another
required measurement. If the mandatory trace cannot fit, refuse before LIVE
and report the exact gap.

Order: causal RED where behavior changes -> fixes -> focused -> affected and
coexistence -> full offline suite -> docs/namespace/whitespace -> commit -> clean
exact-commit delivery gate -> feature-branch fast-forward push -> exact-SHA CI.
Use separate reviewable commits for qualification changes and S1b. Tests must
assert actual native call absence and persisted evidence, not just final status.
No extra implementation-plan approval is needed inside this stated contract.

## 7. Remaining LIVE delegation — no reset of attempt counters

Preserve the original package and append an amendment ledger entry linked to
chain tip `91ab8ef5e6894b9fcff4b2578ee65fa3f7be652a264a0762303428f4d0fd6457`.
Archive this amendment and its hash as new evidence, never replace old work-order
copies. Old records that called the campaign terminal remain historical facts.

Only these two remaining attempts are authorized, conditionally after section 6:

| Scope | Ordinal | Channel/build | Maximum |
|---|---:|---|---|
| Q3 amended coexistence/readiness | 3 of original 3 | file / 9.0.1.0858 | one invocation, 60 operations / 1200 s |
| Q1 amended readiness | 2 of original 2 | file / 9.0.1.0858 | one invocation, 60 operations / 600 s |

Materialize the exact successor full SHA/tree, fixture list, policy revision,
work-order hash and identity into each immutable attempt authorization. No
wildcard SHA, fabricated reviewer signature or reuse of the old c0307ca request.
Both may use one clean CI-green candidate; use new process/session/nonce per
stage. Q0 and DNS omissions remain unchanged. No Q2, Q1b, pool removal,
`dhcpRelease`, reset, claim deletion or capability promotion.

A correct terminal inconclusive result is acceptable. A failure stops that
stage's effects and triggers owned finalization. Offline causal autofix remains
allowed, but there is no additional LIVE retry once that stage's remaining slot
is used. Independent Q1 may continue after a terminal Q3 result only after
artifacts are secure, the owned old process is observed gone and no shared
lifecycle, isolation or safety failure remains. Do not exceed caps to demonstrate
that a later fix works.

## 8. Lifecycle and final delivery

Keep the original explicit permission to gracefully close/reopen the positively
identified disposable Packet Tracer process. Verify PID + creation time + path;
closing an extension window is not process exit. Force termination is allowed
only for the proved owned disposable process under the original safeguards,
never by wildcard or on an unknown/unsaved user document. A conflicting foreign
instance is not authority to kill it. Do not delete foreign mailbox requests.
Prove old consumer exit, check pending queues and identify the new consumer.
Heartbeat cadence proves liveness, not exclusive ownership by itself; corroborate
it with process/session census and the shared-mailbox single-owner checks.

Preserve each attempt's original cleanup state. Inert/unverified observers and
retained claims are not CLEAN merely because a PID was later retired. Do not
rewrite past native facts or past inferred conclusions. Correct overclaims only
in the new projection. Maintain one brief/current index and immutable records,
not a new policy suite or copies of the whole planning history.

Return one `READY_FOR_REVIEW` with exact final SHA/tree/CI, changed contracts and
regressions, S1b offline status, every original/successor attempt and hash, default
before/after snapshots, readiness samples, original measurement conclusions,
primary/secondary causes, per-stage budget and semantic/engine/process cleanup
separated. Include one concise table of what is measured, still UNKNOWN and
not attempted. No main merge, subagents or another general investigation.
