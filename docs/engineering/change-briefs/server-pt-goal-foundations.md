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

## Residual corrections at `5db6916` (risk L)

The independent review of `5db6916` returned `REQUIRES_CHANGES` with four
residual defects. This is one further offline correction inside the same
approved contract: no LIVE entitlement changes, Q3 3/3 and Q1 2/2 stay spent,
every diagnostic authorization stays DRAFT, and no Packet Tracer process is
contacted, launched or stopped by anything below.

| Field | Value |
| --- | --- |
| Checkout | `Cisco-MCP-server-services-goal-foundations` |
| Branch | `feature/server-pt-goal-foundations` |
| Correction base | `5db691665854f541c54f402002171c4c17ea0d05` (tree `eb0dd38255c930174cad53f5e88806a4a4e4a095`) |
| Previously reviewed | `ab668d758a1a9d36fa86b141c9f0ce2021c7a363` |
| Authoritative main | `6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main`) |
| Risk | L - unchanged: authorization, effect dispatch, evidence semantics, destructive cleanup |

Instruction loading evidence for this delivery: `AGENTS.md`, `CLAUDE.md` and
`docs/engineering/standards.md` were read from this checkout before any edit.
An interactive `/context` listing could not be observed from this session, so
that check stays **pending**, exactly as it was recorded for the two deliveries
above.

### R1 - authority is decided at the effect boundary, not once per finalization

The defect that survived `GF-R1` is a caching one. `_finalize` called
`live_authority` once, saved `owned`, and then used that one decision for the
bag release and for *every* removal. A receiver replaced after the first
removal received the later ones, and the postflight reading detected the change
only after the deletions had already been dispatched. The same shape applied
earlier in the run: `_setup_fixtures` creates devices and links, and
`_configure_q1` applies E5 endpoints and enables the E6 listeners, all before
the first measurement's `begin` ever asks about authority.

The correction moves the decision to the one place every effect actually passes
through, and keeps it there.

- **An effect scope is a declared thing.** `OperationLedger.effect_of(purpose)`
  labels a block whose dispatches change engine state, exactly where
  `purpose_of` already labelled them for the record. Reads keep `purpose_of`
  and are unaffected.
- **The gate sits in `admit()`, before dispatch.** A call admitted inside an
  effect scope first asks the bound effect guard - `_Execution.live_authority` -
  whether this invocation still holds the campaign claim and the bound Packet
  Tracer incarnation. A lost authority refuses the call with
  `execution_authority_lost:...` before anything crosses the channel, and the
  refusal is recorded as a refused operation entry like every other one.
- **Fail closed on a missing control.** An effect scope with no guard bound
  refuses with `effect_guard_not_bound`. Constructing `_Execution` binds it,
  so a composition cannot forget the step and dispatch anyway: an execution
  over a ledger is the only thing that can answer for that ledger's effects.
- **Loss stays sticky.** `live_authority` already keeps the first loss and
  never re-acquires; the gate inherits that, so one replacement refuses every
  later effect rather than being re-litigated per call.
- **Zero bridge operations.** The guard enumerates local processes, reads one
  small file and lists one directory. It spends no ledger operation, so an
  exhausted budget cannot suppress it and the cleanup reserve is never borrowed
  for it. Both stage budgets are therefore unchanged.

Which dispatches are now gated: fixture creation, link creation, the Q1 E5
endpoint application and E6 listener enable that D-WEB's setup performs, the
D-DHCP E5 static addressing, the D-DHCP E6 pool configuration and process
enable, the D-WEB marker-page write, the typed ping stimulus, the owned
background client's whole lifecycle, the run-bag release, and each owned device
removal - the cleanup pre-readback and the destructive command separately,
because they are two dispatches and a receiver can be replaced between them.

Q0, Q1 and Q3 keep their behaviour exactly. The guard is shared, but a stage
that declares no diagnostic profile holds authority by definition
(`live_authority` returns `True` on its first line), so the gate is transparent
there. That is the whole justification for the shared guard.

**Stated limit, and it is the reason LIVE stays blocked.** This is an
in-process decision taken immediately before the command is handed to the
channel. It is not an in-band receiver fence. No existing dispatcher - the file
mailbox, the physical runtime's mutation acknowledgement, the product runtime
payloads, the probe readings - carries a receiver-resident session token that
the receiver itself verifies in the same evaluation that mutates. The one
receiver-resident ownership resource this repository has is the engine-global
run bag, and it proves ownership only inside the probe scripts that already
read it; extending it to the mutation dispatchers would change the response
contract of every effect path, which is exactly the new protocol this
assignment forbids. So the interval between the guard's decision and the
receiver consuming the command is **not** fenced. Every diagnostic record now
carries `effect_gate_is_local_and_not_an_in_band_receiver_fence` as a named
limitation, and no claim of universal exclusion is made: what is closed is the
concrete receiver-replacement defect, where the replacement is already visible
in the local process table when the next effect is admitted.

### R3 - the terminal observation is part of finalization, not the last step

`begin_terminal` fixed the paths that reach it. It did not make that path
unavoidable. D4 and W5 were still the bottom of the ordinary stage sequence,
`_Execution.procedure` catches only `OperationRefused`, and any other exception
escaped to `_admitted`, whose `finally` called `_finalize` directly. A stage
that raised an ordinary Python exception mid-sequence deleted its fixtures with
its terminal measurement left `NOT_RUN` and its reason empty.

The correction makes the selected terminal phase a registered, at-most-once
part of guaranteed pre-cleanup finalization.

- `_TerminalPhase` records the measurement ids, the procedure name and the
  closure that takes the reading. `_run_d_dhcp` and `_run_d_web` **register**
  it before their first procedure - over the stage state object, so the
  cumulative D4 summary still has the baseline, the ordered interventions and
  the declared call footprint it needs to be interpreted - and no longer call
  it inline.
- `_admitted`'s `finally` runs `_observe_terminal(execution)` and only then
  `_finalize(execution)`. Normal completion, a handled stop, an intermediate
  exception and a persistence failure all reach the phase through that one
  path, so the reading always precedes the first deletion.
- **Cancellation is explicit.** A `KeyboardInterrupt` sets
  `_Execution.cancelled`. The terminal phase is then *not* taken and is
  recorded as `not_observed:cancelled` for its measurements. A cancelled run
  stops doing work; the only thing that still has to happen is owned cleanup.
  No stimulus is restarted, and nothing is re-dispatched.
- **A terminal-reader failure is secondary.** `_observe_terminal` never raises.
  An exception inside the reading is recorded as
  `terminal_observation:exception:<Type>`; the first primary failure is
  preserved (`stop` keeps the first reason) and owned cleanup still runs.
- Unsafe or unaffordable readings keep the `begin_terminal` semantics they
  already had: an explicit `not_observed:<cause>` absence, paid for out of the
  ordinary allowance and never out of the cleanup reserve, with durable and
  memory-only evidence still distinguished.

Nothing about the D4 content changes: it stays the cumulative baseline-to-final
summary naming the ordered interventions actually executed, with its call lists
labelled as the declared generated footprint. No baseline is invented from a
final reading, no snapshot is overwritten, and no historical `a02c1e0` evidence
is reconstructed.

### R4 - the inspection schedule covers the whole promised window

`TypedPingExecutor._ping_once` computed `interval = timeout / max_inspections`
and read immediately. For a 30-second window and six inspections the reads
landed at 0, 5, 10, 15, 20 and 25 seconds, so statistics published at 29 seconds
- inside the window the safe timeout exists to provide - were missed. The
resulting classification was conservative rather than fabricated: the defect is
the premature closure of the promised window, not an invented unreachable
result.

**The policy, stated once and implemented once.** With `max_inspections = n`,
the reads are the `n` endpoints of an even partition of the closed window
`[0, timeout]`: slot *k* is `k * timeout / (n - 1)` for *k* in `0..n-1`. For six
inspections over 30 seconds that is 0, 6, 12, 18, 24 and 30 seconds, with an
immediate first read and a last read at the deadline itself.

- **`n = 1` is handled deliberately.** One read cannot be both immediate and
  window-covering. The window is the promise, so the single read is taken at
  `timeout`. There is no division by zero: the `n = 1` schedule is built without
  the partition.
- **Elapsed I/O is treated as elapsed.** Slots are absolute times from the start
  of the poll, not delays between reads. After each read the schedule advances
  past every slot that is already in the past, and the next read waits only the
  remainder. Missed slots are skipped, never batched: there is no catch-up
  burst, and the number of inspect calls is at most `n`.
- **Boundary semantics.** A slot at exactly `timeout` is taken; the window is
  closed inclusively. The loop also ends as soon as statistics appear.
- **Late-result semantics.** Ending on the window without statistics stays
  `no_fresh_ping_result`, as it always was for the unbounded default.
  `ping_inspection_budget_exhausted` now means one specific thing: the finite
  schedule was exhausted while the clock was still inside the window, which
  happens when the injected sleeper could not honour the schedule - a
  ledger-capped sleep is the real case. A sample that ends on either bound is
  still reported as incomplete and never as an unreachable destination.
- `max_inspections=None` is untouched: the unbounded poll keeps the caller's own
  interval and every existing caller keeps today's behaviour.

One ping command, bounded attribution and the before/after address reads are
unchanged, as is the registered STP counting/deadline implementation. The fix
adds no seventh inspection: the composed 12-operation probe budget and both
stage ceilings stay exactly where they are. The `D_WEB_PING_INSPECTIONS` and
in-function comments that described the old last-read/deadline behaviour are
corrected to the schedule above.

### C1 - local finalization results are kept, and local readers are bounded

**The campaign release.** `_release_claim` returned reasons and every caller
discarded them, and it ran in `qualify_server_services`' outer `finally` - after
`run.complete()` had already written the immutable record. A campaign lock that
could not be released therefore blocked the next campaign with no corresponding
terminal record or summary failure.

The release now happens inside the record lifecycle. `_CampaignHold` owns the
coordinator, the claim and whether this invocation has already released it;
`_admitted` releases it after `_finalize` and before `run.complete()`, and the
outer `finally` is now the no-op safety net it should always have been. Its
result is recorded as a distinct fact:

- one `ReleaseRecord(kind="claim")` naming the outcome,
- a `secondary_failures` entry, and
- `QualificationRecord.coordination_residue`, a new list that is *not*
  `engine_residue`.

Engine restoration stays a separate claim: a local coordination failure never
touches `restoration_proven` and never invents engine residue. What it does do
is keep the run from reporting `COMPLETED`, and `promotion_evidence_refusal`
refuses a record with coordination residue, so there is no complete-clean
handoff over a lock that is still held. `FileCampaignCoordinator` is unchanged:
it still never deletes another holder's claim, never removes the permanent
attempt marker, and never reclaims by age.

**The incarnation reader.** `PowerShellProcessIncarnationReader.read` called
`subprocess.run` with no timeout. Spending zero bridge operations does not bound
wall-clock time, and this reader is on the authority path that every gated
effect now consults.

- A finite local observation timeout (`LOCAL_OBSERVATION_TIMEOUT_SECONDS`) is
  passed to `subprocess.run`, so the mechanism that terminates on expiry is
  the standard one and it terminates only the owned PowerShell helper. Packet
  Tracer is never signalled. The figure is 30 s, and it is measured rather
  than chosen: one healthy read answered in 0.20-0.24 s on a warm maintainer
  machine, and the first 5 s value this delivery tried was crossed by a cold
  PowerShell start on a loaded GitHub Windows runner -- which CI caught, as
  two failing jobs, before any of it reached a review. A bound a healthy
  environment can cross is worse than no bound: an expired read is
  unobservable authority, so it stops the run and refuses its own cleanup.
- `subprocess.TimeoutExpired` is **not** swallowed into the empty string. It
  propagates, `PacketTracerDiagnosticLifecycleReader` turns it into
  `process_incarnation_unreadable:TimeoutExpired`, and the continuity gate
  reports `process_instance:unobservable:...`. A timeout is unobservable
  authority, which is a loss, not a pass.
- `PowerShellPacketTracerProcessReader` gains the same optional bound, default
  `None` so every existing CP-scale caller is unchanged, and the diagnostic
  lifecycle reader composes it with the finite value.
- The phase is charged for it. `live_authority` measures the wall clock each
  local observation costs and accumulates it into
  `BudgetRecord.local_observation_seconds`; because the ledger's allowance is
  wall-clock, those seconds already reduce what the phase may still spend.
- What is *not* promised: an absolute OS scheduling bound. Process startup,
  PowerShell initialisation and scheduler latency are outside this process's
  control. The bound is on how long this run waits, and the record says so
  through `local_process_observation_bounded_seconds:<n>`.

### Budget arithmetic after these corrections

| Stage | Planned minimum | Operation ceiling | Seconds | Reserve seconds |
| --- | --- | --- | --- | --- |
| D-DHCP | 45 | 50, unchanged | 900 -> 1500 | 180 -> 300 |
| D-WEB | 74 | 80, unchanged | 900 -> 1800 | 180 -> 300 |

No operation figure moves. The effect gate spends no bridge operation, the
terminal phase was already a planned operation, and the ping schedule
redistributes six inspections it was already counting.

The SECONDS move, and this is the one place where the protection genuinely
costs more than the earlier delivery claimed. Deciding authority before each
effect dispatch spends no operation and does spend wall-clock time: two local
process reads per decision, at most one decision per call admitted or refused
inside an effect scope, plus one per procedure and four for setup,
finalization and the two pairing readings.

What bounds the TOTAL is the ceiling itself, not a multiplication by the
per-read timeout. That timeout can be spent in full at most once, because an
expired read is unobservable authority and the loss is sticky: the run stops
and asks nothing further. Every reading that succeeds is charged to the
phase's wall clock, and once the phase has no seconds left the ledger refuses
the next call. So the seconds move to give the gate room on a slow machine,
not to cover an unreachable worst case: D-DHCP 900 -> 1500 and D-WEB
900 -> 1800, with the finalization reserve 180 -> 300 because owned cleanup
is where the per-dispatch decision matters most.

Measured, not assumed: a complete D-WEB simulation takes 46 local readings
(36 of them at effect dispatches) and a complete D-DHCP one takes 37 (28 at
effect dispatches), against 9 before this correction. A typical run therefore
spends a small fraction of the declared bound, and every record now reports
what it actually spent as `budget.local_observation_seconds`, so the figure
above can be checked against evidence rather than argued about.

These are proposed diagnostic limits that no authorization has ever been
granted against. No historical Q budget moves: Q0 20/300, Q1 60/600 and Q3
60/1200 are untouched, and the wall-clock cost of the gate exists only for
the two stages that declare a diagnostic profile.

The only other bound that moves is wall-clock inside `M-DWEB-3`: a fully
unanswered ping now occupies its whole 30-second window instead of closing at
about 25.6 seconds.

`DIAGNOSTIC_PROFILE_VERSION` moves from `2` to `3`. The step sequence and the
fixture binding are unchanged and no operation ceiling moves, but two things
an authorization buys do: the time arithmetic above, and the execution
contract itself -- effects now refuse on an unproven receiver and the
terminal observation is a guaranteed pre-cleanup phase. An
authorization written against the earlier contract must not be replayable
against this one, so the documented rule for the version is widened to cover the
execution contract as well, and the DRAFT authorization templates in the
operator contract move with it.

### One mapping from the four residual findings to their evidence

Every regression below is causal: reverting only its own fix and re-running it
produces RED for the behavioural reason, not for a missing symbol.

| Finding | Fix | Regressions that pin it |
| --- | --- | --- |
| R1 cached finalization authority | effect scopes gated in `admit()` before dispatch; per-dispatch guard over setup, E5/E6, client lifecycle, bag release and each removal | `test_a_receiver_replaced_between_two_removals_deletes_nothing_further`, `test_a_receiver_replaced_during_setup_stops_before_the_next_fixture`, `test_a_receiver_replaced_between_the_cleanup_read_and_the_delete_refuses`, `test_a_lost_campaign_claim_refuses_the_next_effect`, `test_an_effect_scope_without_a_bound_guard_refuses_before_dispatch`, `test_the_same_fixture_names_in_the_foreign_workspace_are_not_adopted`, `test_a_clean_run_still_removes_what_it_owns` (positive control) |
| R3 terminal phase reachable only on ordinary exits | registered `_TerminalPhase`, run at-most-once from the guaranteed pre-cleanup path; explicit cancellation; reader failure is secondary | `test_an_exception_after_an_intermediate_dhcp_intervention_still_reads_d4`, `test_an_exception_before_w5_still_reads_the_after_boundaries`, `test_the_terminal_payload_is_its_own_and_survives_a_reload`, `test_a_failing_terminal_reader_keeps_the_error_and_still_cleans_up`, `test_a_cancelled_run_declares_its_terminal_reading_not_taken`, `test_an_intermediate_dhcp_failure_states_which_path_it_took` |
| R4 premature closure of the ping window | explicit absolute-time schedule over the closed window, endpoint counting, elapsed-I/O treatment, deliberate `n=1` | `test_statistics_late_in_the_window_are_observed` (26 s, 29 s, 29.999 s), `test_the_old_schedule_would_have_missed_these`, `test_an_unreachable_result_late_in_the_window_is_classified`, `test_output_that_never_completes_ends_on_the_window`, `test_a_sleeper_that_cannot_honour_the_schedule_reports_the_inspection_bound`, `test_variable_io_latency_neither_bursts_nor_overruns`, `test_a_missed_slot_is_skipped_and_never_batched`, `test_a_single_inspection_reads_at_the_deadline`, `test_the_unbounded_default_is_unchanged` |
| C1 discarded release reasons, unbounded local reader | `_CampaignHold` released before immutable completion into `coordination_residue`; finite `subprocess.run` timeout with `TimeoutExpired` as unobservable authority | `test_a_failed_campaign_release_is_a_visible_durable_finalization_failure`, `test_a_raising_release_is_recorded_rather_than_lost`, `test_a_claim_that_is_no_longer_ours_is_reported_and_never_deleted` (foreign holder and unreadable lock), `test_coordination_residue_blocks_promotion_on_its_own`, `test_the_incarnation_reader_bounds_its_local_observation`, `test_an_incarnation_timeout_is_unobservable_authority` |

### Invariants added by this correction

43. Authority is decided at the dispatch that carries the effect, not once per
    phase. A decision taken for one effect authorizes exactly that effect.
44. An in-process check immediately before a dispatch is not an in-band receiver
    fence, and the record says which of the two it is.
45. A terminal read-only observation is part of finalization, so every exit that
    reaches cleanup reaches it first, and a cancelled run declares it rather
    than taking it.
46. A local finalization result belongs to the record that the run completes,
    not to the process that outlives it. Local coordination residue and engine
    residue are two claims.
47. A local observation that spends no bridge operation still spends wall-clock
    time, and its bound is declared and charged to the phase.

### Test design for this correction

The receiver switch is driven by **transport milestones**, never by the callback
that reads authority: a counting transport wrapper swaps the answering engine
after the dispatch that matches an effect signature (the first `removeDevice`,
a fixture creation, the cleanup pre-readback), and the lifecycle reader reports
the replacement from that instant. Both engine workspaces hold devices with the
same fixture names and models, and the assertions are zero `remove_calls` and
zero mutations in the foreign snapshot plus the exact named refusals - not
merely `restoration_proven=False`.

R3's regressions inject an ordinary Python exception through an injected
boundary while the engine stays readable: a `service_runtime` proxy that lets
the D3 enable dispatch for real and then raises, and a
`diagnostic_service_runtime` proxy that lets the D-WEB fetch run and then
raises. Each asserts that the fault actually fired, that the original
`exception:RuntimeError` is still the primary failure, that the terminal
measurement RAN, that its operation sequence precedes every `remove:` operation,
that its payload is unique and survives a record reload, and that it appears
exactly once. The vacuous `if record.primary_failure:` guard in the existing
`test_an_intermediate_dhcp_failure_still_takes_the_terminal_reading` is replaced
by a mandatory assertion that the intended failing path occurred.

R4 uses a fake clock whose channel releases complete statistics at a specified
**time**, not after a specified number of reads, so 26 s, 29 s and a value just
below the deadline are all distinguishable from the schedule. Each test asserts
the read timestamps, the number of inspect calls, the attribution call, the
freshness of the result and, for the composed path, the whole operation budget.

C1 injects a release failure, a foreign holder and an unreadable lock, and
asserts the lock file is still there afterwards with its original holder, the
attempt marker is untouched, the failure is visible in the completed durable
record, and `restoration_proven` is still what the engine evidence said.

### Measured verification of this correction

Every figure below was executed in this checkout with its own `.venv`, not
inferred. Nothing here observes Packet Tracer, and nothing here promotes a
capability.

| Check | Command | Result |
| --- | --- | --- |
| Full suite | `python -m pytest -q -rs` | `6826 passed, 3 skipped` at `800d6e5`, exit 0 |
| Delivery gate | `scripts/quality_gate.py --base cisco/main --delivery-commit HEAD` | clean tree at the exact commit, 101 Ruff-gated files, 0 mechanical exemptions, exit 0 |
| Namespace inventory | `scripts/namespace_inventory.py` | 0 active legacy imports, 0 active string references, 0 unreviewed inert mentions |
| Documentation | `python -m mkdocs build --site-dir _site` | built; the two `handoff.md` link warnings are unchanged from the base |
| Whitespace | `git diff --check cisco/main..HEAD` | clean |
| Exact-SHA CI | run `35552373244` at `800d6e5` | six of six jobs `success`: `quality`, `docs`, and pytest on Windows/Ubuntu x 3.11/3.13 |

The three skips are environment absences, unchanged by this correction and
named rather than counted: symlink privilege unavailable for the test account
(`test_cp_live_data_integrity.py:103`), no retained raw run in this checkout
(`test_positive_voice_ab_evidence_ledger.py:131`), and the ignored
qualification artefact absent here
(`test_positive_voice_dhcp_pool_observer.py:562`).

**Causal RED, executed.** Each fix was reverted on its own, its own
regressions were run, and the file was restored byte for byte. Every one went
RED for the behaviour, not for a missing symbol:

| Reverted fix | What the regression reported |
| --- | --- |
| R1 effect gate in `admit()` | `assert ['__MCP_E6Q_PC1', ..., '__MCP_E6Q_SRV'] == []` -- the run deleted three devices from the REPLACEMENT workspace |
| R3 guaranteed terminal phase | `assert <MeasurementStatus.NOT_RUN> is <MeasurementStatus.RAN>` -- the terminal reading never happened on the exception path |
| R4 inspection schedule | `assert (0.0, 5.0, 10.0, 15.0, 20.0, 25.0) == (0.0, 6.0, 12.0, 18.0, 24.0, 30.0)` -- the window closed one interval early |
| C1 release inside the lifecycle | `assert [] == ['campaign_claim:release_unverified']` -- the failed release left no trace in the record |
| C1 bounded local reader | `KeyError: 'timeout'` from the observed `subprocess.run` call -- the wait was unbounded |

**What CI found that offline work had not.** The first delivery of this
correction, at `0b39274`, passed everything above except exact-SHA CI, where
both Windows pytest jobs failed on
`test_one_process_and_only_a_heartbeat_is_a_clean_local_preflight` with
`process_id` `None` instead of `4242`. The five-second bound was crossed by a
cold PowerShell start on a loaded runner, so a healthy preflight came back as
unobservable authority. The control behaved exactly as designed; the figure
was wrong. It is recorded here rather than quietly amended: a bound is an
empirical claim about an environment, and this one was corrected against a
measurement (`800d6e5`) rather than against a preference.

### Delivery identity

| Field | Value |
| --- | --- |
| Delivery commit | `800d6e533903fcd36214af3de29c98b2cb896aa6` |
| Delivery tree | `74e47d5476857cedaac14905a47d8054076fea9a` |
| Branch | `feature/server-pt-goal-foundations` |
| Base | `6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main`) |
| CI run | `35552373244`, six of six successful |
| Status | `READY_FOR_REVIEW` |

Self-review is not independent acceptance. LIVE remains blocked: no
authorization exists for either stage, the effect gate is stated as a local
decision rather than an in-band receiver fence, and Q3 3/3 and Q1 2/2 stay
spent. Every diagnostic authorization in this repository stays DRAFT, and the
two stage ceilings above remain proposed limits that nothing has been granted
against.

## Lifecycle closeout after `ca808e5` (risk L)

| Field | Value |
| --- | --- |
| Checkout | `Cisco-MCP-server-services-goal-foundations` |
| Branch | `feature/server-pt-goal-foundations` |
| Correction base | `ca808e5d774dfd3cf19be6115c861c8a30f921b5` (tree `4926c4e32e3d8395b1d94b82d60663d170c43008`) |
| Authoritative main | `6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main`) |
| Risk | L - unchanged: admission, cancellation, evidence, persistence, and cleanup |

Instruction loading evidence for this Codex delivery: the user-supplied active
`AGENTS.md`, the same file in this checkout, and
`docs/engineering/standards.md` were read before the design delta or behavior
was edited. `CLAUDE.md` is Claude-specific and was not applicable to this Codex
session. No separate interactive Codex process was launched to re-list the
already supplied instruction chain, so that observation remains **pending**
rather than being reported as a pass.

### Design delta

Independent review accepted the local per-dispatch effect gate and the closed
inspection-window schedule, then identified four remaining lifecycle defects.
This correction keeps those accepted contracts, GF-R2 operational
prerequisites, ordinary-exception terminal observation, and the separation of
coordination residue from engine residue.

1. **Compose local observation with the active phase deadline.** The ledger
   checks operation and time allowance before an effect guard can launch local
   helpers, gives the guard one absolute monotonic deadline for the current
   phase, and recomputes allowance before bridge dispatch. The diagnostic
   lifecycle reader recomputes the remaining interval before each PowerShell
   helper and caps each wait at `min(30 seconds, remaining)`. Terminal
   observation spends only ordinary allowance; owned cleanup and postflight
   spend only finalization allowance. A helper that returns after its deadline
   is reported as an observed overrun, not as proof of an absolute OS bound.
2. **Keep a terminal snapshot distinct from a cumulative comparison.** D-DHCP
   always retains a successful final native snapshot. Its cumulative assessment
   accepts an optional baseline and is inconclusive with
   `native_default_baseline_missing` when no earlier snapshot exists; it never
   substitutes the final snapshot for both endpoints. An explicit unobserved
   baseline remains distinct from an absent baseline, while observed baseline
   comparisons keep their existing conclusions.
3. **Treat the first terminal cancellation as a controlled exit.** Terminal
   observation is still at most once. A first `KeyboardInterrupt` raised there
   is recorded separately, preserves any earlier primary failure and partial
   evidence, and then allows bounded finalization, claim finalization, and
   record completion to run before the established cancellation outcome is
   propagated. Cancellation before the terminal phase keeps its existing
   no-terminal-work behavior. Repeated interruption, process death, and force
   termination remain outside this guarantee.
4. **Finalize a campaign claim for every post-claim exit.** One idempotent hold
   owns release and its projection. It distinguishes no claim, successful
   release, ordinary release failure, a retained foreign claim, and a malformed
   claim. When a writable record exists, the release fact is projected before
   immutable completion; otherwise it is returned through the qualification
   result. The original refusal remains the refusal, no failed release permits
   Packet Tracer contact, and foreign lock and attempt bytes are never removed.

The application layer continues to own admission and orchestration, the
infrastructure readers continue to own OS/process work, and the domain evidence
service continues to decide comparison meaning. No transport, receiver
protocol, dispatcher, parser, `.pts`, watchdog, or generalized workflow is
added. Packet Tracer, bridge startup for product use, GUI automation, LIVE
campaigns, claim reset, force push, and merge to `main` remain excluded.

### Lifecycle exit matrix and requirement-to-test mapping

The regressions use the real coordinator, record store, generated JavaScript,
Node stub engine, and fake monotonic clock. They assert effects and durable
facts rather than copied classifiers. Representative combinations cover the
boundaries without a Cartesian expansion.

| Requirement | Representative exit | Regression evidence |
| --- | --- | --- |
| CA-01 composed deadline | zero or one second of ordinary allowance; two sequential successful local helpers; finalization near its deadline | `test_effect_guard_refuses_before_a_zero_time_authority_read`, `test_lifecycle_reader_shares_one_deadline_across_both_helpers`, `test_terminal_observation_cannot_borrow_cleanup_time`, `test_finalization_reports_a_local_observation_deadline_overrun`, plus a normal positive control |
| CA-02 real baseline only | runtime construction raises after fixture setup and before baseline assignment; absent, explicit-unobserved, and observed baselines | `test_d_dhcp_retains_the_terminal_snapshot_without_manufacturing_a_baseline`, `test_cumulative_native_default_requires_a_real_observed_baseline`, and the existing valid-comparison controls |
| CA-03 first terminal cancellation | normal stage body, first cancellation from the terminal reader; ordinary terminal error and cancellation-before-terminal controls | `test_first_terminal_cancellation_still_finalizes_releases_and_persists`, `test_a_failing_terminal_reader_keeps_the_error_and_still_cleans_up`, and `test_a_cancelled_run_declares_its_terminal_reading_not_taken` |
| CA-04 complete claim lifecycle | refusal after admission, build refusal, record-begin failure, unavailable transport after record creation, and admitted completion | `test_claim_release_failure_survives_pre_record_admission_refusal`, `test_claim_release_failure_survives_build_refusal`, `test_claim_release_failure_survives_record_begin_refusal`, `test_claim_release_failure_is_durable_on_transport_refusal`, and the existing admitted-run controls |

### Invariants added by this closeout

48. No local authority observation starts without positive time in its active
    phase, and no bridge dispatch relies on allowance measured before that
    observation.
49. One local lifecycle observation has one absolute monotonic deadline; every
    helper receives only its remaining share, capped by the existing per-helper
    policy.
50. A point-in-time terminal snapshot is evidence of current state only. A
    cumulative comparison requires a distinct, actually observed earlier
    baseline.
51. The first controlled cancellation from terminal observation cannot skip
    bounded finalization or claim projection, and it cannot restart terminal or
    experimental work.
52. Claim release is finalized exactly once for every acquired claim, before a
    writable record becomes immutable; release failure is additional local
    evidence and never changes the original refusal into permission.

### Independent-review correction to this closeout

The read-only review of `8de5d3574e45bfb9db1130dc5c68980cbaa29bba`
found two incomplete exits and one classification edge inside the approved
CA-03/CA-04 contract. The correction is narrower than a redesign:

