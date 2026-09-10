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
| Script Engine files, **in this order** | `core.js`, `protocol_v6.js`, `validation_v6.js`, `runtime_capabilities.js`, `runtime_identity.js`, `dispatcher_v6.js`, `lifecycle.js` |

The engine order is the dependency direction, because *"all script files are
executed (evaluated) in the Script Engine in the same order as listed in the
Scripting Interface"*. Core first, then the protocol envelope and the admission
that refuses with it, then operations — alphabetically among themselves, since
they depend only on core and protocol — then dispatch, then the lifecycle that
may call all of it (`MJ-019`).

## Steps

1. Open Packet Tracer `9.0.1.0858`.
2. **Extensions → Scripting → New PT Script Module**. The editor opens with six
   parts: Info, General, Script Engine, Custom Interfaces, Data Store, Debug.
3. **General**: set the Module ID, set Startup to `On Startup`, and leave every
   privilege unselected. *"The security privileges indicate which IPC calls this
   Script Module can make. Calls to unselected privileges will be denied"* — the
   kernel makes no IPC call, so denying all of them changes nothing it does.
4. **Script Engine**: import the seven files in the order above. Import; do not
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
- `mcpDispatchV6` with `runtime.identify`;
- `mcpDispatchV6` with `runtime.capabilities`.

No topology is created, opened or modified; no device, link or configuration is
touched; no transport, bridge or HTTP endpoint is implemented or contacted. Both
operations are read-only and make no platform call, so a qualification run
changes nothing in Packet Tracer beyond starting and stopping a module.

The two calls, each on one line. Anything **pasted** into the Builder Code
Editor loses its newlines, so a pasted snippet must be a single line and carry
no `//` comment; the compiled engine files are imported rather than pasted and
are unaffected.

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-identify","op":"runtime.identify","args":{}}')
```

```javascript
mcpDispatchV6('{"v":6,"operation_rid":"qual-capabilities","op":"runtime.capabilities","args":{}}')
```

Each returns a JSON **string** carrying
`{v, operation_rid, op, ok, result, error}`, with the `operation_rid` echoed
back unchanged and `error: null` on success.

*Which* surface issues those calls is the operator's choice — the module editor
has a Debug part, and a consumer could call in another way. This repository has
no recorded evidence of the Debug part's exact behaviour, so no steps for it are
written here; a guessed UI step is the same defect as a guessed API signature
(`AGENTS.md` rule 6).

Record the two envelopes verbatim. Until that has happened on the pinned build,
the kernel's live state is `NOT_YET_LIVE_VERIFIED`: a green Node run establishes
what our JavaScript does and nothing about Packet Tracer's engine, which is a
different implementation (`MJ-015`).

**Python decides what the run establishes.** The runtime reports observations
and certifies nothing about itself (`MJ-011`), so a qualification verdict is
never read out of the artifact's own answer.
