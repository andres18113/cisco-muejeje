# application/

The application layer coordinates domain policy with injected infrastructure
ports. It contains DTOs, use cases, CP-SCALE live contracts, and port protocols
that keep Packet Tracer, persistence, and native UI implementations outside the
domain.

Classic use cases plan, validate, repair, render, and export a `TopologyPlan`.
Enterprise use cases compose intent, hardware, topology, configuration,
services, voice, security, control-plane, deployment, observations, and
qualification flows. They sequence contracts and propagate their typed status;
they do not replace a runtime observation with an assumption.

The MCP adapter is a caller of this layer. It should not embed planning or
runtime policy that belongs in a use case.
