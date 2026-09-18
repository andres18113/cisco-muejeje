# S1 — DNS/HTTP product entry point: implementation assignment

**Authorization: S1 OFFLINE DESIGN AND IMPLEMENTATION ONLY.**
**Delivery status: READY_FOR_REVIEW, never self-approved. Risk: L.**

You are the implementer of Cisco-Muejeje, repository
`andres18113/cisco-muejeje`. Work directly, without subagents. Complete this
bounded product slice under the repository's incremental V-Model. Do not
restart the Server-PT investigation or implement the later service slices.

## 1. Accepted dependency, authority and workspace

S0 was independently accepted within its offline scope at:

```text
commit ba45d14b98e86a4f9f863111a246fad0e8d59c9e
tree   fb7aee276494c70c540ec35f0d8d2ec74405b2dc
branch feature/server-pt-s0-observation-integrity
```

Exact-SHA CI: run `35286895624`, attempt 1, all six jobs successful. The
reviewer read the quality log `105421110127` and Ubuntu/Python 3.13 pytest log
`105421110211` (5804 passed, 2 skipped, 3 warnings). This is offline evidence,
not a Packet Tracer observation. Local 5803/3 is a separate execution.

Authoritative main was separately observed at
`6263344e31ba3b0de6539d652f2cd06fc73a3562`; S0 is not yet integrated there.
Do not start S1 from that old main without S0. Use a new local branch
`feature/server-pt-s1-product-entry` starting exactly at the accepted S0 commit,
preferably in an isolated sibling worktree with its own `.venv` and editable
installation. Preserve the S0 branch. Do not merge to main, rewrite history,
force-push, delete branches, or touch another writer's worktree.

Before edits, inspect current refs, worktrees, status, interpreter, package
origin and effective instruction chain. Read AGENTS.md, CLAUDE.md when applicable,
and docs/engineering/standards.md FROM THE ACTIVE CHECKOUT. Do not infer effective
loading from file existence; record an unobservable loading check as pending.
Use only the canonical `packet_tracer_mcp` import identity. Never set PYTHONPATH,
create namespace aliases or disable the TEST_PROCESS gate.

The full source specification is the revision 2.2 content and subsequent accepted
S0 amendments in `docs/engineering/change-briefs/server-pt-services.md`.
Use its current S1 row, sections 2.1, 4.3–4.5, 4.8–4.10 and section 6, not the
older abbreviated S1 table. The role of TD-12 and the accepted S0 corrections is
preservation, not another implementation task.

This assignment makes the following S1 clarifications explicit:
- The store is `ServiceRunRecordStore` in `service_run_record_store.py`, not
  a second evidence-only store named `service_evidence_store.py`.
- "No cleanup" means no destruction of the user's topology or configured
  services. It NEVER means omit release of the verification's owned clients.
- Admission may perform authorized directed reads. The invariant is zero
  user-state mutation before all applicable gates, not zero reads throughout
  admission. Invalid JSON must still cause no bridge invocation.
- The accepted S0 golden exceptions remain in force; do not undo corrected
  ownership just to reproduce the original plan's older string-equality text.
- The starting SHA is ba45d14, not the original planning baseline 6263344.

A public push needs explicit owner authorization. A previous push does not
provide standing permission. If no push is authorized, report local verification
and exact-SHA CI as pending; do not invent completion or substitute S0's run.

## 2. Product objective and hard scope

Deliver exactly one new enterprise MCP tool:

```text
pt_apply_enterprise_services(
    intent_json: str,
    deployment_id: str,
    packet_tracer_version: str,
    run_label: str = ""
) -> JSON
```

It consumes a valid EnterpriseIntent and an existing DeploymentManifest produced
by the physical deployment path; composes E5 and E6 consistently; applies only
the required E5 scope; derives foundations from real typed E5 verification rows;
applies and verifies DNS and HTTP; returns and persists attributable per-client
results, including failures, omissions, uncertainty and owned-resource release.

The initial supported service path is R-NET-01: one site, one segment, static
Server-PT and selected static PC-PT clients, no routed service client. The
acceptance fixture is one access switch, one server and two PCs on the same
segment/VLAN. Reject a requested path requiring unsupported inter-switch/L3
work outside the defined scope rather than claiming same-subnet addressing
alone establishes the path. Do not add a routing feature to make a fixture pass.

