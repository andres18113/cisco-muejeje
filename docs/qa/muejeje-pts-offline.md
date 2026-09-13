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
| Automation | none demonstrated: `BUILD_AUTOMATION_UNPROVEN` |

## Packaging readiness

Two measurements, on two machines, and they say different things because the
machines differ — not because the repository changed under them.

**With the pinned builder installed**, recomputed on the clean committed tree at
`deb13b2`:

```text
.venv/Scripts/python.exe tools/build_muejeje_pts.py --check --builder 'C:/Program Files/Cisco Packet Tracer 9.0.1/bin/PacketTracer.exe'
PACKAGING_MANUAL_AVAILABLE; exit 0
```

| Field | Value |
| --- | --- |
| `status` | `PACKAGING_MANUAL_AVAILABLE` |
| `build_recipe_id` | `568a863532ba0e2aea130ad5e556b6ab74a0c0505a7944af0f4055f9ec5801d1` |
| `source.commit` | `deb13b2d5935793811c3b8b6f2b569b16ea63ba3`, `clean: true` |
| `source.tree` | `59f9e47fb677b09522d0f090fd452547563de910` |
| `inputs.artifact` | 23 files, all under `muejeje_pts/`; the engine files run `010_core.js` to `220_lifecycle.js` |
| `inputs.tooling` | 8 files, the whole auditor |
| `inputs.reference` | `[]` |
| `packaging_state.recipe_complete` | `true` |
| `packaging_state.unresolved_build_options` | `[]` |
| `packaging_state.manual_blockers` | `[]` |
| `packaging_state.automation` | `BUILD_AUTOMATION_UNPROVEN` |
| `builder.actual_sha256` | matches the pinned hash |
| `artifact_sha256` | `null` — no artifact exists yet |

**Clean means nothing untracked is left in the checkout either.** The audit
counts every line of `git status --porcelain --untracked-files=all`, so an
untracked, unignored file of any kind reads as a dirty source — and the
blocker it reports, `dirty tracked source`, names no file. The first run of
this measurement hit exactly that: an agent integration had left a cache
directory, `.atl/`, in the checkout, and the audit reported
`BUILD_SOURCE_INVALID` with no recipe id until the directory was excluded in the
repository's local `info/exclude` — not in the tracked `.gitignore`. The rule is
right, because a recipe has to describe a state someone can name; it is
recorded because nothing in the refusal says where to look.

**Without it**, on the Linux container this line was developed in, at
`bd7250e`, an earlier commit on this line:

```text
.venv/bin/python tools/build_muejeje_pts.py --check
BUILD_TOOLCHAIN_BLOCKED; exit 1
```

| Field | Value |
| --- | --- |
| `status` | `BUILD_TOOLCHAIN_BLOCKED` |
| `blockers` | `missing explicit builder path`, and the two automation prerequisites |
| `build_recipe_id` | `null` — no id is issued outside `PACKAGING_MANUAL_AVAILABLE` |
| `source.commit` | `bd7250e77f386664440214c50e3bf3e180f87587`, `clean: true` |
| `source.tree` | `88f6e97d989d08ac65761cec692ce00524a7112d` |
| `inputs.artifact` | 19 files, all under `muejeje_pts/` |
| `packaging_state.recipe_complete` | `true` |
| `packaging_state.unresolved_build_options` | `[]` |
| `packaging_state.manual` | `PACKAGING_MANUAL_UNAVAILABLE` — one blocker, the builder |

**That difference is the five-state model working** (`MJ-016`). Nothing about
the repository is unresolved on either machine: the recipe is complete in both
readings and no build option is missing. What the second machine lacks is
Packet Tracer, and the audit says so in the one field that means it rather than
reporting the tree as invalid. A `BUILD_TOOLCHAIN_BLOCKED` here is a fact about
this container; it is not a regression, and it is not a claim that packaging is
impossible.

`build_options` at `bd7250e`: `module_id`
`io.github.andres18113.muejeje.runtime`, `startup` `on_startup`, `privileges`
`[]`, one Custom Interface file, and an eighteen-file `engine_script_order` —
core, protocol, envelope admission, argument rules, what a platform reading is,
the call boundary, the four subject adapters alphabetically, the six operations
alphabetically, then dispatch, then lifecycle.

**A report cannot carry its own commit's recipe id.** Source commit and tree are
part of recipe identity, so committing this file changes the id it records. The
measurement above is therefore at the commit *before* the one that writes it
down, which is the only order that can exist; re-running the one command above
gives the id at whatever HEAD you are on, and step 2 of
[the packaging recipe](muejeje-pts-packaging-recipe.md) is where a packaging run
does exactly that.

**The recipe id is a measurement, not a constant**, and that is the design
working: an id that survived a change to its inputs would identify the wrong
build. Read it as "at `deb13b2`, on that machine, the audit reported this".

**It also depends on the line endings of the checkout it was measured in.** The
audit hashes the *working* bytes of each declared input, and the Windows
checkout uses `core.autocrlf=true`, so a fresh clone and that worktree can
disagree on the id while agreeing on every commit. That is a property of the
measurement rather than a defect in it — the recipe's own anchors, the manifest
hash and the source commit and tree, are byte-stable — but it means one recipe
id is comparable only with another measured the same way. Recorded here because
a mismatch between two machines otherwise reads like a tampered input.

Cisco's installed `help/default/` pages were read for the audit and **not** copied
into this repository. Their SHA-256 values, and what each one establishes, are
recorded in the v2 preflight inventory (eight pages, including three that the
original audit missed). The IpcAPI class pages every admitted platform member
is documented on are pinned separately, by hash, in
`tests/muejeje/test_platform_reference.py`, which re-reads each one on a
machine that has the target build. The three pages the unread links rest on —
`Link`, `Cable` and `Antenna` — are pinned the same way in
`tests/muejeje/test_workspace_links_blocked.py`.

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
- **The audit compiles the auditor it runs.** Before any project module is
  imported, the entry point points `sys.pycache_prefix` at a directory created
  for that one invocation, outside the checkout, and removes it when the
  invocation ends. Every auditor module is then compiled from its source into
  that directory, and no `__pycache__` in the tree is read or written. Ordinary
  imports do not guarantee this: Python executes a timestamp-based `.pyc`
  whenever it records the source's mtime and size, and a worktree on this line
  that had been moved kept such an entry in front of different code. `-B` is not
  the mechanism, because it stops writes and still reads. **No cache has to be
  purged before an audit.** The run refuses, with no report, if the entry point
  was imported with `-m` instead of run by path, if the directory would be
  inside the checkout, or if an auditor module was loaded before isolation or
  not compiled from its source into that directory. The directory is never
  reported and is not part of recipe identity; the entry point itself is a
  declared tooling input, so a change to it changes the recipe id.

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
| Stale adjacent bytecode | a `build_state` cache compiled from a forged classifier, recording the current source's size and mtime, makes ordinary imports issue `PACKAGING_MANUAL_AVAILABLE` and a recipe id; the entry point reports what the current source decides, leaves the cache in place, and compiles into its own directory outside every checkout on each invocation. Code it did not compile — loaded before isolation, or from bytecode with no source — is refused |
| Partial privilege declaration | a clean committed manifest declaring `[]`, one token, the evidenced minimum or any other proper subset — every name a real serialized token — reached `PACKAGING_MANUAL_AVAILABLE` with a `build_recipe_id`, because the gate validated the vocabulary and nothing validated the policy. The two questions are now asked separately: vocabulary first, so a namespace fault keeps its own reason, then the declaration, which admits only `list(DECLARED_PRIVILEGES)` in canonical order. Anything else is `BUILD_INPUT_INVALID` with no recipe id, and the whole eleven in another order is refused as an order |

## Where an unavailable reading stopped

The executable change at `30ac927`, and the only thing in it that the `6233d86`
result asked for.

**The defect.** Every unavailable platform reading said *what* happened —
`PLATFORM_ABSENT`, `PLATFORM_MEMBER_ABSENT`, `PLATFORM_CALL_FAILED`,
`PLATFORM_ANSWER_UNUSABLE` — and nothing about *where*. For
`platform.module_descriptors` that is not a small gap: eight interface members
sit between a `factory_index` and a finished chassis tree, and every one of them
produces `PLATFORM_ANSWER_UNUSABLE` — a value this runtime cannot carry back
unchanged, or a descriptor the platform would not hand over inside a count it
reported itself. The `6233d86` run returned exactly that word, and the result
could not say which of the eight it was.

**What was added.** Two fields beside `unavailable_reason`, on every platform and
workspace reading:

```text
unavailable_member    the Interface.member the reading stopped at, or null
unavailable_argument  the position or value that call was made with, or null
```

The stage is recorded at the platform-call boundary — the only file that knows
which member a reading is at, since the thrown sentinel deliberately carries no
location (`MJ-005`) — and cleared where every reading begins, so no reading can
publish the member a previous one stopped at. It is published by the adapter that
shapes the unavailable reading, and only there: an `OBSERVED` reading stopped
nowhere and reports `null`, and an `ENGINE_EXCEPTION` produces no reading at all,
so a defect in this artifact still cannot leave a Packet Tracer member's name in
a result.

**It names a place, never a cause.** The reason stays the authority on what
happened; a privilege denial is still only what Packet Tracer printed beside the
call; and nothing the adapters refuse becomes acceptable because it is now
identified. At that candidate a `null` handed back inside a reported count was
still `PLATFORM_ANSWER_UNUSABLE`, and it was **not** read as "this position is
empty" — no target reading supported any semantic for it yet (`MJ-015`,
`MJ-022`, `MJ-031`). The `504a6e6` run stopped exactly there; the next section is
what changed the first half, and nothing changed the second.

**What it is not.** It is not a fix. Nothing in that candidate was supposed to
make `platform.module_descriptors` answer, and nothing in it did. The cause of
the `6233d86` result is **not established**, and this record does not guess one:
what is established offline is that the chain is target-proven up to and
including `DeviceDescriptor.getType()` — `platform.device_descriptors` and
`platform.module_type_support` were `OBSERVED` at the same index — so the stage
lies at or beyond `DeviceDescriptor.getRootModule()`, among eight members the
next run can now name.

**Written RED first, and the RED was measured rather than asserted.** The two new
gate modules were run against the unchanged engine before the change was
restored: `31 failed, 1 passed`. Against the changed engine: `32 passed`. The one
that passed in both is the guard that a failure envelope carries no member, which
is true whether or not the field exists — it is a guard, not a discriminator, and
it is recorded as one. The discriminating cases pin the exact member for each of
the eight stages, one planted fault at a time, so a stage that drifted one call
early or late fails here rather than sending the next run's reader to the wrong
member.

## A null inside the module count — what `504a6e6` found, and the correction

The one executable change in this candidate. It exists because the `504a6e6`
run, carrying all eleven tokens, did what the stage was added for and named the
member: `platform.module_descriptors` stopped at `ModuleDescriptor.getModuleAt`,
argument 0, `PLATFORM_ANSWER_UNUSABLE`. The run is recorded under *The run at
`504a6e6`*, below.

