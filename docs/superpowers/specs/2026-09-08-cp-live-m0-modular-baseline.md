# CP-LIVE M0: fronteras modulares y baseline de equivalencia

## Decisión y alcance

Este documento nació como la especificación normativa de CP-LIVE M0 y
consolida el mapa de extracción, los contratos, la matriz de caracterización y
la procedencia del oráculo. La autorización posterior de M1 añade aquí el
resultado de la primera extracción. La autorización posterior de M2 reemplaza
el mapa de fases provisional: **M2-A es ejecución de etapas** y **M2-B es
coordinador, ciclo de sesión y CLI**. M3 fue autorizado después para el cierre
e integración offline descritos al final; no autoriza LIVE ni cambia admisión.

M0 se entregó primero como **`BLOCKED_FOR_BASELINE_FIX`**: la
caracterización reprodujo un defecto anterior a la extracción en la
finalización de `run()`. Bajo la fase autorizada **M0-FIX** ese defecto está
corregido, las reproducciones causales están verdes y la referencia de
equivalencia se volvió a registrar como `baseline-v2`, con `baseline-v1`
conservado como histórico. El resultado de M0 es ahora
**`CORRECTED_BASELINE_RECORDED`**.

M0-FIX tocó exactamente tres superficies: la finalización de
`tools/cp_scale_canonical_live.py`, los tests y el harness de M0, y la
preparación de CI. Una segunda pasada autorizada cerró la finalización frente a
interrupciones durante cleanup/archivo/relectura, completó la captura del
oráculo y extendió la procedencia del registro a las reglas realmente
ejecutadas; la referencia pasó a `baseline-v3` y `v1`/`v2` quedan como
histórico. M1 añade sólo contratos/coordinación del preflight local bajo `src`,
lectores locales en infrastructure y la llamada compatible desde `tools`; no
modifica `EXTENSION/`, snapshots de capacidades, evidencia LIVE ni gates. No se
abrió Packet Tracer, no se conectó al bridge y no se ejecutó el runner con
transporte real. La admisión productiva sigue `BLOCKED`. M2-A y M2-B quedan
autorizadas únicamente offline bajo los límites de esta especificación.

La consolidación offline de Task 4 (2026-09-09) verifica las extracciones ya
revisadas de M2-A/M2-B mediante arquitectura, un segundo escenario no canónico
y medidas 1/2/4, sin modificar sus mecanismos. Los resultados y SHAs vigentes
están en «Consolidación offline M1/M2 y prueba de reutilización» al final. Las
secciones de inventario y baseline M0 conservan su contexto histórico.

## Fuente, aislamiento y autoridad vigente

| Concepto | Valor comprobado en M0 |
| --- | --- |
| Repositorio esperado | `andres18113/cisco-muejeje` |
| Remoto correcto | `cisco = https://github.com/andres18113/cisco-muejeje.git` |
| `origin` | apunta a otro repositorio; no se utilizó como autoridad |
| Referencia | `cisco/feature/runtime-ripv2` |
| `HARDENING_BASE_SHA` | `62db3cea84a4bfca1a5bcd3d2389d62864c45946` |
| Árbol fuente | `5c778273445307fa208f207e421f0f5b8dab2de8` |
| Divergencia tras `fetch` | referencia y SHA remoto iguales; `0/0` |
| Worktree | el worktree aislado recibido, sin limpiar cambios ajenos |
| Rama M0 | `refactor/cp-live-m0-baseline` |
| Intérprete | `.venv/Scripts/python.exe`, CPython 3.12.10 |
| Namespace de pytest | sólo `src.packet_tracer_mcp` en el proceso padre |
| Namespace de probes productivos | sólo `packet_tracer_mcp` en subprocess |

M0-FIX continuó sobre la misma rama, desde
`8ba24fe7896114eeab15eeacff84d928c02e0a5f`, con la `.venv` local del checkout
(Linux, CPython 3.11.15). Los dos namespaces se siguen comprobando, y ahora
cada probe los reporta él mismo en su sección `provenance`: el proceso de
pytest nunca carga `packet_tracer_mcp` y cada hijo carga sólo ése.

Los datos históricos del relevo y los datos reproducidos se mantienen
separados:

| Evidencia | Reportada en el relevo | Reproducida en M0 | Reproducida en M0-FIX |
| --- | --- | --- | --- |
| Suite completa del baseline | `4147 passed` | `4147 passed, 3 warnings` en 128.83 s | ver «Registro reproducible» |
| CI | run `34181547224`, Windows/Ubuntu × 3.11/3.13 | no se lanzó ni se presenta como ejecución M0 | run del SHA final de la rama, 4/4 |
| Admisión productiva | `BLOCKED` | no se volvió a adquirir evidencia ni se alteró el gate | sin cambios: no se tocó el gate |
| Router0 LIVE | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

M0-FIX se ejecutó en un entorno distinto del que registró `baseline-v1`
(Linux, CPython 3.11.15, frente a Windows 11 y CPython 3.12.10). Esa diferencia
queda en la procedencia del artefacto, no se normaliza, y no altera las trazas
comparables: son órdenes de coordinación bajo dobles, sin rutas ni relojes.

El techo del claim continúa sin cambios: `3560-24PS` sólo tiene evidencia para
un puerto, insuficiente para los conjuntos simultáneos; `3650-24PS` permanece
`UNKNOWN`; la composición canónica productiva está incompleta y Router0 no es
proyectable. Los fixtures sintéticos de M0 no tienen autoridad productiva.

## Navegación e inventario

`graphify-out/graph.json` existe. La navegación comenzó con consultas sobre el
runner, su cierre y el replay, y después se contrastó cada relación importante
con source y tests. `graphify path` no resolvió de forma inequívoca la relación
entre `run` y `_execute_stage`; la llamada directa se confirmó en
`tools/cp_scale_canonical_live.py`. No existe
`graphify-out/wiki/index.md`, por lo que la navegación amplia continuó con el
árbol y búsquedas estáticas. Los archivos generados del grafo no son evidencia
de comportamiento runtime.

Inventario general relevante:

- `src/packet_tracer_mcp/domain/`: planes y resultados tipados; las políticas
  de validación siguen fuera de los modelos.
- `src/packet_tracer_mcp/application/use_cases/`: composición, proyección,
  applicators, reconciliación, cualificación y reglas de autoridad.
- `src/packet_tracer_mcp/infrastructure/`: transporte HTTP y file mailbox,
  runtimes PT, observadores, parsers y store de capacidades.
- `src/packet_tracer_mcp/adapters/`: hoy no contiene la entrada CP-LIVE; será
  el destino aprobado de la adaptación CLI.
- `tools/cp_scale_canonical_live.py`: entrada, composition root, coordinador,
  ejecutor de stage, observación, diagnóstico, persistencia y cierre actuales.
- `tests/`: consumidores directos de funciones privadas, subprocess probes y
  las referencias test-only de M0.
- `docs/reference/cp-scale/`: autoridad vigente y evidencia histórica. M0 sólo
  la leyó.
- `EXTENSION/`: fuera de alcance y sin cambios.

El camino transitivo actual es:

```text
main()
  -> valida --execute y argumentos
  -> run()
     -> target contract + identidad/evidencia inicial
     -> import isolation + Git/upstream/dirty + proceso PT
     -> una PacketTracerHttpTransport
     -> un runtime físico + baseline
     -> CapabilitySnapshotStore + composición + probes requeridos
     -> una instancia de cada runtime configuration/control-plane/voice
     -> por stage: proyección -> delta/deploy -> reconciliación
        -> _execute_stage -> checkpoint
     -> cierre Router0, o remaining -> full qualification -> disposición
     -> archive -> cleanup/restauración -> evidencia/checkpoint -> stop
```

`FileBridge` sólo se consulta como dato lateral si el HTTP no obtiene polling;
no sustituye al transporte HTTP. `CapabilitySnapshotStore` usa
`GOVERNED_ROOT/data/capabilities`. La evidencia mutable va a `data/cp-scale`,
el checkpoint terminal a `docs/reference/cp-scale` y los archivos inmutables a
`canonical-live-evidence`.

## Mapa de responsabilidades de M0 (histórico)

La columna «autoridad» indica qué decisión puede producir la responsabilidad;
«ninguna» significa que no puede promover aceptación o `VERIFIED`.

| ID | Responsabilidad y símbolos actuales | Entradas → salidas | Estado, efectos y autoridad | Consumidores y cobertura |
| --- | --- | --- | --- | --- |
| R1 | Entrada y composición de dependencias: `main`, `run` y los constructores concretos en `tools/cp_scale_canonical_live.py` | argv y cuatro argumentos de `run` → código `int` | Lee reloj, entorno y rutas; crea transporte/runtimes/store; `main` autoriza la entrada por `--execute`, pero no verifica red | invocación CLI; `test_cp_scale_router0_live_runner.py`; `test_cp_scale_router0_target_stage.py`; oracle M0 |
| R2 | Admisión/preflight: `canonical_cp_scale_target_contract`, `ImportIsolationPreflight.ensure_isolated`, `read_git_repository_state`, `_git_output`, `_governed_source_changed`, `_packet_tracer_processes`, `packet_tracer_process_error`, `compose_cp_scale_canonical`, `canonical_required_capability_probes` | request + repo/entorno/store → hard stop o composición válida | Lee imports, Git, procesos, store y probes; puede emitir hard stop o rechazo de composición; sólo los resultados productivos, nunca fixtures M0, tienen autoridad | `test_worktree_isolation.py`, `test_import_isolation_preflight.py`, runtime-gate tests y escenario `admission-rejected` |
| R3 | Vida de sesión: bloque `run` que instancia `PacketTracerHttpTransport`, `PacketTracerPhysicalTopologyRuntime` y los runtimes E5/E9/Voice | request admitida → recursos vivos de una sesión | `start/stop`; el ownership físico es local a las instancias; ninguna autoridad de aceptación por sí solo | runner subprocess tests; `test_e95_packet_tracer_physical_runtime.py` |
| R4 | Coordinación de stages: bucle de `run`, `_full_qualification_projection`, `_complete_router0_target` | target contract + composición + continuidad → stages alcanzados y finalización | Muta la topología mediante deploy/reconcile, conserva instancias y decide dónde detenerse; compone autoridades existentes, no crea otra política | tests Router0/default; oracle `router0-cleanup`, `full-cleanup`, `full-retain`, `floor2-failure` |
| R5 | Ejecución interna: `_execute_stage`, `_stage_voice`, applicators y reconciliador existentes | proyección, delta, runtimes, resultados retenidos y observaciones previas → evidencia de stage, manifest, workspace, configuration | Solicita mutaciones físicas/E5/E9/Voice y lecturas; puede producir estados tipados, primera frontera y auditoría; no debe confundir aceptación E5 con estado `VERIFIED` | `test_cp_scale_live_failure_evidence.py`, `test_cp_scale_voice_staging.py`, application tests E5/E9/Voice |
| R6 | Observaciones obligatorias: `_wait_for_serial_interfaces`, `_wait_for_core_forwarding`, `_wait_for_site_forwarding`, `_network_state_observation`, observaciones dobles de workspace y Realtime | planes/expectativas + runtimes → evidencia fresca y atribuida | IOS/ping/bridge reads y probes operacionales; sus fallos bloquean la etapa o el cierre; pueden respaldar `VERIFIED` sólo bajo la regla dueña | failure-evidence, realtime-STP, frame-observer, Router0 forwarding y runtime-gate tests |
| R7 | Diagnóstico posterior al fallo: `_post_failure_simulation_diagnostic`, `_bounded_simulation_progression`, `_frame_observer_discovery` | fallo ya establecido + escena aún viva → registro diagnóstico | Puede entrar y avanzar Simulation y debe restaurarla: **no es read-only**. No cambia status, aceptación ni autoridad; fallo diagnóstico es secundario | `test_cp_scale_sim_time_diagnostic.py`, `test_frame_observer_probe.py`, failure-evidence diagnostics |
| R8 | Serialización mutable: `_write_evidence`, `_write_checkpoint_summary` | estado interno → JSON y reemplazo atómico | Crea directorios, escribe, `fsync`, `os.replace`; ninguna autoridad, aunque su éxito sea gate de publicación | failure-evidence checkpoint tests; oracle M0; reproducción roja de escritura |
| R9 | Archivo inmutable: closure local `archive` + `archive_cp_scale_canonical_evidence` | payload + identidad + fase → `CPScaleEvidenceArchive` | Escribe archivo confinado y recibo/digest; ninguna promoción independiente; su fallo es secundario o impide publicar cierre | `test_cp_scale_live_qualification.py`, `test_cp_scale_router0_live_runner.py`, escenarios de archivo M0 |
| R10 | Checkpoints: `_checkpoint`, `canonical_checkpoint_repository_error`, `canonical_final_disposition` | stage/evidencia + stdin + estado Git fresco → continue/retain o fallo | Escribe antes de preguntar, relee Git y fuente; el operador autoriza continuar/retener, pero no concede `VERIFIED` | runtime-gate tests, runner tests y `operator-abort` |
| R11 | Ownership físico: `_attempted_device_ids`, `owned_device_ids`, manifests y estado interno de `PacketTracerPhysicalTopologyRuntime` | resultados de deploy → IDs intentados de esta sesión | Acumula exactamente lo intentado; autoriza sólo el alcance de cleanup, nunca borrar por plan/nombre | physical-runtime tests, delta/replay tests y runner cleanup |
| R12 | Cleanup/restauración: `_cleanup_owned`, `canonical_cleanup_restoration_error`, observación Realtime y attestation | ownership + topología + baseline → mutaciones de borrado + dos inventarios + estado de restauración | Muta recursos propios y observa dos veces; puede acreditar restauración, no la cualificación de red | runtime-gate cleanup, runner terminal, escenarios `cleanup-failure` y `restoration-observation-failure` |
| R13 | Resultado/cierre: `except/finally` de `run`, escritura final y `transport.stop` | resultado primario + fallos secundarios → código y registro observables | Intenta el cierre exactamente una vez, siempre que se adquirió, y conserva la causa primaria; sin causa primaria, un fallo de finalización impide el éxito. Corregido en M0-FIX | doce casos en `test_cp_live_m0_finalization_invariant.py` |
| R14 | Políticas reutilizadas: compositores/proyectores, `ConfigurationApplicator`, `ControlPlaneApplicator`, `VoiceApplicator`, `canonical_stage_mutation_replay_audit` | planes y resultados tipados → aceptación, estados y auditorías | Son la única autoridad de sus dominios. No se duplican al modularizar | target-stage, configuration, control-plane, voice y oracle de política |

