# QA de capability probes

Las pruebas live son manuales y no forman parte de `pytest` normal. Antes de comenzar, abrir Packet Tracer con MCP Control Center, consultar `pt_bridge_status` y usar un proyecto desechable o una región vacía del canvas.

## Secuencia mínima

1. Ejecutar `pt_probe_capabilities(models=["PC-PT", "2911", "2960-24TT", "3560-24PS"], probe_level="physical")`.
2. Confirmar que el resumen indica cleanup limpio y que no queda residuo en **ninguno de los dos namespaces desechables**: `__MCP_PROBE_*` ni `MCP-PROBE-*`. Ver "Namespaces desechables" más abajo.
3. Consultar `pt_capability_report(report="summary")` y registrar la versión de Packet Tracer explícitamente si el runtime no la expone.
4. Revisar puertos descubiertos y comparar contra la GUI; no promover modelos ni aliases automáticamente.

## Namespaces desechables

Existen dos, y el chequeo de residuo debe cubrir los dos:

| Prefijo | Quién lo crea | Atraviesa renderers confiables |
| --- | --- | --- |
| `__MCP_PROBE_*` | capability discovery (`pt_probe_capabilities`) | No |
| `MCP-PROBE-*` | probes desechables de un camino tipado | Sí |

El segundo prefijo existe porque el renderer de control plane sólo acepta
nombres cuyo primer carácter es alfanumérico, así que un guion bajo inicial no
puede llegar hasta él. El validador no se relajó.

Ninguno de los dos prefijos sostiene la limpieza: un dispositivo temporal se
borra por su nombre exacto, no por coincidencia de prefijo. Los prefijos son
para que una persona —y este chequeo de QA— reconozcan lo desechable de un
vistazo.

Si aparece residuo, eliminar manualmente sólo los nombres listados por la
sesión; nunca borrar dispositivos del usuario.

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

## E3.6.2: ciclo de vida temporal y canal de configuracion

Los probes temporales usan `lwAddDevice`, igual que `pt_live_deploy`, en vez de
crear directamente con `addDevice`. La disponibilidad de `CommandPrompt` no se
usa como requisito: Packet Tracer 9.0.1.0858 puede exponer el device y el canal
oficial `configureIosDevice` antes de exponer ese objeto.

El probe espera como maximo 8 segundos, con polling de 250 ms y diagnostico
compacto. Los comandos se envian fire-and-forget por el canal oficial y se
verifican en una lectura separada. En la validacion live se verificaron:

- 2911 IPv4 de una interfaz, con lectura y limpieza;
- 2960-24TT y 3560-24PS VLAN 999, por `VlanManager`, con limpieza;
- sesiones temporales limpias.

No se promueve evidencia de trunk, PoE, DHCP ni SVI L3 de 3560 cuando la lectura
independiente falla. La secuencia combinada revelo una condicion de carrera del
SVI 3560 despues de limpiar VLAN, que permanece como `UNKNOWN`.

## E3.6.3: aislamiento y convergencia de estado

Las definiciones mutantes de VLAN, trunk y L3 ahora exigen un device temporal
fresco. `StateConvergenceWaiter` separa la disponibilidad del device de la
convergencia de lectura posterior a una mutacion. El 3560 L3 no se promovio:
el read-back de IPv4 falla incluso en un temporal aislado, por lo que requiere
investigacion del runtime antes de habilitar el gate jerarquico.

**Superado en ese punto concreto — 2026-08-19, mismo build `9.0.1.0858`.** La
frase anterior queda como registro de lo observado el 2026-08-02, pero ya no
describe el comportamiento medido: la **primera** corrida de capability
discovery gobernada sobre `3560-24PS` del cierre de `TD-HARDWARE-001` configuró
dos SVIs en un temporal y las leyó de vuelta con
`svi_address_readback = observed`, es decir la IPv4 leída coincidió con el
gateway configurado en ambas.

