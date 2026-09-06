# Relevo operativo: adquisición PoE y Router0 — 2026-09-06

## 1. Mandato para la próxima sesión

Continúa autónomamente en el MISMO checkout de `feature/runtime-ripv2` hasta
obtener la evidencia PoE exacta exigida por el producto y ejecutar exactamente
UNA Router0 CP-LIVE gobernada. NO Router3. Conserva los cambios locales de esta
sesión; no empieces desde un checkout nuevo que pierda el WIP y los artefactos
ignorados.

Este relevo se escribe porque el usuario pidió expresamente pausar y preparar
el contexto de la siguiente sesión. NO representa finalización de Router0,
una nueva decisión de imposibilidad física, ni consumo de su única LIVE.

Autorización vigente del usuario:

- Investigar y corregir source, tests, integración, qualifier, observer,
  persistencia y gobernanza cuando exista un defecto o contrato incompleto.
- Test causal RED → fix mínimo → focused/affected/full pytest → aislamiento de
  imports → diff check → revisión fresca → commit/push SOLO a
  `cisco/feature/runtime-ripv2` → Actions 4/4 para ese SHA.
- Ejecutar las calificaciones PoE LIVE gobernadas MÍNIMAS e informativas
  necesarias; persistir evidencia válida y volver a resolver capacidades y
  HardwarePlan después de cada positivo.
- Cuando la admisión productiva pase, congelar SHA limpio y verde y ejecutar
  inmediatamente UNA Router0 CP-LIVE. No pedir de nuevo aprobación de lo ya
  autorizado.
- Corregir blockers de implementación; `PRECONDITION_BLOCKED` por falta de
  evidencia es diagnóstico intermedio, no resultado final.

Límites vigentes:

- Source + tests + evidencia directa > `current_state` > handoffs/historia.
- No cambiar reglas de negocio, reducir `requires_poe`, inventar mappings,
  extrapolar puertos/modelos, promover por analogía, o convertir UNKNOWN en
  autorización. `poe_ports=1` no significa más puertos.
- Cada positivo requiere switch model + switch port + endpoint model + endpoint
  port exactos. Capacidad simultánea debe observarse en un mismo episodio; no
  sumar resultados secuenciales.
- Control diferencial gobernado y caracterizado, nunca UNKNOWN. No inferir
  PoE por catálogo, modelo, link-up, DHCP, forwarding, `getPower()` o
  `isPowerOn()`.
- Una mutación por enlace, readback bilateral exacto, observación endpoint-side
  fresca/atribuible, cleanup endpoint-first, inventario y Realtime restaurados,
  file/runtime safety vigente. No sleeps arbitrarios ni retry-until-green.
- No raw IOS/JS como escape. Usar los adaptadores productivos tipados; una
  consulta documentada implementada y testeada no es licencia para mandar JS
  ad hoc por el bridge.
- No reabrir Floors/Voice/PVST sin contradicción nueva; en el acumulativo,
  mutation delta / verification cumulative y stop en primera frontera real
  contradicha. No modificar source durante una LIVE.
- El crash conocido `0xc0000005` posterior al cierre no bloquea Router0. No
  analizar dumps en esta tarea. Crash dentro del boundary: fail-closed y
  assessment de cleanup/integridad; después de observación, verificación,
  cleanup, safety y persistencia: incidente posterior sin invalidación retroactiva.

El objetivo original solo tiene como cierre Router0 LIVE completado o NUEVA
evidencia empírica de limitación física real que haga imposible el diseño bajo
las reglas existentes. Esta sesión NO ha demostrado esa limitación.

## 2. Restricción nueva del operador: sin Computer Use

El usuario revocó Computer Use: no CUA, sky, capturas automáticas de escritorio,
clicks, pestañas o UI por agente. El operador abre pestañas y ordena iconos;
entrega capturas mediante `-i`/`--image` o archivos locales que se pueden leer
con `view_image`.

Directorio confirmado:

```text
C:\Users\Andres\Desktop\Codex cap
```

