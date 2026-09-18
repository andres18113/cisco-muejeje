# Server-PT plan: review resolution, revision 2.2 (C1 and C2 on revision 2.1; SR, B and G history retained)

Companion to `Server-PT-Services-Plan-rev2.2.md` and
`Server-PT-Services-Implementer-Prompt-S0-rev2.2.md`. Status of the revised
plan: **READY_FOR_REVIEW**. Nothing here authorizes implementation or LIVE
work; the corrected S0 contract awaits independent approval. Revision 2.2
resolves the two finding families of
`Fable_S0_rev21_Two_Finding_Correction.md` (C1, C2) and changes nothing
else: B3, G1 to G4, the E6 architecture, the namespace, the transports and
the slice ownership are as in revision 2.1.

Provenance of this resolution:

| Item | Value |
| --- | --- |
| Repository | `andres18113/cisco-muejeje`, checkout `Cisco-MCP`, branch `main`, HEAD `6263344e31ba3b0de6539d652f2cd06fc73a3562`; `git status --short` empty before and after this work (reported by the agent, not independently observed) |
| Reviewed inputs | rehashed here and equal to the correction's table: plan rev2.1 `345dbbf1…e7e7c`, S0 prompt rev2.1 `b3fe482b…8f27a`, resolution rev2.1 `1d375e1b…e7562` |
| Correction input | `Fable_S0_rev21_Two_Finding_Correction.md`, SHA-256 `7f26d241bc1a9bc297dd145fe67131e30b9674c1209ce86d8ec0adf8466ae12b` |
| Reviewer countermodels | `verification.json` and `audit_contract.py` were not delivered with the correction and were not found on this machine (Downloads, Desktop, session scratchpads searched); the probes in the appendix are independent replacements written for this revision and reproduce the correction's collision pair from their own FNV-1a implementation |
| Outputs | `Server-PT-Services-Plan-rev2.2.md` SHA-256 `1332e4a9a7387c498821ccf09c3c5d9ba39f7e10b0a141f113412650e2309478` (2106 lines); `Server-PT-Services-Implementer-Prompt-S0-rev2.2.md` SHA-256 `d689d1812349a2ce0063c5c41fdab431cc3f1c6b554043f3cf5e0ddfba26312e` (416 lines); `Server-PT-Services-rev2.2-probes/` with `probe_c1_rows.js` `967e1e1ea7f1555dd0558c00dbcb7da73dc7e9351c1ba1933b0e13c9362e0f5d`, `probe_c2_decision.py` `1c9a4d9860e8f38166943727ccaae2dff9cc561f2cb50fb1523d1570414fcc6c`, `c1_rows.json`, `c2_report.txt`, `README.txt` |
| Offline measurements | Node v24.19.0 for the row probe; the checkout `.venv` (CPython 3.12.10) for the table checker; the baseline functions `_derive_dirty_state`, `mutation_execution_status`, `disposition_from_status` and `satisfies_apply_dependency` copied by hand from the read-only checkout; no Packet Tracer contact, no bridge started, no repository file modified, no dependency installed, no subagent, no Git write |
| Instruction loading | `CLAUDE.md`, `AGENTS.md` and `docs/engineering/standards.md` were present in the session's loaded project instructions; `/context` was not run by the agent, so that observation is pending |

Disposition vocabulary: **Accepted**, **Accepted with modification**
(finding adopted; the proposed fix replaced by one the evidence supports
better), **Extended** (finding adopted and a further defect found in the
same area). No finding was rejected. "Design resolution" means the plan now
states the contract; "implementation evidence" is what only the executed
slice, its tests or a LIVE record can provide, and is named as such.

---

## Part 1 — Revision 2 history (SR-01 to SR-10), retained

The revision 2 dispositions stand and are kept as the base of revision 2.1.
Where the targeted review sharpened a rule, the row says so.

| Finding | Disposition (rev2) | Revision 2.1 status |
| --- | --- | --- |
| SR-01 dispatch uncertainty | Accepted with modification (typed `DispatchFact`/`ResultFact`; HTTP 200 is acceptance by the local bridge queue; file phases; `EXECUTE_ONCE` has no at-most-once guarantee) | retained; the post-effect marker guard is replaced by the pre-effect claim of R-EVT-06 (G3) |
| SR-02 direct-read freshness | Accepted; extended (`found:false` was FAILED with fresh True; E5 observer precedent) | retained; observation facts now include INCONCLUSIVE and LOST (B2b, B3) |
| SR-03 error preservation | Accepted; extended (successful E6 runs journal as UNKNOWN; dispositions never set) | retained; superseded in detail by B1 and B2 (four facts, decision table, journal fields) |
| SR-04 quality instructions | Accepted (JSON claim corrected by measurement; no `noqa`; contract-preserving `StrEnum`; `tool_registry.py` owned in S1) | retained; format and lint commits separated (G4) |
| SR-05 capability authority | Accepted; extended (documentary provenance of the DNS/HTTP baseline) | retained; provenance levels made explicit (G4, R-CAP-07) |
| SR-06 E5/E6 integration | Accepted; extended (`SetEndpointDhcp` dropped without an IOS pool; `_mutation_scope` needs P-E5-2; DHCP-mode foundation) | retained; network path and DNS derivation added (G1) |
| SR-07 secrets | Accepted (HTTP-only for secret-bearing invocations; bounded claims; account and POP3 policies) | retained; digests never carry credentials (B1) |
| SR-08 event lifecycle | Accepted; extended (unregistration undocumented) | retained; claims and quarantine separated from observer cleanup (G3) |
| SR-09 DHCP predicates | Accepted (documented MAC getter; lease-time change proposed as the acquisition signal) | modified: the lease-time inequality is demoted to UNKNOWN until M-DHCP-6 (G3) |
| SR-10 qualification versus acceptance | Accepted (staged matrix; S1b; record schema) | retained; Q1 attribution, Q1b, coordinator-based acceptance (G4) |

---

## Part 2 — Targeted review of revision 2 (B1 to B3, G1 to G4)

Each entry reports: disposition; sections and requirements changed;
repository or vendor evidence; one counterexample the corrected predicate
rejects; the required acceptance test; the owning slice; and what remains
implementation evidence.

### B1 — Mutation effect is not the same as matching the requested state [blocks S0]

*(Revision 2.2 note: the digest-based `changed` rule and the "fully successful run is CLEAN" claim recorded below were corrected by C1; see Part 3. The text is the revision 2.1 record.)*

**Disposition: Accepted; Extended.**

Changed: R-OBS-07 (rewritten), R-OBS-02, R-HTTP-01, R-DNS-01, section 4.4
(mutation row contract), section 4.5 (mutation script contract, decision
table rows 8 to 14, journal rule), RD-10, S0 prompt items 1, 4 and 6.

Evidence:

- `enterprise_service_runtime.py:116-121`: `ok = !!p.addARecordToNameServerDb(h,a) || !!p.getARecordWithAddress(h,a)`; a true add result short-circuits the getter, so `ok` is not post-read evidence. Every other family reads once after the setter (109-148); no pre-read exists.
- `execution.py:332-348`, evaluated offline on the copied pure function: entries with only FAILED dispositions return CLEAN (342-345), because `mutations` counts only CHANGED and REASSERTED. The shared model has no field that says "failed and changed".
- `configuration_runtime.py:201-232`: `mutation_execution_status` derives FAILED solely from `applied=False`, which the docstring defines as "never left the process"; the baseline runtime sets `applied=bool(ok)`, so a dispatched setter whose read-back mismatched is reported as never dispatched.

Correction: four separated facts (`dispatch`, `result`, `transition`,
`postcondition`) plus `residual_change` and `cause`; bracketing reads with an
unconditional post-read inside their own try/catch; `ok` computed from the
post-read only; `call_result` recorded and never used; digests (booleans as
"0"/"1", strings as FNV-1a 32-bit plus length, never credentials); one
decision table; the scoped journal change RD-10 (`ExecutionJournalEntry.residual_change`
and one rule in `_derive_dirty_state`) so a failed operation with an observed
unintended change is DIRTY_RECOVERABLE or DIRTY_UNRECOVERABLE, never CLEAN;
row 10 (unsatisfied postcondition with an unknown transition) is the one case
the shared model cannot represent exactly and is reported FAILED without
residual plus the limitation `residual_unknown` and the sticky flag. A
transition is reported as "observed between the bracketing reads of this
dispatch" and never as execution count or sole causation.

Counterexample rejected: before `page-A`, intended `page-B`, after `page-C`.
Revision 2 gave `(was=false, ok=false)` → FAILED and a journal of FAILED
entries → CLEAN. Revision 2.1 gives `transition=CHANGED`,
`postcondition=UNSATISFIED`, `residual_change=True`, status PARTIAL with
`POSTCONDITION_UNSATISFIED`, `dirty_state=DIRTY_UNRECOVERABLE` (no inverse
on E6 actions). The unchanged-failure case (`page-A` → `page-A`) stays
distinct: `residual_change=False`, CLEAN residue for that entry.

Acceptance test: the Node harness scenarios of plan 6.5 (unchanged success,
changed success, unchanged failure, changed-to-wrong, setter effect followed
by exception, getter failure pre/post/both, add-return-true with post-read
missing or mismatching), each asserting the reported row, the derived facts,
the action status and code, and the journal `dirty_state` through the real
applicator; the journal table test proving every baseline input unchanged
for `residual_change=False`.

Owning slice: S0. Implementation evidence: the harness run under Node in
CI; the table tests.

### B2 — The facts chain and uncertainty frontier are still incomplete [blocks S0]

*(Revision 2.2 note: the row 10 reading, the item 1 branch order and the item 5 sticky predicate recorded below were corrected by C2; see Part 3. The text is the revision 2.1 record.)*

**Disposition: Accepted (B2a and B2b); Extended.**

Changed: R-OBS-02, R-OBS-06, R-OBS-08, R-EVD-01 (all rewritten), section
4.4 (`ExecutionJournalEntry` and `ActionApplicationResult` fields,
`ObservationFact` with LOST and INCONCLUSIVE and the `UNSPECIFIED` default,
`cause` on `RuntimeServiceVerification`, import direction of
`transport_outcome.py`), section 4.5 (decision table with sticky and frontier
columns for every admitted combination and an explicit inconsistent row),
S0 prompt items 1, 4 and 5 and the exclusions paragraph.

Evidence:

- `configuration_runtime.py:245-253` (`ActionApplicationResult`) and
  `execution.py:88-100` (`ExecutionJournalEntry`) carry no dispatch or
  result fields; `journal_from_action_results` (294-319) copies a fixed
  subset; `compact_summary()` reports counts (`service_runtime.py:63-88`).