**What the target investigation after it found, on `9.0.1.0858` and nowhere
else.** It was performed by hand outside this session and reported to it; no
transcript of it is committed:

```text
inside 0 <= i < getModuleCount()   getModuleAt(i) answered a ModuleDescriptor or null
outside that range                 Packet Tracer raised "invalid vector subscript"
survey                             172 DeviceDescriptor entries, 669 ModuleDescriptor nodes
positions asked                    1551: 497 objects, 1054 null, 0 errors inside the range
mixed nodes                        a null can precede a module at a later position
first failing shape                a root handing over one module whose count of two answered null, null
```

So a `null` there is **not** an index this runtime got wrong, and on that build
it is ordinary. Refusing it made the reading unavailable on the first chassis
that had one, and a walk that stopped at it would lose every module after it.

**What a null means is not established**, and the reading says only what was
seen. Each node publishes

```text
null_module_positions   positions actually asked below module_count where Packet Tracer handed back JavaScript null
```

and nothing else about them: not an empty slot, not a free or unused slot, not
absent hardware. Nor does any of this say that a module count equals a slot
count: `getSlotCount()` stays a second enumeration the reading keeps apart
(`MJ-014`, `MJ-015`).

**How each answer at a position is read.**

| `getModuleAt(i)` inside the count | Reading |
| --- | --- |
| a `ModuleDescriptor` | handed over, queued and walked; the walk continues |
| `null` | `i` is appended to that node's `null_module_positions`; the walk continues |
| the call throws | `PLATFORM_CALL_FAILED`, stage `ModuleDescriptor.getModuleAt` with argument `i` |
| `undefined` | `PLATFORM_ANSWER_UNUSABLE`, the same stage |
| any other value that is not an object | `PLATFORM_ANSWER_UNUSABLE`, the same stage — `0`, `false` and `''` included, which a truthiness test would have read as a null |

**The boundary change is generic, not a module workaround.** Every member that
hands over an object — eight of the 27 — used to fold `undefined` into `null`.
The boundary now hands `null` over as `null` and refuses `undefined` and every
primitive as `PLATFORM_ANSWER_UNUSABLE`, for all eight alike. Which `null` is an
answer stays each adapter's decision: a null root module is still an observed
absence, and a null device or port inside a count is still unusable.

**Two budgets, because a position is not a node.** A null answers a call and
costs no node, so the calls are counted as calls. Every bound is Muejeje's own,
not a Packet Tracer limit (`MJ-029`):

| Bound | Spent by | When it runs out |
| --- | --- | --- |
| `MAX_MODULE_POSITIONS` = 512 | every `getModuleAt` call one reading makes, a null and a module alike | a node's positions are reserved before any is asked; a node that does not fit asks none, and says `children_truncated` while the reading says `module_positions_truncated` |
| `MAX_MODULE_NODES` = 512 | each node this reading keeps — queued, walked and published — never a null, and never a module dropped with a refused child set | judged once a node's positions have answered; a child set that does not fit is refused whole, `children_truncated` and `nodes_truncated` |
| `MAX_MODULE_DEPTH` = 12 | depth, unchanged | refused before any position is asked, `children_truncated` and `depth_truncated` |
| `MAX_SLOTS` = 64 | slot types, the other enumeration, unchanged | `slot_types_truncated` |

**Separate units, and the same worst case as before.** Until this correction the
node ceiling reserved these calls itself, so one reading asked at most
`MAX_MODULE_NODES` of them; the position budget stays within that, and a gate
holds the two in that order. The survey's 1551 positions were one sweep of all
172 descriptors at once, not one reading of one of them, and size no per-request
bound: a descriptor that needs more positions than this would be evidence about
that descriptor, to weigh on its own.

**What each budget can and cannot say.** A position nobody asked is never in
`null_module_positions`. A node refused on the node budget did ask its positions
first, so Packet Tracer had already handed those modules over and this reading
keeps none of them: `MAX_MODULE_NODES` bounds what a reading retains, never what
the platform built on its own side to answer the calls it did make.

**The result grew and nothing else moved.** `module_positions_truncated` joins
`nodes_truncated` and `depth_truncated`, and every node gains
`null_module_positions`; both are frozen in the V6 shape gates, and nothing was
removed, renamed or retyped. Eight read-only operations, one `mcpDispatchV6`, the
same 27 admitted `Interface.member` entries — `ModuleDescriptor.getModuleAt`
among them already — and `FULL_TRUSTED_MODULE` with its eleven tokens are all
unchanged and gated. No mutation, transport, link or M4 work is in it.

**Written RED first, and the RED was measured.** The new gate module
`test_platform_module_positions` and the updated shape, boundary, stage, modules,
walk and relay-closure gates were run against the unchanged engine:
`26 failed, 107 passed`. The passes include guards rather than discriminators: an
`undefined` at position 0 was already unusable, through the old fold into `null`.
Against the changed engine, with the stage-scope, compatibility and architecture
gates beside them: `176 passed`.

**And the bound was corrected before anything was packaged.** `MAX_MODULE_POSITIONS`
was first set to `2048`, sized against the survey total, which widened the
`getModuleAt` calls one reading could make past the `512` the node ceiling had
reserved for them. The correction was written as RED first: against the `c0b654a`
engine the position and walk gates ran `2 failed, 32 passed` — the declared bounds
in the wrong order, and the widest reading asking `2048` calls where at most `512`
had been asked before — and `33 passed` against the corrected bound. No other
semantics moved with it: `null` versus `undefined`, `null_module_positions`, the
truncation marks, the failure taxonomy and the V6 shape are as `c0b654a` left them.

## Recorded offline results

Two environments have run this suite, and the record keeps them apart: a
measurement is only comparable with another taken the same way.

**Windows, with Packet Tracer `9.0.1.0858` installed**, at `deb13b2` — the
machine that has the target build, and the one this line was measured on
(checkout-local `.venv`, Python 3.12.10, pytest 9.1.1, Node v24.19.0):

```text
.venv/Scripts/python.exe -m pytest tests/muejeje -q -p no:cacheprovider
761 passed, 2 skipped in 286.10s; exit 0

.venv/Scripts/python.exe -m pytest tests/test_worktree_isolation.py tests/test_e95_architecture_boundaries.py -q -p no:cacheprovider
12 passed in 5.00s; exit 0

.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
5206 passed, 3 skipped, 4 warnings in 497.47s; exit 0
```

Node drove the kernel checks. The earlier Windows readings — `353 passed` at
`fc9e460`, `555 passed` at `96976de` and `738 passed` at `d14692d` — are
superseded rather than kept beside this one: each measured a different tree on
the same machine, which is exactly the comparison this record separates
environments to prevent.

**Linux, with Packet Tracer absent**, at `bd7250e` — the container this line was
developed in, checkout-local `.venv` (Python 3.11.15, pytest 9.1.1), Node
v22.22.2:

```text
.venv/bin/python -m pytest tests/muejeje -q
496 passed, 9 skipped in 33.30s; exit 0

.venv/bin/python -m pytest tests/test_worktree_isolation.py tests/test_e95_architecture_boundaries.py -q
12 passed in 2.99s; exit 0

.venv/bin/python -m pytest -q
4940 passed, 11 skipped in 311.37s; exit 0
```

**The skip counts differ for a reason, and it is the one the guards exist for.**
On Linux the two Windows symlink-privilege skips do not apply and pass instead,
while nine checks skip because there is no installed Packet Tracer to read: the
three that quote Cisco's Script Engine lifecycle sentences, the four that
re-derive the privilege identifiers from the installed reference, and the two
that measure the pinned builder. A machine without the target build reports what
it could not check rather than inventing a verdict about `9.0.1.0858`
(`MJ-015`). The hardlink-alias, hidden-source/manifest, malformed-JSON and
reference-input security checks ran in both.

**A green run on either machine establishes the same thing and no more**: what
this repository's own code does. Neither is evidence about Packet Tracer, and
the Linux run is not evidence that packaging works — it is a run of the audit
and the kernel, on a machine with no builder (see *Packaging readiness*).

The muejeje area grew from `155 passed` to `214` with `runtime.capabilities` and
the layer-aware fitness gates, to `353` with the kernel hardening and the first
M2 slice, to `409` with the platform-call boundary and the chassis reading, to
`496` with `platform.module_type_support` and the first workspace reading, and
to `555` with relay closure, three attribution corrections and the first M3
capability, to `738` with a platform boundary enforced per interface member,
exact-integer addressing in named domains and `network.device_ports`, to `748`
with the pinned link evidence and the qualification entry point, and to `761`
with engine files named for the order Packet Tracer lists them, the audit gate
that holds the manifest to that order, and the refusal, restart and diagnostics
steps of the official run, and to `908` with this line: the
`FULL_TRUSTED_MODULE` privilege policy, a privilege-scope baseline frozen as
literals rather than aliased to the collections it checks, and the stage an
unavailable platform reading stops at; and to `959` with `null_module_positions`,
a position budget kept apart from the node budget, and a boundary that no
longer folds `undefined` into `null`.

Twenty-one test modules have been split out along the way, each because its
predecessor crossed the 300-line budget rather than because anyone chose to —
most recently `test_platform_stage_scope` out of `test_platform_stage`,
`test_privilege_api_symbols` out of `test_privilege_evidence`, and
`test_live_outcomes` out of `test_live_runbook`, and before them
`test_network_port_values` out of `test_network_ports`. The artifact split the same way and
for the same reason: `validation_v6.js` and then `arguments_v6.js` out of
`protocol_v6.js`, and `platform_reading.js` plus one adapter per subject out of
`platform_adapter.js`. That is `MJ-020` doing what it is for — the budget forced
each split at the point a file stopped being readable in one sitting.

**One exception table is no longer empty, and the entry is argued rather than
inherited.** `muejejeV6OperationTable` is the V6 whitelist: a declaration with
no branch and no loop, whose length is the number of admitted operations rather
than the amount a reader must follow. Splitting it would split the one thing
that has to be readable in a single place (`MJ-008`). The function budget had no
staleness gate — the file-level one did — so it has one now, because an
exception nobody rechecks is a standing permission rather than an argument.

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

The focused runs above could keep worktree-local temporaries, since none of
them clones the checkout; this record ran them with the default one as well.

### A local runner's result is operational evidence, not a gate

On the Windows machine this line is developed on, the suite is also run through
a coordination runner kept under the repository's Git directory,
`.git/agent-coordination/run_pytest_isolated.py`, which gives each run its own
temporary and bytecode directories. **That runner is machine-local: it is not
tracked, it is in no commit, and nothing this repository verifies depends on
it.** A result it produced is operational evidence about one run on one
machine. It is not a repository-governed verification gate, and citing it does
not make it one, because no reader of a clean checkout can inspect the runner
that produced it.

What the repository governs about stale bytecode is in the tree: the audit's
own isolation, and `tests/muejeje/test_audit_bytecode_isolation.py`, which
reproduces the failure against it. The independent evidence for a candidate is
CI on the exact pushed SHA, which starts from a clean checkout.