- the invocation creates its `_CampaignHold` before `_diagnostic_admission`,
  and that same top-level `try/finally` covers claim acquisition plus every
  fallible admission check. A first cancellation after acquisition releases
  exactly once, propagates exit 130, and carries the release fact through the
  CLI error boundary when no record exists;
- `_d_web_after` places the completed listener/endpoint reading immediately in
  `M-DWEB-5.facts` before starting its next reader. A later cancellation leaves
  the measurement not-run/cancelled but retains the actual partial payload;
  ordinary completion still replaces it with the existing complete assessment;
- the file coordinator treats valid JSON with an invalid claim structure as
  malformed, not as evidence of another holder. Both malformed and foreign
  bytes remain untouched, and release never reclaims either.

| Review finding | Causal regression |
| --- | --- |
| acquired claim outside admission cancellation finalization | `test_pre_record_cancellation_releases_claim_and_reports_outcome` |
| completed W5 listener payload lost on the next cancellation | extended `test_first_terminal_cancellation_still_finalizes_releases_and_persists` assertions over the reloaded `listeners_after` payload |
| malformed JSON structure labeled as a foreign holder | extended `test_a_claim_that_is_no_longer_ours_is_reported_and_never_deleted` cases for `[]` and `{}` |

## Residual-finding closure audit at `7f39314` (risk L)

| Field | Value |
| --- | --- |
| Checkout | `Cisco-MCP-server-services-goal-foundations` |
| Branch | `feature/server-pt-goal-foundations` |
| Audit base | `7f39314b83cada5a36efcfc44f25f5e0f97199d3` (tree `7c0a0530cf9ee8c9ef33f6f659c1f1c4663d74b2`) |
| Authoritative main | `6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main`) |
| Assignment | the independent read-only review of `5db6916`: R1, R3, R4, C1 |
| Risk | L block. This delta changes no production module and buys no new contract |

The assignment named `5db6916` as its starting SHA. This checkout was already
six commits past it, on the corrections that answer the same review
(`d901eca` through `7f39314`), so the changed baseline was inspected rather
than reset. What remained was to check each residual finding against the code
that is actually here, close whatever was still open, and record the result
instead of restating the earlier delivery's claims.

Instruction loading evidence for this Claude Code session: `AGENTS.md` (8749
bytes, `sha256:a9f0e384fa952f16...`), `docs/engineering/standards.md` (13688
bytes, `sha256:2de0d5b20545fcf8...`) and `CLAUDE.md` (616 bytes,
`sha256:293122019c22763d...`) were read from this checkout, not from a copy,
before any edit. `/context` is an interactive command this session cannot
issue, so the Claude Code memory-source observation that `CLAUDE.md` asks for
is reported as **pending** rather than as a pass.

### Disposition of the four residual findings

| Finding | State found at `7f39314` | Left open |
| --- | --- | --- |
| R1 effect boundary | Closed. `OperationLedger.admit` consults the effect guard immediately before each dispatch inside an effect scope, an unbound guard refuses (`effect_guard_not_bound`), the first loss is sticky, allowance is recomputed after the local read, and the unfenced interval between the answer and the receiver consuming the command is declared on every record | One required regression. The review listed a same-PID/changed-incarnation replacement among the R1 cases and required every R1 regression to switch the receiver at a transport or effect milestone. That case existed only in `test_a_reused_pid_at_the_authorized_path_is_not_the_bound_process`, which switches on a count of authority readings -- inside the control under test |
| R3 guaranteed terminal phase | Closed. `_TerminalPhase` is registered before the stage's first procedure and taken at most once from the `finally` that every exit reaches, ahead of the first deletion; unsafe, unaffordable, reader-failure and cancelled paths each produce a named absence | One assertion. The review asked for the `if record.primary_failure` guard to be replaced; a mandatory replacement was added in a new file while the original guard stayed in place and kept running |
| R4 inspection schedule | Closed. `inspection_schedule` returns the endpoints of the closed window (`0, 6, 12, 18, 24, 30`), a single inspection reads at the deadline with no division, missed slots are dropped rather than batched, and the unbounded default is untouched | Nothing |
| C1 release reasons and bounded readers | Closed. One `_CampaignHold` finalizes the claim exactly once for every post-claim exit and projects the release fact before the record becomes immutable, distinct from engine residue; both PowerShell helpers carry a finite timeout that `TimeoutExpired` turns into unobservable authority | Nothing |

### Design delta

Three test corrections and this record. No production module, contract,
budget, invariant or profile version moves, so no new RED-first behavioural
fix was warranted and none was manufactured. `DIAGNOSTIC_PROFILE_VERSION`
deliberately stays at `3`: the closeout after `ca808e5` closed defects inside
the version-3 terms rather than changing what an authorization buys, and no
authorization has ever been issued against any of them. A reviewer who reads
that differently should say so; it is stated here rather than left implicit.

1. **A reused PID is a replacement, and the milestone is the transport's.**
   The `replaced_at` fixture now accepts the pairing the local reader answers
   with from the milestone onward, defaulting to the different-PID case it
   always used. `test_the_same_pid_with_a_new_incarnation_stops_the_next_removal`
   reissues the authorized PID at the authorized path with a later creation
   time, switched by the first `removeDevice` returning, and asserts that the
   one authorized removal landed on the bound instance, that the replacement's
   identically named fixtures were neither mutated nor deleted, that the three
   remaining removals are named refusals carrying
   `execution_authority_lost`, and that restoration is not claimed.
2. **The conditional guard is gone from the file that still carried it.**
   `test_an_intermediate_dhcp_failure_still_takes_the_terminal_reading`
   guarded its body with `if record.primary_failure` and then accepted
   "reading taken **or** explicitly declared not taken", which passes whichever
   occurred. Measured: the guard was true, so the body ran, but the
   disjunction could not distinguish the defect from the fix. It now asserts
   the failing path by name (`d_dhcp_baseline_not_established:`) and that the
   terminal reading was taken.
3. **D-DHCP's no-client-activation claim is read while the clients exist.**
   `test_d_dhcp_runs_the_server_only_sequence_and_activates_no_client`
   asserted `devices == {} or all(not port.get("dhcp_mode") ...)` over a
   snapshot taken after owned cleanup. Measured: after a clean D-DHCP run the
   stub holds `[]` devices and `remove_calls` of all four fixtures, so the
   left branch always won and the port check never evaluated a single port.
   The snapshot is now taken at the last instant the fixtures exist --
   immediately before the first destructive dispatch -- and the test asserts
   the four fixture names and that no port among the six carries `dhcp_mode`.
   This is a safety claim of the stage (no client is ever put into DHCP mode),
   and it was unverified.

### Requirement-to-test mapping for this delta

| Requirement | Regression | Evidence that it can fail |
| --- | --- | --- |
| R1: a replacement that reuses the authorized PID is refused at the next effect, injected at a transport milestone | `test_the_same_pid_with_a_new_incarnation_stops_the_next_removal` | Causal RED: with the effect-guard branch in `OperationLedger.admit` disabled and nothing else changed, `assert ['__MCP_E6Q_PC2', '__MCP_E6Q_PC1', '__MCP_E6Q_SRV'] == []` -- the run deleted three devices from the replacement's workspace. The source file was restored byte for byte (`git diff` clean) |
| R3: the intended failing path is asserted, not guarded | `test_an_intermediate_dhcp_failure_still_takes_the_terminal_reading` | Not a behaviour change, so no RED is manufactured. The old form's weakness was measured instead: the disjunction accepted `RAN` and `not_observed:` alike, so it could not have failed for the defect it was written against |
| Acceptance: D-DHCP activates no client | `test_d_dhcp_runs_the_server_only_sequence_and_activates_no_client` | Not a behaviour change. The old form's vacuity was measured: the post-cleanup snapshot is `devices == []`, so the left branch of the disjunction always satisfied the assertion. The new form reads four devices and six ports |

### Invariants this delta protects

No new invariant is added. It restores enforcement of two that were already
claimed: invariant 43's per-dispatch receiver decision now has a regression
for the replacement a PID comparison cannot see, and D-DHCP's server-only
sequence now has an oracle for the client ports it promises never to touch.

### Independent causal RED for all four residual findings

The earlier delivery recorded its own revert battery. This session re-ran one
independently rather than citing it, because a table is not an observation.
Each fix was disabled alone, its own regressions were run, and the file was
restored byte for byte; after the battery `git status` reports only the three
test files of this delta.

| Reverted fix | Regression run | What it reported |
| --- | --- | --- |
| R1 effect-guard branch in `OperationLedger.admit` | `test_the_same_pid_with_a_new_incarnation_stops_the_next_removal` | `assert ['__MCP_E6Q_PC2', '__MCP_E6Q_PC1', '__MCP_E6Q_SRV'] == []` -- three devices deleted from the replacement's workspace |
| R3 `_observe_terminal` in the pre-cleanup `finally` | `test_an_exception_after_an_intermediate_dhcp_intervention_still_reads_d4` | `assert <MeasurementStatus.NOT_RUN> is <MeasurementStatus.RAN>` with an empty `reason`, after the injected `RuntimeError` had already been asserted to have fired |
| R4 endpoint counting in `inspection_schedule` | `tests/test_typed_ping_schedule.py` | `assert (0.0, 5.0, 10.0, 15.0, 20.0, 25.0) == (0.0, 6.0, 12.0, 18.0, 24.0, 30.0)`, and nine further failures at 25.7 s, 29.25 s and the window edge |
| C1 claim release inside the lifecycle | `test_a_failed_campaign_release_is_a_visible_durable_finalization_failure` | `coordination_residue` was missing `campaign_release_failed:OSError` |
| C1 bounded local reader | `test_the_incarnation_reader_bounds_its_local_observation` | `KeyError: 'timeout'` from the observed `subprocess.run` call |

### Measured verification of this delta

Every figure was executed in this checkout with its own `.venv`. Nothing here
observes Packet Tracer, launches it, contacts a bridge, or promotes a
capability. No campaign attempt was spent.

| Check | Command | Result |
| --- | --- | --- |
| Focused | `pytest tests/test_diagnostic_residual_corrections.py tests/test_diagnostic_focused_corrections.py tests/test_typed_ping_schedule.py tests/test_server_diagnostic_stages.py tests/test_service_qualification_lifecycle.py -q` | `143 passed`, exit 0, after the revert battery restored every source file |
| Full suite | `python -m pytest -q -rs` | `6842 passed, 3 skipped`, exit 0, 476.81 s |
| Provisional gate | `scripts/quality_gate.py --base cisco/main` | base and merge base both `6263344e`, 101 changed Python files, 101 Ruff-gated, 0 mechanical exemptions, exit 0 |
| Namespace inventory | `scripts/namespace_inventory.py` | 0 active legacy imports, 0 active string references, 0 unreviewed inert mentions (65 retained in 22 files), exit 0 |
| Documentation | `python -m mkdocs build --site-dir _site` | built in 4.22 s; the two `handoff.md` link warnings are unchanged from the base |
| Whitespace | `git diff --check` and `git diff --check cisco/main..HEAD` | both clean |

The three skips are the same named environment absences as the previous
delivery, not a count: symlink privilege unavailable for this test account
(`test_cp_live_data_integrity.py:103`), no retained raw run in this checkout
(`test_positive_voice_ab_evidence_ledger.py:131`), and the ignored
qualification artefact absent here
(`test_positive_voice_dhcp_pool_observer.py:562`).

### Delivery identity of this audit

| Field | Value |
| --- | --- |
| Delivery commit | `f9afa1b4d726b7eed859c4452e2f8be3c835af97` |
| Delivery tree | `ce65be8d4a789a56975bfa688621fe13a5c7d192` |
| Branch | `feature/server-pt-goal-foundations` |
| Base | `6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main`) |
| Delivery gate | `scripts/quality_gate.py --base cisco/main --delivery-commit HEAD`: clean tree at the exact commit, 101 Ruff-gated files, 0 mechanical exemptions, exit 0 |
| CI run | `35627312782`, six of six jobs `success`: `quality`, `docs`, and pytest on `windows-latest` and `ubuntu-latest` x Python 3.11 and 3.13 |
| Status | `READY_FOR_REVIEW` |

Self-review is not independent acceptance, and this audit does not accept the
earlier corrections on the reviewer's behalf. What it establishes is narrower
and stated as such: the four residual findings of the `5db6916` review are
closed in the code that is in this checkout, three required test obligations
that were still open are now met, and the offline verification above was
executed rather than cited.

What remains out of reach here is unchanged. The effect gate is an in-process
decision immediately before each dispatch, not an in-band receiver fence, and
every diagnostic record says so. No LIVE run is authorized, none was started,
no Packet Tracer process was launched, contacted or terminated, and no
product bridge was started. Q3 3/3 and Q1 2/2 stay spent, every diagnostic
authorization stays DRAFT, and both stage ceilings remain proposed limits that
nothing has been granted against. Offline CI does not prove Packet Tracer
behaviour, and a green suite is not evidence of LIVE isolation.

## 2026-09-21 corrective successor: Packet Tracer process cohort

### Problem and observed cause

Campaign `SERVER-PT-DIAG-0EA-01` was granted for D-DHCP v3 and D-WEB v3 with
the documented local receiver limitation accepted. Before any CLI invocation,
the production lifecycle reader observed
`packet_tracer_process_count:2`. The exact installed 9.0.1 launch produced one
primary `PacketTracer.exe` and one child of the same executable whose command
line is `--progress-bar-server`. No request was published and no attempt
identity was reserved.

The cause is in `PowerShellPacketTracerProcessReader`: it enumerates every
process whose name starts with `PacketTracer` using `Get-Process`, which does
not retain `ParentProcessId` or `CommandLine`. The lifecycle reader therefore
cannot distinguish the exact progress helper from a second receiver. This is
not a new environment model. The maintained PoE runner already treats exactly
one primary plus at most one same-path, direct-child
`--progress-bar-server` process as one runtime cohort, and historical Server-PT
evidence records that this helper is windowless and owns no mailbox.

### Scope, exclusions and invariants

This L-risk autofix changes only local process observation and its tests. The
shared reader will retain `ParentProcessId` and `CommandLine` long enough to
classify the cohort, return only the primary receiver for authority pairing,
and accept a helper only when all of these facts are observable: one primary,
at most one helper, the helper is a direct child of that primary, and both
resolve to the same executable path. Missing or malformed identity fields, a
helper without a primary, multiple helpers, a wrong parent/path, or multiple
primaries remain refusal evidence. The primary PID/path/version/incarnation,
mailbox gate, campaign claim and per-dispatch continuity rules are unchanged.
The reader keeps its pre-existing injected single-row payload contract when
both new classifier keys are absent; the production PowerShell command always
emits both keys, and an emitted null or malformed value refuses rather than
falling through that compatibility path.

No Packet Tracer API, transport, budget, profile, selected step, capability
claim or historical record changes. The campaign's reviewed initial SHA/tree
will be replaced only by a committed corrective successor with its own exact
tree and green exact-SHA CI. The already launched process is preparation only;
it is not reused as a successor attempt. Force termination remains
unauthorized.

### Requirements and verification

| Requirement | Acceptance evidence |
| --- | --- |
| One primary plus its exact progress helper denotes one receiver cohort | RED first: the real two-row process payload currently yields two candidates; after the fix the shared reader returns only the primary, and the lifecycle reader binds its PID/path/version/incarnation |
| The helper classification cannot hide a competing or unobservable process | Tests reject missing/malformed command line or parent identity, helper-only, multiple-helper, wrong-parent and wrong-path cohorts; two primaries remain two and are refused by the lifecycle gate |
| Existing single-primary readers remain compatible | The shared process-reader suite and lifecycle suite retain their single-process positive controls and typed failure paths |
| The corrective successor is the only executable candidate | Focused reader/lifecycle/diagnostic tests, affected suites, full pytest, provisional and delivery quality gates, namespace inventory, MkDocs, whitespace, clean commit and exact-SHA CI pass before a fresh LIVE attempt |

### Measured autofix verification

The original reader was run against the dedicated launch before this edit and
returned `packet_tracer_process_count:2`. The OS facts were one primary PID
47056 and one PID 47164 child with the same executable path and the exact
`--progress-bar-server` argument. The mailbox contained no `req_*` or `res_*`
artifact, no campaign claim existed, no CLI invocation had started and no
attempt identity had been reserved.

The new regression first failed with `(47056, 47164) != (47056,)`. After the
minimal correction, the production reader run against that same live cohort
returned only PID 47056 with product/file version `9.0.1.0858`; the lifecycle
reader bound its executable path and creation timestamp and observed an empty
mailbox. This process is preparation evidence only and is not reused for the
corrective successor's attempt.

| Check | Result |
| --- | --- |
| Focused reader RED/GREEN | the causal test failed on the two returned PIDs, then the positive and seven fail-closed cohort cases passed |
| Affected tests | `215 passed`, exit 0 |
| Provisional quality gate | base/merge-base `6263344e`, 102 changed Python files Ruff-gated, no mechanical exemption, exit 0 |
| Full suite | `6850 passed, 3 skipped, 3 pre-existing warnings`, exit 0, 548.43 s |
| Namespace inventory | 0 active legacy imports, 0 active string references, 0 unreviewed inert mentions, exit 0 |
| MkDocs | built in 3.77 s, exit 0; the two `handoff.md` warnings are unchanged |

## 2026-09-21 D-DHCP attempt 1: pending response closeout

### Recorded LIVE boundary

The corrective successor `7660bd104c9947badca6010d92d84337976282e0`
(tree `663c83e39cdf90c381d48dc2e549c749dcb0fc07`, exact-SHA CI
`35640377135` six of six green) ran D-DHCP v3 attempt ordinal 1 under campaign
`SERVER-PT-DIAG-0EA-01`. The record is
`2026-09-21T19-09-40Z-876af922`, attempt identity
`1cec3a925255de16907519d1c2919fed`. All five diagnostic measurements ran in
41 operations. The campaign claim released, semantic device/link cleanup and
both restoration reads completed, but the immutable record correctly ended
`stopped`: postflight observed
`res_34708_dd72195a_000022.txt`, set `restoration_proven=false`, and retained
`lifecycle:mailbox:not_drained:...` as a secondary failure. No D-WEB attempt
started.

The response name binds it to operation 22, the only fire-and-forget `send`:
`d-dhcp:product:e5_server_address`. The file disappeared by the later evidence
copy without operator deletion, consistent with the engine's bounded orphan
purge. The record, authorization, stdout, stderr, exit code, process/mailbox
snapshots and hashes were preserved under the campaign evidence directory
before recovery. The failed process received only normal close requests and
remains running; force termination is not authorized.

### Causal defect and minimal correction

`FileBridge.send()` retains each fire-and-forget name in `_pending` and calls
`collect_completed()` only before another `send`. The D-DHCP E5 operation is
followed exclusively by `send_and_wait`/`dispatch_and_wait`, so its completed
response is never retired by Python. The Script Engine may remove the request
and publish the response correctly while the client still carries the pending
name through finalization. This is an integration defect in the existing
instrument, not a native negative and not permission to reinterpret attempt 1.

The file transport will collect completed fire-and-forget responses before and
after every synchronous request. The application finalizer will perform one
last local collection before lifecycle postflight and query the transport's
pending state. If a pending send remains, the record names transport residue,
sets restoration false and stops even when the directory happens to be empty;
it never waits speculatively, replays the mutation, or deletes a foreign
artifact. Transports without this optional local lifecycle surface preserve
their existing behaviour.

### Requirements and tests

| Requirement | Acceptance evidence |
| --- | --- |
| A completed asynchronous response is retired during later synchronous traffic | RED/GREEN file-bridge regression for both `send_and_wait` and `dispatch_and_wait`, asserting request, response and in-memory pending state are all cleared |
| A last completed asynchronous response is retired before postflight | Finalizer regression supplies a transport whose collector resolves its pending state and requires an empty postflight plus preserved restoration claim |
| An unresolved pending send cannot be reported clean | Finalizer regression retains the pending state with an empty mailbox observation and requires named transport residue, `stopped`, and `restoration_proven=false` |
| The failed ordinal is immutable and no scope widens | attempt 1 artifacts/hashes remain unchanged; no budget/profile/API/step/channel change; any second D-DHCP attempt uses a fresh process, instance token and attempt identity at a new exact-SHA green successor |

### Measured autofix verification

The file-bridge regression failed first because the earlier `res_*` survived
the synchronous call. After the owning-layer correction, both synchronous
paths retire it. The application regressions independently establish that a
resolved pending send permits the ordinary clean result, while an unresolved
one produces `transport:pending_fire_and_forget`, stops the record and removes
the restoration claim even when its lifecycle observation reports an empty
directory.

| Check | Result |
| --- | --- |
| Causal RED/GREEN | initial `send_and_wait` case failed on one retained `res_*`; final focused set `4 passed`, exit 0 |
| Affected suite | `268 passed`, exit 0 |
| Provisional quality gate | base/merge-base `6263344e`, 104 changed Python files Ruff-gated, no mechanical exemption, exit 0 |
| Full suite | `6854 passed, 3 skipped, 3 pre-existing warnings`, exit 0, 548.20 s |
| Namespace inventory | 0 active legacy imports, 0 active string references, 0 unreviewed inert mentions, exit 0 |
| MkDocs and whitespace | build exit 0 in 3.92 s with the two unchanged `handoff.md` warnings; `git diff --check` exit 0 |

## 2026-09-21 diagnostic closeout and product readiness at `5296984` (risk L)

The diagnostic campaign `SERVER-PT-DIAG-0EA-01` finished its measurements. This
block does three separable things and deliberately joins none of them: it closes
the campaign's evidence chain additively, it gives the product HTTP workflow a
bounded read-only forwarding prerequisite, and it turns the measured DHCP
native-default transition into an executable pure assessment without promoting
allocation. No part of it launches, contacts or terminates Packet Tracer,
re-runs a stage, edits an earlier envelope, recreates a missing historical fact
or promotes a capability.

### Identity of this delta

| Field | Value |
| --- | --- |
| Checkout | `Cisco-MCP-server-services-goal-foundations` |
| Branch | `feature/server-pt-goal-foundations` |
| Base commit | `52969849408d195436ae250f611318e7e959876f` (tree `62f569e5311771e378a54f5b7aeab1d9abe480c7`) |
| Authoritative main | `6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main`) |
| Reviewed CI on the base | `35646191228`, six successful jobs |
| Risk | L - public report contract, product verification authority, evidence semantics |

Instruction loading evidence: `AGENTS.md`, `CLAUDE.md` and
`docs/engineering/standards.md` were read from this checkout before planning.
Their working-tree SHA-256 digests are `a9f0e384fa952f16a473af47f12f7d67ab3a88ae47ad818040f9ffa09dfae81b`,
`293122019c22763d7637807ef3a7ea12c1b13711cd527250d04a5ed1b4824516` and
`2de0d5b20545fcf8b405bfbe09316af4b4587fa5fa2bc0915e459f8cc0503178`, byte-identical
to the digests the previous block recorded, so the three files did not move
between deliveries. As before, an interactive `/context` listing cannot be
observed from a non-interactive session, so that check stays **pending** rather
than a pass.

### What the carried-forward evidence does and does not say

These are the accepted readings this block builds on. None of them is widened
here.

| Reading | What it establishes | What it does not establish |
| --- | --- | --- |
| D-DHCP attempt 1 at `7660bd1`, record `2026-09-21T19-09-40Z-876af922`, `stopped` | a retained postflight response and `restoration_proven=false` | nothing about the native default; the attempt stays immutable and is not reinterpreted |
| D-DHCP attempt 2 at `5296984`, record `2026-09-21T20-01-43Z-dffd6c3b`, `completed`, 41 of 50 operations | six native-default snapshots localize the first difference to the WHOLE `configurePcIp` interval, on exactly four fields: `network`, `mask`, `start`, `end` | no client acquisition was measured; pool configuration while disabled and process enable added no further difference, which is not evidence that the intended pool will serve a client |
| D-WEB at `5296984`, record `2026-09-21T20-09-02Z-e294177e`, `completed`, 63 of 80 operations | W1 observed VLAN 1 `Fa0/1`-`Fa0/3` in `LIS` (`NON_FORWARDING`); the HTTP client observed its marker at its first performed inspection, offset 4.359 s, and again at the late control; one of four ping packets returned with unique source attribution and stable bindings | the `FWD` sample belongs to W5 AFTER the fetch, so no "ping caused STP forwarding", no cold-path success and no product-level cause |

The native default and the intended pool share subnet `192.0.2.0/24`, and the
realigned native range `192.0.2.0`-`192.0.3.255` contains the intended pool's
single address `192.0.2.100`. Stored coexistence is therefore not proof that the
intended pool would answer a request.

### A. Additive evidence closeout

The campaign package stays exactly as the operator holds it, at
`C:\Users\Andres\Desktop\SERVER-PT-DIAG-0EA-01` with its archive
`SERVER-PT-DIAG-0EA-01-FINAL-5296984.zip`. Nothing in it was edited, moved,
renamed or repaired. The addendum is a new directory with its own index and its
own digest list; it rewrites no attempt file, no manifest and no earlier
envelope, and it creates no "final" history.

#### What was verified, and how

Every digest below was recomputed from the bytes on disk in this delivery.

| Check | Scope | Result |
| --- | --- | --- |
| Archive identity | `SERVER-PT-DIAG-0EA-01-FINAL-5296984.zip` | measured SHA-256 equals the `d30eeabc...755c11` the work order states, and equals the operator's sidecar `.sha256` |
| `FINAL-MANIFEST.sha256` | 7 entries | all 7 match, including the three permanent attempt markers read in place |
| Per-attempt `manifest.sha256.json` | 8 + 9 + 8 = 25 entries | all 25 match |
| Archive against the extracted tree | 30 members, 223,052 bytes | every member is byte-identical to its extracted file |
| Total | 62 comparisons | 0 mismatches, 0 missing |

#### The three permanent attempt markers are recovered and byte-verified

They were never lost. They are in the shared campaign scope,
`%LOCALAPPDATA%\packet-tracer-mcp\bridge\campaign`, where the coordinator
deliberately leaves them, and `FINAL-MANIFEST.sha256` names them by that exact
path. Each is 160 bytes and each matches the manifest digest that already
existed:

| Marker | Manifest SHA-256 | Measured | Runner PID and claim |
| --- | --- | --- | --- |
| `attempt-1cec3a925255de16907519d1c2919fed.json` | `7d31cc42...aaaadb` | equal | 34708, `2026-09-21T19:09:40.187624+00:00` |
| `attempt-08a06b738839b6f48f4b24516089ac09.json` | `3b102060...910aa1` | equal | 39124, `2026-09-21T20:01:43.405474+00:00` |
| `attempt-f2148bbd568a49391a26e83c6efcc67e.json` | `95e2de98...149992` | equal | 57572, `2026-09-21T20:09:01.358759+00:00` |

Each marker also binds to exactly one delivered record through
`authorization.attempt_id`, one-to-one with no leftover on either side, so the
identity chain holds independently of the manifest as well as through it.

#### The post-restart census was retained

`processes-postrun.json`, `mailbox-postrun.json` and `campaign-postrun.json`
exist for all three attempts and are covered by the verified per-attempt
manifests, so the historical observation needs no reconstruction and none was
attempted. They record the Packet Tracer instance cohort of each attempt (parent
PIDs 50940, 25248 and 7704 with their child renderer processes, all from
`C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe`) and a mailbox
holding only `alive.txt` at each attempt end.

A new read-only OS census was taken in this delivery as a separate,
current-state-only observation, and it is labelled as such: at
`2026-09-21T21:53:27Z` no Packet Tracer process is running, the three runner
PIDs and the three instance PIDs are absent, and the mailbox holds no `req_*`
and no `res_*`, only `alive.txt` last written `2026-09-21T20:12:43Z` beside the
campaign subdirectory. That the attempt-1 instance is absent **now** is a later
fact about a different moment and is not evidence about how it ended.

#### The force-termination sequence, preserved rather than reconciled

Four dated statements, each left exactly as its own artifact records it:

| When | Artifact | What it says |
| --- | --- | --- |
| `2026-09-21T19:09:39Z` | D-DHCP attempt 1 `authorization.json` | `force_termination_authorized: false` |
| `2026-09-21T20:01:40Z` | D-DHCP attempt 2 `authorization.json` | `force_termination_authorized: false` |
| `2026-09-21T20:07:16Z` | D-DHCP attempt 2 `retirement-observation.json` | `authorized_force_termination: true`, `force_termination_performed: false`, reason `exact_primary_absent_before_action`, an empty process list |
| `2026-09-21T20:08:58Z` | D-WEB `authorization.json` | `force_termination_authorized: true` |

The operator lifecycle permission therefore arrived between `20:01:40Z` and
`20:07:16Z`, and the retirement record states in its own fields that the
exactly identified process was already absent before any action, so force
termination was **authorized and not performed**. No earlier envelope is edited
to agree with a later one, and consent is not inferred from an envelope's own
fields. `CAMPAIGN-INDEX.md` carries the operator's acceptance of the local
receiver-gate limitation and the grant of D-DHCP v3 and D-WEB v3, and is itself
covered by the verified manifest.

Nothing in A was blocked, so B and C proceed on verified rather than partial
evidence. No Packet Tracer launch, contact, termination, command publication,
wildcard cleanup or marker recreation was needed or performed, and the addendum
adds no authority of any kind.

### B. Product HTTP: one bounded read-only forwarding prerequisite

#### Problem

`observe_access_forwarding` and `access_forwarding_admission` already exist and
are already correct, but nothing in the product path calls them: their only
callers are the diagnostic stages in `qualify_server_services`. The public
workflow therefore issues its first HTTP client request with no statement about
whether the access ports on the path forward user frames, which is exactly the
boundary D-WEB left unresolved. A port that is up and a green light are not that
statement, and the existing gate cannot be "demonstrated and reused" because in
this composition it is never reached.

#### Scope

In scope: one operational-readiness prerequisite in front of the HTTP-family
verification expectations of `apply_enterprise_services`, derived from the
compiled plan, observed through the existing runtime observation, decided by the
existing domain admission, and persisted with its relationship to the dependent
requests.

Excluded, explicitly: any change to the four-argument MCP signature; a second
service subsystem; a duplicated spanning-tree parser; any copy of the Voice
`wait_for_voice_access_forwarding` semantics, its PVST learning extension or its
simulation-time window; a user-facing switch or environment variable that can
skip readiness; gating `dns_resolution` or any non-HTTP kind; reordering the
existing expectation DAG; a ping, PortFast change, link bounce, clock
acceleration, extra warming request or arbitrary sleep; and any topology
deletion.