- `apply_services.py:527-533, 541-548`: every non-VERIFIED verification gets
  a `*_VERIFICATION_FAILED` code and an exception becomes FAILED.
- `execution.py:141-145`: `mark_transport_unknown` is the sticky mechanism
  the applicator must call.
- `configuration_runtime.py:15` imports `OperationSemantics` from
  `.execution`, so the fact enums must live in `execution.py`;
  `file_bridge.py` and `live_bridge.py` import `transport_outcome.py` and
  never the reverse.

Correction (B2a): the table of plan 4.5 lists rows 1 to 16 and the
inconsistent catch-all. ENGINE_ERROR (row 5), MALFORMED (6), missing or
invalid rows (7), post-read failure (8), unsatisfied postcondition with an
unknown transition (10) and Python exceptions (15) all set the sticky flag and
block dependents; only SATISFIED postconditions (rows 9, 11, 12) or legacy
rows (16) establish an effect. Recovery reads are admitted explicitly for
read-only and owned-temporary kinds without satisfying `ACTION_APPLIED`; they
never change the action row or clear the sticky flag.

Correction (B2b): `dispatch`, `result`, `residual_change` and `cause` are
named fields on `ExecutionJournalEntry`; `ActionApplicationResult` carries
all six facts; `RuntimeServiceVerification` carries `observation` (default
`UNSPECIFIED`, distinct from `NOT_ATTEMPTED`) and `cause`, and never
`failure_code` (the applicator derives it, so the `**observed.model_dump()`
construction has no duplicate keyword); `ObservationFact` includes `LOST` and
`INCONCLUSIVE`; the evidence mapper delegates `UNSPECIFIED` rows to the
legacy adapter; the S0 exclusions name `execution.py` and
`configuration_runtime.py` as the shared-DTO exception to "no E5 file"; JSON
gains keys, and a baseline-shaped fixture must still validate.

Counterexample rejected: ACCEPTED + ENGINE_ERROR. Revision 2 gave APPLIED,
disposition UNKNOWN, `OUTCOME_UNKNOWN`, dependents allowed, no sticky flag.
Revision 2.1 row 5 gives postcondition UNOBSERVED, dependents
DEPENDENCY_BLOCKED (`prerequisite_outcome_unknown`), sticky flag set, bundle
never VERIFIED, and the fact survives serialization on the action row, the
journal entry and the run record.

Acceptance test: the round-trip test of S0 item 5 (runtime rows through the
real applicator, journal and evidence mapper, `model_dump_json`,
`model_validate_json`, facts and primary cause still accessible, agreement by
behavior); the full-product table test of `mutation_execution_status`; the
legacy-identity test; the baseline JSON fixture test; compact-summary
byte-identity for legacy rows.

Owning slice: S0. Implementation evidence: the tests above.

### B3 — Tests cannot be both unchanged and consistent with the revised contract [blocks S0]

**Disposition: Accepted; Extended (the repository already has the harness pattern).**

Changed: R-TEST-01 (new), R-OBS-03 (fresh negative evidence, inconclusive
reads), R-HTTPS-02 (affirmative mode read), section 4.5 observation table,
section 6.5 (inventory and authorized changes), RD-9, S0 prompt items 4, 6
and 7 and its RED list.

Evidence:

- `tests/test_service_runtime.py:183-213, 280-303` assert FAILED with
  `fresh_evidence` False for a fresh wrong address and fresh content without
  the marker; 242-279 assert FAILED for a marker present before the request;
  318-345 assert VERIFIED with an empty marker and a start fixture without
  any mode field; 38-66 and 67-87 feed `{id, applied}` rows.
- `tests/test_service_application.py:30-60`: `FakeServiceRuntime` returns
  `RuntimeActionMutation(applied=True)` rows and verification rows with
  `fresh_evidence=True` and no observation fact.
- Harness precedent: `tests/test_typed_ping.py:196-276` evaluates a
  generated script under Node against stub `ipc` objects and captures
  `reportResult`; `tests/test_e95_serial_physical_product_slice.py:1235-1263`
  does the same for module payloads (registry basis
  `PAYLOAD_EXECUTION_SIMULATED`, `mutation_replay.py:113, 545`); both skip
  when Node is absent; the CI workflow installs no Node explicitly
  (`.github/workflows/tests.yml:14-34`).

Correction: an explicit inventory with per-assertion classification (plan
6.5) and five authorized changes with rationale: fixture rows for the two
mutation tests (incidental representation); fresh True with CONTRADICTED for
the wrong-address and wrong-content tests (known incorrect expectations);
UNKNOWN with INCONCLUSIVE for the stale-marker half; `https_mode: true` in
the HTTPS fixture with the mode assertions and PARTIAL for the empty marker.
Every other assertion is a valid invariant and stays. `FakeServiceRuntime`
stays a legacy producer whose `UNSPECIFIED` observation never means
OBSERVED. The generated mutation script is proven by the Node harness, which
fails rather than skips under `GITHUB_ACTIONS` (RD-9), not by a fake's
disposition. Golden-script equality is limited to the vendor-call surface of
the readers.

Counterexample rejected: a fake returning `disposition=CHANGED` for every
row would have made revision 2's R-OBS-07 test green without any generated
script ever running. Revision 2.1 requires the harness to execute the actual
batch script with a setter that stores a different value and asserts
`residual_change=True` from the reported row.

Acceptance test: the inventory committed in the brief; the five authorized
edits RED at the baseline; the harness scenarios; the positive controls
listed in the S0 prompt unchanged.

Owning slice: S0. Implementation evidence: the inventory, the harness run
and the suite.

Mutual satisfiability of B1 to B3: B1's facts are carried by B2's fields and
are what B3's harness asserts; B2's `UNSPECIFIED` default is what lets B3's
legacy fixtures stay unchanged; B3's authorized freshness changes are exactly
the observation rows of B2's table. No contract asks the same test to be
both unchanged and changed.

### G1 — S1 needs a reachable, sufficient network and capability path [before S1]

**Disposition: Accepted; Extended (`ServiceRequirement.required` is unused today).**

Changed: R-ENTRY-02 (reads permitted, mutations forbidden), R-NET-01 and
R-NET-02 (new), R-CAP-06 (new), R-ENTRY-11 (new), R-DNS-03, section 4.5
(client DNS, E5 closure under the bounded topology), section 4.10 (sample
with `required: false`), S1 and S1c slices.

Evidence:

- `configuration.py:149-171`: `ConfigurationPolicy.dns_server` defaults to
  `None`; `configuration_compiler.py:1162-1171` places it on static
  endpoints; `enterprise_configuration_runtime.py:841-858` passes
  `action.dns_server or ""` to `configurePcIp`, which calls
  `port.setDnsServerIp` only for a non-empty value (`main.js:280-310`);
  `compose_enterprise_reference.py:186-193` passes no policy, so no client
  gets a DNS server on the public path.
- `requirements.py:48`: `ServiceRequirement.required` exists; the service
  compiler reads only `verification_required` (`service_compiler.py:637`).
- `configuration_compiler.py:1162-1171, 309-323`: endpoint actions depend on
  their access port, DHCP endpoints on their pool and access port; nothing in
  the E5 dependency graph adds gateways, SVIs, trunks or routing for a
  cross-segment path unless the E6 cross-segment rule names L3 foundations.

Correction: admission performs directed reads and no mutation; the first
supported topology is one segment with static server and clients (R-NET-01),
routed single-gateway clients move to S1c, multi-router paths are out of
scope; `derive_service_policy` sets `dns_server` from the DNS service's
explicit `address` (a DNS service without one is `DNS_SERVER_ADDRESS_REQUIRED`
in S1; two-pass derivation is D-11); `CLIENT_DNS_SERVER` is a new reader,
optional until M-DNS-3 is recorded in Q1 and never SUPPORTED by inference;
required and optional services and expectations are decided by the intent's
existing flags, a required ineligible service refuses before effects, an
optional one is excluded before E5, and unknown mutations are never dispatched.

Counterexample rejected: the revision 2 sample response ran DNS and HTTP
while HTTPS was capability-unknown with no rule saying why the run was not
refused. Under R-ENTRY-11 that response is only possible with
`"required": false` on the HTTPS service; without it the run refuses at A8.

Acceptance test: integration tests from the MCP input with the real
composition and compilers over injected runtimes that record call arguments:
an initially unset DNS policy yields an E5 static action and a runtime call
carrying the DNS address; a routed client is refused; required versus
optional ineligible services; exactly the R-NET-01 closure reaches E5.

Owning slice: S1 (S1c for routed clients; Q1 for M-DNS-3). Implementation
evidence: the S1 tests and the S1 acceptance record.

### G2 — S1 persistence and retained results are not yet a complete safety contract [before S1]

**Disposition: Accepted; Extended (D-9 containment defined).**

Changed: R-ENTRY-06 (rewritten), R-RET-01 and R-RET-02 (new), section 4.8
(record lifecycle, full rows, `persisted_stage`, unbound admission records),
section 2.1 (A1 to A6 annotations), S1 tests.

Evidence:

- `configuration_runtime.py:303-355`: `ConfigurationApplicationResult`
  carries full `action_results`, `verification_results`,
  `mutation_action_ids` and `retained_action_ids`; only `compact_summary()`
  reduces to counts. `cp_scale_stage_evidence.py:78` persists the full
  `model_dump(mode="json")`, the precedent for retained rows.
- `apply_configuration.py:1292-1369`: retained results must be previously
  applied and complete for every action outside the delta.
- `apply_configuration.py:1229-1256`: a missing E5 row is FAILED with
  APPLICATION_FAILED and a runtime-supplied code is cleared when `applied`
  is true (D-9); `execute_enterprise_reference.py` stops on contradiction
  only.
- `deployment_manifest_store.py:30-60, 129-135`: containment pattern for the
  record store.

Correction: A1 and A2 refusals leave no record (no valid identity), A3 to A5
write an unbound admission record when the store is writable, A6 refuses the
run if the bound record cannot be created; after the first effect a failed
rewrite stops new user-state mutations, allows bounded observation and owned
cleanup, preserves the primary error and reports `persisted_stage`; the
record persists the full E5 rows and identity; retained reuse requires the
same deployment, manifest hash, config hash and environment fingerprint, a
prior run without effect uncertainty or unsatisfied postconditions, and fresh
prerequisite verification before trust; interrupted or uncertain prior runs
retain nothing; the tool never trusts an E5 CLEAN when a row in C carries
`SESSION_FAILED` or the missing-row message, stops before E6 effects and
reports run-level UNKNOWN (R-RET-02); the D-9 fix stays a separate brief.

Counterexample rejected: a prior run with the same semantic hash on a
different environment fingerprint, or a prior run that ended with
`transport_unknown`, would have been reused as retained results under
revision 2's "persisted prior result for the same hash". Revision 2.1 refuses
both and re-verifies the rest before trusting it.

