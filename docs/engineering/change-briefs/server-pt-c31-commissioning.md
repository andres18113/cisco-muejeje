# Server-PT C31 commissioning, version 1

## Problem and outcome

The published cold HTTP acceptance route has no maintained way to construct,
deploy, and configure its disposable campus. Its publication reader also trusts
a deadline reported by the publication fact instead of binding it to the
authorized envelope. Complete the setup and then measure one 30-client,
same-segment HTTP-by-IP attempt through the existing product route under
`SERVER-PT-C31-COMMISSION-01`. Risk is **L** because this adds LIVE effects,
authorization and persistent evidence.

## Scope and exclusions

Add a maintained intent/plan export and a phase-oriented commissioning entry
point. Use the existing E4 deployer, E5 applicator, service session, acceptance
coordinator, file transport, and stores. Each attempt has a safe deployment ID,
marker, permanent reservation and one governed root. Setup may establish only
the dependency-closed L2 trunk and VLAN foundation; E5 service/endpoint actions
remain in acceptance. Preserve the public four-input MCP signature, historical
records, grant proposal, receiver controls and unknown capability status.

Do not add a transport, Packet Tracer API, `.pts`, routing, DHCP, DNS, mail,
HTTPS, wireless or event qualification. Do not merge, force push, touch foreign
worktrees or instances, replay uncertain effects, or use a third attempt.

## Requirements and acceptance criteria

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| C1 | Publication binds to the authorized deadline and temporal record | Real-model/store regression rejects a self-extended fact, missing/nonfinite/contradictory times; timely and late controls preserve their result |
| C2 | Intent and full topology are exported from the maintained campus recipe | Parameterized 2/20/200/1000 tests and 30-client recipe compile; persisted full `TopologyPlan` matches the bytes E4 reads, with intent/plan/configuration hashes |
| C3 | E4 uses a safe explicit ID and one root | E4 full result, readbacks, journal and manifest reload from the same root even when the current directory differs; partial/unobservable results cannot pass setup |
| C4 | E5 setup applies only authorized, dependency-closed L2 actions | Real applicator/runtime path records genuine action and verification rows outside service history; contradictions and unknown effects block acceptance, while redundant STP-blocked trunks are classified structurally |
| C5 | Campaign effects stay inside sealed phase grants | Parent digest, SHA/tree, inputs, targets, receiver, bounds and attempt reservation are persisted before contact; setup <= 5000/1800, unchanged acceptance proposal <= 7849/2792 including its 30/40 reserve, cleanup <= 250/300 |
| C6 | Fresh offline end-to-end run proves setup composition | Empty simulated workspace reaches actual E4, E5, stores, `--prepare` and product acceptance; foreign workspace, bad ID/root, contradiction/unknown effect, persistence and receiver loss refuse before dependent dispatch |
| C7 | LIVE attempt is observable and recoverable without replay | Original answers, structured records, publication fact, grants, errors, cleanup, two restoration reads and process exit are retained in immutable attempt directories with a validated hash index |

## Design and effects

`prepare/inspect` is read-only: validate the attempt recipe, compile the full
topology, select the exact L2 dependency closure, calculate worst-case phase
costs, and write an atomic, hash-addressable input bundle. `setup` reads that
bundle and its separate phase authorization, verifies the exact process and
receiver before contact, reserves the permanent attempt once, observes an empty
workspace, then runs E4 and E5 through the bound file channel. It persists the
complete typed results before accepting any next phase. `acceptance` reloads
the same bundle and setup evidence, releases the setup claim explicitly, uses
the unchanged `--prepare` proposal and acceptance coordinator under its own
claim, and never replays setup. `cleanup` operates only on proved owned objects
while authority remains, retains pre-cleanup evidence and two fresh restoration
observations, then releases ownership. An unknown effect, lost durable result,
receiver or process change, exhausted phase cap, or failed graceful retirement
stops further effects with a named reason.

Authorized setup effects are E4 device/link creation and exact readback, then
the compiled `create_vlan` dependencies needed by `configure_trunk`, and those
trunk actions. Acceptance alone owns HTTP content and client requests. The
fixed file channel has no fallback. Required grant inputs are the charter
digest, executing SHA/tree, bundle hashes, safe IDs, exact targets and effects,
phase caps, process identity and the operator's accepted receiver limitation.
Outputs are the typed E4/E5 results, manifest and its hash, original channel
answers, product record, envelope, publication fact and cleanup observations.

## Invariants and test design

