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
`7134d42baeda7328fa324fb4fc5c690b85099e1ce425901e5a05da859fc1de00`.

- Identidad y puertos: observados mediante create/read-back para los cuatro modelos.
- Módulos, PoE, VLAN, trunk y L3: `UNKNOWN` cuando el runtime no tuvo un
  configure/read-back controlado; no se dedujo soporte del nombre del modelo.
- P0.1 estático: `configurePcIp()` conservó la IP y máscara configuradas en
  `PC-PT` y `Server-PT`; no se reprodujo una inversión de argumentos en esa
  versión. DHCP no se promovió a verificado en este baseline.

## E3.6.1: L2/L3 verificado y readiness por escenario

La validación del 2026-08-02 sobre Packet Tracer `9.0.1.0858` produjo el
snapshot `db16439e39bbea0b06cd9ff945e2fa25f53c13469034625c531875be33fa5ee8`.
La sesión `probe-829e47044f34` terminó `clean`: cuatro dispositivos temporales
creados y eliminados, 24 capabilities consultadas, 11 `SUPPORTED`, una
`UNSUPPORTED`, 12 `UNKNOWN` y cero errores de ejecución.

- L2 quedó verificado para `2960-24TT` y `3560-24PS`: ambos expusieron
  `VlanManager` mediante lectura runtime controlada.
- En dispositivos temporales, PT 9.0.1.0858 no expuso un `CommandPrompt`
  utilizable. Por ello las sondas VLAN y L3 no pudieron completar
  configure/read-back/cleanup y se conservaron como `UNKNOWN`/`SKIPPED` con
  una razón explícita. No se publicó evidencia positiva.
- Trunk permanece `UNKNOWN`: no hay getter de estado de trunk confirmado ni un
  test de tráfico que el API de extensión permita originar de forma controlada.
- PoE permanece `UNKNOWN`: no existe un estado de alimentación de puerto fiable
  en la superficie confirmada. No se tocó el Power Distribution Device del
  usuario ni se creó uno temporal como sustituto de evidencia.
- El reporte de readiness ahora calcula perfiles por rol: endpoint sólo exige
  identidad y puertos; access exige L2/VLAN/trunk y PoE sólo en el escenario
  PoE; distribución/core exige L3; edge exige L3. Un `PC-PT` ya no bloquea
  E4 por routing o PoE.
- P0.1 continúa `still_pending`: la observación estática anterior es
  `NOT_REPRODUCED_ON_PT_9.0.1.0858`, pero DHCP aún no tiene una lease
  configure/read-back controlada para PC-PT y Server-PT.

## Si algo falla

Un timeout, callback inválido o disconnect del bridge es `UNKNOWN` y debe conservar el nombre de la sesión para inspección. No cambiarlo a `UNSUPPORTED`. Si hay `DIRTY_SESSION`, eliminar manualmente sólo los nombres temporales indicados; nunca borrar dispositivos del usuario.
