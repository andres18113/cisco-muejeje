---
name: enterprise-security
description: Compila, aplica y verifica ACL, NAT/PAT, port-security, DHCP Snooping, DAI y hardening mediante políticas tipadas y controles positivos y negativos.
---

# Enterprise Security

## Responsibility

Demostrar enforcement, no sólo presencia de configuración.

## Core workflow

SecurityIntent -> SecurityPlan -> placement/dependencies -> typed enforcement -> direct read-back -> positive behavior -> negative behavior -> cleanup -> recovery.

## Rules

- Resolver ACL placement desde topology, L3 boundaries y path; no elegir interfaces por intuición.
- No raw ACE/IOS en el dominio.
- Cada deny requiere baseline allow conocido.
- Preferir ALLOW before -> DENY after -> cleanup -> ALLOW after.
- No usar ping como sustituto de DNS, HTTP, voz, NTP o TFTP.
- No exponer secretos.

## Evidence / readiness

Separar COMPILED, APPLIED, DIRECTLY_OBSERVED, BEHAVIORALLY_VERIFIED y recovery; UNKNOWN no es PASS.

## Stop conditions

Detener si faltan source hashes, placement, baseline, capability, probe tipado o rollback.

## Completion

SecurityPlan con evidencia de allow/deny, read-back, cleanup y limitaciones.

## References

Reutilizar SecurityPlan, renderer y runtime E8; no crear un segundo executor.