No effect precedes admission, reservation, exact receiver/source identity and
durable input publication. A timeout or missing response cannot authorize a
retry of a mutation. The full topology and manifest identities remain equal
from export through E4, E5 and acceptance. Service history is empty before
acceptance. Configured trunk state is distinct from observed forwarding;
acceptance's existing fresh continuity gate makes the forwarding decision.
Historical evidence is immutable, and each phase record is write once.

Focused unit tests cover C1 and recipe/action selection. Integration tests
cover E4/E5 composition, store reload and failure exits. The offline
commissioning test covers C6 and the acceptance route; LIVE observation covers
C5/C7. Routing and other services are not applicable because this charter
excludes them. Verify affected tests, full pytest, namespace inventory,
MkDocs, whitespace, the exact delivery gate and exact-SHA CI before LIVE;
perform self-review and one independent read-only effect-path review. Final
status is `READY_FOR_REVIEW`, even after a successful measurement.

## Discovery delta, version 2

The first empty-workspace E4 test exposed a contract absent from the earlier
six-hole inventory: `backend_verified_port_inventory` has no Server-PT entry
for build 9.0.1.0858. E4 refuses the planned `FastEthernet0` before mutation.
Earlier Q1 records show a Server-PT link target named `FastEthernet0`, but do
not retain a complete fresh port inventory from the E4 readback seam; that is
insufficient to register a measured catalog profile. The existing bounded
port qualifier would create an additional temporary device outside this
charter's exact 35-device campaign. Keep production admission fail closed.
An offline test may inject a clearly labeled inventory double to exercise
downstream composition, but it does not satisfy C6 executable readiness or
authorize LIVE. A genuine measured Server-PT inventory or a separate grant
for the existing qualifier is required before the first E4 effect.

## Operator extension, version 3

The operator explicitly authorized one additional bounded Server-PT port
qualification on 2026-09-23. It creates and removes one temporary Server-PT
through the existing `PortInventoryQualifier` and E4 physical runtime, on an
empty disposable workspace, and retains the complete fresh port observation,
cleanup and two restoration readings. It is a separate preliminary phase; it
does not consume one of the two complete 30-client attempts, and it may not
leave a device behind or borrow the acceptance reserve. Its observed result
is retained as exact-build, attempt-bound setup evidence. A scoped resolver
may admit that measured Server-PT port during this campaign; the global port
catalog remains unchanged and UNKNOWN. No other model,
temporary target or Packet Tracer API is added by this extension. If the
qualification is incomplete or restoration fails, campaign setup remains
blocked. The added phase is charged to the setup ceiling and its exact
worst-case call and time arithmetic must be sealed before contact.

The operator also authorized a bounded exact-build `2950T-24` trunk
qualification on 2026-09-23 after the genuine E5 preflight returned
`CAPABILITY_UNKNOWN` for `supports_trunk`. Use the existing capability probe
and its prerequisite closure on one additional temporary switch, preserve its
raw result and cleanup, and admit a scoped capability only if the verified
measurement warrants it. The supported result is supplied only to this
setup's capability composition, with its original provenance; no global
capability promotion is authorized. This preliminary phase is outside the
35-device campus and precedes the campaign candidate. Recompute its exact
effects and bound, and stop if either
qualification or restoration is unobservable.

## Review delta, version 4

The read-only effect-path reviewer identified two source-level defects to
correct before contact. The scalable acceptance envelope currently says
`trunks_transit_vlans_and_gateways_are_proven_never_configured`, which would
be false after this setup configures trunk/VLAN foundations. The envelope
must state that acceptance itself does not configure them, while the separate
setup result retains what was actually configured; its fresh continuity gate
still decides forwarding. The setup's manifest-persistence boundary also
needs to catch the store's typed `ManifestPersistenceError`, persist/note a
named failure exit and withhold E5. No historical envelope is rewritten.

The reviewer also found that the first maintained recipe inadvertently kept
the test fixture's DNS service; schema 2 rejects the resulting endpoint DNS
actions. The maintained recipe is HTTP-only, as the charter requires, and an
actual `prepare_http_acceptance` integration check pins 30 clients and the
unchanged 7849/2792 proposal. Before E4, setup recompiles and compares the
entire sealed bundle, including configuration hash and action selection.
The 30-client prepare route now refuses any change to the reviewed 35/36
physical shape, four VLAN-10 actions or five paired trunk links.

## Cleanup ownership delta, version 5

