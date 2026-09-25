# Server-PT DHCP fast loop: S3/Q3 qualification, version 1 (risk L)

## Identity and authority

| Field | Value |
| --- | --- |
| Checkout | `Cisco-MCP-server-services-goal-foundations` |
| Branch | `feature/server-pt-goal-foundations` |
| Starting commit | `2a44b38474a32e8978add2e22a81bc5a4efbc812` (tree `1f82e6e404725a45d8a966a21e8052fbbf87f72a`), the inspected baseline the work order names |
| Authoritative main | `6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main`, resolved again locally) |
| Work order | `Next_Work_S3_Q3_FASTLOOP_PROPOSAL.md`, 11,309 bytes, SHA-256 `6c24e5eaf0044e11191012fdd061d02db2098af3422664984844a876330ac5fe`, archived byte for byte under [`docs/reference/server-pt/assignments/`](../../reference/server-pt/README.md) |
| Campaign | `SERVER-PT-DHCP-FASTLOOP-01`, experimental |
| Risk | **L**: evidence semantics, effect admission, a new campaign, persistence and LIVE execution |

**Adoption.** The work order says it is a proposal until the operator adopts
it. On 2026-09-24 the lead asked the operator, verbatim: "Do you adopt it as the
execution order for campaign SERVER-PT-DHCP-FASTLOOP-01, including experimental
LIVE on a Packet Tracer 9.0.1.0858 instance that I launch and gracefully retire
myself (never your university topology)?" The operator selected **"Adopt +
accept risk"**, whose stated meaning was: "Adopted. I accept the exclusive-lab
residual risk. You may launch and gracefully retire campaign-owned PT
9.0.1.0858 instances within the order's 50,000-op / 21,600-s ceilings. No
force-kill." That answer is the adoption and the explicit acceptance of the
exclusive-lab residual risk the order requires. It authorizes nothing the work
order does not, and it withholds force termination.

**Instruction loading.** `AGENTS.md`, `CLAUDE.md` and
`docs/engineering/standards.md` were read from this checkout before planning.
Their SHA-256 digests are `a9f0e384…dfae81b`, `29312201…4b2516` and
`2de0d5b2…503178`, identical to the previous block's record. An interactive
`/context` listing cannot be observed from this session, so that check stays
**pending**.

## Problem and intended outcome

The S3 DHCP code is implemented and the historical Q3 profile is executable,
but no Server-PT client acquisition has ever been measured. Three LIVE Q3
attempts are consumed. Ordinal 1 stopped before any setter. Ordinal 2 observed
the stock `serverPool`. Ordinal 3 (`q3-2026-09-20T03-27-46Z-51ff55e7`) stopped
on `q3_native_default_changed:default_pool_changed:serverPool.end`. D-DHCP
attempt 2 (`d-dhcp-2026-09-21T20-01-43Z-dffd6c3b`) then localized the first
movement to the whole `configurePcIp` interval of the server's static address.
The movement is four fields, `network`, `mask`, `start` and `end`, to
`192.0.2.0/255.255.255.0/192.0.2.0/192.0.3.255`. Pool configuration while the
process was disabled, and enabling the process, added no further difference.
The exact-value classifier `assess_native_default_transition` and its one
reviewed catalog record exist, but nothing calls them. So every Q3 run still
stops on the one transition that was measured.

The Q3 procedure has four more gaps. It never observes spanning-tree
forwarding before a network action, only link and protocol flags. It reads at
most four lease rows and stops at the first `null`, so it keeps neither indexes
nor return types. It cannot discriminate a one-row table from a full one, and
it cannot tell which pool served a client. It also runs the product E5 batch,
server address and client DHCP modes together, so the native-default
transition never falls inside the one reviewed context.

The outcome is one integrated, versioned experimental Q3 profile run under
campaign authority on the maintained path. It records every M-DHCP measurement
as measured, inconclusive, omitted or blocked, each with its reason. It keeps
acquisition, intended-pool attribution, calibrated absence and causality apart.
It preserves every snapshot, row, call and native limitation. A native negative
is demonstrated and kept, never renamed as success.

## Scope and explicit exclusions

In scope:

- The campaign identity, its ledger phase for a qualification run, experimental
  source authority for the qualification runner, and binding of the launched
  process. Retirement uses the existing route, with an ownership basis derived
  from an archived qualification.