#### Design

Readiness is a third concern, kept separate from configuration application,
service eligibility and behavioural verification, and it never becomes one of
them.

1. **Derivation is pure and comes from the plan.** A new domain service,
   `domain/enterprise/services/service_access_readiness.py`, reads the compiled
   `ConfigureAccessPort` actions and the HTTP-family verification expectations
   and returns one requirement per `(switch device, data VLAN)` group. A group
   carries the exact interface set the paths need - the client's access port and
   the host's access port for every dependent expectation - plus, per
   expectation, the client identity it belongs to. The sources are
   `ConfigureAccessPort.device_id`/`device_name`/`interface`/`data_vlan_id`/`endpoint_ids`
   and the expectation's `host_device_id`/`client_device_id`. No fixture name,
   interface-number ordering or diagram position participates, and a group is
   keyed on the switch's semantic device id while its deployed name travels
   alongside for the query. Two things the plan cannot place become two separate
   refusals: an endpoint on no access port at all makes its dependent
   unsatisfiable by construction, naming that endpoint, and a request whose two
   ends sit on different switches or different VLANs is not a single-segment
   path, so it belongs to no group and is reported as
   `path_not_single_switch_and_vlan`. Neither ever silently drops out of the
   required set.
2. **Observation is bounded, read-only and reuses the existing instrument.** A
   new application port, `AccessForwardingObserver`, declares exactly the
   existing `observe_access_forwarding` surface.
   `PacketTracerEnterpriseConfigurationRuntime` already satisfies it, so the
   product composition binds the runtime it already has. The observation runs
   once per group, lazily, immediately before the first dependent HTTP request,
   and its result is memoized for that group inside the same invocation. Four
   client expectations on one switch and VLAN therefore cost one grouped query,
   not four.
3. **Admission is the existing domain decision.** `access_forwarding_admission`
   decides; `access_forwarding_facts` renders. `LIS`/`LRN`/`BLK`, a missing or
   duplicated interface, an absent VLAN instance, stale or truncated output, a
   wrong or unattributed device identity, an exhausted sample budget and a
   deadline all refuse on their own named dimension, and none of them authorizes
   HTTP.
4. **Bounds are enforced where they execute.** Per group: the observer's own
   `max_samples`, `deadline_seconds`, `interval_seconds` and per-sample
   `sample_calls`, unchanged at 3 / 30.0 s / 1.0 s / 6. Across groups:
   `READINESS_TOTAL_BUDGET_SECONDS` (120.0) read from the injected clock and
   `READINESS_MAX_GROUPS` (4), both checked before the next observation is
   started, so a plan with many groups cannot extend the run by multiplying
   bounded waits. A refused budget is a precise blocked result, never a silent
   pass.
5. **A blocked request is named for what actually blocked it.** A dependent
   expectation whose group was not admitted is recorded
   `DEPENDENCY_BLOCKED` with the new failure code
   `ACCESS_FORWARDING_NOT_READY`, observation `NOT_ATTEMPTED`, and a message
   naming the refusing dimension, the switch, the VLAN and the interfaces. It is
   never reported as a listener failure, a fetch failure or a capability
   problem, because the request was not made.
6. **Absence of an observer is a refusal, not a bypass.** A composition that
   supplies no observer while HTTP-family expectations exist blocks them with
   cause `observer_unavailable`. There is no flag, argument or setting that
   turns readiness off.
7. **The evidence is persisted with its dependents.** `ServiceStageResult` gains
   `operational_readiness`: one row per group with the full
   `access_forwarding_facts` sample, the requirement it answered, and the
   expectation ids and client device ids that depended on it.
   `compact_summary()` gains the matching `operational_readiness` key; every
   existing key keeps its name, position and meaning. Freshness is per
   invocation: a result observed in an earlier run is never reused, because
   identity and state may have changed in between.

#### Requirements and acceptance

| Requirement | Acceptance evidence |
| --- | --- |
| B1 Required ports and VLANs are derived from the compiled plan | Unit tests over the derivation with a plan whose access ports, VLAN and endpoint sets are known, including a plan where interface order and device naming disagree with the required set |
| B2 No HTTP client request is dispatched before an admitted grouped `FWD` sample | Integration test over the real composition with an independently timed backend: ports report up while spanning tree stays `LIS`, and the service runtime records no HTTP verify call in that window |
| B3 A request follows the first admissible observation | Same test after the fake's clock passes its forwarding instant: the group is admitted once and the dependent HTTP expectations are then observed |
| B4 One grouped query serves every client of that group | The observer's call log holds exactly one observation for the single switch/VLAN group of the two-client fixture |
| B5 Persistent non-forwarding blocks precisely, with per-client coverage | Integration test asserting `DEPENDENCY_BLOCKED`, `ACCESS_FORWARDING_NOT_READY`, `NOT_ATTEMPTED`, the `NON_FORWARDING` dimension and the per-client rows, and asserting no HTTP verify call happened |
| B6 A foreign or partial sample never authorizes | Tests driving wrong observed device identity, unconfirmed provenance, incomplete output and a missing interface, each refusing on its own dimension |
| B7 The forwarding evidence and its dependents round-trip through the public report | Test asserting the `operational_readiness` rows, their expectation/client links and the unchanged existing `compact_summary()` keys |
| B8 An already-forwarding path is admitted without waiting | Positive control: a first sample in `FWD` admits, dispatches, and records one observation |
| B9 Readiness cannot be switched off | Test that a composition without an observer blocks with `observer_unavailable`, and a review check that no argument, flag or environment read can skip the gate |
| B10 The fake's timer advances with time, not with queries | The independently timed backend answers from an injected clock; repeated observations at the same instant return the same non-forwarding reading |

#### Invariants

- The four-argument MCP signature is unchanged.
- The product tool still deletes no operator topology and releases only what it
  owns.
- Existing retention, optional-service exclusion, uncertainty, ownership, secret
  and public JSON guarantees are unchanged; the report grows one key.
- `FORWARDING_STATES` stays an exact match set; no prefix rule is introduced.
- Readiness never reports `VERIFIED`, never contributes a capability, and never
  rewrites an action row.
- The Voice barrier keeps its own semantics and is not called from this path.

### C. DHCP: the native lifecycle contract, without promoting allocation

#### Problem

The product cannot yet say whether a changed native default is the reviewed
realignment or unexplained drift, so the only safe answer is "refuse
everything", which would also refuse the one transition that was actually
measured. What is missing is a decision, not a permission.

#### Scope

In scope: the smallest executable pure assessment of one before/after native
default pair, its coexistence statement, the backend-bound registry that carries
the reviewed measurement, and their tests.

Excluded, explicitly: wiring the assessment into `apply_enterprise_services` or
the DHCP application path, because admitting the realignment there would change
the existing authorization and restoration contract; any capability promotion -
product DHCP capabilities stay `UNKNOWN`; any change to `serverPool` beyond
observing it; consuming or editing a Q3 slot or its historic profile; and any
claim about table exhaustion, end-of-table semantics, lease-time freshness,
event release or POP3.

Integration is therefore deferred with this delta recording why, which is the
bounded option the work order offers. The registry is the composition seam and
is ready; nothing calls it from the public path yet.

#### Design

A new domain service, `domain/enterprise/services/dhcp_native_default_lifecycle.py`,
decides and states; it holds no backend version literal and performs no I/O.

- `assess_native_default_transition` compares an observed before/after pair
  against a tuple of reviewed `AdmittedNativeDefaultTransition` records supplied
  by the caller. Ordered and fail-closed: an unobserved snapshot is
  `NOT_ASSESSED`; an identical pair is `UNCHANGED`; a pool that was added,
  removed or renamed is `UNEXPLAINED_DRIFT` on its own cause, so `serverPool`
  can never be deleted, renamed or hidden into an admission; otherwise the pair
  is admitted as `ADMITTED_REALIGNMENT` only when some record matches the
  observation **completely** - the same model, backend build, interface and
  named intervention, the same pool name, every before field, every after field
  and exactly the same changed-field set - and is `UNEXPLAINED_DRIFT` with a
  named reason in every other case.
- Nothing is computed from the observation, so nothing is extrapolated. The
  admission is a comparison against exact measured values, which is what makes
  an unmeasured network refuse structurally rather than by policy. The
  intervention the record names is the whole `configurePcIp` call, never an
  internal setter.
- `assess_intended_pool_coexistence` states, as facts and not as permission,
  whether a native default and an intended pool share a subnet and whether their
  ranges overlap, and carries the standing limitation that a matching address
  that could come from the overlapping native default proves no service.
- Every assessment carries `authorizes_allocation=False`. There is no code path
  that sets it otherwise.
- `infrastructure/catalog/dhcp_native_default_transitions.py` holds the one
  reviewed record from D-DHCP attempt 2, keyed by backend build `9.0.1.0858`,
  and is the only public source of admitted transitions. A test supplies its own
  records directly and never mutates the catalog, so no test-only record can
  reach public composition.

#### Requirements and acceptance

| Requirement | Acceptance evidence |
| --- | --- |
| C1 The exact measured transition is admitted | Unit test replaying the six recorded snapshots' before/after values from D-DHCP attempt 2 against the catalog record |
| C2 The initial stock default and the post-E5 state are compared separately | Tests over the `d0_baseline`-to-`d1` pair and over the later pairs, asserting the post-E5 state is never treated as a baseline |
| C3 Any unrelated drift refuses | Tests changing the gateway, the DNS server, `max`, a fifth field, and a field back to an unmeasured value, each `UNEXPLAINED_DRIFT` with its own cause |
| C4 A different model, build, interface or intervention refuses | One test per context field |
| C5 An unmeasured network refuses even under the same arithmetic | Test with a different subnet whose four fields follow the same relationship, asserting refusal |
| C6 `serverPool` cannot be removed, renamed or hidden | Tests for removed, renamed and added pool rows |
| C7 Coexistence is stated and authorizes nothing | Test asserting shared subnet, overlapping range and the standing limitation for the measured pair |
| C8 No assessment authorizes allocation, and capabilities stay `UNKNOWN` | Test asserting `authorizes_allocation is False` on every classification, and that the public capability records for DHCP are unchanged |
| C9 Backend policy is bound by composition | Test asserting the domain module names no backend version and that the catalog is the injected source |

#### Invariants

- All six recorded snapshots stay exactly as the record holds them; nothing is
  re-derived into them.
- The post-E5 state is never redefined as the baseline.
- Product DHCP capabilities remain `UNKNOWN` and no catalog injection reaches
  public composition.
- Further unexplained change after an admitted transition still refuses.
- Q3's slots and its historic profile are untouched.

### Test levels and their justification

| Level | Applies | Why |
| --- | --- | --- |
| Acceptance | yes | B2, B3, B5 and C1 are the acceptance statements of this block, exercised through the real composition and the real domain decision |
| System | yes | the public report contract, including the new `operational_readiness` key and the unchanged existing keys |
| Integration | yes | `apply_enterprise_services` with both runtimes, the readiness port and an independently timed backend |
| Unit | yes | the pure derivation, the pure DHCP assessment and the coexistence statement |
| LIVE | no | offline only by the work order; no Packet Tracer launch or contact is authorized or needed, and the forwarding gate's LIVE behaviour stays unverified until a separately authorized and observed run exists |

### What was delivered, path by path

| Path | Change |
| --- | --- |
| `docs/engineering/change-briefs/server-pt-goal-foundations.md` | this design delta and its verification |
| `docs/reference/server-pt/evidence/campaign-diag-0ea-01/README.md` | the additive closeout index |
| `docs/reference/server-pt/evidence/campaign-diag-0ea-01/verification-01.json` | the 62-comparison verification, both censuses and the force-termination sequence |
| `docs/reference/server-pt/evidence/campaign-diag-0ea-01/ADDENDUM-01.sha256` | digests of the addendum, the two archived work orders, the unmodified package and the three recovered markers |
| `docs/reference/server-pt/assignments/Codex_Next_Product_Readiness_5296984.md` | the work order, archived byte-for-byte (9,412 bytes, `634e9fa5...4b2a`) |
| `docs/reference/server-pt/assignments/Codex_ServerPT_Diagnostic_Goal_DRAFT.md` | the pre-authorization proposal, archived byte-for-byte (10,494 bytes, `e11b4667...1d638`) |
| `docs/reference/server-pt/README.md`, `source-manifest.json` | three index rows, one campaign section and five manifest entries |
| `src/packet_tracer_mcp/domain/enterprise/services/service_access_readiness.py` | new: the pure derivation and the readiness decision |
| `src/packet_tracer_mcp/application/use_cases/service_access_readiness_gate.py` | new: the `AccessForwardingObserver` port and the bounded lazy gate |
| `src/packet_tracer_mcp/domain/enterprise/services/dhcp_native_default_lifecycle.py` | new: the pure native-default transition and coexistence assessments |
| `src/packet_tracer_mcp/infrastructure/catalog/dhcp_native_default_transitions.py` | new: the one reviewed transition, keyed by exact backend build |
| `src/packet_tracer_mcp/application/use_cases/apply_services.py` | `apply()` takes the gate; `_verify` consults it immediately before the request |
| `src/packet_tracer_mcp/application/use_cases/apply_enterprise_services.py` | stage E3r derives the requirement, the gated runtime forwards the reader, and both result assemblies carry the rows |
| `src/packet_tracer_mcp/domain/enterprise/models/configuration_runtime.py` | one new failure code, `ACCESS_FORWARDING_NOT_READY` |
| `src/packet_tracer_mcp/domain/enterprise/models/service_entry.py` | `operational_readiness` on the result and on `compact_summary()` |
| `src/packet_tracer_mcp/domain/enterprise/models/service_run_record.py` | `operational_readiness` on the durable record |
| `tests/service_entry_fixture.py` | `SimulatedClock` and `ForwardingBackend`, and the E5 fake answers the grouped query |
| `tests/test_service_tools_surface.py` | the product simulation answers the registered spanning-tree query and the simulation-state read |
| `tests/test_service_access_readiness.py` | new: derivation, gate and composition tests |
| `tests/test_dhcp_native_default_lifecycle.py` | new: transition, coexistence and non-promotion tests |
| `src/packet_tracer_mcp/application/use_cases/qualify_server_services.py` | the three diagnostic applications declare `ReadinessNotRequired` with their reason |
| `tests/test_service_application.py`, `tests/test_e95_service_voice_manifest_application.py` | one readiness declaration each, plus the 27 docstrings their files owe once touched |
| `tests/test_service_application_uncertainty.py` | the shared applicator arguments declare the exemption |

### Requirement-to-test mapping

| Requirement | Test |
| --- | --- |
| B1 | `test_required_ports_and_vlan_come_from_the_compiled_plan`, `test_derivation_ignores_device_names_and_interface_order`, `test_only_http_family_kinds_are_gated` |
| B2 | `test_no_http_request_is_dispatched_while_spanning_tree_is_still_listening` |
| B3 | `test_a_request_follows_the_first_admissible_observation` |
| B4 | `test_one_grouped_query_serves_every_client_of_the_group` |
| B5 | `test_persistent_non_forwarding_refuses_with_per_client_coverage` |
| B6 | `test_a_foreign_or_partial_sample_never_authorizes` (eight dimensions), `test_an_endpoint_the_plan_never_placed_is_named_not_dropped`, `test_a_path_spanning_two_switches_is_not_a_single_segment_path` |
| B7 | `test_the_forwarding_evidence_round_trips_through_the_public_report` |
| B8 | `test_an_already_forwarding_path_is_admitted_without_waiting` |
| B9 | `test_readiness_cannot_be_switched_off`, `test_an_observer_that_raised_observed_nothing`, `test_the_total_budget_is_checked_before_the_next_group_is_observed` |
| B10 | `test_the_backend_timer_advances_with_time_not_with_queries` |
| C1 | `test_the_exact_measured_transition_is_admitted` |
| C2 | `test_the_post_e5_state_is_never_treated_as_a_baseline`, `test_an_unobserved_reading_decides_nothing` |
| C3 | `test_a_field_outside_the_measured_set_refuses`, `test_a_measured_field_landing_on_an_unmeasured_value_refuses`, `test_further_change_after_the_admitted_transition_still_refuses` |
| C4 | `test_a_different_context_refuses` (four fields), `test_a_build_with_no_reviewed_measurement_refuses` |
| C5 | `test_an_unmeasured_network_refuses_under_the_same_relationship` |
| C6 | `test_a_removed_default_is_drift_not_an_admission`, `test_a_renamed_default_is_drift`, `test_a_second_default_appearing_is_drift`, `test_two_defaults_moving_at_once_is_drift`, `test_a_malformed_inventory_decides_nothing`, `test_a_duplicated_pool_name_decides_nothing` |
| C7 | `test_the_measured_pools_share_a_subnet_and_overlap`, `test_a_disjoint_intended_pool_reports_no_overlap`, `test_a_malformed_pool_row_states_no_coexistence` |
| C8 | `test_no_classification_authorizes_allocation`, `test_product_dhcp_capabilities_remain_unknown` |
| C9 | `test_the_domain_module_names_no_backend_version`, `test_a_caller_supplied_record_never_reaches_the_catalog` |
| A | `verification-01.json` and `ADDENDUM-01.sha256`: 62 recomputed digests, 0 mismatches, 0 missing. A documentary result, so it has no unit test and needs none |

### Three behaviours worth recording exactly

**The by-hostname fetch is blocked by its own prerequisite, not by readiness.**
In the fixture plan `svc/verify-http-name` depends on `svc/verify-http-ip`. When
readiness refuses the group, the by-IP row carries
`ACCESS_FORWARDING_NOT_READY` and the by-hostname row carries
`DEPENDENCY_BLOCKED`, because readiness was never reached on its behalf and no
sample was taken for it. Reporting a forwarding refusal there would claim a
sample that does not exist. Both rows are blocked and neither request is made,
which is what the requirement asks; the codes differ because the reasons differ.

**A group nobody reached is reported as never observed, not omitted.** When
every dependent of a group is blocked upstream, `rows()` still emits that group
with status `not_observed` and cause `dependent_never_became_admissible`. The
report says what the run did not ask as clearly as what it did.

**Readiness is never consulted from the staged verification pass.** The
applicator runs `_verify` twice, once for expectations another action stages and
once for the rest. Only `DHCP_SERVER_STATE` and `DHCP_LEASE` are ever staged
(`service_compiler` assigns `verification_dependencies` to nothing else), so an
HTTP-family expectation always reaches readiness in the final pass. Were one
staged later, the gate would still observe immediately before that request,
because the memo and the observation both belong to the one `apply` call.

### Measured verification

| Check | Result |
| --- | --- |
| Causal RED for B2/B3/B7 | with the gate detached from the applicator, the by-IP fetch reported `VERIFIED` while spanning tree was `LIS`; 3 of the then-23 failed. Reattached: green |
| Focused readiness set | `tests/test_service_access_readiness.py`, `33 passed` |
| Focused DHCP set | `tests/test_dhcp_native_default_lifecycle.py`, `40 passed` |
| Affected integration and system set | the `service_entry_fixture` consumers, both access-forwarding modules and the five direct applicator suites, `362 passed` |
| Evidence verification | 62 recomputed digests over the operator package and the three markers, 0 mismatches, 0 missing; archive SHA-256 equals the work order statement and the operator sidecar |
| Full offline suite | `6927 passed, 3 skipped, 3 pre-existing warnings`, exit 0, 569.81 s. The base recorded `6854 passed, 3 skipped`, so the delta is exactly the 73 tests this block adds: 58 for the block itself and 15 for the independent-review corrections |
| Provisional quality gate | base and merge base `6263344e`, 112 changed Python files Ruff-gated (104 at the base, plus the six this block adds and the two legacy test files the corrections took ownership of), no mechanical exemption, exit 0 |
| Namespace inventory | 0 active legacy imports, 0 active string references, 0 unreviewed inert mentions, exit 0 |
| MkDocs and whitespace | build exit 0 in 5.70 s with the two unchanged `handoff.md` warnings; `git diff --check` exit 0 |
| Public report contract | all 21 `compact_summary()` keys of the base are present and unchanged; `operational_readiness` is the only addition, and `adapters/mcp/service_tools.py` is untouched, so the four-argument signature is preserved by construction |
| Evidence semantics of a blocked row | the record a readiness refusal produces carries `support_status: unknown`, `verification_status: unverified`, `observation_status: not_attempted` and `strength: none`, with the refusing dimension as a limitation |

### What remains, and what is still not established

- **Integration of the DHCP assessment is deferred by design.** The decision and
  its registry are executable and tested; nothing in the public path calls them,
  because admitting the realignment there would change the existing
  authorization and restoration contract. That is the bounded option the work
  order offers, and taking it is recorded here rather than left implicit.
- **The forwarding gate is verified offline only.** Its LIVE behaviour, Packet
  Tracer reachability and the real `show spanning-tree` timing stay unverified
  until a separately authorized and observed LIVE run exists. A green suite is
  not evidence of LIVE isolation or LIVE behaviour.
- **Product DHCP capabilities remain `UNKNOWN`** and no client acquisition has
  been measured. A future acquisition acceptance must still identify the exact
  intended pool, server, client interface and MAC and a freshly observed
  matching lease; an address that could come from the overlapping native default
  is insufficient.
- **The cold HTTP acceptance is still to be designed.** It must be HTTP-only by
  IP before any DNS verification that itself uses ping, or DNS validation could
  warm the same path and hide the defect. Nothing in this block reorders the
  existing expectation DAG.
- **Delivery status is `READY_FOR_REVIEW`.** Self-review is not independent
  audit, no merge or publication is included, and exact-SHA CI belongs to a
  publication the operator has not granted.

### Delivery identity of this block

| Field | Value |
| --- | --- |
| Behaviour commit | `0c8392985f5daf14e436619a98bac168b56d682c` (tree `397203bd08ec70aa011c124551cf3b1b63a11db0`), corrected by the independent-review follow-up recorded below |
| Branch | `feature/server-pt-goal-foundations` |
| Base | `52969849408d195436ae250f611318e7e959876f` |
| Authoritative main | `6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main`) |
| Delivery-mode quality gate | clean tree at that exact commit, base and merge base `6263344e`, 110 Ruff-gated changed Python files, 0 mechanical exemptions, exit 0 |
| Changed paths | 21 files, 3,041 insertions and no deletions |
| Exact-SHA CI | not obtained. Publishing needs the operator's grant, and this block includes no push |
| Status | `READY_FOR_REVIEW` |

The gate result in that row was measured on `0c83929`. The independent review
that followed produced the correction commit
`771205422f694ab77b1928595d9aa3a3ba2528d8` (tree
`28ea25502e3614e92f8c0384667819b4d9fbd0d3`), whose own delivery-mode gate ran on
a clean tree at that exact commit with base and merge base `6263344e`, 112
Ruff-gated changed Python files, 0 mechanical exemptions, exit 0. The full-suite
and focused numbers in **Measured verification** above are the ones re-measured
on that corrected tree.

This section names the commit that carries the behaviour, so it necessarily
lands in a following documentation commit. The gate result above is the one
measured on the behaviour commit with a clean tree, which is the authoritative
delivery validation; the provisional worktree run recorded earlier agreed with
it.

### One pre-existing discrepancy, reported and deliberately not touched

While verifying its own five new entries, this delivery found that
`docs/reference/server-pt/source-manifest.json` already disagrees with two files
of the earlier `SERVER-PT-D02-Q3-Q1-AUTOFIX-01` package, at the reviewed base
`5296984` and not because of anything here:

| Path | Manifest says | Bytes at `5296984` and in the worktree |
| --- | --- | --- |
| `evidence/campaign-d02-q3-q1-autofix-01/amendment-ledger.jsonl` | `05db0a7a...ba43d` | `46dd6b7b...ccf7d` |
| `evidence/campaign-d02-q3-q1-autofix-01/README.md` | `50eeaf86...36708` | `e7dbc251...f72150` |

The committed blob and the working-tree bytes are identical in both cases, so
nothing drifted in this checkout; the manifest entries are stale relative to a
later amendment of those two files. It is left exactly as found. Correcting a
recorded digest of a prior campaign is a change to an evidence claim about work
outside this contract, and doing it incidentally is what the evidence rules
forbid. It is raised here for the reviewer to dispose of, with its own decision.
### Independent review at `0c83929`, and what it changed

An independent adversarial review was run against the delivery commit. It
raised nine findings. Its own focused pytest could not start in its sandbox, so
every claim was traced by reading rather than executed; each was therefore
re-probed here against the committed code before anything was changed. Eight
reproduced as stated. One, the forwarding-envelope binding, did **not**
reproduce in the form the review described and did reproduce in a narrower
form, which is recorded below as the review found the defect and mis-stated its
trigger.

| # | Finding | Reproduced | Disposition |
| --- | --- | --- | --- |
| 1 | `ServiceApplicator.apply` treated a missing readiness argument as "no gate" | yes | the default is now fail-closed: declaring nothing refuses every client request with `readiness_not_declared` |
| 2 | the gate never bound the observation envelope to the group it asked about | yes, narrowly | an answer naming another switch, another VLAN or a narrower interface set is now refused as `observation_does_not_answer_the_request` |
| 3 | one gate could serve two applications from one cached verdict | yes | `begin_invocation()` claims the gate once and raises `ReadinessGateConsumed` on a second application |
| 4 | admission ignores `sample_budget_exhausted`, which the model documents as non-authorizing | yes | refused in the product gate; the shared domain rule is deliberately left unchanged, see below |
| 5 | an unreviewed pool sitting unchanged in both DHCP snapshots was ignored | yes | any pool the reviewed record does not name now refuses, with `unreviewed_pool_present` |
| 6 | `authorizes_allocation` was a caller-settable field | yes | it is a read-only property returning `False`; passing it is now a `TypeError` |
| 7 | the public catalog handed out mutable shared mappings | yes | `before` and `after` are `MappingProxyType`, so a caller cannot edit what the next one is admitted against |
| 8 | every range overlap was reported as inverse containment | yes | the cause now names the containment the numbers show, in all three directions |
| 9 | derivation accepted any object with four matching attributes | yes | only a declared `configure_access_port` action produces a placement |

#### Where finding 2 actually bites

The review's scenario returned a foreign envelope *and* foreign interface names,
and the per-dependent coverage check already refused it. The real defect needs
the same interface names under a foreign switch and VLAN: asked about `SW1`
VLAN 10 on `Fa1/1`/`Fa1/3`, a self-consistent answer claiming `SW2` VLAN 20 on
those same port names was admitted. The shared admission rule checks that a
sample is internally consistent -- that the device it reports is the device it
names -- and it never sees the request, so it cannot check the subject. That
binding belongs to the caller that asked, and now lives there.

#### Why finding 4 is fixed in the gate and not in the shared rule

`AccessForwardingObservation.sample_budget_exhausted` documents itself as
granting no permission, and `access_forwarding_admission` does not enforce it.
That is a genuine gap, and it is **pre-existing at the reviewed base**: the same
rule decides the Voice barrier and the diagnostic stages, and the D-WEB and Q3
evidence was measured under its current behaviour. Changing it here would move
the semantics of recorded evidence outside this contract. The product path
refuses such a sample in its own layer instead, and the sample is retained in
the report showing that the gate is stricter than the rule rather than
rewriting it. The shared-rule gap is raised for the reviewer with its own
decision.

#### The cost this took, measured before it was paid

The fail-closed default changes what an undeclared caller gets, so three legacy
applicator tests that dispatch HTTP and assert success had to declare
`ReadinessNotRequired`. Two of their files were not previously in the Ruff-gated
set, and touching them means owning their current state: 27 missing docstrings,
16 in `tests/test_service_application.py` and 11 in
`tests/test_e95_service_voice_manifest_application.py`. They were written rather
than suppressed, and the gated set grows from 110 files to 112. No other file
was reformatted and no test behaviour was changed beyond the declaration.

An earlier shape of this fix made `operational_readiness` a required argument.
It was rejected in favour of the fail-closed default: a required argument forces
a caller to decide, while a safe default makes forgetting harmless, and the
second is the stronger property for a gate whose whole job is to refuse.

#### Requirement-to-test mapping for this correction

| Finding | Test |
| --- | --- |
| 1 | `test_declaring_nothing_blocks_every_client_request` |
| 2 | `test_an_answer_about_another_question_is_not_a_sample_of_this_group` (switch, VLAN and interface-set cases) |
| 3 | `test_one_gate_serves_one_application` |
| 4 | `test_a_sample_that_ended_on_its_call_budget_grants_nothing` |
| 5 | `test_an_unreviewed_pool_unchanged_in_both_snapshots_still_refuses` |
| 6 | `test_allocation_authority_is_not_a_field_any_caller_can_set` |
| 7 | `test_the_public_catalog_record_cannot_be_edited_in_place` |
| 8 | `test_the_overlap_cause_names_the_containment_the_numbers_show` (three directions) |
| 9 | `test_only_a_declared_access_port_action_produces_a_placement`, `test_the_real_access_port_action_type_is_the_one_derivation_accepts` |
| exemption contract | `test_an_exemption_must_state_its_reason` |

## 2026-09-21 product-readiness time and evidence correction at `557195f` (risk L)

The reviewed product gate can admit a result returned after its 120-second total
allowance, and the public observer's three one-second samples can finish before
an independently delayed forwarding transition. The shared admission rule also
contradicts its observation model by admitting an exhausted sample. The evidence
addendum conflates per-attempt postrun process lists with a later zero-process
census; two mutable index entries identify older revisions without saying so.
The outcome is a bounded, real-path HTTP prerequisite and source-corrected,
additive history. No Packet Tracer LIVE work, capability promotion, public MCP
argument, DHCP public integration, diagnostic profile expansion, or historical
run/ledger edit is in scope.

The existing test `test_the_total_budget_is_checked_before_the_next_group_is_observed`
expects a 30-second first read to admit under a 20-second total. That is a
**requirements and design error in the test**, not compatible behavior. Replace
it with a late refusal and a measured timeout propagated into the executing
channel call. The earlier decision to leave exhausted-sample admission to the
product layer is superseded for new decisions; historical results keep their
original bytes and interpretation.