### Propiedad propuesta y fase autorizada

| ID | Propietario propuesto | Dependencias permitidas | Fase autorizada |
| --- | --- | --- | --- |
| R1 | `tools/...` conserva `main`, `run`, presentación y composition root; request tipado en `application/cp_scale_live` | application contracts/preflight e infrastructure readers | M1 para request/preflight; adapter y façade al mover el coordinador en M2-B |
| R2 | `application/cp_scale_live/admission.py` con puertos de entorno | reglas existentes de application/domain; implementaciones de Git/proceso/import en infrastructure | primera familia de M1 |
| R3 | `infrastructure/execution/cp_scale_live_session.py`, único dueño de `close` | transporte/runtimes concretos; no políticas | M2-B, después de M2-A |
| R4 | `application/cp_scale_live/coordinator.py` | contratos, admission, stage executor y puertos estrechos | M2-B |
| R5 | `application/cp_scale_live/stage_executor.py` | applicators, proyectores, validadores y protocolos runtime existentes | M2-A |
| R6 | `infrastructure/observation/cp_scale_live.py` | IOS parsers, typed ping, frame/runtime adapters | M2-A |
| R7 | `infrastructure/diagnostics/cp_scale_live.py` | Simulation/frame adapters; sin acceso a decisiones | M2-A |
| R8–R9 | `infrastructure/persistence/cp_scale_live.py` | filesystem + serializadores de contratos | M2-B |
| R10 | puerto application `CPScaleCheckpointPort`; adapter de consola | estado/provenance tipados, sin runtimes | M2-B |
| R11–R12 | coordinator + servicio application de cleanup; runtime físico ejecuta | ownership ledger, topología y protocolo físico | M2-B |
| R13 | session owner para cierre; coordinator para precedencia de resultados | result/finalization contracts y persistence port | fix aplicado en M0-FIX; extracción M2-B |
| R14 | permanece donde está | contratos domain/application existentes | se reutiliza desde M2-A/M2-B; no se extrae ni duplica |

`execute_enterprise_reference()` y `_ExecutionState` son precedentes útiles para
resultados tipados, diagnóstico separado y cleanup por ownership. No pueden
invocarse una vez por stage: cada llamada ejecuta su propio cleanup antes de
devolver y destruiría la continuidad física que CP-LIVE necesita.

## Arquitectura objetivo aprobada

El destino, alcanzado offline en M2-B con el coordinador bajo `src`:

```text
tools/cp_scale_canonical_live.py  (façade compatible)
                  |
                  v
adapters/cli/cp_scale_live.py     (parseo, composición, presentación)
             |                 \
             v                  v
application/cp_scale_live/*  <-- ports -- infrastructure/*
             |
             v
use cases, applicators, validators y modelos existentes
```

Antes de M2-B, mientras el coordinador seguía en `tools`, la forma intermedia
correcta conservaba `main`/`run` en `tools` y **llamaba** a las piezas extraídas.

```text
tools/cp_scale_canonical_live.py  (entrada + composition root + coordinador)
                  |
                  v
application/cp_scale_live/*  <-- ports -- infrastructure/*
```

Reglas de dependencia:

1. `tools` puede depender de `src`; ningún archivo bajo `src` depende de
   `tools`. De ahí se sigue la regla que M1 tenía mal: `tools` sólo puede
   convertirse en façade cuando aquello a lo que reenvía ya vive bajo `src`.
   Una façade que siga alojando al coordinador obligaría al adapter a importar
   `tools`, que es exactamente el ciclo que estas reglas prohíben.
2. El adapter es el composition root y puede conocer implementaciones de
   infrastructure. Application sólo conoce contratos y puertos.
3. Domain no depende de application, infrastructure, adapters ni tools.
4. Infrastructure implementa puertos; no llama al coordinador.
5. No hay ciclo entre coordinator, stage executor, observation, diagnostics y
   persistence.
6. La sesión usa una sola instancia de transporte y las mismas instancias de
   runtime físico, E5, E9 y Voice desde `start` hasta `close`.
7. `PacketTracerCPScaleSession` es el único propietario de `close`. Un bundle
   de recursos de sesión no es un contexto de negocio: contiene sólo recursos
   ligados al lifecycle y no expone store, checkpoints, reloj, request ni
   estado de progreso.
8. No se introduce workflow framework, event bus, event sourcing ni una segunda
   política de aceptación.
9. Los contratos internos son tipados. `dict`/JSON sólo aparecen al escribir,
   archivar o presentar.

### Mecanismos, políticas CP-SCALE y adaptadores PT

La extracción sólo es reutilizable si estas tres cosas dejan de estar mezcladas.
La clasificación decide qué puede moverse, qué se inyecta y qué queda detrás de
un puerto.

| Clase | Qué es | Piezas actuales | Regla |
| --- | --- | --- | --- |
| Mecanismo | Coordinación sin conocimiento del dominio CP-SCALE ni de Packet Tracer | vida de sesión y `close` (R3), bucle de stages y precedencia de resultados (R4, R13), persistencia/archivo (R8–R9), puerto de checkpoint (R10), ledger de ownership (R11) | Puede extraerse y reutilizarse. Recibe políticas y adaptadores por parámetro; nunca los nombra |
| Política CP-SCALE | La decisión canónica concreta: qué se construye, qué se acepta y qué cierra | target contract y orden de stages, autoridad de forwarding, `canonical_stage_configuration_error`, replay audit, `canonical_cleanup_restoration_error`, probes de capacidad requeridos, nombres de closure | No se extrae, no se duplica y no se reimplementa. Se sigue invocando donde ya vive (R14) |
| Adaptador PT | Cómo se le habla a Packet Tracer | transporte HTTP y `FileBridge`, runtime físico, runtimes E5/E9/Voice, parsers IOS, typed ping, Simulation/frame, store de capacidades | Vive en infrastructure detrás de puertos nombrados. Ni el mecanismo ni la política conocen `send_and_wait` |

Consecuencias que ya se aplican en este documento:

- un mecanismo que necesite leer una regla CP-SCALE para decidir no es un
  mecanismo: es política mal ubicada;
- un puerto que exponga `execute(kind, dict)` no es un adaptador: es un bus
  genérico, y la regla 8 lo prohíbe;
- «reutilizable» no se declara: se demuestra con los criterios de la sección
  «Criterios de reutilización».

### Preflight local, comprobación de backend y admisión productiva

Son tres decisiones distintas, con autoridad distinta, y confundirlas es cómo
una sesión sintética terminaría pareciendo una admisión. El orden es estricto:
ninguna de ellas implica la siguiente.

| Decisión | Qué comprueba | Efectos | Resultado | Autoridad |
| --- | --- | --- | --- | --- |
| Preflight local | Offline y sin red: `--execute`, target contract, aislamiento de imports, Git/upstream/dirty, procesos PT presentes | sólo lecturas locales | hard stop con código `2`, o continuar | Ninguna. Sólo puede negar |
| Comprobación de backend | El PT que está corriendo: `transport.start` con polling fresco, workspace baseline descartable, probes de capacidad requeridos | abre el bridge, consulta capacidades, escribe evidencia | fallo adquirido con código `1`, o sesión utilizable | Evidencia sobre ese proceso PT. No promueve nada del producto |
| Admisión productiva | Si la composición canónica puede ejecutarse como producto | ninguno aquí: es un gate ya gobernado | hoy `BLOCKED` | La de los gates vigentes en `docs/reference/cp-scale/`. Ni M0, ni M0-FIX, ni M1 la mueven |

Un preflight verde no es un backend comprobado; un backend comprobado no es
admisión productiva. Los fixtures sintéticos de M0 alimentan sólo la primera
columna del harness y nunca las otras dos.

## Contratos propuestos en M0 e implementados en M1

Las firmas siguientes nacieron como diseño de M0. M1 implementa la primera
familia —request, identidad local y preflight— en
`application/cp_scale_live`; las familias de continuidad, stage y finalización
siguen siendo diseño para hitos posteriores. Los nombres se derivan de
consumidores concretos: argumentos actuales de `run`, metadatos ya archivados,
valores que sus callers desempaquetan y campos inspeccionados por los tests.

### Solicitud

```python
@dataclass(frozen=True)
class CPScaleLiveRequest:
    packet_tracer_version: str
    expected_head: str
    retain_on_full_verification: bool
    target_stage: CPScaleCanonicalTarget | str = CPScaleCanonicalTarget.FULL_QUALIFICATION
```

Es la traducción uno a uno de `run(...)`. `--execute` permanece como guard de
la adaptación CLI: no es una política reutilizable ni se debe convertir en un
booleano que capas internas puedan olvidar validar. El target se resuelve con
`canonical_cp_scale_target_contract`; no se reimplementa esa regla.

### Identidad inmutable de sesión