No new SMTP, POP3, email, DHCP, NTP/TFTP features, HTTPS content/behavior,
nslookup parser, event framework, qualification runner, new .pts, muejeje.pts,
Runtime V6, engine protocol, bridge endpoint, transport or GUI automation.
No changes to EXTENSION/, CP-LIVE, voice or PoE as incidental cleanup.
No destructive topology cleanup. No real Packet Tracer contact, including
"read-only" probes. Offline tests use isolated fake channels/stores and the
existing allowed local test-server patterns, never an operator's running bridge.

Preserve the physical-only contract of pt_live_deploy and existing callers of
compose_enterprise_reference. Do not expose the always-cleanup reference executor.
Do not expose experimental capabilities or caller-supplied foundation statuses.

## 3. First commit: the definition side of the V

Before product behavior changes, append a compact S1 design/acceptance section
to the existing change brief. Do not copy the complete planning history into a
second document. Record the current starting SHA, tree, branch, main ref, risk L,
approved scope, requirements, interfaces, error/effect rules and test design.
Reference the independent S0 acceptance and append its now-observed CI result;
retain earlier pending reports as historical.

Requirements in scope:
- R-ENTRY-01..07, 09..11; preserve R-ENTRY-08 from S0.
- R-NET-01/02; R-CAP-01..07; R-HTTP-01..03; R-DNS-01..03.
- R-COV-01/02; R-RET-01/02; R-QUAL-02 product boundary and R-QUAL-04 records.
- R-SEC-02..04 as applicable without building S2 secret resolution.
- R-REG-01..03 and the accepted S0 evidence/uncertainty invariants.

For each group map requirement -> observable acceptance predicate -> owning
symbol -> test level -> negative control -> evidence to retain. State why
LIVE is not part of offline acceptance. Distinguish inherited code, specified
new behavior and unresolved measured capabilities.

Resolve these module contracts in that section before coding:
1. Inputs/outputs of the new use case and its injected ports.
2. ServiceStageRuntimes(configuration: ConfigurationRuntime, services: ServiceRuntime).
3. Complete admission order and which calls are reads, mutations or owned cleanup.
4. E5 mutated/retained/excluded partition, verification scope and hashes.
5. Foundation derivation and conflict precedence.
6. Run record lifecycle, persistence failure containment and retained reuse.
7. Per-client output schema and required/optional aggregation.

Source inspection may refine internal signatures; it must not weaken the scope,
provenance or acceptance rules. Complete routine work autonomously. A material
change of contract requires a specifically identified design decision, not a
silent workaround. Do not produce an indefinite planning exercise.

## 4. Integration map and responsibilities

All paths below are under `src/packet_tracer_mcp/` unless stated otherwise.

| Component | Scope |
| --- | --- |
| `application/use_cases/compose_enterprise_reference.py` | Add opt-in service composition and publish the exact service capability resolution used; add the configuration-policy path for client DNS. Preserve pre-existing caller behavior and hashes where no service composition is requested. |
| `domain/enterprise/services/service_compiler.py` | Reuse DNS/HTTP actions and dependencies; target-aware capabilities; consume required/verification_required; advisory client DNS expectation; per-client coverage. |
| `domain/enterprise/models/service_plan.py`, `service_runtime.py` | Only additive S1 fields/types needed for required expectations, target-aware evidence and output; no new service family. Preserve S0 facts and legacy compatibility. |
| `domain/enterprise/models/configuration.py` | DNS_SERVER_ADDRESS_REQUIRED or the existing appropriate issue vocabulary. No DHCP delegation implementation. |
| `application/use_cases/apply_configuration.py` | P-E5-2 explicit exclusions and scoped verification, with backward-compatible defaults. Do not redesign the E5 error pipeline (D-9). |
| `application/use_cases/foundational_evidence.py` | Extract a shared plan-agnostic endpoint-core predicate; add derive_service_foundational_statuses without duplicating or weakening E9 behavior. |
| `application/use_cases/apply_services.py` | Use per-target operation capability decisions and required/optional aggregation; preserve the canonical mutation decision, TD-12 snapshots and corrected prerequisites. |
| `infrastructure/catalog/service_capabilities.py` | Explicit build/model/operation records, consistency validation and provenance. No enum-driven grants. |
| `application/use_cases/apply_enterprise_services.py` (new) | Own admission, coordination, persistence lifecycle, effect scope, foundation derivation, containment and result assembly through injected ports. |
| `infrastructure/persistence/service_run_record_store.py` (new) | Implement the run-record port: contained local paths, validated typed records, atomic write/rewrite, corrupt-record refusal and bounded loading. |
| `adapters/mcp/service_tools.py` (new) | Register the tool and translate JSON to/from the application contract. No duplicate orchestration, transport selection policy or domain rules. |
| `adapters/mcp/tool_registry.py` | Minimal reviewed registration/dependency wiring using its existing closure-scoped bridge session. Do not extract the whole registry. Own its Ruff debt. |
| `infrastructure/execution/enterprise_service_runtime.py` | Reuse accepted S0 readers; only the explicitly advisory CLIENT_DNS_SERVER extension is in S1, after checking the documented signature. No claim of runtime support for it. |
| `docs/tools.md`, existing brief and focused tests | Public contract, limits, traceability and evidence. Update navigation only if necessary. |

