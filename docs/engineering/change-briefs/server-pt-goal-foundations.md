# Server-PT goal foundations: executable diagnostics (risk L)

One offline delivery that turns the two prepared Server-PT diagnostic profiles
into executable, ungrantable qualification stages, so a later separately
authorized Codex Goal has something to run rather than another plan. Nothing
here authorizes a LIVE run, starts a bridge, contacts Packet Tracer, promotes a
capability, continues the closed Q campaign or edits historical evidence.

Authority order and archive rules are the ones in
[`server-pt-services.md`](server-pt-services.md); this file is the design delta
for the block it adds there (Block I). The operator-facing procedure lives in
[`docs/qa/server-services-goal-contract.md`](../../qa/server-services-goal-contract.md).

## Identity of this delivery

| Field | Value |
| --- | --- |
| Checkout | `Cisco-MCP-server-services-goal-foundations` |
| Branch | `feature/server-pt-goal-foundations` |
| Base commit | `65abf7bd3dbdc5047c4d4601eb18d77dca84367b` (tree `fe84c6a947318298827f857c9944843f342e3ed5`) |
| Authoritative main | `6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main`) |
| Risk | L - execution authority, evidence semantics, product runtime behaviour |

Instruction loading evidence: `AGENTS.md`, `CLAUDE.md` and
`docs/engineering/standards.md` were read from this checkout. Their SHA-256
digests are byte-identical to the same files at the base commit
(`a9f0e384...e81b`, `2931220...4516`, `2de0d5b2...3178`). An interactive
`/context` listing could not be observed from this non-interactive session, so
that check is recorded as **pending**, not as a pass.

## Problem and intended outcome

`service_diagnostic_profiles.py` describes D-DHCP and D-WEB as planning data.
Nothing dispatches them, `DiagnosticAuthorization` binds no SHA or tree, and
its predicate enforces no ordered prerequisite closure. Three concrete gaps
block a Goal from running either one:

1. The D-WEB profile states that no documented STP-state reader and no port
   light enumeration exist. Both statements are false in this repository and in
   the installed vendor reference, so the diagnostic that is supposed to
   discriminate the network path deliberately omits the only two forwarding
   observations available to it.
2. The D-WEB record contract asks for a client timeline the production web
   reader cannot produce: it reads `isHttps()` only in HTTPS mode, coerces the
   native `go()` result with `!!`, keeps only the last poll reading, reads no
   listener port number and never looks again after the deadline.
3. The D-DHCP pool projection removes the enable dependency and nothing else.
   It still carries client-mode foundational requirements that a server-only
   E5 can never verify, and a `DHCP_SERVER_STATE` expectation whose reader
   hard-codes `enabled is True`, so the disabled stage it proposes cannot pass.

The outcome is two executable stages, `D-WEB` and `D-DHCP`, that run through
the existing coordinator, ledger, record store and CLI, under one extended
execution authority that binds profile, SHA, tree, fixture models and ports,
build, channel, ordered step selection, ceilings, cleanup reserve and a unique
attempt identity - and that refuse before any bridge construction whenever any
of that is missing, stale or out of order.

## Scope

In scope:

- a neutral switch-side access-forwarding observation reusing the registered
  `SHOW_SPANNING_TREE` dispatch, its freshness/paging/identity contract and the
  existing parser, plus the documented `Port::getLightStatus()` enum as
  auxiliary evidence;
- instrumentation of the real owned-background-client lifecycle in the product
  service runtime, with an explicit finite inspection schedule and one bounded
  late read;
- a corrected D-DHCP pool projection and a narrowly scoped `enabled`
  expectation on the existing DHCP server-state reader;
- two new executable stage definitions and the extended authority that gates
  them;
- offline tests through the real components and the Node engine stub, including
  a terminal emulation so the real IOS, ping and STP paths execute their actual
  generated scripts;
- the operator/Goal contract and an inactive `/goal` draft.

Explicitly excluded: any LIVE run, bridge start, Packet Tracer contact or
launch; capability promotion; continuation of the exhausted Q campaign (Q3 3/3,
Q1 2/2); reconstruction of the missing pre-cleanup payload of the historical
`a02c1e0` Q3; `http_get`/`http_post`/`http_put`/`http_delete`, `onDone`,
`onRequest`, raw TCP connect, new frame observers and credential getters;
changes to public timeout defaults; any merge, force push or global
configuration change.

