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
- Server setup is 5: two E6 actions, the server-state read-back, the snapshot
  and the scan.
- Acquisition is 2 background readings, then 10 per client: the pre-read, the
  dispatch, three read-backs (the server state the compiled acquisition is
  staged on, the lease and the attribution), four settle reads and the scan.
  With the repeat and its post-read that is 2 + 2 × 10 + 2 = 24.
- Timing is 6: two timed readings, three horizon readings and a scan.
- The terminal reading is 2, and the finalization reserve is 11.

The total is 17 + 3 + 3 + 362 + 6 + 5 + 24 + 6 + 2 + 11 = **439**. The ceiling
of both profiles is **440 operations**, with no spare that could fund a retry.
The server-state read-back is read fresh before each acquisition because the
compiled acquisition carries it as a `verification_dependencies` entry: the
product admits no acquisition until that read-back is VERIFIED, and the
projection does not rewrite that prerequisite away.
The time ceiling is **1,500 s**, with a 300 s finalization reserve. That
covers the gate's 120 s total, 16 s of settle, 75 s of timed and horizon
waits, and the per-call time of the ceiling. The ledger grant of a
qualification phase equals the stage ceiling. An episode's allocation adds the
lifecycle time, so it is 440 operations and 2,400 s. These are ceilings, not
forecasts. A typical run spends one forwarding sample of about ten calls.

## Design refinements made during implementation

Each of these was found by a test against the real product components, and
each is a narrower reading of the approved design, not a wider one.

1. **A known dispatch is not a settled postcondition.** Under the canonical
   product rules, a void `dhcpRun` stays off the decision frontier until a
   read-back VERIFIES it. `DHCP_LEASE` never verifies under the R-EVT-05
   fallback, so historical Q3 ended `outcome_unknown` by construction. Q3-FL
   adds one explicit predicate, `_q3fl_request`. A row that reproduces its
   canonical decision, was accepted and correlated, reported
   `attempted=true` and carried no call error is a *known dispatch*.
   `attempted=false` with a refusal cause is a *known non-dispatch*, and a
   preflight refusal dispatched nothing. Anything else is *outcome unknown*:
   it stops every later effect and is never retried. The predicate admits
   only the next independent subject's acquisition and the same-subject
   replay control. The product frontier rule, and everything that depends on
   `DHCP_LEASE`, are unchanged. Causal controls: a call error stops the run
   before the second client's dispatch, and the replay is never attempted.
2. **An own-claim replay reports `attempted=None`.** The runtime cannot speak
   for the earlier evaluation, so it states nothing. The replay's branch
   report `own_claim_replayed`, correlated and without a call error, is the
   evidence that *this* evaluation reached no `dhcpRun`, because the claim
   script calls it only on the no-claim path. This is the same reading
   historical Q3 used. Negative control: with the claim store dropped, the
   replay dispatches again and the repeat is CONTRADICTED.
3. **The server-state read-back is staged per acquisition.** The compiled
   acquisition lists it in `verification_dependencies`, so the product admits
   no acquisition until it is VERIFIED. The per-client projection keeps it and
   reads it fresh, one operation per client, which the budget now counts
   (439 of 440).
4. **A measurement that was not reached is NOT_RUN, with its reason.** A
   capacity, repeat or timing row whose procedure a stop cut off is never
   recorded as a RAN row that says nothing happened.
5. **A declared omission keeps its own reason.** The diagnostic start used to
   overwrite every unselected measurement with `not_selected_by_authorization`.
   It now leaves a measurement the profile already omits, such as M-DHCP-3 or
   requested renewal, with the reason the profile declares.

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

## Pre-LIVE independent review, version 2

Four focused Codex adversarial reviews ran against the committed delta before
any LIVE contact. The work order requires a review of safety-sensitive deltas
before they execute. Every finding was reproduced as a failing regression
first, fixed at its owning layer, and then proven causally RED by disabling
the fix.

| Review | Findings | Closed by |
| --- | --- | --- |
| 1, on `a6eaf50..ae6c530` | Interrupted run settled at zero operations; no-effect retirement basis accepted before the baseline was checked; any non-empty campaign id waived publication; `undefined` lease read counted as a null end; exact row hid a same-IP wrong-MAC row | `4a59d9e` |
| 2, on `ae6c530..4a59d9e` | Four closed; a `refused` status with unknown effects still passed as an interrupted basis | `8b164c5`, `733d670` |
| 3, on `831e501..8b164c5` | A settled qualification with no archived status read as interrupted | `68ad08d` |
| 4, the full basis matrix | One combination left: an effectful status claiming an unobserved empty baseline | `5df8d05` |

