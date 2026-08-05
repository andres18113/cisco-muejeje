---
name: packet-tracer-capabilities
description: Descubre y resuelve capabilities reales de Packet Tracer mediante catálogo, snapshots versionados y probes controlados para modelos, interfaces, protocolos y runtime.
---

# Packet Tracer Capability Discovery

## Responsibility

Convertir hipótesis de soporte en evidencia versionada sin mutar dispositivos del usuario.

## Core workflow

resolve requirement -> inspect cache -> choose registered probe -> isolate session -> bounded operation -> independent read-back -> cleanup -> verify cleanup -> persist evidence -> resolve capability.

## Rules

- Falta de evidencia es UNKNOWN.
- Timeout, bridge failure, parser failure o cleanup failure no prueban UNSUPPORTED.
- La evidencia debe coincidir con Packet Tracer, extension/runtime, probe schema y backend fingerprint.
- Nunca aceptar IOS o JavaScript arbitrario como probe.
- Resources temporales sólo pueden ser propiedad de ProbeSession.
- Consultar RuntimeQuirkRegistry antes de generalizar.

## Evidence / readiness

Guardar capability, status, provenance, timestamp, runtime fingerprint, modelo, probe definition, read-back, cleanup y contradicciones.

## Stop conditions

Detener si no existe probe registrado, identidad de sesión, cleanup seguro, runtime fingerprint o read-back independiente.

## Completion

Capability report con SUPPORTED, UNSUPPORTED, PARTIAL, UNKNOWN o UNOBSERVABLE y evidencia reproducible.

## References

- evidence.md
- probes.md
- runtime-quirks.md
