# Server-PT services: current workstream brief

This is the **current projection** of the Server-PT services workstream: what is
accepted, what was measured, what is in scope now, which decisions are open, and
where each stable contract lives. It is not a history. The chronological record
it replaced is preserved byte-for-byte under
[`docs/reference/server-pt/`](../../reference/server-pt/README.md): revision 2.2
planning, the S0/S1/S4a narratives (`server-pt-services-brief-9973f66.md`), the
S4A-C1..C4 correction delta (`server-pt-services-brief-0850de3.md`) and the
LIVE Q-batch evidence (`evidence/q-batch-0850de3/`). An archived record is read
only to answer a named question.

Authority order: `AGENTS.md` and `docs/engineering/standards.md` first, then the
approved active requirements and design recorded in this brief, then the owning
code and its tests. Code shows actual behavior and tests verify it; neither may
silently redefine an approved requirement. A historical record never grants a
permission, and a LIVE permission recorded in one never applies to a new run.

## Accepted baselines

| Slice | Commit | State | Record |
| --- | --- | --- | --- |
| S0 — observation integrity | `0bddc9a` | accepted | archived brief `9973f66`, sections 8 and 9 |
| S1 — product entry point (`pt_apply_enterprise_services`) | `1f08afa` | accepted, offline only | archived brief `9973f66`, sections 10 and 11 |
| S4a — qualification runner and Q0/Q1 probes | `0850de3` (tree `acc6caf`) | accepted | archived brief `0850de3`; archived brief `9973f66`, section 12 |

Authoritative main observed by delivery CI:
`6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main` in the maintainer
checkout). It contains none of the slices above.

## Measured limits: the Q batch at `0850de3`

Three authorized LIVE stages ran at `0850de3` on build 9.0.1.0858, each in its
own Packet Tracer process. The accepted input is
`server-pt-q-batch-0850de3.zip` (21,509 bytes, SHA-256
`e93b130a997c7f9a6363446373d744ef4feba54731dcc5571db4da969b8adfdc`), archived
with its records and checksums in
[`evidence/q-batch-0850de3/`](../../reference/server-pt/README.md#q-batch-evidence-at-0850de3).

| Run | Record SHA-256 | Permitted use |
| --- | --- | --- |
| Q0-file `2026-09-18T23-39-18Z-b68e4a7b` | `1a6ee081…c955` | bag persistence and one event-source experiment on file; one finite ordered contender sample; cleanup UNKNOWN |
| Q1-file `2026-09-19T00-13-08Z-985c1368` | `a0e2f938…b005` | failed marker-write diagnosis; unresolved listener behavior; the exact PC resolver-reader sample; semantic restoration CLEAN |
| Q0-http `2026-09-19T00-20-05Z-edbbc347` | `5d0b919f…5b40aa` | bag persistence and a `HostPort.ipChanged` sample on HTTP; separate-evaluation atomicity INCONCLUSIVE; cleanup UNKNOWN |

What these records establish, and what they do not:

- Every record stays attributed to `0850de3`, build 9.0.1.0858 and its own
  channel. The file ATOM-1 sample is finite and does not qualify HTTP, whose
  ATOM-1 is INCONCLUSIVE with `evaluation_scope: unknown`.
- M-UNREG-2 supports the **inert** fallback only.
  `safe_zero_event_release_established=false` on both channels, which activates
  R-EVT-05's fallback set: `SMTP_DELIVERED` as supporting evidence, no POP3
  claim, DHCP read-back at most UNKNOWN.
- Q1's M-HTTPS-1 failed at the marker write (`File not exist` for the two
  newly named pages) and decides nothing about page tables. Its M-HTTPS-2
  timed out on the positive control and both negatives, so it decides nothing
  about the listeners either. M-DNS-3 supports its exact reader sample:
  `DnsClient.getServerIp` returned the configured resolver and the unset
  representation `0.0.0.0`.
- Q1's baseline had zero backend-managed devices; both final reads held one
  `Power Distribution Device0`. Restoration compares semantic devices and links
  and permits retained backend-managed devices, so the run is CLEAN in that
  scope and **not** literal equality of the whole workspace. The raw difference
  stays in the record.
