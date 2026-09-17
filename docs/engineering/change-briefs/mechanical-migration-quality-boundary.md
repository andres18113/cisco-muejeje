# Mechanical migration quality boundary change brief

## Record

- Status: **READY_FOR_REVIEW** once the exact delivery commit passes CI; the
  delivery report, not this file, records that commit's CI run
- Risk: **L** — it changes an executable control that decides which files the
  incremental Ruff gate checks, and who may authorize that decision
- Starting point: `main` at `5330e0dd424bfa746007034ba0672e570cc4ff0f`
- First implementation: `5acd39fd3e339259d5bc5bf6e93c3b63827844ba`
- Audit correction: this revision closes four blockers an independent audit found
  in the first implementation — callee names treated as authority, an ambiguous
  import fallback, filesystem bytes deciding delivery, and an authorization with
  no lifecycle
- Quality lenses used: maintainability, verifiability, security of the control,
  and change control. This brief makes no claim of conformity to, or
  certification against, any external standard.

## Problem and intended outcome

`scripts/quality_gate.py` selects every changed Python file and hands all of them
to Ruff. The selection is per file, so the gate cannot distinguish the bytes a
change authored from the bytes it merely carried along. For ordinary work that
is the correct incremental rule: touching a file semantically means owning its
current Ruff state.

A repository-wide mechanical migration breaks that equivalence. Renaming an
import namespace rewrites one token per import in hundreds of otherwise
untouched files, and the gate then reports every historical violation in those
files as if the migration had written it.

Measured on this repository, using the pre-migration base
`5330e0dd424bfa746007034ba0672e570cc4ff0f` and the namespace-migration content at
`73494e3c095595a01cbccb36f398b24ccea47169` as the sample:

| Measurement | Value |
| --- | --- |
| Python files the migration modifies | 246 |
| Ruff violations in those files before the migration | 3853 |
| Ruff violations in those files after the migration | 3845 |
| Violations the migration actually authors | 0 |

The rename removes four `I001` findings because the canonical name sorts
differently; it introduces none. The incremental gate would nevertheless attribute
3845 violations to the change. That is false incremental debt: it is not caused
by the change, it cannot be repaid inside the change without unrelated edits, and
the only ways to make it go away — weaker rules, broad ignores, mass `noqa`, or
excluding `tests/` — all destroy the control.

The intended outcome is a general, reusable, auditable way to tell authored work
from an authorized mechanical migration, so the gate keeps full strength on the
first and stops manufacturing debt from the second.

## Scope and exclusions

In scope:

- a registry of authorized mechanical transformations;
- a proof-based classifier that decides one file's delta against that registry;
- an explicit, audited inventory of the dynamic string sites a transformation may
  rewrite;
- delivery proofs over exact Git blobs and provisional worktree proofs;
- committed authorization records bound to one exact base commit;
- deterministic loading of the classifier by the gate;
- the first registered transformation, `CANONICAL_PYTHON_NAMESPACE`.

Explicitly excluded:

- performing the namespace migration itself, or modifying
  `feature/canonical-python-namespace`;
- committing an authorization record for `CANONICAL_PYTHON_NAMESPACE`, or
  changing the CI workflow to pass one; the migration does that in its own diff;
- any change to Ruff's configured rules, severity, or scope in `pyproject.toml`;
- any `noqa`, per-file ignore, or exclusion pattern;
- LIVE Packet Tracer work, runtime product behavior, `EXTENSION/`, and any
  evidence artifact;
- `run_ruff`'s command-line length on Windows (`WinError 206`);
- changing the gate's default behavior. With no authorization, the gate selects,
  classifies, and checks exactly what it did before.

## What `MECHANICAL_ONLY` means

The boundary is an equality, not a heuristic:

```text
base revision + authorized mechanical transformation == candidate revision
```

A file is `MECHANICAL_ONLY` only when applying the authorized transformations to
the base revision reconstructs the candidate revision exactly. The comparison is
over decoded text with no normalization of any kind; because strict UTF-8
decoding is injective, equal texts are equal bytes. Nothing else — not the diff
size, not the number of changed lines, not the file name, not the branch, not a
callee's name, not a marker inside the file — can produce that classification.

What "the revisions" are depends on the gate mode:

| Mode | Base revision | Candidate revision | Standing |
| --- | --- | --- | --- |
| Delivery (`--delivery-commit`) | Stored blob at the merge base | Stored blob at the exact delivery commit | Delivery evidence |
| Worktree | Stored blob at the merge base, line endings normalized | Working-tree file, line endings normalized | Provisional only |

