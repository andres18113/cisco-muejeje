# `muejeje_pts/` — owned source root

The source tree of the **Muejeje runtime** artifact (`dist/muejeje.pts`).

This tree is the artifact. Nothing here may carry a consumer's assumptions: no
CP LIVE, PoE, Router0, voice, VLAN or fixed-topology concept, and no reference
to any project that consumes Muejeje (`MJ-001`, `MJ-002`, `MJ-004`).

| Path | Packaged as |
| --- | --- |
| `script-engine/` | Script Engine files, evaluated in the order the Scripting Interface lists them, then `main()` |
| `interface/` | Custom Interface files, imported into the Custom Interfaces tab |
| `manifest/` | the build manifest — build metadata, **not** packaged |

`README.md` files are documentation and are **not** packaged; only the
extensions the build manifest declares as artifact inputs are.

## Relationship to `EXTENSION/`

`EXTENSION/**` is the legacy *MCP Control Center* extension. It keeps serving the
existing published `.pts` and is untouched by Muejeje. It is **not** a Muejeje
artifact input: sharing a source root is what stopped the owned artifact from
evolving independently, and `TODO-SRC-ROOT` resolved that by giving Muejeje this
tree instead.

No PTBuilder source is here, and none may be added. The legacy `main.js` was not
copied — its six PTBuilder globals are exactly what Muejeje must not inherit
(`MJ-013`).

## What is deliberately not here yet

`mcpDispatchV6`, `runtime.identify`, any operation, any transport. See
[the requirements baseline](../docs/architecture/muejeje-pts-requirements.md).