```python
@dataclass(frozen=True)
class CPScaleLiveSessionIdentity:
    run_identity: str
    started_at: datetime
    packet_tracer_version: str
    source_head: str
    source_tree: str
    branch: str
    upstream: str
    python_executable: str
    package_file: str
    loaded_namespace: str
```

Se construye sólo después de validar import isolation y Git. `source_head` es
el observado, no sólo `request.expected_head`; ambos se comparan en preflight.
`source_tree` también se lee de Git, no se deriva del worktree mutable.
`loaded_namespace` sólo puede ser `packet_tracer_mcp` en producción. La
identidad local no contiene `EnvironmentFingerprint`: antes de abrir el bridge
no existe una observación del backend que lo autorice. El fingerprint continúa
adquiriéndose donde ya lo hacía el runner, después del baseline de workspace;
M1 no lo inventa ni lo adelanta.

### Admisión: los tipos de la primera extracción, cerrados

La primera familia que M1 puede mover es request + identidad + admisión, así
que sus tipos no pueden quedar en prosa. Son cerrados: cada campo tiene tipo,
no hay `dict` de propósito general y no hay campo libre para añadir señales
más tarde sin decidirlo aquí.

El preflight actual **cortocircuita**: si el aislamiento de imports falla, no
llega a leer Git; si Git rechaza, no enumera procesos. Los tipos tienen que
poder decir «no se ejecutó» sin inventar una evidencia que nadie obtuvo, así
que cada comprobación es un resultado con estado propio y `NOT_RUN` es uno de
ellos.

```python
class CPScaleCheckState(str, Enum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"

@dataclass(frozen=True)
class CPScaleImportIsolationEvidence:
    state: CPScaleCheckState
    isolation_state: str = ""
    detail: str = ""
    error: str = ""

@dataclass(frozen=True)
class CPScaleRuntimeEvidence:
    python_executable: str = ""
    package_file: str = ""
    loaded_namespaces: tuple[str, ...] = ()
    error: str = ""

@dataclass(frozen=True)
class CPScaleRepositoryEvidence:
    state: CPScaleCheckState
    branch: str = ""
    upstream: str = ""
    head: str = ""
    upstream_head: str = ""
    source_tree: str = ""
    dirty: bool | None = None
    error: str = ""
    dirty_error: str = ""
    upstream_head_error: str = ""
    source_tree_error: str = ""

@dataclass(frozen=True)
class CPScaleProcessRecord:
    pid: int
    name: str
    main_window_handle: int
    product_version: str
    file_version: str
    executable_path: str

@dataclass(frozen=True)
class CPScaleProcessEvidence:
    state: CPScaleCheckState
    processes: tuple[CPScaleProcessRecord, ...] = ()
    error: str = ""

class CPScalePreflightOutcome(str, Enum):
    ADMITTED = "admitted"
    REJECTED = "rejected"

@dataclass(frozen=True)
class CPScalePreflightResult:
    target: CPScaleCanonicalTargetContract
    runtime: CPScaleRuntimeEvidence
    import_isolation: CPScaleImportIsolationEvidence
    repository: CPScaleRepositoryEvidence
    process: CPScaleProcessEvidence
    identity: CPScaleLiveSessionIdentity | None
    issues: tuple[str, ...]

    @property
    def outcome(self) -> CPScalePreflightOutcome:
        return (
            CPScalePreflightOutcome.ADMITTED
            if (
                not self.issues
                and all(check.state is CPScaleCheckState.PASSED for check in checks)
                and evidence_is_coherent
            )
            else CPScalePreflightOutcome.REJECTED
        )
```

Reglas de estos tipos:

1. La autorización local **se deriva del resultado completo**: continuar exige
   `import_isolation`, `repository` y `process` en `PASSED`, evidencia
   estructuralmente coherente, identidad local presente/coincidente y cero
   `issues`. `FAILED`, `NOT_RUN`, evidencia ausente o incoherente bloquean aun
   cuando `issues` esté vacío. No existe un booleano `admitted` escribible.
2. `NOT_RUN` es un estado legítimo y frecuente: es lo que queda tras el
   cortocircuito. Nunca se rellena con un valor por defecto que parezca una
   comprobación superada; una evidencia obligatoria ausente no se fabrica.
3. `issues` conserva orden y duplicados: es el texto que hoy se une con un
   espacio para `evidence["hard_stop"]`, y el adapter lo sigue traduciendo a
   código `2`.
4. `target` es el contrato que devuelve `canonical_cp_scale_target_contract`.
   La regla no se reimplementa ni se copia dentro del preflight.
5. Los procesos preservan todos los datos que consumen los validadores y la
   evidencia vigente: `Path`, `ProductVersion`, `FileVersion`, PID, nombre y
   `MainWindowHandle`. Ninguna conversión tipada los colapsa a una versión
   sintética.
6. Ninguna de estas evidencias contiene transportes, runtimes PT ni callbacks,
   así que el resultado es serializable y comparable tal cual. `started_at`
   sólo pertenece a la identidad local inmutable.
7. El preflight no abre el bridge, no consulta capacidades y no escribe
   evidencia: eso ya es comprobación de backend.

### Estado de avance y continuidad

```python
@dataclass(frozen=True)
class CPScaleLiveProgress:
    target: CPScaleCanonicalTarget
    completed_stages: tuple[CPScaleLiveStageResult, ...]
    active_stage: CPScaleCanonicalStage | None
    first_failed_boundary: str | None
    checkpoint_stage: str | None

@dataclass(frozen=True)
class CPScaleStageContinuity:
    previous_projection: CPScaleCanonicalStageProjection | None
    previous_configuration: ConfigurationApplicationResult | None
    previous_voice_action_results: tuple[ActionApplicationResult, ...]
    previous_control_plane_action_results: tuple[ActionApplicationResult, ...]
    verified_serial_topology: object | None
    verified_serial_manifest: DeploymentManifest | None
    last_workspace: PhysicalWorkspaceObservation | None
```

`CPScaleLiveProgress` no contiene servicios ni transportes. Es un snapshot
reemplazable y serializable en el límite. `CPScaleStageContinuity` contiene
únicamente valores que hoy pasan al stage siguiente; ownership, dependencias y
callbacks quedan fuera. Esto evita un `Context` con acceso universal.

### Resultado de stage

```python
@dataclass(frozen=True)
class CPScaleLiveStageResult:
    stage: CPScaleCanonicalStage
    outcome: str
    manifest: DeploymentManifest | None
    workspace: PhysicalWorkspaceObservation | None
    configuration: ConfigurationApplicationResult | None
    configuration_accepted: bool
    control_plane: ControlPlaneApplicationResult | None
    voice: VoiceApplicationResult | None
    replay_audit: CanonicalMutationReplayAudit | None
    forwarding: tuple[CPScaleSiteForwardingObservation, ...]
    required_observations: tuple[CPScaleObservationRecord, ...]
    diagnostics: tuple[CPScaleDiagnosticRecord, ...]
    first_failed_boundary: str | None
```

La separación `configuration_accepted`/`configuration.status` es intencional:
una aceptación gobernada no equivale a `VERIFIED`. `diagnostics` nunca se usa
para calcular `outcome`. Las colecciones mantienen orden y duplicados; los
journals permanecen dentro de los resultados tipados de cada dominio.

### Finalización

```python
@dataclass(frozen=True)
class CPScaleCleanupResult:
    mutations: tuple[PhysicalMutationResult, ...]
    first: PhysicalWorkspaceObservation | None
    second: PhysicalWorkspaceObservation | None
    realtime: CPScaleObservationRecord | None
    verified: bool
    errors: tuple[str, ...]

@dataclass(frozen=True)
class CPScaleLiveFinalResult:
    identity: CPScaleLiveSessionIdentity | None
    outcome: str
    target: CPScaleCanonicalTarget
    progress: CPScaleLiveProgress
    final_disposition: CPScaleFinalDisposition | None
    closure: str | None
    presentation_retained: bool
    cleanup: CPScaleCleanupResult | None
    archives: tuple[CPScaleEvidenceArchive, ...]
    primary_failure: str | None
    secondary_failures: tuple[str, ...]
```

El adapter traduce el resultado a la compatibilidad actual: éxito/retención
`0`, fallo adquirido `1`, request/preflight hard stop `2`. Si existe causa
primaria, escritura, archivo, diagnóstico, cleanup, observación o `close`
fallidos se conservan como secundarios y no la sustituyen. Si no hay causa
primaria, un fallo de finalización convierte el resultado en fallo.

Esa precedencia ya no es sólo el contrato futuro: es lo que hace hoy `run()`
tras M0-FIX, con `primary_failure` y `secondary_failures` representados por la
causa registrada y la lista `finalization_errors`. La extracción de M2-B tendrá
que conservar ese comportamiento, no inventarlo.

### Puertos necesarios

Sólo se proponen fronteras con un consumidor y un efecto distintos:

```python
class CPScaleExecutionEnvironmentPort(Protocol):
    def inspect(self, request: CPScaleLiveRequest) -> CPScalePreflightResult: ...

class CPScaleSessionFactory(Protocol):
    def open(
        self, request: CPScaleLiveRequest, identity: CPScaleLiveSessionIdentity
    ) -> CPScaleSessionResources: ...

class CPScaleCheckpointPort(Protocol):
    def decide(self, checkpoint: CPScaleCheckpoint) -> CPScaleCheckpointDecision: ...

class CPScaleEvidencePort(Protocol):
    def write_progress(self, progress: CPScaleLiveProgress) -> None: ...
    def archive(
        self, phase: str, result: object, identity: CPScaleLiveSessionIdentity
    ) -> CPScaleEvidenceArchive: ...

class CPScaleRequiredObservationPort(Protocol):
    def observe(self, request: CPScaleObservationRequest) -> CPScaleObservationRecord: ...

class CPScaleDiagnosticPort(Protocol):
    def diagnose(self, request: CPScaleDiagnosticRequest) -> CPScaleDiagnosticRecord: ...
```

Los records auxiliares no son bolsas de `dict`: `CPScalePreflightResult`
contiene `admitted`, el target contract, import/repository/process evidence y
una tupla de issues; `CPScaleCheckpoint` contiene identidad, stage, snapshot de
progreso y estado Git; su decisión es `CONTINUE`, `RETAIN` o `ABORT`.
`CPScaleObservationRecord` contiene kind, stage, provenance, status, evidence y
error. `CPScaleDiagnosticRecord` añade modo inicial/final, mutaciones
diagnósticas intentadas y restauración, pero no un campo de aceptación.
`CPScaleSiteForwardingObservation` vincula el
`CPScaleSiteForwardingCheck` original con cada intento tipado y su resultado.

El puerto de observación se implementa como operaciones nombradas, no como un
dispatcher genérico: observación de estado de red, espera serial, forwarding de
core/sitio, workspace y Realtime de cleanup. La firma abreviada anterior agrupa
la familia para mostrar la dependencia; no autoriza un `execute(kind, dict)`.

`CPScaleSessionResources` contiene sólo las instancias runtime persistentes y
un `close()` idempotente cuyo owner es la session. Los protocolos
`ConfigurationRuntime`, `ControlPlaneRuntime`, `VoiceRuntime` y el contrato
físico existente se reutilizan; no se crea un `TransportPort` genérico ni se
expone `send_and_wait` al coordinator. Observación obligatoria y diagnóstico
son puertos distintos porque tienen autoridad y efectos diferentes.

### Criterios de reutilización

Un mecanismo no se declara reutilizable: se demuestra. Los dos criterios
siguientes se definen ahora y **no se implementan en M0-FIX**; son la condición
de aceptación del hito que extraiga cada mecanismo.

**Estado acotado.** Un mecanismo cumple el criterio cuando:

1. su estado es un conjunto cerrado y enumerado de campos tipados, sin `dict`
   abierto ni `object` de propósito general;