The gate passes the remaining invocation allowance through its observer port
and the E5 wrapper. The product policy uses the neutral runtime's existing
parameters: a 30-second group horizon, at most 31 samples, one second between
non-forwarding samples, and six nested channel calls per sample. The runtime
uses the minimum of group and remaining-invocation allowances, one absolute
deadline for all nested calls, and the channel's normal timeout as another cap.
Auxiliary simulation-state reading is included in the elapsed decision and is
not allowed to grant a late result. The gate rechecks the total deadline after
the observer returns and retains a late sample as non-authorizing evidence.
The existing auxiliary read is bounded by the same deadline and counted once;
with 31 samples the ceiling is 31 x 6 nested IOS calls plus one auxiliary call
per group. Each sample's rows, identity, completeness, call count and elapsed
time are retained in the operational-readiness record.
One episode remains memoized per switch/VLAN for one invocation. The canonical
domain rule refuses `sample_budget_exhausted`; the product layer continues to
bind the response envelope to the requested switch, VLAN and interfaces.

| Requirement | Acceptance test |
| --- | --- |
| T1: total and group deadlines cap actual nested reads and late evidence cannot grant HTTP | Gate regression for short remainder, late answer, exhaustion before next group and raised reader; runtime channel timeout and auxiliary-read checks |
| T2: a delayed FWD transition within the 30-second product horizon reaches the public HTTP-by-IP request after E5 | Clock-driven external channel through real composition, runtime observer and applicator at 4 seconds and near horizon; persistent LIS, foreign identity and already-FWD controls; grouped reuse and durable report reload |
| S1: exhausted samples refuse in the shared rule and every consumer | Domain positive/negative pair, diagnostic projection, product zero-request, and affected Voice/forwarding tests |
| E1: historical claims match their actual source and time | Additive marker-byte package and provenance check; separate per-attempt process lists from any available post-restart census; source-bound grant wording |
| M1: indexes identify original and current ledger/README revisions | Git-history lookup, byte/digest comparison and manifest erratum without changing previous manifests or append-only entries |

Unit tests cover admission and budget arithmetic; integration tests cover the
composed runtime, E5/E6 order, grouped memo and stored record; the public
workflow test covers dispatch and refusal. The full offline suite, namespace
inventory, documentation build, whitespace and exact-delivery gate are the
system checks. LIVE qualification is not applicable to this authorization;
offline evidence cannot establish Packet Tracer behavior. Preserve ownership,
retention, secrets, the single-writer gate and all existing capability limits.

The earlier diagnostic test counted only IOS calls and expected the auxiliary
simulation-state read to be missing from `channel_calls`; its ledger already
charged that physical call. The corrected test asserts at most six calls per
sample, exactly one auxiliary call, and equality between the observation and
ledger totals. It changes no diagnostic profile or physical call ceiling.
The operator approved scoped Ruff cleanup of `ios_terminal.py` on 2026-09-21
because the hard nested-wait correction touches that legacy file. The cleanup
preserves legacy enum `str()` and JSON values and is reviewed separately from
the deadline behavior. The full suite then exposed one CP-SCALE regression test
that parsed the old literal formatting of the qualified-query set. The operator
approved cleanup of that test file too; its replacement uses Python's AST to
assert the exact enum membership while preserving the suite's subprocess
isolation boundary.

### Measured offline closure

- The real public composition, E5 configuration readback, neutral IOS observer,
  `ServiceApplicator`, service runtime and durable store observe FWD at 4.0 and
  26.0 simulated wall seconds. The trace orders the final E5 readback before
  the admissible exact-port/VLAN FWD sample and that sample before the first
  HTTP-by-IP request. Already-FWD admits immediately; persistent LIS, foreign
  ownership and ambiguous ownership dispatch no HTTP.
- A 0.03-second invocation remainder caps the actual nested channel calls and
  returns late evidence without permission. A 0.30-second case proves the
  auxiliary read consumes the same allowance. A collaborator that returns FWD
  after 31 seconds produces zero HTTP requests. The production ceilings remain
  120 seconds and four groups; each group uses a 30-second horizon, up to 31
  samples, one-second cadence and six nested calls per sample.
- `sample_budget_exhausted=true` now refuses in the canonical domain rule. The
  positive control with the same complete FWD rows and `false` still admits.
  Diagnostic projection retains the raw flag and reports INCONCLUSIVE; affected
  Voice, forwarding and diagnostic tests remain green.
- The additive evidence correction includes all three original 160-byte marker
  files with matching digests. No separate historical post-restart zero-process
  census, original operator permission message or lifecycle amendment was
  available; those source claims remain not independently verifiable. The
  current-only census remains scoped to `2026-09-21T21:53:27Z`.
- Git history binds the old D02 README and ledger declarations to `a02c1e0`
  (4,494 and 6,687 bytes) and their current revisions to `65abf7b` (6,770 and
  10,110 bytes, blobs `a2225d6` and `5556700`). No ledger or run record changed.

| Verification | Result |
| --- | --- |
| Focused readiness, forwarding and IOS | 151 passed |
| Affected diagnostic, Voice, IOS, forwarding and persistence | 310 passed |
| CP-SCALE qualification-set regression file | 49 passed |
| Full offline pytest | 6,940 passed, 3 skipped, 3 unchanged deprecation warnings |
| Namespace inventory | 0 active imports, 0 active string references, 0 unreviewed inert mentions |
| MkDocs | exit 0; two pre-existing missing-handoff warnings |
| Whitespace | `git diff --check` exit 0 |

The delivery remains offline and self-reviewed. Packet Tracer capability and
LIVE behavior remain unverified, and independent acceptance is still required.
The exact delivery SHA/tree and clean delivery-gate result are recorded after
the local commit; exact-SHA CI remains pending without a feature-branch
publication grant.

## 2026-09-21 sample/episode/phase boundary correction at `9aa8388` (risk L)

The reviewed closure makes three lifetime mistakes and carries three bounded
documentary defects. `observe_access_forwarding` folds every sample's call
exhaustion into one cumulative flag, so an early incomplete read refuses a
later complete, timely, correctly attributed FWD sample through the canonical
domain rule. `deadline_reached` carries four different facts at once, so the
shared rule publishes `sample_after_deadline` about samples that arrived on
time. The nested IOS waiter snapshots its remaining allowance once, so after
the effective budget is spent it polls locally without sleeping until an
independent deadline that a stopped clock never reaches. The outcome is that a
recoverable failed read stops invalidating a valid later sample, expiration
stops polling promptly and names the boundary that actually expired, and the
published source manifest identifies a revision that exists.

Risk is L because this changes an authorization boundary, the durable evidence
shape and a shared refusal contract. It is a focused correction of the reviewed
closure and not a new readiness subsystem. Out of scope, explicitly: any Packet
Tracer contact, process action or product bridge startup; capability promotion;
attempt reset or Q-stage replay; a main merge or force push; a new public
argument; a replacement transport or parser; the unintegrated pure DHCP
assessment, which stays non-authorizing; and any unrelated refactor. This
delta authorizes no LIVE work.

### The four lifetimes this correction separates

A fact is named for the thing it describes, and nothing wider.

| Lifetime | What it may state | Fields |
| --- | --- | --- |
| Nested call | one channel dispatch was refused or capped | per-sample `channel_calls` |
| Individual sample | this read's own completeness, identity and timeliness | `sample_budget_exhausted`, `sample_after_deadline`, per-sample `deadline_reached` |
| Observation episode | why sampling stopped, and what happened anywhere in it | `episode_end_reason`, `episode_budget_exhausted`, `auxiliary_read_after_deadline`, `auxiliary_budget_exhausted` |
| Invocation and phase | which parent boundary closed permission | `deadline_scope`, `deadline_cause`, aggregate `deadline_reached` |

`sample_budget_exhausted` and `sample_after_deadline` are raw observations
about the authorizing sample, which is the last sample, because its rows are
the rows the admission reads. `episode_budget_exhausted` and
`episode_end_reason` are episode diagnostics and never authorize or refuse on
their own. `deadline_reached` stays the decision fact -- the permission window
is closed -- and `deadline_cause` names which boundary closed it. Legacy
records that carry neither new field keep their historical interpretation,
because an empty `deadline_cause` still reads as `sample_after_deadline`.

### Requirements and acceptance criteria

| Requirement | Acceptance criterion | Acceptance test |
| --- | --- | --- |
| R1: an early read-only sample exhaustion does not refuse a later valid sample | the canonical rule admits the complete, fresh, attributed, in-budget, timely final FWD sample at 4 s and 26 s; the exhausted first sample stays in the history; zero HTTP before it; agreement after reload | `test_an_early_exhausted_read_does_not_refuse_a_later_valid_sample`, `test_an_early_exhausted_read_agrees_after_the_record_is_reloaded`, `test_public_http_follows_a_valid_sample_that_an_earlier_read_preceded`, `test_an_exhausted_final_forwarding_sample_still_refuses`, `test_an_episode_exhaustion_alone_never_refuses_the_authorizing_sample`, `test_an_exhausted_auxiliary_read_refuses_under_its_own_name`, `test_authority_loss_is_never_recovered_by_a_later_sample` |
| R2: sample lateness, episode termination, parent boundary and auxiliary delay are distinct | each refused case names the boundary that actually expired and dispatches no HTTP, in the gate and in the stored projection | `test_a_timely_persistent_lis_episode_does_not_claim_a_late_sample`, `test_a_genuinely_late_sample_is_reported_late`, `test_a_timely_sample_refused_by_an_auxiliary_overrun_stays_timely`, `test_exhaustion_before_any_sample_names_itself`, `test_a_timely_admitted_sample_names_no_boundary_at_all`, `test_the_gate_and_its_stored_row_name_the_boundary_that_expired` (three cases), `test_the_gate_admits_the_timely_positive_and_names_no_boundary`, `test_public_workflow_sends_no_http_after_a_late_forwarding_answer`, `test_the_applicable_parent_boundary_is_recorded_with_its_scope`, `test_a_legacy_record_without_a_named_cause_keeps_its_interpretation`, `test_the_published_projection_separates_raw_facts_from_decisions` |
| R3: a spent effective budget or a terminal refusal stops the nested waiter | bounded exit under a watchdog, no post-expiration dispatch, the primary cause preserved, the cleanup reserve untouched | `test_the_nested_waiter_stops_when_the_phase_allowance_is_spent`, `test_the_nested_waiter_stops_when_the_call_allowance_is_spent`, `test_a_terminal_refusal_stops_the_nested_waiter`, `test_normal_progress_is_unchanged_in_the_same_composition`, `test_a_readiness_waiter_without_a_control_polls_exactly_as_before`, `test_a_readiness_waiter_stops_on_a_spent_control_without_sleeping` |
| R3b: the pager names the boundary that expired | a shorter caller allowance is reported as the caller's, not as the pager's own deadline | `test_a_shorter_caller_allowance_is_not_reported_as_the_pager_deadline`, `test_a_pager_capture_that_owns_the_expired_deadline_still_says_so` |
| R4: published documentary and fixture facts are true | both manifest revisions resolve; the heading renders as a heading with its anchor; the default auxiliary reader is exercised against a valid controlled response | `test_the_manifest_revision_errata_identify_real_revisions`, `test_the_manifest_errata_bytes_and_digests_match_their_revisions`, `test_no_maintained_heading_is_swallowed_by_the_table_above_it`, `test_the_risk_l_headings_render_outside_the_tables_above_them`, `test_default_auxiliary_channel_call_is_counted_and_deadline_capped`, `test_an_unavailable_auxiliary_reader_is_reported_as_unreadable` |
| P1: the shared absolute window is stated and enforced | a group starting at offset 106 of the 120-second window observes for at most 14 seconds | `test_a_late_group_inherits_only_the_remaining_shared_window`, `test_an_expired_shared_window_observes_nothing_at_all` |
| P2: reporting growth has a bounded synthetic control | a four-group readiness-facts projection is measured and labelled as a synthetic estimate, never as the complete record, response or largest supported topology | `test_the_synthetic_four_group_readiness_projection_stays_bounded` |

### Architectural impact and affected contracts

`AccessForwardingObservation` gains seven additive fields with defaults, so
every stored record and every existing constructor keeps working.
`access_forwarding_admission` keeps its dimension order unchanged -- the
DEADLINE dimension still precedes SAMPLE_CALL_BUDGET, and neither moves to
obtain a preferred message -- and reads the authorizing sample's own flags
instead of the episode's. `access_forwarding_facts` publishes the new fields
beside the existing ones; no key is removed or renamed.

`_BoundedTerminalChannel.remaining_seconds` is the existing port between the
bounded channel and `ControlledIosExecutor`. Its contract becomes effective
rather than purely temporal: it returns zero when the channel can no longer
dispatch at all, because its call budget is spent, its deadline has passed, or
the underlying transport refused terminally. Infrastructure catches `Exception`
generically at that seam and records the refusal as a stop reason; it imports
no application type. `DeviceReadinessWaiter` gains one optional keyword-only
control, `remaining_seconds`, and re-reads it every iteration instead of
trusting the construction-time snapshot; it stops without sleeping when the
effective remaining time is not positive. No public product argument is added.

### Invariants

- No sample that refused before this change is admitted after it. The gate,
  the envelope binding, the identity, freshness and completeness checks, the
  sticky process-incarnation, ownership, uncertain-mutation and quarantine
  facts, and the fail-closed order are unchanged.
- Cumulative call accounting (`channel_calls`) and the complete bounded sample
  history stay in the durable record. Nothing is truncated.
- The shared absolute readiness window stays 120 seconds, measured from the
  first readiness observation, and HTTP elapsed time between groups is neither
  paused nor refunded. The 30-second group horizon is an upper bound: a group
  starting at offset 106 has at most 14 seconds. This is not a new HTTP
  transaction timeout and not a new expiration rule for memoized groups.
- Enum wire and string values are unchanged; ordinary boot, Voice and ungated
  IOS behavior keep the lifecycle helper and the defaults they had.
- Historical ledger entries, manifests, campaign files and marker bytes keep
  their bytes. The manifest erratum corrects a malformed revision identifier
  only.

### Test design

Unit tests cover the domain admission rule over the new per-sample and episode
fields. Integration tests cover the composed runtime, the bounded channel, the
real IOS executor, the actual `OperationLedger`/`LedgeredTransport` pair with
controlled time and an outer watchdog, and the gate. System tests cover the
public workflow, the stored projection and its reload. Acceptance traceability
is the table above. LIVE qualification is not applicable: this order authorizes
none, and offline evidence cannot establish Packet Tracer behavior.

### Scope owned by the touched files

The nested-wait correction touches `device_lifecycle.py`, a small legacy module
that was outside the Ruff boundary. Touching it means owning its current state,
so this delivery adds the six missing docstrings and applies the configured
formatter to that one file. Nothing in it is translated: the existing Spanish
class docstrings are legacy content and stay as they are, while the docstrings
this change adds are English, as the coding standard requires of new content.

The pager-diagnostic regressions were deliberately NOT written into
`test_e95_serial_orientation_pager_capture.py`. That file is legacy and
carries thirty unrelated Ruff findings and a seventy-one line reformat, none of
which this correction caused. The two regressions live with the other boundary
tests instead and import that file's measured pager fakes, so the behaviour is
exercised by the same terminals and no unrelated legacy file is reformatted.
The boundary stays where it was; expanding it remains a separate change with
its own debt assessment.

### One deliberate narrowing, stated rather than discovered

A terminal refusal stops the bounded channel for the rest of the invocation,
not only for the sample that met it. One gate serves up to four groups through
one runtime and therefore one channel, so a later group now reports that it
took no sample rather than dispatching into a channel that already refused.
This refuses strictly more than before -- previously the exception escaped the
observation, the group was recorded as `observation_failed`, and the next
group tried again -- and it is what makes the loop bounded. It is the right
reading for the refusal this actually models: a ledger that has closed effects
or spent its allowance does not reopen for the next group. A transport that
raised transiently is treated the same way, which is the conservative
direction, and it is recorded here so a reviewer weighs it rather than finding
it.

### Measured offline closure

- The defect reproduces before the change and not after it. The early
  exhaustion case is a first read that spends its six nested calls on a
  terminal that never converges -- read-only, no key delivered, no pager
  entered, no quarantine raised -- followed by a complete, fresh,
  `confirmed_unique`, in-budget FWD sample. Before: `SAMPLE_CALL_BUDGET_EXHAUSTED`
  with cause `sample_call_budget_exhausted`, although the observation's own
  `failure_reason` was empty. After: admitted at `forwards_at` 4.0 s and
  26.0 s, with the failed read retained as `sample_history[0]` and the whole
  episode still marked `episode_budget_exhausted`.
- A normal sample costs four nested channel calls against a budget of six, so
  the exhaustion above is caused by the stalled read and not by the ceiling.
- R3 reproduces as non-termination, which is what the reduced audit
  described. With a 0.05-second phase allowance and a 0.02-second reserve, the
  composed `OperationLedger`/`LedgeredTransport`/runtime never returned within
  a twenty-second real watchdog: two dispatches reached the transport, four
  ledger refusals were recorded, the simulated clock stopped at 0.030 s and
  `capped_sleep` was never asked for a positive wait. The same composition
  after the change returns immediately with two dispatches, one ledger refusal
  and the clock still at 0.030 s. The dispatch count is identical before and
  after, which is the point: this was a local late-stop defect and never extra
  Packet Tracer commands. The whole boundary file, watchdogs included, runs in
  under a second.
- A terminal refusal underneath the bounded channel now ends the episode as
  `channel_refused:OperationRefused` instead of escaping as an exception into
  the generic readiness waiter, which used to catch it and keep polling. The
  ledger's own half is unchanged and still asserted: three calls used, every
  entry past the ceiling refused before dispatch.
- The blast radius is exactly one executor. Of the ten `ControlledIosExecutor`
  constructions in the package, only the neutral access-forwarding one passes
  `remaining_budget`; every other path -- Voice, control plane, security,
  probes, serial orientation, PoE and the CP-SCALE observers -- leaves the
  control unbound, so its waiters read an unbounded allowance and behave
  exactly as before. That equality is asserted rather than assumed.
- The pager diagnostic distinguishes its two boundaries. Its own 25-second
  deadline still reports "exceeded its bounded deadline of 25s"; a caller
  allowance that runs out first now reports "stopped on the caller's remaining
  allowance, before its own bounded deadline of 25s", measured with the clock
  still below 25 s.
- Both `original_declaration_revision` values are now the 40-character commit
  `a02c1e0`. Verified against the stored Git objects, in binary, and not the
  other way round: README 4,494 bytes / `50eeaf86...`, ledger 6,687 bytes /
  `05db0a7a...` at `a02c1e0`; README 6,770 bytes / `e7dbc251...` (blob
  `a2225d6`) and ledger 10,110 bytes / `46dd6b7b...` (blob `5556700`) at
  `65abf7b`. No ledger entry, manifest, campaign file or marker byte changed.
- Rendering is inspected, not inferred. In the site built by the project's own
  MkDocs configuration, the previously swallowed heading renders as
  `<h2 id="2026-09-21-product-readiness-time-and-evidence-correction-at-557195f-risk-l">`
  with its permalink anchor, this delta's heading renders as its own `<h2>`
  with a table-of-contents entry, and no risk-L heading remains inside a table
  cell. Removing the blank line again makes both the source-level and the
  rendered check fail, which is what makes them regressions.
- The default auxiliary reader is exercised against a controlled simulation
  state (`frames: 3`, `sim_time: 12.5`) and the observation reports
  `sim_time:12.5;frames:3`, derived from that answer rather than from a fake
  refusing a request it never implemented. An intentionally raising reader is
  a separate case and reports `unreadable:RuntimeError`.
- The shared window is stated and tested: with the 120-second allowance and a
  group starting at offset 106, the observer receives `remaining_seconds=14.0`
  beside the unchanged 30-second group horizon, and at offset 120 no
  observation is taken at all. HTTP time between groups is neither paused nor
  refunded, and nothing here is a new HTTP transaction timeout or a new
  expiration rule for memoized groups.
- The readiness projection has a synthetic growth estimate rather than a
  record-size claim. With 24 interfaces and 31 samples, one facts projection
  is 66,468 compact bytes; multiplying that projection by four gives 265,872
  bytes. It is not the complete persisted invocation, not the MCP response and
  not proof of the largest supported topology. No evidence is truncated and no
  reporting framework is added.

| Verification | Result |
| --- | --- |
| Boundary, published-source, readiness, forwarding, diagnostic and pager tests | 206 passed |
| Voice, IOS, forwarding, persistence, readiness, lifecycle and device areas | 1,388 passed, 2 skipped |
| CP-SCALE realtime STP observation | 49 passed |
| Full offline pytest (Python 3.12.10, checkout `.venv`) | 6,977 passed, 3 skipped, 3 unchanged deprecation warnings |
| Namespace inventory | 0 active imports, 0 active string references, 0 unreviewed inert mentions |
| MkDocs build and rendered-heading inspection | exit 0; two pre-existing missing-handoff warnings; 7 risk-L `<h2>` elements, all anchored |
| Whitespace | `git diff --check` exit 0 |
| Quality gate, worktree mode against `cisco/main` | 118 changed Python files gated, all checks passed |

The three skips are environmental and unrelated to this change: symlink
creation is refused for this account, and two Voice evidence tests find no
retained raw run or qualification artefact in this checkout.

### One intermittent failure observed, and what it is not

`test_no_classified_family_names_a_module_that_stopped_dispatching`, a
pre-existing architecture gate that walks every `src/packet_tracer_mcp/**/*.py`
and re-derives which modules dispatch mutations, failed once in eight
full-suite runs. It is reported here rather than filtered out, and it is not
attributed to this change, on this evidence:

- it passes in isolation, in every focused set, and in the last four
  consecutive full runs;
- the sweep it performs is stable across sixty consecutive enumerations in a
  standalone process, with an empty stale set every time;
- a per-test watcher over the whole suite recorded the package tree after each
  of the 6,977 tests and found the same 351 modules at the same sizes
  throughout, so no test changes the content the sweep reads;
- running it together with the two test files this change adds, five times,
  never reproduced it;
- nothing this change touches is named by the gate, which classifies mutation
  dispatchers, and the correction adds no dispatcher and removes no call.

What remains is a transient directory-enumeration miss under `rglob` on this
platform, which the gate would report as a family whose module "stopped
dispatching". Making that gate robust to it is a separate change with its own
brief; this delivery neither introduces it nor hides it.

The delivery remains offline and self-reviewed. Packet Tracer capability and
LIVE behaviour remain unverified; this order authorizes no LIVE work, and an
offline suite cannot establish Packet Tracer behaviour. Exact-SHA CI remains
pending without a feature-branch publication grant, and independent acceptance
is still required. Delivery status is `READY_FOR_REVIEW`, not acceptance.

## 2026-09-22 cold HTTP acceptance preparation after `8197b02` (risk L)

### Identity, problem and intended outcome

The accepted input is clean branch `feature/server-pt-goal-foundations` at
`8197b02528461ae12b051a13bdc65b17cc42e510`, tree
`00833c7f86807f06abcee859233bbe546bdf789a`, with comparison parent
`9aa8388f39f66fd387422c3eba5a5c6dc0e11b5b` and authoritative main
`6263344e31ba3b0de6539d652f2cd06fc73a3562`. This successor prepares, but does
not run or authorize, one cold HTTP-by-IP product acceptance over an
operator-owned disposable deployment. It also closes three bounded review
findings without reopening R1-R4, D-DHCP, D-WEB, lifecycle ownership or any
historical evidence.

Risk remains L: the change corrects a durable evidence term, tightens a
published-source gate, adds exact source-tree provenance and defines a future
LIVE authorization boundary. The public four-string MCP signature, capability
catalogue, canonical forwarding admission rule and its priority are unchanged.

### Scope and explicit exclusions

In scope are the failed-Git-query distinction, a neutral sampling-stop reason,
actual record/response serialization through the admitted public fixture,
source SHA plus tree retention, an HTTP-only two-client offline trace through
the registered MCP tool, and the exact pending attempt proposal below. No
Packet Tracer process is contacted or launched. No branch is published or
merged, no capability is promoted, no historical blob or record is edited, and
no diagnostic stage is repeated. There is no ping, DNS check, preliminary web
fetch, browser warming, PortFast, port bounce, clock acceleration or alternate
client in the prepared scenario. Product topology removal remains outside the
tool and outside this authorization.

The existing qualification coordinator cannot express this product acceptance.
Its request and authorization bind fixed `__MCP_E6Q_*` fixtures, an empty
workspace, stage-owned creation/removal and a fixed stage budget; D-WEB also
places a ping before its fetch. Reusing it would replace the product path and
violate the cold constraint. The smallest missing LIVE integration is an
out-of-band acceptance adapter with a thin ledgered envelope around the
unchanged four-argument product call. It must extract and reuse the production
session composition currently nested in `register_service_tools`, validate the
authorization-bound channel, and construct that fixed channel before either
runtime exists; checking the MCP tool's internal `pick_channel()` result after
the call would be too late. The adapter reuses the existing isolation,
repository, process-incarnation, campaign-claim and postflight readers; counts
the product transport; protects the two client-release operations; reloads the
`ServiceRunRecord`; and persists an immutable envelope that references that
run. The public MCP schema remains unchanged, and the adapter must not contain
another compiler, applicator, readiness gate, HTTP reader or fixture runner.
This order does not add a dead or unmeasured version of that envelope. The
offline trace and arithmetic below are its design inputs, and LIVE remains
blocked until the envelope has its own reviewed implementation and an exact
operator grant.

### Requirements and acceptance criteria

| Requirement | Acceptance criterion |
| --- | --- |
| H1 Published revisions fail closed | Git availability, repository identity and full-history availability are classified once before assertions. A valid full revision resolves as a commit; a syntactically valid nonexistent 40-hex revision raises the query failure. A failed assertion query is never converted to an environmental skip. Historical bytes and expected digests stay unchanged. |
| H2 Sampling stop is not permission | The FWD-row stop reason becomes the neutral `all_requested_interfaces_observed_forwarding`. Timely admission, late-sample refusal and auxiliary-overrun refusal all retain the same sample history, deadline cause and canonical priority. Legacy `forwarding_sample_admitted` is documented as a non-authorizing sampling diagnostic, not reinterpreted or rewritten. |
| H3 Serialization claims name what was measured | The existing four-group calculation is labelled a synthetic facts-projection estimate. A real admitted two-client fixture measures the exact UTF-8 MCP response and the exact indented `ServiceRunRecord` file, reloads the record, and proves the complete readiness history matches. Neither figure is called a maximum supported topology. |
| H4 Exact source identity survives the product record | `SourceTreeIdentity` adds the Git tree with a compatibility default; production observes `HEAD` and `HEAD^{tree}` together. The registered public route persists both. A future acceptance refuses a missing or mismatched value even though ordinary historical schema-1 records still load. |
| H5 The prepared scenario is the real product path | The registered `pt_apply_enterprise_services` route receives exactly its existing four inputs and an HTTP-only intent with one fresh attempt marker. The manifest is built through the supported plan/deployment contract. E5 readback precedes exact VLAN/port FWD, which precedes exactly one first HTTP-by-IP start for each selected PC. No ping, DNS, hostname fetch or warm-up request appears. |
| H6 Evidence is attributable and durable | Each full HTTP verification row is correlated through its client outcome and carries the exact selected `http://198.18.160.2/` input, its own observed owner, HTTP mode, native Boolean `go()` result, fresh marker-bearing inspection trace and release outcome. The stored record reloads with the same interpretation and full sample history. A timeout stays inconclusive; it is never called a listener refusal. |
| H7 The future campaign fails closed | One attempt only, with a unique deployment id and no prior service-run record for it; any retained E5 row refuses the acceptance. Any source/process/session/manifest mismatch, authorized-channel mismatch, budget or reserve loss, non-FWD/late/ambiguous evidence, malformed or unobservable HTTP result, owner/release contradiction, persistence mismatch or operator stop ends the attempt without an identical retry. Fixture cleanup requires a separate grant. |

### Prepared disposable fixture and product scope

The offline plan/manifest derives one `IE-2000` access switch, one `Server-PT`
and two `PC-PT` clients. Its exact current bindings are
`HQ-DEFAULT-ACCESS-SW-01` `FastEthernet1/1`-`FastEthernet1/3`, VLAN 10;
`HQ-DEFAULT-SERVER-01` `FastEthernet0` at `198.18.160.2/29`;
`HQ-DEFAULT-PC-01` `FastEthernet0` at `198.18.160.3/29`; and
`HQ-DEFAULT-PC-02` `FastEthernet0` at `198.18.160.4/29`. The switch ports are
bound from the plan: PC1 on `FastEthernet1/1`, PC2 on `FastEthernet1/2`, and
the server on `FastEthernet1/3`. These names are a proposed disposable fixture,
not display-label authority: a future grant binds a unique deployment id and
the actual persisted manifest hash, the service-record store must contain no
earlier run for that deployment, and the runtime inventory must reproduce every
binding before an effect. This fresh-history precondition is what makes the
operation arithmetic below apply; `e5_effect_scope.retained` must remain empty.

Allowed product effects are only the plan-derived E5 VLAN, three access-port
and three static endpoint actions; E6 HTTP enable plus marked `index.html`
content; two HTTP client starts; and release of those two owned clients. The
compiled hostname action remains excluded from the governed service closure.
The marker is `COLD_HTTP_<attempt-id>` with the actual attempt id substituted
before the plan is compiled. The URL is HTTP by server IP only. There is no DNS
service in the intent and no hostname expectation. The product leaves the
topology and server page in place.

### Proposed attempt ceiling and feasibility

The proposed build is `9.0.1.0858`, the proposed fixed transport is `file`,
and the attempt count is one. The future acceptance adapter must bind `file`
before session construction; ordinary MCP channel selection is not that gate.
The delivery SHA and tree are deliberately not borrowed from the accepted
input: the grant must name the clean delivery commit and tree produced by this
successor. Until those exact values and the actual manifest/process incarnation
are present in a separate operator grant, the proposal is ungranted.

The fresh-history HTTP-only fixture has an operation ceiling of **1,015**
counted Script Engine calls: five environment/inventory/drift reads; at most
751 E5 calls (361 IOS readiness polls, two IOS batches, one endpoint batch, 21
VLAN reads, three access-port reads and 363 endpoint reads); 187 readiness calls
(31 samples x six nested calls plus one auxiliary read); two E6 apply/direct
reads; and 70 client calls (per client: one start, at most 33 inspections in
the eight-second/0.25-second window, and one release). The last two operations
are a protected client-release reserve. A prior reusable record would add
preverification reads and change the effect meaning, so it is a refusal rather
than another path through this ceiling. This is a proposed ceiling for the
exact plan, not permission to add actions or spend the reserve on observation.