## What the V6 kernel run does and does not establish

The V6 kernel checks in `tests/muejeje/` come in two kinds, and conflating them
would be the same error this document was corrected for.

| | Establishes | Does not establish |
| --- | --- | --- |
| `STRUCTURAL_VERIFIED` — always runs | the source layout, who owns `mcpDispatchV6`, `main()` and `cleanUp()`, the absence of `eval`/`new Function` and of `ipc` outside the one declared adapter, the declared `engine_script_order`, and that no document claims a capability this artifact does not have | any behaviour |
| `RUNTIME_VERIFIED` — Node, skipped when absent | what *our* JavaScript does: the envelope, every bound, each rejection class, the session token, and the two platform-free results — `runtime.identify` and `runtime.capabilities` | anything about Packet Tracer |
| `STUB_DRIVEN` — Node, skipped when absent | what the *platform adapters* do with a well-formed answer, with an unusable one, with a call that throws, and with no platform object at all; where a bounded walk stops and what it marks; which methods were actually called; and that a defect inside an adapter comes back as `ENGINE_EXCEPTION` rather than as a platform reading | anything about Packet Tracer's hardware factory, or about whether these calls are permitted there |

**The third row is the one to be careful with.** Every platform and network
operation was driven against a stub that answers with Cisco's documented
getter names, logging the interface each call landed on, and
whose chassis shape was copied from a reading this repository actually recorded
against `9.0.1.0858`. A stub written from a recording is still not the
implementation: it proves our adapters read a well-formed answer correctly and
refuse a malformed one, and it proves they asked for nothing outside the
documented set — which is a claim about *our code*, checked by comparing the
recorded call log against that set, in both directions. It is not evidence that
Packet Tracer answers those calls or that it answers them with these shapes —
and a module with `privileges: []` has since been observed not to be allowed the
root ones at all (see *The official LIVE run at `d37ba37`*).

Node is a different Script Engine implementation from Packet Tracer's. A green
Node run is evidence about the kernel's own logic and is never evidence about
`9.0.1.0858` (`MJ-015`, `AGENTS.md` rule 6). The kernel's live state is no
longer `NOT_YET_LIVE_VERIFIED`: a governed artifact was built from these
sources and its own engine answered inside Packet Tracer, which is
`V6_KERNEL_VERIFIED = PASS`. That is a verdict about the kernel, and still none
about the platform — every platform call that artifact made was denied.

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

## Target packaging and qualification

**A governed `.pts` has been packaged, imported, started and driven.** The
official run at `d37ba37` followed the recipe end to end and is recorded below.
Two runs exist in total: that one, and an earlier *exploratory* module whose
engine files carried names no recipe declared — kept as evidence about Packet
Tracer, promoting nothing.

**Every row below names the artifact it is about.** A verdict belongs to the
bytes that produced it. Four artifacts have run — `d37ba37` (`[]`), `718db50`
(`GET_NETWORK_INFO`), `6233d86` (both evidenced tokens) and `504a6e6` (all
eleven) — and the latest *qualified* one is still `718db50`. The `6233d86` run
produced real target evidence and is **not** a canonical qualification: its
workspace fixture was corrected during execution, so it did not satisfy the
procedure as written, and what it observed is recorded for what it is. The
`504a6e6` run is target evidence too: no transcript of it is committed, so this
record cannot establish it as a canonical qualification. The new candidate reads
a `null` inside a module count as an answer: a different recipe id identifying
different bytes, neither packaged nor run. Reading any earlier artifact's `PASS` as the candidate's would
let a run that never happened look like one that did, so they are separated here
and stay separated.

```text
LAST_QUALIFIED_ARTIFACT (718db50)
  PACKAGING                    = PASS
  V6_KERNEL                    = PASS
  GET_NETWORK_INFO_ROOT_ACCESS = PASS
  RAW_TRANSCRIPT               = NOT_CAPTURED

TARGET_EVIDENCE_ONLY (6233d86)
  FIXTURE_CORRECTED_DURING_RUN = YES
  CANONICAL_QUALIFICATION      = NO
  CHANGE_NETWORK_INFO_MEMBERS  = ANSWERED
  RAW_TRANSCRIPT               = PARTIAL

TARGET_EVIDENCE_ONLY (504a6e6)
  FULL_TRUSTED_SET             = ALL_ELEVEN_SELECTED
  READINGS_OBSERVED            = FIVE_OF_SIX
  MODULE_DESCRIPTORS_STAGE     = ModuleDescriptor.getModuleAt(0)
  CANONICAL_QUALIFICATION      = NOT_ESTABLISHED
  RAW_TRANSCRIPT               = NOT_COMMITTED

CURRENT_NEW_CANDIDATE
  PACKAGED                     = PENDING
  V6_LIVE                      = PENDING
  MODULE_DESCRIPTORS_LIVE      = PENDING
  RAW_TRANSCRIPT               = REQUIRED_COMPLETE
```

`M1_CORE_READY = YES` is the milestone state the governed artifacts
established, and it stays there. No candidate-specific state moves until the
candidate produces its own evidence, out of its own transcript.

| Gate | State | Why |
| --- | --- | --- |
| `OFFICIAL_PACKAGING_PROVED` | `PASS` **for `d37ba37` and `718db50`** | each recipe produced a saved `dist/muejeje.pts` that Packet Tracer loaded and started, and each artifact was measured externally |
| `V6_KERNEL_VERIFIED` | `PASS` **for `d37ba37` and `718db50`** | each saved artifact's own engine answered: `mcpDispatchV6` present, identify and capabilities, all five refusal classes, and identify again across a stop and a start |
| `GET_NETWORK_INFO_ROOT_ACCESS` | `PASS` **for `718db50`** | carrying `GET_NETWORK_INFO`, that artifact reached `IPC.hardwareFactory()` and `IPC.network()` — both roots progressed where the `[]` artifact was denied |
| `TARGET_API_BASELINED` | `PENDING_TARGET` | members have now answered — the `6233d86` run reached `getAvailableDeviceCount` and `getName` and read three readings `OBSERVED`, and the `504a6e6` run read five — but neither is a canonical qualification this record can establish. A baseline waits on a run that satisfies the procedure |
| `CAPABILITY_RESOLUTION_VERIFIED` | `PENDING_TARGET` | three of the six platform and workspace capabilities answered on the `6233d86` run and five on the `504a6e6` run; no capability is resolved off a run this record cannot establish as a canonical qualification |
| `GET_NETWORK_INFO_BINARY_EVIDENCE_RECORDED` | `PASS` | both root calls require privilege index 1 in the pinned binary, and index 1 serializes as `GET_NETWORK_INFO`. Recorded, against a pinned SHA-256 ([the privilege map](muejeje-pts-privilege-map.md)) |
| `BINARY_MAP_REPRODUCIBILITY` | `PENDING` | the root map was supplied from outside this repository and the member requirements are a Ghidra reading with exact addresses; nothing here re-derives either by running it, so no reader of this checkout can reproduce a row from the repository alone |
| `GET_NETWORK_INFO_LIVE_VERIFIED` | `PASS` | the `718db50` run carried the token and reached both roots on `9.0.1.0858` |
| `CHANGE_NETWORK_INFO_MEMBER_EVIDENCE_RECORDED` | `PASS` | two read members require privilege index 2 (`CHANGE_NETWORK_INFO`), read from the pinned binary by Ghidra with verbatim addresses ([the privilege map](muejeje-pts-privilege-map.md)) |
| `CHANGE_NETWORK_INFO_LIVE_VERIFIED` | `PASS` | the `6233d86` run carried the token and both index-2 members answered on `9.0.1.0858` — for those two members, and for no others |
| `CURRENT_NEW_CANDIDATE_PACKAGED` | `PENDING` | the candidate's recipe reaches `PACKAGING_MANUAL_AVAILABLE`, and no `.pts` has been saved from it |
| `CURRENT_NEW_CANDIDATE_V6_LIVE_VERIFIED` | `PENDING` | the kernel verdict belongs to the artifact that ran. This candidate has not run, so it inherits nothing from `718db50`, `6233d86` or `504a6e6` |
| `PRIVILEGE_POLICY` | `FULL_TRUSTED_MODULE` | a deployment decision, not a reading: Muejeje is a private local tool packaged as a trusted Script Module, so the manifest declares all eleven serialized tokens. No token is recorded as required ([the privilege map](muejeje-pts-privilege-map.md)) |
| `FULL_TRUSTED_SET_LIVE_VERIFIED` | `PASS` **for `504a6e6`** | that artifact declared all eleven, was run with every box selected, and the operator reported no reached call privilege-denied. It is a verdict about the selection working; nine of the eleven tokens are still carried by no call evidence at all |
| `PRIVILEGE_SCOPE_UNCHANGED` | `PASS` | the full-trust change adds no V6 operation and no admitted `Interface.member`, and neither does the null-position correction: eight read-only operations and 27 members, both frozen as literals in `test_privilege_scope` rather than read from the collections they check |
| `MODULE_DESCRIPTORS_STAGE_IDENTIFIED` | `PASS` **for `504a6e6`** | the reading stopped at `ModuleDescriptor.getModuleAt`, argument 0, `PLATFORM_ANSWER_UNUSABLE`: a `null` inside the count, which that artifact's adapter refused |
| `GET_MODULE_AT_NULL_INSIDE_COUNT` | `TARGET_OBSERVED` | on `9.0.1.0858` only: 1551 positions over 172 descriptors, 497 modules and 1054 nulls, no error inside the range. Operator-reported, no transcript committed, and what a null means is not observed |
| `MODULE_DESCRIPTORS_LIVE_OBSERVED` | `PENDING` | the corrected walk has run under Node only. Whether it answers `OBSERVED` inside Packet Tracer is what this candidate's run measures |
| `DEVICE_DESCRIPTOR_ADDRESS` | `FACTORY_INDEX_WITHIN_ONE_OBSERVATION` | neither a model nor a model and DeviceType is unique on that build, so `factory_index` stays an address inside one observation and never a persistent identifier — see *What addresses a device descriptor* |
| `DEFAULT_VARIANT_ON_CREATION` | `TARGET_OBSERVED_NOT_IMPLEMENTED` | recorded for the models tested on `9.0.1.0858`; no creation logic exists or changed — see *Which variant a creation selects* |

### The official LIVE run at `d37ba37` — the governed artifact

Performed by hand on Packet Tracer `9.0.1.0858`, following
[the packaging recipe](muejeje-pts-packaging-recipe.md) from step 1. No
privilege was changed at any point.

**What this record preserves is the operator-reported observations, not the
run's raw envelopes.** An earlier revision of this section said the run was
reported back "verbatim"; it was not, and no raw transcript was captured, so
none is attached and none is reconstructed here — writing JSON nobody recorded
would manufacture the very evidence this page exists to keep honest. What the
operator reported is which statement was entered, whether it came back `ok` or
unavailable, and what Packet Tracer printed beside it; that summary is below
and is the whole of what this run establishes.

