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

Recomputed on the clean committed tree at `fc9e460`, with the pinned builder
given explicitly:

```text
.venv/Scripts/python.exe tools/build_muejeje_pts.py --check --builder 'C:/Program Files/Cisco Packet Tracer 9.0.1/bin/PacketTracer.exe'
PACKAGING_MANUAL_AVAILABLE; exit 0
```

| Field | Value |
| --- | --- |
| `status` | `PACKAGING_MANUAL_AVAILABLE` |
| `build_recipe_id` | `73f087e757eb9ab16f29661f1d08b816ede25b98c9e3eb179000d3b0c3f118e1` |
| `source.commit` | `fc9e460351268ab29324f42c80ffc5d2c5b0fffc`, `clean: true` |
| `source.tree` | `33e3857a28447d7ecffadae34198bdb53f9b27cf` |
| `inputs.artifact` | 10 files, all under `muejeje_pts/` |
| `inputs.tooling` | 8 files, the whole auditor |
| `inputs.reference` | `[]` |
| `packaging_state.recipe_complete` | `true` |
| `packaging_state.unresolved_build_options` | `[]` |
| `packaging_state.manual_blockers` | `[]` |
| `packaging_state.automation` | `BUILD_AUTOMATION_UNPROVEN` |
| `builder.actual_sha256` | matches the pinned hash |
| `artifact_sha256` | `null` — no artifact exists yet |

`build_options` at that commit: `module_id`
`io.github.andres18113.muejeje.runtime`, `startup` `on_startup`, `privileges`
`[]`, one Custom Interface file, and the nine-file `engine_script_order` — core,
protocol, admission, the declared platform adapter, then the three operations
alphabetically, then dispatch, then lifecycle.

**A report cannot carry its own commit's recipe id.** Source commit and tree are
part of recipe identity, so committing this file changes the id it records. The
measurement above is therefore at the commit *before* the one that writes it
down, which is the only order that can exist; re-running the one command above
gives the id at whatever HEAD you are on, and step 2 of
[the packaging recipe](muejeje-pts-packaging-recipe.md) is where a packaging run
does exactly that.

The two standing blockers are `compiler_command` and `content_validation`, both
automation prerequisites. Neither stops a human from packaging, which is exactly
the distinction the five-state model exists to keep (`MJ-016`).

**The recipe id is a measurement, not a constant**, and that is the design
working: an id that survived a change to its inputs would identify the wrong
build. Read it as "at `fc9e460`, the audit reported this".

**It also depends on the line endings of the checkout it was measured in.** The
audit hashes the *working* bytes of each declared input, and this repository is
checked out with `core.autocrlf=true`, so a fresh clone and this worktree can
disagree on the id while agreeing on every commit. That is a property of the
measurement rather than a defect in it — the recipe's own anchors, the manifest
hash and the source commit and tree, are byte-stable — but it means one recipe
id is comparable only with another measured the same way. Recorded here because
a mismatch between two machines otherwise reads like a tampered input.

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
353 passed, 2 skipped in 106.37s; exit 0

.venv/Scripts/python.exe -m pytest tests/test_worktree_isolation.py tests/test_e95_architecture_boundaries.py -q --basetemp=tmp/m1-arch -o cache_dir=tmp/m1-arch-cache
12 passed in 2.24s; exit 0