The proposed wall-clock ceiling is **420 seconds**, including the bounded
product windows and two 30-second local lifecycle observations. The final
**40 seconds** are protected for the two three-second release calls, lifecycle
postflight, record completion and campaign-claim release. The current public
tool has no outer ledger that can enforce this ceiling or distinguish release
reserve use. That is the precise missing integration named above, so these
figures cannot authorize LIVE on their own. Delayed-FWD, persistent-LIS,
foreign/ambiguous owner, late sample, auxiliary overrun and HTTP-timeout paths
remain required controls; a lucky immediate-FWD response is not feasibility
evidence.

### Test design and delivery boundary

Focused tests first cover H1, H2 and H4 with causal RED where behavior changes.
The public-route fixture covers H3, H5 and H6 without manufacturing a RED for
behavior already present. Affected published-source, readiness, runtime,
product-tool, persistence and namespace areas follow, then the full offline
suite, MkDocs, whitespace and the quality gate. LIVE acceptance is not an
applicable verification level for this order. The intermittent
`test_no_classified_family_names_a_module_that_stopped_dispatching` observation
remains unresolved: if it recurs in the normal gate, retain the first failure
and investigate that boundary; do not loop until green or call the standalone
reruns a root-cause result.

The handoff status is `READY_FOR_REVIEW`. Exact-SHA CI remains pending without
a publication grant. The pending operator grant must supply the clean delivery
SHA/tree, persisted deployment/manifest identity, exact Packet Tracer process
incarnation and an explicit acceptance of the exclusive disposable-lab and
local receiver-fence limitation before any LIVE command is allowed.

### Measured offline preparation

The admitted two-client S1 fixture, through the registered public MCP route,
produced a 15,106-byte UTF-8 response and an 83,253-byte complete indented run
record in this Windows/Python 3.12 run. The response includes its temporary
record path, so neither byte count is a portable exact-value contract. The test
reads the actual response text and record file, reloads the typed record and
proves every readiness sample remains present. These are measurements of that
DNS-plus-HTTP fixture on this schema, not topology maxima.

The HTTP-only preparation uses a fresh `COLD_HTTP_PREP_ATTEMPT_001` marker and
the same planned physical deployment and an empty temporary service-record
store. The product reports zero retained actions, exactly seven E5 mutations
(one VLAN, three access ports and three static endpoints), and the hostname
action excluded. The simulated page begins with different stale content and is
updated only by parsing the real E6 `setPageContents` dispatch; the direct
readback and both clients then observe the attempt marker. The trace records
one FWD readiness group and exactly one first `http://198.18.160.2/` start for
each client, with E5 readback before FWD and FWD before either start. Both rows
retain their owner, HTTP mode, native Boolean `go()` result, marker-bearing
inspection and `released` outcome; the durable reload agrees with the public
response. The transport trace contains no DNS start, ping or extra web start.
This is offline evidence about the composition only and is not a LIVE product
acceptance.

| Verification | Result |
| --- | --- |
| Final changed-boundary, published-source, persistence and public-tool group | 109 passed |
| Broader affected product, forwarding, readiness and diagnostic groups | 272 passed |
| Full offline pytest (Python 3.12.10, checkout `.venv`) | 6,981 passed, 3 skipped, 3 unchanged deprecation warnings |
| Namespace inventory | 0 active imports, 0 active string references, 0 unreviewed inert mentions |
| Provisional quality gate against `cisco/main` | 118 changed Python files, zero mechanical exemptions, all checks passed |
| MkDocs | exit 0; two pre-existing missing-handoff warnings |
| Whitespace | `git diff --check` exit 0 |

No Packet Tracer process, bridge or LIVE topology was contacted. The
dispatch-inventory test passed in the single normal full-suite run; that result
does not establish the cause of its earlier intermittent failure. Clean
exact-delivery validation and exact-SHA CI are delivery-stage and publication
facts respectively, not relabelled from this provisional worktree run.

## 2026-09-22 minimal cold-HTTP acceptance envelope after `4da4a10` (risk L)

### Identity, instructions and problem

The accepted input is clean branch `feature/server-pt-goal-foundations` at
`4da4a100c95b4ccb25d983d33aa98101a366aa77`, tree
`41a8b049120a935010342468650c0232320cb197`, with authoritative main
`cisco/main` at `6263344e31ba3b0de6539d652f2cd06fc73a3562`. The work runs in
the `Cisco-MCP-server-services-goal-foundations` worktree with its own `.venv`,
as the only writer. `CLAUDE.md`, the imported `AGENTS.md` and this standard were
present in the session's project-instruction context and were read from this
checkout. The interactive `/context` check and a Codex loader check cannot be
run from inside the session, so both remain pending observations rather than
inferred successes.

The preparation above specified, but did not build, the envelope that a LIVE
cold-HTTP acceptance needs: the public tool has no outer ledger, no fixed
authorized channel, no protected release reserve, no pre-effect binding of the
compiled closure to a grant and no durable acceptance record. This block
implements that envelope offline, around exactly one unchanged invocation of
`apply_enterprise_services`. It authorizes nothing: no Packet Tracer contact or
launch, no bridge start, no publication, merge or capability promotion.

Risk stays L: it adds an authorization boundary, evidence persistence and three
optional internal hooks on the product path, and it shares the production
session composition between two routes.

### Scope and explicit exclusions

In scope: extraction of the product session composition; extraction of the
registry's channel guards and targeted-inventory script so a fixed channel can
reuse them; the default-off hooks named below; protected-release accounting in
the existing `OperationLedger`; a bounded any-status history read on the run
store; the domain grant, scope, ordering and verdict rules; the application
coordinator; the envelope store; the out-of-band CLI adapter; tests; and this
section.

Excluded: LIVE work of any kind, D-WEB or any ping, DNS, hostname, HTTPS, DHCP
or mail path, topology creation or removal, workspace restoration, a second
service workflow, any change to the qualification coordinator beyond the
additive ledger accounting, capability or catalogue changes, the public
four-string MCP schema, and dependency updates. R1-R4, the three preparation
follow-through items, historical evidence and the unintegrated DHCP assessment
stay closed and non-authorizing.

### Architecture decision

```text
CLI adapter ──► accept_cold_http (application) ──► apply_enterprise_services
   │  composes         │ grant/scope/verdict rules (domain)       ▲ unchanged
   │  production       │ OperationLedger + LedgeredTransport      │ use case
   ▼  boundaries       ▼                                          │
compose_service_session (adapters, shared with the MCP tool) ─────┘
   └─ FixedChannelProductTransport ─► LedgeredTransport ─► FileBridge
```

- **One composition.** `adapters/service_session.py` owns
  `compose_service_session`, the former `bind_session` closure plus the
  source-tree observer. `register_service_tools` calls it with the picker
  (lazy, after A1/A4, unchanged); the acceptance calls it with a selection that
  was bound before any runtime existed. Both routes therefore reach the same
  runtimes, compilers, applicators, readiness rule, HTTP scripts and stores.
- **Fixed channel.** The only channel the envelope accepts is `file`. The grant
  is checked against it before contact, the heartbeat is read before the ledger
  exists, and `FixedChannelProductTransport` refuses any other channel name
  instead of routing it, so a substituted channel fails before dispatch. The
  ordinary picker is never consulted. Guards and the targeted inventory script
  now live in `infrastructure/execution/product_channel.py`, used by the
  registry closures and the fixed channel alike.
- **Three minimal internal hooks, all default-off.** (1)
  `ServiceInvocationBinding.effect_admission` is asked once, after A10 and
  before E1, with the compiled `ServiceEffectClosure`; a non-empty answer or an
  exception refuses with `effect_scope_not_admitted` before any effect. (2)
  `PacketTracerEnterpriseServiceRuntime(owned_release=...)` enters a caller
  scope around the single release dispatch in `_finalize_client`; nothing
  inspects JavaScript. (3)
  `PacketTracerEnterpriseConfigurationRuntime(wait_allowance=...)` hands the
  runtime's clock, sleeper and that control to every E5 waiter and to the IOS
  boot wait, which `ControlledIosExecutor.wait_until_ready` now accepts as
  optional arguments. With the defaults, every existing composition builds the
  same objects it built before.
- **Ledger reuse.** The acceptance reuses `OperationLedger` and
  `LedgeredTransport`. `OperationLedger.protected_release()` admits one call
  against the reserve: it is charged to the reserve, capped by the absolute
  deadline and still decided by the effect guard. Ordinary allowance becomes
  `max - reserve - (used - reserve_used)`, which is the old value whenever no
  protected release happened, so the qualification stages are unchanged. The
  scope lasts one dispatch; it never switches the invocation into finalization.
- **Authority per dispatch.** Every product dispatch runs inside one ledger
  effect scope whose guard verifies the held campaign claim, a local file read
  that costs time and no bridge operation. The first loss is sticky and refuses
  every later call, protected releases included. Process continuity is the
  lifecycle pairing before transport and after the product returns. Neither is
  an in-band receiver fence.
- **Labels, not parsing.** The coordinator wraps the binding's runtimes,
  observer and inventory reader with ledger purposes (`a5_environment`,
  `a8_inventory`, `a10_drift`, `e5_apply`, `e5_verify`, `readiness`,
  `e6_apply`, `e6_verify:<expectation>`, `owned_release:<expectation>`). The
  ordering oracle reads that ledger sequence together with the reloaded record.

### Requirements and acceptance criteria

| Requirement | Acceptance criterion |
| --- | --- |
| C1 Grant before anything | A missing, malformed or inconsistent grant, a channel other than `file`, a budget other than the frozen proposal, a marker other than `COLD_HTTP_<attempt>`, a URL other than `http://<server>/` or an unaccepted lab/fence limitation refuses before any reader, claim or transport. |
| C2 Source, process and manifest | Import isolation must be `ISOLATED` in this process (pytest and foreign origins refuse); the checkout must be clean, published and equal to the granted SHA and tree; one Packet Tracer process must match the granted PID, path, build and incarnation with an empty mailbox; the stored manifest must equal the granted hash, topology hash and build. Each mismatch refuses before the channel is opened. |
| C3 Fresh history, one attempt | The campaign claim and permanent attempt reservation are taken in the shared scope first. Any stored entry for the deployment, of any status, refuses; an unreadable history refuses; nothing is deleted. |
| C4 Fixed channel | The file heartbeat must be fresh before the ledger is built; another channel name at any product call raises before dispatch; the record must name `file`. |
| C5 Exact closure before E1 | The compiled closure must be the granted one: one VLAN, three access ports and three static endpoints on the granted names, ports, addresses and gateway with no DNS server, only hostname excluded, nothing retained, only HTTP enable and marked content on the server, and exactly the two granted by-IP HTTP fetches plus exactly one direct read. A tree-less or dirty source identity also refuses there. |
| C6 Bounded, truthful execution | Every dispatch is counted once and admitted against one absolute deadline; E5 waits, readiness and HTTP polling end when allowance ends, without a local spin; the stop is reported by its boundary; no mutation is repeated or rerouted. |
| C7 Protected release | Two release dispatches and the last forty seconds are reserved; ordinary calls never reach them; PC1's release does not end ordinary work for PC2; after ordinary exhaustion only owned releases dispatch; after authority loss none does, and ownership is reported unresolved. |
| C8 Ordering oracle | Each client's first dispatch is its only start, it follows the last E5 readback and a readiness observation, itself after that readback, whose sample is authoritative and FWD on the exact granted switch, VLAN and ports; the first client the product tests completes before the next starts. A bypassed gate fails even when the page answers. |
| C9 Durable interpretation | The reloaded `ServiceRunRecord` must agree with the public result and the grant (identity, source tree, status, scope, clients, releases, readiness history); a legacy record without a tree loads but cannot pass. |
| C10 Evidence and verdict | One write-ahead envelope is begun before contact and completed once, never rewritten, referencing the record by path and SHA-256. Campaign completion and HTTP acceptance are separate fields; a timeout is inconclusive; release, persistence and postflight failures are kept apart from the primary failure. |
| C11 Parity | The MCP route and the acceptance route produce the same product result on the same controlled terminal, apart from run identity, label, record path, clock-derived fields and the declared envelope overhead. |

### Invariants

- The public tool keeps exactly `intent_json`, `deployment_id`,
  `packet_tracer_version` and `run_label`, and never receives a hook.
- No acceptance code builds JavaScript, IOS or a URL of its own; its only
  scripts are the product's and the extracted registry ones.
- A refused call never reached the channel; a counted call reached it once.
- Local reads (git, lifecycle, claim, stores) spend time, never operations.
- The reserve is spent only inside `protected_release`, and only on releases.
- Client release is not workspace restoration: the topology and page remain.

### Budget arithmetic, recomputed from the executed code

The proposal's breakdown was checked against the nested code as it actually
dispatches, and two lines were wrong. E6 applies in two phase batches, HTTP
enable at phase 20 and the marked content at phase 30, before its one direct
read, so E6 costs 3 dispatches, not 2. A readiness window of 30 seconds sampled
every second cannot start a 31st sample: the loop sees its deadline before the
31st, so the enforced sample cap of six calls gives 30 x 6 + 1 = 181 dispatches,
not 31 x 6 + 1 = 187. The frozen ceiling of 1,015 is therefore not raised and
not reinterpreted; it covers the recomputed worst case with five operations of
margin, and that margin authorizes nothing.

| Boundary | Calls | Derivation |
| --- | --- | --- |
| A5 environment, A8 inventory, A10 drift | 5 | 1 + 1 cached targeted read + 3 endpoint reads |
| E5 IOS boot wait | 361 | 90 s / 0.25 s, first read included |
| E5 batches | 3 | 2 IOS phases + 1 endpoint payload |
| E5 VLAN, access-port and endpoint readback | 387 | 21 + 3 + 3 x 121 |
| Readiness | 181 | 30 samples x 6 nested calls + 1 auxiliary read |
| E6 phase batches and direct read | 3 | enable batch, content batch, direct read |
| Clients | 70 | 2 x (start + 33 inspections + release) |
| Envelope overhead | 0 | local reads only, measured by the parity trace |
| **Worst case** | **1,010** | 1,008 ordinary + 2 protected releases |
| Frozen ceiling | 1,015 | 1,013 ordinary + 2 reserved; margin 5 |

The executed worst case is a test, not only arithmetic: a controlled terminal
that answers every bounded wait only on its last permitted read (IOS ready at
90 s, VLAN at 5 s, each endpoint at 30 s, FWD at 29 s, the page at 8 s) is
accepted after exactly 950 dispatches, which is the table with the simulator's
measured 4 calls per readiness sample in place of the cap of 6
(950 - 121 + 181 = 1,010).

Worst-case wall clock from the per-call timeouts is about 400 seconds: two
30-second lifecycle observations, 29 seconds of admission reads (10 + 10 +
3 x 3), 93 seconds of IOS boot wait, 8 + 18 + 99 seconds of E5 readback, 30
seconds of readiness, 25 seconds of E6 (two 10-second batches and a 5-second
direct read) and 2 x 19 seconds of client fetches. The ordinary part, PC1's
release included, is about 367 seconds against the 380-second ordinary
deadline; the protected tail (PC2's 3-second release, the 30-second postflight
and local completion) fits the 40-second reserve. These are timeouts added up,
not measured LIVE durations. The ledger enforces the ceiling whatever the
receiver does, so the contract is bounded execution and a truthful stop, not
completion under every timing; the same worst-case run takes 231 simulated
seconds.

### Test design

Unit: grant, closure, lifecycle, ordering and verdict rules; ledger protected
accounting; the E5 wait control and IOS boot wait; the owned-release scope;
the fixed channel; the any-status history read; the envelope store. Integration
and system: the coordinator over the real shared composition, product use case,
runtimes, readiness loop and stores, with only the terminal, clock, git,
process table and campaign scope controlled. Acceptance-level cases follow the
work order's list one by one, including the counterfactual gate bypass and the
MCP/acceptance parity trace. LIVE acceptance is not an applicable level here.

### What was delivered, path by path

- `adapters/service_session.py` holds `compose_service_session`, the former
  nested `bind_session`, and the source-tree observer. `SessionControls` is
  its only extension point and every field defaults to `None`.
- `adapters/mcp/service_tools.py` composes through it with the unchanged
  picker policy and passes no control. `adapters/mcp/tool_registry.py` takes
  its guards and targeted inventory script from
  `infrastructure/execution/product_channel.py`, which also holds
  `FixedChannelProductTransport`.
- `adapters/cli/cold_http_acceptance.py` is the operator entry point.
  `adapters/cli/service_qualification.py` publishes its existing repository
  and runtime-identity readers for reuse instead of a copy.
- `application/use_cases/accept_cold_http.py` and
  `application/ports/cold_http_acceptance.py` are the coordinator and its
  store contracts. `apply_enterprise_services.py` gains the A11 admission and
  the closure builder; `qualify_server_services.py` gains protected-release
  accounting.
- `domain/enterprise/models/cold_http_acceptance.py` (grant, proposal,
  admission and closure rules, envelope) and
  `domain/enterprise/services/cold_http_acceptance_evidence.py` (reload,
  identity, readiness, ordering and per-client judgement).
  `domain/enterprise/models/service_entry.py` gains the closure models and
  `effect_scope_not_admitted`.
- `enterprise_configuration_runtime.py` (`wait_allowance`),
  `ios_terminal.py` (optional boot-wait controls),
  `enterprise_service_runtime.py` (`owned_release`),
  `service_run_record_store.py` (`deployment_history`, `load_evidence`) and
  the new `infrastructure/persistence/cold_http_acceptance_store.py`.
- Tests: the public-route terminal moved to `tests/service_product_simulation.py`
  and is shared; `tests/cold_http_acceptance_harness.py` adds time to it and
  controls only git, the process table, the clock and the campaign scope;
  `test_bounded_product_waits.py`, `test_cold_http_acceptance_rules.py`,
  `test_cold_http_acceptance_boundaries.py` and
  `test_cold_http_acceptance_route.py` are new; the store and surface suites
  and the destructive-call corpus check are extended to the new modules.

### Requirement-to-test mapping

| Requirement | Tests |
| --- | --- |
| C1 | route `test_an_invalid_or_missing_grant_refuses_before_any_contact` (11 cases), `test_an_intent_other_than_the_granted_input_refuses`; rules `test_each_malformed_grant_field_is_named`, `test_a_missing_grant_field_is_missing_not_defaulted`, `test_the_granted_selection_must_be_one_segment_of_distinct_endpoints` |
| C2 | route `test_a_source_mismatch_refuses_before_the_claim`, `test_a_process_mismatch_refuses_before_contact`, `test_a_pytest_or_foreign_process_refuses`, `test_a_manifest_other_than_the_granted_one_refuses`; boundaries `test_the_production_wiring_refuses_under_pytest_before_any_channel` |
| C3 | route `test_an_attempt_identity_is_spent_once_and_never_reset`, `test_a_held_campaign_lock_refuses_and_is_left_as_found`, `test_any_prior_run_of_the_deployment_refuses_before_a_product_record`, `test_unreadable_history_is_not_empty_history`; store history tests |
| C4 | route `test_an_unavailable_granted_channel_refuses_without_fallback`, `test_a_substituted_channel_refuses_before_any_dispatch`, `test_a_product_call_naming_another_channel_raises_before_dispatch`; boundaries fixed-channel tests |
| C5 | route `test_a_source_identity_without_a_tree_refuses_before_effects`, `test_a_closure_the_grant_does_not_name_refuses_before_effects`, `test_a_dirty_executing_tree_refuses_before_effects`; rules `test_any_material_change_to_the_closure_is_a_finding` |
| C6 | route `test_expiry_during_the_e5_boot_wait_stops_without_a_spin`, `test_expiry_during_readiness_stops_the_episode_and_starts_no_client`, `test_expiry_during_http_polling_keeps_the_protected_releases`, `test_every_bounded_wait_run_to_its_last_read_fits_the_frozen_ceiling`, `test_the_lifecycle_reads_share_the_attempt_deadline`; `test_bounded_product_waits.py`; rules arithmetic tests |
| C7 | route `test_every_unresolved_release_exit_withholds_acceptance` (6 exits), `test_an_undelivered_start_is_still_finalized_by_one_release` (2), `test_a_client_that_was_never_created_needs_no_release_dispatch`, `test_an_early_release_leaves_ordinary_work_to_the_next_client`, `test_after_ordinary_exhaustion_only_owned_releases_dispatch`, `test_lost_authority_declines_every_later_dispatch_including_releases`; ledger and owned-release unit tests |
| C8 | route `test_forwarding_at_the_first_sample_is_accepted`, `test_delayed_forwarding_is_accepted_only_after_it_was_observed` (4 s and 26 s), `test_persistent_listening_dispatches_no_request`, `test_forwarding_evidence_that_arrives_late_dispatches_no_request`, `test_foreign_or_ambiguous_forwarding_evidence_dispatches_no_request`, `test_each_client_has_exactly_one_first_request_in_the_products_order`, `test_a_bypassed_readiness_gate_fails_the_ordering_oracle`; rules oracle tests |
| C9 | route `test_the_durable_record_is_reloaded_and_cited_by_its_bytes`, `test_a_record_that_contradicts_the_public_result_is_not_accepted`, `test_a_record_that_cannot_be_reloaded_is_not_accepted`; rules `test_a_legacy_record_without_a_tree_loads_but_cannot_pass` |
| C10 | route `test_an_http_timeout_is_inconclusive_and_never_a_listener_refusal`, `test_a_product_persistence_failure_is_classified_apart`, `test_an_envelope_that_cannot_be_completed_withdraws_acceptance`, `test_a_postflight_that_does_not_pair_is_a_postflight_failure` (3), `test_an_unresolved_fire_and_forget_send_withholds_acceptance`, `test_the_envelope_names_what_it_does_not_claim`; envelope store tests |
| C11 | route `test_the_mcp_route_and_the_acceptance_route_run_the_same_product`; boundaries `test_the_composition_is_lazy_and_inert_without_controls`, `test_the_public_tool_composes_no_governing_control`; the unchanged public-route surface suite |

### Causal RED and what was not manufactured

`tests/test_bounded_product_waits.py` was written first and failed 10 of its
11 tests against the unchanged code: the E5 runtime took no allowance and its
waiters polled a refusing channel on their own clock, `wait_until_ready`
accepted no control, the E6 runtime had no release scope, and the ledger had
no protected release or reserve accounting. The eleventh test is the
inertness guard for the default composition and is meant to pass on both
sides. The grant rules, coordinator, store, adapter and evidence judge are new
behavior with no earlier version to fail against; their tests are positive
and negative controls, and the counterfactual gate bypass is the negative
control of the ordering oracle.

### Independent review before delivery, and what it changed

One read-only Codex review of the uncommitted diff (no writes, no test runs,
one writer in this worktree) reported nine findings. Each was re-checked
against the code before acting; eight were real and are fixed, one is a
deliberate property of the product and is kept.

| Finding | Disposition |
| --- | --- |
| A grant with `reserve_operations`, `reserve_seconds`, `max_*`, `vlan_id` or `prefix_length` equal to zero skipped its check (`if value`), so ordinary work could reach an unreserved ceiling | Fixed: the reader returns `None` only for a missing or malformed field and every read integer is compared, zero included |
| A forwarding sample taken before the last E5 readback could admit a request | Fixed: `forwarding_observed_before_e5_readback_finished` |
| Endpoint gateway and DNS server were compiled effects outside the granted signature; zero or two direct page reads passed | Fixed: the grant binds a segment `gateway`, no endpoint may receive a DNS server, and exactly one direct HTTP read on the server is admitted |
| The readiness judgement trusted the recorded `admitted` flag | Fixed: execution, freshness, completeness, VLAN presence, observed device, `confirmed_unique` identity, window, VLAN and ports are re-read from the sample and from the deciding sample |
| The reloaded record's service hash and selected E6 identities were not bound | Fixed: the closure carries the same full-plan service hash the record keeps, and both hash and selected ids must agree |
| Completion checked and then replaced the envelope file, so two completions could race | Fixed: the terminal envelope is a second file created by one atomic no-overwrite link; the write-ahead file is never rewritten |
| A malformed readiness row could raise out of the judge and leave the envelope unfinished | Fixed: row shapes are read defensively, and any judge failure becomes `evaluation_failed:<type>` in a completed envelope |
| The claim was released after the verdict, so a failed release could sit beside `http_accepted: true` | Fixed: the claim is released before judgement and a failed release is a stop fact |
| PC1 of the grant may be tested after PC2 | Kept: the product orders clients by expectation id, so "PC1" means the client it tests first. The oracle requires that client to be finished and released before the next one starts, and each client row reports its `request_order` |

The 29 regression cases for the eight fixed findings were run against the
code with the fixes reversed and all 29 failed, the zero-reserve grant among
them; the store race is excluded from that count because its fix replaced
the write path rather than a line, and its regression pre-creates the winning
file and checks that it survives. With the fixes restored they all pass.

### Residual limitations

- The local authority check and the process pairing are not an in-band
  receiver fence. A replacement Packet Tracer that answers mid-run is
  detected by the postflight pairing, after the fact; the envelope then
  withholds acceptance and says so.
- The envelope judges the readiness sample the product parsed and recorded;
  it keeps the raw client start and release answers, not the raw STP pages.
- The public tool's own stores are relative to the MCP server's working
  directory. The envelope reads and writes under `<governed root>/data`, so
  the manifest must be persisted there and history elsewhere is not visible.
- A fire-and-forget E5 send still pending at finalization withholds
  acceptance; it cannot prove that the send did or did not execute.

### Pending operator grant

Nothing here authorizes a LIVE attempt. One needs a separate grant document,
checked field by field before contact, naming exactly:

- the clean delivery commit and tree of this successor, published as its
  upstream, because the shared repository rule refuses an unpublished HEAD;
- build `9.0.1.0858`, channel `file`, and the frozen ceiling 1,015 / 420 /
  2 / 40;
- a unique deployment id, its persisted manifest semantic and physical hashes
  under `<governed root>/data/deployments`, with no stored run of any status
  under `<governed root>/data/services/<deployment>`;
- the runtime names, switch ports, VLAN, prefix, gateway and addresses that
  manifest and the compiled plan resolve, since the fixture values are
  proposals (the fixture compiles gateway `198.18.160.1` and no DNS server);
- the SHA-256 of the exact intent file, whose page content is
  `COLD_HTTP_<attempt>` and whose URL is `http://<server>/`;
- a fresh 32-hex attempt id and the Packet Tracer PID, path and creation
  identity read immediately before the attempt;
- `exclusive_disposable_lab: true` and
  `local_fence_limitation_accepted: true`.

It runs from the checkout's own interpreter, never under pytest:
`.venv\Scripts\python.exe -m packet_tracer_mcp.adapters.cli.cold_http_acceptance --execute --grant <grant> --intent <intent>`
with `PT_MCP_GOVERNED_ROOT` set to the checkout. Fixture cleanup, workspace
restoration and any second attempt need their own grants.

### Measured offline verification

Windows, Python 3.12.10, this checkout's `.venv`. No Packet Tracer process,
bridge, mailbox or LIVE topology was contacted, launched or read.

| Verification | Result |
| --- | --- |
| Hook RED before implementation (`test_bounded_product_waits.py`) | 10 failed, 1 passed (the inertness guard) |
| Review regressions with the eight fixes reversed | 29 failed |
| Acceptance-area suites on the final tree | 202 passed: bounded waits 11, route 80, rules 83, boundaries 28 |
| Run-record store suite, extended | 44 passed |
| Affected product, qualification, runtime, readiness, transport and surface groups (before the review fixes) | 1,911 passed |
| Full offline pytest, first run (before the review fixes) | 7,162 passed, 3 skipped, 4 warnings, exit 0 |
| Full offline pytest, final tree | 7,192 passed, 3 skipped, 3 warnings, exit 0 |
| Provisional quality gate against `cisco/main` (`6263344`) | 132 changed Python files, zero mechanical exemptions, all checks passed |
| Namespace inventory | 0 active imports, 0 active string references, 0 unreviewed inert mentions |
| MkDocs | exit 0; the two pre-existing missing-handoff warnings |
| Whitespace | `git diff --check` exit 0 |

The three warnings of the final run are the pre-existing
`PytestRemovedIn10Warning` class-fixture deprecations. The first run showed a
fourth: a `PytestUnhandledThreadExceptionWarning` from a worker thread of
`tests/test_native_ui_phone_control_driver.py`, a `PermissionError` on a
temporary request file. That module and the driver it tests are untouched by
this delivery and the test passed; the warning did not recur in the final run,
which was run once for the final tree, not repeated to make it disappear, and
its cause is not established here. The intermittent dispatch-inventory gate named in earlier sections
passed in both full runs; that says nothing about its cause.

The executed worst case, the parity trace and every route test drive the real
composition over a controlled terminal and a fake clock. They establish the
envelope's offline behavior and dispatch arithmetic, not Packet Tracer
behavior, receiver timing or LIVE acceptance. Exact-SHA CI needs a separately
authorized publication. The delivery commit and tree are reported in the
handoff, because a commit cannot contain its own identity; the clean
exact-delivery gate is run on that commit. Delivery status is
`READY_FOR_REVIEW`, not acceptance.

## 2026-09-22 execution-contract repair and scalable HTTP-by-IP profile after `7736546` (risk L)

### Identity and instructions

Input: clean `feature/server-pt-goal-foundations` at
`77365460a6caaf85f5caec5fee20d70eec3a2d61`, tree
`cbd22ffd9811edd3ad74236b696b4cd641822ebd`, reviewed parent `4da4a10`, with
`cisco/main` resolving to `6263344e31ba3b0de6539d652f2cd06fc73a3562` and an
ancestor of HEAD. The package resolves to this checkout's `src` from its own
`.venv`. `AGENTS.md`, `CLAUDE.md` and the standard were read from this checkout
and still have the digests recorded above (`a9f0e384...`, `29312201...`,
`2de0d5b2...`); `/context` and a Codex loader listing cannot be observed from
this session and stay pending. The work order
`Unified_ServerPT_HTTP_Safety_and_Scale_Opus55_GPT6Sol.md` authorizes offline
implementation, tests and local commits only: no Packet Tracer contact, launch
or mutation, no publication, merge, claim reset, capability promotion, bridge
protocol change or CP-SCALE mutation. Existing Q/D attempts stay consumed.

### Problem and intended outcome

Four defects make the one-attempt envelope weaker than its record claims, and
the product it governs is still limited to one access switch:

