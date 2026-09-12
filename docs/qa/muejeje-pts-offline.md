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
with this line: engine files named for the order Packet Tracer lists them, the
audit gate that holds the manifest to that order, and the refusal, restart and
diagnostics steps of the official run.

Eighteen test modules have been split out along the way, each because its
predecessor crossed the 300-line budget rather than because anyone chose to —
most recently `test_network_port_values` out of `test_network_ports`, and
before it `test_platform_reading_values` out of `test_platform_readings`. The artifact split the same way and
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

| Gate | State | Why |
| --- | --- | --- |
| `OFFICIAL_PACKAGING_PROVED` | `PASS` | the recipe produced a saved `dist/muejeje.pts` that Packet Tracer loaded and started, and the artifact was measured externally |
| `V6_KERNEL_VERIFIED` | `PASS` | that saved artifact's own engine answered: `mcpDispatchV6` present, identify and capabilities, all five refusal classes, and identify again across a stop and a start |
| `TARGET_API_BASELINED` | `PENDING_TARGET` | no platform member has answered. Both root calls were denied for insufficient privilege, which is a fact about privilege and not a reading of the API |
| `CAPABILITY_RESOLUTION_VERIFIED` | `PENDING_TARGET` | every platform and workspace capability was denied at its root call, and none has answered |
| `REQUIRED_PRIVILEGE_IDENTIFIERS` | `UNEVIDENCED` | Packet Tracer's diagnostic names the IPC call and never a privilege identifier, and nothing installed maps one to the other. The manifest declares `[]` (`MJ-032`) |

### The official LIVE run at `d37ba37` — the governed artifact

Performed by hand on Packet Tracer `9.0.1.0858`, following
[the packaging recipe](muejeje-pts-packaging-recipe.md) from step 1, and
reported back verbatim. No privilege was changed at any point.

| Record | Value |
| --- | --- |
| candidate | `d37ba37786107ed8128d17d589d889ee1fe9b16f`, tree `d467133b551088441e07bf4a34d50de323c927d3` |
| `build_recipe_id` | `7d5e710723151a67e2df84dcb11d43b31ad7a89cba8ae2410cdf987689d216bb` |
| artifact | `dist/muejeje.pts`, SHA-256 `6951c066ec158d57855dfd739619482cd05f40e007f5c28fb5fcc66e58a12146`, 48185 bytes, measured outside the artifact (`MJ-017`) |
| Packet Tracer | `9.0.1.0858`, `PacketTracer.exe` SHA-256 `843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1` |
| privileges | `[]` — none selected, and none selected later |
| entry point | the module's Debug Dialog |

**What it established.**

1. **The governed engine order held.** Packet Tracer listed the 22 engine files
   `010_core.js` through `220_lifecycle.js`, in that order — the order
   `build_options.engine_script_order` declares, carried by the file names. The
   packaging correction made at `29afd2c` is confirmed on the target.
2. **The saved artifact loaded and started.** `dist/muejeje.pts` was added as a
   Script Module on the pinned build and started, which is what
   `OFFICIAL_PACKAGING_PROVED` is about: a recipe id now identifies an artifact
   that exists, whose bytes are measured, and which Packet Tracer accepted.
3. **The V6 kernel answered from inside it.** `typeof mcpDispatchV6` answered
   `function`; `runtime.identify` and `runtime.capabilities` came back
   `ok: true`; each of the five refusal classes — `MALFORMED_REQUEST`,
   `PROTOCOL_MISMATCH`, `INVALID_REQUEST`, `UNKNOWN_OPERATION`, `INVALID_ARGS` —
   came back with its own code; and after an explicit stop and start,
   `runtime.identify` answered again. That is `V6_KERNEL_VERIFIED`, and it is
   about *this* artifact rather than about a Node run or an exploratory module.
