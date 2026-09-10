# Muejeje build-audit offline evidence

Offline QA record for the owned build-input audit (`inspect_build`, `recipe_id`,
`artifact_sha256`, `tools/build_muejeje_pts.py`).

This is a **corrected** record. The earlier version of this file was written
against an older branch line and asserted a governance model that has been
withdrawn: it named a moving branch as Muejeje's upstream, pinned a
`MUEJEJE_UPSTREAM_BASE_SHA` watermark, and claimed "upstream is an ancestor of
integration". Those claims are removed, not restated — Muejeje has its own
lifecycle and follows no branch (see the
[operating model](../architecture/muejeje-runtime-operating-model.md)). Test
counts from that line are also removed: they were measured against a different
tree and do not transfer.

The current, evidence-marked audit of record is
[the v2 preflight inventory](muejeje-pts-v2-preflight-inventory.md).

## Toolchain identity (base-independent, re-verified)

| Item | Value |
| --- | --- |
| Builder | Cisco Packet Tracer `9.0.1.0858` |
| `bin/PacketTracer.exe` SHA-256 | `843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1` |
| Packager | the in-app Scripting Interface — the only demonstrated one |
| Automation | none demonstrated: `BUILD_TOOLCHAIN_AUTOMATION_UNPROVEN` |

## Packaging readiness

Measured on the clean committed tree at `ed6195e`, with the pinned builder given
explicitly:

```text
.venv/Scripts/python.exe tools/build_muejeje_pts.py --check --builder 'C:/Program Files/Cisco Packet Tracer 9.0.1/bin/PacketTracer.exe'
PACKAGING_MANUAL_AVAILABLE; exit 0
```

| Field | Value |
| --- | --- |
| `status` | `PACKAGING_MANUAL_AVAILABLE` |
| `build_recipe_id` | `89647e0156f2149e2bef4a0835816a9b13862e7129db88d108869f0b87611cbb` |
| `source.commit` | `ed6195ef25efe0e7d732c57414e1f53108811a06`, `clean: true` |
| `inputs.reference` | `[]` |
| `packaging_state.recipe_complete` | `true` |
| `packaging_state.unresolved_build_options` | `[]` |
| `packaging_state.manual_blockers` | `[]` |
| `packaging_state.automation` | `BUILD_AUTOMATION_UNPROVEN` |
| `builder.actual_sha256` | matches the pinned hash |
| `artifact_sha256` | `null` — no artifact exists yet |

The two standing blockers are `compiler_command` and `content_validation`, both
automation prerequisites. Neither stops a human from packaging, which is exactly
the distinction the five-state model exists to keep (`MJ-016`).

**The recipe id above is a measurement, not a constant.** Source commit and tree
are part of recipe identity, so the id changes with *every* commit — including a
commit that only edits this file. That is the design working: an id that
survived a change to its inputs would identify the wrong build. Read it as "at
`ed6195e`, the audit reported this", and measure again at the commit you
actually package from — which is what step 2 of
[the packaging recipe](muejeje-pts-packaging-recipe.md) does.

Cisco's installed `help/default/` pages were read for the audit and **not** copied
into this repository. Their SHA-256 values, and what each one establishes, are
recorded in the v2 preflight inventory (eight pages, including three that the
original audit missed).

## What the tool does, and does not do

`tools/build_muejeje_pts.py --check [--builder PATH]` validates the current
repository and writes a fixed `dist/muejeje.build.json`. **It does not compile.**

- `inspect_build()` aggregates every missing or invalid input rather than failing
  on the first, checks source commit/tree and own-file correspondence to HEAD,
  requires any explicitly selected local reference to be untracked, ignored and
  SHA-256 pinned, and measures an explicitly selected builder against its pinned
  hash.
- `recipe_id()` is a canonical-JSON hashing primitive (`sort_keys`, compact
  separators, `allow_nan=False`).
- `artifact_sha256()` measures existing bytes without asserting they form a valid
  Packet Tracer module.
- Recipe and artifact IDs stay `null` while any prerequisite is unresolved.

Path containment uses `safe_name_component()` + `resolve_within()`; the CLI
rejects report destinations that are symlinks or carry multiple hard links before
writing; metadata and input reads are size-bounded; Git subprocesses have finite
timeouts.

## Regressions this suite pins

Written test-first. Beyond the basic schema and blocker-aggregation cases, the
suite pins these specific failures, each of which was a real defect found by
review rather than a hypothetical:

| Regression | Behaviour pinned |
| --- | --- |
| Hidden manifest change | a manifest whose working bytes differ from HEAD cannot claim clean source → `BUILD_SOURCE_INVALID`, `source.clean=false` |
| JSON exponent overflow | a valid-shape but non-finite value (e.g. `module_id: 1e999`) cannot crash report serialization → `BUILD_INPUT_INVALID`, exit 1, sentinels preserved |
| Report hardlink aliasing | a report destination with more than one hard link is refused before any write |
| Non-repository root | inspection refuses a root that is not the Git top-level |
| Noncanonical reference path | classified as invalid input, not silently normalized |
| Duplicate reference path | rejected rather than hashed twice |
| Malformed builder metadata | reported as an invalid input, not ignored |

## Current offline result

Run on the rebaselined branch with the checkout-local interpreter, from the
repository root, with worktree-local temporaries (per `AGENTS.md`):

```text
.venv/Scripts/python.exe -m pytest tests/muejeje -q --basetemp=tmp/m1-focused -o cache_dir=tmp/m1-focused-cache
214 passed, 2 skipped in 134.44s; exit 0

.venv/Scripts/python.exe -m pytest tests/test_worktree_isolation.py tests/test_e95_architecture_boundaries.py -q --basetemp=tmp/m1-arch -o cache_dir=tmp/m1-arch-cache
12 passed in 3.51s; exit 0

.venv/Scripts/python.exe -m pytest -q
4659 passed, 3 skipped in 305.63s; exit 0
```

