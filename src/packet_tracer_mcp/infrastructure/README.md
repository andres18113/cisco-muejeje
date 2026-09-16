# infrastructure/

Infrastructure contains the adapters that connect the application and domain
contracts to Packet Tracer, the file system, and reviewed capability data. It
does not define business policy: it implements the bounded operations and
evidence boundaries selected by the application layer.

## Package responsibilities

| Package | Responsibility |
| --- | --- |
| `catalog/` | Provides device, port, module, cable, template, and capability policy data used by planners. Reviewed measurements remain explicitly scoped to their recorded Packet Tracer build and evidence. |
| `diagnostics/` | Performs bounded, post-failure diagnostics. Its records help explain an observed failure; they do not establish acceptance or promote a capability. |
| `execution/` | Owns Packet Tracer transports, authenticated bridge access, command dispatch, physical deployment, typed configuration runtimes, read-back helpers, preflights, session guards, and controlled cleanup. It also exports classic plans when a live runtime is not used. |
| `generator/` | Renders validated plans and typed actions into Packet Tracer Script Engine JavaScript and IOS configuration payloads. Renderers preserve data escaping and reject actions outside their declared coverage. |
| `observation/` | Adapts Packet Tracer read-back into named CP-SCALE observations, including IOS, endpoint, forwarding, DHCP, STP, serial, and simulation evidence. Observation is separate from mutation and does not own physical deployment. |
| `persistence/` | Stores saved topology plans, deployment manifests, capability snapshots, and governed evidence artifacts. It keeps mutable local state separate from reviewed, canonical evidence. |

## Boundaries

Packet Tracer behavior is version-specific. A generated command, successful
transport call, or parsed value is not by itself a verified network claim. Live
paths therefore use their applicable preflight, attribution, read-back, and
cleanup contracts; offline tests verify only the code paths they execute.

The HTTP bridge is loopback-bound and authenticated. The file bridge is a
separate mailbox channel. Callers select the applicable transport through the
execution contracts rather than bypassing them.
