"""Physical container for the package; importing it through `src` is refused.

`src/` is where `packet_tracer_mcp` lives on disk. It is not a name anything may
import through: the canonical namespace migration made `packet_tracer_mcp` the
one identity for production and tests, because the same files loaded as both
`packet_tracer_mcp` and `src.packet_tracer_mcp` become two module objects, two
classes and two enums, and every `isinstance` or enum comparison across them is
silently false.

Whenever the repository root is on `sys.path` -- as it is for the test suite and
for any interpreter started there -- Python finds `src`. Deleting this file would
not close that path, because `src` would still resolve as a PEP 420 namespace
package and `import src.packet_tracer_mcp` would load the package a second time.
This file therefore exists to refuse: importing `src`, and with it any
`src.packet_tracer_mcp` module or `find_spec` of one, raises `ImportError` before
a second identity can be created.

The installed package never reaches this file. The editable install and the
wheel expose `packet_tracer_mcp` directly, and the wheel does not contain `src/`.
"""

raise ImportError(
    "'src' is the repository's source layout directory, not an import namespace. "
    "Use 'import packet_tracer_mcp' instead of 'src.packet_tracer_mcp'.",
    name="src",
)
