---
name: network-acceptance
description: Evalúa si una red Enterprise cumple su intención mediante evidencia de estado, comportamiento, fallos y recuperación; no modifica la red salvo escenarios reversibles autorizados.
---

# Network Acceptance

## Responsibility

Convertir expectativas tipadas en PASS, FAIL, PARTIAL, UNKNOWN, UNOBSERVABLE o SKIPPED.

## Core workflow

foundations -> L2 -> FHRP -> routing -> services -> security -> end-to-end -> failure/recovery.

## Rules

- Configured, observed y behavioral son estados distintos.
- UNKNOWN no es PASS; UNOBSERVABLE no es FAIL.
- Registrar expected, observed, outcome, method, freshness, target y runtime.
- Temporal expectations incluyen IMMEDIATE, EVENTUALLY, STABLE_FOR, MUST_REMAIN y MUST_FAIL.
- Todo fallo requiere baseline, inversa y restore verificado.

## Evidence / readiness

Aceptar sólo evidencia actual, plan-bound y suficiente para la expectativa específica.

## Stop conditions

No ejecutar pruebas dependientes si foundation o baseline falla; no convertir un timeout en UNSUPPORTED.

## Completion

Acceptance report compacto con trazabilidad y recuperación independiente.

## References

Consultar los expectations y result models existentes antes de crear tipos nuevos.
