# Canonical namespace migration change brief

## Record

- Status: **IMPLEMENTED — READY_FOR_REVIEW** (self-review complete; independent
  audit outstanding)
- Risk: **L**
- Authorized starting point: `main@5330e0dd424bfa746007034ba0672e570cc4ff0f`
- Delivery branch: `feature/canonical-python-namespace`
- Target identity: `packet_tracer_mcp` in production and tests — **achieved**
- Former containment: `src.packet_tracer_mcp` is retired. `src/` is now only the
  package's physical location and is not an import namespace.
- Known unmet criterion: **NM9**, deferred by explicit maintainer decision. See
  [Ruff boundary debt](#ruff-boundary-debt-nm9-deferred).

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

## Delivery record

Implemented on `feature/canonical-python-namespace` from
`main@5330e0dd424bfa746007034ba0672e570cc4ff0f`. All measurements below were
taken in this checkout with `.\.venv\Scripts\python.exe` (pytest 9.1.1), whose
editable install resolves inside this checkout.

### Inventory, before and after

Measured with `scripts/namespace_inventory.py`, which parses every tracked
Python file and separates import statements from string constants from prose,
because a name in an import and the same name inside a guard's list of
forbidden values are not the same fact.

| Category | Before | After |
| --- | --- | --- |
| Active legacy import statements | 1384, in 240 files | **0** |
| Active legacy dynamic-import / patch targets | 9 | **0** |
| Retained rejection references | 19, in 14 files | 22, in 18 files |
| Prose mentions (never active) | 4 | 6 |
| Command exit status | 1 | **0** |

The nine active string targets were `importlib.util.find_spec`,
`importlib.import_module`, `__import__` and one `monkeypatch.setattr` target in
`test_cp_scale_live_cli.py`, `test_cp_scale_live_coordinator.py`,
`test_cp_scale_stage_executor.py`, `test_e95_e5_capability_evidence.py`,
`test_mutation_transport_ambiguity.py` and `test_poe_delivery_qualification.py`.
A `find_spec` on a legacy submodule imports the legacy parent package, so these
were live producers of the second identity, not inert text.

Retained references grew and shrank by none. Three superseded containment
assertions (below) now state the migrated invariant, and the guard and the
inventory added by this change necessarily name the retired namespace in order
to reject it. Every allowlist entry is asserted to name a file that exists and
to carry a non-empty reason, so the list cannot become a place to park a real
use.

### Cohorts

Converted in bounded cohorts with focused runs between them, and committed as
one change so no published commit can load both namespaces.

| Cohort | Content | Result |
| --- | --- | --- |
| 1 | Collection and helpers: `conftest.py`, `cp_scale_stage_fixture.py`, `poe_delivery_capabilities.py`, `poe_session_safety.py`, `support/factory_module_cases.py` | 37 imports |
| 2 | Test modules | 1346 imports, 234 files |
| 3 | Dynamic imports and patch targets | 9 targets, 6 files |
| 4 | Guards, configuration and authority: `test_worktree_isolation.py` rewrite, `namespace_preflight.py`, `src/__init__.py`, `import_isolation_preflight.py`, `pyproject.toml`, `AGENTS.md` | - |

Cohort 1 alone produced 53 focused failures, which is the defect itself made
visible: migrated helpers built `packet_tracer_mcp` objects while unmigrated
test modules still held `src.packet_tracer_mcp` classes, so rules rejected
evidence they should have accepted. It is recorded here because it is the
clearest available demonstration of why an intermediate state must never be
published.

### Rewrites the migration forced, and why

Four places asserted the *retired* contract and could not simply be re-pointed.
Each was reproduced first and then corrected at the layer that owned it.

1. **`tests/test_worktree_isolation.py`** ran the two runtime entrypoints with
   `cwd=src`, where Python puts the current directory first on `sys.path`. That
   made them pass regardless of what the editable install resolved - the exact
   fault they existed to detect. They now run from the repository root, with no
   `PYTHONPATH`, so a foreign or missing install fails there. Verified: both
   `python -m packet_tracer_mcp --help` and the `pt-mcp` console script exit 0
   from the root, and a bare import from the root resolves inside this checkout.

2. **Three suite-wide assertions** - in `test_cp_live_m0_equivalence_baseline.py`,
   `test_cp_scale_live_failure_evidence.py` and `test_cp_scale_voice_staging.py` -
   asserted `"packet_tracer_mcp" not in sys.modules`. That held only because the
   suite imported the package under the retired name; its entire content was the
   containment this change removes. A replacement invariant of "the parent never
   loads the live runner" was considered and **rejected as false**: other tests
   import `tools.cp_scale_canonical_live` and `cp_scale_live_session` in-process,
   so it would have been order-dependent fiction. They now assert what is true
   and still worth guarding - one identity loaded, and not the retired one.

3. **`src/__init__.py`** was kept, not deleted. Deleting it does not close the
   namespace: with the repository root on `sys.path`, `src` remains a PEP 420
   namespace package and `import src.packet_tracer_mcp` still resolves. Verified
   empirically on a synthetic tree with no `__init__.py`. The file now documents
   that, and the boundary is held by enforcement instead.

4. **The LIVE import-isolation gate** lost a safety property and had it restored
   under NM10. Before the migration a pytest process failed the gate for lacking
   the production namespace. With one namespace a pytest process satisfies every
   other check, and the gate was measured returning `ISOLATED: True` for a
   process holding `pytest` and the package. `ImportIsolationPreflight` now
   refuses such a process explicitly as `TEST_PROCESS`, so a green suite still
   cannot be read as LIVE isolation. `TEST_NAMESPACE` was renamed
   `LEGACY_NAMESPACE` to stop naming the retired identity as the suite's own.

### Fail-closed preflight (NM3, NM4)

`tests/namespace_preflight.py` runs from `tests/conftest.py` before any test
module is imported and refuses a foreign interpreter, a foreign package origin,
or a loaded `src.packet_tracer_mcp`. It derives the checkout from its own path -
not circular here, because pytest loads it by path out of the checkout under
test, so the root is the observer rather than the observed. `evaluate()` never
raises and reports `INDETERMINATE` on an observation error; `enforce()` names
the expected checkout and the observed values.

Rejections are reachable in tests with injected observations, and two
end-to-end tests run the real rule in a child process: one against a foreign
root, which is the shape a copied or inherited `.venv` takes, and one positive
control from this checkout's own root.

### Pytest import mode (NM7)

Measured on pytest 9.1.1 at this SHA, and pinned in `pyproject.toml` so a change
of the pytest default is a deliberate, re-measured decision.

| Mode | Collected | Collection errors | Decision |
| --- | --- | --- | --- |
| `prepend` (default) | 5059 | 0 | **Chosen** |
| `importlib` | 4762 | 18 | Rejected |

Nineteen test modules import a sibling by bare module name, which resolves only
because `prepend` puts the test's own directory first on `sys.path`. `importlib`
does not, so those modules fail to collect. The suite also uses 72 qualified
`tests.test_*` imports across 25 modules; converting the bare form to the
qualified form to enable `importlib` would risk the same duplicate-module
identity this change exists to remove, and is not attempted here.

### Packaging (NM6)

The wheel was built and installed into a fresh environment **outside the
repository**, with no editable install present. Observed there: the package
resolves from `site-packages`; `import src.packet_tracer_mcp` does **not**
resolve; `CapabilityStatus.SUPPORTED is CapabilityStatus.SUPPORTED` and the
corresponding `isinstance` both hold; `python -m packet_tracer_mcp --help` and
the `pt-mcp` console script both exit 0. The wheel contains `packet_tracer_mcp/`
at top level with no `src/` prefix, confirming `src/` is a build-time layout
only.

### Persisted names (NM8)

Reviewed and unaffected. The only module-qualified value compared by the suite is
`type(coordinator).__module__` in `test_cp_scale_live_cli.py`, which already
expected `packet_tracer_mcp.application.cp_scale_live.coordinator` because the
probe runs in a child process under the production namespace. The CP-LIVE M0
oracle records `executed_scope.digest` over the *set of executed file paths*,
not their contents, and no pytest test re-verifies it against worktree bytes, so
migrating imports inside `tests/cp_live_m0_harness.py` does not invalidate it.
Historical evidence under `docs/reference/` was not modified.

Line endings were preserved throughout: this checkout is CRLF under
`core.autocrlf=true`, and the rewrite was performed on bytes so no file was
silently normalized.

### Ruff boundary debt (NM9, deferred)

**NM9 is not met on this branch, by explicit maintainer decision.**

The gate selects files changed against the base, so a one-line import rename
pulls every migrated test file across the incremental Ruff boundary at once.
Measured in delivery mode on the exact delivery commit, with a clean tree:

| Measure | Value |
| --- | --- |
| Files selected by the gate | 250 |
| The migration's own diff | ~1419 lines |
| `ruff format` would reformat | 235 files, ~36 200 lines |
| `ruff check` violations | 3844 |
| - of which missing-docstring (D100/101/102/103/107) | 3315 |
| - substantive, after `ruff format` and all autofixes | ~530 before autofix, ~77 after |

For context, the boundary is repository-wide and not specific to tests: `src/`
itself currently reports 2746 violations and 262 unformatted files. No
configuration resolves this, because `ruff format` has no per-file ignores.

The options were measured and put to the maintainer, who chose to deliver the
migration alone and open the boundary expansion as its own change with its own
debt assessment - which is what `docs/engineering/standards.md` already
prescribes for expanding enforced scope. Consequences, stated plainly:

- `scripts/quality_gate.py --delivery-commit HEAD` **fails** on this branch, and
  the CI `quality` job fails with it. The `pytest` and `docs` jobs pass.
- No Ruff rule was weakened, no global ignore added, and no exclusion grown.
- Every file this change **authored** does pass the gate:
  `tests/namespace_preflight.py`, `tests/test_namespace_preflight.py`,
  `tests/test_namespace_inventory.py`, `scripts/namespace_inventory.py`,
  `tests/test_worktree_isolation.py` and `src/__init__.py`.
- Two production files carrying legacy format debt were edited for NM10 and are
  left unformatted deliberately, so the security-relevant diff stays readable:
  `import_isolation_preflight.py` and `cp_scale_live_preflight.py`.

### Worktree ownership (NM1)

Proved on a real sibling worktree created at the delivery commit,
`Cisco-MCP-nm1`, which was given its own `.venv` and its own editable install.

Positive: from that worktree's repository root, its own interpreter resolves
`packet_tracer_mcp` at
`Cisco-MCP-nm1/src/packet_tracer_mcp/__init__.py`, and the complete suite runs
there with the same result as the main checkout - 5056 passed, 3 skipped,
exit 0.

Negative, in both directions, refused at `conftest` import before collection:

| Interpreter | Run from | Result |
| --- | --- | --- |
| `Cisco-MCP/.venv` | `Cisco-MCP-nm1` | `FOREIGN_INTERPRETER`, naming both paths |
| `Cisco-MCP-nm1/.venv` | `Cisco-MCP` | `FOREIGN_INTERPRETER`, naming both paths |

What that refusal prevents was measured directly. Standing in the sibling
worktree and importing with the main checkout's interpreter, the package
resolves to `Cisco-MCP/src/packet_tracer_mcp/__init__.py` - the other
checkout - with no error and no warning. That is the original defect, and it is
now a refusal rather than a silent substitution.

### Verification results

All offline, in this checkout, with the checkout-local interpreter.

| Check | Result |
| --- | --- |
| Pre-migration reproduction, at the base SHA | Reproduced: one file tree, two module identities, `isinstance` across them false |
| Legacy inventory | 0 active imports, 0 active targets, exit 0 |
| Baseline suite, before the change | 5030 passed, 3 skipped, exit 0 |
| Full suite, after the change | **5056 passed, 3 skipped, exit 0** |
| Focused: preflight, inventory, worktree identity | 30 passed |
| Focused: LIVE import-isolation gate | 16 passed |
| Root entrypoints | `python -m packet_tracer_mcp --help` and `pt-mcp --help` exit 0 from the repository root, no `PYTHONPATH`, no `cwd=src` |
| Wheel in an environment outside the repository | Import, `python -m`, console script, enum identity and domain behaviour all pass; the retired namespace does not resolve |
| Foreign-environment rejection | Refused with injected observations, end-to-end in a child process, and across two real sibling worktrees |
| Fresh sibling worktree, own `.venv` and editable install | 5056 passed, 3 skipped, exit 0 |
| MkDocs build | Exit 0; the two link warnings are pre-existing in `docs/reference/cp-scale/` |
| `git diff --check` | Clean |
| Ruff gate on files this change authored | Passes |
| Ruff delivery gate over the whole change | **Fails** - NM9 deferred, measured above |

The suite grew by 26 tests: the preflight contract, the inventory controls, the
rewritten worktree identity guard, and the new `TEST_PROCESS` refusal.

### Residual risk and debt

- **NM9 Ruff boundary expansion** is open and unscheduled. Until it is done, CI
  is red on the `quality` job for this branch, and a reviewer must not read that
  failure as a defect in the migration.
- **Duplicate test-module identity** is untouched and pre-existing: under
  `prepend`, a module collected as `test_x` and imported elsewhere as
  `tests.test_x` is two module objects over one file. This is the same class of
  defect as the one just removed, one level up, and is not in this change's
  scope. It is the reason the `importlib` alternative is worth revisiting once
  sibling imports are normalized.
- **LIVE behaviour is unverified and unclaimed.** Everything above is offline.
  The `TEST_PROCESS` refusal was measured in ordinary processes; no authorized
  LIVE Packet Tracer run was performed or is implied.
