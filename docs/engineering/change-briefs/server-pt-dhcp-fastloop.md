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
| M-DHCP-6 | measured, SUPPORTED_IN_SAMPLE for separation | Both clients were served by the **native default**. Each has an exact IP/MAC row in `serverPool` and no row in the intended pool, and the product read-backs are CONTRADICTED `address_outside_intended_allocation`. Each typed request was a known dispatch (`attempted=true`, correlated, no call error) | **causal acquisition by `dhcpRun`: not established.** Both clients already held their addresses before their own request. PC1's reading at 79.1 s, about 14 s after the enable at 65.0 s, shows its address; its prior scan was throw-terminated at zero rows, so no prior absence was calibrated. PC2's row first appears in the scan at 99.5 s, after PC1's request and before PC2's own at 102.6 s, so its acquisition is bounded only between 65.0 s and 99.5 s. Intended-pool attribution: not reached |
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
| Delivery | the last commit of this stabilization, which changes documentation only after `c60116e`. A commit cannot name itself, so its SHA and its exact-SHA CI are reported with the delivery |

**What episode 1's record lacks.** The record predates `41802ca`. Its two
background readings, at offsets 67.4 s and 78.4 s, survive only as correlated
operation rows (`seq` 82 and 83), not as content. PC1's pre-request reading at
79.1 s is in the record, under M-DHCP-6's attribution, and it is the basis of
the autonomous-acquisition finding. Nothing reconstructs the missing content.

**Independent review.** A Codex adversarial review of `5df8d05..c60116e`
reproduced one finding from the archived record. Version 3 said both clients
acquired within about 14 s of the enable, but that bound holds only for PC1.
PC2's first persisted evidence is its row in the scan at 99.5 s. The M-DHCP-6
row above and the services brief now state each client's own bound. The
record is unchanged. The review reported no other finding about the code, the
stub, the regressions or this section.

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

## Delegated DHCP autonomy, version 5: active design delta

**Authority and starting state.** The operator's execution mandate is
`C:\Users\Andres\Downloads\ServerPT_DHCP_Delegated_Autonomy_Mandate.md`, SHA-256
`3bb343ef80d75c0ebf37204c8fbfd57da23eea4e5de57a7227ee1ded2e2d1ea2`.
This checkout is `feature/server-pt-goal-foundations` at
`a921a688a7f7103db2cff3915172d812a8e26644` (tree
`d8ae5896e816d5710877be3dc2f558c6a54a713d`), clean at inspection.
`cisco/main` resolves to `6263344e31ba3b0de6539d652f2cd06fc73a3562`.
Risk stays **L**: changing effect admission, pool authority, evidence and LIVE
behavior. This section is the active change brief; earlier episode records and
their interpretation above remain historical.

**Problem and outcome.** Episode 1 established that the native `serverPool`
served both clients outside the requested `192.0.2.100` one-user allocation.
Both addresses preceded their respective explicit requests. The product must
realize the intent's range, mask, exclusions, gateway, DNS and capacity through
an observed effective Server-PT pool, attribute each selected client's coherent
configuration to it, then admit dependent HTTP through the registered product
path. Existing static HTTP and offline scale behavior remain valid.

**Scope.** Reuse the current E5/E6 compiler, typed runtime, readiness gate,
claim store, campaign ledger, lifecycle automation and evidence archive. A
dedicated versioned probe may test documented native-pool setters or removal on
an owned disposable server, bracketing each effect with complete physical pool
inventory and readback. It may not issue arbitrary operator-supplied source.
The implementation may select a verified effective pool and may treat a
background-acquired lease as a state prerequisite. It must preserve a logical
requested pool identity separately from its physical binding and refuse an
explicit pool-name requirement if the binding cannot honor it. No router DHCP,
hidden API, static client injection, global capability override, main merge,
or rewrite of episode 1 is in scope.

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| DA1 | A new prospective mission authority uses the existing ledger and lifecycle controls | Its charter digest, source SHA/tree, profile, episode, attempt, instance, nonce, effects and finite allocation are checked before contact; old exhausted grants stay closed |
| DA2 | Select an effective pool from evidence, not a name or subnet coincidence | Complete pre/post inventory and exact pool fields distinguish successful native management, no-op, throw, regeneration and overlap; an unsupported route stops before clients |
| DA3 | Preserve the requested address policy | Effective range, mask, exclusions, gateway, DNS and capacity match the compiled requirement; an address outside the allocation contradicts it |
| DA4 | Separate usable state from request causality | A fresh client address/mask, selected interface and MAC, acceptable policy, and exact effective-pool lease row establish state; no `dhcpRun` causality or renewal is inferred from that state |
| DA5 | Admit dependent HTTP through the maintained path | E5/E6 prerequisite and readiness verdicts are stored, then each selected DHCP client makes its first HTTP-by-IP request through the registered four-argument MCP route, with durable reload agreement |
| DA6 | Preserve scale and failure containment | Real affected-flow tests cover 2/20/200/1000 clients offline with shared readiness and indexed lease scans; one client's uncertainty cannot authorize another or repeat an uncertain effect |
| DA7 | Preserve laboratory and evidence integrity | Each LIVE episode has finite arithmetic, primary observations, exact identities, cleanup or quarantine, immutable artifacts and a hash manifest; an uncertain effect blocks dependents |

**Decision sequence.** The first experiment is the smallest discriminating
native-pool probe on a fresh owned server: read full inventory, apply one
documented setter to `serverPool`, read back, then observe whether a known
server-address reapplication regenerates it. If a setter is ineffective,
investigate documented `removePool` on a new disposable instance; do not chain
an uncertain mutation. Choose the least complex route whose physical readback
and lease attribution establish the intent. A separately named pool cannot be
called effective while the overlapping native pool actually serves. C2 is
deferred until it can distinguish a real outcome. A positive exact lease row
does not need an end-of-table claim; negative and renewal claims retain their
separate evidence rules.

**Architecture and invariants.** Domain code owns the pool-selection and
usable-lease predicates. Application orchestration derives subjects from the
compiled intent, gates each effect, and persists the logical-to-physical
binding. Infrastructure owns only fixed documented API calls and readbacks.
The existing MCP signature is unchanged. A candidate capability is private to
the experiment. No missing identity, unobserved field, arbitrary exception,
late read, contradictory row, foreign claim or unknown effect can authorize a
dependent action. R-EVT-05 remains unless separately qualified. Every new
source value entering generated JavaScript uses JSON serialization.

**Verification design.** Start with causal RED tests for the native-pool
decision and state prerequisite through the real runtime and composition;
include no-op, throw, regeneration, competing row, wrong MAC, out-of-range,
missing DNS/gateway, unknown effect and static-client positive controls. Run
focused tests, affected tests, then the full suite and repository gates on the
final candidate. The first LIVE probe is system evidence for build 9.0.1.0858;
the later maintained-path DHCP plus HTTP run is acceptance evidence. Offline
tests do not qualify native behavior. Exact-delivery CI and an independent
review follow the clean delivery commit; reviewer approval remains separate.

**Prospective resource design.** The new mission ledger is separate from the
closed `SERVER-PT-DHCP-FASTLOOP-01` ledger. Its initial finite ceiling is
10,000 operations and 14,400 active seconds, with 1,000 operations and 600 s
protected for finalization. The forecast is: native probes 600 operations /
1,800 s, candidate behavior 1,200 / 3,000, DHCP plus HTTP 1,600 / 3,600,
repeat and representative scale 1,800 / 2,400, contingency 3,800 / 3,000,
and the protected tail 1,000 / 600. Each episode receives its own lower
allocation computed from actual calls and waits before it opens. Idle lab
residence is charged and retirement is immediate after its work.

