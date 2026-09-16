"""Physical container for the package; deliberately not an import namespace.

`src/` is where `packet_tracer_mcp` lives on disk. It is not a name anything may
import through: the canonical namespace migration made `packet_tracer_mcp` the
one identity for production and tests, because the same files loaded as both
`packet_tracer_mcp` and `src.packet_tracer_mcp` become two module objects, two
classes and two enums, and every `isinstance` or enum comparison across them is
silently false.

This file is kept rather than deleted, because deleting it does not close the
hole it appears to open. With the repository root on `sys.path`, removing this
`__init__.py` leaves `src` a PEP 420 namespace package, so `import
src.packet_tracer_mcp` still succeeds -- it would remove the marker while
keeping the defect. What actually holds the boundary is enforcement, not the
absence of a file:

* `tests/namespace_preflight.py` refuses a test process that has the retired
  namespace loaded, before any test module is imported;
* `tests/test_namespace_inventory.py` fails if any tracked source imports it
  again, whether as a statement or as a dynamic import target; and
* `packet_tracer_mcp.infrastructure.execution.import_isolation_preflight`
  refuses a LIVE mutation from a process holding both identities.
"""
