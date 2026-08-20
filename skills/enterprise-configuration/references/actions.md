# Typed configuration actions

Read this reference when an approved foundational change spans multiple typed actions or when prerequisite and verification relationships affect execution.

Let the current compiler choose the action shapes, ordering constraints, desired-state semantics, and verification expectations. Do not reconstruct action enums, model fields, or the dependency graph from Skill prose. A compiled action, rendered backend command, accepted dispatch, direct observation, and behavioral result are different evidence points.

Inspect `src/packet_tracer_mcp/domain/enterprise/models/configuration.py`, `src/packet_tracer_mcp/domain/enterprise/services/configuration_compiler.py`, and `tests/test_enterprise_compiler.py` for current action semantics. Use `tests/test_configuration_application.py` and `tests/test_e95_manifest_application.py` when application or identity binding matters.