2. tiene un propietario único y un ciclo de vida declarado (quién lo crea,
   quién lo reemplaza, quién lo cierra);
3. no contiene servicios, transportes, runtimes, reloj, entrada de operador ni
   callbacks capturados;
4. es reemplazable como snapshot y serializable en el límite sin perder orden,
   duplicados ni autoridad;
5. nada fuera de su propietario lo muta.

`CPScaleLiveProgress`, `CPScaleStageContinuity` y `CPScaleSessionResources`
están escritos contra estos cinco puntos; `active_network_projection` y las
closures `archive`/`observe_cleanup_realtime` de hoy no los cumplen, y por eso
son parte del trabajo del hito, no de su premisa.

**Volumen acotado no es lo mismo que estado tipado.** Un `frozen dataclass`
puede crecer sin límite: `completed_stages`, `issues`, `archives`,
`required_observations` y `diagnostics` son tuplas tipadas y aun así
acumulan. Para la futura extracción, la medida es explícita:

| Campo | Cota declarada | Cómo se mide |
| --- | --- | --- |
| `completed_stages` | número de stages del target contract | `len(...) <= len(target.build_stages)` |
| `required_observations` por stage | operaciones obligatorias que el stage declara | comparar con el plan del stage, no con lo observado |
| `diagnostics` por stage | intentos diagnósticos declarados | `DIAGNOSTIC_ONLY`, sin autoridad y sin crecer por reintento |
| `archives` | fases de archivo alcanzadas | una entrada por fase, no una por escritura |
| `issues` | problemas del preflight | fijo por comprobación; conserva orden y duplicados |

Ningún campo puede crecer por observación, por mutación ni por reintento sin
una cota declarada aquí. Una cota se mide contando entradas frente al plan que
las autoriza, no frente a lo que el runtime produjo.

**No duplicar historial.** El snapshot de progreso referencia la evidencia
durable y los journals; no los copia. Un stage terminado se guarda una vez y no
se vuelve a incrustar en snapshots posteriores, y un recibo de archivo se
referencia por identidad en vez de repetir su payload. Si dos estructuras
distintas contienen la misma lista de acciones, una de ellas es historial
duplicado y el hito no ha terminado.

**Segundo escenario sintético.** Cuando un mecanismo se extraiga, su prueba de
reutilización es una prueba futura que lo ejecuta con un segundo escenario
sintético que no es CP-SCALE canónico: otro contrato de target, otra secuencia
de stages, otra política de aceptación inyectada y otros adaptadores dobles.
Si el mecanismo necesita tocarse para admitir ese segundo escenario, no era un
mecanismo. Esa prueba:

- vive sólo bajo `tests/`, como los fixtures sintéticos actuales;
- no adquiere autoridad productiva ni entra en la admisión;
- no sustituye al oráculo de equivalencia: éste sigue comparando el escenario
  canónico contra la referencia registrada.

Ninguno de los dos criterios autoriza trabajo ahora, ni convierte un mecanismo
en framework: siguen prohibidos el workflow framework, el event bus, el
`Context` de acceso universal y cualquier segunda política de aceptación.

## Observación, diagnóstico y autoridad

| Operación | Efectos posibles | Puede bloquear | Autoridad que puede emitir |
| --- | --- | --- | --- |
| baseline/resume/workspace doble | lecturas PT | sí | workspace/restauración sólo con dos observaciones compatibles |
| E5 readback y voice deferred signal | consultas y fases legítimas ya modeladas | sí | resultado E5 y aceptación gobernada; no promoción automática |
| E9 route/flow verification | queries/ping según plan | sí | `VERIFIED` o `DEPENDENCY_BLOCKED` conforme al prerequisito |
| forwarding de sitio | dos pings tipados, ordenados y atribuibles | sí | autoridad exacta declarada/reversa del plan |
| replay audit | inspección de resultados y journals | sí | `NO_MUTATION_REPLAY` sólo desde auditoría runtime |
| Realtime después de cleanup | lectura de modo | sí, para cierre limpio | restauración de modo únicamente |
| diagnóstico de Simulation/frame | puede cambiar a Simulation, avanzar y restaurar | no puede promover; su propio fallo es secundario | `DIAGNOSTIC_ONLY` |
| escritura/archivo/presentación | filesystem/stdout | puede impedir publicar un éxito | ninguna autoridad de dominio |
| checkpoint de operador | stdin + revalidación Git | sí | permiso de continuar/retener, nunca `VERIFIED` |

`MUTATION_SCOPE_DISJOINT` describe sólo la comparación estática de
proyecciones. `CONFIGURATION_REREAD_MUTATION_SCOPE_EMPTY` describe la relectura
operacional. `NO_MUTATION_REPLAY` depende exclusivamente de
`canonical_stage_mutation_replay_audit` y sus journals. Ninguno sustituye a los
otros dos.

## Dependencias menos visibles y compatibilidad

Dependencias que una extracción debe hacer explícitas o preservar mientras
existan consumidores:

- `GOVERNED_ROOT`, `EVIDENCE_PATH`, `CHECKPOINT_PATH`,
  `FINAL_CHECKPOINT_PATH`, `CANONICAL_EVIDENCE_DIR` y `_BUILD_STAGES` se
  calculan al importar desde `__file__`.
- El argumento predeterminado `destination=CHECKPOINT_PATH` de
  `_write_checkpoint_summary` queda ligado al objeto `Path` de importación;
  cambiar luego la constante no cambia ese default.
- `EXPECTED_BRANCH` y `EXPECTED_UPSTREAM` llegan por import desde
  `qualify_cp_scale_live.py`.
- `run_identity` depende de reloj y de `expected_head`; la procedencia real se
  completa después con el HEAD observado.
- `packet_tracer_mcp.__file__`, `sys.executable` y `sys.modules` forman parte
  de la evidencia, no son metadatos decorativos.
- Las closures `archive` y `observe_cleanup_realtime` capturan `evidence`,
  transporte, identidad, ruta y estado de finalización.
- `active_network_projection` es estado capturado por callbacks de diagnóstico.
- `input`, `print`, `datetime.now`, `subprocess.run` y `_git_output` son I/O
  directo del runner.
- `FileBridge` resuelve su mailbox desde el entorno del usuario; los probes M0
  reemplazan `LOCALAPPDATA`, `TEMP` y `TMP`.
- Los tests monkeypatchean globals del módulo del runner: constructores de
  transporte/runtimes, composición/proyección, `_execute_stage`, checkpoint,
  cleanup, archivo y writers.
- Otros tests importan directamente `_execute_stage`, `_stage_voice`,
  `_wait_for_site_forwarding`, `_network_state_observation`,
  `_post_failure_simulation_diagnostic` y `_frame_observer_discovery`.
- Algunos tests inspeccionan el source del runner y la firma/default del writer.
- El namespace de producción y el de tests son objetos distintos aun sobre los
  mismos archivos; nunca se cargan juntos.

Contratos que deben seguir compatibles durante la migración:

- comando, flags, defaults y códigos observables de `main`;
- firma y default de `run`;
- orden Router0 y continuación del target predeterminado;
- target contracts, proyecciones, forwarding authority, applicator results,
  replay audit, closures y esquemas de evidencia existentes;
- una sesión, mismas instancias, ownership exacto y cierre gobernado;
- import isolation y procedencia.

Los helpers con `_`, closures, ubicación de serializers y forma interna de los
diccionarios pueden cambiar cuando todos sus consumidores se migren en el mismo
slice. Hasta entonces son superficies de compatibilidad de facto. No se copia
el runner a `src`, no se ofrece selector `legacy/new` y no se recalculan
expectativas desde la implementación candidata.

## Baseline ejecutable

### Nivel A — coordinación exterior

`tests/cp_live_m0_harness.py` ejecuta el `run()` productivo real en subprocess.

| Qué sustituye el doble | Qué queda real |
| --- | --- |
| preflight de import, Git/upstream/dirty y procesos PT | resolución del target contract y su recorrido |
| transporte HTTP y `CapabilitySnapshotStore` | bucle de stages, orden, multiplicidad y continuidad |
| composición, proyección y delta | manejo de checkpoints y cierre Router0 |
| runtime físico y runtimes E5/E9/Voice | `_complete_router0_target` y su lectura de `NO_MUTATION_REPLAY` |
| `_execute_stage`, `_checkpoint`, `_cleanup_owned` | secuencia archive/cleanup/attestation |
| `_write_evidence`, `_write_checkpoint_summary`, archivo de evidencia | `except`/`finally`, precedencia de fallos y código devuelto |

La sustitución no se declara: cada probe la mide. El hijo toma una foto de los
símbolos del runner antes de instalar el primer doble y devuelve, en una
sección `provenance` separada de la traza comparable, exactamente qué símbolos
reemplazó, qué namespaces cargó, si el paquete y el runner resuelven dentro de
este árbol, cuántos intentos de dispatch hubo y **qué ficheros del repositorio
ejecutó realmente** (las reglas bajo `src` incluidas; los del entorno local
`.venv` se cuentan aparte y se nombran, no se descartan en silencio). El transporte doble lanza si
alguien llama `send` o `send_and_wait`, y esos intentos se cuentan: el cero
observado es lo que sostiene «no se contactó ningún entorno LIVE», en lugar de
un campo declarado en el expected. El filesystem y el token están aislados por
subprocess.

Este nivel demuestra recorrido, orden, multiplicidad, checkpoints,
terminación, archivo/cleanup y cierre. No demuestra la semántica interna de un
stage ni una cualificación full productiva.

### Nivel B — ejecución interna

`tests/test_cp_scale_live_failure_evidence.py` llama el `_execute_stage` real en
subprocess y sustituye runtimes/I/O. Conserva los applicators y contratos
relevantes necesarios para caracterizar evidencia parcial, journals, primera
frontera, Voice, diagnóstico, Realtime y workspace. Los tests application de
Configuration, Control Plane y Voice ejercitan las implementaciones reales con
runtimes controlados.

El escenario A `floor2-failure` sólo caracteriza que `run` conserva la
evidencia parcial y no continúa; no pretende reemplazar estos tests B.

### Nivel C — política y evidencia

El policy trace M0 llama las funciones reales `_wait_for_site_forwarding`,
`canonical_stage_mutation_replay_audit`,
`canonical_stage_configuration_error` y
`configuration_application_contradiction` con entradas tipadas sintéticas.

La captura parte de lo observado, no de lo planificado: cada dispatch del ping
tipado se convierte en una operación, en orden y con su multiplicidad. El plan
y la evidencia se correlacionan por la identidad exacta fuente/destino y por el
ID del check; la evidencia sólo se atribuye si además confirma esa misma
identidad. La posición nunca concede identidad ni `VERIFIED`. Una identidad de
dispatch duplicada es ambigua y falla cerrada para todas sus ocurrencias. Un
bloque `cardinality` fija cuántas comprobaciones se planificaron, cuántas
operaciones se despacharon, cuántos registros de evidencia hay, cuáles no
quedaron correlacionadas y si las tres cuentas y atribuciones coinciden. Los
probes de inserción, duplicación y destino incorrecto ejercitan el
comportamiento observado: conservan orden y multiplicidad, y ninguna llamada
ajena hereda la comprobación siguiente. Los tests existentes aportan casos
positivos, negativos y ambiguos de forwarding, E9, reread y replay. Las
capacidades sintéticas viven sólo bajo `tests/`, el store se reemplaza y
`live_environment_contacted=false` está fijado en la procedencia.

## Matriz escenario → contrato → test → evidencia