**Pre-LIVE design refinements.** The first `Q3-NATIVE-PROBE` stage tests only
whether one documented `setStartIp` call changes the physical `serverPool`
immediately after the already reviewed server-address realignment. Its result
cannot qualify persistence, reapplication, service, or the full requested
policy. A separate discriminating episode must test reapplication before any
native-management strategy is selected. The assessment compares the complete
typed pool inventory and process envelope before/after the call; a new pool,
changed enable state, no-op, exception or partial read is never clean support.
The direct LIVE use-case entry requires this stage's campaign authority even
when the checkout is published. Retirement must hold the same shared writer
claim as qualification, without consuming a second attempt marker. Its exact
owned save prompt receives an identified `No` response only after process,
window, prompt and button revalidation; otherwise the lab is quarantined and
the uncertainty is recorded. These controls respond to the separate pre-LIVE
adversarial review, not to an observed native capability.

## Delegated LIVE episode 1 and size-probe design delta, version 6

Episode 1 ran the maintained `Q3-NATIVE-PROBE` at clean commit
`c76ab02bc177ba0e0c60f481d009432fdb886485` (tree
`79d7025419191bf0ecbe7f1c376f81aa2af605d2`), Packet Tracer
9.0.1.0858, file channel, attempt `e61273ccccbf4492a33d5e02798facfb`,
instance `6ff7bc8aed7a4187b8e98187b74473e8`. The opened ledger granted
120 operations / 900 seconds. The original qualification record is
`q3-native-probe-2026-09-25T20-36-44Z-84514155.json`, SHA-256
`1dcf4d95f2c8d20dc22f67950b86c0bb4c0b4dac3e828d88ae4a2d31494fa9c1`.
Its source bytes and the closed ledger, launch, exit and lead files are in
[`dhcp-autonomy-02/e1`](../../reference/server-pt/evidence/dhcp-autonomy-02/e1/README.md)
under a 38-entry SHA-256 manifest. Every archived source copy matched its
original at archive time.

The documented `setStartIp("192.0.2.100")` call was attempted once, returned
without a call error and read back `start=192.0.2.100`. It also changed the
same `serverPool` row's `end` from `192.0.3.255` to `192.0.2.255` and `max`
from 512 to 156. The process stayed disabled; the complete pool inventory
remained one row. This is a **known coupled mutation**, so M-NATIVE-START is
CONTRADICTED against its single-field hypothesis. It does not realize the
requested one-user allocation. The final read and fixture restoration were
observed. The identified owned save prompt's `No` was invoked and PID exit,
zero Packet Tracer processes, an empty mailbox and claim release were
observed. The closed ledger charged 34 operations and 347.474369 seconds.
No client serving, reapplication, requested gateway/DNS/exclusions, dependent
HTTP, renewal or capacity behavior was measured.

**Next discriminating question.** A new versioned `Q3-NATIVE-SIZE` stage on a
fresh owned lab will reproduce only the exact build-scoped coupled start
transition above, then call documented `setMaxUsers(1)` once while DHCP is
disabled. Each effect has its own write-ahead boundary and full before/after
inventory and process envelope. The second measurement is positive only if
`serverPool` reads back the requested start and end as `192.0.2.100` and
capacity 1, with no other field, pool or process change. A no-op, error,
regeneration or other coupled movement is recorded as such and stops further
effects. This stage neither enables DHCP nor contacts clients. If successful,
later distinct episodes must establish gateway, DNS, exclusions, stability
under reapplication and actual serving before the product can bind to the
native pool. The former episode and its classification are not rewritten.

The new stage reuses the current qualification runner, charter/ledger,
exclusive claim, fixture lifecycle and fixed file transport. It adds no MCP
argument, generic script route or catalog promotion. Unit assessment tests
cover the exact repeated start transition and max result; a Node integration
test runs the generated calls through the real coordinator and retained
record, including no-op/throw and unexpected-pool controls. The next LIVE
episode remains bounded by a fresh allocation and its exact committed source.

**Windows quality-gate command bound.** At 218 Ruff-gated Python files, the
provisional gate failed before Ruff started with Windows `CreateProcess`
`WinError 206`: its current `run_ruff` passes every absolute file path in one
command. This is a tooling limit exposed by the required delta, not a lint
violation or permission to skip files. The gate will partition the *same*
selected paths into bounded command lines, run both lint and format over
every partition, and return failure if any partition fails. A focused RED
regression proves complete path coverage and preserved failure status.

**Immutable raw-source archive boundary.** The quality gate's newly complete
Windows run also identified the two original Python launch scripts archived
under `dhcp-autonomy-02/e1/lead/`. They are raw episode evidence, copied
byte-for-byte and committed with `-text -diff`, not maintained Python source.
Ruff would require changing their bytes and invalidate the immutable evidence
manifest. The gate will register only those two exact paths and SHA-256 values,
verify the pinned 38-file manifest digest and every archived byte and path,
then report those two files as immutable-evidence exempt. Missing, added or
changed archive bytes fail the gate; every other authored or unverifiable
Python path remains Ruff-gated. This evidence classification is separate from
the mechanical-migration exemption and grants no general path ignore.

**Offline checkpoint before a second LIVE episode.** The design delta began
from clean `a9207513244d7447597ea0db42693fd0509e6e4e` (tree
`16d788998ed239e0b79fa2cfc582b9c562aa3c77`). Causal RED controls
exposed and closed three pre-LIVE defects: a start no-op reaching the capacity
setter, an incomplete or enabled baseline reaching E5, and a path alias or
deleted archive escaping the evidence gate. The affected regression group
finished `357 passed, 1 skipped`; the provisional `cisco/main` quality gate
reported 219 Ruff-gated Python files, two exact immutable-evidence files,
and zero mechanical exemptions. These are offline results; they establish
neither native `setMaxUsers` behavior nor product DHCP support.

## Delegated LIVE episode 2 and policy-probe design delta, version 7

Episode 2 ran `Q3-NATIVE-SIZE` from clean commit
`fcafebd2b4638c69b984a9df529af177f0b9b34e` (tree
`853c51cc0c2c5cb224b1d22184983e34b506569e`), build 9.0.1.0858,
file channel, attempt `42adc4770e544d1e9705478faca0f058` and instance
`49756272b9414810ac5daaf9d84840bf`. The original record is
`q3-native-size-2026-09-25T21-20-06Z-d431ff46.json`, SHA-256
`771cd15b5807244b1642c6cae12075b5c35317417dce5d145d946ba35ab5f6b3`.
The complete original record, the cumulative store snapshot and every lead
file are archived under
[`dhcp-autonomy-02/e2`](../../reference/server-pt/evidence/dhcp-autonomy-02/e2/README.md).
The first launch record was refused on a changing OS main-window title and
recovered by a fresh observation of the same PID/incarnation. One
qualification argv incorrectly named closed episode 1 and was refused before
contact. Both attempts are retained; only `08b` executed this stage.

`setStartIp` reproduced episode 1's exact coupled transition. After it,
`setMaxUsers(1)` returned without error and the single physical `serverPool`
read back `start=end=192.0.2.100`, `max=1`, network `192.0.2.0` and mask
`255.255.255.0`. The process remained disabled. This is a build-scoped
**SUPPORTED_IN_SAMPLE** range/capacity result, not a DHCP service or product
capability. Gateway and DNS still read `0.0.0.0`; exclusions were not read.
The run used 36 operations, proved fixture restoration, and retired its
owned PID after an exact save-prompt `No`. The census showed no process,
pending mailbox file or claim lock. The closed ledger charged 36 operations
and 305.36164 seconds; cumulative totals are 70 operations and 652.836009
seconds. No client acquisition, reapplication, renewal or HTTP was measured.