Acceptance test: rejection before A6; persistence failure before and after
the first effect; retention round-trip; interrupted run; same hash with
changed environment or state; no unrecorded new mutations after persistence
is lost; injected E5 runtime raising after dispatch stops before E6 with
`e5_effect_uncertain`.

Owning slice: S1. Implementation evidence: the S1 store and use-case tests.

### G3 — Event/replay containment and DHCP attribution still need causal predicates [before S2/S3]

**Disposition: Accepted with modification (lease-time signal demoted; claims and quarantine added).**

Changed: R-EVT-06 and R-EVT-07 (new), R-OBS-05, R-DHCP-04, R-DHCP-05,
R-DHCP-07 (rewritten), section 3.7 (single-evaluation atomicity as an
inference), section 4.4 (execution guarantee), section 4.6 (lifecycle),
section 5.8 (Q0 and Q3 discriminating experiments), S2 and S3 tests.

Evidence:

- `technical-debt.md:3355-3470`: re-evaluation of a request is possible when
  its deletion fails; a marker written after the effect cannot guard the case
  where the effect happened and the call threw before the assignment.
- Local reference: `DhcpClientPortData.getLeaseTimeStr()` has no documented
  format or behavior; `DhcpPool.getLeaseAt(int)` has no count or
  end-of-table contract; `getMaxUsers()` bounds the scan and documents
  nothing about the current row count.
- Revision 2's Script C deleted the subject lock on release regardless of
  resolution, contradicting its own claim that a newer operation cannot start
  before the uncertainty is resolved.

Correction: a pre-effect claim `{state: in_progress|completed|unknown}`
written before the effect, never re-entered, atomic within one script
evaluation (an inference recorded in 3.7 and probed in Q0); observer cleanup
separated from effect ownership, unresolved claims quarantine the subject for
the session, and a new operation on a quarantined subject is refused, which
is what makes receipt sequence numbers admissible; registration or
unregistration acknowledgment loss leaves the operation UNKNOWN and the
subject quarantined; the read-back DHCP path yields at most UNKNOWN until
M-DHCP-6 records a no-acquisition negative control over time, an automatic
renewal and a requested renewal; positive lookup, confirmed absence and
completion are three claims, and absence or exhaustion requires the
calibrated end condition of M-DHCP-2. None of this manufactures exactly-once
semantics.

Counterexample rejected: a lease-time string that counts down between two
reads with no acquisition would have satisfied revision 2's R-DHCP-04(b)
inequality and yielded VERIFIED. Revision 2.1 yields UNKNOWN
`acquisition_unattributed` until M-DHCP-6 shows the value is stable without
acquisition and changes only on renewal.

Acceptance test: harness scenarios for the claim lifecycle (claim written
before the call; throw after effect leaves `unknown`; second script refuses);
quarantine tests (late old event after a new dispatch is impossible because
the dispatch is refused; ack loss quarantines); DHCP tests for found, foreign,
not found without and with the end condition, exception before the bound;
the Q0 and Q3 experiments of plan 5.8.

Owning slices: S2, S3 (design); Q0, Q3 (measurement). Implementation
evidence: the recorded stages; until then every affected capability stays
UNKNOWN.

### G4 — Capability provenance and delivery packaging [before product promotion]

**Disposition: Accepted.**

Changed: R-CAP-07, R-QUAL-05, R-QUAL-06 (new), R-CAP-05 (golden identity
limited to the vendor-call surface), RD-8, section 3 (DNS matrix restored;
provenance column), section 4.3 (R-HTTP, R-DNS, R-MAIL, R-COV predicates
restored), section 4.4 (domain DTOs restored), section 4.10 (sample input
restored), section 4.9 (format and lint commits separated), S1b and Q1b.

Evidence:

- `service_capabilities.py:22` and `enterprise-services.md:102-118`: the
  DNS/HTTP baseline records no run id, tree SHA or transport (`grep` over
  `docs/` and `reference/`: 0 hits for the evidence method names).
- Revision 2 replaced section 3.3, several requirement rows, the DTO block
  and the sample input with "unchanged from revision 1", which made a
  committed brief depend on an untracked file.
- Ruff lint fixes for D-rules and I001 change docstrings and import order,
  which change the AST; an AST-equality proof is only meaningful for a
  formatting-only commit.

Correction: every capability record carries `provenance` ∈
{`documentary_baseline`, `recorded_run`}; legacy DNS/HTTP records stay
documentary forever and are disclosed in the response while the product tool
uses them under RD-8; promotion of any new claim needs a `recorded_run` with
the executed SHA; Q1 attributes to the runner SHA executed and S1b is
qualified at its own SHA (Q1b) or carries a reviewer-approved equivalence
argument; S2 and S3 acceptance records go through the shared coordinator via
the tool or its CLI adapter; the plan is self-contained; formatting-only
commits carry the AST proof and lint commits carry the suite.

Counterexample rejected: relabeling a Q1 measurement taken on the runner's
probe script at SHA X as evidence for the S1b product script at SHA Y.
R-QUAL-05 refuses promotion without Q1b or the explicit equivalence argument.

Acceptance test: catalog and response tests for provenance; record schema
requiring `executed_sha`; promotion test refusing a mismatched SHA; the
acceptance record template naming the entry point; `ast.dump` equality on
the formatting commit.

Owning slices: S1 (provenance), S1b and Q1b (HTTPS), S2 and S3 acceptance
records, every slice (packaging). Implementation evidence: the records.

---

---

## Part 3 — Correction review of revision 2.1 (C1 and C2)

Each entry reports: disposition; the revision 2.1 clauses deleted or
replaced; evidence from the disposable probes; the corrected contract; the
acceptance case; and what remains implementation evidence. Section and row
numbers refer to the revision 2.2 plan.

### C1a — FNV-1a equality cannot prove unchanged content [blocks S0]

**Disposition: Accepted; Extended.**

Deleted or replaced (revision 2.1 text):

- S0 prompt item 4: `changed = pre===null ? null : pre!==post` (deleted);
  "Digests: … pre and post" as the row's value fields (replaced by
  `pre_read`/`post_read` flags plus diagnostic digests); the row literal
  `{id,attempted:false,call_error:"",pre:null,post:null,ok:false,changed:null}`
  (replaced).
- Plan 4.4 runtime block: "pre/post are digests: … (helper defined once per
  script)" as the row contract (replaced by the eleven-field row and the
  sentence "Python derives no fact from them").
- Plan 4.5 "Mutation script contract (B1)" paragraph (replaced by the
  revision 2.2 paragraph); R-OBS-07 and R-HTTP-01 (rewritten).

Evidence (`probe_c1_rows.js`, scenario `collision_pair`, stub page
`yI76Uj5ZfPNL`, intended `INTENDED_WEB_PAGE`, setter stores
`qx51K0WT5Lj1`): the probe's own FNV-1a 32-bit gives `1bb90b62` for both
strings, both of length 12, so the revision 2.1 row reports
`pre="1bb90b62:12"`, `post="1bb90b62:12"`, `ok=false`, `changed=false`. Under
the revision 2.1 table that is row 13 (FAILED, `residual_change=False`) and
RD-10 yields CLEAN, while the stub state changed from one string to the
other. The revision 2.2 row on the same stub reports `changed=true` from the
typed comparison, which is row 14 (FAILED, `residual_change=True`) and
DIRTY_UNRECOVERABLE. A second defect surfaced in the same probe: with a
failed post-read the revision 2.1 rule compares a digest with `null` and
reports `changed=true` (scenario `post_read_failed`), a transition claim
without a completed read; revision 2.2 reports `changed=null` and row 8.

Corrected contract (plan 4.4, 4.5; prompt item 4): `ok` and `changed` are
computed inside the same script evaluation from the actual typed values
(`preValue !== postValue`; `postValue === intended`), `pre_read` and
`post_read` state whether each read completed, `ok` is null without a
post-read and `changed` is null without both reads; digests remain as
bounded diagnostics (`pre`, `post`) that Python never compares and from
which no fact is derived, and equal digests, equal lengths or a true native
return are never authority for UNCHANGED, SATISFIED or CLEAN. No hash
algorithm was substituted. Raw values are never serialized into rows,
journals or logs, and credentials never enter a digest or a `cause`.

Acceptance: harness scenarios "digest-collision pair", "unchanged failure",
"changed success", "unchanged success", "changed-to-wrong", "getter failure
(pre, post, both)" with expected values from the stub state (prompt item 6,
plan 6.5); RED entry "digest-collision pair" (baseline CLEAN). Probe result:
all C1a checks pass (`C1a typed changed equals truth` for every scenario with
both reads; `changed-to-wrong never clean` for every changed unsatisfied
scenario).

Owning slice: S0. Implementation evidence: the harness run under Node in
CI against the real generated script; nothing in this probe executes the
product runtime.

### C1b — An unchanged membership predicate does not prove an unchanged DNS table [blocks S0]

**Disposition: Accepted with modification.**

Deleted or replaced (revision 2.1 text):

- Plan 4.5 rows 11 to 14 as the only outcomes of a CORRELATED row with both
  reads (replaced: they now require footprint COVERED; rows 17 to 19 added
  for the skipped add and the PARTIAL footprint).
- R-OBS-07 claim "a fully successful run has `dirty_state=CLEAN`" (replaced
  by the COVERED-only claim plus the RD-11 claim for PARTIAL footprints);
  R-DNS-01 "add call unchanged; membership read before and after" (replaced:
  the add is skipped when the pre-read shows the record).
- RED entry "R-OBS-07: a fully successful apply … target CLEAN" (scoped to
  COVERED families; a DNS-record run now expects UNKNOWN with the named
  limitation).
- Plan 4.10 sample response `"dirty_state": "clean"` with a DNS record
  (replaced by `"unknown"` and the limitation).

Evidence (`probe_c1_rows.js`, DNS stub with an in-memory table; the wanted
record is `www.example.test -> 192.0.2.10`):

| Scenario | Table before → after | Membership pre/post | Revision 2.1 (row → journal) | Revision 2.2 (row → journal) |
| --- | --- | --- | --- | --- |
| `dns_add_incorrect_other_record` | `{}` → `{www: 192.0.2.11}` | false/false | 13 → FAILED, no residual → **CLEAN** | 19 → PARTIAL, disposition UNKNOWN, sticky → UNKNOWN |
| `dns_add_true_membership_absent` | `{}` → `{}` | false/false | 13 → CLEAN | 19 → UNKNOWN (indistinguishable from the row above by this observation) |
| `dns_add_replaces_existing` | `{www: 192.0.2.5}` → `{www: 192.0.2.10}` | false/true | 12 → CHANGED → **CLEAN** (the old record is gone) | 18 → APPLIED, disposition UNKNOWN, frontier open → UNKNOWN with `residue_unknown` |
| `dns_add_correct` | `{}` → `{www: 192.0.2.10}` | false/true | 12 → CLEAN | 18 → UNKNOWN with `residue_unknown` (footprint not observed) |
| `dns_add_already_present` | unchanged | true/true | 11 → REASSERTED (add called, repeat semantics unmeasured) | 17 → NO_OP, no add call, CLEAN |
| `dns_skip_then_post_false` | unchanged | true/false, no call | 14 → FAILED with residual → DIRTY_UNRECOVERABLE (a change this batch never made) | invalid row → 7 → APPLIED, UNKNOWN, sticky → UNKNOWN |

