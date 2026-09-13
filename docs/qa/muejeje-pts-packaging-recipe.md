# Muejeje `.pts` — the official packaging recipe

The complete procedure for producing `dist/muejeje.pts` from a pinned recipe.

**The only packager is Cisco's own Scripting Interface.** PTBuilder is not used,
and neither is any community or offline `.pts` packager: the artifact is
encrypted by Packet Tracer, and a `.pts` produced by anything else would be a
file whose provenance we could not explain (`MJ-013`). No automated packaging
path has been demonstrated, which is why `packaging_state.automation` stays
`BUILD_AUTOMATION_UNPROVEN` — that is a recorded fact about Packet Tracer, not a
defect in this repository (`MJ-016`).

Every UI element named below is quoted from Cisco's installed `help/default/`
pages and recorded, with its source page, in
[the v2 preflight inventory](muejeje-pts-v2-preflight-inventory.md). Nothing here
is inferred from a screenshot or from memory (`AGENTS.md` rule 6). The one
behaviour this procedure depends on that no installed page documents — how the
Scripting Interface orders the engine files it lists — is marked, where it is
used, as observed on the target build, with the run that observed it.

## Preconditions

All four, in order. Each one is checkable before Packet Tracer is opened.

1. **The tree is committed and clean.** A recipe describes bytes at a commit; a
   dirty tree would produce an artifact identifying a state that never existed.
2. **The audit reaches `PACKAGING_MANUAL_AVAILABLE`.** Run, from the repository
   root with the checkout-local interpreter:

   ```powershell
   .\.venv\Scripts\python.exe tools/build_muejeje_pts.py --check --builder 'C:/Program Files/Cisco Packet Tracer 9.0.1/bin/PacketTracer.exe'
   ```

   `dist/muejeje.build.json` must report `status: PACKAGING_MANUAL_AVAILABLE`, a
   non-null `build_recipe_id`, and `reference_inputs: []`. No bytecode cache
   has to be purged first: the audit compiles its own code from source into a
   directory of its own, outside the checkout, and reads no `__pycache__` in it.
3. **The builder is the pinned build.** Packet Tracer `9.0.1.0858`, with
   `bin/PacketTracer.exe` SHA-256
   `843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1`. The audit
   checks this when `--builder` is given; without it the run reports a missing
   explicit builder path and manual packaging is unavailable.
4. **The destination is disposable.** `dist/muejeje.pts` is git-ignored,
   machine-local output. No existing `.pts` is ever replaced — in particular the
   legacy MCP Control Center artifact, which keeps serving its own product, is
   never overwritten, moved or edited (`MJ-013`).

## The recipe

Values come from `build_options` in
`muejeje_pts/manifest/muejeje-build-manifest.json`. They are not retyped from
here: the manifest is the source, this table is the reading of it.

| Field | Value |
| --- | --- |
| Module ID | `io.github.andres18113.muejeje.runtime` |
| Startup | `On Startup` |
| Privileges | `GET_NETWORK_INFO` and `CHANGE_NETWORK_INFO`, and nothing else |
| Signing | none (`TODO-SIGNING` is open; an unsigned module is what this recipe produces) |
| Custom Interfaces | `muejeje_pts/interface/index.html` |
| Script Engine files | every file below, all from `muejeje_pts/script-engine/`, and listed by Packet Tracer **in this order** |

1. `010_core.js`
2. `020_protocol_v6.js`
3. `030_validation_v6.js`
4. `040_arguments_v6.js`
5. `050_platform_reading.js`
6. `060_platform_adapter.js`
7. `070_network_adapter.js`
8. `080_network_identity_adapter.js`
9. `090_network_ports_adapter.js`
10. `100_platform_device_adapter.js`
11. `110_platform_module_adapter.js`
12. `120_platform_support_adapter.js`
13. `130_network_identity.js`
14. `140_network_inventory.js`
15. `150_network_ports.js`
16. `160_platform_discovery.js`
17. `170_platform_modules.js`
18. `180_platform_support.js`
19. `190_runtime_capabilities.js`
20. `200_runtime_identity.js`
21. `210_dispatcher_v6.js`
22. `220_lifecycle.js`

This list is a reading of `build_options.engine_script_order`, and a gate holds
it equal to that declaration. An earlier revision named nine of these files
long after the kernel had split, so a module packaged by following it would
have been missing its admission rules, its reading vocabulary and every
platform adapter — and nothing noticed, because nothing compared the two.

