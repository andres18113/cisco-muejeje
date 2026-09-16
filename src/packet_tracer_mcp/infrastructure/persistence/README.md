# infrastructure/persistence/

Persistence keeps local project data and governed evidence durable without
collapsing their different authorities.

- `ProjectRepository` stores and reloads serialized `TopologyPlan` values and
  their local metadata under a path-constrained project directory. This is not
  Packet Tracer `.pkt` file control.
- Deployment-manifest storage retains the physical deployment contract used by
  later configuration and observation stages.
- Capability snapshot storage manages local, versioned discovery observations;
  callers must still apply the resolver and evidence rules before relying on
  them.
- Evidence publishers persist canonical and CP-SCALE records with their
  provenance and integrity requirements.

Paths and names are normalized through the shared containment helpers. Deletion
is limited to a resolved project directory; callers must not construct storage
paths by concatenation.