**Next discriminating question.** The compiled one-user requirement contains
gateway `192.0.2.1`, DNS `192.0.2.10`, and two singleton exclusions for those
addresses. A new versioned `Q3-NATIVE-POLICY` stage will repeat the two exact
known pool transitions on a fresh disabled server, then apply documented
`setDefaultRouter`, `setDnsServerIp` and `addExcludedAddress` operations as
distinct interventions. The values come from the compiled requirement.
Each call has a write-ahead boundary and a fresh full policy read including
physical pool identity, range/mask/capacity, process state and exclusions.
Only the intended field/range change may authorize the next effect. Any
unobservable result, no-op, overlapping new pool or other movement stops the
sequence. The stage does not enable DHCP or activate a client. A later distinct
episode must test reapplication/persistence and actual serving before the
product may choose the native pool.

The profile reuses the campaign, source/process gates, counted file transport
and finalizer. It adds fixed typed probes rather than a general script route.
The provisional ceiling is 160 operations and 900 stage seconds including a
300-second finalization reserve; the next episode will separately budget
launch and retirement. RED controls will cover each effect through the Node
engine/coordinator, plus wrong pool, unexpected exclusion, no-op, throw and
unknown-result cases. Full product and scale verification remain pending.

## Native policy result and serving design delta, version 8

Episode 3 ran `Q3-NATIVE-POLICY` from clean commit
`76a60a8d259e1f2cee571a446664ef3cb1a2d6bc` (tree
`190f53c41ee0a930be08a3253633fc706eb72f23`), build 9.0.1.0858,
attempt `3abd3d33dfeb48e0bbd689c314418ed4`, instance
`6f66d1d16a3d49fbbbfff96829dfcde4`, file channel. The original
qualification record SHA-256 is
`3222546e0497fae88139ad0cd6fbc20dff6223118cb1e494f0bba00e42020f01`;
the complete 74-entry archive is
[`dhcp-autonomy-02/e3`](../../reference/server-pt/evidence/dhcp-autonomy-02/e3/README.md).
The first launch record was refused on a changing window title and retained;
the same process incarnation was revalidated and recorded before contact.

The single physical disabled `serverPool` read back the compiled one-user
range `192.0.2.100-192.0.2.100`, `192.0.2.0/24`, gateway
`192.0.2.1`, DNS `192.0.2.10`, capacity 1 and singleton exclusions for
`.1` and `.10`. The repeated start, size, gateway, DNS, exclusions and final
inventory measurements were each **SUPPORTED_IN_SAMPLE**. Each policy call
was bracketed by complete process/pool/exclusion reads; no second named pool
was created. This establishes stored disabled-server policy on this build,
not serving, reapplication, renewal, or product capability. The run used 45
operations and proved fixture restoration. The maintained retirement observed
the owned PID exit; no save-prompt button was sent because a fresh document
check had changed. Final process/mailbox/claim census was empty. Episode 3
closed at 45 operations and 258.04685 seconds, cumulative 115 operations and
910.882859 seconds.

**Next discriminating question.** A fresh bounded `Q3-NATIVE-STABILITY`
profile will first repeat the exact disabled native policy under the same
complete guards. It will then reapply the compiled E5 static server-address
action as a distinct product intervention and compare complete physical
pool/process/exclusion inventories before and after. The expected result is
the identical singleton `serverPool` policy, with no new pool or exclusion,
and a disabled process. A retained `already_satisfied` product decision is
recorded distinctly from a newly dispatched setter; a skipped action never
proves the setter itself is idempotent. Unknown E5 outcome, changed policy,
enabled process or missing inventory stops the episode. The profile will not
activate clients or call `dhcpRun` or HTTP. Restart/reload persistence, actual
serving and the maintained service/HTTP path remain separate subsequent
questions; this episode does not promote the global DHCP catalog.

The current E5 generator catches a JavaScript setter exception inside its
fire-and-forget call. A positive reapplication interval establishes retained
physical state, not that the native setter succeeded or is idempotent. The
record retains the product action row as reported and carries that explicit
limitation; neither an `APPLIED` label nor an unchanged post-read removes it.

E5's endpoint runtime reports a boolean batch result while the counted
transport retains the separate dispatch fact. A `False` or exception after a
queued command may leave the effect unknown even if the product action row
says `FAILED`. The stability coordinator will inspect only the counted
operations of this E5 intervention; any `ACCEPTANCE_UNKNOWN` makes the
measurement `INCONCLUSIVE` with `outcome_unknown=True`. A later readback
cannot turn earlier dispatch into known acceptance.

The stability profile will reuse the compiled E5 action, application result,
campaign ledger, counted file transport and owned fixture finalizer. It adds
one full policy read before and after reapplication and an exact interval
assessment. RED tests cover a repeated no-op, regeneration, overlap, throw,
unknown dispatch, and the unchanged positive control. The risk remains L.
Its finite operation/time allocation and reserve are computed before LIVE,
followed by focused/affected verification and independent pre-LIVE review.

## E5 stability result and native serving design delta, version 9

Episode 4 ran `Q3-NATIVE-STABILITY` from clean commit
`fee6a152f64fb48350127d3c0d8f124bf885ba84` (tree
`3b8b858440acb4c871d4c113bac53d6eb712ba6b`), build 9.0.1.0858,
attempt `2242018879574929b400839cc5f60059`, instance
`9c7bce4bbf1849f0ade10e82b825090e`, file channel. The original
qualification record SHA-256 is
`b5ed514137c88e0fd9230bfd36d06e5452109935d15b27988ee30b19853493c8`;
its complete 90-entry archive is
[`dhcp-autonomy-02/e4`](../../reference/server-pt/evidence/dhcp-autonomy-02/e4/README.md).
The first launch record was refused during a changing window title and
retained, then the same PID/incarnation was revalidated and recorded.

The compiled server static-address action was reapplied by product E5 after
the exact native policy was established. The full before/after reads matched:
one disabled `serverPool` with `192.0.2.100-192.0.2.100`, network
`192.0.2.0/24`, gateway `.1`, DNS `.10`, capacity 1 and both singleton
exclusions. The product action row reported `APPLIED`, with no counted
acceptance-unknown dispatch. This is **SUPPORTED_IN_SAMPLE** for retained
physical state under one E5 reapplication; the generated JavaScript catches
native setter exceptions, so setter success/idempotence is unproven. The
run used 48 operations and proved fixture restoration. The exact owned
save prompt was answered `No`; the process exited and final
process/mailbox/claim census was empty. Episode 4 closed at 48 operations
and 221.202394 seconds, cumulative 163 operations and 1132.085253 seconds.

