# Changelog

No Cisco-Muejeje release has been tagged. The package version in
`pyproject.toml` (`0.8.0`) is inherited from upstream and has not been changed.
This file keeps two histories apart: Cisco-Muejeje development since the fork
diverged from upstream, and the upstream release notes written before that.

## Cisco-Muejeje development (unreleased)

This covers the work since the divergence from upstream at `b075961`
(2026-07-31), starting with `aadbb94` (2026-08-02). It is a summary; the Git
history is the detailed record.

### CP-LIVE and runtime

- Governed CP-SCALE canonical LIVE targets for the three-site, 279-endpoint
  reference design
  ([cp-scale-qualification](docs/architecture/cp-scale-qualification.md)). Every
  canonical target is refused before Packet Tracer contact unless an explicit
  authorization names the target and the exact source SHA.
- `ROUTER0_BRANCH_VERIFIED_AND_CLEANED`, executed at `8980ada`, and
  `ROUTER3_BRANCH_VERIFIED_AND_CLEANED`, executed at `d2245d4`.
- `CP_SCALE_FULL_QUALIFICATION_VERIFIED_AND_CLEANED`, from run
  `canonical-cp-scale-voice-20260915T193037865890Z-6a80b24626d4`:
  - executed at `6a80b24626d40fb59bad5f0dc2e47d18a51f4a49`;
  - evidence promoted in `4206ee3`;
  - reconciled in `3b292ca`.

  The earlier full-qualification run, executed at `ff11765`, FAILED at `floor3`
  when the Packet Tracer process crashed, and it stays FAILED.
- A backend qualification policy for Packet Tracer `9.0.1.0858`. It qualifies
  voice configuration, phone registration and extension binding. Call behaviour
  and wireless association are unqualified, and intersite calling is off. The
  call-observability qualification attempt was BLOCKED (diagnostic only).
- Governed PoE observation episodes (POE-2 and POE-3A), with their immutable
  evidence under `docs/reference/cp-scale/`.
- Runtime qualifications on Packet Tracer `9.0.1.0858`:
  - RIPv2 replay safety and typed RIPv2 route exchange
    ([ripv2-runtime-qualification](docs/architecture/ripv2-runtime-qualification.md));
  - EIGRP on `1941`
    ([eigrp-runtime-qualification](docs/architecture/eigrp-runtime-qualification.md)).
- Runtime safety contracts:
  - import isolation proved in the process that mutates;
  - a typed registry of product mutation families;
  - a same-payload replay guard for module insertion;
  - the FileBridge containment that discharges branch B of `TD-TRANSPORT-001`.

### Enterprise pipeline

- Enterprise planning (E2), Packet Tracer capability discovery (E3.5), and
  hardware planning that consumes measured capability evidence.
- The Enterprise compiler (E4): endpoint expansion, physical port and link
  allocation, layout and serial WAN links.
- Typed configuration (E5), network services, voice, security policy and
  control-plane plans, applied and verified through the Packet Tracer runtime.
- Deployment manifests and execution contracts. E9.5 stabilization was closed at
  CP3-HARD ([e95-stabilization](docs/architecture/e95-stabilization.md)).

### MCP surface

- A governed public MCP surface. The default `enterprise` surface does not
  register `pt_send_raw`; `PT_MCP_PUBLIC_SURFACE=developer-capability-investigation`
  adds it.
- New tools: `pt_probe_capabilities`, `pt_capability_report` and
  `pt_compose_enterprise_reference`.

## Upstream heritage: Mats2208/MCP-Packet-Tracer

