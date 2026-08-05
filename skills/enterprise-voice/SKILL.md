---
name: enterprise-voice
description: Diseña y opera telefonía IP empresarial en Packet Tracer mediante VoicePlan, voice VLAN, bootstrap, extensiones, call-control y verificación de registro y llamada.
---

# Enterprise Voice

## Responsibility

Coordinar voz sin convertir limitaciones de la UI en API falsa.

## Core workflow

VoiceIntent -> VoicePlan -> voice VLAN/addressing -> call-control -> bootstrap -> registration -> call initiation -> call behavior -> teardown.

## Rules

- Voice VLAN es explícita y no se reutiliza silenciosamente como data VLAN.
- Teléfono usa identidad lógica, no el puerto físico passthrough.
- Extensiones deterministas; detectar colisiones y agotamiento.
- Seleccionar CME/SCCP/SIP sólo por capability evidence.
- TFTP/bootstrap, registration, call initiation, connection y audio son evidencias distintas.

## Evidence / readiness

Conservar STRUCTURED_API, PACKET_TRACER_NATIVE_UI, HYBRID o UNOBSERVABLE. APPLIED_BY_UI no equivale a CALL_VERIFIED ni a RTP/audio probado.

## Stop conditions

No llamar callbacks, coordenadas o dial routines desde otras Skills. Detener si falta PhoneControl adapter o evidencia de runtime.

## Completion

VoicePlan aplicado con estados de registro/llamada separados y limitaciones explícitas.

## References

Consultar el VoicePlan y VoiceApplicator existentes; no duplicar sus adaptadores.