.venv/Scripts/python.exe -m pytest -q
4798 passed, 3 skipped in 329.53s; exit 0
```

M0F split the two monolithic modules into `tests/muejeje/`. The ADR-001 run this
replaced was `39 passed, 2 skipped` over `tests/test_muejeje_build.py` and
`tests/test_muejeje_build_identity.py`, which no longer exist. The muejeje area
grew from `155 passed` to `214 passed` with `runtime.capabilities` and the
layer-aware fitness gates, and from `214` to `353` with the kernel hardening
and the first M2 slice: bounded V6 admission, the V6 compatibility contract,
the privilege-evidence rule, the future-safe architecture gates, and the
read-only platform adapter with `platform.device_descriptors`.

Five test modules were split out along the way, each because its predecessor
crossed the 300-line budget rather than because anyone chose to: `measure` out
of `support`, `test_layer_boundaries` out of `test_source_root`,
`test_capability_claims` out of `test_unobserved_claims`, and
`test_platform_adapter` and then `test_platform_readings` out of
`test_platform_descriptors`. `validation_v6.js` came out of `protocol_v6.js`
for the same reason. That is `MJ-020` doing what it is for: the budget forced
each split at the point a file stopped being readable in one sitting, and both
exception tables in the fitness gate are still empty.

The two skips are Windows symlink-creation privilege limitations. The hardlink
alias, hidden-source/manifest, malformed-JSON and reference-input security checks
all executed. Two further gates skip when Packet Tracer is **not** installed —
they read Cisco's own pages for the Script Engine lifecycle sentences and the
privilege identifiers — and both ran here.

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
| `STRUCTURAL_VERIFIED` — always runs | the source layout, who owns `mcpDispatchV6`, `main()` and `cleanUp()`, the absence of `eval`/`new Function` and of `ipc` outside the one declared adapter, the declared `engine_script_order`, and that no document claims a capability this artifact does not have | any behaviour |
| `RUNTIME_VERIFIED` — Node, skipped when absent | what *our* JavaScript does: the envelope, every bound, each rejection class, the session token, and the two platform-free results — `runtime.identify` and `runtime.capabilities` | anything about Packet Tracer |
| `STUB_DRIVEN` — Node, skipped when absent | what the *platform adapter* does with a well-formed answer, with an unusable one, with a call that throws, and with no platform object at all; and which methods it actually called | anything about Packet Tracer's hardware factory, or about whether these calls are permitted there |

**The third row is the one to be careful with.** `platform.device_descriptors`
was driven against a stub that answers with Cisco's documented getter names. A
stub written from a reference is not the reference implementation: it proves
our adapter reads a well-formed answer correctly and refuses a malformed one,
and it proves the adapter asked for nothing outside the documented set — which
is a claim about *our code*, checked by comparing the recorded call log against
that set. It is not evidence that Packet Tracer answers those calls, that it
answers them with these shapes, or that a module with `privileges: []` may make
them at all.

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
| `CAPABILITY_RESOLUTION_VERIFIED` | `PENDING_TARGET` | the platform adapter has only ever been driven against a stub |

### A green V6 run is not IpcAPI qualification

`TARGET_API_BASELINED` asks whether the **platform APIs Muejeje uses** are
evidenced against the pinned build, from the artifact that uses them. Nothing
about a successful V6 execution answers that question, and it would still not
answer it if the `.pts` were built and both platform-free operations replied
perfectly: `runtime.identify` and `runtime.capabilities` make no platform call,
so they can succeed on a target with every privilege denied and every factory
API missing.

The nine calls the adapter makes, and what each is actually backed by:

| Call | Cisco reference | Target-evidenced against `9.0.1.0858` |
| --- | --- | --- |
| `ipc.hardwareFactory()` | `class_hardware_factory.html` | **yes** — the CP-SCALE factory surveys |
| `HardwareFactory.devices()` | `class_hardware_factory.html` | **yes** — same surveys |
| `DeviceDescriptor.getModel()` | `class_device_descriptor.html` | **yes** — same surveys |
| `DeviceDescriptor.getType()` | `class_device_descriptor.html` | **yes** — same surveys |
| `DeviceFactory.getAvailableDeviceCount()` | `class_device_factory.html` | **no** — documented only |
| `DeviceFactory.getAvailableDeviceAt(int)` | `class_device_factory.html` | **no** — documented only |
| `DeviceDescriptor.isModelSupported()` | `class_device_descriptor.html` | **no** — documented only |
| `DeviceDescriptor.getSupportedModuleTypeCount()` | `class_device_descriptor.html` | **no** — documented only |
| `DeviceDescriptor.getSupportedModuleTypeAt(int)` | `class_device_descriptor.html` | **no** — documented only |

The four "yes" rows are evidenced by
[the factory-structure record](../reference/cp-scale/ROUTER0_POE_FACTORY_STRUCTURE_20260907.md)
— runs `factory-survey-9f967ef6` and `factory-survey-102006c6`, read-only, zero
mutations, against `9.0.1.0858`. **Those runs are not Muejeje's evidence.** They
were driven from the legacy channel, in a context with its own privileges, not
from a Script Module carrying `privileges: []`; and they used
`getDescriptor(DeviceType, string)`, which Muejeje deliberately does not, since
asking by type would require carrying a numeric Cisco enum as the authority for
which types exist (`MJ-014`). So they establish that the descriptor path works
on this build — which is why it was chosen — and nothing about whether *this
artifact* may walk it.

The five "no" rows are documented and unmeasured. They are the enumeration and
per-model support pair, and they are exactly what a target run has to observe
first. Until it does, `platform.device_descriptors` is code with a contract and
no target reading, which is what `PENDING_TARGET` means.

**And the expected first reading is a denial.** The module requests no
privilege, because no evidence says which privilege these calls need
(`MJ-032`), so the first target run should report
`PLATFORM_CALL_FAILED` — an observation worth recording, and still not
qualification of any API.

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
preconditions are met at `fc9e460` — clean tree, `PACKAGING_MANUAL_AVAILABLE`,
recipe id `73f087e7…`, verified builder — so a person can start at its step 1.

When that run happens, it records: source commit and tree, the recipe id, the
externally measured artifact SHA-256, the Packet Tracer build, and the **three**
response envelopes verbatim — including whichever `resolution` and
`unavailable_reason` the descriptor reading came back with. Only then do
`OFFICIAL_PACKAGING_PROVED`, `TARGET_API_BASELINED` and
`CAPABILITY_RESOLUTION_VERIFIED` change, and only from that evidence — never
from a clean offline report, and never from the two operations that make no
platform call.

**No exact-HEAD `.pts` exists.** Checked at this commit: `dist/` holds only the
ignored `muejeje.build.json`, no `muejeje*.pts` exists anywhere in the checkout
outside pytest temporaries, and the user profile's
`Cisco Packet Tracer 9.0.1\extensions\` directory is empty. There is therefore
nothing to qualify read-only, and `OFFICIAL_PACKAGING_PROVED` stays
`PENDING_GUI` rather than being softened into anything else.

## Scope

This is **validator** qualification only. It establishes nothing about a
candidate `.pts`, its content, or its runtime behaviour. No `.pts` was built or
installed, no Script Module was imported or started, and no LIVE operation was
performed.

The platform adapter added in this line does not change that. Its only
executions have been under Node — against no platform object, and against a
stub — and neither is a Packet Tracer reading.

```text
KERNEL_HARDENING               = PASS
V6_CONTRACT_VERIFIED           = PASS
M1_OFFLINE                     = COMPLETE
OFFICIAL_PACKAGING_PROVED      = PENDING_GUI
TARGET_API_BASELINED           = PENDING_TARGET
M2_IMPLEMENTATION              = STARTED
CAPABILITY_RESOLUTION_VERIFIED = PENDING_TARGET
```

`LIVE: NO_LIVE_THIS_SESSION`