Causal RED on the implementation itself found one rule no test protected: the
capacity negative's calibrated-absence requirement. `3a899b4` added its
regression. In total, 31 causal cases were disabled one at a time, and each
turned its named regression RED. The tree was byte-identical after every
restore.

## LIVE episode 1, version 3

| Field | Value |
| --- | --- |
| Checkpoint | `5df8d05ec89b9bb5042e1dd2a040c0eaad9890e8` (tree `3f1bc384c8bfe5b755839eba67e5b1b4dcddf603`), clean, unpublished, no CI claimed |
| Ledger episode | 1, opened 2026-09-25T03:11:07Z (`bc75a86f…582de6`), closed 10:58:46Z (`4859805b…b1c3`) |
| Attempt / instance | `8500b4688a054130a2b18cdb183b0a0a` / `e75c633c76924a69b12ef693fcac724c` |
| Laboratory | one blank Packet Tracer 9.0.1.0858, PID 47680, created 03:11:20Z, launched with no argument; `--record-launch` proved a blank document |
| Stage | `Q3-FL-C1`, file channel, run `2026-09-25T03-12-05Z-97cc881e` |
| Record | `q3-fl-c1-2026-09-25T03-12-05Z-97cc881e.json`, SHA-256 `4139f6c97c27ea6b33e2a485032467d1351ea6729770b9ecbf83077c83b17223` |
| Result | `completed`, 123 of 440 operations, 219.3 s, restoration proven, no primary or secondary failure, `dirty_state: unknown` because both product claims are engine residue retained until retirement |
| Evidence | archived byte for byte, 41 files under [`evidence/dhcp-fl-01/`](../../reference/server-pt/README.md), with `MANIFEST.sha256` |

**Chronology, from the record's own offsets.** Fixtures and links were created
first. The typed baseline admitted the exact stock `serverPool`. The server's
address alone moved it to `192.0.2.0/255.255.255.0`, `192.0.2.0`–`192.0.3.255`.
The versioned policy matched that move to the reviewed D-DHCP record, and every
later interval was unchanged, through `before_cleanup`. The product readiness
gate admitted both clients on its first episode: `Fa0/1`–`Fa0/3` were FWD in
VLAN 1 after 11 samples and 47 channel calls in 27 s. Client DHCP mode was
activated while the process was still disabled. Both mode read-backs were
true, and neither client had an address then. The pool and the enable were
dispatched once, at offsets 61.6–65.0 s. At 79.1 s, PC1's pre-request reading
already showed `192.0.2.3/24`, lease "1 days 0:0:0". The typed acquisitions
were then dispatched, one per client under its claim. The same-action repeat,
the timed readings, the 60 s horizon and the terminal reading followed, then
owned finalization.

**Retirement.** `--retire` selected the document window by the build signature
(`Qt687QWindowIcon`, "Cisco Packet Tracer"), with basis
`owned_qualification_restored`. It posted one revalidated `WM_CLOSE` at
03:15:59Z. Packet Tracer raised the modal `QMessageBox` "Exit -- Cisco Packet
Tracer": *"Any unsaved changes will be lost. Do you want to save your work?"*
(Yes / No / Cancel), read read-only through UI Automation. The process did not
exit within the 60 s grace. The campaign refused to force
(`forced_retirement_not_authorized_by_campaign`), and the attempt is archived
as a refused retirement. The dialog was not answered by the lead. The
operator, asked, answered "No". A read-only census at 10:58:33Z then found no
Packet Tracer process, and the mailbox held only its heartbeat. That exit is
lead-observed evidence (`06-exit-observation.json`); it is not a campaign
retirement record, and its instant is bounded only by that census.

**Ledger.** The qualification phase settled at 123 operations and 220.4 s.
The closed episode charges its whole open interval, 28,059 s, because a
laboratory stayed up with the prompt unanswered while the lead's session was
paused. The ledger's rule is deliberately conservative and never subtracts, so
the campaign has committed 123 of 50,000 operations and 28,059 of 21,600
seconds. Its ordinary time is **exhausted (−7,059 s)**, and no further episode
can open under this charter without a new operator grant.

## Measured results per M-DHCP identifier, version 3

Every row belongs to episode 1, `5df8d05`, build 9.0.1.0858 and the file
channel. Nothing here is a product capability.