The engine order is the dependency direction, because *"all script files are
executed (evaluated) in the Script Engine in the same order as listed in the
Scripting Interface"*. Core first, then the protocol envelope and the admission
that refuses with it, then what a platform reading is, then the call boundary
and the adapters that read through it, then operations — alphabetically among
themselves, since no operation depends on another — then dispatch, then the
lifecycle that may call all of it (`MJ-019`).

**The file names carry that order, because the Scripting Interface lists by
name.** Observed on `9.0.1.0858` by an exploratory run at `ed3a0b0`, which was
not an official artifact: the engine files imported one at a time in dependency
order were listed alphabetically instead, and no control to reorder them was
observed; copies of the same bytes renamed with a two-digit prefix were listed
in prefix order, and the kernel ran. So a module is evaluated in the order its
file names sort in, whatever order they were imported in. Each name here starts
with a three-digit prefix, in steps of ten so a file can be inserted without
renaming the kernel, and no two files share one — how Packet Tracer collates the
rest of a name was never measured, so nothing is left for it to decide. The
audit refuses a declared order the names do not sort in, with no recipe id and
no `PACKAGING_MANUAL_AVAILABLE`, rather than leave the difference to be found in
the GUI.

## Steps

1. Open Packet Tracer `9.0.1.0858`.
2. **Extensions → Scripting → New PT Script Module**. The editor opens with six
   parts: Info, General, Script Engine, Custom Interfaces, Data Store, Debug.
3. **General**: set the Module ID, set Startup to `On Startup`, and select
   **`GET_NETWORK_INFO` and `CHANGE_NETWORK_INFO`, and no other privilege**.
   *"The security privileges indicate which IPC calls this Script Module can
   make. Calls to unselected privileges will be denied"*.

   **Then read the selection back and record it**, before importing anything.
   Every other privilege must be unselected. If the module shows any third
   privilege selected, or either of these two missing, stop: a module carrying a
   different set is a different recipe, and nothing it answered would be evidence
   about this one.

   **This is a deliberate, and consequential, choice.** The `runtime.*`
   operations make no IPC call, so nothing selected here changes what they do.
   The `platform.*` and `network.*` ones do. The two root calls —
   `IPC.hardwareFactory()` and `IPC.network()` — require privilege index 1,
   which serializes as `GET_NETWORK_INFO`; the `718db50` run confirmed both
   roots answer with it. Two read members beneath them —
   `DeviceFactory.getAvailableDeviceCount()` and `Device.getName()` — require
   index 2, which serializes as `CHANGE_NETWORK_INFO`, read from the pinned
   `PacketTracer.exe` by Ghidra. That evidence, the whole privilege map and what
   it does *not* establish — in particular that `CHANGE_NETWORK_INFO` is a call
   requirement and not a mutation claim — are recorded in
   [the privilege map](muejeje-pts-privilege-map.md).

   **Least privilege is the rule, not the starting point.** Nothing else is
   selected, because no other call this module makes is evidenced to require
   anything else — and a privilege is a build option, so a different set is a
   different recipe id identifying a different artifact.
   **Never change the privileges during a run.**
4. **Script Engine**: import every engine file above, under the name it has in
   the tree. Import; do not paste. Pasted source loses its newlines in the
   Builder Code Editor, and these files are ordinary multi-line JavaScript with
   comments. The order they are imported in decides nothing, because the
   Scripting Interface lists them by name, and no file is renamed or copied to
   change that: an alias would be a file the recipe never declared.
   **Then compare the list it shows with the list above, entry by entry, and
   record it.** If they differ, stop — the module would evaluate in an order
   nobody declared, and nothing it answered would be evidence about this recipe.
5. **Custom Interfaces**: import `index.html`. It is the only interface file, it
   references no external resource, and it loads no script.
6. **Data Store**: leave empty. *"Data store files … are not saved to the pts
   file unless the user edits the Script Module and saves it to pts file"*, and
   this module stores nothing.
7. **Save** in the Scripting Interface, to `dist/muejeje.pts`. *"Editing a Script
   Module does not save it to disk until you click on Save"*, and `#include` —
   which these sources do not use — would be resolved at this point.

## After saving

Measure and record, in this order. The artifact hash is measured **outside** the
artifact and is never embedded in it (`MJ-017`).

```powershell
.\.venv\Scripts\python.exe -c "from packet_tracer_mcp.infrastructure.pts import artifact_sha256; print(artifact_sha256('dist/muejeje.pts'))"
```

