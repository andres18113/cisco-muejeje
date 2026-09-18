# Server-PT S0 — technical decision and binding handoff TD-12

**Decision: APPROVED_WITH_BINDING_AMENDMENTS, S0 OFFLINE IMPLEMENTATION ONLY.**

The execution contract is **revision 2.2 plus this addendum**, not the revision 2.2 prompt alone. The implementer must incorporate TD-12 into the versioned change brief before behavioral implementation. This is a technical decision on the design; it does not certify implemented behavior, authorize LIVE, authorize S1 or later slices, or permit a merge to main.

## 1. Reviewed identity and evidence

Repository baseline: `andres18113/cisco-muejeje`, `main@6263344e31ba3b0de6539d652f2cd06fc73a3562`. The GitHub branch collection was read independently during this review and returned that SHA. The operator's Windows working-tree state and instruction-loading state were not independently observed.

| Supplied artifact | SHA-256 | Lines |
| --- | --- | ---: |
| Server-PT-Services-Plan-rev2.2.md | `1332e4a9a7387c498821ccf09c3c5d9ba39f7e10b0a141f113412650e2309478` | 2106 |
| Server-PT-Services-Implementer-Prompt-S0-rev2.2.md | `d689d1812349a2ce0063c5c41fdab431cc3f1c6b554043f3cf5e0ddfba26312e` | 416 |
| Server-PT-Services-Review-Resolution-rev2.2.md | `27fc567980d121c3d2bf2b50eb762c3b6791e3a31727d175c38109b7d3bf983e` | 1355 |

The embedded section 7.1 prompt is byte-identical to the standalone file. The separately named probes directory was not attached, but both full sources were recovered from the resolution's appendix. Their SHA-256 hashes match the resolution. After source inspection, both were executed in the review sandbox with Node 22.16.0 and CPython 3.13.5, without repository imports, installs, or Packet Tracer contact.

The reproduced output is byte-identical to the appendix: 8640 fact tuples (29 admitted, including the default-disposition legacy tuples, and 8611 inconsistent), 17 generated-row scenarios, and `ALL CHECKS PASSED`. A separate predicate-overlap check found zero overlaps. These are specification checks, not 8640 repository tests and not an integration/LIVE qualification.

## 2. Accepted design decisions

C1's digest-collision and DNS-membership countermodels are addressed at the specification level: compare actual typed values, make the post-read unconditional, keep diagnostic hashes non-authoritative, and distinguish observed scope from the effect footprint. Accept RD-11 for S0: an attempted DNS add has PARTIAL footprint and unknown residue, while a proven skipped add is NO_OP within the stated scope. Do not widen observation to the DNS table during S0.

C2's competing classification rules are replaced by the canonical validated decision. Accept the table's treatment of row 10, exceptions, malformed outcomes, legacy defaults, and inconsistent tuples. Status, frontier and sticky uncertainty must come from that decision, not independent interpretations of raw fields.

B3 remains accepted in design: actual generated scripts must execute under the Node stub harness, and the identified incorrect expectations may change for their stated requirements. G1–G4 remain owned by their later slices and measurement gates.

A VERIFIED service claim and UNKNOWN residue describe different dimensions. Never convert the former into a cleanup, compensation, retry, capability-promotion, or whole-environment safety claim. A later NO_OP run does not erase an earlier run's UNKNOWN record.

## 3. TD-12 — complete the result boundary before implementing behavior

### TD-12.1 Preserve the original classifier input

**Evidence.** The baseline `ActionApplicationResult` in `domain/enterprise/models/configuration_runtime.py` has no `applied` field. Revision 2.2 section 4.4 and prompt item 1 add seven observation fields plus `residual_change`, but still do not retain that original input. By contrast, the disposable checker's `apply_action()` dictionary retains `applied`, and its round-trip test reads it back directly. The probe therefore tests a wider result shape than the specified DTO.

