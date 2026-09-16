# infrastructure/catalog/

This package supplies the backend data and policies consumed by topology and
Enterprise planners. It covers device and port descriptions, modules, cable
rules, model aliases, topology templates, and capability profiles for hardware,
services, security, voice, link modes, and control planes.

Catalog data is an input to planning, not proof that an arbitrary Packet Tracer
build supports an operation. The generic device catalog is distinct from
measured inventories and reviewed capability projections. A measurement is
scoped to the model, build, method, and source evidence it records; missing or
out-of-scope evidence remains unknown.

Callers should resolve names and ports through this package rather than deriving
them from display labels. Module compatibility and factory-module information
are likewise catalog inputs, not permission to guess a Packet Tracer API or a
physical slot.
