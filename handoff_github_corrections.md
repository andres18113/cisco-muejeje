# GitHub corrections and governed PoE handoff

Compact continuity note for the next AI. It is not authority. Resolve any
discrepancy in this order:

```text
source + tests + evidence
> docs/reference/cp-scale/current_state.json
> handoff.md
> handoff_github_corrections.md
> logs/history
```

## BASELINE_FINAL

- Repository/branch: `andres18113/cisco-muejeje`,
  `feature/runtime-ripv2`; publish only to
  `cisco/feature/runtime-ripv2`.
- Reproducibility correction:
  `d2fd950d93eebf41f2f1166c9a452fdb1f6f669c`.
- Original fail-closed PoE baseline:
  `9dcc9183f0891de91a7e5c2532c2aa3e492219f8`.
- Governed design:
  `0c8ec25dd4783a4096f082b57387ae3ea4a5d3e4`.
- Product implementation:
  `98a6b671539fb4c67e00ff04fdcce6ef8c09e844`.
- Reviewed product corrections:
  `055ee779655fe16d0d0c100a0101fae79f55ba69`.
- Governance split:
  `61fc5da8e2de1ffd59ccf2e7b9423d34b8d39111`.
- Planner-to-compiler port authority:
  `ebb996f68da6750d95862616bef42b7d8be413ca`.
- Productive PoE link-readback correction:
  `f3f646c872f2ec3d786a810b443fe7996b5ff04a`.
- Productive PoE link-result/cable correction:
  `4c4071923b137d401a4b6b6cb41044c26a295bc1`.
- Observer/deadline and common LIVE file-integrity hardening:
  `b356c57aa06443aea8947992e8901aa1af2726d0`.
- The commit containing this file is documentary only; the offline operational
  gate is deliberately bound to product SHA `b356c57aa06443aea8947992e8901aa1af2726d0`.

## LATEST_POE_QUALIFICATION

- Governed session `poe-9d0d21961c1c` on Packet Tracer `9.0.1.0858`
  ended `C — UNOBSERVABLE / INVALID EVIDENCE`. The observer returned no
  visible-state observation during the governed `observe(...)` invocation, so
  no later image can be admitted retroactively. The stored result is
  `UNKNOWN`, has no claim dimensions, keeps `poe_ports=null`, and authorizes
  no Router0 work.
- Its product snapshot recorded endpoint-first cleanup of all four temporary
  identities and semantic inventory restoration. A subsequent Windows
  Application Error event (`RecordId 17417`, report
  `cc89fdb1-bc7b-4758-a911-cbad5eb2fab4`) records `PacketTracer.exe`
  `0xc0000005` at `2026-09-06T03:37:53.1303623Z`. There is no retained stack or
  dump, so causation is not attributed to PoE or repository code.
- The run did not record canonical `.pts` identity or pre/post SHA-256. Its
  semantic cleanup result therefore cannot prove physical file integrity or
  session reuse after the crash. The combined incident is archived at
  `docs/reference/cp-scale/canonical-live-evidence/poe-delivery-20260906T033734787716Z-9d0d21961c1c-incident.json`,
  SHA-256 `0fe066fcb77a137277440e34e5f582db2780c8d9f62484a9a88e2428d47dc0a9`.
- Governed session `poe-e0da8048e559` ran from clean GREEN HEAD
  `f194ec6bc3302e579c5249b4315567fd2f3e80bf` on Packet Tracer
  `9.0.1.0858` and ended `UNOBSERVABLE / INVALID EVIDENCE`.
- Candidate `3560-24PS` and comparison `2960-24TT` each used
  `FastEthernet0/1` against a `7960` endpoint port `Switch`. Each
  `lwAddLink` returned exactly `true`, used straight-through `8100`, was
  emitted once, and reached exact bilateral readback without replay.
- The attributed simultaneous observation reported only green/red link-side
  triangles, no unequivocal endpoint-side power signal, and no confirmed
  endpoint settling. It also arrived outside the 300-second deadline. These
  facts cannot evidence powered-device delivery.
- Cleanup deleted all four attempted identities and semantic inventory
  restoration verified clean. The backend-managed
  `Power Distribution Device0` is neither semantic residue nor delivery
  evidence. Runtime snapshot:
  `data/capabilities/runtime/9.0.1.0858/0fa978810e5d4f368126553ce56a767c04c49adc5cb9beac9f04eb52b2494207.json`,
  SHA-256 `98901736ba53266a77d55eb8c54f16be8d0587935f7b9e79e9b23e18fb8eb0f4`.
