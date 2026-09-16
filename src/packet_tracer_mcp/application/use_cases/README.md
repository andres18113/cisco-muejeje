# application/use_cases/

Use cases coordinate domain services, typed plans, and injected runtime ports.
They include the classic planning and artifact path as well as Enterprise
composition, hardware planning, compilation, configuration, services, voice,
security, control-plane application, physical deployment, observation, and
qualification workflows.

Each use case owns sequencing and status propagation for its contract. Runtime
implementations are supplied by infrastructure, while validation remains in the
domain. A use case must preserve a refusal, unknown result, failure, or cleanup
outcome rather than translating it into a verified Packet Tracer claim.
