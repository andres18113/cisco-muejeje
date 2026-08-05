---
name: first-hop-redundancy
description: Diseña y verifica redundancia de gateway mediante capabilities FHRP observadas, actualmente HSRP cuando el perfil runtime lo permite.
---

# First-Hop Redundancy

## Responsibility

Separar intención ACTIVE/STANDBY, forwarding VIP, failover y recuperación.

## Core workflow

FHRP intent -> VIP/subnet validation -> deterministic group/priority -> apply -> role observation -> VIP baseline -> failure -> VIP recovery -> role recovery.

## Rules

- VIP pertenece a la subnet y no colisiona con IP físicas.
- Preferencia activa determinista.
- VIP forwarding no prueba ACTIVE/STANDBY.
- Syslog transition es evidencia de evento, no estado persistente.
- No inventar VRRP/GLBP.

## Evidence / readiness

Reportar role verification, behavioral gateway verification, failover y recovery por separado.

## Stop conditions

Detener si VIP, subnet, physical addresses, capability o baseline son ambiguos.

## Completion

Resultado HSRP/FHRP con método de evidencia y campos UNOBSERVABLE cuando PT no ofrece getter.

## References

Usar el profile de capabilities y el runtime existente; no acoplar esta Skill a UI.
