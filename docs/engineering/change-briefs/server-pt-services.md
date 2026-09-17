# Server-PT services for PC-PT clients: architecture and implementation plan

Contract: **`rev2.2 + TD-12, S0 approved for offline implementation; later
slices not approved by this act`**. Read section 0 first: it carries the
binding amendments of technical decision TD-12 and takes precedence over the
revision 2.2 clauses it names.

Status of S0: implemented offline on branch
`feature/server-pt-s0-observation-integrity`, **READY_FOR_REVIEW**; see section
8 for the implementation record. Status of every later slice: not approved and
not implementation-ready without its own independent approval and the gates
named in sections 4.6, 5.8 and 7.3. Risk class **L**.

Planning deliverable for Cisco-Muejeje (`andres18113/cisco-muejeje`). This
document is the versioned M/L change brief required by
`docs/engineering/standards.md`: chapters 0 to 7 record the design before
implementation and chapter 8 records what was implemented against it. It is
self-contained and needs no other file. Revision 2.2 answered the correction
review of revision 2.1 (findings C1 and C2) and changed nothing outside those
findings and their dependent clauses; revision 2.1 answered B1 to B3 and G1 to
G4; revision 2 answered SR-01 to SR-10. Technical decision TD-12 then approved
the S0 contract with the binding amendments of section 0.

Source classes used throughout:

| Tag | Meaning |
| --- | --- |
| `[REPO]` | Repository fact at the selected commit, with path, symbol and lines |
| `[MEASURED]` | Fact measured offline in this checkout (interpreter, Ruff, fakes, pure functions); never a Packet Tracer observation |
| `[CISCO]` | Vendor-documented API, local reference `help/default/IpcAPI` labelled 8.1.0 |
| `[EVIDENCE]` | Existing runtime evidence with the provenance the repository actually records |
| `[DECISION]` / `[INFERENCE]` / `[GATE]` | This plan's decision, inference, or an unmeasured fact held as an explicit gate |

Exclusions inherited from the assignment and preserved: no `muejeje.pts`, no
Runtime V6, no new `.pts`, dispatcher, protocol version, bridge, replacement
transport or new bridge endpoint; IoT and `feature/iot-connectivity`
untouched; no reopening of CP-LIVE, voice, PoE or namespace work; no new
NTP/TFTP features; no GUI automation; no commits, branches, installs, bridge
starts or LIVE actions in this assignment.

## Change log

Revision 2.2 (answers C1 and C2; B3 and G1 to G4 unchanged):

| Item | Change | Driven by |
| --- | --- | --- |
| R-OBS-07, R-DNS-01, R-HTTP-01, sections 4.4 and 4.5 | `ok` and `changed` computed from the actual typed before/after values inside the same script evaluation; digests demoted to bounded diagnostics with no authority; explicit `pre_read`/`post_read` flags; observation scope and effect footprint stated per S0 family (`FootprintFact`); an attempted `AddDnsRecord` has a PARTIAL footprint, so its residue outside the wanted record stays unobserved and is never reported CLEAN; ensure-present skip when the pre-read shows the wanted record; gate M-DNS-4; RD-11 | C1 |
| R-OBS-02, R-OBS-06, R-OBS-08, section 4.5 | One canonical `decide_mutation` with validity and legacy-default detection before outcome classification; row 10, the exception row and the declined row defined once; sticky and frontier are decision outputs, not field predicates; contradictory received facts preserved as diagnostics; the competing prompt clauses (item 1 (a) to (e), the item 4 disposition sentence, the item 5 field predicate) deleted | C2 |
| Section 6.5, S0 prompt items 1, 4, 5, 6 and the RED list | Harness scenarios for the digest-collision pair, the incorrect add that changes another record, the replaced record, the ensure-present skip and the contradictory skip row; the positive CLEAN test scoped to COVERED families; a DNS-record run expects `dirty_state=UNKNOWN` with a named limitation; expected values come from the stub state, never from the row | C1, C2 |

Revision 2.1 (answers B1 to B3, G1 to G4):

| Item | Change | Driven by |
| --- | --- | --- |
| R-OBS-07, section 4.5 | Mutation facts separated into channel acceptance (`dispatch`), attempt knowledge (`result`), observed transition (`transition`), postcondition satisfaction (`postcondition`) and `residual_change`; unconditional post-read; the DNS add short-circuit removed; authoritative decision table; scoped journal change RD-10 | B1 |
| R-OBS-02, R-OBS-06, R-OBS-08, R-EVD-01 | One decision table for every admitted combination; ENGINE_ERROR, MALFORMED, missing rows and exceptions set the sticky uncertainty; facts carried by `ActionApplicationResult` and `ExecutionJournalEntry`; `LOST` and `INCONCLUSIVE` observation facts; `cause` field; `UNSPECIFIED` default distinct from `NOT_ATTEMPTED`; recovery reads admitted explicitly | B2 |
| R-TEST-01 (new), section 6.5 | Test inventory with per-assertion classification; five authorized changes with rationale; Node stub harness for generated scripts (precedent `tests/test_typed_ping.py`); fresh contradictions carry fresh negative evidence; stale output is inconclusive | B3 |
| R-ENTRY-02, R-NET-01, R-NET-02, R-CAP-06, R-ENTRY-11 | Admission may read; first supported topology bounded to one segment; client DNS server derived in composition through `ConfigurationPolicy.dns_server`; `CLIENT_DNS_SERVER` optional until M-DNS-3; required versus optional services and expectations from the intent's existing `required` and `verification_required` flags | G1 |
| R-ENTRY-06, R-RET-01, R-RET-02 | Record lifecycle for early rejections; full typed rows retained; reuse eligibility with fresh prerequisite verification; stop mutations when the record cannot advance; D-9 containment | G2 |
| R-EVT-06, R-EVT-07, R-DHCP-04, R-DHCP-05, R-DHCP-07 | Pre-effect claim lifecycle; observer cleanup separated from effect ownership and quarantine; lease-time inequality demoted to UNKNOWN until M-DHCP-6; positive lookup, confirmed absence and completion defined separately with M-DHCP-2 | G3 |
| R-CAP-07, R-QUAL-05, R-QUAL-06, section 4.9 | Provenance levels; Q1 attribution and S1b re-qualification; later acceptance records through the shared coordinator; restored DNS matrix, requirement predicates, DTOs and sample input; format and lint commits separated | G4 |
| RD-8, RD-9, RD-10 | New decisions recorded in 1.5 | B1, B3, G4 |

Revision 2 (answered SR-01 to SR-10, retained): typed dispatch and result
facts; freshness as a completed correlated read; error preservation across
the pipeline; no blanket `noqa`; capability authority per build, model and
operation; bounded E5 scope with delegation derived before E5 compilation;
HTTP-only transport for secret-bearing invocations; event lifecycle; DHCP
predicates; staged qualification.

---

## 0. Contract revision: rev2.2 + TD-12 (read first)

**Contract label: `rev2.2 + TD-12, S0 approved for offline implementation;
later slices not approved by this act`.**

The execution contract of this brief is revision 2.2 of the plan **plus** the
binding amendments of technical decision TD-12, not revision 2.2 alone. TD-12
was issued as `APPROVED_WITH_BINDING_AMENDMENTS, S0 OFFLINE IMPLEMENTATION
ONLY` against repository baseline
`andres18113/cisco-muejeje`, `main@6263344e31ba3b0de6539d652f2cd06fc73a3562`.
TD-12 is a technical decision on the design. It does not certify implemented
behavior, authorize LIVE, authorize S1 or any later slice, or permit a merge to
`main`.

Where TD-12 and revision 2.2 disagree, **TD-12 governs**. It supersedes exactly
these revision 2.2 clauses and nothing else:

| Superseded rev2.2 clause | Superseded by | Where amended in this brief |
| --- | --- | --- |
| Section 4.4 `ActionApplicationResult` field list and section 7.1 prompt item 1, which add seven observation fields plus `residual_change` but retain no copy of the classifier input | TD-12.1 | section 4.4 (`configuration_runtime.py` block), section 7.1 prompt item 1, section 7.1 prompt item 5 round-trip clause |
| The unconditional sentence of section 7.1 prompt item 5 mapping *any* missing runtime mutation row to row 7 | TD-12.2 | section 4.5 (row 7 provenance note), section 7.1 prompt item 5 |
| Section 1.1 `Instruction loading` row, which attributes a current-session `/context` observation | TD-12 section 5 | section 1.1 |
| The C1b RED text asserting baseline `CLEAN` for a true-returning incorrect or replacing DNS add | TD-12 section 5 | section 7.1 RED list |
| The section 7.1 item 8 Ruff measurement `tests/test_service_runtime.py 12, formatted` | TD-12 section 5 (record the measured baseline) | section 7.1 prompt item 8 |

Design decisions TD-12 accepted without change, restated here because they
bound implementation:

- C1's digest-collision and DNS-membership countermodels are answered at the
  specification level: compare actual typed values, keep the post-read
  unconditional, keep diagnostic hashes non-authoritative, and distinguish the
  observed scope from the effect footprint. RD-11 holds for S0: an attempted
  DNS add has PARTIAL footprint and unknown residue, while a **proven skipped**
  add is NO_OP within the stated scope. Observation is not widened to the DNS
  table during S0 (gate M-DNS-4).
- C2's competing classification rules are replaced by the one canonical
  validated decision of section 4.5. Status, frontier and sticky uncertainty
  come from that decision, never from an independent reading of raw fields.
- B3 remains accepted: actual generated scripts must execute under the Node
  stub harness, and the identified incorrect expectations may change for their
  stated requirements. G1 to G4 remain owned by their later slices and
  measurement gates.
- A VERIFIED service claim and an UNKNOWN residue are different dimensions.
  Neither is ever converted into a cleanup, compensation, retry,
  capability-promotion or whole-environment safety claim, and a later NO_OP run
  never erases an earlier run's UNKNOWN record.

### 0.1 TD-12.1 — preserve the original classifier input

**Evidence.** The baseline `ActionApplicationResult`
(`domain/enterprise/models/configuration_runtime.py:245-252`) has no `applied`
field. Revision 2.2 adds seven observation fields plus `residual_change` to it
but retains no copy of the tuple that `decide_mutation` actually classified.

**Counterexample.** The received tuple `ACCEPTED / CORRELATED / SATISFIED /
CHANGED / COVERED / attempted=True / applied=False` is inconsistent and must
stay UNKNOWN, closed and sticky. With `applied` dropped, reconstructing it as
`dispatch is ACCEPTED` turns the tuple into row 12. Reconstructing it from a
derived status is equally prohibited: the output is not the original input.

**Binding amendment.**

1. `ActionApplicationResult` gains one optional field
   `received_mutation: RuntimeActionMutation | None = None`, in the shared
   model file already in S0 scope.
2. For E6 the applicator populates it with a defensive, sanitized copy of the
   exact typed mutation handed to `decide_mutation`: `applied`, the original
   disposition, the original failure code, the original `cause` and all seven
   observation fields. No script body, credential or raw pre/post page content
   belongs in the snapshot. It is never mutated after classification.
3. The flattened observation fields stay on the public result. `status`,
   `disposition`, `failure_code` and `residual_change` come from the canonical
   decision.
4. The original `cause` is preserved in the snapshot and the decision's
   canonical classification reason is carried separately on the result, so an
   incidental error string can never hide `inconsistent_facts`. In this
   implementation `ActionApplicationResult.cause` carries the decision's
   canonical cause and `received_mutation.cause` carries the producer's
   original string; for an inconsistent tuple the canonical cause is exactly
   `inconsistent_facts` and the producer string is never composed into it.
5. The decision computed for each action during application is the one used.
   An explicit deserialization or audit re-evaluation calls `decide_mutation`
   on the retained input snapshot, never on a mutation reconstructed from
   decision outputs. A stored result without the snapshot stays a legacy
   record; it acquires no new fact-bearing authority by inference, and
   `applied` is never fabricated for it.
6. The field is additive: baseline-shaped input JSON still validates, old
   producers need not populate it, and compact legacy summaries keep their
   existing shape. The new full-JSON key is documented in section 4.8. No new
   general-purpose evidence subsystem is introduced.

**Acceptance.** Through the real DTOs, applicator, journal and serializer,
round-trip the valid, inconsistent, legacy, exception and missing-result cases.
Compare the full retained classifier input and the re-derived decision, not
only the happy-path status. The inconsistent `applied=False` tuple above must
still be inconsistent after the round-trip. Mutating the original object after
application must not change the stored snapshot. The review's
dictionary-snapshot experiment is supporting design evidence only; the model
test is mandatory.

### 0.2 TD-12.2 — never synthesize channel acceptance from a missing list item

This clarifies the provenance requirement of row 7 and **supersedes** the
unconditional sentence of section 7.1 prompt item 5 that mapped any missing
runtime mutation to row 7.

- A missing or invalid action row **inside an observed ACCEPTED, CORRELATED
  batch envelope** is row 7: APPLIED with `RESPONSE_MALFORMED`, disposition
  UNKNOWN and sticky uncertainty. The Packet Tracer adapter holds that
  envelope, so it must return the classified typed result for **every**
  requested action, including one whose row is absent or invalid.
- A missing item at the application port **without any evidence of acceptance
  for that item or batch** does not prove ACCEPTED. It is a local
  runtime-boundary contract error and takes the row 15 uncertainty path with
  an explicit sanitized cause `exception:MissingRuntimeMutationResult`:
  UNKNOWN, `SESSION_FAILED`, frontier closed, sticky. An empty result list
  from a runtime that made no dispatch is never labeled proof of dispatch.

This preserves the table and requires no new transport, endpoint or service
family.

**Acceptance.** Test both a correlated batch missing one row and a runtime
returning an empty list without dispatch. The first retains proven acceptance;
the second makes no acceptance claim. Both retain uncertainty and block
dependent effects. A missing result is never inferred to mean successful
cancellation or non-execution.

### 0.3 Verification boundaries required by TD-12 section 4

These are verification boundaries, not new product scope:

- The review's checker is disposable. It is not copied as the product
  implementation and is not its complete oracle. Its row validator accepted
  `ok=1, changed=1` through equality-based membership, and its simplified
  `run_result()` labeled a stand-in bundle from frontier and sticky alone.
- The real runtime enforces the row-shape contract strictly: flags are actual
  booleans; `ok` and `changed` are exact bool-or-null values; numeric `0`/`1`,
  strings and wrong-shaped diagnostics are invalid. A completed post-read
  requires a boolean `ok` even when the pre-read failed. `changed` requires
  both reads and is null otherwise. Digests carry no semantic authority. Tests
  cover these boundary cases, omitted keys, duplicate and foreign identifiers,
  and both documented skip shapes.
- The acceptance tests exercise the real generated payload, row parser,
  canonical decision, applicator, journal, evidence adapter and Pydantic
  round-trip. Independent client evidence, capability gates, dependency gates
  and cleanup failures are never replaced by a synthetic bundle expression.
- The S0 positive controls and the causal RED/GREEN requirement stand. Unknown
  behavior is not permission to weaken a test.

### 0.4 Acceptance boundary of the approval

S0 approval concerns design readiness for offline implementation under these
amendments. It is not implementation acceptance. Final acceptance requires
actual code and diff review, legacy compatibility, focused regressions,
generated-script harness execution in CI, the full required suite, the quality
and documentation gates, and independent audit of the exact delivered SHA. S1
and every engine, HTTPS, mail, DHCP, cleanup and provenance qualification
retain their existing owners and explicit authorization gates.

---

## 1. Executive decision and provenance

### 1.1 Selected baseline

| Item | Value | Source |
| --- | --- | --- |
| Plan commit | `6263344e31ba3b0de6539d652f2cd06fc73a3562` (`main`) | `[REPO]` `git rev-parse HEAD`, `cisco/main` and `git ls-remote cisco refs/heads/main` on 2026-09-17 all return this SHA; working tree clean at the time of measurement (reported, not independently observed by reviewers) |
| Review baselines | revision 2 review and revision 2.1 targeted review both cite this SHA | review texts |
| Maintainer remote alias | `cisco` in this checkout; standard clones use `origin` | `[REPO]` `AGENTS.md`, `git remote -v` |
| Interpreter used for offline measurements | checkout `.venv`, CPython 3.12.10; CI matrix is Windows and Ubuntu on 3.11 and 3.13 (`.github/workflows/tests.yml:20-23`) | `[MEASURED]` |
| Ruff | 0.16.7 (pinned in `pyproject.toml`) | `[MEASURED]` |
| Node for the generated-script harness | used by `tests/test_typed_ping.py:268-275` and `tests/test_e95_serial_physical_product_slice.py:1254-1261` through `shutil.which("node")`; those tests skip without it; the workflow installs no Node explicitly | `[REPO]` |
| Packet Tracer install found | `C:\Program Files\Cisco Packet Tracer 9.0.1` | filesystem only; not an observation of a running instance |
| API reference edition | local `help/default/IpcAPI/index.html` labels itself "Cisco Packet Tracer Extensions API 8.1.0" | `[CISCO]` |
| Instruction loading, planning session | An observation of `/context` listing `CLAUDE.md`, `AGENTS.md` and `docs/engineering/standards.md` under Memory files is attributed to an **earlier** planning session, not to the session that wrote revision 2.2; the revision 2.2 review resolution states `/context` was not run in that session. This planning session is therefore recorded as **pending** (TD-12 section 5) | historical attribution; pending for this session |
| Instruction loading, implementation session | Recorded in section 8.1 by the implementer, using the product-specific instruction inspection rather than treating `/context` as a universal command. A fresh observation never retrospectively certifies another session | see section 8.1 |

Baseline decision requiring review: none. `main` did not move.

### 1.2 What is already implemented `[REPO]`

E6 exists as a backend-neutral service stage with tests but without a product
caller:

- Domain: `src/packet_tracer_mcp/domain/enterprise/models/service_plan.py`
  defines `ServiceType` (18-23), `ServicePhase` (26-28), eight typed actions
  (96-152), `ServiceCapabilityProfile` (70-81), `ServiceDefinition`,
  `FoundationalServiceRequirement` (185-192), `ServiceVerificationExpectation`
  (195-207), `ServicePlan` (210-227). `service_runtime.py` defines
  `RuntimeServiceVerification` (20-27), `ServiceVerificationResult`,
  `ServiceOutcome`, `ServiceApplicationResult` (43-88). `execution.py` holds
  `OperationSemantics`, `MutationDisposition`, `DirtyState`, the journal
  (21-49, 88-260) and `_derive_dirty_state` (332-348).
  `configuration_runtime.py` holds `ActionExecutionStatus` (19-62),
  `ConfigurationFailureCode` (73-110), `RuntimeActionMutation` (191-198),
  `mutation_execution_status` (201-232), `ActionApplicationResult` (245-253).
- Compiler: `domain/enterprise/services/service_compiler.py::ServiceCompiler`
  requires a static E5 host address (172-179), selects clients that have an E5
  endpoint action (425-461), binds foundations (463-474), warns on unknown
  capabilities (240-284), compiles expectations (600-720); it reads
  `verification_required` (637) and never reads `ServiceRequirement.required`.
- Application: `application/use_cases/apply_services.py::ServiceApplicator`
  (`ServiceRuntime` protocol 59-69; hash and manifest checks 90-121;
  foundation gate 145-158; identity binding 160-231; capability gate 242-268;
  host-batched apply 270-360; verification DAG 409-553; aggregation 555-624).
- Infrastructure: `infrastructure/execution/enterprise_service_runtime.py`
  applies through `getProcess(...)` (67-148; `_mutation_lines` 109-148), reads
  direct state (175-220), verifies DNS by typed `ping` with a fresh output
  window (222-302) and HTTP through `HttpBackgroundClientManager` (318-413).
  `_json_result` (435-443) collapses timeout, `ERROR:`/`PT_ERROR:` and JSON
  failures into `{}`.
- Transports: `live_bridge.py::correlated_http_send_and_wait` (111-135),
  `PTCommandBridge` (231-375, handlers 473-600), `file_bridge.py::FileBridge`
  (124-341); routing in `adapters/mcp/tool_registry.py::_bridge_send_and_wait`
  (1520-1552), whose bridge session (`PTCommandBridge()` at 918,
  `_file_bridge` at 937, `_http_post` at 852) is closure-scoped.
- E5 endpoint path: `enterprise_configuration_runtime.py::_endpoint_call`
  (841-858) passes `action.dns_server or ""` to `configurePcIp`, which calls
  `port.setDnsServerIp` only for a non-empty value
  (`EXTENSION/script-engine/main.js:280-310`); the compiler places
  `policy.dns_server` on static endpoints (`configuration_compiler.py:1162-1171`),
  and `ConfigurationPolicy.dns_server` defaults to `None`
  (`configuration.py:149-171`).
- Generated-script harnesses: `tests/test_typed_ping.py:196-276` runs a
  generated script under Node against stub `ipc` objects and captures
  `reportResult`; `tests/test_e95_serial_physical_product_slice.py:1235-1263`
  does the same for module payloads (registry basis
  `PAYLOAD_EXECUTION_SIMULATED`, `mutation_replay.py:113, 545`).
- Catalog: `infrastructure/catalog/service_capabilities.py` (18-87).
- Replay registry: `domain/enterprise/mutation_replay.py` (490-530 service
  families; 693-701 fail-closed lookup).
