# Device lifecycle

Read this reference when an operation depends on a newly created, booting, or otherwise transitioning live target.

Connection readiness, object existence, target identity, device boot, command-interface readiness, and post-change convergence are separate facts. Observe the state required by the intended operation and use a timeout appropriate to that state. Do not infer later readiness from an earlier successful step.

Read `src/packet_tracer_mcp/infrastructure/execution/device_lifecycle.py` and `tests/test_device_lifecycle.py` for the current state machine and failure handling. Terminal-specific readiness belongs in `ios-terminal.md`.
