---
name: enterprise-hardware
description: Selecciona y dimensiona routers, switches, módulos e interfaces a partir de capacidad, resiliencia y capabilities observadas, después de IPAM y antes del compilador físico.
---

# Enterprise Hardware Planning

## Responsibility

Resolver HardwarePlan y DeviceRequirements sin convertir catálogos en evidencia runtime.

## Core workflow

CapacityDemand -> DeviceRequirements -> capability resolution -> candidate evaluation -> device groups -> HardwarePlan.

## Rules

- Consultar CapabilityRegistry y Runtime snapshots.
- UNKNOWN obligatorio produce NEEDS_VERIFICATION, nunca soporte ficticio.
- Distinguir interfaces físicas de interfaces lógicas.
- Reservar uplinks antes de puertos de endpoint.
- Validar capacidad por dispositivo, no sólo globalmente.
- PoE port count y PoE power budget son hechos distintos.
- No inventar módulos.
- HardwarePlanner no ejecuta probes.
- Preservar FailureDomains.

## Evidence / readiness

Cada candidato queda COMPATIBLE, NEEDS_VERIFICATION o INCOMPATIBLE con razones de selección y rechazo.

## Stop conditions

Detener ante capacidad insuficiente, módulo desconocido, capability obligatoria UNKNOWN o confusión entre puerto físico y SVI/Port-channel.

## Completion

HardwarePlan determinista, explicable y listo para el compilador físico.

## References

- Consultar device-selection.md.