**Counterexample.** A received tuple `ACCEPTED / CORRELATED / SATISFIED / CHANGED / COVERED / attempted=True / applied=False` is inconsistent and must remain UNKNOWN, closed and sticky. After dropping `applied`, reconstructing it as `dispatch == ACCEPTED` converts the tuple into row 12. Reconstructing it from a derived status is also prohibited: the output is not the original input.

**Binding amendment.** Add an optional `received_mutation: RuntimeActionMutation | None = None` field to `ActionApplicationResult`, in the same shared model file already in S0 scope. For E6, populate it with a defensive, sanitized copy of the exact typed mutation supplied to `decide_mutation`, including `applied`, original disposition, original failure code, cause, and all seven observation fields. No script body, credentials or raw pre/post page contents belong in this snapshot. Do not mutate it after classification.

The existing flattened observation fields remain available for the public result. Status, disposition, failure code and residual-change output come from the canonical decision. Preserve the original cause in the snapshot and the decision's canonical classification reason separately in the result/limitations, so an incidental error string cannot hide `inconsistent_facts`.

Cache/use the decision computed for each action during the application. On an explicit deserialization/audit re-evaluation, call `decide_mutation` on the retained input snapshot, never on a synthetic mutation reconstructed from decision outputs. An old result without the snapshot remains a legacy record; it does not acquire new fact-bearing authority by inference. Do not fabricate `applied` for such a record.

The new field is additive. Baseline-shaped input JSON must still validate, old producers need not populate it, and compact legacy summaries must retain their existing shape. Document the new full-JSON key. No new general-purpose evidence subsystem is required.

**Acceptance.** Through the real DTOs, applicator, journal and serializer, round-trip valid, inconsistent, legacy, exception and missing-result cases. Compare the full retained classifier input and re-derived decision, not just the happy-path status. In particular, the inconsistent `applied=False` input above must remain inconsistent after the round-trip. Check that modifying an original mutable object after application cannot change the stored snapshot. The review's dictionary-snapshot experiment is supporting design evidence only; the actual model test remains mandatory.

### TD-12.2 Do not synthesize channel acceptance from a missing list item

This clarifies the provenance requirement of row 7 and supersedes the unconditional sentence in prompt item 5 that maps any missing runtime mutation to row 7.

A missing/invalid action row **inside an observed ACCEPTED, CORRELATED batch envelope** is row 7: APPLIED with RESPONSE_MALFORMED, unknown disposition and sticky uncertainty. The Packet Tracer adapter has that envelope and must return the classified typed result for every requested action.

A missing item at the application port **without any evidence of acceptance for that item/batch** does not prove ACCEPTED. Treat it as a local runtime-boundary contract error and use the row 15 uncertainty path, with an explicit sanitized cause such as `exception:MissingRuntimeMutationResult`: UNKNOWN, SESSION_FAILED, closed frontier, sticky. An empty result list from a runtime that made no dispatch must not be labeled proof of dispatch. This preserves the table and requires no new transport, endpoint, or service family.

**Acceptance.** Test both a correlated batch missing one row and a runtime returning an empty list without dispatch. The first retains proven acceptance; the second makes no acceptance claim. Both retain uncertainty and block dependent effects. A missing result is never inferred to mean successful cancellation or non-execution.

## 4. Required verification boundaries, not new product scope

The supplied checker is disposable and must not be copied as the product implementation or its complete oracle. Its row validator accepts `ok=1, changed=1` through equality-based membership, although the prompt requires actual booleans. Its simplified `run_result()` labels a stand-in bundle from frontier/sticky alone; it does not execute the product's independent verification and aggregation.

Enforce the existing row-shape contract strictly in the real runtime: flags must be actual booleans; `ok`/`changed` are exact bool-or-null values; numeric 0/1, strings and wrong-shaped diagnostics are invalid. A completed post-read requires a boolean `ok`, even when the pre-read failed. `changed` requires both reads; otherwise it is null. Digests have no semantic authority. Tests must include these boundary cases, omitted keys, duplicate and foreign identifiers, and the documented skip shapes.