## Requirements and acceptance

| ID | Requirement | Acceptance |
| --- | --- | --- |
| I1 | A neutral access-forwarding observation reports the exact selected switch-side interfaces of one switch/VLAN group, reusing the registered IOS dispatch, the existing STP parser and the existing freshness/completeness/identity contract. It introduces no arbitrary-command escape hatch, no second parser and no `voice_vlan_id`/`voice_forwarding` field for ordinary service clients. Existing Voice behaviour is unchanged. | The neutral observer and `_wait_voice_access_group` share one extracted authority/state core; the Voice suite passes unchanged; a test proves the neutral path dispatches only `OperationalQueryId.SHOW_SPANNING_TREE` and emits no voice field. |
| I2 | FWD admission requires a fresh, complete, uniquely attributed sample of the exact switch and VLAN in which **every** requested interface appears exactly once in a forwarding state. Missing, stale, duplicate, ambiguous, wrong-VLAN, learning, listening and blocking rows each refuse on their own, and the refusal names its dimension. | A table-driven unit test covers each dimension; `UP`/`green` without an attributable row grants nothing; a sample for another VLAN or after the deadline grants nothing. |
| I3 | `Port::getLightStatus()` is read as auxiliary evidence: the raw value keeps its strict type and is interpreted only through the documented enum (`0 off`, `1 amber`, `2 green`, `3 blink`). An unknown or non-integer value stays unknown. No light value substitutes for per-VLAN FWD or for IP reachability, and contemporaneous conflicting evidence is retained beside it. | Readiness payloads carry `light_status`, `light_status_type` and `light_status_name`; the maintained claims that no light enum and no usable registered STP observation exist are removed from the probes' documented surface, the listener evidence and the D-WEB profile, and their tests follow. |
| I4 | D-WEB executes through the existing qualification coordinator, ports, record store and CLI. It observes endpoint bindings, link state, per-VLAN FWD, listener enable states with their read-back port numbers, documented port readers and existing page content; then performs exactly one `ForwardingProbeExecutor.probe_once` with the existing `TypedPingExecutor` at `measurement_attempts=1`, counting every nested bridge call. No second ping parser is written and the safe ping timeout contract is preserved. | A coordinator test drives the whole path over the Node stub with a real terminal; the ledger shows every nested terminal call; the record carries both endpoint bindings before and after the ping; the ping is labelled an active stimulus. |
| I5 | The D-WEB client timeline instruments the real owned background client: actual owner device, selected request URL and path as inputs, client mode read in both HTTP and HTTPS, the native `go()` result with its type and no Boolean coercion, pre-request content, marker, every attempted inspection with its dispatch, result, monotonic offset and remaining budgets, one separately bounded late read that starts no second request, and the release outcome. Missed sampling slots are recorded, never fabricated or replayed in a burst. | Timeline entries survive a record reload; a non-boolean `go()` yields a malformed reading rather than `client_go_false`; the late read is one counted operation and issues no `go`; no public timeout default changes. The Node ownership harness answers the documented `HttpClient::getOwnerDevice()` the reader now calls, and a client that reports no owner, or one owned by another device, refuses while still being released. |
| I6 | D-DHCP executes the causal sequence disabled baseline, then server static addressing only, then the intended pool while still disabled, then process enable, then terminal observation and owned cleanup. Client DHCP flags are untouched, no acquisition, release, reset, event or default-pool setter is dispatched, and the pool projection selects only applicable server foundations derived from the executed static-only E5 plan. | The stage runs with zero client activation and zero default setter in the dispatched scripts; the disabled stage verifies `enabled=False` with the exact pool fields; the following stage verifies the transition to `True`; every projection rewrite is recorded explicitly. |
| I7 | D1's real native call footprint is recorded. The static-address action is one `configurePcIp` call that also writes gateway and DNS, so the interval is attributed to that broader intervention and never to an IP-only cause. A bounded control observation distinguishes autonomous drift from a transition following an intervention. | The record names `configurePcIp` with its written fields; two adjacent baseline readings with no intervention between them are persisted as the control; a difference found there is reported as drift, not as an effect of D1. |
| I8 | One execution authority. The existing `QualificationRequest`/`QualificationAuthorization`, repository identity, `ImportIsolationPreflight`, manifest targets, fixed transport, ledger and store gate both new stages. The authority additionally binds profile id and version, the exact SHA **and** tree, the exact fixture models and link ports, build, channel, the ordered step selection, operation and time ceilings, the cleanup reserve, a fresh instance token, the exact observed Packet Tracer PID/path and a unique attempt identity. Reordered, duplicated, incomplete and activation-only selections are refused. The local preflight also requires that process at the authorized build and an empty mailbox before transport, and the same read-only reading after finalization must still name that process with nothing left in the mailbox; `DiagnosticAuthorization` stays planning data and is never the execution gate. | Negative admission tests cover every added binding and process/mailbox observation; a `GRANTED` diagnostic draft alone changes nothing; selecting an activation step whose prerequisite the run has not established refuses; a replaced process, an undrained mailbox or an unreadable exit reading keeps the readings, drops `restoration_proven`, stops the run and refuses promotion; historical records still validate under schema version 1 with both lifecycle fields absent. |
| I9 | Invalid, missing or stale authority refuses before the transport is constructed or contacted. Persistence failure closes new effects while preserving the primary error and affordable owned finalization, and budget exhaustion never borrows the cleanup reserve. | Refusal tests assert an empty channel-open log and an empty call log; a failing store keeps the first primary failure and still finalizes; a ceiling that leaves only the reserve refuses the next effect instead of spending it. |
| I10 | The required/optional service projection, retained results, shared HTTP/HTTPS content handling, secrets, the single `packet_tracer_mcp` namespace and the public four-argument MCP signature are unchanged. | The full offline suite, the namespace inventory, MkDocs and the whitespace check pass on the delivery commit, and exact-SHA CI is green. |

