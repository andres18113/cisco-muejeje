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
is inferred from a screenshot or from memory (`AGENTS.md` rule 6).

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
   non-null `build_recipe_id`, and `reference_inputs: []`.
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
| Privileges | none selected |
| Signing | none (`TODO-SIGNING` is open; an unsigned module is what this recipe produces) |
| Custom Interfaces | `muejeje_pts/interface/index.html` |
| Script Engine files | every file below, **in this order**, all from `muejeje_pts/script-engine/` |

1. `core.js`
2. `protocol_v6.js`
3. `validation_v6.js`
4. `arguments_v6.js`
5. `platform_reading.js`
6. `platform_adapter.js`
7. `network_adapter.js`
8. `network_identity_adapter.js`
9. `platform_device_adapter.js`
10. `platform_module_adapter.js`
11. `platform_support_adapter.js`
12. `network_identity.js`
13. `network_inventory.js`
14. `platform_discovery.js`
15. `platform_modules.js`
16. `platform_support.js`
17. `runtime_capabilities.js`
18. `runtime_identity.js`
19. `dispatcher_v6.js`
20. `lifecycle.js`

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

## Steps

1. Open Packet Tracer `9.0.1.0858`.
2. **Extensions → Scripting → New PT Script Module**. The editor opens with six
   parts: Info, General, Script Engine, Custom Interfaces, Data Store, Debug.
3. **General**: set the Module ID, set Startup to `On Startup`, and leave every
   privilege unselected. *"The security privileges indicate which IPC calls this
   Script Module can make. Calls to unselected privileges will be denied"*.

   **This is a deliberate, and consequential, choice.** The `runtime.*`
   operations make no IPC call, so nothing selected here changes what they do.
   The `platform.*` and `network.*` ones do make calls, and **what happens to
   them with nothing selected is exactly what this run is for**. Selecting a privilege would mean
   guessing which one the reading needs, and no evidence in this repository
   says (`MJ-032`); predicting the outcome would be the same guess in the other
   direction. Record whichever reading comes back — that observation is the
   point of the run.
4. **Script Engine**: import the engine files in the order above. Import; do not
   paste. Pasted source loses its newlines in the Builder Code Editor, and these
   files are ordinary multi-line JavaScript with comments.
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
| Packet Tracer build | `9.0.1.0858`, and its `PacketTracer.exe` hash |
| observed responses | the read-only exercise below |

## Read-only qualification

The artifact is exercised, never used to change anything. Import the saved
`.pts` on the pinned build, start it, and drive only:

- the module lifecycle — start, then stop;
- `mcpDispatchV6` once per operation `runtime.capabilities` reports, starting
  with `runtime.identify` and `runtime.capabilities` themselves.

Driving the list the runtime reports, rather than a list copied into this
document, is what keeps this procedure current when an operation is added
(`MJ-008`). The calls below cover every operation admitted today, and a gate
drives each one through the kernel and holds the set complete — an earlier
revision omitted one, and nothing noticed.

No topology is created, opened or modified; no device, link or configuration is
touched; no transport, bridge or HTTP endpoint is implemented or contacted.
Every admitted operation is read-only. The `runtime.*` ones make no platform
call at all; the `platform.*` ones make documented getter calls on the hardware
*factory*, which describes what models exist and instantiates nothing; the
`network.*` ones make documented getter calls on the *workspace* the running
instance holds, and change nothing on it. What a module carrying no privilege
gets back from them is unknown until this run answers it.

One call per admitted operation, each on one line. Anything **pasted** into
the Builder Code Editor loses its newlines, so a pasted snippet must be a
single line and carry no `//` comment; the compiled engine files are imported
rather than pasted and are unaffected. `runtime.capabilities` answers with the
whole whitelist, so a run that starts with it needs no list from this document
to know what else to drive.

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-identify","op":"runtime.identify","args":{}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-capabilities","op":"runtime.capabilities","args":{}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-descriptors","op":"platform.device_descriptors","args":{"offset":0,"limit":4}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-modules","op":"platform.module_descriptors","args":{"device_index":0}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-support","op":"platform.module_type_support","args":{"device_index":0,"module_type":18}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-inventory","op":"network.device_inventory","args":{"offset":0,"limit":8}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-identity","op":"network.device_identity","args":{"device_index":0}}')
```

The last two read the **workspace**, so what they report depends on what the
running instance holds — an empty workspace answering `available_count: 0`, or
a position answering `device_present: false`, is a reading, not a failure.
Record the workspace's state alongside them, because the same call on a
different session is a different observation (`MJ-002`).

The `platform.*` and `network.*` calls are the ones that reach Packet Tracer,
and **every outcome is a result worth recording verbatim**:

| `result.resolution` | `unavailable_reason` | What it establishes |
| --- | --- | --- |
| `UNAVAILABLE` | `PLATFORM_CALL_FAILED` | the member was called and the call did not return. It says nothing about *why* — the runtime cannot see that, and does not guess. In particular it is not a privilege reading: which privilege these calls need, and what a target does without one, are both unmeasured here (`MJ-031`, `MJ-032`) |
| `UNAVAILABLE` | `PLATFORM_ABSENT` | there was no `ipc` object in the Script Engine at all. That would be a fact about the engine, not about privileges, and it needs recording as such |
| `UNAVAILABLE` | `PLATFORM_MEMBER_ABSENT` | the object was there and did not offer the member. Nothing was called, so this is a fact about the interface rather than about permission — record which member |
| `UNAVAILABLE` | `PLATFORM_ANSWER_UNUSABLE` | Packet Tracer answered and the answer could not be attributed. Record the whole envelope: this is the interesting failure |
| `OBSERVED` | `null` | the platform answered. Record the whole result verbatim — every descriptor, chassis node and workspace device it carries. For a `platform.*` reading this is the first real target evidence for `MJ-014`'s descriptor path from inside the artifact |

None of these readings is a verdict. Python decides what the run established,
from the recorded envelopes, outside the artifact (`MJ-011`).

Each returns a JSON **string** carrying
`{v, operation_rid, op, ok, result, error}`, with the `operation_rid` echoed
back unchanged and `error: null` on success.

**Record every envelope from one start.** Cisco documents that every engine
file is evaluated when the module starts, so a stop and a start is a new
evaluation and the `runtime_session_id` will differ (`MJ-023`). Envelopes
carrying the same token were observed in the same evaluation; two carrying
different tokens say the module was restarted between them, which is a
different observation and must be written down as one.

*Which* surface issues those calls is the operator's choice — the module editor
has a Debug part, and a consumer could call in another way. This repository has
no recorded evidence of the Debug part's exact behaviour, so no steps for it are
written here; a guessed UI step is the same defect as a guessed API signature
(`AGENTS.md` rule 6).

Record every envelope verbatim. Until that has happened on the pinned build,
the kernel's live state is `NOT_YET_LIVE_VERIFIED`: a green Node run establishes
what our JavaScript does and nothing about Packet Tracer's engine, which is a
different implementation (`MJ-015`).

**Python decides what the run establishes.** The runtime reports observations
and certifies nothing about itself (`MJ-011`), so a qualification verdict is
never read out of the artifact's own answer.