The five classifications are:

| Classification | Meaning | Gate effect |
| --- | --- | --- |
| `NEW_FILE` | No base revision exists | Full Ruff |
| `UNCHANGED` | The revisions are identical | Exempt: there are no new bytes |
| `MECHANICAL_ONLY` | The reconstruction equals the candidate | Exempt from Ruff |
| `SEMANTIC_OR_AUTHORED_CHANGE` | Any other delta | Full Ruff |
| `UNVERIFIABLE` | The inputs could not be obtained or decoded | Full Ruff **and** the gate fails |

### Line-ending semantics

- The authoritative delivery proof is repository blob content. Checkout line-ending
  conversion does not participate, because filesystem bytes are not the delivery
  authority: a Windows checkout of LF blobs as CRLF files yields the same decision
  as an LF checkout.
- A whitespace or line-ending change stored in Git is part of the delta. CRLF, CR,
  trailing whitespace, or a removed final newline beside a rename is authored
  work and never obtains an exemption.
- Worktree mode normalizes CRLF and CR to LF in both revisions so a local run on a
  converting checkout stays useful. That normalization makes its verdict
  provisional; it is never delivery evidence.
- The classifier itself never normalizes. Offsets into CRLF or CR text are
  computed with Python's own line terminators, so exact comparison is sound for
  any stored convention.

## Source of authority

Authority is layered, and every layer must agree before one file is exempt:

1. **Registration.** `MECHANICAL_TRANSFORMATIONS` in
   `scripts/mechanical_migration.py` is the only place a transformation, and the
   audited dynamic sites it may rewrite, can exist. It is reviewed, committed
   source. No authorization record, environment variable, command-line value, or
   in-file marker can add a transformation or a site.
2. **Authorization.**
   - Delivery: a committed authorization record passed with
     `--mechanical-authorization PATH`, read from the delivery commit's blob and
     active only while its base commit equals the comparison merge base. The
     command line refuses `--mechanical-migration` together with
     `--delivery-commit`, so a delivery exemption cannot come from a per-run flag.
   - Worktree: either an authorization record, read from the working tree and
     bound to the merge base in the same way, or `--mechanical-migration
     IDENTIFIER` for a provisional local run.
3. **Proof.** Each file is classified on its own reconstructed revision.

A developer therefore cannot declare a file mechanical. The classifier proves it,
under an authorization the gate can show was bound to this exact comparison, or
the file stays under Ruff.

## Why the mechanism is fail-closed

Every path that does not end in a completed proof ends under the Ruff gate:

- an unrecognized construct is not rewritten, so the reconstruction differs from
  the candidate and the file is authored work;
- a dynamic string at an unregistered site is not rewritten, whatever its callee
  is called;
- an unparseable base or candidate revision is authored work;
- a delta with no authorized site in it is authored work;
- a partially authorized delta is authored work, because the proof is all or
  nothing per file;
- inputs that cannot be read or decoded are `UNVERIFIABLE`, which keeps the file
  under Ruff and additionally fails the gate;
- a malformed authorization record, a missing field, an unknown field, an
  unregistered transformation, an abbreviated or symbolic base, a record absent
  from the delivery commit, or a cited brief absent from it makes the gate exit
  inconclusive (`2`);
- a well-formed record bound to any other base is inactive and grants nothing.

## Dynamic-site authority

### Threat

The first implementation rewrote a string argument whenever its callee was
spelled like a known dynamic-import or patch callable. A name proves nothing
about its binding. In

```python
def patch(target):
    return target

value = patch("src.packet_tracer_mcp.foo")
```

renaming the literal changes an ordinary string, yet the first implementation
classified it `MECHANICAL_ONLY`. The same held for `patch = custom_patch`, a local
`import_module` or `__import__`, a method bound to `find_spec`, and any object
named `monkeypatch` or `importlib`. Resolving bindings correctly would require a
Python name resolver, which this boundary deliberately does not implement.

### Design

- Import statements stay generic. The dotted name of `import src.packet_tracer_mcp...`
  and the module of `from src.packet_tracer_mcp... import ...` bind a module by
  syntax alone, so the AST recognizes them in any file.