- Governed session `poe-d085610a5c94` ended
  `UNOBSERVABLE / INVALID EVIDENCE`; it did not produce delivery evidence.
- Its candidate `lwAddLink` was emitted exactly once, but the old adapter
  discarded the Boolean result and reported `requested=true`; every bounded
  exact bilateral readback remained `NO_LINK`. The comparison link and manual
  observer were not reached, and cleanup/restoration verified clean.
- Product fix `4c4071923b137d401a4b6b6cb41044c26a295bc1` captures an exact
  `true` result before readback and applies the existing switch-to-IP-phone
  straight-through cable rule (`8100`), without replaying `lwAddLink` or
  relaxing bilateral convergence.
- The earlier governed session `poe-e76063f692ec` ended
  `UNOBSERVABLE / INVALID EVIDENCE`; it did not produce delivery evidence.
- Cause: the fixture attempted bilateral `getLink()` readback immediately after
  `lwAddLink` in the same command, before the governed convergence boundary.
- Product fix `f3f646c872f2ec3d786a810b443fe7996b5ff04a` separates the
  single link mutation from bounded, exact bilateral readback and never replays
  `lwAddLink`.
- PoE remains `UNKNOWN`, `poe_ports` remains `null`, and Router0 remains blocked.

## RESULTING_POE_ARCHITECTURE

- Typed domain observation models and fail-closed rules describe candidate and
  comparison switches, exact switch/endpoint bindings, observer identity,
  UTC observation time, visible indicators, deadline, cleanup and inventory
  restoration.
- The application service captures exact Packet Tracer build/inventory,
  creates the governed fixture, requests one typed manual observation, rejects
  an observation delivered after its existing deadline, cleans endpoints
  before switches, verifies restoration, and persists only a fully valid
  result.
- `GovernedPoEDeliveryObserver` owns one complete synchronous visual cycle:
  request, receipt, request/fixture attribution, deadline/freshness checks,
  domain validation and typed manual observation. It performs no sleeps or
  retry-until-green and returns no evidence for late, stale, misattributed or
  incomplete capture receipts.
- `PacketTracerLiveFileGuard` is common execution infrastructure. It pins one
  explicit canonical `.pts` identity, makes the file-to-open disposable,
  records canonical and disposable SHA-256 before/after, restores unexpected
  canonical changes through an exclusive verified staging file, and keeps
  crash, modification or unverifiable health sessions non-reusable.
- `PacketTracerLiveSessionSafety` samples crash and runtime health immediately
  before and after file verification/restoration. Either adverse sample, or an
  unobservable boundary, closes reuse and positive claims before persistence.
- The application service requires the `LiveSessionSafety` port and finalizes
  it after semantic cleanup but before snapshot persistence. Exact file
  identity/hashes are persisted in the probe context; inconsistent or legacy
  decided PoE snapshots without that evidence are capped at `UNKNOWN` at load
  and evidence-release boundaries.
- Infrastructure supplies fixture operations and governed measured-capability
  persistence. There is no checked-in LIVE runner; governed sessions use an
  ephemeral runner around the product service and persist through the existing
  snapshot store.
- `MeasuredCapabilityRecord` carries Packet Tracer version plus immutable
  `dimensions`; `as_evidence()` returns a defensive copy.
- Only manual verification or curated static override can authorize a manual
  delivery claim. Automated provenance cannot relabel manual observation.
- Claims require exact canonical model/build, tested bindings, candidate and
  comparison states, simultaneous count, method, observer, timestamp,
  indicators, readiness, cleanup and restoration.
- Valid same-model/build claims may union exact bindings. `poe_ports` is the
  maximum simultaneous count from one execution, never a sum across runs.
- The planner and compiler both enforce the exact switch port, endpoint model
  and endpoint port. Evidence for a phone cannot authorize an AP or camera.
- `PortAssignmentRange.first_port`/`last_port` are normative. The compiler
  rebuilds each range positionally from the planned device's ordered
  `access_capable` descriptors and reserves those exact ports, so it cannot
  permute the planner's per-endpoint mapping while keeping the same global
  port set. A range that contradicts the inventory is
  `PORT_ASSIGNMENT_RANGE_INCONSISTENT`, not a licence to reassign.

## CURRENT_GOVERNANCE

`docs/reference/cp-scale/current_state.json` schema v2 separates:

```text
last_live_state != current_offline_operational_gate
```

All previous canonical LIVE source identity, run evidence, counters, hashes,
artifacts and Voice/PVST outcomes remain frozen under `last_live_state`. Its
`36` counter is historical through 2026-09-03, not the current total. Five
later PoE runtime snapshots establish only a non-exhaustive lower bound of 41.
The current offline gate records:

```text
source_head           = b356c57aa06443aea8947992e8901aa1af2726d0
poe_delivery          = unknown
poe_ports             = null
hardware_plan         = partially_resolved
canonical_composition = blocked_before_topology
router0_authorized    = false
```

The current `source_head` is now
`b356c57aa06443aea8947992e8901aa1af2726d0`, the product hardening commit.
The latest qualification is consumed and invalid evidence; the observer and
`.pts` containment changes completed offline tests and fresh adversarial
review. No future LIVE qualification is authorized by this handoff. Its next
step is to await separate, explicit authority for any fresh disposable session.

Router0 is not eligible until sufficient exact PoE-delivery evidence is
obtained, reviewed and persisted.

## VALIDATION

- This offline hardening closure: the crash-during-finalization regression
  failed before the dual boundary sample and passed after it; the final focused
  product matrix was `72 passed`, the affected product/governance matrix was
  `189 passed`, and the final full suite was `3768 passed, 5 warnings`. The
  warnings are the known Pydantic, fixture-deprecation and pytest-cache noise.
- Required focused product matrix: `255 passed`.
- Recovered-review affected matrix: `249 passed`.
- Final governance matrix: `10 passed`.
- Final full offline suite after reviewed fixes: `3720 passed, 5 warnings`;
  warnings are the known
  Pydantic/pytest cache and fixture-deprecation noise.
- Full offline suite after the port-authority correction: `3723 passed,
  4 warnings`, same known noise.
- Import preflight used this worktree's `.venv`, resolved the production module
  inside this worktree and loaded exactly `packet_tracer_mcp`.
- The first independent review found three real defects: generated-JS brace imbalance,
  a vacuous malformed-claim test provider, and uncaught whitespace-invalid
  manual observations. All three were reproduced with failing tests, fixed and
  covered by green gates. The recovered complete fresh review verified those
  fixes and found two additional gaps: untrimmed request identities could still
  escape the typed result, and generic compilation could choose a port outside
  a narrow exact PoE claim. Both were reproduced, corrected surgically and
  covered by the final green gates.
- A later offline audit of the planner-to-compiler contract found that the
  narrow-PoE fix was verified only by global port sets. The compiler still
  ignored `first_port`/`last_port` and re-chose every endpoint access port, so
  it could permute the planner's per-endpoint mapping inside the authorized
  set. Reproduced with an adversarial fixture (two powered source groups of one
  endpoint model over four non-contiguous authorized ports on one switch),
  corrected, and covered by causal tests.

## DO_NOT_REDISCOVER

- `UNKNOWN != SUPPORTED`; UNKNOWN never authorizes.
- `APPLIED != VERIFIED`; `FAILED != UNOBSERVABLE != UNKNOWN`.
- Do not derive delivery from `getPower()`, `isPowerOn()`, a `-PS` suffix,
  catalog analogy, or a different endpoint/model/port.
- A derived claim cannot exceed its evidence. Partial observations authorize
  only their exact triples. Independent simultaneous capacities are not added.
- Malformed evidence of equal or greater authority blocks; stale, incomplete,
  non-canonical or inconsistent snapshots fail closed.
- Do not reopen or alter Voice, convergence, Floor1/Floor2/Floor3 or PVST
  semantics without new contradictory evidence.
- ISO/IEC 25010 and ISO/IEC/IEEE 42010 are engineering lenses only; no ISO
  certification or formal conformity is claimed.

## OPEN_DECISIONS

- Before any future LIVE mutation, an authorized operator must choose the exact
  candidate/comparison fixture scope, tested ports/bindings, observer identity
  and deadline, then confirm the live-run import gate in the mutating process.
- The physical delivery result is intentionally unknown offline. Only the
  future governed observation can determine whether its exact evidence is
  sufficient for any Router0 eligibility decision.

## REMAINING_CP_LIVE_ROUTE

```text
one governed PoE delivery qualification
-> review and persist exact evidence
-> re-evaluate canonical PoE gate
-> Router0 only if authorized
-> Router3 -> final canonical qualification
-> Voice 69/69 -> routing/control-plane -> IoT closure
-> cleanup + evidence + gates -> CP-LIVE COMPLETE
```

## AGENTS_MUEJEJE

`agents-muejeje` may provide complementary independent reviews or bounded
specialist analysis. It never substitutes for autonomous agents, deterministic
repository evidence, or Codex's final authority. Treat every external finding
as a hypothesis until reconciled with source and tests.

## NO_LIVE