```text
OFFICIAL_RUN_D37BA37_RAW_TRANSCRIPT = NOT_CAPTURED
```

**So this run is not field-level LIVE verification of any result shape.** It
establishes official packaging, kernel execution, the lifecycle across a stop
and a start, the observed rejection classes, and the privilege denial
diagnostics — each of which the operator observed and reported. It does not
establish that any envelope carried the fields V6 specifies, because no
envelope was preserved to check. Every run since has been required to preserve
one raw transcript per execution
([the full-trust LIVE runbook](muejeje-pts-privilege-live-runbook.md)), and
none has yet done so completely: `718db50` captured none and `6233d86`
captured a prefix. The requirement stands; it has not yet been met.

| Record | Value |
| --- | --- |
| candidate | `d37ba37786107ed8128d17d589d889ee1fe9b16f`, tree `d467133b551088441e07bf4a34d50de323c927d3` |
| `build_recipe_id` | `7d5e710723151a67e2df84dcb11d43b31ad7a89cba8ae2410cdf987689d216bb` |
| artifact | `dist/muejeje.pts`, SHA-256 `6951c066ec158d57855dfd739619482cd05f40e007f5c28fb5fcc66e58a12146`, 48185 bytes, measured outside the artifact (`MJ-017`) |
| Packet Tracer | `9.0.1.0858`, `PacketTracer.exe` SHA-256 `843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1` |
| privileges | `[]` — none selected, and none selected later |
| entry point | the module's Debug Dialog |
| raw transcript | **not captured** — this record preserves the operator-reported observations |

**What it established.**

1. **The governed engine order held.** Packet Tracer listed the 22 engine files
   `010_core.js` through `220_lifecycle.js`, in that order — the order
   `build_options.engine_script_order` declares, carried by the file names. The
   packaging correction made at `29afd2c` is confirmed on the target.
2. **The saved artifact loaded and started.** `dist/muejeje.pts` was added as a
   Script Module on the pinned build and started, which is what
   `OFFICIAL_PACKAGING_PROVED` is about: a recipe id now identifies an artifact
   that exists, whose bytes are measured, and which Packet Tracer accepted.
3. **The V6 kernel answered from inside it.** The operator reported that
   `typeof mcpDispatchV6` answered `function`; that `runtime.identify` and
   `runtime.capabilities` came back `ok: true`; that each of the five refusal
   classes — `MALFORMED_REQUEST`, `PROTOCOL_MISMATCH`, `INVALID_REQUEST`,
   `UNKNOWN_OPERATION`, `INVALID_ARGS` — came back with its own code; and that
   after an explicit stop and start, `runtime.identify` answered again. That is
   `V6_KERNEL_VERIFIED`, and it is about *this* artifact rather than about a
   Node run or an exploratory module. It is a verdict about **which operations
   answered and with which code**, which is what the operator reported; no
   envelope was preserved, so no field beyond those is target-evidenced.
4. **The kernel stayed healthy through the denials.** Every `platform.*` and
   `network.*` reading was reported as an envelope carrying `UNAVAILABLE` /
   `PLATFORM_CALL_FAILED`, and Packet Tracer printed beside each that the
   module lacked the necessary privilege for IPC call `"hardwareFactory"` or
   `"network"`. A denied call did not damage the engine: the runtime operations
   kept answering afterwards. Those two field values are what the operator
   read back; the rest of each envelope was not preserved and is not claimed.

**What it did not establish.** No platform member answered, so nothing about
Cisco's API was baselined and no capability resolved. `PLATFORM_CALL_FAILED` is
still not a privilege reading by itself — the diagnostic printed beside it is
what attributed the cause, for those two calls, in that run (`MJ-022`,
`MJ-031`).

**Its manifest configuration is superseded.** `privileges: []` was the right
declaration while no identifier was evidenced for either call. Target-binary
evidence then established that both roots require privilege index 1,
`GET_NETWORK_INFO`, and the `718db50` run below carried and verified it; the
two-token manifest followed, for the reason that run recorded — the members
beneath the roots need index 2 — and the `6233d86` run carried it. The manifest
now declares all eleven under `FULL_TRUSTED_MODULE`, which is a policy rather
than the next step of that sequence, and the audit refuses every one of the
earlier declarations outright.

### The official LIVE run at `718db50` — the `GET_NETWORK_INFO` artifact

Performed by hand on Packet Tracer `9.0.1.0858`, following
[the packaging recipe](muejeje-pts-packaging-recipe.md) from step 1, outside the
session that wrote this record. The privilege selection was
`["GET_NETWORK_INFO"]` and was not changed at any point.

| Record | Value |
| --- | --- |
| candidate | `718db5054261d95a2dd8b86247dc6b38ae426c7b`, tree `92c1e72897efb746c25414d46c16d7fe4349eca3` |
| `build_recipe_id` | `1d836e478ff3caf5d7a3cc2fa3823005943d6a07c637820f1a23d6ff274a37a7` |
| artifact | `dist/muejeje.pts`, SHA-256 `11073b67603fe795657f4c38aee1039063a6e87c299e618bc63ffafdd17857a8`, 48698 bytes, measured outside the artifact (`MJ-017`) |
| Packet Tracer | `9.0.1.0858`, `PacketTracer.exe` SHA-256 `843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1` |
| privileges | `["GET_NETWORK_INFO"]` — selected, read back, and not changed |
| entry point | the module's Debug Dialog |
| run id | `20260913T001112Z` |
| raw transcript | **not captured** — this record preserves the operator-reported observations |

```text
OFFICIAL_RUN_718DB50_RAW_TRANSCRIPT = NOT_CAPTURED
```

**The transcript requirement was already in force for this run, and no
transcript exists.** The `d37ba37` record declared that the next official run
would preserve one raw transcript per execution; this was that run, and no such
file was written or committed. What it establishes is therefore bounded exactly
as the `d37ba37` run's was: which statement was entered, whether it came back
`ok` or unavailable, and what Packet Tracer printed beside it. **No envelope of
this run was preserved, so it establishes no result shape**, and nothing here
is reconstructed from memory to close the gap (`MJ-011`, `AGENTS.md` rule 6).
The evidence level of a run that has happened is never raised afterwards to
match what the procedure asked of it.

**What it established.** The saved artifact loaded and started; its kernel
answered — `typeof mcpDispatchV6` `function`, `runtime.identify` and
`runtime.capabilities` `ok: true`, all five refusal classes, and `identify`
again across a stop and a start — so `CURRENT_CANDIDATE_PACKAGED` and
`CURRENT_CANDIDATE_V6_LIVE_VERIFIED` became `PASS` for this artifact. Carrying
`GET_NETWORK_INFO`, **both root calls progressed** where the `[]` artifact had
been denied, which is `GET_NETWORK_INFO_LIVE_VERIFIED = PASS`. The precise
member-level observations the operator reported, kept apart because a root
answering is not a member answering:

```text
IPC.hardwareFactory                    OBSERVED_REACHABLE
HardwareFactory.devices                OBSERVED_REACHABLE
DeviceFactory.getAvailableDeviceCount  OBSERVED_PRIVILEGE_DENIED

IPC.network                            OBSERVED_REACHABLE
Network.getDeviceCount                 OBSERVED_REACHABLE
Network.getDeviceAt                    OBSERVED_REACHABLE
Device.getName                         OBSERVED_PRIVILEGE_DENIED
```

**What it did not establish.** No platform or workspace member answered, so no
capability resolved and `TARGET_API_BASELINED` stays `PENDING_TARGET`. The two
denied members — `getAvailableDeviceCount` and `getName` — are what the Ghidra
index-2 reading explains: they require `CHANGE_NETWORK_INFO`, which this run did
not carry. Because those first members were denied,
`platform.device_descriptors` published no `factory_index` and
`network.device_inventory` published no device name, so the dependent V6
operations were `NOT_EXERCISED_PREREQUISITE_UNAVAILABLE` in this run and are
**not** marked executed. That accounting is what the operator reported, and
this summary does not inflate it — there is no transcript behind it to check it
against, which is itself part of what this run establishes and does not.

**Its manifest configuration is superseded.** Its `["GET_NETWORK_INFO"]` was
right while only the roots were evidenced. The two member denials, and the
Ghidra reading that both require index 2, are why the manifest then declared
`["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"]`, which the `6233d86` run carried.
The manifest now declares all eleven tokens under `FULL_TRUSTED_MODULE`, which is
a policy rather than a reading of this run — see
[the privilege map](muejeje-pts-privilege-map.md), fact 4. Each is a different
recipe id needing its own run; this record is what they are measured against.

### The run at `6233d86` — target evidence, not a canonical qualification

Performed by hand on Packet Tracer `9.0.1.0858`, carrying
`["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"]`.

| Record | Value |
| --- | --- |
| candidate | `6233d860e129cd8722e15d06f231a61b2ede7659`, tree `3a6b92a7c41ba618e593135f499a2646e765f512` |
| `build_recipe_id` | `6e1ef42c90d6785d050f3aebbfb1199d7d74f68c1c9a840667e8e5e7246c8efe` |
| artifact | `dist/muejeje.pts`, SHA-256 `c51e700ddabadd0083ab36327345735e4cedeeb11b489842c942629720e66580`, 46984 bytes |
| Packet Tracer | `9.0.1.0858`, `PacketTracer.exe` SHA-256 `843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1` |
| privileges | `["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"]` — selected, read back, not changed |
| run id | `20260913T025441Z` |

**Why it qualifies nothing.** Its workspace fixture was **not satisfied when the
run started** and was corrected during execution, so the run did not follow the
declared procedure, and a run that departed from the procedure cannot be the
procedure's result. It is recorded as **target evidence** and moves no
qualification gate. `WORKSPACE_FIXTURE_STABLE = NO` for this run.

Its transcript preserves the header, the artifact load and start, and the first
statement, and stops there: `RUN_6233D86_RAW_TRANSCRIPT = PARTIAL`. The
transcript's own **post-run evidence note** records that — appended after the
run, editing nothing above it — so the immutable header's
`workspace_precondition` is read as the fixture the run *declared* rather than
as one it met. Everything below is what the operator reported afterwards, is
**target evidence and not raw transcript**, and nothing is reconstructed from
memory (`MJ-011`, `AGENTS.md` rule 6).

**What it observed.**

```text
platform.device_descriptors    OBSERVED   available_count = 172
platform.module_type_support   OBSERVED   factory_index 0, module_type 2, supported
network.device_inventory       OBSERVED   available_count = 3
platform.module_descriptors    UNAVAILABLE  PLATFORM_ANSWER_UNUSABLE
```

Four descriptors the operator reported from the factory window, as read:

```text
factory_index 0  model 1841     device_type 0  supported_module_types [2, 30]
factory_index 1  model 1841                    supported_module_types [2, 30]
factory_index 2  model 1941                    supported_module_types [2, 30]
factory_index 3  model 2620XM                  supported_module_types [1, 2]
```

and the workspace, after the fixture was corrected:

```text
workspace_index 0  PC0
workspace_index 1  Switch0
workspace_index 2  Power Distribution Device0
```

