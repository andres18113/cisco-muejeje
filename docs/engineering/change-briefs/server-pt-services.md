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
| S2 — mail and repaired Q1 candidate | `cdc30cd` (tree `629573e`) | offline candidate; S2-R1 C0 closed on the S3 branch, independent review pending | this brief, Blocks A to C and C0 below |
| S3 — DHCP candidate reviewed for correction | `d02ddac` (tree `2e62042`) | `REQUIRES_CHANGES`; bounded correction and qualification campaign active | this brief, Blocks D and E |

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

One governed correction and qualification campaign on
`feature/server-pt-s3-dhcp`, starting from audited commit
`d02ddac37864e2b390219d5c30eee4045f3d146e` (tree
`2e62042ab032b913f522033615b6e138bf3c1bf7`):

- **C0 — close S2-R1 at the source.** A generated owned-client release script
  that may execute after credential resolution returns only a closed error
  category, never cropped engine text.
- **Block D — Server-PT DHCP.** R-DHCP-01..08 under the measured R-EVT-05
  fallback: canonical per-segment authority, delegated E5 bootstrap, typed
  Server-PT pool actions, one claimed acquisition action, bounded read-back,
  stage-aware lease prerequisites, admission, persistence and reporting.
- **Block E — audited corrections and qualification.** Strict native boolean
  integrity, coherent bounded lease evidence, bounded exclusion reads, an
  executable Q3 stage, and the exact-SHA Q3-file then repaired-Q1-file campaign
  authorized by `SERVER-PT-D02-Q3-Q1-AUTOFIX-01`.
- **Block F — amendment 01.** Typed native-default coexistence for Q3, one
  bounded readiness gate before any network attempt, the E5-before-E6 effect
  classification, the explicit M-DHCP-3 omission, and S1b implemented offline
  on the measured `shared_content` branch, authorized by
  `SERVER-PT-D02-Q3-Q1-AUTOFIX-01-AMENDMENT-01`.

