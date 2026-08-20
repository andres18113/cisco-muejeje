---
name: network-autofix
description: Registra la futura remediación gobernada de una red después de un diagnóstico demostrado; no usar para diagnóstico, pt_fix_plan ni reparaciones operativas actuales.
---

# Network Autofix

## Responsibility

Definir el contrato futuro para una corrección acotada, autorizada, reversible y respaldada por evidencia.

## Availability

Esta responsabilidad no es operativa. Consultar `skills/manifest.json`: mientras su distribución sea `none`, no seleccionarla como Skill primaria ni ejecutar mutaciones en su nombre.

El `fix_plan` actual corrige de forma determinista un conjunto pequeño de defectos de `TopologyPlan`. No es diagnóstico de una red live, no consume una causa raíz y no implementa un ChangeSet con rollback.

## Future workflow boundary

Una implementación futura deberá recibir un diagnóstico sustentado, limitar impacto y precondiciones, preparar la inversa antes de mutar, obtener read-back fresco, repetir sólo las verificaciones afectadas y restaurar ante fracaso.

No describir comandos, cambios de configuración ni atajos de ejecución hasta que esos contratos existan en source/tests y tengan exposición gobernada.

## Routing

- Para explicar una falla, usar `network-diagnosis`.
- Para corregir un `TopologyPlan` con el helper existente, usar el flujo actual de planificación/validación.
- Para aplicar configuración ya aprobada, usar el owner de dominio con `enterprise-configuration` y, si corresponde, `packet-tracer-runtime`.

## Hard stop

Detener cualquier intento de activación normal, mutación o afirmación de rollback soportado. No convertir esta memoria futura en capacidad presente.
