# MCP Tools

This page is the reference for the tools the server registers, grouped by
purpose. The default `enterprise` public surface registers every tool listed
here except `pt_send_raw`, which is registered only when the server starts with
`PT_MCP_PUBLIC_SURFACE=developer-capability-investigation`. The
`pt://capabilities` resource reports the active surface at runtime.

Tools that touch a running Packet Tracer require the
[live bridge](live-deploy.md) to be connected.

Discovery comes first: call `pt_list_devices`, and `pt_list_modules` before
installing expansion cards, so that model names, ports and cables come from the
catalog rather than from guesswork. Most NAT, ACL and module tools accept
`dry_run=True` to preview the generated CLI or JavaScript without touching
Packet Tracer.

## Catalog & discovery

| Tool | What it does |
|------|--------------|
| `pt_list_devices` | List the device models with their exact ports and aliases. |
| `pt_get_device_details` | Ports and details for one model (accepts a model name or alias). |
| `pt_list_templates` | List the topology templates and their defaults. |
| `pt_list_modules` | List expansion modules; optional `router_model` or `category` filter. |
| `pt_list_projects` | List saved projects under the exports directory. |

## Capability discovery

These two read and produce the E3.5 capability evidence that hardware planning
consumes. See
[Packet Tracer Capability Discovery](architecture/packet-tracer-capability-discovery.md)
and [Capability Probes QA](qa/capability-probes.md).

| Tool | What it does |
|------|--------------|
| `pt_probe_capabilities` | Discover capabilities using isolated, auto-cleaned temporary devices. It creates only devices prefixed `__MCP_PROBE_`, never modifies existing devices and never saves the `.pkt`. It runs registered internal probes only, and accepts no user JavaScript or IOS. Evidence is scoped to the Packet Tracer version given or detected. |
| `pt_capability_report` | Read stored capability evidence without touching Packet Tracer. `report` accepts `summary`, `model`, `unknown`, `readiness` and `catalog_gaps`. |

## Planning

| Tool | What it does |
|------|--------------|
| `pt_plan_topology` | Generate a full `TopologyPlan` (devices, links, IPs, routing, DHCP). |
| `pt_estimate_plan` | Fast dry-run: device, link and subnet counts and complexity, without a full plan. |
| `pt_validate_plan` | Validate a plan; returns typed errors and warnings. |
| `pt_fix_plan` | Auto-fix a plan (cables, port reassignment, model upgrades). |
| `pt_explain_plan` | Explain the plan's design choices in natural language. |
| `pt_compose_enterprise_reference` | Compose the Enterprise reference flow offline from an `intent_json`, without contacting Packet Tracer. |

## Generation & export

| Tool | What it does |
|------|--------------|
| `pt_generate_script` | Emit the Script Engine JavaScript (`lwAddDevice`/`lwAddLink`/…). |
| `pt_generate_configs` | Emit IOS CLI configuration for every router and switch, plus host settings. |
| `pt_export` | Write script, per-device configuration and plan JSON to `projects/<name>/`. |
| `pt_load_project` | Load a previously saved project's plan. |
| `pt_full_build` | One-shot pipeline: plan, validate, generate, explain, optionally deploy. |
| `pt_deploy` | Copy the generated JavaScript to the clipboard and export the files. |

## Live bridge

The bridge has two channels and picks one per command: HTTP while the MCP Control
Center window is open, and the file bridge, where the Script Engine reads a
mailbox under `%LOCALAPPDATA%`, when the window is closed but Packet Tracer is
still open. Every tool below works over either. See
[Live deploy](live-deploy.md).

| Tool | What it does |
|------|--------------|
| `pt_bridge_status` | Which channel is connected (HTTP, file bridge, or both). |
| `pt_live_deploy` | Send a plan to a running Packet Tracer (devices, links, configuration). |
| `pt_query_topology` | List devices currently in Packet Tracer with ports and per-port IPs. |
| `pt_export_topology` | Full snapshot: positions, per-interface IPs, links, cable information. |
| `pt_save_project` | Save the running topology as a real `.pkt` file. |
| `pt_open_project` | Open a `.pkt` in Packet Tracer, replacing the current topology. |

### Developer capability-investigation surface

The default `enterprise` surface does not register `pt_send_raw` and does not
advertise raw IOS or JavaScript as an enterprise capability. For controlled IPC
investigation, set `PT_MCP_PUBLIC_SURFACE=developer-capability-investigation`
before starting the server. That explicit opt-in preserves the legacy
`pt_send_raw(js_code, wait_result=False)` name and signature. It does not make
arbitrary code typed, replay-safe, or suitable for normal enterprise operation.

## Live editing