## Architecture and affected contracts

- **Domain.** `domain/enterprise/models/forwarding.py` gains
  `PortLightReading`, `AccessForwardingInterface` and
  `AccessForwardingObservation`; the new
  `domain/enterprise/services/access_forwarding.py` owns the FWD admission rule
  and the documented light enum. Neither performs I/O.
  `domain/enterprise/models/service_qualification.py` gains the two stage
  definitions, the selectable-step model and the extended authority rule; it
  remains the single owner of stage identity and admission.
- **Application.** `qualify_server_services.py` gains the two stage procedures
  and the injected boundaries they need (`access_forwarding`,
  `forwarding_probe`). Assessment rules live in the existing domain evidence
  module, not in the coordinator.
- **Infrastructure.** `enterprise_configuration_runtime.py` gains
  `observe_access_forwarding`, sharing one extracted core with the Voice
  observer. `service_qualification_probes.py` gains the light-status and
  listener-port readers inside evaluations that already run.
  `enterprise_service_runtime.py` gains the web-fetch timeline, the explicit
  inspection schedule and the late read; its defaults reproduce today's
  behaviour exactly.
- **Adapters.** The qualification CLI composes the new boundaries and accepts
  the added authority arguments. No raw JavaScript, IOS or bridge command is
  accepted from the operator, and the MCP tool surface is untouched.

### Completion audit delta

The interrupted G1 integration left the neutral forwarding observer's bounds
and simulation-time field only partially wired. Completion keeps the existing
read-only `SimulationTraceRuntime` reader as the single default source for both
Voice convergence and neutral access-forwarding evidence. One simulation-state
read is taken per neutral observation, after its bounded STP samples, and is a
separate ledgered operation; it never extends the wall-clock deadline or the
sample ceiling. A zero sample ceiling performs zero STP reads, and non-finite or
negative bounds refuse before dispatch instead of being silently widened.

The same audit found two G2 contract holes in the instrumented web client. An
owned request is admissible only when the actual owner, the mode in both HTTP
and HTTPS, and a coherent native boolean `go()` value plus type were observed.
A missing or mismatched owner/mode and an absent, non-boolean or contradictory
native result close the read without polling. If all explicit inspection slots
have already elapsed, every slot is retained as missed and no unscheduled
replacement inspection is dispatched; the separately labelled late control,
when configured, remains the only read after the request window.