**Next discriminating question.** A fresh `Q3-NATIVE-SERVE` profile will
repeat the measured disabled policy and E5 stability gate, then enable only
the exact Server-PT DHCP process behind an in-evaluation complete policy
guard. It will immediately read the entire physical policy and stop on drift
or unknown enable. Once an enabled exact policy is established, one compiled
owned client will enter DHCP mode through a fixed diagnostic call using the
same documented `configurePcIp` signature as product E5. Its script checks
the complete enabled physical pool policy and the client's mode in the same
evaluation that could activate the client. The product E5 fire-and-forget
batch has no such admission guard and remains for a later product correction.
A fresh full policy read also brackets the call; any unknown mode dispatch
stops. The stage will then
take bounded repeated client and physical `serverPool` lease reads without
calling `dhcpRun`, reset, ping, DNS or HTTP. The separately named logical
pool is also read as an absence/overlap control. A positive serving result
requires two consecutive fresh observations of DHCP mode, the exact usable
address/mask, stable MAC, and a matching IP/MAC/port row in the physical
native pool. A lease-time string, an IP alone or a named-pool row is not
sufficient. Positive row attribution does not require proving a table end;
client-side autonomous acquisition is distinguished from explicit request
causality. The fixture's second client stays inactive.

The serving profile will reuse the governed fixture, compiled E5 client action,
counted file transport, typed client and lease readers, and finalizer. A
fixed native enable probe performs one documented setter only after its own
complete policy precondition; this remains a diagnostic until the product's
compiled enable/pool ordering and logical-to-physical binding are corrected.
An unknown or contradicted effect stops dependents and retains terminal
state. RED tests cover missing/changed policy, lost enable or mode result,
autonomous acquisition from a wrong pool, wrong MAC/port and a matching
native row, plus unchanged static-client HTTP and 2/20/200/1000 offline
scale. Risk remains L; the operation schedule and reserve are bounded before
LIVE and reviewed independently.

The mode procedure reserves nine bridge calls: up to four forwarding
readiness reads, then one client read, one full policy read, the guarded mode
call, one client read and one full policy read. The serving window reserves
39 calls for thirteen client/lease/policy triples, with at most twelve
ten-second waits. The profile ceiling is 260 operations and 1800 seconds,
including a protected 300-second finalization reserve.

The one-user pool makes the second fixture client a competing consumer even
though this stage never activates it. Before server enable, both compiled
client ports must be freshly observed with DHCP mode off and no assigned
address or mask. The native enable probe repeats those checks inside the exact
evaluation that could call `setEnable(true)`. A client that becomes active
between the pre-read and dispatch therefore withholds server enable. During
serving samples PC2 must stay off and unassigned; any departure stops native
attribution. The bounded enable procedure adds one aggregate client read,
so its three planned calls remain sufficient.

The separately named logical-pool scan is an independent overlap control.
If that entry is unreadable, the bounded serving window remains
`INCONCLUSIVE` even when client and native-row observations are positive;
absence is never inferred from a missing scan entry.
The existing lease-scan classifier also treated a `getPool` exception as
observed pool absence when the probe returned `found=false` with a nonempty
error. That false absence would admit a positive native attribution. It will
instead mark that pool entry unobserved and carry `pool_lookup_error`; the
separate `found=false,error=""` positive absence control remains valid.
For a found pool, the returned physical `getDhcpPoolName()` text must also
equal the requested scan name. An exact IP/MAC row reached through a
misidentified object cannot be attributed to `serverPool`; a blank or
different returned name marks the scan unobserved and cannot support serving.
At the serving window's end, a still-unassigned client with complete reads
is a bounded negative. A client already at the intended address without a
qualified native row or readable capacity is `INCONCLUSIVE`, including a
throw-terminated native scan; table absence is not invented. A coherent
native scan with more lease rows than the one-user capacity is instead a
direct `CONTRADICTED` over-capacity observation.
An observed intended address with a different client netmask is a direct
contradiction of usable configuration, not a timeout or mere absence.

The terminal `M-NATIVE-FINAL` measures whether the final physical inventory
was completely observed. The serving stage may end with DHCP enabled, so its
terminal admission accepts either typed boolean process state while still
requiring the exact subject, singleton physical pool, and complete exclusion
count/list. Earlier disabled-policy stages retain their disabled terminal
predicate. Terminal support never substitutes for the separate serving
measurement or proves the policy fields are correct.

## Native serving result and product-path design delta, version 10

Episode 5 ran `Q3-NATIVE-SERVE` from clean commit
`04f5337eef67f0c850e057537ce80757e3aa73b1` (tree
`b0a0d2e0e34b4efd7892ee52aff6d033bfc16ecc`), build 9.0.1.0858,
attempt `66645cff81524e8f93d05295ddcd075f`, instance
`6d045ac7212f481c91ccd97a6dc621b5`, file channel. The original
qualification record SHA-256 is
`83e01280787c46b422c1339c2d6b7e8bce58a44aee6ac67804b3bf1edb775149`;
the complete 103-entry archive is
[`dhcp-autonomy-02/e5`](../../reference/server-pt/evidence/dhcp-autonomy-02/e5/README.md).
The first owned launch was recorded without a retry. The guarded server
enable and PC1 DHCP-mode effects were followed by two fresh samples 11.140
seconds apart: PC1 was DHCP-on with `192.0.2.100/24`, stable MAC
`0004.9AB0.A2B2`, and the exact IP/MAC/`FastEthernet0` row in the one-user
physical `serverPool`. The separately named logical pool was observed
absent, the complete requested server policy persisted, and PC2 was
DHCP-off/unassigned. No explicit `dhcpRun`, ping, DNS or HTTP call was made.
All required native serving measurements were **SUPPORTED_IN_SAMPLE** for
this disposable fixture and exact build. The run used 63 operations, proved
fixture restoration, retired its owned PID via exact save-prompt `No`, and
left no process/mailbox/claim residue. Episode 5 closed at 63 operations
and 217.331687 seconds; cumulative use is 226 operations and 1349.41694
seconds.

**Product strategy.** Compose a new acceptance intent with one explicitly
selected DHCP and HTTP client (PC1), capacity one, and no explicit pool name.
The earlier Q3 fixture explicitly named `MCP_E6Q_DHCP`; that request is not
silently rewritten. Keep a derived logical pool label in the plan and an
explicit `effective_pool_name="serverPool"` backend binding in the typed
pool action, verification expectations and durable authority record. The
binding is admitted only for the measured build, model, interface and
one-user policy under a reviewed evidence identity. Named-pool plans and
other builds retain their existing behavior and UNKNOWN support.

The E5 client-mode effect currently precedes E6. For the native candidate,
it must check the owned disabled Server-PT process and both exact client
port preconditions inside the same evaluation that can activate mode.
Product E6 then configures the sole physical native pool while disabled,
with a complete read after each measured setter transition and a full
policy verification before process enable. The enable action depends on
that verified pool; no second named pool is created. A partial, unknown or
contradictory setter result stops later effects. The product state-based
DHCP mode compiles no `AcquireDhcpLease` and makes per-client `DHCP_LEASE`
required: two fresh stable client-mode/address/mask/MAC readings must join
an exact IP/MAC/port row in the effective pool and the complete requested
server policy. A positive row does not require table-end proof. Explicit
`dhcpRun` remains a separate causal action and stays UNKNOWN in the exact
candidate capability binding.

The existing service scheduler must stage that required lease state before
PC1 HTTP effects or HTTP verification. It must continue to withhold HTTP
for missing, foreign, malformed, unstable or unobservable lease evidence.
The public four-argument MCP product route is the acceptance entrypoint;
its HTTP check is the cold first request by IP, with no ping/DNS/warm-up or
static address injection. The one-client LIVE fixture locates the cause.
The maintained 2/20/200/1000-client offline scale route must keep grouped
physical-pool reads and per-client outcomes; no native thousand-client
capacity claim follows from offline tests.