Su última aclaración textual fue:

> Solo movi iconos, abro pesatañas nada mas

Esto quedó registrado como declaración de que solo hubo cambios de iconos y
pestañas, sin cambios de alimentación, módulos ni enlaces por el operador.
No es recibo visual dentro del boundary ni prueba de aislamiento eléctrico.
No pedir otra vez la ruta. Coordinar disponibilidad y revisar imágenes nuevas
DENTRO de la ventana antes de devolver el recibo al observer.

## 3. Estado Git y validación al entregar

```text
REPO       andres18113/cisco-muejeje
CHECKOUT   C:\Users\Andres\Desktop\Universidad\Uce\Cuarto\Infra\Cisco-MCP\.claude\worktrees\runtime-ripv2
BRANCH     feature/runtime-ripv2
UPSTREAM   cisco/feature/runtime-ripv2
HEAD       ab2e0f098a10b9c6f5075cf9cce329418d6b6f50
WORKTREE   DIRTY: cambios de esta sesión, enumerados más abajo
ROUTER0    NO ejecutado; autorización de una CP-LIVE aún sin consumir
ROUTER3    NO ejecutado
```

Actions del HEAD, reconsultadas al preparar el relevo: **4/4 success**,
[run 34059022088](https://github.com/andres18113/cisco-muejeje/actions/runs/34059022088):
Windows y Ubuntu, Python 3.11 y 3.13. Esto NO valida los cambios sin commit.

Historia corta de esta cadena de trabajo:

- `247294b619dfd7805a542a27019d3f78f94713c0`: baseline recibido, decisión PoE
  exacta intacta; registro de dumps corregido.
- `c4f1e8d680f569c00e68129bfd8c9a39f34935fd`: persistencia de admisión Router0
  bloqueada antes de LIVE; Actions 34056492520 verde.
- `ab2e0f098a10b9c6f5075cf9cce329418d6b6f50`: fix de layout visible del fixture
  simultáneo, causal RED/GREEN, revisión fresca, full pytest 3804 passed
  (4 warnings), commit/push y Actions 4/4.

No hubo otro commit/push después de `ab2e0f0`. No se ha corrido full pytest
sobre el WIP de diagnóstico de fábrica. No darlo por validado para LIVE.

## 4. Causa productiva y demanda rederivada

El planner NO está roto: rechaza correctamente porque los bindings PoE exactos
que requiere no están cubiertos. `router0_authorized=true` ya está registrado;
el bloqueo actual no es ese campo documental ni la atribución del crash.

Artefacto causal de precondición:

```text
docs/reference/cp-scale/prelive-evidence/router0-precondition-20260906T195307168481Z-247294b619df.json
SHA256 6e2e46376debb1e0cdc5a63de8b501bb9ddcd85c8281ec6d36a53c2f8dd99fab
```

Autoridades de source:

- `domain/enterprise/scenarios/cp_scale_physical.py`
- `domain/enterprise/services/reference_hardware_planner.py`
- `application/use_cases/compose_cp_scale_canonical.py`
- `ReferenceHardwarePlanner._powered_bindings_by_device(...)`

Las rutas de source anteriores son relativas a `src/packet_tracer_mcp/`.
Se volvió a ejecutar el harness SIN `--execute` al preparar este relevo:
`admission_before=false`, sin mutación PT, y demanda Router0 aún exacta:

| Dispositivo/modelo | Binding requerido | Simultáneo |
| --- | --- | --- |
| MLS3 / 3650-24PS | Gi1/0/2, Gi1/0/3, Gi1/0/5–Gi1/0/13 → 7960/Switch; Gi1/0/4 → AccessPoint-PT/Port 0 | 12 |
| MLS4 / 3650-24PS | Gi1/0/2 → 7960/Switch; Gi1/0/3 → AccessPoint-PT/Port 0 | 2 |
| MLS5 / 3560-24PS | Fa0/1–Fa0/8 → 7960/Switch | 8 |
| MLS6 / 3560-24PS | Fa0/13 → AccessPoint-PT/Port 0 | 1 |

Fa0/1 ya tiene autoridad individual; preservarla. Su participación en una
prueba simultánea de 8 puede ser causalmente necesaria, no una repetición para
recalificar artificialmente ese binding.

Hallazgo importante: el compositor exige el HardwarePlan del diseño físico
completo ANTES de la proyección de etapa. Cubrir solo los puertos nuevos de
Router0 no garantiza admisión. La unión del diseño actual para 3560 incluye
7960/Switch en Fa0/1–Fa0/21 y AccessPoint-PT/Port 0 en
Fa0/{4,5,13,14,15,16,21,22,23}. No confundir esta exigencia de admisión con
permiso para reejecutar Router3 o reabrir resultados de Floors.

El resolver ya conserva la unión exacta de bindings y el máximo de capacidad
observada por episodio, NO una suma de episodios. No cambiar esa regla.

Plan de agrupación considerado, condicionado a resolver la observabilidad y
volver a derivar el source: dos episodios 3650 (MLS4 y MLS3, porque Gi1/0/3
cambia de endpoint), y dos 3560 (teléfonos Fa1–21 + AP Fa22/23, 23 simultáneos;
AP restantes Fa4/5/13/14/15/16/21). No ejecutar de golpe este plan: todavía
no se ha establecido cómo obtener un control AP sin alimentación independiente.
Tampoco hay un comando listo para todos esos grupos en el harness actual.

## 5. Única autoridad PoE positiva que sigue vigente

```text
run_identity  poe-7950198d050f
build         9.0.1.0858
binding       3560-24PS / FastEthernet0/1 + 7960 / Switch
control       2960-24TT / FastEthernet0/1 + 7960 / Switch
capacity      1
```

Artefacto:

```text
docs/reference/cp-scale/canonical-live-evidence/poe-delivery-20260906T184155139196Z-7950198d050f-verified.json
SHA256 45ea94314228f1b0f49979f5fb815eddd55d63c972429ad548f583b11c3d9a90
```

No otro binding nuevo resultó VERIFIED en esta sesión. Las adquisiciones
fallidas NO deben degradar ni ampliar esta autoridad. Ningún AP está calificado.

## 6. Episodios PoE realizados y cerrados

Todos los siguientes terminaron sin recibo visual completo dentro de su
`observe(...)`: UNKNOWN / unobservable, NO prueba de incapacidad física.
Todos registraron cleanup, inventario semántico, Realtime e integridad `.pts`
restaurados y no crash en sus boundaries. No hay una LIVE que deba continuarse
retroactivamente.

| Run ID | Source | Fixture y resultado causal | Cierre UTC / cleanup |
| --- | --- | --- | --- |
| `r0poe-mls4-b4810d48` | c4f1e8d | 3650: Gi2→phone y Gi3→AP; control 2960 Fa1/Fa2. 6 devices, 4 links exactos. Coordenadas 9000/9000 fueron clampadas y superpuestas: observador inutilizable. | 20:27:35.626491 / 6 de 6 |
| `r0poe-mls4-6ffe810b` | ab2e0f0 | Mismo fixture tras fix causal de layout. No recibo completo. Diagnóstico de boot del 3650 detectó teléfono y denegó inline power; ver abajo. | 20:57:51.778697 / 6 de 6 |
| `r0poe-mls6-07e15945` | ab2e0f0 | 3560 Fa13→AP y control 2960 Fa1→AP, 4 devices/2 links. Usuario interrumpió el tool para revocar Computer Use; runner siguió hasta deadline y limpió. | 21:07:42.875440 / 4 de 4 |
| `r0poe-mls6-df79fafe` | ab2e0f0 | Igual binding, cambio causal a observador humano coordinado (“Listo para capturar”). Imágenes no llegaron al callback dentro del deadline. | 21:14:32.461330 / 4 de 4 |

En el último episodio la ventana fue
`2026-09-06T21:09:32.108453Z` → `2026-09-06T21:14:32.108453Z`.
El PTY 96093 se recogió hasta salida. No reenviarle recibos ni reconstruir
un resultado positivo ahora. El directorio `r0poe-mls4-37a30e1f` está vacío;
su mera existencia NO es evidencia de una LIVE consumida.

Raw evidence por episodio:

```text
tmp/router0-poe-live/<run-id>/preflight.json
tmp/router0-poe-live/<run-id>/capture-request.json
tmp/router0-poe-live/<run-id>/result.json
tmp/router0-poe-live/<run-id>/closure.json
```

Los snapshots fueron escritos por el mecanismo gobernado en
`data/capabilities/runtime/9.0.1.0858/`; la ruta exacta está en cada result.
Los archivos `tmp/` son ignorados: conservarlos en este checkout.

### Diagnóstico 3650 — todavía no es un veredicto físico final

Una lectura de CLI de boot (sin enviar IOS) en `6ffe810b` registró:

```text
Would you like to enter the initial configuration dialog? [yes/no]:
%ILPOWER-7-DETECT: Interface Gig1/0/2: Power Device detected: IEEE PD
%ILPOWER-5-ILPOWER_POWER_DENY: Interface Gig1/0/2: inline power denied
```

Se vieron dos bays de PSU vacíos en Physical; el diseño productivo actual del
3650 no añade módulos (`modules=[]`). Es una pista causal de provisión de
alimentación, NO permiso para inventar una PSU/mapping ni una conclusión de
que ningún 3650 pueda satisfacer Router0. Hay que investigar con autoridad de
source/API y observación, y corregir el contrato solo si corresponde.

Archivos retenidos:
`tmp/router0-poe-live/r0poe-mls4-6ffe810b/candidate-switch-cli.txt` y `.jpg`.
Esa observación antigua de UI precede a la revocación de Computer Use. No volver
a usar Computer Use para ampliarla.

## 7. Capturas humanas revisadas: qué prueban y qué no

Se encontraron y revisaron SEIS PNG (incluido `imagen2ap.png`, aunque no estaba
en la lista textual inicial de cinco archivos):

| Archivo | Hallazgo visible |
| --- | --- |
| `imagen1.png` | Physical del AP de control; identidad completa del episodio; cable dibujado conectado e indicador verde. |
| `imagen2.png` | Physical del AP candidato; misma presentación alimentada. |
| `imagenap.png` | Config del AP de control, nombre completo, reloj del dispositivo 00:02:57. |
| `imagen2ap.png` | Config del candidato, nombre completo, reloj 00:03:11. |
| `cli1.png` | Boot del 2960 de CONTROL, “Press RETURN to get started”, Fa1 up. NO es CLI del 3560 candidato. |
| `topologia.png` | Dos brazos, modelos e identidades completos, links verdes; link-up NO es PoE. |

Los timestamps de archivo locales caen aproximadamente entre 16:12 y 16:13:56
(UTC−5), dentro de la ventana nominal. Pero la recepción/revisión por el
observer ocurrió después del cierre: metadata de archivo NO reemplaza un
recibo síncrono dentro de `observe(...)`. No retrovalidar ni reescribir runs.

Ambos AP presentan alimentación visible. Por eso falta aislar y atribuir la
fuente: el control no permite demostrar el diferencial requerido. El gráfico
de un cable no basta para establecer por sí solo la fuente eléctrica exacta.
Tampoco demuestra que AccessPoint-PT sea incapaz de recibir PoE.

Originales sin modificar en `C:\Users\Andres\Desktop\Codex cap`.
Copias byte-idénticas y manifiesto de revisión en:

```text
tmp/router0-poe-live/r0poe-mls6-df79fafe/late-diagnostic-images/
tmp/router0-poe-live/r0poe-mls6-df79fafe/late-diagnostic-images/review.json
docs/reference/cp-scale/canonical-live-evidence/poe-acquisition-df79fafe-images/
```

Los seis hashes y la declaración del usuario están en el artefacto agregado
siguiente; las pruebas comprueban cada hash de la copia archivada.

## 8. Evidencia y gobernanza nueva, aún sin commit

Artefacto agregado de los tres episodios posteriores, con preflights,
requests, results, closures y revisión tardía de imágenes:

```text
docs/reference/cp-scale/canonical-live-evidence/poe-acquisition-20260906T211432-df79fafe-diagnostic.json
SHA256 4c757ed701c3f69ef01b6e2a774698da2b09415ae68a5af7bdd2aeaa1859fe87
schema cp-scale-poe-acquisition-diagnostic-v1
decision ACQUISITION_INCOMPLETE_NO_CAPABILITY_PROMOTION
physical_incapability_established false
router0_attempts_consumed 0
```

El primer episodio sigue en su propio artefacto ya comprometido:

```text
docs/reference/cp-scale/canonical-live-evidence/poe-acquisition-20260906T202735-b4810d48-unobservable.json
SHA256 f26cbe1ab1c2b254b5da73aba285086982b68aa8c7022a38443ad29b0e2640c8
```

`current_state.json` se actualizó sin tocar `last_live_state` histórico:

- Última adquisición `r0poe-mls6-df79fafe`, unobservable, cleanup 4/4, sin
  limitación física demostrada.
- `artifact` apunta al agregado nuevo; `prior_artifact` conserva el primero.
- Continuación: `INVESTIGATE_EXACT_AP_POWER_SOURCE_ISOLATION_BEFORE_NEXT_INFORMATIVE_QUALIFICATION`.
- Se añadieron las tres sesiones directas posteriores: lower bound total 46
  (36 histórico + 10 PoE indexadas), explícitamente NO exhaustivo. No confundir
  este contador global con las cero Router0 CP-LIVE consumidas por este mandato.
- La cualificación positiva Fa1 sigue intacta; el `source_head=247294b` del
  gate identifica la admisión offline histórica, NO el checkout actual.
- Proyección de compatibilidad de `handoff.md`: solo contador/cleanup actualizados;
  no reescribir su narrativa histórica.

`NEXT_GOVERNED_POE_LIVE_RELAY.md` es un relay RETIRADO con instrucciones
históricas de atribuir dumps antes de Router0. NO seguir esa secuencia: fue
explícitamente supersedida por el usuario.

## 9. Autofix ya comprometido: layout visible

El primer fixture se creó entero en (9000,9000); PT lo clampó a una misma
posición, haciendo imposible inspeccionar endpoints simultáneos. El fix de
`ab2e0f0` en `infrastructure/execution/poe_delivery_runtime.py` asigna una
cuadrícula por ordinal:

```text
x = 160 + 320 * (ordinal % 4)
y = 160 + 140 * (ordinal // 4)
```

Reserva el ordinal ANTES del dispatch, para que un timeout ambiguo no haga
reutilizar una posición quizá ocupada. Tests cubren 50 dispositivos distintos
y la reserva tras timeout. No cambió modelo, power, ports, planner ni reglas.
Ese fix sí pasó full/revisión/CI, pero no convirtió las adquisiciones siguientes
en evidencia positiva.

## 10. Punto exacto donde se interrumpió el trabajo: diagnóstico de fábrica

Se investigó la documentación Cisco instalada y un revisor independiente
(`review_poe_layout`, Kuhn) confirmó una vía de SOLO LECTURA, sin crear otro
fixture, para consultar el modelo exacto:

```text
IPC.hardwareFactory() → HardwareFactory.devices()
DeviceFactory.getDescriptor(DeviceType, string)
DeviceDescriptor.getModel(), getType(), isModuleTypeSupported(ModuleType), getRootModule()
ModuleDescriptor.getModel(), getType(), isHotSwappable()
ModuleDescriptor.getSlotCount(), getSlotTypeAt(int)
ModuleDescriptor.getModuleCount(), getModuleAt(int)
```

Referencia local de Cisco:

```text
C:\Program Files\Cisco Packet Tracer 9.0.1\help\default\IpcAPI\
class_i_p_c.html
class_hardware_factory.html
class_device_factory.html
class_device_descriptor.html
class_module_descriptor.html
```

`eAccessPoint=7`; `eAccessPointPowerAdaptor=31`. La existencia del enum 31 NO
demuestra compatibilidad con AccessPoint-PT: podría corresponder a otro modelo.
Los descriptores usan `getType()`, NO los métodos del runtime Module
`getModuleType()`/`getSlotPath()`. No mezclar esas dos interfaces.

Hallazgos documentales complementarios:

- La descripción del AP genérico muestra un slot de módulos tipo hub/repeater;
  no se encontró una instrucción que pruebe un adaptador aislable del modelo
  exacto. Esto no es evidencia empírica de incapacidad PoE.
- `Device.setPower(false)` apaga el dispositivo entero. NO es “retirar la
  fuente externa” y usarlo como tal fabricaría un falso negativo.
- `Port.setPower` tampoco identifica/retira la fuente externa.
- `ModulePhysicalView.setIsPower` pertenece a la representación del módulo,
  no es una intervención válida de aislamiento eléctrico.
- FAQ 98 documenta 7960 con 3560 sin cordón; no se encontró equivalente para
  el AP genérico. No extrapolar esa FAQ al AP.

Implementación NUEVA y SIN COMMIT:

```text
src/packet_tracer_mcp/infrastructure/execution/poe_delivery_runtime.py
  PacketTracerPoEDeliveryFixtureRuntime.observe_factory_structure(model, *, module_type)

tests/test_poe_factory_structure.py
```

El método selecciona DeviceType solo para modelo catalogado, codifica campos
con `json.dumps`, lee el descriptor y recorre árbol acotado (64 nodos, 8 niveles),
rechaza respuestas incompletas/mal atribuidas y devuelve
`FACTORY_STRUCTURE_ONLY_NOT_POWER_DELIVERY`. No crea dispositivos, no muta
red/power/módulos, no persiste ni promueve capacidades.

Pruebas causales: 12 casos fallaron primero porque el método no existía.
Luego 37 passed al ejecutar el archivo nuevo junto con el runtime existente.
Algunas pruebas ejecutan el JS generado en Node contra una interfaz de fábrica
controlada que NO expone APIs de red/mutación; si Node no existe se marcan skip.
No confundir esos dobles offline con compatibilidad real del IPC de PT.

**NO SE EJECUTÓ AÚN LA CONSULTA CONTRA PACKET TRACER.**
El último anuncio fue que iba a consultarse sin mutación; el usuario interrumpió
y pidió este relevo antes de que se enviara. NO hay resultado empírico que
inventariar, interpretar o convertir en `module_type_supported=false`.

La revisión independiente cubrió el fix de layout anterior y las referencias
del API, NO el nuevo diff completo de `observe_factory_structure`. Falta revisión
fresca de esta implementación y endurecer cualquier defecto que encuentre.

## 11. Inventario del WIP a preservar

Modificados antes de escribir este relevo:

```text
docs/reference/cp-scale/README.md
docs/reference/cp-scale/current_state.json
handoff.md
src/packet_tracer_mcp/infrastructure/execution/poe_delivery_runtime.py
tests/test_cp_scale_canonical_voice_evidence_ledger.py
tests/test_cp_scale_current_state.py
tests/test_positive_voice_handoff.py
```

Nuevos antes de este relevo:

```text
docs/reference/cp-scale/canonical-live-evidence/poe-acquisition-20260906T211432-df79fafe-diagnostic.json
docs/reference/cp-scale/canonical-live-evidence/poe-acquisition-df79fafe-images/  (6 PNG)
tests/test_poe_factory_structure.py
```

Este relevo añade este Markdown y su enlace en README. Son cambios de la
sesión, no basura ajena. Revisar/stagear por rutas explícitas; nada de
`git add -A`, reset/checkout destructivo, edición de otro checkout o push a otro
remote. Puede haber cambios concurrentes nuevos al retomar: volver a inspeccionar.

## 12. Validación exacta, hecha y pendiente

Hecha previamente en el WIP de gobernanza: 62 tests passed, un warning de
permiso de `.pytest_cache` (no fallo de producto).

Hecha al preparar el relevo, sobre gobernanza + nuevo diagnóstico juntos:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_poe_factory_structure.py tests/test_poe_delivery_runtime.py tests/test_cp_scale_current_state.py tests/test_positive_voice_handoff.py tests/test_cp_scale_canonical_voice_evidence_ledger.py tests/test_poe_delivery_provider.py tests/test_worktree_isolation.py -q -o cache_dir=tmp/pytest-cache --basetemp tmp/poe-handoff-validation
```

Resultado: **99 passed in 5.95s**, sin warnings en esta ejecución.
`git diff --check` pasó; solo avisos informativos Git de futura conversión
LF→CRLF. Se comprobó el hash del agregado nuevo. La rederivación offline volvió
a dar Router0 `admission_before=false`.

También se ejecutó `graphify update .` al cerrar el relevo: exit 0, índice
actualizado a 12530 nodos, 41240 aristas y 386 comunidades. Avisó de 44 archivos
sin nodos AST y etiquetas de comunidades desactualizadas; no se lanzó extracción
semántica ni `graphify label` con LLM. El grafo es navegación, no autoridad PoE.
Se comparó además `last_live_state` con HEAD: permanece estructuralmente intacto.

Pendiente para source nuevo: tests afectados más amplios, FULL pytest,
revisión fresca, commit/push exacto y Actions 4/4 del nuevo SHA.
La prueba de aislamiento estático NO sustituye la
prueba de aislamiento en el proceso que vaya a mutar Packet Tracer.

## 13. Entorno y seguridad para retomar

Interpreter obligatorio: `./.venv/Scripts/python.exe` de ESTE worktree.
No `python` de PATH ni `.venv` del checkout principal, no `PYTHONPATH` personalizado.
Antes de mutación, comprobar en el mismo proceso:

```text
sys.executable == interpreter local
packet_tracer_mcp.__file__ dentro del checkout
exactamente uno de packet_tracer_mcp / src.packet_tracer_mcp en sys.modules
```

Tests usan `src.packet_tracer_mcp`; producción `packet_tracer_mcp`. No mezclar
enums/módulos de ambos namespaces.

Packet Tracer esperado: `9.0.1.0858`. Al preparar el relevo, Get-Process aún
mostraba PIDs 16184 y 32992. NO tomar esos PIDs ni su existencia como un preflight
fresco. La inspección global de command lines con Get-CimInstance devolvió
Acceso denegado en el sandbox; no se afirma un inventario global de procesos
Python por esa consulta. Los cuatro episodios propios sí tienen cierres
persistidos, y no se inició un nuevo runner en esta fase de relevo.

Último baseline gobernado: 0 dispositivos SEMÁNTICOS, 0 links, Realtime.
Puede aparecer `Power Distribution Device0`, objeto backend-managed sin puertos
que el inventario productivo excluye semánticamente. No borrar objetos internos
por suposición. Confirmar que no hay dispositivos/links temporales reales.

Canonical `.pts`:

```text
C:\Users\Andres\Downloads\V5.2.pts
SHA256 175f775560af7c17348c3d20cffc81ae5dc8d294d2486cc9e8409fbead8bc071
```

Bridge: `PacketTracerHttpTransport`, authenticated/fresh; no exponer token.
Usar `PacketTracerLiveFileGuard` + `PacketTracerLiveSessionSafety` antes de
fixtures y finalizar safety ANTES de persistencia positiva. Cada futura
mutación exige HEAD==upstream remoto exacto, worktree limpio, CI exacta verde,
build, aislamiento, bridge, baseline semántico, Realtime y `.pts` verificados.

El reporte anterior de Claude sobre dos reproducciones sin crash es historia
aportada por el usuario, no medición nueva de esta sesión. Conservar
`poe-live-1788719834` y los tres dumps en `%LOCALAPPDATA%\CrashDumps`.
No limpiar dumps ni reverse-engineering. `C:\CrashDumps` vacío en aquel reporte
no anula los dumps previos ni la decisión positiva cerrada.

## 14. Harness existente y continuación concreta

Harness operador ignorado, conservar y leer antes de usar:

```text
tmp/router0_poe_acquire.py
```

Sin `--execute`: rederivación offline. Grupos actuales:
`mls3`, `mls4`, `mls56`, `mls6`. Con `--execute`: gates exactos, disposable,
fixture gobernado, callback humano, cleanup/safety/snapshot, recompose.

Al emitir `CAPTURE_PENDING`, escribe `capture-request.json` con run identity,
fingerprint, ventana y bindings. Espera un nombre de archivo de recibo por stdin
o `abort`. El timeout devuelve None y limpia; no extenderlo con sleeps/retries.
`receipt.json` debe estar dentro de la carpeta del run y validar como
`PoEVisualCaptureReceipt`: identidad, fingerprint, observador, captured_at,
método, simultaneidad y observaciones por binding. No fabricar campos de
readiness/settled ni declarar simultaneidad solo porque varias capturas existen.

Siguiente acción técnica:

1. Leer AGENTS y verificar el WIP contra este relevo. Revisar el pequeño método
   de diagnóstico, especialmente las firmas Cisco, fallos cerrados y la
   separación descriptor/instancia/PoE. No cambiar el planner para eludirlo.
2. Tras checks apropiados, consultar `observe_factory_structure("AccessPoint-PT",
   module_type=31)` usando el transporte productivo, con aislamiento y bridge
   fresco, registrando source SHA + dirty diff/hash y observación before/after.
   Es SOLO LECTURA, no una qualification ni una mutación. No usar JS crudo.
3. Interpretar esa respuesta solo como estructura de fábrica. Un error o API
   ausente es diagnóstico unobservable; ausencia de un adaptador en metadata
   no basta para declarar incapacidad PoE. Si existe una fuente removible,
   observar identidad/slot instalado exacto y documentar una intervención
   legítima; no sustituirla por apagar todo el dispositivo.
4. Resolver causalmente el aislamiento AP y la pista de power deny del 3650.
   Cualquier cambio real del qualifier/provisión requiere RED→fix mínimo→
   focused/affected/full→revisión→commit/push cisco→CI verde antes de mutar.
5. Coordinar capturas humanas ya con la carpeta conocida, recoger un recibo
   completo DENTRO del boundary de una qualification informativa, limpiar,
   persistir por el mecanismo gobernado y volver a resolver. No repetir un
   episodio idéntico sin cambio causal.
6. Solo al admitir el producto: congelar SHA limpio con CI exacta y ejecutar
   `tools/cp_scale_canonical_live.py` por su pipeline canónico existente,
   detenerlo en Router0, nunca Router3. Releer CLI/contratos antes de invocarlo;
   este relevo no proporciona flags inventados.

No arrancar una nueva ventana de captura solo por el “Listo” histórico: el
operador pidió este relevo y puede no estar frente a PT en la próxima sesión.
La coordinación de evidencia no es pedir permiso otra vez.

## 15. Informe de continuación exigido por el usuario

```text
POE_DEMAND
QUALIFICATION_PLAN
AUTOFIX
POE_LIVE_RUNS
VERIFIED_BINDINGS
SIMULTANEOUS_CAPACITY
REMAINING_GAPS
ROUTER0_ADMISSION
ROUTER0_LIVE_RUN_ID
ROUTER0_RESULT
FIRST_CONTRADICTED_BOUNDARY
CLEANUP
FINAL_HEAD
GITHUB_ACTIONS
DECISION
NEXT_ACTIVE_STEP
```

Estado al pausar: adquisición incompleta, sin nuevo positivo, sin limitación
física final demostrada, Router0 no admitido/no ejecutado, cleanup de episodios
cerrado, diagnóstico de fábrica offline implementado pero todavía NO consultado
en PT. La próxima sesión retoma allí, no en análisis de dumps ni en otra
repetición ciega de fixtures.