- A dynamic string is rewritten only at an `AuditedDynamicSite` registered with
  the transformation. A site is bound to:
  - the repository-relative path of its file;
  - the SHA-256 of the exact base text it was audited in, which is
    `git cat-file blob <base>:<path> | sha256sum` for a stored blob;
  - its enclosing scope, the qualified name of the definition whose body holds it;
  - its construct, the callee as written and the argument slot;
  - the exact legacy literal;
  - its occurrence among identical references in that scope.
- A matching construct is necessary but never sufficient: registration validates
  each site against the enumerated call shapes, so an inventory cannot authorize
  `record("src.packet_tracer_mcp...")`, and matching a shape without a registered
  site grants nothing.
- The content hash binds the site to the text the audit read. Adding a shadowing
  definition to an audited file, copying its content to another path, or moving
  the literal to another construct, scope, or occurrence all miss the site.
- The classifier receives the path as input and stays pure: it reads no Git
  object and no file.

### Inventory for `CANONICAL_PYTHON_NAMESPACE`

Inventoried at `5330e0dd424bfa746007034ba0672e570cc4ff0f` by locating every
string argument that names `src.packet_tracer_mcp` in a recognized call shape,
then auditing the binding of each callee in its file. Nine such arguments exist:

| File | Scope | Construct | Callee bound by |
| --- | --- | --- | --- |
| `tests/test_cp_scale_live_cli.py` | `test_persistence_uses_the_composed_root_and_hashes_the_actual_progress` | `importlib.util.find_spec`, argument 0 | `import importlib.util` |
| `tests/test_cp_scale_live_coordinator.py` | `test_application_coordinator_is_available_without_loading_the_tool` | `importlib.util.find_spec`, argument 0 | `import importlib.util` |
| `tests/test_cp_scale_live_coordinator.py` | `test_partial_session_acquisition_closes_the_acquired_transport_once` | `importlib.util.find_spec`, argument 0 | `import importlib.util` |
| `tests/test_cp_scale_live_coordinator.py` | `test_session_reuses_resources_and_marks_close_before_a_failing_stop` | `importlib.util.find_spec`, argument 0 | `import importlib.util` |
| `tests/test_cp_scale_stage_executor.py` | `_api` | `find_spec`, argument 0 | `from importlib.util import find_spec` |
| `tests/test_cp_scale_stage_executor.py` | `test_ping_result_is_the_same_neutral_value_at_the_legacy_import` | `find_spec`, argument 0 | `from importlib.util import find_spec` |
| `tests/test_e95_e5_capability_evidence.py` | `test_default_execution_materializes_one_catalog_for_both_compositions` | `importlib.import_module`, argument 0 | `import importlib` |
| `tests/test_mutation_transport_ambiguity.py` | `test_the_connectivity_tool_budget_meets_the_floor` | `__import__`, argument 0 | the builtin |
| `tests/test_poe_delivery_qualification.py` | `test_service_degrades_dimension_encoder_rejection_to_typed_unknown` | `monkeypatch.setattr`, argument 0 | pytest fixture parameter |

None of the audited files rebinds its callee, imports with `*`, or depends on a
`conftest.py` definition of that name. The first eight are registered. The ninth
is an implicitly concatenated literal, which the boundary has never rewritten,
so it is not registered and its file stays authored work, exactly as before.

## Registered transformations

### `CANONICAL_PYTHON_NAMESPACE`

Renames `src.packet_tracer_mcp` to `packet_tracer_mcp`. Authorizing brief:
[`namespace migration`](namespace-migration.md), requirement NM9.

Authorized sites:

- the dotted name of an `import src.packet_tracer_mcp...` statement, including
  its `as` form;
- the module of a `from src.packet_tracer_mcp... import ...` statement at
  import level zero;
- the eight audited dynamic sites above, each only in its exact audited base
  text.

Never authorized, so rewriting one makes the file authored work: comments,
docstrings, f-strings, implicitly concatenated or escaped literals, a dynamic
string at any unregistered site whatever its callee is called, `from src import
packet_tracer_mcp`, a package whose name merely starts alike such as
`src.packet_tracer_mcp_legacy`, and every other edit in the same file.

Re-simulated with this implementation over exact blobs of the real migration
content, the boundary classifies 250 selected files as 234 `MECHANICAL_ONLY`
(1363 proven rewrite sites), 4 `NEW_FILE`, and 12 `SEMANTIC_OR_AUTHORED_CHANGE`.
The per-file result is identical to the first implementation's: the audited
inventory covers exactly the dynamic sites the real migration needs, and removes
only the unsound authority.

