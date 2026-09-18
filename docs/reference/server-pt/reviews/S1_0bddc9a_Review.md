# S1 review of 0bddc9a: close the product integration contract

**Independent disposition: REQUIRES_CHANGES.**
**Work authorization: causal S1 corrections and requested documentation packaging, offline only.**
**Risk: L. No S1 acceptance, merge, capability promotion, or Packet Tracer authorization.**

## 1. Identity, review basis and limits

Repository: `andres18113/cisco-muejeje`.

```text
Reviewed S1 commit  0bddc9a5203584b14869bdd9cabb071f25d528e1
Reviewed S1 tree    4c46e8cf5838a2b26f3cc99d51ef724ea196bd84
Branch             feature/server-pt-s1-product-entry
Accepted S0        ba45d14b98e86a4f9f863111a246fad0e8d59c9e
Authoritative main 6263344e31ba3b0de6539d652f2cd06fc73a3562 (re-resolve locally)
```

GitHub confirms ten commits ahead of S0, no divergence. Run **35299653719**,
attempt 1, is successful on **0bddc9a**, with six successful jobs. The reviewer
read the complete quality log (105459409880: 44 Python files, zero mechanical
exemptions, exact clean delivery SHA, base/merge-base 6263344) and Ubuntu/Python
3.13 log (105459410288: **5923 passed, 2 skipped, 3 warnings**). The local
5922/3 count is a different execution. The old pending-CI statement is
historical; annotate it rather than relabeling another run.

This review used pinned GitHub source, diffs, tests, repository policy, the
versioned change brief and the attached historical planning sources. It did
not execute the repository suite or Packet Tracer. An attempted disposable
clone failed DNS resolution. The accompanying predicate probes are explicitly
transcribed, synthetic countermodels, not repository RED runs. Reproduce each
behavioral regression against the real affected component before fixing it.
Do not manufacture a particular RED result if the actual component behaves
differently: report the trace and resolve the discrepancy causally.

Read AGENTS.md, CLAUDE.md as applicable, and docs/engineering/standards.md from
the active checkout. Preserve the S0 reference, unrelated/unpublished work,
the canonical import identity and TEST_PROCESS refusal. One writer per
worktree. Do not use subagents. Do not contact Packet Tracer, start a product
bridge, run CP-LIVE, rewrite Git history, push or merge without separate
explicit authorization. Hermetic test sockets under the repository test
contract are not authorization to contact the operator's bridge.

## 2. What remains accepted and what is not being reopened

Keep the E6 architecture, canonical `decide_mutation`, TD-12 input snapshots,
S0 cleanup semantics and DNS PARTIAL-footprint distinction. Keep the opt-in
`services=False` default of composition and the existing E9 endpoint-core
predicate shared by E6. Keep the physical-only contract of `pt_live_deploy`.

A functionally successful DNS observation can coexist with UNKNOWN residue;
UNKNOWN residue alone must not be treated as effect uncertainty. Conversely,
verified recovery reads cannot erase uncertain mutation execution or promote
the aggregate product result above the accepted S0 contract.

Do not implement SMTP, POP3, Server-PT DHCP, routed services, general
inter-switch path support, HTTPS expansion, IoT, or a new engine protocol.
Do not remove the S1 boundary to make a large-topology fixture pass. Safe refusal
of an unsupported path is part of coexistence, not a failure to be hidden.

The following are bounded contract corrections. They are not a request to
restart the investigation or split large modules arbitrarily.

## 3. S1-01 — Actual production admission, fixed transport and provenance

### Evidence

At the reviewed SHA, `adapters/mcp/service_tools.py::pt_apply_enterprise_services`
calls `pick_channel()` before entering A1/A4. The actual registry picker performs
HTTP health reads and reads the file heartbeat; a no-op picker fake does not
prove that invalid JSON or TEST_PROCESS avoids the operator's bridge.

Only `bound_send_and_wait` captures the chosen channel. E5 receives the
unbound `send_payload` and `query_inventory`; the registry's `_bridge_send_payload`
uses `_channel_send` without a channel, and `_live_devices` calls
`_bridge_send_and_wait` without one. Both can select again. E6 receives only
the legacy string-returning callback, not S0's `dispatch_and_wait`.

The adapter constructs an EnvironmentFingerprint using the caller's version,
a default-empty extension-version callable and a fixed runtime-mode string.
The registration never supplies the extension-version callable. The adapter
also omits `source_tree`; the use case then persists `sha="", dirty=True`.
A schema that accepts these defaults is not evidence of executed-SHA provenance.