| Record | From |
| --- | --- |
| source commit and tree | `report.source` |
| `build_recipe_id` | `report.build_recipe_id` |
| artifact SHA-256 | the command above |
| artifact size | measured the same way, in bytes |
| run id | created before the first qualification statement, one per execution |
| Packet Tracer build | `9.0.1.0858`, and its `PacketTracer.exe` hash |
| observed responses | the read-only exercise below |
| Script Engine listing | step 4, as Packet Tracer showed it |
| Packet Tracer diagnostics | beside each envelope, verbatim — see below |

## Read-only qualification

The artifact is exercised, never used to change anything. Add the saved `.pts`
on the pinned build — *"Add/remove in Extensions->Scripting->Configure PT Script
Modules..."* — start it, and drive only, in this order:

1. `typeof mcpDispatchV6`, which must answer `function`;
2. `runtime.identify`, then `runtime.capabilities`;
3. one request per refusal class, from the table below;
4. an explicit **stop** of the module and a **start**, each recorded by the
   operator as it happens, then `runtime.identify` again;
5. every other operation `runtime.capabilities` reported, each accounted for
   exactly once: `EXECUTED`, or `NOT_EXERCISED_PREREQUISITE_UNAVAILABLE` when a
   relay input it needs was not published in this run.

Driving the list the runtime reports, rather than a list copied into this
document, is what keeps this procedure current when an operation is added
(`MJ-008`). The calls below cover every operation admitted today, and a gate
drives each one through the kernel and holds the set complete — an earlier
revision omitted one, and nothing noticed. A written statement is not an
instruction to enter it regardless: the gate holds what is *written*, and which
statements a run enters depends on which relay inputs that run observed.

The module creates, opens and modifies nothing, and neither does this
procedure: no device, link or configuration is touched, and no transport, bridge
or HTTP endpoint is implemented or contacted. The workspace readings are taken
on a disposable workspace the operator prepares beforehand, and never on a
topology that holds anyone's real work. **A run declares which workspace it was
taken over, and that workspace decides what the run can establish**: on an empty
one an answering `network.*` root reaches no member below it, so nothing beneath
it is observed. The next declared run requires a specific two-device fixture for
exactly that reason —
[the minimum-privilege LIVE runbook](muejeje-pts-privilege-live-runbook.md). Every admitted operation is
read-only. The `runtime.*` ones make no platform call at all; the `platform.*`
ones make documented getter calls on the hardware *factory*, which describes
what models exist and instantiates nothing; the `network.*` ones make
documented getter calls on the *workspace* the running instance holds, and
change nothing on it. A governed artifact carrying no privilege was denied the
root call of both on this build, in the official LIVE run; what an artifact
carrying `GET_NETWORK_INFO` gets back is what this run records.

### Where the statements are entered

The qualification entry point is the module's **Debug Dialog**, the part of the
Script Module editor of that name. A statement entered there is evaluated **in
that module's Script Engine** — the engine the saved artifact's files were
evaluated into when the module started — which is what makes a reading taken
there a reading *of the artifact* rather than of a second interpreter standing
in for it. `mcpDispatchV6` resolves there because `210_dispatcher_v6.js` defined it
there, in that evaluation.

Open it on the module under test, the one added from the saved
`dist/muejeje.pts`, and enter one call at a time, copying the whole answer back
before entering the next. Nothing else is used to issue a call: a reading taken
anywhere but this module's engine is evidence about that other surface.

Cisco documents the dialog on `scriptModules_scriptingInterface.htm`, a page the
v2 preflight inventory already pins by hash for other rows, and the exploratory
run brought its sentence back: *"Each Script Module has its own debug dialog
that accesses only the Script Module. Statements can be entered into the input
field, and they will be evaluated in the script engine."*
`tests/muejeje/test_cisco_reference.py` re-reads that sentence from the
installed page, as it does the Script Engine lifecycle ones, so a build that
words it differently fails there rather than here.

One statement at a time, each on one line. Anything **pasted** into a Packet
Tracer code editor loses its newlines, so a pasted statement must be a single
line and carry no `//` comment; the compiled engine files are imported rather
than pasted and are unaffected. `runtime.capabilities` answers with the whole
whitelist, so a run that starts with it needs no list from this document to
know what else to drive.

**First, that the dispatcher is there, and who it is.**

```javascript
typeof mcpDispatchV6
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-identify","op":"runtime.identify","args":{}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-capabilities","op":"runtime.capabilities","args":{}}')
```