## CI authorization lifecycle

### Record

An authorization is a committed UTF-8 JSON object holding exactly these fields:

```json
{
  "schema": "cisco-mcp/mechanical-migration-authorization",
  "version": 1,
  "transformation": "CANONICAL_PYTHON_NAMESPACE",
  "base_commit": "<full 40- or 64-character lowercase commit SHA>",
  "authority": "docs/engineering/change-briefs/namespace-migration.md"
}
```

`transformation` must be registered; `authority` must equal that
transformation's registered brief and exist in the tree the record is read from;
`base_commit` must be a full lowercase SHA, never a ref, branch, or abbreviation.
Duplicate or additional fields are rejected, so a record cannot name a second
transformation, paths, or sites. The recommended location is
`scripts/mechanical_authorizations/<migration>.json`; the gate does not infer
records from any location, and each one must be passed explicitly.

### Activation

Before any classification the gate resolves the comparison base, the target, and
their merge base, then evaluates each record:

- `base_commit == merge base` — **ACTIVE**: its transformation is evaluated per
  file;
- any other merge base — **INACTIVE**: it grants no exemption and contributes no
  transformation. With no active transformation the gate does not classify at
  all, so behavior is exactly the ordinary Ruff gate.

The gate prints every record with its transformation, bound base, authority, and
state, then every exempted path. Branch names, user names, environment
variables, pull request identity, and event type never participate.

### Timeline for the namespace migration

1. The migration commits a record naming its merge base with `main` and adds
   `--mechanical-authorization <record>` to the quality job in its own reviewed
   diff.
2. Feature push CI compares with `origin/main`; while `main` has not moved, the
   merge base is the record's base, so the record is **ACTIVE**.
3. Pull request CI compares with the pull request base; the merge base is still
   the record's base, so the record is **ACTIVE**.
4. The first `main` CI after a fast-forward compares with the push's previous
   SHA, which is the record's base, so the record is **ACTIVE**.
5. Every later comparison has a different merge base, so the record is
   **INACTIVE**; by then the migration is integrated and no delta remains.
6. If `main` advances before integration, the integration CI's merge base
   differs and the record is **INACTIVE**, so the migration's files face full
   Ruff. The migration must rebase and commit a new record for the new base,
   which is reviewed again.

A stale record is harmless and visible, never a bypass. Removing it, and the
workflow argument, belongs to the migration's own cleanup.

## Deterministic classifier loading

The gate is both a script and a module. The first implementation tried
`from scripts import mechanical_migration` and fell back to
`import mechanical_migration` on any `ImportError`, so an import failure inside
the classifier silently switched to whatever module of that name the import path
offered. The gate now selects the form from its execution context:

- with a package (`import scripts.quality_gate`, `python -m scripts.quality_gate`),
  `from . import mechanical_migration`;
- as a script (`python scripts/quality_gate.py`), the sibling file loaded by its
  location, which does not search the import path and so also holds under
  `python -P`.

Neither form has a fallback, so an internal failure propagates and a decoy
`mechanical_migration` elsewhere is never loaded.

## Adding a future transformation

1. Write or extend the migration's own change brief and state why the
   transformation is mechanical.
2. Add a `MechanicalTransformation` to `MECHANICAL_TRANSFORMATIONS` whose
   `rewrite(source, path)` locates sites structurally and returns one
   `RewriteSite` per authorized position. Recognize a construct generically only
   when its syntax alone determines its meaning; any construct whose meaning
   depends on a name binding needs audited sites bound to path and base text.
3. Add positive tests for every authorized construct and negative tests for the
   nearest unauthorized neighbours of each one, including shadowed names and at
   least one case where a functional edit rides along with a valid rewrite.
4. In the migration's diff, commit an authorization record for its merge base
   and pass it to the quality job with `--mechanical-authorization`.

Transformations compose: several may be active in one run, and the
reconstruction applies them in registry order. Audited sites are fingerprinted
against the text their transformation receives, which is the base revision only
for the first transformation in that order.

## Why this cannot become a permanent bypass

- The exemption only ever applies to a delta against a comparison base, and a
  record only while that comparison's merge base is its exact base. Once the
  migration is integrated, no delta remains and the record is inactive.
- It is off unless a run passes a record or, for provisional worktree runs, a
  registered identifier; the CI quality job as configured today passes neither.
- The command line refuses a per-run flag in delivery mode, so CI cannot hold an
  unbound authorization.