La atribución importa: el resultado global de esa misma corrida fue
`multilayer_intervlan = UNKNOWN`, y la re-corrida posterior que sí cerró la
entrada no registra valores de campo SVI. Lo medido es el read-back de IPv4;
no repetir aquí la investigación de un fallo que esa medición no reproduce,
pero tampoco citar la corrida de cierre como fuente de este dato.

Esto **no** promueve la fila `3560 SVI` de `e95-runtime-debt.md`, que es otra
afirmación: esa fila exige que el estado administrativo y el line protocol se
mantengan separados, y ambos se leyeron `up`, sin control negativo que
distinguiera un `admin up / protocol down`. El read-back de IPv4 está medido;
la separación de esos dos estados no.

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

## CP-SCALE: observación tipada de potencia de puerto

La calificación live del 2026-08-22 sobre Packet Tracer `9.0.1.0858` confirmó
que `SwitchPort.getPower()` e `isPowerOn()` son lectores disponibles. En
dispositivos frescos y sin enlaces, los 24 puertos FastEthernet de
`3560-24PS` devolvieron `true/true`, mientras los 24 de `2950T-24` devolvieron
`false/false`. Los dos puertos Gigabit de cada modelo se conservaron como
uplinks y no se contaron como capacidad PoE de acceso.

El probe físico registrado ahora guarda por separado el estado administrativo
y el estado runtime, exige booleanos estrictos y una observación completa y
homogénea. Ausencia, valores malformados o resultados mixtos permanecen
`UNKNOWN`; modelo o build distintos no heredan la evidencia. El snapshot
exacto `3560-24PS` / `9.0.1.0858` quedó `SUPPORTED`, `VERIFIED`, con 24 puertos
de acceso y método `object_state` (hash
`ae52cee8f8e23d032141aaa025c6ea466aa82b90bc5cc156660f67f625b9156e`).

Esta afirmación autoriza capacidad hardware PoE, no entrega activa a un equipo
alimentado. No se conectó un powered device y `power_delivery_active` continúa
sin observarse. La sesión eliminó el temporal por identidad exacta, confirmó
dos veces el workspace semántico vacío y preservó el PDD preexistente.

Al alcanzar después el preflight de despliegue físico, Stage A identificó cinco
inventarios exact-build ausentes sin ejecutar ninguna mutación de topología. El
`PortInventoryQualifier` existente midió de forma acotada `AccessPoint-PT`,
`7960`, `Printer-PT`, `819HG-4G-IOX` y `3560-24PS` mediante el mismo
`observe_device` de producción. Las cinco identidades observadas coincidieron
con el modelo solicitado, expusieron inventarios no vacíos y quedaron
versionadas para `9.0.1.0858`; otra identidad o build no recibe autorización.
Los cinco temporales se eliminaron en orden inverso, dos observaciones finales
restauraron el baseline y `Power Distribution Device0` se preservó.

La primera ejecución física reveló además que el inventario enumerado del
`819HG-4G-IOX` contiene un alias no independiente. Tras verificar un enlace en
`FastEthernet0`, el pre-readback exacto rechazó `Ethernet1` como ya enlazado;
`GigabitEthernet0` aceptó y verificó un segundo enlace distinto. El inventario
conserva ambos nombres observados, pero registra
`Ethernet1 -> FastEthernet0` como alias no canónico: no cuenta como otro puerto
ni autoriza un binding concreto. El control limpió sus dos dispositivos y
enlaces, confirmó dos veces la restauración y preservó ambos PDD retenidos.

## Si algo falla

Un timeout, callback inválido o disconnect del bridge es `UNKNOWN` y debe conservar el nombre de la sesión para inspección. No cambiarlo a `UNSUPPORTED`. Si hay `DIRTY_SESSION`, eliminar manualmente sólo los nombres temporales indicados; nunca borrar dispositivos del usuario.
