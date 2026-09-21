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
| `tests/test_service_access_readiness.py` | new: 24 derivation, gate and composition tests |
| `tests/test_dhcp_native_default_lifecycle.py` | new: 34 transition, coexistence and non-promotion tests |

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
| Focused readiness set | `tests/test_service_access_readiness.py`, `24 passed` |
| Focused DHCP set | `tests/test_dhcp_native_default_lifecycle.py`, `34 passed` |
| Affected integration and system set | the nine `service_entry_fixture` consumers plus both access-forwarding modules, `236 passed` |
| Evidence verification | 62 recomputed digests over the operator package and the three markers, 0 mismatches, 0 missing; archive SHA-256 equals the work order statement and the operator sidecar |
| Full offline suite | `6912 passed, 3 skipped, 3 pre-existing warnings`, exit 0, 638.60 s. The base recorded `6854 passed, 3 skipped`, so the delta is exactly the 58 tests this block adds |
| Provisional quality gate | base and merge base `6263344e`, 110 changed Python files Ruff-gated (104 at the base plus the six this block adds), no mechanical exemption, exit 0 |
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
