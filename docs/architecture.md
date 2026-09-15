# Architecture

Cisco-Muejeje follows a clean, hexagonal layout under `src/packet_tracer_mcp/`,
keeping domain logic independent of the MCP and Packet Tracer details.

```text
adapters/        MCP boundary
  mcp/           tool_registry.py · resource_registry.py
application/      use cases + DTOs
  use_cases/     plan_topology, validate_plan, fix_plan, full_build,
                 generate_configs, apply_acl, apply_nat, export_artifacts, …
domain/           pure business logic (no I/O)
  models/        TopologyPlan, ACLPlan, NAT, errors …
  rules/         cable_rules, device_rules, ip_rules, acl_rules, nat_rules
  services/      orchestrator, validator, auto_fixer, ip_planner, explainer, estimator,
                 topology_diff, security_audit, port_inspect, packet_trace
infrastructure/   adapters to the outside world
  catalog/       devices, cables, modules, aliases, templates
  generator/     ptbuilder_generator, cli_config_generator, acl/nat generators
  execution/     live_bridge, file_bridge, bridge_token, deploy_executor, manual_executor
  persistence/   project_repository (save/load projects)
```

## Enterprise E4 path

The Enterprise path adds a backend-neutral planning pipeline above the same
`TopologyPlan` contract:

```text
EnterpriseIntent -> EnterprisePlan -> HardwarePlan
                  -> EnterpriseCompiler (E4) -> concrete TopologyPlan
                  -> backend adapter -> Packet Tracer
```

E4 performs deterministic endpoint expansion, physical port and link allocation,
and hierarchical layout. Configuration remains a separate E5 concern. See
[`architecture/enterprise-compiler.md`](architecture/enterprise-compiler.md).

## Request flow

```text
LLM tool call
   │
adapters/mcp/tool_registry.py        ← validates args, orchestrates
   │
application/use_cases/*              ← pipeline steps
   │
domain/services/*  +  domain/rules/* ← planning, validation, IP assignment
   │
infrastructure/generator/*          ← Script Engine JavaScript + IOS CLI
   │
infrastructure/execution/{live_bridge,file_bridge} ← HTTP (:54321) or file mailbox
   │
MCP Control Center extension → PT Script Engine → Cisco Packet Tracer
```

## The live bridge

Two channels reach the extension; `_pick_channel()` selects one per command.

**HTTP** — `PTCommandBridge` (`live_bridge.py`) runs a small HTTP server on
`127.0.0.1:54321`, used while the extension window is open:

- `GET /next` — the Packet Tracer webview polls this for queued commands (token
  required).
- `POST /queue` — the MCP server enqueues a JavaScript command (token required).
- `POST /result` / `GET /result` — round-trips results back via `reportResult()`.
- `GET /ping` — unauthenticated identity check (fingerprint of the token only).

**File bridge** — `FileBridge` (`file_bridge.py`), used when the window is
closed. The Script Engine polls a mailbox under
`%LOCALAPPDATA%\packet-tracer-mcp\bridge\` (`req_*.js` → execute → `res_*.txt`,
plus an `alive.txt` heartbeat). It needs no token: a browser page cannot write a
user-owned local file. It provides neither exactly-once nor at-most-once
execution; see `TD-TRANSPORT-001` in
[`architecture/technical-debt.md`](architecture/technical-debt.md).

**Authentication** — the HTTP bridge requires a per-machine token
(`bridge_token.py`, generated under `%LOCALAPPDATA%`). The extension reads it
from disk through the Script Engine, so there is no pairing and nothing to
paste. See
[SECURITY.md](https://github.com/andres18113/cisco-muejeje/blob/main/SECURITY.md).

## PTBuilder as historical reference

The Script Engine helper layer that runs inside Packet Tracer was based on
[PTBuilder](https://github.com/kimmknight/PTBuilder) as a reference. The
extension, the MCP Control Center, is a separate build whose source is in
`EXTENSION/`. See [Credits & Attribution](credits.md).

## Trust model

`/queue` is the authenticated internal bridge endpoint. The default `enterprise`
MCP surface does not expose arbitrary JavaScript. `pt_send_raw` exists only when
the operator explicitly selects
`PT_MCP_PUBLIC_SURFACE=developer-capability-investigation`; it remains an untyped
compatibility tool rather than a normal enterprise operation. The token stops a
browser page from reaching `:54321`, and the file channel is confined to a
user-owned directory. Run the developer surface only on a machine, and against
topologies, that you trust.