The first two rows are the correction's countermodel: the same
observation covers a changed and an unchanged table, so a false/false
membership can never justify CLEAN. The third row is a further case of the
same defect on the success side.

Corrected contract: each S0 family states its observed scope and effect
footprint in plan 4.5, and a new fact `footprint` (COVERED, PARTIAL,
NOT_APPLICABLE) travels with the row. A transition is proven only within the
state read. For an attempted `AddDnsRecord` the footprint is PARTIAL and the
decision returns residue UNKNOWN: the journal entry is disposition UNKNOWN
with cause `footprint_partial:dns_a_record_table`, `dirty_state` is UNKNOWN
by the baseline rule, and the E6 result carries
`residue_unknown:<id>:footprint_partial:dns_a_record_table`. The narrower
claims stay separate and explicit: the postcondition (SATISFIED or
UNSATISFIED) is reported on the action row, opens or closes the frontier and
drives the bundle status, so a run with a satisfied add may still be
VERIFIED; the unobserved residue is preserved in the journal and the
limitations. `residual_change=False` is defined as the absence of an observed
unintended change and is never read as proof that nothing changed (RD-10
text revised). The modification relative to the correction's literal text:
the ensure-present family now reads first and skips the add when the wanted
record is present (`attempted=false`, `skip_reason="already_satisfied"`),
which the 4.5 effect table already required ("pre-read then act") and which
is the only way a DNS-record action can have a known residue in S0 (no call,
no effect); it also removes the unmeasured repeat semantics of the add from
the product path. Widening the observation with the documented
`getSizeOfNameServerDb`/`getRrFromNameServerDbAt` readers is recorded as gate
M-DNS-4 and decision RD-11; S0 does not call them and adds no other
enumeration. No generic evidence subsystem was added: the uncertainty rides
on the existing disposition UNKNOWN, the existing `cause` field and the
existing limitations list.

Consequence stated for review (RD-11): a first run that adds a DNS record
reports `dirty_state=UNKNOWN` although its services may be VERIFIED; a
re-run that finds the record is NO_OP and CLEAN. This is the honest reading
of the API surface S0 may use; the plan's positive CLEAN test is scoped to
COVERED families (EnableDnsService, EnableHttpService, SetHttpContent).

Acceptance: harness scenarios "add returns true, membership missing",
"incorrect add changes another record", "add replaces an existing record",
"add already present" (with the stub's call log proving no add call) and
"skipped row whose post-read contradicts its pre-read"; RED entries C1b and
the scoped R-OBS-07 entry. Probe result: every DNS scenario matches the
expectation derived from the stub table; no scenario with an attempted add
reaches CLEAN.

Owning slice: S0. Implementation evidence: the harness run; the applicator
tests asserting the limitation and the journal disposition.

### C2a — Row 10 disagrees with two prompt clauses [blocks S0]

**Disposition: Accepted.**

Deleted or replaced (revision 2.1 text):

- Plan 4.5 paragraph "Row 10 is the one case the shared journal cannot
  represent exactly … sets the sticky flag so `dirty_state` becomes UNKNOWN
  rather than CLEAN" (deleted; replaced by the paragraph on rows 9, 10, 18
  and 19).
- Plan 4.5 row 10 "FAILED | PARTIAL | POSTCONDITION_UNSATISFIED, cause
  `pre_read_failed` | unknown (journal: FAILED without residual; limitation
  `residual_unknown`) | blocked | yes" (replaced).
- S0 prompt item 4 "post known and pre null -> transition UNOBSERVED,
  disposition UNKNOWN (transition unknown, status still APPLIED when ok),
  cause `pre_read_failed`" and the derivation list "disposition REASSERTED
  (SATISFIED+UNCHANGED), CHANGED (SATISFIED+CHANGED), FAILED with
  residual_change False (UNSATISFIED+UNCHANGED), FAILED with residual_change
  True (UNSATISFIED+CHANGED)" (deleted; the runtime now maps rows to fact
  tuples by row number and the decision owns every output).
- S0 prompt item 5 "call execution_journal.mark_transport_unknown() whenever
  any action result has postcondition UNOBSERVED and dispatch not in
  {NOT_SUBMITTED, REJECTED}; that covers …" (deleted; replaced by "exactly
  when any decision has sticky True").

Evidence (`probe_c2_decision.py`, `rev21_row10_variants`): the three
revision 2.1 texts applied to the row 10 facts give three readings and two
journal outcomes: the table alone (FAILED disposition plus its own sticky
column) yields UNKNOWN; the table's FAILED disposition combined with item 5's
predicate (which is false for UNSATISFIED) yields **CLEAN**; item 4's UNKNOWN
disposition combined with item 5 yields UNKNOWN. The checker records
`{"table_alone": "unknown", "table_disposition_plus_item5": "clean",
"item4_disposition_plus_item5": "unknown"}`.

Corrected contract: row 10 is defined once in `decide_mutation`: status
PARTIAL, disposition UNKNOWN, `POSTCONDITION_UNSATISFIED`, cause
`pre_read_failed`, residue UNKNOWN, frontier closed, sticky True. `sticky`
and `frontier` are outputs of the decision; the applicator calls
`mark_transport_unknown()` exactly when any decision is sticky and computes
`effect_established` from the decision's `frontier`. No field predicate
re-derives either. The revision 2.1 limitation `residual_unknown` is replaced
by the uniform `residue_unknown:<id>:<cause>` limitation used by every
unknown-residue row.

Acceptance (correction item 1): probe checks `A1 row 10 status PARTIAL`,
`A1 row 10 sticky retained`, `A1 row 10 never clean` (journal UNKNOWN from
both the disposition and the sticky flag), `A1 row 10 frontier closed`; the
two demonstration checks record that the revision 2.1 texts disagreed and
that one combination produced CLEAN. All pass.

Owning slice: S0. Implementation evidence: the decision-table test through
the real `journal_from_action_results` and applicator.

### C2b — Exceptional and inconsistent facts need explicit precedence [blocks S0]

**Disposition: Accepted; Extended.**

Deleted or replaced (revision 2.1 text):

- S0 prompt item 1, the list "(a) `postcondition is UNSATISFIED` -> PARTIAL;
  (b) `not applied` and `dispatch` in {NOT_SUBMITTED, REJECTED, UNSPECIFIED}
  -> FAILED; (c) … -> UNKNOWN; (d) `applied`: … ; (e) an inconsistent row
  (…) -> UNKNOWN" (deleted; replaced by `decide_mutation` with legacy
  detection, admission and the inconsistent fallback in that order).
- S0 prompt item 1 "`residual_change: bool = False`" on
  `RuntimeActionMutation` (deleted as an input; residue is a decision
  output on `ActionApplicationResult` and the journal entry).
- Plan 4.4 "`mutation_execution_status`: the decision table of 4.5"
  (replaced by `decide_mutation` plus the status projection).
- Plan 4.5 "Mutation frontier: `effect_established(result)` is
  `postcondition is SATISFIED`, or …" (replaced by the decision's
  `frontier`).

Evidence (`probe_c2_decision.py`): the literal item 1(b) returns FAILED for
the row 15 tuple (dispatch UNSPECIFIED, postcondition UNOBSERVED, `applied`
False) although the table says UNKNOWN with `SESSION_FAILED`
(`A2 … literal gives FAILED (demonstration)`). The literal item 1 order
returns APPLIED for NOT_SUBMITTED / CORRELATED / SATISFIED with
`applied=True`, and item 5's `effect_established` then opens the frontier on
the invalid SATISFIED field (`A3 rev2.1 literal order … opens the frontier
(demonstration)`).

Corrected contract: `decide_mutation` evaluates (a) legacy detection on
every new fact at its default, including `footprint` and `attempted`, so the
legacy branch never captures an exception row; (b) admission against the
listed rows, with `applied` required to equal `dispatch is ACCEPTED`; (c) the
inconsistent fallback (UNKNOWN, disposition UNKNOWN, `OUTCOME_UNKNOWN`,
residue UNKNOWN, closed, sticky, `inconsistent_facts`). The received facts
stay on the result as diagnostics; every consumer (applicator, journal
builder, evidence mapper, aggregation) reads only the decision outputs, so a
SATISFIED inside an inconsistent tuple is never trusted afterwards. Row 15
(exception; no dispatch fact) and row 7 (invalid row after proven channel
acceptance) keep distinct statuses (UNKNOWN + `SESSION_FAILED` versus
APPLIED + `RESPONSE_MALFORMED`), as the correction requires. Extension:
making the table total for every S0 family required a row for the declined
`PublishTftpFile` script (row 20: FAILED, `APPLICATION_FAILED`, residue NONE,
not sticky), which preserves its baseline FAILED outcome instead of letting
an unimplemented family poison the run with sticky uncertainty; and the
baseline `journal_from_action_results` fallback (`disposition_from_status`)
was checked against the UNKNOWN dispositions of rows 9, 10, 18 and 19, which
survive it because APPLIED and PARTIAL are not in its map.

Acceptance (correction items 2 to 6): probe checks `A2 row 15
UNKNOWN/SESSION_FAILED`; `A3 invalid SATISFIED -> frontier closed`, `-> UNKNOWN
sticky`, `raw postcondition preserved as diagnostic`, `dirty unknown` for
five invalid tuples; `A4 accepted+engine_error/malformed/lost/not_observed
uncertain`; `P4` legacy identity for every baseline disposition and both
`applied` values against the copied baseline functions; the full product of
the seven inputs (8640 tuples: 29 admitted, 8611 inconsistent) under `P1`
(frontier only on a validated SATISFIED or a legacy row), `P2` (a CLEAN
single-entry journal only with residue NONE and no sticky), `P3`
(inconsistent tuples UNKNOWN, closed, sticky, never CLEAN), `P10` (residue
UNKNOWN never CLEAN and always named in the limitations), `P11` (sticky never
VERIFIED) and `P12` (the builder keeps UNKNOWN for fact-bearing rows); `R`
JSON round trip re-decides identically and preserves the journal entry's
UNKNOWN disposition and cause; the C1 rows survive mapping, application,
journal, serialization and the evidence representation with the expected
values. All pass.