Those positions are what one reading reported in that run. They are not identity
and not placement order, and nothing carries them into another run (`MJ-002`,
`MJ-029`).

**What it establishes.** `DeviceFactory.getAvailableDeviceCount()` and
`Device.getName()` — the two members `718db50` saw denied — both answered with
`CHANGE_NETWORK_INFO` selected. That is
`CHANGE_NETWORK_INFO_LIVE_VERIFIED = PASS`, **for those two members and for no
others**: the token's name is still not read as a mutation semantic, and nothing
was written.

**What it did not establish, and the defect it exposed.**
`platform.module_descriptors` at `factory_index` 0 came back `UNAVAILABLE` with
`PLATFORM_ANSWER_UNUSABLE`, and **Packet Tracer printed no privilege diagnostic
beside it**. On this build a privilege denial does print one, and reaches the
runtime as `PLATFORM_CALL_FAILED` — both earlier runs recorded exactly that — so
this is not a privilege result and was not treated as one.

What the result could not say is *where* the reading stopped. Eight interface
members sit between a `factory_index` and a finished chassis tree — one to reach
the chassis root, seven to read a node of it — and every one of them produces
that same word: an answer this runtime cannot carry back unchanged, or a
descriptor the platform would not hand over inside a count it reported itself.
The two readings either side of it were `OBSERVED` at the same index, so
everything up to and including `DeviceDescriptor.getType()` is target-proven and
the stage lies at or beyond `DeviceDescriptor.getRootModule()`.

**The cause is not established, and this record does not guess one.** The
candidate after this run adds the missing discrimination rather than a fix: an
unavailable reading now reports `unavailable_member` and `unavailable_argument`
beside its reason, so the next run names the member. A `null` handed back inside
a reported count was still refused at that candidate rather than read as an
empty position — that would have been a semantic for `null` no target reading
supported — and it was to become a reported position only once a run said it is
ordinary. The `504a6e6` run and the investigation after it said so, and it is
still never read as an empty position (`MJ-015`, `MJ-022`).

### The run at `504a6e6` — full trust, target evidence

Performed by hand on Packet Tracer `9.0.1.0858`, outside the session that wrote
this record, carrying all eleven serialized tokens.

| Record | Value |
| --- | --- |
| candidate | `504a6e6e63b0fb1ad5af5daf6dee114275d0ccf5`, tree `9668bb40436147bbc62a5821ad52405c0edbcb43` |
| `build_recipe_id` | `b4a26d8a07add4cea5dbcae4c7832e7d85bbb3c633bee3c2feb2134a09a4cc60`, as the run's header records it |
| artifact | SHA-256 `5066fff38a6d908d3697cc357ed04ac328c67470a399ce657bf6ea328ddf41d1`, 50872 bytes, as the run's header records it |
| Packet Tracer | `9.0.1.0858`, `PacketTracer.exe` SHA-256 `843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1` |
| privileges | all eleven selected, none clear |
| workspace | `2960-24TT` `Switch0` and `PC-PT` `PC0`, no cable, no configuration |
| run id | `20260913T151440Z` |
| raw transcript | **not committed** with this record: `RUN_504A6E6_RAW_TRANSCRIPT = NOT_COMMITTED` |

**What the operator reported.**

```text
privilege selection            11 of 11
platform.device_descriptors    OBSERVED
platform.module_type_support   OBSERVED
network.device_inventory       OBSERVED
network.device_identity        OBSERVED
network.device_ports           OBSERVED
platform.module_descriptors    UNAVAILABLE  PLATFORM_ANSWER_UNUSABLE
  unavailable_member           ModuleDescriptor.getModuleAt
  unavailable_argument         0
```

**What it establishes.** Under the full selection no reached call was
privilege-denied, which is `FULL_TRUSTED_SET_LIVE_VERIFIED = PASS` for this
artifact — a verdict about the selection, not call evidence for any of the nine
tokens no member is evidenced to need. And the stage did its job:
`MODULE_DESCRIPTORS_STAGE_IDENTIFIED = PASS`, `ModuleDescriptor.getModuleAt`,
argument 0. `network.device_identity` and `network.device_ports` answered on the
target for the first time.

**What it does not establish.** With no transcript committed, this record cannot
establish the run as a canonical qualification:
`RUN_504A6E6_CANONICAL_QUALIFICATION = NOT_ESTABLISHED`. No capability resolves
off it, no API is baselined by it, and no milestone moves. It is recorded as
target evidence, like `6233d86`.

**The investigation after it** is what the correction in this candidate rests
on — see *A null inside the module count*, above. It also read two things about
device descriptors, recorded here because they bound how this runtime may
address one, and both are about `9.0.1.0858` only.

#### What addresses a device descriptor

- `model` does not identify one descriptor, and neither does
  `(model, device_type)`: distinct `factory_index` entries share both and carry
  different module trees.
- `getDescriptor(type, model)` does not necessarily hand back the entry an
  enumeration listed.
- `===` between two hand-overs is not a stable identity for a descriptor.
- `factory_index` addressed the same entry, semantically, across 20 repetitions.

So the architecture stays as it is. `factory_index` addresses one concrete entry
of the enumeration **within one observation or session**. It is not replaced by a
model or a type, no entry is reconstructed through `getDescriptor(type, model)`,
and it is **not** promoted to a persistent or global identifier: twenty stable
repetitions on one build are evidence about that build, not a contract
(`MJ-002`, `MJ-029`).

#### Which variant a creation selects — recorded, not implemented

For the models it tested, `getDescriptor(type, model)` and
`LogicalWorkspace.addDevice(type, model, …)` selected the same default variant:
64 controlled creations, repeated after a full restart of Packet Tracer, with no
contradiction. It is recorded as evidence about `9.0.1.0858` and those models.
**No creation logic changed** — Muejeje creates nothing — and it is not read as a
Cisco contract for any other build or model (`MJ-015`).

### The exploratory run at `ed3a0b0` — evidence, not an artifact

Performed by hand on Packet Tracer `9.0.1.0858`, following the recipe as it then
stood until its import step, where the listing order made it impossible to
follow. No privilege was changed at any point. As with the official run, what
is preserved is the operator-reported observations — including the two
diagnostics below, reported as printed — and not a raw transcript:
`EXPLORATORY_RUN_ED3A0B0_RAW_TRANSCRIPT = NOT_CAPTURED`. The field values it
reports are read as what the operator observed, and never as a verified result
shape.

| Record | Value |
| --- | --- |
| candidate | `ed3a0b04a5dbdd2ecd5c12cf45ad4c6f7887d50d`, tree `c3487252ed95225dd150879f482223c864e7847e` |
| build audit | `PACKAGING_MANUAL_AVAILABLE`, `source.clean: true`, 23 artifact inputs, `reference_inputs: []` |
| `build_recipe_id` | `d1f91b68639eed883a26d337532a339cde1348438c3ed8a6ca8a541fd9bb41a6` |
| Packet Tracer | `9.0.1.0858`, `PacketTracer.exe` SHA-256 `843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1` |
| module | the recipe's 22 engine files, byte for byte, imported as copies named `01_core.js` to `22_lifecycle.js`; saved as an experimental `.pts` and added as a Script Module |
| privileges | none selected, and none selected later |
| entry point | the module's Debug Dialog |
| workspace | a `2960-24TT` (`Switch0`) and a `PC-PT` (`PC0`): no link, no configuration, not saved |

**Why it qualifies nothing.** A recipe describes the files a module is packaged
from, names included, and this module's names were not the recipe's. Its
answers are evidence about Packet Tracer and about the kernel's source, not
about any artifact a recipe id identifies, so no gate on this page moves
because of them.

**What it observed.**

1. **Listing order.** The 22 files as `ed3a0b0` named them, imported one at a
   time in dependency order, were listed alphabetically — `arguments_v6.js`,
   `core.js`, `dispatcher_v6.js`, `lifecycle.js`, … — and no control to reorder
   them was observed. The prefixed copies were listed `01` to `22`.
2. **The entry point.** The Debug Dialog is documented on
   `scriptModules_scriptingInterface.htm`, SHA-256
   `4bc04309b184ec2f28f8de95762a899a523ae849e462c6c6e4a2069b2d8d1517`, the bytes
   the v2 preflight inventory already pins: *"Each Script Module has its own
   debug dialog that accesses only the Script Module. Statements can be entered
   into the input field, and they will be evaluated in the script engine."*
3. **The kernel.** `typeof mcpDispatchV6` answered `function`.
   `runtime.identify` came back `ok: true` with `extension_name: muejeje`,
   `extension_version: 0.1.0`, `protocol_versions: [6]` and
   `lifecycle.started: true`; `runtime.capabilities` came back `ok: true` with
   all eight admitted operations, each `read_only: true`. Malformed JSON was
   refused `MALFORMED_REQUEST`, `v: 5` `PROTOCOL_MISMATCH`, an envelope with no
   `args` `INVALID_REQUEST`, an unknown operation `UNKNOWN_OPERATION`, and an
   argument from the other address domain `INVALID_ARGS`. After an explicit
   stop and start, `runtime.identify` came back `ok: true` again; the
   operator's record of the stop and the start, not the two tokens, is what
   separates the evaluations (`MJ-023`).
4. **The platform and the workspace.** `platform.device_descriptors`,
   `platform.module_descriptors` and `platform.module_type_support` each came
   back `UNAVAILABLE` with `PLATFORM_CALL_FAILED`, and for each Packet Tracer
   printed:

   ```text
   IPC Call ERROR: IPC - ExApp or Script Module does not have the necessary privilege for IPC call "hardwareFactory"
   ```

   `network.device_inventory`, `network.device_identity` and
   `network.device_ports` each came back the same way, and for each Packet
   Tracer printed:

   ```text
   IPC Call ERROR: IPC - ExApp or Script Module does not have the necessary privilege for IPC call "network"
   ```

   The workspace readings were repeated with the two devices in place, without
   restarting the module, and came back the same, with the same diagnostic.

**What it establishes, and what it does not.**

- **Packet Tracer lists engine files by name.** The packaging contract assumed
  import order and was wrong. It is corrected: every engine file's name now
  carries its place, and the audit refuses a declared order the names do not
  sort in.
- **`privileges: []` is target-observed to deny `IPC.hardwareFactory()` and
  `IPC.network()`** on `9.0.1.0858` — the root calls the `platform.*` and the
  `network.*` readings go through. For those two calls, in that run, Packet
  Tracer's diagnostic names the cause.
- **Which privilege either call needs was unevidenced when this run happened.**
  The diagnostic names an IPC call, never a privilege identifier, and nothing
  *installed* maps one to the other — which is why the manifest declared `[]`
  through both runs. The pinned binary has since been read, and it does map
  them: [the privilege map](muejeje-pts-privilege-map.md) (`MJ-032`).
- **`PLATFORM_CALL_FAILED` is still not a privilege reading.** It says a member
  was called and did not return. Here a diagnostic printed beside it gave the
  reason; for another call, another build or another module the reason may
  differ, and only a recorded diagnostic attributes one (`MJ-022`, `MJ-031`).
