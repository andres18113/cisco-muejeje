---
name: network-acceptance
description: Evalúa si una red cumple su intención con evidencia gobernada de estado, comportamiento y recuperación; no usar para explicar causas ni aplicar reparaciones.
---

# Network Acceptance

## Responsibility

Emitir un veredicto trazable para expectativas declaradas sin asumir el diagnóstico ni la reparación de un resultado fallido.

## Boundary

Acceptance decide si la evidencia satisface una expectativa. `network-diagnosis` explica por qué falló; el owner de dominio conserva su política. Los escenarios de fallo sólo pertenecen aquí cuando son reversibles, están autorizados y tienen baseline e inversa verificables.

## Decision sequence

1. Localizar la expectativa y el modelo de resultado vigentes en source/tests; no recrear sus campos en prose.
2. Confirmar identidad de despliegue, frescura, prerequisites y baseline aplicables.
3. Reutilizar evidencia todavía válida y obtener sólo la observación adicional necesaria.
4. Evaluar por separado configuración, observación directa, comportamiento, fallo y recuperación cuando la expectativa los requiera.
5. Registrar veredicto, método, procedencia, alcance y cualquier evidencia ausente o no observable.

## Evidence discipline

- `COMPLETED` no significa `VERIFIED`; una ejecución terminada puede conservar verificaciones parciales o desconocidas.
- La existencia del executor interno de referencia no lo convierte en un entrypoint público live.
- Un timeout, parser ausente o observación indirecta conserva su ceiling; no se promueve para cerrar acceptance.
- Un resultado de dominio puede alimentar acceptance sin transferirle la propiedad de esa decisión de dominio.

## Hard stops

Detener la evaluación dependiente cuando falten identidad vigente, baseline, cleanup, prerequisite obligatorio o una inversa segura. Reportar el hueco de evidencia en lugar de fabricar un PASS o FAIL más fuerte.

## Source-of-truth navigation

Usar Graphify sólo para ubicar la expectativa, el resultado y su runner actuales. Confirmar después en source/tests exactos y, para una ejecución live, en evidencia runtime fresca.