Owning slice: S0. Implementation evidence: the decision-table test in
`tests/test_execution_status_facts.py` with these predicates as its oracle,
the round-trip test of item 5, and the harness.

### Mutual consistency of the three deliverables

The plan's section 7.1 is the standalone prompt verbatim (byte-identical
over the fenced block). Items 2, 3, 7, 8 and 9 of the prompt are
byte-identical to revision 2.1. The plan changed only in the title and
header, the change log, RD-10/RD-11, section 2.2 (one line), section 3.3
(one gate row), the six requirement rows named above, sections 4.4, 4.5,
4.10, the S0 slice table, sections 6.3, 6.5, 7.1, 7.3 and Appendix B. B3's
inventory table in 6.5 and the G1 to G4 sections are untouched. The
countermodels of the correction no longer permit a false CLEAN (probe
scenarios `collision_pair`, `dns_add_incorrect_other_record`,
`dns_add_replaces_existing`, row 10) or an unsafe dependency admission
(invalid SATISFIED tuples). Actual repository verification remains the
implementer's later obligation, followed by independent review.

---

## Technical-director positions (RD-1 to RD-4) as reflected in revision 2.1

| Decision | How revision 2.1 satisfies the position |
| --- | --- |
| RD-1 | application owns the workflow; the adapter composes and translates; E5 scope is the closure of the bounded topology with P-E5-2, disclosed, pre-read for endpoints; no whole-plan reapplication; foundation promotion limited to the exact IPv4/netmask core per action id; E5 effect uncertainty stops the run |
| RD-2 | `derive_service_policy` runs once in composition before E5 compilation; per-segment delegation; client `SetEndpointDhcp` preserved; conflicts refused |
| RD-3 | client actions typed with `host_device_id` = client; capability resolved for the target model and operation; service owner on `ServiceDefinition` |
| RD-4 | register-then-poll kept as a candidate with pre-effect claims, quarantine and observer cleanup; capability UNKNOWN until Q0; fallback set defined |

## Consistency checks performed on the deliverables

- The embedded S0 prompt in plan section 7.1 was produced by inserting the
  standalone `Server-PT-Services-Implementer-Prompt-S0-rev2.2.md` verbatim
  and compared byte for byte after generation.
- The plan was generated from the revision 2.1 file by anchored line-range
  edits; every anchor was asserted before replacement; the untouched
  sections are byte-identical to revision 2.1.
- Every requirement still names its owning slice and test level (plan
  6.2); no requirement id was added or removed.
- The disposable probes were run on this machine and their sources and
  output are in the appendix and in `Server-PT-Services-rev2.2-probes/`;
  they are specification-consistency probes, not repository pytest or LIVE
  evidence, and the S0 tests must execute the real generator, applicator,
  journal and serializer.
- Unmeasured runtime facts remain gates (M-ENG-1, M-UNREG-1/2, the
  atomicity inference, M-HTTPS-1/2, M-DNS-1/2/3/4, M-MAIL-1/2/3,
  M-POP3-1/2, M-DHCP-1..6); none is treated as measured.

---

## Appendix — Disposable probe sources and recorded output

Reproduce with Node 24 and CPython 3.11+ from any directory (no repository
import):

```text
node probe_c1_rows.js > c1_rows.json
python probe_c2_decision.py c1_rows.json
```

### probe_c1_rows.js

```javascript
'use strict';
// Disposable contract probe for finding C1 (Server-PT plan revision 2.2).
// It is NOT product code and executes no repository module. It evaluates two
// mutation-row contracts against in-memory stub processes:
//   rev21: digests compared to derive `changed` (Server-PT-Services-Implementer-Prompt-S0-rev2.1.md, item 4)
//   rev22: typed before/after values compared inside the same evaluation; digests diagnostic only
// The truth of every scenario is the stub's actual state, printed next to the rows.

function fnv1a32(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return (h >>> 0).toString(16).padStart(8, '0');
}
function digest(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === 'boolean') return v ? '1' : '0';
  const s = String(v);
  return fnv1a32(s) + ':' + s.length;
}

// ---- rev2.1 row (item 4): `changed = pre===null ? null : pre!==post` on digests ----
function rev21Row(id, read, setter, satisfied) {
  const r = { id, attempted: false, call_error: '', call_result: null, pre: null, post: null, ok: false, changed: null };
  try { r.pre = digest(read()); } catch (e) { r.pre = null; }
  try { r.attempted = true; const cr = setter(); if (cr !== undefined) r.call_result = !!cr; } catch (e) { r.call_error = String(e && e.message || e); }
  try { const post = read(); r.post = digest(post); r.ok = satisfied(post); } catch (e) { r.post = null; r.ok = false; }
  r.changed = r.pre === null ? null : (r.pre !== r.post);
  return r;
}

// ---- rev2.2 row: typed comparison; unconditional post-read; ensure-present skip ----
function rev22Row(id, family, read, setter, satisfied) {
  const r = { id, attempted: false, skip_reason: '', call_error: '', call_result: null,
              pre_read: false, post_read: false, ok: null, changed: null, pre: null, post: null };
  let preV, postV;
  try { preV = read(); r.pre_read = true; r.pre = digest(preV); } catch (e) { r.pre_read = false; }
  if (family === 'ensure_present' && r.pre_read && satisfied(preV)) {
    r.skip_reason = 'already_satisfied';
  } else {
    r.attempted = true;
    try { const cr = setter(); if (family === 'ensure_present') r.call_result = !!cr; }
    catch (e) { r.call_error = String(e && e.message || e).slice(0, 200); }
  }
  try { postV = read(); r.post_read = true; r.post = digest(postV); r.ok = satisfied(postV); } catch (e) { r.post_read = false; }
  if (r.pre_read && r.post_read) r.changed = (preV !== postV);
  return r;
}

// ---- stubs ----
function pageStub(initial, behavior) {
  const state = { page: initial, reads: 0 };
  const read = () => {
    state.reads += 1;
    if (behavior.failRead && behavior.failRead.includes(state.reads)) throw new Error('getter_failed');
    return String(state.page);
  };
  const setter = () => {
    if (behavior.store !== undefined) state.page = behavior.store;
    if (behavior.throwAfter) throw new Error('setter_threw');
  };
  return { state, read, setter, snapshot: () => state.page };
}
function dnsStub(initialTable, behavior) {
  const state = { table: Object.assign({}, initialTable), reads: 0 };
  const wanted = behavior.wanted;
  const read = () => {
    state.reads += 1;
    if (behavior.failRead && behavior.failRead.includes(state.reads)) throw new Error('getter_failed');
    if (behavior.flipSecondRead && state.reads === 2) return false;
    return state.table[wanted.name] === wanted.address;
  };
  const setter = () => {
    if (behavior.store) state.table[wanted.name] = behavior.store;
    return behavior.returns === undefined ? true : behavior.returns;
  };
  return { state, read, setter, snapshot: () => JSON.stringify(state.table) };
}

const INTENDED = 'INTENDED_WEB_PAGE';
const W = { name: 'www.example.test', address: '192.0.2.10' };
const scenarios = [
  // page family (footprint COVERED: the observed page is the documented footprint of setPageContents)
  { id: 'collision_pair', family: 'page', make: () => pageStub('yI76Uj5ZfPNL', { store: 'qx51K0WT5Lj1' }), intended: INTENDED },
  { id: 'unchanged_failure', family: 'page', make: () => pageStub('page-A', {}), intended: 'page-B' },
  { id: 'changed_success', family: 'page', make: () => pageStub('page-A', { store: 'page-B' }), intended: 'page-B' },
  { id: 'unchanged_success', family: 'page', make: () => pageStub('page-B', { store: 'page-B' }), intended: 'page-B' },
  { id: 'changed_to_wrong', family: 'page', make: () => pageStub('page-A', { store: 'page-C' }), intended: 'page-B' },
  { id: 'setter_effect_then_throw', family: 'page', make: () => pageStub('page-A', { store: 'page-C', throwAfter: true }), intended: 'page-B' },
  { id: 'pre_read_failed_success', family: 'page', make: () => pageStub('page-A', { store: 'page-B', failRead: [1] }), intended: 'page-B' },
  { id: 'pre_read_failed_wrong', family: 'page', make: () => pageStub('page-A', { store: 'page-C', failRead: [1] }), intended: 'page-B' },
  { id: 'post_read_failed', family: 'page', make: () => pageStub('page-A', { store: 'page-B', failRead: [2] }), intended: 'page-B' },
  { id: 'both_reads_failed', family: 'page', make: () => pageStub('page-A', { store: 'page-B', failRead: [1, 2] }), intended: 'page-B' },
  // DNS family (footprint PARTIAL when the add is attempted: only the wanted membership is read)
  { id: 'dns_add_correct', family: 'ensure_present', make: () => dnsStub({}, { wanted: W, store: W.address }) },
  { id: 'dns_add_incorrect_other_record', family: 'ensure_present', make: () => dnsStub({}, { wanted: W, store: '192.0.2.11' }) },
  { id: 'dns_add_true_membership_absent', family: 'ensure_present', make: () => dnsStub({}, { wanted: W, returns: true }) },
  { id: 'dns_add_already_present', family: 'ensure_present', make: () => dnsStub({ [W.name]: W.address }, { wanted: W, store: W.address }) },
  { id: 'dns_add_replaces_existing', family: 'ensure_present', make: () => dnsStub({ [W.name]: '192.0.2.5' }, { wanted: W, store: W.address }) },
  { id: 'dns_add_pre_read_failed', family: 'ensure_present', make: () => dnsStub({}, { wanted: W, store: W.address, failRead: [1] }) },
  { id: 'dns_skip_then_post_false', family: 'ensure_present', make: () => dnsStub({ [W.name]: W.address }, { wanted: W, flipSecondRead: true }) },
];

const out = [];
for (const sc of scenarios) {
  const satisfied = sc.family === 'page' ? (v) => v === sc.intended : (v) => v === true;
  const a = sc.make(); const before = a.snapshot();
  const r21 = rev21Row(sc.id, a.read, a.setter, satisfied);
  const after21 = a.snapshot();
  const b = sc.make();
  const r22 = rev22Row(sc.id, sc.family, b.read, b.setter, satisfied);
  const after22 = b.snapshot();
  const truthAfter = after22;
  out.push({
    scenario: sc.id, family: sc.family,
    truth: { before, after: truthAfter, state_changed: before !== truthAfter,
             satisfied: sc.family === 'page' ? truthAfter === sc.intended : (JSON.parse(truthAfter)[W.name] === W.address),
             same_state_both_runs: after21 === after22 },
    rev21: r21, rev22: r22,
  });
}
process.stdout.write(JSON.stringify({ fnv_check: { a: fnv1a32('yI76Uj5ZfPNL'), b: fnv1a32('qx51K0WT5Lj1') }, scenarios: out }, null, 1) + '\n');
```

