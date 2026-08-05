---
name: enterprise-configuration
description: Compila y aplica configuración Enterprise mediante ConfigurationPlan, acciones tipadas y dependencias explícitas para VLAN, access/voice ports, trunks, L3, SVI, subinterfaces, DHCP y endpoints.
---

# Enterprise Configuration

## Responsibility

Traducir intención validada a acciones tipadas, aplicarlas y verificar su efecto.

## Core workflow

ConfigurationIntent -> typed ConfigurationPlan -> dependency DAG -> apply -> convergence -> direct read-back -> behavioral verification.

## Rules

- Planner decide; compiler valida y traduce.
- No raw IOS actions.
- Cada action tiene ID estable, capability, dependencias y expectativas.
- Usar ENSURE_PRESENT, ENSURE_ABSENT, SET_VALUE o REPLACE.
- Bind al physical topology identity, no al layout.
- Runtime resuelve target por DeploymentManifest.
- COMPILED, APPLIED, DIRECTLY_OBSERVED y BEHAVIORALLY_VERIFIED son estados distintos.

## Evidence / readiness

Guardar hash fuente, action status, fresh query, parser, behavior y estado transaccional.

## Stop conditions

Bloquear dependientes si falla una dependencia obligatoria; DIRTY requiere recuperación explícita.

## Completion

ConfigurationPlan aplicado sin acciones arbitrarias y con evidencia actual o limitación declarada.

## References

- Consultar actions.md.