| Id | Record status | What is established | What is not |
| --- | --- | --- | --- |
| M-DHCP-1 | measured, SUPPORTED_IN_SAMPLE | `DhcpServerMain` binds `FastEthernet0`. The native default moved only by the reviewed realignment and stayed put after it. The ensure-present path stored `MCP_E6Q_DHCP` (the product server-state read-back was VERIFIED, enabled true, two exclusions). The intended range lies inside the realigned native range | that a stored intended pool serves anyone |
| M-DHCP-4 | measured, SUPPORTED_IN_SAMPLE | Each port reports dotted-hex MAC text, stable across every reading. The lease rows carry the same MAC text exactly (`0009.7CBD.2093`, `0001.C9C3.9696`) | a general MAC-representation equivalence |
| M-DHCP-5 | measured, SUPPORTED_IN_SAMPLE | `isDhcpClientOn` returned boolean false before activation and true after it, and forwarding was admitted before any client activity | that activation is inert: see M-DHCP-6 |
| M-DHCP-2 | measured, INCONCLUSIVE | `getLeaseAt` never returned null. It threw `invalid vector subscript` at exactly the row count and at every later index, in all 12 scans: intended pool 0 rows; `serverPool` 0 rows, then 2 rows. Rows are objects whose `ipAddress`, `macAddress` and `port` are strings and whose `leaseTime` is the number 86,400,000 | end-of-table by throw is not admitted by the conservative rule (a getter failure is not automatically an end); no full state and no one-row state of the intended pool was ever reached |
| M-DHCP-3 | omitted | the approved event deferral stands; no observer was registered | — |
| M-DHCP-6 | measured, SUPPORTED_IN_SAMPLE for separation | Both clients were served by the **native default**. Each has an exact IP/MAC row in `serverPool` and no row in the intended pool, and the product read-backs are CONTRADICTED `address_outside_intended_allocation`. Each typed request was a known dispatch (`attempted=true`, correlated, no call error) | **causal acquisition by `dhcpRun`: not established.** Both clients already held their addresses before their request, acquired autonomously within about 14 s of the enable; the scans before the request were throw-terminated, so no prior absence was calibrated. Intended-pool attribution: not reached |
| M-DHCP-6-CAP | measured, INCONCLUSIVE | the second client was served by the native default | `lease_not_acquired` from the intended pool: the one-user pool was never filled by the first client, and absence is uncalibrated |
| M-DHCP-6-REPEAT | measured, SUPPORTED_IN_SAMPLE | The identical replay reported `own_claim_replayed`, correlated, with no call error. The claim script calls `dhcpRun` only on its no-claim path, so no second `dhcpRun` was sent, and the address and lease text were unchanged afterwards | anything about renewal |
| M-DHCP-6-TIME | measured, INCONCLUSIVE | Two timed readings 15 s apart and three horizon readings over 60 s all showed the same address and "1 days 0:0:0" | natural renewal: a 1-day lease renews at about 12 h, far beyond the declared horizon; nothing was manipulated |
| M-DHCP-6-RENEW | omitted | `requested_renewal_contract_absent`: no typed renewal operation exists, and replay is not renewal | — |
| M-DHCP-1-FINAL | measured, SUPPORTED_IN_SAMPLE | the pre-cleanup native default equals the realigned reading; both tables were read again | — |

## Current projection and the remaining boundary, version 3

- **The first unmet boundary is native, and it is demonstrated.** On 9.0.1.0858,
  giving the Server-PT its address realigns `serverPool` to the server's
  subnet. Once the process is enabled, DHCP-mode clients on that segment are
  served from `serverPool`, not from the product's intended pool, even though
  the intended pool is stored and enabled. The product may not delete, rename,
  reset or rewrite `serverPool`. So on this fixture and build, an intended pool
  that shares the server's subnet has no observed path to serving a client.
  That is a product-design question for review, not a qualification defect.
- **Causal acquisition is not observable on this path.** A DHCP-mode client
  acquires autonomously once a server becomes available, so the typed
  `dhcpRun` met a client that already held a lease. The request is proven to
  have been dispatched once, and the replay is proven refused. What the
  request caused is not.
- **Table completion stays open.** Every observed end of rows was the same
  throw at the same index. Admitting it as a calibrated end would be a new
  decision predicate, which needs its own design delta, causal controls and
  review. No full state is reachable while `serverPool` serves: its capacity
  is 512, and the intended pool is never filled. This is why `Q3-FL-C2` was
  not run. Beyond the exhausted time ceiling, a two-user intended pool that is
  never served cannot discriminate one row from a full table.