Still excluded: capability promotion, a public experimental switch, claim
reset or deletion, product `dhcpRelease`/`resetDhcpConfOn`, a new MCP tool or
argument, relay/routed/wireless DHCP, Q0/Q2, Q1b, `EXTENSION/` or `.pts`
changes, transport/protocol changes, merge to main and force publication. The
campaign and its amendment authorize only ordinary fast-forward publication of
this feature branch for exact-SHA CI and the bounded attempts defined in Block
E and in Block F. They do not authorize unrelated GUI work or contact with
foreign/user state.

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
| **R-HTTPS-01 — the shared page store (S1b)** | **this brief, Block F (active);** `domain/enterprise/models/service_plan.py` (`SetHttpContent`), `service_compiler.py` (`_bind_shared_web_content`, `SHARED_PAGE_STORE_RECORD`); `tests/test_service_https_content.py` |
| **R-DHCP-01..08, R-EVT-05/06/07, R-REG-02 — S3 DHCP** | **this brief (active), then** [E6 architecture](../../architecture/enterprise-services.md#server-pt-dhcp-under-the-event-fallback) |
| R-HTTPS-04, R-DNS-04, R-MAIL-07, R-EVT-01..03, R-OBS-05 | **not active.** Their text stays in the [archived brief](../../reference/server-pt/server-pt-services-brief-9973f66.md). R-EVT-01..03 and R-OBS-05 describe observer registration, which the measured fallback forbids in production |

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
| Q1R-5 | Q1 keeps the reviewed 60-operation / 600-second ceiling and its 10-operation reserve. Optional M-DNS-1/2 are omitted explicitly as optional measurements without a reviewed probe, not as a budget refusal, and M-DNS-3 is not repeated (Q1R-5.1 records its declared omission and its accounting). | Stage-definition test pins the new worst case; a coordinator run at the ceiling with every extra poll forced refuses nothing and never borrows the reserve. |
| Q1R-6 | Restoration keeps comparing semantic devices and links; the record states that scope and names a changed backend-managed count instead of implying whole-workspace equality. | Finalization test with a retained backend-managed device: CLEAN in scope, limitation present, raw reads unchanged. |

### Planned worst case

| Phase | Step | Operations |
| --- | --- | --- |
| admission | executable build, workspace baseline | 2 |
| setup | 4 fixture devices at 2 each, 3 links at 2 each, fixture identity | 15 |
| setup | E5 endpoints, E6 enable HTTP and HTTPS | 2 |
| experiment | M-HTTPS-1: write H, read both, write S, read both | 4 |
| experiment | M-HTTPS-2: the bounded readiness gate (4), marker page, HTTP positive (4), HTTP off, HTTPS positive (4), HTTP negative (4), HTTPS off, HTTPS negative (4) | 23 |
| finalization reserve | 4 device removals at 2 each, 2 restoration reads | 10 |
| | **planned worst case** | **56** |

A failed positive spends one readiness read instead of the steps it stops, so
every early exit costs less than the complete path. Block C drops M-DNS-3's
operation and adds no reconciliation read; Block F's readiness gate then takes
up to four reads instead of one, so the figure the stage definition computes is
56 and four operations of slack remain. They are not a retry entitlement.

## Block C — review correction delta on `6e78e74` (risk L)

Review disposition **REQUIRES_CHANGES**, not a rejection of the E6 architecture.
This block corrects six originating boundaries on the candidate lineage; every
preserved contract above stays as it is, and the archived Q batch, the
historical records and the `0850de3` attributions are untouched. Risk stays
**L**: the delta affects secret handling, effect admission and evidence.

### Requirements and acceptance

| ID | Requirement | Component | Acceptance |
| --- | --- | --- | --- |
| S2-12 (R-SEC-01) | One invocation-local sanitization boundary carries every outbound runtime string: verification causes, mutation diagnostics, batch-wide details, observed snapshots, limitations and messages. Redaction runs **before** whitespace folding and truncation, over exactly the values this invocation resolved. A script that carries a resolved value never returns arbitrary external text: its caught engine error becomes one of a closed category vocabulary instead of a cropped message. | `infrastructure/execution/secret_resolver.py` (`EvidenceSanitizer`), `transport_outcome.py` (`detail_text`/`bound_detail`), `enterprise_service_runtime.py` (`_safe`, `__ec`) | Real runtime → applicator → JSON/store with explicit test-bound capabilities and a synthetic credential: a correlated verification ENGINE_ERROR carrying the value is safe; raw, JSON-escaped and URL-encoded forms stay safe on mutation and on verification; repeated whitespace and a value crossing the truncation bound leak no material; a value resolved by an earlier batch of the same invocation does not escape in a later verification error; cause category, stage, TD-12 snapshot and the send's original uncertainty survive; safe diagnostics, `secret_unresolved` admission and the no-file-fallback refusal are unchanged. |
| S2-02.1 (R-MAIL-02, R-SEC-05) | Account existence has four distinct outcomes, not two: `absent` (null), `present` (non-null, `getUser()` equal), `mismatch` (non-null, `getUser()` different) and an unobserved pre-read. Only `absent` authorizes `addUser`. A mismatch is a correlated refusal (`account_identity_mismatch`, decision row 21) that repairs, overwrites and calls nothing. | `enterprise_service_runtime.py` (`_account_lines`, `_allowed_skips`, `_row_invalid_check`) | Generated script over the Node engine with null, matching object, mismatched non-null object and a throwing getter. Mismatch and error: zero `addUser` calls and independently inspected account state unchanged. The matching no-op and the genuine absence/creation positives keep their rows. |
| S2-05.1 (R-MAIL-04, R-EVT-06/07) | The send's prerequisite is the **absence of an own key** on the claim object. A present key whose value is not a readable claim (`op_id` and `nonce` strings) is unknown ownership: no send, no overwrite, no adoption, no reset (`subject_claim_unreadable`, decision row 21). A readable claim keeps the own-replay/foreign distinction. | `enterprise_service_runtime.py` (`_send_lines`, `_allowed_skips`) | Repeated invocations of the generated script over the persistent Node engine: valid own claim, valid foreign claim and each of `null`, `false`, `0`, `""` under the key. Every present inadmissible entry: zero sends and a byte-equivalent held claim. One send for a genuinely missing key, and no retry after a lost answer. |
| S2-06.1 (R-MAIL-04 supporting) | A mailbox scan row is used only when its counters are coherent with the bounded scanner that produced them: non-negative counts, `scanned == min(count, MAILBOX_SCAN_LIMIT)`, `matches + mismatched <= scanned`, `truncated == (count > scanned)`, and all counters at their defaults when the recipient account was not found. An incoherent payload is MALFORMED (`mailbox_scan_incoherent:<relation>`) and establishes neither presence nor absence. | `enterprise_service_runtime.py` (`_mailbox_scan_incoherence`, `_verify_smtp_delivered`) | The real reader over controlled payloads and over its normal generated-script path: zero scanned with a match, negative counters, a count over the bound, conflicting truncation, missing fields, a valid match inside a truncated scan and valid no-match results. `supporting_evidence_only`, the absent POP3 claim, unrelated-message privacy and the send's original uncertainty are unchanged, and no new field-format claim is made. |
| Q1R-7 | The page procedure separates three cases: no mutation attempted, an attempted effect reconciled by a complete read of both handles, and an attempted effect that remains unresolved. Only the third sets `outcome_unknown`, which stops every further experimental effect and leaves only the owned finalization. A setter return, a caught exception and an inconclusive table conclusion are none of them a reconciliation. The first causal error is preserved and no write is retried. | `service_qualification_evidence.py` (`assess_page_tables`), `qualify_server_services.py` | Generated probe, pure assessor and coordinator: a baseline read failure runs no setter and attributes no unknown effect; a page change followed by a throwing setter admits no later page setter, listener toggle, fetch or unrelated experimental effect; a lost or unreadable necessary read after an attempted write stops conservatively while a loss before any effect does not; the ordinary shared and separate models still complete; finalization, record persistence, ownership and budget limits are unchanged. |
| Q1R-5.1 | The repaired Q1 stage does not repeat M-DNS-3. It is declared OMITTED with the reason naming the `0850de3` sample that already measured it, and the stage's accounting drops its operation. Nothing relabels that sample as new support, and the reviewed probe and rule stay available for a future authorized measurement. | `service_qualification.py` (`_q1`), `qualify_server_services.py` (`_q1`), `docs/qa/server-services-qualification.md` | The stage-definition test pins the worst case at 56 of 60 with the 10-operation reserve intact; a coordinator run records M-DNS-3 as OMITTED with its reason and dispatches no resolver read. |

### Invariants added by this block

6. No outbound runtime string is folded or truncated before it is redacted, and
   no script holding a resolved value returns arbitrary external text.
7. An effect is admitted only by positive evidence of the documented
   precondition. Inconsistent identity, an unreadable claim and a malformed
   observation are unknown, never absence.
8. An experimental effect whose outcome is unresolved ends the experimental
   phase; only the owned finalization and persistence continue.

## Block D — S3 DHCP design delta (risk L)

Risk is **L**: this block changes addressing authority, shared E5/E6
orchestration, execute-once effects, evidence and persistence. It extends the
existing `pt_apply_enterprise_services` flow and its fixed four-argument MCP
surface. There is no second executor, alternate DHCP tool, public capability
override or LIVE claim.

### C0 prerequisite

`_background_http_release` currently crops arbitrary `deleteClient` exception
text inside JavaScript before `_finalize_client` redacts it. A value spanning
that crop can therefore leave a credential fragment. Once an invocation has
resolved any credential, every generated adapter error emitter uses the closed
`__ec` category vocabulary before folding or truncation. The owned-client
lifecycle remains one bounded finalization with primary and cleanup facts kept
separate. The causal test executes the real generated release script in the
long-lived Node harness and carries its result through the real runtime and
record serialization; it covers complete, crop-crossing, earlier-batch,
raw/JSON/URL forms and a safe non-secret control.

### Requirements and acceptance

| ID | Requirement | Acceptance |
| --- | --- | --- |
| S3-01 | `ServiceRequirement` adds `dhcp_pool` with `ServerDhcpPoolRequirement(interface="", pool_name="", start_offset=0, max_users=0)`. One derivation runs inside canonical composition, after site, segment and device identities exist and before E5. It preserves DNS and the caller policy, records `delegated_dhcp_segment_ids`, rejects duplicate/conflicting/ambiguous/foreign-segment authority, and suppresses only an implicit IOS default on the delegated segment. E5 records `DHCP_DELEGATED_TO_SERVICE`, emits no IOS pool there and retains `SetEndpointDhcp` with only its access/VLAN prerequisites; E6 refuses a delegated segment that still has an IOS pool. | Real intent-to-plan tests cover separate segment authorities, a same-segment conflict, missing/ambiguous interface, same display names across sites, retained DHCP clients and byte-equivalent router-only semantics. |
| S3-02 | Delegated `SetEndpointDhcp` uses the new `endpoint_dhcp_mode` foundation. It requires a nonfailed/nonuncertain E5 row plus a fresh, manifest-bound `HostPort.isDhcpClientOn() is true`; it never treats APPLIED alone or an address as mode proof. The default catalog leaves this reader UNKNOWN, so only explicitly injected candidate evidence can admit a mutation. | The real E5 verifier and foundation derivation distinguish true mode with no address, false mode, wrong interface, malformed/unreadable output and uncertain dispatch. Ordinary router-served clients keep address foundations. |
| S3-03 | E6 adds `EnableServerDhcp(interface)` and `ConfigureServerDhcpPool(...)`. Domain validation derives or refuses structural defaults; validates IPv4 network/mask/range/capacity without materializing the subnet; excludes server, gateway and static clients as compact ranges; and never invents optional TFTP/WLC values. Generated scripts resolve the exact server interface, use documented getters and setters, bracket before/after state, post-read after a setter throws, preserve unrelated pools/exclusions, leave a matching pool unchanged and refuse missing/unreadable/mismatched identity rather than delete or overwrite it. | Unit validation plus Node state/call-log tests cover matching no-op, create then `getPool`, conflict, getter failure, setter effect-then-throw, missing post-read, unrelated state and partial/unknown footprint. |
| S3-04 | `AcquireDhcpLease` is a client/interface `EXECUTE_ONCE` action. Under a pre-effect claim keyed to that device/interface, it calls documented `dhcpRun(port)` at most once per invocation. Any existing key, including falsey or malformed values, refuses unchanged; own replay never resends; lost or post-effect failure stays sticky and quarantined. Product code never releases, resets or deletes the claim. | Persistent Node harness tests the call log and claim bytes for missing, own, foreign, falsey/malformed, throw-after-effect, lost response and replay cases. |
| S3-05 | Mode, current address/mask/lease-time and intended-pool lease lookup are separate bounded readers. Exact types, interface subject, IP/mask relationships and pool identity are checked. An in-range address or lease-time change is only UNKNOWN `acquisition_unattributed`; a well-observed incompatible address contradicts. A coherent matching lease row supports only `attributed_to_intended_server`; same IP/different valid MAC is `foreign_lease_row`; without qualified M-DHCP-2 termination a no-match is UNKNOWN `lease_table_incomplete`. Scans are capped by declared capacity and an implementation limit, and repeated/unparseable rows never establish completion. | Reader and harness cases cover null/throw/malformed, in/out of range, matching/foreign MAC, repeated rows, bound truncation, unqualified termination and a retained positive row. |
| S3-06 | An additive action field carries verification prerequisites. The existing applicator advances the action DAG once, evaluates only prerequisites whose producers have run, and admits a dependent action only after the named verification is VERIFIED. It detects cycles, makes bounded progress and never redispatches an uncertain action. Every client-side service action for a delegated client depends on that client's `DHCP_LEASE`; server enable/pool actions and independent static-client work do not. | Integration proves the actual dependent runtime call is absent under UNKNOWN/FAILED lease evidence, independent work runs, and a synthetic test-bound VERIFIED lease admits the call without creating a product evidence path. |
| S3-07 | Admission freezes one manifest-directed inventory including the access switch, resolves optional dependency closure before E5, and refuses required ineligible DHCP or unavailable required dependents before the first E5 mutation. Optional DHCP exclusion retains complete rows and cannot reactivate an IOS pool, convert clients to static or admit dependents. The supported path is one site/segment, static Server-PT, wired PC-PT clients and one access-switch path; relay/routed clients receive `DHCP_RELAY_REQUIRED`. Typed policy codes reach the entry unchanged. | Default catalog tests prove zero effects for required UNKNOWN DHCP and complete exclusions for optional work; candidate tests inject records only at existing nonpublic seams. Mixed static DHCP/DNS/HTTP/mail cases keep independent successes. |
| S3-08 | Existing write-ahead records, effect gate and retained-result rules persist authority, exact interfaces, action/expectation identity, observations, claims, limitations and effect scope. Persistence loss blocks the next mode/acquisition mutation while bounded reads and owned cleanup remain allowed. Mode, configuration, acquisition and attribution are distinct additive rows with legacy defaults; retained evidence is never borrowed to replay acquisition. Response rows remain complete and within the existing budget or compilation refuses explicitly. | Store round trips, loss-before-effect, loss-after-effect, retention and 2/20/200/1000-client offline reporting tests; no limit is raised and no row is sampled away. |

### Architecture and vendor contract

The domain owns DHCP authority, pool arithmetic, validation, typed actions and
evidence meanings. Application owns the one canonical derivation, dependency
closure, E5/E6 admission, the stage-aware prerequisite loop and persistence.
Infrastructure alone names Cisco members and emits JavaScript; all data enters
that source through `json.dumps`.

The installed 9.0.1 IpcAPI was inspected locally before implementation. The
candidate uses exactly `getDhcpServerProcessByPortName(string)`,
`isEnable()`/`setEnable(bool)`, `addPool(string)` (void) followed by
`getPool(string)`, the documented pool getters and void setters including
`setNetworkMask(network, mask)`, `addExcludedAddress(start, end)`,
`getExcludedAddressCount/At`, `DhcpClientProcess.dhcpRun(port)` (void),
`getDataOfPort(port).getLeaseTimeStr()`, `HostPort.isDhcpClientOn()`, its
IP/mask/MAC getters, and `DhcpPool.getLeaseAt(index)` with public
`ipAddress`, `macAddress`, `leaseTime` and `port`. The reference documents no
lease count/end condition, no lease-time semantics, no MAC representation
equivalence and no serving effect for the setter sequence; those remain
M-DHCP-1/2/4/6 and every corresponding capability remains UNKNOWN.

### Invariants

9. Exactly one policy derivation precedes E5; no display-name guess creates a
   semantic identity, and delegation never disables a real DHCP server.
10. DHCP mode, acquisition, attribution and sole authority are different
    claims. No APPLIED row, setter return, digest, timeout or unqualified scan
    promotes one into another.
11. `dhcpRun` is called at most once under a subject claim; no cleanup path
    deletes that claim and no read is a retry entitlement.
12. Dependent client effects require VERIFIED `DHCP_LEASE`; mode or an
    intended-pool row is insufficient. Independent static work remains live.
13. Default product capability stays UNKNOWN/UNMEASURED. Offline Node and
    integration tests prove code paths, never Packet Tracer support.

## Block E — S3 audit correction and bounded qualification campaign (risk L)

Risk remains **L** because the correction changes effect admission, evidence
classification, native-loop bounds and LIVE qualification. The binding work
order is campaign `SERVER-PT-D02-Q3-Q1-AUTOFIX-01`; it authorizes routine
in-scope autofix, clean fast-forward feature-branch publication and the
enumerated exact-SHA attempts, but it does not accept the product or promote a
capability.

### Problem, outcome and scope

The audited candidate coerces several native DHCP getters with JavaScript
truthiness, admits malformed lease identities and incoherent scan payloads,
and lets exclusion getters drive unbounded native loops. Q3 also remains
declarative, so none of those product claims can be measured through the
governed runner. The outcome is four separately reviewable units: F1, F2, F3,
then executable Q3. Q1 keeps its repaired definition and is run only after Q3
is safely finalized or archived.

The owning files are the DHCP observer/compiler/runtime and their real Node
harnesses, plus the existing qualification model, evidence rules, probes,
coordinator, CLI, record store tests and maintained QA/architecture projection.
No alternate executor, endpoint, transport, `.pts`, extension or public
capability path is introduced.

### Requirements and acceptance

| ID | Requirement | Acceptance |
| --- | --- | --- |
| F1 | Read every new DHCP boolean exactly once and accept it only when `typeof value === "boolean"`. Preserve true, false, missing, invalid and throwing outcomes separately; acquisition requires observed true and cannot write/adopt a claim first. Apply the same rule to Server-PT `isEnable()` reads. | Actual generated observer, acquisition, client read-back and server read-back scripts execute in persistent Node for true, false, numeric/string/null/undefined and throw cases. Invalid values cause no `dhcpRun`, no claim change and no satisfied mode foundation; true and false remain positive and real-negative controls. |
| F2 | Validate the client subject, usable IPv4/mask, measured MAC text, intended pool identity, finite lease-time fields and coherent scan metadata before attribution. Carry the compiled lease window and compact exclusions into both client expectations. Preserve a valid positive prefix alongside a later scan limitation, give a fresh valid same-IP/different-MAC contradiction precedence, and reject oversize/malformed rows. Address compatibility means membership in the intended non-excluded allocation, not merely the subnet. | Generated-script and runtime-to-result tests cover valid/no-match, unset and malformed identities, conflicting rows, oversize payloads, same-subnet outside-window, excluded address, null/throw/repeat/end, matching-prefix-then-error, and truncated scans with and without a match. The real applicator/store retain acquisition uncertainty and no capability changes. |
| F3 | Both mutation bracketing and direct Server-PT state reads enforce one internal finite exclusion ceiling of 4096 rows, validating a finite nonnegative integer count before any iteration. A refused pre-read performs no setter; a failed/oversize post-read preserves outcome uncertainty. Payload validation is conditional on error and subject state so correlated errors stay `ENGINE_ERROR`, coherent missing subjects retain their category, and impossible success payloads stay `MALFORMED`. | Real Node tests cover negative, fractional, nonfinite, boundary and oversized counts, before/after getter failures, no setters after refused pre-read, uncertain post-effect state, and retained missing-subject/engine-error categories. Infinity is refused by a finite stub without looping. |
| Q3-1 | Make Q3 executable with only `__MCP_E6Q_SRV`, `__MCP_E6Q_PC1`, `__MCP_E6Q_PC2` and `__MCP_E6Q_SW`, exact ports/links, TEST-NET-1 addressing, pool `MCP_E6Q_DHCP`, one usable lease (`192.0.2.100`) and private recorded candidate capabilities. Q2 remains declarative and the public catalog remains UNKNOWN/UNMEASURED. | Contract and CLI tests pin the exact fixture, fixed file channel, stage admission and absence of public promotion. The runner refuses before contact on authorization, identity, fixture or budget mismatch. |
| Q3-2 | Use the real service compiler, E5/E6 runtimes and application-owned scheduling for configuration, mode bootstrap, one acquisition per client, read-back and the declared same-action guard control. Native-only probes establish only their named facts. M-DHCP-3 uses at most four owned registrations and never becomes a product observer. | Offline CLI/coordinator tests drive the real generated scripts and product components for setup, expected-negative/inconclusive/contradicted outcomes, duplicate guard, persistence failure, exception cleanup and record round trip. No reset, release, pool removal or hidden backend action exists. |
| Q3-3 | Keep Q3 at 60 operations / 1200 seconds. The worst case is 17 admission/fixture operations, at most 32 required application/measurement operations and an untouchable 11-operation finalization reserve (run-bag release, four owned removals and two restoration reads). Reserve 180 seconds for finalization. | Definition tests prove `17 + 32 + 11 = 60`, every shared procedure is counted once, optional unobservable work is explicitly recorded, and calls after a stop can only be finalization. |
| CAMPAIGN | Each LIVE attempt is a clean published descendant of `d02ddac`, exact-SHA/tree/build/channel authorized, CI-green, isolated from pytest, and run in a freshly owned disposable Packet Tracer process. Q3-file has at most three attempts; repaired-Q1-file then has at most two. | Immutable authorization/record/stdout/stderr/exit-code hashes, append-only correction ledger, process identity and mailbox disposition, two restoration reads where observable, and final `READY_FOR_REVIEW` indexing. A blocker or inconclusive row remains truthful evidence, never a forced green result. |

### Architecture and invariants

Boolean and count validation stay at the JavaScript/native boundary; Python
classifies only typed payloads. Allocation semantics stay in the compiler and
are copied into expectations rather than recomputed from observations. The
qualification domain owns definitions and pure conclusions, probes own only
bounded Cisco calls, the coordinator owns ordering/budget/stop/finalization,
and the CLI only composes existing production boundaries.

14. Invalid native truthy/falsy values never become booleans and never admit an
    effect. Getter exceptions are observations, not default false values.
15. A matching lease row, completed scan, acquisition in this run and sole
    authority remain separate claims. One does not imply another.
16. No native count controls a loop until it passes the internal finite bound;
    incomplete post-effect state is UNKNOWN, never a clean/no-residue claim.
17. Q3 candidate authority is private to its record. It cannot mutate the
    product catalog, survive a new process, or authorize a retry after an
    uncertain effect.
18. Historical records are immutable. Every corrected attempt gets a new SHA,
    run id, nonce, process identity and authorization; failed evidence remains
    indexed beside any successor.

## Block F — amendment 01: coexistence, readiness and S1b (risk L)

Risk stays **L**: this block changes effect admission, adds a precondition
before network attempts, removes a measurement from an executable LIVE profile,
and gives the product a new content contract. The binding authority is
amendment `SERVER-PT-D02-Q3-Q1-AUTOFIX-01-AMENDMENT-01` to campaign
`SERVER-PT-D02-Q3-Q1-AUTOFIX-01`. The amendment authorizes exactly these
contract changes, S1b offline, fast-forward publication of this feature branch
for exact-SHA CI, and the two successor attempts in its section 7. It resets no
attempt counter, promotes no capability and accepts nothing.

### What the campaign measured, and its exact scope

Three LIVE records were produced under the original work order and are accepted
only within the scope stated here. The input package is
`SERVER-PT-D02-Q3-Q1-AUTOFIX-01.zip` (127,800 bytes, SHA-256
`1b71018a…dfa2f`), whose 80 files total 318,993 bytes. The original Windows
before/after filesystem snapshot was not available to the reviewer and is not
claimed to have been reproduced.

| Record | Hash | Accepted scope |
| --- | --- | --- |
| Q3 ordinal 1, `71fc1aa`, run `2026-09-19T21-55-45Z-1efec675` | `c3aa5707…4166a6` | process binding absent; the stage stopped before any setter |
| Q3 ordinal 2, `c0307ca`, run `2026-09-19T22-52-28Z-6d12894c` | `b303bd9d…f38d79b` | `DhcpServerMain` resolves; a disabled process and one native pool observed; no product setters and no acquisition |
| Q1 ordinal 1, `c0307ca`, run `2026-09-19T23-00-53Z-b17240ad` | `7f7a4d91…54a54cf` | bidirectional visibility for the existing `index.html` through distinct handles over one shared page store; listener behavior inconclusive |

Q3's MAC and mode rows prove the actual sampled getters, including a `false`
mode and the `0.0.0.0` address and mask. They are not a successful true-mode
bootstrap and not a DHCP acquisition. Q1 never executed the HTTPS positive or
either negative, because its HTTP positive failed first. The down-before and
up-after port readings suggest a readiness problem; they do not establish the
unique cause of the timeout or the exact port state at `go`. Q3 ordinal 1's
process-exit observation stays unconfirmed at its original deadline, and a
later process disappearance does not rewrite that artifact.

### F-Q3-DEFAULT — qualification-only, non-destructive coexistence

**Problem.** The Q3 runner admitted only an empty pool inventory. Stock
Server-PT on build 9.0.1.0858 ships one native pool, so the stage stopped at
admission twice and measured nothing past M-DHCP-1. Removing or rewriting that
pool is forbidden, and relaxing the predicate into "any baseline" would admit
an unknown server state.

**Outcome.** One typed admission policy that admits exactly two baselines on
the disposable fixture, exact build `9.0.1.0858` and the fixed file channel:

- a coherently observed empty inventory under a disabled process, or
- exactly one complete, exact native row under a disabled process:
  `{"name":"serverPool","network":"0.0.0.0","mask":"0.0.0.0","gateway":"0.0.0.0","dns":"0.0.0.0","start":"0.0.0.0","end":"0.0.2.0","max":512}`.

Both require the owned newly created Server-PT by true subject identity, exact
`FastEthernet0`, an actual boolean `enabled=false`, a complete bounded
inventory, no error, no duplicate or extra pool and absence of `MCP_E6Q_DHCP`.
A matching name alone is not authority: every field is compared by value and by
type. Unknown, malformed, incomplete and truncated baselines still refuse
before any effect.

**Scope and exclusions.** `serverPool` is never deleted, renamed, reset,
replaced, per-pool disabled or worked around in the GUI, and its options are
never rewritten. Enabling the DHCP process is process-wide, so the authorized
experiment may also activate the native pool's behavior; this brief does not
describe the default as remaining disabled or inert afterwards, and infers
nothing about harmlessness from its numeric range or zero mask. The public
admission and capability records are unchanged: this policy is private to the
Q3 qualification profile.

**Preservation.** The observed default configuration is snapshotted three
times with bounded reads — before E5 (the admission read itself), after setup,
and before cleanup — and every snapshot is kept in the record with any
difference between them. An unexpected default change, an extra pool, a
conflicting assignment or an unresolved effect stops subsequent experimental
effects. A newly observed default is never learned and whitelisted.

**Intended pool.** Unchanged: `MCP_E6Q_DHCP`, one address `192.0.2.100`,
capacity one, the exact existing fixtures and exclusions. Intended-pool
attribution and the two clients are observed separately. An intended-pool row
is not sole-authority and not same-run acquisition proof; a timeout on client 2
is not pool exhaustion; unknown table termination stays unknown with its
positive prefix preserved; and no qualified end-of-table predicate exists, so
the default lease table is never required or claimed to be empty.

### F-READY — bounded precondition before network attempts

**Problem.** Q1 dispatched its HTTP positive while all six fixture ports read
`port_up=false` and `protocol_up=false`, and read them up afterwards. The stage
had no precondition, and the existing readiness probe coerced native returns
with `!!`, so a non-boolean was indistinguishable from `false`.

**Outcome.** One reusable readiness check — not another transport or executor
— over the exact six fixture ports. It retains raw typed `found`, `linked`,
`port_up`, `protocol_up`, the port and device identity and safe error text, and
keeps missing, invalid and false distinct: a value is a boolean only when
`typeof value === "boolean"`. Network attempts are admitted only from a fresh
complete reading whose required link and protocol booleans are all true. These
fields prove readiness of the measured links; they prove nothing about STP
forwarding, reachability or HTTP success.

**Bounds.** At most four aggregate read attempts and a 30-second monotonic
deadline, capped by the stage's unspent time and its finalization reserve,
stopping at the first complete ready sample. No unconditional sleep, no busy
loop and no extended fetch deadline. The read count, elapsed time, first and
last observations and the precise failure reason are recorded. No background
client and no requested DHCP acquisition is created or dispatched before the
gate passes.

**Per stage.** Q1 gates before its initial positive and keeps the same-mode
positive prerequisites, the owned-client release and the immediate
contradiction stop; a failure to become ready is a readiness result, never
evidence that HTTP or HTTPS is broken, and a started fetch is never retried
inside one experiment. Q3 gates the physical path before activating DHCP
clients and keeps that distinct from the clients' addressing. A topology change
forces a recheck; no topology change is invented to obtain `up`.

### F-Q3-SAFETY — fix the active path, defer unsafe event probing

Neither LIVE Q3 record reached the code after the old baseline gate, so those
stops qualify none of it.

**A. Classify E5 before E6.** `_run_q3` now classifies the complete E5
configuration result and the derived foundational statuses before any E6 server
mutation, reusing the domain's mutation and contradiction semantics rather than
a new subset of raw-field tests. Missing rows, unknown dispatch or results,
exceptions and contradictory foundations grant no permission. The same rule
applies before the intentional same-claim guard control, which is now also
blocked by a contradicted product verification, not only by an unknown effect.
Stage stop rules never weaken product semantics for independent work elsewhere,
and primary and cleanup causes stay separate. Persistence already closes the
effect gate through `OperationLedger.close_effects` from `_Run.transition`; that
protection is retained and covered by a regression. The old code is not accused
of dispatching after a failed record write merely because control flow reached
another wrapper.

**B. M-DHCP-3 is OMITTED / NOT_EVALUATED** in the amended Q3 profile, reason
`qualification_event_source_and_release_not_qualified`. It is not marked
supported and it is not silently removed. No private DHCP event registration or
unregistration executes in the remaining Q3 slot, and a regression proves the
amended profile registers zero observers. Its measured operation allowance is
reallocated to readiness and native-default preservation, never to extra
acquisitions. The stage definition, the executable path, the recorded
capability scope and the budget tests change together, and R-EVT-05 production
gating is unchanged.

The reason is bounded and specific. `register_dhcp_observers` subscribes on
`d.getPort(...)`, while Cisco documents `dhcpSucceed`/`dhcpFailed` on
`DhcpClientProcess`; the Node stub emits them as `HostPort`, which masks the
mismatch. `_q3_event_assessment` also called detachment *observed* from an
unregister attempt that merely did not throw, and `_q3_record_observer_releases`
then omitted that unresolved resource — an attempt is not observed detachment.
Those two classifiers are removed rather than left unreachable and wrong; the
probes stay, documented as unqualified, until a separately reviewed event
change fixes source identity, correlation and release evidence. No new event
framework is built here.

**C. No rebuilt plans.** Server mutations are not repeated to reconstruct a
plan setup already applied. The real coordinator and applicator stages and
their established results are reused where their contracts permit; no
fabricated VERIFIED row is injected and no copied probe replaces the product
runtime. Native primitive samples stay distinguishable from integrated product
evidence, and any setup uncertainty blocks the next effect.

### F-S1B — the measured shared-content branch, offline

Q1 ordinal 1 measured distinct `HttpServer` and `HttpsServer` process objects
over **one shared page store** for the existing `index.html` on Server-PT,
build 9.0.1.0858, file channel, at `c0307ca`. S1b therefore implements
`shared_content`, not an invented independent HTTPS page store. The sample
demonstrates neither arbitrary page creation nor protocol isolation. The
repaired Q1 is not a prerequisite for this offline block.

- E6 and its current content writer are reused. One content payload and one
  marker are bound to the canonical server page, and the action carries only
  the metadata that shared ownership and its source record need:
  `shared_service_ids` and `content_source_record` on `SetHttpContent`.
- HTTP and HTTPS requirements for one shared page must agree. Incompatible
  content is a compile **error** with zero effects — it refuses before E5
  rather than resolving last-writer-wins — and the runtime is not touched
  while the conflict is discovered.
- HTTPS-only content setup writes through `HttpsServer` and never requires
  enabling the HTTP listener. When both protocols are required on one host,
  the single surviving action is owned by the HTTP service and depends on both
  enables, so the large payload is never duplicated in two actions or two
  record rows purely for representation.
- Pre/post reads, effect footprints, the exact client HTTPS mode and per-client
  rows are preserved. The MCP surface keeps its four arguments. Capabilities
  resolve on the actual model and operation. `SET_HTTP_CONTENT` is an existing
  replay family, so no new replay registration is added.
- Default application and verification support stays UNKNOWN/UNMEASURED, and
  probe metadata never sets behavioral readiness READY. A Q1 run at a commit
  that also contains S1b is still not Q1b if it exercises only the probe path;
  no promotion is authorized here.

### Requirements and acceptance

| ID | Requirement | Acceptance |
| --- | --- | --- |
| F1 (amd) | A typed Q3 baseline admission policy admits the coherently observed empty disabled process and the one exact observed native `serverPool` row, and refuses everything else before any effect. | Domain tests admit the real native fixture and the empty control; arbitrary `DEFAULT`, a changed field, an enabled process, an extra or duplicate pool, a foreign subject, malformed types and a truncated inventory all refuse. CLI and coordinator runs prove no setter is dispatched on a refusal. |
| F2 (amd) | The observed default is snapshotted before E5, after setup and before cleanup, and every snapshot and difference is preserved. A changed default stops later experimental effects. | Coordinator tests read the three snapshots out of the record, prove an equal-snapshot run proceeds, and prove a mutated default stops before the next effect with the difference recorded. The default configuration is unchanged in the engine after the run. |
| F3 (amd) | Readiness is a bounded reusable gate: at most four aggregate reads, a 30-second monotonic deadline capped by unspent stage time and the reserve, first-complete-ready wins, raw typed booleans, recorded read count, elapsed time, first and last samples and a precise failure reason. | Real coordinator and generated-probe tests cover initially ready, delayed up, persistently down, a wrong or missing port, a non-boolean return, late budget exhaustion and persistence failure. A failed gate produces no fetch, no created client and no `dhcpRun`, and finalization still runs. |
| F4 (amd) | The amended Q3 profile registers zero DHCP observers, records M-DHCP-3 as OMITTED / NOT_EVALUATED with its reason, and drops `engine.dhcp_event_delivery` from the recorded experimental scope. | A regression asserts zero `registerEvent` dispatches in a full Q3 run, the omitted measurement row and its reason, and the recorded capability list. |
| F5 (amd) | E5 and its derived foundations are classified before any E6 server mutation, and a contradicted product verification blocks the same-claim guard control. | Coordinator tests with an unaccepted E5 batch and with an unverifiable foundation prove no E6 server dispatch; a contradicted read-back proves the guard is not dispatched. The persistence gate regression proves no effect follows a failed record write. |
| F6 (amd) | Q3 stays 60/1200 with at least its 11-operation and 180-second finalization reserve; Q1 stays 60/600 with at least 10/120, and readiness is charged to the trace, not to unlogged preparation. | Definition tests pin Q3 at 17 + 32 + 11 = 60 and Q1 at 19 + 27 + 10 = 56, prove each shared procedure is counted once, and prove a stage whose worst case exceeds its ceiling refuses before contact. |
| F7 (S1b) | The compiler binds one shared content payload per host page, owned by HTTP when present and by HTTPS otherwise, exposes `shared_service_ids` and `content_source_record`, and refuses incompatible content as an error with zero effects. | Compiler tests cover the same payload through both protocols, the conflicting payload refusal, HTTPS-only with HTTP off, absence of a duplicate content mutation, and the unchanged existing HTTP-only path. Use-case tests prove a conflicting plan applies nothing. |
| F8 (S1b) | Both protocols' verification expectations resolve the shared marker, the runtime writes it through the owning process only, and no capability or readiness is promoted. | Runtime and expectation tests cover the fresh marker, the exact client HTTPS mode, the no-marker negative, optional-service coexistence, record round trip, and unknown-build or unknown-capability refusal. Catalog tests keep application and verification support UNKNOWN/UNMEASURED and readiness not READY. |

### Invariants added by this block

19. A qualification baseline is admitted only by exact typed value equality
    against a reviewed named shape. A matching pool name, a plausible range or
    a zero mask grants nothing.
20. An observed native default is preserved, never removed, rewritten or
    learned. Enabling a process is process-wide and is recorded as such.
21. Readiness is a property of the measured links at the moment it was read.
    It never implies forwarding, reachability or a successful request, and a
    failure to become ready is a readiness result, not a service verdict.
22. A native boolean exists only when the engine returned `typeof "boolean"`.
    Coercion never manufactures one, so missing, invalid and false stay
    distinct at the boundary and in the record.
23. An unregister attempt that did not throw is not observed detachment. A
    measurement whose release evidence is unqualified is OMITTED with its
    reason, never silently skipped and never SUPPORTED.
24. One page store means one content action. Two protocols that disagree about
    the same page are a compile error before any effect, never a resolved
    conflict and never a second write.

## Block G — focused closure addendum at `243ddc8` (risk L)

Review disposition on `243ddc8` (tree `f16efe8`) is
**REQUIRES_CHANGES**. This block closes four integration and uncertainty
boundaries in the already-approved amendment; it does not introduce another
service subsystem, transport, protocol, scheduler, public tool argument,
capability promotion or campaign. The maintained Block F design and its
measured shared-page/default-pool facts remain authoritative wherever this
delta does not replace a narrower decision.

### Problem and intended outcome

The compiled shared page action records every owning service, but product
admission and execution projection still use only its single writer
`service_id`. Optional exclusion can therefore leave a retained service with a
dependency on an excluded listener, or remove the only page writer. The
readiness loop also lets a fixed ten-second probe finish after its local
thirty-second deadline, and Q3 first activates DHCP mode in E5 before it checks
the link precondition. Later native-default snapshots accept incomplete or
malformed readings as observations. Finally, Q3's continuation guard ignores
some canonical unresolved mutation rows and the product phase schedules the
server setup setters a second time.

The outcome is one provenance-aware admitted projection for shared content,
one deadline-enforcing readiness gate before the first protected activation,
one strict reusable default-snapshot classifier, and one exact staged-result
reuse boundary that executes every setup mutation once while preserving its
original typed result.

### Requirements and acceptance

| ID | Requirement | Acceptance |
| --- | --- | --- |
| F1-close | Shared-content admission evaluates the binding recorded in `shared_service_ids`, not only the selected writer key. The selected execution projection keeps one compatible content action, chooses a writer among admitted HTTP/HTTPS services whose exact writer operation is supported, rewrites only dependencies owned by excluded sharing services, and preserves the source plan id/hash plus explicit selected service/action identities. If no admitted writer has the exact required capability, admission refuses before E5. | Required HTTP plus optional unknown HTTPS executes HTTP with one writer and no dangling HTTPS dependency; admitted HTTPS plus excluded optional HTTP either writes through HTTPS or refuses before effects; both admitted execute one write and retain both service markers; incompatible stated content still refuses with zero E5/E6 effects; HTTPS-only never enables HTTP; a supported unrelated service key cannot authorize an unknown writer; outcome rows, retained rows and the stored record preserve the binding. |
| F2-close | `_await_readiness` computes a timeout for every read as the minimum of the probe's normal timeout, the local deadline remainder and the stage allowance outside finalization reserve. A read that returns after the local deadline is retained as a late observation but cannot establish readiness. Q3 runs this gate after typed baseline admission and before its first `SetEndpointDhcp`; the same sample may protect later DHCP work only while the fixture topology relevant to it is unchanged. | Initially ready, delayed ready, persistent down and late completion are driven through the real coordinator with an injected clock/transport; the late call receives a reduced timeout and grants no permission; the gate stays within four reads and thirty seconds without reserve borrowing or unconditional sleep; unready Q3 makes zero `SetEndpointDhcp`, `dhcpRun` and background-client calls, while finalization still runs. |
| F3-close | Every post-setup and pre-cleanup default snapshot passes the same subject/interface, process, typed inventory, error, truncation, cardinality, unique-name and typed-pool validation as the admitted baseline. The intended new pool is accounted for separately and excluded from the immutable-default comparison only after its row is valid. Raw bounded facts and the original unobserved cause are preserved. | Complete equal snapshots establish preservation; a changed field establishes a change; extra/duplicate pools, wrong subject, count mismatch, malformed rows/fields, truncation and an error after a valid prefix are unobserved snapshots with their original cause. Unknown and changed both stop later experimental effects but remain distinct in the record; an affordable final snapshot is retained after a stop; legacy archive bytes do not change. |
| F4-close | Q3 classifies the exact full governed E5/E6 result identities and the canonical decided rows before any subsequent effect. Missing or duplicate rows, unresolved effect, runtime exception and contradicted verification stop. Server setup is applied once through the real `ServiceApplicator`; a later full-plan call may reuse only exact original action rows whose retained input snapshot reproduces the same canonical decision and whose plan/action identity matches. Reuse never fabricates a new dispatch, accepted envelope or verified observation; full-plan read-only verification may run fresh. | An acknowledgement lost with `attempted=None`, a missing/duplicate row and a contradicted read-back all block the guard and subsequent effects; native setter call logs prove one setup call across both phases; the same-claim negative runs only after every prerequisite is established; record/store roundtrip preserves the original mutation inputs, decisions, uncertainty and journal; budget arithmetic counts actual calls and not retained rows. |

### Architecture and affected contracts

- `apply_enterprise_services` owns admitted-plan projection. The compiler's
  `SetHttpContent.shared_service_ids` and source record are the provenance; the
  projection does not infer sharing from host names, service type alone or a
  missing dependency. Capability resolution is performed on each candidate
  writer action, and only the selected execution copy is rebound. The compiled
  plan identity remains the source identity; selected service and action ids
  are persisted separately so the executed subset is not mistaken for the
  source plan.
- `PacketTracerQualificationProbes` continues to own the normal per-read
  timeout. Its readiness methods accept a smaller caller-provided timeout; the
  coordinator owns local-deadline and stage-reserve arithmetic and rejects a
  sample completed after expiry.
- `service_qualification_evidence` owns one strict snapshot classifier shared
  by the admission and later snapshots. A valid intended-pool row is presence
  evidence, not part of the immutable default. A malformed intended row makes
  the whole snapshot unobserved rather than disappearing from comparison.
- `ServiceApplicator` owns retained E6 action admission. It accepts only
  exact, unique plan rows with retained `received_mutation`; rerunning the
  canonical `decide_mutation` over that retained input must reproduce the
  stored decision outputs. Invalid retention fails before runtime inventory or
  effects. Q3 setup uses an exact server-only projection through this
  applicator and the product phase reuses those rows in the full plan.

### Invariants added by this block

25. Shared-resource provenance can broaden ownership, never capability. One
    service's supported key cannot authorize another process as the writer.
26. A ready sample authorizes nothing after its local deadline, even when the
    underlying transport returns a correlated body.
27. A positive prefix in a bounded inventory remains evidence of those rows,
    but it never proves complete preservation after an error, truncation or
    incoherent cardinality.
28. A retained result is the original decided row, not a synthetic success and
    not permission to redispatch. Exact plan/action identity and canonical
    input/output agreement are prerequisites to reuse.
29. Q3 calls each native setup setter at most once across setup and product
    phases; read-only verification and protected finalization are not setters.

### Test design and budget

Behavioral changes use causal RED first through existing real boundaries:
`test_apply_enterprise_services.py` and `test_service_https_content.py` for the
admitted shared projection; `test_service_qualification_coordinator.py` plus
the generated probe harness for deadlines and ordering;
`test_service_qualification_contracts.py` for strict snapshots; and the real
applicator/coordinator/store harnesses for retained results and native setter
call counts. Focused runs precede affected/coexistence and the full suite.
Documentation, namespace, whitespace and the clean exact-commit delivery gate
remain mandatory. Q3's recalculated worst case is 59 operations within its
60 / 1200 ceiling: 17 fixture/admission + 31 measurement/application + 11
reserved; the spare operation is not a retry entitlement. Q1 remains 60 / 600
with at least 10 / 120 reserved. Cached rows cost no bridge call, while every
fresh verification, readiness read and finalization call is counted. Packet
Tracer contact remains conditional on clean publication and exact-successor-SHA
CI.

### Focused closure implementation evidence

Observed offline in `Cisco-MCP-s3` from reviewed candidate `243ddc8` (tree
`f16efe8`). The executable closure head is `35cbc7c30a504330d663619e36bcd26a0104ab37`
(tree `b534a2c392f5581c80fbf6cc0821cd11603adce6`). The branch remains local at
this point; exact clean delivery, feature publication and successor-SHA CI are
the next gates. No Packet Tracer process was opened, no LIVE attempt was used
and no capability was promoted.

| Commit | Scope |
| --- | --- |
| `b297913` | this Block G design delta, recorded before behavior edits |
| `3a08de8` | F2 through F4: hard readiness deadline/order, strict snapshots, complete result classification and exact retained setup rows |
| `35cbc7c` | F1: admitted shared writer projection plus persisted source/selected binding identity |

The closure results are deliberately narrow. F1 keeps one page writer and one
write after optional exclusion, rebinds to an eligible HTTPS writer without an
HTTP enable, and refuses when no exact writer operation is supported. F2 caps
each read and places Q3 readiness before `SetEndpointDhcp`. F3 preserves raw
later readings but grants preservation only to complete typed inventories. F4
runs setup setters once, retains their original decided rows and refuses the
same-claim guard when the full product result remains unresolved. The nominal
offline Q3 simulation therefore terminates honestly as
`outcome_unknown:q3_product_service`; it is not relabelled successful to keep
the older guard trace.

| Verification | Result at the executable closure head |
| --- | --- |
| focused runner | 318 passed |
| runner plus DHCP affected | 542 passed |
| shared-content affected | 385 passed |
| combined affected/coexistence | 763 passed |
| full offline suite | 6544 passed, 3 skipped, 3 pre-existing warnings |
| namespace inventory | 0 active imports, 0 active strings, 0 unreviewed inert mentions |
| documentation | built; only the two pre-existing `handoff.md` link warnings |
| whitespace | clean |

Q3 now plans `17 + 31 + 11 = 59` operations inside the unchanged 60 / 1200
ceiling; one spare operation is not a retry entitlement. Q1 remains
`19 + 27 + 10 = 56` inside 60 / 600. Campaign ledger entry 5 archives the
focused review addendum at 14,426 bytes, SHA-256
`4a5f96a18671101b743385c78224bb444becb8d3977310c4a0e3d7b21f5442a5`,
linked to entry 4 without replacing the original package or any prior record.

## Block H — A02 evidence closure and diagnostic preparation (risk L)

Review disposition on `a02c1e0` (tree `fdec9ee`) names one demonstrated
evidence-persistence defect and asks for two prepared diagnostics. This block
closes the defect, corrects two projection statements that the delivered
records contradict, preserves the closed campaign, and records two proposed
measurement profiles that nothing here authorizes to dispatch. It introduces no
new transport, bridge endpoint, executor, `.pts`, capability promotion or
attempt counter, and it resets nothing.

Risk stays **L**: the change touches durable run evidence and the qualification
execution path.

### Problem and intended outcome

`_q3_snapshot_default` appended each bounded native-default reading to
`_Execution.default_pool_snapshots`, an in-memory list. That list reached the
record only when a later `conclude()` projected it into a measurement's facts.
On the stopped Q3 branch the final reading is taken *after* the last
`conclude()` and after `finish("Q3_SETUP")`, so it reached nothing durable.
The delivered Q3 record `q3-2026-09-20T03-27-46Z-51ff55e7` proves the loss: its
ledger counts operation 32 as an accepted, correlated `dispatch_and_wait`, its
`purpose` is empty because `finish()` had already cleared the ledger label, and
the pool values it returned are not recoverable from the record. The same
record's M-DHCP-1 row carries the limitation
`native_default_pool_coexists_and_is_never_modified` beside its own cause
`q3_native_default_changed:default_pool_changed:serverPool.end`.

The outcome is one authoritative durable sink for every default reading, a
precise operation purpose assigned before dispatch, an explicit
not-observed entry for a reading that could not be afforded or performed, and
prose that distinguishes *no explicit setter targeted the native default* from
*the default's values did not change*.

### Requirements and acceptance

| ID | Requirement | Acceptance |
| --- | --- | --- |
| H1 | Every acquired native-default reading is written to one authoritative sink on the record itself — `QualificationRecord.native_default_pool` — at the moment it is taken, whatever phase the run is in and whether or not it has stopped. Each entry preserves the label, the observed flag, the unobserved cause, the bounded pool rows, the intended-pool presence, the exact raw payload, the differences against the first reading, the purpose dispatched under it and the ledger sequence of the counted operation. The measurement projection reads that sink instead of a parallel list. | A real coordinator/store run stops early on a changed default and then returns a third, deliberately different value on the final reading; the reloaded terminal record carries all three observations with their labels, purposes and operation sequences, the third differs from `after_setup`, and the primary cause is unchanged. |
| H2 | The reading is dispatched under `q3:native_default:<label>`, set before the call and never inferred afterwards from an ordinal. A reading the remaining allowance cannot pay for, or that the ledger refuses, is recorded as an explicit unobserved entry with its own cause and no counted operation; no additional bridge operation is added to repair documentation, and the stage budgets are unchanged. | Record purposes contain no empty label for a counted default reading; a ceiling that leaves nothing for the final reading yields `default_pool_snapshot_not_affordable` with `operation_seq` 0 and no extra dispatch; ledger totals stay inside the pinned Q3 worst case of 59. |
| H3 | A failing final reading or a failing record write is additional evidence. It never replaces the first primary failure, never authorizes a new experimental effect, and leaves owned finalization bounded and running. | With the store failing the terminal write, the returned record still holds the three observations, `persist_error` is set, the primary failure is the original default change, and no experimental dispatch follows; with the final reading malformed, errored or unobserved, the entry states the cause and the primary failure is still the original one. |
| H4 | `native_default_pool_coexists_and_is_never_modified` is replaced by `no_explicit_setter_targeted_the_native_default`. The Q1 planned-worst-case projection is corrected from 53 to the 56 the stage definition and its contract test compute, in the brief and in the M-DNS-1/M-DNS-2 omission reasons a future record copies into its own evidence. Historical records, their bytes and their hashes are unchanged, and an external review limitation states that the pre-cleanup payload of the delivered Q3 record is missing and is never reconstructed. | The limitation token appears in a new run's setup row and nowhere claims immutability; the brief's Q1 table sums to 56; the archived campaign files reverify byte-for-byte against their recorded digests. |
| H5 | Two diagnostic profiles, D-DHCP and D-WEB, exist as typed offline records built from the existing runner, product writers, native readers and operation ledger. Each carries its proposed sequence, exact target/effect list, per-step observation contract, budget arithmetic including finalization, its declared seams and a draft authorization whose status is `DRAFT` and whose `granted` flag is false. Dispatch is refused for any profile whose authorization is not an exact-scope granted record. | The profiles are generated from the real Q3 product contract and the installed vendor reference; the refusal function returns a non-empty reason for both drafts and for a granted record whose stage, fixture set, step set, budget or build differs; no stage definition, CLI path or tool registration can reach them. |

### Architecture and affected contracts

- `QualificationRecord` gains `native_default_pool`, a list of
  `DefaultPoolObservation`. It is the single sink; `_Execution` keeps no
  parallel list and `_native_default_facts` projects from the record. Durability
  uses the existing write-ahead machinery: each reading is followed by a
  `native_default:<label>` transition through `QualificationRecordStore`, and
  the terminal `complete()` write carries whatever the last transition did not.
  No new persistence subsystem and no event-sourcing layer is introduced.
- `_q3_default_read` in `qualify_server_services.py` owns the whole reading:
  affordability, purpose, dispatch, classification through the existing
  `default_pool_snapshot` classifier, ledger association and persistence. The
  domain classifier and the difference rule are unchanged.
- `service_diagnostic_profiles.py` is a new pure domain service. It owns the
  two profiles, the plan projections they propose, the seams they declare and
  the fail-closed dispatch gate. It performs no I/O, registers no tool and is
  reachable from no executable stage.

### Invariants added by this block

30. An observation that was performed is durable evidence of the run, not of
    the measurement that happened to be open when it was taken. A stop, a
    concluded procedure and finalization change what may be *done* next; they
    never change what was *seen*.
31. An operation's purpose is decided before its dispatch. A purpose
    reconstructed afterwards from a sequence number is an inference, not a
    record.
32. A reading that could not be afforded or that the ledger refused is
    explicitly not observed. Absent evidence is never repaired by dispatching
    another operation for the sake of the record.
33. A prepared diagnostic is a question, not a contract. Its expected
    transition is the dependent variable; observing it confirms no new product
    invariant and learns no allowlist from it.

### Test design and budget

Causal RED comes first through the real coordinator, the real record store and
the stub engine's own native-state and call log as the oracle:
`tests/test_service_qualification_coordinator.py` for the terminal-evidence
regression, the unaffordable reading, the failing terminal write and the
unchanged success-path trace; `tests/test_service_qualification_cli.py` for
the persisted sink through the real command line; and the new
`tests/test_service_diagnostic_profiles.py` for the two profiles, their
projections against the real Q3 product contract and the refusal gate. The
pinned stage worst cases do not move: Q3 stays `17 + 31 + 11 = 59` inside
60 / 1200 and Q1 stays `19 + 27 + 10 = 56` inside 60 / 600, because this block
adds no bridge operation to either stage.

### D-DHCP — proposed sequence to identify when the native default changes

The dependent variable is the native `serverPool` transition that the delivered
record observed between `before_e5` and `after_setup`: network `192.0.2.0`,
mask `255.255.255.0`, start `192.0.2.0` and end `192.0.3.255`, with the name,
the 512 maximum, the zero gateway and the zero DNS unchanged. The old record
cannot say which operation caused it, because eleven counted operations sit
between the two readings — one client read, three readiness reads, four E5
calls and three E6 calls — and the bracket attributes the transition to none of
them.

| Step | Effect | Targets | Observation retained | Ops |
| --- | --- | --- | --- | --- |
| admission | observe | executable build, workspace baseline | build identity, baseline inventory | 2 |
| fixtures | create | `__MCP_E6Q_SRV`, `__MCP_E6Q_PC1`, `__MCP_E6Q_PC2`, `__MCP_E6Q_SW` and the three links | creation disposition per device and link, fixture identity | 15 |
| D0-a | observe | `DhcpServerMain` on `__MCP_E6Q_SRV/FastEthernet0` | typed baseline admission: disabled boolean process, one exact native row | 1 |
| D0-b | observe | `FastEthernet0` of both PCs | client mode and MAC proving no client is activated | 1 |
| D0-c | observe | the three fixture links | bounded readiness gate, at most four reads in thirty seconds | 4 |
| D1-a | configure | the server's `SetEndpointStaticAddress` only | typed mutation row and its read-back; no `SetEndpointDhcp`, no DHCP setter | 2 |
| D1-b | observe | the same DHCP process | default reading after the server address alone, with differences against D0-a | 1 |
| D2-a | configure | `ConfigureServerDhcpPool` only, process still disabled | typed mutation row and DHCP server-state read-back | 2 |
| D2-b | observe | the same DHCP process | both pools, intended presence, differences against D0-a and D1-b | 1 |
| D3-a | activate | `EnableServerDhcp` — **future explicit authorization only** | typed mutation row; the compiler attaches the server-state read-back to the pool row, so this projection carries none | 1 |
| D3-b | observe | the same DHCP process | enabled boolean and the default reading after the process is enabled | 1 |
| D4 | observe | the same DHCP process | pre-cleanup reading, always attempted, always recorded | 1 |
| finalization | release | run bag, four removals, two restoration reads | release rows, restoration proof | 11 |
| | | | **worst case** | **43** |

Proposed ceiling 60 operations / 900 seconds with the Q3 reserve of 11
operations / 180 seconds. Without D3 the sequence costs 41. The sequence
creates no client acquisition, registers no DHCP event observer, calls no
default-pool setter, removal or reset, and never rewrites the default's values
to restore them. An unknown effect, a wrong subject identity, a malformed or
incomplete inventory or a foreign fixture stops the sequence where it stands.

**Declared seam.** The compiled Q3 service plan makes
`svc/server-dhcp-pool/…` depend on `svc/enable-server-dhcp/…` in both
`depends_on` and `apply_dependencies`, so the existing writer cannot configure
the pool while the process stays disabled. D2 therefore requires one minimal
reviewed extension: a projection that drops the enable action and records that
it rewrote exactly that dependency, declared on the profile and blocking D2
until a reviewer approves it. The alternative — copying `addPool` and the pool
setters into the diagnostic — is refused.

### D-WEB — proposed narrow diagnostic for the client reader

The delivered Q1 record shows four readiness reads ending with all six exact
ports up, both page handles reading the new marker at 53 bytes, and the HTTP
positive returning `unestablished:inconclusive:no_response_within_deadline`
with `client_mode: not_read_back`. The HTTPS positive and both negatives never
ran. That is neither a demonstrated HTTP or HTTPS failure nor evidence that a
longer timeout would change it: the runner's fetch timeout and its polling
interval are both `HTTP_TIMEOUT_SECONDS`, so the bounded poll performs exactly
two inspections, the second at the deadline.

Three alternatives have to be separated: the network path, the listener or the
request, and the polling or the reader.

| Step | Effect | Targets | Observation retained | Ops |
| --- | --- | --- | --- | --- |
| admission | observe | executable build, workspace baseline | build identity, baseline inventory | 2 |
| fixtures | create | the four devices, three links, E5 endpoints, E6 listener enable | creation rows, fixture identity, listener application rows | 17 |
| W0-a | observe | `HttpServer` and `HttpsServer` on `__MCP_E6Q_SRV` | `isEnabled`, `isHttpsEnabled` and `getPortNumber` for each handle, plus the page read-back through both | 1 |
| W0-b | observe | the three fixture links | bounded readiness gate, at most four reads | 4 |
| W1 | configure | the existing `index.html` through both handles | marked page written and read back through both handles | 1 |
| W2-a | request | one owned background client on `__MCP_E6Q_PC1`, HTTP mode | owner device, `isHttps()` mode, content before the request, the selected URL and path, and the `go()` result | 1 |
| W2-b | observe | the same owned client | two timestamped bounded inspections with the remaining operation and time budget of each | 2 |
| W2-c | observe | the same owned client | one late control read after the deadline and before release, timestamped | 1 |
| W2-d | release | the same owned client | found, deleted, present-after and error | 1 |
| W3 | request | a second owned client on `__MCP_E6Q_PC1`, HTTPS mode, same page and marker | the same fields as W2 | 5 |
| W4-a | observe | both listeners | states and port numbers after the attempts | 1 |
| W4-b | observe | the three fixture links | endpoint readiness after the attempts | 1 |
| finalization | release | four removals, two restoration reads | release rows, restoration proof | 10 |
| | | | **worst case** | **47** |

Proposed ceiling 60 operations / 600 seconds with the Q1 reserve of 10
operations / 120 seconds. Every owned client is named, released once and
reported; no client is recreated, no fetch is retried automatically, no
unconditional wait is added, PortFast and forwarding configuration are not
touched, the transport is not switched and no event is registered.

The discriminating comparison is the same fixture, the same page and the same
marker under two client modes. A retrieved HTTPS marker beside an unretrieved
HTTP marker places the boundary at the HTTP listener or request; neither
retrieved, with both listeners enabled on their read-back port numbers and all
six ports up, places it at the network path or at the reader; a late control
read that finds the marker after the deadline places it at the polling window.
A timeout remains a timeout: it is never a negative listener claim, and no TLS
property is asserted.

**Declared seams.** Four existing contracts cannot support this record as
they are, and each step that needs one stays blocked until it is approved.

| Seam | What exists | What is needed | Minimal extension |
| --- | --- | --- | --- |
| `http-client-mode-not-read` | only the HTTPS start reads `isHttps()` | the mode the client held when the request started | read it in the same start evaluation for both modes; no extra operation |
| `poll-discards-intermediate-readings` | only the last reading survives | each inspection with its timestamp and remaining budget | collect the readings the poll already takes; no extra inspection |
| `no-late-control-read` | nothing reads the page after the window closes | one late read that separates late content from no content | one counted read per fetch, budgeted as its fifth operation |
| `listener-port-number-not-read` | the reader reports enable flags only | the actual port number of each handle | add `getPortNumber()` to the same evaluation; no extra operation |

**Vendor reference audit.** Checked against the Extensions API reference
installed with the measured Packet Tracer build, which labels itself 8.1.0.
Documentation is not measurement, and nothing below is a support claim.

| Member | Reference contract | Disposition |
| --- | --- | --- |
| `HttpClient::getOwnerDevice()` | inherited from `Process` | newly read; proves which device owns the client |
| `HttpClient::isHttps()` | returns true for HTTPS mode, false for HTTP | already used by the HTTPS reader; newly read in HTTP mode, which closes `http_client_mode_not_read_back` |
| `HttpClient::go(string)` | creates a request to a URL; returns whether it succeeded | unchanged; success is about the request, never about a response |
| `HttpClient::cancel()` | cancels the request and closes the TCP connection | available; not used, because it discriminates none of the three alternatives |
| `HttpClient::http_get/http_post/http_put/http_delete` | signatures only — no parameter names, semantics or return description | refused; an undocumented signature is never guessed |
| `HttpClient::onStart(string)`, `onDone(string, ip, HttpResponseType, string)` | IPC events; `HttpResponseType` has no page in the installed reference | refused here; the only contract that could separate the network path from the listener needs its own qualification and its own authorization |
| `HttpServer::getPortNumber()` | returns the port number of the HTTP service | newly read for both handles |
| `HttpServer::getUsername()`, `getPassword()` | documented readers | deliberately not read; this order excludes credential work |
| `HttpServer::onRequest(string, TcpConnection)` | IPC event | refused; same reason as `onDone` |
| `HttpsServer::isHttpsEnabled()` | returns whether the HTTPS service is enabled | already read; retained per handle beside `isEnabled` |

**Stated uncertainty.** With documented read-only members alone, the network
path and the listener cannot be separated: only layer-1 and layer-2 readiness
is observable, `onRequest` and `onDone` are unqualified event sources, and
`HttpResponseType` is undocumented in the installed reference. The profile says
so instead of inferring a listener refusal from silence. The measured link
fields stay separate from any forwarding, spanning-tree or reachability claim:
`isPortUp`, `isProtocolUp`, `getLink` and the host address readers are carried
as themselves, and the record repeats what the Q1 sample already names — no
documented STP state reader and an undocumented port light-status enumeration.

### Where the profiles live

`domain/enterprise/services/service_diagnostic_profiles.py` holds both
profiles as typed records, the plan projections D-DHCP would dispatch, the
declared seams, the vendor reference audit and the fail-closed
`diagnostic_dispatch_refusal` gate. It is pure: it performs no I/O, it
registers no tool and no stage definition names either profile.
`tests/test_service_diagnostic_profiles.py` generates the projections from
the real Q3 product contract, so the sequences are the ones the existing
compiler can produce, pins both budget sums including their reserves, and
proves that every scope mismatch refuses on its own.

### Draft authorizations — no granted status

Both drafts are recorded with `status: DRAFT` and `granted: false`. Neither
names an attempt ordinal, because neither belongs to
`SERVER-PT-D02-Q3-Q1-AUTOFIX-01`, whose Q3 3-of-3 and Q1 2-of-2 attempts are
spent and whose counters this block does not touch. Each draft requires, before
any dispatch: an independent reviewer's exact-scope approval naming this
sequence; a clean delivery commit with exact-SHA CI; an operator-confirmed
dedicated Packet Tracer process; the measured build and one fixed channel; and,
for D-DHCP, a separate decision on the declared plan-dependency seam. The
refusal gate is fail-closed: an absent, draft, differently scoped or
differently budgeted authorization refuses, and an unobservable value is
unknown, never permission.

### A02 implementation evidence

Observed offline in `Cisco-MCP-s3` from `a02c1e0894f425f51c26e686e917cb41e59e3745`
(tree `fdec9eeab3a4af4c8decfc70ac60451b746898f1`), whose authoritative base and
merge base is `6263344e31ba3b0de6539d652f2cd06fc73a3562` on the `cisco` remote.
No Packet Tracer process was opened or contacted, no bridge was started, no LIVE
attempt was used and no capability was promoted. This order authorized offline
work only.

| Commit | Scope |
| --- | --- |
| `d97f0ee` | this Block H design delta, recorded before any behavior edit |
| `68ed2e4` | A02-E1: the record is the one sink for every native default reading |
| `4996e55` | the D-DHCP and D-WEB profiles, their projections, seams and gate |
| `a0e8e4b` | the Q1 omission prose corrected to the computed worst case |

#### Causal RED and GREEN

The RED was produced at `d97f0ee` by restoring the two pre-fix source files and
running the new coordinator regression against them. The stub engine's own call
log is the oracle:

```text
ENGINE READS: 3
PERSISTED LABELS: ['before_e5', 'after_setup']
OPERATION 30 PURPOSE: ''
AssertionError: assert ['before_e5', 'after_setup'] == ['before_e5', 'after_setup', 'before_cleanup']
```

That is the delivered LIVE defect reproduced offline: three reads performed, two
persisted, and the counted operation of the third carrying no purpose. Six new
regressions failed at `d97f0ee` and pass at `68ed2e4`, covering the terminal
record, a failing completion write, a failing write of the reading itself, a lost
answer, an incoherent inventory and an unaffordable reading. The success-path
snapshot trace and the semantic restoration controls stayed green throughout.

The measured consequence is narrow and honest. The record now carries each
reading's label, the purpose it was dispatched under, the sequence of the counted
operation, the raw bounded payload and the differences against the run's first
reading. The stage budgets do not move, because the first reading reuses the
typed baseline admission read and the later ones replace reads the stage already
made. A reading nothing could pay for is recorded with `operation_seq` 0 and
`default_pool_snapshot_not_affordable`, and no dispatch follows it.

One case is deliberately not escalated: an unobserved final reading on a run that
has not stopped records its cause in the entry and in the measurement projection
without adding a secondary failure, because there is no primary cause for it to
be additional to.

#### Suites and gates

| Verification | Result |
| --- | --- |
| focused coordinator regression | 64 passed |
| qualification and diagnostics affected | 318 passed |
| combined affected/coexistence | 1310 passed, 1 skipped |
| diagnostic profiles | 34 passed |
| full offline suite | 6582 passed, 3 skipped, 3 pre-existing warnings |
| namespace inventory | 0 active imports, 0 active strings, 0 unreviewed inert mentions |
| documentation | built; only the two pre-existing `handoff.md` link warnings |
| whitespace | clean |
| Ruff gate against `cisco/main` | 86 gated Python files, zero mechanical exemptions |
| clean delivery gate | run on the final commit, with `--delivery-commit HEAD` |
| exact-SHA CI | inspected at the published head, matrix included |

The pinned stage worst cases are unchanged: Q3 `17 + 31 + 11 = 59` inside
60 / 1200 and Q1 `19 + 27 + 10 = 56` inside 60 / 600. The two prepared
diagnostics ask for their own ceilings and neither is granted one: D-DHCP 43 of
60 with an 11-operation reserve, 41 without the activation step, and D-WEB 47 of
60 with a 10-operation reserve.

Campaign ledger entry 6 archives this closure against entry 5. It reverifies the
operator's package byte for byte — 17 files, 90,548 bytes, internal manifest
SHA-256 `317eaf45…4a2902c` — records both delivered attempt records unchanged at
`7e22a2bc…f89636` and `11af4155…2da917`, archives the A02 work order at 11,737
bytes and SHA-256 `f507f3f1…5f3f38`, and states the missing pre-cleanup payload
as an external review limitation. It consumes no attempt: Q3 3 of 3 and Q1 2 of 2
remain spent, and there are zero remaining LIVE attempts.

## Test design

| Level | Scope | Files |
| --- | --- | --- |
| unit (domain) | pairing, ids, hash content, decision rows 21/22, secret value and redaction, Q1 page-table and listener rules | `tests/test_service_mail_compiler.py`, `tests/test_execution_status_facts.py`, `tests/test_service_secrets.py`, `tests/test_service_qualification_contracts.py` |
| harness (generated scripts) | the real mail and Q1 JavaScript executed by Node stubs whose state, not the reported row, is the oracle | `tests/test_service_mail_script_harness.py`, `tests/test_service_qualification_probes.py` |
| integration | the real composition, compiler, applicators, runtime and store with only external seams injected | `tests/test_service_mail_integration.py`, `tests/test_service_qualification_coordinator.py` |
| system | the public tool surface and the Q1 stage gate an operator meets | `tests/test_service_tools_surface.py`, `tests/test_service_qualification_cli.py` |
| regression | S1 entry, S0 decision, S4a runner and the containment gates | the existing modules, unchanged except where a delta above names them |
| S3 unit/domain | canonical authority, compact range arithmetic, mode foundations, IDs/hashes, capability/replay defaults | `tests/test_dhcp_authority_composition.py`, `tests/test_endpoint_dhcp_mode_observer.py`, `tests/test_service_foundational_evidence.py`, capability and replay suites |
| S3 generated-script harness | real generated pool, mode, acquisition and lease-reader scripts executed by persistent Node stubs; stub state and call log are the oracle | `tests/test_service_dhcp_script_harness.py`; the C0 case in `tests/test_service_client_ownership_harness.py` |
| S3 integration/system | intent through composition, E5/E6, stage-aware application, persistence, unchanged MCP schema and reporting budgets | `tests/test_service_dhcp_integration.py`, `tests/test_apply_enterprise_services.py`, `tests/test_service_product_scale.py`, surface tests |
| S3 audit corrections | actual generated strict-boolean, allocation/attribution and exclusion-bound counterexamples plus real applicator/store preservation | `tests/test_endpoint_dhcp_mode_observer.py`, `tests/test_service_dhcp_script_harness.py`, `tests/test_dhcp_authority_composition.py`, `tests/test_service_dhcp_integration.py` |
| Q3 qualification system | exact definition/budget, private real composition, generated probes, CLI/coordinator admission, persistence, stop rules, guard and record round trip | `tests/test_service_qualification_contracts.py`, `tests/test_service_qualification_probes.py`, `tests/test_service_qualification_coordinator.py`, `tests/test_service_qualification_cli.py` |
| Block F qualification | typed baseline admission, the three default snapshots, the bounded readiness gate, zero observers in the amended profile and the E5-before-E6 gate | `tests/test_service_qualification_contracts.py`, `tests/test_service_qualification_probes.py`, `tests/test_service_qualification_coordinator.py`, `tests/test_service_qualification_cli.py` |
| Block F S1b | shared page-store binding, conflict refusal with zero effects, HTTPS-only ownership, expectation markers, generated writer and unchanged capability defaults | `tests/test_service_https_content.py`, `tests/test_enterprise_services.py`, `tests/test_service_runtime.py`, `tests/test_apply_enterprise_services.py` |

Acceptance testing is offline through the product use case and the runner. A
positive runtime test with a private candidate catalog is not product
acceptance. Block E's campaign authorizes only its clean, published, CI-green
exact-SHA Q3-file and repaired-Q1-file attempts; it grants nothing to Q2 and
does not promote or independently accept S3.

## S3 implementation evidence

Observed offline in sibling worktree `Cisco-MCP-s3`, branch
`feature/server-pt-s3-dhcp`, cut from exact commit `cdc30cd` (tree `629573e`).
The worktree owns a CPython 3.14 `.venv`; `packet_tracer_mcp` resolves from that
worktree. `AGENTS.md` and `docs/engineering/standards.md` were read from it.
This Codex session was not freshly started there, so effective instruction
loading for the sibling remains **pending**, not inferred from matching files.
Nothing opened or contacted Packet Tracer, started a product bridge, ran a Q
stage, promoted a capability, reset a claim, pushed or merged.

The installed Cisco reference under Packet Tracer 9.0.1
`help/default/IpcAPI` was inspected before behavior edits. It confirms the
members and return types recorded above. `addPool` and `dhcpRun` are void;
`isEnable` is the getter; `setNetworkMask` takes network and mask; and no lease
count/end condition or lease-time semantics is documented. Those gaps remain
M-DHCP-1/2/4/6 rather than being filled by offline tests.

| Commit | Scope |
| --- | --- |
| `e565752` | design delta recorded before behavior changes |
| `09295d2` | C0 originating-boundary correction and real generated-script/store regressions |
| `d6cfecd` | canonical authority, E5 mode bootstrap, typed DHCP runtime, scheduling, admission and persistence |
| `9fd6163` | format only; AST hashes equal for all 25 formatted files |
| `945265a` | touched-file lint ownership and preserved enum presentation |
| `b25eb20` | acceptance hardening, scale, containment and stable documentation |
| `ea7f8d2` | explicit replay-taxonomy delta: Services 13 to 16, total 53 to 56 |
| `874be85` | evidence-only projection of the first full-green S3 candidate |
| `8bcfdec` | single author-review fix pass: exclusion conflict, staged recovery evidence, configure-only admission, generated error boundary and exact typed reads |

### Causal RED and GREEN

| Boundary | RED | GREEN |
| --- | --- | --- |
| C0 owned release | the real generated Node release script cropped a synthetic value and the production store retained `S3C0-`; a later non-secret mutation batch retained `S3C0-mut` from an earlier resolved value | both emit `engine_error:Error`; complete raw/JSON/URL forms, cross-bound fragments and safe controls remain bounded; 87 focused and 234 affected tests passed |
| authority/bootstrap | real intent composition emitted an IOS pool and could not compile DHCP; an uncertain E5 action plus a VERIFIED mode row incorrectly founded E6 | one canonical delegation suppresses only that IOS pool, retains clients, and the exact fresh true mode plus an admissible action is required |
| pool/acquisition/readers | the runtime had no DHCP family; the persistent Node harness failed at the missing dispatch | 22 harness cases exercise void add/get, no-op/conflict, post-read after throw, exclusions, claims/nonces, lost response, replay, address and bounded lease-table evidence; no release/reset/event method exists |
| dependent effects | the real applicator dispatched mail client configuration while `DHCP_LEASE` was UNKNOWN | stage-aware verification prerequisites suppress the actual call, retain independent work, detect cycles and admit a synthetic VERIFIED control once |
| full taxonomy | the first full run had one failure: Services was still pinned at 13 although three S3 families were registered | the accepted delta pins 16 services and 56 total families with enable replay-safe and pool/acquisition UNKNOWN |

### Suites and gates

| Check | Commit/tree | Result |
| --- | --- | --- |
| untouched baseline | `cdc30cd` / `629573e` | 6317 passed, 3 skipped, 5 warnings |
| S3 focused closure | executable content through `b25eb20` | 234 passed, 1 pre-existing Pytest warning |
| affected/coexistence | executable content through `b25eb20` | 628 passed |
| full offline suite, first run | `b25eb20` | 6385 passed, 3 skipped, 1 taxonomy-delta failure |
| full offline suite | `ea7f8d2` / `752718f` | 6386 passed, 3 skipped, 3 pre-existing warnings |
| namespace inventory | `ea7f8d2` | 0 active imports, 0 active strings, 0 unreviewed inert mentions |
| documentation | `ea7f8d2` | built; only the two pre-existing `handoff.md` link warnings |
| whitespace | `ea7f8d2` | worktree and index clean |
| self-review focused fix pass | `8bcfdec` | 266 passed |
| affected/coexistence after self-review | `8bcfdec` | 628 passed |
| full offline suite after self-review | `8bcfdec` / `9caf1d2` | 6392 passed, 3 skipped, 3 pre-existing warnings |

C0 is closed for this adapter and its invocation-local resolved values; it is
not a claim about arbitrary strings elsewhere in the process. S3 is complete
offline at the intentional boundary: candidate paths execute only with
test-injected capability records, while every product DHCP capability remains
UNKNOWN/UNMEASURED and dependent effects therefore remain unavailable by
default. Exact-SHA CI is pending because push is not authorized.
The whole-branch review was performed by the author; independent review is
still required and was not simulated because this assignment forbids
subagents.

## Block F implementation evidence

Observed offline in worktree `Cisco-MCP-s3`, branch `feature/server-pt-s3-dhcp`,
from exact commit `c0307ca` (tree `407760f`), which equals the published
`cisco/feature/server-pt-s3-dhcp` head and descends from `cisco/main`
`6263344`. The worktree owns its `.venv` and `packet_tracer_mcp` resolves
inside it. `AGENTS.md` and `docs/engineering/standards.md` were read from this
checkout at the start of the work. This Claude Code session was started here,
and `CLAUDE.md` with both imported files are present as project instructions;
an independent `/context` listing was not captured, so effective loading is
recorded as **observed through the session's own instruction context**, not as
a separately reproduced check. Nothing opened or contacted Packet Tracer,
started a product bridge, ran a Q stage, promoted a capability, reset a claim
or merged to main.

| Commit | Scope |
| --- | --- |
| `468d81a` | Block F design delta recorded before any behavior change |
| `56d80b4` | typed Q3 coexistence, the readiness gate, the E5-before-E6 classification and the M-DHCP-3 omission |
| `702a271` | S1b shared page store: one content action per host page, conflict refusal, expectations and metadata |

### Causal RED and GREEN

| Boundary | RED | GREEN |
| --- | --- | --- |
| baseline admission | the real CLI run with the exact observed native pool stopped at `q3_initial_server_state_not_admissible`, exactly as both LIVE records did | the measured `serverPool` row admits, an arbitrary `DEFAULT`, a changed field, a wrong type, a duplicate, an extra pool, an enabled process, a truncated inventory, a foreign subject and an unqualified build or channel all refuse before any effect |
| default preservation | a run whose default moved under it completed and dispatched the acquisitions anyway | the three bounded snapshots are recorded, the difference is named, and `q3_native_default_changed:default_pool_changed:serverPool.gateway` stops the stage with `dhcp_runs == []` |
| readiness | with every port down, the Q1 executor wrote its marked page and started four fetches; the Q3 executor requested both acquisitions | the gate reads at most four times inside 30 monotonic seconds, and an unready fixture produces no marked page, no created client and no `dhcpRun`, with both stages still finalizing and proving restoration |
| native boolean integrity | `isPortUp` answering with a number read back as `port_up: false` | it reads back as `port_up: null` with `port_up_type: "number"`, the sample is incomplete rather than down, and no fetch starts |
| E5 before E6 | a short E5 batch and an unverifiable foundation each reached `addPool` | both stop with `q3_foundations_not_established` before any server mutation, and a contradicted product read-back stops before the same-claim guard instead of after it |
| event deferral | the profile registered four observers and called detachment observed from an attempt that did not throw | the amended profile dispatches zero `registerEvent` and zero `unregisterIpcEventByID` calls, records M-DHCP-3 OMITTED with its reason, and leaves no observer release row |
| shared page store | the compiler emitted no HTTPS content action at all, so an HTTPS fetch verified the empty marker | one action serves both protocols, both expectations resolve the same marker, HTTPS-only publishes through `HttpsServer` with no HTTP enable, and two stated contents refuse with `WEB_CONTENT_CONFLICT` and zero dispatched calls |
| plan identity | adding the shared metadata moved the semantic hash of every existing plan | self-only ownership and the source record stay out of the hash, so `844b7665…b66e8` is unchanged and only a real shared binding moves it |

### Suites and gates

| Check | Commit/tree | Result |
| --- | --- | --- |
| focused qualification closure | `56d80b4` | 282 passed |
| S1b acceptance closure | `702a271` | 18 passed |
| full offline suite | `56d80b4` | 6504 passed, 3 skipped |
| full offline suite | `702a271` | 6522 passed, 3 skipped, 3 pre-existing warnings |
| quality gate, worktree mode | `702a271` | 84 changed Python files gated, 0 mechanical exemptions, lint and format clean |
| namespace inventory | `56d80b4` | 0 active imports, 0 active strings, 0 unreviewed inert mentions |
| whitespace | `702a271` | worktree and index clean |
| quality gate, delivery mode | `1c1f954` / `cc1a7c8` | clean tree at the exact commit, base and merge base `6263344`, 84 gated files, 0 exemptions |
| documentation | `1c1f954` | built; only the two pre-existing `handoff.md` link warnings |
| exact-SHA CI | `1c1f954` | run 35480784437 success: `quality`, `docs` and pytest on Windows/Linux x 3.11/3.13 |

The branch was published by ordinary fast-forward (`c0307ca..1c1f954`), which
is the only publication this amendment authorizes. Delivery-mode gate and
exact-SHA CI results always name the commit they ran on; this evidence commit
is a later one, and its own CI status is reported with the delivery.

Both LIVE slots remain unused. The amendment's section 7 attempts are
conditional on the delivery gate, the fast-forward publication and exact-SHA
CI, and a correct terminal inconclusive result is an acceptable outcome of
either one.

## Block I — executable diagnostic foundations for a Goal (risk L)

The two prepared profiles become two executable qualification stages,
`D-DHCP` and `D-WEB`, so a later separately authorized Codex Goal has
something to run rather than another plan. The design delta, the requirement
table and the invariants are in
[`server-pt-goal-foundations.md`](server-pt-goal-foundations.md); the operator
procedure, the budget arithmetic, the ungranted authorization templates and
the inactive `/goal` draft are in
[`../../qa/server-services-goal-contract.md`](../../qa/server-services-goal-contract.md).
This block authorizes no LIVE run, starts no bridge, contacts no Packet Tracer
instance, promotes no capability, continues no exhausted campaign and edits no
archived record.

What it changes in this workstream, and nothing else:

- **Two false maintained claims are corrected.** A usable registered STP
  observation does exist (`OperationalQueryId.SHOW_SPANNING_TREE` with the
  maintained parser), and `Port::getLightStatus()` is documented with its
  enumeration (`off=0, amber=1, green=2, blink=3`). The D-WEB profile's
  limitation, the listener evidence tokens and the probe module's documented
  surface said otherwise; they now say which procedure reads them instead. The
  light is auxiliary evidence and never a forwarding or reachability claim.
- **The D-DHCP pool projection is corrected.** Removing the enable edge was
  not enough: the compiled plan also carried two client `endpoint_dhcp_mode`
  foundations a server-only E5 can never verify, a `DHCP_SERVER_STATE`
  expectation written for `enabled=True`, and prerequisites naming actions the
  projection drops. Every rewrite is now returned explicitly and recorded, the
  disabled stage verifies `enabled=False` with the exact pool fields, and the
  enable stage rebinds that read-back so activating the process also verifies
  the transition it makes. The D-DHCP profile's D3-a step therefore costs two
  operations, not one, and its proposed worst case is 44 of 60.
- **The product web reader is instrumented.** It reads `isHttps()` in both
  modes, binds the observed owner, keeps a coherent native `go()` result with
  its type instead of coercing it, retains every attempted inspection with its
  dispatch, result, offset and remaining budgets, accepts a finite explicit
  inspection schedule without replaying missed slots, and grants one bounded
  late read before release. The public timeout defaults are unchanged and the
  default composition reproduces today's behaviour exactly.
- **One execution authority, not a second framework.** `D-DHCP` and `D-WEB`
  are stages: the same request rule, repository and process gates, fixed
  transport, ledger, write-ahead record and CLI. The authority binds, in
  addition, the profile and version, the exact tree, the exact fixture models
  and link ports, the ordered step selection, the cleanup reserve, a fresh
  instance token and a unique attempt identity the record store must confirm is
  new. Profile version 2 additionally binds the exact Packet Tracer PID and
  executable path. Before transport construction a read-only local preflight
  requires exactly that one process at the authorized build and an empty file
  mailbox; it launches, stops and deletes nothing. The existing empty-workspace
  read remains the last admission gate before any effect, so a user's document
  is never accepted as the disposable fixture. `DiagnosticAuthorization` stays
  planning data that nothing executable reads.

Proposed, reviewable ceilings: D-DHCP 50 / 900 with a planned worst case of 45,
D-WEB 68 / 900 with a planned worst case of 63. Both are measured from the
composed call paths. No existing ceiling moves: Q0 stays 20 / 300, Q1 stays
60 / 600, Q3 stays 60 / 1200.

## Open decisions

| # | Decision | Current disposition |
| --- | --- | --- |
| 1 | **Q1 budget.** | 60 / 600 with the 10-operation reserve; the worst case the stage definition computes is 56, after Block C stopped repeating M-DNS-3 and Block F added the bounded readiness gate. No LIVE authorization follows from it. |
| 2 | **Q0 slack.** | Unchanged: 20 / 300; one spare operation is not a retry entitlement. |
| 3 | **Mail evidence under the fallback.** | `SMTP_DELIVERED` is supporting evidence only. Promotion of any mail operation needs a Q2 record at its own SHA; an event path needs a safe zero-event release first. |
| 4 | **Claim scope on HTTP.** | The claim bounds duplicates only within one evaluation. HTTP separate-evaluation atomicity is INCONCLUSIVE, so the claim is a candidate mechanism, not a qualified one. |
| 5 | **R-QUAL-05/06.** | A repaired-Q1 sample would be attributed to its own SHA and can never be relabeled as S1b/Q1b evidence. |
| 6 | **S1b content contract.** | Decided by the Q1 ordinal-1 record: `shared_content`. Implemented offline in Block F. Promotion still needs Q1b at the S1b SHA or a reviewer-approved exact-equivalence argument; neither exists. |
| 7 | **Q3 native default.** | `serverPool` coexists under the Block F admission policy for this disposable fixture, build and channel only. Whether Packet Tracer serves from the native pool or from `MCP_E6Q_DHCP` when the process is enabled is unqualified and is not assumed either way. |

Deferred, with its consumers identified in the `0850de3` archive: reducing root
`handoff.md` to a route.

## Next authorized offline work

1. Deliver Block F as two separately reviewable commits — the qualification
   changes, then S1b — with causal RED first at every boundary whose behavior
   changes, then run focused, affected, full, documentation, namespace and
   whitespace gates.
2. From a clean exact delivery commit, run the delivery gate, fast-forward
   publish only this feature branch and require exact-SHA CI green.
3. Only after that, and only if the recomputed worst case fits, use the two
   remaining attempts in the amendment: Q3 ordinal 3 of the original 3, then
   the independent Q1 ordinal 2 of the original 2, each with its own immutable
   attempt authorization, process, session and nonce. A correct terminal
   inconclusive result is an acceptable outcome; exceeding a cap is not.
4. Deliver `READY_FOR_REVIEW`. Author self-review and campaign measurements do
   not provide independent acceptance, merge authority or capability promotion.

## Verification evidence

Observed in the sibling worktree `Cisco-MCP-s2`, branch
`feature/server-pt-s2-mail`, cut from `0850de3` (tree `acc6caf`), with its own
`.venv` (CPython 3.12.10) and `packet_tracer_mcp` resolving inside that
worktree. `cisco/main` resolved to `6263344`. Instruction loading: this session
loaded `CLAUDE.md`, `AGENTS.md` and `docs/engineering/standards.md` from the
primary checkout, and the three files in this worktree are byte-identical to
them; a fresh session started inside this worktree was not observed, so its
effective loading remains **pending**, not passed. Nothing contacted Packet
Tracer, started a product bridge, executed a Q stage, promoted a capability or
reset a claim.

| Commit | Tree | Scope |
| --- | --- | --- |
| `51e5164` | `d833d18` | evidence: the `0850de3` Q batch and the S4a brief, archived byte-for-byte |
| `17153c6` | `7c00f00` | design: the S2 and Q1-repair requirements above, recorded before any behavior change |
| `27fb87f` | `8e617e4` | format only: the replay registry and its taxonomy test, AST-identical to the parent |
| `1cf1b45` | `c10b7e4` | lint only: the registry's Ruff findings, with its enum presentation pinned by test |
| `6ebd517` | `ec14119` | Block A: S2 mail under the R-EVT-05 fallback |
| `147f3b4` | `a900a06` | Block B: the Q1 page-table repair and its listener observations |
| `6e78e74` | `5c0850c` | results of Blocks A and B; the reviewed candidate |
| `7d37db9` | `675fc96` | design: the Block C requirements above, recorded before any behavior change |
| `5313eb0` | `ab95747` | Block C: the S2 secret boundary, both effect admissions and the mailbox coherence rule |
| `4b45039` | `2cf89ce` | Block C: the unresolved Q1 page effect and the M-DNS-3 scope alignment |
| `ec3dc24` | `d804d8b` | results of the three commits above |
| `26b1015` | `a60166c` | Block C: the owned-client release diagnostics, found by self-review of the same boundary |
| `897242f` | `3698880` | results of the two commits above |
| `9a09cf2` | `dc17ce5` | the coherence rule's input contract |
| `8ae2d60` | `64b579b` | risk S: the two bridge wait bounds, measured soundly after a CI failure |
| this commit | — | results only: this line and the rows above |

CI runs are attributed to their exact SHA and never inherited. Run
`35414623111` is evidence for `6e78e74`. Run `35449378228` on `9a09cf2`
failed one job of six; the risk-S note below is its correction. Run
`35450975803` on `8ae2d60` is green on all six, and `8ae2d60` carries every
executable change in this package — this commit changes documentation only,
and its own run is verified at delivery rather than quoted here.

**Risk S — the CI clock measurement.** CI run `35449378228` on `9a09cf2`
failed one job of six, `pytest (windows-latest, 3.11)`, on
`assert 9.249999999999972 >= 9.25` in
`test_governed_wait_longer_than_the_old_fixed_window_is_honored` — a test
this package does not touch, in a module it does not import.

The deficit is exactly one ulp of `time.monotonic()` at an uptime of
128-256 s, which a fresh runner has. The clock returns seconds-since-boot as
a float, `GetTickCount64` in milliseconds on that platform, so each endpoint
carries up to half an ulp of representation error and their difference can
read below the interval that actually elapsed. The bound left no margin for
it. The same test also read its start point AFTER starting the responder
thread, so the sleep being measured could begin before the measurement did;
the two microsecond-scale terms nearly cancelled and the rounding decided the
comparison.

Both bounds now read `time.monotonic_ns`, which has no representation error,
and allow the clock's own resolution — one tick is the most a pair of samples
can under-report, so this is the measurement's own uncertainty and not slack.
The governed wait measures from before the thread starts, making the observed
window a true superset of the sleep. A wait genuinely short by more than one
tick still fails. `test_file_bridge.py` carried the same unsound float bound
without ever firing and is corrected with it rather than left as a known
latent flake.

No production code changes. Touching both files takes ownership of their Ruff
state, so their 25 pre-existing findings are cleared here — eleven docstrings,
two import blocks and one `zip(..., strict=True)` over two lists the same
assertion already requires to be parallel — and the gated set grows 73 -> 75.

### Causal RED and GREEN

| Block | RED, before the production change | GREEN, after it |
| --- | --- | --- |
| A — compiler, secrets, script harness, integration | the four new modules failed at collection on the absent API | 22, 10, 32 and 12 passed |
| A — decision rows 21 and 22 | 4 failed / 89 passed: both tuples were `inconsistent`, and the sticky-row set lacked `22` | 94 passed |
| A — public surface | new assertions on an unchanged surface | 3 passed, on both channels |
| B — the Node stub made update-only | the unchanged `0850de3` probe reproduced the LIVE failure offline: INCONCLUSIVE, `marker_write_failed`, `File not exist: mcpq-…-h.html` and `-s.html` | — |
| B — probes, contracts, coordinator, CLI | 8/34, 18/64, 9/34 and 1/18 failed/passed | 42, 82, 43 and 19 passed |
| C — S2-12 boundary and S2-06.1 coherence | both new modules failed at collection on the absent `EvidenceSanitizer` and `mailbox_scan_incoherence` | 20 and 13 passed |
| C — S2-02.1 and S2-05.1 over the real scripts | 7 failed / 48 passed: the mismatched identity ran `addUser`, each of `null`, `false`, `0` and `""` under an own claim key sent a message, and a credential-bearing script returned engine text | 42 passed |
| C — S2-12 through the applicator and the store | 1 failed: the response and the stored record carried the whole credential from a verification `ENGINE_ERROR`, and a second occurrence left the cropped prefix `pa\"ss\\w` behind | 13 passed |
| C — Q1R-7 assessor, probe and coordinator | 1 failed on the assertion that encoded the defect (`lost_read.outcome_unknown is False`); the stub setter that changes the page and then throws reproduced it against the real probe | 87, 43 and 45 passed |
| C — the owned-client release path | 1 failed: the folded value `top secret value` reached the row's limitations through `_with_release`, which bypasses `_observed` | 21 passed |

One defect surfaced during GREEN and was fixed in the layer that caused it: a
VERIFIED mailbox-presence recovery read made the SMTP service's usability
VERIFIED while the send's own outcome stayed unobserved
(`test_unrelated_dns_and_http_success_never_upgrades_mail`). That was a design
defect of the reader, not a test to relax: presence is now OBSERVED with status
PARTIAL and `supporting_evidence_only` (S2-06). One Block B test premise was
corrected the same way: the all-timeouts trace needs a stub that serves nothing
(`serve_nothing`), not merely an unchanged page after a refused fetch.

Explicit deltas to existing tests, each with its reason in the diff: the
taxonomy counts (Services 8 → 13, families 48 → 53), the sticky-row set (adds
`22`), the S0 effect-class test (the three event kinds are the first
`user_state` kinds), the converted-enum presentation list (the four registry
enums and `AddressingPreference`), the mutation-containment inventory (six mail
mutators), and every Q1 figure (worst case 46 → 54, M-HTTPS-1 2 → 4, M-HTTPS-2
14 → 20). The three `0850de3` page-table probe tests and the listener contract
tests were replaced by tests of the repaired procedure that keep their
invariants: an unreadable cell is never an absence, and no negative control
establishes the listener model.

Block C's explicit deltas, each with its reason in the diff:
`test_a_failed_or_lost_step_stops_without_a_conclusion` no longer asserts
`lost_read.outcome_unknown is False`, which was the defect written down as an
expectation; the three page-effect cases are now their own tests. Every Q1
budget figure moves with the scope (worst case 54 → 53, required experiment
operations 25 → 24, the nominal executor trace 52 → 51, the infeasibility
control 53 → 52). The coordinator's M-DNS-3 assertions become OMITTED with its
reason instead of `ran`/`stopped:`, and `test_q1_measures_all_three_...` is
renamed for the two experiments it now measures. `_page_procedure` in the
probe harness follows the coordinator's step admission instead of running all
four steps unconditionally, so a skipped step is `None` there too. The Node
mail stub gains `account_identity` and a guarded `getUser`, without which it
always returned the requested username and could not express the identity
defect; the Q stub gains `setpage_throws_after_http/https`.

### Suites and gates

| Check | Tree | Result |
| --- | --- | --- |
| E6, S1, S0, S4a and both architecture gates | `147f3b4` | 946 passed |
| full offline suite | `147f3b4` | 6274 passed, 3 skipped, 3 pre-existing Pytest warnings |
| full offline suite | the Block A worktree, Python identical to `6ebd517` | 6263 passed, 3 skipped |
| quality gate, delivery mode | `147f3b4`, clean tree | 72 changed Python files gated, 0 mechanical exemptions, Ruff lint and format clean |
| mail, secrets, observation and integration suites | `4b45039` | 20, 13, 42 and 13 passed |
| qualification contracts, coordinator, probes and CLI | `4b45039` | 87, 45, 43 and 19 passed |
| full offline suite | `4b45039` | 6316 passed, 3 skipped, the same 3 pre-existing Pytest warnings |
| full offline suite | `26b1015` | 6317 passed, 3 skipped, the same 3 warnings |
| quality gate, delivery mode | `4b45039`, clean tree | base `cisco/main` → `6263344`, merge base identical; 73 changed Python files gated, 0 mechanical exemptions, Ruff lint and format clean |
| quality gate, delivery mode | `26b1015`, clean tree | the same base and merge base, the same 73 files, clean |
| quality gate, delivery mode | `9a09cf2`, clean tree | the same 73 files, clean. That commit changed one docstring and one table row, so the `26b1015` suite result stands for its executable content |
| full offline suite | `8ae2d60` | 6317 passed, 3 skipped, the same 3 pre-existing Pytest warnings |
| quality gate, delivery mode | `8ae2d60`, clean tree | 75 changed Python files gated, 0 mechanical exemptions, Ruff lint and format clean |
| the two corrected wait bounds, repeated | `8ae2d60` | 3 consecutive runs, 2 passed each |
| exact-SHA CI, run `35450975803` | `8ae2d60` | 6 of 6 green: `pytest` on windows-latest and ubuntu-latest × Python 3.11 and 3.13, plus `quality` and `docs`. The `windows-latest, 3.11` job that failed on `9a09cf2` is among them |
| quality gate, delivery mode | this commit, clean tree | the same 75 files, clean; this commit changes documentation only |
| namespace inventory | this commit | 0 active imports, 0 active strings, 0 unreviewed inert mentions |
| documentation build | this commit | built; only the two pre-existing `handoff.md` link warnings, none introduced |
| whitespace | this commit | `git diff --check` clean |
| archive integrity | `51e5164` | the committed ZIP is 21,509 bytes with SHA-256 `e93b130a…adfdc`; every archived record hashes to its `source-manifest.json` value |

Every Node harness ran: the suite reports three skips and none of them is the
missing-Node skip. They are the symlink-privilege case in
`test_cp_live_data_integrity.py` and the two absent-artefact cases in the
positive-voice modules, all three pre-existing and environmental.

The documentation-only commits changed no Python, so the suite above is
unaffected by them; the gate, the docs build and the whitespace check were
re-run on this commit.

## Residual limitations

- **READY_FOR_REVIEW, never self-approved.** Only an independent reviewer can
  accept this package. CI being green is not acceptance: it is six offline
  jobs, and every limitation below survives it.
- **CI covers `8ae2d60`, not each commit behind it.** Run `35450975803` is
  attributed to that SHA alone. The Block C commits below it were never run
  individually, so the package is green as delivered, not commit by commit.
- **The Q1 page effect is bounded, not reconciled.** Block C adds no
  reconciliation read. An attempted write that was not read back stops the
  experimental phase instead of being resolved, so a repaired-Q1 run can end
  with `index.html` on the owned disposable server in a state its own record
  calls unresolved. That is the conservative answer, not a measurement.
- **The safe error category costs detail.** A batch that resolved a credential
  now reports `engine_error:<Name>` instead of the engine's own message, so a
  mail setter failure is diagnosed by category and by the surrounding typed
  facts. Batches with no resolved value keep their bounded diagnostic.
- **The boundary is this adapter's, not the whole process's.** Every outbound
  string of `enterprise_service_runtime.py` crosses it, and `sanitized_detail`
  has no caller left there. The channels keep calling it for socket and OS
  errors, which carry no resolved value and never see one.
- **M-DNS-3 is not re-measured.** Its only sample remains the Q1-file run at
  `0850de3`, with that run's reader, model, build and channel. The probe and
  its rule stay in the runner and in their own tests, unscheduled.
- **Offline only.** Every mail and Q1 result above comes from a Node stub
  engine. Whether Packet Tracer behaves that way is exactly what Q2 and a
  re-authorized Q1 would measure, and no offline run promotes anything.
- **Two vendor inferences are labelled, not measured.** The mailbox reader
  reads `Mail`'s `from`, `rcpt`, `subject` and `content` as properties, which
  Cisco's `struct_mail` page documents as public attributes but does not show
  through the Script Engine; and the claim bounds duplicates only under the
  single-evaluation atomicity inference, which the HTTP channel's ATOM-1 left
  INCONCLUSIVE.
- **No mail capability is usable in the product.** Every mail operation is
  UNKNOWN in the catalog and UNKNOWN/UNMEASURED in the replay registry, so a
  required mail service is refused before E5 and an optional one is excluded.
- **No event path exists.** SMTP send, POP3 retrieval and end-to-end rows
  report a typed blocked result. R-EVT-01..03 and R-OBS-05 are not implemented
  and R-SEC-06 is unreachable, because no retrieval is dispatched; R-MAIL-07
  belongs to Q2.
- **The repaired Q1 has not run.** M-HTTPS-2 stays INCONCLUSIVE by
  construction until a qualified listener-refusal observable exists, and any
  future sample is attributed to the SHA that executed it.
- **Reporting budget.** Mail adds up to five rows per selected client while the
  S1 response budget stays at five rows per client, so a very large mail plan
  is refused at composition rather than reported partially.
- **Carried from `0850de3`:** Q0 observer cleanup stays UNKNOWN, pid 28652 was
  still running at the batch handoff, and any later LIVE work needs a fresh,
  operator-confirmed dedicated process.
- **The delivered Q3 pre-cleanup payload is missing, and stays missing.**
  Operation 32 of `q3-2026-09-20T03-27-46Z-51ff55e7` was dispatched and
  correlated, but the reading it returned reached no durable field, so the
  pool values held at that moment are unrecoverable. Block H stops the loss
  for future runs; it does not reconstruct this one. The payload is never
  assumed equal to `after_setup`, and the exhausted attempt is never rerun to
  fill it. The record's bytes and hashes are unchanged.
- **Which operation moved the native default is still unknown.** The change
  is observed between two readings eleven operations apart. D-DHCP is the
  proposed way to find out; it is a draft with no granted authorization, and
  the transition remains a dependent variable, not a product invariant.
- **The Q1 HTTP boundary is still unlocated.** The single HTTP positive ended
  with no observed content change inside its deadline, and the HTTPS positive
  and both negatives never ran. D-WEB is prepared and ungranted; with only
  documented read-only members, the network path and the listener cannot be
  separated, because `onRequest`, `onDone` and `HttpResponseType` are
  unqualified or undocumented in the installed reference.
- **Both campaign attempt pools are spent.** Q3 3 of 3 and Q1 2 of 2 are
  consumed. No SHA, nonce, diagnostic label or restart creates another.