Risk remains L. RED controls will cover exact client selection and PC2
exclusion, explicit-name refusal, native pool/enable order, in-evaluation
guards, unknown effects, joined lease state and HTTP dependency, static
client HTTP positives, and scale. The next LIVE product episode is admitted
only after focused/affected verification and independent adversarial review,
with a new clean SHA and finite campaign allocation. Product acceptance,
restart/renewal and final integrated capability promotion remain separate
from this already measured diagnostic result.

**Backend authority correction.** The initial candidate placed
`backend_binding=native_default` in the input-facing DHCP pool requirement.
That would let a public intent request a backend strategy directly. Remove
that field. An unnamed `state_only` DHCP request remains only a logical
requirement; the compiler selects physical `serverPool` exclusively when the
current exact-build capability snapshot contains the reviewed native-binding
operation record. This marker has recorded-run provenance and the episode-5
build/SHA/channel/run identity. The default catalog has no such marker until
product qualification and reviewed feature-branch registration. An explicit
different pool name still refuses the native strategy.

The selected E5 client action carries the compiler's exact inactive PC2
name/interface binding as well as the server binding. Its correlated
same-evaluation guard checks PC2 DHCP mode off and IP/mask unassigned before
it can change PC1. A PC2 activation at the dispatch boundary therefore
reports a refused PC1 effect, and the later E6 enable guard checks both
clients again. The client action cannot use a missing inactive binding in
this one-user candidate.

The required state-only lease verification also re-reads the compiled
inactive PC2 port on each sample after server enable, with DHCP mode off and
IP/mask unassigned. The E5/E6 pre-effect guards cannot stand in for this
later observation; a PC2 activation after enable prevents lease VERIFIED
and therefore withholds the dependent HTTP request.

The native-binding marker authorizes only the measured one-user policy.
After allocation derivation, the service compiler rejects any different
network/mask, gateway, DNS, `.100-.100` window or two singleton exclusions
before E5 begins. E6 runtime retains its own exact pre-effect check; the
compiler check prevents a selected client's E5 mode from being changed for
an intent that E6 could never implement.

**Product qualification boundary.** Add `Q3-NATIVE-PRODUCT` as a finite
experimental stage in the DHCP autonomy campaign. Its owned Server-PT,
two PCs and IE-2000 links match the composed reference manifest exactly.
The IE-2000 switch ports use the already recorded exact-build backend
inventory (`FastEthernet1/x`) for this stage; the declared `0/x` catalog
is not silently treated as a backend observation. The stage supplies the
manifest-directed four-device inventory to the maintained A1-E6 product
entry without enumerating the whole workspace. It records the product run
and accepts only overall VERIFIED plus required DHCP lease and HTTP fetch
VERIFIED. An independent terminal reading and fixture restoration still
occur on a failed product result. The private capability snapshot is
candidate authority for this episode, not default catalog promotion.

**Episode 6 runtime-composition correction.** The first maintained product
LIVE attempt at `7e06fdc` stopped at E5 VLAN. Its qualification runtime's
internal inventory callback was `_no_inventory`; the outer manifest-directed
wrapper returned four targets for product admission, but the inner E5 setter
still called `_no_inventory`, reported `session_failed` and left effect
uncertain. No E6 DHCP or HTTP effect ran. The terminal reading and fixture
restoration completed, and the owned process was retired. The product record
also exposed a persistence-location defect: writing under the checkout root
made the source dirty and initially blocked retirement; the original bytes
were preserved externally before the clean-source retry.

The correction belongs in the qualification runtime composition. Supply
the already compiled and fixture-verified four-target inventory to both
inner E5 and E6 runtimes for this one product stage. The ordinary diagnostic
runtimes keep their workspace-enumeration refusal. Persist the product run
under ignored sibling `data/services/product-qualification`, then archive its bytes
with the episode. Focused tests must verify both inner runtimes index exactly
the fixture inventory and ordinary diagnostics still reject workspace
enumeration. The sibling location keeps product JSON outside the
qualification store's recursive attempt-uniqueness scan. This is a
new candidate SHA and episode; episode 6 is immutable negative evidence.

**Suite drift correction (S).** Exact-SHA CI run 36211546830 at `27ee68c`
failed three offline tests on Ubuntu; CI was last green at `a921a68`, and no
full suite ran on the six commits between. The campaign authority test still
expected three campaigns, so it now names `SERVER-PT-DHCP-AUTONOMOUS-02` and
pins its fixed identity against the mandate hash rather than the
implementation. The namespace inventory flagged episode 1's archived launch
preflight, whose inert `"src.packet_tracer_mcp" in sys.modules` probe is
isolation evidence; it gains a reviewed retained-reference entry and the
archive bytes are unchanged. No runtime, LIVE or product behavior changes.

## Pre-episode-7 review corrections, version 11

**Windows long paths (S).** The same CI run failed two more tests on
Windows only: episode archive paths reach 157 characters, and a temp copy
under the runner's pytest root overflows MAX_PATH, which Git for Windows
refuses without `core.longpaths`. The governed-root test clones with that
setting persisted in the new repository, and the immutable-evidence test
enables it in its temp repository; the archives stay byte-identical. A
local run with CI's 69-character basetemp reproduced both failures and now
passes. Touching the governed-root test brought it under Ruff (import
order, two docstrings, formatting).

**Independent review before LIVE.** No retained record showed the claimed
review of `27ee68c`, so a fresh Codex adversarial review covered
`210e4e9..33f1bbf`. It returned two high findings.

The product record was outside the campaign archive: only the
qualification record was registered, so deleting or changing the product
JSON after a VERIFIED run left `verify_index()` passing. This is accepted
and corrected in the owning finalization block. When the qualification
record's `M-NATIVE-PRODUCT` facts name a product record, it is registered
as external source `product-record`, so the index rehashes it thereafter.
A follow-up review of that correction found an older gap in the same
block: a status whose JSON was written but whose digest write failed, or a
failed qualification-record registration, only appended a finding, so the
CLI could exit 0 with an unloadable status. Both records are now sealed
before the status is written, each independently, and any sealing or
status-write failure stops the phase with a named finding. The CLI exits 0
only when the use case completed, the phase status is not `stopped`, the
status reloads under its digest, every cited record is registered, and
the index verifies. The offline harness now writes product records to
production's `data/services/product-qualification` location. Regressions
prove that tampering or deletion fails the index, an unsealable product
record fails closed, and a failed status digest write never exits 0 while
both records stay sealed for recovery.

The second finding is that injected fixture inventory resolves names in
whichever receiver consumes a command, and a replacement receiver in the
unfenced interval could hold a same-named device. The code confirms that
every product dispatch still passes the ledger's per-call live-authority
guard, but that guard is local: `effect_guard` already declares that no
dispatcher carries a receiver-verified session token, and every
diagnostic record since episode 1 carries that limitation. The delta did
not widen it. An in-band fence would redesign every dispatcher and the
Script Engine receiver, outside Server-PT DHCP. Episode 7 proceeds under
the existing declared limitation, with verified exclusivity, one writer,
the per-dispatch guard, and campaign-unique `Q3-DEFAULT-*` names that a
foreign document would not resolve. The operator is asked not to open
Packet Tracer during the episode.

A third review of the status-write correction found that a status JSON
written without its digest leaves no governed retirement basis for a
completed run. That is older than this change, fails closed (retirement
refuses, so the lab is quarantined rather than touched) and needs a
local-disk fault between two small writes. A recovery path that adopts a
status without its digest would weaken evidence, so it is a separate
offline change and is recorded in episode 7's interpretation limit.

## Episode 7 result and access-readiness design delta, version 12

