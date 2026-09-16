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

## Audit closure revision

### Record

- Status: implemented; local verification complete; clean-tree delivery and
  exact-SHA CI pending
- Risk: **L**
- Audited starting commit: `708980548ac8976e918d903834c4318550088fde`
- Scope: close instruction-authority, quality-gate, CI-permission, collaboration,
  and namespace-planning findings without changing product or LIVE behavior.

### Requirements and acceptance

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| R9 | Separate global user preferences, checkout authority, detailed standards, and Claude-specific imports without editing global files. | Record discovered instruction sources, installed versions, effective locations, and any conflicts without publishing private content. |
| R10 | Require agents to read the standard from the current checkout before planning or editing; make Claude import both shared authority files. | `AGENTS.md` contains an explicit read requirement; `CLAUDE.md` contains `@AGENTS.md` and `@docs/engineering/standards.md` with no duplicated project rules. |
| R11 | Define authoritative-main, one-writer, checkout/SHA, per-worktree environment, local-instruction, Git-propagation, and handoff invariants. | Shared-authority review covers every invariant; the migration brief records the four-step integration sequence without executing it. |
| R12 | Make the quality gate explicit about its comparison base and about provisional worktree versus exact clean-commit delivery validation. | The gate prints resolved SHAs, fails on an invalid base or missing selected file, refuses dirty/exact-SHA mismatches for delivery, and labels `--files` as focused only. |
| R13 | Cover authoritative remote `cisco`, all Git change states, staged/worktree divergence, missing files, lint failure, format failure, and positive controls. | Focused regressions reproduce every case and fail before the causal implementation where applicable. |
| R14 | Apply least privilege to verification CI without changing Pages deployment privileges or the four-job pytest matrix. | Verification workflow declares `contents: read`, all checkouts disable credential persistence, YAML inspection passes, and final job logs show read-only token permissions. |
| R15 | State `packet_tracer_mcp` as the target namespace for production and tests while retaining `src.packet_tracer_mcp` as temporary containment until a separate migration. | Shared authority preserves current isolation controls, performs no import migration, and links a separate L migration brief with the approved inventory and acceptance criteria. |
| R16 | Reproduce the dual-namespace defect outside ordinary pytest and preserve the result without aliases or source/package changes. | A standalone isolated diagnostic demonstrates distinct identities; its normalized result is recorded in the migration brief and is absent from normal test collection. |
| R17 | Deliver only from the audited branch by fast-forward push, with local validation and all six final-SHA jobs green. | Clean-tree delivery gate, focused/affected/full tests, docs, diff check, remote SHA equality, and four pytest plus quality/docs success. |

### Architecture, risks, and invariants

The quality gate remains one small cross-platform script. Worktree mode examines
filesystem bytes and is explicitly provisional. Delivery mode requires a clean
tree whose `HEAD` equals the requested commit, so checked filesystem bytes are
the exact committed bytes. `--files` remains a focused diagnostic and cannot
claim delivery validation.

Primary risks are comparing a feature branch with its own upstream, silently
skipping a path missing from disk, certifying corrected working-tree bytes while
bad bytes remain staged, leaking checkout credentials in CI, inheriting
instructions from another checkout, or loading both package namespaces in the
ordinary pytest process. Each is addressed fail-closed. Existing product,
bridge, evidence, and namespace-isolation controls remain unchanged.

Global instruction files, other worktrees, `feature/iot-connectivity`, runtime
source, extension source, and historical evidence are out of scope. Any global
conflict is reported as a separate proposed change and is not edited here.

### Test design

- Unit/integration: temporary Git repositories exercise `cisco/main`, invalid
  bases, committed/staged/unstaged/untracked selection, staged/worktree
  divergence, and an index path missing from the filesystem.
- Tool behavior: subprocess controls prove one clean file passes, one lint
  violation fails, and one formatting violation fails; focused output cannot be
  mistaken for full delivery validation.
- Delivery: a clean temporary repository validates an exact commit; dirty or
  mismatched commits fail before Ruff.
- Namespace: a standalone script launches an isolated child interpreter and
  records the current duplicate-module identity result. Ordinary pytest never
  imports both namespaces.
- Documentation/CI: review instruction discovery against official Codex and
  Claude Code documentation and installed versions; parse workflows, build docs,
  inspect final permission logs, and run `git diff --check`.
