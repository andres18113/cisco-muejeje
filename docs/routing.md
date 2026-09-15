# Routing Protocols

Set `routing` on `pt_plan_topology` or `pt_full_build`. Valid values: `static`,
`ospf`, `eigrp`, `rip`, `none`.

Run `pt_validate_plan` before deploying. It reports unreachable networks and
missing links before any routing configuration reaches a live device.

## Static (default)

Bidirectional static routes are generated between LANs over the WAN links.

```text
R1:  ip route 192.168.1.0 255.255.255.0 10.0.0.2
R2:  ip route 192.168.0.0 255.255.255.0 10.0.0.1
```

- `floating_routes=True`, with `routing=static`, adds backup routes with
  administrative distance 254 over alternate paths. It needs a topology that has
  multiple paths.

## OSPF

- `ospf_process_id` (default `1`).
- Networks are advertised per interface, single-area by default.

## EIGRP

- `eigrp_as` — autonomous-system number (default `100`).

## RIP

- RIPv2, with the relevant networks advertised.

## None

- `routing=none` builds the topology and its addressing but configures no
  routing protocol. It suits pure layer-2 scenarios, or cases where routing is
  configured separately.