- **The kernel's source ran inside Packet Tracer, and that verifies no
  artifact.** `V6_KERNEL_VERIFIED` is about the saved `dist/muejeje.pts` a
  recipe id identifies, and that artifact has not run.

### Milestone states, and what they are not

`MJ-033` separates *implementation progress* from *Core Readiness*, and this is
where the second one is measured. A milestone may be implemented while an
earlier one waits on target evidence; none of them is `DONE` until it is
`CORE_READY`.

```text
M0B = NOT_COMPLETE
M0C = NOT_COMPLETE
M1_CORE_READY = YES
M2_CORE_READY = NO
M3_CORE_READY = NO
ZERO_CHANGE_CUTOVER = NOT_ACHIEVED
```

`M1_CORE_READY = YES` is the one state the official LIVE run moved, and it
moved exactly as far as that run's evidence goes. `M1` is the V6 kernel: a
governed artifact, built from a declared recipe, loaded and started on the
pinned build, and answering identify, capabilities, every refusal class and a
stop-and-start from its own engine. All of that was observed. Nothing about the
platform was, which is why no other milestone moved with it.

| State | What is still missing |
| --- | --- |
| `M0B` | a canonical qualification first, then credential and transport API qualification. The privilege question is answered as far as evidence answers it — `[]` denied both roots at `d37ba37`, `GET_NETWORK_INFO` reached them at `718db50`, `CHANGE_NETWORK_INFO` reached the two members beneath them at `6233d86` — but no run that satisfied the procedure has reached them, so no API is baselined. No transport exists, so `MJ-026`'s terms are baselined rather than exercised |
| `M0C` | batch and auth-boundary semantics. `MJ-027` is the contract the first batch operation must satisfy and no batch operation exists; the auth boundary is in the same position |
| `M2_CORE_READY` | target evidence. Two of three platform readings answered on the `6233d86` and `504a6e6` runs, neither established as a canonical qualification; `platform.module_descriptors` stopped at a `null` inside a module count at `504a6e6`, and whether the corrected walk answers is what the next run reports |
| `M3_CORE_READY` | complete intended scope and target evidence. The workspace inventory, one device's identity and one device's ports are implemented; the workspace's links are not (see below). `network.device_inventory` answered on the `6233d86` run, and all three workspace readings on the `504a6e6` run; every workspace capability stays `PENDING_TARGET` until a canonical qualification reaches it |
| `ZERO_CHANGE_CUTOVER` | a release-qualified artifact, and a compatibility facade outside the V6 core (`MJ-034`). One artifact is now packaged and kernel-qualified, no version is release-qualified, no facade exists, and no consumer has been cut over |

**A green offline run still moves none of them, and neither does binary
evidence.** The suite establishes what this repository's own code does; reading
a requirement out of `PacketTracer.exe` establishes what the target *requires*,
not what it then does. `M0C` waits on work that has not been written; `M2` and
`M3` wait on platform readings that answer, and `M3` on unfinished scope as
well; the cutover waits on all of it.

**The next task for `M0B`, `M2` and `M3` is the full-trust canonical
qualification, not more implementation.** The privilege question the earlier
runs were about is answered as far as evidence can answer it: `[]` was denied
both roots at `d37ba37`, `GET_NETWORK_INFO` reached both roots at `718db50`,
and `CHANGE_NETWORK_INFO` reached the two members beneath them at `6233d86`.
The manifest declares all eleven serialized tokens under
`PRIVILEGE_POLICY = FULL_TRUSTED_MODULE` — a deployment decision, not a reading
of that evidence ([the privilege map](muejeje-pts-privilege-map.md), fact 4) —
and the `504a6e6` artifact carried it with no reached call privilege-denied.
What the next run must establish is not a privilege result: it is a canonical
qualification with a stable fixture and a complete raw transcript, and whether
`platform.module_descriptors` — stopped at a `null` from
`ModuleDescriptor.getModuleAt` there — answers under the corrected walk
([the full-trust LIVE runbook](muejeje-pts-privilege-live-runbook.md)).

**Where M3 stands.** `network.device_ports` is implemented and tested. The
contract question the previous revision of this record left open — re-report the
device identity beside the ports, or make a consumer correlate two readings — is
decided for snapshot consistency: the port reading selects the device once,
reads its name, its model and its ports off that one hand-over, and reports them
together, so no consumer joins an identity from one moment with ports from
another (`MJ-031`). Its three members are documented and called by legacy code;
none has a Muejeje reading.

**Where M3 stops, and the reason is in Cisco's reference.** The workspace's
links are the next read-only topology subject, and every documented route to
one hands over the base interface. `Network.getLinkAt(int)` answers a `Link`,
and so does `getLink()` on `Port` and on every other interface that documents
it; across every installed class page, no other member hands over a `Link`. The
`Link` page documents one member, `getConnectionType()`. A link's endpoints are
documented only on the two interfaces derived from it: `Cable.getPort1()` and
`Cable.getPort2()` for a cable, `Antenna.getPort()` for a wireless link. No
installed member hands over a `Cable`, and the only one that hands over an
`Antenna`, `Antenna.getReceiverAt(int)`, is asked of an `Antenna` already held.

Reading an endpoint therefore means deciding which derived interface a
handed-over `Link` is, and nothing installed documents a way to decide it.
`getClassName()`, which the legacy runtime probes, appears on no installed
IpcAPI page. The `Link` page lists the `CONNECT_TYPES` values but not which
interface carries each, so a table from connection type to interface would be a
Cisco enum mirror (`MJ-014`) and an inference nobody documented. Probing members
with `typeof`, as legacy code does, would be guessing an interface. The boundary
refuses that by construction as well: a handle carries the interface its member
documents, so even an admitted `Cable` member would be refused on a `Link`.

The port side does not get round it. `Port.getRemotePortName()` is documented
only as the name of the remote port: a name with no device attached, which could
be attributed only by matching names across devices — the join `MJ-031` forbids
— and nothing documents what an unlinked or wireless port answers.

So the slice is blocked on target evidence: from an artifact running inside
`9.0.1.0858`, which interface a Script Module is actually handed for a workspace
link. It is not blocked on work this repository could do offline.
`tests/muejeje/test_workspace_links_blocked.py` re-derives each fact above from
the installed pages, with the three link pages hash-pinned, and holds the
allowlist to admitting no member that reads a link.

### A green V6 run is not IpcAPI qualification

`TARGET_API_BASELINED` asks whether the **platform APIs Muejeje uses** are
evidenced against the pinned build, from the artifact that uses them. Nothing
about a successful V6 execution answers that question, and it would still not
answer it if the `.pts` were built and both platform-free operations replied
perfectly: `runtime.identify` and `runtime.capabilities` make no platform call,
so they can succeed on a target where every privilege is refused and every
factory API is missing.

The boundary admits **interface members, not names** (`MJ-031`): one allowlist
entry per member, called only on a platform object the boundary itself handed
out as that interface. The table below has one row per entry and cites the page
that member is documented on, and a gate holds both — every entry has exactly
one row, and every row cites its own interface's page. An earlier revision of
this table carried two fewer rows than the boundary had entries and cited
`IPC.hardwareFactory()` to the `HardwareFactory` page; nothing compared the
table with the allowlist, so neither was noticed.

The third column says whether a **legacy channel** has observed the member on
`9.0.1.0858`, and through what. It is not Muejeje's evidence: a legacy `yes` and
a Muejeje reading are two different observations, through two different channels,
under two different privilege contexts, and this column never becomes the second.
Which members Muejeje itself has reached is the run records above.

| Interface member | Cisco reference | Observed on `9.0.1.0858` through a legacy channel |
| --- | --- | --- |
| `IPC.hardwareFactory()` | `class_i_p_c.html` | **yes** — factory-structure record |
| `HardwareFactory.devices()` | `class_hardware_factory.html` | **yes** — factory-structure record |
| `DeviceFactory.getAvailableDeviceCount()` | `class_device_factory.html` | **no** — documented only |
| `DeviceFactory.getAvailableDeviceAt(int)` | `class_device_factory.html` | **no** — documented only |
| `DeviceDescriptor.getModel()` | `class_device_descriptor.html` | **yes** — factory-structure record |
| `DeviceDescriptor.getType()` | `class_device_descriptor.html` | **yes** — factory-structure record |
| `DeviceDescriptor.isModelSupported()` | `class_device_descriptor.html` | **no** — documented only |
| `DeviceDescriptor.isModuleTypeSupported(ModuleType)` | `class_device_descriptor.html` | **yes** — factory-structure record |
| `DeviceDescriptor.getSupportedModuleTypeCount()` | `class_device_descriptor.html` | **no** — documented only |
| `DeviceDescriptor.getSupportedModuleTypeAt(int)` | `class_device_descriptor.html` | **no** — documented only |
| `DeviceDescriptor.getRootModule()` | `class_device_descriptor.html` | **yes** — factory-structure record |
| `ModuleDescriptor.getModel()` | `class_module_descriptor.html` | **yes** — factory-structure record |
| `ModuleDescriptor.getType()` | `class_module_descriptor.html` | **yes** — factory-structure record |
| `ModuleDescriptor.isHotSwappable()` | `class_module_descriptor.html` | **yes** — factory-structure record |
| `ModuleDescriptor.getSlotCount()` | `class_module_descriptor.html` | **yes** — factory-structure record |
| `ModuleDescriptor.getSlotTypeAt(int)` | `class_module_descriptor.html` | **yes** — factory-structure record |
| `ModuleDescriptor.getModuleCount()` | `class_module_descriptor.html` | **yes** — factory-structure record |
| `ModuleDescriptor.getModuleAt(int)` | `class_module_descriptor.html` | **yes** — factory-structure record |
| `IPC.network()` | `class_i_p_c.html` | legacy code only — no per-member record cited |
| `Network.getDeviceCount()` | `class_network.html` | legacy code only — no per-member record cited |
| `Network.getDeviceAt(int)` | `class_network.html` | legacy code only — no per-member record cited |
| `Device.getName()` | `class_device.html` | legacy code only — no per-member record cited |
| `Device.getModel()` | `class_device.html` | legacy code only — no per-member record cited |
| `Device.getType()` | `class_device.html` | **no** — documented only |
| `Device.getPortCount()` | `class_device.html` | legacy code only — no per-member record cited |
| `Device.getPortAt(int)` | `class_device.html` | legacy code only — no per-member record cited |
| `Port.getName()` | `class_port.html` | legacy code only — no per-member record cited |

**"yes" means a recorded run.** Every "yes" row is a member the read-only
factory survey calls — `observe_factory_structure` in
`infrastructure/execution/poe_delivery_runtime.py` — in runs
`factory-survey-9f967ef6` and `factory-survey-102006c6`, zero mutations, whose
outputs are committed under `docs/reference/cp-scale/canonical-live-evidence/`
as `factory-structure-20260907T003018Z-cf89481fa3ea-observed.json` (recording
`packet_tracer_build: 9.0.1.0858`) and
`factory-structure-20260907T005226Z-86c75f1c304c-accesspoint-family.json`, and
summarised in
[the factory-structure record](../reference/cp-scale/ROUTER0_POE_FACTORY_STRUCTURE_20260907.md):
whole chassis trees, among them an `AccessPoint-PT` root reporting `model: ""`
with slot types `[6, 18]` and two child modules, and a `3650-24PS` with three
non-removable root slots.

