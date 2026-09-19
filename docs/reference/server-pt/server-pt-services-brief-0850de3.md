# Server-PT services: current workstream brief

This is the **current projection** of the Server-PT services workstream: what is
accepted, what is in scope now, which decisions are open, and where each stable
contract lives. It is not a history. The chronological record it replaced —
revision 2.2 planning, the S0/S1/S4a implementation narratives and their review
resolutions — is preserved byte-for-byte under
[`docs/reference/server-pt/`](../../reference/server-pt/README.md) and is read
only to answer a named unresolved question.

Authority order: `AGENTS.md` and `docs/engineering/standards.md` first, then the
approved active requirements and design recorded in this brief, then the owning
code and its tests. Code shows actual behavior and tests verify it; neither may
silently redefine an approved requirement. A historical record never grants a
permission, and a LIVE permission recorded in one never applies to a new run.

## Accepted baselines

| Slice | Commit | State | Record |
| --- | --- | --- | --- |
| S0 — observation integrity | `0bddc9a` | accepted | archived brief, sections 8 and 9 |
| S1 — product entry point (`pt_apply_enterprise_services`) | `1f08afa` | accepted, offline only | archived brief, sections 10 and 11 |
| S4a — qualification runner and Q0/Q1 probes | `9973f66` (tree `6c8af15`) | **REQUIRES_CHANGES**, not LIVE-ready | archived brief, section 12; the review's three findings are the active scope below |

Authoritative main observed by delivery CI:
`6263344e31ba3b0de6539d652f2cd06fc73a3562` (`cisco/main` in the maintainer
checkout). It contains none of the slices above.

Nothing in this workstream has contacted Packet Tracer. Q0, Q1, Q1b, Q2, Q3 and
the S1 LIVE acceptance are all unexecuted. Every capability claim in the catalog
stays at its documentary or offline level.

## Active scope

Complete, offline, the existing S4A-C1..C4 correction contract after review of
`405f293`, and keep S4a unaccepted until the remaining continuation ownership,
effect-ordering, evidence-scope and projection defects close. The reviewed
commit, not main, is the base of this focused correction.

In scope:

- `infrastructure/execution/service_qualification_probes.py` — run-bag ownership,
  and the observability of a cross-read cell that threw;
- `application/use_cases/qualify_server_services.py` — the order in which a stop
  rule is applied relative to the next effect, and the Q1 budget trace;
- `domain/enterprise/services/service_qualification_evidence.py` — the strength
  of each conclusion relative to what was actually observed;
- `domain/enterprise/models/service_qualification.py` — the Q1 design ceiling and
  its planned worst case;
- `docs/qa/server-services-qualification.md` — the stage row that states it;
- the tests named under **Test design**.

Explicitly excluded: S1b, S2, S3, Q2/Q3 beyond their declarative metadata, any
Packet Tracer contact, a new `.pts`, any `EXTENSION/` change, a replacement
transport or protocol, a `tool_registry.py` refactor, catalog or capability
promotion, CP-LIVE reconciliation, and any push, merge or LIVE authorization.

## Where each stable contract lives

Every requirement family the replaced document carried is listed here with its
authoritative destination — the artifact a reviewer must read to decide that
requirement today. The archived record is a destination only for clauses that
were already superseded, rejected or not yet activated there.