1. `_Attempt.authority` decides each dispatch against the campaign claim only.
   A replacement Packet Tracer that polls the same mailbox receives every later
   product command until postflight notices it.
2. `_complete` sets `completed_at` and then calls `begin` on an unbegun
   envelope, which the store refuses, so a reserved attempt refused on process,
   history or manifest admission leaves no durable reason.
3. `_contact` and `_verify_http` handle `Exception` only; a `KeyboardInterrupt`
   after a client was created skips its release and the terminal envelope.
4. The deadline check precedes the record reload, the claim release and the
   verdict, so a verdict can be published after the absolute limit.

Beyond repair, two clients are the legacy smoke profile, not a product
invariant. The outcome is one delivery where A1-A4 are closed with causal
regressions, the public product admits plan-derived N-client and multi-access
same-VLAN paths with per-dependency evidence, a versioned scalable acceptance
profile derives its scope and budget from the manifest and compiled plans, and
the cost of evaluation and evidence scales with the work.

### Scope and explicit exclusions

In scope: the acceptance coordinator, its ports, envelope store use and CLI
(`--prepare` is added); the receiver-continuity reader; the E6 client
finalization; the product's path admission, readiness plan, readiness gate and
E5 endpoint batching; a registered trunk-continuity observation; the domain
path, continuity, scope, cost and evaluator rules; tests, a plan-driven campus
simulator and a scale benchmark; this section.

Excluded: LIVE work, wireless, dynamic-routing qualification, DNS/hostname
paths, mail, DHCP acquisition, HTTPS, a replacement service runtime, a second
product path, changes to E5 trunk verification semantics, to the bridge or to
the MCP four-input signature, and mutation of CP-SCALE fixtures, evidence or
other worktrees. Routed completion is not claimed (see B7).

### Design delta

**A1 - receiver continuity per governed dispatch.** The ledger already asks
`_Attempt.authority` immediately before each effect-scope dispatch, protected
releases included, and recomputes allowance after it. The guard now also takes
one fresh receiver observation, bounded by the dispatch's absolute deadline and
the local observation cap, and compares it with the preflight incarnation using
the existing `diagnostic_lifecycle_continuity` rule (mailbox traffic excluded,
as in the diagnostic `live_authority`) plus the granted build binding. Missing,
changed, ambiguous (zero or several Packet Tracer processes) or unreadable
observations lose authority irreversibly; claim loss still does. Postflight
stays. The receiver port is `AcceptanceBoundaries.bind_receiver(preflight,
deadline) -> ReceiverContinuity`. Its default re-reads the full lifecycle per
dispatch (correct but slow). Production composes a Windows handle-bound reader:
after preflight it opens a query/synchronize handle on the paired PID, confirms
the pairing with one more full read (PID and creation identity unchanged, so
the handle names that incarnation; Windows does not reuse a PID while a handle
is open), and then answers each dispatch from a fresh read of that handle
(not signalled, same creation time, same image path) and of the process table
(exactly one Packet Tracer image, that PID). Versions are properties of the
bound image and are carried from the confirmed pairing; nothing about
permission is cached. The interval between the local check and the receiver
executing the command remains unfenced and is declared.

**A2 - durable reserved refusals.** The write-ahead envelope is begun right
after the claim and permanent reservation, before the process, history and
manifest reads. Every later refusal completes it once with its reason.
`_complete` never sets `completed_at` before a begin exists, and the store's
incomplete-begin invariant is unchanged. A begin that fails is a persistence
failure (`envelope_persisted: false`), reported apart from ordinary refusals.

**A3 - cancellation is terminal.** `_verify_http` attempts the owned release on
a non-`Exception` interruption exactly once (never when the interruption hit
the release itself) and re-raises. The coordinator catches `BaseException`
after the claim: it stops ordinary work, finalizes the envelope with
`cancelled:<type>@<boundary>` as the primary failure, derives unresolved
ownership from the ledger and tap, never converts to success, and re-raises
the original exception. An interruption inside finalization still completes
the envelope. An uncatchable kill is not covered.

**A4 - one temporal contract through publication.** The absolute attempt
deadline is checked at the publication boundary, after the record reload, the
claim release and the verdict and immediately before the terminal write. Past
it, acceptance is withheld as `acceptance_deadline_exceeded:<boundary>` while
the reloaded evidence is kept. `elapsed_at_verdict_seconds` and
`completion_seconds` are recorded; the write itself is not claimed to be
preemptible.

**B1 - versioned profiles.** Grant schema 1 stays the legacy two-client smoke
profile with its frozen 1,015 / 420 / 2 / 40 proposal and unchanged rules.
Schema 2 is the scalable profile `http_by_ip_scalable_v1`: it names the
selected client and server deployed names, the digest of the derived scope and
an explicit budget equal to the derived proposal. A schema 1 grant or envelope
is never read as schema 2.

**B2 - derived scope.** The product closure (`ServiceEffectClosure`) gains the
per-client dependency paths and readiness groups on deployed names. The
acceptance scope (server, clients, placements, paths, groups, E5 signatures,
checks, cost model) is derived from it and hashed canonically. A schema 2 grant
must list exactly the selected client set; duplicates, omissions, foreign
names, a scope digest or budget other than the derived ones, and any client
whose binding or path is unobservable refuse at A11, before E1. `--prepare`
computes the same scope offline from the stored manifest and intent.

**B3 - N clients.** No client-position branch remains. Each selected client
has one first request, one outcome and one bounded release charged to the
protected reserve, whose size is the selected client count. The product's
deterministic order is kept and clients stay sequential.

**B4 - public admission.** `_unsupported_paths` classifies each selected
client-to-server dependency from the compiled plans. A same-VLAN path between
two access switches is admitted when the compiled trunk links carrying that
VLAN connect them. The foundation identity, model, static/DHCP, site and
single-placement guards are unchanged, and a routed path still refuses at A8.

**B5 - dependency readiness.** The readiness plan yields access groups per
`(switch, VLAN)` and trunk-continuity groups per `(VLAN, component)`. A
dependent names every group its path needs and is admitted only when all admit
it; a failed shared group blocks its dependents only. Memo keys are the
complete identity (semantic switch ids, deployed names, VLAN, interface set)
plus a dependency revision that `invalidate_devices` advances. Group ceiling
and time budget are derived from the plan and equal the legacy 4 / 120 s
whenever the plan fits them.

**B6 - trunk continuity.** A new bounded runtime observation reads the
registered `show interfaces trunk` on each switch of the component per round,
through the same bounded channel as the forwarding observer. An edge is usable
only when both ends are fresh, complete, uniquely attributed, trunking, and
carry the VLAN as allowed, active and forwarding. A dependent is admitted when
its client and server switches are connected by usable edges in a timely,
authoritative round; an unreadable switch makes its edges unusable. Rounds
stop when every required pair is connected or the window closes. STP-blocked
redundant trunks are therefore not failures, which is why trunks stay outside
the governed E5 closure: the E5 trunk readback requires forwarding on every
trunk and would refuse the planner's own redundant campus.

**B7 - routed paths, the named blocker.** The planner routes a separate server
segment through SVIs on a 3560. No registered E5 action enables IPv4 routing on
that device and no registered observable reads its routing table (`show ip
route` is registered only filtered by OSPF, EIGRP and RIP). Routed dependents
therefore refuse at A8 as
`routed_path_unobservable:ipv4_routing_action_and_route_table_reader_unregistered`,
with the derived gateway interfaces and trunk components named. No routed
completion is reported.

**C1 - cost model.** A pure model derives, from unique E5 actions, IOS devices
and phases, endpoint sends, readbacks, readiness groups and their bounded
samples, continuity rounds, selected client checks and releases: ordinary
operations, reserved release operations, ordinary seconds, polling windows and
reserved finalization seconds. The legacy table stays the schema 1 proposal;
schema 2 requires the grant to equal the derived proposal. An executed worst
case must not exceed it.

**C2 - linear evaluation.** The evaluator builds one index of ledger entries by
purpose and expectation and one of record rows by expectation, then judges each
client from them.

**C3 - bounded batches.** Endpoint addressing is sent in chunks of at most 64
calls, each its own batch id, so script size is bounded and a failed chunk
marks only its actions.

### Requirements and acceptance criteria

| Id | Acceptance criterion | Tests |
| --- | --- | --- |
| R-A1 | After a replacement at a transport milestone (different PID, same PID with a new incarnation, receiver gone, two receivers, unreadable identity) no later governed dispatch, protected release included, reaches the terminal; authority loss is sticky and named; a failed product read with an unchanged receiver is still accepted; claim loss still blocks | `test_cold_http_contract_repairs.py` |
| R-A1c | The handle-bound reader detects exit, a second image and a changed path, charges its cost, and falls back to a full read when it cannot bind | `test_receiver_continuity.py` |
| R-A2 | A refusal after reservation on process, history and manifest admission reloads from the real store with its attempt id and reason; an unwritable store is a persistence failure, not an ordinary refusal | `test_cold_http_contract_repairs.py` |
| R-A3 | Interruption during start, inspection, release and record reload leaves one terminal envelope with the cancellation primary, at most one release dispatch per client, no acceptance, and the original exception re-raised | `test_cold_http_contract_repairs.py` |
| R-A4 | A successful run whose record reload crosses the deadline is not accepted and keeps its evidence; an on-time control is accepted | `test_cold_http_contract_repairs.py` |
| R-B1/B2 | Schema 2 grants refuse duplicates, omissions, foreign clients, a wrong scope digest or budget and unobservable bindings before E1; schema 1 behaviour is unchanged | `test_scalable_http_acceptance.py`, existing acceptance suites |
| R-B3 | 2, 20, 200 and 1,000 selected clients each get one first request, one outcome and one release, in the product order | `test_http_acceptance_scale.py` |
| R-B4/B7 | Multi-access same-VLAN paths are admitted by the public tool; routed paths refuse before any effect naming the contract; other guards unchanged | `test_service_path_closure.py`, `test_http_acceptance_scale.py` |
| R-B5/B6 | Faults on a shared trunk, one client port and an unrelated branch block exactly their dependents; every selected client stays represented; memo reuse and invalidation follow identity and revision | `test_readiness_dependency_groups.py`, `test_trunk_continuity.py`, `test_http_acceptance_scale.py` |
| R-C1 | The derived model covers the executed worst case; schema 1 values are untouched | `test_scalable_http_acceptance.py` |
| R-C2/C3 | Evaluation is linear in retained evidence; endpoint sends are bounded and partial | `test_http_acceptance_scale.py`, `test_bounded_endpoint_batches.py` |
| R-C4 | Campus at least as large as CP-SCALE in declared devices and links, and growth for immediate, delayed and persistent non-FWD, measured with authority-check cost | `test_http_acceptance_scale.py`, benchmark below |
| R-D1 | MCP and acceptance routes agree on the same controlled backend; default-off hooks leave legacy, qualification, Voice and namespace behaviour unchanged | existing parity and surface suites |

### Invariants

- The public tool keeps its four inputs and composes no control.
- No acceptance code builds JavaScript, IOS or URLs of its own.
- One observation decides one dispatch; nothing about permission is reused.
- A schema 1 grant is decided exactly as before, frozen budget included.
- Nothing outside the admitted closure is mutated; trunks, transit VLANs and
  SVIs are proven, never configured, by the service path.
- A refused call never reached the channel; a counted call reached it once.
- Historical evidence is not rewritten; failed evidence is kept.

### Test design

Unit: path classification, continuity rule, readiness plan and gate, scope and
cost derivation, evaluator indexes, receiver reader (fakes plus the current
process on Windows). Integration and system: the real coordinator, stores,
shared composition, product use case, runtimes and readiness loop over a
plan-driven simulated terminal, labelled as simulated Packet Tracer. LIVE
acceptance is not applicable to this delivery.

### Current projection

What holds for a governed HTTP-by-IP acceptance attempt after this block,
superseding the earlier blocks where they differ:

- **Two profiles.** Schema 1 is the legacy two-client profile with its frozen
  `1015/420/2/40` ceiling and rules. Schema 2, `http_by_ip_scalable_v1`,
  selects every client of every eligible service, and its grant must equal the
  scope, digest and cost that `--prepare` derives from the real product.
- **Authority per dispatch.** Every governed dispatch, protected releases
  included, is decided by the held claim and a fresh handle-bound receiver
  reading. A missing, changed or ambiguous reading ends authority for the
  rest of the attempt. A receiver that cannot be handle-bound refuses before
  contact and names why.
- **One terminal envelope per reserved attempt.** Refusals after the
  reservation, cancellations and interruptions all end in exactly one
  terminal envelope; a cancellation is the primary result and is re-raised.
  The terminal link is the publication point.
- **Time.** The deadline covers the evidence join. Late evidence is kept,
  acceptance is refused, and the boundary that crossed it is named.
- **Product admission.** Static, same-site, same-segment wired paths over one
  access switch or a multi-access L2 component. Routed paths refuse before
  any effect with the named missing contract.
- **Readiness per dependency.** Access groups per switch and VLAN, trunk
  continuity per component, bounded narrowing, invalidation by revision. A
  failed group blocks only its dependents; lost authority stops the whole
  invocation.
- **Evidence.** Offline and SIMULATED only. No capability, LIVE claim or
  published CI result changes here.

### Design refinements made during implementation

The design above was recorded before any production edit. The refinements
below followed from facts found while implementing or from the independent
reviews; each is inside the approved contract and each has its own
regression.

- **Dependency-local readiness needs narrowing.** The canonical access rule
  admits a group only when every requested port forwards, so one client's
  non-forwarding port would have refused every client of its switch, and one
  isolated switch every pair of its component. After a refused episode whose
  last sample was structurally clean (every requested row present exactly
  once, authoritative apart from port states), the gate asks one fresh,
  bounded episode about exactly the forwarding subset, or the joined pairs.
  It is a different group identity, it admits only the dependents it fully
  covers, and it never rescues the failing port or pair. A page that omits or
  repeats a requested row seeds no narrowing. Each group may therefore take
  two episodes; the derived gate ceilings (still exactly 4 / 120 s for a plan
  that fits them) and the cost model both count two.
- **Continuity follows the access rule's timeliness.** Only an episode that
  ended because a complete, timely round joined every required pair admits;
  a window that ran out admits nothing, and the pairs its last timely round
  joined are only a narrowing hint.
- **The receiver fallback is refused, not priced.** A full lifecycle reading
  per dispatch is a correct check but launches local helpers and has no
  per-dispatch bound; neither budget covers it. An attempt records its
  receiver mode and refuses before contact unless the reading is
  handle-bound. The fallback remains the composition's answer where no handle
  can be held. A declined binding raises `ReceiverBindingDeclined` with one
  stable reason (`process_api_unavailable`, `preflight_not_paired`,
  `primary_handle_refused`, `primary_creation_time_unreadable`,
  `primary_image_path_differs`, `process_table_unreadable`,
  `cohort_ambiguous:<detail>`, `helper_handle_refused`, `helper_unreadable`,
  `confirmation_differs`, `primary_exited`), and the refusal and the
  envelope's `process_preflight.receiver_binding_declined` both keep it.
- **The terminal link is the publication point.** After an interruption the
  outcome of a store write is unknown, so the store decides it: a linked
  write-ahead envelope of this invocation (same attempt and `started_at`) is
  adopted, never begun twice, and a linked terminal envelope means the
  attempt completed before the interruption, so its published verdict stands
  and nothing retries against the immutable file. An interruption before the
  terminal link completes the attempt as a cancellation.
- **The claim is interruption-safe and recoverable.** Claim files are written
  to a private temporary file and hard-linked in whole, so ownership is always
  readable. A reserved attempt always keeps its permanent marker. After an
  interruption inside `claim` the lock stays only when the caller chose the
  holder and can recover the claim; every other lock of that claim is
  removed. The acceptance coordinator chooses the holder and calls `recover`
  after any failed claim. A recovered interruption completes as
  `cancelled:<Type>@during:campaign_claim`, and a recovered ordinary error is
  refused after the claim as `campaign_claim_outcome_unknown:<Type>:<reason>`.
  A reservation that cannot be read back is unknown, never absent: nothing is
  written for it, and the lock that names the chosen holder is removed. A
  lock that cannot be read or removed is reported as a second refusal reason,
  `campaign_lock_may_remain:<holder>:<cause>`, or as a note on the
  interruption. The diagnostics' call is unchanged and never strands the
  lock.
- **Shared evidence once.** A scalable envelope cites the product record by
  path and digest and references its readiness rows by count and digest
  instead of copying them; the closure, the ledger and every per-client
  outcome stay whole. The legacy envelope keeps its copy.
- **One site's capacity is the planner's.** The real planner cannot place
  more than about 400 clients on one site (its two distribution switches run
  out of uplink ports at 500), so the 1,000-client case spreads clients over
  three sites, each with its own Server-PT and HTTP service, and every
  client-to-server path stays inside its site.

### The routed blocker, stated exactly

A separate server segment is compiled as SVIs on the site's 3560 distribution
switch. The derived routed closure names both gateway interfaces and the
trunk components on each side. Two contracts are missing: no registered E5
action enables IPv4 routing on that device, and no registered observable reads
its connected or static routing table (`show ip route` is registered only as
`show ip route ospf`, `eigrp` and `rip`). Routed dependents therefore refuse
at A8 as
`routed_path_unobservable:ipv4_routing_action_and_route_table_reader_unregistered`
before any effect. Nothing here enables routing, reads a route, or reports
routed completion; closing it needs a registered E5 routing action and a
registered route-table reader, each confirmed against the Packet Tracer
reference before implementation.

### Independent review before delivery, and what it changed

A read-only Codex adversarial review of `7736546...c2fd2e6` returned
*needs-attention* with four findings. Each was re-checked against the code;
all four were real and are fixed in `602a877`, with regressions that fail when
the fix is disabled. Self-review found a fifth.

| Finding | Disposition |
| --- | --- |
| A progress helper that exits can hand its process id to another Packet Tracer, which the id-only check would accept (high) | Fixed: the helper is held by its own handle for the life of the binding, so its id cannot be reused, and each reading re-checks its parent and creation time |
| An interruption after the reservation but before or during the write-ahead begin leaves no terminal envelope (high) | Fixed: one attempt-level handler covers every interval after the reservation, completes the envelope once as a cancellation named by phase, and re-raises |
| A second interruption during the verdict or the terminal write skips publication (high) | Fixed by the same handler; the first interruption stays the named one and a partial terminal write is retried once |
| The cost model prices the full-lifecycle fallback as a bounded reading (medium) | Fixed: attempts refuse before contact unless the receiver mode is handle-bound; the fallback is named in the refusal |
| Self-review: a narrowed episode could exhaust the derived episode ceiling and starve a later group | Fixed: two episodes per group in the ceilings, matching the cost model |

A second read-only Codex adversarial review, of `c2fd2e6...602a877`, returned
*needs-attention* with three new findings. Each was re-checked against the
code and reproduced by a regression before the fix; all three are fixed in
`270090c`.

| Finding | Disposition |
| --- | --- |
| An interruption after a store link leaves the attempt uncompleted: after the write-ahead link no terminal envelope is ever written, and after the terminal link the handler contradicts the stored verdict and retries against the immutable file (high) | Fixed: the store decides the unknown outcome (`stored`); a linked write-ahead is adopted, and a linked terminal envelope is the publication point, left as the attempt's verdict. Regressions interrupt immediately after each link |
| An interruption inside `claim` can leave the campaign lock held, or a spent attempt marker with no envelope (high) | Fixed: whole-payload claim files, rollback of an unreserved lock, and recovery of a reserved claim by the holder the coordinator chose. Markers are never deleted. Regressions interrupt after each claim-side creation and mid-payload |
| The bounded-mode refusal discards why the handle could not be held (medium) | Fixed: `ReceiverBindingDeclined` carries a stable reason into the fallback, the refusal and the envelope |

A third read-only Codex adversarial review of `602a877...270090c` returned
*needs-attention* with two findings. Both were real and are fixed in
`eed576f`, each with a regression that failed first.

| Finding | Disposition |
| --- | --- |
| The diagnostics call `claim` without choosing a holder, so an interruption after the reservation kept a lock nobody could recover or release (high) | Fixed in the coordinator: a lock is kept only for a caller that chose its holder; any other lock of an interrupted claim is removed, and the permanent marker stays. The diagnostics call is unchanged. Before these fixes an interruption anywhere in the claim left the lock |
| An ordinary exception after the reservation (for example a coordinator wrapper timing out) was treated as a refusal before reservation, leaving the lock held and no envelope (medium) | Fixed: on any claim error the coordinator first recovers the reservation of the holder it chose. A recovered attempt is refused after the claim as `campaign_claim_outcome_unknown:<Type>`, with its terminal envelope and the lock released |

A fourth review, of `270090c...eed576f`, returned *needs-attention* with
one finding, fixed in `27e1b2e` with regressions that failed first.

| Finding | Disposition |
| --- | --- |
| A reservation whose marker cannot be read back was answered as absent, so a claim that reserved and then failed left the chosen holder's lock held, the marker spent and nothing recorded (high) | Fixed: `recover` answers the claim, None only as proof of no reservation, or an error when the marker cannot be read. Whenever no claim is recovered, the coordinator removes a lock that names its own holder (`abandon`), never a marker. An unknown reservation is not written for, since it may not be this invocation's; its refusal is `campaign_claim_outcome_unknown:<Type>:reservation_unreadable:<claim reason>`, and the unpersisted result records the holder so the operator can match the marker |

A fifth review, of `eed576f...27e1b2e`, returned one medium finding, fixed in
`9c71225` with regressions that failed first.

| Finding | Disposition |
| --- | --- |
| A lock that cannot be read or removed after a failed claim was swallowed, so the operator saw the claim refusal but not the lock that would refuse every later claim (medium) | Fixed: `abandon` answers `released` or `not_held` and raises when the lock cannot be read or removed. The coordinator records the outcome, adds `campaign_lock_may_remain:<holder>:<cause>` as a second refusal reason carried by the CLI summary, and attaches the same text as a note to an interruption. An unknown reservation is still never written for |

The diagnostics still do not record an envelope for an attempt interrupted
inside its own claim; the spent marker refuses its identity afterwards. That
is their existing evidence contract, outside this work order.

What stays uncovered: an interruption that lands inside a recovery or
rollback step itself, or between a system call returning and Python recording
its result, and an uncatchable process kill. Whatever those leave is
fail-closed: a held lock refuses later campaigns until an operator removes it,
and a spent marker refuses the attempt identity.

### What was delivered, path by path

- **A1.** `application/ports/cold_http_acceptance.py` adds the
  `ReceiverContinuity` port. `infrastructure/execution/receiver_continuity.py`
  holds the handle-bound Win32 reader (query/synchronize handle, creation time,
  image path, toolhelp process table; primary plus at most the helper present
  at binding). `accept_cold_http.py` binds it before any channel, reads it in
  `_Attempt.authority` for every governed dispatch, and stops the labelled
  boundaries after a loss; `receiver_continuity_findings` in
  `domain/enterprise/models/cold_http_acceptance.py` is the rule. The CLI
  composes `bind_production_receiver` (handle, or one full lifecycle reading
  per dispatch carrying the `ReceiverBindingDeclined` reason, which the
  coordinator refuses).
- **A2-A4.** `accept_cold_http.py`: early write-ahead begin, begin-before-complete
  ordering, `persisted` and `completion_seconds` on the result, cancellation
  handling in `_contact_bound`, `_finalize` and one attempt-level handler,
  store-decided recovery of an interrupted write (`stored` on the envelope
  port and `cold_http_acceptance_store.py`), claim recovery, `_TemporalContract`,
  citation of unreturned product records; `campaign_coordination.py` writes
  whole-payload claim files, removes on interruption any lock its caller
  cannot recover, and adds a caller-chosen holder, a three-way `recover` and
  `abandon`; `enterprise_service_runtime.py`
  makes the one release on an interruption; the envelope gains
  `cancellation`, `temporal` and per-dispatch receiver counters.
- **B.** `domain/enterprise/services/service_path_closure.py` (placements,
  paired trunk links, per-VLAN components, path classification, the routed
  contract); `trunk_continuity.py` (readings, usable edges, window-scoped
  verdicts, narrowing hint); `service_access_readiness.py` (dependency groups,
  continuity requirements and results, group keys); `access_forwarding.py`
  (`forwarding_subset`); `service_access_readiness_gate.py` (multi-group
  verdicts, narrowing, revisions, derived limits);
  `enterprise_configuration_runtime.py` (`observe_trunk_continuity`, bounded
  endpoint chunks); `apply_enterprise_services.py` (path admission, closure
  paths and groups, gate wiring); `apply_services.py` (invalidation after E6
  batches); `service_entry.py` (closure path and group models).
- **Scalable profile.** `domain/enterprise/models/scalable_http_acceptance.py`
  (schema 2 grant, scope, digest, cost model, scope findings);
  `services/acceptance_evidence_index.py` (indexes built once);
  `services/scalable_http_acceptance_evidence.py` (per-client readiness
  re-derivation, per-group ordering oracle); `cold_http_acceptance_evidence.py`
  (shared `judge_client_request`, indexed legacy evaluation);
  `application/use_cases/prepare_http_acceptance.py` (planning session) and
  `--prepare` in the CLI.
- **Tests.** `test_cold_http_contract_repairs.py`, `test_receiver_continuity.py`,
  `test_campaign_claim_interruption.py`, `test_campus_service_paths.py`,
  `test_readiness_dependency_groups.py`,
  `test_bounded_endpoint_batches.py`, `test_scalable_http_acceptance.py`,
  `test_http_acceptance_scale.py`; the plan-driven SIMULATED campus
  (`campus_product_simulation.py`), the scalable harness and the benchmark
  runner `http_acceptance_scale_benchmark.py`.

### Requirement-to-test mapping

| Requirement | Tests |
| --- | --- |
| R-A1 | repairs `test_no_governed_dispatch_reaches_a_replaced_receiver` (5 replacements x 3 milestones), `test_every_governed_dispatch_is_decided_by_its_own_fresh_reading`, `test_a_failed_read_sample_with_an_unchanged_receiver_is_still_accepted`, `test_a_receiver_that_cannot_be_bound_refuses_before_contact`, `test_lost_campaign_ownership_still_blocks_every_later_effect`, `test_a_reading_that_spends_the_last_second_refuses_only_that_dispatch`, `test_the_legacy_worst_case_fits_with_receiver_and_dispatch_cost`, rule tests; scalable `test_a_replaced_receiver_stops_the_whole_invocation` |
| R-A1c | `test_receiver_continuity.py` (32: fake process tables, a reused helper id, every declined binding with its reason, plus the real Win32 reads on this process and a child it starts and stops); repairs `test_an_unbounded_receiver_reading_is_refused_before_contact`, `test_a_declined_binding_names_its_reason_in_the_refusal_and_the_envelope` |
| R-A2 | repairs `test_a_reserved_refusal_is_reloaded_with_its_identity_and_reason` (process, history, manifest), `test_an_unwritable_store_is_a_persistence_failure_not_a_refusal_reason`, `test_a_refusal_before_reservation_owes_no_envelope` |
| R-A3 | repairs `test_an_interruption_after_ownership_finalizes_once_and_propagates` (start, inspection, release), `test_an_interruption_during_finalization_is_never_an_acceptance`, `test_an_interruption_outside_the_product_still_completes_one_envelope` (process read, manifest, channel), `test_every_interruption_after_reservation_leaves_a_terminal_envelope` (begin, verdict, terminal write), `test_an_interruption_after_the_write_ahead_link_still_completes_the_attempt`, `test_an_interruption_after_the_terminal_link_leaves_the_published_verdict`, `test_an_interruption_inside_the_claim_leaves_nothing_unaccounted` (lock, marker), `test_an_ordinary_claim_error_after_the_reservation_is_a_recorded_refusal`, `test_an_unreadable_reservation_after_a_failed_claim_leaves_no_lock` (ordinary error, interruption), `test_a_refused_claim_over_an_unreadable_marker_keeps_its_reason`, `test_a_lock_that_cannot_be_removed_after_a_failed_claim_is_reported` (ordinary error, interruption), `test_a_second_run_of_a_cancelled_attempt_is_still_refused`; `test_campaign_claim_interruption.py` (11) |
| R-A4 | repairs `test_a_reload_that_crosses_the_deadline_withholds_acceptance`, `test_an_on_time_evidence_join_is_accepted`, `test_a_verdict_reached_after_the_deadline_names_the_verdict_boundary` |
| R-B1/B2 | scalable `test_the_prepared_scope_names_every_selected_client_and_its_cost`, `test_a_malformed_scalable_grant_refuses_before_any_contact` (9), `test_a_schema_two_grant_is_never_read_as_the_legacy_profile`, `test_a_grant_that_differs_from_the_derived_scope_refuses_before_e1` (5), `test_the_prepare_command_prints_the_derived_grant_fields`, `test_a_legacy_grant_keeps_its_frozen_ceiling_and_rules`; the unchanged legacy suites |
| R-B3 | scalable `test_selected_clients_are_each_accepted_once_in_the_products_order` (2, 20, 30), scale `test_two_hundred_clients_on_one_site_through_the_whole_envelope`, `test_a_thousand_clients_over_three_sites_through_the_whole_envelope` |
| R-B4/B7 | campus `test_a_multi_access_campus_is_verified_through_the_public_tool`, `test_a_routed_server_segment_is_refused_before_any_effect`, `test_the_routed_closure_names_the_gateways_it_would_need`; `test_service_path_admission.py` (unchanged guards); scalable `test_a_routed_campus_is_refused_by_the_product_before_any_effect` |
| R-B5/B6 | `test_readiness_dependency_groups.py` (17), campus `test_every_request_follows_every_group_its_path_names`, `test_an_unreadable_switch_off_the_forwarding_path_blocks_nobody`, `test_a_fault_in_an_unselected_branch_is_never_observed`; scalable `test_every_selected_client_stays_represented_when_trunks_fail`, `test_one_clients_fault_is_its_own`, `test_a_fault_in_an_unselected_branch_does_not_interfere`, `test_a_bypassed_readiness_gate_fails_the_per_group_ordering_oracle` |
| R-C1 | scalable `test_the_executed_worst_case_fits_the_derived_model`, `test_the_cost_profile_matches_the_constants_the_product_executes`, `wrong_budget` refusal |
| R-C2/C3 | scalable `test_the_evaluator_indexes_the_ledger_once`; `test_bounded_endpoint_batches.py` (3) |
| R-C4 | scale `test_the_generated_campus_is_larger_than_the_cp_scale_reference`; the benchmark below |
| R-D1 | legacy `test_the_mcp_route_and_the_acceptance_route_run_the_same_product`; scalable `test_the_public_tool_and_the_scalable_envelope_run_the_same_product`; the full offline suite (qualification, Voice, namespace and surface suites unchanged) |

