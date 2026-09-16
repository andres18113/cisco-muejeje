# Mechanical migration quality boundary change brief

## Record

- Status: **READY_FOR_REVIEW**
- Risk: **L** — it changes an executable control that decides which files the
  incremental Ruff gate checks
- Starting point: `main` at `5330e0dd424bfa746007034ba0672e570cc4ff0f`
- Quality lenses used: maintainability, verifiability, and change control. This
  brief makes no claim of conformity to, or certification against, any external
  standard.

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
- integration of the classifier into both gate modes behind an explicit opt-in;
- the first registered transformation, `CANONICAL_PYTHON_NAMESPACE`.

Explicitly excluded:

- performing the namespace migration itself, or modifying
  `feature/canonical-python-namespace`;
- any change to Ruff's configured rules, severity, or scope in `pyproject.toml`;
- any `noqa`, per-file ignore, or exclusion pattern;
- LIVE Packet Tracer work and any evidence artifact;
- changing the gate's default behavior. With no migration authorized, the gate
  selects, classifies, and checks exactly what it did before.

## What `MECHANICAL_ONLY` means

The boundary is an equality, not a heuristic:

```text
base revision + authorized mechanical transformation == candidate revision
```

A file is `MECHANICAL_ONLY` only when the classifier can reconstruct the
candidate byte for byte by applying a registered transformation to the base
revision fetched from the comparison merge base. The reconstruction is the proof.
Nothing else — not the diff size, not the number of changed lines, not the file
name, not the branch, not a marker inside the file — can produce that
classification.

The five classifications are:

| Classification | Meaning | Gate effect |
| --- | --- | --- |
| `NEW_FILE` | No base revision exists | Full Ruff |
| `UNCHANGED` | The revisions are identical | Exempt: there are no new bytes |
| `MECHANICAL_ONLY` | The reconstruction equals the candidate | Exempt from Ruff |
| `SEMANTIC_OR_AUTHORED_CHANGE` | Any other delta | Full Ruff |
| `UNVERIFIABLE` | The inputs could not be obtained or decoded | Full Ruff **and** the gate fails |

Line terminators are outside the comparison because Git's own checkout filters
own them: this repository stores LF and checks out CRLF. Both revisions are
normalized before the proof, so a checkout convention can neither grant nor
withhold an exemption.

## Source of authority

Authority is layered, and all three layers must agree before one file is exempt:

1. **Registration.** `MECHANICAL_TRANSFORMATIONS` in
   `scripts/mechanical_migration.py` is the only place a transformation can
   exist. It is reviewed, committed source. There is no configuration file,
   environment variable, or in-file marker that can add one.
2. **Invocation.** The gate authorizes nothing by default. A run must name a
   registered transformation with `--mechanical-migration IDENTIFIER`. An
   unregistered identifier fails the gate as inconclusive rather than
   authorizing nothing silently.
3. **Proof.** Even with a transformation registered and authorized, each file is
   classified on its own reconstructed bytes.

A developer therefore cannot declare a file mechanical. The classifier proves it,
or the file stays under Ruff.

## Why the mechanism is fail-closed

Every path that does not end in a completed proof ends under the Ruff gate:

- an unrecognized construct is not rewritten, so the reconstruction differs from
  the candidate and the file is authored work;
- an unparseable base or candidate revision is authored work;
- a delta with no authorized site in it is authored work;
- a partially authorized delta is authored work, because the proof is all or
  nothing per file;
- inputs that cannot be read or decoded are `UNVERIFIABLE`, which keeps the file
  under Ruff and additionally fails the gate, because an unestablished
  classification must never read as a pass.

The analysis is structural. Authorized sites are located through the base
revision's AST — import statements, and the string arguments of an enumerated
set of dynamic import and patch callables — never by a textual search and
replace. A global replace would rewrite comments, docstrings, and inert strings,
and would therefore accept deltas this boundary must refuse.

## Registered transformations

### `CANONICAL_PYTHON_NAMESPACE`

Renames `src.packet_tracer_mcp` to `packet_tracer_mcp`. Authorizing brief:
[`namespace migration`](namespace-migration.md), requirement NM9.

Authorized sites:

- the dotted name of an `import src.packet_tracer_mcp...` statement, including
  its `as` form;
- the module of a `from src.packet_tracer_mcp... import ...` statement at
  import level zero;
- a plain string literal naming the namespace, when it is the recognized module
  argument of `__import__`, `import_module`, `importlib.import_module`,
  `find_spec`, `importlib.util.find_spec`, `patch`, `mock.patch`,
  `unittest.mock.patch`, `monkeypatch.setattr`, or `monkeypatch.delattr`.

Never authorized, so rewriting one makes the file authored work: comments,
docstrings, f-strings, implicitly concatenated or escaped literals, string
arguments of any other callable, `from src import packet_tracer_mcp`, a package
whose name merely starts alike such as `src.packet_tracer_mcp_legacy`, and every
other edit in the same file.