| Tool | What it does |
|------|--------------|
| `pt_add_device` | Add one device (validates name, model, and duplicates). |
| `pt_add_link` | Link two devices; validates that ports are free; infers the cable if omitted. |
| `pt_delete_link` | Remove the link on a given interface. |
| `pt_delete_device` | Delete a device (via `getLogicalWorkspace().removeDevice()`). |
| `pt_rename_device` | Rename a device. |
| `pt_move_device` | Move a device to new canvas coordinates. |
| `pt_set_port` | Low-level port attributes (bandwidth, duplex, description, MAC, power). |
| `pt_add_module` | Install one expansion module, with an automatic power cycle. |
| `pt_install_modules_batch` | Install several modules in one power cycle. |

## NAT & ACL

| Tool | What it does |
|------|--------------|
| `pt_apply_nat` | Apply NAT or PAT (`static`, `dynamic`, `pat`) on a live router. |
| `pt_remove_nat` | Remove a NAT or PAT configuration. |
| `pt_apply_acl` | Build, validate and apply a standard, extended or named ACL via CLI. |
| `pt_apply_acl_object` | The same, through Packet Tracer's ACL object API. |
| `pt_remove_acl` | Remove an ACL, and unbind it, via CLI. |
| `pt_remove_acl_object` | Remove an ACL through the object API. |

## Switching, security & tuning

| Tool | What it does |
|------|--------------|
| `pt_apply_vlan` | VLANs, access ports, trunks and router `.1q` subinterfaces for inter-VLAN routing. |
| `pt_apply_stp` | Spanning-tree mode, root primary, per-VLAN priority, portfast, BPDU guard. |
| `pt_apply_port_security` | Port security: maximum MACs, sticky or static MACs, violation action. |
| `pt_apply_hardening` | Hostname, banner, enable secret, local users, SSH (RSA keys and vty), password encryption. |
| `pt_apply_interface_tuning` | Serial clock rate (DCE), bandwidth, per-interface OSPF and EIGRP settings. |

All of them accept `dry_run=True` to preview the generated CLI without touching
Packet Tracer.

## Verification

| Tool | What it does |
|------|--------------|
| `pt_diff` | Compare a plan against the live topology (missing or extra devices, IP mismatches). |
| `pt_health_check` | Sweep the live topology: down links, cabled-without-IP, duplicate IPs. |
| `pt_verify_connectivity` | Run a ping from a device's console and parse the result. |

## Enterprise services

| Tool | What it does |
|------|--------------|
| `pt_apply_enterprise_services` | Apply governed Server-PT services for selected clients against a deployment `pt_live_deploy` already produced. DNS/HTTP use the documentary baseline; native DHCP has an exact-build, policy-scoped recorded binding. Mail and generic DHCP remain UNKNOWN. |

```text
pt_apply_enterprise_services(
    intent_json: str,
    deployment_id: str,
    packet_tracer_version: str,
    run_label: str = "",
) -> JSON
```

It does not deploy a topology and it does not delete anything of yours. It also
does not clean up when it finishes: the only thing it releases is the temporary
background clients its own verification created, and it reports the outcome of
every one of those releases, including the ones that did not resolve.

**Supported path.** One site, one segment, a static Server-PT and wired PC-PT
clients whose required access-port foundations terminate on one access switch.
The accepted DNS/HTTP baseline uses static clients. S3 also compiles a
same-segment delegated DHCP candidate with a mode-only E5 bootstrap; relay,
routed, wireless, foreign-site and ungoverned inter-switch paths are refused.

**Inputs.**

- `intent_json` — an `EnterpriseIntent` as JSON, carrying the requested
  services. A DNS service must declare an explicit `address`; there is no
  inference from whatever the host is later assigned.
- `deployment_id` — the verified physical deployment to bind to.
- `packet_tracer_version` — the exact build. It must equal the manifest's, and
  separately the *current* environment fingerprint is validated against the
  manifest, because a caller string agreeing with a stored string is not an
  observation of anything.
- `run_label` — display metadata. It never chooses a file and never overwrites
  another run.

**What it refuses, before touching anything.** An unparseable intent (which
reaches no bridge at all), an unknown or unreadable deployment, a version
mismatch, a process that is not the isolated live one, no available channel, an
unwritable run record, a DNS service with no address or two DNS services that
disagree, a composed identity that is not the deployed one, a changed
environment fingerprint, a required service whose operations are not authorized
on this build, an endpoint that already carries a different address, and an
endpoint whose current address could not be read — unknown is not empty.

**What it returns.** Per service and **per client** results, each check with its
observation, cause, claim level and limitations; the E5 scope it actually
applied (`mutated`, `retained`, `excluded`); whether an E5 effect is uncertain;
the owned-resource releases; the last durable stage and the path of the
persisted record; and the provenance of every capability it used.

