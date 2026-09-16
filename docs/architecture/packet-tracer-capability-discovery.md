# E3.5: Packet Tracer Capability Discovery

E3.5 measures Packet Tracer capabilities before Enterprise hardware selection
relies on them. It does not compile a user topology, generate layout, configure
a user network, or promote a model into the catalog automatically.

## Boundaries

The domain defines identities, ports, probe results, sessions, snapshots,
conflicts, and E4 readiness. Application use cases coordinate prerequisites,
bounded batches, cleanup, caching, and reports. Infrastructure provides the
typed bridge adapter, local snapshot store, and the reviewed Git-tracked
projection of governed measurements. MCP tools only adapt these contracts.

A probe creates only recorded disposable devices in an isolated workspace and
attempts exact-name cleanup. It does not modify, rename, link, power down, or
delete existing devices, and it does not save a user Packet Tracer file. Logical
commands come from an internal registry, not arbitrary JavaScript or IOS input.

## Evidence and status

SUPPORTED, UNSUPPORTED, and UNKNOWN describe a capability. They are distinct
from execution outcomes such as timeout, bridge failure, verification failure, a
skipped action, or a missing prerequisite. A timeout is not evidence of
unsupported behavior.

Runtime and controlled-probe observations are scoped to the exact Packet Tracer
version when one is recorded. Resolver precedence is controlled probe/runtime,
manual verification, static override, catalog, then inference. Conflicts remain
recorded; a winning value does not erase prior evidence.

The local capability store is mutable discovery state. In contrast,
measured_capabilities.py is a reviewed, exact-build projection for facts that an
exposed plan already requires. It retains model, build, producer, method, and
source-snapshot identity. A newer exact runtime observation can outrank that
projection without rewriting it. Absent, other-build, or non-equivalent-model
evidence remains unknown.

## Scope and use

Physical discovery establishes only the facts it reads back, such as temporary
creation and port inventory. Administrative or runtime PoE getters are not
proof of endpoint power delivery. A reusable PoE claim requires coherent
active-delivery evidence on access ports.

The runtime does not fabricate a model enumeration or Packet Tracer version API.
Callers supply a model to probe and may supply a version to scope the evidence.
Runtime-only models are reported as such and are never copied automatically into
the generic device catalog.

pt_probe_capabilities runs the bounded discovery path. pt_capability_report
reports already stored snapshots. E4 readiness keeps identity, ports, modules,
PoE, Layer 3, and endpoint-addressing evidence separate, and refuses a hardware
selection with blocking unknowns.
