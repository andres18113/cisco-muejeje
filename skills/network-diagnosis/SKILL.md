---
name: network-diagnosis
description: Diagnostica fallos Enterprise a partir de resultados de acceptance y evidencia estructurada, identificando el primer invariante causal sin modificar la red.
---

# Network Diagnosis

## Responsibility

Explicar evidencia, no perseguir síntomas ni mutar Packet Tracer.

## Core workflow

EvidenceBundle -> first failing invariant -> ranked hypotheses -> contradicting evidence -> next discriminating observation.

## Rules

- Orden: identity/runtime -> interface/link -> L2 -> FHRP -> L3 -> routing -> security -> service.
- Separar evidencia de configuración, control-plane, RIB y forwarding.
- No diagnosticar BGP por una interfaz física caída.
- No convertir hipótesis en hechos.
- No ejecutar IOS mutante.

## Evidence / readiness

Cada RootCauseHypothesis incluye supporting evidence, contradicting evidence, confidence y siguiente observación.

## Stop conditions

Detener si el bundle está stale, falta identity, hay cleanup pendiente o el supuesto causal sólo se basa en un model name.

## Completion

Diagnóstico ordenado y no mutante, listo para acceptance o un ChangeSet explícitamente autorizado.

## References

Usar los modelos de aceptación, runtime quirks y evidence bundle del repositorio.
