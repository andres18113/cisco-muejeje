# infrastructure/execution/

This package implements the operational boundary with Packet Tracer and local
artifacts. It contains the authenticated HTTP bridge, file-mailbox transport,
command dispatch and attribution, classic artifact export, typed configuration
runtimes, physical topology operations, terminal read-back, probes, and
governed CP-SCALE live-session support.

## Operational contracts

- Transport delivery is not execution evidence. Command dispatch distinguishes
  the requested command, terminal echo, IOS execution, and independent
  observation.
- Live operations apply preflight and session-integrity guards appropriate to
  their scope. They preserve source, file, import-isolation, workspace, and
  cleanup evidence rather than treating a bridge response as success.
- The HTTP bridge is loopback-bound and token-authenticated except for its
  health probe. The file bridge is a separate local mailbox transport; callers
  select one governed channel for an operation.
- Packet Tracer calls are limited to signatures already established by the
  project. A runtime adapter does not infer API support from a model name or a
  partial response.

`ManualExecutor` and `DeployExecutor` support the classic plan-export path.
They are not a substitute for the physical deployment, configuration, and
read-back contracts used by Enterprise live execution.
