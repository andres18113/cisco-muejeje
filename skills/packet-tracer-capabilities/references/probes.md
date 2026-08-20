# Probe protocol

Read this reference only after matching stored evidence fails to resolve the capability question and a probe is authorized.

Select a registered typed probe for the exact requirement. Establish a fresh isolated session, limit mutation to session-owned resources, use an independent observation path, bound every wait, and verify cleanup before accepting the result. If isolation, read-back, or cleanup fails, preserve the inconclusive outcome instead of converting it to unsupported.

Read `CapabilityProbeRegistry` and `CapabilityDiscoveryService` in `src/packet_tracer_mcp/application/use_cases/capability_discovery.py` for the current protocol. Inspect `src/packet_tracer_mcp/infrastructure/execution/probe_runtime.py` and `tests/test_e95_probe_isolation.py` only when probe execution or isolation behavior matters.
