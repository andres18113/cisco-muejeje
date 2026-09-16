# shared/

Shared code provides small, dependency-light contracts used across layers. It
contains common enums and defaults, IP and interface helpers, typed ping
evidence helpers, IOS payload construction, JavaScript escaping, and safe file
name and path-containment utilities.

The safety helpers are part of the implementation boundary: generated
JavaScript serializes data instead of interpolating it, and filesystem callers
normalize a component before resolving it within an approved base directory.
Domain policy belongs in `domain/`; Packet Tracer transport and runtime behavior
belongs in `infrastructure/`.
