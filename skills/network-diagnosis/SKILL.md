---
name: network-diagnosis
description: Explica una falla de red mediante razonamiento causal sustentado en evidencia fresca y sin mutaciones; no usar para certificar readiness ni ejecutar correcciones.
---

# Network Diagnosis

## Responsibility

Encontrar el primer invariante causal respaldado por evidencia y proponer la observación mínima que discrimine las hipótesis restantes.

## Boundary

Diagnosis interpreta evidencia; no cambia configuración, no declara acceptance, no eleva un estado de evidencia y no presupone un executor dedicado que el repositorio no expone.

## Decision sequence

1. Partir del resultado fallido y conservar su identidad, alcance, método, frescura y ceilings.
2. Separar hechos observados, contradicciones, supuestos y datos faltantes.
3. Seguir dependencias causales desde el primer prerequisite fallido, cargando sólo el owner del dominio afectado.
4. Ordenar hipótesis por evidencia explicativa, no por cantidad de síntomas compatibles.
5. Solicitar una sola observación tipada y discriminante cuando la evidencia actual no baste.
6. Entregar causa respaldada o incertidumbre explícita, con evidencia a favor, en contra y siguiente paso.

## Evidence discipline

Las primitivas actuales de health, auditoría y packet trace pueden aportar observaciones; ninguna certifica por sí sola la causa. Una hipótesis no se vuelve hecho por coincidir con un nombre de modelo, configuración esperada o resultado histórico.

## Hard stops

Detener si la identidad cambió, el bundle está stale, cleanup sigue pendiente, la observación requerida no existe o el siguiente paso implicaría mutación. Devolver la incertidumbre sin alterar el estado gobernado.

## Source-of-truth navigation

Usar Graphify para localizar el parser, trace runtime o resultado de dominio pertinente. Leer después su source/test exacto y consultar `packet-tracer-runtime` sólo cuando haga falta una observación live.