| Escenario | Contrato congelado | Tests/oráculo | Evidencia obtenida |
| --- | --- | --- | --- |
| 1. Router0 | `routing-core → router4-switch10 → floor1 → floor2 → floor3 → router0-branch → cierre`; nunca Router3/remaining/full | `test_run_reaches_router0_cleanup_and_never_enters_the_later_stages`, target-stage terminal test, oracle `router0-cleanup` | seis stages en orden, archive→cleanup→archive→write→summary→write→stop, exit 0, closure `ROUTER0_BRANCH_VERIFIED_AND_CLEANED` |
| 2a. Default continúa | target omitido sigue más allá de Router0 | `test_default_run_still_walks_past_router0_into_router3`, `test_default_target_preserves_the_full_qualification_route` | el test histórico que falla al alcanzar remaining sólo prueba alcance, no éxito full |
| 2b. Full limpia | coordinación completa bajo dobles | oracle `full-cleanup` | Router3, remaining y full alcanzados; exit 0; closure cleaned; cleanup antes de stop |
| 2c. Full retiene | retención sólo tras full y autorización | oracle `full-retain`, final-disposition tests | exit 0; retained; no cleanup propio; archive/write/summary/stop |
| 3. Admisión rechazada | sin deploy, reconcile ni stage dependiente de composición válida | oracle `admission-rejected` y preflight/application tests | cero stages y cero operaciones de mutación; se adquiere/cierra el doble y cleanup vacío se intenta; exit 1 |
| 4. Forwarding | conserva `DECLARED_TRAFFIC_FLOW` vs `REVERSE_PATH_OF_DECLARED_FLOW`, IDs exclusivos y dos direcciones; ambigüedad fail-closed | policy trace, todos los forwarding tests de `test_cp_scale_router0_target_stage.py`, dispatch/failure de runner | dos operaciones ordenadas: Router4→destino declarado y Router0→reversa; autoridad, flow IDs, destinatario y status quedan en el fixture |
| 5. E9 | ruta `VERIFIED` permite flow; otra condición produce `DEPENDENCY_BLOCKED` sin ping; normalización conserva prerequisito | tres tests en `test_control_plane_application.py` líneas 747, 769 y 794 | llamadas y ausencia de llamadas al runtime, estado tipado y plan normalizado |
| 6a. Delta/reread/replay | las tres afirmaciones tienen autoridad distinta | transition/reread/replay tests de target-stage | disjoint estático, reread sin mutación y audit runtime permanecen separados |
| 6b. Replay en superficies | Configuration, Control Plane y Voice respetan mutación delta, retención, journals y fases Voice diferidas | configuration incremental/reread/zero-delta; control incremental; voice incremental/deferred; policy trace | IDs autorizados, despachados y journalled preservados por superficie y en orden |
| 6c. Replay adversarial | retained reejecutado, identidad no autorizada, dispatch sin journal o intento adicional niegan claim | tests target-stage `retained_action...`, `dispatch_no_journal...`, `authorized_surface...` y audit parametrizado | `NO_MUTATION_REPLAY` sólo cuando todos los journals verifican; no se deduce de ID repetido aislado |
| 6d. Error previo | un replay en floor2 bloquea el cierre Router0 aunque Router0 aislado pase | `test_a_replayed_retained_action_blocks_the_router0_closure` | auditoría terminal recorre todos los stages, lista stage sin audit y retained replayed |
| 7. Fallo durante stage | conserva parcial y primera frontera; no continúa dependientes | oracle `floor2-failure`; suite real `_execute_stage` failure-evidence | stages terminan en floor2 `failed/configuration`; archive, cleanup, attestation y stop se intentan; no floor3 |
| 8. Mutación ambigua | no retry automático ni cambio de transporte | `test_lost_mutation_ack_is_unknown_dirty_and_never_replayed` | `UNKNOWN`, dirty y una sola solicitud; no replay |
| 9. Cancelación | checkpoint abort conserva evidencia y cleanup de ownership | oracle `operator-abort`, checkpoint EOF existente | se detiene en floor1, luego archive→cleanup→archive→write→stop; exit 1 |
| 10a. Diagnóstico | su fallo no promueve ni reemplaza la causa y Simulation se restaura | sim diagnostic y failure-evidence tests | modo inicial/final, progresión, fallo diagnóstico separado y no autoridad |
| 10b. Archivo | fallo precleanup conserva causa, intenta cleanup/attestation/stop | oracle `precleanup-archive-failure` | exit 1, closure queda precleanup, segundo archive de fallo y cleanup se intentan |
| 10c. Cleanup | fallo de cleanup no permite cierre exitoso, pero no abandona attestation/stop | oracle `cleanup-failure` | cleanup inicial falla, finally vuelve a intentar según estado actual, archiva y cierra; exit 1 |
| 10d. Restauración | observación Realtime fallida rechaza cierre y continúa finalización | oracle `restoration-observation-failure` | cierre sólo precleanup, causa explícita, cleanup archive y stop |
| 10e. Escritura/cierre | escritura final no impide stop; ni escritura ni close sustituyen la causa primaria; sin causa primaria, un fallo de finalización impide el éxito | quince casos en `test_cp_live_m0_finalization_invariant.py`: escritura y stop fallando solos y juntos, con y sin fallo previo, más cancelaciones y control sano | siempre se intenta `transport.stop`; código `1` en los seis casos de fallo; causa primaria y secundarios en el registro `CP_SCALE_FINALIZATION_INCOMPLETE`; la cancelación sigue viajando y nunca se convierte en código |
| 10g. Interrupción antes de la escritura | una cancelación durante cleanup, archivo o relectura no puede saltarse el cierre ni llevarse los secundarios | cancelación en cleanup con `stop` fallido; cancelación en la escritura con `stop` fallido | `transport.stop` intentado en ambos; el fallo de cierre queda en el registro y no sustituye la cancelación; no se persiste ningún registro de la sesión fallida |
| 10h. Canal de reporte | un canal de reporte roto no sustituye la causa primaria ni promete persistencia | `stdout` roto, y luego `stdout`+`stderr` rotos, con causa primaria y escritura fallida | con `stdout` roto el registro sale por `stderr`; con ambos rotos no sale nada, no se inventa nada y el código sigue siendo `1` |
| 10f. Aceptación Configuration | «sin contradicción» no equivale a aceptación canónica | policy trace: `canonical_stage_configuration_error` sobre plan y relectura coherentes, con un rechazo | aceptado `PARTIAL` con techo gobernado y `fully_verified=false`; techo promovido rechazado aunque no contradiga nada |
| 11. Captura de operaciones | ninguna operación observada puede quedar fuera de la traza ni heredar identidad/evidencia por posición; cardinalidades explícitas y ambigüedad fail-closed | policy trace más probes de inserción, duplicación y destino incorrecto | la inserción conserva tres operaciones en orden y marca la segunda como no planificada; una identidad duplicada no recibe `VERIFIED`; un destino incorrecto no recibe check ni evidencia; `aligned=false` y el comparador rechaza cada traza adversarial |
| 12. Procedencia del registro | una referencia no puede atribuirse a un SHA cuyas dependencias ejecutables difieren | `test_cp_live_m0_reference_recording.py`: alcance ejecutado, regla importada modificada, fichero ausente en cualquiera de los dos lados, procedencia de probes y commit desconocido | el alcance medido incluye las reglas bajo `src`; cualquier diferencia byte a byte rechaza la grabación; una procedencia de probe inválida la rechaza antes de escribir |

La matriz mantiene «aceptación gobernada» separada de `VERIFIED`. El policy
trace congela un resultado Configuration `PARTIAL`, aceptado por la regla
vigente y explícitamente `fully_verified=false`; no lo promociona.

## Oráculo y procedencia

Referencia vigente:

- `tests/fixtures/cp_live_m0/baseline-v3.json`
- `tests/fixtures/cp_live_m0/baseline-v3.sha256`
- `tests/fixtures/cp_live_m0/.gitattributes` fija los tres JSON como bytes
  exactos para que `core.autocrlf` no cambie su digest
- schema `cp-live-m0-equivalence-baseline-v3`
- fixture version `cp-live-m0-fixture-v3`
- fuente caracterizada: el commit del código corregido, fijado también en
  `BASELINE_SOURCE_SHA` dentro de `test_cp_live_m0_equivalence_baseline.py`

Referencias históricas, conservadas y verificables, ya no oráculo:

- `baseline-v2.json` y su `.sha256`, schema
  `cp-live-m0-equivalence-baseline-v2`, fuente
  `7a6c552dd570f683fe3f249c1037815192543ae7`
- `baseline-v1.json` y su `.sha256`, schema
  `cp-live-m0-equivalence-baseline-v1`, fuente
  `62db3cea84a4bfca1a5bcd3d2389d62864c45946`, SHA-256
  `99adcea78b0dbf861cfa4a32b49c50577ea6d0cca3f33725a136272273387634`

El bloque `supersedes` de v3 es una cadena, de la más reciente a la más
antigua, con el digest de cada artefacto conservado y las diferencias
justificadas. Frente a v2 son exactamente tres:

1. `policy_trace.operations` se construye desde cada dispatch observado y se
   añade `policy_trace.cardinality`, porque el `zip()` anterior podía truncar y
   esconder una operación adicional;
2. `provenance.executed_scope` registra el alcance ejecutado que la grabación
   verificó contra su commit, porque antes sólo se comprobaban cuatro ficheros
   estáticos y las reglas reales bajo `src` quedaban fuera;
3. la fuente caracterizada es el runner con el cierre protegido también durante
   cleanup/archivo/relectura y con el canal de reporte con reserva. Ningún
   escenario de coordinación ejerce una escritura, un cierre o un reporte
   fallidos, así que sus trazas congeladas son idénticas a las de v2.

Un test comprueba, para cada referencia conservada, que sigue coincidiendo con
su propio digest y que cada diferencia está nombrada; otro comprueba que el
commit fijado existe, que su árbol coincide y que el digest de v3 corresponde a
sus bytes. Esa lectura de `git` es local y necesita la
historia completa: por eso el workflow de CI hace checkout con
`fetch-depth: 0`, con el motivo escrito junto al paso. Si el objeto falta, el
test falla nombrando esa dependencia; no se salta y no toca la red.

La procedencia fijada dentro del JSON es commit y árbol fuente, repositorio,
referencia, fecha, intérprete, plataforma y versiones de pytest, Pydantic y
MCP. Esos datos no se normalizan. La procedencia medida por el candidato
—intérprete, namespaces cargados, ficheros dentro del árbol, intentos de
dispatch y símbolos sustituidos— se afirma aparte y nunca entra en la
comparación.

Las métricas medidas son obligatorias y tipadas. En particular,
`transport_dispatch_attempts` debe estar presente como `list[str]`: sólo una
lista vacía demuestra cero intentos; ausencia, `None` o cualquier otro tipo
rechazan la procedencia antes de grabar.

Se comparan recursivamente tipos, claves, valores y listas ordenadas. La
comparación conserva operaciones, fases, IDs, destinatarios, orden,
multiplicidad, stages, primera frontera, decisión, autoridad, estado, journals,
archivo, cleanup, cierre y exit code. Pruebas adversariales demuestran que el
comparador detecta una operación extra, destinatario cambiado, autoridad
incorrecta, promoción indebida a `VERIFIED` y una aceptación puesta sobre un
resultado que la regla canónica rechaza.

Sólo se omiten del trace comparable:

- timestamps de reloj;
- run IDs y nombres/digests de archivo generados;
- paths absolutos del directorio temporal.

Son variabilidad no semántica. No se omiten ni normalizan SHA/árbol/entorno de
procedencia, autoridades, destinos, status, duplicados, orden o journals. El
expected es un archivo test-only; las pruebas nunca lo recalculan.

Regenerarlo es una decisión, y se toma fuera de pytest:

```bash
.venv/bin/python -m tests.cp_live_m0_record_baseline \
    --record --source-sha <sha del código corregido>
```

`tests/cp_live_m0_record_baseline.py` no es un módulo de test, pytest no lo
recoge y se niega a ejecutarse dentro de un proceso de pytest. Antes de
escribir nada hace dos cosas:

