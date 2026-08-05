---
name: campus-layer2
description: Diseña, aplica y verifica resiliencia Layer 2 con STP/Rapid-PVST/MST y EtherChannel, incluyendo roles, bundles, fallo y recuperación según capabilities observadas.
---

# Campus Layer 2

## Responsibility

Resolver loop prevention y agregación sobre los enlaces físicos exactos de E4.

## Core workflow

L2 intent -> root/member policy -> typed plan -> apply -> current state -> forwarding baseline -> controlled failure -> alternate forwarding -> recovery.

## Rules

- Root intent explícito y determinista.
- Edge ports no son infraestructura, trunk ni miembros EtherChannel.
- Port-channel es lógico y no cableable.
- STP observa el bundle lógico, no inventa miembros independientes.
- Rapid-PVST verificado no implica MST ni PAgP/static.

## Evidence / readiness

Separar root/role/state, bundle/member state, forwarding, failover y recovery.

## Stop conditions

Detener si E4 no contiene camino redundante, el baseline no funciona o la capability del modo es UNKNOWN.

## Completion

Estado L2 actual, forwarding baseline, failover y recovery con cleanup verificado.

## References

- Consultar stp.md.
- Consultar etherchannel.md.
