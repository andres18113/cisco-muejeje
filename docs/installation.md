# Installation

## Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | |
| `mcp[cli]` | ≥ 1.13, < 2 | Installed automatically |
| `pydantic` | ≥ 2.11, < 3 | Installed automatically |
| Cisco Packet Tracer | `9.0.1.0858` | Only for live deploy. That is the build every governed record in this repository was measured on; other builds are not qualified here |
| MCP Control Center extension | V5 or later | Packet Tracer extension (`.pts`), only for live deploy. Source in `EXTENSION/`; this repository publishes no compiled build — see [Live Deploy Setup](live-deploy.md) |

`pydantic` 2.11 or later is required. Current `mcp` releases build tool output
schemas from return annotations and need it; an older pydantic makes the server
fail on startup. The pinned dependencies handle this, so do not force an older
pydantic.

## Install the server

```bash
git clone https://github.com/andres18113/cisco-muejeje.git
cd cisco-muejeje
pip install -e .
```

After `pip install -e .`, the `packet_tracer_mcp` module is importable from any
directory, so `python -m packet_tracer_mcp --stdio` works from anywhere. There is
no need to change into the repository or keep a server running.

## Connect your MCP client

### Claude Code

Linux, macOS, Git Bash and Windows `cmd.exe`:

```bash
claude mcp add --scope user --transport stdio packet-tracer -- python -m packet_tracer_mcp --stdio
```

Windows PowerShell, with the `--` separator quoted:

```powershell
claude mcp add --scope user --transport stdio packet-tracer "--" python -m packet_tracer_mcp --stdio
```

In Windows PowerShell a bare `--` separator is consumed before it reaches the
`claude` CLI, so the following `-m` is treated as one of its own options and the
command aborts with `error: unknown option '-m'`. Quoting it as `"--"` passes it
through. The `cmd.exe` or Git Bash form above also works, as does wrapping the
whole command in `cmd /c "…"`.

Verify, in any shell:

```bash
claude mcp list
# packet-tracer: python -m packet_tracer_mcp --stdio - [OK] Connected
```

Remove it later with `claude mcp remove packet-tracer --scope user`.

### VS Code and Copilot

Add this to the MCP configuration (`.vscode/mcp.json` or user settings):

```json
{
  "servers": {
    "packet-tracer": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "packet_tracer_mcp", "--stdio"]
    }
  }
}
```

### Any other stdio client

```json
{
  "mcpServers": {
    "packet-tracer": {
      "command": "python",
      "args": ["-m", "packet_tracer_mcp", "--stdio"]
    }
  }
}
```

## Live deploy extension (optional)

To apply topologies to a running Packet Tracer, also install the MCP Control
Center extension:

1. Get a compiled `.pts`, V5 or later. Cisco-Muejeje does not publish one; build
   it from `EXTENSION/` (see `EXTENSION/script-engine/README.md`). The upstream
   project published `V5.2.pts` with its
   [releases](https://github.com/Mats2208/MCP-Packet-Tracer/releases).
2. In Packet Tracer: **Extensions → Scripting → Configure PT Script Modules →
   Add…**, select the `.pts`, and confirm.
3. Open **Extensions → MCP BUILDER**. It connects to the bridge.

Full walkthrough: [Live Deploy Setup](live-deploy.md).

## Transport modes

- **stdio**, recommended for desktop clients: the client spawns the server as a
  child process. The internal HTTP bridge to Packet Tracer (`:54321`) still
  starts inside that process, so live deploy works the same way.
- **streamable-http** (`http://127.0.0.1:39000/mcp`): start the server with
  `python -m packet_tracer_mcp` and let several clients share one instance.

On Windows, `python` must be on `PATH`. If the client cannot spawn the server,
put the full interpreter path in the `command` field, for example
`C:\\Users\\you\\AppData\\Local\\Programs\\Python\\Python312\\python.exe`.

Next: run the [Quick Start](quickstart.md) example.