- Two versioned stage profiles, `Q3-FL-C1` (a one-user intended pool) and
  `Q3-FL-C2` (a two-user intended pool). They share one procedure.
- A versioned native-default policy that wires the existing classifier into
  the run.
- DHCP acquisition readiness, derived from the compiled plan and observed
  through the product readiness gate with the FASTLOOP sampling contract.
- One calibrated lease-scan probe, with pure termination, calibration and
  attribution classifiers.
- The Node stub extensions and the tests, then the LIVE episodes and their
  evidence.

Excluded:

- S2/Q2, HTTPS/Q1b, S1c routed paths and S5 nslookup.
- Relay, routed and wireless DHCP.
- DHCP event observers, callbacks, zero-event unregister, `dhcpRelease` and
  `resetDhcpConfOn`. M-DHCP-3 stays OMITTED under the approved deferral.
- Any write to `serverPool`, and any change to the simulation clock or lease
  settings.
- A second DHCP subsystem, a test-only LIVE executor, an arbitrary-script
  escape hatch, and any change to the MCP public signature.
- Capability promotion, merge, force termination, HTTP on DHCP clients, and
  any change to the historical Q3/D-DHCP profiles, counters or records.

## Requirements and acceptance criteria

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| DF1 | The campaign is selected by identity and charter digest together | `SERVER-PT-DHCP-FASTLOOP-01` is experimental, its charter digest is the work order's, and its ledger enforces 50,000 operations and 21,600 s with 1,000 / 600 protected. C31 and FASTLOOP derive exactly as before |
| DF2 | A qualification run is a ledger phase | Before contact, a `qualification` phase is admitted against the open episode at the episode's exact HEAD and tree. Its grant is the stage ceiling. Its result records the operations and active seconds used. A phase that is admitted but never settled is charged at its grant. Qualification never draws the protected reserve |
| DF3 | Only campaign authority waives publication, and only publication | The runner drops the `repository_upstream` refusal only for an authority that names exactly this campaign, episode, attempt, authorization, HEAD and tree. Clean-tree, head, tree, isolation, process, budget and record rules stay. A mismatched authority refuses before contact, and the public invocation without a campaign still requires publication |
| DF4 | The run binds the launched process | A campaign run's authorized PID and path must equal the attempt's `--record-launch` record, and the preflight incarnation must equal the recorded one. Any mismatch refuses before a transport exists |
| DF5 | Retirement keeps its rules | `--retire` for a campaign qualification attempt derives its basis from the archived qualification status: `owned_qualification_restored`, `blank_launch_then_qualification_effects`, `blank_launch_then_interrupted_qualification` or a blank launch. This campaign never forces |
| DF6 | The experiment is a versioned profile, not a renewed grant | `Q3-FL-C1` and `Q3-FL-C2` (profile `Q3-FL`, version 1) pin fixtures, links, pool capacity, steps, the file channel and build `9.0.1.0858`. Their ceiling is their composed worst case plus the finalization reserve. `Q3` and `D-DHCP` definitions, ceilings and records do not change |
| DF7 | Only the reviewed native-default transition is admitted, then stability is required | The server-address interval is admitted only as the exact catalog realignment in its exact context, or as unchanged. Every later interval must be unchanged against the reading after the address. Drift or an unobserved reading stops further effects. Every snapshot and difference stays on the record |
| DF8 | Forwarding is observed before a network action | One readiness plan is derived from the compiled access placements and the DHCP lease dependents, each needing the client's and the server's access ports. It is decided by the product gate with the 16-call sample and the episode allowance, before any client mode activation and acquisition. A refused group blocks exactly its dependents |
| DF9 | Lease tables are calibrated, not assumed | One probe reads an explicit index window of every named pool without stopping at `null`. It keeps each index, return type, raw field and field type, exception text and repetition. A pure classifier names each scan's termination and derives a calibration verdict across states. A capacity is never a count, and a throw is never end of table |
| DF10 | Acquisition, attribution, absence and causality stay separate | Each client gets one classification. It states native addressing, an exact intended row, an exact native-default row, a wrong-MAC contradiction, a calibrated or incomplete absence, and causal acquisition as separate fields. The indexes are built once per scan |
| DF11 | The capacity-one negative needs completed negatives | `lease_not_acquired` from the intended pool needs a dispatched request, the full intended pool holding the first client's row, a calibrated absence for the second client, and no intended-window address. Service from the native default is `served_by_native_default`, a separate result |
| DF12 | Time and renewal are observed, not forced | Two timed readings with no new request, then a declared 60 s natural-renewal horizon. A changed lease string is not renewal, and no renewal inside the horizon is INCONCLUSIVE. Requested renewal is OMITTED as `requested_renewal_contract_absent` |
| DF13 | A same-action repeat sends no second `dhcpRun` | After an acquisition whose outcome is known, replaying the identical action reports `own_claim_replayed` with `attempted=false`, and anything else is CONTRADICTED. No claim is deleted and no nonce is changed |
| DF14 | Stop rules and finalization hold | An unresolved effect, a policy stop, a persistence failure or a contradiction ends further experimental effects. The terminal reading and owned finalization still run. An outcome-unknown mutation is never retried |
| DF15 | Logic scales per client, pool and group | The pure derivation and classifiers are exercised at 2, 20, 200 and 1000 clients offline with linear work. Nothing claims the large cases ran natively |
| DF16 | Evidence is immutable and complete | Each episode leaves its ledger records, launch, qualification record, stdout, stderr, exit code, retirement and hashes. Product capability records stay UNKNOWN, and proposed capability decisions await independent review |