1. **valida la procedencia de cada probe** con la misma función que usa el
   oráculo: un solo namespace, ficheros dentro del árbol, cero intentos de
   dispatch, los dobles instalados y las reglas intactas. Una sola discrepancia
   rechaza la grabación;
2. **comprueba el alcance ejecutado completo**: la unión de los ficheros del
   repositorio que los probes importaron, más las entradas estáticas de la
   grabación, tiene que ser byte a byte idéntica a la del commit nombrado. Una
   regla importada modificada rechaza la grabación aunque el runner esté
   comiteado.

Así una referencia no puede atribuirse a un SHA cuyas dependencias ejecutables
difieren. El registro de la referencia va en un commit distinto del de la
corrección.

## Registro reproducible de validación M0

Todas las ejecuciones usaron la `.venv` del worktree, instalación editable,
sin `PYTHONPATH` y un `LOCALAPPDATA`/token temporal. El patrón de entorno fue:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
$env:LOCALAPPDATA = (Join-Path $PWD "tmp\cp-live-m0-<gate>")
$env:TEMP = $env:LOCALAPPDATA
$env:TMP = $env:LOCALAPPDATA
$env:PT_MCP_BRIDGE_TOKEN = "cp-live-m0-synthetic-token"
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
```

El Python de `PATH` no se usó. Los probes de namespace se ejecutaron por
separado: el proceso de tests resolvió
sólo `src.packet_tracer_mcp`; el probe productivo resolvió sólo
`packet_tracer_mcp`; ambos archivos quedaron dentro de este worktree.

| Gate | Resultado M0 | Interpretación |
| --- | --- | --- |
| siete módulos mínimos solicitados sobre fuente intacta | `111 passed` | reproducción focal previa a añadir M0 |
| suite completa sobre `HARDENING_BASE_SHA` antes de añadir tests | `4147 passed, 3 warnings` en 128.83 s | reproduce el conteo histórico; no es CI |
| oráculo nuevo aislado | `16 passed` en 7.17 s | artefacto/digest, nueve coordinaciones, policy trace y sensibilidad |
| matriz afectada sin las reproducciones rojas | `194 passed` | runners, `_execute_stage`, forwarding, E9, replay/reread, ambigüedad e imports |
| invariantes de finalización | `2 failed` en 1.54 s | reproducción causal deliberada, no regresión escondida |
| suite completa candidata | `4163 passed, 2 failed, 3 warnings` en 139.72 s | sólo fallan los dos invariantes; M0 queda bloqueada |

M0-FIX se validó en Linux con CPython 3.11.15, la `.venv` local del checkout,
instalación editable y sin `PYTHONPATH`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest -q
```

| Gate | Resultado M0-FIX | Interpretación |
| --- | --- | --- |
| invariantes de finalización sobre el runner anterior | `10 failed, 2 passed` en 10.85 s | la cobertura causal nueva es roja antes del cambio; los dos verdes son el control sano |
| invariantes de finalización sobre el runner corregido | `12 passed` en 11.23 s | escritura y stop, solos y juntos, con y sin fallo previo, más cancelaciones |
| oráculo aislado | `19 passed` en 9.24 s | artefacto/digest, referencia superseded, nueve coordinaciones con su procedencia medida, policy trace, aceptación canónica y sensibilidad |
| matriz afectada, ya sin reproducciones rojas | `220 passed` en 41.20 s | runners, `_execute_stage`, forwarding, E9, replay/reread, ambigüedad, gates canónicos e imports |
| suite completa | `4176 passed, 2 skipped, 3 warnings` en 173.07 s | +13 tests frente a la candidata de M0: 10 de finalización y 3 del oráculo |

Segunda pasada, en el mismo entorno:

| Gate | Resultado | Interpretación |
| --- | --- | --- |
| finalización sobre el runner de `baseline-v2` | `4 failed, 11 passed` en 14.88 s | los cuatro casos nuevos son rojos antes del cambio: cancelación en cleanup, cancelación en la escritura con `stop` fallido, `stdout` roto y los dos canales rotos |
| finalización sobre el runner corregido | `15 passed` en 14.77 s | los doce anteriores más esos cuatro, menos ninguno |
| reglas de grabación de referencia | `7 passed` en 1.08 s | alcance ejecutado, regla importada modificada, ausencias en cada lado, procedencia de probes y commit desconocido |
| oráculo aislado | `20 passed` en 10.75 s | añade la captura completa con su probe de dispatch adicional |
| matriz afectada | `231 passed` en 50.00 s | la anterior más las reglas de grabación |
| suite completa | `4187 passed, 2 skipped, 3 warnings` en 190.88 s | +11 frente a la pasada anterior: 3 de finalización, 1 del oráculo y 7 de grabación |

Los dos `skipped` son los ya existentes de artefactos ausentes en el checkout
(`test_positive_voice_ab_evidence_ledger.py`,
`test_positive_voice_dhcp_pool_observer.py`), y aparecían igual en el CI del
SHA anterior. Los tres warnings siguen siendo la misma deprecación de fixtures
de clase.

Comandos de los gates nuevos:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_cp_live_m0_equivalence_baseline.py -q

.\.venv\Scripts\python.exe -m pytest `
  tests\test_cp_scale_router0_live_runner.py `
  tests\test_cp_scale_router0_target_stage.py `
  tests\test_cp_scale_live_failure_evidence.py `
  tests\test_control_plane_application.py `
  tests\test_worktree_isolation.py `
  tests\test_import_isolation_preflight.py `
  tests\test_e95_architecture_boundaries.py `
  tests\test_configuration_application.py `
  tests\test_voice_runtime.py `
  tests\test_e95_packet_tracer_physical_runtime.py `
  tests\test_mutation_transport_ambiguity.py `
  tests\test_cp_live_m0_equivalence_baseline.py -q

.\.venv\Scripts\python.exe -m pytest `
  tests\test_cp_live_m0_finalization_invariant.py -q

.\.venv\Scripts\python.exe -m pytest -q
```

Los mismos gates en el entorno POSIX de M0-FIX, añadiendo
`tests/test_cp_scale_canonical_runtime_gates.py` a la matriz afectada porque
la aceptación canónica de Configuration entró en el policy trace:

```bash
.venv/bin/python -m pytest tests/test_cp_live_m0_equivalence_baseline.py -q
.venv/bin/python -m pytest tests/test_cp_live_m0_finalization_invariant.py -q
.venv/bin/python -m pytest tests/test_cp_live_m0_reference_recording.py -q
.venv/bin/python -m pytest -q
```

Los tres warnings completos son la deprecación ya existente de fixtures de
clase en pytest. Ningún resultado anterior se presenta como ejecución LIVE.

## Defecto previo a la extracción, corregido en M0-FIX

Frontera afectada: R13, la finalización de `run()` en
`tools/cp_scale_canonical_live.py`.

Reproducción causal mínima:

1. `run()` adquiere el transporte doble.
2. `_execute_stage` produce `CanonicalLiveFailure("PRIMARY_STAGE_FAILURE")`.
3. El `except` registra esa causa y prepara retorno `1`.
4. `finally` intenta archive/cleanup/attestation.
5. `_write_evidence(evidence)` lanza
   `OSError("FINAL_EVIDENCE_WRITE_FAILED")`.
6. La línea siguiente, `transport.stop()`, no se ejecuta.
7. El caller recibe sólo el `OSError`; la causa primaria queda enmascarada.

El segundo probe deja escribir la evidencia y hace fallar `stop`: el caller
recibe sólo `OSError("TRANSPORT_STOP_FAILED")`, no la causa primaria.

| Dimensión | Baseline observado | Invariante exigido | Comportamiento corregido |
| --- | --- | --- | --- |
| intento de cierre tras fallo de escritura | no | sí, siempre que se adquirió | `transport.stop()` vive en el `finally` interno de la escritura, así que se intenta también cuando la escritura lanza |
| causa primaria observable | sustituida | preservada como primaria | la causa sigue en el resultado; escritura y cierre sólo pueden añadir secundarios |
| cleanup disponible | ocurrió en memoria/doble antes de escribir | debe conservarse si se puede; su persistencia fallida queda secundaria | el bloque de cleanup/attestation no cambia; su fallo sigue siendo secundario |
| resultado del caller | excepción secundaria | resultado/fallo que incluye primaria y secundarios | código `1` más un registro `CP_SCALE_FINALIZATION_INCOMPLETE` con la causa primaria y cada secundario |

La corrección aplicada es mínima y no cambia la API: `run()` sigue devolviendo
`int` y conserva los códigos publicados (`0` éxito o retención, `1` fallo
adquirido, `2` hard stop de request/preflight). No se fuerza una excepción sólo
porque el texto fuese cómodo de afirmar en un test.

1. Cada salida de la sesión pasa por `_settled(code)`, que deja registrado qué
   código alcanzó la sesión antes de finalizar. Una cancelación nunca llega a
   registrar uno.
2. Toda la finalización vive en `_finalize()`: cleanup, archivo, relectura de
   Realtime, attestation y escritura final ocurren dentro de un `try`, y
   `transport.stop()` está en su `finally`. El cierre queda protegido aunque la
   interrupción ocurra **antes** de la escritura —durante cleanup, durante el
   archivo o durante la relectura— y no sólo cuando falla la escritura.
3. Los fallos de escritura, de cierre y de cualquier otro paso de finalización
   se acumulan como secundarios, en orden, con su tipo y su mensaje.
4. Si hubo secundarios, se emite un registro
   `CP_SCALE_FINALIZATION_INCOMPLETE` con `run_identity`, la causa primaria, el
   hard stop si lo hubo y la lista de secundarios. Sale desde el `finally`
   interno, así que una cancelación que siga viajando no se lleva los
   secundarios con ella. El intento de cierre no se anota como restauración ni
   toca el veredicto de cleanup.
5. El registro usa los canales disponibles y no promete persistencia:
   `_emit_finalization_report` intenta `stdout`, luego `stderr`, y si ambos
   rechazan la escritura calla en vez de lanzar por encima de la causa que
   estaba preservando. El canal durable puede ser justo el que acaba de fallar;
   el código de salida y el registro en memoria siguen llevándola.
6. Sin causa primaria, un fallo de finalización convierte el `0` en `1`. Con
   causa primaria, el código ya es `1` y no se toca. Con hard stop, el `2` se
   conserva.
7. `KeyboardInterrupt` y demás `BaseException` no se capturan como secundarios
   ni se convierten en código: siguen viajando después de intentar el cierre.

La cobertura causal son quince casos en
`tests/test_cp_live_m0_finalization_invariant.py`: escritura y `stop` fallando
solos y juntos, con y sin fallo previo (seis); la comprobación de que la
escritura que falla es la de finalización y no una anterior (dos); una
finalización sana que sigue devolviendo `0` (uno); cancelación durante el stage
(dos), durante cleanup y durante la escritura final, ambas con `stop` fallido
(dos); y el canal de reporte roto —sólo `stdout`, y luego los dos— con la causa
primaria intacta (dos). Diez fallan sobre el runner previo a la primera
corrección y cuatro sobre el previo a esta segunda pasada.

## M1 autorizado: extracción acotada

M1 fue autorizado por separado con un gate inicial M1-0. Su prerequisito
—corregir R13, obtener suite verde y registrar una referencia nueva
identificada— estaba cumplido por M0-FIX. M1-0 corrigió antes de extraer la
correlación del policy trace y la validación tipada de su procedencia, sin
regenerar `baseline-v3` ni cambiar la traza normal.

Primera familia a extraer en M1: **solicitud, identidad y admisión/preflight**
(R1 parcial + R2). Es la frontera anterior a cualquier contacto/mutación y no
requiere mover `_execute_stage` ni alterar lifecycle.

