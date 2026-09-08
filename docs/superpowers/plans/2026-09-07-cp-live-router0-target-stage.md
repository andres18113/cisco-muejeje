# CP-LIVE Router0: contrato incremental y cierre propio

## 1. Base, alcance y admisión

Trabajar en `cplive-ripv2`, branch `feature/runtime-ripv2`, baseline
`999a09f295c364feeb0037182e2730ef158ead15`, usando exclusivamente su `.venv`.

La inspección productiva realizada encontró `PRODUCT_ADMISSION=BLOCKED`: 72
snapshots, capacidad PoE simultánea acreditada de 1 para `3560-24PS` y `UNKNOWN`
para `3650-24PS`. La composición queda unresolved, sin E5, y Router0 no puede
proyectarse. Estos valores describen esa observación; no son constantes del
producto. Los 45 tests existentes seleccionados pasan y el worktree está limpio.

- Archivar el rechazo prelive con SHA, build, intérprete, namespace, hashes del
  store y carencias exactas. No modificar la autoridad histórica del último LIVE.
- Preparar los contratos y runner offline. No abrir LIVE ni ejecutar probes
  mientras la admisión productiva permanezca bloqueada.
- Antes del LIVE, repetir la composición canónica completa y la proyección
  Router0 con el store productivo del checkout. Rechazar evidencia insuficiente,
  corrupta o incompatible.
- No promover fixtures sintéticas ni extrapolar capacidades entre puertos,
  modelos o builds. Adquirir nuevas capacidades PoE queda fuera de esta entrega.

## 2. Contrato del baseline y ausencia de replay

Añadir tests específicos de `floor3 → router0-branch` sobre los compositores y
proyectores productivos.

| Assertion del baseline | Valor |
| --- | ---: |
| Devices / links acumulativos | 290 / 202 |
| Dispositivos realmente nuevos | 58 |
| Records del physical delta | 59 |
| Módulos nuevos / links nuevos | 0 / 42 |
| Configuration: nuevas / retained | 84 / 328 |
| Control plane: nuevas / retained | 40 / 160 |
| Voice: nuevas / retained | 45 / 89 |
| Teléfonos nuevos / acumulativos | 20 / 62 |
| AP nuevos / demanda PoE | 3 / 0 |

- Router0 será el único ancla existente del delta. No recrearlo ni reinstalar su
  `NM-4A/S`.
- Los switches nuevos serán MLS3–MLS7. Congelar la igualdad completa de las
  acciones retained.
- Control plane añadirá 5 acciones de spanning tree y 35 de puertos edge;
  ninguna `ConfigureRipv2`. Verificar nuevamente los tres procesos RIPv2 y el
  dominio MULTILAYER con MLS3 primary y MLS7 secondary.
- Voice conservará las 89 acciones anteriores. Su capacidad CME se derivará del
  intent; el baseline deberá producir 20 teléfonos y 20 extensiones para Router0.
- `VoicePlan` deberá enlazar los hashes E4/E5 exactos del stage.

Separación obligatoria: los números anteriores pertenecen a assertions del
baseline. El runner calculará inventarios, diferencias, capacidades esperadas y
cobertura desde los planes y resultados tipados. No añadir gates operativos como
`devices == 290` o `phones == 62`.

## 3. Forwarding gobernado por el plan

Extender `CPScaleCanonicalStageProjection` con `branch_forwarding_checks`, una
colección tipada de comprobaciones por dirección. Cada elemento identificará
dirección, dispositivo origen, destino resuelto, IPv4 y acción E5 que acredita
esa dirección.

- Resolver Large→Multilayer y Multilayer→Large durante la composición del
  contrato Router0, utilizando la topología y configuration del propio stage.
- Extraer y reutilizar la selección semántica de destinos del compilador de
  control plane. Conservar su orden determinista; evitar duplicar esa política en
  el runner.
- Para el cierre Router0, exigir un endpoint estático representativo del sitio
  destino, presente y enlazado en la topología. Si no puede resolverse, rechazar
  el contrato; no sustituir silenciosamente esa prueba por un ping al router.
- El runner consumirá `projection.branch_forwarding_checks` y ejecutará ping
  tipado. No elegirá destinos por nombre, posición o literales IP.
