# Interpreting capability evidence

Read this reference when deciding whether stored evidence matches the current question or when records conflict.

Match the capability scope, target, scenario, environment fingerprint, probe definition, observation method, and freshness required by the request. Keep provenance and cleanup outcome attached to the record. Do not collapse contradictory records into a stronger conclusion than either supports.

Interpret the current evidence types and statuses from `src/packet_tracer_mcp/domain/enterprise/models/discovery.py` and `src/packet_tracer_mcp/domain/enterprise/models/capabilities.py`; do not reproduce their fields or status rules here. Use `tests/test_e95_version_scoped_evidence.py` and `tests/test_e95_capability_reconciliation.py` for current matching and reconciliation behavior.
