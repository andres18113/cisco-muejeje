---
name: network-autofix
description: Propone y ejecuta correcciones Enterprise acotadas únicamente después de un diagnóstico respaldado por evidencia, con análisis de impacto, read-back, retest y rollback.
---

# Network Autofix

## Responsibility

Aplicar un ChangeSet pequeño, idempotente y reversible cuando la causa esté demostrada.

## Core workflow

RootCauseHypothesis -> Candidate ChangeSet -> impact analysis -> preconditions -> rollback -> one atomic mutation -> fresh read-back -> affected acceptance -> regression -> commit or restore.

## Rules

- Requiere acceptance failure, root cause con evidencia, DeploymentManifest limpio y capability suficiente.
- Nunca arreglar síntomas ni cambiar mecanismos no relacionados.
- Nunca sustituir un protocolo salvo autorización arquitectónica.
- No continuar desde DIRTY sin recovery policy.
- Toda mutación tiene inversa o rollback explícito.

## Evidence / readiness

Registrar scope, hashes, preconditions, change, read-back, retests, rollback y resultado.

## Stop conditions

No mutar si root cause es hipótesis débil, identity está stale, capability es UNKNOWN, impact no está acotado o rollback no existe.

## Completion

ChangeSet exitoso con acceptance recuperado, o restaurado y marcado unsuccessful; nunca redefine silenciosamente EnterprisePlan.

## References

Usar network-diagnosis y network-acceptance antes de ejecutar cualquier cambio.