4. **The kernel stayed healthy through the denials.** Every `platform.*` and
   `network.*` reading came back as a well-formed envelope reporting
   `UNAVAILABLE` / `PLATFORM_CALL_FAILED`, and Packet Tracer printed beside each
   that the module lacked the necessary privilege for IPC call
   `"hardwareFactory"` or `"network"`. A denied call did not damage the engine:
   the runtime operations kept answering afterwards.

**What it did not establish.** No platform member answered, so nothing about
Cisco's API was baselined and no capability resolved. `PLATFORM_CALL_FAILED` is
still not a privilege reading by itself — the diagnostic printed beside it is
what attributed the cause, for those two calls, in that run (`MJ-022`,
`MJ-031`).

**Its manifest configuration stands.** `privileges: []` is the right
declaration while no identifier is evidenced for either call (`MJ-032`).
Whatever supersedes it is a different recipe id and needs its own run; this
record is what that run is measured against.

### The exploratory run at `ed3a0b0` — evidence, not an artifact

Performed by hand on Packet Tracer `9.0.1.0858`, following the recipe as it then
stood until its import step, where the listing order made it impossible to
follow, and reported back verbatim. No privilege was changed at any point.

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
- **Which privilege either call needs is still unevidenced.** The diagnostic
  names an IPC call, never a privilege identifier, and nothing installed maps
  one to the other, which is why the manifest declares `[]` through both runs
  (`MJ-032`).
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
| `M0B` | IPC privilege qualification first, then credential and transport API qualification. The governed artifact carrying no privilege was denied both root IPC calls, so no API reached through them is baselined until the privilege each needs is evidenced. No transport exists, so `MJ-026`'s terms are baselined rather than exercised |
| `M0C` | batch and auth-boundary semantics. `MJ-027` is the contract the first batch operation must satisfy and no batch operation exists; the auth boundary is in the same position |
| `M2_CORE_READY` | privilege and target evidence. Every platform capability is `PENDING_TARGET`: with `privileges: []` its root call, `IPC.hardwareFactory()`, was denied, and which privilege it needs is unevidenced |
| `M3_CORE_READY` | complete intended scope and target evidence. The workspace inventory, one device's identity and one device's ports are implemented; the workspace's links are not (see below); and every workspace capability is `PENDING_TARGET`, its root call `IPC.network()` denied the same way |
| `ZERO_CHANGE_CUTOVER` | a release-qualified artifact, and a compatibility facade outside the V6 core (`MJ-034`). One artifact is now packaged and kernel-qualified, no version is release-qualified, no facade exists, and no consumer has been cut over |

**A green offline run still moves none of them.** The suite establishes what
this repository's own code does. `M0C` waits on work that has not been written;
`M2` and `M3` wait on platform readings that answer, and `M3` on unfinished
scope as well; the cutover waits on all of it.

**The next task for `M0B`, `M2` and `M3` is controlled privilege qualification,
not more implementation.** It is its own declared run, changing exactly one
thing: a privilege set whose identifiers are evidenced (`MJ-032`), in a recipe
that declares it, with Packet Tracer's diagnostics recorded beside every
envelope. Nothing here yet says which identifier either call needs, and finding
that evidence is the first half of the task.

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
`9.0.1.0858`, and through what. It is not Muejeje's evidence, and no row of it
is a Muejeje target reading — every one of those is still `PENDING_TARGET`.

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

Until a governed artifact's run answers, every `platform.*` and `network.*`
operation is code with a contract and no target answer, which is what
`PENDING_TARGET` means.