Episode 7 ran `Q3-NATIVE-PRODUCT` at `81af939` (tree `6c9aabb`), attempt
`bd94e8f5316748819310a0ef0983c995`; the archive is
[`dhcp-autonomy-02/e7`](../../reference/server-pt/evidence/dhcp-autonomy-02/e7/README.md).
Both inner runtimes indexed the fixture inventory and the maintained
product ran E5 and E6. The required `DHCP_LEASE` check for PC1 was
VERIFIED at claim level `attributed_to_effective_server_pool` with fresh
evidence, which is the first product-path verification of the native
`serverPool` lease. HTTP was withheld and never dispatched. The access
readiness group for the IE-2000, VLAN 10, `Fa1/1` and `Fa1/3` took one
complete sample showing both ports in STP `LIS`; that sample cost 11
channel calls and about 19 s, because `show spanning-tree` paginates, and
the next sample fell after the 30-second wall-clock group window. The
product withheld the request as designed. Episode 7 used 78 operations and
342.694246 seconds; restoration, retirement and sealing were clean.

**Cause.** PVST timers run on Packet Tracer's simulation clock. The
retained measurement behind `simulation_time_convergence.py` is 0.53 to
0.59 simulated seconds per wall second under load, and the retained
`show spanning-tree` reports a 15-second forward delay. An access port
that E5 moves into a VLAN needs up to two forward delays (listening, then
learning), up to 30 simulated seconds or roughly 55 wall seconds under
load, before it forwards. The neutral access observer's single 30-second
wall window, at about 19 seconds per complete sample, cannot watch that
sequence finish. On a fresh lab the product reaches HTTP soon after E5, so
this is a product-path defect in the readiness design, not an artifact of
the qualification stage. Trunk and Voice already met the same fact and use
the reviewed `BoundedPvstLearningExtension`, which spends one bounded
window on simulation time. That contract grants only when every pending
port is already in `LRN`; the neutral access observer was deliberately
built without it.

**Decision.** Give the neutral access observer one protocol-sized
extension, measured on Packet Tracer's simulation clock, when its
wall-clock window ends on transitional STP evidence. The admission rule
does not change: HTTP still requires one authoritative, timely sample in
which every requested port forwards.

- *Eligibility.* The caller must grant a nonzero extension allowance; the
  default of zero keeps every existing caller's behavior. The window must
  have ended on its own boundary (deadline or sample ceiling), not on
  forwarding, a stopped channel or a spent episode call budget. The most
  recent authoritative sample of the window must carry the VLAN instance,
  resolve every requested port to exactly one row, show only `LIS`, `LRN`
  or `FWD` with at least one of the first two, and report the qualified
  15-second forward delay. A later sample that the window's own deadline
  truncated is incomplete rather than contradictory, so it does not deny
  eligibility. A later sample that failed for any other reason does.
  `BLK`, a missing or duplicated row, an absent VLAN or an unattributed
  identity never earn an extension.
- *Budget.* When every pending port is `LRN` the target is the existing
  qualified 20 simulated seconds under the existing 45-second wall cap.
  When any port is `LIS` the target is 35 simulated seconds (two forward
  delays and the same 5-second margin) under an 80-second wall cap; 35
  simulated seconds at the slowest measured rate need 66 wall seconds, and
  80 keeps the qualified cap's 2.25 ratio. The effective cap is the lesser
  of that and the caller's allowance. Extension samples draw on the same
  per-sample and episode call budgets, and each simulation-clock read is a
  counted call on the same bounded channel.
- *Conduct.* The extension reuses `SimulationTimeConvergenceWaiter`, so
  an unreadable, non-realtime, invalid or regressing simulation clock
  ends it without admission. Each extension sample is one registered,
  read-only `show spanning-tree`; nothing is reconfigured to make ports
  converge. A sample completing after the extension's wall boundary is late
  evidence. Continuation stops as soon as a sample is non-authoritative or
  shows anything other than `LIS`, `LRN` or `FWD`.
- *Result.* Every sample keeps its record with a `window` or `extension`
  phase, and the observation carries the extension's evidence (candidate,
  target, wall cap, simulation start/end/progress, stop reason and
  outcome). When the extension converges, the authorizing sample is its
  last one and the window's closing is not charged against it; otherwise
  the observation stays closed exactly as before.
- *Gate.* The readiness gate offers each access group an allowance equal
  to its remaining shared budget minus the group window and the first
  windows it still owes every unobserved group, so an extension can never
  starve a later group that would have been admitted. A result that
  arrives after the group window is timely only when its observation
  reports a converged extension within the allowance the gate offered.

Rejected: a longer fixed wall window for every group, which would slow
every refused plan and change the legacy 4 / 120-second ceilings without
measuring the protocol clock; a second wall-clock episode for converging
ports, which at 19 seconds per sample yields one more reading and misses
listening-to-forwarding; `spanning-tree portfast` in E5, which changes the
compiled configuration of every plan and is unqualified on this switch;
and a per-VLAN `show spanning-tree vlan` query, a new registered query that
would need its own LIVE qualification.

Risk remains L because the product's readiness permission changes. RED
controls cover the episode 7 shape (an authoritative `LIS` sample followed
by a deadline-truncated one) reaching `FWD` within the extension; the
`LRN`-only and `LIS` targets and caps; each ineligible terminal state and
failure; a zero allowance reproducing today's result; clock failures; a
late extension sample; call-budget exhaustion; and the gate admitting
only a converged extension within its offered allowance while reserving
later groups' first windows. Episode 8 is admitted after focused and
affected verification and an independent adversarial review.

**Implementation refinements.** Retained voice evidence (a recorded
extension from 1172103 to 1173124 over two samples) establishes that
`getCurrentSimTime()` reports milliseconds, which the targets use. The
extension builds `SimulationTimeConvergenceWaiter` directly rather than
through `BoundedPvstLearningExtension`, because that object hard-wires the
process clock and sleep while this observer must keep its injected clock
and ledger-capped sleeper; the clock semantics and stop reasons are the
same. A read that ends at or after the extension boundary is reported as
the observer running out of time, so the extension closes on
`wall_clock_safety_cap` (`observer_incomplete`) and the observation names
`sample_after_deadline`, never a network answer. The product's gated E5
runtime forwarded an explicit keyword list and would have silently
dropped the allowance on the exact product path; it now forwards it, with
a regression. The existing `persistent_lis` boundary test keeps its
original meaning with a budget of one window and one interval, which offers
no extension; persistent listening through an extension is tested
separately and ends on the wall cap. An independent Codex review of
`e083979` found three gaps, all accepted and fixed with causal
regressions that fail on that commit. First, the extension's cap started
when the window actually ended, so a window read that overran 30 seconds
pushed it later, and the gate accepted a converged result until the whole
shared budget expired; together they could starve a later group. The
observer now anchors the extension's absolute deadline to the episode
start plus the window plus the offer, and the gate accepts an extended
result only up to the shared budget minus the windows still owed to other
groups. Second, a late authoritative read could seed eligibility and a
late but complete foreign-device read was tolerated as a truncation; now
only a timely authoritative read seeds, only a late incomplete read is
tolerated, and a late complete read that has left the transitional path
denies. Third, the shared waiter reads the clock, then inspects, and only
afterwards checks progress, so one read could open after the protocol
budget was spent; the access inspection now refuses to open a read once
the last clock reading shows the budget spent, and the waiter closes on
`simulation_progress_exhausted`. The shared waiter itself is unchanged for
Trunk and Voice. A follow-up review confirmed those three closed and the
episode 7 path stays eligible, and found one more: after a non-converged
extension that ends near 89 seconds with a forwarding subset, the existing
narrowing starts a second observation that could spend another group's
first window. The reservation now applies to every observation, access and
continuity: a group's first observation keeps its own window as before,
and anything beyond it (an extension, a narrowed episode) may use only the
time not owed to other groups' first windows; a narrowed episode with
nothing left is refused as `reserved_for_other_groups`. Narrowing windows
of later groups are not reserved against an extension; their first windows
are. Under the derived ceilings of two windows per group, plans without an
extension behave as before, and the injected tight-budget test keeps its
first-come result. The offer derives from remaining time, so recording it
on every observation made two route-equivalence tests (scalable envelope
and cold HTTP acceptance) fail intermittently in CI on runs that never
needed an extension. An observation now records nothing about an extension
unless one was a candidate, so equivalent runs record identical facts; both
equivalence tests keep their original comparisons and passed 20 of 20
repeated runs, with a regression proving a run admitted in its window
records no offer.
With the pre-change sources restored,
the real gate replaying episode 7's shape (listening until 60 s, about 19 s
per read) refuses with the same dimension and cause as LIVE
(`EXECUTION`, `sample_call_budget_exhausted`); with the change it admits
after the extension's reads observe forwarding. Touching
`simulation_time_convergence.py` brought it under Ruff (import order, three
docstrings and formatting).

