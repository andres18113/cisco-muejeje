# CP-LIVE M0: fronteras modulares y baseline de equivalencia

## Decisión y alcance

Este documento es la única especificación normativa de CP-LIVE M0. Consolida
el mapa de extracción, los contratos propuestos, la matriz de caracterización
y la procedencia del oráculo. No autoriza ni contiene implementación de M1,
M2-A, M2-B o M3.

El resultado de M0 es **`BLOCKED_FOR_BASELINE_FIX`**. La caracterización
reprodujo un defecto anterior a la extracción: una excepción de la escritura
final de evidencia impide intentar `transport.stop()` y sustituye la causa
primaria. Una excepción de `transport.stop()` también sustituye la causa
primaria. Las reproducciones están deliberadamente rojas, sin `xfail`, `skip`
ni cambio de expectativa. La corrección productiva necesita autorización
separada y, si se aprueba, un baseline nuevo identificado explícitamente.

No se modificaron `src/`, `tools/`, `EXTENSION/`, snapshots de capacidades,
evidencia LIVE ni gates. No se abrió Packet Tracer, no se conectó al bridge y
no se ejecutó el runner con transporte real.

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

Los datos históricos del relevo y los datos reproducidos se mantienen
separados:

| Evidencia | Reportada en el relevo | Reproducida en M0 |
| --- | --- | --- |
| Suite completa del baseline | `4147 passed` | `4147 passed, 3 warnings` en 128.83 s |
| CI | run `34181547224`, Windows/Ubuntu × 3.11/3.13 | no se lanzó ni se presenta como ejecución M0 |
| Admisión productiva | `BLOCKED` | no se volvió a adquirir evidencia ni se alteró el gate |
| Router0 LIVE | `NOT_RUN` | `NOT_RUN` |

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

## Mapa de responsabilidades actual

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
| R13 | Resultado/cierre: `except/finally` de `run`, escritura final y `transport.stop` | resultado primario + fallos secundarios → código/exception observable | Debe intentar cierre exactamente una vez y conservar causa primaria. El baseline no cumple ambos invariantes | dos tests rojos `test_cp_live_m0_finalization_invariant.py` |
| R14 | Políticas reutilizadas: compositores/proyectores, `ConfigurationApplicator`, `ControlPlaneApplicator`, `VoiceApplicator`, `canonical_stage_mutation_replay_audit` | planes y resultados tipados → aceptación, estados y auditorías | Son la única autoridad de sus dominios. No se duplican al modularizar | target-stage, configuration, control-plane, voice y oracle de política |

### Propiedad propuesta y fase prevista

| ID | Propietario propuesto | Dependencias permitidas | Fase prevista, no autorizada ahora |
| --- | --- | --- | --- |
| R1 | `adapters/cli/cp_scale_live.py`; `tools/...` queda como façade | application contracts/coordinator e infrastructure composition root | M1 para request/CLI; façade hasta M3 |
| R2 | `application/cp_scale_live/admission.py` con puertos de entorno | reglas existentes de application/domain; implementaciones de Git/proceso/import en infrastructure | primera familia de M1 |
| R3 | `infrastructure/execution/cp_scale_live_session.py`, único dueño de `close` | transporte/runtimes concretos; no políticas | M2-A, después del fix de baseline |
| R4 | `application/cp_scale_live/coordinator.py` | contratos, admission, stage executor y puertos estrechos | M2-A |
| R5 | `application/cp_scale_live/stage_executor.py` | applicators, proyectores, validadores y protocolos runtime existentes | M2-B |
| R6 | `infrastructure/observation/cp_scale_live.py` | IOS parsers, typed ping, frame/runtime adapters | M2-B |
| R7 | `infrastructure/diagnostics/cp_scale_live.py` | Simulation/frame adapters; sin acceso a decisiones | M2-B |
| R8–R9 | `infrastructure/persistence/cp_scale_live.py` | filesystem + serializadores de contratos | M2-A |
| R10 | puerto application `CPScaleCheckpointPort`; adapter de consola | estado/provenance tipados, sin runtimes | M2-A |
| R11–R12 | coordinator + servicio application de cleanup; runtime físico ejecuta | ownership ledger, topología y protocolo físico | M2-A |
| R13 | session owner para cierre; coordinator para precedencia de resultados | result/finalization contracts y persistence port | fix separado primero; extracción M2-A |
| R14 | permanece donde está | contratos domain/application existentes | se reutiliza; no se extrae ni duplica |