- Q0 observer cleanup (`cb2`, `cb3`) stays UNKNOWN whatever happened to the
  process afterwards. The handoff reported pid 28652 still running; any later
  LIVE work needs a fresh, operator-confirmed dedicated process.

No inconclusive row is deleted or rewritten, no capability is promoted, and the
three execution authorizations are consumed.

## Active scope

One review package with independently reviewable commits, offline only, on
`feature/server-pt-s2-mail` cut from `0850de3`:

- **Block A — S2 mail under the measured fallback.** R-MAIL-01..06 and the
  applicable R-SEC, R-OBS, R-COV and R-REG requirements, with R-EVT-05
  constraining which verification paths may exist. R-MAIL-07 belongs to Q2.
- **Block B — the Q1 experiment repair.** The marker-write defect and the
  listener observations, inside the existing runner, ledger and transport.

Explicitly excluded: Packet Tracer contact, a product bridge start, any Q stage
execution (no Q0 rerun, no Q1 retry, no Q1b/Q2/Q3), capability promotion, claim
reset, a new MCP tool or argument, an observer framework, S1b model selection,
S3, `EXTENSION/` or `.pts` changes, a transport or protocol change, and any push
or merge.

## Where each stable contract lives

| Requirement family | Authoritative destination today |
| --- | --- |
| R-OBS-01 — transport facts | `infrastructure/execution/transport_outcome.py`, `live_bridge.py`, `file_bridge.py`; `tests/test_transport_dispatch_facts.py` |
| R-OBS-02, 06, 07, 08; RD-10 — mutation decision, script contract, effect footprint | `domain/enterprise/models/configuration_runtime.py` (`decide_mutation`), `enterprise_service_runtime.py`; [E6 architecture](../../architecture/enterprise-services.md#mutation-and-observation-vocabulary); `tests/test_execution_status_facts.py`, `tests/test_service_mutation_script_harness.py`, `tests/test_service_application_uncertainty.py` |
| R-OBS-03, R-HTTPS-02/03, R-ENTRY-08, R-CAP-05 — observation limits | `enterprise_service_runtime.py`; `tests/test_service_runtime_observation.py`, `tests/test_service_runtime.py` |
| R-EVD-01 — evidence separated from status | `domain/enterprise/models/service_runtime.py`; `tests/test_service_application_uncertainty.py` |
| R-ENTRY-01..11, R-NET-01/02, R-RET-01/02 — product entry, admission, run records | `adapters/mcp/service_tools.py`, `application/use_cases/apply_enterprise_services.py`, `infrastructure/persistence/service_run_record_store.py`, `docs/tools.md`; `tests/test_apply_enterprise_services.py`, `tests/test_service_tools_surface.py`, `tests/test_service_run_record_store.py` |
| R-ENTRY-04 — foundational evidence | `application/use_cases/foundational_evidence.py`; `tests/test_service_foundational_evidence.py` |
| R-CAP-01..07 — capability authority and provenance | `infrastructure/catalog/service_capabilities.py`, `domain/enterprise/services/service_capability_resolution.py`; `tests/test_service_capabilities.py`, `tests/test_service_client_capabilities.py` |
| R-QUAL-01..04 — the governed qualification runner | `domain/enterprise/models/service_qualification.py`, `application/use_cases/qualify_server_services.py`, `adapters/cli/service_qualification.py`, `docs/qa/server-services-qualification.md`; the `tests/test_service_qualification_*.py` modules |
| R-SEC-02/04, R-REG-01/03 — serialization, registry hygiene, enum presentation | `docs/engineering/standards.md`, `pyproject.toml`, `scripts/quality_gate.py`; `tests/test_execution_status_facts.py` |
| R-TEST-01 — test-inventory discipline | `docs/engineering/standards.md`, *Architecture and test design* |
| R-HTTP-01..03, R-DNS-01..03 — DNS and HTTP service contracts | [E6 architecture](../../architecture/enterprise-services.md); `service_compiler.py`; `tests/test_enterprise_services.py` |
| R-COV-01/02 — complete, honestly labelled per-client results | `apply_enterprise_services.py`, `service_compiler.py`; `tests/test_apply_enterprise_services.py` |
| **R-MAIL-01..06, R-SEC-01/03/05/06, R-OBS-04, R-EVT-04..07, R-REG-02 — S2 mail** | **this brief (active), then** [E6 architecture, *Mail under the event fallback*](../../architecture/enterprise-services.md#mail-under-the-event-fallback) |
| R-QUAL-05/06 — re-qualification after a content or protocol change | this brief, **Open decisions** |
| R-HTTPS-01/04, R-DNS-04, R-MAIL-07, R-DHCP-01..08, R-EVT-01..03, R-OBS-05 | **not active.** Their text stays in the [archived brief](../../reference/server-pt/server-pt-services-brief-9973f66.md). R-EVT-01..03 and R-OBS-05 describe observer registration, which the fallback forbids in production |

Supersessions that still bind: TD-12.1 (the classifier reads the original
runtime input), TD-12.2 (a missing list item never synthesizes channel
acceptance) and RD-11 (digests are bounded diagnostics with no authority).

## Block A — S2 design delta (risk L)

Risk is **L**: the slice introduces credentials, an execute-once user-state
effect, a claim/quarantine mechanism and new evidence claims. It reuses the E6
models, compiler, applicator, entry coordinator, run records, fixed transport
and TD-12 fact preservation. There is no second service subsystem and no new
tool. Primary vendor references: Cisco's `class_smtp_client`,
`class_pop3_client`, `class_email_server`, `class_email_user`,
`class_mail_box`, `struct_mail`, `class_smtp_server` and `class_pop3_server`
pages, read from the local 9.0.1 install (`help/default/IpcAPI`, labelled 8.1.0).

### Requirements and acceptance

| ID | Requirement (active form) | Acceptance |
| --- | --- | --- |
| S2-01 (R-MAIL-01) | `EnableSmtpService(domain_name)` and `EnablePop3Service` set and read back the enable flag and the SMTP domain in one bracketed evaluation. The server direct read-back (`DIRECT_SERVICE_STATE` for `smtp`/`pop3`, the plan's MAIL_SERVER_STATE) reads the flags, the domain and each planned account's existence. | Node-harness scenarios over the real generated scripts: changed, reasserted, wrong stored domain and throwing setter reach the documented decision rows; the direct reader contradicts a wrong domain and reports an unreadable account as unobserved. |
| S2-02 (R-MAIL-02, R-SEC-05) | `EnsureEmailAccount(username, secret_ref)` is ENSURE_PRESENT. Existence is `getEmailUser(name)` non-null with `getUser()` equal to the name. `addUser` runs only after a completed pre-read proved absence; a present account is never changed and reports `account_preexisting` with `credential_claim:unverified`; a failed pre-read refuses (`precondition_unobserved`) and is never read as absence. An attempted add is PARTIAL footprint: existence never proves the credential. | Harness: account missing → one `addUser`, PARTIAL footprint, run `dirty_state=unknown`; account present → no call, NO_OP, cause names the unverified credential; getter throws → no call, typed refusal. The script corpus never names `getPassword`, `getAllEmailAcctAsStrings`, `changePassword`, `updateAllAccounts`, `deleteUser` or `deleteMailAt`. |
| S2-03 (R-MAIL-03, R-OBS-04) | `ConfigureEmailClient` on each selected client sets name, user, mail id, SMTP and POP3 server and password, and reads back every field except the password (PARTIAL footprint). It is refused while any claim exists on that client, so an `EmailClient` is never reconfigured while an operation on it is unresolved. Unselected clients are never touched. | Harness: read-back compares every non-secret field; a foreign claim refuses with zero setter calls; the stub shows no change on an unselected client. |
| S2-04 (R-MAIL-06, R-EVT-04, R-COV-01) | Pairs are deterministic: explicit `email_pairs`, else a ring over the sorted selected clients for n≥2 and a self-send for n=1; never all pairs. Each pair has one `message_ref`; its nonce is generated per run, is shared by subject and body and by every row of the pair, and is recorded in the run record. Every selected client and pair keeps a result row when skipped, blocked or unobserved. | Compiler tests for 0, 1, 2 and n clients, explicit and duplicate pairs, missing account, stable ids; the plan and its hash carry `secret_ref` strings only and no nonce; integration shows every pair row present under refusal, exclusion and blocking. |
| S2-05 (R-MAIL-04, R-EVT-06/07) | `SendMailMessage` is a typed EXECUTE_ONCE action on the sender, dispatched at most once per run under a pre-effect claim written in the same evaluation: an absent claim is written `in_progress` before `sendMail`, then `completed` or `unknown`; an existing foreign claim refuses with no call; this operation's own claim (same op id and run nonce) reports the earlier evaluation's effect as unknown rather than as not attempted. No claim is ever reset or deleted by product code. The row is never successful: no qualified observation of `mailSent` exists under the fallback. | Harness: claim written before the call; throw after the effect leaves `unknown` and sticky uncertainty; a replayed script sends nothing more; a foreign claim sends nothing; a lost response is UNKNOWN and is never redispatched. |
| S2-06 (R-MAIL-04 supporting, R-SEC-06) | `SMTP_DELIVERED` is a read-only, bounded scan of the intended recipient's server mailbox for the pair's nonce subject, checking sender, recipient and body. It reports presence (`claim_level=server_mailbox_presence`) and only presence: observation OBSERVED with status PARTIAL and `supporting_evidence_only`, because VERIFIED would roll up into service usability. It is not a `mailSent` success, not POP3 evidence, and it never rewrites the send row or clears its uncertainty. Unrelated mailbox content is never returned. | Harness: matching, wrong (nonce with other fields), missing within the deadline, truncated scan, absent account; payload carries counts and flags only; a recovery read after the unresolved send keeps the send UNKNOWN and sticky. |
| S2-07 (R-MAIL-05, R-EVT-05) | No event-dependent product verification exists. `SMTP_SEND`, `POP3_RETRIEVE` and `EMAIL_END_TO_END` compile as optional, typed blocked expectations; the reader registers no observer and never calls `getMailIpc`. | Catalog and runtime tests: the three kinds are UNKNOWN, their reader returns NOT_ATTEMPTED without dispatch, and the script corpus never contains `getMailIpc` or `registerEvent`. |
| S2-08 (R-CAP-03, R-REG-02) | The new action families are registered explicitly in the replay registry and the catalog. SMTP/POP3 operations and send/retrieve readiness stay UNKNOWN/UNMEASURED; required unknown services refuse before E5 (`SERVICE_INELIGIBLE`), optional ones are excluded and reported, and the applicator dispatches no unknown operation. Positive runtime tests use explicit test-bound catalogs passed to the use case, never a public override. | Registry completeness test; catalog tests; default-catalog admission tests with zero mutating calls; applicator test keeps every mail action SKIPPED under UNKNOWN. |
| S2-09 (R-SEC-01, R-SEC-02) | Secret-bearing actions (`EnsureEmailAccount`, `ConfigureEmailClient`, `SendMailMessage`) are admitted only on the authenticated HTTP channel fixed at A5, with no file fallback (`SECRET_TRANSPORT_UNAVAILABLE`), and every `secret_ref` resolves before any user-state mutation (`SECRET_UNRESOLVED`). Secrets reach JavaScript only through `json.dumps`, never enter a plan, hash, record or response, and are redacted in raw, JSON-escaped and URL-encoded form from every runtime row, TD-12 snapshot and persisted record. No secret-bearing script is written to disk. | Admission tests with a file channel and a failing resolver (zero mutating calls, nothing leaked); a round trip through the real applicator, snapshot and record store with an adversarial secret in an engine error; a file-bridge spy proves no secret-bearing request was written. |
| S2-10 (R-ENTRY-06, R-RET-02, R-COV-02) | The existing entry controls bind mail: E5 failure or uncertainty prevents mail effects, a lost record rewrite stops further mutation, and successful unrelated DNS/HTTP never upgrades an unobserved mail row. | Integration tests through the real composition, compiler, applicators and store with only external seams injected. |
| S2-11 (public surface) | No additional MCP tool and no experimental-profile argument; the default catalog prevents live mail effects; S1 DNS/HTTP behavior is unchanged. | Surface test on the registered tools and the tool signature; the S1 suites pass unchanged. |

### Design

**Intent.** `ServiceRequirement` gains `domain_name`, `email_accounts`
(`EmailAccountRequirement(username, secret_ref, display_name)`),
`email_clients` (`EmailClientRequirement(client_device_id, username)`),
`email_pairs` (`EmailPairRequirement(sender_device_id, recipient_device_id)`)
and `verification_mode` (`effectful`, the default, or `configure_only`, which
compiles no message). An SMTP service selects exactly its email clients; a POP3
service selects none and owns only its enable and direct read-back.

**Plan.** `ServiceType` gains `smtp` and `pop3`; `ServicePhase` gains
`CLIENT = 40` and `MESSAGE = 50`. Actions: `EnableSmtpService`,
`EnablePop3Service` (server, ENABLE), `EnsureEmailAccount` (server, CONTENT),
`ConfigureEmailClient` (client host, CLIENT) and `SendMailMessage` (sender host,
MESSAGE, EXECUTE_ONCE). Verification kinds: `email_client_state` (client direct
read-back), `smtp_send` (optional, gated), `smtp_delivered` (performed on the
server, reported on the recipient), `pop3_retrieve` and `email_end_to_end`
(optional, gated, compiled only when a POP3 service shares the host). All pair
rows belong to the SMTP service so that no expectation depends across services.

**Why the send is an action, not a verification.** A verification passes the
mutation gate unchecked because reads and owned releases must continue after a
persistence loss. `sendMail` is a user-state effect, so it is dispatched by the
applicator as an action: the gate, the capability check, the replay registry and
the no-redispatch rule then apply to it without new machinery. This matches the
revision 2.1 DHCP correction (acquisition by an action, never by a
verification).

**Decision table.** Two rows are added to `decide_mutation`:

| Row | Facts | Decision |
| --- | --- | --- |
| 21 | ACCEPTED, CORRELATED, UNOBSERVED, NOT_APPLICABLE, COVERED, attempted=False | FAILED, disposition FAILED, residue NONE, frontier closed, not sticky; cause `not_attempted:refused:<reason>` |
| 22 | ACCEPTED, CORRELATED, UNOBSERVED, NOT_APPLICABLE, PARTIAL, attempted ∈ {True, None} | APPLIED, disposition UNKNOWN, OUTCOME_UNKNOWN, residue UNKNOWN, frontier closed, sticky; cause `effect_unobservable:<reason>` |

Row 21 is a correlated refusal before any setter: nothing was called, so there
is no residue and nothing to doubt. Row 22 is an execute-once effect with no
qualified same-evaluation observation: the effect may have happened, so it is
sticky and never opens the frontier. Both tuples were `inconsistent` before, so
no existing producer changes meaning.

**Claims and serialization (R-EVT-06/07, R-OBS-04).** Claims live in the
production global `__mcpE6Claims`, keyed `email_client:<device>`, as
`{state, op_id, message_ref, nonce, seq}`. Within one invocation the applicator
dispatches one batch at a time and never runs a verification concurrently;
across invocations in one MCP process the runtime serializes mail batches and
mail reads behind one process lock; across processes only the engine claim
remains. The claim bounds duplicates **only** under the single-evaluation
atomicity inference, which the file sample supports for its sample and the HTTP
sample left INCONCLUSIVE, so no dispatch path is admitted on it: the family is
UNKNOWN in the catalog and in the replay registry, and execution stays blocked
pending Q2 evidence.

**Secrets.** A `SecretResolver` port (`application/ports/secret_resolver.py`)
returns an opaque `SecretValue` whose representation never shows the value. The
local adapter reads `PT_MCP_SECRET_<REF>` from the process environment, refuses
refs outside `[A-Za-z0-9_.-]{1,64}` and values shorter than four characters
(redaction of a shorter value would be unsound), and memoizes per invocation so
admission and dispatch see one value. Admission resolves every ref; the runtime
resolves again from the same instance while building a script, and redacts
every value it resolved from every string it returns.

**Nonces.** The compiled plan carries `message_ref` only, so its semantic hash
is stable across runs. Before E4 the coordinator binds one fresh nonce per
`message_ref` into a copy of the eligible plan and records the mapping in the
run record. Nonces are not secrets.

**Catalog and registry.** `Server-PT:smtp` and `Server-PT:pop3` profiles and
every new operation record are UNKNOWN with `documentary_baseline` provenance.
Registry: the two enables are REPLAY_SAFE on payload shape (declarative setters
read back in the payload, like the existing enables); `EnsureEmailAccount`,
`ConfigureEmailClient` and `SendMailMessage` are UNKNOWN/UNMEASURED. The
mutation-containment inventory gains the mail mutators.

**Not implemented, by design.** Observer registration, `mailSent`/`mailReceived`
parsers, `getMailIpc`, POP3 mailbox ownership checks (R-SEC-06 is unreachable
because no retrieval exists) and any claim reset.

### Invariants

1. No mail effect is dispatched by the default catalog, and no dispatch path
   depends on an unmeasured concurrency guarantee.
2. A secret never appears in a plan, hash, record, response, journal, snapshot
   or file-channel request.
3. An execute-once effect is dispatched at most once per run and never after an
   ambiguous outcome; a claim is never reset by product code.
4. Dispatch, server-mailbox presence and client retrieval remain three claims;
   none is inferred from another.
5. S1's manifest, E5 closure, foundation, persistence, retained-result and
   per-client coverage invariants hold unchanged.

## Block B — Q1 repair design delta (risk L)

Risk stays **L**: the change alters what a future LIVE stage writes and what it
may conclude. S1b stays gated and no model is selected.

### Requirements and acceptance

| ID | Requirement | Acceptance |
| --- | --- | --- |
| Q1R-1 | M-HTTPS-1 writes only a page already observed to exist on the owned disposable server (`index.html`), with run-specific **content**, never a new filename. Both handles must read the page successfully and non-empty before it is mutated; a read failure, empty content or truncated representation is INCONCLUSIVE, never a separate table. | Node stub whose `setPageContents` is update-only (`File not exist` for an unknown URL, as recorded LIVE): the repaired probe never creates a page and the stub's page keys are unchanged; baseline read failures stop before any write. |
| Q1R-2 | The procedure is write H through `HttpServer`, independent read through both handles, write S through `HttpsServer`, independent read through both handles, each step admitted only after the previous one was interpreted. Shared requires coherent cross-visibility both ways; separate requires both own writes visible and the opposite handle unchanged. Anything mixed, unread or thrown is INCONCLUSIVE with per-cell causes. | Domain tests for shared, separate, mixed, per-cell errors, truncation and lost answers; harness runs under both stub table models. |
| Q1R-3 | M-HTTPS-2 records bounded, sanitized observations where documented readers exist: page read-back through both handles, HTTP/HTTPS/inherited enable flags, the request URL and client mode, and endpoint readiness on the fixture links (`Port.isPortUp`, `isProtocolUp`, `getLink`, `HostPort.getIpAddress/getSubnetMask`). Unavailable observations are named: no documented `HttpClient` URL getter, no mode read in the HTTP reader, no documented STP or light-status reader. | Stage facts carry each observation or its named absence; the production fetch scripts stay byte-identical. |
| Q1R-4 | A negative is interpreted only after a same-mode working positive: an HTTP-mode positive with both listeners enabled precedes the HTTP-mode negative, and the HTTPS-only positive precedes the HTTPS-mode negative. A failed positive stops the negatives it would qualify and triggers one readiness read. No sleep, timeout or status-code semantics is added; a declared negative without a qualified refusal observable stays INCONCLUSIVE. | Coordinator tests for timed-out positives, wrong content, lost answers, unobserved toggles and the nominal path, each ending in authorized finalization. |
| Q1R-5 | Q1 keeps the reviewed 60-operation / 600-second ceiling and its 10-operation reserve. Optional M-DNS-1/2 are omitted explicitly as optional measurements without a reviewed probe, not as a budget refusal, and M-DNS-3 is not repeated. | Stage-definition test pins the new worst case; a coordinator run at the ceiling with every extra poll forced refuses nothing and never borrows the reserve. |
| Q1R-6 | Restoration keeps comparing semantic devices and links; the record states that scope and names a changed backend-managed count instead of implying whole-workspace equality. | Finalization test with a retained backend-managed device: CLEAN in scope, limitation present, raw reads unchanged. |

### Planned worst case

| Phase | Step | Operations |
| --- | --- | --- |
| admission | executable build, workspace baseline | 2 |
| setup | 4 fixture devices at 2 each, 3 links at 2 each, fixture identity | 15 |
| setup | E5 endpoints, E6 enable HTTP and HTTPS | 2 |
| experiment | M-HTTPS-1: write H, read both, write S, read both | 4 |
| experiment | M-HTTPS-2: readiness, marker page, HTTP positive (4), HTTP off, HTTPS positive (4), HTTP negative (4), HTTPS off, HTTPS negative (4) | 20 |
| experiment | M-DNS-3 client resolvers | 1 |
| finalization reserve | 4 device removals at 2 each, 2 restoration reads | 10 |
| | **planned worst case** | **54** |

A failed positive spends one readiness read instead of the steps it stops, so
every early exit costs less than the complete path. Six operations of slack
remain; they are not a retry entitlement.

## Test design

| Level | Scope | Files |
| --- | --- | --- |
| unit (domain) | pairing, ids, hash content, decision rows 21/22, secret value and redaction, Q1 page-table and listener rules | `tests/test_service_mail_compiler.py`, `tests/test_execution_status_facts.py`, `tests/test_service_secrets.py`, `tests/test_service_qualification_contracts.py` |
| harness (generated scripts) | the real mail and Q1 JavaScript executed by Node stubs whose state, not the reported row, is the oracle | `tests/test_service_mail_script_harness.py`, `tests/test_service_qualification_probes.py` |
| integration | the real composition, compiler, applicators, runtime and store with only external seams injected | `tests/test_service_mail_integration.py`, `tests/test_service_qualification_coordinator.py` |
| system | the public tool surface and the Q1 stage gate an operator meets | `tests/test_service_tools_surface.py`, `tests/test_service_qualification_cli.py` |
| regression | S1 entry, S0 decision, S4a runner and the containment gates | the existing modules, unchanged except where a delta above names them |

Acceptance testing is offline through the product use case and the runner. A
positive runtime test with an injected catalog is not product acceptance, and
LIVE acceptance of S2 (Q2) or of the repaired Q1 requires a new exact-SHA
authorization that this brief does not grant.

## Open decisions

| # | Decision | Current disposition |
| --- | --- | --- |
| 1 | **Q1 budget.** | 60 / 600 with the 10-operation reserve; the repaired worst case is 54. No LIVE authorization follows from it. |
| 2 | **Q0 slack.** | Unchanged: 20 / 300; one spare operation is not a retry entitlement. |
| 3 | **Mail evidence under the fallback.** | `SMTP_DELIVERED` is supporting evidence only. Promotion of any mail operation needs a Q2 record at its own SHA; an event path needs a safe zero-event release first. |
| 4 | **Claim scope on HTTP.** | The claim bounds duplicates only within one evaluation. HTTP separate-evaluation atomicity is INCONCLUSIVE, so the claim is a candidate mechanism, not a qualified one. |
| 5 | **R-QUAL-05/06.** | A repaired-Q1 sample would be attributed to its own SHA and can never be relabeled as S1b/Q1b evidence. |

Deferred, with its consumers identified in the `0850de3` archive: reducing root
`handoff.md` to a route.

## Next authorized offline work

1. Land Block A and Block B with their regressions and keep the package
   `READY_FOR_REVIEW`.
2. Exact-SHA CI once a push is authorized; no earlier run is relabeled.
3. Independent review. Only after it may a new exact-SHA Q1 authorization be
   requested; its sample cannot become S1b/Q1b evidence.

## Verification evidence

Pending: recorded by the results commit of this package.
