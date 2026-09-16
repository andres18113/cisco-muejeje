# Canonical namespace migration change brief

## Record

- Status: **PROPOSED — NOT AUTHORIZED FOR IMPLEMENTATION**
- Risk: **L**
- Required starting point: accepted `main` after the engineering-standards audit
- Target identity: `packet_tracer_mcp` in production and tests
- Current containment: `src.packet_tracer_mcp` remains mandatory in ordinary
  pytest until this migration replaces it without an isolation gap.

## Problem, scope, and exclusions

The same source tree can be loaded as both `packet_tracer_mcp` and
`src.packet_tracer_mcp`. Python then creates distinct module, class, and enum
objects, so identity and `isinstance` checks can silently disagree. The current
test namespace prevents cross-worktree imports, but it is temporary containment,
not the target architecture.

The future migration covers editable installation, test/helper/script imports,
dynamic imports and patch targets, early interpreter/package-origin checks,
pytest import behavior, wheel validation, persisted module names, and Ruff impact.
It excludes product behavior changes, LIVE execution, historical evidence edits,
IoT fixes, aliases in `sys.modules`, and deletion of `src/__init__.py` as a
shortcut.

## Concrete inventory at the audited starting point

- 233 Python files contain direct `src.packet_tracer_mcp` imports; all are under
  `tests/`. This includes `tests/conftest.py`, `tests/cp_scale_stage_fixture.py`,
  `tests/poe_delivery_capabilities.py`, `tests/poe_session_safety.py`, and
  `tests/support/factory_module_cases.py`.
- 251 Python files contain the legacy namespace text: 242 tests, seven `tools/`
  runners, and two source files. The source references are the temporary
  `src/__init__.py` contract and `import_isolation_preflight.py` namespace guard;
  tool references are identity guards rather than production imports.
- No `scripts/` file currently imports the legacy namespace directly. No dynamic
  `importlib`/`__import__` or `mock.patch` target using that namespace was found
  by the audited search; both categories remain mandatory re-scan items.
- `tests.support.factory_module_cases` has three direct consumers, and
  `tests.cp_live_m0_record_baseline` has one. Their package resolution must remain
  valid under the selected pytest import mode.
- `tests/test_worktree_isolation.py` currently runs two production-entrypoint
  checks with `cwd=src`; those checks must be replaced by root-directory checks
  that expose editable-install errors instead of hiding them.
- `pyproject.toml` has no explicit pytest `--import-mode=importlib` setting.
  Effects on `tests.support`, collection, fixtures, and patch targets require a
  measured decision.
- No active persisted module-name field was identified by the source/config text
  scan. Payload schemas and stores still require review; historical evidence is
  immutable even if it contains legacy names.
- Every migrated Python file enters the incremental Ruff boundary. Its existing
  violations must be measured before implementation and handled without global
  ignores, mass unrelated formatting, or weakened rules.

Inventory commands and their exact counts belong in the delivery record and must
be rerun from the authorized starting SHA; this snapshot is not a substitute for
that fresh inventory.

## Requirements and acceptance criteria

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| NM1 | Every worktree owns its editable installation and `.venv`. | A fresh sibling worktree installs with its own interpreter; package origin resolves inside that worktree from repository root. |
| NM2 | Tests, helpers, scripts, dynamic imports, and patch targets use `packet_tracer_mcp`. | AST/text inventories contain no active legacy imports or targets outside explicitly retained migration assertions. |
| NM3 | Fail before collection or execution when interpreter or package origin is foreign. | Early preflight reports expected/observed executable and package origin and rejects another checkout. |
| NM4 | Exactly one package identity is loaded without aliases. | A negative check rejects either namespace mixture; no code assigns aliases in `sys.modules`. |
| NM5 | The production entrypoint works from repository root. | `python -m packet_tracer_mcp --help` and the console entrypoint pass from root; no test uses `cwd=src` to make them pass. |
| NM6 | The built wheel works independently of repository layout. | Install the wheel in a separate environment outside the repository and run import, module entrypoint, and representative smoke tests there. |
| NM7 | Pytest import mode is an explicit, measured decision. | Compare the default mode with `--import-mode=importlib`, including collection, fixtures, `tests.support`, dynamic imports, and patch targets; record the chosen mode and rejected alternative. |
| NM8 | Persisted names remain compatible or are migrated deliberately. | Review schemas, serialized payloads, stores, and non-historical fixtures for module-qualified names; document compatibility and never rewrite historical evidence. |
| NM9 | Ruff remains fail-closed and incremental. | Inventory violations in every touched file before migration; changed files pass the unchanged gate without broad suppressions or unrelated formatting. |
| NM10 | Product behavior and governed safety remain unchanged. | Focused, affected, full offline, packaging, and exact-SHA CI pass; LIVE remains separately authorized and unclaimed. |

## Test design

1. Preserve an isolated pre-migration reproduction showing the two names load
   the same files as distinct module, enum-class, and enum-member identities.
2. Add an early subprocess preflight that imports only `packet_tracer_mcp`, checks
   `sys.executable` and `__file__`, and fails against an environment installed
   from another checkout.
3. Convert imports in bounded cohorts: collection/helpers, pure unit tests,
   integration tests, tool subprocesses, then namespace guards. Run focused and
   affected tests after each cohort; never create a mixed ordinary pytest run.
4. Exercise the entrypoint from root and a separate directory. Do not set
   `PYTHONPATH` and do not use `cwd=src`.
5. Build a wheel, install it into a separate temporary environment outside the
   repository, and test import, `python -m`, console entrypoint, and representative
   domain/application behavior.
6. Run the pytest import-mode experiment in disposable environments and preserve
   command, interpreter, SHA, collection count, failures, and `tests.support`
   observations.
7. Re-scan dynamic imports, patch strings, persisted names, and loaded namespaces;
   then run Ruff, full offline tests, docs, packaging, and exact-SHA CI.

## Preserved isolated reproduction

Command, run outside ordinary pytest with the checkout-local interpreter:

```powershell
.\.venv\Scripts\python.exe scripts\reproduce_namespace_identity.py
```

Observed at the engineering-standards audit starting point:

```json
{
  "cross_namespace_isinstance": false,
  "enum_member_identity_same": false,
  "enum_type_identity_same": false,
  "legacy_origin": "src/packet_tracer_mcp/__init__.py",
  "loaded_namespaces": [
    "packet_tracer_mcp",
    "src.packet_tracer_mcp"
  ],
  "package_identity_same": false,
  "physical_origin_same": true,
  "production_origin": "src/packet_tracer_mcp/__init__.py"
}
```

The parent diagnostic imports neither package. It launches a child interpreter,
requires the checkout-local `.venv`, normalizes origins relative to the checkout,
and exits successfully only when the known pre-migration defect is reproduced.

## Risks and rollback boundary

Primary risks are a foreign editable install producing false-green tests,
collection failures caused by changing pytest import semantics, stale patch
targets, module-qualified serialized values, and an intermediate commit that
loads both namespaces. The migration must be delivered atomically enough that
every published commit retains one tested identity. Rollback is a normal Git
revert to the accepted pre-migration commit; never add runtime aliases or rewrite
published SHAs to conceal a mixed state.

## Authorized integration sequence

Documented only; this brief does not authorize any step:

1. Audit and independently accept the corrected engineering standards.
2. Integrate them into `main` only with explicit authorization.
3. Start this namespace migration from that accepted `main` as an independent
   delivery.
4. After migration acceptance, merge the accepted `main` into
   `feature/iot-connectivity`, resolve imports there, and complete validation
   before resuming IoT fixes.