**Then one refusal per class a request can provoke.** Each must come back
`ok: false` with exactly this `error.code`, and none of them reaches the
platform. A gate drives each through the kernel and holds the table to every
class; `ENGINE_EXCEPTION` is absent on purpose, because no request can provoke
it.

| Statement | `error.code` |
| --- | --- |
| `mcpDispatchV6('{not json')` | `MALFORMED_REQUEST` |
| `mcpDispatchV6('{"v":5,"operation_rid":"qual-refuse-protocol","op":"runtime.identify","args":{}}')` | `PROTOCOL_MISMATCH` |
| `mcpDispatchV6('{"v":6,"operation_rid":"qual-refuse-envelope","op":"runtime.identify"}')` | `INVALID_REQUEST` |
| `mcpDispatchV6('{"v":6,"operation_rid":"qual-refuse-operation","op":"runtime.unadmitted","args":{}}')` | `UNKNOWN_OPERATION` |
| `mcpDispatchV6('{"v":6,"operation_rid":"qual-refuse-domain","op":"network.device_identity","args":{"factory_index":0}}')` | `INVALID_ARGS` |

**Then stop the module, start it again, and ask who it is.** Record when each
happened: that record, and nothing the answers carry, is what separates the two
evaluations.

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-identify-restart","op":"runtime.identify","args":{}}')
```

**Then every other admitted operation.**

**Three of these carry an observed relay input, and every relay input below is
a placeholder.** Two are addresses in named domains — a `factory_index` in the
factory enumeration and a `workspace_index` in one workspace reading — and one,
`module_type`, is an opaque value the platform produced, relayed and never
interpreted. They are written below only so each statement is a complete,
admissible request: a gate drives every one of them through the kernel, and it
cannot drive a blank. **A placeholder is never entered.** A dependent statement
is entered only with the value the preceding reading actually published in this
run — a `factory_index` and a `module_type` from `platform.device_descriptors`
or `platform.module_descriptors`, a `workspace_index` that
`network.device_inventory` reported for the device the run means to read — and
one whose input was not published is not entered at all: it is accounted for as
`NOT_EXERCISED_PREREQUISITE_UNAVAILABLE`. Which descriptor to choose, what to do
when a reading publishes nothing, and what a mismatch does and does not
invalidate are in
[the minimum-privilege LIVE runbook](muejeje-pts-privilege-live-runbook.md).

The order below is therefore load-bearing: the reading that publishes a relay
input is driven before the statements that send it back.

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-descriptors","op":"platform.device_descriptors","args":{"factory_offset":0,"limit":4}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-modules","op":"platform.module_descriptors","args":{"factory_index":0}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-support","op":"platform.module_type_support","args":{"factory_index":0,"module_type":18}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-inventory","op":"network.device_inventory","args":{"workspace_offset":0,"limit":8}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-identity","op":"network.device_identity","args":{"workspace_index":0}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-ports","op":"network.device_ports","args":{"workspace_index":0,"limit":8}}')
```

The last three read the **workspace**, so what they report depends on what the
running instance holds — an empty workspace answering `available_count: 0`, a
position answering `device_present: false`, or a device answering
`port_count: 0`, is a reading, not a failure.
Record the workspace's state alongside them, because the same call on a
different session is a different observation (`MJ-002`).

**The last two must re-report the device they were meant to reach.** They read
`name` and `model` off the same hand-over they read everything else from, so
an identity that does not match the one the inventory published at that
position says the workspace moved between observations. Record
`WORKSPACE_ATTRIBUTION_UNSTABLE`: the cross-reading chain through that address
is not qualified, and each call's own answer still stands as an observation in
the reading that made it.

### What Packet Tracer prints beside an answer

**Record, beside every envelope, whatever Packet Tracer printed while that
statement ran** — verbatim, with where it appeared, and "nothing" when it
printed nothing. The runtime cannot see that output and never reports it, so an
envelope alone cannot say why a call did not return; a diagnostic recorded
beside it can, for that call. The exploratory run saw this for every
`platform.*` reading:

```text
IPC Call ERROR: IPC - ExApp or Script Module does not have the necessary privilege for IPC call "hardwareFactory"
```

and the same with `"network"` for every `network.*` reading.