### Required correction

Keep parsing and process admission in the actual use-case path. Make transport
selection and collaborator initialization lazy enough that A1/A4 refusal
cannot contact a bridge. No new public bypass parameter is allowed.

Bind **every** read and write used by E5/E6 to one admitted session/channel,
including inventory, endpoint observations, fire-and-forget dispatch where
still required by the legacy contract, and typed E6 dispatch. Reuse the
existing bridge instance and typed transport; do not create a parallel bridge
or wrap a lost string result and pretend to recover its original facts.

A small explicit session binding/factory at the existing composition boundary
is permitted when needed to enforce this contract. It must not introduce a
new wire protocol or a general registry framework. Legacy callers keep their
signatures and behavior. Preserve uncertain dispatch and the existing D-9
containment across the legacy E5 boundary rather than treating a false return
as proof of no effect.

Obtain source-tree identity and required runtime provenance through trustworthy
internal observations/ports. Validate current provenance separately from input
versus stored-version equality. Do not copy the manifest into a purported
runtime observation. Reuse documented existing observation paths; an unavailable
required value is a typed limitation/refusal, not a guessed API or an empty
string that grants execution. Early unbound refusal records may honestly lack
fields; records of attempted execution must identify their source and state
which provenance remains unobserved. Never promote an unobserved build.

### Acceptance

- Real `register_tools` wiring, controlled external health/transport seams:
  malformed input and TEST_PROCESS cause zero bridge calls. Counting only
  fake runtime mutations is insufficient.
- Picker changes its recommendation after admission: every inventory/read/
  mutation/finalization still uses the original channel; no fallback or replay.
- Typed NOT_SUBMITTED, REJECTED and ACCEPTANCE_UNKNOWN reach E6 unchanged.
- Non-empty extension-version manifest, actual version mismatch, unobservable
  current provenance and source-tree identity round-trip are distinct cases.
- No token, payload body or raw exception secret is added to the record.

## 4. S1-02 — Effect scope must govern admission as well as dispatch

### Evidence

`ConfigurationApplicator.apply` computes exclusions, but later resolves every
`plan.devices` target, validates every serial-clock action and calls target
validation over the whole plan. An unrelated excluded target or serial
orientation can block a supposedly bounded service slice.

`_unsupported_paths` checks segment equality only and permits a missing segment
entry. The service compiler accepts foundations from both static and DHCP
endpoint actions; `_clients` does not reject DHCP. Drift admission skips
non-static endpoints. Thus the documented static-client boundary is not
established by this predicate before E5 effects. Same segment also does not
prove that the required path avoids an unconfigured inter-switch trunk.

### Required correction

Define the active/retained/excluded partition once. Validate identities,
interfaces, orientation, capabilities and verification prerequisites for the
actual required closure, without unrelated excluded work granting or blocking
it. A required dependency cannot be excluded. Unknown/missing closure seeds
and dependencies must refuse, not disappear through `_e5_closure`'s `continue`.
Keep the complete plan identity; do not manufacture retained rows or recompute
a smaller hash to bypass identity checks. With no exclusions, preserve the old
whole-plan contract and the CP-SCALE/voice behavior.

Before the first E5 mutation, enforce the approved S1 service-path contract:
static Server-PT, static selected PC-PT clients, same selected site/segment,
and only a path whose required switching prerequisites are actually included
or observed under the existing contract. Explicitly refuse a DHCP client,
missing foundation identity, routed path, and an unsupported inter-switch
path. Do not implement DHCP or routing as a fix. A large unrelated workspace
is not permission to process all its devices, nor a reason to silently ignore
missing identity on a selected one.

### Acceptance

Use the actual composition/applicators with controlled backend ports. Assert
both refusal/result and exact runtime call identities.

- Selected valid service fixture plus unrelated missing device, unrelated
  serial action, and foreign deployment: unrelated items neither mutate nor
  contaminate the selected closure's status.
- Missing/ambiguous selected target and required excluded dependency refuse.
- DHCP-selected client and unsupported inter-switch/L3 path refuse **before
  any E5 effect**, not only at the E6 foundation gate.
- Extra CP-like devices and links remain untouched in the in-memory state.
- Default legacy invocation (no exclusions, services opt-out) preserves the
  existing CP-SCALE composition, trace and regression contracts.

## 5. S1-03 — Connect retained reuse to the product, safely

### Evidence

`ServiceRunRecordStore.retained_result_for` exists, but the coordinator never
calls it. `_execute` always sends the entire C as `mutation_action_ids` and
passes no retained results. Store unit tests do not establish R-RET-01 on the
product path. The store's candidate selection also does not itself reject
failed/unsatisfied configuration rows, so simply calling it would not complete
the contract.