- A run prints every record's state and every exempted path, so an exemption
  cannot be used invisibly.
- The proof is per file and all or nothing, so the mechanism's blast radius is
  bounded by what a registered transformation and its audited sites can express,
  not by what a change or a record claims.

## Requirements and acceptance criteria

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| MB1 | A mechanical delta is classified `MECHANICAL_ONLY` only when reconstruction equals the candidate. | Positive tests for each import form and for every audited dynamic site at its registered path; the classification carries the proven site count. |
| MB2 | Any additional delta in the same file removes the exemption. | Parameterized tests for an added statement, a functional edit, an arbitrary string edit, an unnecessary reformat, an extra import, an import reorder, a removal, and a functional edit beside audited sites. |
| MB3 | Unauthorized namespace text is never rewritten by the transformation. | Rewriting a comment, a docstring, an f-string, an inert string, an unregistered call argument, or a dynamic string at an unaudited site classifies as authored. |
| MB4 | The mechanism fails closed. | Unparseable base or candidate is authored; undecodable bytes are `UNVERIFIABLE`, stay under Ruff, and fail the gate. |
| MB5 | No file can declare itself mechanical. | An in-file marker beside a real edit still classifies as authored. |
| MB6 | The default gate is unchanged. | With no authorization, classification does not run and every changed file reaches Ruff; `tests/test_quality_gate.py` passes unmodified. |
| MB7 | Authorization is explicit and auditable. | An unregistered identifier exits 2; a focused `--files` run refuses both authorization forms; a run prints each record's state and each exempted file. |
| MB8 | The boundary is reusable. | The registry is keyed by identifier, and `namespace_transformation` builds a rename from a legacy/canonical pair and its audited sites, as the synthetic transformations in the dynamic-site tests do. Composition order is a design rule with only one transformation registered, so no test exercises it yet. |
| MB9 | A callee's name never authorizes a dynamic rewrite. | Shadowed `patch`, rebound `patch`, local `import_module` and `__import__`, a method bound to `find_spec`, and objects named `monkeypatch` or `importlib` are authored at any path; the same literal in another file, another construct, scope, occurrence, argument, or base text is authored; a malformed audited site cannot be registered; registered sites match their audited blobs. |
| MB10 | The gate loads exactly one classifier. | As a script, with and without `-P`, and as a package, the gate uses its sibling; an internal `ImportError` propagates; a decoy on the import path is never loaded. |
| MB11 | Delivery proves equivalence over exact Git blobs. | Stored LF rename is mechanical; stored CRLF, CR, trailing whitespace, or missing final newline beside a rename is authored; a CRLF checkout does not change the decision; skip-worktree filesystem bytes can neither grant nor revoke an exemption; worktree mode stays provisional. |
| MB12 | CI authorization is committed and bound to one exact base. | A record at the merge base exempts a proven file and keeps an unproven one under Ruff; a record at another base grants zero exemptions and leaves every file under Ruff; malformed, incomplete, extended, or unregistered records fail closed; records must be committed at the delivery commit with their brief; the branch name has no effect; the command line refuses a manual migration in delivery mode. |

## Architectural impact and invariants

`scripts/mechanical_migration.py` holds the classifier, the registry with its
audited sites, and the authorization parser as pure functions over text and
identifiers, with no Git or filesystem access. `scripts/quality_gate.py` keeps
ownership of Git identity, file selection, reading blobs, files, and records, and
the Ruff invocation, and calls the classifier with bytes and paths it already
resolved. That split is what makes the proof testable without a repository.

Public contract changes relative to the first implementation:

- `MechanicalTransformation.rewrite` receives `(source, path)`;
  `classify_source_change` and `classify_bytes_change` accept `path`.
- The classifier no longer normalizes line endings; worktree mode does.
- `select_worktree_changes` and `select_delivery_changes` accept keyword
  `authorizations`, and `ChangeSelection` reports `authorizations` and
  `active_authorizations`.
- The command line adds `--mechanical-authorization` and refuses
  `--mechanical-migration` in delivery mode.

Invariants that must remain true:

- Ruff rules, severities, and configuration are untouched.
- With no authorization, the gate's behavior is unchanged.
- Exemption requires registration, a base-bound authorization, and proof
  together; a delivery exemption requires a committed record.
- An unproven or unverifiable comparison never yields an exemption.
- Delivery mode keeps requiring a clean tree at the exact requested commit.

