---
name: enterprise-network-design
description: Define the logical structure, segmentation goals, and resilience intent of an enterprise network before addressing, hardware selection, configuration, or Packet Tracer execution. Use for deciding what the network must contain and tolerate; do not use for assigning subnets or choosing devices.
---

# Enterprise Network Design

Own the logical structure and tolerated outcomes of the network without making downstream physical or runtime choices.

## Workflow

1. Classify sites, buildings, floors, zones, endpoint populations, service and trust boundaries, connectivity, and tolerated failures.
2. Separate requirements from assumptions. Preserve stable hierarchy and grouped demand; do not expand individual endpoints merely to make the design concrete.
3. Define logical roles, segment purposes, topology intent, and failure outcomes. Record cross-domain requirements without choosing specialist policy.
4. Verify that each material choice traces to a requirement or explicit assumption and that equivalent intent produces the same logical result.
5. Hand the plan to `enterprise-ipam-capacity`; hardware planning follows resolved demand.

## Boundaries and stops

- Do not allocate addresses, select hardware or interfaces, place coordinates, generate configuration, or mutate Packet Tracer.
- A placement zone is not automatically a VLAN, and duplicated equipment is not automatically independent redundancy.
- Stop when scope, demand, identity boundaries, or tolerated failure is ambiguous enough to change the plan.
- Mechanical model validation does not prove intent satisfaction; review the result against the stated requirements.

## Source navigation

Use Graphify only to locate symbols, then read `EnterpriseDesigner` and focused planning tests. Inspect `compose_enterprise_reference` only for the public offline composition seam; it is not a live deployment entrypoint.

## Conditional references

- Read the [hierarchy reference](references/hierarchy.md) when grouping boundaries affect the plan.
- Read the [redundancy reference](references/redundancy.md) when availability, failover, or failure domains affect the plan.