### Required correction

Implement the already-authorized A10 reuse path: exact deployment, manifest,
configuration semantic identity, current environment, complete prior facts,
selected retained-set validity and fresh prerequisite verification. Respect
replay policy. Do not reinterpret a newer interrupted/uncertain record as
absence and then silently resurrect an older success for the same affected
state. A prior uncertain attempt never grants a retry merely because it is
not reusable. Surface the blocked/unknown state or prove admissibility under
the registered operation semantics.

Record actual mutated, retained and excluded IDs. A retained result is not an
unchecked cached permission. Keep this logic on the shared product path; do
not build a separate rerun helper only used by tests.

### Acceptance

Two calls through the same real coordinator and temporary store. On the second
eligible run, freshly verify and retain the eligible E5 rows, and prove from
runtime call traces that they were not re-dispatched. Add controls for changed
environment, changed plan, drift, incomplete/failed rows, corrupt record and
newer interrupted/uncertain state. Verify the serialized record supports the
actual retention decision, not only matching counters.

## 6. S1-04 — Public aggregation and release coverage must preserve E6 facts

### Evidence

`_overall_status` checks only that `service_result` is non-null and then
aggregates required **client** outcomes. It ignores the E6 aggregate status,
critical application failures, direct-state contradictions and sticky effect
uncertainty. All-VERIFIED client recovery observations can therefore produce a
VERIFIED top-level result even when E6 deliberately remains PARTIAL/FAILED.

`_releases` searches limitations beginning with `release`. Real S0 writes
`observed["released"]` and, when unresolved,
`client_ownership_unresolved:<outcome>:<cause>`. The new integration fake uses
a different `release_failed:...` limitation, masking the broken integration.

`_finish` passes only eligible services to `_client_rows`; excluded optional
service/client pairs disappear from that list. `_halted` also returns an
empty coverage representation rather than preserving already-known and
not-attempted selected pairs.

### Required correction

Define a monotone, explicit product aggregation of the actual E6 decision and
per-client results. The same response cannot make an unqualified successful
run claim while its own E6 outcome says execution is uncertain or a required
state contradicted. Preserve independently verified client observations as
such; do not rewrite them to erase useful evidence. Keep residue-only UNKNOWN
separate and allowed when functional success is genuinely supported.

Expose every selected service/client pair, including optional exclusions,
blocked rows and interrupted/ halted work. Use the real S0 release contract to
surface successful and unresolved cleanup, without altering the primary
functional observation or interpreting a missing release as success. A minimal
typed projector may own the existing legacy limitation format at one boundary;
do not scatter prefix-based authority rules through the product.

### Acceptance

Drive the actual coordinator over the actual E6 applicator. Include accepted
but uncertain mutation with successful recovery reads, fresh direct
contradiction with successful behavior, critical unsatisfied action, genuine
full success and genuine successful DNS with residue UNKNOWN. Assert public
JSON, full typed result and stored record agree at each dimension.

Use actual S0 runtime/harness output for successful release, release failure,
unknown ownership and malformed cleanup. Assert first-class `releases[]` and
per-row facts both survive storage. Cover excluded optional services per
selected client and a halt after partial progress. Fix the fake to match the
production DTO, not the other way around.

## 7. S1-05 — Real filesystem failures and stage boundaries remain governed

### Evidence

Store construction calls `mkdir` before the tool reaches its use case. In
`_write`, `target.parent.mkdir` is outside the OSError-to-RunRecordPersistenceError
boundary. Real directory failures can escape while tests that override
`advance` with an already-typed exception pass. Source-tree fields permit empty
defaults despite the traceability table promising required provenance.

Stage-transition failure closes a gate, but callers must still distinguish
that pre-dispatch refusal from a runtime exception after possible effects.
Already-returned E5/E6 rows and the last durable stage must not be lost or
renamed while assembling the terminal result.

### Required correction

Put every relevant initialization/path/write/read failure behind the specified
store/use-case error contract. Lazy factories must not let construction errors
escape the public typed result. Report what is and is not durable; preserve
primary and secondary error categories without publishing unsafe detail.
Before entering the next mutation stage, observe failure of its write-ahead
transition. A closed local gate establishes no dispatch for that call, but
cannot erase uncertain effects of earlier calls.

Protect record identity on begin/load/update so one run cannot overwrite or
masquerade as another. Validate provenance conditional on stage/binding, not
by pretending early refusal records already executed a source SHA. Retention
must remain safe in the presence of malformed records.