**"legacy code only" is weaker, and says so.** The legacy runtime's workspace
inventories — `inventory_fingerprint` in
`infrastructure/execution/probe_runtime.py`, and the live safety gate's
`_workspace_observation_js` in `packet_tracer_physical_runtime.py` — call these
members. An earlier revision recorded them as "yes — this repository's live
channel drives it", which was a claim about code standing in for a recorded
observation. No record here ties each of these members to a run on
`9.0.1.0858`, so none of them is recorded as observed.

**"no" rows are documented and unmeasured**: the factory enumeration pair, the
per-model support flag, the supported-type pair and `Device.getType()`. The
enumeration pair is what a target run has to observe first, because it is how
this artifact reaches every descriptor member beneath it. The `getType` this
repository has driven is `DeviceDescriptor`'s — a different member of a
different interface, and no evidence about `Device`'s, which is exactly the
distinction a per-member table exists to keep.

`Device` also documents `getDescriptor()`, `getRootModule()`,
`getSerialNumber()`, `getPower()` and `getUpTime()`, and none is admitted.
`getDescriptor()` is the only documented way to relate a workspace device to a
factory descriptor; it is recorded here so that the relation having an API is
on record, and so that the absence of a correlation field in
`network.device_identity` reads as a decision rather than an oversight
(`MJ-031`). `getRootModule()` on `Device` hands over installed hardware, and is
not the descriptor member of the same name the boundary admits.

**Those runs are not Muejeje's evidence**, and the distinction is the whole
point of this section. They were driven from the legacy channel, in a context
with its own privileges, not from a Script Module carrying `privileges: []`;
and they reached the descriptor through `getDescriptor(DeviceType, string)`,
which Muejeje deliberately does not use, because asking by type would require
carrying a numeric Cisco enum as the authority for which types exist
(`MJ-014`). Muejeje reaches the same descriptors through the unqualified
enumeration and addresses a model by its index in it. So those runs establish
that this descriptor path answers on this build — which is why it was chosen —
and nothing about whether *this artifact* may walk it.

Until a governed artifact's run answers *under the declared procedure*, every
`platform.*` and `network.*` operation is code with a contract and no qualified
target answer, which is what `PENDING_TARGET` means. The `6233d86` run answered
three of them and did not follow the procedure, so it is recorded as target
evidence beside them rather than in place of them.

**What the first reading was, and what it still does not say.** Both runs in
this section were made by a module declaring `privileges: []`; the governed
manifest now declares all eleven tokens under `FULL_TRUSTED_MODULE`, a policy
rather than a reading, and the recorded binary evidence continues to say which
privilege each known call requires (`MJ-032`). An earlier revision of this file said the
first run "should report `PLATFORM_CALL_FAILED`"; that was a claim about
`9.0.1.0858` with nothing behind it, and it stays withdrawn even though the
exploratory run then came back that way. What made that run evidence is what
the operator recorded beside each reading: Packet Tracer's own diagnostic,
naming a missing privilege for `IPC.hardwareFactory()` and `IPC.network()`.
Whether declaring the evidenced token makes either call answer is unmeasured,
and a run records whichever reading comes back — an answer, a member the object
does not offer, a call that did not return, or an answer that could not be
attributed — with whatever Packet Tracer printed beside it.

That attribution is also why the boundary was corrected before this line was
written. A bug inside an adapter used to come back as `PLATFORM_CALL_FAILED`,
and so did a member that was never called — on a target, neither would have
been distinguishable from a refusal (`MJ-022`, `MJ-031`).

What was checked, and what each check found:

- Packet Tracer `9.0.1.0858` **is installed**, and `bin/PacketTracer.exe` hashes
  to the pinned SHA-256. The audit verified this, not a person reading a version
  dialog.
- Two `PacketTracer` processes **were running** at the time of this record; the
  session that wrote it neither drove nor inspected them.
- The only packager is the in-app Scripting Interface. There is **no CLI and no
  documented programmatic packaging entry point** — recorded in the v2 preflight
  inventory, and the reason `automation` stays `BUILD_AUTOMATION_UNPROVEN`.
- Driving that GUI would mean synthesising native window automation against a
  running instance holding a user's session. That is not a demonstrated path;
  it is one that would have to be invented, and inventing it is precisely what
  turns "unproven" into an unfalsifiable claim.

So the remaining action is **one manual procedure**, already written down in
full: [the packaging recipe](muejeje-pts-packaging-recipe.md). It has been
followed three times — at `d37ba37`, `718db50` and `6233d86`, each recorded
above — and it is followed again for each new recipe id, which is what a
changed privilege set produces. The current `FULL_TRUSTED_MODULE` candidate has
no run of its own yet.

Each run records: source commit and tree, the recipe id, the externally
measured artifact SHA-256, the Packet Tracer build, the privilege selection
read back from the module, the workspace the instance held, the Script Engine
listing as Packet Tracer showed it, and every response envelope with whatever
Packet Tracer printed beside it — including whichever `resolution` and
`unavailable_reason` each platform reading came back with. Since the `d37ba37`
record those envelopes have been required to go into **one raw transcript per
execution**, named by the artifact SHA-256 and the run's own `run_id`,
append-only and unnormalized, and this page interprets that file rather than
standing in for it; a summary is what a run establishes only as far as the
transcript behind it goes, which is why **none of the runs above establishes a
result shape** — `d37ba37` and `718db50` captured no transcript, `6233d86`
captured a prefix, and nothing of `504a6e6`'s is committed. The target gates change only
as far as that
evidence goes: `OFFICIAL_PACKAGING_PROVED` and `V6_KERNEL_VERIFIED` from the
saved artifact loading and its kernel answering, which the `d37ba37` and
`718db50` runs did; `TARGET_API_BASELINED` and `CAPABILITY_RESOLUTION_VERIFIED`
only from platform readings that answered **in a canonical qualification**.
Three answered on the `6233d86` run and five on the `504a6e6` run, and neither
is established as one, so neither gate has moved. Never from a clean offline report, never
from the operations that make no platform call, never from a call Packet Tracer
denied, and never from a requirement read out of the binary.

**The last qualified artifact is the `718db50` one**, SHA-256
`11073b67603fe795657f4c38aee1039063a6e87c299e618bc63ffafdd17857a8`, 48698
bytes: the most recent artifact that was packaged, loaded and driven through the
whole kernel qualification. `dist/` is git-ignored machine-local output, so no
`.pts` is tracked in the checkout and none is expected to be. The `504a6e6`
artifact was built from the same eleven-token manifest; **no artifact exists for
the current recipe**, whose engine sources differ from that artifact's and whose
recipe id therefore differs from every artifact above.

`Cisco Packet Tracer 9.0.1\extensions\` holds **no Muejeje entry** — and it is
not empty, which is what an earlier revision of this file recorded. It carries
Cisco's own eleven bundled extension directories and six `.pts` files
(`ActivitySequencer`, `Clear Terminal Agent`, `Marvel`, `PcSoftware`,
`PTINTERNAL`, `resource`), and the user profile's own `extensions\` is empty.
"Empty" was the wrong measurement of the right fact, and the right fact is that
nothing of ours is installed there. The governed module was added through the
Scripting Interface from a saved `.pts` rather than dropped into that
directory, which is what the recipe prescribes.

## Scope

This page's *offline* half is **validator** qualification only: it establishes
nothing about a candidate `.pts`, its content, or its runtime behaviour. What
is established about an artifact comes from the LIVE runs recorded above — the
official ones at `d37ba37` and `718db50`, the target-evidence runs at `6233d86`
and `504a6e6`, and the earlier exploratory one at `ed3a0b0` — each performed by
hand, outside the sessions that wrote this record, and no complete set of raw
envelopes from any of them committed here. **This session performed no LIVE
run**; it corrected how the chassis walk reads a `null` inside a module count,
recorded the target evidence that correction rests on, and declared what the
next run must capture — all of which is offline work.

The platform surface's executions inside Packet Tracer are those four runs':
denied at its root call at `d37ba37`; reaching the root at `718db50` and denied
at the member beneath it; at `6233d86` reaching past both, with three readings
`OBSERVED` and `platform.module_descriptors` unattributable; and at `504a6e6`,
with five readings `OBSERVED` and `platform.module_descriptors` stopped at
`ModuleDescriptor.getModuleAt`, argument 0. Everywhere
else it has run under Node — against no platform object, and against a stub —
and neither is a Packet Tracer reading.

```text
KERNEL_BOUNDARIES              = HARDENED
PLATFORM_BOUNDARY              = INTERFACE_MEMBER_ENFORCED
ADDRESSING                     = EXACT_INTEGER_NAMED_DOMAINS
V6_CONTRACT                    = CONSISTENT
M1_OFFLINE                     = COMPLETE
M2_DEVICE_DISCOVERY            = IMPLEMENTED
M2_MODULE_DISCOVERY            = IMPLEMENTED
M2_MODULE_TYPE_SUPPORT         = IMPLEMENTED
M2_OFFLINE                     = COMPLETE
M3_DEVICE_INVENTORY            = IMPLEMENTED
M3_DEVICE_IDENTITY             = IMPLEMENTED
M3_DEVICE_PORTS                = IMPLEMENTED
M3_WORKSPACE_LINKS             = BLOCKED
M3_READ_ONLY_TOPOLOGY          = STARTED
CAPABILITY_RESOLUTION_VERIFIED   = PENDING_TARGET
OFFICIAL_PACKAGING_PROVED        = PASS
V6_KERNEL_VERIFIED               = PASS
M1_CORE_READY                    = YES
TARGET_API_BASELINED             = PENDING_TARGET
M0B_TARGET_API_BASELINED         = NOT_COMPLETE
M2_CORE_READY                    = NO
M3_CORE_READY                    = NO
ZERO_CHANGE_CUTOVER              = NOT_ACHIEVED
ENGINE_ORDER                     = CARRIED_BY_FILE_NAMES
EMPTY_PRIVILEGES_ROOT_IPC        = TARGET_OBSERVED_DENIED
GET_NETWORK_INFO_ROOT_IPC        = TARGET_OBSERVED_REACHABLE
CHANGE_NETWORK_INFO_MEMBERS      = TARGET_OBSERVED_ANSWERED
PRIVILEGE_POLICY                 = FULL_TRUSTED_MODULE
FULL_TRUSTED_SET_LIVE_VERIFIED   = PASS
PRIVILEGE_SCOPE_UNCHANGED        = PASS
MODULE_DESCRIPTORS_STAGE_IDENTIFIED = PASS
GET_MODULE_AT_NULL_INSIDE_COUNT  = TARGET_OBSERVED
MODULE_DESCRIPTORS_LIVE_OBSERVED = PENDING
DEVICE_DESCRIPTOR_ADDRESS        = FACTORY_INDEX_WITHIN_ONE_OBSERVATION
DEFAULT_VARIANT_ON_CREATION      = TARGET_OBSERVED_NOT_IMPLEMENTED
GET_NETWORK_INFO_BINARY_EVIDENCE_RECORDED = PASS
BINARY_MAP_REPRODUCIBILITY                = PENDING
GET_NETWORK_INFO_LIVE_VERIFIED            = PASS

