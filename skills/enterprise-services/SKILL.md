---
name: enterprise-services
description: Planifica, aplica y verifica DNS, HTTP/HTTPS, NTP y TFTP en Packet Tracer mediante ServicePlan, dependencias tipadas y evidencia directa o conductual.
---

# Enterprise Services

## Responsibility

Resolver servicios y demostrar tanto su estado como su uso por clientes.

## Core workflow

ServiceRequirement -> ServicePlan -> placement -> typed actions -> apply -> direct observation -> behavioral verification -> composed verification.

## Rules

- La identidad y dirección de hosts vienen de E4/E5.
- No asumir soporte de Server-PT sin capability evidence.
- Separar service state, record/content state y client behavior.
- DNS requiere lookup positivo y negativo cuando el intent lo pide.
- HTTP se verifica por IP y por hostname cuando DNS participa.
- NTP/TFTP pueden permanecer UNOBSERVABLE.

## Evidence / readiness

APPLIED no equivale a VERIFIED; una cadena hostname -> DNS -> HTTP sólo es VERIFIED si cada enlace tiene evidencia.

## Stop conditions

Detener si falta host placement, connectivity foundation, capability o evidencia independiente.

## Completion

ServicePlan con dependencias, acciones, resultados directos, conductuales y limitaciones.

## References

Usar los metadatos ServicePlan existentes y registrar quirks del runtime, no hardcodearlos aquí.
