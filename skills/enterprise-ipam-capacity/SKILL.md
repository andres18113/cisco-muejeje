---
name: enterprise-ipam-capacity
description: Planifica IPv4, VLSM, bloques resumibles, crecimiento, reservas y capacidad de puertos, PoE y uplinks; soporta asignación INITIAL y reconciliación sin renumeración innecesaria.
---

# Enterprise IPAM and Capacity

## Responsibility

Convertir demanda normalizada en direccionamiento y capacidad física suficiente.

## Core workflow

EndpointRequirements -> normalized growth -> ResolvedDemand -> IPAM -> address capacity -> ports/PoE/uplinks -> reconciliation report.

## Rules

- Normalizar crecimiento una vez; reservar capacidad sin crear endpoints ficticios.
- Preferir bloques resumibles por site.
- En RECONCILE preservar asignaciones válidas y reportar renumeración necesaria.
- Separar demanda IP, puertos físicos y potencia PoE.
- PC-through-phone puede usar dos IP y un puerto.
- Wireless clients no consumen puertos cableados; los AP sí.
- Reservar management, SVI, FHRP, transit y loopbacks explícitamente.

## Evidence / readiness

No overlaps, host capacity suficiente, agregación preservada, reservas explicadas y allocation determinista.

## Stop conditions

Detener ante overlap, capacidad insuficiente, crecimiento aplicado dos veces o renumeración silenciosa.

## Completion

Entregar IPAM, reservas, capacidad por segmento y reconciliación con cambios explícitos.

## References

- Consultar addressing.md.
- Consultar reconciliation.md.