Use existing models/ports wherever they own the behavior. New store/run-record
contracts belong to the appropriate application/domain boundary, not concrete
filesystem dependencies imported by domain. Do not create a general orchestration
framework or a second evidence vocabulary. Names in the old plan are not proof
that a symbol already exists: inspect before editing.

## 5. Admission and one fixed runtime path

Follow the A1..A10/E1..P1 flow in plan section 2.1. Before the first E5 mutation:

- Parse the intent; validate tool argument shape and limits. Resolve the exact
  deployment manifest from the existing store; missing/corrupt/unbound identity
  is a typed refusal, not a guessed target.
- Require caller version == manifest backend version, and independently validate
  the current environment against the manifest using existing mechanisms.
  A caller string agreeing with a stored string is not a current observation.
- Enforce ImportIsolationPreflight and readiness. Select the existing channel
  once and bind both E5 and E6 runtime dependencies to it for this invocation.
  E6 receives S0's typed dispatch_and_wait. No fallback or mutation redispatch
  after an ambiguous outcome. Preserve authentication and result correlation.
- Create the required write-ahead record before effects. Compose the intent with
  the manifest, exact capability snapshot and explicit configuration policy.
  Require physical identity/hash equality and exact host/client/interface binding.
- Decide eligibility for all requested services, each action and each required
  expectation on its actual target. Reject a required ineligible service before
  E5; exclude an optional ineligible service before deriving C and still report
  its selected clients. Optional never means permission to dispatch UNKNOWN.
- Derive C, perform directed endpoint drift reads, and validate any retained
  result. All failures keep zero user-state mutations and typed causes.

Use actual runtime factories/ports in the production path. Offline tests may
inject deterministic safe collaborators; never add a public bypass flag or an
`if pytest` branch. Include a separate test proving the real production
TEST_PROCESS guard refuses under pytest BEFORE contacting a channel.

Keep the workflow serial for this scope. Reuse existing exclusive/session
admission where available; do not promise safe concurrent invocations over a
shared terminal/client bag without an enforced boundary.

## 6. Client DNS and bounded E5 application

`derive_service_policy` derives the DNS server from an eligible DNS service's
explicit address. Missing explicit DNS address => DNS_SERVER_ADDRESS_REQUIRED.
Incompatible requested DNS authorities must refuse rather than arbitrarily
choosing one. Do not implement the deferred two-pass address allocator.
The service address must agree with the actual E5 host address; preserve the
compiler's existing SERVICE_ADDRESS_MISMATCH validation.

Prove the whole configuration path, not just a policy object:
MCP intent -> composition -> ConfigurationPolicy.dns_server ->
SetEndpointStaticAddress.dns_server -> actual endpoint runtime call arguments.
Preserve user input without hidden mutation and preserve the physical manifest
identity. Do not configure the optional client's DNS getter instead of this path.

