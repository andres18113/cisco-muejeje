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

Single writer is held by that evidence, not by a new lock. The mailbox
protocol was built for coexistence rather than exclusion: `FileBridge`
names every request `pid_boot_seq` so concurrent MCP processes sharing one
mailbox cannot collide, and `_purge_own_stale` deliberately never touches
another process artifact. A lock file would bind only the Python side and
would not observe the hazard that actually exists here, which is a second
Packet Tracer answering the same mailbox. What is observable is what is
used: exactly one process at admission, an empty mailbox at admission, and
the same pairing with nothing undrained at exit.

The sampling and evidence corrections do not add a stage, fixture, effect,
parser or timeout. The lifecycle correction adds only the two exact process
identity fields described above. They update D-WEB's measured worst case from 61 to 63
operations: M-DWEB-1 is nine operations (two four-call STP samples plus one
simulation-state read) and M-DWEB-5 is six (one listener read, one four-call
STP sample and one simulation-state read). The proposed ceiling stays 68, so
the finalization reserve remains untouched.

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

Every figure below is the worst case of the real composed call path measured
against the stub, not a sum of placeholder steps. The measured Q3 path is the
calibration source: an endpoint E5 batch costs one `send` plus one verification
read per expectation, an E6 service action costs one dispatch plus one
read-back per expectation, and one native default reading costs one dispatch.
The exact per-stage tables are pinned by a contract test and reproduced in the
operator contract.

The old 60-operation ceiling and the 43/47 planning figures of the prepared
profiles are not evidence that this fits; the numbers are recomputed from the
composed paths. Neither ceiling is raised by this delivery.

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