The D-DHCP snapshots already bracket each intervention, but the stage facts
must also retain the applicators' typed action rows. D1, D2 and D3 therefore
persist each action's dispatch, result, postcondition, transition, attempted
flag, call error and received mutation beside the adjacent snapshots. D2 names
the full generated pool-mutator footprint (`addPool`, exclusions when present,
mask, router, DNS, range and capacity setters), rather than the earlier partial
three-call label. These are observations of the generated/product path and do
not attribute a native-default transition to any one call inside the interval.

The authority audit also found that `instance_token` was only caller-supplied
text: it was not paired with an observed Packet Tracer process, and a fresh
file-channel heartbeat could still be mistaken for exclusivity. Diagnostic
profile version 2 adds exact authorized process PID and executable path. A
read-only local lifecycle preflight, before transport construction, requires
exactly one coherent Packet Tracer process matching that PID, path and build,
and requires the fixed file mailbox to contain no request, response or
temporary command artifacts. It never deletes a stale artifact and never
launches or stops a process. The existing read-only disposable-workspace
observation remains the last admission gate before any effect, protecting an
operator's existing document even after the local process/mailbox checks pass.

Binding that process once is not the same as preserving the pairing. A
Packet Tracer that is closed or crashes mid-run is replaced by an instance
that polls the same mailbox, so the owned removals and both restoration
reads would be answered by a process the authorization never named, and the
run could still report `COMPLETED`. The same read-only reading is therefore
taken again after finalization and stored beside the first. A changed
PID/path/build, an unreadable second reading or any remaining `req_*` or
`res_*` artifact becomes engine residue, drops `restoration_proven` and
leaves the run stopped; the promotion gate reads both readings. It is a
local process enumeration and one directory listing, so it spends no bridge
operation, the cleanup reserve is never borrowed for it, an exhausted budget
cannot suppress it, and it changes no stage worst case. It still deletes
nothing: an artifact left behind is reported because it is precisely what a
later instance could re-execute. A run refused before any effect owns no
state and claims no restoration, so it takes no second reading; the gate
that would consume one already requires a completed run.

Single writer was held by that evidence alone. **Superseded by GF-R1 below.**
The pairing observes which Packet Tracer answers; it does not observe whether
a second Python campaign writer, in another checkout, is driving the same
mailbox. The mailbox protocol was built for coexistence rather than exclusion:
`FileBridge` names every request `pid_boot_seq` precisely so concurrent MCP
processes sharing one mailbox do not collide, and `_purge_own_stale`
deliberately never touches another process artifact. Unique filenames avoid
collisions between requests; they exclude nothing between campaigns. GF-R1
adds the claim that does, in the scope the two writers share, and keeps the
three obligations -- one campaign writer, one bound Packet Tracer incarnation,
and ownership of each mutated object -- separate, because none of them implies
another.

The sampling and evidence corrections do not add a stage, fixture, effect,
parser or timeout. The lifecycle correction adds only the two exact process
identity fields described above. They updated D-WEB's figure from 61 to 63
operations, counting a registered spanning-tree sample as four calls and a
typed ping as three.

**Superseded by GF-R4 below.** Four and three were the intended paths of those
compositions, not their worst cases, and the figure they produced is not
evidence that the stage fits. The proved bounds, and the 74-operation worst
case they give, are in the focused corrections section.

## Invariants added by this block

34. A forwarding permission is per VLAN, per interface and per sample. A light
    status, a port-up flag and a previous FWD sample are auxiliary evidence and
    never a substitute for a fresh attributed row in the exact VLAN.
35. A diagnostic stimulus is labelled as one. A ping changes ARP, MAC and
    timing state, so a later success is not attributable to the boundary the
    diagnostic was asking about unless a governed comparison changed only that
    boundary.
36. An execution authority binds identity, not intent. Text preconditions, a
    `GRANTED` flag and a known step name grant nothing on their own, and no
    selection may bypass state the same run has already established.
37. A projection that changes what a compiler asserted records the exact
    rewrite it made. A modified plan is never presented as a fresh execution of
    the unmodified one.