### Causal RED: each repaired behavior disabled on its own

All 34 rows were re-run against the final code commit `9c71225`. Each row
patched one behavior out, ran only its selected regressions, and restored the
bytes. Afterwards every selected file passed again and `git status` was
empty, so the tree was byte-identical to the commit.

| Disabled behavior | Selected regressions failing |
| --- | --- |
| A1 receiver reading in the dispatch guard | 16 of 16 |
| A2 early begin and begin-before-complete, both reverted | 3 of 3 |
| A2 early begin only (completion order kept) | 0 of 3: the corrected order alone keeps the reason; the two fixes are redundant by design |
| A3 cancellation handling in the product call | 3 of 16: the attempt-level handler added after review 1 now completes the other interruptions on its own |
| A3 E6 release on interruption | 2 of 3 (the third is the interruption *at* the release, which must not release twice) |
| A4 temporal contract | 2 of 2 |
| B4 multi-access admission | 3 of 3 |
| B7 routed refusal | 2 of 2 |
| B5 narrowing | 3 of 3 |
| B5 revision invalidation | 1 of 1 |
| B6 continuity dependency | 2 of 2 |
| B2 client-set comparison | 2 of 2 |
| C1 budget binding | 1 of 1 |
| C2 ledger index built per client | 1 of 1 |
| C3 endpoint chunking | 2 of 3 (the third is the within-one-chunk control) |
| B3 per-group ordering oracle | 1 of 1 |
| Review 1: helper identity re-check | 2 of 2 |
| Review 1: attempt-level cancellation handler | 6 of 6 |
| Review 1: bounded receiver mode | 1 of 1 |
| Self-review: two episodes per group in the ceilings | 1 of 1 |
| Review 2: write-ahead recovery from the store | 1 of 1 |
| Review 2: terminal publication point | 1 of 1 |
| Review 2: rollback of an unreserved lock | 1 of 3: the coordinator-level regression; at attempt level the later `abandon` also removes the lock, and the third is the reserved case |
| Review 2: claim recovery by the chosen holder | 1 of 2 (the other is the unreserved case) |
| Review 2: whole-payload claim files | 1 of 1 |
| Review 2: reason kept in the refusal | 1 of 1 |
| Review 2: reason carried by the fallback | 2 of 2 |
| Review 3: release of an unrecoverable lock | 1 of 1 |
| Review 3: recovery after an ordinary claim error | 1 of 1 |
| Review 4: an unreadable reservation answered as absent | 3 of 4 (the interruption case is also covered by `abandon`) |
| Review 4: removal of this holder's own lock (`abandon`) | 2 of 2 |
| Review 4: the claim's reason kept in an unknown refusal | 2 of 3 (the interruption case has no refusal) |
| Review 5: an unreadable lock answered as not held | 1 of 1 |
| Review 5: a lock that may remain, reported | 2 of 2 |

A2's original defect reproduces with both fixes reverted: the real store
refuses `begin` on an envelope whose `completed_at` is already set, so the
refusal's reason was never written.

### Scale evidence, and what produced each number

Every campus below is what the real planner and compiler produce for the
intent; the acceptance route, composition, product, runtimes, readiness gate,
ledger, evaluator and stores are the production ones. Packet Tracer is
SIMULATED by `tests/campus_product_simulation.py` (per-VLAN spanning tree from
the compiled trunks, the measured page formats) with a fake clock; nothing
here is Packet Tracer behaviour, timing or capacity.

| Clients | Sites | Devices | Links | Switches | Access groups | Continuity components |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 1 | 4 | 3 | 1 | 1 | none |
| 20 | 1 | 25 | 26 | 4 | 1 | none (all on one access switch) |
| 30 | 1 | 35 | 36 | 4 | 2 | one of 4 switches |
| 200 | 1 | 215 | 225 | 14 | 9 | one of 14 switches |
| 1,000 | 3 | 1,066 | 1,114 | 63 | 42 | three of 21 switches |

The maintained CP-SCALE reference, composed read-only through its
maintained helper, declares 314 devices and 219 links; the generated
1,000-client campus declares 1,066 and 1,114. That is a larger compiled
fixture, not evidence that Packet Tracer can hold it.

Measured with `tests/http_acceptance_scale_benchmark.py` at `eed576f` (`27e1b2e` and `9c71225` change only the failed-claim path, which no row reaches) on Windows-11-10.0.26200-SP0, Python 3.12.10, this checkout's `.venv`, with nothing else running: every dispatch costs 0.05 simulated seconds and every receiver reading 0.015 s (the measured Win32 maximum), so no row is a zero-latency trace. Immediate FWD forwards at once; delayed FWD forwards 26 s after each switch is first read and trunks 12 s after the first trunk read; persistent non-FWD never forwards any access port. Envelope and record sizes are the persisted files; peak memory is Python allocations under `tracemalloc` for the whole attempt; wall and evaluator seconds are this machine's.

| Clients | Behaviour | Accepted | Represented / never started | Operations used / ceiling | Receiver readings (s) | Simulated s / ceiling | Wall s | Evaluator s | Peak MiB | Envelope MB | Record MB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | immediate fwd | yes | 2 / 0 | 30 / 1,191 | 30 (0.45) | 2.95 / 530 | 0.226 | 0.002 | 1.0 | 0.04 | 0.06 |
| 2 | delayed fwd | yes | 2 / 0 | 114 / 1,191 | 114 (1.71) | 29.41 / 530 | 0.278 | 0.004 | 1.3 | 0.07 | 0.08 |
| 2 | persistent non fwd | no | 2 / 2 | 115 / 1,191 | 115 (1.725) | 32.235 / 530 | 0.27 | 0.004 | 1.3 | 0.07 | 0.08 |
| 20 | immediate fwd | yes | 20 / 0 | 138 / 4,035 | 138 (2.07) | 9.97 / 1,770 | 0.379 | 0.009 | 3.6 | 0.17 | 0.32 |
| 20 | delayed fwd | yes | 20 / 0 | 222 / 4,035 | 222 (3.33) | 36.43 / 1,770 | 0.562 | 0.024 | 4.3 | 0.20 | 0.40 |
| 20 | persistent non fwd | no | 20 / 20 | 169 / 4,035 | 169 (2.535) | 35.745 / 1,770 | 0.538 | 0.026 | 3.9 | 0.19 | 0.38 |
| 200 | immediate fwd | yes | 200 / 0 | 1,349 / 43,654 | 1,349 (20.235) | 88.685 / 16,079 | 2.581 | 0.14 | 28.2 | 1.55 | 2.93 |
| 200 | delayed fwd | yes | 200 / 0 | 2,273 / 43,654 | 2,273 (34.095) | 340.745 / 16,079 | 4.486 | 0.26 | 37.0 | 1.89 | 3.79 |
| 200 | persistent non fwd | no | 200 / 200 | 1,512 / 43,654 | 1,512 (22.68) | 313.12 / 16,079 | 4.372 | 0.227 | 31.0 | 1.68 | 3.49 |
| 1,000 | immediate fwd | yes | 1000 / 0 | 6,666 / 213,164 | 6,666 (99.99) | 434.29 / 78,922 | 20.047 | 0.805 | 137.5 | 7.67 | 14.50 |
| 1,000 | delayed fwd | yes | 1000 / 0 | 10,362 / 213,164 | 10,362 (155.43) | 1558.53 / 78,922 | 29.932 | 1.294 | 169.4 | 9.01 | 18.65 |
| 1,000 | persistent non fwd | no | 1000 / 1000 | 7,236 / 213,164 | 7,236 (108.54) | 1469.26 / 78,922 | 28.474 | 1.211 | 151.2 | 8.26 | 17.29 |

### Measured offline verification

Everything below ran in this checkout's own `.venv` (Python 3.12.10) on
Windows 11, against `cisco/main` resolving to `6263344`. The last code commit
is `9c71225`; the commit that adds this block changes only this brief.

| Check | Result |
| --- | --- |
| Full offline suite at `9c71225` | 7,355 passed, 3 skipped, 3 warnings (the existing class-scoped-fixture deprecation in two `test_e95_*` files) in 469 s; the tree was clean before and after |
| Earlier full runs, oldest first | 7,280 passed after the multi-access commit; one run on `c2fd2e6` ended in the native access violation described below (log kept); 7,327 passed, 3 skipped at `602a877`; 7,345 passed, 3 skipped at `270090c`, provisional because files were edited while it ran; 7,347 passed, 3 skipped at `eed576f`; 7,352 passed, 3 skipped at `27e1b2e`, provisional because causal patches ran during it |
| Affected suites (38 files: coordination, acceptance, qualification, diagnostics, receiver, bridge security) | 1,115 passed on the tree committed as `270090c` |
| Focused suites at `9c71225` (claim interruption, receiver, contract repairs, diagnostic corrections, acceptance boundaries) | 168 passed |
| Causal RED at `9c71225` | 34 of 34 disabled behaviors caught (table above); every restored file passes, and `git status` was empty afterwards |
| Quality gate, worktree mode, `--base cisco/main` | 150 Ruff-gated files; lint and format pass |
| Namespace inventory | 0 active legacy references, 0 unreviewed inert mentions |
| MkDocs build | passes with the two warnings that already exist on `cisco/main` |
| `git diff --check` | clean |
| Delivery gate on the delivery commit | reported in the handoff: a commit cannot record its own gate |
| Exact-SHA CI | pending; nothing was published |

Six read-only Codex adversarial reviews ran; the first five findings tables
are above. The sixth, of `27e1b2e...9c71225`, returned *approve* with no
material findings: a failed lock read or unlink reaches the refusal reasons or
the interruption note, and the claim's own reason stays first. These reviews
are advisory; none of them is the independent audit the standard requires.

### Residual limitations

- Offline only. The campus terminal is a simulation: its spanning tree is
  deterministic (root by name, breadth-first tree), its trunk and
  spanning-tree pages follow recorded 9.0.1.0858 formats, and its timing is a
  fake clock. `observe_trunk_continuity` is new runtime code over a registered
  query and the same bounded executor as the forwarding observer; it has
  never read a live switch.
- The interval between a receiver reading and the receiver executing the
  command is unfenced, as before. An interruption inside a recovery or
  rollback step itself, one between a system call returning and Python
  recording its result, and an uncatchable kill are not covered; what they
  leave is fail-closed (a held lock or a spent marker).
- The terminal link is the publication point: an interruption that lands
  after it propagates, and the stored verdict, accepted or not, is the
  attempt's.
- Readiness episodes run one group at a time, so delayed forwarding costs
  time linearly in the number of groups (measured above). A plan whose
  derived ceiling is hours is honest about it; it is not evidence that such a
  run is practical.
- Evidence grows linearly with clients (the product record dominates, mostly
  E5 per-action readback). Nothing was truncated to reduce it.
- Trunks, transit VLANs and gateways are proven, never configured, by the
  service path; a campus whose E5 configuration was not applied first is
  refused per dependency by readiness, not repaired.
- Routed paths are refused with the exact missing contract above.
- A schema 2 grant must list exactly the product's selection (every client
  of every eligible service); it cannot select a subset.
- An intermittent native access violation ended two combined test processes
  during this work (one full-suite run, in
  `tests/test_cp_scale_live_architecture.py`'s AST walk, which runs before any
  code this delivery adds native calls to; one targeted run whose top frames
  were not retained). The same files pass alone and in later runs. Its cause
  is not established here, and its disappearance proves nothing.
- The Win32 reads were exercised against this Python process and a child it
  owns, never against Packet Tracer.

### Pending operator grants

Nothing here authorizes a LIVE attempt, a publication or a merge. The
delivery commit must be published before any attempt, because the repository
rule refuses an unpublished HEAD; exact-SHA CI is pending that publication.

A **schema 1** (legacy two-client) attempt still needs the grant listed in
the previous block, and now also a handle-bound receiver: the executing
process must be able to open the paired Packet Tracer PID for query and
synchronize (same user), and the Packet Tracer cohort must be the primary
plus at most the helper it started, or the attempt refuses before contact
with `receiver_mode_not_bounded:lifecycle_per_dispatch:<reason>`, the reason
naming what to correct.

A **schema 2** (scalable) attempt needs, in order:

1. The deployment's E5 configuration applied by the enterprise execution
   path, so trunks and transit VLANs exist; the service path only proves them.
2. The manifest persisted under `<governed root>/data/deployments`, and no
   stored run of the deployment under `<governed root>/data/services`.
3. `.venv\Scripts\python.exe -m packet_tracer_mcp.adapters.cli.cold_http_acceptance --prepare --intent <intent> --deployment <id> --build 9.0.1.0858 --attempt <32-hex>`
   with `PT_MCP_GOVERNED_ROOT` set, on the published delivery commit. It
   contacts nothing and prints the derived `servers`, `clients`,
   `scope_sha256` and budget.
4. A grant document with `schema_version: 2`, `profile:
   http_by_ip_scalable_v1`, those derived fields unchanged, the
   authorization id, attempt id, published SHA and tree, build, channel
   `file`, deployment and manifest hashes, the intent digest, marker
   `COLD_HTTP_<attempt>`, the Packet Tracer PID, path and creation identity
   read immediately before the attempt, and both laboratory flags `true`.
5. `... cold_http_acceptance --execute --grant <grant> --intent <intent>` from
   the checkout's own interpreter, never under pytest.

A first LIVE scalable attempt should be the smallest multi-access case (the
30-client, two-access-switch campus) before any larger one. Fixture cleanup,
workspace restoration, a second attempt, routed paths and capability
promotion each need their own grant.

## 2026-09-23 acceptance-boundary closure after `cc272c9` (risk L)

### Identity and instructions

Input: clean `feature/server-pt-goal-foundations` at
`cc272c94eed434ae3fee73b92e1cd5188cd0eef7`, tree
`93ad8ab8886a79c6fbaea05cacd93c370caa0dd4`, implementation parent `7736546`,
with `cisco/main` resolving to `6263344e31ba3b0de6539d652f2cd06fc73a3562` and
an ancestor of HEAD. The package resolves to this checkout's `src` from its own
`.venv` (Python 3.12.10). `AGENTS.md`, `CLAUDE.md` and the standard were read
from this checkout and still have the digests recorded above (`a9f0e384...`,
`29312201...`, `2de0d5b2...`); `/context` and a Codex loader listing cannot be
observed from this session and stay pending. The work order
`Unified_CC272C9_Acceptance_Closure.md` authorizes offline fixes, causal
autofix, tests and local commits only: no Packet Tracer contact, bridge
startup, process launch or termination against Packet Tracer, LIVE attempt,
topology cleanup, claim reset, historical-record edit, publication, merge or
capability promotion. Historical Q/D limits are unchanged. Windows tests touch
only processes they own.

### Problem and intended outcome

The reviewed commit is correct on its working N-client path but its acceptance
boundary is weaker than its record claims, in four families:

1. **R1 - evidence is not derived from raw observations.** `_joined` trusts a
   continuity round's `usable_links` summary, so a round labelled complete with
   no readings, or with unexecuted, foreign or wrong-VLAN readings, joins its
   endpoints. `_access_findings` reads the top-level sample and ignores whether
   the retained history agrees with it. `scalable_ordering_findings` accepts
   the first observation of a group before a request, even when the
   observation that actually admitted the client came afterwards.
2. **R2 - a failed Windows census is read as a complete one.** Every false
   `Process32NextW` ends enumeration as if it were the documented end, so an
   error after the primary row can hide a second receiver.
3. **R3 - timeliness is decided before publication.** `_judge` decides the
   deadline; `_complete` then assembles the budget and the store reloads,
   serializes, flushes and links without deciding again, so an on-time verdict
   can be linked as an accepted envelope after the deadline.
4. **R4 - consumers are not linear.** The evaluator rebuilds the scope group
   map per client, re-derives each component's graph per dependent and
   computes `max(e5_verify)` inside the client loop (N(N+1) visits of N E5
   entries); `_names` calls `names.count` per name.

The outcome is one delivery that closes all four, keeps the working
N-client/multi-access path and both profiles, and leaves a reproducible
offline acceptance package.

### Scope and explicit exclusions

In scope: the readiness gate's evidence identity, the acceptance ledger labels,
the closure and scope readiness-group model, the scalable evaluator and its
indexes, the handle-bound receiver's Windows census, the coordinator's
finalization and publication protocol, the envelope store, the acceptance
result and CLI summary, tests, the scale benchmark and this section.

Excluded: routing, DHCP, HTTPS, mail, events, wireless, a replacement runtime or
service workflow, a second IOS parser, schema 1 rules and its frozen
`1015/420/2/40` proposal, the bridge, the MCP four-input signature, CP-SCALE
data, historical evidence and other worktrees. Schema 2 still verifies existing
trunks and transit VLANs and configures none. Nothing claims complete campus
installation or cross-site connectivity.

### Design delta

**R1 - one evidence contract from raw observation to per-client decision.**

- *Episode identity (additive, product).* Every readiness episode for which the
  gate called an observer carries `episode: {ordinal, revision, narrowed}` on
  its record row: `ordinal` is the 1-based count of observer calls for that
  group identity, `revision` the group's dependency revision when it was
  observed, and `narrowed` whether it is the narrowing episode. Each dependent
  entry whose verdict the gate actually used when it decided that expectation
  gains `decision: {revision}`, the group's revision at decision time. Rows
  without an episode (no observer call) carry none. Nothing else in a row
  changes.
- *Ledger correlation (acceptance composition).* The scalable labelled runtime
  names readiness dispatches `readiness:<group key>#<ordinal>`, counting
  observer calls per group key exactly as the gate does, so each row's episode
  maps to the exact ledger positions it dispatched.
- *Edge endpoints in the derived scope.* The closure's continuity group gains
  `links` (each compiled trunk link as its two `switch:interface` ends,
  canonically ordered), carried into `ReadinessGroupScope`. The scalable scope
  digest therefore changes; no schema 2 grant was ever issued.
- *Raw re-derivation, once per episode row.* Access: the recorded sample is
  parsed strictly into an `AccessForwardingObservation` (duplicate interface
  rows are ambiguous and refused), bound to the group's switch, VLAN and
  interface set, required to agree with the last entry of its history
  (rows, execution, freshness, completeness, identity, VLAN instance, call
  budget, lateness, and `samples == len(history)`), and admitted only by the
  canonical `access_forwarding_admission`. Recorded `admitted`, `dimension` and
  `forwarding_interfaces` labels must agree with the re-derivation.
  Continuity: the row's switches and links must equal the derived scope; the
  deciding round's raw readings are parsed strictly (exactly one reading per
  component switch, no foreign switch, exactly one entry per trunk port and no
  foreign port, `complete` agreeing with the readings), and the canonical
  `trunk_continuity_verdicts` over `usable_links` decides every dependent pair
  at once. The recorded `usable_links`, `complete` and
  `authoritative_readings` summaries must agree with the re-derivation. A
  summary is never permission.
- *Per-client binding.* For each group a client's path names: exactly one
  dependent entry with a `decision` mark (none or several refuse), the
  expectation listed once in that row, the decision revision equal to the
  episode revision, the dependent admitted by the re-derivation (its ports
  forwarding, or its switch pair joined), the episode's ledger dispatches all
  before the client's first request, and no episode of a later revision of
  that group dispatched before that request. Legitimate narrowing, shared
  group reuse and later revalidation for other clients are decided per
  client; later valid work never invalidates an earlier correctly authorized
  request. An older record without episode identity stays readable and cannot
  be accepted.

**R2 - only the documented end completes a census.** `WindowsProcessApi.snapshot`
sets the ctypes private error to 0 before each `Process32FirstW` and
`Process32NextW`, and reads `ctypes.get_last_error()` immediately after a false
return, before any cleanup call can replace it (the kernel32 binding uses
`use_last_error=True`, whose private copy is swapped immediately after each
foreign call). A census is complete only when `Process32NextW` returns false
with `ERROR_NO_MORE_FILES` (18), the documented end. A failed first read or any
other error raises `ProcessTableUnreadable` with a stable cause
(`toolhelp_snapshot_failed`, `process32first_failed` or
`process32next_failed`, the Win32 error and the number of rows read, which is
diagnostic and authorizes nothing); the snapshot handle is closed on every
path. Binding declines as `process_table_unreadable:<cause>`; a per-dispatch
reading is `process_table_unreadable:<cause>`, which the existing rule turns
into a sticky authority loss, so no later effect or release reaches the
channel. This defect is not claimed as the cause of the recorded native access
violations.

**R3 - one publication boundary for cancellation and timeliness.** Publication
stays the terminal link. Every controlled step that shapes the published bytes
consumes the one absolute deadline, in order: record reload, claim release,
verdict, budget assembly, write-ahead begin (when still owed), and inside the
store the begun-envelope reload, serialization and flush, the last
immediately before the link. The store's `complete` takes a `checkpoint`
callback, called after each of its steps; when a checkpoint finds the deadline
passed while the payload claims acceptance, it refuses, nothing is linked, and
the coordinator publishes the same evidence with acceptance withheld as
`acceptance_deadline_exceeded:<boundary>`. A link that cannot be preempted is
not claimed to be: after it returns, the coordinator records an independent,
write-once publication fact (`<attempt>.publication.json`) binding the terminal
file's SHA-256, the deadline, the decision offset, the last checkpoint before
the link and the instant the link returned. The link instant is known only to
lie between those two; the attempt is accepted only when the terminal verdict
is accepted and the link returned within the deadline. The terminal envelope's
`http_accepted` is therefore the provisional verdict; `AcceptanceResult`, its
exit code and the CLI summary report the claim. An interruption before the
link still completes one cancellation envelope; one after the link leaves the
published verdict and records the fact from the store's own answer, with the
interruption named in it. A completed envelope is never rewritten. The first
failure stays the primary failure; later persistence errors are listed apart.

**R4 - linear consumers.** One evaluation context is built per attempt: the
scope group map, per-row validated evidence (one canonical admission per
access episode, one connectivity derivation per continuity episode), the
ledger boundary maxima (`max(e5_verify)`, `max(e6_apply)`, first readiness
dispatch) and, per group, the earliest dispatch of each later revision. Each
client then costs lookups in its own relationships. `_names` counts once.

### Requirements and acceptance criteria

| Id | Acceptance criterion |
| --- | --- |
| R1a | A continuity row whose deciding round has no raw readings, or unexecuted, foreign, duplicated or wrong-VLAN readings, refuses its dependents whatever its `complete`, `admitted` or `usable_links` labels say |
| R1b | An access row whose sample disagrees with its retained history, lacks required fields, repeats an interface or contradicts its own labels refuses |
| R1c | A client admitted only by an episode dispatched after its first request (early LIS, request, later FWD) is refused; an absent, duplicated or foreign decision refuses |
| R1d | A decision older than its group's revision, or superseded by a later revision dispatched before the request, refuses |
| R1e | Redundant trunks with an STP-blocked unused link, legitimate narrowing, a shared group reused by many clients, later unrelated observations and the unchanged campus stay accepted, through the real evaluator and the whole envelope |
| R2a | The shipped Windows adapter returns a census only at `ERROR_NO_MORE_FILES`; a first-read failure, a failure after the primary and a failure before a second Packet Tracer row are unreadable with their cause; the snapshot handle is closed every time |
| R2b | Through the governed route, an unreadable census at binding declines with its cause, and one at a dispatch stops that dispatch and every later effect and release |
| R3a | Timely success is accepted and records its publication fact |
| R3b | A late reload, late evaluation, late budget assembly, late reload/serialization/flush inside the store each withhold acceptance, name their boundary, keep the evidence and link one non-accepted envelope |
| R3c | A link that returns after the deadline leaves the provisional verdict and a fact that does not establish acceptance |
| R3d | A persistence error and interruptions immediately before and after the link keep one terminal envelope, keep the first failure primary, and never rewrite a completed envelope |
| R4a | Visits of E5 entries, readiness rows, dependents and component links, and connectivity builds, grow linearly with clients, groups, E5 entries and shared components |
| R4b | The 2/20/200/1,000 end-to-end cases, delayed and persistent non-forwarding included, still represent every client and are measured again |

### Invariants

- A label, summary or count in a record is never permission; only a re-derived
  raw observation is.
- One observation decides one dependent's permission for one group, bound to
  its episode, revision and ledger positions.
- A census is complete only at the documented end of enumeration.
- Acceptance is never published when the run already knows its allowance is
  gone, and a completed envelope is never rewritten.
- Schema 1 decisions and its frozen proposal are unchanged; historical
  evidence is untouched; the product still configures no trunk, transit VLAN
  or gateway.

### Test design

Unit: strict parsers and re-derivation per row; the binding rules; the Win32
adapter over a controlled kernel32; the store's checkpoints. Integration and
system: the real coordinator, stores, ledger, readiness gate, product and
evaluator over the plan-driven SIMULATED campus, with whole-envelope fault
injection. Scale: deterministic visit and build counts over growing synthetic
evidence, and the existing end-to-end benchmark. LIVE acceptance is not
applicable to this delivery.

### Design refinements made during implementation

The design above was committed (`496bfd5`) before any production edit. The
refinements below are inside that contract; each has a regression.

- **Two counters, one sequence.** The gate numbers an episode when it calls
  its observer; the scalable labelled runtime numbers the calls it receives
  per group key, before anything can refuse them. Every gate observer call
  reaches that runtime exactly once, so both count the same events. The
  evaluator does not assume it: a ledger episode that no record row carries is
  `readiness_episode_unrecorded`, and a row episode with no ledger dispatch is
  `readiness_episode_not_dispatched`, for every decision of that group.
- **Decision marks by retained result.** The gate keeps every observation it
  made for its whole invocation (current, superseded and narrowed), so the
  identity of the result object it decided with is stable while it renders
  the rows; the mark is written only onto that observation's dependent entry.
- **Foreign rows are not read.** A row whose identity is not a group of the
  derived scope cannot speak for any client. A row of a scoped group that fails
  validation refuses every decision it carries, not only the faulted port.
- **The ledger oracle keeps its own view.** `scalable_ordering_findings` still
  requires, from the ledger alone, some episode of every group before a
  client's first request; which episode admitted the client, and when, is now
  bound per client by `readiness_evidence`.
- **Recovery adopts, never duplicates.** A publication fact already stored for
  this invocation is adopted by a recovering handler, never written twice.
- **Scope digest.** Adding link ends changes every schema 2 scope digest. No
  schema 2 grant was ever issued, and a grant must equal the scope the
  executing commit derives, so nothing issued is invalidated.
- **R2 delegation.** The Windows census fix and its tests were implemented by a
  delegated Codex task in an isolated worktree (`wip/r2-windows-census`,
  its own `.venv`); it could not commit there because the worktree's index
  lies outside its sandbox. The diff was reviewed and integrated here with two
  changes: the private error is also cleared before `CreateToolhelp32Snapshot`,
  and the binding-failure route test composes the real
  `bind_production_receiver`. The dispatch-failure route test keeps a binder
  that mirrors it on the harness's fake clock, because the production reader
  compares deadlines on the monotonic clock its coordinator uses.
- **Rows are read twice.** The existing reload comparison serializes the record
  once more; the visit counts below include it.

### What was delivered, path by path

- **R1.** `domain/enterprise/services/readiness_evidence.py` (new: strict
  parsers, per-row validation, decision index, per-group supersession,
  per-client binding); `scalable_http_acceptance_evidence.py` (uses it, keeps
  the ledger oracle); `acceptance_evidence_index.py` (`READINESS_PREFIX`,
  `readiness_episode_spans`; the superseded `ReadinessIndex` is removed);
  `service_access_readiness.py` (`episode` on group results, `trunk_link_ends`);
  `service_access_readiness_gate.py` (episode ordinals and revisions, decision
  marks); `accept_cold_http.py` (`readiness:<key>#<ordinal>` labels);
  `service_entry.py` and `apply_enterprise_services.py` (closure link ends);
  `scalable_http_acceptance.py` (scope link ends).
- **R2.** `infrastructure/execution/receiver_continuity.py`
  (`ProcessTableUnreadable`, the documented end, capture before cleanup, the
  binding and per-dispatch causes).
- **R3.** `accept_cold_http.py` (`_TemporalContract.of`, `_decide`, the
  checkpointed `_complete`, `_record_publication`, recovery,
  `AcceptanceResult.accepted`, the CLI summary);
  `infrastructure/persistence/cold_http_acceptance_store.py` (checkpoints,
  `record_publication`, `stored_publication`, `load_publication`);
  `application/ports/cold_http_acceptance.py`;
  `domain/enterprise/models/cold_http_acceptance.py` (`AcceptancePublication`,
  `publication_claim`, temporal fields).
- **R4.** `readiness_evidence.py` and `scalable_http_acceptance_evidence.py`
  (built once, hoisted maxima, one bounded reference per client for group
  faults); `trunk_continuity.py` (`usable_links` indexes readings and ports
  once); `_names` in `scalable_http_acceptance.py`.