Let P be all typed E5 action IDs, C the closure of the eligible E6 foundational
action IDs over depends_on and apply_dependencies. First application:
mutated=C, retained=empty, excluded=P-C. For a valid re-run, C partitions into
mutated and eligible retained IDs; exclusions stay P-C. Enforce disjointness,
complete identity accounting, no foreign/duplicate IDs, no mutated dependency
on an excluded action and the existing retained reverse-dependency rule.

P-E5-2 adds excluded_action_ids with an empty default to ConfigurationApplicator.
Excluded actions receive SKIPPED/OUT_OF_SCOPE, never fabricated retained APPLIED
rows. Omitted exclusions preserve the old contract. Do not shrink/re-hash a copy
of the configuration plan to evade its scope validation. Verification and target
requirements outside C must not accidentally block or be applied as part of S1;
report their exclusion rather than global success for the complete E5 plan.

A non-empty conflicting endpoint address refuses before effects. An unreadable
required identity/drift observation is not an empty endpoint. Disclose that the
existing access-port/VLAN declarative path does not independently pre-read every
field; do not manufacture equivalence. Exactly C, and no DHCP pool, routing,
security, voice or unrelated endpoint action, may reach the E5 mutating runtime.

After E5, contradictions, missing results and effect uncertainty stop E6 effects.
Contain the documented D-9 defect: an E5 row with SESSION_FAILED or the legacy
missing-result representation is not evidence of non-execution or a CLEAN run.
Record e5_effect_uncertain and run-level UNKNOWN as specified by R-RET-02. Keep
that compatibility recognition isolated and tested; do not spread message parsing
or redesign E5 in this slice.

## 7. Foundations, capabilities and per-client evidence

Derive foundations from executed verification rows for C and the exact source
configuration plan ID/hash. Reuse the endpoint-core predicate's freshness,
method, IPv4/netmask field statuses, convergence details, device/interface and
subject checks. Conflicting evidence must not be resolved by choosing success.
A valid PARTIAL endpoint core may satisfy only its matching service foundation;
it never rewrites the E5 row to VERIFIED or verifies DNS/gateway/other fields.
Aggregate VERIFIED without attributable core proof is not a substitute.

The catalog must use explicit build evidence, not stamp the supplied version
onto a fixed SUPPORTED table. Preserve the legacy baseline dimensions needed by
existing consumers at 9.0.1.0858; any other build starts UNKNOWN. Resolve apply
by actual target model + action operation; resolve client verification by client
model + kind, not by the server's profile. Use one resolution consistently for
compilation, admission and execution. Reject duplicate/contradictory records
before conversion to a dictionary could silently discard one.

RD-8 permits the first DNS/HTTP product slice to use documentary_baseline records
as a disclosed compatibility decision. This does not turn them into recorded_run
or prove the corrected reader's LIVE behavior. New measurements/promotions need
build, executed SHA, transport, target model and run identity. No public parameter
may inject experimental support. Preserve S0's accepted golden exceptions.

CLIENT_DNS_SERVER is advisory: compile an optional per-client expectation and
its UNKNOWN capability. Do not execute it through the product as a SUPPORTED
reader or use it to gate the first slice until M-DNS-3 is qualified. Its proposed
runtime implementation may be tested offline against documented shapes. Do not
infer support from another getter or claim DNS-server attribution from cached ping.

For every selected client, return DNS resolution and negative-control results,
HTTP-by-address, and the specified HTTP-by-hostname dependency/composition where
requested. Keep per-check observation, cause, freshness, claim level and limits;
then aggregate per service/client without hiding missing, skipped, blocked or
recovery rows. Never promote an untested client from a server-level success.
No sampling is needed for the two-client acceptance; any future sampling must
label unsampled clients NOT_ATTEMPTED under R-COV-02.

Retain the accepted difference between functional success, effect uncertainty
and residue uncertainty. In particular, an attempted partial-footprint DNS add
may leave dirty_state UNKNOWN even when the behavioral claim is VERIFIED.
Expose that limitation and all unresolved client releases in the public result
and persisted record. A "no topology cleanup" requirement never removes the
owned-client finalization obligation.

## 8. Persistence and reuse are part of the product, not a final save call

