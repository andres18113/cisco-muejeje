# Switching, IPv6 & Wireless

Beyond basic routing, the server can plan and configure VLANs, dual-stack IPv6,
wireless clients, and layer-2 and device hardening. Each section below states
what the generator emits. What has been qualified against a real Packet Tracer,
and on which build, is recorded separately in the qualification records under
`architecture/` and in `reference/cp-scale/current_state.json`.

## VLANs and inter-VLAN routing (router-on-a-stick)

Build a one-armed router that routes between VLANs using `.1q` subinterfaces:

```text
"Build a router-on-a-stick with 3 VLANs and 6 PCs, DHCP."
```

The model calls:

```python
pt_full_build(template="router_on_a_stick", vlans=3, pcs_per_lan=6, dhcp=True)
```

The resulting plan contains:

- N VLANs spread across the PCs (ids `10, 20, 30, …`), each with its own `/24`
  and DHCP pool.
- A trunk on the switch uplink, and access ports for the PCs in their VLAN.
- One router subinterface per VLAN (`GigabitEthernet0/0.10`, `…0.20`, …) with
  `encapsulation dot1Q <id>` and the VLAN gateway address.

On a `2960-24TT`, which is dot1q-only, the generator omits
`switchport trunk encapsulation`. On a `3560-24PS`, which supports several
encapsulations, it emits `switchport trunk encapsulation dot1q`.

To add VLANs to an already deployed topology, use [`pt_apply_vlan`](tools.md):

```python
pt_apply_vlan(
  switch="SW1", router="R1",
  vlans=[{"vlan_id":10,"name":"SALES"},{"vlan_id":20,"name":"ENG"}],
  access_ports=[{"switch":"SW1","port":"FastEthernet0/1","vlan_id":10},
                {"switch":"SW1","port":"FastEthernet0/2","vlan_id":20}],
  trunks=[{"switch":"SW1","port":"GigabitEthernet0/1"}],
  subinterfaces=[{"router":"R1","parent_port":"GigabitEthernet0/0","vlan_id":10,"ip_cidr":"192.168.10.1/24"},
                 {"router":"R1","parent_port":"GigabitEthernet0/0","vlan_id":20,"ip_cidr":"192.168.20.1/24"}],
  dry_run=True)   # preview the CLI before applying
```

## IPv6 dual-stack

Add IPv6 alongside IPv4 with one flag:

```python
pt_full_build(routers=2, dual_stack=True)
```

- Routers get `ipv6 unicast-routing` and `ipv6 address <prefix>::1/64` per
  interface, through the CLI.
- Hosts use SLAAC. They auto-configure from the router's Router Advertisements;
  `configurePcIpv6` enables IPv6 and address auto-configuration.

Static host IPv6 is not available: Packet Tracer's Script Engine rejects
`addIpv6Address` on host ports, so end devices use SLAAC rather than a hardcoded
address. Routers carry the explicit `ipv6 address`.

## Wireless laptops

Connect Laptop-PTs over WiFi instead of a cable:

```python
pt_full_build(laptops_per_lan=2, wireless_laptops=True)
```

- Each laptop's wired NIC is replaced with a wireless card
  (`PT-LAPTOP-NM-1W` → `Wireless0`).
- An access point is added and cabled to the switch.
- The plan places the wireless hosts on the same LAN as the wired PCs, with the
  default SSID and no explicit security parameters.

Wireless association is **not qualified**. The governed backend policy in
`reference/cp-scale/current_state.json` records `wireless_association` as
`unqualified`, which means no governed run has established that association, or
the DHCP lease that depends on it, occurs in a given Packet Tracer build. Treat
the wireless path as planned configuration, not as verified behaviour.

Access-point SSID and WPA2 settings cannot be configured from here: Packet Tracer
does not expose them through its Script Engine, so a custom SSID or security
profile has to be set in the access point's own GUI.

## Layer-2 security and device hardening

These are configuration-driven and accept `dry_run=True` to preview the CLI:

| Tool | Example |
|------|---------|
| [`pt_apply_stp`](tools.md) | `pt_apply_stp(switch="SW1", root_primary_vlans=[10], portfast_ports=["FastEthernet0/1"])` |
| [`pt_apply_port_security`](tools.md) | `pt_apply_port_security(switch="SW1", port="FastEthernet0/1", max_mac=2)` |
| [`pt_apply_hardening`](tools.md) | `pt_apply_hardening(device="R1", enable_secret="cisco", users=[{"username":"admin","secret":"pass","privilege":15}], ssh={"domain":"lab.local"})` |
| [`pt_apply_interface_tuning`](tools.md) | `pt_apply_interface_tuning(router="R1", interface="Serial0/0/0", clock_rate=64000)` |

## Verifying a deployment

After a deploy, reconcile what the plan intended against what Packet Tracer
actually holds:

```python
pt_diff(plan_json=...)   # missing/extra devices, IP mismatches
pt_health_check()        # down links, cabled-without-IP, duplicate IPs
```

`pt_live_deploy` also reconciles on its own: when Packet Tracer drops a device
during a deploy, a behaviour observed with Laptop-PT, it re-adds the missing
devices and links and verifies again within the same call.