**Three kinds of uncertainty are kept apart**, and the response says each one
separately:

| Field | What it answers |
|-------|-----------------|
| `status`, per-client `status` | Did the service work for this client? |
| `e5_effect_uncertain` | Is it known whether a mutation this run dispatched actually happened? |
| `dirty_state` | Is it known what else changed? |

A run can be `verified` while `dirty_state` is `unknown`. Adding a DNS record is
observed only within the record it wanted, so what else the table may hold is
not something this run measured, and it says so rather than reporting a clean
result it cannot support.

**Persistence.** Each run writes `data/services/<deployment_id>/<run_id>.json`
before the first effect and rewrites it at every stage boundary; refusals that
never bound a deployment go to `data/services/_admission/`. The record holds the
full typed E5 and E6 results, not counts. Only stage boundaries are durable, so
an interrupted record tells you which stage was last written — it is never proof
that the work inside that stage did not execute, and it is never resumed
automatically.

**Capability provenance.** Every DNS and HTTP capability this tool uses is
`documentary_baseline`: read from Cisco's reference and from controlled process
probes, not from a recorded run of this code against Packet Tracer. Every
response carries `provenance:documentary_baseline` in `limitations`. The tool is
offline verified; it has no LIVE acceptance record yet, and a capability is
promoted only by a committed record naming the build, the executed tree SHA, the
transport, the target model and the run id. `CLIENT_DNS_SERVER` is compiled as
an advisory per-client reader, always optional and always `unknown`: it gates
nothing and is never inferred from another getter.