`execute_enterprise_reference()` y `_ExecutionState` son precedentes útiles para
resultados tipados, diagnóstico separado y cleanup por ownership. No pueden
invocarse una vez por stage: cada llamada ejecuta su propio cleanup antes de
devolver y destruiría la continuidad física que CP-LIVE necesita.

## Arquitectura objetivo aprobada

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

Reglas de dependencia:

1. `tools` puede depender del adapter; ningún archivo bajo `src` depende de
   `tools`.
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

## Contratos propuestos

Las firmas siguientes son diseño de M0, no clases creadas. Los nombres se
derivan de consumidores concretos: argumentos actuales de `run`, metadatos ya
archivados, continuidad que `_execute_stage` recibe, valores que sus callers
desempaquetan y campos inspeccionados por los tests.

### Solicitud

```python
@dataclass(frozen=True)
class CPScaleLiveRequest:
    packet_tracer_version: str
    expected_head: str
    retain_on_full_verification: bool
    target_stage: CPScaleCanonicalTarget = CPScaleCanonicalTarget.FULL_QUALIFICATION
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
    environment_fingerprint: EnvironmentFingerprint
```

Se construye sólo después de validar import isolation y Git. `source_head` es
el observado, no sólo `request.expected_head`; ambos se comparan en admisión.
La identidad nunca cambia al avanzar stages y viaja completa a cada recibo de
archivo. `loaded_namespace` sólo puede ser `packet_tracer_mcp` en producción.

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
Son reales su control flow, target contract, checkpoints/closures,
`_complete_router0_target`, manejo de excepciones y `finally`. Se sustituyen
Git/proceso/import preflight, transporte, store, composición/proyección,
runtimes, stage executor, persistencia y entrada del operador. El transporte
doble lanza si alguien llama `send` o `send_and_wait`; ninguna operación puede
escapar a PT. El filesystem y token están aislados por subprocess.

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
`canonical_stage_mutation_replay_audit` y
`configuration_application_contradiction` con entradas tipadas sintéticas. Los
tests existentes aportan casos positivos, negativos y ambiguos de forwarding,
E9, reread y replay. Las capacidades sintéticas viven sólo bajo `tests/`, el
store se reemplaza y `live_environment_contacted=false` está fijado en la
procedencia.

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
| 10e. Escritura/cierre | escritura final no debe impedir stop; close no debe sustituir causa primaria | dos tests rojos M0 | baseline observado incumple ambos; bloquea M0 |

La matriz mantiene «aceptación gobernada» separada de `VERIFIED`. El policy
trace congela un resultado Configuration `PARTIAL`, aceptado por la regla
vigente y explícitamente `fully_verified=false`; no lo promociona.

## Oráculo y procedencia

Artefactos:

- `tests/fixtures/cp_live_m0/baseline-v1.json`
- `tests/fixtures/cp_live_m0/baseline-v1.sha256`
- `tests/fixtures/cp_live_m0/.gitattributes` fija el JSON como bytes exactos
  para que `core.autocrlf` no cambie su digest
- schema `cp-live-m0-equivalence-baseline-v1`
- fixture version `cp-live-m0-fixture-v1`
- SHA-256 `99adcea78b0dbf861cfa4a32b49c50577ea6d0cca3f33725a136272273387634`

La procedencia fijada dentro del JSON es commit y árbol fuente, repositorio,
referencia remota, fecha, CPython 3.12.10, Windows 11, pytest 9.1.1, Pydantic
2.13.5 y MCP 1.29.1. Esos datos no se normalizan.

Se comparan recursivamente tipos, claves, valores y listas ordenadas. La
comparación conserva operaciones, fases, IDs, destinatarios, orden,
multiplicidad, stages, primera frontera, decisión, autoridad, estado, journals,
archivo, cleanup, cierre y exit code. Pruebas adversariales demuestran que el
comparador detecta una operación extra, destinatario cambiado, autoridad
incorrecta y promoción indebida a `VERIFIED`.