**What the first reading was, and what it still does not say.** The module
requests no privilege, because no evidence says which privilege these calls
need (`MJ-032`). An earlier revision of this file said the first run "should
report `PLATFORM_CALL_FAILED`"; that was a claim about `9.0.1.0858` with nothing
behind it, and it stays withdrawn even though the exploratory run then came
back that way. What made that run evidence is what was recorded beside each
envelope: Packet Tracer's own diagnostic, naming a missing privilege for
`IPC.hardwareFactory()` and `IPC.network()`. Which privilege those calls need is
still unmeasured, and a run records whichever reading comes back — an answer, a
member the object does not offer, a call that did not return, or an answer that
could not be attributed — with whatever Packet Tracer printed beside it.

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
full: [the packaging recipe](muejeje-pts-packaging-recipe.md). It was followed
once, at `d37ba37`, and that run is recorded above; it is followed again for
each new recipe id, which is what a changed privilege set produces.

Each run records: source commit and tree, the recipe id, the externally
measured artifact SHA-256, the Packet Tracer build, the privilege selection
read back from the module, the Script Engine listing as Packet Tracer showed
it, and every response envelope verbatim with whatever Packet Tracer printed
beside it — including whichever `resolution` and `unavailable_reason` each
platform reading came back with. The target gates change only as far as that
evidence goes: `OFFICIAL_PACKAGING_PROVED` and `V6_KERNEL_VERIFIED` from the
saved artifact loading and its kernel answering, which the `d37ba37` run did;
`TARGET_API_BASELINED` and `CAPABILITY_RESOLUTION_VERIFIED` only from platform
readings that answered, and none has. Never from a clean offline report, never
from the operations that make no platform call, never from a call Packet Tracer
denied.

**The `.pts` of record is the `d37ba37` artifact**, SHA-256
`6951c066ec158d57855dfd739619482cd05f40e007f5c28fb5fcc66e58a12146`, 48185
bytes. `dist/` is git-ignored machine-local output, so no `.pts` is tracked in
the checkout and none is expected to be. **No artifact exists for the current
manifest**, whose privilege set differs and whose recipe id therefore differs.

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
is established about an artifact comes from the two LIVE runs recorded above —
the official one at `d37ba37` and the earlier exploratory one — each performed
by hand, outside the sessions that wrote this record. **This session performed
no LIVE run**; it recorded the official one, which is offline work.

The platform surface's only executions inside Packet Tracer were those two
runs', and every one of its six operations was denied at its root call in both.
Everywhere else it has run under Node — against no platform object, and against
a stub — and neither is a Packet Tracer reading.

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
REQUIRED_PRIVILEGE_IDENTIFIERS   = UNEVIDENCED
```

`ENGINE_ORDER = CARRIED_BY_FILE_NAMES` was the previous line's packaging
correction, and the official run confirmed it on the target: Packet Tracer
lists engine files by name, the names spell the declared order, and the audit
refuses any other.

`EMPTY_PRIVILEGES_ROOT_IPC = TARGET_OBSERVED_DENIED` records the diagnostics
for `IPC.hardwareFactory()` and `IPC.network()` in both runs, and nothing
wider.

`REQUIRED_PRIVILEGE_IDENTIFIERS = UNEVIDENCED` is why the manifest still
declares `[]`: Packet Tracer's diagnostic names the IPC call and never an
identifier, and nothing installed maps one to the other.

`IMPLEMENTED` and `COMPLETE` are statements about this repository — the
operations exist, are admitted, are bounded and are tested offline — and
deliberately not about Packet Tracer. `M2_OFFLINE = COMPLETE` says the three
descriptor readings this milestone set out to build are built and gated; it
says nothing about whether any of them answers on a target.
`M3_READ_ONLY_TOPOLOGY = STARTED` is three workspace readings — an inventory, one
device's identity, and one device's ports beside that identity — with addresses
and every piece of device state deliberately unread, and links `BLOCKED` for the
reason recorded above.

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
these sources *answers* inside `9.0.1.0858`. No offline, Node or
exploratory result is promoted into that evidence. Whether a module carrying
`privileges: []` may make the two root calls is no longer unknown — it was
denied them — and which privilege would allow them still is (MJ-015, MJ-032).

`LIVE: NO_LIVE_THIS_SESSION` — both runs above were performed by hand, outside
the sessions that wrote this record.