Implement section 4.8 through ServiceRunRecordStore, under contained paths:
`data/services/<deployment_id>/<run_id>.json` and `_admission/<run_id>.json`.
Use safe_name_component and resolve_within, validate on load, and tmp + atomic
replace as the existing pattern. run_label is display metadata, not authority to
choose a path or overwrite another run. Generate run IDs independently.

Persist full typed E5 and E6 results and identity, not only compact counts:
plan IDs/hashes, manifest hash, environment fingerprint, executed source SHA,
build, fixed channel, capability provenance, stage outcomes, selected clients,
mutated/retained/excluded IDs, uncertainty, release results and limitations.
Retain TD-12 received_mutation, canonical cause and separate call_error.

A1/A2 failures have no run record because no valid bound identity exists. A3–A5
failures produce an unbound refusal record if writable. A6 failure refuses before
effects. Stage transitions are written before the next effectful stage begins.
If persistence fails after effects, keep the last durable persisted_stage, report
persist_error separately from the primary error, and dispatch no further user-state
mutation; only bounded observation and already-owned resource cleanup may continue.

Specify the concrete enforcement point BEFORE implementation. An application-owned
guard around the existing runtime ports or an appropriately scoped existing hook
may enforce this; do not copy either applicator's orchestration. A test must fail
the store while additional work is available and prove no later mutating runtime
call occurs, not merely that the final response contains persist_error.
Do not claim per-action crash recovery if only stage boundaries are durable.
An interrupted record never proves work did not execute and must not auto-resume.

Retained E5 reuse requires R-RET-01 identity equality, completed eligible prior
results and fresh prerequisite re-verification. The full rows must survive store
round-trip. No reuse of an interrupted/uncertain record or conflicting evidence.
Re-entry into a mutation scope is NOT automatic retry permission: every new
explicit invocation still passes admission, drift, replay-policy and effect checks.
Do not replay an ambiguous action merely because its prior result was not retained.

Public responses and records must exclude bridge tokens, raw generated scripts,
unsafe raw exception payloads and secrets. Use typed, bounded diagnostics and
redaction tests for raw/escaped/encoded sentinel forms. Do not add an email secret
resolver merely to test redaction in S1.

## 9. Verification side of the V: concrete acceptance groups

Before each behavior change establish causal RED where meaningful, then implement,
GREEN, affected tests and broader verification. Do not use import errors or a newly
added enum's absence as the sole evidence of a behavioral regression. Never replace
production decisions with a copy of the algorithm in the test oracle.

| Level/group | Required positive and negative controls |
| --- | --- |
| Unit — admission | Invalid JSON/missing manifest/version mismatch/foreign process/TEST_PROCESS/capability unknown; zero mutations on every rejection and no bridge on invalid JSON. Record reads and order explicitly. |
| Unit — catalog | Exact baseline build vs another build; client unknown while server supported; duplicate and inconsistent records; documentary provenance; advisory getter remains UNKNOWN; no experimental override at public boundary. |
| Unit — E5 scope | First application without fabricated retained results; disjoint partition; foreign/duplicate IDs; excluded dependency; retained reverse dependency; default old API behavior; no out-of-scope rendering or effects. |
| Unit — foundations | PARTIAL with complete attributable core succeeds; VERIFIED aggregate without core, wrong hash/ID/interface, stale/missing freshness, failed field or contradictory row does not. Existing E9 derivation remains unchanged. |
| Unit — store | Create/rewrite/load, atomic replacement failure leaves last valid file, malformed record refusal, traversal/unsafe IDs, interrupted record, exact identity retention, no path from run_label. |
| Integration — real product components | Real input models, composition, compilers, both applicators, foundation helper and real store in a temporary directory, with injected runtimes only at external boundaries. Two PCs get separate results; runtime call arguments include the DNS address; exact C reaches E5. |
| Integration — containment | Existing endpoint conflict, missing or uncertain E5 result, store failure before/after first effect, stale retained rows, one client's contradiction, skipped optional service and unknown optional reader. Assert dispatch traces and absence of forbidden calls. |
| Integration — evidence | TD-12 and S0 facts survive JSON and store; per-client outcome agrees with rows; DNS partial footprint and cleanup failure remain visible; no blanket VERIFIED; redact sentinels. |
| Offline system — MCP | Exactly one new enterprise tool registered; schema matches the four inputs; public tool route invokes the same application use case, not a test-only helper; TEST_PROCESS refusal on default production wiring; existing surfaces unchanged. |
| Regression | Existing E5/E6/E8/E9, namespace, bridge authentication, replay registry and S0 table/harness regressions. No fixture simplification that evades the production path. |