## Test design

| Level | Scope | Location |
| --- | --- | --- |
| Unit | Classifier contracts over pure source pairs, audited-site binding, registry validation, record parsing | `test_mechanical_migration_boundary.py`, `test_mechanical_dynamic_site_authority.py`, `test_mechanical_authorization.py` |
| Integration | Gate selection with temporary Git repositories, blob reading, record activation, branch invariance | `test_mechanical_delivery_blobs.py`, `test_mechanical_authorization.py`, `test_mechanical_migration_boundary.py` |
| System | The command line and its exit codes, printed audit trail, and classifier loading in isolated interpreters | `test_mechanical_authorization.py`, `test_quality_gate_import_authority.py`, `test_mechanical_migration_boundary.py` |
| Acceptance | The real audited blobs at `5330e0d` and the re-simulation over the real migration content | `test_mechanical_dynamic_site_authority.py`; the measurement above |

Shared repositories and sources live in `tests/mechanical_migration_fixtures.py`.
There is no LIVE or Packet Tracer level, because this change has no effect outside
the quality gate.

Tests derive from the requirements, not from the implementation. The shadowing,
line-ending, skip-worktree, and import-fallback tests were written first and
observed failing against `5acd39f` on their assertions: the unmodified classifier
returned `MECHANICAL_ONLY` for every shadowed callee, for unaudited dynamic
targets, for audited files classified without a path, and for committed CRLF or CR
deltas; filesystem bytes decided delivery in both directions; and a failing
classifier fell back to a decoy under `-P` and in package context. Tests of the
new contracts failed there for want of the path input, the audited-site types, or
the authorization parser. Three tests of the first implementation asserted the
defective behavior itself — name-based dynamic authority — and one asserted
classifier-level line-ending normalization; they were replaced by tests of the
corrected contract rather than kept.

Twelve mutations, each reintroducing one defect, were each detected by the focused
tests: callee-name authority, ignoring the path, the base-text hash, the
occurrence or the scope, classifier normalization, filesystem candidates in
delivery, the broad import fallback, stale records treated as active, unknown
record fields accepted, a manual migration accepted in delivery, and records read
from the filesystem in delivery.

## Residual risk and debt

- An exempted file's historical debt stays unpaid and unmeasured by the gate.
  That is the intended semantics, but it means a migration's brief, not the gate,
  is where that debt is recorded.
- An authorized rename can change import sort order, so a migration can make a
  latent `I001` newly reachable in an exempted file. Measured on the namespace
  sample the effect is favourable — four fewer findings — but a future
  transformation should measure it rather than assume it.
- Import statements are recognized generically. An unaliased
  `import src.packet_tracer_mcp.x` binds the name `src`, and renaming it changes
  that binding; the classifier does not analyze later uses of the name. The
  audited base holds no such statement — only 1381 `from` imports and 3 aliased
  imports — and the offline suite remains the behavioral backstop.
- The per-file proof cannot see bindings supplied by other files, such as a
  `conftest.py` fixture, a star import, or runtime patching of builtins. The
  audited sites depend on none of these at the audited base; a candidate that
  changes such a definition carries that change in its own authored, gated delta.
- Delivery's Ruff run still reads checked-out files. The clean-tree check does
  not detect `skip-worktree` or `assume-unchanged` index flags, which can hide
  divergent working bytes from `git status`. The mechanical proof no longer
  depends on filesystem bytes; the Ruff step does, as it did before this change.
- Worktree mode fingerprints the normalized base, so an audited file stored with
  CRLF would miss its site provisionally and classify as authored. Every Python
  file in this repository is stored with LF.
- `select_worktree_changes` and `select_delivery_changes` still accept manual
  transformations for direct Python callers and tests. Only the command line,
  which CI and the documented procedure use, enforces committed records in
  delivery mode.
- Audited sites are bound by content, not by commit. If an audited file changes at
  a future base, its sites stop matching and the file becomes authored work until
  it is re-inventoried and re-audited. New dynamic sites introduced at a later base
  are likewise authored until audited. Both failures are closed, not open.
- A stale record stays in the tree, printed as **INACTIVE**, until the migration's
  cleanup removes it.
- `run_ruff` passes every selected path on one command line. A migration-sized
  selection of several hundred absolute paths exceeds the Windows command-line
  limit and raises `WinError 206`. This is pre-existing behavior, unchanged here
  and not triggered by the configured CI quality job, which runs on Linux.
