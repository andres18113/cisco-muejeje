# infrastructure/generator/

Generators convert validated domain plans and typed Enterprise actions into
artifacts that Packet Tracer can consume. The package produces Script Engine
JavaScript for topology construction and device operations, IOS configuration
payloads, and specialized renderings for configuration, control-plane,
security, services, voice, VLANs, ACLs, NAT, hardening, and interface tuning.

Rendering is deliberately separate from validation and dispatch. Generators use
structured serialization for JavaScript data and the shared IOS safety helpers;
they must not interpolate untrusted values into executable source. A typed
renderer reports an action it cannot cover instead of silently omitting it.

Generated output is an intended command sequence. Whether Packet Tracer
accepted or applied it is established only by the applicable execution and
observation path.