Prefer the plan's cohesive test locations: test_apply_enterprise_services.py,
test_service_run_record_store.py, test_service_tools_surface.py,
test_configuration_mutation_scope_exclusion.py, test_service_policy_derivation.py,
test_service_foundational_evidence.py, and test_service_client_capabilities.py;
extend the relevant existing capability/aggregation tests. File count and test
count are not acceptance targets. Positive integration fixtures must be valid
through the real designer/compilers and the physical-manifest contract, not manually
patched to skip them.

## 10. Commit and verification sequence

1. Design/acceptance section committed before behavior changes.
2. Mechanical debt only on the files the slice must touch. Separate format-only
   changes (per-file AST equality) from lint fixes (docstrings/imports may change
   AST). Run appropriate regressions. Do not revive the consumed namespace
   authorization, add noqa, weaken Ruff, or reformat unrelated files.
3. Implement cohesive units: policy/capability/eligibility; bounded E5 and shared
   foundations; record lifecycle/containment; complete use case/per-client response;
   thin MCP registration and docs. Coupled changes may share a coherent commit.
   Every unit carries its tests; no dead code just to satisfy substring tests.
4. Self-review the full diff, requirement traceability and unchanged contracts.
5. Run focused tests, the relevant integration/system tests, both S0 Node harnesses,
   full pytest with skip reasons, documentation build, namespace inventory,
   whitespace and the clean exact-commit quality gate.

Use the checkout-local interpreter. Prove the authoritative main ref before the
quality gate. For this maintainer checkout it is normally `cisco/main`; it is not
a universal name. The full gate compares to authoritative main, NOT to the new
feature upstream or merely ba45d14. Additionally report the S1-only diff from
ba45d14 so the reviewer can separate inherited S0 from new work.

```text
<venv-python> -m pytest -q -rs
<venv-python> -m mkdocs build --site-dir _site
<venv-python> scripts/namespace_inventory.py
git diff --check
<venv-python> scripts/quality_gate.py --base <verified-main-ref> --delivery-commit HEAD
```

Record commands, interpreter, SHA/tree and outcomes. Recheck clean status after
verification. Update CI facts append-only in time: a later run supersedes a
pending report, but do not rewrite history or relabel old results as a new SHA.
After an explicitly authorized push, inspect the six jobs and logs for the actual
S1 delivery SHA. Until then, exact-SHA CI is pending and final acceptance is not
claimed. Do not start the next slice as incidental work.

## 11. Delivery and later LIVE boundary

Return READY_FOR_REVIEW with full SHA/tree, branch/base, commit-to-requirement map,
changed paths, exact verification results/skip reasons, deviations, remaining
capability gates and the S1-only diff boundary. Retain the updated single brief,
working code/tests and the executable two-client offline example. Do not return
only a plan or a self-review summary claiming the task is complete.

LIVE acceptance is a separate future authorization: one explicitly identified
operator-owned sample topology (never the university topology), one segment,
DNS + HTTP for two PCs, through the actual MCP entry point, exact executed SHA,
build/channel, per-client results, persisted record and owned-client release.
Leave the user topology and services in place. Stop at the first contradiction
and preserve evidence; do not repair or repeat automatically. None of that is
authorized to run now. Until the record exists, product usability is offline
verified only, with documentary capability provenance disclosed.

Rollback of the code does not undo Packet Tracer state and does not delete run
records. Never describe git revert as restoration of a topology. No merge to
main, cleanup of user resources, capability promotion or S2 work is part of
this assignment.

Use targeted searches and bounded file/log reads, expanding as needed to verify
conclusions. Keep brief user-facing updates that state a concrete finding or
completed milestone. Write maintained code/docs/tests and the technical delivery
in English, with a short Spanish summary. Do not use subagents.