Sólo se omiten del trace comparable:

- timestamps de reloj;
- run IDs y nombres/digests de archivo generados;
- paths absolutos del directorio temporal.

Son variabilidad no semántica. No se omiten ni normalizan SHA/árbol/entorno de
procedencia, autoridades, destinos, status, duplicados, orden o journals. El
expected es un archivo test-only; las pruebas nunca lo recalculan. Regenerarlo
requiere una decisión explícita y no forma parte del runner ni de una futura
implementación candidata.

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

Los tres warnings completos son la deprecación ya existente de fixtures de
clase en pytest. Ningún resultado anterior se presenta como ejecución LIVE.

## Defecto previo a la extracción

Frontera afectada: R13, `tools/cp_scale_canonical_live.py:4811-4871`.

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

| Dimensión | Baseline observado | Invariante exigido |
| --- | --- | --- |
| intento de cierre tras fallo de escritura | no | sí, siempre que se adquirió |
| causa primaria observable | sustituida | preservada como primaria |
| cleanup disponible | ocurrió en memoria/doble antes de escribir | debe conservarse si se puede; su persistencia fallida queda secundaria |
| resultado del caller | excepción secundaria | resultado/fallo que incluye primaria y secundarios |

Corrección propuesta para autorización separada: capturar primero el resultado
primario; ejecutar persistencia final y `stop` en bloques independientes con un
`finally` interno que garantice el intento de cierre; acumular ambos fallos como
secundarios; devolver/elevar con precedencia explícita de la causa primaria.
Si no existe fallo primario, cualquier fallo de persistencia/cierre impide el
éxito. La corrección debe ser mínima en el runner actual, con estas dos pruebas
en rojo antes y verde después. Sólo entonces se identifica un nuevo SHA/árbol,
se vuelve a ejecutar suite completa y se crea, mediante revisión explícita, un
nuevo baseline. No se actualiza automáticamente este fixture.

## Plan acotado de M1

M1 permanece no autorizado y no puede comenzar mientras este baseline esté
bloqueado.

Prerequisito fuera de M1: aprobar y aplicar la corrección aislada de R13,
obtener suite verde, fijar el nuevo SHA/árbol y aprobar un nuevo oracle.

Primera familia a extraer en M1: **solicitud, identidad y admisión/preflight**
(R1 parcial + R2). Es la frontera anterior a cualquier contacto/mutación y no
requiere mover `_execute_stage` ni alterar lifecycle.

Slice propuesto:

1. Crear los contratos `CPScaleLiveRequest`, `CPScaleLiveSessionIdentity` y el
   resultado tipado de preflight en application.
2. Mover parseo/presentación a `adapters/cli/cp_scale_live.py`; mantener
   `tools/cp_scale_canonical_live.py` como façade con flags, firma y códigos.
3. Extraer sólo la coordinación de import isolation, Git/upstream/dirty,
   proceso/build y validación de target a `application/cp_scale_live/admission.py`.
4. Implementar el puerto de entorno en infrastructure y reutilizar
   `canonical_cp_scale_target_contract`, `ImportIsolationPreflight` y reglas
   actuales. No duplicar composición ni aceptación.
5. Dejar transporte, sesión, stage loop, applicators, observaciones,
   diagnóstico, persistencia, cleanup y cierre en su ubicación actual.
6. Comparar con el oracle fijo, ejecutar tests de namespaces y full suite; no
   avanzar a la siguiente familia dentro del mismo mandato.

M2-A sería la sesión persistente/coordinación/persistencia/finalización; M2-B,
el stage executor, observación y diagnóstico; M3, la retirada de compatibilidad
privada después de migrar consumidores. Son únicamente hitos de diseño.

## Criterio de cierre de esta entrega

M0 entrega documentación, harness, fixture, digest, comparador y reproducciones
causales. No puede declararse completa porque las pruebas de seguridad de R13
fallan en el baseline productivo. El estado final correcto es:

```text
CP_LIVE_M0=BLOCKED_FOR_BASELINE_FIX
PRODUCT_ADMISSION=BLOCKED
ROUTER0_LIVE=NOT_RUN
M1=NOT_AUTHORIZED_NOT_STARTED
```
