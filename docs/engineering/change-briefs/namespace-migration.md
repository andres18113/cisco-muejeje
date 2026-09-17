# Canonical namespace migration change brief

## Record

- Status: **IMPLEMENTED — READY_FOR_REVIEW** once the exact delivery commit
  passes CI; the delivery report, not this file, records that run
- Risk: **L**
- Authorized starting point: `main@5330e0dd424bfa746007034ba0672e570cc4ff0f`
- First implementation: `73494e3c095595a01cbccb36f398b24ccea47169`
- Integrated base: `main@502c14ba2b586e46045b1a2bfeedbb944a355af0`, which adds
  the mechanical migration quality boundary, merged into this branch by
  `89b914f06c86815a5677010e665f736f208d542d`
- Blocker correction: `31772fe6af409b5eb6f5db505d2cb6e7383b6b14`
- Delivery branch: `feature/canonical-python-namespace`
- Target identity: `packet_tracer_mcp` in production and tests — **achieved**
- Retired identity: `src.packet_tracer_mcp` is **not importable**. `src/` is only
  the package's physical location, and `src/__init__.py` refuses any import
  through it.
- NM9: **met** through the mechanical migration quality boundary; see
  [Ruff boundary (NM9)](#ruff-boundary-nm9).

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

The reproduction lived at `scripts/reproduce_namespace_identity.py` through
`main@502c14ba2b586e46045b1a2bfeedbb944a355af0` and is removed by this
migration. It cannot succeed after it, because `src/__init__.py` now refuses
the import it depends on, and its child source is an executable import of the
retired namespace, which the inventory rejects in any file. To reproduce the
defect, check out that commit and run it there. Its recorded observation is
kept below.

Command, run outside ordinary pytest with the checkout-local interpreter, at
`502c14b` or earlier:

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
`main@5330e0dd424bfa746007034ba0672e570cc4ff0f`, then corrected at `31772fe`
after integrating `main@502c14b`. Each measurement names the commit it was taken
at. All were taken in this checkout with `.\.venv\Scripts\python.exe` (pytest
9.1.1), whose editable install resolves inside this checkout, except where a
sibling worktree or an outside environment is named.

### Inventory, before and after

Measured with `scripts/namespace_inventory.py`, which parses every tracked
Python file and classifies each mention of the retired namespace by its
syntactic context, never by the file it is in:

- **Active** mentions load or register a second identity: an import statement
  (including `from src import ...`), a string passed to a callable that imports
  or patches by name, a key added to `sys.modules`, or source text executed by
  `exec`, `eval`, `compile`, or after `-c`, including source kept in a string
  constant and launched later. Active mentions fail the inventory in every file.
- **Inert** mentions name the retired namespace as data: a guard's list of
  forbidden names, an assertion subject, a `sys.modules` lookup, or source text
  that is never executed. They are allowed only in the files listed in
  `RETAINED_STRING_REFERENCES` with a reason, and an inert mention anywhere else
  fails as **unreviewed**.
- Docstrings and comments are prose and never fail it.

| Category | Before, at `502c14b` | After, at `31772fe` |
| --- | --- | --- |
| Active import statements | 1384, in 240 files | **0** |
| Active dynamic-import and patch targets | 9 | **0** |
| Active executed source | 2 | **0** |
| Unreviewed inert mentions | not applicable | **0** |
| Retained inert mentions | not applicable | 65, in 22 files |
| Prose mentions | 6 | 11 |
| Command exit status | 1 | **0** |

The nine dynamic targets were `importlib.util.find_spec`,
`importlib.import_module`, `__import__` and one `monkeypatch.setattr` target in
`test_cp_scale_live_cli.py`, `test_cp_scale_live_coordinator.py`,
`test_cp_scale_stage_executor.py`, `test_e95_e5_capability_evidence.py`,
`test_mutation_transport_ambiguity.py` and `test_poe_delivery_qualification.py`.
A `find_spec` on a legacy submodule imports the legacy parent package, so these
were live producers of the second identity, not inert text. The two executed
sources were the child processes of the reproduction script and of the superseded
containment tests in `test_worktree_isolation.py`. The retained-mention counts are
measured only after the migration, because the allowlist describes the migrated
file set.

The first implementation's inventory decided retention per file: any string in
an allowlisted file counted as retained, so an `import_module`, a patch target, a
`sys.modules` registration, or a `-c` child source in such a file was hidden, and
`from src import packet_tracer_mcp` was not seen at all. Each of those thirteen
executable forms was reproduced against it — all hidden — before the
classification was replaced. Every allowlist entry must name an existing file with
a reason, and the allowlist must equal the set of files that still hold a retained
mention, so it can neither park a real use nor keep a stale entry.

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

3. **`src/__init__.py`** refuses import. Deleting it does not close the
   namespace: with the repository root on `sys.path`, `src` becomes a PEP 420
   namespace package and `import src.packet_tracer_mcp` still resolves. The first
   implementation kept the file as a documented marker, which left the second
   identity importable — measured, from the repository root, `import src`,
   `import src.packet_tracer_mcp`, a submodule import, and `find_spec` of the
   package and of a submodule all succeeded. The file now raises `ImportError`
   naming `import packet_tracer_mcp`, and all five forms are refused. The
   installed package never reaches it: the editable install and the wheel expose
   `packet_tracer_mcp` directly, and the wheel holds no `src/`.

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

Re-verified at `31772fe`. The wheel was built from the clean tree and installed
into a fresh environment **outside the repository**, with no editable install
present. Observed there: the package resolves from `site-packages`; the retired
namespace does not resolve (`ModuleNotFoundError`) and `src` is never loaded;
`CapabilityStatus.SUPPORTED` keeps one identity and `isinstance` holds; `python -m
packet_tracer_mcp --help` and the `pt-mcp` console script both exit 0; and
planning a two-router DHCP topology yields a valid plan of 8 devices and 7 links.
The wheel contains only `packet_tracer_mcp/` and its metadata at top level, with
no `src/` prefix, confirming `src/` is a build-time layout only.

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

### Ruff boundary (NM9)

**NM9 is met.** The first implementation deferred it: a one-line import rename
pulls every migrated file across the incremental Ruff boundary, and the gate
attributed about 3845 historical violations to the migration. The mechanical
migration quality boundary, integrated from `main@502c14b`, removes exactly that
false debt and nothing else.

The authorization is the committed record
`scripts/mechanical_authorizations/canonical-python-namespace.json`, which binds
`CANONICAL_PYTHON_NAMESPACE` to base commit
`502c14ba2b586e46045b1a2bfeedbb944a355af0` under this brief. The CI quality job
passes it with `--mechanical-authorization`; it is active only while the
comparison merge base is that commit.

Measured in delivery mode at `31772fe`, with a clean tree, over exact Git blobs:

| Measure | With the record | Without it (control) |
| --- | --- | --- |
| Selected Python files | 249 | 249 |
| Record state | **ACTIVE** at merge base `502c14b` | — |
| Exempt as `MECHANICAL_ONLY` | 235 | 0 |
| Checked by Ruff | 14 | 249 |
| Ruff lint findings | **0** | 3663 |
| Files needing formatting | **0** | 226 |
| Gate exit status | **0** | 1 |

The 14 checked files are the ones this migration authored or created, and each
passes Ruff in full:

- new: `scripts/namespace_inventory.py`, `tests/namespace_preflight.py`,
  `tests/test_namespace_preflight.py`, `tests/test_namespace_inventory.py`;
- authored: `src/__init__.py`, `import_isolation_preflight.py`,
  `cp_scale_live_preflight.py`, `tests/conftest.py`,
  `test_cp_live_m0_equivalence_baseline.py`,
  `test_cp_scale_live_failure_evidence.py`, `test_cp_scale_voice_staging.py`,
  `test_import_isolation_preflight.py`, `test_poe_delivery_qualification.py`,
  `test_worktree_isolation.py`.

`test_poe_delivery_qualification.py` is authored because its patch target was an
implicitly concatenated literal, which the boundary deliberately never rewrites.
Two files had changed only in docstring prose — `tests/cp_live_m0_harness.py` and
`tests/test_e95_productive_pipeline.py` — and that prose was reverted, so the first
is unchanged and the second is proven mechanical instead of reformatting a
CP-LIVE-adjacent harness.

Bringing the authored files to the gate took formatting, 119 docstrings, and
Ruff's fixes for import order, an unused import, `datetime.UTC`, unpacking, 27
unused unpacked names, and an `Optional` ordering. No rule was changed, and no
ignore, exclusion, or `noqa` was added. One fix reaches production behavior:
`ImportIsolationState` is now a `StrEnum` instead of `(str, Enum)`. That changes
only `str()` and `format()` of a member, which no consumer uses: the LIVE runners
and CP-SCALE evidence record `state.value`, the rendered diagnostic starts with it,
and JSON writes the value either way. A test pins those recorded forms for every
state.

### Worktree ownership (NM1)

Re-verified at `31772fe` on a fresh sibling worktree, `Cisco-MCP-nm1`, detached
at that commit with its own `.venv` and editable install. Its interpreter
resolves `packet_tracer_mcp` inside that worktree. Installed with the
prescribed `.[test,docs,quality]` extras, its complete suite ran there with
5297 passed, 3 skipped, exit 0, matching this checkout; a first run installed
with only `.[test]` failed the two tests that invoke Ruff. Each checkout's
`conftest` refused the other checkout's interpreter as `FOREIGN_INTERPRETER`,
naming both paths, before collection. The worktree was removed afterwards.

First proved on a real sibling worktree created at the first implementation,
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

All offline, with the checkout-local interpreter. Counts are at `31772fe` unless
stated.

| Check | Result |
| --- | --- |
| Pre-migration reproduction, at `5330e0d` | Reproduced: one file tree, two module identities, `isinstance` across them false |
| Retired namespace from the repository root | `import src`, the package, a submodule, and `find_spec` of the package and a submodule are all refused with `ImportError` |
| Legacy inventory | 0 active imports, 0 active string references, 0 unreviewed mentions, exit 0 |
| Inventory controls | 13 executable forms are active in allowlisted and unlisted files alike; 6 inert forms are retained only where allowlisted |
| Mutation checks | 8 of 8 detected: refusal removed, allowlist hiding active references, `from src import` missed, registry, dynamic import, executed source, name-resolved source, and unreviewed mentions each ignored |
| Affected suites | 544 passed |
| Full suite | **5297 passed, 3 skipped, exit 0** |
| Root entrypoints | `python -m packet_tracer_mcp --help` and `pt-mcp --help` exit 0 from the repository root, no `PYTHONPATH`, no `cwd=src` |
| Wheel in an environment outside the repository | Import, `python -m`, console script, enum identity and a domain plan all pass; the retired namespace does not resolve |
| Foreign-environment rejection | Refused with injected observations, end-to-end in a child process, and across two real sibling worktrees |
| Fresh sibling worktree, own `.venv` and editable install | 5297 passed, 3 skipped, exit 0, matching this checkout, once installed with the prescribed `.[test,docs,quality]` extras (a first run installed with only `.[test]` failed the two tests that invoke Ruff) |
| Ruff delivery gate with the committed record | Exit 0: 235 exempt, 14 checked, 0 findings |
| Ruff delivery gate without it (control) | Exit 1: 249 checked, 3663 findings, 226 files to format |
| MkDocs build | Exit 0; the two link warnings are pre-existing in `docs/reference/cp-scale/` |
| `git diff --check` | Clean |

### Requirement results

| ID | Result at `31772fe` | Evidence |
| --- | --- | --- |
| NM1 | Met | Fresh sibling worktree with its own environment; origin inside it; foreign interpreters refused in both directions |
| NM2 | Met | Inventory: no active import, dynamic target, registry key, or executed source; controls prove the classification |
| NM3 | Met | `tests/namespace_preflight.py` refuses before collection, naming expected and observed values |
| NM4 | Met | Retired namespace refused at import; preflight and LIVE gate reject any mixture; no `sys.modules` alias |
| NM5 | Met | Module and console entrypoints exit 0 from the repository root without `cwd=src` |
| NM6 | Met | Wheel installed outside the repository passes import, entrypoints, identity, and a domain plan |
| NM7 | Met at `73494e3`, unchanged since | `prepend` chosen and pinned; `importlib` measured and rejected |
| NM8 | Met at `73494e3`, unchanged since | No module-qualified persisted name affected; historical evidence untouched |
| NM9 | Met | Delivery gate exit 0 with the base-bound record; control without it exits 1 |
| NM10 | Met offline; exact-SHA CI in the delivery report | Focused, affected, full, packaging, and entrypoint checks pass; `TEST_PROCESS` refusal retained; LIVE unclaimed |

### Residual risk and debt

- **Duplicate test-module identity** is untouched and pre-existing: under
  `prepend`, a module collected as `test_x` and imported elsewhere as
  `tests.test_x` is two module objects over one file. This is the same class of
  defect as the one removed, one level up, and is not in this change's scope. It
  is the reason the `importlib` alternative is worth revisiting once sibling
  imports are normalized.
- **The inventory reads literal text.** A module name assembled at run time from
  separate pieces, or a callee reached through `getattr`, is outside any static
  scan; `src/__init__.py` refuses such an import at run time.
- **Outside pytest there is no preflight.** An interpreter from one checkout
  started in another still imports that other checkout's package silently, as
  measured for NM1; the environment rule and the LIVE gate, not the suite, own
  that boundary.
- **The authorization record goes stale on purpose.** Once the migration is
  integrated and `main` moves past `502c14b`, the quality job prints the record as
  INACTIVE and grants nothing. Removing the record and its workflow argument is a
  cleanup for a later change.
- **LIVE behaviour is unverified and unclaimed.** Everything above is offline.
  The `TEST_PROCESS` refusal was measured in ordinary processes; no authorized
  LIVE Packet Tracer run was performed or is implied.