## Architecture and affected contracts

The existing layers keep their responsibilities. No new executor, transport,
bridge endpoint, MCP argument or `.pts` change is introduced.

- **Domain.** `service_qualification.py` gains the two stages, two operational
  preconditions and their measurement set. `dhcp_native_default_lifecycle.py`
  gains `assess_native_default_sequence`, which applies the versioned policy
  over a list of intervals with the existing pairwise classifier.
  `service_access_readiness.derive_access_readiness_plan` gains an explicit
  `request_kinds` argument. It defaults to the HTTP kinds, so every existing
  caller is unchanged. `DHCP_ACQUISITION_KINDS = {DHCP_LEASE}` is the named
  second set: the compiled lease expectation names the server as host and the
  PC as client, and the acquisition it follows needs both access ports. The
  new `dhcp_lease_evidence.py` holds the scan termination classifier, the
  calibration verdict and the per-client attribution. The Q3-FL projections
  (client-mode E5, per-client acquisition E6, fixture access-VLAN binding)
  join the existing D-DHCP projections and `ProjectionRewrite`.
- **Application.** `qualify_server_services.py` gains `_run_q3_fastloop`,
  composed from the existing fixture setup, default reader, E5/E6 applicators,
  readiness gate, ledger and finalizer. `server_pt_campaign.py` gains the
  campaign. `server_pt_campaign_ledger.py` gains the `qualification` phase.
- **Infrastructure.** `service_qualification_probes.py` gains
  `read_dhcp_lease_calibration`, with data serialized through `json.dumps`.
  The commissioning store gains a qualification status record.
- **Adapters.** The qualification CLI gains the campaign composition:
  `--campaign`, `--charter` and `--episode`, with the attempt identity shared
  with the launch record. The commissioning CLI accepts the new campaign for
  the ledger, `--record-launch` and `--retire` only.

**The forwarding fixture binding, stated.** The compiled Q3 plan places the
server and both PCs on `__MCP_E6Q_SW` `Fa0/1`–`Fa0/3` in VLAN 10. As in
historical Q3, the runner owns the physical fixture and applies no switch
action, so those ports stay in the stock VLAN 1. The readiness plan keeps the
compiled switch, interface and endpoint placement. It rebinds only the VLAN to
the one the fixture carries, and records that as a `ProjectionRewrite`. A
placement that is missing or ambiguous refuses, and nothing is inferred from
device names.

**Order of effects.** The profile keeps the product's E5-before-E6 order. It
splits E5 by subject so the native-default transition falls inside its
reviewed context:

1. admission, fixtures;
2. the baseline: typed server admission (`before_e5`), client identity and
   mode, and a calibrated scan of the native pool;
3. the server's static address alone (`after_server_address`), assessed
   against the catalog record;
4. forwarding, decided through the gate for every client's lease dependent;
5. client DHCP mode for admitted clients, while the server's process is still
   disabled, so any background discover finds no server. The step is followed
   by a client reading, a stability snapshot and a calibrated scan;
