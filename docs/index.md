# Cisco-Muejeje

Cisco-Muejeje is a [Model Context Protocol](https://modelcontextprotocol.io)
(MCP) server for Cisco Packet Tracer. It builds typed network plans and validates
them. It generates Packet Tracer Script Engine JavaScript and IOS configuration,
applies both to a running Packet Tracer through a local bridge, and reads the
result back.

The project started as a fork of
[Mats2208/MCP-Packet-Tracer](https://github.com/Mats2208/MCP-Packet-Tracer); see
[Credits & Attribution](credits.md).

- [Installation](installation.md): install the server and register it with an MCP client.
- [Live Deploy Setup](live-deploy.md): connect a running Packet Tracer through the bridge.
- [MCP Tools](tools.md): tool reference.
- [Architecture](architecture.md): layers, planning paths and the bridge.

## Capabilities

| Area | Scope |
|---|---|
| Planning | `TopologyPlan` from structured parameters; the Enterprise path compiles `EnterpriseIntent` through hardware planning into a concrete plan |
| IP addressing | /24 LANs and /30 links for classic plans; VLSM and IPAM with capacity planning on the Enterprise path |
| DHCP | One pool per LAN, gateway excluded |
| Routing | Static, OSPF, EIGRP, RIP |
| Switching | VLANs, trunks, inter-VLAN routing, STP, port-security |
| IPv6 | Dual-stack addressing; routers via CLI, hosts via SLAAC |
| Wireless | Laptops with wireless NICs and access points |
| Validation | Typed error codes and an auto-fixer |
| ACL, NAT, hardening | Generated and applied to live devices through the bridge |
| Verification | Plan-versus-live diff, health check, live configuration audit, port inspection, packet trace reading |
| Deploy | HTTP bridge while the extension window is open, file bridge while it is closed |
| Export | Plans, scripts and CLI configuration on disk |

Which of these are qualified against a real Packet Tracer, and on which build, is
recorded in the architecture and qualification pages. The operational authority
for the CP-LIVE state is `docs/reference/cp-scale/current_state.json`; the
repository README summarises it.

## Pipeline

```text
MCP client
        │  MCP tools
   Cisco-Muejeje MCP server   (:39000 or stdio)
        │  HTTP bridge (:54321, window open)  ·  file bridge (window closed)
   MCP Control Center extension
        │  Script Engine
   Cisco Packet Tracer
   ── devices created
   ── cables connected
   ── IOS configuration applied
```

## Where to start

Read [Installation](installation.md), run the [Quick Start](quickstart.md)
example, then set up [Live Deploy](live-deploy.md) to apply plans to a running
Packet Tracer.

## The extension and PTBuilder

Live deploy uses the MCP Control Center extension, whose source is in
`EXTENSION/` in the repository. Its Script Engine helper layer was originally
based on [PTBuilder](https://github.com/kimmknight/PTBuilder). The two are
separate projects; see [Credits & Attribution](credits.md).