The acceptance tests must exercise the real generated payload, row parser, canonical decision, applicator, journal, evidence adapter and Pydantic round-trip. Independent client evidence, capability gates, dependency gates and cleanup failures must not be replaced by the probe's synthetic `bundle` expression. Keep the existing S0 positive controls and the causal RED/GREEN requirement; unknown behavior is not permission to weaken tests.

## 5. Small document corrections in the initial change brief

- Reconcile the plan's section 1.1 current-session `/context` claim with the resolution's statement that it was not run. Record this planning session as pending, or explicitly attribute a previous observation to its historical session. The implementer checks its own instruction sources; a fresh observation does not retrospectively certify another session. Use the product-specific instruction inspection, rather than treating `/context` as a universal command.
- Distinguish the executable baseline `6263344` from the rejected rev2.1 specification. The DNS RED text incorrectly says a true-returning incorrect/replacing add always produces baseline CLEAN. At the baseline, `add(...) || getter(...)` may return true, yielding APPLIED with default UNKNOWN disposition and therefore UNKNOWN residue. The true regressions for that case are skipped post-read, absent footprint/cause, wrong frontier on an unsatisfied record, and absent skip-on-present behavior. Record the measured baseline of each case; do not force a fabricated baseline CLEAN assertion. This correction also applies to any earlier reviewer wording that blurred the two baselines.
- Incorporate TD-12 into the relevant DTO, item 5 and round-trip clauses of the committed plan and embedded prompt. Label the result `rev2.2 + TD-12, S0 approved for offline implementation; later slices not approved by this act`. Do not rewrite unrelated chapters or create a new general planning round.

## 6. Implementer kickoff

Use this text together with the revision 2.2 plan and S0 prompt:

> Implement S0 only under the technical contract `rev2.2 + TD-12`. Read this addendum first; it takes precedence over the superseded result-snapshot, missing-row and editorial clauses of rev2.2. Verify the active checkout, branch, authoritative main reference, starting SHA and instruction sources. Before behavioral edits, commit the updated change brief containing TD-12 and the required focused test inventory. Then execute the approved S0 prompt, including the real DTO round-trip and both missing-result tests. Do not ask for another general planning round; stop and report a concrete contract conflict only if evidence requires a material change beyond this scope. Preserve all S0 exclusions, the canonical namespace, exact-SHA delivery gates and independent review. No subagents, no LIVE, no product bridge startup, no S1, no main merge, no changes to EXTENSION. Local ephemeral test servers and temporary test mailboxes are allowed only as isolated offline tests. Deliver READY_FOR_REVIEW with commit identity, focused and broader results, actual Node harness execution, limitations and the exact delivery CI status. Do not claim capability promotion or Packet Tracer functionality.

A repository write is the implementer's explicitly assigned S0 work, not an action executed by this review. No push or merge is authorized by this addendum alone. If the delivery CI cannot be run on an authorized remote commit, report that gate as pending; never substitute another SHA's green run.

## 7. Acceptance boundary and sources

S0 approval concerns design readiness for offline implementation under the amendments. It is not implementation acceptance. Final acceptance requires actual code/diff review, legacy compatibility, focused regressions, generated-script harness execution in CI, the full required suite and quality/documentation gates, and independent audit of the exact delivered SHA. S1 and all engine, HTTPS, mail, DHCP, cleanup and provenance qualifications retain their existing owners and explicit authorization gates.

Source basis: the three hashed supplied artifacts; their embedded probe sources; GitHub `AGENTS.md` and `docs/engineering/standards.md` at 6263344; `domain/enterprise/models/configuration_runtime.py` (RuntimeActionMutation, ActionApplicationResult, mutation_execution_status); `domain/enterprise/models/execution.py` (journal builder and residue rule); `infrastructure/execution/enterprise_service_runtime.py` (batch mapping and DNS short-circuit). Cisco's public DnsServerProcess reference confirms that `getARecordWithAddress` addresses the specified record and separately lists the database enumeration methods; no new LIVE claim was inferred from it.

Review artifacts: `verification.json`, reproduced probes and output, and `review_boundary_checks.py` / `independent_boundary_checks.json`. All user-supplied originals remained unchanged in the review sandbox.