38. An execution pairing is preserved, not asserted once. Evidence produced
    after the bound process stopped being observable describes some process,
    not the authorized one, so it proves no restoration and completes no run.

## Test design

Focused unit tests own the domain rules (FWD admission dimensions, the light
enum, the step-selection rule, the extended authority). Integration tests drive
both stages through the real coordinator, the real product runtimes, the real
record store and the Node engine stub, whose terminal emulation executes the
actual generated IOS, ping and STP scripts. Acceptance tests assert the five
G5 criteria directly. Simulations stay labelled `offline_simulation`; no test
result is evidence about Packet Tracer.

## Budget arithmetic

**The D-WEB figures in this section are superseded by GF-R4 below.** The
calibration is still right for what it covers -- an endpoint E5 batch costs one
`send` plus one verification read per expectation, an E6 service action costs
one dispatch plus one read-back per expectation, and one native default reading
costs one dispatch -- but a registered spanning-tree sample and a typed ping
were counted at their intended paths rather than their worst cases, so "the
worst case of the real composed call path" was not what the figures described.
The proved bounds, and the ceiling change they require, are in the focused
corrections. D-DHCP's arithmetic is unaffected: nothing it does polls a
terminal.

The old 60-operation ceiling and the 43/47 planning figures of the prepared
profiles are not evidence that any of this fits; the numbers are recomputed
from the composed paths. No granted ceiling is raised by this delivery.

## Residual limitations

- Offline CI cannot verify Packet Tracer, the webview CORS boundary, the
  `this-sm:` origin or Script Engine reachability. Everything both stages would
  measure stays UNKNOWN/UNMEASURED until a separately authorized, observed LIVE
  run exists.
- R-EVT-05 still gates event-driven product verification; no event source is
  registered by either stage.
- The missing pre-cleanup payload of the historical `a02c1e0` Q3 is permanently
  missing and is not reconstructed.
- The native default transition observed across server and client E5 plus E6
  setup has no known causal trigger. The stub that changes it on process enable
  is a controlled test scenario, not a measured attribution.
- `/goal` availability in the operator's Codex installation is recorded as
  observed-version-only: `codex-cli 0.155.1` is installed and its
  non-interactive command surface lists no `goal` entry, which is not proof
  either way about the interactive slash command.

## Focused corrections at `ab668d7` (risk L)

One offline correction delivery inside this block's approved contract, not a
new phase. It closes four audit findings against the components that actually
ship, and it changes no LIVE entitlement: Q3 3/3 and Q1 2/2 stay exhausted,
every diagnostic authorization stays DRAFT, and no Packet Tracer process is
contacted, launched or stopped by anything below.

| Field | Value |
| --- | --- |
| Checkout | `Cisco-MCP-server-services-goal-foundations` |
| Branch | `feature/server-pt-goal-foundations` |
| Correction base | `ab668d758a1a9d36fa86b141c9f0ce2021c7a363` (tree `114e07e9ac8934ed7c89f9b544b227bf05100c66`) |
| Authoritative main | `6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main`) |
| Risk | L - unchanged: authorization, evidence semantics and destructive cleanup |

Instruction loading evidence for this delivery: `AGENTS.md`, `CLAUDE.md` and
`docs/engineering/standards.md` were read from this checkout and compared
byte-for-byte against the copies already in the working session; all three are
identical. An interactive `/context` listing could not be observed from this
session, so that check stays **pending**, exactly as it was recorded above.

### GF-R1 - foreign effects are prevented, not merely reported

The defect is an ordering one. `_finalize` removed devices and read restoration
*before* `_lifecycle_postflight` looked at the process pairing again, so a
permanent replacement was detected one step too late to stop a removal in the
replacement's workspace. Three separate obligations were also being carried by
one observation: a single cooperating Python campaign writer, the permitted
Packet Tracer process, and ownership of the resource being mutated.

The correction keeps them separate and uses the seams that already exist.

- **One campaign writer.** `FileCampaignCoordinator` takes an exclusive claim
  in the fixed file mailbox under `%LOCALAPPDATA%`, which is the resource two
  checkouts actually share; a per-checkout record directory is not. The claim
  is one `O_CREAT|O_EXCL` file. An existing claim refuses admission and is
  never removed, never inspected for staleness and never reclaimed by age.
  Release deletes only a claim whose stored holder identity is this process's.
