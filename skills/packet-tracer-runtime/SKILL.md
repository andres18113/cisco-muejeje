---
name: packet-tracer-runtime
description: Opera Packet Tracer mediante lifecycle controlado, DeploymentManifest, queries tipadas, evidencia fresca, read-back, convergencia y cleanup. Usar para cualquier operación live.
---

# Packet Tracer Runtime

## Responsibility

Aplicar y observar planes contra una instancia concreta de Packet Tracer sin confundir callable API con estado operativo.

## Core workflow

preflight bridge/runtime -> fingerprint -> resolve DeploymentManifest -> validate identity -> await lifecycle -> typed mutation/query -> fresh window -> parse -> bounded convergence -> cleanup/read-back.

## Rules

- Crear dispositivo no significa IOS ready.
- Usar sólo queries y mutations registradas.
- Cada query debe aislar output actual; histórico no es evidencia.
- Configuración aceptada no es read-back ni comportamiento.
- No write memory en recursos desechables.
- Restaurar fallos en finally y verificar cleanup.

## Evidence / readiness

Registrar target identity, command echo, current window, parser, freshness, runtime, status y transacción CLEAN, DIRTY, RESTORED o RESTORE_FAILED.

## Stop conditions

Detener si bridge, token, fingerprint, prompt operativo, target identity, capability o baseline no están listos.

## Completion

Resultado compacto con aplicación, observación, convergencia, recovery y cleanup independientes.

## References

- lifecycle.md
- ios-terminal.md
- transactions.md