Slice implementado:

1. Crear los contratos `CPScaleLiveRequest`, `CPScaleLiveSessionIdentity` y
   `CPScalePreflightResult` —con los tipos ya cerrados arriba— en application.
2. Extraer sólo la coordinación de import isolation, Git/upstream/dirty,
   proceso/build y validación de target a `application/cp_scale_live/admission.py`.
3. Implementar el puerto de entorno en infrastructure y reutilizar
   `canonical_cp_scale_target_contract`, `ImportIsolationPreflight` y reglas
   actuales. No duplicar composición ni aceptación.
4. `tools/cp_scale_canonical_live.py` **sigue siendo la entrada y el
   composition root**, y pasa a llamar a esas piezas. No se crea todavía
   `adapters/cli/cp_scale_live.py` ni se convierte `tools` en façade: el
   coordinador aún vive ahí, y una façade que reenvía a algo que no está bajo
   `src` obligaría a `src` a importar `tools`. El parseo, la presentación y la
   façade se mueven en el mismo slice que mueva el coordinador, no antes.
5. Dejar transporte, sesión, stage loop, applicators, observaciones,
   diagnóstico, persistencia, cleanup y cierre en su ubicación actual.
6. Comparar con la referencia fija `baseline-v3`, ejecutar tests de namespaces
   y full suite; no avanzar a la siguiente familia dentro del mismo mandato.

La nomenclatura autorizada reemplaza ese mapa provisional: **M2-A** extrae el
stage executor, sus colaboradores de Configuration, Voice, Control Plane,
forwarding y reconciliación, más observación y diagnóstico separados; **M2-B**
extrae la coordinación, sesión persistente, persistencia/finalización y mueve
la composición/presentación al adapter CLI, dejando `tools` como façade. M3 es
la retirada de compatibilidad privada después de migrar consumidores; esa fase
fue autorizada y cerrada offline el 2026-09-09. Cada mecanismo que salga en M2 se acepta contra los
«Criterios de reutilización»: estado acotado y un segundo escenario sintético.

## Criterio de cierre de esta entrega

M0 entregó documentación, harness, fixture, digest, comparador y reproducciones
causales, y quedó bloqueada porque las pruebas de seguridad de R13 fallaban en
el baseline productivo. M0-FIX corrige esa finalización, deja las
reproducciones verdes, corrige el oráculo y su preparación de CI, y registra
`baseline-v2` sobre el código corregido conservando `baseline-v1` como
histórico. La segunda pasada cierra el cierre frente a interrupciones anteriores
a la escritura y frente a un canal de reporte roto, completa la captura de
operaciones con sus cardinalidades, extiende la procedencia del registro al
alcance ejecutado real y registra `baseline-v3` conservando `v1` y `v2`. El
estado final es:

```text
CP_LIVE_M0=CORRECTED_BASELINE_RECORDED
PRODUCT_ADMISSION=BLOCKED
ROUTER0_LIVE=NOT_RUN
M1=AUTHORIZED_LOCAL_PREFLIGHT_EXTRACTED
M2_A=AUTHORIZED_OFFLINE_IN_PROGRESS
M2_B=AUTHORIZED_OFFLINE_PENDING_M2_A_GATE
M3=NOT_AUTHORIZED_NOT_STARTED
```

## Consolidación offline M1/M2 y prueba de reutilización

Estado vigente después de las correcciones y revisiones de M2; el bloque
anterior documenta el cierre histórico de M1, no el estado actual.

| Hito | Commits | Gates y revisión |
| --- | --- | --- |
| M1 fixes — COMPLETE | `aad6da0ee6e5d77ab57be45c2bdb2d1c0ebfb2be` | parsing estricto, política única de identidad/build y snapshot Git ligado al SHA capturado; ledger de revisión limpio con dos sugerencias Minor de cobertura; revalidación focal Task 4: **27 passed** |
| M2-A — COMPLETE | `14a79bcde15df95e8ca832e14afc9bebe00da9a2`, `585dc08ad979341ee762c58f6f16d115fc9a0763` | Gate A del implementador: **665 passed**; re-review de los dos Important: **Ready yes**, **8 passed** frescos; serializer sin ping inventado y primera causa Voice atribuible preservada |
| M2-B — COMPLETE | `aea3a19`, `22bbc17`, `884f1a5`, `0df0e5f`, `89cb524`, `3ee64c65f2c23e609b778f23b6c88ea1e45512d3` | Gate B del implementador: **727 passed**; re-review independiente: **124 passed**, **Ready yes**, sin Critical/Important/Minor |

Las revisiones y registros causales completos están en el ledger local de
ejecución `.superpowers/sdd/2026-09-08-cp-live-m2-modular-execution/`. Son
artefactos locales ignorados por Git; esta sección conserva los resultados
esenciales en documentación versionada.

El coordinator es el único dueño que reemplaza los tres ledgers frozen de
cualificación, progreso y finalización. `CPScaleRunReport` es una proyección
frozen de publicación, no un Context compartido. Backend/build/completion
reciben valores estrechos; checkpoint divide preparación/publicación/prompt y
reanudación/publicación para adquirir cada valor antes del siguiente efecto.
El resultado final mantiene `cleanup_realtime` tipado junto a `cleanup`, un
equivalente explícito del contrato propuesto que conserva la identidad de ambos
resultados originales. El adapter es el único que traduce outcome a 0/1/2.

La observación Realtime de cleanup está cerrada y tipada. No se afirma que la
observación Realtime del stage (`observation.py`/`voice_stage.py`), ni todos los
payloads históricos de evidencia de dominio, hayan sido reescritos: el Minor de
tipado de esa observación interna de M2-A sigue registrado. No se amplía su
autoridad y no se modifica producción como parte de estas pruebas.

### Prueba no canónica y mecanismos sin cambios

`tests/test_cp_scale_live_reuse_and_state.py` usa un `DocumentAuditTarget` con
`capture → inspect → seal`, cursor propio y dos adaptadores dobles distintos
(`MemoryDocumentReader`, `AuditReceiptAdapter`). Una política de máximo de
errores inyectada hace fallar `inspect` o permite los tres pasos con exactamente
las mismas observaciones. El `execute_stage_sequence` real permanece intacto:
la prueba afirma orden, duplicados de IDs, primera falla, identidad exacta de
continuidad/resultados/journals y secundarios duplicados en orden.

El mecanismo sólo itera y acumula. No conoce este target, CP-SCALE, Router0,
PoE, checkpoints, cleanup, persistencia ni PT. El target sintético no pasa por
admisión y no concede ninguna autoridad productiva.

Identidad del archivo aceptado antes/después de Task 4:

- Git blob: `4beb4860d031296b12f5963315f3061a8a06a5c0`.
- SHA-256 de `application/cp_scale_live/sequence.py`:
  `661629942ef62c31c0e8b28baef31d9e46996f1f86c6cd26989d1323cf18a562`.

### Medidas de estado y serialización 1/2/4

Las cotas se declaran **antes** de ejecutar la medida en `MeasurementPlan` y
en el target, no se obtienen contando lo que produjo un runtime: dos lecturas
obligatorias, un intento diagnóstico `DIAGNOSTIC_ONLY`, tres journals completos
de tres entradas por stage, dos fases de archivo y cuatro comprobaciones de
preflight. El mecanismo sintético conserva cuatro entradas de journal por
stage, con la operación `check` duplicada de forma intencional.

La fixture CP declara además una acción Voice controlada para habilitar el
único intento diagnóstico permitido. Cada resultado se contrasta con las
cotas reales de `CPScaleStageExecutionInput`: configuration attempts ≤ 3,
required observations ≤ 9, diagnostics ≤ 1, secondary failures ≤ 3 para ese
plan. `completed_stages` no supera los seis stages declarados del target y
los dos recibos no superan `archive_phase_limit`. No se afirma que estos planes
de medida sean la composición canónica ni que una secuencia de snapshots de
fallo equivalga a una ejecución que continúe después de fallar.

Para la proyección pública se construyen snapshots CP tipados/controlados,
frozen y sin aceptación productiva, y se llama al boundary real `run_evidence`.
Se usan las opciones productivas exactas: JSON UTF-8 con `ensure_ascii=False`,
`indent=2`, orden de inserción y LF final. Para cada tamaño, la prueba compara
los bytes con `CPScaleLivePersistence.write_progress` real en un directorio
temporal. Reloj, IDs y payloads son fijos: una segunda construcción produce
exactamente los mismos bytes. Esta es una medida del boundary público y del
escritor real, no una serialización alternativa ni una captura LIVE.

| Stages | Entradas del mecanismo | Filas journal sintético | Resultados CP únicos | Journals CP únicos | Filas journal CP | Observaciones requeridas | Diagnósticos | Archivos | Issues | JSON UTF-8 bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 4 | 1 | 3 | 9 | 2 | 1 | 2 | 0 | 11 451 |
| 2 | 2 | 8 | 2 | 6 | 18 | 4 | 2 | 2 | 0 | 20 967 |
| 4 | 4 | 16 | 4 | 12 | 36 | 8 | 4 | 2 | 0 | 39 979 |

El sobre sin stages es idéntico en las tres medidas: **1 937 bytes**. Las
cuatro entradas con su indentación miden **9 510 / 9 514 / 9 504 / 9 504 bytes**;
las pequeñas diferencias se deben a los nombres canónicos, no a historial.
La prueba comprueba la descomposición exacta
`bytes = sobre + suma(bytes_de_stage) + 4 + 2(n - 1)` y las cotas predeclaradas de
8 192 bytes para el sobre y 16 384 por stage. No fija como supuesto el tamaño
observado ni recorta journals para cumplir la cota. Estas cotas en bytes son
del plan controlado de medición, no límites universales para cualquier payload
de evidencia canónico.

Se recorre el grafo de valores por identidad: hay exactamente `n` resultados
de stage y `3n` journals originales, no copias. Cada entrada de progreso apunta
al mismo resultado que el final frozen; las continuidades no contienen
resultados terminados ni snapshots previos. Los recibos sólo llevan metadatos,
no payloads archivados. En JSON hay exactamente `n` objetos de stage, sin
historial anidado; las tres colecciones completas de journal se conservan en
su orden y multiplicidad. Los aliases legítimos de resultados tipados no se
cuentan como objetos nuevos. Esto no elimina claves redundantes que otros
escenarios del esquema público histórico deban conservar por compatibilidad.

### Guardas de arquitectura y alcance de la prueba

`tests/test_cp_scale_live_architecture.py` analiza AST y el grafo real de imports,
incluyendo rutas intermedias fuera del slice cuando conectan sus componentes.
Rechaza `src → tools` en todo `src`, imports concretos de infrastructure en
`application/cp_scale_live`, ciclos runtime de coordinación/ejecución/
observación/diagnóstico/persistencia y una façade que ejecute coordinación,
defina funciones/clases, cargue dinámicamente o reenvíe globals. Ignora texto
de docstrings y aristas exclusivas de `TYPE_CHECKING` para ciclos, no para la
dirección de capas. Los use cases históricos con imports de infrastructure
siguen explícitamente fuera de esta extracción; no se presenta el repositorio
entero como una migración de capas completada.

