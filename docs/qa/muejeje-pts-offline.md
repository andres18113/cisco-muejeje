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
`d14692d`:

```text
.venv/Scripts/python.exe tools/build_muejeje_pts.py --check --builder 'C:/Program Files/Cisco Packet Tracer 9.0.1/bin/PacketTracer.exe'
PACKAGING_MANUAL_AVAILABLE; exit 0
```

| Field | Value |
| --- | --- |
| `status` | `PACKAGING_MANUAL_AVAILABLE` |
| `build_recipe_id` | `bbe6a2d53b38224e3973735af3df56324d2b864aedb114934201633a046bf8ab` |
| `source.commit` | `d14692d0a1aa04602053c5c1d8b6e5c90634579f`, `clean: true` |
| `source.tree` | `67f1a8e3ca4616c242e1a859ce3ca09a801a152d` |
| `inputs.artifact` | 23 files, all under `muejeje_pts/` |
| `inputs.tooling` | 8 files, the whole auditor |
| `inputs.reference` | `[]` |
| `packaging_state.recipe_complete` | `true` |
| `packaging_state.unresolved_build_options` | `[]` |
| `packaging_state.manual_blockers` | `[]` |
| `packaging_state.automation` | `BUILD_AUTOMATION_UNPROVEN` |
| `builder.actual_sha256` | matches the pinned hash |
| `artifact_sha256` | `null` — no artifact exists yet |

**Without it**, on the Linux container this line was developed in, at
`bd7250e` — the commit before the one you are reading:

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
build. Read it as "at `d14692d`, on that machine, the audit reported this".

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

**Windows, with Packet Tracer `9.0.1.0858` installed**, at `d14692d` — the
machine that has the target build, and the one this line was measured on
(checkout-local `.venv`, Python 3.12.10, pytest 9.1.1, Node v24.19.0):

```text
.venv/Scripts/python.exe -m pytest tests/muejeje -q --basetemp=tmp/fin1 -o cache_dir=tmp/fin1-cache
738 passed, 2 skipped in 168.18s; exit 0

.venv/Scripts/python.exe -m pytest tests/test_worktree_isolation.py tests/test_e95_architecture_boundaries.py -q --basetemp=tmp/fin2 -o cache_dir=tmp/fin2-cache
12 passed in 3.05s; exit 0

.venv/Scripts/python.exe -m pytest -q
5183 passed, 3 skipped, 4 warnings in 391.66s; exit 0
```

Node drove the kernel checks. The earlier Windows readings — `353 passed` at
`fc9e460` and `555 passed` at `96976de` — are superseded rather than kept beside
this one: each measured a different tree on the same machine, which is exactly
the comparison this record separates environments to prevent.

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
capability, and to `738` with this line: a platform boundary enforced per
interface member, exact-integer addressing in named domains, and
`network.device_ports`.

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

The focused runs above keep their worktree-local temporaries: none of them
clones the checkout.

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
Packet Tracer answers those calls, that it answers them with these shapes, or
that a module with `privileges: []` may make them at all.

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
| `CAPABILITY_RESOLUTION_VERIFIED` | `PENDING_TARGET` | every platform and network capability has only ever been driven against a stub |

### Milestone states, and what they are not

`MJ-033` separates *implementation progress* from *Core Readiness*, and this is
where the second one is measured. A milestone may be implemented while an
earlier one waits on target evidence; none of them is `DONE` until it is
`CORE_READY`.

```text
M0B = NOT_COMPLETE
M0C = NOT_COMPLETE
M1_CORE_READY = NO
M2_CORE_READY = NO
M3_CORE_READY = NO
ZERO_CHANGE_CUTOVER = NOT_ACHIEVED
```

| State | What is still missing |
| --- | --- |
| `M0B` | credential and transport API qualification. No transport exists, so `MJ-026`'s terms are baselined rather than exercised and there is nothing to qualify a credential against |
| `M0C` | batch and auth-boundary semantics. `MJ-027` is the contract the first batch operation must satisfy and no batch operation exists; the auth boundary is in the same position |
| `M1_CORE_READY` | target evidence. The V6 kernel is verified under Node and has never run inside Packet Tracer (`MJ-015`) |
| `M2_CORE_READY` | target evidence, and packaging. Every platform and network capability is `PENDING_TARGET`, no `.pts` has been built from these sources, and `OFFICIAL_PACKAGING_PROVED` is `PENDING_GUI` |
| `M3_CORE_READY` | complete intended scope, and target evidence. The workspace inventory, one device's identity and one device's ports are implemented; the workspace's links are not (see below), and every workspace capability is `PENDING_TARGET` |
| `ZERO_CHANGE_CUTOVER` | a release-qualified artifact, and a compatibility facade outside the V6 core (`MJ-034`). Nothing has been packaged or qualified, no facade exists, and no consumer has been cut over |

