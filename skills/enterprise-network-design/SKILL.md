---
name: enterprise-network-design
description: Diseña EnterpriseIntent y EnterprisePlan para matrices, datacenters, sucursales, edificios, pisos, zonas, usuarios, servicios y resiliencia antes de IPAM, hardware o IOS.
---

# Enterprise Network Design

## Responsibility

Transformar requisitos de negocio y red en una estructura lógica determinista.

## Core workflow

requirements -> hierarchy -> roles -> segments -> service/security/control-plane intent -> redundancy -> acceptance expectations -> EnterprisePlan

## Rules

- Conservar site, building, floor y zone.
- Mantener EndpointGroups agregados.
- Distinguir matriz, sucursal, datacenter, bodega y failure domains.
- Redundancia describe fallos tolerados, no sólo equipos duplicados.
- No crear dispositivos, seleccionar interfaces, módulos, cables o coordenadas.
- No asignar direcciones finales ni generar IOS.
- Preservar razones de decisiones importantes.

## Evidence / readiness

El plan debe exponer requisitos resueltos, pendientes, supuestos, segmentos, roles, dependencias, FailureDomains y expectativas de aceptación.

## Stop conditions

Detener si la jerarquía, el alcance, la cantidad de endpoints o el fallo tolerado son ambiguos y cambiarían materialmente el diseño.

## Completion

EnterprisePlan determinista con requisitos no resueltos explícitos y sin decisiones físicas prematuras.

## References

- Consultar hierarchy.md para la estructura canónica.
- Consultar redundancy.md para dominios de fallo.