**If a root call is denied for privilege again, record the diagnostic and keep
going through the rest of the list.** Every operation is still accounted for,
because a denied reading is still a reading: one that carries no relay input is
entered, and one whose input the denied reading could not publish is
`NOT_EXERCISED_PREREQUISITE_UNAVAILABLE` rather than entered with a placeholder.
None is entered twice.
Do not select another privilege and ask again: a module with a wider set is a
different recipe, so its answers would belong to an artifact this run did not
package. A root still denied while carrying `GET_NETWORK_INFO` is a
**contradiction between the binary evidence and the artifact's behaviour** — it
is recorded and investigated, never answered by adding privileges
(`MJ-032`, and [the privilege map](muejeje-pts-privilege-map.md)).

**If a root call now succeeds, continue through every operation below it in the
same run.** Each dependent one is entered with the relay input that root's
reading published, and accounted for otherwise. A deeper call that then fails
is a fact about that
`Interface.member`, not about the root privilege: record which member was
reached, and keep the root result and the descendant result apart.

The `platform.*` and `network.*` calls are the ones that reach Packet Tracer,
and **every outcome is a result worth recording verbatim**:

| `result.resolution` | `unavailable_reason` | What it establishes |
| --- | --- | --- |
| `UNAVAILABLE` | `PLATFORM_CALL_FAILED` | the member was called and the call did not return. It says nothing about *why* — the runtime cannot see that, and does not guess — so it is not a privilege reading by itself: only a diagnostic recorded beside it attributes a cause, and only for that call. The exploratory and the official `privileges: []` runs both did, for `IPC.hardwareFactory()` and `IPC.network()`; whether `GET_NETWORK_INFO` lifts that is what this run measures, and which member a *deeper* failure reached is recorded separately (`MJ-031`, `MJ-032`) |
| `UNAVAILABLE` | `PLATFORM_ABSENT` | there was no `ipc` object in the Script Engine at all. That would be a fact about the engine, not about privileges, and it needs recording as such |
| `UNAVAILABLE` | `PLATFORM_MEMBER_ABSENT` | the object was there and did not offer the member. Nothing was called, so this is a fact about the interface rather than about permission — record which member |
| `UNAVAILABLE` | `PLATFORM_ANSWER_UNUSABLE` | Packet Tracer answered and the answer could not be attributed. Record the whole envelope: this is the interesting failure |
| `OBSERVED` | `null` | the platform answered. Record the whole result verbatim — every descriptor, chassis node and workspace device it carries. For a `platform.*` reading this is the first real target evidence for `MJ-014`'s descriptor path from inside the artifact |

None of these readings is a verdict. Python decides what the run established,
from the recorded envelopes, outside the artifact (`MJ-011`).

Each returns a JSON **string** carrying
`{v, operation_rid, op, ok, result, error}`, with the `operation_rid` echoed
back unchanged and `error: null` on success.

**Record which start every envelope came from.** Cisco documents that every
engine file is evaluated when the module starts, so a stop and a start is a new
evaluation, and that evaluation generates a new correlation token (`MJ-023`).
Envelopes carrying the same token were observed in the same evaluation, and the
stop and start in step 4 is the one point where this run moves from one
evaluation to the next.

**Nothing here requires two evaluations to produce different tokens, and no
step compares them.** The token is a clock reading and a random draw, so the
kernel guarantees no uniqueness and could not detect a collision if one
happened: two tokens being unequal is not a uniqueness result, and it is not
what tells one evaluation from another. The operator's own record of when the
module was stopped and started is what does, and it is written down beside the
envelopes rather than derived from them.

Record every envelope verbatim, into this execution's own raw transcript — one
file per run, named by the artifact SHA-256 and the run's own `run_id`, opened
with a header of facts that exist before the first statement, append-only while
the run happens, preserved without normalizing or rewriting what came back, and
interpreted by the QA record afterwards rather than replaced by it. The
`d37ba37` run kept a summary instead, which is why it establishes packaging,
execution, lifecycle and the denial diagnostics and no result shape at all.

**The kernel's live state belongs to an artifact, not to the sources**: a green Node run establishes what our
JavaScript does and nothing about Packet Tracer's engine, which is a different
implementation (`MJ-015`). It was established once, for the artifact the
`d37ba37` run saved — `V6_KERNEL_VERIFIED = PASS` — and each new recipe id
identifies a different artifact, whose own kernel is unverified until this
exercise has been driven through it.

**Python decides what the run establishes.** The runtime reports observations
and certifies nothing about itself (`MJ-011`), so a qualification verdict is
never read out of the artifact's own answer.