### probe_c2_decision.py

```python
"""Disposable specification-consistency checker for findings C1 and C2 (plan revision 2.2).

Not product code; executes no repository module. It models:
  BASELINE  pure functions copied by hand from main@6263344 (execution.py, configuration_runtime.py)
  REV21     the competing revision 2.1 rules (table row 10, prompt item 4, prompt item 5, item 1(b))
  REV22     the single canonical decision of revision 2.2, the RD-10 journal rule, the runtime
            row-to-facts mapping, the applicator sticky/frontier rules, a JSON round trip and the
            run-level evidence representation.
Oracles: safety predicates over the full fact product, the baseline functions for legacy rows, and
the stub truth recorded by probe_c1_rows.js. The classifier is never compared with itself.
Run:  python probe_c2_decision.py c1_rows.json
"""
import itertools
import json
import sys
from collections import namedtuple

# ----------------------------------------------------------------------------- BASELINE (copied)
def baseline_status(applied, disposition):
    if not applied:
        return "failed"
    if disposition == "no_op":
        return "no_op"
    if disposition == "reasserted":
        return "reasserted"
    return "applied"

def disposition_from_status(status):
    return {"no_op": "no_op", "reasserted": "reasserted", "failed": "failed",
            "dependency_blocked": "blocked", "skipped": "skipped"}.get(status, "unknown")

def satisfies_apply_dependency(status):
    return status in {"applied", "no_op", "reasserted", "verified"}

SEV = {"clean": 0, "dirty_recoverable": 1, "unknown": 2, "dirty_unrecoverable": 3}

def derive_dirty_state(entries, rd10):
    if not entries:
        return "clean"
    if any(e["disposition"] == "unknown" for e in entries):
        return "unknown"
    failed = any(e["disposition"] == "failed" for e in entries)
    mutations = [e for e in entries if e["disposition"] in {"changed", "reasserted"}
                 or (rd10 and e["disposition"] == "failed" and e["residual_change"])]
    if not failed:
        return "clean"
    if not mutations:
        return "clean"
    if all(e["inverse_available"] for e in mutations):
        return "dirty_recoverable"
    return "dirty_unrecoverable"

def journal_dirty(entries, sticky, rd10=True):
    floors = [derive_dirty_state(entries, rd10)]
    if sticky:
        floors.append("unknown")
    return max(floors, key=SEV.get)

def journal_entry(result):
    """Models journal_from_action_results: an UNKNOWN disposition falls back to the status map."""
    explicit = result["disposition"]
    disp = explicit if explicit != "unknown" else disposition_from_status(result["status"])
    return {"disposition": disp, "inverse_available": False,
            "residual_change": result.get("residual_change", False), "cause": result.get("cause", ""),
            "dispatch": result["dispatch"], "result": result["result"]}

# ----------------------------------------------------------------------------- REV22 decision
DISPATCH = ["not_submitted", "rejected", "accepted", "acceptance_unknown", "unspecified"]
RESULT = ["correlated", "engine_error", "malformed", "not_observed", "lost", "not_applicable"]
POST = ["satisfied", "unsatisfied", "unobserved", "not_applicable"]
TRANS = ["unchanged", "changed", "unobserved", "not_applicable"]
FOOT = ["covered", "partial", "not_applicable"]
ATTEMPTED = [True, False, None]
APPLIED = [True, False]
BASE_DISPOSITIONS = ["changed", "no_op", "reasserted", "failed", "blocked", "skipped", "unknown"]

Facts = namedtuple("Facts", "dispatch result postcondition transition footprint attempted applied disposition_in cause_in")

def is_legacy(f):
    return (f.dispatch == "unspecified" and f.result == "not_applicable" and f.postcondition == "not_applicable"
            and f.transition == "not_applicable" and f.footprint == "not_applicable" and f.attempted is None)

def D(status, disposition, code, residue, frontier, sticky, cause=""):
    return {"status": status, "disposition": disposition, "failure_code": code, "residue": residue,
            "frontier": frontier, "sticky": sticky, "cause": cause}

ROWS = [
    ("1", lambda f: f == f._replace(disposition_in=f.disposition_in, cause_in=f.cause_in) and (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("not_submitted", "not_applicable", "not_applicable", "not_applicable", "not_applicable", None, False),
     lambda f: D("failed", "failed", "application_failed", "none", False, False, "not_submitted")),
    ("2", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("rejected", "not_applicable", "not_applicable", "not_applicable", "not_applicable", None, False),
     lambda f: D("failed", "failed", "application_failed", "none", False, False, "rejected")),
    ("3", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("acceptance_unknown", "not_observed", "unobserved", "unobserved", "not_applicable", None, False),
     lambda f: D("unknown", "unknown", "outcome_unknown", "unknown", False, True, "acceptance_unknown")),
    ("4", lambda f: f.dispatch == "accepted" and f.result in {"not_observed", "lost"} and (f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("unobserved", "unobserved", "not_applicable", None, True),
     lambda f: D("applied", "unknown", "outcome_unknown", "unknown", False, True, f.result)),
    ("5", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("accepted", "engine_error", "unobserved", "unobserved", "not_applicable", None, True),
     lambda f: D("applied", "unknown", "outcome_unknown", "unknown", False, True, "engine_error")),
    ("6", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("accepted", "malformed", "unobserved", "unobserved", "not_applicable", None, True),
     lambda f: D("applied", "unknown", "response_malformed", "unknown", False, True, "malformed")),
    ("7", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("accepted", "correlated", "unobserved", "unobserved", "not_applicable", None, True),
     lambda f: D("applied", "unknown", "response_malformed", "unknown", False, True, f.cause_in or "row_missing")),
    ("8", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.applied) == ("accepted", "correlated", "unobserved", "unobserved", True) and f.footprint in {"covered", "partial"} and f.attempted in {True, False},
     lambda f: D("applied", "unknown", "outcome_unknown", "unknown", False, True, "post_read_failed")),
    ("9", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.attempted, f.applied) == ("accepted", "correlated", "satisfied", "unobserved", True, True) and f.footprint in {"covered", "partial"},
     lambda f: D("applied", "unknown", "none", "unknown", True, False, "pre_read_failed")),
    ("10", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.attempted, f.applied) == ("accepted", "correlated", "unsatisfied", "unobserved", True, True) and f.footprint in {"covered", "partial"},
     lambda f: D("partial", "unknown", "postcondition_unsatisfied", "unknown", False, True, "pre_read_failed")),
    ("11", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("accepted", "correlated", "satisfied", "unchanged", "covered", True, True),
     lambda f: D("reasserted", "reasserted", "none", "none", True, False)),
    ("12", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("accepted", "correlated", "satisfied", "changed", "covered", True, True),
     lambda f: D("applied", "changed", "none", "none", True, False)),
    ("13", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("accepted", "correlated", "unsatisfied", "unchanged", "covered", True, True),
     lambda f: D("partial", "failed", "postcondition_unsatisfied", "none", False, False, "postcondition_unsatisfied")),
    ("14", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("accepted", "correlated", "unsatisfied", "changed", "covered", True, True),
     lambda f: D("partial", "failed", "postcondition_unsatisfied", "changed", False, False, "postcondition_unsatisfied")),
    ("15", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("unspecified", "not_applicable", "unobserved", "unobserved", "not_applicable", None, False),
     lambda f: D("unknown", "unknown", "session_failed", "unknown", False, True, f.cause_in or "exception")),
    ("17", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("accepted", "correlated", "satisfied", "unchanged", "covered", False, True),
     lambda f: D("no_op", "no_op", "none", "none", True, False, "skipped:already_satisfied")),
    ("18", lambda f: (f.dispatch, f.result, f.postcondition, f.footprint, f.attempted, f.applied) == ("accepted", "correlated", "satisfied", "partial", True, True) and f.transition in {"changed", "unchanged"},
     lambda f: D("applied", "unknown", "none", "unknown", True, False, "footprint_partial")),
    ("19", lambda f: (f.dispatch, f.result, f.postcondition, f.footprint, f.attempted, f.applied) == ("accepted", "correlated", "unsatisfied", "partial", True, True) and f.transition in {"changed", "unchanged"},
     lambda f: D("partial", "unknown", "postcondition_unsatisfied", "unknown", False, True, "footprint_partial")),
    ("20", lambda f: (f.dispatch, f.result, f.postcondition, f.transition, f.footprint, f.attempted, f.applied) == ("accepted", "correlated", "unobserved", "not_applicable", "not_applicable", False, True),
     lambda f: D("failed", "failed", "application_failed", "none", False, False, "not_attempted:family_not_implemented")),
]

def decide(f):
    """The single canonical decision: legacy detection, then admitted rows, else inconsistent."""
    if is_legacy(f):
        status = baseline_status(f.applied, f.disposition_in)
        d = D(status, f.disposition_in, "baseline", "none", satisfies_apply_dependency(status), False, "")
        d["row"] = "16"
        return d
    for row_id, pred, outputs in ROWS:
        if pred(f):
            d = outputs(f)
            d["row"] = row_id
            return d
    d = D("unknown", "unknown", "outcome_unknown", "unknown", False, True, "inconsistent_facts")
    d["row"] = "inconsistent"
    return d

# ----------------------------------------------------------------------------- REV22 runtime mapping
FAMILY_FOOTPRINT = {"page": "covered", "flag": "covered", "ensure_present": "partial"}

def validate_row(row):
    b = (True, False)
    if not (isinstance(row.get("attempted"), bool) and isinstance(row.get("pre_read"), bool) and isinstance(row.get("post_read"), bool)):
        return "types"
    if row.get("ok") not in (True, False, None) or row.get("changed") not in (True, False, None):
        return "types"
    if not isinstance(row.get("call_error"), str) or not isinstance(row.get("skip_reason"), str):
        return "types"
    if row["post_read"] is False and (row["ok"] is not None or row["changed"] is not None):
        return "ok_or_changed_without_post_read"
    if row["pre_read"] is False and row["changed"] is not None:
        return "changed_without_pre_read"
    if row["pre_read"] and row["post_read"] and (row["ok"] is None or row["changed"] is None):
        return "missing_ok_or_changed"
    if row["attempted"] is False:
        if row["skip_reason"] not in {"already_satisfied", "family_not_implemented"} or row["call_result"] is not None or row["call_error"]:
            return "skip_shape"
        if row["skip_reason"] == "already_satisfied" and not (row["pre_read"] and (row["post_read"] is False or row["ok"] is True)):
            return "skipped_but_unsatisfied"
        if row["skip_reason"] == "family_not_implemented" and (row["pre_read"] or row["post_read"]):
            return "declined_with_reads"
    elif row["skip_reason"]:
        return "skip_reason_with_attempt"
    return None

def facts_from_row(family, row):
    err = validate_row(row)
    if err:
        return Facts("accepted", "correlated", "unobserved", "unobserved", "not_applicable", None, True, "unknown", "row_invalid:" + err)
    if row["attempted"] is False and row["skip_reason"] == "family_not_implemented":
        return Facts("accepted", "correlated", "unobserved", "not_applicable", "not_applicable", False, True, "unknown", "not_attempted:family_not_implemented")
    footprint = FAMILY_FOOTPRINT[family] if row["attempted"] else "covered"
    cause = row["call_error"]
    if not row["post_read"]:
        return Facts("accepted", "correlated", "unobserved", "unobserved", footprint, row["attempted"], True, "unknown", "post_read_failed" + (":" + cause if cause else ""))
    post = "satisfied" if row["ok"] else "unsatisfied"
    if not row["pre_read"]:
        return Facts("accepted", "correlated", post, "unobserved", footprint, row["attempted"], True, "unknown", "pre_read_failed" + (":" + cause if cause else ""))
    trans = "changed" if row["changed"] else "unchanged"
    return Facts("accepted", "correlated", post, trans, footprint, row["attempted"], True, "unknown", cause)

def apply_action(f):
    """Applicator: decision -> result row (facts preserved as received + decision outputs)."""
    d = decide(f)
    return {"dispatch": f.dispatch, "result": f.result, "postcondition": f.postcondition, "transition": f.transition,
            "footprint": f.footprint, "attempted": f.attempted, "applied": f.applied,
            "status": d["status"], "disposition": d["disposition"], "failure_code": d["failure_code"],
            "residual_change": d["residue"] == "changed", "residue": d["residue"], "frontier": d["frontier"],
            "sticky": d["sticky"], "cause": (f.cause_in or d["cause"]), "row": d["row"]}

def run_result(results):
    """E6 run-level representation: journal dirty_state, sticky flag, limitations, bundle status."""
    entries = [journal_entry(r) for r in results]
    sticky = any(r["sticky"] for r in results)
    dirty = journal_dirty(entries, sticky)
    limitations = [f"residue_unknown:{i}:{r['cause']}" for i, r in enumerate(results) if r["residue"] == "unknown"]
    limitations += [f"effect_uncertain:{i}" for i, r in enumerate(results) if r["sticky"]]
    bundle = "verified" if (not sticky and all(r["frontier"] for r in results)) else "partial"
    return {"dirty_state": dirty, "transport_unknown": sticky, "limitations": limitations, "bundle": bundle, "entries": entries}

# ----------------------------------------------------------------------------- REV21 competing rules
def rev21_row10_variants():
    """Row 10 under the three revision 2.1 texts: the table, item 4 and item 5."""
    table = {"status": "partial", "disposition": "failed", "residual_change": False, "sticky": True}
    item4 = {"status": "partial", "disposition": "unknown", "residual_change": False, "sticky": None}
    item5_sticky = False  # postcondition UNSATISFIED is not UNOBSERVED
    out = {}
    out["table_alone"] = journal_dirty([{"disposition": table["disposition"], "residual_change": False, "inverse_available": False}], table["sticky"])
    out["table_disposition_plus_item5"] = journal_dirty([{"disposition": table["disposition"], "residual_change": False, "inverse_available": False}], item5_sticky)
    out["item4_disposition_plus_item5"] = journal_dirty([{"disposition": item4["disposition"], "residual_change": False, "inverse_available": False}], item5_sticky)
    return out

def rev21_item1_status(applied, dispatch, postcondition, disposition):
    """Literal prompt item 1 order: (a) UNSATISFIED, (b)/(c) not applied, (d) applied, (e) inconsistent."""
    if postcondition == "unsatisfied":
        return "partial"
    if not applied and dispatch in {"not_submitted", "rejected", "unspecified"}:
        return "failed"
    if not applied and dispatch == "acceptance_unknown":
        return "unknown"
    if applied:
        return {"no_op": "no_op", "reasserted": "reasserted"}.get(disposition, "applied")
    return "unknown"

def rev21_item5_effect_established(postcondition, status):
    return postcondition == "satisfied" or (postcondition == "not_applicable" and satisfies_apply_dependency(status))

def rev21_facts_from_row(r):
    """Prompt item 4 derivation on a revision 2.1 row (digest-based `changed`)."""
    if r["post"] is None:
        return {"postcondition": "unobserved", "transition": "unobserved", "disposition": "unknown", "residual_change": False, "sticky": True}
    if r["pre"] is None:
        return {"postcondition": "satisfied" if r["ok"] else "unsatisfied", "transition": "unobserved", "disposition": "unknown", "residual_change": False, "sticky": False}
    post = "satisfied" if r["ok"] else "unsatisfied"
    trans = "changed" if r["changed"] else "unchanged"
    if post == "satisfied":
        return {"postcondition": post, "transition": trans, "disposition": "changed" if r["changed"] else "reasserted", "residual_change": False, "sticky": False}
    return {"postcondition": post, "transition": trans, "disposition": "failed", "residual_change": bool(r["changed"]), "sticky": False}

# ----------------------------------------------------------------------------- checks
failures = []
def check(name, cond, detail=""):
    if not cond:
        failures.append(f"{name}: {detail}")

# 1. Full product: every tuple has exactly one decision; safety predicates.
product = list(itertools.product(DISPATCH, RESULT, POST, TRANS, FOOT, ATTEMPTED, APPLIED))
counts = {}
for t in product:
    f = Facts(*t, "unknown", "")
    d = decide(f)
    counts[d["row"]] = counts.get(d["row"], 0) + 1
    r = apply_action(f)
    run = run_result([r])
    if d["frontier"]:
        check("P1 frontier only on validated SATISFIED", f.postcondition == "satisfied" or d["row"] == "16", str(t))
        check("P1b frontier never on an inconsistent tuple", d["row"] != "inconsistent", str(t))
    if run["dirty_state"] == "clean":
        check("P2 clean only with residue NONE and no sticky", d["residue"] == "none" and not d["sticky"], str(t))
    if d["row"] == "inconsistent":
        check("P3 inconsistent -> UNKNOWN/blocked/sticky", d["status"] == "unknown" and d["disposition"] == "unknown" and not d["frontier"] and d["sticky"] and d["residue"] == "unknown", str(t))
        check("P3b inconsistent tuple never clean", run["dirty_state"] == "unknown", str(t))
    if d["residue"] == "unknown":
        check("P10 residue unknown never clean", run["dirty_state"] != "clean", str(t))
        check("P10b residue unknown named in limitations", any(l.startswith("residue_unknown:") for l in run["limitations"]), str(t))
    if d["sticky"]:
        check("P11 sticky -> bundle never verified", run["bundle"] != "verified", str(t))
    # journal fallback never launders an UNKNOWN disposition into a mutation
    if r["disposition"] == "unknown" and d["row"] != "16":
        check("P12 builder keeps UNKNOWN for fact-bearing rows", run["entries"][0]["disposition"] == "unknown", str(t))

# 2. Legacy rows equal the baseline for every baseline disposition x applied.
for disp in BASE_DISPOSITIONS:
    for applied in APPLIED:
        f = Facts("unspecified", "not_applicable", "not_applicable", "not_applicable", "not_applicable", None, applied, disp, "")
        d = decide(f)
        check("P4 legacy status == baseline", d["status"] == baseline_status(applied, disp), f"{disp} {applied}: {d['status']}")
        check("P4b legacy frontier == satisfies_apply_dependency", d["frontier"] == satisfies_apply_dependency(d["status"]), f"{disp} {applied}")
        check("P4c legacy not sticky", not d["sticky"], f"{disp} {applied}")
        run = run_result([apply_action(f)])
        base_entry = {"disposition": disp if disp != "unknown" else disposition_from_status(baseline_status(applied, disp)), "residual_change": False, "inverse_available": False}
        check("P4d legacy dirty_state == baseline derive", run["dirty_state"] == derive_dirty_state([base_entry], rd10=False), f"{disp} {applied}: {run['dirty_state']}")

# 3. Acceptance item 1: row 10.
f10 = Facts("accepted", "correlated", "unsatisfied", "unobserved", "covered", True, True, "unknown", "")
d10 = decide(f10); run10 = run_result([apply_action(f10)])
check("A1 row 10 status PARTIAL", d10["status"] == "partial", d10["status"])
check("A1 row 10 sticky retained", d10["sticky"] is True)
check("A1 row 10 never clean", run10["dirty_state"] == "unknown", run10["dirty_state"])
check("A1 row 10 frontier closed", d10["frontier"] is False)
v = rev21_row10_variants()
check("A1 rev2.1 texts disagree on row 10 (demonstration)", len(set(v.values())) > 1, str(v))
check("A1 rev2.1 table disposition + item 5 gives false CLEAN (demonstration)", v["table_disposition_plus_item5"] == "clean", str(v))

# 4. Acceptance item 2: row 15 stays UNKNOWN; literal item 1(b) gave FAILED.
f15 = Facts("unspecified", "not_applicable", "unobserved", "unobserved", "not_applicable", None, False, "unknown", "exception:TypeError")
d15 = decide(f15)
check("A2 row 15 UNKNOWN/SESSION_FAILED", d15["status"] == "unknown" and d15["failure_code"] == "session_failed" and d15["sticky"], str(d15))
check("A2 rev2.1 item 1(b) literal gives FAILED (demonstration)", rev21_item1_status(False, "unspecified", "unobserved", "unknown") == "failed")

# 5. Acceptance item 3: invalid SATISFIED tuples never open the frontier and preserve uncertainty.
bad = [Facts("not_submitted", "correlated", "satisfied", "changed", "covered", True, True, "unknown", ""),
       Facts("accepted", "engine_error", "satisfied", "changed", "covered", True, True, "unknown", ""),
       Facts("accepted", "correlated", "satisfied", "changed", "covered", True, False, "unknown", ""),
       Facts("rejected", "not_applicable", "satisfied", "not_applicable", "not_applicable", None, False, "unknown", ""),
       Facts("accepted", "correlated", "satisfied", "changed", "covered", None, True, "unknown", "")]
for f in bad:
    d = decide(f); r = apply_action(f); run = run_result([r])
    check("A3 invalid SATISFIED -> frontier closed", d["frontier"] is False, str(f))
    check("A3 invalid SATISFIED -> UNKNOWN sticky", d["status"] == "unknown" and d["sticky"], str(f))
    check("A3 raw postcondition preserved as diagnostic", r["postcondition"] == "satisfied", str(f))
    check("A3 dirty unknown", run["dirty_state"] == "unknown", str(f))
# rev2.1 literal item 1 + item 5 opened the frontier for the first tuple (demonstration)
s = rev21_item1_status(True, "not_submitted", "satisfied", "changed")
check("A3 rev2.1 literal order gives APPLIED and opens the frontier (demonstration)",
      s == "applied" and rev21_item5_effect_established("satisfied", s))

# 6. Acceptance item 4: ACCEPTED + ENGINE_ERROR / MALFORMED / LOST remain uncertain.
for res in ["engine_error", "malformed", "lost", "not_observed"]:
    f = Facts("accepted", res, "unobserved", "unobserved", "not_applicable", None, True, "unknown", "")
    d = decide(f); run = run_result([apply_action(f)])
    check("A4 accepted+" + res + " uncertain", d["residue"] == "unknown" and d["sticky"] and not d["frontier"] and run["dirty_state"] == "unknown" and run["bundle"] != "verified", str(d))

# 7. Acceptance item 6 + C1: the Node scenarios through mapping, application, journal, JSON, evidence.
c1 = json.load(open(sys.argv[1], encoding="utf-8"))
report = []
for sc in c1["scenarios"]:
    truth, row, family = sc["truth"], sc["rev22"], sc["family"]
    f = facts_from_row(family, row)
    r = apply_action(f)
    # JSON round trip of the result and the journal entry
    r2 = json.loads(json.dumps(r))
    f2 = Facts(r2["dispatch"], r2["result"], r2["postcondition"], r2["transition"], r2["footprint"], r2["attempted"], r2["applied"], "unknown", "")
    d2 = decide(f2)
    check("R round trip re-decides identically", {k: d2[k] for k in ("status", "disposition", "failure_code", "residue", "frontier", "sticky")} == {k: r[k] for k in ("status", "disposition", "failure_code", "residue", "frontier", "sticky")}, sc["scenario"])
    run = run_result([r])
    e2 = json.loads(json.dumps(run["entries"][0]))
    check("R journal entry survives JSON", e2["disposition"] == run["entries"][0]["disposition"] and e2["cause"] == run["entries"][0]["cause"], sc["scenario"])
    # expectations from the stub truth (independent of the classifier)
    name = sc["scenario"]
    if family == "page":
        if row["pre_read"] and row["post_read"]:
            if truth["satisfied"] and truth["state_changed"]:
                exp = ("applied", "changed", "clean", True)
            elif truth["satisfied"]:
                exp = ("reasserted", "reasserted", "clean", True)
            elif truth["state_changed"]:
                exp = ("partial", "failed", "dirty_unrecoverable", False)
            else:
                exp = ("partial", "failed", "clean", False)
        elif row["post_read"]:
            exp = ("applied", "unknown", "unknown", True) if truth["satisfied"] else ("partial", "unknown", "unknown", False)
        else:
            exp = ("applied", "unknown", "unknown", False)
    else:
        if row["attempted"] is False and row["ok"] is True:
            exp = ("no_op", "no_op", "clean", True)
        elif row["attempted"] is False:
            exp = ("applied", "unknown", "unknown", False)      # contradictory row -> row 7 after channel acceptance
        elif not row["post_read"]:
            exp = ("applied", "unknown", "unknown", False)
        elif truth["satisfied"]:
            exp = ("applied", "unknown", "unknown", True)       # partial footprint: residue outside scope unobserved
        else:
            exp = ("partial", "unknown", "unknown", False)
    got = (r["status"], r["disposition"], run["dirty_state"], r["frontier"])
    check("C1 " + name, got == exp, f"got {got} expected {exp}")
    if truth["state_changed"] and not truth["satisfied"]:
        check("C1 core: changed-to-wrong never clean: " + name, run["dirty_state"] != "clean")
    if family == "page" and row["pre_read"] and row["post_read"]:
        check("C1a typed changed equals truth: " + name, row["changed"] == truth["state_changed"])
    # revision 2.1 outcome for comparison
    r21 = sc["rev21"]; f21 = rev21_facts_from_row(r21)
    dirty21 = journal_dirty([{"disposition": f21["disposition"], "residual_change": f21["residual_change"], "inverse_available": False}], f21["sticky"])
    report.append((name, truth["state_changed"], truth["satisfied"], r21["changed"], f21["disposition"], f21["residual_change"], dirty21, r["row"], r["status"], r["disposition"], r["residue"], run["dirty_state"], r["frontier"], r["sticky"]))

print("rows in product:", len(product))
print("decision counts by row:", json.dumps(dict(sorted(counts.items(), key=lambda kv: (len(kv[0]), kv[0])))))
print("rev2.1 row 10 variants:", json.dumps(rev21_row10_variants()))
print()
print(f"{'scenario':32} {'chg':>3} {'sat':>3} | rev2.1: changed disp      resid dirty                | rev2.2: row status     disp      residue dirty              front sticky")
for t in report:
    print(f"{t[0]:32} {str(t[1])[:1]:>3} {str(t[2])[:1]:>3} | {str(t[3]):7} {t[4]:9} {str(t[5]):5} {t[6]:20} | {t[7]:>3} {t[8]:10} {t[9]:9} {t[10]:7} {t[11]:18} {str(t[12])[:1]:5} {str(t[13])[:1]}")
print()
if failures:
    print("FAILURES:", len(failures))
    for x in failures[:60]:
        print(" -", x)
    sys.exit(1)
print("ALL CHECKS PASSED")
```