- **One attempt, reserved atomically.** The attempt identity is reserved in the
  same coordination scope by the same exclusive creation, so the scan and the
  reservation are no longer two steps with a window between them.
  `QualificationRecordStore.attempt_exists` stays as a second fail-closed check
  over the immutable records, which remain the audit trail.
- **One process incarnation.** `DiagnosticLifecycleObservation` gains
  `process_incarnation`, read as the bound process's creation time. A PID that
  is reused by a new process no longer satisfies the pairing.
  `CPScaleProcessRecord` is deliberately not touched: the incarnation is read
  by the diagnostic lifecycle reader's own source.
- **Authority is checked before effects, and its loss is sticky.** Every
  effecting step and owned finalization re-evaluate the pairing and the claim
  before acting. The first loss is kept, later ones are recorded separately,
  and a lost authority is never re-acquired inside the same run.
- **A destructive action on an unproven receiver does not happen.** When
  authority is lost, `_finalize` performs no removal and no bag release. It
  records each one as `not_attempted` with its cause, keeps whatever was
  already observed, and drops `restoration_proven`. The postflight reading
  stays exactly where it was and keeps its detection role.

Stated limit, not a claim of universal exclusion: this proves one Python
campaign writer and one bound Packet Tracer incarnation. It does not prove that
no other program mutates the same workspace by other means. That receiver
boundary is not establishable within the existing seams, so it is recorded here
and LIVE stays blocked on it rather than being described as excluded.

### GF-R2 - operational prerequisites are not experimental conclusions

`_Execution.admissible` required every prerequisite measurement to conclude
`SUPPORTED_IN_SAMPLE`. A coherent native-default change concludes
`NEGATIVE_OBSERVED`, so D1 blocked D2 and D2 blocked D3 even when E5/E6 applied
and their exact read-backs succeeded - the diagnostic's dependent variable
disqualified its own continuation.

`ExperimentSpec` gains `operational_prerequisites`: named preconditions a run
*establishes*, distinct from what a measurement *concludes*. `_Execution` keeps
the established set, and for a stage that declares a diagnostic profile the
admission rule reads that set instead of the prerequisite conclusions. Q0, Q1,
Q3 and every product caller keep the conclusion rule unchanged; nothing
globally admits a NEGATIVE or UNKNOWN prerequisite.

The preconditions are small, observable and operational: the subject/session is
the bound one, the retained inventory was read coherently, the required
configuration was established and read back, the required enabled/disabled
state was verified, persistence is usable, authority and budget are present,
and no effect is left unresolved. A negative experimental conclusion is kept
negative and is never relabelled to pass a gate. Autonomous baseline drift, a
lost response, a contradictory read-back, a wrong subject and an unreadable
inventory each still stop effects, because each one fails a precondition rather
than only producing a negative conclusion.

### GF-R3 - terminal boundaries are observed on unsuccessful paths

Two distinct holes. `_d_web_after` was gated behind the HTTP fetch concluding
`SUPPORTED_IN_SAMPLE`, so the very timeout the diagnostic investigates
suppressed the after-listener and STP readings. `_run_d_dhcp`'s D4-final used
the ordinary `begin`, which refuses once a primary failure exists, so a stopped
DHCP diagnostic deleted its fixtures without the terminal native reading it
promises.

Safe final observation is separated from success-dependent progression.
`_Execution.begin_terminal` admits a read-only terminal observation when the
subject/session authority holds and the ordinary (non-reserve) allowance covers
it, whatever the primary failure was - a timeout, a contradiction, a stopped
procedure or a persistence problem. It dispatches no fetch, ping, DHCP
acquisition or configuration. A reading that is unsafe or unaffordable produces
an explicit not-observed entry naming its cause; it is never silently omitted
and never paid for out of the cleanup reserve. The first primary failure is
preserved and later failures are recorded separately. When persistence itself
is unavailable the record says that the terminal evidence is retained in memory
and was not durably stored, rather than presenting it as persisted.