**A green run on this page does not move any of them.** The suite establishes
what this repository's own code does. `M0B` and `M0C` wait on work that has not
been written; `M1`, `M2` and `M3` wait on a target reading, and `M3` on
unfinished scope as well; the cutover waits on all of it. This line hardened the
contract and added a capability and changed none of these states — which is
`MJ-033` working as intended, not a milestone being skipped.

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

Until a target run happens, every `platform.*` and `network.*` operation is
code with a contract and no target reading, which is what `PENDING_TARGET`
means.

**And what the first reading will be is not something this record predicts.**
The module requests no privilege, because no evidence says which privilege
these calls need (`MJ-032`). Whether a Script Module carrying none may make
them is a second unknown, and this repository has measured neither — so an
earlier revision of this file, which said the first run "should report
`PLATFORM_CALL_FAILED`", was making a claim about `9.0.1.0858` with nothing
behind it, and it is withdrawn rather than restated. The run records whichever
reading comes back, and every reading is worth recording: an answer, a member
the object does not offer, a call that did not return, or an answer that could
not be attributed.

That attribution is also why the boundary was corrected before this line was
written. A bug inside an adapter used to come back as `PLATFORM_CALL_FAILED`,
and so did a member that was never called — on a target, neither would have
been distinguishable from a refusal (`MJ-022`, `MJ-031`).

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
preconditions are met at `d14692d` — clean tree, `PACKAGING_MANUAL_AVAILABLE`,
recipe id `bbe6a2d5…`, verified builder — so a person can start at its step 1.

When that run happens, it records: source commit and tree, the recipe id, the
externally measured artifact SHA-256, the Packet Tracer build, and every
response envelope verbatim — including whichever `resolution` and
`unavailable_reason` each platform reading came back with. Only then do
`OFFICIAL_PACKAGING_PROVED`, `TARGET_API_BASELINED` and
`CAPABILITY_RESOLUTION_VERIFIED` change, and only from that evidence — never
from a clean offline report, and never from the operations that make no
platform call.

**No exact-HEAD `.pts` exists.** Checked at `d14692d` on the Windows machine
that has the target build: `dist/` holds only the ignored `muejeje.build.json`,
and no `muejeje*.pts` exists anywhere in the checkout.

`Cisco Packet Tracer 9.0.1\extensions\` holds **no Muejeje entry**, re-checked
at `d14692d` — and it is
not empty, which is what an earlier revision of this file recorded. It carries
Cisco's own eleven bundled extension directories and six `.pts` files
(`ActivitySequencer`, `Clear Terminal Agent`, `Marvel`, `PcSoftware`,
`PTINTERNAL`, `resource`). "Empty" was the wrong measurement of the right fact,
and the right fact is that nothing of ours is installed there. Nothing has been
packaged from these sources, and `OFFICIAL_PACKAGING_PROVED` stays `PENDING_GUI`
rather than being softened into anything else.

## Scope

This is **validator** qualification only. It establishes nothing about a
candidate `.pts`, its content, or its runtime behaviour. No `.pts` was built or
installed, no Script Module was imported or started, and no LIVE operation was
performed.

The platform surface added in this line does not change that. Its only
executions have been under Node — against no platform object, and against a
stub — and neither is a Packet Tracer reading.

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
CAPABILITY_RESOLUTION_VERIFIED = PENDING_TARGET
OFFICIAL_PACKAGING_PROVED      = PENDING_GUI
TARGET_API_BASELINED           = PENDING_TARGET
```

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

Every capability stays `PENDING_TARGET` until an artifact built from these
sources answers inside `9.0.1.0858`. No offline or Node result is promoted into
that evidence, and nothing here predicts what a target will answer — including
whether a module carrying `privileges: []` is allowed to ask (MJ-015, MJ-032).

`LIVE: NO_LIVE_THIS_SESSION`