| Requirement family | Authoritative destination today |
| --- | --- |
| R-OBS-01 — transport facts | `infrastructure/execution/transport_outcome.py`, `live_bridge.py`, `file_bridge.py`; `tests/test_transport_dispatch_facts.py` |
| R-OBS-02, 06, 07, 08; RD-10 — mutation decision, script contract, effect footprint | `domain/enterprise/models/execution.py` (`decide_mutation` and its fact enums), `enterprise_configuration_runtime.py`, `enterprise_service_runtime.py`; [E6 architecture](../../architecture/enterprise-services.md#mutation-and-observation-vocabulary); `tests/test_execution_status_facts.py`, `tests/test_service_mutation_script_harness.py`, `tests/test_service_application_uncertainty.py` |
| R-OBS-03, R-HTTPS-02/03, R-ENTRY-08, R-CAP-05 — observation limits | `enterprise_service_runtime.py`; `tests/test_service_runtime_observation.py`, `tests/test_service_runtime.py` |
| R-EVD-01 — evidence separated from status | `domain/enterprise/models/service_runtime.py` (`ObservationFact`); `tests/test_service_application_uncertainty.py` |
| R-ENTRY-01..11, R-NET-01/02, R-RET-01/02 — product entry, admission, run records | `adapters/mcp/service_tools.py`, [apply_enterprise_services.py](https://github.com/andres18113/cisco-muejeje/blob/cb2b1fb12978d5050546f31ee51d0918dc5ee38c/src/packet_tracer_mcp/application/use_cases/apply_enterprise_services.py), `infrastructure/persistence/service_run_record_store.py`, `docs/tools.md`; [test_apply_enterprise_services.py](https://github.com/andres18113/cisco-muejeje/blob/cb2b1fb12978d5050546f31ee51d0918dc5ee38c/tests/test_apply_enterprise_services.py), `tests/test_service_tools_surface.py`, `tests/test_service_run_record_store.py`. R-ENTRY-07 is active for S1: the product path removes no user topology, service, account or message; future S2 coverage is an extension, not activation of the existing S1 obligation |
| R-ENTRY-04 — foundational evidence | `application/use_cases/foundational_evidence.py`; `tests/test_service_foundational_evidence.py` |
| R-CAP-01..07 — capability authority and provenance | `infrastructure/catalog/service_capabilities.py`, `domain/enterprise/services/service_capability_resolution.py`; [E6 architecture](../../architecture/enterprise-services.md#packet-tracer-9010858-baseline); `tests/test_service_capabilities.py`, `tests/test_service_client_capabilities.py` |
| R-QUAL-01..04 — the governed qualification runner | `domain/enterprise/models/service_qualification.py`, `application/use_cases/qualify_server_services.py`, `adapters/cli/service_qualification.py`, `docs/qa/server-services-qualification.md`; the S4a tests below |
| R-SEC-02/04, R-REG-01/03 — secret handling, registry hygiene, enum presentation | `docs/engineering/standards.md`, the Ruff configuration in `pyproject.toml`, `scripts/quality_gate.py`; `tests/test_execution_status_facts.py` |
| R-TEST-01 — test-inventory discipline | `docs/engineering/standards.md`, *Architecture and test design*. It is a general rule, not an S0-only one |
| R-HTTP-01..03, R-DNS-01..03 — DNS and HTTP service contracts | [E6 architecture](../../architecture/enterprise-services.md); `domain/enterprise/services/service_compiler.py`; `tests/test_enterprise_services.py` |
| R-COV-01/02 — complete, honestly labelled per-client product results | [apply_enterprise_services.py](https://github.com/andres18113/cisco-muejeje/blob/cb2b1fb12978d5050546f31ee51d0918dc5ee38c/src/packet_tracer_mcp/application/use_cases/apply_enterprise_services.py), [service_compiler.py](https://github.com/andres18113/cisco-muejeje/blob/cb2b1fb12978d5050546f31ee51d0918dc5ee38c/src/packet_tracer_mcp/domain/enterprise/services/service_compiler.py); [test_apply_enterprise_services.py](https://github.com/andres18113/cisco-muejeje/blob/cb2b1fb12978d5050546f31ee51d0918dc5ee38c/tests/test_apply_enterprise_services.py), including skipped, blocked, recovery and unsampled-result assertions. These obligations are active in S1; later slices extend their service coverage |
| R-QUAL-05/06 — re-qualification after a content or protocol change | this brief, **Open decisions**; unimplemented until S1b, S2 or S3 is authorized |
| R-HTTPS-01/04, R-DNS-04, R-MAIL-01..07, R-DHCP-01..08, R-EVT-01..07, R-SEC-01/03/05/06, R-OBS-04/05 | **not active.** Their text stays in the [archived brief](../../reference/server-pt/server-pt-services-brief-9973f66.md); each becomes active only when its slice (S1b, S2, S3, S5) is authorized, and must be restated here at that point |

Supersessions that still bind: TD-12.1 — the classifier reads the original
runtime input, never a repaired copy — and TD-12.2 — a missing list item never
synthesizes channel acceptance. Both are implemented in `execution.py` and
pinned by `tests/test_execution_status_facts.py`. RD-11 — digests are bounded
diagnostics with no authority over `ok`, `changed` or CLEAN — is implemented in
the mutation script contract and pinned by
`tests/test_service_mutation_script_harness.py`.

## S4a correction: design delta (risk L)

Risk stays **L**: the change touches the authorization of a write, the order in
which an effect is admitted, and the strength of an evidence claim. It is a
delta on the S4a design in the archived record, section 12; only what changes is
restated here.

### Requirements and acceptance

| ID | Requirement | Acceptance |
| --- | --- | --- |
| S4A-C1 | A pre-existing run key is rejected **without writing anything**. Every later read/write continuation that can mutate the run bag or an owned resource, and the final release, is permitted only by ownership this invocation proves inside that same evaluation through its nonce — never by the key's name or an earlier successful claim. A collided, absent or ownership-replaced key is not adopted, overwritten, reclaimed or deleted, and foreign logs are not reclassified as this run's evidence. | Node-harness tests execute the real generated scripts with a foreign complete atom log and with observer bookkeeping at every continuation branch. Foreign and ownership-replaced state is unchanged; registration, unregistration, trigger and deletion call counts remain zero. Directly absent and foreign keys stay distinguishable, while a fresh owned key keeps the positive collection, observer and bounded finalization paths. Assertions read the stub's independent snapshot, never a response field. |
| S4A-C2 | The outcome of the preceding effect is evaluated before the next effect is admitted: E5 is classified before any E6 enable is dispatched, the second atomicity contender is queued only after the first receipt is interpreted, an unestablished listener setup admits no fetch, and the positive HTTPS fetch is classified before the HTTP-negative fetch. An incomplete result set or unreleased client is unknown, not success. | Coordinator tests through the real runtimes and generated readers: empty, short and unknown E5 result sets put zero E6 enable scripts on the channel; an unaccepted first contender leaves exactly one queued contender; a lost `prepare_https_only` produces no fetch and no `setHttpsEnable`; and fresh wrong positive content with a released client preserves the contradiction while the channel shows no later negative client, listener toggle or DNS3 effect. Authorized finalization and persistence still run. The nominal successful paths still complete. |
| S4A-C3 | A conclusion is never stronger than its observation. A cross-read cell that threw is unobserved, not `false`, and keeps its cause; two failed cross reads can never yield the separate-table model, and one failed cross read can never manufacture a contradiction. The listener-isolation model is supported only by a coherent, correlated negative observable with a positive control **in the same mode**; where the implementation has no such observable the measurement is INCONCLUSIVE, and no HTTP code, `onDone` semantics or timeout is invented to replace it. Wrong content on the marked positive page still contradicts that positive expectation. An ordered ATOM-1 log is retained as an observation, but a sample whose evaluations were coalesced or whose separation is unknown is INCONCLUSIVE for the separate-evaluation claim. | Domain tests over generated shared and separate table reads with per-cell exceptions and with missing or contradictory fields; listener tests for a wrong-page response while the listener still serves, an absent same-mode positive, a timeout, and the coherent positive; and the existing coalesced HTTP harness test expecting INCONCLUSIVE while retaining its ordered log and scope limitation. Sample, build and channel limitations stay in the record. |
| S4A-C4 | Q1 fits its ceiling on its **bounded worst case**, not on its luckiest trace, with the cleanup reserve intact. | A stage-definition test pins the planned worst case against the ceiling; a coordinator test drives the Q1 executor at the production ceiling with the responses that force every extra poll, and asserts that no call was refused, that the finalization reserve was never borrowed, and that both restoration reads ran. |

### S4A-C1 — ownership before a run key write

`write_bag_sentinel` computed `run_bag_preexisting` and then wrote the sentinel
unconditionally, so the later refusal could not undo the write; `release_run_bag`
deleted `this.__mcpE6Q[<run>]` behind a Python-side flag, so a lost
acknowledgement could let the finalizer delete a key that was never ours. The
run bag now carries an `owner` field set to this invocation's nonce when it is
created:

- the claim writes only when the run key is absent, and reports `written` and
  `owned` as separate facts;
- every probe that writes under the run key (`atom`, `unreg`) first proves
  `owner === <nonce>` in the same evaluation, and otherwise does nothing and
  says so;
- the release proves the same before deleting, and reports `owned` and `deleted`
  separately from `had_run_bag`.

A proven collision means nothing was written: the run stops, the collision is
recorded, and the finalizer touches nothing. An unobserved claim leaves ownership
undecided in Python, and the engine-side check — not a name — then decides
whether the release may delete.

The same-evaluation proof applies to every existing continuation, not only
the initial claim, the first observer registration and final release.
`collect_atomicity` must not read or delete a foreign `atom`; each observer
continuation must stop before copying evidence, creating callbacks, changing
callback state, unregistering, triggering or deleting when the run bag is
absent or no longer owned. Lost ownership remains distinct from absent observer
bookkeeping, and foreign data never becomes this run's measured evidence.

### S4A-C2 — stop rules before the next effect

`_configure_q1` dispatched the E6 enables and only then read its E5 flag, and
both classifications accepted a short result list. E5 is now classified — every
requested action present exactly once, and applied — before the E6 batch is
constructed, and the same completeness rule applies to E6. `_run_q0` interprets
contender A's receipt before queueing contender B. `_https_listener` starts no
fetch and no second toggle unless the first toggle was read back in the same
evaluation, and a fetch whose owned client could not be proven released stops
further experiments. `e5_accepted` keeps its meaning — channel acceptance of a
fire-and-forget batch, never an observed effect — and the record still says so.

The positive HTTPS fetch is itself a stop boundary: its completed reading is
assessed immediately, before the HTTP-negative client is created. A wrong fresh
page preserves the positive contradiction, leaves all later experimental rows
NOT_RUN with their causal stop, and proceeds only to the already-authorized
finalization and persistence path.

### S4A-C3 — conclusions no stronger than observations

`cross_read_page_markers` returns `true`, `false` or `null` per cell and carries
the per-cell cause. `assess_page_tables` decides nothing while any cell is
unobserved, and refuses a reading whose `read_errors` count disagrees with the
unobserved cells.

For M-HTTPS-2 the production reader has **no qualified failure observable**: a
refused request and a slow or lost one both surface as
`no_response_within_deadline`, and fresh non-marker content proves a marker
mismatch rather than a refusal. A declared negative control can therefore only
*contradict* the model — the marker was retrieved while the listener was read
back as disabled — and can never establish it; the HTTP-mode negative
additionally has no HTTP-mode positive control in this stage. M-HTTPS-2 is
consequently INCONCLUSIVE unless something contradicts it, with every
descriptive observation and both limitations preserved. Fresh content without
the marker on the marked positive page contradicts that positive expectation and
stops the stage.

ATOM-1 similarly separates what was observed from what is claimed. Its ordered
log remains evidence about the executed sample, but an HTTP sample that was
coalesced, or any sample whose evaluation separation is unknown, cannot support
non-interleaving between separate evaluations. Such a sample is INCONCLUSIVE
for that claim; an observed counterexample remains CONTRADICTED, and the finite
file-channel sample remains explicitly non-universal.

### S4A-C4 — the Q1 budget

The reviewed design ceiling for Q1 is **60 operations and 600 seconds**,
approved for this offline correction only. It is not a LIVE authorization and it
does not change Q0, Q2 or Q3. The planned figure is now the bounded worst case,
in which every production fetch spends its start, both inspections and its
release:

| Phase | Step | Operations |
| --- | --- | --- |
| admission | executable build, workspace baseline | 2 |
| setup | 4 fixture devices at 2 each, 3 links at 2 each, fixture identity | 15 |
| setup | E5 endpoints, E6 enable HTTP and HTTPS | 2 |
| experiment | M-HTTPS-1 page write and cross read | 2 |
| experiment | M-HTTPS-2: HTTP-off toggle, 3 fetches at 4 each, HTTPS-off toggle | 14 |
| experiment | M-DNS-3 client resolvers | 1 |
| finalization reserve | 4 device removals at 2 each, 2 restoration reads | 10 |
| | **planned worst case** | **46** |

Fourteen operations of slack remain above the worst case, and the ten reserved
operations stay untouchable outside finalization. Q0 keeps **20 / 300**: its one
spare operation is slack, not a retry entitlement, and a Q0 experiment may still
stop inconclusively.

### Invariants that must remain true

1. No call reaches Packet Tracer outside the `OperationLedger`.
2. No probe writes a production global (`__mcpE6Claims`, `__mcpE6Inert`,
   `__mcpE6HttpClients`), and no probe touches a run key it has not proven it
   owns.
3. A mutation is never repeated after an ambiguous outcome. A refusal before
   dispatch is the only proof that one call did not run.
4. `DOCUMENTED` never implies `SUPPORTED`, an offline record is never promotion
   evidence, and `COMPLETED` is not universal support.
5. Finalization always runs once an effect was admitted, its failures stay
   secondary, and its reserve is never borrowed by an experiment.

### Test design

| Level | Scope | Files |
| --- | --- | --- |
| unit (domain) | the pure assessment rules behind every changed conclusion | `tests/test_service_qualification_contracts.py` |
| harness (generated scripts) | the real probe JavaScript executed by the Node stub engine, with the stub's snapshot as the oracle | `tests/test_service_qualification_probes.py` |
| integration (coordinator) | the real coordinator, runtimes, probes and record store over a controlled channel | `tests/test_service_qualification_coordinator.py` |
| system (CLI) | the stage gate an operator actually meets | `tests/test_service_qualification_cli.py` |

Offline acceptance testing of the runner applies through the coordinator and
CLI contracts above. LIVE acceptance of Q0 or Q1 requires a separately
authorized observed run at an exact SHA and is not performed here; its absence
does not make the offline acceptance controls N/A.

## Open decisions

| # | Decision | Current disposition |
| --- | --- | --- |
| 1 | **Q1 budget.** The stage refused before contact because its executable definition exceeded its ceiling. | A design ceiling of 60 operations / 600 seconds is approved for this offline correction, against the proven worst case of 46 with the 10-operation reserve intact. It is **not** LIVE authorization. If a future change no longer fits, the arithmetic is reported and the refusal is retained; no unlimited retry and no stage split is implicitly approved. |
| 2 | **Q0 slack.** Q0 fits with one spare operation. | Keep 20 / 300. One spare operation is not a retry entitlement, the finalization reserve stays whole, and the adverse paths — not only the 19-call positive — are proven. |
| 3 | **M-UNREG event source.** Is `HostPort.ipChanged` on the owned temporary PC an acceptable engine-generic subject? | Accepted as an engine experiment, triggered through `setIpSubnetMask` on the owned fixture. It qualifies nothing about mail or DHCP callbacks, their argument shapes, or safe zero-event detachment; those gates stay open. |
| 4 | **ATOM-1 evaluation scope.** The HTTP channel may join the two queued contenders into one `runCode`. | A coalesced sample is not evidence of non-interleaving between *separate* evaluations, and two queued strings never imply two evaluations. The record states the observed or unknown evaluation scope and keeps a scoped result or INCONCLUSIVE. File-channel sampling is finite too: it proves neither universal atomicity nor exactly-once delivery. No transport or extension change follows from this. |

Deferred, with its consumers identified: reducing root `handoff.md` to a route.
It is the authoritative CP-SCALE projection, with a machine-parsed state block
(`tests/handoff_state.py`) and roughly 220 prose assertions across
`tests/test_cp_scale_current_state.py`,
`tests/test_cp_scale_realtime_stp_observation.py`,
`tests/test_cp_scale_sim_time_diagnostic.py`,
`tests/test_cp_scale_canonical_voice_evidence_ledger.py`,
`tests/test_positive_voice_handoff.py`, `tests/test_positive_voice_slice.py` and
`tests/test_voice_root_cause_retrospective.py`. Reducing it means rewriting
those pinned CP-LIVE evidence assertions, which this delivery excludes. A route
header was added to it instead; the reduction is a separate change with this
consumer list as its input.

## Next authorized offline work

1. Land the S4A-C1..C4 corrections with their regressions, and keep S4a
   `READY_FOR_REVIEW`, not accepted.
2. Obtain exact-SHA CI for the resulting commit once a push is authorized. No
   earlier green run may be relabelled onto it.
3. Independent review of the corrected S4a. Only after that review may a Q0 LIVE
   authorization be *requested*; this brief grants none.
4. S1b, S2 and S3 stay blocked on their Q stages. Nothing here promotes a
   capability, and no offline record is promotion evidence.

## Verification evidence

The prior-delivery figures through **Measured result of the corrections** were
observed in the sibling worktree `Cisco-MCP-s4a` on
branch `feature/server-pt-s4a-qualification-runner`, with its own `.venv`
(CPython 3.12.10) and `packet_tracer_mcp` resolving inside that worktree.
Instruction loading: this session loaded `CLAUDE.md`, `AGENTS.md` and
`docs/engineering/standards.md` from the primary checkout, and the three files
in this worktree are byte-identical to them (same Git blob identities). A fresh
session started inside this worktree was not observed, so its effective loading
remains **pending**, not passed. Nothing in that delivery contacted Packet
Tracer. This block is historical evidence preserved from `405f293`; the
focused-correction evidence follows it and does not relabel these earlier runs.

| Commit | Tree | Scope |
| --- | --- | --- |
| `b311657` | `0e16fdd` | Part A: documentation projection, no runtime or test behavior |
| `78fdb91` | `dfe8858` | Part B: the S4A-C1..C4 corrections and their regressions |

The documentation-only commit `405f293` added this historical section. It
changed no Python file, so the Ruff gate, the namespace inventory and the suite
below were unaffected by it; the exact-commit delivery gate, the MkDocs build
and the whitespace check were re-run on it.

Checks, against `78fdb91` unless stated:

| Check | Command | Result |
| --- | --- | --- |
| causal regressions | `pytest -q` on the four S4a modules | 115 + 33 + 40 + 19 passed |
| affected S4a and S1 area | `pytest -q` on the S4a, run-record, product-entry and service-runtime modules | 455 passed |
| full offline suite | `pytest -q` | 6166 passed, 3 skipped, 3 pre-existing warnings |
| quality gate, delivery mode | `scripts\quality_gate.py --base cisco/main --delivery-commit HEAD` | clean tree at the exact commit; 63 changed Python files gated, 0 mechanical exemptions, Ruff lint and format clean |
| namespace inventory | `scripts\namespace_inventory.py` | 0 active imports, 0 active strings, 0 unreviewed inert mentions. Markdown is not scanned, so the archival path does not affect its classification |
| docs | `mkdocs build --site-dir _site` | built; only the two pre-existing `handoff.md` link warnings, none introduced |
| whitespace | `git diff --check` | clean |
| archive integrity | SHA-256 of every archived file after deleting and re-checking it out | all eight match `source-manifest.json`; the brief archive's Git blob identity equals its source blob at `9973f66` |

Measured result of the projection, as committed blob bytes:

| File | Before (`9973f66`) | After (`78fdb91`) |
| --- | --- | --- |
| `docs/engineering/change-briefs/server-pt-services.md` | 391,435 | 19,052 |
| `handoff.md` | 267,914 | 269,299 |
| `AGENTS.md`, `CLAUDE.md`, `docs/engineering/standards.md` | 22,625 | 22,625 |
| **default reading set** | **681,974** | **310,976** |

No token or cost figure is claimed: none was measured, and none would be
meaningful without naming its tokenizer.

Measured result of the corrections: the Q1 executor's nominal trace spends 45
operations and its worst case, with the positive fetch's first inspection lost,
spends exactly the planned 46 with no refused call and the 10-operation reserve
untouched. The full Q1 stage now passes its gate and completes through the CLI.

### Focused correction evidence

The focused correction is local commit
`cb2b1fb12978d5050546f31ee51d0918dc5ee38c`, tree
`a6b2e9fdb182f31e78ec57bda0537d4a376ee06d`, based directly on reviewed
`405f29334a514f9323b693f7f5340a62b761bf3a`. It changes no budget, transport,
protocol, `.pts`, `EXTENSION/` file or capability state and contacted no Packet
Tracer process.

| Check | Result |
| --- | --- |
| causal RED regressions before production edits | 11 failed for the expected ownership, effect-ordering and evaluation-scope causes |
| focused regressions after the owning-layer fixes | 11 passed |
| complete S4a domain, Node harness and coordinator files | 156 passed |
| affected S4a/S1 and coexistence modules | 401 passed |
| full offline suite | 6174 passed, 3 skipped, 3 pre-existing Pytest deprecation warnings |
| exact-SHA delivery gate | clean tree at `cb2b1fb`; 63 changed Python files gated, 0 mechanical exemptions, Ruff lint and format clean |
| namespace inventory | 0 active imports, 0 active strings, 0 unreviewed inert mentions |
| documentation build | built; only the two pre-existing `handoff.md` link warnings, none introduced |
| whitespace | `git diff --check` clean |

The repository's pytest-isolation wrapper refused this sibling because
`worktrees.json` has no S4a assignment. The tests above therefore used this
checkout's own `.venv` directly, as the active `AGENTS.md` permits; no other
checkout's interpreter or test artifacts were used.

### Residual limitations

- **Not LIVE-ready, and not accepted.** S4a stays `READY_FOR_REVIEW`. Only an
  independent reviewer can accept it, and no Q0 or Q1 LIVE authorization exists.
- **Exact-SHA CI is pending.** Runs for `9973f66` and `405f293` remain historical
  evidence at those SHAs; run 35396445227 succeeded at `405f293`. Neither
  `cb2b1fb` nor its documentation-only successor has been pushed, so no CI run
  has seen this focused correction and no earlier run is relabelled.
- **Offline only.** Every probe result above comes from the Node stub engine.
  Whether Packet Tracer behaves the way that stub does is exactly what Q0 and Q1
  would measure, and no offline run is promotion evidence.
- **M-HTTPS-2 cannot be supported by this build's readers.** The measurement is
  INCONCLUSIVE by construction until a qualified listener-refusal observable
  exists. Adding one is an S1b/Q1b question, not a change to make here.
- **The `handoff.md` reduction is deferred**, with its consumers listed above.
- **Instruction loading inside this worktree is unobserved**, as stated above.
