# E3.5: Packet Tracer Capability Discovery

E3.5 mide capacidades de Packet Tracer antes de usarlas para seleccionar hardware Enterprise. No compila topologías, no genera layout, no escribe IOS para una red de usuario y no promociona automáticamente modelos al catálogo.

```text
Catalog
  + Runtime discovery / controlled probes
  -> CapabilitySnapshot (versioned JSON)
  -> RuntimeCapabilityProvider / ProbeCapabilityProvider
  -> CapabilityResolver
  -> DeviceSelector
  -> HardwarePlanner
```

## Capas

- `domain.enterprise.models.discovery`: contratos de identidad, puertos, resultados, sesiones, snapshots, conflictos y preparación E4.
- `application.use_cases.capability_discovery`: orquesta lotes secuenciales, prerequisites, cache, limpieza y resumen.
- `infrastructure.execution.probe_runtime`: adaptador tipado del bridge; sólo usa APIs de Packet Tracer ya presentes en el proyecto.
- `infrastructure.persistence.capability_snapshot_store`: snapshots JSON UTF-8, ordenados y confinados bajo `data/capabilities`.
- `adapters.mcp.tool_registry`: dos adaptadores delgados: `pt_probe_capabilities` y `pt_capability_report`.

El dominio no importa MCP, bridge ni JavaScript.

## Seguridad de probes

Cada sesión crea dispositivos temporales llamados `__MCP_PROBE_<session>_<index>` en una región aislada. Registra cada objeto inmediatamente y siempre intenta eliminarlo en un bloque de limpieza. Si falla una eliminación, el resultado queda `DIRTY_SESSION` y lista únicamente los nombres temporales afectados.

Los probes no modifican, renombran, enlazan, apagan ni eliminan dispositivos existentes; tampoco guardan el `.pkt`. Los comandos lógicos proceden exclusivamente del registry interno: la tool no acepta JavaScript ni IOS arbitrario.

## Estados y evidencia

`SUPPORTED`, `UNSUPPORTED` y `UNKNOWN` describen la capacidad. Son distintos de los estados de ejecución (`TIMEOUT`, `EXECUTION_ERROR`, `BRIDGE_ERROR`, `VERIFY_FAILED`, `SKIPPED` y `PREREQUISITE_MISSING`). Un timeout no significa que una capacidad sea unsupported.

Las observaciones runtime y los probes controlados se guardan con versión exacta de Packet Tracer cuando está disponible. La evidencia de otra versión no se reutiliza. La precedencia es:

1. controlled probe / runtime;
2. manual verification;
3. static override;
4. catalog;
5. inference.

Los conflictos permanecen registrados como `CapabilityConflict`; el ganador no borra evidencia anterior.

## Alcance inicial

El default es un lote físico y limitado: `PC-PT`, `2911`, `2960-24TT` y `3560-24PS`. El nivel `physical` verifica creación e inventario de puertos y conserva PoE o módulos como `UNKNOWN` si Packet Tracer no expone hechos fiables. El nivel `logical` está modelado con dependencias, pero el bridge actual no cuenta todavía con una vía confirmada de configurar y releer L2/L3 de forma segura; por eso esos probes quedan `SKIPPED`/`UNKNOWN`, nunca inventados.

Packet Tracer no expone en la superficie confirmada de este proyecto una enumeración fiable de modelos ni una consulta de versión. El runtime no finge esas APIs: usa create probes cuando se le da un modelo y acepta una versión explícita para scope de evidencia.

Los modelos runtime-only, como `IE-3400`, se reportan como tales. No se escriben automáticamente en `devices.py`.

## Uso MCP

`pt_probe_capabilities(models=[...], probe_level="physical")` crea devices temporales y devuelve un resumen compacto. `force=True` ignora la cache de misma versión/modelos/capacidades/schema. `pt_capability_report(report="summary|model|unknown|readiness|catalog_gaps")` sólo consulta snapshots ya almacenados.

## Graphify First

Antes de explorar arquitectura o hacer cambios: `graphify update .`, una consulta concreta, `explain`, `path` o `affected`. El source confirma y los tests demuestran; Graphify sólo guía la navegación.

## Límite hacia E4

`E4ReadinessReport` conserva por separado identidad, puertos, módulos, PoE, L3 y P0.1. E4 sólo será apto cuando no queden unknowns bloqueantes para el hardware seleccionado. E3.5 no cierra P0.1: `setIpSubnetMask()` requiere aún prueba real independiente.