The entries below are release notes written by the upstream project,
[Mats2208/MCP-Packet-Tracer](https://github.com/Mats2208/MCP-Packet-Tracer),
before Cisco-Muejeje diverged. Their content and provenance are retained,
although some wording has been translated into English; they are not
Cisco-Muejeje releases. The tool counts, test counts and Packet Tracer version
they cite describe upstream at that time.

### 0.8.0

The server could build and inspect a network but could not show it. This
release closes that gap: the agent returns a diagram rather than a description.

**58 → 61 tools · 319 → 349 tests.** Verified against Packet Tracer 9.0.0.0810.

#### Added

- **`pt_screenshot`** — captures the logical canvas to a file and returns its
  path. It does not return the image itself: that would fill the model context
  with tens of thousands of bytes that cannot be inspected there. PNG is the
  default because it compressed the same canvas better than JPG (33 KB versus
  105 KB).
- **`pt_add_note`** — writes a note on the canvas, for example to label a
  subnet, mark an OSPF area, or name a trunk.
- **`pt_clear_annotations`** — removes notes and drawings. It never touches
  devices or links.

Together they support **self-documenting topologies**: build with
`pt_full_build`, label each subnet and link, then capture a diagram ready for a
class from a single prompt.

#### Known limitation

**There is no drawing tool.** Packet Tracer can draw lines and circles on the
canvas, but not usefully from an extension: the argument expected to set size
controlled stacking order instead—three circles requesting 60, 60, and 300 all
appeared at the same tiny size—and colors did not produce the requested value.
Rather than expose parameters that do not do what they say, annotation is
limited to text notes. Font size is likewise not configurable.

### 0.7.0

Until now the server could build a network but not look at one. It planned,
validated and deployed, and if the result misbehaved the model was blind — it
could redeploy and hope. This release adds the other half: reading the live
devices back, and explaining what they decided and why.

**46 → 58 tools · 188 → 319 tests.** Verified against Packet Tracer 9.0.0.0810.

#### Fixed

- **`pt_full_build(deploy=True)` now deploys.** It always went to the clipboard,
  so with the bridge connected it reported `Validation: PASS` and left the canvas
  empty — the main pipeline silently built nothing. It now deploys through the
  `pt_live_deploy` path (device and link verification, plus the reconcile pass
  for the devices PT drops) and falls back to the clipboard only when no channel
  exists.

#### Added — reading the live topology

- **`pt_audit_security`** — grades the effective configuration of every IOS
  device: missing `enable secret`, credentials stored reversibly, `service
  password-encryption` off, no local users, no MOTD banner, and a
  config-register left at `0x2142` (which discards the startup-config on the
  next reboot). Findings carry a severity and a suggested fix.
  Credentials never leave the device — only the algorithm label is transmitted,
  because a hash in a tool result ends up in the model's context and the client's
  logs.
- **`pt_inspect_ports`** — per-port line and protocol status, MAC, addressing,
  duplex, bandwidth, MTU, delay, CDP, DHCP-client state, NAT mode and applied
  ACLs. Flags cabled-but-down and line-up-protocol-down.
- **`pt_read_vlans`** — the switch's real VLAN database, separating your VLANs
  from the ones PT ships with.
- **`pt_device_power`** — power a device off and on with read-back, to simulate
  an outage or force a reboot.

#### Added — simulation

- **`pt_read_packet_trace`** — the simulation event list: per frame the path,
  the outcome, and **PT's own per-OSI-layer explanation of each decision**. A
  failing ping stops being "no reply" and becomes a cause, e.g. *"The next-hop IP
  address is not in the ARP table. The ARP process buffers this packet."*
- **`pt_simulation_mode`** / **`pt_simulation_step`** — switch between Realtime
  and Simulation, and move the event list forward, back or to the start.

#### Added — telemetry, QoS and backup

- **`pt_apply_netflow`** — create, reconfigure or remove a NetFlow exporter
  (collector address, UDP port, version, source interface, monitors) and read the
  result back. Reapplying a name reconfigures rather than duplicating.
- **`pt_read_qos`** — class-maps and policy-maps with their CLI form. Read-only:
  QoS cannot be created programmatically, so author it with IOS CLI and use this
  to confirm it landed.
- **`pt_backup_config`** — the device's real startup-config plus serial,
  config-register, boot images and uptime. Optional full XML dump.
- **`pt_project_metadata`** — saved filename, PT version, description and
  device/link count; flags a project that has never been saved.
- **`pt_workspace_options`** — auto-cabling (turn it off before a scripted build
  if you need links on exact interfaces) and access to the real network, plus the
  canvas labels that decide whether a screenshot is readable.

#### Improved

- **`pt_apply_interface_tuning`** gains `ospf_dead_interval` and OSPF
  authentication in both message-digest and plaintext form. The key is emitted
  before authentication is enabled — the other order leaves the interface
  demanding auth with nothing to answer and the adjacency drops. `dead <= hello`
  is rejected, since mismatched timers mean no adjacency forms at all.
- **`pt_set_port`** gains `zone_member` (Zone-Based Firewall), `proxy_arp` —
  turning it off is routine hardening, since a router answering ARPs that are not
  its own leaks topology — and `ike` for IPsec.

Both were extended rather than given their own tools: `pt_apply_interface_tuning`
already set the other OSPF knobs and `pt_set_port` already applied low-level port
attributes, so separate tools would have been mostly duplicate.

#### Known limitations

- **No `pt_send_pdu`.** Packet Tracer does not let an extension originate a
  packet the way the GUI's *Add Simple PDU* button does. Generate traffic with a
  real ping (`pt_verify_connectivity`) and then read the trace.
- **QoS is read-only.** Class-maps and policy-maps cannot be created through the
  API; author them with IOS CLI.
- **`zone_member` needs its zone to exist.** Setting it succeeds, but the
  interface line only appears once a matching `zone security` is configured.

### 0.6.0

- The live-deploy bridge authenticates with a per-machine token. Earlier versions
  had an unauthenticated bridge: any web page open while Packet Tracer was
  running could execute code inside it. **Requires the V5 extension.**