- Vincular la evidencia de cada dirección a los hashes E4/E5, identidad origen,
  destino despachado y resultado fresco.
- Mantener separados los probes existentes del routing core.

`172.18.30.2` y `172.16.30.2` serán únicamente assertions del baseline. Añadir
un test que cambie válidamente el direccionamiento E5 y demuestre que el plan y
el dispatch utilizan las nuevas direcciones. El recorrido full-scale conservará
su comportamiento; las comprobaciones adicionales se exigirán para el cierre
solicitado de Router0.

## 4. Semántica terminal propia

Añadir al runner:

```text
--target-stage {full-qualification,router0-branch}
```

Default: `full-qualification`. Añadir el parámetro opcional equivalente a
`run()`, manteniendo compatibilidad con sus llamadas existentes.

Router0 tendrá dos estados explícitos:

```text
ROUTER0_BRANCH_VERIFIED_PRECLEANUP
ROUTER0_BRANCH_VERIFIED_AND_CLEANED
```

El segundo será su único cierre exitoso, con alcance `router0-branch`. No
reutilizar las etiquetas de full-scale ni clasificar esta terminación como abort.

- Rechazar opciones inválidas y Router0 combinado con retención antes de
  contactar PT.
- Mantener los checkpoints y gates previos.
- Tras verificar Router0, sus dos direcciones de forwarding y el workspace dos
  veces, cerrar automáticamente sin solicitar otro `continue`.
- Archivar precleanup → eliminar dispositivos propios → comprobar baseline dos
  veces → verificar Realtime → archivar cleanup → publicar resultado → retornar
  0.
- No entrar en Router3, remaining ni full qualification.
- Registrar delta físico y resultados parciales antes de validar condiciones que
  puedan lanzar una excepción.
- Ante contradicción o fallo de archivo/restauración, preservar la primera
  frontera fallida y ejecutar cleanup pendiente. Nunca publicar éxito anticipado.

Configuration conservará el contrato vigente acordado: aceptación gobernada y
estados `PARTIAL/UNOBSERVABLE` explícitos donde existen límites medidos. No
promoverlos a `VERIFIED`.

## 5. Validación, LIVE y entrega

Escribir primero tests causales para los comportamientos nuevos:

- Batches y journals sólo contienen mutaciones del delta; la verificación sigue
  siendo acumulativa.
- Acciones retained alteradas, resultados incompletos, IDs duplicados y hashes
  incompatibles son rechazados.
- El runner, probado en subprocess aislado, termina exitosamente en Router0 con
  la secuencia correcta y sin etapas posteriores.
- El default full-scale permanece igual.
- Probar fallo en cada dirección de forwarding, destinos no resolubles, evidencia
  obsoleta, archivo precleanup, cleanup y cada comprobación de restauración.
- Los tests deben ejercitar llamadas y resultados, no limitarse a buscar cadenas
  en el source.

Completar:

```text
focused
→ affected
→ full
→ diff review
→ graphify update .
→ commit
→ push
→ exact-SHA CI 4/4
→ clean worktree
```

Usar `.venv/Scripts/python.exe`, sin `PYTHONPATH`, y token aislado para tests.
Exigir los cuatro jobs de Windows/Ubuntu × Python 3.11/3.13 para el SHA que
ejecutará LIVE.

Sólo con admisión productiva y gate offline aprobados, ejecutar una única sesión:

```text
routing-core → router4-switch10 → floor1 → floor2 → floor3 → router0-branch
```

Demostrar aislamiento en el mismo proceso que mutará. Cerrar Router0 con physical
VERIFIED, configuration aceptada bajo el contrato acordado, todos los teléfonos
previstos VERIFIED, control plane y MULTILAYER PVST VERIFIED, core sin regresión,
forwarding en ambas direcciones y restauración verificada dos veces.

Publicar evidencia y auditoría en un commit posterior separado, conservando el
SHA ejecutado y dejando el worktree limpio. La auditoría comparará planes,
dispatches y journals para acreditar `NO_MUTATION_REPLAY`.

Mientras PoE siga bloqueado:

```text
PRODUCT_ADMISSION=BLOCKED
ROUTER0_LIVE=NOT_RUN
```

El DoD global permanece pendiente. Tras cierre y auditoría exitosos:
`NEXT=ROUTER3_BRANCH`.
