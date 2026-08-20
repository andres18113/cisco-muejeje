---
name: packet-tracer-layout
description: Arrange an already-defined Packet Tracer topology into a deterministic, readable hierarchy while preserving every device, link, interface, address, and policy decision. Use for coordinates and visual grouping; do not use to design or change the network.
---

# Packet Tracer Layout

Own presentation state only: compute or apply coordinates for an existing topology without changing network semantics.

## Operating modes

- For a whole planned topology, use the offline `LayoutPlanner` and approved layout profile.
- For one bounded live move, establish runtime readiness and identity before using the current public move operation. Do not invent a batch mutation surface.

## Workflow

1. Require a concrete topology with stable device identities and links.
2. Read hierarchy and role metadata from the plan; do not infer semantics from names or current canvas position.
3. Compute deterministic placement through the current planner.
4. Compare device and link inventory before and after. Physical identity must remain unchanged while layout identity may change.
5. For live movement, retain the request, acknowledgement, read-back when available, tolerance, and transport result. Acknowledgement alone is not exact placement proof.

## Stops and evidence

- Stop if the request changes a device, link, interface, address, site, zone, redundancy path, or policy.
- Stop when the intended runtime device cannot be resolved. Hand design changes to `enterprise-network-design` and live lifecycle concerns to `packet-tracer-runtime`.
- Check deterministic placement, supported non-overlap guarantees, unchanged physical identity, and bounded live read-back.

Use Graphify only to locate symbols, then read `LayoutPlanner` and focused compiler tests. Read topology identity tests for layout-only change, and current move/observation source for live evidence semantics. Source and tests own exact hashing and tolerance behavior.
