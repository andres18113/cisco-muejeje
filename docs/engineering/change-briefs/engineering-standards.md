# Engineering standards change brief

## Record

- Status: implemented; local verification complete; exact-SHA CI and independent
  audit pending
- Risk: **L**
- Baseline: `cisco/main` at `9cb1c1ceb1e77e17daa5a06e4bf21a52db932479`
- Delivery branch: `chore/engineering-standards`
- Rationale: this change governs public engineering policy, security and evidence
  controls, and CI behavior. Diff size is not a risk input.

## Problem and boundaries

Repository instructions currently mix durable safety constraints with obsolete
branch, language, and tool statements. The repository has no executable Python
lint or format gate, and it does not define one proportional V-Model workflow
that connects requirements and design decisions to verification.

In scope: consolidate shared agent authority; define the incremental V-Model,
coding, architecture, error, evidence, and autonomy rules; add a pinned Ruff
lint/format gate for changed Python files; preserve the four-job pytest matrix;
and add independent quality and documentation-build CI jobs.

Out of scope: production behavior, Packet Tracer LIVE execution, public contract
changes, mass translation or formatting, historical evidence changes, IoT work,
main-branch merge, and ISO certification claims.

## Requirements and acceptance

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| R1 | `AGENTS.md` is the shared authority; `CLAUDE.md` imports it without duplicating shared rules. | Diff review; docs build where linked content is published. |
| R2 | S/M/L classification is objective, independent of diff size, and can only rise when risk is discovered. | Standards review against the approved definitions and escalation rule. |
| R3 | One proportional brief records problem, scope, acceptance, architecture, invariants, and test design before implementation. | This committed brief and the standards template. |
| R4 | The V-Model maps requirements, system design, architecture, and module contracts to the corresponding verification levels, followed by review, traceability, CI, and independent audit. | Standards review and requirement-to-verification table below. |
| R5 | Coding, layering, error, fail-closed, provenance, retry, and evidence-state rules are explicit without changing production contracts. | Diff review; full offline suite remains green. |
| R6 | Ruff lint and format use one exact version and one local/CI entry point, with no global ignores or expanding exclusions. | Gate positive control passes; deliberately invalid fixture fails; quality CI passes. |
| R7 | Existing debt is explicit and adoption is incremental: changed/new Python is clean without a repository-wide rewrite. | Gate file-selection tests; debt snapshot recorded after implementation; diff review. |
| R8 | Windows/Linux × Python 3.11/3.13 pytest remains intact; docs and quality controls run on the final SHA. | Four pytest matrix jobs plus `docs` and `quality` jobs succeed for the final commit. |

## Architecture and invariants

The change adds no production dependency and does not alter package/runtime
layers. `pyproject.toml` remains the single Ruff configuration and dependency
authority. A small cross-platform Python entry point computes changed Python
paths and delegates lint and format checks to Ruff. CI and developers call that
same entry point with the checkout-local interpreter.

The following invariants must hold:

- `src/packet_tracer_mcp` and Packet Tracer extension behavior are unchanged.
- No LIVE command runs and no historical evidence file changes.
- The production/test namespace contract and checkout-local interpreter gate
  remain fail-closed.
- The bridge authentication and path/JavaScript injection controls remain
  normative.
- Capability, execution, and evidence states remain distinct.
- No test, security control, or acceptance criterion is weakened to obtain green.

## Verification design

| V-Model definition side | Verification side for this change |
| --- | --- |
| R1-R8 requirements | Acceptance traceability in this record and final delivery. |
| CI and instruction-system design | Documentation build and workflow inspection. |
| Repository/CI architecture | Integration tests of Git file selection plus final CI jobs. |
| Quality-gate module contract | Tests for Git selection, invalid base, and clean/violating Ruff inputs. |

The quality gate is behavioral, so its tests are written RED first and use a
known violation plus a clean positive control. Documentation-only rules do not
receive artificial unit tests. System verification is the full offline pytest
suite. LIVE verification is not applicable because production and Packet Tracer
behavior are excluded. Independent audit remains pending after delivery; this
work may reach only `READY_FOR_REVIEW`.

The initial design proposed strict MkDocs warnings as errors. Local verification
showed two pre-existing broken-link warnings in immutable historical evidence.
The control was narrowed to a successful documentation build rather than modify
evidence or add a global warning ignore. This remains within R8's approved docs
build contract.

## Deferred baseline debt

The full-tree Ruff snapshot at the governed baseline plus this change reports
7,103 lint findings and 541 files that would be reformatted. This change does
not suppress or rewrite that legacy debt; the executable boundary is complete
new and changed Python files. MkDocs also reports two pre-existing links from
historical evidence to the repository-root `handoff.md`; they remain unchanged.

## Planned requirement-to-verification traceability

- R1-R5: focused document review, `mkdocs build`, and `git diff --check`.
- R6-R7: focused quality-gate tests, explicit negative/positive demonstrations,
  Ruff on changed Python, and quality CI.
- R8: local full suite and docs build, followed by all required final-SHA jobs.

## Local verification results

- RED: `tests/test_quality_gate.py` failed collection because the gate module did
  not exist; after the causal implementation, all 4 gate tests passed.
- Affected tests: 15 passed across the gate, documentation style, and worktree
  isolation tests.
- Full offline suite: 5,025 passed, 3 skipped, and 3 pre-existing pytest
  deprecation warnings in 286.24 seconds.
- Incremental Ruff gate: 2 changed Python files passed lint and format checks
  with Ruff 0.16.7. An unknown base returned the fail-closed exit status 2.
- Documentation: MkDocs completed successfully; the two historical-link warnings
  listed above remain deferred.
- Workflow configuration parsed successfully as YAML. `git diff --check` passed.
- CI and independent audit remain pending; the delivery state is not approval.