### Recorded output (`c2_report.txt`)

```text
rows in product: 8640
decision counts by row: {"1": 1, "2": 1, "3": 1, "4": 2, "5": 1, "6": 1, "7": 1, "8": 4, "9": 2, "10": 2, "11": 1, "12": 1, "13": 1, "14": 1, "15": 1, "16": 2, "17": 1, "18": 2, "19": 2, "20": 1, "inconsistent": 8611}
rev2.1 row 10 variants: {"table_alone": "unknown", "table_disposition_plus_item5": "clean", "item4_disposition_plus_item5": "unknown"}

scenario                         chg sat | rev2.1: changed disp      resid dirty                | rev2.2: row status     disp      residue dirty              front sticky
collision_pair                     T   F | False   failed    False clean                |  14 partial    failed    changed dirty_unrecoverable F     F
unchanged_failure                  F   F | False   failed    False clean                |  13 partial    failed    none    clean              F     F
changed_success                    T   T | True    changed   False clean                |  12 applied    changed   none    clean              T     F
unchanged_success                  F   T | False   reasserted False clean                |  11 reasserted reasserted none    clean              T     F
changed_to_wrong                   T   F | True    failed    True  dirty_unrecoverable  |  14 partial    failed    changed dirty_unrecoverable F     F
setter_effect_then_throw           T   F | True    failed    True  dirty_unrecoverable  |  14 partial    failed    changed dirty_unrecoverable F     F
pre_read_failed_success            T   T | None    unknown   False unknown              |   9 applied    unknown   unknown unknown            T     F
pre_read_failed_wrong              T   F | None    unknown   False unknown              |  10 partial    unknown   unknown unknown            F     T
post_read_failed                   T   T | True    unknown   False unknown              |   8 applied    unknown   unknown unknown            F     T
both_reads_failed                  T   T | None    unknown   False unknown              |   8 applied    unknown   unknown unknown            F     T
dns_add_correct                    T   T | True    changed   False clean                |  18 applied    unknown   unknown unknown            T     F
dns_add_incorrect_other_record     T   F | False   failed    False clean                |  19 partial    unknown   unknown unknown            F     T
dns_add_true_membership_absent     F   F | False   failed    False clean                |  19 partial    unknown   unknown unknown            F     T
dns_add_already_present            F   T | False   reasserted False clean                |  17 no_op      no_op     none    clean              T     F
dns_add_replaces_existing          T   T | True    changed   False clean                |  18 applied    unknown   unknown unknown            T     F
dns_add_pre_read_failed            T   T | None    unknown   False unknown              |   9 applied    unknown   unknown unknown            T     F
dns_skip_then_post_false           F   T | True    failed    True  dirty_unrecoverable  |   7 applied    unknown   unknown unknown            F     T

ALL CHECKS PASSED
```

