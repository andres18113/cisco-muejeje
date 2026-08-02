# QA de capability probes

Las pruebas live son manuales y no forman parte de `pytest` normal. Antes de comenzar, abrir Packet Tracer con MCP Control Center, consultar `pt_bridge_status` y usar un proyecto desechable o una región vacía del canvas.

## Secuencia mínima

1. Ejecutar `pt_probe_capabilities(models=["PC-PT", "2911", "2960-24TT", "3560-24PS"], probe_level="physical")`.
2. Confirmar que el resumen indica cleanup limpio y que no quedan devices `__MCP_PROBE_*`.
3. Consultar `pt_capability_report(report="summary")` y registrar la versión de Packet Tracer explícitamente si el runtime no la expone.
4. Revisar puertos descubiertos y comparar contra la GUI; no promover modelos ni aliases automáticamente.

## PoE manual

Si Packet Tracer no expone un estado de potencia fiable, conservar PoE como `UNKNOWN`. Para verificación manual documentar: versión PT, modelo, puerto, powered device, estado visible y resultado. Esa observación puede convertirse después en `MANUAL_VERIFICATION` versionada; no debe codificarse como heurística por el nombre del switch.

## P0.1: `setIpSubnetMask()`

Probar por separado una PC-PT y un Server-PT con IP estática. Verificar mediante getters/API real que IP y máscara persisten. Un escenario DHCP requiere un router, switch y parser/read-back de lease controlado; si no existe esa evidencia, queda pendiente y no altera `DeviceCapabilities` ni marca E4 como listo.

## Baseline E3.6 registrado

La validación live del 2026-08-02 usó Packet Tracer `9.0.1.0858`, ambos
canales del bridge disponibles al inicio y dispositivos temporales con prefijo
`__MCP_PROBE_*`. El snapshot consolidado de `PC-PT`, `2911`, `2960-24TT` y
`3560-24PS` terminó `clean`, con hash
`62530cbc46627d5eaec95704ce5516889a61704ab94d8b53d9bad54789d96671`.

- Identidad y puertos: observados mediante create/read-back para los cuatro modelos.
- Módulos, PoE, VLAN, trunk y L3: `UNKNOWN` cuando el runtime no tuvo un
  configure/read-back controlado; no se dedujo soporte del nombre del modelo.
- P0.1 estático: `configurePcIp()` conservó la IP y máscara configuradas en
  `PC-PT` y `Server-PT`; no se reprodujo una inversión de argumentos en esa
  versión. DHCP no se promovió a verificado en este baseline.

## Si algo falla

Un timeout, callback inválido o disconnect del bridge es `UNKNOWN` y debe conservar el nombre de la sesión para inspección. No cambiarlo a `UNSUPPORTED`. Si hay `DIRTY_SESSION`, eliminar manualmente sólo los nombres temporales indicados; nunca borrar dispositivos del usuario.
