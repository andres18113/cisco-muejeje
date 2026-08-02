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

Probar por separado una PC-PT con IP estática y un Server-PT con DHCP. Verificar en GUI y conectividad que IP y máscara persisten. Registrar versión PT, pasos, resultado y cualquier error. Esta prueba no altera `DeviceCapabilities` ni marca E4 como listo.

## Si algo falla

Un timeout, callback inválido o disconnect del bridge es `UNKNOWN` y debe conservar el nombre de la sesión para inspección. No cambiarlo a `UNSUPPORTED`. Si hay `DIRTY_SESSION`, eliminar manualmente sólo los nombres temporales indicados; nunca borrar dispositivos del usuario.