- **Review corrections.** `readiness_evidence.py` (exact trunk-port sets,
  first-fault rows, `evidence_findings`); `scalable_http_acceptance_evidence.py`
  (every dispatched purpose must name the scope); `cold_http_acceptance.py`
  (`publication_claim` derives timeliness from the fact's offsets);
  `cold_http_acceptance_store.py` (`load_publication` checks the terminal
  file's name and SHA-256); `acceptance_evidence_index.py`
  (`readiness_episode`, the one canonical label parser).
- **Tests.** `test_readiness_evidence_binding.py` (36),
  `test_acceptance_evaluation_linearity.py` (9),
  `test_windows_process_census.py` (13), `test_acceptance_publication_boundary.py`
  (16); updated `test_cold_http_contract_repairs.py` (temporal key names, the
  publication fact after a post-link interruption) and
  `test_cold_http_acceptance_route.py` (a store fake that accepts the new
  keyword); `tests/http_acceptance_scale_benchmark.py` (the claim, per-case
  processes, RSS, publication size, source identity).

### Shared contracts and schema changes

| Contract | Change | Compatibility |
| --- | --- | --- |
| Readiness record row | adds `episode` (observed rows only) and dependent `decision` | additive; legacy readers ignore them |
| Scalable ledger purpose | `readiness:<key>` becomes `readiness:<key>#<ordinal>` | scalable profile only; the legacy label is unchanged |
| Closure readiness group, `ReadinessGroupScope` | adds `links` | additive; schema 2 scope digests change |
| `AcceptanceEnvelopePort.complete` | adds keyword `checkpoint` | fakes must accept the keyword |
| `AcceptanceEnvelopePort` | adds `record_publication`, `stored_publication`, `load_publication` | new write-once `<attempt>.publication.json` |
| Envelope `temporal` | `publication_offset_seconds` (it was the verdict instant) becomes `verdict_offset_seconds`; adds `decided_offset_seconds`, `publication_point` | no historical envelope exists |
| Envelope `http_accepted` | now the provisional verdict | the claim is `publication_claim(envelope, fact)` |
| `AcceptanceResult` | adds `accepted`, `publication`, `publication_path`, `publication_failure`; `exit_code` uses `accepted` | CLI summary `http_accepted` is the claim, `provisional_http_accepted` the verdict |
| `ProcessApi.snapshot` | may raise `ProcessTableUnreadable` | `None` still accepted from other implementations |

### Requirement-to-test mapping

| Requirement | Tests |
| --- | --- |
| R1a | binding `test_a_positive_continuity_summary_over_bad_readings_refuses` (no, unexecuted, foreign, wrong-VLAN, repeated, missing-switch, late readings and a missing port of an STP-blocked trunk), `test_a_link_that_is_not_in_the_derived_scope_refuses`, `test_the_whole_envelope_refuses_incomplete_continuity_evidence` (no readings, missing port) |
| R1b | binding `test_an_access_sample_that_its_history_does_not_support_refuses` (history not fresh, foreign, absent, miscounted, repeated interface, contradicted labels, missing field) |
| R1c | binding `test_a_request_between_listening_and_forwarding_samples_is_refused`, `test_a_second_admitting_row_for_the_same_decision_is_ambiguous`, `test_a_client_listed_twice_in_one_row_is_refused`, `test_a_client_without_a_decision_is_refused`, `test_an_older_record_without_episode_identity_cannot_be_accepted`, `test_a_dispatch_outside_the_derived_scope_refuses_the_attempt` (foreign group, no ordinal, a leading-zero or zero ordinal, unselected request and release), `test_every_dispatch_of_the_unchanged_campus_names_the_scope`; scalable `test_a_bypassed_readiness_gate_fails_the_per_group_ordering_oracle` |
| R1d | binding `test_a_decision_older_than_its_group_revision_is_stale`, `test_a_later_revision_dispatched_before_a_request_supersedes_it` (earlier requests stay accepted) |
| R1e | binding `test_the_unchanged_campus_is_accepted_with_blocked_redundant_trunks`, `test_delayed_forwarding_is_accepted_from_its_admitting_sample`, `test_each_decision_names_the_episode_and_revision_the_gate_used`, `test_legitimate_narrowing_is_bound_to_the_narrowed_episode`; the existing scalable, campus and scale suites |
| R2a | census `test_documented_end_returns_every_row_and_closes_once`, `test_first_read_failure_is_unreadable_even_for_no_more_files` (0, 5, 18), `test_failure_after_primary_reports_one_row_and_closes_once`, `test_failure_before_second_receiver_declines_bind_and_observe`, `test_false_next_without_error_is_unreadable`, `test_next_error_is_captured_before_close_replaces_it`, `test_invalid_snapshot_has_no_handle_to_close`; the unchanged `test_receiver_continuity.py` (real Win32 self/child, same-PID and helper incarnation) |
| R2b | census `test_governed_route_refuses_binding_failure_before_channel`, `test_governed_route_stops_at_failed_dispatch_and_owned_releases` |
| R3a | publication `test_a_timely_attempt_is_accepted_with_its_publication_fact`; repairs `test_an_on_time_evidence_join_is_accepted`, `test_the_legacy_worst_case_fits_with_receiver_and_dispatch_cost` |
| R3b | publication `test_a_step_after_the_verdict_that_crosses_the_deadline_withholds_acceptance` (budget, reload, serialization, flush); repairs `test_a_reload_that_crosses_the_deadline_withholds_acceptance`, `test_a_verdict_reached_after_the_deadline_names_the_verdict_boundary` |
| R3c | publication `test_a_link_that_returns_after_the_deadline_does_not_establish_acceptance` |
| R3d | publication `test_a_persistence_error_withdraws_a_timely_verdict`, `test_a_late_decision_whose_late_write_fails_keeps_the_first_failure_primary`, `test_an_interruption_immediately_before_the_link_is_a_cancellation`, `test_an_interruption_immediately_after_the_link_keeps_the_published_verdict` (in time, late), `test_an_interruption_while_recording_the_fact_still_records_it`, `test_a_contradictory_publication_fact_establishes_nothing`, `test_a_fact_whose_terminal_bytes_changed_cannot_be_loaded`; repairs `test_every_interruption_after_reservation_leaves_a_terminal_envelope`, `test_an_interruption_after_the_terminal_link_leaves_the_published_verdict`; route `test_an_envelope_that_cannot_be_completed_withdraws_acceptance` |
| R4a | linearity `test_the_evidence_grows_in_every_dimension`, `test_each_episode_is_derived_once_and_each_element_read_a_bounded_number_of_times` (30/1, 90/3, 240/3), `test_the_counting_apparatus_sees_a_per_client_scan`, `test_degraded_evidence_is_reported_once_not_copied_per_client`, `test_one_growing_component_is_derived_with_linear_inner_lookups` (10, 100, 1,000 switches) |
| R4b | scale `test_two_hundred_clients_on_one_site_through_the_whole_envelope`, `test_a_thousand_clients_over_three_sites_through_the_whole_envelope`; the benchmark below |

### RED before the fix, then causal RED on the fix

RED first, against the code the design commit `496bfd5` carries (identical to
`cc272c9` outside the brief):

- **R1.** The new binding module run against the old evaluator: 25 of 27
  failed and the two counter-controls passed. For the format-independent
  faults the old evaluator *accepted* the faulted evidence: every multi-access
  client with a continuity round that had no, unexecuted, foreign, repeated,
  wrong-VLAN or missing-switch readings; every client of a switch whose
  history was not fresh, was foreign, was miscounted or whose labels
  contradicted the sample; the client whose request was moved between its
  episode's LIS and FWD samples; and, end to end, the envelope whose product
  recorded a joined summary with no readings. The other failures need the new
  episode identity and fail for that reason, not as reproductions.
- **R3.** A scratch reproduction (not committed) over the old coordinator
  and store, run in the delegated `496bfd5` worktree, whose only changes were
  the uncommitted R2 files, which R3 does not touch: after an on-time
  verdict, a budget assembly or a serialization that ended at 501 s linked an
  envelope with `http_accepted: true` and exit code 0 under the 420 s
  contract, `exceeded_at` empty and `publication_offset_seconds: 1.0` (the
  verdict instant).
- **R2.** The delegated task reported 12 of 13 new tests failing with only
  `snapshot()` reverted; that count is its own report. The causal rows below
  were run here.
- **R4.** The work order's own measurement (N(N+1) visits of N E5 entries) is
  the RED; the control test shows the counting apparatus measures a per-client
  maximum as exactly clients x E5 entries.

Causal RED at `afa7ddf`, the last code commit: each row patched one
behavior out of `src/`, ran only its selected regressions and restored the
bytes (checked by SHA-256). The restored selection then passed 66 of 66 and
`git status` was empty. The first 19 rows were also run at `98e9c99` with the
same counts.

| Disabled behavior | Selected regressions failing |
| --- | --- |
| R1 continuity re-derivation (row findings and pair join ignored) | 9 of 9 |
| R1 access re-derivation and history agreement ignored | 7 of 7 |
| R1 episode dispatched before the request | 1 of 1 |
| R1 later revision supersedes | 1 of 1 |
| R1 decision revision equals episode revision | 1 of 1 |
| R1 ambiguous decisions refused | 1 of 1 |
| R1 repeated dependents refused | 1 of 1 |
| R1 gate decision marks | 3 of 3 |
| R1 ledger episode ordinals | 2 of 2 |
| R1 derived scope link ends | 1 of 1 |
| R4 E5 boundary maximum per client | 3 of 3 |
| R4 readiness evidence built per client | 3 of 3 |
| R2 only `ERROR_NO_MORE_FILES` ends a census | 6 of 13 (the other 7 are the normal end, first-read and invalid-handle cases, which that line does not decide) |
| R2 private error cleared before `Process32NextW` | 1 of 1 |
| R3 budget assembly consumes the deadline | 1 of 4 (the other three name other boundaries) |
| R3 store checkpoints withhold a late publication | 4 of 5 (the fifth is the budget boundary) |
| R3 link upper bound compared with the deadline | 2 of 3 (the third is the in-time control) |
| R3 recovery records the owed publication fact | 4 of 4 |
| R3 result reports the claim, not the provisional verdict | 1 of 1 |
| Review: each reading answers exactly its trunk ports | 2 of 2 |
| Review: a group inconsistency is one bounded reference per client | 1 of 1 |
| Review: the first reading fault names the row | 1 of 1 |
| Review: readings indexed once per derivation | 3 of 3 |
| Final review: every dispatched purpose names the scope | 6 of 6 |
| Final review: the claim derives timeliness from the fact's offsets | 1 of 3 (the other two are the provisional-verdict and boolean checks) |
| Final review: a fact is read back only with its terminal digest | 1 of 1 |
| Focused review: only the canonical episode label names an episode | 1 of 1 |

### Linear evaluation, counted

Evidence captured from real attempts over SIMULATED campuses; the evaluator
judged it with counting containers (`test_acceptance_evaluation_linearity.py`), at `52bc051`.

| Clients / sites | Groups | Components | Ledger entries | E5 entries | Entry visits | Position visits | E5 visits | Per-client-max control | Admissions / connectivity builds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 30 / 1 | 3 | 1 | 223 | 64 | 313 | 277 | 1 | 1,920 | 2 / 1 |
| 90 / 3 | 9 | 3 | 664 | 192 | 934 | 829 | 1 | 17,280 | 6 / 3 |
| 240 / 3 | 15 | 3 | 1,668 | 498 | 2,388 | 2,191 | 1 | 119,520 | 12 / 3 |

Rows, links and deciding-round readings are each handed out exactly twice
(the evaluation and the reload comparison); dependents at most three times.
One canonical derivation runs per episode, never per client or dependent.

One large component, counted inside the canonical rule (a ring of VLAN 10
trunks, `test_one_growing_component_is_derived_with_linear_inner_lookups`):

| Switches | Reading visits before | After | Port visits after |
| --- | --- | --- | --- |
| 10 | 230 | 30 | 40 |
| 100 | 20,300 | 300 | 400 |
| 1,000 | 2,003,000 | 3,000 | 4,000 |

Degraded evidence (one shared group with 10 and then 100 unrecorded ledger
episodes, repeated-ordinal rows and foreign readings): before the correction
the largest per-client finding list grew from 32 to 302; now it is the same at
both sizes and each group fault is reported once for the attempt.

### Independent review before delivery, and what it changed

Read-only Codex adversarial reviews, run while nothing wrote the tree. They are
advisory; none of them is the independent audit the standard requires. Every
finding was re-checked against the code and reproduced by a failing regression
before its fix.

- **Review 1** (composed, `cc272c9..98e9c99`): its output was truncated by the
  coordinator's own launch command, which kept only the last lines; only its
  last finding survived, and it was run again.
- **Review 2** (the same scope, full output kept): *needs-attention*; no
  material R2 or R3 issue.
- **Review 3** (composed, `cc272c9..f51281f`, after the first corrections):
  *needs-attention*.
- **Review 4** (focused on the corrections, `98e9c99..52bc051`):
  *needs-attention*, one finding.

| Finding | Disposition |
| --- | --- |
| Group inconsistencies are copied into every client of the group, so degraded evidence costs clients x faults (medium, review 1) | Real, and wider: a row's per-reading faults were copied too (32 findings per client at 10 faults, 302 at 100). Row validation stops at its first fault; each group inconsistency is reported once for the attempt and each client carries one bounded reference (`f51281f`) |
| A continuity reading that omits one port of an STP-blocked, unused trunk still passes every summary check, so the client is admitted over the alternate path (high, review 2) | Real: accepted by the evaluator and by the whole envelope. Each reading must answer exactly the trunk ports of its switch, once each (`f51281f`) |
| The canonical `usable_links` finds each link end by scanning the round's readings, so one episode costs links x switches (medium, review 2) | Real: 230, 20,300 and 2,003,000 reading visits for rings of 10, 100 and 1,000 switches. Readings and ports are indexed once per derivation with the same first-match semantics; now 3 reading and 4 port visits per switch. The product gate shares the rule (`f51281f`) |
| A dispatch whose purpose has a known prefix passes the ledger oracle even when it names a group or expectation outside the derived scope (high, review 3) | Real, and older than this delivery: four such dispatches produced no finding. Every dispatched purpose must name the scope exactly (`dispatches_outside_scope`); an unselected client's request is an effect outside the admitted scope (`52bc051`) |
| `publication_claim` trusts a fact's stored booleans, and a fact is read back without checking the terminal file (medium, review 3) | Real: a fact whose returned offset exceeds its deadline, and a changed terminal file, were both still accepted. Timeliness is derived from the fact's own offsets; `load_publication` returns a fact only while the terminal file keeps its name and SHA-256, which also governs a recovering handler's adoption (`52bc051`) |
| `readiness:<group>#01` passes the scope check as episode 1 and, dispatched before the real `#1`, has its span overwritten (high, review 4) | Real: judged with no finding. One parser accepts only the canonical label the runtime writes, for both the span index and the scope check (`afa7ddf`) |

The last correction, `afa7ddf`, was self-reviewed and caught by causal RED but
was not re-reviewed by Codex: the standard does not ask for review rounds
until one is silent, and its change is one parser used in two places.

### Scale evidence, re-measured on the final code

`tests/http_acceptance_scale_benchmark.py` at `afa7ddf` (tree `1ed8e4a8`),
clean, Windows-11-10.0.26200-SP0, Python 3.12.10, this checkout's `.venv`,
nothing else running. Each case ran in its own interpreter process. Packet
Tracer is SIMULATED by `tests/campus_product_simulation.py` on a fake clock:
every dispatch costs 0.05 simulated seconds and every receiver reading 0.015 s,
so no row is a zero-latency trace. Behaviours are as in the previous block
(immediate FWD; access ports forwarding 26 s and trunks 12 s after first read;
access ports never forwarding). "Response" is the product's returned summary,
"summary" the acceptance CLI summary, "fact" the publication fact; record,
envelope and fact sizes are the persisted files. The Python peak is
`tracemalloc` over the attempt alone; RSS is the process's working set before
and after the attempt and its peak, which includes compiling the campus and
the tracemalloc bookkeeping.

| Clients | Behaviour | Accepted | Represented / never started | Operations / ceiling | Receiver readings (s) | Simulated s / ceiling | Wall s | Evaluator s | Python peak MiB | RSS before / after / peak MiB | Response / summary KB | Record MB | Envelope MB | Fact bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | immediate fwd | yes | 2 / 0 | 30 / 1,191 | 30 (0.45) | 2.95 / 530 | 0.227 | 0.002 | 1.1 | 66.8 / 69.3 / 69.3 | 6.9 / 1.1 | 0.06 | 0.04 | 670 |
| 2 | delayed fwd | yes | 2 / 0 | 114 / 1,191 | 114 (1.71) | 29.41 / 530 | 0.261 | 0.005 | 1.3 | 66.9 / 68.2 / 69.8 | 18.2 / 1.1 | 0.08 | 0.07 | 673 |
| 2 | persistent non fwd | no | 2 / 2 | 115 / 1,191 | 115 (1.725) | 32.235 / 530 | 0.283 | 0.005 | 1.3 | 66.7 / 68.3 / 69.9 | 19.4 / 3.1 | 0.08 | 0.07 | 678 |
| 20 | immediate fwd | yes | 20 / 0 | 138 / 4,035 | 138 (2.07) | 9.97 / 1,770 | 0.361 | 0.008 | 3.6 | 68.0 / 71.1 / 75.6 | 31.4 / 1.1 | 0.32 | 0.17 | 671 |
| 20 | delayed fwd | yes | 20 / 0 | 222 / 4,035 | 222 (3.33) | 36.43 / 1,770 | 0.516 | 0.021 | 4.3 | 68.6 / 72.2 / 78.1 | 72.5 / 1.1 | 0.41 | 0.20 | 674 |
| 20 | persistent non fwd | no | 20 / 20 | 169 / 4,035 | 169 (2.535) | 35.745 / 1,770 | 0.53 | 0.022 | 4.0 | 68.2 / 71.5 / 76.9 | 77.1 / 20.7 | 0.38 | 0.20 | 679 |
| 200 | immediate fwd | yes | 200 / 0 | 1,349 / 43,654 | 1,349 (20.235) | 88.685 / 16,079 | 2.499 | 0.176 | 28.6 | 76.8 / 95.4 / 125.5 | 428.2 / 1.1 | 2.97 | 1.56 | 678 |
| 200 | delayed fwd | yes | 200 / 0 | 2,273 / 43,654 | 2,273 (34.095) | 340.745 / 16,079 | 3.984 | 0.262 | 35.6 | 76.7 / 103.6 / 141.7 | 829.4 / 1.1 | 3.82 | 1.89 | 681 |
| 200 | persistent non fwd | no | 200 / 200 | 1,512 / 43,654 | 1,512 (22.68) | 313.12 / 16,079 | 4.783 | 0.371 | 31.4 | 76.5 / 101.0 / 136.7 | 855.7 / 213.4 | 3.50 | 1.77 | 680 |
| 1,000 | immediate fwd | yes | 1000 / 0 | 6,666 / 213,164 | 6,666 (99.99) | 434.29 / 78,922 | 28.944 | 0.907 | 139.4 | 110.4 / 200.3 / 344.2 | 2,131.8 / 1.1 | 14.69 | 7.68 | 678 |
| 1,000 | delayed fwd | yes | 1000 / 0 | 10,362 / 213,164 | 10,362 (155.43) | 1558.53 / 78,922 | 42.914 | 1.881 | 171.8 | 110.1 / 227.0 / 433.2 | 4,076.3 / 1.1 | 18.83 | 9.03 | 681 |
| 1,000 | persistent non fwd | no | 1000 / 1000 | 7,236 / 213,164 | 7,236 (108.54) | 1469.26 / 78,922 | 38.963 | 1.744 | 152.4 | 110.6 / 206.3 / 414.7 | 4,250.5 / 1,092.3 | 17.35 | 8.70 | 683 |

Terminal dispatches equal the operations used in every row, and each equals
the receiver readings: one reading decided each dispatch. The product did the
same work as at `eed576f` (operations and simulated seconds are identical row
by row). The evaluator is slower than there (0.907 s instead of 0.805 s, and
1.881 s instead of 1.294 s, at 1,000 clients) because it now parses and
re-derives every episode; its growth is bounded by the counts above, not by
these wall times. Wall time rose too (fresh interpreter per case); it is this
machine's and no claim. The acceptance summary is about 1 KB when every
client is accepted and grows with the named refusals otherwise; the product's
own response dominates the transfer and is unchanged by this block. Nothing
was sampled or truncated.

### The first LIVE candidate: offline procedure and evidence inventory

Not executed. The candidate is the 30-client, two-access-switch campus, not a
product limit. A read-only delegated investigation mapped the registered
paths; every claim below that shapes the procedure was re-checked against the
code before it was written here.

**The candidate, as the real planner compiles it** (SIMULATED plans, the
`campus_payload(30)` intent): one site, 35 devices, 36 links; one Server-PT and
30 static PCs in VLAN 10; `HQ-DEFAULT-ACCESS-SW-01` (24 clients) and
`HQ-DEFAULT-ACCESS-SW-02` (6 clients and the server) behind
`HQ-DIST-SW-01/02`; five compiled trunk links in one component. The derived
scope has three readiness groups (two access, one continuity over four
switches and five links), local and L2 multi-access paths, and a derived
budget of 7,849 operations, 2,792 s, 30 reserved release operations and 40
reserved seconds. A LIVE deployment's manifest identities, and therefore its
scope digest, are its own; `--prepare` on the real manifest is authoritative.

**Procedure over registered paths, up to (not including) `--execute`:**

1. *Intent.* The exact attempt-marked intent (`http_content` equal to
   `COLD_HTTP_<attempt>`). Only the test helper `campus_payload` produces it.
2. *Physical (E4).* `pt_live_deploy(plan_json, ...)` is the registered path
   with observed readback (devices, module port effects, link peers and
   ports); it persists the manifest and prints its path and hashes. Cable type
   is unobservable by its reader and stays unverified.
3. *E5 prerequisites.* Trunks and transit VLANs must already exist; schema 2
   only proves them through trunk continuity at run time.
4. *Manifest.* The manifest must be under
   `<PT_MCP_GOVERNED_ROOT>/data/deployments` with the deployment id the grant
   names.
5. *Service-history freshness.* `<governed root>\data\services\<deployment>`
   must list nothing (`Get-ChildItem -LiteralPath <dir> -Force -Name`); any
   entry, whatever its state, refuses as
   `the deployment already has stored runs`, and an unlistable directory
   refuses as `history_unreadable:<type>`.
6. *Derived scope.* On the published delivery commit, with
   `PT_MCP_GOVERNED_ROOT` set:
   `.venv\Scripts\python.exe -m packet_tracer_mcp.adapters.cli.cold_http_acceptance --prepare --intent <intent> --deployment <id> --build 9.0.1.0858 --attempt <32-hex>`.
   It contacts nothing and prints the derived grant fields, `intent_sha256`
   and the cost.
7. *Grant.* A schema 2 document (fields below), then `--execute` from the
   checkout's own interpreter, never under pytest, under its own LIVE grant.

**Missing setup contracts, precisely.** Each blocks a complete, verifiable
operator procedure today; none is closed here.

| Step | What is missing | Where it shows |
| --- | --- | --- |
| Intent | A maintained, non-test producer of the attempt-marked 30-client intent | `tests/campus_product_simulation.py::campus_payload` is the only producer |
| Plan handoff | A registered export of the complete enterprise `TopologyPlan` bound to that intent | `pt_compose_enterprise_reference` returns a summary; `pt_live_deploy` needs `plan_json` |
| Deployment identity | A deployment id schema 2 accepts | `EnterprisePhysicalTopologyDeployer.deploy` defaults to `deployment/<hash16>` and `pt_live_deploy` passes none; the `/` fails the grant's `safe_name_component` check |
| Manifest root | One root shared by deployment and acceptance | `pt_live_deploy` saves with `DeploymentManifestStore()` (relative to the MCP process's working directory); acceptance reads `<governed root>/data/deployments` |
| Prior E5 proof | A registered, evidenced way to establish trunks and transit VLANs before an attempt without leaving a service run | `pt_apply_enterprise_services` configures only VLANs, access ports and endpoint addressing and writes a `data/services` record that makes history non-empty; the full configuration applicator (`execute_enterprise_reference`) has no registered LIVE entry point |
| Physical evidence | A durable E4 evidence inventory beyond the manifest | the deployer's item results and journal are returned in memory; the tool persists the manifest only |

An operator statement that E5 is applied is not observed forwarding: the
attempt reads history, the manifest and its own run, and trunk continuity is
decided only from its own fresh readings.

**Evidence inventory of one attempt** (all under the governed root):
the grant document and its SHA-256; the `--prepare` output; the manifest file;
the Packet Tracer process reading taken immediately before; the campaign
claim and the permanent attempt marker; the write-ahead envelope
`<attempt>.json`; the terminal envelope `<attempt>.completed.json` (ledger,
per-dispatch receiver counters, per-client outcomes, readiness citation by
count and digest, temporal record); the publication fact
`<attempt>.publication.json`; and the product record under
`data/services/<deployment>/`, cited by path and digest, whose readiness rows
carry episode identity and decision marks.

**Remaining LIVE-grant fields.** `schema_version: 2`, `profile:
http_by_ip_scalable_v1`, and unchanged from `--prepare`: `deployment_id`,
`manifest_hash`, `physical_topology_hash`, `servers`, `clients`,
`scope_sha256`, `max_operations`, `max_seconds`, `reserve_operations`,
`reserve_seconds`, and `intent_sha256`. Operator-chosen: `authorization_id`,
`attempt_id` and `marker: COLD_HTTP_<attempt_id>`. From the published,
clean executing checkout: `sha` and `tree`. From the instance: `build`
(exact), `channel: file`, and `process_id`, `process_path`,
`process_incarnation` read immediately before. Operator decisions:
`exclusive_disposable_lab: true` and `local_fence_limitation_accepted: true`.
Before any of this: a publication grant for the delivery commit (the
repository rule refuses an unpublished HEAD) and exact-SHA CI.

### Current projection

What holds for a governed HTTP-by-IP acceptance attempt after this block,
superseding the earlier blocks where they differ:

- **Readiness is re-derived.** A scalable client is admitted by a group only
  through the one episode the gate decided it with: raw readings parsed
  strictly, bound to the derived switch, VLAN, interfaces and link ends,
  decided again by the canonical rules, at the decided revision, dispatched
  wholly before the client's first request and not superseded before it.
  Labels, summaries and counts never grant. Older records without episode
  identity are readable and not accepted.
- **A census is complete only at `ERROR_NO_MORE_FILES`.** Any other ending is
  unreadable with its cause; at binding it declines, at a dispatch it ends
  authority for the rest of the attempt.
- **Publication decides timeliness.** Every controlled step up to the last
  checkpoint before the terminal link consumes the deadline; past it the same
  evidence is published with acceptance withheld and the boundary named. The
  link is bounded by a write-once publication fact; acceptance is established
  only when the terminal verdict is accepted and the link returned within the
  deadline. The envelope's `http_accepted` is the provisional verdict;
  `AcceptanceResult.accepted`, the exit code and the CLI summary report the
  claim.
- **Evaluation is linear.** One derivation per episode; per-client work is
  lookups in its own relationships.
- **Unchanged.** Schema 1's rules and frozen `1015/420/2/40` proposal; routed
  paths refused as
  `routed_path_unobservable:ipv4_routing_action_and_route_table_reader_unregistered`;
  trunks, transit VLANs and gateways proven, never configured; no routing,
  DHCP, HTTPS, mail, events or wireless; no claim of complete campus
  installation or of cross-site connectivity from independently served sites.
- **Evidence.** Offline, with SIMULATED Packet Tracer; the Win32 reads observed
  only this Python process and processes it owns. No capability, LIVE claim or
  published CI result changes here.

### Residual limitations

- The terminal link is bounded, not timed: a link that returns late leaves an
  immutable envelope whose provisional verdict says accepted and a fact that
  says acceptance is not established. A reader must use both; the CLI summary
  and `publication_claim` do.
- A crash between the terminal link and the publication fact leaves no fact;
  acceptance is then not established. A later invocation of the same attempt
  identity is refused by its spent marker, so nothing can add the fact later.
- The gate's episode ordinal and the labelled runtime's counter are two
  counters of the same calls; a composition that routed an observer call
  around the labelled runtime would be refused (`readiness_episode_unrecorded`
  or `readiness_episode_not_dispatched`), never accepted.
- Record rows name switches by the names the compiled plan and the observer
  use; the evaluator requires them to equal the derived scope's deployed names,
  as before. A deployment whose runtime names differ from its compiled names
  would be refused, not repaired.
- An interruption inside a recovery step itself, between a system call
  returning and Python recording it, or an uncatchable kill remains
  uncovered; what it leaves is fail-closed.
- The receiver interval between a reading and the receiver executing the
  command is unfenced, as before.
- The Windows census was exercised against a controlled kernel32 and against
  this process and its own children, never against Packet Tracer. Whether it
  explains the recorded native access violations is not established, and the
  earlier crash logs are kept.
- Trunk continuity and readiness were only ever observed against the
  SIMULATED campus terminal.

### Measured offline verification

Everything below ran in this checkout's own `.venv` (Python 3.12.10) on
Windows 11, against `cisco/main` resolving to `6263344`. The last code commit
is `afa7ddf`; the commit that adds these sections changes only this brief.

| Check | Result |
| --- | --- |
| Full offline suite at `afa7ddf` | 7,429 passed, 3 skipped, 3 warnings (the existing class-scoped-fixture deprecation) in 611 s; empty stderr; the tree was clean before and after |
| Earlier full runs, each on a clean committed tree | 7,412 passed at `98e9c99`; 7,418 at `f51281f`; 7,427 at `52bc051` (all 3 skipped) |
| Causal RED at `afa7ddf` | 27 of 27 disabled behaviors caught (table above); the restored selection passed 66 of 66 and `git status` was empty |
| Quality gate, worktree mode, `--base cisco/main` | 155 Ruff-gated files at `afa7ddf`; lint and format pass |
| Namespace inventory | 0 active legacy references, 0 unreviewed inert mentions |
| MkDocs build | passes with the two warnings that already exist on `cisco/main` |
| `git diff --check` | clean |
| Scale benchmark | `afa7ddf`, clean (table above) |
| Delivery gate on the delivery commit | reported in the handoff: a commit cannot record its own gate |
| Exact-SHA CI | pending; nothing was published |

### Pending operator grants

Nothing here authorizes a LIVE attempt, a publication or a merge.

1. **Publication.** The delivery commit must be published before any attempt,
   because the repository rule refuses an unpublished HEAD; exact-SHA CI is
   pending that publication.
2. **The first scalable LIVE attempt** (the 30-client candidate) needs, beyond
   its own LIVE grant, a decision on each missing setup contract listed above:
   either a registered path that closes it, or an explicit operator procedure
   the grant names. Until then no complete, verifiable operator procedure
   exists, and a grant naming a deployment id that contains `/` refuses at
   parsing.
3. **The grant fields** are those listed above; the Packet Tracer process
   reading and the published SHA and tree are taken immediately before the
   attempt.
4. **A schema 1 attempt** keeps the requirements of the previous block and now
   also gets a publication fact; acceptance is the claim, not the provisional
   verdict.

Fixture cleanup, workspace restoration, a second attempt, routed paths and
capability promotion each need their own grant.

### Delivery identity

Branch `feature/server-pt-goal-foundations`, reviewed base `cc272c9`, commits
`496bfd5` (design), `56c3a4f` (R2), `5cc46da` (R1 and R4), `98e9c99` (R3),
`f51281f`, `52bc051` and `afa7ddf` (review corrections), then this brief.
Status: READY_FOR_REVIEW. Self-review and the Codex reviews are not the
independent audit the standard requires.