That last case needed one addition to the ledger. A failed write-ahead boundary
closes the effect gate, and the gate refused everything outside finalization --
including the read-only reading this correction exists to take. The ledger
therefore gains a `terminal_observation` phase, which the gate admits and which
`allowance()` still treats as ordinary, non-reserve spending. A closed gate
stops further mutation; it is not a reason to stop looking at what the run is
about to leave behind, and the phase makes that distinction visible in the
record's own operation list rather than implicit in a boolean.

The D4 interval metadata is corrected in the same pass. D4 compared the
baseline with the final reading while labelling it with D1's last intervention
and D1's native-call and field lists. It now reports a **cumulative**
baseline-to-final summary that names the ordered sequence of interventions
actually executed, and the call lists it carries are labelled as the declared
generated footprint, not as an observed execution count. An adjacent interval
and a cumulative summary are two different claims and are recorded as such.

### GF-R4 - composed slow paths are budgeted from their real worst case

The 63-operation figure assigned seven calls to the bind-before-ping
composition and four to a spanning-tree sample. Neither is that composition's
worst case. `TypedPingExecutor._ping_once` polls `inspect()` until statistics
appear or the 30-second window closes; at a 0.25-second interval that is tens
of counted calls, not one. `ControlledIosExecutor.execute` is worse: session
preparation, up to three dispatch attempts, a convergence waiter, an
attribution read, pager capture and pager cancellation are all nested calls
that the caller's per-sample deadline cannot cap, because it is only read after
the nested command returns.

Both get a finite, explicit sampling policy that preserves the safe observation
window and the single command attempt.

- **Ping.** `TypedPingExecutor` gains an optional `max_inspections`. Default
  `None` keeps today's behaviour for every existing caller and changes no
  public default. When set, the poll interval is spread so the inspections
  cover the whole safe window instead of shortening it, and the loop ends on
  the window or on the cap, whichever comes first. A sample that ends on the
  cap is classified as bounded-incomplete, never as an unreachable
  destination.
- **Registered STP reads.** The neutral access-forwarding observation dispatches
  through its own `ControlledIosExecutor` bound to a counting channel that
  carries the remaining deadline into each actual `send_and_wait` timeout and
  refuses past a declared per-sample call budget. `ios_terminal.py` is not
  modified; the bound is applied where the diagnostic composes its executor.
  A sample that exhausts the budget is returned as an explicitly incomplete
  sample with its cause and grants no forwarding permission.
- **The advertised schedule is stated and tested.** Two closely spaced samples
  do not cover a nominal 30-second convergence window, and the contract now
  says what the schedule actually is instead of implying coverage. No blind
  sleep, PortFast, bounce or configuration retry is introduced.

Recomputed worst cases, from the complete feasible paths including the GF-R1
authority checks (which cost zero bridge operations) and the GF-R3 terminal
observations (which are already counted as planned operations):

| Stage | Was | Now | Ceiling |
| --- | --- | --- | --- |
| D-DHCP | 45 | 45 | 50, unchanged |
| D-WEB | 63 | 74 | 68 -> 80 |

The D-WEB deltas are M-DWEB-1 (9 -> 13: two samples at six calls plus one
simulation read), M-DWEB-3 (7 -> 12: four endpoint reads, one dispatch, six
inspections, one attribution) and M-DWEB-5 (6 -> 8). D-DHCP is unchanged
because nothing it does polls a terminal; the GF-R1 authority checks cost no
bridge operation and the GF-R3 terminal reading was already a planned one.

D-WEB's draft ceiling is raised because the corrected worst case exceeds 68. It
is a never-granted draft limit; no historical Q budget is raised, and Q0
20/300, Q1 60/600 and Q3 60/1200 are untouched. Each per-stage figure, the
sample budget the runtime enforces and the inspection bound the production
probe composes are pinned by contract tests, so a figure the code does not
apply fails the suite.

### One mapping from the four findings to their evidence

Every regression below is causal: reverting only its own fix and re-running it
produces RED, which was executed and recorded rather than assumed.