## Episode 8 result: native DHCP and dependent HTTP through the product, version 13

Episode 8 ran `Q3-NATIVE-PRODUCT` at `04c06ad` (tree `6c5a644`), attempt
`331fa0baf0974dfaa59efd69bd0590ac`, file channel, after four independent
review rounds ended in approval; the archive is
[`dhcp-autonomy-02/e8`](../../reference/server-pt/evidence/dhcp-autonomy-02/e8/README.md).
The maintained A1-E6 product path completed with overall status
`verified` and a completed, sealed product record. The required
`DHCP_LEASE` check verified PC1 at `192.0.2.100/24` with its exact
IP/MAC/port row in the effective physical `serverPool`, the logical pool
label kept apart, and PC2 as the checked inactive client. Access readiness
saw the same shape as episode 7 (`LIS` at 19.3 s, a deadline-truncated read
at 32.3 s) and the simulation-time extension then read both ports `FWD` at
53.6 s. The required `HTTP_FETCH` check verified one cold request from PC1
to `http://192.0.2.10/` with fresh marker content. No `dhcpRun`, ping, DNS,
warm-up or client static address was dispatched. The independent terminal
reading showed PC2 DHCP-off and unassigned, the single pool row, the
separately named pool absent and the complete requested policy. The run
used 93 operations and 330.315531 seconds; launch, restoration, retirement
and sealing were clean. Cumulative use is 431 operations and 2349.124315
seconds.

**What this establishes.** For the exact build, fixture, one-user policy and
file channel, the maintained product configures the native pool, verifies an
autonomous lease attributed to the effective pool, waits for access STP
forwarding on Packet Tracer's own clock, and serves dependent HTTP to that
client. It does not establish renewal, explicit `dhcpRun` causality, native
capacity beyond one user, other builds, the public four-argument entry
without the private capability snapshot, default catalog promotion or
independent product acceptance. The simulation-time extension's listening
budget is qualified for this fixture only; this run spent 1.75 simulated
seconds between its two clock reads before its one extension read, so it
does not measure the protocol clock rate.

## Delivery, version 14

**Default catalog decision.** The compiler admits the native binding only
for the measured policy (`192.0.2.0/24`, `.100`-`.100`, gateway `.1`, DNS
`.10`, the two exclusions) and every native measurement so far is at
capacity one. Registering the binding in the default catalog now would
publish a capability that refuses every other address plan, so it stays a
private exact-build candidate snapshot; the public four-argument entry
therefore still refuses state-only DHCP and was not run LIVE with it. Policy
generalization and native capacity above one user are the prerequisites for
any default registration.

The READY_FOR_REVIEW delivery, with source and CI identities, design and
rejected alternatives, decisive records, scale measurements, resource use,
residual limitations and its integrity manifest, is
[`dhcp-autonomy-02/DELIVERY.md`](../../reference/server-pt/evidence/dhcp-autonomy-02/DELIVERY.md).

## Public policy and multi-client continuation, version 15 design delta

**Starting identity and risk.** This continuation starts from clean
`feature/server-pt-goal-foundations` at `543adbe8e761c04fb824b7fbd5de1c6aedf34530`
(tree `13f8e33c11972c0b9cc1cb364e4e5d09ee0d4ea3`). Risk remains **L**:
the public capability, native effect admission, and DHCP-to-HTTP evidence gate
change. Episode 8 remains immutable evidence for its exact one-client policy.
Its readiness observation records 53.639 seconds total elapsed; about 34.327
seconds elapsed from the first retained sample. The archived delivery report's
roughly-34-second description is corrected here without changing its pinned
historical bytes. The final Ubuntu/Python 3.13 CI at `543adbe` reported 8116
passed and 22 skipped; the skip reasons must be retained and inspected, not
inferred from the platform or replaced by the earlier local pass count.

**Outcome and bounded family.** Admit unnamed `state_only` Server-PT DHCP on
`FastEthernet0` only with exact-build recorded native capability and an
independently checked policy scope. Represent the requested allocation in the
existing intent and typed pool action, with physical `serverPool` recorded
separately. The current private candidate binds `192.0.2.0/24`, one wired
segment, a
contiguous usable interval within that subnet, 1 through 16 selected PC-PT
clients, capacity at least the selected count and at most 16, and no more
than 16 compact exclusion ranges. Require a server and gateway inside the
segment, a complete DNS address, disjoint exclusions and allocation, unique
client identities, and one native pool. The initial observed one-client
policy is included, but other values remain candidate behavior until measured
LIVE. Other masks, larger capacity, explicit pool names, other models/builds,
and incomplete policy are refused before effects. A recorded capability scope
narrows the policy family independently of the generic `/24` implementation;
the private candidate's wider values remain experimental. The runtime independently
validates the same family and each exact physical transition; it never treats
the capability marker alone as proof of a setter's effect.

**Composition and evidence.** Derive selected and competing clients from the
plan and deployed manifest. A one-PC plan has no invented inactive control;
each selected E5 effect checks the disabled owned server and real competing
ports before changing DHCP mode. Enabling the pool requires all selected
ports eligible and all actual competing ports still inactive. The native
state reader obtains fresh complete policy and one bounded indexed lease
scan per group sample, reads each selected port, and joins every positive row
to the exact server, physical pool, IP, MAC and interface. Two stable positive
samples establish usable state per client. Duplicate/conflicting addresses or
global server/pool ownership loss block all dependent operations; a client's
incomplete evidence blocks that client's HTTP. Persist shared scan evidence
once and retain per-client outcomes and sample history. No success wording
implies `dhcpRun` causality, renewal, or lease-table end. The optional
`dhcp_lease_attributed` projection duplicates the required native-state
join and produced `lease_client_identity_invalid` in episodes 7 and 8; omit
it for native `state_only` plans while preserving it for other DHCP modes.

**Public authority.** Register only the measured scope in the trusted
exact-build default catalog after discriminating owned-lab evidence. Keep the
four-argument MCP signature and the standard application composition. An
unqualified policy is rejected before E5. No global support override or
public strategy selector is introduced.