### Acceptance

Inject actual filesystem errors at base creation, deployment-directory creation,
temporary creation/write/replace/read and terminal completion, not just canned
exceptions from an overridden store. Prove no new user-state mutation occurs
after durability is lost; earlier facts remain accessible; no local
pre-dispatch refusal is fabricated into a dispatched E6 result. Test partial
completion, primary error plus persistence error, and identity collisions.

## 8. Coexistence and scale: explicit additional concern, not wider capability

The user now requests stronger evidence of coexistence and scalability.
Record this as a scoped extension of the verification brief, not retroactive
proof that load testing was already done (10.8 explicitly excluded it).

Keep these claims separate:

1. **Regression coexistence:** existing CP-LIVE/voice/control-plane paths still
   behave correctly with the new modules installed and services opted out.
2. **Noninterference of a bounded service invocation:** only authorized
   selected identities, prerequisites and owned temporaries may be affected.
3. **Serving clients on a complex routed topology:** later S1c or another
   approved path contract, not automatically covered by S1.
4. **Concurrent writers to the same Packet Tracer session:** not authorized or
   proven by per-run `_MutationGate` or request correlation. Preserve the
   existing single-writer discipline. Do not claim a local mutex protects other
   MCP processes or CP-LIVE runners. A broader shared lease needs its own
   explicit design; no speculative engine protocol is requested here.
5. **Large-scale performance:** unmeasured until workload, bounds and metrics
   are recorded; green regression CI does not provide throughput.

### Concrete scalability work

The selected public wiring currently enumerates all devices and all ports via
`_LIVE_DEVICES_JS`, and `_client_rows` rescans all expectations of a service for
each client. With k checks per client, that nested filter performs k*n^2 checks
for k*n rows. `retained_result_for` also loads all matching full run records
into a list. These are concrete costs, not objections to line count.

Prefer target-directed inventory/read ports already supported by the backend,
with explicit completeness and ambiguity checks, rather than repeated global
snapshots. Index expectations by (service, client), rows by identity, and client/service
membership once; avoid repeated membership scans over client lists.
Use bounded/streamed history lookup with explicit behavior for corrupt records;
do not silently skip evidence to improve speed. State input, response, history
and runtime budgets at the appropriate existing boundary; derive values from
measured offline work and existing transport limits, not invented LIVE capacity.

Add deterministic operation-count/coverage tests with 2, 20, 200 and 1000
synthetic reporting clients. These exercise pure aggregation/record lookup;
they do not authorize a 1000-host physical deployment. Separately test a small
supported service selection in an increasingly large unrelated synthetic
inventory and verify exact noninterference/refusal. Do not parallelize the
shared PC command prompt or HTTP-client operations to mask algorithmic cost.

## 9. tool_registry.py: maintainability decision

The reviewed file extends beyond 5400 lines, not approximately 3000. The
important defect is the hidden, untyped session contract exposed to the new
registration, not the count itself.

Keep service behavior out of the registry. A minimal explicit binding at its
existing session/composition boundary, together with S1-01's production tests,
is authorized. Document each callable's channel, identity, return and error
semantics. Move pure helpers to their owning layer; in particular, an
application helper should not claim infrastructure independence while importing
the persistence module solely to generate an ID.

Do not extract all tool families or move thousands of lines as part of this
fix. D-8 remains a separate behavior-preserving modularization option: only
pursue it with measured coupling/change reasons, a brief, and stable tool IDs,
schemas, lazy startup and one shared bridge session. No line-count threshold,
plugin framework or second registry is justified by this review.

## 10. Place the requested sources under docs/ without losing authority

The companion `Server_PT_Docs_Overlay.zip` contains exact byte copies of the
three requested revision-2.2 files, their SHA-256 manifest, the accepted S0
act/TD-12 and the S1 assignment. Proposed root:

```text
docs/reference/server-pt/
  README.md
  source-manifest.json
  planning/rev2.2/
    Server-PT-Services-Plan-rev2.2.md
    Server-PT-Services-Review-Resolution-rev2.2.md
    Server-PT-Services-Implementer-Prompt-S0-rev2.2.md
  decisions/
    Server_PT_S0_Rev22_Approval_TD12.md
    S0_BA45_Acceptance.md
  assignments/S1_Implementer_Prompt.md
  reviews/S1_0bddc9a_Review.md
```

