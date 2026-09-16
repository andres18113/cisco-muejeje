# domain/

The domain layer defines the typed network language and deterministic business
rules. It has no dependency on Packet Tracer transports, MCP adapters, or local
persistence.

| Area | Responsibility |
| --- | --- |
| `models/` | Classic topology contracts and typed configuration, security, routing, and service values. |
| `enterprise/` | Enterprise intent, planning, hardware, compilation, deployment, runtime, and qualification contracts. |
| `rules/` | Pure validation that returns typed results for the calling use case to decide. |
| `services/` | Planning, addressing, validation coordination, comparison, analysis, and presentation transformations. |

The domain can describe an intended topology or the status of evidence, but it
does not perform I/O or claim that Packet Tracer applied a change.