**Verification and acceptance.** First prove causal RED for the old fixture
restriction, real one-PC and multi-client selection, transition rejection,
shared scan/index behavior, duplicate/foreign rows, partial client failures,
optional-check removal, and public catalog admission. Verify focused module,
affected product composition, durable records and 2/20/200/1000 offline
workloads with explicit backend substitution and measured operation/byte
growth. Then run new exact-SHA owned-lab episodes with finite recorded
allocations: contrasting address policies and capacity above one, followed
by registered four-input DHCP plus each client's cold HTTP-by-IP request.
Preserve campaign archives, result/exit/persistence/cleanup agreement and
exact-SHA CI. Static-client HTTP controls remain positive. Router DHCP,
alternate transports, renewal proof, other masks and native thousand-client
capacity are outside this delivery. Unit, integration, system and acceptance
levels all apply; LIVE acceptance is required for a SUPPORTED public scope.

## Episode 9 capacity result and shifted-policy decision, version 16

Episode 9 executed `Q3-NATIVE-PRODUCT` profile 2 from clean
`68680209eaaa5c88fd0f7cc30675232c645cc263` (tree
`c996b28b9744308b9833fdefdbf847b207fcae96`), attempt
`22d8ccc6f02540f1842f42ad2d3fdf88`, on Packet Tracer 9.0.1.0858 through
the file channel. The source-linked, 180-file archive is
[`dhcp-autonomy-02/e9`](../../reference/server-pt/evidence/dhcp-autonomy-02/e9/README.md)
with manifest SHA-256 `b37759403d70a5feef1846645b73ce6df31f353e8e2cb3de79d0fe675b1bff12`.
The maintained A1-E6 product record SHA-256 is
`cc92eae7e34680db7dbeb510c3f9a83c2e33e88108bce9865cd33971549769de`;
the qualification record SHA-256 is
`288286ba175acb1848773120e8df2db3cc13a4c9eb424bdc8dc386185c74c081`.

The private candidate configured physical `serverPool` at capacity two,
`.100`-`.101` within the requested policy. PC1 received `.100`, PC2 `.101`,
with distinct stable MACs and exact positive physical rows in two consecutive
samples for each after one unassigned sample. Both cold first HTTP-by-IP
requests VERIFIED. The product and both required stage measurements completed
SUPPORTED_IN_SAMPLE; fixture restoration and owned process retirement were
proven, with a zero-process, empty-mailbox final census. Qualification spent
88 operations and 161.016 active seconds; the closed campaign ledger charged
405.774797 seconds for the episode and totals 519 operations/2754.899112
seconds. This qualifies capacity two for this exact policy and build, not the
shifted policy, other networks or public default catalog.

**Next discriminating episode.** Keep the owned four-device fixture and
capacity two, but change the input `start_offset` from 99 to 150 so the
requested window is `.151`-`.152`. Advance the stage profile revision and
freeze a new clean source SHA/tree before contact. The setter's observed
post-start state and subsequent size, gateway, DNS and exclusion reads must
match the derived policy before enable; a different native coupling stops the
episode. Require two distinct attributed client states and both cold HTTP
requests. The existing finite 600-operation/2100-second stage ceiling and
per-episode lifecycle allocation remain upper bounds, with a new plan and
attempt identity recorded before launch. This is a policy discrimination,
not a repeat of the positive `.100`-`.101` case.

## Shifted-policy result and public composition design, version 17

Episode 10 executed profile 3 at `e8c810192b44d75340ffa6ad81c16473eb060fd2`
(tree `81802ac0307688a5acde8e503b169c39b82af857`), attempt
`4d5e9960ce0a4de291697ce7c667c7d2`, Packet Tracer 9.0.1.0858/file.
The new request set `start_offset=150`; the native pool read back exactly
`.151`-`.152`, capacity two, gateway `.1`, DNS `.10` and the two exclusions.
PC1 received `.151`, PC2 `.152`; both required attributed lease rows and
both cold HTTP-by-IP checks VERIFIED. Product and two stage measurements
completed, fixture restoration was proven and owned PID 4956 retired with a
zero-process, empty-mailbox final census. Qualification used 89 operations
and 159.469 active seconds; the closed ledger totals 608 operations and
3074.101403 seconds. The source-linked
[`episode 10 archive`](../../reference/server-pt/evidence/dhcp-autonomy-02/e10/README.md)
pins 198 files with manifest SHA-256
`611e57fd02b2c75fa8660bda11b0d85712a3a6e13fe551f13dda42804aa90150`.
The qualification and product record SHA-256 digests are respectively
`77d957b092d7c74e021b01f37e5e88837a1efcdf452f71dac6b24d41a9a9e60e`
and `909e55d1fdeb8bdc6c3c8763c16464c6fb5995b836221ec41b93930cfa7fe63e`.

**Public authority design.** Register one exact-build native binding in the
trusted default catalog, with both episode identities and a bounded policy:
physical Server-PT `FastEthernet0`, `192.0.2.0/24`, server/DNS `.10`, gateway
`.1`, exact exclusions `.1` and `.10`, a contiguous requested window starting
from `.100` through `.151` and ending no later than `.152`, and capacity one
or two with at most two selected PC-PT clients. The two measured start points
and capacity cases justify this finite family together with per-invocation
full transition readback; intermediate values are admitted only when their
exact backend state is verified before enable. Other networks, masks, gateways,
DNS, exclusions, capacities, models and builds remain UNKNOWN. Keep the
general DHCP service profile UNKNOWN: the native marker may resolve only
native-bound E6 actions and state-only verifications. A named pool, generic
server DHCP, explicit `dhcpRun` and other policies must not inherit support.

RED controls will prove that the default public catalog admits the bounded
unnamed state-only request and rejects each outside-scope dimension before
E5; static HTTP and the private diagnostic composition remain positive. The
registered four-argument MCP handler must reach the same A1-E6 runtime and
durable record, then a fresh owned-lab episode must exercise it with two
selected clients and first HTTP-by-IP requests. The public route must expose
no capability override, strategy selector or alternate DHCP runner. Risk
remains L; focused, affected, full and exact-commit validation plus separate
review apply before READY_FOR_REVIEW.

**Registered LIVE route, version 18 design refinement.** The current
qualification stage's private call passes a candidate capability snapshot
directly to `apply_enterprise_services`; it cannot establish the registered
MCP route. For the next profile revision, keep the same owned fixture,
manifest admission, bounded channel, A1-E6 use case, persistence and
retirement. Invoke the actual registered four-input
`pt_apply_enterprise_services` handler inside the governed stage, with the
already verified fixture manifest and ledgered real runtimes supplied as
internal composition ports. The tool passes no capability override; the
default catalog is its only capability source. Capture the typed use-case
result and compare it with the handler's JSON response and stored product
record before concluding. Use requested start offset 124 (window `.125`-
`.126`, capacity two) as an interior point of the bounded public family.
Run the existing required lease and HTTP checks for both clients, terminal
inventory, restoration, retirement and archive. A refusal, mismatch, missing
record or uncertain effect stops the episode; it never falls back to the
private candidate path. The MCP public signature remains four arguments.

**Pre-LIVE offline validation.** The changed native/public, capability,
product, campaign and legacy-service group passed 229 tests. The provisional
full Windows suite passed 8163 with 6 skips and 3 pytest deprecation
warnings. The skip reasons were retained by a focused `-rs` run: two tests
require symlink privilege, two lack ignored historical raw artefacts, and
two native-window tests require the explicit Windows opt-in. All required
native/public path tests ran on this job. The provisional quality gate and
MkDocs build passed; exact clean-commit validation and governed LIVE remain
separate gates.