This hardening task executed no Packet Tracer LIVE operation and did not touch
Router0. Session `poe-9d0d21961c1c` is prior direct evidence being reconciled,
not a run performed by this task. Its crash remains a non-attributed
reliability finding. No new qualification is authorized here.

## AUTHORIZED_LIVE_ATTEMPT_BLOCKED_BEFORE_QUALIFY

One LIVE PoE qualification was explicitly authorized from frozen source
`d782a0e5ed85776a2f5f6a89f368350df49c6bb3`. It did not run. The attempt
stopped at the bridge precondition, before any Packet Tracer mutation and
before `PoEDeliveryQualificationService.qualify()`. The authorization is
therefore NOT consumed.

Frozen state revalidated at attempt time:

```text
HEAD                        = d782a0e5ed85776a2f5f6a89f368350df49c6bb3
cisco/feature/runtime-ripv2 = d782a0e5ed85776a2f5f6a89f368350df49c6bb3
worktree                    = clean
actions run 34047619642     = success, 4/4
  windows 3.11 / windows 3.13 / ubuntu 3.11 / ubuntu 3.13
```

Offline preflight PASSED: worktree-local `.venv`; `packet_tracer_mcp` resolved
only inside this worktree; a single production namespace under `python -P`
(`src.packet_tracer_mcp` is findable only as an artifact of the current working
directory being on `sys.path`, and is never loaded); canonical
`C:\Users\Andres\Downloads\V5.2.pts` SHA-256
`175F775560AF7C17348C3D20CFFC81AE5DC8D294D2486CC9E8409FBEAD8BC071`
recomputed and matching; `PacketTracer.exe` FileVersion exactly `9.0.1.0858`;
two Packet Tracer processes running.

BLOCKER, direct evidence: `PacketTracerHttpTransport.start()` cannot bind
`127.0.0.1:54321`.

```text
PermissionError: [WinError 10013]
netsh int ipv4 show excludedportrange protocol=tcp
  54280-54379   (not administered)
  54380-54479   (not administered)
bind 54321 -> 10013 ; bind 54380 -> 10013
bind 54279 -> OK    ; bind 54200 -> OK
Get-NetTCPConnection -LocalPort 54321 -> nothing listening
winnat / hns / vmcompute / vmms -> Running
process elevated -> False
```

This is an operating-system port reservation held by the Hyper-V/WSL NAT stack,
not a port conflict (that would be `10048`) and not a stale listener. The bridge
port is fixed on both sides: `DEFAULT_PORT = 54321` in `live_bridge.py`, and the
MCP Control Center extension polls `:54321` from inside the webview
(`docs/live-deploy.md`). The `.pts` script module is an opaque encrypted Packet
Tracer artifact with no readable port, and the only negotiated file beside it is
`bridge_token`; there is no port-discovery channel. Moving the Python transport
to a free port would therefore leave the extension polling a port nothing
serves. Precondition 7 (authenticated, fresh, healthy bridge) is unsatisfiable
in this machine state.

No side effects were produced. `safety.prepare()` was never called,
`%LOCALAPPDATA%\packet-tracer-mcp\live-sessions` does not exist, no disposable
`.pts` was created, the canonical SHA-256 is unchanged, and no snapshot,
qualification or evidence artifact was written. The gate is untouched:
`poe_delivery = unknown`, `poe_ports = null`, Router0 BLOCKED.

Second precondition, reached but NOT verified because the bridge never
connected: `PacketTracerLiveSessionSafety.bind_active_workspace()` requires the
serving Script Module's `getCommandLineArg()` to equal the prepared disposable
`.pts` path exactly. The disposable must therefore be the module Packet Tracer
actually serves the bridge from, which is a registered-Script-Module identity
(**Extensions -> Scripting -> Configure PT Script Modules**), not a topology
file. Directly observed: both running `PacketTracer.exe` processes carry no
`.pts` argument on their process command lines. Whether the module argument and
the process argument coincide was not observable in this session; the next
attempt must confirm it against a live sample rather than assume it.

Remediation for the next attempt, operator action, elevated shell:

```text
net stop winnat
netsh int ipv4 add excludedportrange protocol=tcp startport=54321 numberofports=1
net start winnat
```

A reboot also reshuffles these dynamic reservations. Either way, re-probe that
`127.0.0.1:54321` binds BEFORE preparing a disposable, so a prepared session is
never abandoned mid-flight.

## NEXT_ACTIVE_STEP

```text
AWAIT_EXPLICIT_AUTHORIZATION_FOR_ANY_FUTURE_FRESH_DISPOSABLE_POE_SESSION
```
