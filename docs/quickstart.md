# Quick Start

Once the [MCP client is connected](installation.md), the model in that client
calls the server's tools for each request.

Discovery comes first. The server instructs the client to call `pt_list_devices`,
and `pt_list_modules` before installing expansion cards, so that model names,
ports and cables come from the catalog instead of being guessed. See the
[tool reference](tools.md).

## Example request

> "Build a network with 2 routers, 2 switches, 4 PCs, DHCP and static routing."

The model calls `pt_full_build`, which runs the pipeline — plan, validate,
generate, explain, estimate — and returns a summary:

```text
Devices (8):  R1, R2 (2911), SW1, SW2 (2960-24TT), PC1..PC4 (PC-PT)
Links   (7):  R1<->R2 (cross), R1<->SW1 (straight), R2<->SW2 (straight),
              SW1<->PC1, SW1<->PC2, SW2<->PC3, SW2<->PC4 (straight)

IP Plan:
  LAN 1:  192.168.0.0/24 -- R1 Gig0/1: .1, PC1: .2, PC2: .3
  LAN 2:  192.168.1.0/24 -- R2 Gig0/1: .1, PC3: .2, PC4: .3
  Link:   10.0.0.0/30    -- R1 Gig0/0: .1, R2 Gig0/0: .2

DHCP:   Pools on R1 and R2
Routes: Bidirectional static routes
```

## Recommended flow

For a new topology:

```text
pt_list_devices → pt_plan_topology → pt_validate_plan → pt_live_deploy
```

The one-shot equivalent:

```text
pt_full_build        # plan + validate + generate + (optional) deploy
```

To edit a topology already open in Packet Tracer:

```text
pt_bridge_status → pt_query_topology → pt_add_device / pt_add_link /
                                        pt_rename_device / pt_move_device /
                                        pt_delete_link / pt_delete_device
```

To check a deployment afterwards:

```text
pt_verify_connectivity(from_device, to_ip)   # real ping, parsed result
pt_health_check                              # down links, duplicate IPs
pt_save_project(filename)                    # persist the running .pkt
```

## Three ways to get a topology into Packet Tracer

1. **Live deploy** (`pt_live_deploy`) sends commands to a running Packet Tracer
   through the bridge. See [Live Deploy Setup](live-deploy.md).
2. **Clipboard** (`pt_full_build` or `pt_deploy`) copies the generated JavaScript
   to the clipboard, to be pasted into Packet Tracer's Builder Code Editor.
3. **Export to disk** (`pt_export`) writes the generated JavaScript, the
   per-device IOS configuration and the plan JSON to `projects/<name>/`.

Next: [Live Deploy Setup](live-deploy.md).