The physical runtime's `remove_device` intentionally accepts only creation
attempts held in that runtime instance. A separate cleanup process cannot use
it after setup exits. Persist the exact empty baseline before E4; if that
write fails, no physical effect starts. Add one narrowly checked ownership
adoption seam for cleanup: only a complete VERIFIED E4 result with the same
topology hash, deployment ID, manifest and observed changed device rows may
populate the runtime's owned-name set. Cleanup additionally requires the same
Packet Tracer process incarnation as setup, an exclusive cleanup claim and
the fixed cleanup cap. It removes only those proved device names, stops on an
unknown removal outcome, keeps each result, and compares two fresh workspace
readings to the saved baseline. This does not authorize replaying setup.

## Phase allowance calculation

The 30-client plan has 35 devices, 36 links, no modules and 14 selected L2
actions. E4's structural call upper bound is `2 + 35*3 + 36*(2 +
(1+ceil(3/0.15))) = 935`: two empty-workspace reads, device
pre-read/mutation/readback, and link pre-read/mutation/bounded two-ended
readback. Cleanup's structural upper bound is `35*2 + 3 = 73` calls:
pre-read/removal per device, pre-cleanup inventory and two restoration reads.
The preliminary qualifiers are capped at 250 bridge calls/300 s, setup at
4750/1500 and cleanup at 250/300. The first two shares sum to the charter's
5000/1800 setup ceiling. E5's separate structural upper bound is 3343 calls:
one inventory, at most 14 action sends, four 45-second IOS boot polls at
0.25-second intervals (724 reads), four 5-second VLAN readbacks (84 reads),
and 21 grouped trunk rounds across four switches with an enforced 30-call
ceiling per nested registered IOS query (2520 calls). The setup wires no
PVST transition observer, so the optional learning extension cannot start.
E4 plus E5 is at most 4278 calls, below 4750. The product acceptance retains its
own exact 7849/2792 proposal and 30/40 release reserve. No phase borrows
another's allowance. Local source/receiver/process reads are tracked
separately and consume wall time, even though they are not bridge calls.

The preliminary probe's generic 90-second IOS wait would allow about 361
reads by itself, so this campaign binds that existing wait to 30 seconds.
Its plan-derived structural bound is 203 calls and roughly 221 seconds,
inside its 230-call/250-second ordinary allowance; 20 calls/50 seconds stay
reserved for owned temporary-device cleanup and restoration. E4 uses 3-second
mutation/read timeouts; setup E5 uses a 45-second IOS boot wait per switch and
5-second grouped trunk convergence before the acceptance route makes fresh
forwarding decisions. Each nested IOS query also has a five-second absolute
deadline. Charging a final four-switch inspection beyond the grouped wait,
receiver checks, mailbox cancellation, and the final in-flight E4/VLAN/boot
reads gives a 1484.25-second coded-wait projection inside the 1500-second
phase clock. This includes the targeted E5 inventory's 10-second wait and
1.5-second cancellation window. Filesystem publication and claim release have
no numeric OS wall bound; an observed phase overrun is STOPPED, not success.
Cleanup uses 2.5-second
read/mutation bounds and 0.25-second receiver reads; its computed structural
bound is below 300 seconds. A call that still overruns a phase cap stops the
campaign without mutation replay.

## Partial E4 retirement and E5 call proof, version 6

A stopped setup may leave an unobservable physical effect, so cleanup cannot adopt
ownership from a partial E4 result. After preserving and indexing the stopped
setup result, an owned disposable Packet Tracer process may instead be closed
gracefully and its actual process exit observed. Its retirement outcome is
`exited_dirty`; this records process isolation, never workspace restoration or
safe object deletion. A second attempt requires the archived failed result,
this exact exit evidence, a causal correction tied to those bytes, a fresh
process incarnation, an observed empty disposable workspace, and the ordinary
source/CI admission. A restored cleanup path still records `exited`.

The nested IOS query ceiling is enforced inside `ControlledIosExecutor` for this
setup alone. Reaching it yields a failed read, not an inferred trunk result.

## Nested IOS wall-time bound, version 7

The grouped trunk waiter checks its five-second window only after one round of
four registered IOS queries. A 30-call ceiling alone does not bound that round's
wall time. For C31 setup, give each registered IOS query its own five-second
absolute deadline in `ControlledIosExecutor`, including nested waits and pager
reads. The wrapper passes only remaining time to the file channel and treats an
expired or late answer as an unobservable query. The default runtime path keeps
its existing behavior. Charge the grouped waiter for its own five-second window
plus one possible four-query round, and charge E4 readbacks, IOS boot, VLAN
polls, receiver checks and mutation calls conservatively. The independently
enforced whole-phase 1,500-second clock still stops any unexpected local stall.