- **Renewal.** Natural renewal is outside any reasonable horizon at a 1-day
  lease. Requested renewal has no typed contract.
- **Events.** M-DHCP-3 stays deferred. `DHCP_LEASE` is never promoted to
  VERIFIED, and the R-EVT-05 fallback stays active.
- **HTTP on DHCP clients stays blocked.** The product's DHCP prerequisite,
  a VERIFIED lease from the intended pool, is not established, and a native
  default address is not a substitute.
- **Retirement of a laboratory with campaign effects** raises Packet Tracer's
  save prompt. Graceful retirement of such a laboratory therefore needs an
  operator answer, or a separately reviewed and authorized dismissal step. The
  blank-lab retirement qualified by FASTLOOP does not cover it.

## Proposed operation-specific capability decisions, awaiting independent review

Nothing below is applied. Every catalog record stays UNKNOWN.

| Operation, 9.0.1.0858 / file channel | Proposal | Evidence |
| --- | --- | --- |
| `Server-PT:enable_server_dhcp`, `configure_server_dhcp_pool` (ensure-present of a pool with exclusions) | candidate for SUPPORTED as *configuration*, with the explicit limitation "stored configuration is not service" | M-DHCP-1: product read-back VERIFIED; setters dispatched once |
| `Server-PT:dhcp_server_state` read-back | candidate for SUPPORTED | M-DHCP-1 |
| `PC-PT:endpoint_dhcp_mode` reader and activation | candidate for SUPPORTED, with the limitation "activation is effectful: the client acquires autonomously once a server is available" | M-DHCP-5, M-DHCP-6 |
| `PC-PT:acquire_dhcp_lease` (typed `dhcpRun` under a claim) | keep UNKNOWN. Execute-once and replay refusal are demonstrated; the effect is not attributable | M-DHCP-6, M-DHCP-6-REPEAT |
| `PC-PT:dhcp_lease` read-back and `Server-PT:dhcp_lease_attributed` | keep UNKNOWN. Intended-pool attribution is unreachable while the native default serves the subnet | M-DHCP-6 |
| DHCP service as a product prerequisite for dependent services | NOT SUPPORTED on this design and build, pending a product decision about the native default | M-DHCP-6, M-DHCP-6-CAP |

## Stabilization and traceability, version 4

The measurements, the projection and the proposals of version 3 stand
unchanged. This section records what stabilization established and adds the
requirement-to-test and measurement map.

| Identity | Value |
| --- | --- |
| Executed checkpoint | `5df8d05ec89b9bb5042e1dd2a040c0eaad9890e8` (tree `3f1bc384c8bfe5b755839eba67e5b1b4dcddf603`), the only code any LIVE episode ran |
| Production code after it | `41802ca` alone. M-DHCP-6 now keeps the whole labelled client reading series as `client_readings`, and `test_every_client_reading_is_retained_with_its_label` protects it. No decision changed |
| Tests added at stabilization | `20b7b2e` (DF12) and `3dfd493` (DF14): test code and the Node stub only |
| Evidence commits | `eea238e` (episode 1 and its archive) and `651b8c7` (shorter archive paths, every byte unchanged) |
| Delivery | the commit that adds this section. A commit cannot name itself, so its SHA and its exact-SHA CI are reported with the delivery |

**What episode 1's record lacks.** The record predates `41802ca`. Its two
background readings, at offsets 67.4 s and 78.4 s, survive only as correlated
operation rows (`seq` 82 and 83), not as content. PC1's pre-request reading at
79.1 s is in the record, under M-DHCP-6's attribution, and it is the basis of
the autonomous-acquisition finding. Nothing reconstructs the missing content.

**Evidence integrity.** All 41 archived files match `MANIFEST.sha256`, and the
archived file set is exactly the manifest's. Each file is byte-identical to its
gitignored source: 24 lead files under
`pt-q-evidence/dhcp-fastloop-01/episode-0001/`, 16 store files under
`data/commissioning/SERVER-PT-DHCP-FASTLOOP-01/` and the qualification record
under `data/services/qualification/q3-fl-c1/`. A read-only `--ledger-status`
reports 123 operations and 28,059.3 s committed, no open episode and
−7,059.3 s of ordinary time left.

**Two acceptance criteria had no test.** Tracing DF1 to DF16 found them. Both
are now regressions through the real coordinator and the Node stub, and each
was proven causally RED. Every mutation was restored, and the tree was
byte-identical afterwards. No production code changed.