CHANGE_NETWORK_INFO_MEMBER_EVIDENCE_RECORDED = PASS
CHANGE_NETWORK_INFO_LIVE_VERIFIED            = PASS

CURRENT_NEW_CANDIDATE_PACKAGED             = PENDING
CURRENT_NEW_CANDIDATE_V6_LIVE_VERIFIED     = PENDING
SUFFICIENT_FOR_FULL_M2_M3_CHAIN            = NOT_PROVEN

OFFICIAL_RUN_D37BA37_RAW_TRANSCRIPT       = NOT_CAPTURED
OFFICIAL_RUN_718DB50_RAW_TRANSCRIPT       = NOT_CAPTURED
RUN_6233D86_RAW_TRANSCRIPT                = PARTIAL
RUN_6233D86_WORKSPACE_FIXTURE_STABLE      = NO
RUN_6233D86_CANONICAL_QUALIFICATION       = NO
RUN_504A6E6_RAW_TRANSCRIPT                = NOT_COMMITTED
RUN_504A6E6_CANONICAL_QUALIFICATION       = NOT_ESTABLISHED
NEXT_LIVE_RUN_RAW_TRANSCRIPT              = REQUIRED_PER_EXECUTION
NEXT_LIVE_RUN_TRANSCRIPT_IDENTITY         = ARTIFACT_SHA256_AND_RUN_ID
NEXT_LIVE_RUN_TRANSCRIPT_HEADER           = PRE_RUN_FACTS_ONLY
NEXT_LIVE_RUN_WORKSPACE_FIXTURE           = REQUIRED_TWO_DEVICES
NEXT_LIVE_RUN_RELAY_INPUTS                = OBSERVED_NOT_PREDICTED
NEXT_LIVE_RUN_ACCOUNTING                  = EXECUTED_OR_NOT_EXERCISED_PREREQUISITE_UNAVAILABLE
```

`ENGINE_ORDER = CARRIED_BY_FILE_NAMES` was the previous line's packaging
correction, and the official run confirmed it on the target: Packet Tracer
lists engine files by name, the names spell the declared order, and the audit
refuses any other.

`EMPTY_PRIVILEGES_ROOT_IPC = TARGET_OBSERVED_DENIED` records the diagnostics
for `IPC.hardwareFactory()` and `IPC.network()` in the `d37ba37` `[]` run.
`GET_NETWORK_INFO_ROOT_IPC = TARGET_OBSERVED_REACHABLE` records that the
`718db50` run, carrying that token, reached both — and that Packet Tracer then
denied the two members beneath them, `getAvailableDeviceCount` and `getName`.
`CHANGE_NETWORK_INFO_MEMBERS = TARGET_OBSERVED_ANSWERED` records what happened
next: the `6233d86` run carried that second token, and both of those members
answered. The state is about **those two members and no others**.

`GET_NETWORK_INFO_BINARY_EVIDENCE_RECORDED = PASS` is a reading of the pinned
`PacketTracer.exe` rather than of a run: both root calls require privilege
index 1, and index 1 serializes as `GET_NETWORK_INFO`. The full map, the call
descriptors and what none of it establishes are in
[the privilege map](muejeje-pts-privilege-map.md), which keeps the binary
mapping, the call requirements and the run-by-run behaviour as separate facts.
`CHANGE_NETWORK_INFO_MEMBER_EVIDENCE_RECORDED = PASS` is the parallel reading
for the two members, this time a Ghidra static disassembly with exact addresses
recorded verbatim there.

`BINARY_MAP_REPRODUCIBILITY = PENDING` is the strength of those readings, kept
apart from their existence. The root map was supplied from outside this
repository and the member requirements are a Ghidra reading; nothing here opens
the binary and recovers a row by running it. Recorded evidence and reproducible
evidence are different states, and this record does not let the first be read as
the second. **The governed manifest no longer declares the tokens those readings
name.** It declares all eleven, under `PRIVILEGE_POLICY = FULL_TRUSTED_MODULE`,
which is a deployment decision rather than a reading of the descriptors; what
those readings compose to is `EVIDENCED_MINIMUM_PRIVILEGES`, kept beside the
policy as what a least-privilege selection would be and as what a denial on the
target is read against.

`GET_NETWORK_INFO_LIVE_VERIFIED = PASS` because the `718db50` run reached both
roots with the token selected. `CHANGE_NETWORK_INFO_LIVE_VERIFIED = PASS`
because the `6233d86` run carried that token and the two members it is
evidenced for both answered — **for those two members and no others**, and on a
run that was target evidence rather than a canonical qualification.
`FULL_TRUSTED_SET_LIVE_VERIFIED = PASS` because the `504a6e6` artifact carried
the whole eleven-token declaration with every box selected, and the operator
reported no reached call privilege-denied. It says the selection works on this
build, and nothing about which call needs any of the nine tokens no member is
evidenced to need. `MODULE_DESCRIPTORS_STAGE_IDENTIFIED = PASS` because that run
named `ModuleDescriptor.getModuleAt`, argument 0.
`GET_MODULE_AT_NULL_INSIDE_COUNT = TARGET_OBSERVED` is the investigation after
it, and `MODULE_DESCRIPTORS_LIVE_OBSERVED = PENDING` the corrected walk, which
has run under Node only. `DEVICE_DESCRIPTOR_ADDRESS` and
`DEFAULT_VARIANT_ON_CREATION` are that investigation's other two findings,
recorded under *The run at `504a6e6`* and bounded there to `9.0.1.0858`.

`OFFICIAL_RUN_D37BA37_RAW_TRANSCRIPT = NOT_CAPTURED`,
`OFFICIAL_RUN_718DB50_RAW_TRANSCRIPT = NOT_CAPTURED`,
`RUN_6233D86_RAW_TRANSCRIPT = PARTIAL` and
`RUN_504A6E6_RAW_TRANSCRIPT = NOT_COMMITTED` are why all four runs are read
narrowly: the first two preserved only the operator-reported observations, the
third a header and one statement, the fourth nothing committed here, and no
complete set of raw envelopes reached this record. The six `NEXT_LIVE_RUN_*` states are the conditions the next run
carries so that it can establish what these could not.

- **One unnormalized, append-only transcript per execution**, named by the
  artifact SHA-256 and by the run's own `run_id`: the artifact hash because
  evidence is about the bytes that ran, and the `run_id` because a second
  execution of the same artifact must never overwrite the first.
- **A header holding only facts that exist before the first statement**, so it
  can be written first and never edited. The `network.device_inventory`
  envelope is an observation in the body, where it anchors every later
  workspace address.
- **A workspace with something in it** for an answering `IPC.network()` to
  actually walk.
- **Every observed relay input read out of the reading that published it** —
  the factory and workspace addresses, and the opaque `module_type` value —
  never predicted here.
- **Every admitted operation accounted for** as `EXECUTED` or
  `NOT_EXERCISED_PREREQUISITE_UNAVAILABLE`, so a dependent operation whose
  input was never published is recorded as unreached rather than entered with
  a placeholder.

A position is where the platform handed a subject over in one reading, and this
record makes no claim about where anything sits.

`CURRENT_NEW_CANDIDATE_PACKAGED` and `CURRENT_NEW_CANDIDATE_V6_LIVE_VERIFIED` are
`PENDING` for the same reason every candidate-specific state is: they are
questions about bytes nobody has built or run yet, and the `718db50` artifact
cannot answer them. `SUFFICIENT_FOR_FULL_M2_M3_CHAIN = NOT_PROVEN` says the two
tokens are the evidenced minimum, not that they are known to carry a descriptor
or workspace chain to the end — only a run can show that.

`IMPLEMENTED` and `COMPLETE` are statements about this repository — the
operations exist, are admitted, are bounded and are tested offline — and
deliberately not about Packet Tracer. `M2_OFFLINE = COMPLETE` says the three
descriptor readings this milestone set out to build are built and gated; it
says nothing about whether any of them answers on a target.
`M3_READ_ONLY_TOPOLOGY = STARTED` is three workspace readings — an inventory, one
device's identity, and one device's ports beside that identity. They read a
device instance's **identity and structural metadata**: its name, its model,
its DeviceType, its port count and each port's name. They read no **mutable
operational or configuration state** — no address, no link, no port up/down
state, no configuration, power, uptime or serial number — and write nothing at
all; links are `BLOCKED` for the reason recorded above. An earlier revision of
this line said every piece of device state was unread, which described the
artifact as reading less than it does.

`KERNEL_BOUNDARIES = HARDENED` covers the previous line's corrections: an
argument outside an adapter's bounds is a defect rather than a clamp, a member
that is not there is not a failed call, and the entry point answers with an
envelope even when admission or the encoder is what broke. `V6_CONTRACT =
CONSISTENT` covers the other half: a nested path is a floor rather than a fixed
set, fields are held with their types, and a published shape is externally
frozen only once a version is release-qualified — which is why this line's
shape corrections were made rather than carried, each recorded under `MJ-030`.

`PLATFORM_BOUNDARY = INTERFACE_MEMBER_ENFORCED` is this line's first correction.
A platform call is an `Interface.member` with its documented arity; every
platform object the boundary hands out carries the interface its member
documents; and a member admitted on one interface is refused on another before
anything is touched. `ADDRESSING = EXACT_INTEGER_NAMED_DOMAINS` is the second:
work is bounded by windows and walks and an address only by exact-integer
fidelity, so a topology of any size is paged rather than capped, and every
address names its domain — `factory_index`, `workspace_index` and `port_index`,
with their offsets — while the index that selects a subject is required.

Every capability stays `PENDING_TARGET` until a governed artifact built from
these sources *answers* inside `9.0.1.0858`, in a run that followed the declared
procedure. No offline, Node, exploratory or binary-reading result is promoted
into that evidence, and neither is a run that departed from the procedure. What
is no longer unknown: `privileges: []` is denied both root calls; index 1
(`GET_NETWORK_INFO`) lifts that denial at both; index 2
(`CHANGE_NETWORK_INFO`) lifts it at the two members evidenced for it; and the
full set was denied no call the `504a6e6` run reached. What is still unmeasured
is what a canonical run over the whole read-only surface returns, and — the
question this candidate exists to make answerable — whether
`platform.module_descriptors`, which stopped at a `null` from
`ModuleDescriptor.getModuleAt` at `504a6e6`, answers under the corrected walk
(MJ-015, MJ-022, MJ-032).

`LIVE: NO_LIVE_THIS_SESSION` — every run above was performed by hand, outside
the sessions that wrote this record.