- System: run affected tests and the full offline suite. LIVE validation is not
  applicable and historical CP-LIVE evidence is not reused.
- Fresh-session instruction loading remains pending unless it can be inspected
  without launching another agent; documented configuration is not labeled as
  loaded merely because its files exist.

### Instruction-source audit

- Installed tools: Codex CLI 0.154.0 and Claude Code 2.1.273.
- `CODEX_HOME` is unset and resolves to `C:\Users\Andres\.codex`.
  `CLAUDE_CONFIG_DIR` is unset and resolves to
  `C:\Users\Andres\.claude`.
- The global Codex `AGENTS.md` exists but is empty; no global
  `AGENTS.override.md` exists. Codex configuration does not override fallback
  instruction names or the default project-document byte limit.
- No user or managed Claude `CLAUDE.md`, user/project `.claude/rules`, managed
  `claudeMd`, or `claudeMdExcludes` setting was found. Existing user settings
  were inspected only for instruction-resolution keys; private values were not
  copied into the project.
- The only applicable ancestor instruction files found from this checkout are
  its own `AGENTS.md` and `CLAUDE.md`. No absolute import to another checkout was
  found, so no global conflict proposal is pending.
- `codex debug prompt-input` on the installed version verified that the current
  checkout `AGENTS.md` is model-visible. It correctly did not auto-load
  `CLAUDE.md` or the linked standards body. Reading the standard remains the
  explicit first project action.
- A genuinely fresh Codex agent session and Claude `/context` session were not
  launched because this task prohibits subagents. Their documented checks remain
  pending and must not be reported as verified loading.

### Audit closure local results

- RED: the expanded gate tests failed collection because the delivery/worktree
  selection contracts did not yet exist. After the causal implementation, all
  gate regressions passed.
- Full offline suite: 5,030 passed, 3 skipped, and 3 pre-existing pytest
  deprecation warnings in 266.71 seconds.
- Provisional gate: `cisco/main` resolved to
  `9cb1c1ceb1e77e17daa5a06e4bf21a52db932479`; three changed Python files passed
  Ruff lint and format. The output explicitly denied delivery status.
- Namespace diagnostic: the isolated child reproduced equal physical origins
  but distinct package, enum type, and enum member identities, with cross-namespace
  `isinstance` false. Ordinary pytest did not import both namespaces.
- Affected instruction, worktree-isolation, documentation, and gate tests passed;
  MkDocs built successfully with the two already-recorded historical warnings.
  Workflow YAML parsed and `git diff --check` passed.
- Runtime source, extension source, and historical evidence have no diff.
  `feature/iot-connectivity` remains unchanged at
  `a535d4811589226bcb1afe9ce9c90d2c40ae4eb4` locally and remotely.
- Clean-tree delivery validation, effective CI permission logs, all six final-SHA
  jobs, and independent audit remain pending.

## Authoritative-main reference clarification

- Status: implemented; local verification complete; clean-tree delivery and
  exact-SHA CI pending
- Risk: **L**, because this changes shared engineering authority even though it
  does not change runtime or gate behavior.
- Requirement R18: quality-gate instructions must select the verified reference
  for the authoritative `main` in the current checkout, never silently infer a
  remote or use the feature branch upstream. The maintainer checkout uses
  `cisco/main`; the standard clone documented by `CONTRIBUTING.md` and GitHub
  Actions use `origin/main`. The selected reference must resolve to a commit
  before the gate runs.
- Acceptance: normative documentation states the general rule and each concrete
  context; searches show no portable clone instructions using `cisco/main` and
  no maintainer instructions using `origin/main`. Existing historical results
  and the deliberate `cisco/main` gate regression remain unchanged.
- Test design: search both reference names, run affected documentation tests and
  MkDocs, then full pytest, `git diff --check`, clean-tree delivery validation,
  and all six exact-SHA CI jobs. No unit test is invented for this documentation
  correction.
- Local results: the reference search confirmed maintainer-only `cisco/main`,
  clone-only `origin/main`, and both contexts in the shared standard/testing
  explanation. `cisco/main` resolved to
  `9cb1c1ceb1e77e17daa5a06e4bf21a52db932479`; 14 affected tests passed, MkDocs
  built with the two known historical warnings, the provisional quality gate
  passed, `git diff --check` passed, and the full suite reported 5,030 passed,
  3 skipped, and 3 inherited warnings in 286.41 seconds.
