# Engineering standards

This document is the detailed standard incorporated by `AGENTS.md`. Repository
statements using **must** are local policy. The external standards in the final
section inform that policy; this project does not claim full conformance,
certification, or a clause-by-clause implementation.

## Instruction authority and verification

Instruction scope is intentionally separated:

- Global Codex or Claude files contain only the user's cross-project
  preferences.
- The active checkout's `AGENTS.md` is the shared Cisco-Muejeje authority.
- This file owns the detailed engineering method and rules.
- The active checkout's `CLAUDE.md` imports both files above and contains only
  Claude Code-specific differences.

Never copy project rules into global files or import an absolute path to another
checkout. Policy reaches other branches and worktrees through Git integration.
File existence proves documented configuration, not effective loading.

Codex builds its chain once per run: it uses `AGENTS.override.md` before
`AGENTS.md` at each applicable level, reads global instructions from
`CODEX_HOME` (default `~/.codex`), and then walks from repository root toward the
working directory. In a fresh session, run
`codex --cd <checkout> --ask-for-approval never "Show which instruction files are active."`
or inspect enabled session logs. Record the checkout and reported sources.

Claude Code loads user and project `CLAUDE.md` files and expands relative `@`
imports from the importing file. In a fresh interactive session, run `/context`
and inspect Memory files. If either product cannot be started independently,
record the check as pending rather than inferring success. These procedures are
based on the official
[Codex AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md)
and [Claude Code memory guide](https://docs.anthropic.com/en/docs/claude-code/memory).

## Incremental V-Model and risk

Classify the change from its credible impact, never from diff size:

- **S — low risk:** local change that does not alter behavior or contracts.
- **M — medium risk:** bounded behavior, parser, integration, or internal
  interface change.
- **L — high risk:** architecture, public contract, security, authorization,
  evidence, persistence, or LIVE execution change.

When investigation exposes a higher risk, raise the classification and add the
new controls before continuing. Never lower risk to omit a control. If several
categories apply, use the highest.

Before implementation, create one proportional change brief. S changes need a
few lines in the active change record. M/L changes need a versioned file under
`docs/engineering/change-briefs/`. The single brief records:

- problem and intended outcome;
- scope and explicit exclusions;
- requirements paired with acceptance criteria;
- architectural impact and affected contracts;
- invariants that must remain true; and
- test design, including justified non-applicable levels.

Do not split these fields into six ceremonial documents. Record the design
before implementation, then continue through routine work without repeated
approval requests unless the approved contract must materially change.

The definition and verification sides pair as follows:

| Definition | Verification |
| --- | --- |
| Requirements | Acceptance tests and acceptance results |
| System design | System tests |
| Architecture | Integration tests |
| Module input/output/error contracts | Unit tests |

After the implementation point, validate applicable levels from focused to
broader scope, self-review the entire diff, complete acceptance traceability,
run CI on the exact delivery commit, and request independent audit. A
non-applicable level needs a reason. Tests and expected results derive from the
requirements, not from incidental implementation behavior. Pure documentation
changes do not need invented unit tests.

## Coding standard

English is canonical for maintained identifiers, comments, docstrings, new
diagnostics, tests, documentation, and commits. Exceptions are external
literals, localized content, attribution or quotation, immutable historical
evidence, and public/protocol contracts that must not be translated
incidentally. Language detection heuristics are review aids, never definitive
proof.

Python follows PEP 8 and PEP 257. Public boundaries have useful type annotations
and explicit input, output, and error contracts. Prefer readable, direct code;
do not add speculative abstractions or refactor solely because a file is large.
Ruff enforces the configured mechanical subset, while review covers semantics
that a formatter or linter cannot establish.

For maintained JavaScript and scripts:

- use English for maintained names, comments, diagnostics, and tests;
- define boundary inputs, outputs, asynchronous completion, and error behavior
  in code or adjacent API documentation;
- keep data separate from executable source and serialize untrusted values;
- use explicit error handling at external and asynchronous boundaries; and
- follow the local file's stable formatting unless an automated formatter is
  adopted for that language.

Adoption is progressive. New code and every changed Python file must satisfy the
current Ruff gate. Do not translate or reformat unrelated legacy files. Existing
debt is recorded in the active M/L brief; it is not hidden with global ignores,
growing exclusions, or broad suppressions.

## Architecture and test design

- Domain code contains deterministic business concepts and rules, with no I/O
  or concrete backend dependency.
- Application code orchestrates use cases through ports. Infrastructure
  implements backend, transport, filesystem, persistence, and framework
  integration.
- Structural validation and deserialization are separate from business rules.
  Successful parsing does not establish business admissibility.
- Put a helper in the module or layer that owns its behavior. `shared` is for
  genuinely cross-cutting concepts, not the automatic destination for reusable
  code.
- Avoid speculative abstractions, semantic duplication, and size-only
  refactors. A large cohesive module is preferable to arbitrary fragmentation;
  a small module may still violate boundaries.
- Organize tests around cohesive behavior. Avoid monolithic test files and do
  not copy production algorithms into tests as the oracle.

## Errors, effects, retries, and evidence

Authorize and validate fail-closed before effects. Required identity and
provenance must match exact expected values; missing or unobservable values are
unknown, not permission. Preserve typed error categories and causal chains while
sanitizing secrets and unsafe external detail at public boundaries.

Retries must be bounded and permitted only when the operation is read-only,
idempotent by contract, or there is reliable evidence that no effect occurred.
A timeout with unknown outcome never authorizes repeating a mutation.

Track capability, execution, and evidence independently:

- `DOCUMENTED` does not imply `SUPPORTED`.
- Configuration or dispatch does not imply an observed result.
- `PARTIAL`, `APPLIED`, or unobservable output does not imply `VERIFIED`.
- Offline CI does not prove LIVE Packet Tracer behavior.
- Earlier or foreign evidence does not substitute for exact current provenance.

Historical evidence is immutable. New evidence must identify the source tree,
commit, environment, authorization, observed result, and cleanup state required
by its governing contract.

## Autonomous correction and review

Agents may correct causal defects inside the approved contract. On failure,
classify the defect as a requirements, design, implementation, or test defect;
fix the originating layer and revalidate the focused test, affected area, and
broader suite in proportion to risk.

Never weaken tests, acceptance criteria, security, authorization, or evidence
semantics to obtain green. A material contract change requires approval.
Behavioral bugs require a reproducible regression; write RED first especially at
critical boundaries or when the cause is ambiguous. Do not manufacture RED for
a change with no behavior.

Self-review is mandatory but is not independent audit. Delivery status is
`READY_FOR_REVIEW`; only an independent reviewer can provide final approval.

## Executable controls and human review

`pyproject.toml` pins Ruff and holds its lint/format configuration.
`scripts/quality_gate.py` is the one local and CI entry point. A full gate
requires `--base`. There is no universal remote name: select the reference for
the authoritative `main` in the current checkout and prove it resolves to a
commit before invoking the gate. This maintainer checkout uses `cisco/main`; a
standard clone and GitHub Actions use `origin/main`. Never silently guess a
remote or derive the base from the feature branch upstream, which could compare
the branch with itself. The gate re-resolves the selected reference and prints
the base and merge-base SHAs. Worktree mode checks complete committed, staged,
unstaged, and untracked Python paths but is provisional because it reads
filesystem bytes. Delivery mode additionally requires `--delivery-commit`, a
clean tree/index, and exact equality with `HEAD`, so filesystem bytes equal the
requested commit. Missing paths and unresolved identities fail closed. `--files`
is a focused check, never delivery validation.

The gate intentionally does not scan every legacy Python file. This makes the
adoption boundary measurable without global ignores or mass formatting. The
behavioral tests prove both a clean positive control and a known failing
violation. Expanding the enforced scope is a separate change with its own debt
assessment.

| Automated | Requires human or independent review |
| --- | --- |
| Ruff lint and format on changed Python | Risk classification and justified test levels |
| Offline pytest on Windows/Linux and Python 3.11/3.13 | Architectural fitness and absence of speculative abstractions |
| MkDocs build and whitespace check | Contract meaning, evidence claims, and safe exception handling |
| Quality-gate positive and negative controls | ISO mapping or any claim of external conformity |
| Exact-SHA CI status | LIVE behavior and final independent approval |

## Reference basis

The repository's incremental V-Model and S/M/L tailoring are project decisions,
not requirements quoted from ISO. They are informed by the following official
sources, using the published editions current when this standard was written:

- [ISO/IEC/IEEE 12207:2026](https://www.iso.org/standard/90219.html) for
  software life-cycle process vocabulary and incremental application.
- [ISO/IEC/IEEE 29148:2018](https://www.iso.org/standard/72089.html) for
  requirements engineering and requirements information items.
- [ISO/IEC/IEEE 42010:2022](https://www.iso.org/standard/74393.html) for
  architecture-description concepts and stakeholder concerns.
- [ISO/IEC/IEEE 29119-2:2021](https://www.iso.org/standard/79428.html) for
  software test processes across life-cycle models.
- [ISO/IEC 25010:2023](https://www.iso.org/standard/78176.html) for the product
  quality model used when identifying quality impacts.
- [ISO/IEC 27001:2022](https://www.iso.org/standard/27001) for risk-based
  information-security management context.
- [PEP 8](https://peps.python.org/pep-0008/) and
  [PEP 257](https://peps.python.org/pep-0257/) for Python style and docstrings.
- Ruff's official [configuration](https://docs.astral.sh/ruff/configuration/),
  [formatter](https://docs.astral.sh/ruff/formatter/), and
  [versioning](https://docs.astral.sh/ruff/versioning/) documentation for the
  executable lint/format controls and exact-version policy.