- DF12, *a changed lease string is not renewal.* The stub can return lease text
  that moves on every read. The unchanged and the changed case both stay
  INCONCLUSIVE, each with its own named cause, and no renewal is requested.
  Blinding the change detector, or concluding renewal on changed text, turns
  the changed case RED.
- DF14, *a persistence failure ends further experimental effects.* Each of the
  four Q3-FL boundaries that announce an effect (server address, client mode,
  E6 server and acquisition) loses its write in turn. The stub's own counters
  show that the announced effect and every later one were never applied, and
  that no `dhcpRun` was sent. The terminal reading and owned finalization
  still ran. Making one boundary ignore its lost write turns exactly that case
  RED.

**Requirement-to-test and measurement map.** Test files are under `tests/`;
"coordinator" is `test_q3_fastloop_coordinator.py`. Measurements are episode
1's.

| ID | Tests | LIVE measurement or evidence |
| --- | --- | --- |
| DF1 | `test_server_pt_dhcp_fastloop_campaign.py`: selection by identity and charter, per-charter ledger ceilings, another campaign's charter refused, an episode opened under its own campaign | ledger opening and closing records |
| DF2 | the same file: phase admitted at its checkpoint, protected tail never drawn, an unsettled phase charged at its grant, an admission naming only its attempt; `test_q3_fastloop_campaign_cli.py`: admit, settle and archive, an interrupted run stays charged | qualification admission and result: 123 operations, 220.4 s |
| DF3 | `test_q3_fastloop_campaign_cli.py`: an unpublished HEAD refused without authority, an authority for anything else waives nothing, every campaign fact refused before contact, stage and campaign mismatches refused | episode 1 ran at unpublished `5df8d05` under campaign authority |
| DF4 | the same file: another incarnation at the launched PID refused, every campaign fact refused before contact | `process-launch.json`, PID 47680 |
| DF5 | `test_server_pt_dhcp_fastloop_campaign.py`: the retirement-basis matrix and never forcing | the refused retirement attempt, `forced_retirement_not_authorized_by_campaign` |
| DF6 | `test_q3_fastloop_profile.py`, all six | stage `Q3-FL-C1`, ceiling 440 |
| DF7 | `test_dhcp_native_default_sequence.py`, all eight; coordinator: realignment then stability, an unreviewed movement stops, unchanged admitted, `serverPool` never written | M-DHCP-1, M-DHCP-1-FINAL |
| DF8 | `test_service_access_readiness_dhcp.py`, all three; coordinator: the forwarding worst case is the gate's cap, a refused group blocks exactly its dependent | FWD after 11 samples and 47 calls |
| DF9 | `test_dhcp_lease_evidence.py`: scan termination and calibration; coordinator: C2 discriminates one row from full | M-DHCP-2, INCONCLUSIVE |
| DF10 | `test_dhcp_lease_evidence.py`: exact text, calibrated absence, causality, native-default service, ambiguity, the wrong-MAC row; coordinator: C1 claim separation, activation before the enable, every reading retained | M-DHCP-4, M-DHCP-5, M-DHCP-6 |
| DF11 | `test_dhcp_lease_evidence.py`: the capacity-one negative cases; coordinator: an unfilled pool decides no negative | M-DHCP-6-CAP, INCONCLUSIVE |
| DF12 | coordinator: `test_a_changed_lease_string_is_never_a_renewal`, C1 timing, declared omissions; `test_q3_fastloop_profile.py`: declared omissions | M-DHCP-6-TIME, INCONCLUSIVE; M-DHCP-6-RENEW, omitted |
| DF13 | coordinator: C1 (one `dhcpRun` per client), a repeat that dispatches again is CONTRADICTED | M-DHCP-6-REPEAT |
| DF14 | coordinator: an unknown acquisition outcome stops later effects, an unreviewed movement stops, `test_an_unannounced_effect_is_never_applied_and_finalization_still_runs`; `test_service_qualification_coordinator.py`: persistence loss before and after an effect | no stop in episode 1; the terminal reading and finalization ran and restoration was proven |
| DF15 | `test_dhcp_lease_evidence.py::test_attribution_is_linear_in_clients_and_rows` and `test_service_access_readiness_dhcp.py::test_one_group_serves_every_client_of_a_switch_and_vlan`, each at 2, 20, 200 and 1000 clients | offline only; two clients ran natively |
| DF16 | `test_q3_fastloop_campaign_cli.py`: a campaign run archives its phase; `test_dhcp_native_default_lifecycle.py::test_product_dhcp_capabilities_remain_unknown` | the `dhcp-fl-01/` archive of 41 files; no catalog or capability file changed since `2a44b38` |