The originals are **historical inputs**, not a new executable instruction
chain. They contain superseded observations, old READY_FOR_REVIEW headings,
and clauses later amended by TD-12 and accepted S0 corrections. Do not edit
their bytes or silently re-run their old commands. Keep the current decisions
and implementation record in the maintained
`docs/engineering/change-briefs/server-pt-services.md`; link the index from it
and the appropriate MkDocs navigation. Add at most one contextual link for
coding agents if needed, not giant @imports into AGENTS/CLAUDE.

Copy, do not remove the Downloads sources. Verify both source/destination bytes
and Git-staged blob hashes, including newline conversion. Never overwrite a
pre-existing different archive file. Resolve inert historical namespace mentions
under the existing inventory policy without enabling aliases or broad ignores.
Run MkDocs and link checks in the actual checkout. This review created only an
overlay; it did not commit, push, or modify the user's local checkout.

## 11. Execution and delivery under the V-Model

First record this review's findings, requirement mapping, updated scope and
causal test designs in the one maintained brief; archive/link the supplied
sources. Then proceed through the coherent corrections. A technical design
change may be necessary; an incidental module extraction or another 2000-line
planning rewrite is not.

For each behavioral defect: establish RED using the real affected component,
fix the cause, then run the focused and affected suites. Keep conceptual test
oracles independent of the algorithm. Test actual production construction and
callback wiring as well as fake-backed application logic. Keep CP-SCALE,
voice, E5 default behavior, manifest identity, S0 facts and both Node harnesses
as regressions. Fresh runtime simulation is not LIVE evidence.

Bring touched files to the configured Ruff standard without suppressions. Where
mechanical format/lint debt exists, preserve the agreed format-only proof and
separate semantics changes. Do not reformat unrelated files. Preserve English
for newly maintained artifacts/diagnostics unless a documented existing public
contract deliberately keeps a localized literal.

Validate against the authoritative main resolved in this checkout; never use
the feature's upstream as the gate base. Provide both S1-only diff
`ba45d14..HEAD` and correction-only diff `0bddc9a..HEAD`. Run affected tests,
full suite, both Node harnesses, namespace inventory, docs, whitespace and the
clean exact-commit delivery gate. Exact-SHA CI belongs to the final published
candidate only; without push permission record it pending and retain honest
local evidence.

Deliver READY_FOR_REVIEW with full SHA/tree, requirement-to-test-to-result
traceability for S1-01..05, the separately labeled coexistence/scale results,
archive byte hashes, deviations, and every remaining unmeasured LIVE gate.
Do not self-approve S1, promote documentary capability records, merge, or start
S2/S3/LIVE as a consequence of passing these tests.

## Pinned source index

All paths below are relative to this repository at
`0bddc9a5203584b14869bdd9cabb071f25d528e1`:

- `src/packet_tracer_mcp/adapters/mcp/service_tools.py`: public construction.
- `src/packet_tracer_mcp/adapters/mcp/tool_registry.py`: picker/health near 900–1080;
  global inventory and registration near 2835–2912.
- `src/packet_tracer_mcp/application/use_cases/apply_enterprise_services.py`:
  `_e5_closure`, `_drift_conflicts`, `_client_rows`, `_overall_status`, admission,
  `_execute`, `_finish`, `_halted`, `_releases`, `_unsupported_paths`.
- `src/packet_tracer_mcp/application/use_cases/apply_configuration.py`:
  `apply` initial target/serial validation, `_mutation_scope`.
- `src/packet_tracer_mcp/application/use_cases/apply_services.py`:
  canonical E6 uncertainty/direct-contradiction aggregation.
- `src/packet_tracer_mcp/infrastructure/execution/enterprise_service_runtime.py`:
  `_observe`, `_with_release` (accepted S0 behavior).
- `src/packet_tracer_mcp/infrastructure/persistence/service_run_record_store.py`:
  constructor, `_write`, `load`, `retained_result_for`.
- `src/packet_tracer_mcp/domain/enterprise/models/service_run_record.py`:
  SourceTreeIdentity, identity/interruption fields.
- `src/packet_tracer_mcp/domain/enterprise/services/service_compiler.py`:
  endpoint foundation selection, `_clients`, `_add_foundation`.
- `tests/test_apply_enterprise_services.py`, `tests/test_service_tools_surface.py`,
  `tests/service_entry_fixture.py`: integration coverage and substituted seams.
- `docs/engineering/change-briefs/server-pt-services.md` sections 10.6–10.10:
  claimed traceability, deviations and scope; these are claims to verify.
- GitHub run `35299653719`, jobs `105459409880` and `105459410288`: independently
  read CI logs, not evidence of current Packet Tracer behavior.