6. the server's pool and enable, through the existing server projection. The
   step is followed by a stability snapshot, the empty-state calibrated scan
   and two timed client readings with no request;
7. per admitted client, in plan order: a pre-request reading, one typed
   acquisition under its claim (the existing script), the product read-back,
   a bounded settle of four readings, and a calibrated scan. After the first
   client, the same-action repeat;
8. two timed readings and the 60 s natural-renewal horizon;
9. terminal: the `before_cleanup` snapshot and a final scan, then owned
   finalization.

## Budget arithmetic

Worst case for two clients, one operation per bridge call. Setup is 17: two
admission reads, four devices at two, three links at two, and one identity
read.

- Baseline is 3: server, clients and scan.
- The server address is 3: one E5 `send`, one read-back and one snapshot.
- Forwarding is 362: one access group of three interfaces. Its two episodes (its own
  and at most one narrowed) are each capped at `READINESS_EPISODE_CALLS = 181`.
- Client mode is 6: one E5 `send`, two mode read-backs, the client reading,
  the snapshot and the scan.
- Server setup is 7: two E6 actions, the server-state read-back, the snapshot,
  the scan and two timed readings.
- Acquisition is 9 per client: the pre-read, the dispatch, two read-backs,
  four settle reads and the scan. With the repeat and its post-read that is
  2 × 9 + 2 = 20.
- Timing is 6: two timed readings, three horizon readings and a scan.
- The terminal reading is 2, and the finalization reserve is 11.

The total is 17 + 3 + 3 + 362 + 6 + 7 + 20 + 6 + 2 + 11 = **437**. The ceiling
of both profiles is **440 operations**, with no spare that could fund a retry.
The time ceiling is **1,500 s**, with a 300 s finalization reserve. That
covers the gate's 120 s total, 16 s of settle, 75 s of timed and horizon
waits, and the per-call time of the ceiling. The ledger grant of a
qualification phase equals the stage ceiling. An episode's allocation adds the
lifecycle time, so it is 440 operations and 2,400 s. These are ceilings, not
forecasts. A typical run spends one forwarding sample of about ten calls.

## Invariants

1. `serverPool` is never written, renamed, removed, disabled or reset. An
   in-range address never identifies the serving pool.
2. The versioned policy admits one reviewed transition in one exact context.
   After it, only an unchanged native default permits further effects. No
   observed value is learned.
3. A native boolean exists only as `typeof "boolean"`. A capacity is not a
   count. A `null` is end of table only for the scan that observed it, and a
   throw never is.
4. Mode activation, acquisition, an intended row, calibrated absence and
   causal acquisition are distinct claims. Read-back plus table attribution
   never becomes `DHCP_LEASE=VERIFIED`, and the R-EVT-05 fallback stays
   active.
5. `dhcpRun` is dispatched at most once per subject claim. A lost or failed
   effect is never retried, and no claim is deleted or re-nonced.
6. Campaign authority is selected by identity plus charter digest, never by a
   flag, and it waives exactly one rule for exactly one attempt.
7. Historical records, counters and profiles are immutable. Product capability
   records stay UNKNOWN.

## Test design

Unit tests cover the campaign and ledger arithmetic, the qualification phase,
the authority waiver and its refusals, the process binding, the retirement
basis, the stage definitions and their budget arithmetic, the sequence policy
over the recorded D-DHCP snapshots and its drift controls, and the DHCP
readiness derivation. They also cover the scan termination, calibration and
attribution classifiers with positive, negative and incomplete controls,
including 2/20/200/1000-client linear scale.

Integration tests run the real generated scripts in the persistent Node stub.
They cover the calibration probe, the whole Q3-FL coordinator (default
realignment admitted, then drift refused; forwarding refused; background
acquisition; native-default service; capacity-one negative; claim repeat;
outcome-unknown stop; terminal reading after a stop) and the CLI campaign
composition end to end, with the ledger and store.

System and acceptance tests are the LIVE episodes on Packet Tracer 9.0.1.0858,
reported with their original chronology. Behavioral changes get causal RED at
their boundary. Focused and affected tests run per checkpoint. The full suite,
delivery gate, MkDocs, namespace inventory and whitespace run once on the final
candidate.