- Docs: `docs/architecture/enterprise-services.md:102-118` baseline table;
  `docs/qa/e95-runtime-debt.md:289-296` ("`ServiceApplicator` has no product
  caller").

### 1.3 What is missing or defective `[REPO]` `[MEASURED]`

| Gap | Evidence |
| --- | --- |
| No MCP tool reaches E6 or E5 application | `grep` of `tool_registry.py` for `ServiceApplicator`, `compile_enterprise_services`, `ConfigurationApplicator`: 0 hits; `pt_live_deploy` ends before E5 |
| Transport outcomes collapse | `_http_post`/`_http_get` return `(None, None)` for every `OSError`/`URLError` (`live_bridge.py:204-230`); `correlated_http_send_and_wait` returns `None` for POST non-200 and for GET 204/404/410/socket error alike (111-135); `FileBridge.send_and_wait` returns `None` before publication (242-249) and after publication (273) alike and updates the shared `last_disposition` only on some paths |
| Setter return short-circuits the read-back | `_mutation_lines` computes `ok = addARecordToNameServerDb(...) || getARecordWithAddress(...)` (116-121): a true add result skips the getter, so `ok` is not post-read evidence |
| No before/after observation | every family reads back once after the setter (109-148); an unintended change (before A, intended B, after C) is indistinguishable from an unchanged failure |
| Every successful E6 application is journaled as dirty-state UNKNOWN | `[MEASURED]` offline with `tests/test_service_application.py::FakeServiceRuntime`: `status=verified`, `dirty_state=unknown`, journal counts `{'unknown': 4}`. Cause: no configuration, security or service runtime sets a `MutationDisposition` (0 hits), `journal_from_action_results` maps `APPLIED` without an explicit disposition to UNKNOWN by design (`execution.py:267-291`), and `_derive_dirty_state` returns UNKNOWN for any UNKNOWN entry (332-336). The design is deliberate for fire-and-forget channels (`tests/test_e95_security_control_plane_manifest.py:226-231`); the E6 channel returns a correlated result that the runtime discards |
| A failed operation with a residual change journals as CLEAN | `[MEASURED]` on the pure `_derive_dirty_state`: entries with only FAILED dispositions and no CHANGED/REASSERTED entry return CLEAN (342-345); the shared model has no field for "failed and changed" |
| Applicator manufactures certainty | `apply_services.py:318-327` maps a runtime exception to `applied=False` (FAILED, "never left the process") for the whole batch; 330-346 maps a missing row to FAILED and clears a runtime failure code whenever `applied` is true; 527-533 maps every non-VERIFIED verification to a `*_VERIFICATION_FAILED` code; 541-548 maps a verification exception to FAILED |
| Direct read-back freshness and subject handling | `_verify_direct` sets `fresh_evidence=bool(observed)` (217): `{}` after a timeout gives FAILED with `fresh_evidence=False`; `{found: false}` gives FAILED with `fresh_evidence=True` |
| Behavioral contradictions and stale output share one status | `_verify_dns` and `_verify_http` return FAILED with `fresh_evidence=False` for a fresh wrong address, fresh content without the marker, a marker present before the request, an incomplete window and a refused command alike (222-302, 318-378, 425-433); `tests/test_service_runtime.py:183-213, 242-303` pin that shape |
| Evidence adapter disagreement | `evidence.py::evidence_from_legacy_result` (172-203): `verified` with `fresh_evidence=False` becomes PROBE_FAILED/UNVERIFIED; an `unknown` status becomes NOT_ATTEMPTED |
| HTTPS verification accepts any fresh body and never reads the client mode | `_verify_http` with empty marker; `tests/test_service_runtime.py:318-345` asserts VERIFIED; no `isHttps()` read |
| Catalog stamps any version and authorizes by default | `service_capabilities.py:18-35`; keys `Server-PT:<type>` only (86-87) |
| Capability keys ignore the operation target | application keyed by `action.host_model` (`apply_services.py:244`); verification by `service.host_model` (479) even for client operations |
| DNS/HTTP baseline provenance is documentary | `service_capabilities.py:22` and `enterprise-services.md:102-118`; no run id, tree SHA or transport anywhere under `docs/` or `reference/` |
| Public composition never selects a Server-PT DHCP authority nor a client DNS server | `compose_enterprise_reference.py:186-193` passes no `ConfigurationPolicy`; `_dhcp_actions` falls back to the site gateway (`configuration_compiler.py:1212-1213`); `policy.dns_server` stays `None`, so static clients get no DNS server |
| A segment without an IOS pool loses its DHCP clients | `configuration_compiler.py:298-303` |
| `ServiceRequirement.required` is unused | `requirements.py:48`; no consumer in `service_compiler.py` (only `verification_required` at 637) |
| Event unregistration is undocumented | only `EXTENSION/script-engine/main.js:16`; no page under `help/default` documents an unregister member |
| Secret-bearing scripts would be written to disk on the file channel | `file_bridge.py:175-185` |
| Ruff debt | section 4.9 |

### 1.4 Recommended approach `[DECISION]`

1. Reuse and extend E6 (`ServicePlan`, `ServiceCompiler`, `ServiceApplicator`,
   `PacketTracerEnterpriseServiceRuntime`, capability profiles, replay
   registry). No second subsystem.
2. Make the observation chain truthful first (S0): typed transport facts;
   bracketing reads with an unconditional post-read; four separated mutation
   facts; one decision table; a scoped journal change for residual changes;
   observation facts with fresh negative evidence; structured codes through
   applicator, journal, evidence and JSON; HTTPS mode claims; a Node stub
   harness that executes the generated scripts.
3. Add one product entry point `pt_apply_enterprise_services` (S1) with
   zero-mutation admission, a bounded first topology and E5 closure, client
   DNS derivation through composition, hash-bound foundation derivation,
   capability authority per build, model and operation, a run record with a
   defined lifecycle, retained-result eligibility, and per-client reporting.
4. Resolve engine facts that determine the runtime design (Q0) before the
   email and DHCP runtimes are finalized; resolve HTTPS ownership (Q1) and
   implement and re-qualify the chosen content contract (S1b).
5. Add SMTP/POP3 (S2) and Server-PT DHCP (S3) as typed E6 actions with
   pre-effect claims, quarantine and capability profiles at `UNKNOWN` until
   their own qualification stage (Q2, Q3) is recorded. Promotion only from a
   committed record that names the executed SHA.

### 1.5 LIVE limits and decisions requiring review

- No LIVE action is authorized by this plan. Q0..Q3 and the S1 LIVE
  acceptance each name their exact scope; each needs its own authorization.
- RD-1 (E5 + E6 through one entry point): accepted conditionally. Section
  4.5 satisfies the conditions: application owns the workflow, the adapter
  composes and translates, the E5 effect scope is an explicit closure
  (P-E5-2), no whole-plan reapplication, no global PARTIAL promotion.
- RD-2 (DHCP delegation): per-segment ownership derived before E5
  compilation and carried through the real composition; the client
  `SetEndpointDhcp` action is preserved (P-E5-1 revised).
- RD-3 (client actions): typed client actions; service owner and operation
  target distinct; capability resolved for the target model and operation.
- RD-4 (register-then-poll): candidate with the lifecycle of 4.6, including
  pre-effect claims and quarantine; capability UNKNOWN until Q0.
- RD-5: secret-bearing invocations run on the HTTP channel only, fixed at
  admission, no fallback.
- RD-6: P-E5-2 adds `excluded_action_ids` to `ConfigurationApplicator.apply`.
- RD-7: S1 touches `tool_registry.py` (one import, one call) and owns its
  measured Ruff debt with the two-commit split of 4.9.
- RD-8 (new): the product tool may use the legacy documentary DNS/HTTP
  capability records for its first slice as an explicit legacy-compatibility
  decision, always disclosing `provenance:documentary_baseline`; no new claim
  is promoted without a recorded run (R-CAP-07).
- RD-9 (new): the S0 generated-script harness runs under Node following the
  existing test precedent; it skips locally without Node and fails, not
  skips, when `GITHUB_ACTIONS` is set. `pyproject.toml` is unchanged.
- RD-10 (revised in 2.2): a scoped, additive change to the shared journal
  (`ExecutionJournalEntry.residual_change` and one rule in
  `_derive_dirty_state`) so a failed operation with an observed unintended
  change is never reported CLEAN; baseline behavior for every existing
  producer is proven identical by a table test. `residual_change=True` is an
  observed fact; `False` is only the absence of that observation. Unknown
  residue is carried by disposition UNKNOWN with a `cause`, never by
  `residual_change=False`.
- RD-11 (new): in S0 the effect footprint of an attempted `AddDnsRecord` is
  PARTIAL (only the wanted record's membership is read), so a run that
  attempts an add reports `dirty_state=UNKNOWN` with the limitation
  `residue_unknown:<id>:footprint_partial:dns_a_record_table` even when every
  postcondition is SATISFIED and the bundle is VERIFIED; a run whose pre-read
  finds the record skips the add and is NO_OP with complete knowledge. The
  documented table readers (`getSizeOfNameServerDb`, `getRrFromNameServerDbAt`)
  are the path to a COVERED footprint only after M-DNS-4 is measured; S0 does
  not use them and does not widen the scope by any other enumeration.

---

## 2. Repository integration map

### 2.1 Call flow of the proposed product invocation

```text
MCP client
  └─ pt_apply_enterprise_services(intent_json, deployment_id, packet_tracer_version, run_label="")
       [proposed: adapters/mcp/service_tools.py::register_service_tools, called once from
        tool_registry.py::register_tools with the registry's transport closures]
       ├─ A1 EnterpriseIntent.model_validate_json                                    [REPO intent.py]  (no record: no identity yet)
       ├─ A2 DeploymentManifestStore().latest_by_deployment_id(deployment_id)       [REPO deployment_manifest_store.py:87]  (no record)
       ├─ A3 packet_tracer_version == manifest.backend_version, else refuse         [R-CAP-02]  (unbound admission record if writable)
       ├─ A4 ImportIsolationPreflight.ensure_isolated() (TEST_PROCESS/foreign refused) [REPO import_isolation_preflight.py]
       ├─ A5 BridgeReadinessPreflight; transport selected once; secret-bearing plan -> http only [R-SEC-01]
       ├─ A6 ServiceRunRecordStore.begin(run_id, deployment_id, ...) write-ahead; refuse if not writable [R-ENTRY-06]
       ├─ A7 compose_enterprise_reference(intent, packet_tracer_version, deployment_manifest,
       │        configuration_policy=derive_service_policy(intent)) -> E4, hardware, E5, E6 ServicePlan   [REPO 112-123 + extension; R-NET-02, R-DHCP-01]
       ├─ A8 identity: physical hash equality; resolve_manifest_targets for every host and client; eligibility of required and optional services [R-ENTRY-03, R-ENTRY-11]
       ├─ A9 capability resolution for every E6 action and expectation on its target model; every secret_ref resolved [R-CAP-03, R-SEC-01]
       ├─ A10 E5 closure C; directed endpoint pre-reads (read-only) for drift; retained-result eligibility [R-ENTRY-09, R-RET-01]
       ├─ E1 ConfigurationApplicator(...).apply(plan, mutation_action_ids=C or delta, excluded_action_ids=plan-C, retained_action_results=...)  [REPO apply_configuration.py:91 + P-E5-2]
       ├─ E2 contradiction or E5 effect uncertainty -> stop before E6 effects              [REPO execute_enterprise_reference.py; R-RET-02]
       ├─ E3 derive_service_foundational_statuses(service_plan, configuration_result)  [proposed, foundational_evidence.py]
       ├─ E4 ServiceApplicator(runtime).apply(service_plan, ..., capabilities=resolved, deployment_manifest=manifest)  [REPO apply_services.py:77]
       ├─ E5 release owned temporaries; record release outcomes
       ├─ P1 ServiceRunRecordStore.complete(record)                                   [R-ENTRY-06]
       └─ JSON response: per service, per client, limitations, e5_effect_scope, persisted_stage, record_path [R-ENTRY-05]
```

Admission (A1 to A10) performs directed reads and no user-state mutation.
Every runtime call is one bridge operation through the channel fixed at A5.
The E6 runtime receives `dispatch_and_wait` (typed) bound to that channel;
`send_and_wait` remains for legacy callers.

### 2.2 Reuse / extend / new / defer map

| Path or symbol | Decision | Concrete responsibility and reason |
| --- | --- | --- |
| `domain/enterprise/models/execution.py` | **extend (S0, RD-10)** | `DispatchFact`, `ResultFact`, `PostconditionFact`, `TransitionFact`, `FootprintFact`; journal entry facts and `residual_change`; one `_derive_dirty_state` rule; four enums to contract-preserving `StrEnum` |
| `domain/enterprise/models/configuration_runtime.py` | **extend (S0)** | fact fields on `RuntimeActionMutation` and `ActionApplicationResult`; `OUTCOME_UNKNOWN`, `RESPONSE_MALFORMED`, `POSTCONDITION_UNSATISFIED`; `mutation_execution_status` decision table; five enums converted |
| `domain/enterprise/models/service_runtime.py` | **extend (S0, S1)** | `observation`, `cause`, `claim_level`, `limitations`; `evidence_from_service_verification`; `client_results` in `compact_summary()` (S1) |
| `domain/enterprise/models/service_plan.py` | **extend (S1b, S2, S3)** | new `ServiceType`, actions, kinds, requirements; `required` on expectations; untouched in S0 |
| `domain/enterprise/models/requirements.py::ServiceRequirement` | **extend (S2, S3)** | `domain_name`, `email_accounts`, `email_clients`, `email_pairs`, `dhcp_pool`, `https_content`, `verification_mode`; existing `required` and `verification_required` become consumed (S1) |
| `domain/enterprise/models/configuration.py` | **extend (S3)** | `ConfigurationPolicy.delegated_dhcp_segment_ids`; issue codes `DHCP_DELEGATED_TO_SERVICE`, `DHCP_AUTHORITY_CONFLICT`, `DHCP_RELAY_REQUIRED`, `DNS_SERVER_ADDRESS_REQUIRED` (S1) |
| `domain/enterprise/services/configuration_compiler.py` | **extend (S3, P-E5-1 revised)** | delegated segments emit no IOS pool, record the delegation, keep `SetEndpointDhcp` without a pool dependency |
| `domain/enterprise/services/service_compiler.py` | **extend (S1..S3)** | client-model capability keys; required/optional handling; email and DHCP actions and expectations; `message_ref`; authority invariant |
| `domain/enterprise/mutation_replay.py` | **extend (S1b, S2, S3)** | every new family registered explicitly; `EXECUTE_ONCE` families `UNKNOWN`/`UNMEASURED` until a controlled repeat is recorded |
| `application/use_cases/apply_services.py` | **extend (S0, S1, S3)** | fact propagation, decision table consumer, frontier, recovery reads, aggregation, evidence (S0); per-target capability and required/optional (S1); DHCP-mode foundation (S3) |
| `application/use_cases/apply_configuration.py` | **extend (S1, P-E5-2, bounded)** | `excluded_action_ids` with `SKIPPED/OUT_OF_SCOPE` rows and the closure invariant |
| `application/use_cases/foundational_evidence.py` | **extend (S1)** | plan-agnostic core predicate shared with `_endpoint_core_is_verified`; `derive_service_foundational_statuses` |
| `application/use_cases/compose_enterprise_reference.py` | **extend (S1, S3)** | `services`, `service_capabilities`; `configuration_policy` derived once (`derive_service_policy`: DNS server for clients, delegated DHCP segments) |
| `application/use_cases/apply_enterprise_services.py` | **new (S1)** | the workflow of 2.1 |
| `application/ports/secret_resolver.py`, `infrastructure/execution/secret_resolver.py` | **new (S2)** | `SecretResolver` port and local resolver |
| `infrastructure/execution/transport_outcome.py` | **new (S0)** | `BridgeDispatchOutcome`; imports only domain facts |
| `infrastructure/execution/live_bridge.py`, `file_bridge.py` | **extend (S0, additive)** | `correlated_http_dispatch`, `dispatch_and_wait` on both transports; legacy functions unchanged with differential characterization tests |
| `infrastructure/execution/enterprise_service_runtime.py` | **extend (S0, S1b, S2, S3)** | `_observe`, bracketing reads, row validation, fact derivation, observation facts, HTTPS mode, release paths (S0); content contract (S1b); email, DHCP, claims and the event lifecycle (S2, S3, gated) |
| `infrastructure/execution/enterprise_security_runtime.py::_typed_http` | **defer** | D-1 |
| `infrastructure/catalog/service_capabilities.py` | **rewrite (S1)** | explicit evidence table per build with provenance level; unknown build yields UNKNOWN; client operation keys; consistency validation |
| `infrastructure/persistence/service_run_record_store.py` | **new (S1)** | run record with the lifecycle of 4.8, mirroring `deployment_manifest_store.py` containment (`safe_name_component`, `resolve_within`, tmp + replace) |
| `adapters/mcp/service_tools.py` | **new (S1)** | registration and JSON translation only; receives the registry's transport closures |
| `adapters/mcp/tool_registry.py` | **extend (S1, minimal)** | one import and one call inside `register_tools`; debt owned per 4.9 |
| `application/use_cases/qualify_server_services.py`, `adapters/cli/service_qualification.py` | **new (S4a)** | staged qualification runner (5.8), patterned on `cp_scale_live.py` |
| `application/use_cases/execute_enterprise_reference.py` | **defer** | D-6 |
| `endpoint_address_observer.py`, `typed_ping.py`, `command_dispatch.py` | **reuse** | IP/mask read-back, typed dispatch with pager guard and fresh window |
| `tests/test_typed_ping.py` harness pattern | **reuse (S0)** | Node stub harness for generated scripts |
| `EXTENSION/`, CP-SCALE, voice, PoE, namespace controls | **do not touch** | out of scope |

### 2.3 Layer boundaries

- Domain: models and compiler rules only; the fact enums are domain
  vocabulary in `execution.py`; no Cisco names, no JavaScript, no bridge
  imports (`tests/test_e95_architecture_boundaries.py:24`).
- Application: orchestration and admission, E5 closure, foundation
  derivation, capability resolution, secret port, run record lifecycle.
- Infrastructure: process and member names, `json.dumps` serialization,
  transports and their fact classification, persistence, secret storage.
- Adapters: input validation and JSON rendering; `service_tools.py` holds no
  transport logic.

### 2.4 Product entry point and rejected alternatives

`[DECISION]` unchanged: `pt_apply_enterprise_services` on the `enterprise`
surface, bound to a `DeploymentManifest` from `pt_live_deploy`. Rejected
alternatives: exposing `execute_enterprise_reference` (empty workspace and
always cleans up); an E6-only tool with caller-supplied foundations; a
read-only foundation reread as the first slice (D-3); wiring services into
`pt_live_deploy`; registering only from `server.py` (cannot share the
closure-scoped bridge session, `tool_registry.py:918, 937, 1520`).

---
## 3. API and capability evidence matrix

All `[CISCO]` rows come from the local reference
`C:\Program Files\Cisco Packet Tracer 9.0.1\help\default\IpcAPI\class_<name>.html`
(edition 8.1.0). Process names come from `Device::getProcess`: `DhcpClient`,
`DhcpServerMain`, `DhcpServer`, `DnsClient`, `DnsServer`,
`HttpBackgroundClient`, `HttpBackgroundClientManager`, `HttpClient`,
`HttpServer`, `HttpsServer`, `EmailClient`, `EmailServer`, `Pop3Client`,
`Pop3Server`, `SmtpClient`, `SmtpServer`. Documented is not supported;
capability columns use the repository vocabulary (`CapabilityStatus`,
`ReadinessStatus`) and, from revision 2.1, a provenance level
(`documentary_baseline` or `recorded_run`, R-CAP-07).

### 3.1 HTTP

| Aspect | Reference |
| --- | --- |
| Server | `HttpServer::setEnable/isEnabled`, `setPortNumber/getPortNumber`, `setPageContents(url, contents)`, `getPage(url)`, `setUsername/setPassword/getUsername/getPassword` (htaccess; plaintext getter, never read) `[CISCO]` |
| Client | `HttpBackgroundClientManager::createClient() -> HttpClient`, `deleteClient(HttpClient)`; `HttpClient::go(url) -> bool` ("true if successful", not completion), `getLastPageContent()`, `cancel()`, `setHttps(bool)`, `isHttps()`, events `onStart(string)`, `onDone(string, ip, HttpResponseType, string)`; `HttpResponseType` values undocumented `[CISCO]` |
| Existing evidence | apply, direct read-back and fresh background-client fetch `SUPPORTED` for 9.0.1.0858 at provenance `documentary_baseline` (`service_capabilities.py:22`; `enterprise-services.md:102-118`; no run id, SHA or transport recorded) `[EVIDENCE]` |
| Predicate | fresh content differs from `content_before` and contains the marker; owned client released (`enterprise_service_runtime.py:318-378`) `[REPO]`; revision 2.1 observation facts in 4.5 |
| Reader compatibility after S0 | the http-scheme verification scripts (start, inspect, release) are byte-identical to the baseline (golden test); the mutation script changes its observation bracket, not its setter calls |
| `[GATE]` M-HTTP-1 | `onDone` argument semantics (optional; polling is the supported path) |

### 3.2 HTTPS

| Aspect | Reference |
| --- | --- |
| Class | `HttpsServer` inherits `HttpServer`; own members `setHttpsEnable(bool)`, `isHttpsEnabled()`; inherits `setPageContents/getPage/setPortNumber/...` `[CISCO]` |
| Client | `HttpClient::setHttps(bool)`, `isHttps()` `[CISCO]` |
| Repository state | compiles `EnableHttpsService` only; runtime `go("https://...")` without `setHttps(true)`; empty marker accepted `[REPO]`; readiness apply `PARTIAL`, verify `UNKNOWN` (`service_capabilities.py:58-70`) |
| S0 predicate | the start payload reports `https_mode` from `isHttps()` after `setHttps(true)`: true continues, false is CONTRADICTED (`https_mode_not_confirmed`), absent is MALFORMED; fresh content containing the marker is OBSERVED; an empty marker is PARTIAL `no_https_marker` |
| `[GATE]` M-HTTPS-1 | whether `getProcess("HttpsServer")` is the same object as `getProcess("HttpServer")` and whether `setPageContents` on one is visible through `getPage` on the other; decides the S1b contract (`SetHttpsContent` or `shared_content`) |
| `[GATE]` M-HTTPS-2 | whether a client with `setHttps(true)` retrieves the page when only HTTPS is enabled and HTTP is disabled, and fails when HTTPS is disabled; expected negative control: fetch fails with HTTPS disabled; contradiction: a fetch succeeds in https mode with HTTPS disabled |

### 3.3 DNS

| Aspect | Reference |
| --- | --- |
| Server | `DnsServerProcess::setEnable/isEnabled`, `setPortNumber(int)/getPortNumber`, `addARecordToNameServerDb(domainName, address) -> bool`, `getARecordWithAddress(domainName, ip) -> DnsRrA`, `isDomainNameExisted`, `getIpAddOfDomain -> ip`, `removeARecordFromNameServerDb`, CNAME/NS/SOA add/get/remove, `getSizeOfNameServerDb`, `getRrFromNameServerDbAt` `[CISCO]`; no MX member; `addIpAddress` is the legacy table and is not wire-operational (`enterprise-services.md:116-118`) `[EVIDENCE]` |
| Client | `DnsClient::getServerIp() -> ip`, `setServerIp(ip)`, `getIpOfHost(hostname) -> vector<ip>`, `isHostNameExisted`, `addIpAddress` (local table; never resolution evidence) `[CISCO]` |
| PC terminal | `Pc::getCommandPrompt() -> TerminalLine`; `TerminalLine::enterCommand(string)`; `ConsoleLine::getOutput()`; events `commandEnded(inputCommand, CommandStatus)`, `outputWritten(newOutput, isDebug, cursorPositionFromEnd)` `[CISCO]` |
| Native commands | `config_PCs.htm` lists `nslookup`, `ping`, `ipconfig`; no flags documented `[CISCO]` |
| Client DNS configuration path | E5 `SetEndpointStaticAddress.dns_server` -> `configurePcIp(..., dnsServer, ...)` -> `HostPort.setDnsServerIp` for a non-empty value (`enterprise_configuration_runtime.py:841-858`, `main.js:280-310`); `policy.dns_server` is `None` by default, so nothing sets it on the public path `[REPO]` (R-NET-02) |
| Existing evidence | typed `ping <hostname>` fresh window plus negative control `SUPPORTED` at provenance `documentary_baseline` (`_verify_dns`, `service_capabilities.py:40`) `[EVIDENCE]` |
| Predicates | positive: a complete fresh window (contains `packets: sent`) with the expected address is OBSERVED; a complete window with a different address or a not-found line is CONTRADICTED; negative control: a not-found line is OBSERVED and a resolution is CONTRADICTED; an incomplete window at the deadline, a refused command (pager active) or a command that did not start is INCONCLUSIVE `[REPO]` + 4.5. The ping reader cannot distinguish a client-cached answer from a fresh query; the claim is "client resolves name to expected address" |
| New direct read-back | `CLIENT_DNS_SERVER`: `pc.getProcess("DnsClient").getServerIp()` equals the service address; a new reader, optional until M-DNS-3 (R-CAP-06) |
| `[GATE]` M-DNS-1 | `nslookup <name>` output lines for success, NXDOMAIN and timeout (S5) |
| `[GATE]` M-DNS-2 | whether `DnsClient.getIpOfHost` reflects a clearable cache (fresh-query control, S5) |
| `[GATE]` M-DNS-3 | `getServerIp()` read on a PC configured through E5 (value format, emptiness when unset) |
| `[GATE]` M-DNS-4 | whether `getSizeOfNameServerDb` and `getRrFromNameServerDbAt` return a complete, stable A-record table before and after `addARecordToNameServerDb`, including the replace-or-append behavior for an existing name (Q1 candidate); until measured the attempted `AddDnsRecord` footprint is PARTIAL (RD-11) and S0 does not call them |

### 3.4 SMTP

| Aspect | Reference |
| --- | --- |
| Server | `SmtpServer::setEnable/isEnabled`, `setServerDomainName/getServerDomainName` `[CISCO]` |
| Accounts | `EmailServer::addUser(name, password) -> bool`, `deleteUser(name) -> bool`, `changePassword(name, newpassword)`, `getEmailUser(username) -> EmailUser`, `updateAllAccounts("name:password;...")`, `getAllEmailAcctAsStrings()` (plaintext, never call) `[CISCO]`; the boolean of `addUser` for an existing user is undocumented `[GATE M-MAIL-3]` |
| `EmailUser` | `get/setUser`, `get/setName`, `get/setMailId`, `get/setPassword` (getter never called), `get/setSmtpServer`, `get/setPop3Server`, `getMailBox() -> MailBox` `[CISCO]` |
| Server mailbox | `MailBox::getMails() -> vector<Mail>` with `Mail{from, rcpt, subject, content, dateTime}`, `deleteMailAt(int)` `[CISCO]` |
| Client | `EmailClient::getEmailUser()`, `getSmtpClient()`, `getPop3Client()`; `SmtpClient::sendMail(fromEmailId, toEmailId, subject, contents, password, ipAddr) -> bool`, `cancelSend()`; event `mailSent(dest, subject, body, SmtpResponseType)` with `eSmtpRequest=1, eSmtpResponseSuccess=2, eSmtpRequestForward=3, eSmtpRemoteReceieverDoesNotExist=4, eSmtpResponseError=5, eSmtpTimeout=6, eSmtpPeerReset=7, eSmtpDnsServerNotFound=8, eSmtpDnsUnResolvedHostName=9, eSmtpProtocolError=10, eSmtpUserNotFound=11, eSmtpServerDomainError=12, eSmtpServerNotFound=13` `[CISCO]` |
| Predicate | `SMTP_SEND`: `sendMail` dispatched once under a pre-effect claim with the message nonce in subject and body; a captured `mailSent` whose subject equals the nonce and `responseType == 2`; anything else is not success. `SMTP_DELIVERED` (read-only supporting state): the recipient's server `MailBox.getMails()` contains the nonce subject |
| `[GATE]` M-MAIL-1 | whether `sendMail` uses the client `EmailUser` fields and whether `ipAddr` accepts a hostname |
| `[GATE]` M-MAIL-2 | delivery of `mailSent` to a Script Engine `registerEvent` callback and its `args` member names |

### 3.5 POP3

| Aspect | Reference |
| --- | --- |
| Server | `Pop3Server::setEnable/isEnabled` `[CISCO]` |
| Client | `Pop3Client::getMailIpc() -> bool` ("always returns true"); events `mailReceived(sender, subject, dateTime, body)`, `errorReceivingMail(Pop3ResponseType)` with `ePop3Request=1, ePop3ResponseSuccess=2, ePop3ResponseError=3, ePop3Timeout=4, ePop3PeerReset=5, ePop3DnsServerNotFound=6, ePop3DnsUnResolvedHostName=7, ePop3ProtocolError=8, ePop3UserNotFound=9`; `cancelReceive()` `[CISCO]` |
| Predicate | `POP3_RETRIEVE`: `getMailIpc()` dispatched once under a pre-effect claim after registering; a captured `mailReceived` whose subject and body equal the message nonce for that account; unrelated messages are never reported or counted; `errorReceivingMail` is a typed failure; the boolean return is recorded as dispatched only |
| `[GATE]` M-POP3-1 | which `EmailUser` fields `getMailIpc` reads; one `mailReceived` per message or not |
| `[GATE]` M-POP3-2 | whether retrieval removes the message from the server |

### 3.6 DHCP (Server-PT)

| Aspect | Reference |
| --- | --- |
| Server | `DhcpServerMainProcess::getDhcpServerProcessByPortName(portName) -> DhcpServerProcess`; `DhcpServerProcess::setEnable(bool)`, `isEnable()`, `addPool(name)`, `addNewPool(name, gateway, dns, startIp, mask, maxUsers, tftp, wlc)`, `getPool(name)`, `getPoolCount()`, `getPoolAt(i)`, `removePool`, `addExcludedAddress(ip, ip)`, `getExcludedAddressCount/At`, `updateNetworkReservation(ip)` (undocumented meaning) `[CISCO]` |
| Pool | `DhcpPool` getters `getDhcpPoolName, getDefaultRouter, getDnsServerIp, getStartIp, getEndIp, getSubnetMask, getNetworkAddress, getMaxUsers, getDomainName, getTftpAddress, getWlcAddress`, setters `setDefaultRouter, setDnsServerIp, setStartIp, setEndIp, setMaxUsers, setNetworkAddress, setNetworkMask(network, mask), setNextAvailableIpAddress`; `getLeaseAt(int) -> DhcpPoolLease{ipAddress, macAddress, leaseTime, port}`; **no lease count getter and no documented end-of-table behavior** `[CISCO]` |
| GUI semantics | `config_servers.htm`: pool fields are Pool Name, Default Gateway, DNS Server, Starting IP, Subnet Mask, Maximum Users `[CISCO]` |
| Client | `Pc::setDhcpFlag/getDhcpFlag`; `HostPort::isDhcpClientOn()`, `setDhcpClientFlag(bool)`, `getIpAddress()`, `getSubnetMask()`, `getMacAddress()`, `getBia()`; `DhcpClientProcess::dhcpRun(port)`, `dhcpRelease(port) -> bool`, `resetDhcpConfOn(port) -> bool`, `isPortExisted(port)`, `getDataOfPort(port) -> DhcpClientPortData.getLeaseTimeStr()`; events `dhcpSucceed(deviceName, portName, newip, newmask)`, `dhcpFailed(deviceName, portName)`, `dhcpConfigured(deviceName, portName, isConfigured)` `[CISCO]` |
| Corrections | `isEnable`, not `isEnabled`; `getMacAddress()` documented on `HostPort` and `Port` (M-DHCP-4 closed as documented, unmeasured); `isDhcpClientOn()` is the documented DHCP-mode getter (M-DHCP-5); `getLeaseTimeStr()` has no documented format or behavior (M-DHCP-6) |
| Predicates | section 4.5 (R-DHCP-04, R-DHCP-05, R-DHCP-07, R-DHCP-08) |
| `[GATE]` M-DHCP-1 | `addPool(name)` plus setters yields a serving pool, or `addNewPool` is required; what `tftpServerIp`/`wlcIp` accept |
| `[GATE]` M-DHCP-2 | the end-of-table contract of `getLeaseAt(i)` (null, throw, or repeat) and how a completed scan is recognized |
| `[GATE]` M-DHCP-3 | `dhcpSucceed` delivery to a `registerEvent` callback and its `args` names; `dhcpRelease` on a PC with `setDhcpFlag` true |
| `[GATE]` M-DHCP-4 | value of `getMacAddress()` on a PC port versus the lease row `macAddress` |
| `[GATE]` M-DHCP-5 | `isDhcpClientOn()` read on the manifest-bound interface |
| `[GATE]` M-DHCP-6 | `getLeaseTimeStr()` behavior: no-acquisition negative control over time (does it change by itself), automatic renewal, requested renewal |

### 3.7 Cross-cutting engine facts

| Fact | Source |
| --- | --- |
| File channel: queued JS runs as `(new Function("reportResult", js))(report)`; `this` at file scope is the engine global (`var GLOBAL = this`) | `[REPO]` `main.js:133-142, 225` |
| File channel: only names matching `req_*` with suffix `.js` are executed (`f.slice(-3) === ".js"`); a `.js.tmp` residue is never executed | `[REPO]` `main.js:171-181` |
| HTTP channel: the webview polls `/next` and hands the batch to `$se('runCode', text)`; the receiver of `this` inside `runCode` is not verified in source | `[REPO]` `interface.js:50-61, 528-540`; `[GATE]` M-ENG-1 |
| HTTP channel: the webview logs a 120-character preview of each batch (`interface.js:529-530`); the wrapper prefix `report_result_js(...)` is 347 characters and the user script starts at offset 352, so the preview never reaches the script body and the token is not within the first 120 characters | `[REPO]`, `[MEASURED]` |
| The existing HTTP verification already relies on bag persistence across three calls (`this.__mcpE6HttpClients`, `enterprise_service_runtime.py:380-413`); the baseline record does not say on which channel it was measured | `[REPO]`, provenance gap |
| Script Engine events: `object.registerEvent("eventName", obj, callback)`; `callback(src, args)`; `src` has `className`, `objectUuid`, `eventName`; `args` members follow the pki definition; registration and callbacks must live in the script engine | `[CISCO]` `scriptModules_scriptEngine.htm` |
| Unregistration: `_ScriptModule.unregisterIpcEventByID(className, uuid, eventName, obj, callback)` is used by the maintained extension for a `MenuItem`; no reference page documents it; only `MenuItem` exposes a uuid getter | `[REPO]` `main.js:16`; `[CISCO]` absence |
| One script evaluation is not interleaved with another in the engine's JavaScript thread | `[INFERENCE]` from JavaScript execution semantics; not vendor-documented; the claim lifecycle of 4.6 relies on it and Q0 records any observed counterexample |
| No product runtime registers events; all observation is polling | `[REPO]` |
| Pasted `executeCode` source loses newlines; generated scripts are single-line without `//` comments | `[REPO]` `AGENTS.md` |

### 3.8 Corrections to the attached research (consolidated)

| Research claim | Correction |
| --- | --- |
| All six services "Supported" | documented only; DNS and HTTP behavioral `SUPPORTED` at documentary provenance; HTTPS `UNKNOWN`; SMTP, POP3 and DHCP have no runtime evidence |
| `DeviceFactory` enumeration recommended | not needed; identity comes from the `DeploymentManifest` and `resolve_manifest_targets` |
| `nslookup` proven | documented, output unmeasured; parser conditional on M-DNS-1 |
| `ipconfig /release`, `/renew` documented | only `ipconfig` is listed; the API path `DhcpClientProcess` is the client operation |
| `dhcp.isEnabled()` | member is `isEnable()` |
| `getMailIpc()` returns true | confirmed; recorded as dispatch, never retrieval |
| `mailReceived.sender == "alice@lab.test"` | format undocumented; correlate on nonces |
| `HttpsServer.setPortNumber(443)` | inherited; HTTPS port and page ownership unresolved (M-HTTPS-1/2) |
| Pipeline order "DHCP, then DNS, then HTTP" | replaced by the dependency graph of 4.5 |
| `TerminalLine.commandEnded` as completion signal | unused; the proven path is polling `getOutput()` with a fresh window |
| Event unregistration available | not documented; observed extension usage only |

---

## 4. Change brief and design

### 4.1 Problem and intended outcome

Problem: Server-PT services exist only as an unexposed E6 stage; email and
Server-PT DHCP are absent; no MCP invocation configures or verifies services;
transport, runtime and application distinctions are lost: a timeout reads as
"never sent", a successful run reads as "residue unknown", a failed setter
that changed the state reads as "clean", a fresh read of an unchanged value
would read as "probe failed", and a fresh contradiction reads as "no fresh
evidence".

Outcome: one MCP invocation configures the requested services on a selected
Server-PT for a selected set of PC-PT clients, verifies each service per
client with fresh, attributed evidence, leaves the topology usable, releases
only owned temporaries, persists a run record whose lifecycle is defined for
every exit, and reports per-service and per-client statuses without secrets
and without claims stronger than what was observed.

### 4.2 Scope and exclusions

In scope: section 2.2 rows marked extend, new or rewrite; the six services;
single client and explicit client sets; co-hosting on one Server-PT; the
bounded first topology of R-NET-01 with routed single-gateway clients as a
later slice (S1c); typed offline tests; the staged qualification design.

Out of scope: IoT; `.pts` or runtime replacement; NTP/TFTP features beyond
regression; high availability; MX records; real TLS guarantees; DHCP relay;
DHCPv6; automatic repair of conflicting DHCP authorities; GUI paths; changing
the file bridge protocol; a general routing expansion; extracting the bridge
session out of `register_tools` (D-8); the E5 applicator's own error-loss
paths beyond the containment of R-RET-02 (D-9); `apply_security.py` (D-10);
secret rotation as a feature.

### 4.3 Requirements and acceptance predicates

Definitions:

- **Channel acceptance** (`dispatch`): the transport proved that the request
  entered the channel (HTTP: the local bridge answered 200 on `/queue`; file:
  the request file was published). It produces `APPLIED`
  (`configuration_runtime.py:19-62, 201-232`) and never means Packet Tracer
  executed anything.
- **Attempt knowledge** (`result`): whether a correlated result was received
  and parsed (CORRELATED), the engine reported an error (ENGINE_ERROR), the
  body was not a valid response (MALFORMED), no result arrived (NOT_OBSERVED)
  or the result slot was lost (LOST).
- **Observed transition** (`transition`): whether the bracketing reads before
  and after the setter differ (CHANGED), are equal (UNCHANGED) or could not
  both be read (UNOBSERVED). A transition is reported as "observed between
  the two bracketing reads of this dispatch"; it is never a proof of
  execution count or of sole causation.
- **Postcondition** (`postcondition`): whether the post-read equals the
  intended value (SATISFIED), differs (UNSATISFIED) or was not obtained
  (UNOBSERVED).
- **Residual change**: `transition is CHANGED and postcondition is UNSATISFIED`.
- **Fresh read**: a correlated result of a read dispatched in this run for
  this expectation that parsed to the typed shape and located its subject.
  Freshness does not require the value to differ from a previous value. A
  fresh read that contradicts the expectation is fresh negative evidence.
- **Inconclusive read**: a completed read whose predicate cannot decide
  (marker present before the request, incomplete window, refused command);
  it is neither evidence for nor against the service.
- **Effect classes** of verification kinds: read-only (`DIRECT_SERVICE_STATE`,
  `NTP_SYNC`, `TFTP_RETRIEVE`, mailbox listing, lease table), owned-temporary
  (`DNS_RESOLUTION`, `DNS_NEGATIVE_CONTROL`, `HTTP_FETCH`, `HTTPS_FETCH`,
  `HTTP_BY_HOSTNAME`), user-state (`SMTP_SEND`, `POP3_RETRIEVE`,
  `AcquireDhcpLease`).
- **Required versus optional**: `ServiceRequirement.required` (exists,
  currently unconsumed) decides whether an ineligible service refuses the run
  or is excluded; `verification_required` decides whether its expectations
  are required; advisory readers are always optional (R-ENTRY-11).

| ID | Requirement | Acceptance predicate | Slice |
| --- | --- | --- | --- |
| R-ENTRY-01 | `pt_apply_enterprise_services(intent_json, deployment_id, packet_tracer_version, run_label="")` registered on the `enterprise` surface from `service_tools.py`, documented in `docs/tools.md` | tool listed; invalid JSON returns a structured error without contacting the bridge | S1 |
| R-ENTRY-02 (rev2.1) | Admission A1..A10 completes before the first user-state mutation; admission may perform directed reads (manifest identity, endpoint pre-read, capability and secret resolution); `TEST_PROCESS`, foreign trees, version mismatch, unresolved secrets and ineligible required services are refused | recording fake proves zero mutating runtime calls before every gate and records every admission read; each refusal has a typed code | S1 |
| R-ENTRY-03 | manifest binding: composed hash equals `manifest.physical_topology_hash`; `validate_manifest_environment` passes; every host and client resolves through `resolve_manifest_targets` | mismatch returns `TARGET_IDENTITY_MISMATCH`/`ENVIRONMENT_FINGERPRINT_MISMATCH` with zero mutations | S1 |
| R-ENTRY-04 | foundations come only from executed E5 verification rows through `derive_service_foundational_statuses`, reusing the hash-bound, field-specific core predicate of `_endpoint_core_is_verified` (`foundational_evidence.py:96-153`) keyed by `configuration_action_id`; a satisfied IPv4/netmask core never promotes the E5 row, gateway, DNS or any other action | no status parameter; PARTIAL endpoint with verified core and matching `source_configuration_hash` accepted; mismatched hash, stale method, missing `fresh_evidence` or non-endpoint PARTIAL not | S1 |
| R-ENTRY-05 | response: per service and per client status, `observation`, `claim_level`, `limitations`, `e5_effect_scope`, `persisted_stage`, `record_path`, `run_id`, `transport`, `packet_tracer_version`, `provenance` per capability used; no secret, no script | schema test; redaction test with a fixture secret in raw, JSON-escaped and URL-encoded forms | S1 |
| R-ENTRY-06 (rev2.1) | run record lifecycle (4.8): A1 and A2 failures return without a record; A3 to A5 failures write an unbound admission record when the store is writable, else return the refusal with `record: none`; A6 creates the bound record before any effect and refuses the run if it cannot; every stage rewrites it atomically; when a rewrite fails after the first effect, no further user-state mutation is dispatched, bounded read-only observation and owned-resource cleanup continue, the primary error is preserved and the response reports `persisted_stage` (last durable stage) and `persist_error` | store tests: rejection before A6; persistence failure before and after the first effect; interrupted run leaves the last stage; corrupt file refused; no new mutation after persistence is lost | S1 |
| R-ENTRY-07 | product use never removes user devices, links, services, accounts or messages; deletions are owned background clients, owned event registrations and owned bag entries only | grep-level test on the product path for `removeDevice`, `removePool`, `deleteUser`, `deleteMailAt` | S1, S2 |
| R-ENTRY-08 | owned temporaries are released on success, failure, timeout, contradiction, exception and transport uncertainty; outcome recorded (`released`, `release_failed`, `release_unverified`) | runtime tests per exit path | S0 |
| R-ENTRY-09 | E5 effect scope is the closure C of the E6 foundational action ids over `depends_on` and `apply_dependencies`; first application: `mutation_action_ids=C`, `excluded_action_ids=plan−C` (P-E5-2); re-run: retained results per R-RET-01; endpoints in C are pre-read and a non-empty different address refuses with `EXISTING_CONFIGURATION_CONFLICT`; the scope is disclosed | integration test with the real composition and applicator over an injected runtime: exactly C reaches the runtime; excluded rows `SKIPPED/OUT_OF_SCOPE`; conflict refuses with zero effects | S1 |
| R-ENTRY-10 | every operation-level check (capability for every action and required expectation on its target model, secret resolution, transport eligibility, service eligibility) completes before the first E5 effect; an unknown mutation is never dispatched | ordered recording fake; a plan with one unknown required client operation refuses before E5 | S1 |
| R-ENTRY-11 (new) | eligibility: a service is eligible when every action and every required expectation resolves `SUPPORTED` on its target; an ineligible service with `required: true` refuses the run before effects (`SERVICE_INELIGIBLE`); an ineligible optional service is excluded before E5 compilation of its closure and reported `SKIPPED` with the unknown operations named; optional expectations (advisory readers, `verification_required=False`) never gate eligibility and never report VERIFIED for a capability they lack | composition and admission tests for required/optional mixes; the sample response of 4.10 is produced only with HTTPS marked optional | S1 |
| R-NET-01 (new) | first supported topology: one site, one segment, the Server-PT and the selected PC-PT clients on that segment, static server and static clients, no routed client (`SERVICE_PATH_UNSUPPORTED`); closure C therefore covers the endpoint, access-port and VLAN actions of the selected devices; a single-gateway routed topology is slice S1c with explicit L3 path ownership; multi-router paths need E9 and are out of scope | composition tests: routed client refused; C enumerated exactly | S1 |
| R-NET-02 (new) | client DNS derivation: `derive_service_policy(intent)` in composition sets `ConfigurationPolicy.dns_server` from the requested DNS service's explicit `address` (a DNS service without an explicit address is `DNS_SERVER_ADDRESS_REQUIRED` in S1); E5 places it on every static endpoint (`SetEndpointStaticAddress.dns_server` -> `configurePcIp` -> `setDnsServerIp`); for DHCP-served clients (S3) the pool's `setDnsServerIp` carries it; `CLIENT_DNS_SERVER` is an observation, not a configuration action | integration test from the MCP input with an initially unset policy: the E5 action and the recorded runtime call arguments carry the address | S1 |
| R-OBS-01 | transport outcomes are typed `BridgeDispatchOutcome(dispatch, result, body, disposition, detail)` per the tables of 4.4; legacy `send_and_wait` functions unchanged, with differential characterization tests as regression guards and independent truth tables plus real-socket tests as the oracle | table tests; socket tests (refused, hanging, no-webview, duplicate rid, late result); file phase tests | S0 |
| R-OBS-02 (rev2.2) | every mutation row carries `dispatch`, `result`, `postcondition`, `transition`, `footprint`, `attempted` and `cause`; `decide_mutation` (4.4) is the single decision of 4.5 and runs legacy-default detection and validity before outcome classification; `mutation_execution_status` is its status projection; every consumer reads status, disposition, failure code, residue, frontier and sticky from the decision; rows with every fact at its default map as at the baseline; contradictory received facts are preserved as diagnostics and grant nothing; no mutation is re-dispatched and no channel changes after ambiguity | domain table test over the full fact product asserting safety predicates (never equality with a copy of the table); legacy-identity test | S0 |
| R-OBS-03 | fresh read and inconclusive read as defined; subject not found, malformed or engine error is UNOBSERVABLE; not observed, lost or acceptance unknown is UNKNOWN; a contradiction is FAILED with `fresh_evidence=True`; an unchanged value freshly read is VERIFIED; an inconclusive read is UNKNOWN with `fresh_evidence=False` | runtime tests per fact; golden getter script | S0 |
| R-OBS-04 | one client operation at a time per client device; one server batch at a time; no concurrent verification on one device; an `EmailClient` is never reconfigured while an operation on it is unresolved | serialization test with an interleaving fake | S2 |
| R-OBS-05 | late, duplicate or foreign callbacks never satisfy a newer operation: bag entries keyed by `(run_token, op_id)`, receipt sequence compared with the dispatch sequence, and exclusive subject ownership with quarantine (R-EVT-07) | runtime tests with injected stale, foreign and reordered events | S2, S3 |
| R-OBS-06 (rev2.1) | error kind, stage and cause travel as typed fields through transport (`BridgeDispatchOutcome`), runtime (`RuntimeActionMutation` with `dispatch`, `result`, `postcondition`, `transition`, `footprint`, `attempted`, `cause`; `RuntimeServiceVerification.observation/cause`), applicator (`ActionApplicationResult` with the received facts plus the decision outputs, `ServiceVerificationResult.failure_code`), journal (`ExecutionJournalEntry.dispatch/result/residual_change/cause`), evidence (`EvidenceRecord.observation_status/limitations`) and JSON; message prefixes are never parsed; exceptions and malformed rows are UNKNOWN, never FAILED; earlier rows are preserved; `UNSPECIFIED` (producer stated nothing) is distinct from `NOT_ATTEMPTED` | round-trip test through the real applicator, journal and evidence mapper with serialize and deserialize; legacy JSON fixture validates | S0 |
| R-OBS-07 (rev2.2) | E6 mutation scripts bracket every setter with typed reads and always post-read; `ok` and `changed` are computed from the actual typed before/after values inside the same evaluation; digests are bounded diagnostics and never derive a fact; a native add return never stands for a read-back; each S0 family states its observation scope and effect footprint (4.5) and a transition is proven only within the state read; dispositions derive from `(postcondition, transition, footprint, attempted)`: NO_OP, REASSERTED, CHANGED, FAILED without residual, FAILED with residual, UNKNOWN; a fully successful run of COVERED families has `dirty_state=CLEAN`; a run that attempts a PARTIAL-footprint action has `dirty_state=UNKNOWN` with the limitation named (RD-11); a failed run with an observed unintended change has `dirty_state=DIRTY_*` (RD-10); an uncertain run has `dirty_state=UNKNOWN` | Node harness scenarios of 6.5 through the real applicator with expectations from the stub state; RED at baseline (`dirty_state=unknown` for success; CLEAN for changed-to-wrong, for the digest-collision pair and for an incorrect add) | S0 |
| R-OBS-08 (rev2.2) | frontier: `effect_established` is the `frontier` output of `decide_mutation` (a validated SATISFIED postcondition; legacy rows: `satisfies_apply_dependency`) and never the raw `postcondition` field; dependents of a non-established action are DEPENDENCY_BLOCKED (`prerequisite_outcome_unknown` or `prerequisite_unsatisfied`); independent actions and services continue; read-only and owned-temporary expectations of a non-established action run as recovery reads with a limitation; user-state expectations are blocked; sticky effect uncertainty is set exactly when the decision's `sticky` output is True for any action (rows 3 to 8, 10, 15, 19 and every inconsistent tuple); the bundle is never VERIFIED while it is set; a recovery read never changes the action row and never claims execution count | applicator tests per row of the decision table | S0 (rule), S2/S3 (user-state kinds) |
| R-EVD-01 (rev2.1) | E6 evidence records come from `evidence_from_service_verification`: `UNSPECIFIED` delegates to `evidence_from_legacy_result`; explicit facts map per 4.5; the verification row, the record classification and the summary agree by behavior (an UNKNOWN row with a PROBE_FAILED record is consistent) | agreement table; legacy rows identical to the baseline adapter | S0 |
| R-TEST-01 (new) | before implementing S0 the implementer inventories every assertion and fixture contract of the affected test modules and classifies each as valid invariant, incidental representation or known incorrect expectation; only the changes listed in 6.5 are authorized, each with a before/after rationale in the brief; the generated mutation script is proven by the Node harness, not by a fake's disposition | inventory committed in the brief; harness fails rather than skips under `GITHUB_ACTIONS` | S0 |
| R-HTTP-01 | enable, content and port read-back preserved (setter calls unchanged; typed observation bracket added; footprint COVERED) | existing script-substring assertions; harness scenarios "unchanged success" and "digest-collision pair" for `SetHttpContent` | S0, S1 |
| R-HTTP-02 | per selected client a fresh HTTP fetch by address with the marker through an owned background client; per-client expectation count equals the selected clients | existing `_verify_http` predicate with 4.5 observation facts; compiler count test | S1 |
| R-HTTP-03 | HTTP by hostname stays composed on `DNS_RESOLUTION` and `HTTP_FETCH` | `test_http_hostname_is_dependency_blocked_when_dns_resolution_fails` unchanged | S1 |
| R-HTTPS-01 | enable and read back `isHttpsEnabled()`; HTTPS content is `SetHttpsContent` if M-HTTPS-1 shows separate page tables, or `shared_content` on `SetHttpContent` if one table; implemented in S1b and qualified per R-QUAL-05 | compiler and runtime script tests for the selected contract | S1b |
| R-HTTPS-02 | client HTTPS mode: `setHttps(true)` before `go`, `https_mode` from `isHttps()` in the same payload; true continues, false is CONTRADICTED `https_mode_not_confirmed`, absent is MALFORMED; the http-scheme scripts are byte-identical | runtime tests for the three values; golden http scripts | S0 |
| R-HTTPS-03 | an empty marker never yields VERIFIED for https: PARTIAL with `no_https_marker` | authorized change to `tests/test_service_runtime.py:318-345` | S0 |
| R-HTTPS-04 | behavioral VERIFIED for HTTPS requires readiness `verify=READY` set only by a recorded run at the executed SHA (R-QUAL-05) | catalog test | S1, Q1, S1b |
| R-DNS-01 | A-record apply and read-back preserved (add call unchanged when attempted; wanted-record membership read before and after; `ok` from the post-read only; the add is skipped when the pre-read already shows the wanted record; footprint PARTIAL when attempted, RD-11) | script substrings; harness scenarios "add returns true, membership missing", "incorrect add changes another record", "add replaces an existing record", "add already present" | S0 |
| R-DNS-02 | per client a fresh resolution and a negative control; per-client count | existing predicates with 4.5 facts; compiler count test | S1 |
| R-DNS-03 | `CLIENT_DNS_SERVER` direct read-back per client (`DnsClient.getServerIp()` equals the service address), optional per R-CAP-06 | runtime and compiler tests; optional flag | S1 |
| R-DNS-04 | `DNS_LOOKUP` via `nslookup` compiled only when the catalog marks it SUPPORTED after M-DNS-1 | conditional slice S5 | S5 |
| R-CAP-01 | catalog is an explicit evidence table per build: SUPPORTED dimensions only for `"9.0.1.0858"`; any other version yields every dimension UNKNOWN with `source="no recorded evidence for <version>"`; nothing defaults from an enum comprehension | unknown version yields nothing SUPPORTED; a newly added `ServiceType` has no SUPPORTED dimension | S1 |
| R-CAP-02 | the tool derives the catalog version from `manifest.backend_version`; the caller's `packet_tracer_version` must equal it; runtime fingerprint must match the manifest | mismatch refuses before effects | S1 |
| R-CAP-03 | capability resolved per operation and target: application by `f"{action.host_model}:{action.action_type.value}"`, verification by `f"{target_model}:{kind.value}"` (client model for client expectations); the catalog carries server profiles and the four legacy client operation entries (`PC-PT:dns_resolution`, `PC-PT:dns_negative_control`, `PC-PT:http_fetch`, `PC-PT:http_by_hostname`) re-keyed from the documentary baseline with provenance `documentary_baseline` | server-authorized but client-unknown kind is UNKNOWN; PC-PT action without an entry is SKIPPED `CAPABILITY_UNKNOWN` | S1 |
| R-CAP-04 | catalog consistency validated at construction: unique keys, version equality, behavioral SUPPORTED implies readiness `verify=READY`, no contradictory records | construction test fails closed | S1 |
| R-CAP-05 | a changed reader keeps its evidence only with a golden-script equality test on its vendor-call surface; golden identity preserves the surface and nothing else (not classifier equivalence, ownership, provenance or live capability) | golden tests for direct, DNS and http-scheme verification scripts | S0, S1 |
| R-CAP-06 (new) | `CLIENT_DNS_SERVER` is a new reader with no evidence; it is compiled optional (advisory) in S1, never SUPPORTED by inference from another getter, and becomes a required expectation only after M-DNS-3 is recorded | catalog entry `PC-PT:client_dns_server` UNKNOWN; optional expectation never blocks and never reports VERIFIED | S1, Q1 |
| R-CAP-07 (new) | every capability record carries `provenance` ∈ {`documentary_baseline`, `recorded_run`}; legacy DNS/HTTP records stay `documentary_baseline` forever (historical, never upgraded by golden identity); the product tool may use them under RD-8 with a response limitation; any new claim and any promotion requires `recorded_run` with build, SHA, transport, model and run id | catalog and response tests | S1, S4a |
| R-MAIL-01 | `EnableSmtpService(domain_name)`, `EnablePop3Service` with read-back of enabled flags and domain; direct expectation `MAIL_SERVER_STATE` | runtime script tests with bracketing reads | S2 |
| R-MAIL-02 | `EnsureEmailAccount(username, secret_ref)` is ENSURE_PRESENT; existence read-back uses `getEmailUser(username)` non-null and `getUser()`; never `getPassword` or `getAllEmailAcctAsStrings`; pre/post digests are existence booleans, never credentials | forbidden members absent from the script corpus; replay policy registered | S2 |
| R-MAIL-03 | `ConfigureEmailClient` per selected client sets name, user, mail id, SMTP and POP3 server and password; read-back compares every field except password | script and read-back tests | S2 |
| R-MAIL-04 | `SMTP_SEND` per sender: nonce subject and body, one dispatch under a pre-effect claim, `mailSent` with `responseType==2` and matching subject captured within the deadline; other codes are typed failures | runtime tests with captured events for success, `eSmtpUserNotFound`, timeout | S2 |
| R-MAIL-05 | `POP3_RETRIEVE` per receiver: `mailReceived` with the same nonces for that account; `getMailIpc` return ignored; `errorReceivingMail` typed; R-SEC-06 protection | runtime tests including an unrelated message that must not satisfy | S2 |
| R-MAIL-06 | `EMAIL_END_TO_END` composed: `SMTP_SEND` and `POP3_RETRIEVE` of the same `message_ref`; ring pairing over selected clients for n≥2, self-send for n=1 | compiler tests for 1, 2 and n clients | S2 |
| R-MAIL-07 | negative controls in qualification only: wrong credential and unknown recipient yield non-success codes without leakage | qualification script; redaction test | Q2 |
| R-DHCP-01 | DHCP authority per segment derived once by `derive_service_policy` before E5 compilation; delegated segments reach E5 as `delegated_dhcp_segment_ids` (no IOS pool, `DHCP_DELEGATED_TO_SERVICE`, client `SetEndpointDhcp` kept without a pool dependency) and E6 compiles `ConfigureServerDhcpPool` only for them; two authorities for one segment is `DHCP_AUTHORITY_CONFLICT`; nothing is disabled automatically | composition tests from the MCP intent: two segments with different authorities; a segment claimed twice; router segments unchanged; delegated segment keeps its client action | S3 |
| R-DHCP-02 | server bootstrap: host static (core verified), DHCP interface is the host's addressed interface, pool network equals the host segment | compiler tests | S3 |
| R-DHCP-03 | `EnableServerDhcp(interface)` and `ConfigureServerDhcpPool(...)` apply with bracketing reads on every field; exclusions include server, gateway and static clients | script and read-back tests | S3 |
| R-DHCP-04 (rev2.1) | `DHCP_LEASE` per served client: prerequisites are a fresh `isDhcpClientOn()==true` on the bound interface and an unclaimed subject; the acquisition is dispatched once by the `AcquireDhcpLease` action under a pre-effect claim, never by the verification; success is a `dhcpSucceed` for that device and port received after the dispatch sequence while the claim is held; the read-back path (fresh in-range IP/mask and any lease-time observation) yields at most UNKNOWN `acquisition_unattributed` until M-DHCP-6 is recorded with the negative controls of 5.8, after which admitting it is a reviewed change | runtime tests: event path; read-back path UNKNOWN; out-of-range address FAILED `foreign_lease` | S3 |
| R-DHCP-05 (rev2.1) | `DHCP_LEASE_ATTRIBUTED`: three distinct claims: positive lookup (a row with the client IP and MAC found in the intended pool within the bound proves that row exists), confirmed absence (requires the calibrated end condition of M-DHCP-2 reached within the bound) and completion (end condition reached); a row with the client IP and a different MAC is FAILED `foreign_lease_row`; without M-DHCP-2, absence and exhaustion are UNKNOWN `lease_table_incomplete`; the claim is `attributed_to_intended_server`, never `sole_authority` | runtime tests: found, foreign, not found without end condition, not found with end condition, exception before the bound | S3 |
| R-DHCP-06 | client-side services on DHCP-served clients depend on `DHCP_LEASE` VERIFIED; enabling the server never depends on leases | compiler DAG tests | S3 |
| R-DHCP-07 (rev2.1) | captured `dhcpFailed` is FAILED `lease_refused`; deadline with a completed negative measurement (fresh read shows no address and a completed lease scan per M-DHCP-2 shows no row for the MAC) is FAILED `lease_not_acquired` with cause unknown; deadline otherwise is UNKNOWN `acquisition_not_observed`; `pool_full_observed` requires a completed scan counting `max_users` rows; a timeout alone never proves exhaustion | runtime tests per branch | S3 |
| R-DHCP-08 | foundation kind `endpoint_dhcp_mode` for a DHCP-served client on a delegated segment: E5 `SetEndpointDhcp` result not FAILED and a fresh `isDhcpClientOn()` true on the manifest-bound interface; no address foundation before the lease; `APPLIED` alone never satisfies it; until M-DHCP-5, such clients are refused with `FOUNDATIONAL_CONFIGURATION_MISSING` | applicator tests; reader gated | S3 |
| R-SEC-01 | secrets enter as `secret_ref` and resolve through `SecretResolver` at apply time; a plan containing any secret-bearing action requires the HTTP channel selected at admission with no fallback, else `SECRET_TRANSPORT_UNAVAILABLE` before any effect; plans, hashes, journals, evidence, records and responses carry only refs | admission test with a file-only transport; hash test | S2 |
| R-SEC-02 | every external value reaches JavaScript through `json.dumps`; no f-string interpolation of data | adversarial string tests (quotes, `</script>`, newlines) | S0..S3 |
| R-SEC-03 | only allowlisted process names and members appear in generated scripts; no caller-supplied JavaScript or command text; no `getPassword`, `getAllEmailAcctAsStrings` | allowlist test over the script corpus | S2 |
| R-SEC-04 | bridge token, `/ping` exception, path containment unchanged | `tests/test_bridge_security.py` | every slice |
| R-SEC-05 | an existing account is never overwritten; `EnsureEmailAccount` records `account_preexisting=true` and `credential_claim=unverified`; a stable ref or hash never implies an unchanged credential; rotation is out of scope | runtime tests; mismatching secret yields a typed send failure without leakage | S2 |
| R-SEC-06 | before any `getMailIpc`, the recipient mailbox is listed read-only; `POP3_RETRIEVE` runs only for accounts created by this run or mailboxes containing only this run's nonces; otherwise SKIPPED `mailbox_not_owned` and only `SMTP_DELIVERED` is claimed | runtime tests with a pre-existing message | S2 |
| R-COV-01 | every selected client has a result row for every service it was selected for, including SKIPPED, DEPENDENCY_BLOCKED and recovery-read rows | aggregation test | S1 |
| R-COV-02 | where a behavioral check is sampled, the response names the sampled clients and labels unsampled clients `NOT_ATTEMPTED`, never VERIFIED | aggregation test | S1 |
| R-RET-01 (new) | the run record persists the full `configuration_result.model_dump(mode="json")` rows and identity (config plan id and semantic hash, manifest hash, environment fingerprint hash, backend version, tree SHA, run id); retained reuse requires the same deployment id, manifest hash, config semantic hash and environment fingerprint, a prior run that completed without effect uncertainty and without FAILED or `POSTCONDITION_UNSATISFIED` rows in the retained set, and fresh prerequisite verification before trust (endpoint pre-read for endpoints; E5 read-only verification of the retained expectations for other kinds); after an interrupted or uncertain run, nothing is retained and those actions re-enter the mutation scope | round-trip retention; same hash with changed environment refused; interrupted prior run not reused | S1 |
| R-RET-02 (new, D-9 containment) | the tool never trusts an E5 `dirty_state=CLEAN` when any E5 row in C carries `SESSION_FAILED` or the message "Runtime returned no mutation result."; such a run stops before E6 effects, records `e5_effect_uncertain=true`, and reports run-level `dirty_state=UNKNOWN`; the E5 fix itself is D-9 | injected E5 runtime raising after dispatch: no E6 effect, record flag set, response UNKNOWN | S1 |
| R-EVT-01 | ownership before dispatch: bag entry with its callback function object, sequence stamp and claim created and the registration outcome checked before the effect; a registration exception aborts before the effect | script order test; injected registration failure yields no dispatch | S2, S3 |
| R-EVT-02 | zero-event release: without `objectUuid` the observer entry is marked released so the callback is inert; `release_unverified` recorded; inert registrations counted and refused at 32 per session | no event ever; callback after release; old callback after a new run; duplicate callbacks; budget refusal | S2, S3 |
| R-EVT-03 | release with a known uuid calls `unregisterIpcEventByID(...)` and reports `unregistered` true/false/null; every exit path releases observers; a cleanup exception preserves the primary error | runtime tests | S2, S3 |
| R-EVT-04 | one `message_ref` per pair shared by `SMTP_SEND`, `SMTP_DELIVERED`, `POP3_RETRIEVE`; `POP3_RETRIEVE` depends on `SMTP_SEND` VERIFIED; self-send for one client | compiler tests | S2 |
| R-EVT-05 | register-then-poll kinds stay UNKNOWN until Q0 records M-ENG-1 and M-UNREG-1/2 and the service stage records delivery; without safe zero-event release the fallback set applies (`SMTP_DELIVERED`; DHCP read-back at most UNKNOWN; no POP3 claim) | catalog tests | S2, S3, Q0 |
| R-EVT-06 (new) | pre-effect claim: before an `EXECUTE_ONCE` effect the script writes `GLOBAL.__mcpE6Claims[subject] = {state: "in_progress", run_token, op_id, seq}` and refuses if any claim exists for the subject (`CLAIM_EXISTS`); after the effect returns the state becomes `completed`; if the effect call throws the state becomes `unknown`; a claim is never re-entered; the transition is atomic within one script evaluation ([INFERENCE], 3.7); this bounds duplicates, it does not manufacture exactly-once | harness scenarios: throw after effect leaves `unknown`; second script refuses; claim written before the call | S2, S3 |
| R-EVT-07 (new) | observer cleanup (callbacks, bag entries) is separate from effect ownership: an `unknown` or unresolved claim quarantines the subject for the Packet Tracer session; a new operation on a quarantined subject is refused; the receipt sequence number is admissible only under this ownership guarantee; registration or unregistration acknowledgment loss leaves the operation UNKNOWN and the subject quarantined; the qualification runner alone may reset a claim under explicit authorization | tests: late old event after a new dispatch is impossible because the new dispatch is refused; ack loss quarantines | S2, S3 |
| R-QUAL-01 | the runner creates only `__MCP_E6Q_*` devices in an observed empty workspace, one stage per authorization (Q0..Q3) with an exact target list and `--expected-head`, budgets operations, separates expected negative controls from contradictions, stops on the first contradiction, removes only its devices and proves restoration twice | use-case tests with fakes | S4a |
| R-QUAL-02 | promotion to SUPPORTED only through a committed `recorded_run` record naming build, tree SHA, transport, model, interface where relevant, run id and observation; the product composition root has no parameter for experimental capabilities | catalog and composition tests | S4a, S1 |
| R-QUAL-03 | runner and product share the same runtime, applicator and compilers; the runner may call the use cases without an MCP tool; product acceptance is a separate record through the tool | runner tests assert the shared classes | S4a |
| R-QUAL-04 | stage records and run records follow 4.8 and preserve every measurement's SHA, build, transport and model | schema tests | S4a, S1 |
| R-QUAL-05 (new) | a Q1 record attributes its measurement to the runner SHA actually executed; the S1b product HTTPS contract is qualified at its own SHA (Q1b) or the record carries a reviewer-approved "exact relevant equivalence" argument (vendor-call surface equality between the Q1 probe script and the S1b product script, same build and transport); a result is never relabeled as a later SHA's measurement | record schema requires `executed_sha`; promotion test refuses a mismatched SHA without the argument | S1b, Q1 |
| R-QUAL-06 (new) | S2 and S3 acceptance records exercise the shared coordinator through `pt_apply_enterprise_services` or its CLI adapter over the same composition, capability, foundation, runtime and persistence path; no parallel orchestration | acceptance record template names the entry point | S2, S3 |
| R-REG-01 | NTP/TFTP, E5, E8, E9, voice and CP-SCALE suites unchanged | full `pytest -q` | every slice |
| R-REG-02 | replay registry covers every new action family | registry test | S1b, S2, S3 |
| R-REG-03 | touched files satisfy the Ruff gate; no `noqa`; UP042 resolved by `StrEnum` with `__str__ = Enum.__str__` and a semantics test per enum; formatting-only commits proven by AST equality, lint commits by tests | quality gate; enum tests | every slice |

### 4.4 Contracts (DTOs, ports, modules), all proposed unless cited

Domain, `execution.py` (S0, RD-10):

```text
class DispatchFact(StrEnum):      NOT_SUBMITTED, REJECTED, ACCEPTED, ACCEPTANCE_UNKNOWN, UNSPECIFIED
class ResultFact(StrEnum):        CORRELATED, ENGINE_ERROR, MALFORMED, NOT_OBSERVED, LOST, NOT_APPLICABLE
class PostconditionFact(StrEnum): SATISFIED, UNSATISFIED, UNOBSERVED, NOT_APPLICABLE
class TransitionFact(StrEnum):    UNCHANGED, CHANGED, UNOBSERVED, NOT_APPLICABLE   # transition of the state actually read
class FootprintFact(StrEnum):     COVERED, PARTIAL, NOT_APPLICABLE                 # does the state read cover the setter's effect footprint
ExecutionJournalEntry += dispatch: DispatchFact = UNSPECIFIED, result: ResultFact = NOT_APPLICABLE,
                         residual_change: bool = False, cause: str = ""
journal_from_action_results: copies the four fields with getattr defaults; keeps the baseline disposition_from_status
                             fallback, which serves legacy rows only (a fact-bearing result always carries an explicit disposition,
                             UNKNOWN included; APPLIED and PARTIAL are not in the fallback map, so UNKNOWN survives it)
_derive_dirty_state: a FAILED entry with residual_change=True counts as a mutation (one added rule); an UNKNOWN entry
                     still yields UNKNOWN (baseline rule) and is how unknown residue is carried
```

Domain, `configuration_runtime.py` (S0):

```text
RuntimeActionMutation    += dispatch, result, postcondition: PostconditionFact = NOT_APPLICABLE,
                            transition: TransitionFact = NOT_APPLICABLE, footprint: FootprintFact = NOT_APPLICABLE,
                            attempted: bool | None = None, cause: str = ""      # observations only; residue is not an input
ActionApplicationResult  += the same seven fields as received, plus residual_change: bool = False
                            (status, disposition, failure_code and residual_change are decision outputs)
ActionApplicationResult  += received_mutation: RuntimeActionMutation | None = None      # TD-12.1, binding
                            defensive sanitized copy of the EXACT typed mutation handed to decide_mutation:
                            applied, original disposition, original failure code, original cause and all
                            seven observation fields; never a script body, credential or raw page content;
                            never mutated after classification; optional, so baseline-shaped JSON validates
                            and a legacy record without it gains no fact-bearing authority by inference
sanitized_mutation_snapshot(mutation) -> RuntimeActionMutation   # TD-12.1; bounds free text, drops nothing else
ConfigurationFailureCode += OUTCOME_UNKNOWN, RESPONSE_MALFORMED, POSTCONDITION_UNSATISFIED
MutationDecision(status, disposition, failure_code, residue: NONE | CHANGED | UNKNOWN, frontier: bool, sticky: bool, cause: str, row: str)
decide_mutation(mutation) -> MutationDecision       # the single decision of 4.5: legacy detection and validity first
mutation_execution_status(mutation) = decide_mutation(mutation).status   # projection kept for baseline callers
```

Domain, `service_runtime.py` (S0):

```text
class ObservationFact(StrEnum): OBSERVED, CONTRADICTED, INCONCLUSIVE, SUBJECT_NOT_FOUND, MALFORMED, ENGINE_ERROR,
                                NOT_OBSERVED, LOST, ACCEPTANCE_UNKNOWN, NOT_SUBMITTED, REJECTED, NOT_ATTEMPTED, UNSPECIFIED
RuntimeServiceVerification += observation: ObservationFact = UNSPECIFIED, cause: str = "",
                              claim_level: str = "", limitations: list[str]
evidence_from_service_verification(result, *, claim, backend, backend_version,
                                   environment_fingerprint, capability_snapshot_hash) -> EvidenceRecord
```

Domain, `service_plan.py` (S1b, S2, S3; untouched in S0), restored from
revision 1 with the revision 2.1 additions:

```text
ServiceType += SMTP="smtp", POP3="pop3", DHCP="dhcp"
ServiceActionType += ENABLE_SMTP, ENABLE_POP3, ENSURE_EMAIL_ACCOUNT, CONFIGURE_EMAIL_CLIENT,
                     ENABLE_SERVER_DHCP, CONFIGURE_SERVER_DHCP_POOL, SET_HTTPS_CONTENT (S1b, if separate tables), ACQUIRE_DHCP_LEASE
ServicePhase += CLIENT = 40
EnableSmtpService(domain_name: str)
EnablePop3Service()
EnsureEmailAccount(username: str, secret_ref: str)                         operation=ENSURE_PRESENT
ConfigureEmailClient(username, mail_id, display_name, smtp_server, pop3_server, secret_ref)   host_device_id = client id
SetHttpsContent(path="index.html", content, content_sha256)                 only if M-HTTPS-1 shows separate tables
EnableServerDhcp(interface: str)
ConfigureServerDhcpPool(interface, pool_name, network, prefix, netmask, gateway, dns_server, start_ip, end_ip, max_users, excluded_ranges)
AcquireDhcpLease(interface: str)                                            host_device_id = client id; operation=EXECUTE_ONCE
ServiceVerificationKind += CLIENT_DNS_SERVER, MAIL_SERVER_STATE, EMAIL_CLIENT_STATE, SMTP_SEND, SMTP_DELIVERED,
                           POP3_RETRIEVE, EMAIL_END_TO_END, DHCP_SERVER_STATE, DHCP_LEASE, DHCP_LEASE_ATTRIBUTED, DNS_LOOKUP
ServiceVerificationExpectation += required: bool = True                    (R-ENTRY-11; advisory readers False)
EmailAccountRequirement(username, secret_ref, display_name="")
EmailClientRequirement(client_device_id, username)
ServerDhcpPoolRequirement(interface="", pool_name="", start_offset=0, max_users=0)
FoundationalServiceRequirement += kind: Literal["endpoint_address", "endpoint_dhcp_mode", "l3_interface"] = "endpoint_address"
```

`ServiceRequirement` (`requirements.py:45-62`) gains `domain_name`,
`https_content`, `email_accounts`, `email_clients`, `email_pairs`,
`dhcp_pool`, `verification_mode` ∈ {`configure_only`, `effectful`}; the
existing `required`, `verification_required`, `address`, `segment_id`,
`client_device_ids`, `dns_records`, `hostname`, `http_content` keep their
meaning and `required` becomes consumed (R-ENTRY-11).

Infrastructure, `transport_outcome.py` (S0):

```text
@dataclass(frozen=True)
class BridgeDispatchOutcome:
    dispatch: DispatchFact
    result: ResultFact
    body: str | None
    disposition: str        # RequestDisposition value; file channel only; "" otherwise
    detail: str             # sanitized, bounded
# imports only domain facts; file_bridge.py and live_bridge.py import this module, never the reverse
```

HTTP classification (`live_bridge.py`; bridge handler codes at 527-579 and
500-520):

| Observation | `dispatch` | `result` |
| --- | --- | --- |
| connect refused or name resolution failure before sending | NOT_SUBMITTED | NOT_APPLICABLE |
| failure after the request was sent (read timeout, reset, disconnect), or phase undecidable | ACCEPTANCE_UNKNOWN | NOT_OBSERVED |
| POST `/queue` 400, 401, 409 (duplicate rid), 503 (result table or queue full; registration discarded) | REJECTED | NOT_APPLICABLE |
| POST `/queue` 200 "queued" | ACCEPTED (local bridge queue; the webview has not necessarily fetched it) | pending |
| GET `/result` 200 | ACCEPTED | CORRELATED (the body may still be `PT_ERROR:` → ENGINE_ERROR, or non-JSON → MALFORMED, decided by the runtime) |
| GET `/result` 204 | ACCEPTED | NOT_OBSERVED (slot `timed_out`; a later `/result` POST is refused 410, never attributed) |
| GET `/result` 404 or 410 | ACCEPTED | LOST |
| GET socket error | ACCEPTED | NOT_OBSERVED (`socket_error`) |

File classification (`file_bridge.py`):

| Phase | `dispatch` | `result` / `disposition` |
| --- | --- | --- |
| `_ensure()` or `tmp.write_bytes` OSError | NOT_SUBMITTED (discard `.tmp` best effort; the engine ignores non-`.js` names) | NOT_APPLICABLE |
| `os.replace` OSError and `req_` path absent | NOT_SUBMITTED | NOT_APPLICABLE |
| `os.replace` OSError and `req_` path present | ACCEPTED | as below |
| published | ACCEPTED | pending |
| `res_` read | ACCEPTED | CORRELATED |
| read/unlink OSError after publication, until deadline | ACCEPTED | NOT_OBSERVED + `_cancel` disposition |
| deadline | ACCEPTED | NOT_OBSERVED + `RequestDisposition` (EXECUTED_LATE, WITHDRAWN_NO_EXECUTION_OBSERVED, IN_FLIGHT_UNKNOWN); `proves_no_execution` False for all (`file_bridge.py:103-111`) |

Runtime, `enterprise_service_runtime.py` (S0):

```text
BridgeObservation(kind, payload: dict | None, message: str, outcome: BridgeDispatchOutcome)
PacketTracerEnterpriseServiceRuntime(query_inventory, send_and_wait, *, dispatch_and_wait=None, ...)
  legacy wrapper: body -> result/engine_error/malformed; None -> ACCEPTANCE_UNKNOWN + NOT_OBSERVED
  mutation row (per action, reported by the batch script):
    {id, attempted: bool, skip_reason: str, call_error: str, call_result: bool|null,
     pre_read: bool, post_read: bool, ok: bool|null, changed: bool|null, pre: str|null, post: str|null}
    ok and changed are computed in the script from the actual typed values, never from pre/post;
    pre/post are bounded diagnostic digests (booleans "0"/"1"; strings fnv1a32(value)+":"+length; null when the read failed),
    never a credential; Python derives no fact from them
  row -> facts: row validation, then the mapping of 4.5 (postcondition from ok, transition from changed,
                footprint from the family and attempted); the runtime sets observations and applied only
  verify: observation fact and cause on every RuntimeServiceVerification; failure_code never set by the runtime
```

Execution guarantee for `EXECUTE_ONCE` operations (`sendMail`, `getMailIpc`,
`dhcpRun`) `[REPO]` TD-TRANSPORT-001 (`technical-debt.md:3355-3470`): the
deployed engine can re-evaluate a request whose deletion failed until the
orphan purge; Python-side retirement narrows the window; the actual guarantee
is "at least zero, possibly more than once within that window". Containment
is the pre-effect claim of R-EVT-06 (in-progress before the effect, completed
or unknown after, never re-entered), which depends on bag persistence
(M-ENG-1), plus a controlled repeat measured in Q2/Q3 before the family
leaves UNKNOWN in the replay registry (`EvidenceBasis` rules,
`mutation_replay.py:96-116`). No enum manufactures at-most-once.

Application (S1):

```text
apply_enterprise_services(intent, *, deployment_id, packet_tracer_version, runtimes, manifest_store,
                          secret_resolver, record_store, import_preflight, environment_fingerprint,
                          transport_selection) -> ServiceStageResult
ServiceStageResult: stage ∈ {admission, configuration_apply, foundational_evidence, service_apply, release, persist, completed},
                    blocked_reason, e5_effect_scope{mutated, retained, excluded, conflicts}, e5_effect_uncertain: bool,
                    configuration_result, foundational_statuses, service_result, persisted_stage, record_path, limitations
ConfigurationApplicator.apply(..., excluded_action_ids: Collection[str] = ())   # P-E5-2; rows SKIPPED/OUT_OF_SCOPE
derive_service_foundational_statuses(service_plan, configuration_result) -> dict[str, ActionExecutionStatus]
derive_service_policy(intent, enterprise) -> ConfigurationPolicy   # dns_server from the DNS service address (S1); delegated_dhcp_segment_ids (S3)
class SecretResolver(Protocol): resolve(secret_ref) -> SecretValue     # S2
```

Catalog (S1):

```text
packet_tracer_service_capabilities(version) -> dict[str, ServiceCapabilityProfile | ClientOperationCapability]
    keys: "Server-PT:<service_type>" (profiles), "<model>:<action_type|verification_kind>" (operations)
    every record carries provenance ∈ {documentary_baseline, recorded_run} and, for recorded_run, build, sha, transport, run_id
    version != "9.0.1.0858" -> every dimension UNKNOWN, source "no recorded evidence for <version>"
```

Persistence (S1): `ServiceRunRecordStore(base_dir=data/services)` with
`begin`, `advance(stage)`, `complete`, `load`, `retained_result_for(deployment_id, config_semantic_hash, manifest_hash, environment_hash)`;
containment as `deployment_manifest_store.py:30-60, 129-135`.

### 4.5 State, effect, dependency and error rules

Effect classification of operations:

| Operation | Class | Retry | Compensation |
| --- | --- | --- | --- |
| Getters, `getOutput`, `getLastPageContent`, mailbox listing, lease table | read-only | bounded polling within the deadline; admissible after any uncertainty | none |
| `setEnable`, `setServerDomainName`, `setPageContents`, pool setters | declarative setter (`_STRUCTURED_SETTER`) | none after dispatch; postcondition and verification decide | inverse exists, not used in product use |
| `addARecordToNameServerDb`, `addUser`, `addPool` | ensure-present; repeat unmeasured | none; pre-read then act; post-read decides | inverse only in the qualification runner |
| `createClient`/`deleteClient`, `registerEvent` | owned temporary | none | release on every exit path |
| `sendMail`, `getMailIpc`, `dhcpRelease`/`dhcpRun` | `EXECUTE_ONCE`, user-state | never after ambiguity; one claim per subject per session | none |
| Qualification device creation/removal | disposable | none | remove owned devices; two empty-baseline observations |

Mutation script contract (B1, C1): for every action the batch script performs
a typed pre-read (own try/catch; `pre_read` true only when the read
completed), the setter (own try/catch; `attempted` set before the call;
`call_error` on exception; a native add return recorded as `call_result` and
never used for `ok`) and an unconditional typed post-read (own try/catch).
`ok` is computed in the script from the actual post value (`=== true` for a
flag, `=== content` for the page string, `=== true` for a membership) and
`changed` from the actual typed values (`preValue !== postValue`), both inside
the same evaluation; `ok` is null when the post-read failed and `changed` is
null when either read failed. `pre` and `post` are digests of the values for
bounded diagnostics only: equal digests, equal lengths or a true
`call_result` are never authority for UNCHANGED, SATISFIED or CLEAN, and
Python derives no fact from them. Digests and `cause` strings never contain
credentials (no S0 family carries one; the rule binds S2). The ensure-present
family reads first and skips the add when the pre-read already shows the
wanted record (`attempted=false`, `skip_reason="already_satisfied"`); the
post-read is still performed.

Observation scope and effect footprint per S0 family (R-OBS-07, C1b). A
transition is proven only within the observed scope; `footprint` says
whether that scope covers everything the setter is documented to change:

| Family | Setter | Typed read (pre and post) | Observed scope | Effect footprint | `footprint` when attempted |
| --- | --- | --- | --- | --- | --- |
| `EnableDnsService`, `EnableHttpService` | `setEnable(true)` | `!!isEnabled()` | the enabled flag | the enabled flag | COVERED |
| `EnableHttpsService` | `setHttpsEnable(true)` | `!!isHttpsEnabled()` | the HTTPS flag | the HTTPS flag | COVERED |
| `SetHttpContent` | `setPageContents(path, content)` | `String(getPage(path))` | the page at `path` | the page at `path` (`[CISCO]` per-path setter) | COVERED |
| `AddDnsRecord` | `addARecordToNameServerDb(h, a)`, skipped when the pre-read shows the record | `!!getARecordWithAddress(h, a)` | membership of the wanted `(h, a)` record | the server's A-record table (replace-or-append for an existing name unmeasured, M-DNS-4) | PARTIAL |
| `ConfigureNtpService`, `EnableTftpService` | `setEnabled(true)` | `!!isEnabled()` | the enabled flag | the enabled flag | COVERED |
| `PublishTftpFile` | none (baseline `ok=false`) | none | none | none | declined row (row 20) |

A skipped add (`attempted=false`) has footprint COVERED because no call was
made: the absence of a call, not the read, is what proves no effect. An
attempted add has footprint PARTIAL: a false/false membership observation
cannot distinguish "nothing changed" from "a different record was written",
and a false/true observation cannot show what happened to an existing record
for the same name. Widening the scope with the documented table readers is
gate M-DNS-4 (RD-11), not an S0 change.

Authoritative decision (R-OBS-02, B2a, C2). `decide_mutation` is the one
function that maps a fact tuple `(dispatch, result, postcondition,
transition, footprint, attempted, applied)` to `(status, disposition,
failure_code, residue, frontier, sticky, cause)`, evaluated in this order:

1. Legacy detection: every new fact at its default (`dispatch` UNSPECIFIED;
   `result`, `postcondition`, `transition`, `footprint` NOT_APPLICABLE;
   `attempted` None) selects row 16 and the baseline rule on `applied` and
   the given `disposition`.
2. Admission: the tuple must match exactly one listed row; the received
   values stay on the result as diagnostics.
3. Everything else is inconsistent (last row): UNKNOWN, disposition UNKNOWN,
   `OUTCOME_UNKNOWN`, residue UNKNOWN, frontier closed, sticky, cause
   `inconsistent_facts`. A received SATISFIED in an inconsistent tuple grants
   nothing, and no consumer reads it.

"Sticky" is `execution_journal.mark_transport_unknown()`, called by the
applicator exactly when any decision has `sticky=True`; "frontier" is the
decision's `frontier` output, the only input of `effect_established`;
"residue" is what the journal may claim: NONE (no unintended change within a
COVERED footprint, or no call), CHANGED (observed unintended change,
`residual_change=True`, RD-10) or UNKNOWN (carried as disposition UNKNOWN
with the cause, never as `residual_change=False`).

| # | dispatch | result | postcondition | transition | footprint | attempted | applied | status | disposition | failure_code, cause | residue | frontier | sticky |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | NOT_SUBMITTED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | None | False | FAILED | FAILED | APPLICATION_FAILED, `not_submitted` | NONE | closed | no |
| 2 | REJECTED | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | None | False | FAILED | FAILED | APPLICATION_FAILED, `rejected:<code>` | NONE | closed | no |
| 3 | ACCEPTANCE_UNKNOWN | NOT_OBSERVED | UNOBSERVED | UNOBSERVED | NOT_APPLICABLE | None | False | UNKNOWN | UNKNOWN | OUTCOME_UNKNOWN | UNKNOWN | closed | yes |
| 4 | ACCEPTED | NOT_OBSERVED or LOST | UNOBSERVED | UNOBSERVED | NOT_APPLICABLE | None | True | APPLIED | UNKNOWN | OUTCOME_UNKNOWN | UNKNOWN | closed | yes |
| 5 | ACCEPTED | ENGINE_ERROR (whole batch `PT_ERROR:`) | UNOBSERVED | UNOBSERVED | NOT_APPLICABLE | None | True | APPLIED | UNKNOWN | OUTCOME_UNKNOWN, `engine_error` | UNKNOWN | closed | yes |
| 6 | ACCEPTED | MALFORMED (non-JSON, non-object, non-list, duplicate ids) | UNOBSERVED | UNOBSERVED | NOT_APPLICABLE | None | True | APPLIED | UNKNOWN | RESPONSE_MALFORMED | UNKNOWN | closed | yes |
| 7 | ACCEPTED | CORRELATED, row missing or invalid for this id (row validation of 4.4) | UNOBSERVED | UNOBSERVED | NOT_APPLICABLE | None | True | APPLIED | UNKNOWN | RESPONSE_MALFORMED, `row_missing` or `row_invalid:<check>` | UNKNOWN | closed | yes |
| 8 | ACCEPTED | CORRELATED, `post_read` false | UNOBSERVED | UNOBSERVED | COVERED or PARTIAL | True or False | True | APPLIED | UNKNOWN | OUTCOME_UNKNOWN, `post_read_failed` (+ `call_error`) | UNKNOWN | closed | yes |
| 9 | ACCEPTED | CORRELATED, ok, `pre_read` false | SATISFIED | UNOBSERVED | COVERED or PARTIAL | True | True | APPLIED | UNKNOWN | NONE, `pre_read_failed` | UNKNOWN | open | no |
| 10 | ACCEPTED | CORRELATED, not ok, `pre_read` false | UNSATISFIED | UNOBSERVED | COVERED or PARTIAL | True | True | PARTIAL | UNKNOWN | POSTCONDITION_UNSATISFIED, `pre_read_failed` | UNKNOWN | closed | yes |
| 11 | ACCEPTED | CORRELATED, ok, unchanged | SATISFIED | UNCHANGED | COVERED | True | True | REASSERTED | REASSERTED | NONE | NONE | open | no |
| 12 | ACCEPTED | CORRELATED, ok, changed | SATISFIED | CHANGED | COVERED | True | True | APPLIED | CHANGED | NONE | NONE | open | no |
| 13 | ACCEPTED | CORRELATED, not ok, unchanged | UNSATISFIED | UNCHANGED | COVERED | True | True | PARTIAL | FAILED | POSTCONDITION_UNSATISFIED (+ `call_error`) | NONE | closed | no |
| 14 | ACCEPTED | CORRELATED, not ok, changed | UNSATISFIED | CHANGED | COVERED | True | True | PARTIAL | FAILED | POSTCONDITION_UNSATISFIED (+ `call_error`) | CHANGED (`residual_change=True`) | closed | no |
| 15 | UNSPECIFIED (Python exception in `apply_actions`; tuple built by the applicator) | NOT_APPLICABLE | UNOBSERVED | UNOBSERVED | NOT_APPLICABLE | None | False | UNKNOWN | UNKNOWN | SESSION_FAILED, `exception:<Type>` | UNKNOWN | closed | yes |
| 16 | UNSPECIFIED, every other fact at its default (legacy producer) | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | None | as given | baseline rule on `applied` and the given disposition | as given | baseline rule | NONE | `satisfies_apply_dependency(status)` | no |
| 17 | ACCEPTED | CORRELATED, skipped (`already_satisfied`), ok, unchanged | SATISFIED | UNCHANGED | COVERED (no call) | False | True | NO_OP | NO_OP | NONE, `skipped:already_satisfied` | NONE | open | no |
| 18 | ACCEPTED | CORRELATED, ok, attempted on a PARTIAL footprint | SATISFIED | CHANGED or UNCHANGED | PARTIAL | True | True | APPLIED | UNKNOWN | NONE, `footprint_partial:<footprint>` | UNKNOWN | open | no |
| 19 | ACCEPTED | CORRELATED, not ok, attempted on a PARTIAL footprint | UNSATISFIED | CHANGED or UNCHANGED | PARTIAL | True | True | PARTIAL | UNKNOWN | POSTCONDITION_UNSATISFIED, `footprint_partial:<footprint>` | UNKNOWN | closed | yes |
| 20 | ACCEPTED | CORRELATED, declined (`family_not_implemented`, no reads) | UNOBSERVED | NOT_APPLICABLE | NOT_APPLICABLE | False | True | FAILED | FAILED | APPLICATION_FAILED, `not_attempted:family_not_implemented` | NONE | closed | no |
| — | any other tuple (including `applied` disagreeing with `dispatch is ACCEPTED`) | | | | | | | UNKNOWN | UNKNOWN | OUTCOME_UNKNOWN, `inconsistent_facts` | UNKNOWN | closed | yes |

Row 7 provenance (TD-12.2, binding). Row 7 requires an **observed
ACCEPTED, CORRELATED batch envelope**. The Packet Tracer adapter holds that
envelope, so it returns the classified typed result for every requested
action, including one whose row is absent or invalid. A missing item at the
application port with no evidence of acceptance for that item or batch does
**not** prove ACCEPTED: it is a local runtime-boundary contract error and takes
the row 15 path with cause `exception:MissingRuntimeMutationResult`. An empty
result list from a runtime that made no dispatch is never proof of dispatch,
and a missing result is never read as successful cancellation or as
non-execution.

Rows 9, 10, 18 and 19 are the cases whose residue the observation cannot
establish: the journal entry is UNKNOWN with the cause, `dirty_state` is
UNKNOWN by the baseline rule, and the E6 result names each such action in
`limitations` as `residue_unknown:<id>:<cause>`. A satisfied postcondition
(rows 9 and 18) still opens the frontier and may leave the bundle VERIFIED;
an unsatisfied one (rows 10 and 19) is PARTIAL, closes the frontier and sets
the sticky flag. Row 7 (an invalid row after proven channel acceptance) and
row 15 (no dispatch fact because the runtime raised) stay distinct.

Journal rule (RD-10): `_derive_dirty_state` returns UNKNOWN for any UNKNOWN
entry; otherwise, with `failed = any FAILED` and `mutations = CHANGED or
REASSERTED entries plus FAILED entries with residual_change`, CLEAN when not
failed or no mutations, DIRTY_RECOVERABLE when every mutation has an inverse,
DIRTY_UNRECOVERABLE otherwise. The only new input is `residual_change`;
every baseline input maps as before (`[MEASURED]` on the copied pure function
for the baseline rows; table test in S0). `journal_from_action_results`
keeps its baseline fallback (`disposition_from_status`) for a result whose
disposition is UNKNOWN; because APPLIED and PARTIAL are not in that map, the
UNKNOWN disposition of rows 9, 10, 18 and 19 survives it (proven by the
decision-table test through the real builder).

Outcome-unknown rule: after any sticky row on an effectful operation the
runtime records the facts, does not re-dispatch, does not switch channels,
and continues only with read-only or owned-temporary observation.

Mutation frontier (R-OBS-08): `effect_established(result)` is the
`frontier` output of `decide_mutation` for that result (a validated
SATISFIED postcondition, or `satisfies_apply_dependency(status)` for a legacy
row); the raw `postcondition` field is never consulted. Dependents of a
non-established action are DEPENDENCY_BLOCKED
(`prerequisite_outcome_unknown:<id>` for UNOBSERVED or inconsistent facts,
`prerequisite_unsatisfied:<id>` for UNSATISFIED). Independent actions on
other hosts and other services proceed. Verification admission: an
`ACTION_APPLIED` prerequisite is satisfied only by `effect_established`;
when it is not, a read-only or owned-temporary expectation still runs as a
recovery read with the limitation `recovery_read_after_unresolved_action:<id>`,
and a user-state expectation is DEPENDENCY_BLOCKED. A recovery read may mark
its own expectation VERIFIED from a fresh read; it never changes the action
row, never clears the sticky flag and never claims execution count. The
bundle is never VERIFIED while the sticky flag is set (PARTIAL with the
action ids in `limitations`).

Verification observation facts (R-OBS-03, B3):

| Observation | Status | `fresh_evidence` | Meaning |
| --- | --- | --- | --- |
| OBSERVED | VERIFIED | True | fresh read satisfies the predicate (an unchanged value counts) |
| CONTRADICTED | FAILED | True | fresh read contradicts the predicate (fresh negative evidence) |
| INCONCLUSIVE | UNKNOWN | False | completed read cannot decide: marker present before the request, incomplete window, refused or unstarted command, no response by the deadline, `go()` false |
| SUBJECT_NOT_FOUND / MALFORMED / ENGINE_ERROR | UNOBSERVABLE | False | the read could not observe its subject |
| NOT_OBSERVED / LOST / ACCEPTANCE_UNKNOWN / NOT_SUBMITTED / REJECTED | UNKNOWN | False | transport did not deliver a correlated read |
| NOT_ATTEMPTED | as produced | False | explicit: the runtime did not attempt this kind |
| UNSPECIFIED | as produced | as produced | legacy producer stated no fact; evidence mapping falls back to the legacy adapter |

Direct contradiction: a direct expectation FAILED with fresh evidence caps
`usability_status` at PARTIAL even when behavior is VERIFIED
(`direct_state_contradiction`); PARTIAL or UNOBSERVABLE direct state keeps
the existing rule. Bundle: FAILED with APPLICATION_FAILED when any action is
FAILED; FAILED with POSTCONDITION_UNSATISFIED when any critical action is
PARTIAL with that code; never VERIFIED under the sticky flag.

Dependency graph (compiler output, one Server-PT `S`, clients `C1..Cn`):

```text
phase ENABLE (host S):   EnableDnsService, EnableHttpService, EnableHttpsService, EnableSmtpService, EnablePop3Service, EnableServerDhcp(if)
phase CONTENT (host S):  AddDnsRecord*, SetHttpContent, SetHttpsContent? (S1b), EnsureEmailAccount*, ConfigureServerDhcpPool(if)
phase CLIENT (host Ci):  ConfigureEmailClient(Ci), AcquireDhcpLease(Ci)   [depends on ConfigureServerDhcpPool and the Ci endpoint_dhcp_mode foundation]

verification order:
  DIRECT_SERVICE_STATE(S, each service)      read-only, after its terminal action
  DHCP_SERVER_STATE(S)                       read-only
  DHCP_LEASE(Ci)                             observation of the AcquireDhcpLease(Ci) action; VERIFIED prerequisite of every other Ci expectation when Ci is DHCP-served
  DHCP_LEASE_ATTRIBUTED(Ci)                  read-only, depends_on DHCP_LEASE(Ci)
  CLIENT_DNS_SERVER(Ci) [optional], DNS_RESOLUTION(Ci), DNS_NEGATIVE_CONTROL(Ci)
  HTTP_FETCH(Ci), HTTPS_FETCH(Ci), HTTP_BY_HOSTNAME(Ci) [depends DNS_RESOLUTION + HTTP_FETCH]
  EMAIL_CLIENT_STATE(Ci)                     read-only
  SMTP_SEND(Ci -> pair receiver)             user-state; SMTP_DELIVERED(S) read-only; POP3_RETRIEVE(receiver) user-state, depends_on SMTP_SEND
  EMAIL_END_TO_END(pair)                     composed, depends_on SMTP_SEND + POP3_RETRIEVE with the same message_ref
```

E5 effect scope (RD-1, R-ENTRY-09, R-NET-01):

- Closure C: every `configuration_action_id` in
  `service_plan.foundational_requirements`, closed over `depends_on` and
  `apply_dependencies`. At the baseline an endpoint action depends only on
  its access-port action (`configuration_compiler.py:1162-1171`), a DHCP
  endpoint on its pool and access port (309-323), an access port on its VLAN.
  Under R-NET-01 (one segment) C contains exactly the endpoint, access-port
  and VLAN actions of the selected devices; nothing else is rendered.
- First application: `mutation_action_ids=C`, `excluded_action_ids=plan−C`
  (P-E5-2); excluded rows are SKIPPED with `OUT_OF_SCOPE`; invariant: no
  mutated action depends on an excluded one. Re-runs: R-RET-01.
- Drift: endpoints in C are pre-read with `endpoint_address_observer.py`; a
  non-empty address different from the plan refuses with
  `EXISTING_CONFIGURATION_CONFLICT` and zero effects. Access-port and VLAN
  kinds have no typed pre-read and are applied as registered declarative
  setters; this is disclosed as explicit partial-application semantics in
  `e5_effect_scope`.
- Foundation evidence: only verification rows of C feed
  `derive_service_foundational_statuses`; the core predicate is the one at
  `foundational_evidence.py:96-153`, refactored to take the E6 plan's
  `source_configuration_id` and hash; a satisfied IPv4/netmask core satisfies
  only its own `configuration_action_id`.
- E5 effect uncertainty (R-RET-02): any E5 row in C with `SESSION_FAILED` or
  the missing-row message stops the run before E6 effects and marks
  `e5_effect_uncertain`.

Client DNS (R-NET-02): `derive_service_policy` sets
`ConfigurationPolicy.dns_server` from the requested DNS service's explicit
`address`; E5 places it on every static endpoint; the runtime call
`configurePcIp(..., dnsServer, ...)` carries it (`_endpoint_call`,
`enterprise_configuration_runtime.py:841-858`). For DHCP-served clients the
pool's DNS option carries it (S3). `CLIENT_DNS_SERVER` observes it and is
optional until M-DNS-3.

DHCP ownership (RD-2, R-DHCP-01, P-E5-1 revised): `derive_service_policy`
also returns `delegated_dhcp_segment_ids`; `_dhcp_actions` emits no IOS pool
for a delegated segment and records `DHCP_DELEGATED_TO_SERVICE`; the
`pending_dhcp` loop emits `SetEndpointDhcp` for delegated segments with
`depends_on=[access_dependency]` only (today it skips them, 298-303); router
segments are unchanged; E6 compiles `ConfigureServerDhcpPool` only for
delegated segments and refuses if the E5 plan still carries a
`ConfigureDhcpPool` for that segment. Observed serving authority is a
separate claim (`DHCP_LEASE_ATTRIBUTED`); runtime uniqueness is never claimed.

Error and closure vocabulary:

| Fact | Status / code / fields |
| --- | --- |
| Not attempted (admission refused) | result FAILED at admission with the admission code; `preflight_errors`; zero mutations; record per 4.8 |
| Refused by capability | SKIPPED + `CAPABILITY_UNKNOWN`/`CAPABILITY_UNSUPPORTED` |
| Excluded optional service | SKIPPED + `SERVICE_INELIGIBLE` with the unknown operations named |
| Out of E5 scope | SKIPPED + `OUT_OF_SCOPE` |
| Not submitted / rejected / declined family | FAILED + `APPLICATION_FAILED` (rows 1, 2, 20) |
| Accepted, result not observed, lost, engine error, malformed | APPLIED + disposition UNKNOWN + `OUTCOME_UNKNOWN`/`RESPONSE_MALFORMED` (rows 4 to 8); sticky |
| Acceptance unknown | UNKNOWN + `OUTCOME_UNKNOWN` (row 3); sticky |
| Applied and postcondition satisfied | APPLIED (CHANGED), REASSERTED or NO_OP (rows 11, 12, 17); APPLIED with disposition UNKNOWN and the `residue_unknown` limitation when the residue is unobserved (rows 9, 18) |
| Postcondition unsatisfied | PARTIAL + `POSTCONDITION_UNSATISFIED`; residual flag per rows 13/14; residue UNKNOWN with the sticky flag per rows 10/19 |
| Runtime exception | UNKNOWN + `SESSION_FAILED` (row 15); sticky |
| Direct state matched | VERIFIED, fresh, OBSERVED |
| Direct subject not found / malformed / engine error | UNOBSERVABLE + `DIRECT_READBACK_UNOBSERVABLE` |
| Inconclusive or undelivered verification read | UNKNOWN + `OUTCOME_UNKNOWN` with the observation fact |
| Contradiction observed | FAILED + `VERIFICATION_FAILED`/`BEHAVIORAL_VERIFICATION_FAILED`, fresh |
| Capability limitation | UNOBSERVABLE + `OBSERVABILITY_LIMITATION` |

### 4.6 Asynchrony and correlation `[DECISION]` RD-4 (candidate)

Polling remains primary wherever a getter exists. For `SMTP_SEND`,
`POP3_RETRIEVE` and `DHCP_LEASE` no getter carries the completion code, so
register-then-poll is the candidate with this lifecycle:

1. Ownership before dispatch (R-EVT-01, R-EVT-06). Script A checks
   `GLOBAL.__mcpE6Claims[subject]`; any existing claim refuses
   (`CLAIM_EXISTS`). It creates the observer entry
   `GLOBAL.__mcpE6Runs[run_token][op_id] = {events: [], registered: false, uuid: "", released: false, seq_at_dispatch: 0, callback: <function>}`,
   calls `process.registerEvent(event, null, entry.callback)` inside
   try/catch (failure reports `{registered: false}` and stops), then writes
   the claim `{state: "in_progress", run_token, op_id, seq}`, records
   `seq_at_dispatch = GLOBAL.__mcpE6Seq`, calls the effect inside try/catch,
   and sets the claim state to `completed` (returned) or `unknown` (threw).
   The callback appends `{eventName, uuid, seq: ++GLOBAL.__mcpE6Seq, args}`
   only while `entry.released` is false, sets `entry.uuid`, and stops at 64
   events per entry (2 KB per serialized event). Report
   `{registered, claimed, dispatched, claim_state}`. If this script's result
   is not observed, the operation is UNKNOWN and the claim stays.
2. Script B (read-only, polled): reports the entry's events with
   `seq > seq_at_dispatch` and a fresh observable where one exists.
3. Script C (observer release): if `entry.uuid` is known, calls
   `_ScriptModule.unregisterIpcEventByID(className, uuid, event, null, entry.callback)`
   and reports `unregistered` true/false; otherwise sets `entry.released = true`
   (inert callback), increments `GLOBAL.__mcpE6Inert`, reports
   `unregistered: null` (`release_unverified`). Deletes the observer entry.
   It never deletes a claim: a `completed` claim whose operation resolved is
   cleared by Script C; an `in_progress` or `unknown` claim, or a completed
   claim whose result was not observed, stays as quarantine for the session
   (R-EVT-07). When `GLOBAL.__mcpE6Inert >= 32` Script A refuses
   (`EVENT_SUBSCRIPTION_BUDGET_EXHAUSTED`).

Correlation rules: a DHCP event matches only by device and port, received
after the dispatch sequence, while the subject's claim belongs to this
operation; the receipt sequence dates the callback, not the event's origin,
and is admissible only because a quarantined subject never receives a new
dispatch. Mail correlation is by `message_ref` nonce in subject and body
(R-EVT-04). A run token in the bag labels storage, never provenance.

Deadlines (proposed defaults): SMTP 15 s, POP3 15 s, DHCP 30 s. Deadline
expiry is UNKNOWN unless a typed error event was captured or a completed
negative measurement exists (R-DHCP-07).

Gates: M-ENG-1, M-UNREG-1, M-UNREG-2, M-MAIL-2, M-POP3-1, M-DHCP-3, plus the
single-evaluation atomicity inference of 3.7. Until Q0 records them,
event-driven kinds compile and execute only in the qualification runner
(R-EVT-05). If M-UNREG-2 shows no safe zero-event release, the production
design is the fallback set: DHCP through R-DHCP-04's read-back path at most
UNKNOWN until M-DHCP-6, mail through `SMTP_DELIVERED`, and no POP3 claim.
Every fallback keeps the claim contract of R-EVT-06.

### 4.7 Security and secrets

- Transport (RD-5, R-SEC-01): a plan containing a secret-bearing action
  (`EnsureEmailAccount`, `ConfigureEmailClient`, `SMTP_SEND`) is admitted only
  when the HTTP channel is selected at A5; the tool passes `channel="http"`
  explicitly and never falls back. On the HTTP channel the script is a POST
  body over loopback, an item in the bridge's in-memory `Queue`
  (`live_bridge.py:238`), then webview and engine memory. The file channel
  writes the whole script to `req_<name>.js.tmp` and `req_<name>.js`
  (`file_bridge.py:175-185`) with possible residue after failure; it stays
  eligible for operations without secrets.
- Bounded claim: this product controls only the MCP process, the loopback
  request and the generated script. Packet Tracer stores account credentials
  in its own model; a local secret file under `%LOCALAPPDATA%` is storage by
  definition (`bridge_token.py:40-48` precedent); "memory only" is claimed
  for the product's own handling and nothing else.
- Disclosure surfaces not changed here: the webview log preview
  (`interface.js:529-530`, 120 characters) never reaches the script body
  because the HTTP wrapper prefix is 347 characters `[MEASURED]`;
  `PT_ERROR:` text and `call_error` strings are redacted and bounded before
  they leave infrastructure.
- Redaction: `redact(value, secrets)` covers the raw value, `json.dumps`
  escaped form and URL-encoded form; digests of pre/post state never include
  a credential (existence booleans for accounts).
- Account policy (R-SEC-05), verification modes (`configure_only`,
  `effectful`, explicit `email_pairs`, self-send for one client), POP3
  protection (R-SEC-06), forbidden members (R-SEC-03), bridge authentication,
  `/ping` exception, `%LOCALAPPDATA%`, path containment via
  `safe_name_component`/`resolve_within` for `run_id` and `deployment_id`.

### 4.8 Persistence

`ServiceRunRecordStore` (S1) writes one JSON per run under
`data/services/<deployment_id>/<run_id>.json` (gitignored) and unbound
admission records under `data/services/_admission/<run_id>.json`:

```text
schema_version: 1
run_id, run_label, created_at, completed_at
source_tree: {sha, dirty: bool}
packet_tracer_version, transport, channel_fixed_at
deployment_id, manifest_hash, physical_topology_hash, configuration_plan_id, configuration_semantic_hash, service_semantic_hash
environment_fingerprint_hash, capability_snapshot: {version, catalog_hash, provenance_by_key}
stages: [{stage, started_at, ended_at, outcome, blocked_reason}]      # write-ahead: rewritten at every transition
persisted_stage                                                        # last durable stage, echoed in the response
admission: {refusals[], reads[]}
e5_effect_scope: {mutated[], retained[], excluded[], conflicts[]}
e5_effect_uncertain: bool
configuration_result: full model_dump(mode="json")                     # rows needed for retained results (R-RET-01)
foundational_statuses: {...}
service_result: full model_dump(mode="json")                           # facts, dispositions, observation facts, evidence records
releases: [{resource, outcome}]
nonces: {message_ref: nonce}                                           # not secrets
limitations: []
persist_error: str | null
```

Lifecycle (R-ENTRY-06): A1 and A2 refusals return without a record (no valid
identity). A3 to A5 refusals write an unbound admission record when the store
is writable, else the response says `record: none`. A6 creates the bound
record before any effect; if it cannot, the run is refused. Every stage
rewrites the record atomically (tmp + replace). If a rewrite fails after the
first effect, no further user-state mutation is dispatched; bounded read-only
observation and owned-resource cleanup continue; the primary error is
preserved; the response reports `persisted_stage` and `persist_error`.
Durable claims are transcribed into `docs/qa/server-services-qualification.md`
per stage with run id, executed SHA, build and transport. Historical evidence
files are never rewritten.

### 4.9 Ruff and enum presentation debt (measured, revision 2.1)

`[MEASURED]` with the checkout `.venv`, Ruff 0.16.7, at the baseline:

| File | Lint | Format |
| --- | --- | --- |
| `execution.py` | 14 (4 UP042, 1 F401) | would be reformatted |
| `configuration_runtime.py` | 21 (5 UP042) | would be reformatted |
| `live_bridge.py` | 12 | would be reformatted |
| `file_bridge.py` | 6 (1 UP042) | already formatted |
| `service_runtime.py` | 5 | would be reformatted |
| `enterprise_service_runtime.py` | 5 | would be reformatted |
| `apply_services.py` | 7 | would be reformatted |
| `service_plan.py` | 32 (4 UP042) | would be reformatted; untouched by S0 |
| `service_capabilities.py` | 2 | would be reformatted; untouched by S0 |
| `evidence.py` | 19 (7 UP042) | would be reformatted; untouched by S0 |
| `tool_registry.py` (5,132 lines) | 23 | would be reformatted; S1 |
| `server.py` | 1 (I001) | would be reformatted; untouched |
| `tests/test_service_runtime.py` | 12 | formatted |
| `tests/test_service_application.py` | 16 | formatted |

Enum semantics `[MEASURED]` on CPython 3.12.10 (identical by the documented
3.11 change to `Enum.__format__`; the CI matrix on 3.11 and 3.13 is the
verification):

| Form | `str()` / `format()` / f-string | `json.dumps` | `== "dns"` | pydantic `model_dump(mode="json")` and round-trip |
| --- | --- | --- | --- | --- |
| `class A(str, Enum)` | `A.DNS` | `"dns"` | True | `"dns"`, identity preserved |
| `class B(StrEnum)` | `dns` | `"dns"` | True | `"dns"`, identity preserved |
| `class C(StrEnum)` with `__str__ = Enum.__str__` | `C.DNS` | `"dns"` | True | `"dns"`, identity preserved |

Decision (R-REG-03): `StrEnum` changes textual presentation, not JSON of
string-valued members; form C preserves the presentation the project
established for `ImportIsolationState`. No `noqa`. Touched files are
brought to a clean gate in the slice that touches them, in two commits per
file set: a formatting-only commit proven by AST equality (`ast.dump` before
and after) and the unchanged suite, then a lint commit (docstrings, imports)
proven by the suite with no AST-equality claim. `tool_registry.py` is owned
in S1 the same way. JSON of `ActionApplicationResult`,
`ExecutionJournalEntry` and `ApplicationExecutionJournal` gains keys; that is
recorded, and a baseline-shaped fixture without the new keys must still
validate (shape of `cp_scale_stage_evidence.py:78` output).

### 4.10 Illustrative data (hypothetical, no execution evidence)

Sample intent (labels only; no real user data), R-NET-01 shape:

```json
{
  "name": "SAMPLE-LAB",
  "sites": [{
    "name": "HQ", "type": "hq",
    "endpoints": [
      {"role": "user_pc", "count": 2, "addressing_preference": "static"},
      {"role": "server", "count": 1, "addressing_preference": "static", "metadata": {"requirement.ipv4": "198.18.160.10"}}
    ],
    "services": [
      {"name": "lab-dns", "service_type": "dns", "host_device_id": "hq/server/1", "address": "198.18.160.10",
       "client_device_ids": ["hq/user_pc/1", "hq/user_pc/2"],
       "dns_records": [{"hostname": "www.lab.example", "address": "198.18.160.10"}]},
      {"name": "lab-web", "service_type": "http", "host_device_id": "hq/server/1", "hostname": "www.lab.example",
       "http_content": "SAMPLE_WEB_PAGE"},
      {"name": "lab-web-tls", "service_type": "https", "host_device_id": "hq/server/1", "required": false}
    ]
  }]
}
```

With `"required": false` the HTTPS service is excluded before E5 when its
client operation is capability-unknown (R-ENTRY-11); without it the run is
refused before effects. Hypothetical response excerpt (shape only):

```json
{
  "run_id": "2026-09-17T10-00-00Z-3f9c",
  "stage": "completed",
  "persisted_stage": "completed",
  "status": "verified",
  "transport": "http",
  "provenance": {"Server-PT:dns": "documentary_baseline", "PC-PT:http_fetch": "documentary_baseline"},
  "e5_effect_scope": {"mutated": ["endpoint-static/hq/server/1/…", "endpoint-static/hq/user_pc/1/…", "access-port/…", "vlan/…"], "retained": [], "excluded": ["…"], "conflicts": []},
  "e5_effect_uncertain": false,
  "services": [
    {"service_id": "service/hq/lab-dns", "usability_status": "verified", "direct_readback_status": "verified"},
    {"service_id": "service/hq/lab-web", "usability_status": "verified"},
    {"service_id": "service/hq/lab-web-tls", "usability_status": "skipped", "limitations": ["service_ineligible:PC-PT:https_fetch=unknown"]}
  ],
  "clients": [
    {"client_device_id": "hq/user_pc/1", "deployed_name": "HQ-PC-01",
     "results": {"dns": {"status": "verified", "claim_level": "behavioral", "observation": "observed"},
                 "http": {"status": "verified", "claim_level": "behavioral", "observation": "observed"},
                 "client_dns_server": {"status": "unknown", "observation": "not_attempted", "required": false}}}
  ],
  "actions": [{"action_id": "…/enable-dns", "status": "applied", "disposition": "changed", "dispatch": "accepted", "result": "correlated",
               "postcondition": "satisfied", "transition": "changed", "footprint": "covered", "attempted": true, "residual_change": false},
              {"action_id": "…/add-record", "status": "applied", "disposition": "unknown", "dispatch": "accepted", "result": "correlated",
               "postcondition": "satisfied", "transition": "changed", "footprint": "partial", "attempted": true, "residual_change": false,
               "cause": "footprint_partial:dns_a_record_table"}],
  "dirty_state": "unknown",
  "limitations": ["provenance:documentary_baseline", "residue_unknown:…/add-record:footprint_partial:dns_a_record_table"],
  "record_path": "data/services/<deployment_id>/<run_id>.json"
}
```

The DNS record makes `dirty_state` UNKNOWN on a first run although every
postcondition is satisfied and the services are verified (RD-11); a re-run
whose pre-read finds the record is NO_OP and CLEAN.

---
## 5. Incremental implementation slices

Ordering rationale: truthful observation first (S0); one usable product path
for the already-evidenced services on a bounded topology (S1); the
qualification runner and the engine facts that decide the asynchronous
design (S4a, Q0) before email and DHCP runtimes are finalized; HTTPS
ownership (Q1), its contract (S1b) and its re-qualification (Q1b); email
(S2, Q2); DHCP (S3, Q3); routed single-gateway clients (S1c); conditional
`nslookup` (S5); documentation (S6). Q stages are separately authorized LIVE
runs; every other slice is offline.

Every slice: risk L unless stated; delivery READY_FOR_REVIEW; validation
from `AGENTS.md` (replace `cisco/main` with the implementer's verified base):

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test,docs,quality]"
git rev-parse --verify "<base>/main^{commit}"
.\.venv\Scripts\python.exe scripts\quality_gate.py --base <base>/main
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m mkdocs build --site-dir _site
git diff --check
# after commit:
.\.venv\Scripts\python.exe scripts\quality_gate.py --base <base>/main --delivery-commit HEAD
```

### S0 — Observation integrity (offline)

| Field | Content |
| --- | --- |
| Purpose | Make transport, runtime, applicator, journal, evidence and JSON tell the same truth, with the generated scripts proven against stubs, before any new service reuses them |
| Depends on | independent approval of the section 7.1 contract |
| Requirements | R-OBS-01, 02, 03, 06, 07, 08; R-EVD-01; R-TEST-01; R-ENTRY-08; R-HTTP-01, R-DNS-01 (bracketing reads); R-HTTPS-02, 03; R-CAP-05 (golden readers); R-REG-01, 03; R-SEC-02 |
| Paths | `execution.py`, `configuration_runtime.py`, `service_runtime.py`, `transport_outcome.py` (new), `live_bridge.py`, `file_bridge.py`, `enterprise_service_runtime.py`, `apply_services.py`, new test modules, the authorized edits of 6.5 in `tests/test_service_runtime.py` |
| Exclusions | `service_plan.py`, `evidence.py`, `mutation_replay.py`, `service_capabilities.py`, `tool_registry.py`, `pyproject.toml`, E5 compiler/applicator/runtime, security runtime, any MCP tool |
| Tests | section 7.1 RED list; decision-table test over the full fact product with safety predicates; legacy-identity tests; journal table test; differential characterization tables; real-socket tests; Node harness scenarios with expectations from the stub state; golden reader scripts; round-trip and agreement tests; JSON fixture compatibility |
| Acceptance gate | quality gate clean on touched files; full suite green; harness executed in CI (fails, not skips, under `GITHUB_ACTIONS`); self-review checklist 6.3; test inventory recorded in the brief |
| Rollback | revert commits |

### S1 — Product entry point for DNS and HTTP on the bounded topology (offline, plus a separately authorized LIVE acceptance)

| Field | Content |
| --- | --- |
| Depends on | S0 |
| Requirements | R-ENTRY-01..07, 09, 10, 11; R-NET-01, 02; R-CAP-01..07; R-HTTP-*; R-DNS-01..03; R-COV-01/02; R-RET-01, 02; R-QUAL-02 (product side), R-QUAL-04; R-REG-* |
| Paths | `apply_enterprise_services.py` (new), `service_tools.py` (new), `tool_registry.py` (one import, one call; debt owned per 4.9), `compose_enterprise_reference.py` (+services, `derive_service_policy`), `configuration.py` (`DNS_SERVER_ADDRESS_REQUIRED`), `foundational_evidence.py` (shared core predicate + service derivation), `apply_configuration.py` (P-E5-2), `service_capabilities.py` (rewrite with provenance), `service_run_record_store.py` (new), `service_compiler.py` (client keys, required/optional, optional `CLIENT_DNS_SERVER`), `docs/tools.md`, tests |
| Integration tests | from the real MCP input through composition, E5 applicator and E6 applicator over injected runtimes and stores that record call arguments: initially unset DNS policy produces the E5 action and runtime call with the DNS address; exactly C reaches the E5 runtime; excluded rows `OUT_OF_SCOPE`; endpoint conflict refuses with zero effects; routed client refused; required ineligible service refuses before E5, optional one excluded; foundation derivation with and without sufficient field-level evidence; admission ordering and reads; record lifecycle (rejection before A6, persistence failure before and after the first effect, interrupted run, retention round-trip, same hash with changed environment, no mutation after persistence loss); E5 runtime raising after dispatch stops before E6 with `e5_effect_uncertain`; redaction; version mismatch |
| LIVE acceptance (separate authorization) | one operator-owned sample topology of the R-NET-01 shape deployed by `pt_live_deploy` (never the university topology), DNS + HTTP for two PCs, through the tool; per-client VERIFIED rows; record persisted with executed SHA, build, transport; no cleanup; stop on the first contradiction. Until this record exists, product usability is "offline verified" and every DNS/HTTP capability used is disclosed as `documentary_baseline` |
| Rollback | revert; records are local |

### S4a — Qualification runner and Q0/Q1 probes (offline)

| Field | Content |
| --- | --- |
| Depends on | S0, S1 |
| Requirements | R-QUAL-01, 03, 04, 05 (record fields); R-EVT-05 (gating) |
| Paths | `qualify_server_services.py` (stage definitions Q0..Q3 with discriminating experiments), `adapters/cli/service_qualification.py` (exact target list, `--expected-head`, stage id; pattern `cp_scale_live.py:284-363`, `admission.py:547-592`), `docs/qa/server-services-qualification.md` (template), tests |
| Runner contract | prerequisites: empty workspace observed, `ImportIsolationPreflight` isolated, transport fixed and recorded, build exact. Fixture: `__MCP_E6Q_SRV`, `__MCP_E6Q_PC1`, `__MCP_E6Q_PC2`, `__MCP_E6Q_SW`. Experimental capabilities are a runner parameter only. Claim reset only under explicit authorization. Cleanup: remove owned devices, two consecutive empty-workspace observations, `dirty_state` reported. Every record carries `executed_sha` |
| Tests | authorization refusal, budget stop, expected-negative versus contradiction classification, cleanup on failure, restoration proof, record schema |

### Q0 — Engine facts (LIVE, separately authorized)

M-ENG-1 (bag persistence across two calls on each channel), M-UNREG-1,
M-UNREG-2, the atomicity inference of 3.7 (two queued scripts writing the
same claim; any interleaving observed is a counterexample), M-HTTP-1
(optional). Budget: 20 bridge operations, 5 minutes, one temporary PC. Stop
rules: foreign device observed, outcome-unknown effect, budget. Decides
whether register-then-poll and the claim lifecycle can be implemented in
S2/S3 or the fallback set applies.

### Q1 — HTTPS ownership and readers (LIVE, separately authorized)

M-HTTPS-1, M-HTTPS-2, M-DNS-3 (`getServerIp` read), M-DNS-1/2 if budget
allows. Expected negative controls: fetch fails with HTTPS disabled; fetch in
http mode fails with HTTP disabled. Contradiction: a fetch succeeds in https
mode with HTTPS disabled. Budget: 30 operations, 10 minutes. Decides the
S1b contract; attributed to the runner SHA executed (R-QUAL-05).

### S1b — HTTPS content contract (offline, after Q1) and Q1b (LIVE)

Implements `SetHttpsContent` or `shared_content` per the Q1 record: compiler,
runtime script with bracketing reads, replay registry entry, catalog readiness
from a record. Promotion requires Q1b at the S1b SHA or the reviewer-approved
equivalence argument of R-QUAL-05. Requirements: R-HTTPS-01, R-HTTPS-04,
R-QUAL-05, R-REG-02.

### S2 — Email (offline)

| Field | Content |
| --- | --- |
| Depends on | S0, S1, Q0 record; independent of S3 |
| Requirements | R-MAIL-01..07, R-SEC-01, 03, 05, 06, R-OBS-04, 05, R-EVT-01..07, R-COV-01/02, R-REG-02 |
| Paths | `service_plan.py`, `requirements.py`, `service_compiler.py`, `enterprise_service_runtime.py` (claims, observers, mail operations), `mutation_replay.py` (`sendMail`/`getMailIpc` UNKNOWN/UNMEASURED), `service_capabilities.py` (SMTP/POP3 UNKNOWN), secret port and adapter, tests |
| Tests | compiler: ids; 1/2/n pairing incl. self-send; missing account; refs only in the hash. Runtime (harness where practical): claim written before the effect; throw after effect leaves `unknown` and quarantines; second operation on a claimed subject refused; allowlist; `mailSent` code 2 with matching nonce is the only success; unrelated message never satisfies; pre-existing mailbox skips retrieval; timeout UNKNOWN; `errorReceivingMail(9)` typed; no event ever; ack lost; callback after release; old callback after a new run; duplicate callbacks; cross-run interference; budget refusal; cleanup exception preserves the primary error. Admission: file-only transport refuses secret-bearing plans. Applicator: UNKNOWN capability keeps every email action SKIPPED |
| Acceptance gate | gates green; profiles remain UNKNOWN (explicit test) |

### Q2 — Mail (LIVE, separately authorized)

M-MAIL-1/2/3, M-POP3-1/2, controlled repeat of `sendMail` under a claim.
Expected negatives: wrong credential and unknown recipient yield non-success
codes without leakage. Budget: 60 operations, 15 minutes, random per-run
secrets in memory. Acceptance through the shared coordinator (R-QUAL-06).

### S3 — Server-PT DHCP with the E5 authority rule (offline)

| Field | Content |
| --- | --- |
| Depends on | S0, S1, Q0 record, RD-2 |
| Requirements | R-DHCP-01..08, R-OBS-05, R-EVT-01..03, 06, 07, R-REG-02 |
| Paths | `configuration.py` (policy field, issue codes), `configuration_compiler.py` (P-E5-1 revised), `compose_enterprise_reference.py` (`derive_service_policy` delegation), `service_plan.py`, `service_compiler.py`, `apply_services.py` (`endpoint_dhcp_mode` foundation), `enterprise_service_runtime.py` (DHCP operations, claims, `isDhcpClientOn` reader, bounded lease lookup), `mutation_replay.py`, `service_capabilities.py` (DHCP UNKNOWN), tests |
| Tests | composition from the MCP intent: two segments with different authorities; conflict; relay refusal; router segments unchanged; delegated segment keeps `SetEndpointDhcp`. Runtime: event path under a held claim; read-back path UNKNOWN; out-of-range FAILED; positive lookup found; foreign MAC; not found without end condition (UNKNOWN); not found with end condition (FAILED); exception before the bound (UNKNOWN); `dhcpFailed`; completed versus incomplete negative measurement; claim and quarantine; one attempt per session. Applicator: DHCP-mode foundation gate; APPLIED alone never satisfies |
| Acceptance gate | gates green; DHCP profile UNKNOWN |

### Q3 — DHCP (LIVE, separately authorized)

M-DHCP-1..6 with the discriminating experiments: `getLeaseAt` end-of-table
behavior on an empty pool, a one-row pool and a full pool (M-DHCP-2);
`getLeaseTimeStr` read twice with no acquisition over the deadline interval,
then across an automatic renewal, then across a requested renewal
(M-DHCP-6); controlled repeat of `dhcpRun` under a claim. Expected negatives:
second client on a one-user pool → `lease_not_acquired` only if the end
condition is calibrated, else UNKNOWN. Contradiction: an in-range address not
in the fixture's lease table. Budget: 60 operations, 20 minutes. Acceptance
through the shared coordinator (R-QUAL-06).

### S1c — Routed single-gateway clients (offline, after S1)

Extends R-NET-01 to two segments on one gateway device: closure C includes
the L3 or SVI actions of both segments (existing E6 cross-segment foundation
rule), still no routing protocol. Requires its own LIVE acceptance record.

### S5 — `nslookup`-based `DNS_LOOKUP` (conditional on M-DNS-1/2)

Adds a typed `nslookup` reader using the `command_dispatch.py` fresh window
and pager guard with positive and negative controls and, if a cache control
exists, a fresh-query claim. Until then the ping reader remains the supported
DNS behavioral method.

### S6 — Documentation and debt closure

Update `docs/architecture/enterprise-services.md`, `docs/tools.md`,
`docs/architecture/technical-debt.md` (D-1, D-8, D-9, D-10 entries), and
`docs/qa/server-services-qualification.md` per recorded stage. Pure
documentation.

### 5.8 Staged qualification matrix

| Stage | Prerequisite slices | Measurements | Expected negative controls | Contradiction (stop) | Budget | Record |
| --- | --- | --- | --- | --- | --- | --- |
| Q0 | S0, S1, S4a | M-ENG-1, M-UNREG-1, M-UNREG-2, atomicity counterexample search, M-HTTP-1 | none | foreign device; outcome-unknown effect | 20 ops, 5 min | `q0-<run>.json` + QA row with executed SHA |
| Q1 | S4a | M-HTTPS-1, M-HTTPS-2, M-DNS-3, M-DNS-1/2 if budget allows | fetch fails with HTTPS disabled | fetch succeeds in https mode with HTTPS disabled | 30 ops, 10 min | `q1-<run>.json` |
| Q1b | S1b | product HTTPS contract at the S1b SHA | as Q1 | as Q1 | 30 ops, 10 min | `q1b-<run>.json` |
| Q2 | S2 | M-MAIL-1/2/3, M-POP3-1/2, controlled repeat | wrong credential, unknown recipient | success code with wrong credential | 60 ops, 15 min | `q2-<run>.json` |
| Q3 | S3 | M-DHCP-1..6 with the discriminating experiments above, controlled repeat | second client on a one-user pool | in-range address not in the fixture's lease table | 60 ops, 20 min | `q3-<run>.json` |
| S1 LIVE acceptance | S1 | product path, DNS + HTTP, two PCs, R-NET-01 shape | none | any FAILED row | 60 ops, 20 min | `acceptance-s1-<run>.json` |
| S1c, S2, S3 acceptance | each slice | product path through the tool or CLI adapter | per stage | any FAILED row | per stage | `acceptance-<slice>-<run>.json` |

Every record preserves executed SHA, build, transport, model and interface;
the integrated delivery is validated by its own acceptance record and never
inferred from Q stages.

---

## 6. Verification and traceability

### 6.1 Levels

| Level | Applies to | Oracle source |
| --- | --- | --- |
| Unit / regression | fact enums, decision table, journal rule, transports (truth tables and real sockets), runtime row derivation and observation facts, applicator rules, evidence mapping, catalog, record store, compiler rules | requirements R-*; differential characterization tables copy baseline functions only as regression guards |
| Script harness | the generated mutation scripts and, from S2, claim scripts, executed under Node against stub APIs | scenario truth of section 6.5 |
| Integration | use case over recording fakes and injected stores from the real MCP input through composition, E5 and E6 applicators | R-ENTRY, R-NET, R-CAP, R-RET, R-DHCP-01, R-OBS-08 |
| Offline system | tool registration on the surface, JSON contract, full `pytest -q`, quality gate, docs build, exact-SHA CI | R-ENTRY-01/05, R-REG |
| LIVE | Q0..Q3, Q1b, acceptance records | R-QUAL, capability promotion, R-HTTPS-04 |
| Not applicable | performance/load (no requirement); webview CORS and `this-sm:` origin (unverifiable offline per `docs/testing.md`) | recorded reason |

### 6.2 Traceability matrix

| Requirement | Slice | Level | Component | Test file (proposed) |
| --- | --- | --- | --- | --- |
| R-OBS-01 | S0 | unit, socket | `live_bridge.py`, `file_bridge.py`, `transport_outcome.py` | `tests/test_transport_dispatch_facts.py` |
| R-OBS-02, 06, 07, 08; RD-10 | S0 | unit, harness, integration | `execution.py`, `configuration_runtime.py`, `enterprise_service_runtime.py`, `apply_services.py` | `tests/test_execution_status_facts.py`, `tests/test_service_mutation_script_harness.py`, `tests/test_service_application_uncertainty.py` |
| R-OBS-03, R-HTTPS-02, 03, R-ENTRY-08, R-CAP-05 | S0 | unit | `enterprise_service_runtime.py` | `tests/test_service_runtime_observation.py`, `tests/test_service_runtime.py` (authorized edits) |
| R-EVD-01 | S0 | unit | `service_runtime.py` | `tests/test_service_application_uncertainty.py` |
| R-TEST-01 | S0 | process | brief | inventory in `docs/engineering/change-briefs/server-pt-services.md` |
| R-REG-03 | every slice | unit, gate | converted enums | `tests/test_execution_status_facts.py` |
| R-ENTRY-01..07, 09, 10, 11; R-NET-01, 02; R-RET-01, 02 | S1 | unit, integration, offline system | `service_tools.py`, `apply_enterprise_services.py`, `compose_enterprise_reference.py`, `apply_configuration.py`, `service_run_record_store.py` | `tests/test_apply_enterprise_services.py`, `tests/test_service_run_record_store.py`, `tests/test_service_tools_surface.py`, `tests/test_configuration_mutation_scope_exclusion.py`, `tests/test_service_policy_derivation.py` |
| R-ENTRY-04 | S1 | unit | `foundational_evidence.py` | `tests/test_service_foundational_evidence.py` |
| R-CAP-01..04, 06, 07 | S1 | unit | `service_capabilities.py`, `apply_services.py`, `service_compiler.py` | `tests/test_service_capabilities.py` (extended), `tests/test_service_client_capabilities.py` |
| R-HTTPS-01, 04; R-QUAL-05 | S1b, Q1, Q1b | unit, LIVE | compiler, runtime, catalog, records | `tests/test_service_https_content.py` |
| R-MAIL-*, R-SEC-01/03/05/06, R-EVT-01..07, R-OBS-04/05 | S2 | unit, harness | S2 components | `tests/test_service_email_compiler.py`, `tests/test_service_email_runtime.py`, `tests/test_service_event_lifecycle.py`, `tests/test_service_secrets.py` |
| R-DHCP-01..08 | S3 | unit, harness, integration | S3 components, P-E5-1 | `tests/test_service_dhcp_compiler.py`, `tests/test_service_dhcp_runtime.py`, `tests/test_dhcp_authority_composition.py` |
| R-QUAL-01..06 | S4a, Q0..Q3 | unit, LIVE | runner, catalog, records | `tests/test_qualify_server_services.py` |
| R-COV-01/02 | S1 | unit | applicator aggregation | `tests/test_service_application.py` (extended) |
| R-REG-01/02 | every slice | offline system | whole tree | full suite, registry test |

### 6.3 Self-review checklist for each slice

- Every new action family registered in `mutation_replay.py` with a basis
  and containment; `EXECUTE_ONCE` families never leave UNKNOWN without a
  controlled repeat record.
- No `{}` collapse; every unsuccessful path names `dispatch`, `result`,
  `postcondition`, `transition` or `observation`, plus `cause`.
- No setter return used as read-back; every mutation post-read is
  unconditional.
- No `applied=False` after channel acceptance; no FAILED without an observed
  contradiction, an unsatisfied postcondition or a proven non-submission.
- No VERIFIED without a fresh read; no bundle VERIFIED with the sticky flag.
- A failed operation with an observed residual change is never CLEAN; an
  unobserved residue is never CLEAN either and is never inferred from
  `residual_change=False`.
- No fact derived from a digest, a length or a native return value; `ok` and
  `changed` come from typed values compared in the same script evaluation.
- Every consumer reads status, disposition, residue, frontier and sticky from
  `decide_mutation`; no field predicate re-derives them.
- No secret in any string that can leave infrastructure; no secret-bearing
  script on the file channel; no credential in a digest.
- No caller-supplied JavaScript, command text or process name.
- No `noqa`; enums converted with the contract-preserving form and its test;
  format and lint commits separated.
- No NTP/TFTP, voice, security, CP-SCALE or namespace file touched beyond
  the named lines.
- Docs say "documented", "supported", "measured" and "documentary
  baseline" as different facts.

### 6.4 Unscheduled implementation work (identified, not scheduled)

| Item | Why it is outside these slices |
| --- | --- |
| D-8 Extract the bridge session out of `register_tools` | architecturally right but a registry refactor beyond this scope; S1 pays one import and one call |
| D-9 E5 applicator `failure_code` clearing and missing-row FAILED (`apply_configuration.py:1229-1256`) | same defect class as B2 in E5; S1 contains it (R-RET-02); the fix needs its own E5 brief and RED cases |
| D-10 `apply_security.py` whole-batch rule | recorded in `technical-debt.md:3197-3203`; not reached by this scope |
| Legacy `evidence_from_legacy_result` UNKNOWN→NOT_ATTEMPTED for E5/E7/E8/E9 | E6 uses its own mapping; other stages keep the adapter until their own brief |
| Two-pass DNS address derivation for a DNS host without an explicit address | S1 requires an explicit address; the derivation is a later composition change |
| Secret rotation as a product feature | R-SEC-05 refuses overwrite |
| DHCP relay, DHCPv6, MX, TLS guarantees, routing protocols on the service path | out of scope by assignment |

### 6.5 S0 test inventory and authorized changes (R-TEST-01, B3)

Classification of the baseline assertions that the S0 contract touches. The
implementer repeats and commits the full inventory (every assertion of the
three modules) in the brief before implementation.

| Test | Baseline assertion | Classification | Revision 2.1 |
| --- | --- | --- | --- |
| `test_dns_actions_use_documented_process_api_and_json_escaping` (`test_service_runtime.py:38-66`) | script substrings for `getProcess("DnsServer")`, `.setEnable(true)`, `addARecordToNameServerDb(...)` | valid invariant (vendor-call surface) | unchanged |
| same | fixture rows `{id, applied}`; `all(item.applied)` | incidental representation of the row contract | fixture rows become the 4.4 row contract; assertion becomes postcondition SATISFIED and applied True |
| `test_http_content_is_serialized_and_never_interpolated_as_javascript` (67-87) | serialization invariants; fixture rows | valid invariant; incidental fixture | fixture rows updated only |
| `test_direct_dns_readback_requires_enabled_state_and_expected_record` (88-113) | VERIFIED, fresh True, method | valid invariant | unchanged |
| `test_dns_behavior_starts_typed_ping_and_reads_only_fresh_command_output` (114-150) | VERIFIED, method, script calls | valid invariant | unchanged |
| `test_dns_negative_control_requires_fresh_not_found_output` (151-182) | VERIFIED, fresh, method | valid invariant | unchanged |
| `test_dns_behavior_rejects_a_fresh_but_wrong_address` (183-213) | FAILED; `not fresh_evidence` | FAILED valid; freshness is a known incorrect expectation (a complete fresh window with the wrong address is fresh negative evidence) | FAILED, fresh True, observation CONTRADICTED |
| `test_http_behavior_uses_a_fresh_background_client_and_releases_it` (214-241) | VERIFIED; create/delete calls | valid invariant | unchanged |
| `test_http_behavior_rejects_stale_marker_and_accepts_fresh_fetch` (242-279), fresh half | VERIFIED, fresh, method | valid invariant | unchanged |
| same, stale half | FAILED; `not fresh_evidence` | known incorrect expectation (unattributed output is not a demonstrated failure) | UNKNOWN, observation INCONCLUSIVE, fresh False |
| `test_http_behavior_rejects_fresh_content_without_expected_marker` (280-303) | FAILED; `not fresh_evidence` | FAILED valid; freshness incorrect | FAILED, fresh True, CONTRADICTED |
| `test_ntp_and_tftp_behavior_remain_unobservable_without_client_evidence` (305-316) | UNOBSERVABLE, not fresh | valid invariant | unchanged (observation NOT_ATTEMPTED) |
| `test_https_behavior_uses_https_url_and_never_substitutes_http` (318-345) | https URL used, http URL absent | valid invariant | unchanged |
| same | VERIFIED with empty marker; start fixture without a mode field | known incorrect expectation (R-HTTPS-03); fixture lacks the affirmative mode read | fixture adds `https_mode: true`; asserts `setHttps(true)` and `isHttps()` in the script; status PARTIAL with `no_https_marker` |
| `tests/test_service_application.py` (all tests) | statuses, codes, no-mutation preflights, capability skips, DAG blocking | valid invariants; `FakeServiceRuntime` is a legacy producer (rows without facts; verification rows with observation UNSPECIFIED, never OBSERVED) | unchanged |
| `tests/test_e95_service_voice_manifest_application.py` | to be inventoried | unknown until inventoried | changes only if a known incorrect expectation is found, with rationale |

Harness scenarios (Node, `tests/test_service_mutation_script_harness.py`,
pattern `tests/test_typed_ping.py:196-276`): unchanged success; changed
success; unchanged failure (setter no-op); changed-to-wrong (setter stores a
different value); digest-collision pair (setter stores `qx51K0WT5Lj1` over
`yI76Uj5ZfPNL`, equal FNV-1a digest and length); setter effect then thrown
exception; getter failure (pre, post, both); AddDnsRecord native add returns
true while membership reports missing; incorrect add that leaves a different
record for the same name (membership false before and after, table changed);
add that replaces an existing record with a different address; add skipped
because the record is already present (no add call in the stub log); a
skipped row whose post-read contradicts its pre-read (row invalid). Each
scenario asserts the reported row, the derived facts, the decision, the
action status and code, and the journal `dirty_state` through the real
applicator, with every expected value taken from the stub's actual state and
call log rather than from the row. The harness skips only when Node is absent
locally and fails when `GITHUB_ACTIONS` is set (RD-9).

---

## 7. Implementer handoff

### 7.1 Ready-to-use prompt for the first eligible slice (S0)

The prompt below is the revision 2.2 S0 contract as approved, with the TD-12
amendments applied in place and marked `TD-12`. It is the text the implementer
executed; section 0 governs wherever the two could still be read apart.

```text
You are implementing slice S0 ("Observation integrity") of the plan "Server-PT services for
PC-PT clients", under the technical contract `rev2.2 + TD-12` recorded in this brief, in
the repository andres18113/cisco-muejeje. Read section 0 of this brief first: it takes precedence
over the superseded result-snapshot, missing-row and editorial clauses of revision 2.2. Execution
of this prompt required that approval; the existence of this prompt authorizes nothing.
Any LIVE Packet Tracer action needs a separate, exact-scope authorization; this slice is
offline only and must never contact a running Packet Tracer instance or start a bridge for
product use.

Baseline: main at 6263344e31ba3b0de6539d652f2cd06fc73a3562. Before editing: verify checkout,
branch and starting SHA; confirm the alias of the authoritative main in your checkout (this
maintainer checkout calls it `cisco`, a standard clone `origin`; never infer it from a feature
branch upstream); read AGENTS.md, CLAUDE.md and docs/engineering/standards.md from this
checkout; run /context in a fresh session and record the result (pending if unobservable).
Create a feature branch; do not touch other worktrees.

Exclusions that apply to every slice: no muejeje.pts, Runtime V6, new .pts, dispatcher,
protocol version, replacement transport or new bridge endpoint; IoT and feature/iot-connectivity
untouched; no CP-LIVE, voice, PoE or namespace work reopened; no NTP/TFTP features; no GUI
automation; no commits to main; no Packet Tracer execution; no changes to EXTENSION/.
S0 additionally excludes: new ServiceType, action or expectation members; mutation_replay.py;
service_capabilities.py; evidence.py; service_plan.py; tool_registry.py; any MCP tool; the
E5 compiler, applicator and runtime; the security runtime; pyproject.toml. The two shared
domain DTO files below (execution.py, configuration_runtime.py) are the explicit exception to
"no E5 file": they are shared models, and every change to them is additive with legacy
defaults proven by table tests.

Risk: L (shared domain vocabulary, journal semantics, transport contract, evidence semantics).

Boundary of S0: the whole fact chain from transport to the E6 result, including its journal
and evidence representation, plus the test inventory that makes the chain checkable.

1. Domain facts. In src/packet_tracer_mcp/domain/enterprise/models/execution.py add
   `DispatchFact` {NOT_SUBMITTED, REJECTED, ACCEPTED, ACCEPTANCE_UNKNOWN, UNSPECIFIED},
   `ResultFact` {CORRELATED, ENGINE_ERROR, MALFORMED, NOT_OBSERVED, LOST, NOT_APPLICABLE},
   `PostconditionFact` {SATISFIED, UNSATISFIED, UNOBSERVED, NOT_APPLICABLE},
   `TransitionFact` {UNCHANGED, CHANGED, UNOBSERVED, NOT_APPLICABLE} (the transition of the
   state actually read) and `FootprintFact` {COVERED, PARTIAL, NOT_APPLICABLE} (whether that
   state covers everything the setter is documented to change) (execution.py is imported by
   configuration_runtime.py, so the facts live here to avoid a cycle). Add to
   `ExecutionJournalEntry`: `dispatch: DispatchFact = UNSPECIFIED`, `result: ResultFact =
   NOT_APPLICABLE`, `residual_change: bool = False`, `cause: str = ""`; make
   `journal_from_action_results` copy them with getattr defaults and keep its baseline
   `disposition_from_status` fallback: a fact-bearing result always carries an explicit
   disposition (UNKNOWN included), and the table test proves that the fallback never turns the
   UNKNOWN disposition of an APPLIED or PARTIAL result into a mutation. Extend
   `_derive_dirty_state` by exactly one rule: a FAILED entry with `residual_change=True` counts
   as a mutation, so a failed operation that left an observed unintended change yields
   DIRTY_RECOVERABLE when its inverse is available and DIRTY_UNRECOVERABLE otherwise; every
   other input maps as at the baseline (table test over the full product of dispositions,
   inverse flags and residual_change values, with the baseline function copied into the test as
   the oracle for residual_change=False only). `residual_change=True` is an observed fact and
   `False` is only the absence of that observation: unknown residue is carried by disposition
   UNKNOWN plus `cause`, never by `residual_change=False`. In configuration_runtime.py add to
   `RuntimeActionMutation` the observation fields `dispatch`, `result`, `postcondition:
   PostconditionFact = NOT_APPLICABLE`, `transition: TransitionFact = NOT_APPLICABLE`,
   `footprint: FootprintFact = NOT_APPLICABLE`, `attempted: bool | None = None` and `cause: str =
   ""` (no `residual_change` input: residue is a decision output); add the same seven fields
   plus `residual_change: bool = False` to `ActionApplicationResult`; **TD-12.1** additionally add
   the optional `received_mutation: RuntimeActionMutation | None = None` to
   `ActionApplicationResult` and the helper `sanitized_mutation_snapshot`, so the exact classifier
   input survives and is never reconstructed from `dispatch is ACCEPTED` or from a derived status;
   add
   `ConfigurationFailureCode.OUTCOME_UNKNOWN`, `RESPONSE_MALFORMED` and
   `POSTCONDITION_UNSATISFIED`. Add `MutationDecision` (frozen dataclass: status, disposition,
   failure_code, residue in {NONE, CHANGED, UNKNOWN}, frontier: bool, sticky: bool, cause: str,
   row: str) and `decide_mutation(mutation) -> MutationDecision`, the single decision table of
   plan section 4.5, evaluated in this order: (a) legacy detection: every new fact at its
   default (dispatch UNSPECIFIED; result, postcondition, transition and footprint
   NOT_APPLICABLE; attempted None) selects row 16, the baseline rule on `applied` and the given
   `disposition`, frontier `satisfies_apply_dependency(status)`, residue NONE, not sticky;
   (b) admission: the tuple (dispatch, result, postcondition, transition, footprint, attempted,
   applied) must match exactly one of rows 1 to 15 and 17 to 20 of the table; (c) any other
   tuple, including one whose `applied` disagrees with `dispatch is ACCEPTED`, SATISFIED with a
   dispatch other than ACCEPTED, or CORRELATED without ACCEPTED, yields UNKNOWN, disposition
   UNKNOWN, OUTCOME_UNKNOWN, residue UNKNOWN, frontier closed, sticky, cause
   `inconsistent_facts`; the received fields stay on the row as diagnostics and grant nothing.
   `mutation_execution_status(mutation)` becomes `decide_mutation(mutation).status` and stays
   the only status entry point for baseline callers; rows with every new field at its default
   map exactly as the baseline (table test over every baseline disposition and both `applied`
   values, with the baseline function copied into the test as the oracle for those rows only).
   The decision-table test enumerates the full product of the seven inputs and asserts safety
   predicates rather than equality with a copy of the table: frontier open only on a validated
   SATISFIED postcondition or a legacy row; a single-entry journal CLEAN only with residue NONE
   and no sticky; every unlisted tuple UNKNOWN, closed and sticky; row 15 UNKNOWN with
   SESSION_FAILED; rows 3 to 8, 10, 15 and 19 sticky; the UNKNOWN disposition of rows 9, 10, 18 and
   19 preserved through the real `journal_from_action_results`. Convert the `(str, Enum)`
   classes of both files to `StrEnum` with `__str__ = Enum.__str__` (precedent:
   ImportIsolationState) and prove per enum that str(), format(), f-string, json.dumps,
   equality with the value, dict-key lookup, pydantic model_dump(mode="json") and round-trip
   identity are unchanged. Apply the same form to RequestDisposition in file_bridge.py. No
   `# noqa` anywhere in this slice. JSON compatibility: `ActionApplicationResult`,
   `ExecutionJournalEntry` and `ApplicationExecutionJournal` gain keys in model_dump output;
   prove that a baseline-shaped JSON fixture without the new keys still validates to defaults
   (shape of infrastructure/persistence/cp_scale_stage_evidence.py:78 output) and that every
   compact_summary() output is byte-identical to the baseline for legacy rows.

2. HTTP transport, src/packet_tracer_mcp/infrastructure/execution/live_bridge.py. Add
   `correlated_http_dispatch(js, timeout, *, base_url, port, token, http_connect_post, http_get)
   -> BridgeDispatchOutcome`, a frozen dataclass in the new
   infrastructure/execution/transport_outcome.py with fields dispatch, result, body,
   disposition (the RequestDisposition value as a string; transport_outcome imports only
   domain facts, file_bridge and live_bridge import transport_outcome, never the reverse)
   and detail (sanitized, bounded). Classification: POST /queue 200 -> ACCEPTED (acceptance by
   the local bridge queue, not by Packet Tracer); 400, 401, 409 or 503 -> REJECTED; a failure
   before the request bytes were sent (connection refused, name resolution) -> NOT_SUBMITTED;
   any failure after sending (read timeout, reset, disconnect) or an undecidable phase ->
   ACCEPTANCE_UNKNOWN. GET /result 200 -> CORRELATED; 204 -> NOT_OBSERVED; 404 or 410 -> LOST;
   socket error -> NOT_OBSERVED with detail "socket_error". Implement the phase split with a
   connect-then-send helper (http.client with an explicit connect(), or equivalent); the
   existing `_http_post`, `_http_get` and `correlated_http_send_and_wait` keep their
   signatures. Re-express `correlated_http_send_and_wait` as a wrapper and add a differential
   characterization test over every (status_post, status_get, body) combination against the
   frozen baseline body; that test is a regression guard, not the oracle. Add
   `PacketTracerHttpTransport.dispatch_and_wait`. The safety oracle is an independent truth
   table plus real-socket tests on an ephemeral port with PT_MCP_BRIDGE_TOKEN set (patterns:
   tests/test_bridge_security.py, tests/test_bridge_results.py): closed port -> NOT_SUBMITTED;
   a fake server that reads the request and closes without responding -> ACCEPTANCE_UNKNOWN;
   PTCommandBridge with no webview -> ACCEPTED plus NOT_OBSERVED; duplicate rid -> REJECTED; a
   result posted after the timeout is refused by the bridge (410) and never attributed.

3. File transport, src/packet_tracer_mcp/infrastructure/execution/file_bridge.py. Add
   `FileBridge.dispatch_and_wait -> BridgeDispatchOutcome`. Phases: `_ensure()` or
   `tmp.write_bytes` OSError -> NOT_SUBMITTED (discard any .tmp residue best effort);
   `os.replace` OSError -> ACCEPTED if the req_ path exists afterwards, else NOT_SUBMITTED;
   replace succeeded -> ACCEPTED; response read -> CORRELATED; read or unlink OSError after
   publication -> keep polling until the deadline, then NOT_OBSERVED; deadline -> NOT_OBSERVED
   carrying the per-call RequestDisposition from `_cancel`. `last_disposition` and
   `send_and_wait` are unchanged. Tests: failure before publication leaves no req_ file and
   reports NOT_SUBMITTED; failure after publication reports NOT_OBSERVED with a disposition; a
   second call after a failed first call never reports the first call's disposition;
   `proves_no_execution` stays False for every disposition. State in a comment that the engine
   filter `req_*.js` (EXTENSION/script-engine/main.js:179) is why a `.tmp` residue is not
   executable; do not test the engine.

4. Runtime, src/packet_tracer_mcp/infrastructure/execution/enterprise_service_runtime.py.
   Replace `_json_result` with `_observe(js, timeout) -> BridgeObservation(kind, payload,
   message, outcome)`; `{}` never stands for a failure. Accept `dispatch_and_wait` as an
   optional constructor argument; when only the legacy `send_and_wait` is given, wrap it: a
   body maps to result, engine_error or malformed, and None maps to ACCEPTANCE_UNKNOWN plus
   NOT_OBSERVED (never NOT_SUBMITTED). Mutation script (B1, C1): for every action the batch
   script performs a typed pre-read, the setter and an unconditional typed post-read, each
   inside its own try/catch, and reports
   `var r={id,attempted:false,skip_reason:"",call_error:"",call_result:null,pre_read:false,post_read:false,ok:null,changed:null,pre:null,post:null};`
   Pre-read: the typed value (`!!p.isEnabled()`, `!!p.isHttpsEnabled()`,
   `String(p.getPage(path))`, `!!p.getARecordWithAddress(h,a)`) is kept in a script variable;
   `pre_read=true` and `pre` = its digest only when the read completed. Ensure-present family
   (AddDnsRecord): when `pre_read` is true and the wanted record is present, the add is not
   called and `skip_reason="already_satisfied"`; otherwise `attempted=true` before the call,
   the native return is recorded as `call_result` (boolean) and never used for `ok`, and a
   bounded `call_error` is recorded on exception. Every other family always calls its setter
   (`attempted=true`). PublishTftpFile reports the declined row (`attempted=false`,
   `skip_reason="family_not_implemented"`, no reads), preserving its baseline FAILED outcome.
   Post-read: unconditional; `post_read=true` and `post` = its digest only when it completed;
   `ok` is the postcondition computed from the actual typed post value (`=== true` for a flag,
   `=== content` for the page string, `=== true` for the membership) and null when the
   post-read failed; `changed` is `preValue !== postValue` on the actual typed values and null
   when either read failed. Digests: booleans as "0"/"1"; strings as an FNV-1a 32-bit hash plus
   length computed by a helper defined once in the batch script; never a credential (no S0
   family carries one; record the rule for S2). Digests are bounded diagnostics with no
   authority: Python never compares them and derives no fact from them; equal hashes, equal
   lengths or a true `call_result` are never UNCHANGED, SATISFIED or CLEAN (the collision pair
   `yI76Uj5ZfPNL` / `qx51K0WT5Lj1`, both `1bb90b62:12`, is a harness scenario). Row validation
   (`row_invalid:<check>`, row 7): `results` must be a list of objects with `id` in the batch;
   `attempted`, `pre_read`, `post_read` bool; `ok` and `changed` bool or null; `pre`, `post`
   string or null; `call_result` bool or null; `call_error`, `skip_reason` string; `post_read`
   false requires `ok` and `changed` null; `pre_read` false requires `changed` null; both reads
   true require `ok` and `changed` non-null; `attempted` false requires `skip_reason` in
   {already_satisfied, family_not_implemented}, `call_result` null and `call_error` empty;
   `already_satisfied` requires `pre_read` true and either `ok` true or `post_read` false (a
   skipped row whose post-read contradicts its pre-read is invalid); `family_not_implemented`
   requires no reads; `attempted` true requires an empty `skip_reason`; a non-list or duplicate
   ids -> every action result MALFORMED; a missing id -> that action MALFORMED; foreign ids
   ignored and named in the message. Row -> facts for a CORRELATED batch, with footprint
   COVERED for every family except an attempted AddDnsRecord (PARTIAL,
   `footprint_partial:dns_a_record_table`) and COVERED for any skipped row (no call): invalid
   row -> row 7; declined -> row 20; `post_read` false -> postcondition UNOBSERVED, transition
   UNOBSERVED, cause `post_read_failed` (+ `call_error`), row 8; `post_read` true ->
   postcondition SATISFIED when `ok` else UNSATISFIED; `pre_read` false -> transition
   UNOBSERVED, cause `pre_read_failed`, rows 9/10; both reads -> transition CHANGED or
   UNCHANGED, rows 11 to 14 (COVERED, attempted), 17 (skipped) or 18/19 (PARTIAL); `cause`
   carries the bounded `call_error` when present. The runtime sets only the observation fields
   and `applied` (True for every ACCEPTED dispatch); status, disposition, failure_code,
   residue, frontier and sticky come from `decide_mutation` in the applicator. Whole-batch
   outcomes: ENGINE_ERROR, MALFORMED, NOT_OBSERVED, LOST -> every action postcondition
   UNOBSERVED, transition UNOBSERVED, footprint NOT_APPLICABLE, attempted None, applied per
   dispatch (rows 3 to 6). A transition observed between the two bracketing reads is reported
   as exactly that, within the observed scope of the family; it is never a claim of execution
   count, of sole causation or of anything outside that scope. Verification facts (B3): add
   `observation: ObservationFact` with members OBSERVED, CONTRADICTED, INCONCLUSIVE,
   SUBJECT_NOT_FOUND, MALFORMED, ENGINE_ERROR, NOT_OBSERVED, LOST, ACCEPTANCE_UNKNOWN,
   NOT_SUBMITTED, REJECTED, NOT_ATTEMPTED and UNSPECIFIED (the default, meaning "producer did
   not state a fact"), plus `cause: str = ""`, `claim_level: str = ""` and `limitations:
   list[str]` on RuntimeServiceVerification in domain/enterprise/models/service_runtime.py; the
   runtime never sets failure_code (the applicator derives it, so ServiceVerificationResult is
   built without a duplicate keyword). Status mapping: OBSERVED -> VERIFIED, fresh_evidence
   True; CONTRADICTED -> FAILED, fresh_evidence True (a fresh observed contradiction is fresh
   negative evidence); INCONCLUSIVE -> UNKNOWN, fresh False; SUBJECT_NOT_FOUND, MALFORMED,
   ENGINE_ERROR -> UNOBSERVABLE, fresh False; NOT_OBSERVED, LOST, ACCEPTANCE_UNKNOWN,
   NOT_SUBMITTED, REJECTED -> UNKNOWN, fresh False, with cause. Direct read-back: fresh iff
   the read was CORRELATED and parsed to the typed shape and located its subject; found False
   or process missing -> SUBJECT_NOT_FOUND; a matching read of an unchanged value ->
   OBSERVED; a mismatching complete read -> CONTRADICTED; the generated getter payload is
   byte-identical to the baseline (golden test). DNS behavior: a complete fresh window
   ("packets: sent" or a not-found line) with the wrong address or a not-found line for a
   positive expectation -> CONTRADICTED; a complete not-found window for the negative control
   -> OBSERVED; an incomplete window at the deadline -> INCONCLUSIVE; pager active or command
   not started -> INCONCLUSIVE with cause (not FAILED). HTTP behavior: content changed and
   marker present -> OBSERVED; content changed and marker absent -> CONTRADICTED; marker
   present before the request -> INCONCLUSIVE with cause "marker_present_before_request";
   no content change by the deadline -> INCONCLUSIVE with cause
   "no_response_within_deadline"; go() false -> INCONCLUSIVE with cause "client_go_false";
   the http-scheme scripts (start, inspect, release) stay byte-identical to the baseline
   (golden test). HTTPS: on the https scheme only, the start script calls setHttps(true)
   before go() and reports `https_mode` from isHttps() in the same payload; `https_mode`
   true -> continue; false -> CONTRADICTED "https_mode_not_confirmed"; absent or non-boolean
   -> MALFORMED (missing is neither false nor true). An empty marker never yields VERIFIED for
   https: PARTIAL with observation OBSERVED and limitations ["no_https_marker"]. Release the
   owned client on every exit path and record released, release_failed or release_unverified
   in observed. A verify() exception is caught inside the runtime and yields UNKNOWN with
   cause "exception:<TypeName>".

5. Applicator, src/packet_tracer_mcp/application/use_cases/apply_services.py. For every
   mutation row call `decide_mutation` once and build ActionApplicationResult from the received
   facts (dispatch, result, postcondition, transition, footprint, attempted, cause) plus the
   decision outputs (status, disposition, failure_code, residual_change = residue is CHANGED);
   no consumer in this module or downstream reads `applied` or the raw `postcondition` to decide
   anything. An exception from runtime.apply_actions yields, for every action in the batch, the
   row 15 fact tuple (dispatch UNSPECIFIED, result NOT_APPLICABLE, postcondition UNOBSERVED,
   transition UNOBSERVED, footprint NOT_APPLICABLE, attempted None, applied False, cause
   "exception:<TypeName>") passed through the same decision: status UNKNOWN, SESSION_FAILED,
   never applied=False/FAILED. **TD-12.2** replaces the unconditional missing-row sentence of
   revision 2.2: a missing item at this port has no evidence of acceptance, so it takes the row 15
   path with cause "exception:MissingRuntimeMutationResult" (UNKNOWN, SESSION_FAILED, closed,
   sticky); the row 7 tuple with cause "row_missing" is produced by the Packet Tracer adapter,
   which does hold the observed ACCEPTED, CORRELATED envelope and must return a classified typed
   result for every requested action. An empty result list from a runtime that made no dispatch is
   never proof of dispatch. Keep a
   runtime-supplied failure_code only for legacy rows (only NONE is replaced: NONE with applied
   -> NONE, NONE without applied -> APPLICATION_FAILED). Effect uncertainty: call
   execution_journal.mark_transport_unknown() exactly when any decision has sticky True (rows 3
   to 8, 10, 15, 19 and every inconsistent tuple); no field predicate re-derives it. Residue:
   for every decision with residue UNKNOWN add the limitation `residue_unknown:<id>:<cause>` to
   the E6 result; the journal entry carries disposition UNKNOWN and the cause, so `dirty_state`
   is UNKNOWN by the baseline rule and `residual_change=False` on such an entry is never read
   as "nothing changed". Frontier: `effect_established(result)` is the decision's `frontier` (a
   validated SATISFIED postcondition, or `satisfies_apply_dependency(status)` for a legacy
   row); dependents of an action that is not established become DEPENDENCY_BLOCKED with message
   "prerequisite_outcome_unknown:<id>" (UNOBSERVED or inconsistent facts) or
   "prerequisite_unsatisfied:<id>" (UNSATISFIED); independent actions and services continue.
   Verification admission: an ACTION_APPLIED prerequisite is satisfied only by
   `effect_established`; when it is not, an expectation whose kind is read-only or
   owned-temporary (module constant VERIFICATION_EFFECT_CLASSES: DIRECT_SERVICE_STATE
   read-only; DNS_RESOLUTION, DNS_NEGATIVE_CONTROL, HTTP_FETCH, HTTPS_FETCH, HTTP_BY_HOSTNAME
   owned-temporary; NTP_SYNC, TFTP_RETRIEVE read-only) still runs as a recovery read and its
   row carries the limitation "recovery_read_after_unresolved_action:<id>"; a user-state kind
   (none in S0) is DEPENDENCY_BLOCKED. A recovery read never changes the action row, never
   clears transport_unknown and never claims an execution count. Verification failure codes
   derive from status: VERIFIED -> NONE; FAILED -> VERIFICATION_FAILED (direct) or
   BEHAVIORAL_VERIFICATION_FAILED; UNKNOWN -> OUTCOME_UNKNOWN; UNOBSERVABLE ->
   DIRECT_READBACK_UNOBSERVABLE (direct) or OBSERVABILITY_LIMITATION; PARTIAL ->
   OBSERVABILITY_LIMITATION. A verify() exception reaching the applicator yields UNKNOWN with
   SESSION_FAILED, not FAILED. Aggregation: `_overall` returns FAILED with APPLICATION_FAILED
   when any action is FAILED; FAILED with POSTCONDITION_UNSATISFIED when any critical action
   is PARTIAL with that code; never VERIFIED while transport_unknown is set (PARTIAL, with
   limitations naming the action ids); a run whose only uncertainty is residue (rows 9 and 18)
   may be VERIFIED and reports `dirty_state` UNKNOWN with the `residue_unknown` limitation; a
   direct contradiction (direct FAILED with fresh evidence) caps usability_status at PARTIAL
   even when behavior is VERIFIED; direct PARTIAL or UNOBSERVABLE keeps the existing rule.
   Evidence: add `evidence_from_service_verification` in
   domain/enterprise/models/service_runtime.py; for observation UNSPECIFIED it delegates to the
   existing evidence_from_legacy_result (legacy producers keep their exact records); for
   explicit facts it sets observation_status OBSERVED (OBSERVED, CONTRADICTED), PROBE_FAILED
   (ENGINE_ERROR, MALFORMED, SUBJECT_NOT_FOUND, and, with limitation "transport:<fact>",
   NOT_OBSERVED, LOST, ACCEPTANCE_UNKNOWN, INCONCLUSIVE), NOT_ATTEMPTED (NOT_ATTEMPTED,
   NOT_SUBMITTED, REJECTED) and verification_status VERIFIED only for VERIFIED with
   fresh_evidence True. Do not modify evidence.py. Round-trip test: build runtime rows, pass
   them through the real ServiceApplicator, serialize the result with model_dump_json, validate
   it back, and assert that dispatch, result, postcondition, transition, footprint, attempted,
   residual_change and cause on action results, the journal entries' facts and UNKNOWN
   dispositions, the `residue_unknown` limitations, the verification rows' observation and
   cause, and the evidence records' observation_status and limitations are all still
   accessible and that `decide_mutation` on the validated-back facts returns the same decision;
   assert status agreement by behavior (an UNKNOWN row with a PROBE_FAILED evidence record is
   consistent), not vocabulary identity. **TD-12.1** extends this to the retained classifier
   input: round-trip the valid, inconsistent, legacy, exception and missing-result cases; compare
   the full `received_mutation` snapshot and the decision re-derived FROM THAT SNAPSHOT, never
   from a mutation rebuilt out of decision outputs; prove that the inconsistent tuple
   ACCEPTED/CORRELATED/SATISFIED/CHANGED/COVERED/attempted=True/applied=False is still
   inconsistent after the round-trip and does not become row 12; prove that mutating the original
   mutation object after application cannot change the stored snapshot; and prove that a
   baseline-shaped result without the snapshot stays a legacy record whose `applied` is never
   fabricated.

6. Generated-script harness. Add tests/test_service_mutation_script_harness.py following
   tests/test_typed_ping.py:196-276: a Node program that installs stub `ipc.network()`,
   device and process objects over an in-memory state, captures reportResult, and evaluates
   the actual batch script produced by PacketTracerEnterpriseServiceRuntime (captured through
   a recording dispatch callable). Scenarios: unchanged success, changed success, unchanged
   failure (setter is a no-op), changed-to-wrong (setter stores a different value),
   digest-collision pair (setter stores a different string whose FNV-1a digest and length equal
   the original: `yI76Uj5ZfPNL` -> `qx51K0WT5Lj1`), setter effect followed by a thrown
   exception, getter failure (pre, post, both), AddDnsRecord whose native add returns true
   while the membership getter reports missing, AddDnsRecord whose add leaves a different
   record for the same name (membership false before and after, table changed), AddDnsRecord
   that replaces an existing record with a different address (membership false then true, old
   record gone), AddDnsRecord skipped because the record is already present (NO_OP, no add
   call in the stub's call log), and a skipped row whose post-read contradicts its pre-read
   (row invalid). Feed the harness output to the runtime's row-to-facts mapping and assert the
   derived facts, the decision and the journal dirty_state through the real applicator; every
   expected value comes from the stub's actual state before and after and from its call log,
   never from the reported row, a digest or a fake disposition. Skip only when Node is absent
   locally; when the GITHUB_ACTIONS environment variable is set the test fails instead of
   skipping, so CI is the oracle. pyproject.toml is not changed.

7. Test inventory and authorized changes. Before implementation, list every assertion and
   fixture contract in tests/test_service_runtime.py, tests/test_service_application.py and
   tests/test_e95_service_voice_manifest_application.py and classify each as valid invariant,
   incidental representation or known incorrect expectation; commit that inventory in the
   change brief. Authorized changes, each with its before/after rationale in the brief:
   (a) mutation fixture rows `{id, applied}` in test_dns_actions_use_documented_process_api_and_json_escaping
   and test_http_content_is_serialized_and_never_interpolated_as_javascript become the item 4
   row contract, and `all(item.applied)` becomes an assertion on postcondition SATISFIED and
   applied True (incidental representation; the script substring assertions stay);
   (b) test_dns_behavior_rejects_a_fresh_but_wrong_address keeps FAILED and asserts
   fresh_evidence True with observation CONTRADICTED (known incorrect expectation: a complete
   fresh window with the wrong address is fresh negative evidence);
   (c) test_http_behavior_rejects_fresh_content_without_expected_marker keeps FAILED and
   asserts fresh_evidence True with CONTRADICTED (same reason);
   (d) the stale-marker half of test_http_behavior_rejects_stale_marker_and_accepts_fresh_fetch
   becomes UNKNOWN with INCONCLUSIVE and fresh False (known incorrect expectation:
   unattributed output is not a demonstrated failure); its fresh half is unchanged;
   (e) test_https_behavior_uses_https_url_and_never_substitutes_http adds `https_mode: true` to
   the start fixture, asserts the setHttps and isHttps calls, and changes VERIFIED to PARTIAL
   with limitation no_https_marker (R-HTTPS-03); its URL assertions stay.
   Everything else in those files is a valid invariant and stays unchanged, including
   test_direct_dns_readback_requires_enabled_state_and_expected_record,
   test_dns_behavior_starts_typed_ping_and_reads_only_fresh_command_output,
   test_dns_negative_control_requires_fresh_not_found_output,
   test_http_behavior_uses_a_fresh_background_client_and_releases_it,
   test_ntp_and_tftp_behavior_remain_unobservable_without_client_evidence and every test in
   tests/test_service_application.py (its FakeServiceRuntime is a legacy producer: rows
   without facts follow the legacy mapping, and its verification rows carry observation
   UNSPECIFIED, which never means OBSERVED). New tests go in new files:
   tests/test_execution_status_facts.py, tests/test_transport_dispatch_facts.py,
   tests/test_service_runtime_observation.py, tests/test_service_application_uncertainty.py,
   tests/test_service_mutation_script_harness.py. Golden-script equality (direct read-back,
   DNS verification, http-scheme verification) preserves the vendor-call surface only; it is
   not evidence of classifier equivalence, ownership, provenance or a live capability.

8. Ruff. Every touched file passes scripts/quality_gate.py. Measured at the baseline with
   ruff 0.16.7: execution.py 14 findings (4 UP042) and would be reformatted;
   configuration_runtime.py 21 (5 UP042) and reformat; live_bridge.py 12 and reformat;
   file_bridge.py 6 (1 UP042), already formatted; service_runtime.py 5 and reformat;
   enterprise_service_runtime.py 5 and reformat; apply_services.py 7 and reformat;
   tests/test_service_runtime.py 12 and would be reformatted (**TD-12 section 5** correction:
   revision 2.2 recorded "formatted"; the measured baseline is "would be reformatted", and the
   measured value is what this brief records). Own that debt in the files you touch and
   nowhere else. Split it into two commits per file set: first `ruff format` only, proven by
   AST equality (ast.dump before and after) and the unchanged suite; then lint fixes that add
   docstrings or reorder imports, proven by the suite, with no AST-equality claim. No `# noqa`.

9. Registry and catalog untouched: no new action families (mutation_replay.py unchanged);
   dispositions change no replay classification; service_capabilities.py unchanged; no
   ServiceType additions.

RED first. Each case must fail at the baseline for the stated reason, then pass:
- B1/C1a facts: harness scenario "changed-to-wrong" -> baseline row `applied=False` and journal
  dirty_state CLEAN; target FAILED disposition with residual_change True, action status
  PARTIAL with POSTCONDITION_UNSATISFIED, dirty_state DIRTY_UNRECOVERABLE (no inverse).
  "digest-collision pair" -> baseline `applied=False` and CLEAN, and a digest comparison would
  report unchanged; target transition CHANGED from the typed comparison, FAILED with
  residual_change True, DIRTY_UNRECOVERABLE. "setter effect then exception" -> baseline
  whole-batch PT_ERROR and `{}` collapse; target post-read still reported, facts derived from
  it. "getter failure (post)" -> target row 8 with `changed` null, never a transition claim.
- C1b facts: "add returns true, membership missing" -> baseline applied=True (short-circuit);
  target postcondition UNSATISFIED, footprint PARTIAL, disposition UNKNOWN, sticky,
  dirty_state UNKNOWN with `residue_unknown`. "incorrect add changes another record" and "add
  replaces an existing record" -> **TD-12 section 5** correction: revision 2.2 said these produce
  baseline CLEAN, which is wrong. At the executable baseline `6263344` the generated
  `add(...)||getter(...)` may return true, so the row is applied=True with the default UNKNOWN
  disposition, and `journal_from_action_results` plus `_derive_dirty_state` therefore yield
  dirty_state UNKNOWN, not CLEAN. Record the measured baseline of each case and do not assert a
  fabricated baseline CLEAN. The true regressions for these cases are the skipped post-read, the
  absent footprint and cause, the wrong frontier on an unsatisfied record, and the absent
  skip-on-present behavior; the target is dirty_state UNKNOWN with a named
  `residue_unknown:<id>:<cause>` limitation, never CLEAN and never a silent UNKNOWN.
  "add already present" -> target NO_OP, no add call in the stub log, frontier open, CLEAN;
  record its measured baseline too rather than assuming it.
- R-OBS-07: a fully successful apply of COVERED families (EnableDnsService, EnableHttpService,
  SetHttpContent) -> baseline dirty_state "unknown" (measured offline); target CLEAN with
  CHANGED or REASSERTED from the harness rows. The same run plus AddDnsRecord on an empty table
  -> target usability unchanged, dirty_state UNKNOWN, limitation
  `residue_unknown:<id>:footprint_partial:dns_a_record_table`; a re-run with the record present
  -> NO_OP and CLEAN.
- R-OBS-01/02: send_and_wait None during apply -> baseline FAILED ("never left the process");
  target UNKNOWN with ACCEPTANCE_UNKNOWN under the legacy wrapper, APPLIED with disposition
  UNKNOWN and OUTCOME_UNKNOWN under an ACCEPTED outcome, and transport_unknown set in both.
- B2a/C2: ACCEPTED plus ENGINE_ERROR -> baseline FAILED; target APPLIED, postcondition
  UNOBSERVED, dependents DEPENDENCY_BLOCKED, transport_unknown set, bundle never VERIFIED.
  Runtime exception after dispatch -> baseline FAILED for the batch; target UNKNOWN with
  SESSION_FAILED and transport_unknown set (row 15, never the legacy FAILED branch). Missing
  row -> baseline FAILED; target APPLIED with disposition UNKNOWN, RESPONSE_MALFORMED and
  transport_unknown set. Row 10 (pre-read failed, postcondition unsatisfied) -> target PARTIAL,
  disposition UNKNOWN, sticky, dirty_state UNKNOWN; a journal built from a FAILED disposition
  without residual for that row is the rejected revision 2.1 reading. Inconsistent tuples
  (NOT_SUBMITTED with CORRELATED and SATISFIED and applied True; ACCEPTED with ENGINE_ERROR and
  SATISFIED; ACCEPTED, CORRELATED, SATISFIED with applied False) -> target UNKNOWN, frontier
  closed, sticky, the received SATISFIED preserved on the row and never consulted.
- B2b: round-trip test of item 5; baseline models drop every new fact.
- R-OBS-03: direct read found=False -> baseline FAILED with fresh True; target UNOBSERVABLE,
  SUBJECT_NOT_FOUND. Malformed payload -> baseline FAILED; target UNOBSERVABLE MALFORMED.
  Timeout -> baseline FAILED; target UNKNOWN NOT_OBSERVED.
- B3 semantics: the four authorized assertion changes of item 7 (b) to (e) are RED at the
  baseline by construction.
- R-EVD-01: VERIFIED fresh direct read -> classification "verified"; UNKNOWN NOT_OBSERVED ->
  "probe_failed" with "transport:not_observed"; legacy rows -> identical to the baseline
  adapter output.
- Transport: the real-socket cases of items 2 and 3; the differential table is green at the
  baseline by construction and is a regression guard only.
Positive controls that must stay green unchanged: the tests named in item 7 as valid
invariants; tests/test_file_bridge.py and tests/test_file_bridge_lifecycle.py;
tests/test_bridge_results.py; tests/test_bridge_security.py;
tests/test_product_mutation_replay_registry.py; tests/test_e95_execution_semantics.py; every
other tests/test_e95_* module; golden-script equality for the direct read-back, DNS
verification and http-scheme verification payloads.

Validation (repository root, checkout-local venv):
  .\.venv\Scripts\python.exe -m pip install -e ".[test,docs,quality]"
  git rev-parse --verify "<base>/main^{commit}"
  .\.venv\Scripts\python.exe scripts\quality_gate.py --base <base>/main
  .\.venv\Scripts\python.exe -m pytest -q
  .\.venv\Scripts\python.exe -m mkdocs build --site-dir _site
  git diff --check
After committing:
  .\.venv\Scripts\python.exe scripts\quality_gate.py --base <base>/main --delivery-commit HEAD

Delivery: one commit series on the feature branch, status READY_FOR_REVIEW. The first commit
adds docs/engineering/change-briefs/server-pt-services.md containing the `rev2.2 + TD-12`
contract (self-contained; no reference to any externally supplied file) and a record section
(baseline SHA, branch,
risk L, the test inventory of item 7 with each classification, what changed, tests added,
measured Ruff counts before and after, the two-commit format/lint split). Do not claim runtime
functionality: S0 proves offline behavior against stubs only; every LIVE fact in the plan
stays a qualification gate.
```

### 7.2 Context for subsequent slices

- Repository facts the implementer must not rediscover: E6 has no product
  caller; `pt_live_deploy` stops at the manifest; `ServiceApplicator` needs
  VERIFIED foundations; the E5 `_mutation_scope` contract requires retained
  results for everything outside the delta (hence P-E5-2); a segment without
  an IOS pool loses its `SetEndpointDhcp` actions today; `policy.dns_server`
  is never set on the public path; `ServiceRequirement.required` is unused;
  every action family must be in the replay registry; `data/` is gitignored;
  the file channel runs scripts through `new Function` with `this` as the
  global; the HTTP channel's `runCode` receiver is unverified; the extension
  uses `registerEvent` and an undocumented `unregisterIpcEventByID`; the
  bridge session lives inside `register_tools`; Node harnesses exist in
  `tests/test_typed_ping.py` and `tests/test_e95_serial_physical_product_slice.py`.
- Cisco facts: section 3, local reference edition 8.1.0.
- Requirement ids, exclusions, RD-1..10, gates M-* and their owning stages
  are in sections 1.5, 3, 4, 5.
- Next eligible slice after S0: S1. Its prompt reuses the S0 header, the S1
  table, the RD-1 conditions, R-NET-01/02, R-ENTRY-11, R-RET-01/02 and
  R-CAP-07, with the LIVE acceptance paragraph marked "not authorized by this
  prompt".

### 7.3 Blockers

| Blocker | Blocks | Resolution path |
| --- | --- | --- |
| Technical director approval of the revision 2.2 S0 contract | S0 | independent review |
| No LIVE authorization | S1 acceptance, Q0..Q3, Q1b | separate exact-scope authorizations naming fixture, build, SHA, transport and stage |
| M-ENG-1, M-UNREG-1, M-UNREG-2, atomicity inference unmeasured | production use of register-then-poll and claims; S2/S3 runtime design finalization | Q0 |
| M-HTTPS-1/2, M-DNS-3, M-DNS-4 unmeasured | S1b, HTTPS promotion, required `CLIENT_DNS_SERVER`, COVERED footprint for `AddDnsRecord` | Q1 |
| M-MAIL-*, M-POP3-*, M-DHCP-1..6 unmeasured | promotion of SMTP/POP3/DHCP; DHCP-mode reader; lease-time signal; confirmed absence | Q2, Q3 |
| DNS/HTTP baseline provenance documentary | nothing today under RD-8; disclosed until the S1 acceptance record | S1 LIVE acceptance |
| `tool_registry.py` debt | S1 | RD-7 with the two-commit split |
| Node absent on a CI runner | S0 harness fails | the workflow adds `actions/setup-node` in the S0 delivery if CI proves it necessary |

### 7.4 Deferred debt

| Id | Item |
| --- | --- |
| D-1 | `enterprise_security_runtime.py::_typed_http` duplicates the background-client pattern |
| D-3 | read-only foundation reread beyond retained results |
| D-4 | DHCP relay for routed clients |
| D-5 | `nslookup` reader and DNS cache control (S5) |
| D-6 | `SERVICE_APPLY` stage in `execute_enterprise_reference` |
| D-7 | pre-existing Ruff debt in E6 files not touched by a slice |
| D-8 | bridge session extraction from `register_tools` |
| D-9 | E5 applicator `failure_code` clearing and missing-row FAILED (contained by R-RET-02, not fixed) |
| D-10 | `apply_security.py` whole-batch rule |
| D-11 | two-pass derivation of a DNS host address without an explicit intent address |

### 7.5 Readiness verdict

Planning: revised, source-backed and self-contained; status
READY_FOR_REVIEW. Implementation readiness after independent approval: S0 is
eligible (offline, bounded, with RED cases that fail at the baseline for
measured reasons and a stub harness that executes the generated scripts).
S1 is eligible after S0 on the bounded topology of R-NET-01. S4a after S1.
S1b, S2 and S3 depend on Q1 and Q0 records for their final runtime design;
their compilers and offline tests may start after S1 with the gated paths
compiled but not authorized. Runtime functionality: not established for
HTTPS behavior, SMTP, POP3 or Server-PT DHCP; established for DNS and HTTP
apply, read-back and behavioral verification on 9.0.1.0858 only by the
documentary baseline (RD-8). No claim in this document is a new observation
of a running Packet Tracer.

---

## 8. S0 implementation record

This chapter is the durable record required by `docs/engineering/standards.md`
for the S0 slice. It is written before behavioral implementation and completed
with measured results at delivery. Everything above it is the design contract
(`rev2.2 + TD-12`); this chapter is what was actually done against it.

This chapter records the candidate `ec8c8bc45c848bbc5651f99e1bc0816be346d95d`,
which an independent review returned as `REQUIRES_CHANGES`. It is kept as
written: its statements were true of that tree. Chapter 9 records the
correction and names every statement here that it supersedes.

### 8.1 Identity and authorization

| Item | Value |
| --- | --- |
| Checkout | `C:\Users\Andres\Desktop\Universidad\Uce\Cuarto\Infra\Cisco-MCP` |
| Authoritative `main` reference in this checkout | `cisco/main` (remote `cisco` = `https://github.com/andres18113/cisco-muejeje.git`) |
| Starting SHA | `6263344e31ba3b0de6539d652f2cd06fc73a3562`, equal to `cisco/main` and to the TD-12 baseline |
| Starting tree | clean (`git status --porcelain` empty) |
| Branch | `feature/server-pt-s0-observation-integrity`, created from that SHA |
| Risk class | **L** (shared domain vocabulary, journal semantics, transport contract, evidence semantics) |
| Authorization | TD-12, `APPROVED_WITH_BINDING_AMENDMENTS, S0 OFFLINE IMPLEMENTATION ONLY` |
| Interpreter | checkout-local `.venv\Scripts\python.exe`, CPython 3.12.10; `packet_tracer_mcp.__file__` resolves inside this checkout |
| Ruff | 0.16.7 (pinned) |
| Node for the generated-script harness | v24.19.0 present locally |
| LIVE Packet Tracer | not contacted; no bridge started for product use; no `EXTENSION/` change |

Instruction loading, this implementation session: the contents of
`CLAUDE.md`, `AGENTS.md` and `docs/engineering/standards.md` from this checkout
were present in the session context and were read before planning. The
interactive `/context` panel is a user-invoked command and was **not**
independently observed by the implementer in this session, so per
`docs/engineering/standards.md` the `/context` check is recorded as
**pending**, not as a passed observation. No earlier session's observation is
reused as evidence for this one.

### 8.2 Test inventory (R-TEST-01, prompt item 7)

Every assertion of the three named modules, classified as *valid invariant*,
*incidental representation* or *known incorrect expectation*. "Change" states
what this slice does to it.

#### `tests/test_service_runtime.py`

| Assertion | Classification | Change |
| --- | --- | --- |
| `test_dns_actions_use_documented_process_api_and_json_escaping`: `'getProcess("DnsServer")' in captured[0]` | valid invariant (vendor-call surface) | unchanged |
| same: `".setEnable(true)" in captured[0]` | valid invariant | unchanged |
| same: `'.addARecordToNameServerDb("safe.example.local","198.18.160.10")' in captured[0]` | valid invariant | unchanged |
| same: `all(item.applied for item in result)` over fixture rows `{id, applied}` | incidental representation of the row contract | fixture rows become the prompt item 4 row contract; the assertion becomes postcondition SATISFIED **and** `applied` True (authorized change (a)) |
| `test_http_content_is_serialized_and_never_interpolated_as_javascript`: `json.dumps(marker) in captured[0]` | valid invariant (serialization) | unchanged |
| same: `'.setPageContents("index.html",' in captured[0]` | valid invariant | unchanged |
| same: `result[0].applied` over a fixture row `{id, applied}` | incidental representation | same as (a) |
| `test_direct_dns_readback_requires_enabled_state_and_expected_record`: VERIFIED | valid invariant | unchanged |
| same: `fresh_evidence` True | valid invariant | unchanged |
| same: `evidence_method == "structured_service_getters"` | valid invariant | unchanged |
| `test_dns_behavior_starts_typed_ping_and_reads_only_fresh_command_output`: VERIFIED | valid invariant | unchanged |
| same: `evidence_method == "typed_pc_ping_hostname_fresh_output"` | valid invariant | unchanged |
| same: `getCommandPrompt` present in a call | valid invariant | unchanged |
| same: the typed `ping <hostname>` command is JSON-serialized into a call | valid invariant | unchanged |
| `test_dns_negative_control_requires_fresh_not_found_output`: VERIFIED, `fresh_evidence` True, `evidence_method == "typed_pc_ping_hostname_negative_control"` | valid invariant | unchanged |
| `test_dns_behavior_rejects_a_fresh_but_wrong_address`: FAILED | valid invariant | unchanged |
| same: `not fresh_evidence` | known incorrect expectation: a complete fresh window carrying the wrong address is fresh **negative** evidence | becomes `fresh_evidence` True with observation CONTRADICTED (authorized change (b)) |
| `test_http_behavior_uses_a_fresh_background_client_and_releases_it`: VERIFIED | valid invariant | unchanged |
| same: `getProcess("HttpBackgroundClientManager")`, `createClient()`, `deleteClient` in the calls | valid invariant (owned-temporary lifecycle) | unchanged |
| `test_http_behavior_rejects_stale_marker_and_accepts_fresh_fetch`, fresh half: VERIFIED, `fresh_evidence` True, `evidence_method == "http_client_fresh_content"` | valid invariant | unchanged |
| same, stale half: FAILED and `not fresh_evidence` | known incorrect expectation: a marker already present before the request is unattributed output, not a demonstrated failure | becomes UNKNOWN with observation INCONCLUSIVE and `fresh_evidence` False (authorized change (d)) |
| `test_http_behavior_rejects_fresh_content_without_expected_marker`: FAILED | valid invariant | unchanged |
| same: `not fresh_evidence` | known incorrect expectation (same reason as (b)) | becomes `fresh_evidence` True with observation CONTRADICTED (authorized change (c)) |
| `test_ntp_and_tftp_behavior_remain_unobservable_without_client_evidence`: UNOBSERVABLE and `not fresh_evidence` for NTP_SYNC and TFTP_RETRIEVE | valid invariant | unchanged; the row now also carries observation NOT_ATTEMPTED |
| `test_https_behavior_uses_https_url_and_never_substitutes_http`: the https URL is used and the http URL is absent | valid invariant | unchanged |
| same: `evidence_method == "https_client_fresh_content"` | valid invariant | unchanged |
| same: VERIFIED with an empty marker and a start fixture with no mode field | known incorrect expectation (R-HTTPS-03): no affirmative HTTPS-mode read, and an empty marker cannot prove the page came from the HTTPS listener | fixture adds `https_mode: true`; asserts the `setHttps(true)` and `isHttps()` calls; status becomes PARTIAL with limitation `no_https_marker` (authorized change (e)) |

#### `tests/test_service_application.py`

Every test in this module is a **valid invariant** and stays unchanged.
`FakeServiceRuntime` is a legacy producer: its mutation rows carry no
observation facts, so they select row 16 and map exactly as at the baseline;
its verification rows carry observation UNSPECIFIED, which never means
OBSERVED and delegates evidence to the legacy adapter.

| Test | Assertions | Classification |
| --- | --- | --- |
| `test_stale_topology_or_configuration_stops_before_runtime_mutation` | FAILED, `SOURCE_TOPOLOGY_MISMATCH`, no apply call | valid invariant |
| `test_foundation_must_be_verified_and_e6_never_runs_e5_implicitly` | FAILED, `FOUNDATIONAL_CONFIGURATION_MISSING`, no apply call | valid invariant |
| `test_unknown_application_capability_is_skipped_not_attempted` | PARTIAL, no DNS action attempted | valid invariant |
| `test_unsupported_application_capability_is_skipped_with_distinct_reason` | DNS rows SKIPPED with `CAPABILITY_UNSUPPORTED` | valid invariant |
| `test_action_capability_override_gates_only_the_unverified_action` | `ENABLE_HTTP` APPLIED, `SET_HTTP_CONTENT` SKIPPED with `CAPABILITY_UNKNOWN` | valid invariant |
| `test_behavioral_success_can_prove_usability_when_direct_getter_is_unobservable` | VERIFIED bundle, usability VERIFIED, direct PARTIAL | valid invariant |
| `test_applied_service_is_not_verified_when_behavior_fails` | PARTIAL bundle, a usability FAILED | valid invariant |
| `test_http_hostname_is_dependency_blocked_when_dns_resolution_fails` | composed row DEPENDENCY_BLOCKED with `DEPENDENCY_BLOCKED` | valid invariant |
| `test_runtime_target_model_mismatch_stops_without_partial_application` | `TARGET_IDENTITY_MISMATCH`, no apply call | valid invariant |

#### `tests/test_e95_service_voice_manifest_application.py`

Inventoried in full for this slice; **every** assertion is a valid invariant
and stays unchanged. No known incorrect expectation was found, so item 7's
conditional clause ("changes only if a known incorrect expectation is found")
produces no change here.

| Test | Assertions | Classification |
| --- | --- | --- |
| `test_service_manifest_retargets_runtime_copies_without_mutating_plan` | deployment id on result and journal; evidence records present; every action and verification target is the manifest-deployed name; the plan's own action names are unmutated | valid invariant |
| `test_voice_manifest_retargets_call_control_and_phone_runtime_copies` | same for the voice applicator, including phone bindings | valid invariant |
| `test_service_manifest_hash_mismatch_is_clean_and_precedes_inventory` | `TARGET_IDENTITY_MISMATCH`, `dirty_state == "clean"`, zero inventory calls, zero apply calls | valid invariant |
| `test_voice_manifest_hash_mismatch_is_clean_and_precedes_inventory` | same for voice | valid invariant |
| `test_modern_e6_plan_requires_manifest_before_runtime_inventory` | `physical-topology-v2` schema; `DEPLOYMENT_MANIFEST_REQUIRED`; zero inventory and apply calls | valid invariant |
| `test_e7_manifest_environment_mismatch_precedes_runtime_inventory` | `ENVIRONMENT_FINGERPRINT_MISMATCH`; zero inventory calls; nothing applied | valid invariant |
| `test_service_manifest_missing_binding_never_falls_back_to_plan_name` | `TARGET_IDENTITY_MISMATCH`, zero apply calls | valid invariant |
| `test_voice_manifest_missing_binding_never_falls_back_to_plan_name` | same for voice | valid invariant |
| `test_service_no_op_actions_satisfy_dependencies_and_reach_verification` | bundle VERIFIED; every action row NO_OP; verification reached; every journal entry disposition NO_OP | valid invariant; exercises the legacy row 16 path with an explicit NO_OP disposition |
| `test_voice_reasserted_actions_satisfy_dependencies_and_registration` | application APPLIED; every action row REASSERTED; registrations VERIFIED; every journal entry disposition REASSERTED | valid invariant; same legacy path with REASSERTED |

#### Authorized changes, with before/after rationale

| # | File and target | Before | After | Rationale |
| --- | --- | --- | --- | --- |
| (a) | `test_service_runtime.py`, the two mutation fixtures and their `applied` assertions | rows `{id, applied}`; `all(item.applied)` | rows follow the prompt item 4 contract; assertion is postcondition SATISFIED and `applied` True | the row shape was an incidental representation; the script substring assertions, which are the real invariant, stay |
| (b) | `test_dns_behavior_rejects_a_fresh_but_wrong_address` | FAILED, `not fresh_evidence` | FAILED, `fresh_evidence` True, observation CONTRADICTED | a complete fresh window with the wrong address is fresh negative evidence; calling it stale hid a real observation |
| (c) | `test_http_behavior_rejects_fresh_content_without_expected_marker` | FAILED, `not fresh_evidence` | FAILED, `fresh_evidence` True, observation CONTRADICTED | same reason as (b) |
| (d) | stale half of `test_http_behavior_rejects_stale_marker_and_accepts_fresh_fetch` | FAILED, `not fresh_evidence` | UNKNOWN, observation INCONCLUSIVE, `fresh_evidence` False | output that cannot be attributed to this request is not a demonstrated failure; the fresh half is unchanged |
| (d, measured) | the same test's stale fixture | assumed to exercise the marker-before-request path | assertions unchanged; a docstring records what it actually exercises | While making (d) the fixture was found never to reach the marker path at all: its dispatcher answers any script containing `deleteClient` with the release payload, and the start script contains that call to retire a previous client, so the start read returns no `started` flag and the row is INCONCLUSIVE for `client_go_false`. Same authorized outcome, so the assertion stands as item 7 specifies. The real marker path is covered by a new test in `tests/test_service_runtime_observation.py`, where new tests belong. |
| (e) | `test_https_behavior_uses_https_url_and_never_substitutes_http` | VERIFIED with an empty marker | start fixture carries `https_mode: true`; asserts `setHttps` and `isHttps`; PARTIAL with limitation `no_https_marker` | R-HTTPS-03: without a marker the fetched page cannot be attributed to the HTTPS listener, and the mode must be read affirmatively; the URL assertions stay |
| (f) | `tests/test_fire_and_forget_surface.py::test_every_applicator_uses_the_single_domain_definition` | the source of each of the five applicators must contain the literal `mutation_execution_status(mutation)` | the source must contain that literal **or** `decide_mutation(mutation)` | **Disclosed addition beyond item 7's five changes.** The invariant is "no applicator re-implements the status rule locally". S0 makes `decide_mutation` the single domain decision and defines `mutation_execution_status(mutation)` as `decide_mutation(mutation).status`, so `apply_services.py` satisfies the invariant through the stronger entry point while the literal name changes. Accepting either symbol preserves the invariant for all five applicators and still fails on a local copy. No assertion is removed or relaxed to a weaker predicate. |

#### New test modules

| Module | Scope |
| --- | --- |
| `tests/test_execution_status_facts.py` | the fact enums, their presentation equivalence, `decide_mutation` over the full seven-input product, the safety predicates, the journal `_derive_dirty_state` table, `journal_from_action_results` fact copying, legacy JSON compatibility and `compact_summary` byte-equality, and the TD-12.1 snapshot round-trip at DTO level |
| `tests/test_transport_dispatch_facts.py` | the HTTP and file dispatch classification truth tables, the differential characterization of `correlated_http_send_and_wait`, and the real-socket cases of prompt items 2 and 3 |
| `tests/test_service_runtime_observation.py` | the row validator, the row-to-facts mapping, whole-batch outcomes, the verification observation facts and the golden-script equalities |
| `tests/test_service_application_uncertainty.py` | the applicator: one decision per row, the TD-12.1 snapshot, TD-12.2's two missing-result cases, sticky propagation, frontier and dependency blocking, recovery reads, aggregation and the evidence adapter, plus the full result round-trip |
| `tests/test_service_mutation_script_harness.py` | the Node stub harness executing the actual generated batch script for the thirteen scenarios of prompt item 6, with every expected value taken from the stub's state and call log |

### 8.3 What changed

| File | Change |
| --- | --- |
| `domain/enterprise/models/execution.py` | five fact enums; four new `ExecutionJournalEntry` fields copied by `journal_from_action_results`; one added `_derive_dirty_state` rule; `StrEnum` presentation form |
| `domain/enterprise/models/configuration_runtime.py` | seven observation fields on `RuntimeActionMutation`; the same seven plus `residual_change` and the TD-12.1 `received_mutation` snapshot on `ActionApplicationResult`; three failure codes; `MutationResidue`, `MutationDecision`, `decide_mutation`, `sanitized_mutation_snapshot`; `mutation_execution_status` becomes the status projection; `StrEnum` presentation form |
| `domain/enterprise/models/service_runtime.py` | `ObservationFact`; `observation`, `cause`, `claim_level`, `limitations` on `RuntimeServiceVerification`; `limitations` on `ServiceApplicationResult`; `evidence_from_service_verification` |
| `infrastructure/execution/transport_outcome.py` (new) | `PostPhase`, `HttpPostOutcome`, `BridgeDispatchOutcome` |
| `infrastructure/execution/live_bridge.py` | `correlated_http_dispatch`, the connect-then-send phase split, `PacketTracerHttpTransport.dispatch_and_wait`; `correlated_http_send_and_wait` re-expressed as a wrapper with its signature unchanged |
| `infrastructure/execution/file_bridge.py` | `FileBridge.dispatch_and_wait`; the publication phase split; `RequestDisposition` in `StrEnum` presentation form; `send_and_wait` and `last_disposition` behaviorally unchanged |
| `infrastructure/execution/enterprise_service_runtime.py` | `_observe`/`BridgeObservation` replacing `_json_result`; the optional `dispatch_and_wait` port with the legacy wrapper; the typed pre/set/post batch script with digests and the ensure-present skip; row validation; row-to-facts mapping; whole-batch outcomes; observation facts on every verification path; the HTTPS mode read |
| `application/use_cases/apply_services.py` | one `decide_mutation` per row; result construction from received facts plus decision outputs plus the TD-12.1 snapshot; TD-12.2 missing-result handling; sticky propagation; frontier and dependency blocking; verification admission with recovery reads; verification failure codes from status; aggregation rules; the evidence adapter |

Untouched, as required: `mutation_replay.py`, `service_capabilities.py`,
`evidence.py`, `service_plan.py`, `tool_registry.py`, every MCP tool, the E5
compiler/applicator/runtime, the security runtime, `pyproject.toml`,
`EXTENSION/`. No new `ServiceType`, action or expectation member. No `# noqa`
anywhere in the slice.

### 8.4 Measured Ruff state

`ruff 0.16.7`, per file, `ruff check` findings and `ruff format --check`.

| File | Before: findings | Before: codes | Before: format | After |
| --- | ---: | --- | --- | --- |
| `execution.py` | 14 | D101×3, D102×4, D103×2, F401×1, UP042×4 | would reformat | 0, formatted |
| `configuration_runtime.py` | 21 | D101×11, D102×5, UP042×5 | would reformat | 0, formatted |
| `live_bridge.py` | 12 | D102×8, D107×2, I001×1, UP035×1 | would reformat | 0, formatted |
| `file_bridge.py` | 6 | D103×2, D107×1, D202×1, D401×1, UP042×1 | already formatted | 0, formatted |
| `service_runtime.py` | 5 | D101×4, D102×1 | would reformat | 0, formatted |
| `enterprise_service_runtime.py` | 5 | D102×3, D107×1, I001×1 | would reformat | 0, formatted |
| `apply_services.py` | 7 | D101×1, D102×4, D107×1, I001×1 | would reformat | 0, formatted |
| `tests/test_service_runtime.py` | 12 | D103×11, F401×1 | **would reformat** | 0, formatted |
| `tests/test_fire_and_forget_surface.py` | 13 | D103×12, I001×1 | would reformat | 0, formatted |

Correction required by TD-12 section 5: revision 2.2 item 8 recorded
`tests/test_service_runtime.py 12, formatted`. The measured state at the
baseline is 12 findings **and** `ruff format --check` reports it would be
reformatted. The measured value is recorded; the plan's value is not asserted.

`tests/test_fire_and_forget_surface.py` is in this table because authorized
change (f) touches it, and touching a file means owning its Ruff state. It was
not in revision 2.2's measurement, so its before-column is measured here.

The eight files of the planned set are split into two commits: first `ruff
format` alone, proven by `ast.dump` equality before and after plus the
unchanged suite (5300 passed, 3 skipped, identical); then the lint fixes
(docstrings and import order), proven by the suite with no AST-equality claim.
The UP042 findings are deliberately excluded from both: converting the ten
`(str, Enum)` classes to `StrEnum` is a presentation change that the contract
requires to carry its own per-enum equivalence proof, so it belongs with that
proof rather than in a mechanical lint commit.

A directory-wide `ruff check --fix` briefly reached seventeen model files
outside this slice during the lint commit; they were reverted before it was
made, and the commit changes only authorized files.

After the slice: **every touched file reports 0 Ruff findings and is already
formatted**, and there is no `# noqa` anywhere in the slice. The five new test
modules and `transport_outcome.py` are clean from their first commit.

| New file | Findings | Format |
| --- | ---: | --- |
| `infrastructure/execution/transport_outcome.py` | 0 | formatted |
| `tests/test_execution_status_facts.py` | 0 | formatted |
| `tests/test_transport_dispatch_facts.py` | 0 | formatted |
| `tests/test_service_runtime_observation.py` | 0 | formatted |
| `tests/test_service_application_uncertainty.py` | 0 | formatted |
| `tests/test_service_mutation_script_harness.py` | 0 | formatted |

### 8.5 Results

#### Measured baseline (RED), before implementation

Measured by checking `src/` out at `6263344` and driving the **baseline**
runtime and the baseline status and journal rules over the same Node stub the
harness uses. This is the measurement TD-12 section 5 requires, and it
corrects revision 2.2 in two places.

| Case | Measured baseline | Stub's own state | Target |
| --- | --- | --- | --- |
| changed-to-wrong (`setPageContents` stores a different value) | `applied=False`, FAILED, `APPLICATION_FAILED`, `dirty_state` CLEAN | the page **did** change to the wrong value | PARTIAL, `POSTCONDITION_UNSATISFIED`, `residual_change` True, DIRTY_UNRECOVERABLE |
| digest-collision pair (`yI76Uj5ZfPNL` to `qx51K0WT5Lj1`) | `applied=False`, FAILED, CLEAN; both digests `1bb90b62:12` | the page changed | transition CHANGED from the typed comparison, residue CHANGED, DIRTY_UNRECOVERABLE |
| setter effect then a thrown exception | `applied=False`, FAILED, CLEAN | the flag **was** set to true | the post-read is still reported; row 12 from the reading |
| post-read getter failure (pre-read succeeded) | `applied=True`, APPLIED, `dirty_state` UNKNOWN | the flag was set | row 8, `changed` null, never a transition claim |
| DNS add returns true, membership reports missing | `applied=True`, APPLIED, UNKNOWN | the table is untouched | row 19: UNSATISFIED, PARTIAL, UNKNOWN, sticky, `residue_unknown` |
| incorrect add writes a different record | `applied=True`, APPLIED, **UNKNOWN** | a *different* record appeared | `dirty_state` UNKNOWN with `residue_unknown`, never CLEAN |
| add replaces an existing record | `applied=True`, APPLIED, **UNKNOWN** | the old address is gone | row 18: SATISFIED, PARTIAL, frontier open, `residue_unknown` |
| add whose record is already present | `applied=True`, APPLIED, UNKNOWN, **and the add WAS called** | the table is unchanged | row 17 NO_OP, no add call in the stub log, frontier open, CLEAN |
| three COVERED families, fully successful | `applied=True`, APPLIED, `dirty_state` UNKNOWN | every intended state present | CLEAN with CHANGED or REASSERTED |
| the same run plus `AddDnsRecord` on an empty table | UNKNOWN | record written | usability unchanged, `dirty_state` UNKNOWN, limitation `residue_unknown:<id>:footprint_partial:dns_a_record_table` |
| `send_and_wait` returns None during apply | `applied=False`, FAILED, `APPLICATION_FAILED`, CLEAN | -- | UNKNOWN with ACCEPTANCE_UNKNOWN under the legacy wrapper; transport uncertainty set |
| accepted plus `PT_ERROR:` body | `applied=False`, FAILED, CLEAN | -- | APPLIED, postcondition UNOBSERVED, dependents blocked, sticky, never VERIFIED |
| missing row in a correlated batch | `applied=False`, FAILED, CLEAN | -- | adapter: row 7 APPLIED/UNKNOWN/`RESPONSE_MALFORMED`; applicator: row 15 (TD-12.2) |
| direct read `found=false` | FAILED, `fresh_evidence` True | -- | UNOBSERVABLE, SUBJECT_NOT_FOUND |
| direct read, malformed payload | FAILED, `fresh_evidence` False | -- | UNOBSERVABLE, MALFORMED |
| direct read, timeout | FAILED, `fresh_evidence` False | -- | UNKNOWN, transport fact, not FAILED |

**Two corrections to revision 2.2, both predicted by TD-12 section 5.** The
plan asserted baseline CLEAN for the incorrect add and for the replacing add.
The measurement says **UNKNOWN** for both, and the mechanism is exactly the one
TD-12 named: at the baseline the generated `add(...)||getter(...)` returns
true, so the row is `applied=True` with the default UNKNOWN disposition;
`journal_from_action_results` falls back to `disposition_from_status`, which
has no entry for `applied`, so the entry stays UNKNOWN and `_derive_dirty_state`
returns UNKNOWN. No fabricated CLEAN assertion was written for either case.
The same mechanism makes the fully successful COVERED run UNKNOWN at the
baseline, which revision 2.2 did record correctly.

A third measured fact the plan did not state: at the baseline an
`AddDnsRecord` whose record is **already present** still calls
`addARecordToNameServerDb`. There is no pre-read and therefore no skip, so the
"already present" case was not a no-op at all.

The five new test modules were also run against the baseline `src/` and fail
at collection, because the fact vocabulary does not exist there. That is a
true RED but a trivial one, which is why the behavioural baseline above was
measured separately in baseline vocabulary rather than inferred from it.

#### Verification results

| Level | Result |
| --- | --- |
| Unit and integration (offline, this checkout) | `pytest -q`: **5693 passed, 3 skipped**, up from 5300 passed, 3 skipped at the baseline. 393 new tests, no test removed or weakened |
| Generated-script harness | 20 scenarios executed by **Node v24.19.0** against the stub network, running the actual generated batch script. Skips only when Node is absent locally; fails under `GITHUB_ACTIONS` |
| Real-socket transport | closed port, read-then-close server, real `PTCommandBridge` with no webview, duplicate rid, late result refused 410 -- all on ephemeral ports with `PT_MCP_BRIDGE_TOKEN` supplied by the test |
| Golden-script equality | direct read-back (DNS, HTTP, HTTPS), DNS verification start and inspect, HTTP start, inspect and release: **byte-identical** to the baseline module, compared by loading both modules in one process |
| Quality gate | `scripts/quality_gate.py --base cisco/main`: 15 changed Python files, 0 mechanical exemptions, all checks passed, 15 files already formatted |
| Docs | `mkdocs build --site-dir _site` succeeds; the only warnings are the pre-existing `handoff.md` links in `docs/reference/cp-scale/` |
| Whitespace | `git diff --check` clean |
| Delivery gate | `scripts/quality_gate.py --base cisco/main --delivery-commit HEAD` on the final commit; see below |
| CI on the exact delivery SHA | **pending**: nothing was pushed by this work, so no authorized remote commit exists to run it on. No other SHA's status is offered in its place. *Historical, as of this chapter: the branch was pushed afterwards and run `35273030571` ran on `ec8c8bc`. See 9.2 for the verified current status.* |

#### Positive controls, all green and unchanged

`tests/test_file_bridge.py`, `tests/test_file_bridge_lifecycle.py`,
`tests/test_bridge_results.py`, `tests/test_bridge_security.py`,
`tests/test_product_mutation_replay_registry.py`,
`tests/test_e95_execution_semantics.py` and every other `tests/test_e95_*`
module, plus every assertion this brief classified as a valid invariant in the
three named modules.

### 8.6 Limitations

- **Nothing here is evidence of Packet Tracer behaviour.** Every observation in
  this slice comes from a stub, a fake or a local socket. The Node harness
  proves what the generated script does against an in-memory object graph, not
  what `DnsServerProcess` or `HttpBackgroundClient` do in a running instance.
  No Packet Tracer instance was contacted, no bridge was started for product
  use, and `EXTENSION/` is unchanged.
- The HTTPS mode read (`setHttps(true)` then `isHttps()`) is built on the
  documented `HttpClient` members in the local vendor reference
  (`help/default/IpcAPI/class_http_client.html`, labelled 8.1.0 on a 9.0.1.0858
  install). `DOCUMENTED` is not `SUPPORTED`: whether the call actually switches
  the listener is gate M-HTTPS-2 and stays unqualified.
- The `AddDnsRecord` footprint stays PARTIAL because gate M-DNS-4 is unmeasured.
  Widening the observation to the A-record table is not an S0 change, so an
  attempted add's residue outside the wanted record remains unobserved by
  construction, not by omission.
- The enum presentation equivalence was measured locally on **CPython 3.12.10**
  and cross-checked on 3.14.6. The CI matrix runs 3.11 and 3.13, which are not
  installed on this machine; the per-enum test runs there and is the check that
  settles them. Until that CI run exists, 3.11 and 3.13 presentation is
  **unverified**, not assumed.
- The `os.replace` phase of `FileBridge._publish` -- a rename that fails with
  the `req_` path nonetheless present -- is covered by reasoning and by the
  `_publish` contract, not by a test that provokes a real partial rename.
  `send_and_wait` deliberately keeps its baseline behaviour in that one phase.
- `ServiceApplicationResult.compact_summary()` does not carry the new
  `limitations` key, and `ApplicationExecutionJournal.compact_summary()` is
  byte-identical to the baseline. The facts are reachable through the full
  `model_dump`; the compact shapes are frozen because consumers were written
  against those exact keys.
- One change reaches outside the three modules item 7 names:
  `tests/test_fire_and_forget_surface.py`, change (f) in section 8.2. Touching
  it meant owning its Ruff state, so it also gained twelve docstrings and a
  reformat. Both are disclosed rather than folded into the mechanical commits.
- Delivery status is `READY_FOR_REVIEW`. Self-review is not independent audit,
  and this slice claims no capability promotion and no Packet Tracer
  functionality.

## 9. S0 correction record (independent review, `REQUIRES_CHANGES`)

An independent review of `ec8c8bc45c848bbc5651f99e1bc0816be346d95d` returned
`REQUIRES_CHANGES` with five findings and one narrow design clarification. This
chapter is the durable record of the correction. Chapter 8 is left as the
record of the reviewed candidate and is **not** rewritten: its statements were
true of that tree, including the ones this chapter supersedes.

### 9.1 Identity, authorization and instruction loading

| Item | Value |
| --- | --- |
| Checkout | `C:\Users\Andres\Desktop\Universidad\Uce\Cuarto\Infra\Cisco-MCP` |
| Authoritative `main` reference in this checkout | `cisco/main` (remote `cisco` = `https://github.com/andres18113/cisco-muejeje.git`) |
| Branch | `feature/server-pt-s0-observation-integrity`, upstream `cisco/feature/server-pt-s0-observation-integrity` |
| Starting SHA for this correction | `ec8c8bc45c848bbc5651f99e1bc0816be346d95d` (the reviewed candidate; `HEAD` had not moved) |
| Starting tree | `b1b14f510932b19eac5c3c85d80acb12c9f36882`, clean (`git status --porcelain` empty) |
| Verified base | `cisco/main` = `6263344e31ba3b0de6539d652f2cd06fc73a3562`, the TD-12 baseline |
| Risk class | **L**, unchanged: the corrections touch evidence semantics, the transport contract and a shared domain field |
| Authorization | TD-12, `APPROVED_WITH_BINDING_AMENDMENTS, S0 OFFLINE IMPLEMENTATION ONLY`, plus the review's narrow golden-payload clarification recorded in 9.3 |
| Interpreter | checkout-local `.venv\Scripts\python.exe`, CPython 3.12.10; `packet_tracer_mcp.__file__` resolves inside this checkout |
| Ruff | 0.16.7 (pinned) |
| Node for the generated-script harnesses | v24.19.0 present locally |
| LIVE Packet Tracer | not contacted; no bridge started for product use; no `EXTENSION/` change |

Instruction loading, this correction session: the contents of `CLAUDE.md`,
`AGENTS.md` and `docs/engineering/standards.md` **from this checkout** were
present in the session context and were read before any change. The
interactive `/context` panel is a user-invoked command and was again **not**
independently observed by the implementer, so per
`docs/engineering/standards.md` that check stays recorded as **pending**. No
earlier session's observation is reused as evidence for this one.

### 9.2 What the review superseded, and what it did not

* **CI status.** Chapter 8 recorded CI on the delivery SHA as *pending*
  because nothing had been pushed by that work. That statement is retained as
  a dated historical report and is **no longer current**: the branch was
  pushed afterwards and GitHub Actions run `35273030571` ran on head SHA
  `ec8c8bc45c848bbc5651f99e1bc0816be346d95d`. Verified directly from this
  checkout with `gh run view 35273030571 --repo andres18113/cisco-muejeje`:
  status `completed`, conclusion `success`, six jobs -- `quality`, `docs`, and
  `pytest` on `{ubuntu-latest, windows-latest} x {3.11, 3.13}` -- all
  `success`. The `pytest (ubuntu-latest, 3.13)` job (`105376774386`) logged
  `5694 passed, 2 skipped, 3 warnings`. The `quality` job (`105376774082`)
  logged `--base "origin/main"`, `Changed Python files: 15`,
  `Mechanical-only exempt: 0`, `All checks passed!`,
  `15 files already formatted`. That run says nothing about the corrected
  tree; 9.6 records the new SHA's status separately.
* **The audit counterexamples are not the correction.** The review's extracted
  predicates and stub runs were reproduced here against the real runtime, the
  real applicator and the real `FileBridge`, with controlled boundaries
  injected at the channel and at the filesystem. No audit predicate was copied
  into production code or used as a test oracle.
* **The substring check keeps a behaviour test beside it.** The review
  noted that `test_every_applicator_uses_the_single_domain_definition` --
  a source check -- cannot prove that a duplicated local classifier is
  absent. It is left as written, and
  `test_the_applicator_routes_every_row_through_the_domain_decision` now
  observes the real `ServiceApplicator` calling `decide_mutation`
  pass-through, once per row, with exactly the mutation the runtime
  reported and the row's status taken from that call.
* **Unchanged by design.** The TD-12 decision table, the canonical namespace,
  the legacy `send_and_wait` contract, the DNS partial-footprint limitation,
  the snapshot and provenance rules, and the measured DNS UNKNOWN baseline in
  8.5 all stand. No capability was promoted, no endpoint or transport was
  added, and no LIVE work was performed or claimed.

### 9.3 R1: the ownership/finalization payload exception

The review's narrow clarification takes precedence over byte-identical
ownership payloads, and only for the minimum R1 needs. Three generated
strings changed, plus the two `reportResult` calls in the reader that carry the
new `owned` field the start builders define. The scope is recorded here:

| Builder | Change | Why the minimum |
| --- | --- | --- |
| `_background_http_start` | the tracking assignment moves to immediately after `createClient()`, the stale slot is dropped only once the previous client is actually deleted, and the builder defines `owned` for the reader's `reportResult` to carry | a client created and then lost to a throw in `getLastPageContent()`, `go()` or the mode calls was untracked, so no later release could find it |
| `_background_https_start` | the same two changes; the mode calls keep their position relative to `go()` | the HTTPS start is the HTTP start plus the mode read, and the golden test that asserts exactly that relation still holds |
| `_background_http_release` (was inline in `_release_background_http`) | reports `found`, `deleted`, `present` and a bounded `error` instead of `released:!slot||!bag[key]`; the deletion is guarded and the slot is dropped only when the deletion completed | `released` was true whenever the slot was absent, so an untracked live client and a real deletion were the same answer |

Preserved in all three: the vendor call surface
(`getProcess("HttpBackgroundClientManager")`, `createClient`, `deleteClient`,
`getLastPageContent`, `setHttps`, `isHttps`, `go`), `json.dumps` serialization
of every data field, single-line source with no `//` comments, and the device
lookup the baseline performed. The inspect script and the direct read-back
scripts are byte-identical to the baseline and their golden tests are
untouched.

The affected golden expectation is **not** replaced by a weaker string
comparison. `tests/test_service_runtime_observation.py` keeps
`test_the_https_start_adds_only_the_mode_calls_to_the_http_start` (a relation
between the two builders, which the change preserves) and the frozen
`_GOLDEN_HTTP_INSPECT`; the ownership behaviour itself is asserted by the new
lifecycle harness in `tests/test_service_client_ownership_harness.py`, where
the oracle is the stub's own live-client count and call log. A changed payload
is not evidence of LIVE support: `HttpBackgroundClient` ownership remains gate
M-HTTPS-2 and is **unqualified**.

### 9.4 Finding to requirement to acceptance test to result

Every row's RED was measured on `ec8c8bc` by checking out `src/` at that
commit with the corrected tests in place (`git stash push -- src/`), per module,
and the GREEN on the corrected tree.

| Finding | Correction (requirement) | Acceptance tests | Measured RED on `ec8c8bc` | GREEN |
| --- | --- | --- | --- | --- |
| **R1** HTTP/HTTPS ownership is not finalized on every exit | Ownership is established before any later fallible call and recorded in a `ClientLease`; `_verify_http` finalizes exactly once on success, start-response loss, engine error, malformed reply, poll exception, deadline and cleanup failure; primary and cleanup outcomes are separate records; a missing slot after an unobserved start is `ownership_unknown`, never a release | `tests/test_service_client_ownership_harness.py`, 20 scenarios, oracle = the stub's live-client count and `deleteClient` log | **13 failed, 7 passed.** Seven scenarios ended with `engine.live == 1`: a live client the row reported as released. `not_submitted` on the start produced `KeyError: 'released'` (no ownership record at all). The `manager_missing` and `create_returns_null` scenarios dispatched a release for a client that never existed | 20 passed |
| **R2** recovery admission removes unrelated prerequisites | The recovery rule withholds exactly the ACTION_APPLIED prerequisites it admits, by typed `(kind, reference_id)` identity, and re-evaluates the rest through the unchanged `prerequisites_satisfied` | `tests/test_service_application_uncertainty.py` section 6b: positive recovery for ACTION_APPLIED alone; ACTION_APPLIED + ACTION_VERIFIED for the same id; ACTION_APPLIED + RESOURCE_READY for the same id; an unrelated missing id; `verification_verified:check-<id>` on a blocked verification. Every blocked case asserts the runtime verifier was NOT called | **3 failed.** `action_verified:<id>`, `resource_ready:<id>` and `verification_verified:check-<id>` were all erased by the suffix filter, the row ran and `runtime.verify_calls` contained it | 37 passed |
| **R3a** HTTP/DNS payload shape and subject | Stage-appropriate exact-type validation before freshness, content or success; `found` is read, not assumed; `owned:false` is a missing subject; uncertainty, malformed payload, subject-not-found and fresh contradiction stay distinct; R1 finalization holds on every malformed path | `tests/test_service_runtime_observation.py` section 7: the audited `{"found": false, "content": {"unexpected": "AUDIT_MARKER"}}`; six malformed page shapes; six malformed start shapes; five malformed DNS start shapes; three DNS window shapes; valid positive and negative controls | the audited counterexample returned **VERIFIED/OBSERVED**; `found: 1` and `found: "true"` with a matching marker returned **OBSERVED**; a dict or list `content` returned **OBSERVED**; a DNS start missing `blocked` or reporting `blocked: "pager_active"` was read as not blocked | 120 passed in the module |
| **R3b** DNS address equality | The resolved address is parsed from the supported complete shapes (`Pinging <address> with`, `Pinging <host> [<address>] with`, `Ping statistics for <address>:`) and compared by value; ambiguous or unreadable output is inconclusive; window completeness no longer depends on the expectation | same module, section 8: `192.0.2.10` versus `192.0.2.100`; the expected address only in the echo; only in a reply line; the exact address; the bracketed form; two disagreeing addresses; no address; an unparsable address; both negative-control directions; poll termination; an unreadable expectation | `192.0.2.100` satisfied an expectation of `192.0.2.10` and reported **VERIFIED**; the echo-only and reply-line-only windows reported **VERIFIED**; a complete wrong-address window polled to the deadline instead of terminating | 120 passed in the module |
| **R4** unobservable publication classified as NOT_SUBMITTED | `_publish` returns a three-valued `PublicationPhase`; a rename failure whose existence probe also raises is `UNKNOWN` and maps to `ACCEPTANCE_UNKNOWN` + `NOT_OBSERVED` with both causes preserved; a correlated answer still upgrades it to ACCEPTED; the `.tmp` residue is discarded best effort and `_publish` itself never withdraws the `req_` path, which `_await_response` still does at its deadline under a disposition that claims no non-execution | `tests/test_transport_dispatch_facts.py` section 4: write failure; rename failure with the request present; rename failure with the request absent; rename failure with an unobservable probe; the same, answered; the domain reading of the uncertain phase; per-call independence; the frozen `send_and_wait` behaviour | **5 failed**, four behavioural plus the new enum's own distinctness test, which fails there because the symbol does not exist. The unobservable probe reported `NOT_SUBMITTED` + `NOT_APPLICABLE`, which `decide_mutation` reads as row 1 -- a definite local FAILURE that authorizes a retry -- instead of row 3, UNKNOWN and sticky | 197 passed in the module |
| **R5** the mapper drops a setter error | `RuntimeActionMutation.call_error` carries the bounded sanitized setter detail on every admitted row, beside whatever canonical reason `cause` needs; `sanitized_mutation_snapshot` bounds it; `decide_mutation` never reads it | `tests/test_service_runtime_observation.py` section 9 (adapter), `tests/test_execution_status_facts.py` (decision and snapshot), `tests/test_service_mutation_script_harness.py` section 7 (the real generated script plus the real applicator and a real JSON round trip) | **12 failed** across the three modules. `test_no_stored_record_drops_the_setter_error_it_was_given`, which names no new field, failed because the detail was absent from the whole serialized record: for a failed pre-read `cause` was set to `""`, and for an attempted DNS add it was replaced by the footprint label | 78 + 120 + 27 passed in the three modules |

Two assertions in the R3a/R1 rows failed on `ec8c8bc` because the release
payload contract itself changed (`observed["released"]` read
`release_unverified` where the corrected contract reads `released`). They are
positive controls affected by the 9.3 payload exception, not behavioural REDs,
and are reported as such rather than counted as evidence of a defect.

### 9.5 Changed files in this correction

| File | Change |
| --- | --- |
| `domain/enterprise/models/configuration_runtime.py` | `RuntimeActionMutation.call_error`; `sanitized_mutation_snapshot` bounds it. No decision input, no new row, no change to the table |
| `infrastructure/execution/enterprise_service_runtime.py` | R1: `ClientOwnership`, `ClientLease`, `ReleaseOutcome`, `_web_fetch` split out of `_verify_http`, `_finalize_client`, `_with_release`, `_background_http_release`, ownership-first start scripts. R3a: `_typed_payload`, `TextReading`, `_text_reading`, stage validation in both readers. R3b: `_PING_TARGET`, `_PING_STATISTICS`, `_dns_resolution`, expectation-independent `_dns_window_complete`, the expected-address admission check. R5: `call_error` on every admitted row |
| `application/use_cases/apply_services.py` | R2: the suffix filter replaced by typed `(kind, reference_id)` withholding plus a re-evaluation through `prerequisites_satisfied` |
| `infrastructure/execution/file_bridge.py` | R4: `PublicationPhase`; `_publish` returns it; `dispatch_and_wait` maps `UNKNOWN` to `ACCEPTANCE_UNKNOWN` + `NOT_OBSERVED`. `send_and_wait` and `_write_atomic` untouched |
| `tests/test_service_client_ownership_harness.py` (new) | the client-ownership lifecycle harness: one long-lived Node process, the real generated scripts, per-phase injected channel boundaries, oracle = live-client count and call log |
| `tests/test_service_runtime_observation.py` | sections 7, 8 and 9 (R3a, R3b, R5 adapter); stub payloads updated to the shape the real scripts report |
| `tests/test_service_runtime.py` | stub payloads updated to the real shape; the stale-marker fixture rebound to its own script so it exercises the path it claims |
| `tests/test_service_application_uncertainty.py` | section 6b (R2); `_apply` gains an optional plan `transform`; one behaviour test that the real applicator routes every row through `decide_mutation` with exactly the mutation the runtime reported |
| `tests/test_transport_dispatch_facts.py` | R4: the `_publish` stub replaced by real filesystem-boundary injection, plus the four publication phases and the domain reading of the uncertain one |
| `tests/test_execution_status_facts.py` | R5 at DTO level: the snapshot retains and bounds `call_error`, and the decision ignores it |
| `tests/test_service_mutation_script_harness.py` | R5 through the real script: a `fail_before` and a `failure_detail` stub switch, four setter-error scenarios, the JSON round trip and the size bound |

Untouched: `EXTENSION/`, the E5 compiler/applicator/runtime, the security
runtime, `mutation_replay.py`, `service_plan.py`, `tool_registry.py`, every
MCP tool, `pyproject.toml`, and the TD-12 decision table in
`configuration_runtime.py`. No `# noqa`, no broadened ignore, no removed gate,
no unrelated cleanup.

### 9.6 Verification results for the correction

| Level | Result |
| --- | --- |
| Focused RED then GREEN, per finding | recorded in 9.4, measured per module |
| Client-ownership harness | 20 scenarios executed by **Node v24.19.0** against the stub client manager, running the actual generated start, inspect and release scripts; skips only when Node is absent locally and fails under `GITHUB_ACTIONS` |
| Generated mutation-script harness | 27 scenarios, same Node engine, same fail-not-skip rule |
| Affected runtime, application and transport modules | `tests/test_service_runtime.py`, `test_service_runtime_observation.py`, `test_service_application_uncertainty.py`, `test_transport_dispatch_facts.py`, `test_execution_status_facts.py`, `test_service_mutation_script_harness.py`, `test_service_client_ownership_harness.py`, `test_fire_and_forget_surface.py` |
| Full offline suite | `pytest -q -rs` on the delivery tree at `cc1d8951700c102693fe1512685aa071ce3ed35a`: **5779 passed, 3 skipped, 3 warnings in 365.97s**, against 5300 passed at the baseline and 5694 passed on the reviewed candidate. No test was removed, skipped or weakened |
| Ruff | `ruff check` and `ruff format --check` clean on every changed Python file, `ruff 0.16.7` |
| Docs | `mkdocs build --site-dir _site` succeeds; the only warnings are the pre-existing `handoff.md` links under `docs/reference/cp-scale/` |
| Whitespace | `git diff --check` clean |
| Delivery gate | `scripts\quality_gate.py --base cisco/main --delivery-commit HEAD` on `cc1d8951700c102693fe1512685aa071ce3ed35a`: clean tree at the exact commit, comparison base and merge base both `6263344`, 16 changed Python files, 0 mechanical exemptions, all checks passed, 16 files already formatted. Re-run on the final documentation commit, which changes no Python file; both runs are reported in the delivery summary |
| CI on the new delivery SHA | Recorded as **pending** when this table was written, because the corrected commits were then local. Superseded: `280f923` was pushed afterwards and run `35282016408` ran on it. See 9.8 for the verified result and for this round's own status |

The three skipped tests are pre-existing, environmental, and unrelated to this
correction. `pytest -q -rs` names them exactly:

* `tests/test_cp_live_data_integrity.py:103` -- `Symlinks are unavailable for
  this test account: [WinError 1314]`. Creating a symlink on Windows needs a
  privilege this non-elevated account does not hold, so the protected-snapshot
  detection cannot be exercised locally. It runs on the Linux CI legs.
* `tests/test_positive_voice_ab_evidence_ledger.py:131` -- `no retained raw run
  is present in this checkout`. The test re-hashes a retained raw LIVE run
  against its ledger entry; that evidence is gitignored, so there is nothing to
  compare and skipping is correct rather than asserting over an empty set.
* `tests/test_positive_voice_dhcp_pool_observer.py:562` -- `the ignored
  qualification artefact is absent here`, the same gitignored-evidence reason.

Neither Node harness skips here: Node v24.19.0 is present, and under
`GITHUB_ACTIONS` both fail rather than skip, so CI is the oracle.

### 9.7 Remaining limitations of the correction

- **Nothing here is evidence of Packet Tracer behaviour.** Every observation
  comes from a stub, a fake, a local socket or the local filesystem. The two
  Node harnesses prove what the generated scripts do against an in-memory
  object graph, not what `HttpBackgroundClient`, `DnsServerProcess` or the
  Script Engine do in a running instance. No Packet Tracer instance was
  contacted and no bridge was started for product use.
- The R1 finalization is bounded to **one** release dispatch. When that
  dispatch is not correlated, or the start was never observed and no slot is
  found, the row reports unresolved ownership explicitly
  (`release_failed`, `release_unverified`, `ownership_unknown`) and the
  ownership state stays **UNKNOWN**. That is the honest answer under the known
  engine boundary: a command that may execute late can create a client this
  process will never see, and no bounded observation can exclude it.
- The `Pinging`/`Ping statistics` output shapes R3b parses are taken from the
  PC command-prompt output the existing fixtures already carry, not from a
  measured LIVE run. A Packet Tracer build whose ping output uses a third
  shape would be read as `address_not_reported`, which is inconclusive and
  fail-closed rather than wrong, and would be a real gap to close with
  measured output.
- R4's `UNKNOWN` publication phase is now provoked by injecting `OSError`
  into `os.replace` and into `Path.exists` for the request path. That
  exercises the classification and the mapping; it is still not a real partial
  rename on a real filesystem, and the review's own acceptance list treats the
  injected boundary as the available evidence.
- `ServiceApplicationResult.compact_summary()` still does not carry
  `limitations`, and `call_error` is reachable through the full `model_dump`
  and `received_mutation`, not through the frozen compact shapes.
- The enum presentation equivalence remains measured locally on CPython
  3.12.10 only; 3.11 and 3.13 are settled by the CI matrix.
- Delivery status is `READY_FOR_REVIEW`. Self-review is not independent audit.
  This correction claims no capability promotion, no LIVE behaviour and no
  merge authorization.

### 9.8 Follow-up review (V1, V2) and the corrections to this record

A second independent review of `280f92363d041839166218e3485c5a2da68fbf24`
(tree `d5e6db792b9a152b0853f01bd1eb53d0e1a6603f`) returned `REQUIRES_CHANGES`
with two verification-boundary findings and three corrections to this chapter.
It accepted R1-R5, the TD-12 table, the DNS partial-footprint semantics, the
legacy compatibility boundary and the narrow ownership golden exception. The
starting point for this round is that candidate; `HEAD` had not moved.

**Exact-SHA CI is no longer pending for `280f923`.** GitHub Actions run
`35282016408`, attempt 1, completed successfully on head SHA
`280f92363d041839166218e3485c5a2da68fbf24`. Verified directly from this
checkout with `gh run view 35282016408 --repo andres18113/cisco-muejeje`: six
jobs -- `quality`, `docs` and `pytest` on
`{ubuntu-latest, windows-latest} x {3.11, 3.13}` -- all `success`. The
`pytest (ubuntu-latest, 3.13)` job (`105405865163`) logged `5780 passed,
2 skipped, 3 warnings in 342.19s`. The `quality` job (`105405864961`) logged
`Delivery validation: clean tree at exact commit 280f923...`, base and merge
base `6263344`, `Changed Python files: 16`, `Mechanical-only exempt: 0`,
`All checks passed!`, `16 files already formatted`. The local `5779 passed,
3 skipped` figure in 9.6 is a different execution on a different machine and
is retained as such; neither is relabelled as the other, and run
`35273030571` still stands for `ec8c8bc` alone.

#### The two findings

| Finding | Correction (requirement) | Acceptance tests | Measured RED on `280f923` | GREEN |
| --- | --- | --- | --- | --- |
| **V1** ownership settled from internally inconsistent stage payloads | A denied client is granted only by a payload that is coherent about it; until then the lease stays UNKNOWN and the one bounded finalization still runs. The release payload adds `error` to its shape and is checked for cross-field contradictions before any outcome: only a tuple the script can actually produce may be read as `released` | `tests/test_service_client_ownership_harness.py` section 8, through the real runtime and the persistent Node engine, overriding only one stage's reported body after its script has really run | **10 failed.** `{"owned": false, "started": true, "content_before": ""}` produced `nothing_owned` with **zero** release dispatches while the stub still held the created client; the page-text variant left `engine.live == 1`. Four impossible release tuples and two mis-typed ones returned `released`, and `{"found": false, "present": true}` was reported as `owned_slot_absent` | 33 passed |
| **V2** DNS ambiguity bypassed by the negative control | The window is classified ONCE, before either expectation is applied, into coherent not-found, coherent resolved, or ambiguous. Mutually conflicting signals and unreadable addresses are inconclusive in both directions | `tests/test_service_runtime_observation.py` section 8, every unreadable and mixed window parameterized over `DNS_RESOLUTION` **and** `DNS_NEGATIVE_CONTROL`, plus poll termination and the retained coherent controls | **8 failed.** The three unreadable windows were `INCONCLUSIVE` for a positive expectation and `FAILED`/CONTRADICTED -- fresh negative evidence -- for the negative control. A window carrying both a not-found line and a successful resolution was `VERIFIED` for the negative control and a fresh contradiction for the positive one, in both line orders | 131 passed in the module |

#### What "contradictory" means here, and what it deliberately does not

The admissible tuples are derived from what the generated builders can emit,
never from what looks odd. Writing V1 surfaced one case where those differ:
`{"found": false, "deleted": false, "present": true}` LOOKS self-contradictory
and is perfectly reachable, because `found` is
`!!(slot&&slot.manager&&slot.client)` and a slot object missing either member
reports exactly that. It is therefore not a contradiction but unresolved
ownership -- `release_unverified:slot_not_usable`, something owned that this
release could not act on -- and it has its own test saying so. The four tuples
that are refused are refused because `deleted` is only ever assigned inside
`if(found)`, after the vendor call returned and before the `catch` that fills
`error`, and the slot is dropped in the same synchronous evaluation.

The same rule governs the start payload: `owned` is `!!(m&&p)` and `p` is
`m&&m.createClient()`, so a denied client forces `content_before` to `''`,
`started` to `false` and `https_mode` to `null`. A payload that denies the
client while reporting any of those is inadmissible, and -- the point of the
finding -- it may not be read as absence, because absence is the one answer
that lets the reader skip cleanup entirely.

Neither correction adds a transport, an engine protocol, an error subsystem or
a LIVE requirement. A valid correlated no-client start still dispatches no
release; a valid release still closes normally; and an unsupported ping output
dialect stays unqualified and inconclusive rather than being guessed at.

#### Corrections to this record

* 9.4's R1 cell said **six** scenarios ended with a live client. The retained
  RED log for `ec8c8bc` shows **seven** `assert engine.live == 0` failures, and
  the delivery report and commit message said seven. The table now says seven;
  the count is reconciled against the log, not re-measured, and no log was
  reconstructed. Both this and the next item were reported as applied in the
  delivery summary for `280f923` and were not in the file: the patch used a
  `str.replace` that silently matched nothing. Every edit to this record now
  asserts its own match count.
* 9.4's R4 cell counted five failures without saying what they were. Four are
  behavioural; the fifth is the new enum's own distinctness test, which fails
  on `ec8c8bc` because the symbol does not exist there. That is now stated.
* "the `req_` path is never withdrawn" described `_publish`, not the whole
  `dispatch_and_wait` call: `_await_response` still withdraws the request at
  its deadline through `_cancel`. The wording is scoped to the publication
  phase in the table, in the `_publish` docstring and in the test comment.
  The timeout and cancellation policy is unchanged, and no
  `RequestDisposition` claims non-execution.

---

## Appendix A — Source index

Repository (commit `6263344`): `AGENTS.md`; `CLAUDE.md`;
`docs/engineering/standards.md`; `docs/engineering/change-briefs/namespace-migration.md`;
`docs/architecture/enterprise-services.md:102-118`;
`docs/qa/e95-runtime-debt.md:289-296`;
`docs/architecture/technical-debt.md:3150-3206, 3355-3470`; `docs/tools.md:70-95`;
`docs/testing.md:60-105`; `pyproject.toml` (`[tool.ruff]`, extras);
`.github/workflows/tests.yml:14-34`;
`src/packet_tracer_mcp/domain/enterprise/models/service_plan.py`;
`.../models/service_runtime.py`; `.../models/requirements.py:45-62`;
`.../models/configuration.py:149-171, 269-320, 297-307`;
`.../models/configuration_runtime.py:19-62, 73-110, 191-253, 303-355`;
`.../models/execution.py:21-49, 88-145, 206-244, 262-348`;
`.../models/evidence.py:73-122, 155-249`; `.../models/verification.py:83-109`;
`.../models/deployment.py:104-142`; `.../models/forwarding.py:97-110`;
`.../services/service_compiler.py:160-300, 420-475, 600-720`;
`.../services/configuration_compiler.py:286-326, 1128-1172, 1194-1256`;
`.../mutation_replay.py:78-135, 485-552, 693-701`;
`application/use_cases/compile_services.py`; `.../apply_services.py`;
`.../apply_configuration.py:62-104, 1196-1260, 1292-1455`;
`.../foundational_evidence.py:85-245`; `.../compose_enterprise_reference.py`;
`.../compile_configuration.py:22-47`; `.../execute_enterprise_reference.py:775-840`;
`.../plan_enterprise_hardware.py:59-70`;
`application/cp_scale_live/admission.py:196, 547-592`;
`infrastructure/execution/enterprise_service_runtime.py`;
`.../enterprise_configuration_runtime.py:838-860, 2188-2360`;
`.../endpoint_address_observer.py`; `.../live_bridge.py:34-56, 60-135, 137-230, 231-375, 473-600`;
`.../file_bridge.py:75-341`; `.../import_isolation_preflight.py:62-74`;
`.../transport_health.py:86-131`; `.../bridge_token.py:40-48`;
`.../probe_runtime.py:355-385`; `infrastructure/catalog/service_capabilities.py`;
`.../enterprise_capabilities.py:112-137, 260-288`;
`infrastructure/persistence/deployment_manifest_store.py:30-60, 87-135`;
`.../cp_scale_stage_evidence.py:78`;
`adapters/mcp/tool_registry.py:134-160, 845-860, 906-937, 949-1000, 1515-1552, 1574-1583`;
`adapters/mcp/public_surface.py`; `adapters/cli/cp_scale_live.py:1-70, 284-363`;
`src/packet_tracer_mcp/server.py`;
`EXTENSION/script-engine/main.js:1-30, 125-145, 171-181, 220-230, 278-310`;
`EXTENSION/webview/interface.js:50-61, 528-540, 672-684, 730-740`;
`tests/test_service_runtime.py:26-345`, `tests/test_service_application.py:1-300`,
`tests/test_service_capabilities.py`, `tests/test_file_bridge.py`,
`tests/test_file_bridge_lifecycle.py`, `tests/test_bridge_results.py`,
`tests/test_bridge_security.py`, `tests/test_e95_foundational_evidence.py`,
`tests/test_e95_execution_semantics.py:55-90`,
`tests/test_e95_security_control_plane_manifest.py:222-232, 300-310`,
`tests/test_e95_architecture_boundaries.py:1-40`,
`tests/test_product_mutation_replay_registry.py:40-70`,
`tests/test_typed_ping.py:196-276`,
`tests/test_e95_serial_physical_product_slice.py:1235-1263`.

Cisco (local `C:\Program Files\Cisco Packet Tracer 9.0.1\help\default\`,
edition 8.1.0): `IpcAPI/class_dhcp_client_process.html`,
`class_dhcp_client_port_data.html`, `class_dhcp_pool.html`,
`struct_dhcp_pool_lease.html`, `class_dhcp_server_process.html`,
`class_dhcp_server_main_process.html`, `class_host_port.html`, `class_port.html`,
`class_pop3_client.html`, `class_smtp_client.html`, `class_email_client.html`,
`class_email_server.html`, `class_email_user.html`, `class_mail_box.html`,
`struct_mail.html`, `class_dns_server_process.html`, `class_dns_client.html`,
`class_http_client.html`, `class_http_background_client_manager.html`,
`class_https_server.html`, `class_http_server.html`, `class_c_script_module.html`;
`scriptModules_scriptEngine.htm`; `config_servers.htm`; `config_PCs.htm`.

Offline measurements (this checkout, 2026-09-17): input SHA-256 hashes;
`git ls-remote`; enum semantics on CPython 3.12.10; Ruff 0.16.7 lint and
format state; `report_result_js` prefix length 347; baseline E6 fake run
`status=verified, dirty_state=unknown, counts {'unknown': 4}`; the copied
pure `_derive_dirty_state` returning CLEAN for FAILED-only entries.

## Appendix B — Status vocabulary mapping

| Research term | Repository term |
| --- | --- |
| Configuration assertion | `DIRECT_STATE` expectation, `direct_readback_status` |
| Functional assertion | `BEHAVIORAL` / `COMPOSED_BEHAVIORAL` expectation, `behavioral_status`, `usability_status` |
| PASS / FAIL | `ActionExecutionStatus.VERIFIED` / `FAILED`, with `PARTIAL`, `UNKNOWN`, `UNOBSERVABLE`, `DEPENDENCY_BLOCKED`, `SKIPPED` preserved |
| Sent / delivered / acknowledged / took effect | `DispatchFact`, `ResultFact`, `TransitionFact`, `PostconditionFact` (revision 2.1), `FootprintFact` (revision 2.2) |
| Supported (research) | `DOCUMENTED` only; `CapabilityStatus.SUPPORTED` with provenance `documentary_baseline` or `recorded_run` |
| Evidence level 1/2/3 | `claim_level` configured / read_back / behavioral, plus attributed |