**Mail (SMTP/POP3) is accepted in the intent and never executed on this
build.** An `smtp` service carries `domain_name`, `email_accounts` (a
`username` and an opaque `secret_ref` each), `email_clients`, optional
`email_pairs` and `verification_mode`; a `pop3` service on the same host adds
its enable and retrieval rows. Every mail operation is `unknown` in the
capability catalog, so a required mail service is refused before the first
effect (`service_ineligible`) and an optional one is excluded and reported per
selected client. No argument or catalog override exists to change that. The
candidate runtime behind it -- credential references resolved from
`PT_MCP_SECRET_<REF>` on the HTTP channel only, a pre-effect claim per client,
mailbox presence as supporting evidence only, and no send or retrieval event
observed -- is described in the
[E6 architecture](architecture/enterprise-services.md#mail-under-the-event-fallback).

**Scoped native Server-PT DHCP.** A `dhcp` service names the canonical
`host_device_id`, `segment_id` and selected wired PC-PT clients, sets
`verification_mode` to `state_only`, and leaves `dhcp_pool.pool_name` empty.
The exact-build 9.0.1.0858 binding uses Server-PT `FastEthernet0` and the
physical `serverPool` on `192.0.2.0/24`, with server/DNS `192.0.2.10`, gateway
`192.0.2.1`, and only those two singleton exclusions. The requested
`start_offset` from 99 through 150 must derive a contiguous lease window
starting at `.100` through `.151` and ending no later than `.152`;
`max_users` is one or two and
at least the selected client count. The file channel is required. These are
admission limits, not addresses injected into clients: each run reads back
the requested physical policy and attributes two stable samples per selected
client to exact IP/MAC/interface rows before dependent HTTP begins. One PC
requires no inactive second PC; real competing clients are checked.

Named pools, other networks/builds, masks, gateways, DNS values, exclusions,
capacities, acquisition modes and channels remain UNKNOWN or outside scope
and are refused before E5. The public four-input tool has no override. A
positive native state establishes usable attributed addressing, not explicit
`dhcpRun` causality, renewal, table-end proof or thousand-client native
capacity. The measured sample and evidence limits are in the
[E6 architecture](architecture/enterprise-services.md#server-pt-dhcp-under-the-event-fallback).

## Live-state inspection

These read the device rather than the plan, which is what makes them useful to
confirm that a change landed, or to inspect a topology built elsewhere. They were
verified against Packet Tracer `9.0.0.0810` when they were added upstream.

| Tool | What it does |
|------|--------------|
| `pt_audit_security` | Security posture of every IOS device, graded high, medium or low: missing `enable secret`, reversibly stored credentials (type 7), `service password-encryption` off, no local users, no MOTD banner, config-register left at `0x2142`. |
| `pt_inspect_ports` | Per-port line and protocol status, MAC, IP, duplex, bandwidth, MTU, delay, CDP, DHCP client, NAT mode and applied ACLs. Flags cabled-but-down and line-up-protocol-down. |
| `pt_read_vlans` | The switch's VLAN database, separating configured VLANs from the factory ones (1, 1002-1005). |
| `pt_device_power` | Power a device off and on with read-back, to simulate an outage or force a reboot. |

`pt_audit_security` never returns credentials. Passwords and hashes do not leave
the device: the reader classifies each credential by its prefix and transmits
only the algorithm label (`md5`, `type7`, `scrypt`, …), which is enough to audit
without putting a hash into the model's context or the client's logs.

## Canvas: capture & annotations

| Tool | What it does |
|------|--------------|
| `pt_screenshot` | Capture the logical canvas to an image file and return its path. |
| `pt_add_note` | Write a text note on the canvas, for example to label a subnet or name a trunk. |
| `pt_clear_annotations` | Remove notes and drawings. It never touches devices or links. |

The three combine into a documented topology: build with `pt_full_build`, label
each subnet and link with `pt_add_note`, then capture with `pt_screenshot`.

`pt_screenshot` returns a path, not the image. A capture runs to tens of
thousands of bytes, and returning it inline would fill the model's context with
data that cannot be read, so the file is written to disk and only its path comes
back. PNG is the default because it compresses a line diagram far better than
JPG: measured on the same canvas, 33 KB against 105 KB.

There is no drawing tool. Packet Tracer can draw lines and circles on the canvas,
but not usefully from an extension: the size argument turned out to control
stacking order rather than radius or thickness — three circles asking for 60, 60
and 300 all came out the same small size — and the colour arguments do not
produce the colour requested. Rather than expose parameters that do not do what
they say, annotation is limited to text notes.

## Backup & workspace

| Tool | What it does |
|------|--------------|
| `pt_backup_config` | The device's startup configuration, the one it rereads on reboot, plus serial, config-register, boot images and uptime. `include_xml=True` adds the full device dump. |
| `pt_project_metadata` | The open project's saved filename, the Packet Tracer version that wrote it, its description and the device and link count. Pass `description` to set it. |
| `pt_workspace_options` | Read or toggle workspace behaviour: auto-cabling, access to the real network, and the canvas labels that decide whether a screenshot is readable. |

Turn auto-cabling off before a scripted build. With auto-cabling on, Packet
Tracer picks the cable and the port. To place a link on an exact interface, call
`pt_workspace_options(auto_cabling=0)` first.

## Telemetry & QoS

| Tool | What it does |
|------|--------------|
| `pt_apply_netflow` | Create, reconfigure or remove a NetFlow exporter on a router — collector address, UDP port, version, source interface, monitors — and read the result back. |
| `pt_read_qos` | Read the device's class-maps and policy-maps, including each one's CLI form and the features a policy uses (bandwidth, priority, shaping, fair-queue). |

The two are not symmetric. `pt_apply_netflow` configures the exporter directly
and verifies the result, with no CLI involved. QoS can be read but not created on
the enterprise surface: `pt_read_qos` verifies a policy applied through a
separately governed process, and is not a raw CLI authoring path.

## Simulation

Packet Tracer's Simulation mode holds packets in an event list instead of moving
them in real time, which is what makes a step-by-step trace possible.

| Tool | What it does |
|------|--------------|
| `pt_simulation_mode` | Switch between Realtime and Simulation. |
| `pt_simulation_step` | Advance, rewind or reset the simulation (`forward`, `back`, `reset`). |
| `pt_read_packet_trace` | Read the event list: per frame the device, ingress and egress port, source, destination, traffic type and outcome, plus Packet Tracer's own per-OSI-layer explanation of each decision. |

The decision log is the same text Packet Tracer shows in its PDU Details pane, so
a failing ping reports a cause rather than only a symptom:

```text
L3 :: The destination IP address is in the same subnet. The device sets the next-hop to destination.
L2 :: The next-hop IP address is not in the ARP table. The ARP process tries to
      send an ARP request for that IP address and buffers this packet.
```

There is no `pt_send_pdu`. Packet Tracer does not let an extension originate a
packet the way the GUI's *Add Simple PDU* button does. Generate traffic the way a
user would, with `pt_verify_connectivity`, and then read the trace.

## Build flags

`pt_plan_topology` and `pt_full_build` accept `vlans` (router-on-a-stick VLAN
count), `dual_stack` (IPv6: routers via CLI, hosts via SLAAC), `ipv6_base`, and
`wireless_laptops` (Laptop-PT with a wireless NIC and an access point). Wireless
association is not qualified; see
[Switching, IPv6 & Wireless](advanced-features.md).

## Cable types for `pt_add_link`

Valid values: `straight`, `cross`, `serial`, `fiber`, `console`, `roll`, `phone`,
`coaxial`, `auto`, `usb`. Aliases: `crossover` → `cross`, `rollover` → `roll`.
Omit `cable_type` to infer it from the device categories. The full list is in
[Cable Types](cables.md).