| Finding | Fix | Regressions that pin it | Reverting the fix |
| --- | --- | --- | --- |
| GF-R1 foreign effects | authority re-checked before every effect and before owned cleanup, sticky on loss; no removal to an unproven receiver; campaign claim and atomic attempt reservation in the shared mailbox scope; incarnation bound | `test_a_replacement_before_the_first_removal_deletes_nothing`, `test_a_second_packet_tracer_mid_run_stops_before_the_next_effect`, `test_a_reused_pid_at_the_authorized_path_is_not_the_bound_process`, `test_a_second_campaign_writer_is_refused_by_the_shared_scope`, `test_one_attempt_identity_cannot_be_reserved_twice`, `test_a_claim_is_never_reclaimed_by_age_or_guesswork`, `test_a_held_campaign_refuses_the_run_before_any_contact` | RED |
| GF-R2 prerequisites | `operational_prerequisites` over established state for diagnostic stages; conclusion rule unchanged everywhere else | `test_a_coherent_change_at_d1_does_not_stop_d2_or_d3`, `test_a_coherent_change_at_d2_does_not_stop_the_enable`, `test_a_coherent_change_at_the_enable_is_the_finding_itself`, `test_autonomous_drift_still_stops_every_later_effect` | RED |
| GF-R3 terminal boundaries | `begin_terminal` admits read-only final observations after a failure; cumulative D4 summary | `test_an_http_timeout_does_not_suppress_the_after_boundaries`, `test_every_unsuccessful_fetch_path_still_reads_its_boundaries`, `test_the_terminal_reading_is_cumulative_and_names_its_interventions`, `test_a_terminal_reading_without_authority_is_declared_not_taken` | RED |
| GF-R4 budgets | `max_inspections` on the typed ping; per-sample channel call budget carrying the remaining deadline into the I/O; recomputed figures | `test_a_delayed_ping_costs_its_inspections_and_still_classifies`, `test_an_output_slower_than_the_sample_budget_is_incomplete_not_forwarding`, `test_the_sample_bound_caps_the_nested_calls_the_deadline_cannot`, `test_a_ledger_that_cannot_pay_refuses_the_next_nested_call`, `test_the_composed_worst_cases_are_pinned_not_only_below_the_ceiling` | RED |

The positive controls stay green beside them: a clean run still removes what it
owns (`test_a_clean_run_still_removes_what_it_owns`), a slow-but-finishable
sample is still admitted
(`test_delayed_forwarding_observed_within_the_bound_is_still_admitted`), and
autonomous drift still closes the run.

### Invariants added by this correction

39. A destructive action requires a proven receiver at the moment it is taken.
    Detecting afterwards that the receiver was not the authorized one
    invalidates the report; it does not undo the deletion.
40. An experimental conclusion and an operational precondition are different
    claims. A negative finding is the result the diagnostic exists to produce
    and never disqualifies the step that depends on the state, only on the
    conclusion.
41. A terminal read-only observation belongs to the run, not to its success.
    An unobserved terminal reading is an explicit absence with a cause.
42. A budget figure is the worst case of the composed path, including every
    nested call the caller cannot see. An instantly answered stub command is
    not a worst-case oracle.

### Test design for this correction

Causal RED first for each behavioural fix, through the real components rather
than the audit's isolated countermodels. GF-R1 adds two competing campaign
writers, two competing reservations of one attempt, a replacement immediately
before the first removal, a second Packet Tracer detected mid-run, a reused PID
with a changed incarnation, and a foreign engine workspace holding objects with
the exact fixture names and models - asserting zero mutations and zero
deletions in that foreign workspace, not only `restoration_proven=False`.
GF-R2 drives coherent native changes independently at static addressing, pool
configuration and enable, asserting the later intervention runs, that all
adjacent observations survive a reload, and that client acquisition, client
mode changes and native-default setters stay at zero. GF-R3 exercises the HTTP
timeout, `go=False`, fresh wrong content, an unresolved release and an
intermediate DHCP failure, asserting the terminal payloads and their own
operation identities after reload, with the terminal value forced to differ
from every earlier snapshot. GF-R4 runs the real composition against the fake
clock with delayed ping statistics, slow and incomplete terminal output,
delayed STP forwarding, a budget exhaustion that genuinely forces refusal, a
deadline crossing, and the cleanup/attribution reservation, pinning actual
ledger calls against the calculated bound.