Los guardas de estado resuelven aliases/annotations/constructores/`replace`
por ámbito léxico de módulo, función y clase, y acumulan conjuntos de tipos
monótonos hasta un punto fijo finito. Incluyen annotations locales con un
inicializador opaco, sin mezclar los bindings de funciones hermanas. Detectan
mutaciones sobre valores identificados, requieren registros frozen sin
campos abiertos y detectan servicios directos o anidados en bundles. No se
basan en LOC ni en buscar palabras dentro de texto. Los controles adversariales
del checker pasaron de **19 + 3 + 2 + 2 REDs** a GREEN; seis controles adicionales
prueban sensibilidad a snapshots corruptos (pérdida, duplicado, copia, cambio
de continuidad, truncado y secundarios reordenados). El control de truncado
mantiene intacta la identidad del recibo para fallar por pérdida de filas, no
por sustituir un objeto. Tres REDs adicionales identificaron que la primera
medida compacta no era byte a byte la escritura pública; se corrigieron las
opciones de medida, sin tocar producción. Otros tres REDs detectaron una
fixture con diagnóstico sin acción Voice declarada; la corrección fue sólo
de la fixture y no cambió los bytes públicos. Esos REDs pertenecen a las nuevas
pruebas, no a un defecto productivo inventado: no se modificó M2 para fabricarlos.

La primera suite completa produjo **4 365 passed / 1 failed**: el guard legacy
de contención sólo clasificaba `application/use_cases/`. Conforme R11–R12 se
actualizó exclusivamente su clasificación a las dos raíces application
explícitas, añadiendo pruebas de que cleanup se descubre como orquestador pero
no dispatcher y de que una tercera ruta sigue rechazada por el guard real.
No se añadió una excepción de dispatcher ni se relajó la tabla de familias.

Verificación de la primera implementación Task 4 (`930bb6f`): foco
arquitectura/reuse/estado/contención **74 passed
en 13.41 s**; matriz afectada incluido el oráculo fijo **801 passed en 116.76 s**;
suite completa checkout-local **4 370 passed, 3 warnings en 195.81 s**. Los tres
warnings existentes son de fixtures class-scoped de pytest en pruebas E9.5,
no fallos de esta extracción. La revisión posterior encontró dos defectos del
checker: el filtro prematuro de ciclos DFS y la inferencia global oscilante de
bindings. El detector ahora calcula SCC/Tarjan sobre **todo** el grafo runtime
antes de seleccionar componentes cíclicos con CP; reporta una ruta cerrada
real, no el listado de miembros del SCC. Doce permutaciones de nodos/aristas
comprueban la ruta transitiva por dos módulos externos. La inferencia scoped
conserva sus controles de ownership; un subprocess con timeout de cinco
segundos acota la reproducción de dos funciones con locales homónimos.

Gates después de estas correcciones de revisión: foco **90 passed en 12.20 s**,
matriz afectada/oráculo **817 passed en 117.47 s**, suite completa local
**4 386 passed, 3 warnings existentes en 197.95 s**. Los tres Important se
entregan corregidos para re-review; estos gates no sustituyen la revisión
independiente ni el CI remoto pendiente.

El oráculo sigue siendo `baseline-v3`, SHA-256
`639cd07674460c83c9a78d6c66459f0ce84648cc18a21579bcbc83826766baa7`.
No se regraba ni normaliza una divergencia. Las pruebas de reuse/volumen no lo
sustituyen.

```text
M1_FIXES=COMPLETE
M2_A=COMPLETE_OFFLINE
M2_B=COMPLETE_OFFLINE
PRODUCT_ADMISSION=BLOCKED
ROUTER0_LIVE=NOT_RUN
M3=COMPLETE_OFFLINE_READY_FOR_FINAL_AUDIT
M3_AUTHORIZATION=OFFLINE_ONLY
CI=REQUIRED_ON_FINAL_M3_CORRECTIONS_SHA
```

Ninguna prueba offline demuestra PT/webview/CORS real, capacidad PoE simultánea
ni admisión productiva. No se abrió PT, no se contactó el bridge del usuario,
no se adquirieron capacidades LIVE y no se modificaron `.pts`. La entrega M2 se
publicó en `fae7a7f9` y su run `34322942037` terminó 4/4. Para M3, el mandato
autoriza y exige publicar `refactor/cp-live-m0-baseline` en `cisco` sin force
después de la revisión final y verificar los cuatro jobs del nuevo SHA. Ese CI
M3 sigue pendiente; merge, force-push y adquisición LIVE siguen prohibidos.

## M3 — cierre e integración offline

M3 parte de `fae7a7f9ae7db80c1fad921ddc81ed57d695d853`. Su
HEAD funcional revisado antes de este registro es
`030e6ae7be7546fbfdaa071495e524a8037b6ea3`; el SHA final de documentación y
CI se reporta fuera del propio commit para no crear una autorreferencia.

| Requisito | Implementación | Prueba | Evidencia offline |
| --- | --- | --- | --- |
| Raíz gobernada independiente | `run()` lee únicamente `PT_MCP_GOVERNED_ROOT`; la misma `Path` entra en preflight, store de capacidades, checkpoint y `CPScaleLivePersistence`. No existe fallback a `packet_tracer_mcp.__file__` | `test_cp_scale_live_governed_root.py`, CLI, import/worktree isolation | dos clones A/B en el mismo SHA: tool A + venv/paquete B retorna `2`, no escribe en B, no crea store y no alcanza backend |
| Fallos parciales serializables | `run_evidence()` trata `first`, `second`, `unresolved` y errores de cleanup de forma independiente, conservando `None` como ausencia | `test_cp_scale_live_partial_persistence.py` | el fallo real de la segunda observación conserva la primera, la causa `SECOND_WORKSPACE_READ_FAILED`, un solo close y evidencia/archives reales en `tmp_path` |
| Aislamiento fuera de Git | snapshot SHA-256+mtime iniciado en `pytest_configure`, verificado en `pytest_unconfigure`, y entorno común para subprocess; token/mailbox/temp/store separados | `test_cp_live_data_integrity.py`, harness M0 y affected | crear, borrar, reemplazar, reescribir los mismos bytes o retargetear symlink rompe el sentinel; affected **822 passed / 1 skip** y full **4 406 passed / 1 skip** terminaron sin diferencia protegida |
| Migración y Realtime de stage | tool reducido a `main/run`; adapter conserva sólo composición/presentación; consumidores importan desde application/observation/diagnostics/persistence. `CPScaleRealtimeObservation` y `CPScaleRealtimeState` llevan presencia, error, provenance y autoridad requerida | `test_cp_scale_live_realtime_contract.py`, stage/failure/Voice/diagnostics/arquitectura | mapping público before/after idéntico; ausencia y Simulation permanecen fallos, diagnóstico no adquiere autoridad y no queda wrapper `_execute_stage` |
| Desenlace durable posterior al cierre | `finalize_session` puede diferir el reporte sin alterar su comportamiento por defecto; el coordinador publica una vez los errores adquiridos tras `close` o presentación y sólo hace una corrección adicional si el propio reporte añade un secundario. Ninguna de esas rutas repite sesión, cleanup ni PT | `test_cp_scale_live_terminal_persistence.py`, `test_cp_scale_live_terminal_obligations.py`, `test_cp_live_m0_finalization_invariant.py` | **3 RED** por ausencia durable y **1 RED** por fallo del reporte; con writer disponible, disco y resultado conservan stop/presentación; si falla el writer final, el archivo atómico previo queda byte-idéntico y resultado/reporte declaran `terminal_evidence_write` |
| Cleanup parcial y cancelación | `CPScaleCleanup.restore` acumula mutaciones confirmadas, primera y segunda lectura, captura sólo `Exception` en `CPScaleCleanupResult`; el coordinador marca el intento antes de entrar para que `BaseException` viaje sin retry ambiguo | `test_cp_scale_live_terminal_persistence.py`, serializers y terminal obligations | **2 RED** perdían mutación/primera lectura y **1 RED** repetía dos borrados durante cancelación; los casos verdes conservan sólo los resultados adquiridos, una única secuencia `remove:s → remove:r`, un `close` y ninguna restauración inventada |
| Realtime coherente | `realtime_boundary_error` sigue siendo la política única y exige presencia explícita, tipos `bool` exactos, `observed is True` y `simulation_mode is False`; stage y cleanup consumen la misma regla | `test_cp_scale_live_realtime_contract.py`, Voice/stage/cleanup/Router0 | **8 RED** admitían ausencia, `None`, `0`, texto o presencia contradictoria; **10 passed** focales y **132 passed** afectados tras cerrar la regla, sin cambiar APIs PT ni autoridad |
| Acumulación reutilizable | `execute_stage_sequence` usa listas locales con `append`/`extend` y congela a tuplas en sus dos retornos | `test_cp_scale_live_reuse_and_state.py`, coordinator/arquitectura/oráculo | **2 RED** observaron cientos de identidades de acumulador; escenario de 512 stages conserva una sola, orden, duplicados, identidad y continuidad, y corta exactamente en la falla 257 sin umbral temporal; gate combinado **145 passed** |
| Equivalencia e integración | inyección del harness adaptada a factories propietarias; ninguna expectativa del oráculo se regeneró | Router0/default/retención/rechazos/cancelación/finalización, baseline-v3 | foco Realtime/migración **334 passed**, review-fix **120 passed / 1 skip**, affected **822 passed / 1 skip**, full **4 406 passed / 1 skip / 3 warnings existentes**; re-review independiente **Ready YES** |
| Cierre de correcciones finales | el harness de cleanup devuelve el contrato fallido tipado; `baseline-v3` conserva literalmente su retry histórico y el candidato se compara por separado contra el delta autorizado: se elimina sólo el segundo `cleanup` y la causa incluye el límite `CanonicalLiveFailure` sin perder `RuntimeError: SYNTHETIC_CLEANUP_FAILURE` | oráculo M0, affected CP-LIVE/CP-SCALE, full checkout-local | `baseline-v3` conserva su digest; escenario corregido y otros 8 escenarios quedan exhaustivamente comparados; affected **627 passed / 1 skip**, full **4 425 passed / 1 skip / 3 warnings existentes** |

### Incidencia de evidencia ignorada

Al comenzar M3 existía
`data/cp-scale/live-canonical-progress.json`, ignorado por Git, con **1 218
bytes**, SHA-256
`bf2ac3bfda1326ee274a5714df0d16bebd53afb9e31e4f90d49ba28eaef9c60d` y
mtime `2026-09-08T22:16:35.3824955-05:00`. Sus propios campos lo clasifican
como `SYNTHETIC_PREFLIGHT_REJECTION_NON_AUTHORITATIVE`: run identity terminado
en `aaaaaaaaaaaa`, target Router0 combinado deliberadamente con retención,
cero stages, hard stop anterior al backend, sin `http_bridge` ni
`capability_prequalification`. Es consistente con la incidencia del harness
reportada en M2, pero no permite saber qué bytes había antes de esa escritura.
Por eso M3 no lo borró, reemplazó ni presentó como restaurado. Su longitud y
hash permanecieron iguales después de focused, affected y full.

### Compatibilidad con `feature/runtime-ripv2`

La referencia remota se refrescó sin merge. El HEAD contemporáneo de
`cisco/feature/runtime-ripv2` es
`62db3cea84a4bfca1a5bcd3d2389d62864c45946`; es también el merge-base con el
HEAD funcional M3. La divergencia observada fue **0 commits exclusivos de
feature / 30 commits de CP-LIVE**. Por tanto no había avances de feature que
incorporar o resolver, y no se exigió igualdad entre ramas. No se hizo merge ni
push a la rama productiva.

`baseline-v3` continúa byte-idéntico con SHA-256
`639cd07674460c83c9a78d6c66459f0ce84648cc18a21579bcbc83826766baa7`.
Las correcciones finales parten de
`a22ee4a882f6aac2bb53aba73dfe2319c1407c23`; su SHA final y el CI 4/4 se
reportan fuera del propio commit para evitar autorreferencia. M3 queda
técnicamente cerrado y listo para auditoría final, separado de
`PRODUCT_ADMISSION=BLOCKED` y `ROUTER0_LIVE=NOT_RUN`. Ningún resultado de esta
sección afirma comportamiento PT/webview/CORS o autoridad PoE LIVE.