Simulated over the real migration content, the boundary classifies 250 selected
files as 234 `MECHANICAL_ONLY` (1363 proven rewrite sites), 4 `NEW_FILE`, and 12
`SEMANTIC_OR_AUTHORED_CHANGE`. It exempts 3706 historical violations it did not
cause and still gates 200 violations in the 16 files that carry authored edits.

## Adding a future transformation

1. Write or extend the migration's own change brief and state why the
   transformation is mechanical.
2. Add a `MechanicalTransformation` to `MECHANICAL_TRANSFORMATIONS` whose
   `rewrite` locates sites structurally and returns one `RewriteSite` per
   authorized position. Keep the recognized surface enumerated; a construct that
   cannot be recognized with certainty must be left alone.
3. Add positive tests for every authorized construct and negative tests for the
   nearest unauthorized neighbours of each one, including at least one case where
   a functional edit rides along with a valid rewrite.
4. Authorize it per run with `--mechanical-migration`, and record in the
   migration's brief the exact invocation used for delivery.

Transformations compose: several may be authorized in one run, and the
reconstruction applies them in registry order.

## Why this cannot become a permanent bypass

- The exemption only ever applies to a delta against a comparison base. Once a
  migration is integrated, no delta remains and nothing is exempt. It cannot
  accumulate.
- It is off unless a run asks for it by name, so the ordinary gate, including the
  CI quality job as configured today, grants no exemption at all.
- A run that grants exemptions prints the authorizing identifiers, every exempted
  path, and its proven site count, so an exemption cannot be used invisibly.
- A delivery that needs the flag has to put it in its own reviewed diff, and
  removing it again belongs in that migration's brief as a delivery item.
- The proof is per file and all or nothing, so the mechanism's blast radius is
  bounded by what a transformation can express, not by what a change claims.

## Requirements and acceptance criteria

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| MB1 | A mechanical delta is classified `MECHANICAL_ONLY` only when reconstruction equals the candidate. | Positive tests for each authorized construct; the classification carries the proven site count. |
| MB2 | Any additional delta in the same file removes the exemption. | Parameterized tests for an added statement, a functional edit, an arbitrary string edit, an unnecessary reformat, an extra import, an import reorder, and a removal. |
| MB3 | Unauthorized namespace text is never rewritten by the transformation. | Rewriting a comment, a docstring, an f-string, an inert string, or an unregistered call argument classifies as authored. |
| MB4 | The mechanism fails closed. | Unparseable base or candidate is authored; undecodable bytes are `UNVERIFIABLE`, stay under Ruff, and fail the gate. |
| MB5 | No file can declare itself mechanical. | An in-file marker beside a real edit still classifies as authored. |
| MB6 | The default gate is unchanged. | With no `--mechanical-migration`, classification does not run and every changed file reaches Ruff; the pre-existing gate tests pass unmodified. |
| MB7 | Authorization is explicit and auditable. | An unregistered identifier exits 2; a focused `--files` run refuses authorization; a run that exempts files prints each one. |
| MB8 | The boundary is reusable. | The registry is keyed by identifier, transformations compose, and the namespace rewriter is built from a parameterized legacy/canonical pair. |

## Architectural impact and invariants

`scripts/mechanical_migration.py` holds the classifier and the registry as pure
functions over source text, with no Git or filesystem access.
`scripts/quality_gate.py` keeps ownership of Git identity, file selection, and
the Ruff invocation, and calls the classifier with bytes it already resolved.
That split is what makes the proof testable without a repository.

Invariants that must remain true:

- Ruff rules, severities, and configuration are untouched.
- The gate's default behavior is byte-identical to the previous behavior.
- Exemption requires registration, invocation, and proof together.
- An unproven or unverifiable comparison never yields an exemption.
- Delivery mode keeps requiring a clean tree at the exact requested commit.

## Test design

`tests/test_mechanical_migration_boundary.py` covers the module contracts with
pure source pairs, the gate integration with temporary repositories, and the
command line with subprocess runs. System and acceptance levels are the gate's
own end-to-end runs in that file; there is no LIVE or Packet Tracer level,
because this change has no effect outside the quality gate.

The suite is written against the invariant rather than the implementation. Three
mutations of the classifier confirm it: replacing the AST analysis with a global
textual replace fails 12 tests, widening the call-target registry to every call
fails the unregistered-argument test, and replacing the exact reconstruction with
a line-count heuristic fails 12 tests including the adversarial one.

## Residual risk and debt

- An exempted file's historical debt stays unpaid and unmeasured by the gate.
  That is the intended semantics, but it means a migration's brief, not the gate,
  is where that debt is recorded.
- An authorized rename can change import sort order, so a migration can make a
  latent `I001` newly reachable in an exempted file. Measured on the namespace
  sample the effect is favourable — four fewer findings — but a future
  transformation should measure it rather than assume it.
- `run_ruff` passes every selected path on one command line. A migration-sized
  selection of several hundred absolute paths exceeds the Windows command-line
  limit and raises `WinError 206`. This is pre-existing behavior, unchanged here
  and not triggered by the configured CI quality job, which runs on Linux. It is
  recorded because a future wide change that is *not* mechanical would hit it.