---

## Resumen en español

**Revisión 2.2.** Resuelve únicamente las dos familias de hallazgos de la
revisión de corrección (C1 y C2) sobre la revisión 2.1; B3, G1 a G4, la
arquitectura E6, el espacio de nombres y los transportes no cambian.

**C1.** `ok` y `changed` se calculan en la misma evaluación del script a
partir de los valores tipados reales, nunca de los resúmenes FNV-1a, que
quedan como diagnóstico acotado sin autoridad (el par de colisión
`yI76Uj5ZfPNL`/`qx51K0WT5Lj1` se reproduce en el probe y pasa a ser un
escenario del arnés). Cada familia S0 declara su alcance observado y su
huella de efecto; un `AddDnsRecord` intentado tiene huella PARCIAL, así que
su residuo fuera del registro pedido queda como desconocido (disposición
UNKNOWN, `dirty_state` UNKNOWN y limitación `residue_unknown`) y nunca se
informa CLEAN, aunque la postcondición satisfecha siga abriendo la frontera
y permitiendo VERIFIED. El alta se omite cuando la lectura previa ya muestra
el registro (NO_OP con residuo conocido). Los lectores de tabla documentados
quedan como compuerta M-DNS-4 (RD-11), sin usarse en S0.

**C2.** Una única función `decide_mutation` fija estado, disposición,
código, residuo, frontera y bandera pegajosa; primero detecta filas legadas
(todos los hechos nuevos en su valor por defecto), luego admite sólo las
tuplas listadas y todo lo demás es inconsistente (UNKNOWN, cerrada,
pegajosa). La fila 10 queda definida una sola vez (PARTIAL, disposición
UNKNOWN, pegajosa, nunca CLEAN); la fila 15 (excepción) sigue siendo UNKNOWN
con `SESSION_FAILED`; los hechos contradictorios recibidos se conservan como
diagnóstico y no otorgan nada. Las cláusulas rivales del prompt (ítem 1 (a) a
(e), la frase de disposición del ítem 4 y el predicado de campos del ítem 5)
se eliminaron.

**Evidencia.** Dos probes desechables fuera del repositorio (Node y Python)
reproducen los contraejemplos, enumeran las 8640 tuplas de hechos y
comprueban predicados de seguridad, no la igualdad con una copia del
clasificador; todo pasa. No son evidencia de pytest ni LIVE.

**Bloqueos restantes.** Aprobación independiente del contrato S0 de la
revisión 2.2; ninguna autorización LIVE; compuertas de motor y de API sin
medir (incluida M-DNS-4); procedencia documental de la evidencia DNS/HTTP;
deuda Ruff de `tool_registry.py`.
