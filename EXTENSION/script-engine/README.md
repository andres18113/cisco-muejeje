# script-engine — Packet Tracer script-engine side of the extension

This folder is the **script-engine half** of the *MCP Control Center* Packet
Tracer extension (the `.pts` distributed via
[Releases](https://github.com/Mats2208/MCP-Packet-Tracer/releases/latest)). The
other half is the webview UI in [`../webview/`](../webview/).

## What's tracked here, and why only `main.js`

| File | Origin | Tracked in git? |
| --- | --- | --- |
| `main.js` | **This project.** Bridge bootstrap, token read (`getMcpToken`), the file-bridge loop, and `installMcpHelpers()`. | **Yes** |
| `userfunctions.js`, `devices.js`, `links.js`, `modules.js`, `runcode.js`, `windows.js` | Reference copies of **[PTBuilder](https://github.com/kimmknight/PTBuilder)**'s script engine, by Kim Knight. | No — see below |

PTBuilder is credited as the starting point in the
[main README](../../README.md#credits--acknowledgements) and
[docs/credits](https://mats2208.github.io/MCP-Packet-Tracer/credits/). Its
repository carries **no license**, so those files are not redistributed from this
repository. They are `.gitignore`d on purpose (`EXTENSION/script-engine/*.js`
except `main.js`).

## Building the `.pts`

To compile **this** extension you need the PTBuilder reference files alongside
`main.js`. Get them from [PTBuilder](https://github.com/kimmknight/PTBuilder),
place them in this folder, and package with the webview UI from `../webview/`.
The published `.pts` in Releases is the ready-to-install build.

## Muejeje and PTBuilder

Muejeje (`dist/muejeje.pts`, a separate owned artifact — this `.pts` is never
replaced automatically) does **not** take PTBuilder as a build input: its
manifest selects no reference inputs and `tools/build_muejeje_pts.py --check`
has no PTBuilder prerequisite.

That is a statement about the build, not about the runtime. The tracked sources
still call six globals that PTBuilder's script engine supplies today —
`htmlWindow`, `runCode`, `configureIosDevice`, `allModuleTypes`, `addDevice` and
`addLink` — so the attribution above stays until each one is replaced. The
per-symbol evidence, the owned alternatives (`webViewManager.createWebView`, the
native `getCommandLine()` terminal, Cisco module descriptors) and the decisions
each replacement needs are recorded in
[the v2 preflight inventory](../../docs/qa/muejeje-pts-v2-preflight-inventory.md).

## How it runs

`main.js`'s `main()` runs whenever Packet Tracer is open (the module registers
the **Extensions → MCP BUILDER** menu). It:

1. installs the improved helpers (`installMcpHelpers` — `lwAddDevice`, `lwAddLink`,
   `configurePcIp`, `configurePcIpv6`, `swapLaptopToWireless`, `addModule`);
2. shows the webview window (HTTP polling lives there);
3. starts the file-bridge loop, which runs **with the window closed** — it reads
   commands from `%LOCALAPPDATA%\packet-tracer-mcp\bridge\` and executes them in
   the script engine.

The script engine can read/write files (`ipc.systemFileManager`) but has no
`XMLHttpRequest`, which is exactly why the file channel lives here and the HTTP
channel lives in the webview.