M0F split the two monolithic modules into `tests/muejeje/`. The ADR-001 run this
replaced was `39 passed, 2 skipped` over `tests/test_muejeje_build.py` and
`tests/test_muejeje_build_identity.py`, which no longer exist. The muejeje area
grew from `155 passed` to `214 passed` with `runtime.capabilities`, the
build-option value gates, the layer-aware fitness gates and the claim gates.

The two skips are Windows symlink-creation privilege limitations. The hardlink
alias, hidden-source/manifest, malformed-JSON and reference-input security checks
all executed.

### The full run needs a short `--basetemp`

Run the whole suite with pytest's **default** temporary directory, as above. A
worktree-local `--basetemp` inside this checkout fails
`tests/test_cp_scale_live_governed_root.py::test_real_entry_rejects_checkout_a_with_interpreter_and_package_b_before_wrong_tree_writes`
with `git clone … returned non-zero exit status 128`: that test clones the
checkout into the temporary directory, and a deep base path pushes the cloned
`docs/reference/cp-scale/**` paths past the Windows path limit.

Measured both ways on the same tree: `--basetemp=tmp/m1-gov` fails in 1.2s, the
default temporary directory passes in 8.5s. It is a path-length limit in the
harness, not a defect in what is being tested — recorded here because the
failure names `git clone` and reads like a repository problem.

The focused runs above keep their worktree-local temporaries: none of them
clones the checkout.

## What the V6 kernel run does and does not establish

The V6 kernel checks in `tests/muejeje/` come in two kinds, and conflating them
would be the same error this document was corrected for.

| | Establishes | Does not establish |
| --- | --- | --- |
| `STRUCTURAL_VERIFIED` — always runs | the source layout, who owns `mcpDispatchV6`, `main()` and `cleanUp()`, the absence of `eval`/`new Function`/`ipc.*`, the declared `engine_script_order`, and that no document claims an operation the dispatcher does not admit | any behaviour |
| `RUNTIME_VERIFIED` — Node, skipped when absent | what *our* JavaScript does: the envelope, the whitelist, each rejection class, the session token, and both read-only results — `runtime.identify` and `runtime.capabilities` | anything about Packet Tracer |

Node is a different Script Engine implementation from Packet Tracer's. A green
Node run is evidence about the kernel's own logic and is never evidence about
`9.0.1.0858` (`MJ-015`, `AGENTS.md` rule 6). No `.pts` has been built from these
sources and the kernel has never run inside Packet Tracer, so its live state is
`NOT_YET_LIVE_VERIFIED`.

Node is optional and guarded. The suite already drives Node this way in
`tests/test_e95_serial_physical_product_slice.py`, so this adds no undeclared
dependency: with Node absent the structural gates still run and the executable
ones skip.

To reproduce the real-checkout report from a clean tree:

```powershell
.\.venv\Scripts\python.exe tools/build_muejeje_pts.py --check --builder 'C:/Program Files/Cisco Packet Tracer 9.0.1/bin/PacketTracer.exe'
```

`dist/muejeje.build.json` is ignored, machine-local audit output — not an
installable artifact and not a runtime verdict.

## Target packaging and qualification — not performed

**No `.pts` was built, imported or started, and no operation was driven inside
Packet Tracer.** Both target gates stay open, and the reason is a capability
limit, not an unresolved decision:

| Gate | State | Why |
| --- | --- | --- |
| `OFFICIAL_PACKAGING_PROVED` | `PENDING_GUI` | packaging is a native GUI procedure and no agent-operable path to it exists here |
| `TARGET_API_BASELINED` | `PENDING_TARGET` | nothing has been imported or started on the target build |
| `V6_KERNEL_VERIFIED` | `NOT_YET_LIVE_VERIFIED` | Node establishes our JavaScript; it establishes nothing about PT's engine |

What was checked, and what each check found:

- Packet Tracer `9.0.1.0858` **is installed**, and `bin/PacketTracer.exe` hashes
  to the pinned SHA-256. The audit verified this, not a person reading a version
  dialog.
- A `PacketTracer` process **was running**, with a main window, at the time of
  this record.
- The only packager is the in-app Scripting Interface. There is **no CLI and no
  documented programmatic packaging entry point** — recorded in the v2 preflight
  inventory, and the reason `automation` stays `BUILD_AUTOMATION_UNPROVEN`.
- Driving that GUI would mean synthesising native window automation against a
  running instance holding a user's session. That is not a demonstrated path;
  it is one that would have to be invented, and inventing it is precisely what
  turns "unproven" into an unfalsifiable claim.

So the remaining action is **one manual procedure**, already written down in
full: [the packaging recipe](muejeje-pts-packaging-recipe.md). Its
preconditions are met at `ed6195e` — clean tree, `PACKAGING_MANUAL_AVAILABLE`,
recipe id `89647e01…`, verified builder — so a person can start at its step 1.

When that run happens, it records: source commit and tree, the recipe id, the
externally measured artifact SHA-256, the Packet Tracer build, and the two
response envelopes verbatim. Only then do `OFFICIAL_PACKAGING_PROVED` and
`TARGET_API_BASELINED` change, and only from that evidence — never from a clean
offline report.

## Scope

This is **validator** qualification only. It establishes nothing about a
candidate `.pts`, its content, or its runtime behaviour. No `.pts` was built or
installed, no Script Module was imported or started, and no LIVE operation was
performed.

`LIVE: NO_LIVE_THIS_SESSION`
