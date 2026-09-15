# Topology Templates

Templates seed a topology's shape and its defaults. Pass `template=<key>` to
`pt_plan_topology` or `pt_full_build`, or list them with `pt_list_templates` or
the `pt://catalog/templates` resource.

| Key | Name | Shape | Default routing |
|-----|------|-------|-----------------|
| `single_lan` | Single LAN | 1 router + 1 switch + PCs | static |
| `multi_lan` | Multi LAN | N routers chained, each with its LAN | static |
| `multi_lan_wan` | Multi LAN + WAN | N routers with LANs + a Cloud WAN | static |
| `star` | Star (Hub & Spoke) | 1 central router → N switches | static |
| `hub_spoke` | Hub and Spoke | 1 hub router + N spoke routers | static |
| `branch_office` | Branch Office | HQ + branches over WAN | static |
| `three_router_triangle` | Three Router Triangle | 3 routers, redundant | ospf |
| `router_on_a_stick` | Router on a Stick | 1 router + 1 switch, inter-VLAN | static |
| `custom` | Custom | Everything manual | static |

Selecting a template does not freeze the rest of the request:
`template=three_router_triangle` defaults to three routers and OSPF, and
`routers`, `pcs_per_lan` and `routing` can still be set explicitly.
