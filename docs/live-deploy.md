# Live Deploy Setup

Live deploy sends commands to a running Packet Tracer instance, which creates the
devices, cables and configuration as each command executes.

There are two channels, and the server picks one per command:

```text
                                   ┌─ HTTP bridge (:54321) ──▶ extension webview ─┐
LLM ──▶ MCP Server (:39000) ──────►┤   (window OPEN)                             ├─▶ PT Script Engine
                                   └─ file mailbox (%LOCALAPPDATA%) ──▶ Script ──┘
                                       (window CLOSED)               Engine loop
```

- **HTTP** is used while the MCP Control Center window is open: the webview polls
  `:54321` and runs each command.
- The **file bridge** takes over when the window is closed but Packet Tracer is
  still open. The Script Engine has no `XMLHttpRequest` but can read files, so it
  polls a mailbox under `%LOCALAPPDATA%\packet-tracer-mcp\bridge\`
  (`req_*.js` → execute → `res_*.txt`). Packet Tracer keeps executing with the
  window minimised or closed.

`_pick_channel()` selects one channel per command, so a command is not queued on
both at once. That is a routing property, not a delivery guarantee: the file
bridge provides neither exactly-once nor at-most-once execution, because the
deployed Script Engine publishes no claim marker and a request that was read
cannot be distinguished from one that was never read. The limitation is recorded
as `TD-TRANSPORT-001` in the
[technical debt ledger](architecture/technical-debt.md).

| Port | Service | Purpose |
|------|---------|---------|
| 39000 | MCP server (streamable-http) | Receives tool calls from the MCP client |
| 54321 | HTTP bridge | Queues JavaScript commands while the extension window is open |

## Install the extension (one-time)

Live deploy uses the MCP Control Center Packet Tracer extension, a `.pts` script
module whose source is in `EXTENSION/`. No other extension is needed.

1. Obtain a compiled `.pts`, V5 or later. Cisco-Muejeje does not publish one.
   Build it from `EXTENSION/`, which needs the PTBuilder reference files
   described in `EXTENSION/script-engine/README.md`. The upstream project
   published `V5.2.pts` with its
   [releases](https://github.com/Mats2208/MCP-Packet-Tracer/releases).
2. In Packet Tracer, open **Extensions → Scripting → Configure PT Script
   Modules**.
3. Click **Add…**, select the `.pts`, and confirm.

The module is then registered.

## Use it (each session)

1. Open Cisco Packet Tracer 8.2 or later.
2. Open **Extensions → MCP BUILDER**. The MCP Control Center window appears.
3. It connects to the bridge and starts polling. There is no snippet to paste.

The MCP Control Center has the polling loop built in: it polls `:54321` every
500 ms and runs commands through the Script Engine. The Editor, Terminal, Status
and Quick Build tabs show what it is doing.

### Authentication

Since v0.6.0 the bridge requires a token unique to the machine. Without it, any
web page open while Packet Tracer is running could inject and execute code inside
it. The MCP server creates the token on first run and the extension reads it
through the Script Engine, so there is nothing to configure or paste.

If the Terminal tab reports that no token was found, start the MCP server once
and reopen the window. Extensions built before V5.0 cannot authenticate.

## Verify and deploy

```text
pt_bridge_status          # → "Bridge ACTIVE and CONNECTED"
pt_live_deploy(plan_json) # sends the topology to PT
pt_query_topology         # read back what is in PT
pt_export_topology        # full snapshot (positions, per-interface IPs, links)
```

## Troubleshooting

### `Extensions → MCP BUILDER` is missing

The extension is not registered yet. Repeat the install step
(**Extensions → Scripting → Configure PT Script Modules → Add…**) and select a
compiled `.pts`, V5 or later. See
[Install the extension](#install-the-extension-one-time).

### A red error popup appeared (`An error occurred on line N`)

A command raised inside the Script Engine. The Control Center's polling loop
lives in the webview, so it keeps running, but the popup blocks Packet Tracer's
UI until it is dismissed. Click **OK** and run the command again. The validated
tools (`pt_add_device`, `pt_add_link`, …) pre-check their inputs before sending.

### Packet Tracer becomes slow when the window is in the background

This is a QtWebEngine compositing limitation: when the webview is behind Packet
Tracer but not minimised, Chromium keeps rendering and competes for the GPU.
Minimising the MCP Control Center window stops its render pipeline. The upstream
project tracked this as
[Mats2208/MCP-Packet-Tracer#5](https://github.com/Mats2208/MCP-Packet-Tracer/issues/5).
