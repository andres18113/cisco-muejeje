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
- `infrastructure.catalog.measured_capabilities`: proyección revisada, Git-tracked y acotada por build de los resultados gobernados que consumen los planes distribuidos.
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

Hay dos superficies de infraestructura con responsabilidades distintas. El
store bajo `data/capabilities` conserva observaciones mutables y permite que un
probe/runtime posterior corrija el conocimiento local. No forma parte de una
instalación limpia. `measured_capabilities.py` conserva únicamente la proyección
revisada de hechos que un plan distribuido ya requiere, con modelo, build,
productor, método y hash estable del snapshot de origen. Se publica como
`static_override`, por debajo de probe/runtime en la precedencia: una nueva
observación exacta gana sin reescribir el baseline.

Agregar un registro exige evidencia gobernada `VERIFIED` de ese mismo modelo y
build; no se admite analogía entre modelos ni inferencia por nombre. Lo ausente
sigue siendo `UNKNOWN`, una evidencia de otro build no se reutiliza y una
medición negativa se conserva como `UNSUPPORTED`, no como ausencia.

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

## E3.6.1: readiness dependiente del escenario

El nivel `logical` verifica L2 mediante la presencia real de `VlanManager`.
VLAN y L3 tienen una ruta de configure/read-back/cleanup basada en el
`CommandPrompt` ya usado por la tool de ping. Si el dispositivo temporal no
expone ese prompt, el resultado queda `SKIPPED`/`UNKNOWN`, nunca inventado.
Trunk continúa pendiente hasta contar con lectura de trunk o tráfico originable
por la API.

El readiness calcula `non_poe_e4` y `full_poe_e4` a partir de perfiles por rol:
endpoint no requiere PoE ni routing; access requiere L2/VLAN/trunk; distribución
y core requieren L3; edge requiere routing. PoE se exige sólo en el escenario
que de verdad lo necesita.
