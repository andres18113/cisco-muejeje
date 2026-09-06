# Continuación del diagnóstico de fábrica — 2026-09-06

Se retomó el mismo checkout `runtime-ripv2`, branch `feature/runtime-ripv2`,
HEAD `ab2e0f098a10b9c6f5075cf9cce329418d6b6f50`. El inventario del WIP coincidía
con el [handoff operativo](ROUTER0_POE_SESSION_HANDOFF_20260906.md); su agregado
diagnóstico conservaba SHA256 `4c757ed701c3f69ef01b6e2a774698da2b09415ae68a5af7bdd2aeaa1859fe87`.
GitHub API y `git -c http.sslBackend=openssl ls-remote` confirmaron el mismo
HEAD remoto. No se sustituyeron los artefactos de adquisiciones anteriores.

## Revisión del adaptador

Se contrastaron las firmas con la referencia Cisco instalada en
`C:/Program Files/Cisco Packet Tracer 9.0.1/help/default/IpcAPI/`:
`class_i_p_c.html`, `class_hardware_factory.html`, `class_device_factory.html`,
`class_device_descriptor.html` y `class_module_descriptor.html`.
`getDescriptor(DeviceType, string)` y el recorrido usan descriptores;
`getType()` no se confundió con `Module.getModuleType()` ni con hardware
instalado. `eAccessPoint=7` y `eAccessPointPowerAdaptor=31` están documentados.
La consulta codifica sus entradas con JSON, limita el árbol a 64 nodos y
profundidad 8, exige atribución exacta y tipos completos, y devuelve únicamente
`FACTORY_STRUCTURE_ONLY_NOT_POWER_DELIVERY`. No toca red, módulos, alimentación
ni persistencia de capacidades. La revisión fue local y fresca; no se atribuye
a un revisor independiente de la sesión anterior.

Se detectó un defecto de contrato: `resolve_model("ap")` aceptaba el alias de
catálogo y el método enviaba `"ap"` al IPC como identidad exacta de fábrica.
Un caso añadido al test de rechazo previo al dispatch falló por ese envío
(1 failed, 12 passed). El fix mínimo exige `catalog_model.pt_type == model`.
Focused posterior: 38 passed. Affected: 233 passed, incluyendo PoE,
gobernanza, transporte autenticado, correlación y aislamiento.
FULL con el intérprete local: **3818 passed, 4 warnings in 312.00s**:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -o cache_dir=tmp/pytest-cache --basetemp tmp/factory-full
```

`git diff --check` pasó. `graphify update .` finalizó con exit 0 (12530 nodos,
41240 aristas, 388 comunidades; advertencias de AST vacío/etiquetas, sin LLM).
Se revisó el diff final y se confirmó que dominio, aplicación y workflow no
cambiaron. Estas comprobaciones offline no validan el IPC ni el webview real.

## Intento de lectura y frontera efectiva

El runner local conservado `tmp/poe_factory_readonly.py` se inició con
`./.venv/Scripts/python.exe`; usa exclusivamente los adaptadores productivos
y `PacketTracerHttpTransport`. No usa JavaScript ad hoc ni Computer Use.
El registro original, copiado byte a byte, está en
[factory-structure-20260906T215401-0e856f07-bridge-blocked.json](canonical-live-evidence/factory-structure-20260906T215401-0e856f07-bridge-blocked.json).
SHA256: `861004ad18256d85dea3ec1e253b03d0d1055004a7349b441d7030482382101c`.

Boundary: `2026-09-06T21:53:39.953037Z` a `2026-09-06T21:54:01.980115Z`.
El aislamiento se verificó en ese proceso: intérprete local, paquete dentro
del worktree y solo `packet_tracer_mcp` en `sys.modules`. Source/diff y hashes
de archivos sin seguimiento se conservaron before/after. Ambos procesos PT
16184 y 32992 reportaron build `9.0.1.0858` y siguieron presentes al cierre.
El `.pts` mantuvo el hash canónico documentado en ambos extremos.

El bridge no recibió polls durante su ventana de conexión de 20 segundos:
`connected=false`, `last_poll_ago=null`, `unauth_count=0`.
**No se envió la consulta** (`query_dispatched=false`, `reads=[]`).
No se observaron inventario ni Realtime actuales, porque el gate cerró antes
de esas lecturas. No hubo fixture, mutación, qualification ni Router0 CP-LIVE.
El transporte se cerró. Esto es falta de conexión del canal, no error observado
del API de fábrica y no una respuesta `module_type_supported=false`.

Se solicitó al operador restablecer el polling del MCP Control Center;
es coordinación de disponibilidad bajo la restricción de no Computer Use,
no una nueva solicitud de autorización. No reintentar sin un cambio causal.

## Pista 3650 y continuación

La referencia Cisco local
`C:/Program Files/Cisco Packet Tracer 9.0.1/help/default/devicesAndModules_switches.htm`,
sección `Switch: 3650-24PS`, enumera `AC-POWER-SUPPLY` y `POWER-COVER-PLATE`
entre los módulos del modelo exacto. El catálogo productivo ya contiene esos
nombres como ModuleType 4. Esto aporta un nombre documentado a la pista
`inline power denied`; no establece una PSU instalada, su slot exacto,
necesidad eléctrica, entrega PoE ni un mapping productivo autorizado.
No se modificó la provisión ni el planner.

La primera acción dependiente del canal sigue siendo
`observe_factory_structure("AccessPoint-PT", module_type=31)` con bridge fresco
y registro before/after. Solo una respuesta válida permitirá investigar
estructura de fábrica; después hará falta atribuir hardware instalado y una
intervención legítima de aislamiento. Ausencia de metadata o UNKNOWN no
demuestran incapacidad física. La pista de PSU del 3650 también requiere
contraste empírico antes de cambiar la provisión.

La única autoridad positiva sigue siendo 3560-24PS/FastEthernet0/1 →
7960/Switch, capacidad simultánea 1. Los gaps y la demanda del handoff
permanecen. Router0 no admitido, sin run ID y con su única autorización
sin consumir; Router3 no ejecutado.
