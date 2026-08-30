"""El unico punto de entrada de ejecucion del producto Enterprise.

Por que existe, dicho sin rodeos: la secuencia completa -- desplegar, orientar,
configurar, evidenciar, rutear, verificar conducta, limpiar -- solo existia
dentro de un harness. Un harness que secuencia componentes ES la implementacion,
y eso es exactamente lo que TD-ACCEPTANCE-001 rechaza: la University Acceptance
funciono y aun asi no probo nada sobre el producto, porque el producto no la
habia ejecutado.

Asi que la secuencia vive aqui, en la capa de aplicacion. Un harness puede
ARRANCAR este caso de uso y recoger evidencia; no puede ordenar las etapas por
su cuenta. El adaptador MCP hace transporte y serializacion; la secuencia es de
la aplicacion.

Este modulo no planifica, no compila y no muta: delega. Cada etapa es una
llamada a un seam que ya existia y que no se toca.

Tres reglas que la forma del codigo impone, no solo el comentario:

- ningun gate que rechaza deja pasar una mutacion. El preflight de import y el
  inventario de workspace corren ANTES del primer `ensure_device` y devuelven
  BLOCKED sin haber tocado nada;
- una etapa que falla corta las siguientes. No se aplica plano de control sobre
  una configuracion que no se verifico, ni se compila conducta sin fundaciones;
- la limpieza corre SIEMPRE, tambien despues de fallar, y su exito se comprueba
  volviendo a observar el workspace -- no infiriendolo de que las llamadas de
  borrado devolvieran exito.

E4 es inmutable de punta a punta: `physical_identity_hash` se captura antes de
desplegar y se compara al final. La orientacion DCE/DTE observada es evidencia
de despliegue y viaja en el manifiesto; nunca vuelve al TopologyPlan.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from time import perf_counter_ns

from pydantic import BaseModel

from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
)
from ...domain.enterprise.models.control_plane import ControlPlaneIntent
from ...domain.enterprise.models.control_plane_runtime import ControlPlaneApplicationResult
from ...domain.enterprise.models.deployment import DeploymentManifest, EnvironmentFingerprint
from ...domain.enterprise.models.intent import EnterpriseIntent
from ...domain.enterprise.models.voice_plan import VoiceCapabilityProfile, VoiceIntent
from ...domain.enterprise.models.voice_runtime import VoiceApplicationResult
from ...domain.enterprise.services.hardware_planner import HardwarePlanningPolicy
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentItemStatus,
    PhysicalDeploymentResult,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
    ImportIsolationResult,
)
from ...infrastructure.persistence.capability_snapshot_store import CapabilitySnapshotStore
from .apply_configuration import ConfigurationApplicator, ConfigurationRuntime
from .apply_control_plane import ControlPlaneApplicator, ControlPlaneRuntime
from .apply_voice import VoiceApplicator, VoiceRuntime
from .compose_enterprise_reference import (
    EnterpriseReferenceComposition,
    compose_enterprise_reference,
)
from .deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
    disposable_workspace_error,
)
from .foundational_evidence import derive_foundational_hashes, derive_foundational_statuses
from .observe_serial_orientation import SerialOrientationObserver, SerialOrientationResult
from .qualify_serial_physical_slice import DisposablePhysicalTopologyRuntime


#: Firma del observador previo a la limpieza. Devuelve lineas legibles; el
#: producto no interpreta ninguna.
DiagnosticHook = Callable[["EnterpriseDiagnosticContext"], "Sequence[str] | None"]


class EnterpriseExecutionStage(str, Enum):
    IMPORT_PREFLIGHT = "import_preflight"
    WORKSPACE_INVENTORY = "workspace_inventory"
    COMPOSE = "compose"
    PHYSICAL_DEPLOYMENT = "physical_deployment"
    SERIAL_ORIENTATION = "serial_orientation"
    CONFIGURATION_COMPILE = "configuration_compile"
    CONFIGURATION_APPLY = "configuration_apply"
    FOUNDATIONAL_EVIDENCE = "foundational_evidence"
    VOICE_APPLY = "voice_apply"
    CONTROL_PLANE_APPLY = "control_plane_apply"
    CLEANUP = "cleanup"
    POST_CLEANUP_OBSERVATION_1 = "post_cleanup_observation_1"
    POST_CLEANUP_OBSERVATION_2 = "post_cleanup_observation_2"
    COMPLETED = "completed"


class EnterpriseExecutionStatus(str, Enum):
    #: Todas las etapas corrieron y la limpieza restauro el workspace.
    COMPLETED = "completed"
    #: Un gate rechazo ANTES de mutar. No hay nada que limpiar.
    BLOCKED = "blocked"
    #: Una etapa fallo despues de empezar a mutar. La limpieza si corrio.
    FAILED = "failed"


class EnterpriseExecutionStageMetric(BaseModel):
    """Measured work for one reached stage; durations are descriptive, not gates."""

    stage: EnterpriseExecutionStage
    duration_ms: float
    item_count: int = 0
    issue_count: int = 0
    outcome: str = "completed"


@dataclass(frozen=True)
class EnterpriseRuntimes:
    """Los cuatro runtimes de produccion que la secuencia necesita."""

    physical: DisposablePhysicalTopologyRuntime
    serial_orientation: object
    configuration: ConfigurationRuntime
    control_plane: ControlPlaneRuntime
    voice: VoiceRuntime | None = None


@dataclass(frozen=True)
class EnterpriseDiagnosticContext:
    """Lo que el producto le ofrece a un diagnostico previo a la limpieza.

    Existe porque la limpieza vive DENTRO de esta secuencia: cuando el caso de
    uso devuelve, la topologia ya no esta y cualquier observacion posterior es
    imposible. Un harness que quisiera mirar antes tendria que ordenar las
    etapas, que es exactamente lo que MEG-3 prohibe.

    Es de SOLO LECTURA y solo diagnostico. Lo que devuelva no entra en
    `status`, ni en `errors`, ni en ninguna evidencia de configuracion o de
    fundacion: se acumula aparte, en `diagnostics`. Un diagnostico que explota
    no puede convertir una corrida en fallida, y uno que sale limpio no puede
    promover nada.
    """

    stage: EnterpriseExecutionStage
    topology: object
    oriented_manifest: DeploymentManifest | None
    composition: EnterpriseReferenceComposition | None
    configuration_result: ConfigurationApplicationResult | None
    voice_result: VoiceApplicationResult | None
    control_plane_result: ControlPlaneApplicationResult | None


@dataclass(frozen=True)
class EnterpriseExecutionResult:
    status: EnterpriseExecutionStatus
    stopped_at: EnterpriseExecutionStage
    composition: EnterpriseReferenceComposition | None = None
    import_isolation: ImportIsolationResult | None = None
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    confirmation_inventory: PhysicalWorkspaceObservation | None = None
    inventory_restored: bool | None = None
    cleanup_confirmed_twice: bool | None = None
    deployment: PhysicalDeploymentResult | None = None
    oriented_manifest: DeploymentManifest | None = None
    orientation: SerialOrientationResult | None = None
    configuration_result: ConfigurationApplicationResult | None = None
    foundational_statuses: dict[str, ActionExecutionStatus] = field(default_factory=dict)
    voice_result: VoiceApplicationResult | None = None
    control_plane_result: ControlPlaneApplicationResult | None = None
    cleanup_results: list[PhysicalMutationResult] = field(default_factory=list)
    e4_identity_preserved: bool | None = None
    # Lineas producidas por el diagnostico previo a la limpieza. NO son
    # evidencia: no se derivan estados de aca y `status` las ignora.
    diagnostics: list[str] = field(default_factory=list)
    stage_metrics: list[EnterpriseExecutionStageMetric] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def completed(self) -> bool:
        return self.status is EnterpriseExecutionStatus.COMPLETED

    @property
    def configuration_fully_verified(self) -> bool:
        """Si TODA la evidencia de E5 quedo VERIFIED, no solo las fundaciones.

        COMPLETED significa que cada etapa corrio y que cada fundacion DECLARADA
        por el plan de plano de control quedo VERIFIED. NO significa que toda la
        configuracion se haya podido releer: en este backend hay familias que no
        tienen getter registrado, asi que una corrida puede completar con
        evidencia parcial fuera del conjunto requerido. Se expone aparte para
        que `completed` no se lea como algo mas fuerte de lo que es.
        """
        return (
            self.configuration_result is not None
            and self.configuration_result.status
            is ConfigurationApplicationStatus.VERIFIED
        )

    @property
    def mutated(self) -> bool:
        """BLOCKED significa exactamente que no se toco Packet Tracer."""
        return self.status is not EnterpriseExecutionStatus.BLOCKED

    def compact_summary(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "stopped_at": self.stopped_at.value,
            "import_isolation": (
                self.import_isolation.state.value if self.import_isolation else None
            ),
            "composition": (
                self.composition.compact_summary() if self.composition else None
            ),
            "deployment": (
                self.deployment.compact_summary() if self.deployment else None
            ),
            "orientation": (
                self.orientation.compact_summary() if self.orientation else None
            ),
            "configuration_status": (
                self.configuration_result.status.value
                if self.configuration_result else None
            ),
            "configuration_fully_verified": self.configuration_fully_verified,
            "foundational_statuses": {
                key: value.value for key, value in sorted(self.foundational_statuses.items())
            },
            "voice_status": self.voice_result.status.value if self.voice_result else None,
            "control_plane_status": (
                self.control_plane_result.status.value
                if self.control_plane_result else None
            ),
            "inventory_restored": self.inventory_restored,
            "cleanup_confirmed_twice": self.cleanup_confirmed_twice,
            "e4_identity_preserved": self.e4_identity_preserved,
            "cleanup": [item.model_dump(mode="json") for item in self.cleanup_results],
            "diagnostics": list(self.diagnostics),
            "stages": [item.model_dump(mode="json") for item in self.stage_metrics],
            "errors": list(self.errors),
        }


class _ExecutionState:
    """Acumula evidencia y es la unica que construye resultados.

    Separa deliberadamente `blocked` de `failed`: el primero no limpia porque no
    hubo mutacion que deshacer, y decir lo contrario inventaria una limpieza que
    nunca ocurrio. El segundo limpia siempre.
    """

    def __init__(self, started_at: datetime) -> None:
        self.started_at = started_at
        self.import_isolation: ImportIsolationResult | None = None
        self.composition: EnterpriseReferenceComposition | None = None
        self.baseline_inventory: PhysicalWorkspaceObservation | None = None
        self.final_inventory: PhysicalWorkspaceObservation | None = None
        self.confirmation_inventory: PhysicalWorkspaceObservation | None = None
        self.inventory_restored: bool | None = None
        self.cleanup_confirmed_twice: bool | None = None
        self.deployment: PhysicalDeploymentResult | None = None
        self.oriented_manifest: DeploymentManifest | None = None
        self.orientation: SerialOrientationResult | None = None
        self.configuration_result: ConfigurationApplicationResult | None = None
        self.foundational_statuses: dict[str, ActionExecutionStatus] = {}
        self.voice_result: VoiceApplicationResult | None = None
        self.control_plane_result: ControlPlaneApplicationResult | None = None
        self.cleanup_results: list[PhysicalMutationResult] = []
        self.e4_identity_preserved: bool | None = None
        self.diagnostics: list[str] = []
        self.stage_metrics: list[EnterpriseExecutionStageMetric] = []
        self.errors: list[str] = []
        self.diagnostic: DiagnosticHook | None = None
        self._diagnostic_ran = False

    def record_stage(
        self,
        stage: EnterpriseExecutionStage,
        started_ns: int,
        *,
        item_count: int = 0,
        issue_count: int = 0,
        outcome: str = "completed",
    ) -> None:
        self.stage_metrics.append(EnterpriseExecutionStageMetric(
            stage=stage,
            duration_ms=round((perf_counter_ns() - started_ns) / 1_000_000, 3),
            item_count=item_count,
            issue_count=issue_count,
            outcome=outcome,
        ))

    def blocked(
        self, stage: EnterpriseExecutionStage, *errors: str,
    ) -> EnterpriseExecutionResult:
        return self._result(EnterpriseExecutionStatus.BLOCKED, stage, errors)

    def failed(
        self,
        stage: EnterpriseExecutionStage,
        runtimes: EnterpriseRuntimes,
        topology,
        e4_identity: str,
        *errors: str,
    ) -> EnterpriseExecutionResult:
        self._diagnose(stage, topology)
        self._cleanup(runtimes, topology, e4_identity)
        return self._result(EnterpriseExecutionStatus.FAILED, stage, errors)

    def completed_run(
        self, runtimes: EnterpriseRuntimes, topology, e4_identity: str,
    ) -> EnterpriseExecutionResult:
        self._diagnose(EnterpriseExecutionStage.CONTROL_PLANE_APPLY, topology)
        self._cleanup(runtimes, topology, e4_identity)
        status = (
            EnterpriseExecutionStatus.COMPLETED
            if self.inventory_restored is True and not self.errors
            else EnterpriseExecutionStatus.FAILED
        )
        stage = (
            EnterpriseExecutionStage.COMPLETED
            if status is EnterpriseExecutionStatus.COMPLETED
            else EnterpriseExecutionStage.CONTROL_PLANE_APPLY
        )
        return self._result(status, stage, ())

    def _diagnose(self, stage: EnterpriseExecutionStage, topology) -> None:
        """Corre el diagnostico una sola vez, justo antes de destruir la escena.

        Aislado a proposito: cualquier excepcion queda anotada en `diagnostics`
        y NO en `errors`, porque un observador roto no es una corrida rota. La
        limpieza corre despues pase lo que pase.
        """
        if self.diagnostic is None or self._diagnostic_ran:
            return
        self._diagnostic_ran = True
        context = EnterpriseDiagnosticContext(
            stage=stage,
            topology=topology,
            oriented_manifest=self.oriented_manifest,
            composition=self.composition,
            configuration_result=self.configuration_result,
            voice_result=self.voice_result,
            control_plane_result=self.control_plane_result,
        )
        try:
            lines = self.diagnostic(context)
        except Exception as exc:
            self.diagnostics.append(f"diagnostic_failed: {type(exc).__name__}: {exc}")
            return
        for line in lines or ():
            self.diagnostics.append(str(line))

    def _attempted(self, device) -> bool:
        """True when the deployment reported reaching this device at all.

        No deployment result means the run never got as far as the deployer, so
        nothing was created. An item still `NOT_ATTEMPTED` means the deployer
        stopped before it. Either way the product owns nothing to remove.
        """

        if self.deployment is None:
            return False
        target_id = device.id or device.name
        return any(
            item.target_kind is PhysicalObjectKind.DEVICE
            and item.target_id == target_id
            and item.status is not PhysicalDeploymentItemStatus.NOT_ATTEMPTED
            for item in self.deployment.item_results
        )

    def _cleanup(
        self, runtimes: EnterpriseRuntimes, topology, e4_identity: str,
    ) -> None:
        """Solo recursos gestionados por el producto, y verificado observando."""
        # E4 no puede haberse movido: la orientacion observada es evidencia de
        # despliegue y vive en el manifiesto, nunca en el TopologyPlan.
        self.e4_identity_preserved = topology.physical_identity_hash == e4_identity

        # Lo PLANIFICADO no es lo CREADO. Si el despliegue se nego antes de
        # mutar -- un preflight que no autoriza un nombre de puerto, por
        # ejemplo -- el producto no es dueno de ningun dispositivo, y borrar por
        # nombre igual seria mutar recursos que podrian ser de otro. Se limpia
        # exactamente lo que el despliegue reporto haber intentado.
        cleanup_started = perf_counter_ns()
        errors_before_cleanup = len(self.errors)
        for device in reversed(list(topology.devices)):
            if not self._attempted(device):
                continue
            try:
                self.cleanup_results.append(runtimes.physical.remove_device(device))
            except Exception as exc:
                self.errors.append(f"Cleanup failed for {device.name!r}: {exc}")
        self.record_stage(
            EnterpriseExecutionStage.CLEANUP,
            cleanup_started,
            item_count=len(self.cleanup_results),
            issue_count=len(self.errors) - errors_before_cleanup,
            outcome="failed" if len(self.errors) > errors_before_cleanup else "completed",
        )

        observation_started = perf_counter_ns()
        try:
            self.final_inventory = runtimes.physical.observe_workspace()
        except Exception as exc:
            self.errors.append(f"Final workspace inventory failed: {exc}")
            self.final_inventory = None
        self.record_stage(
            EnterpriseExecutionStage.POST_CLEANUP_OBSERVATION_1,
            observation_started,
            item_count=(
                len(self.final_inventory.devices) if self.final_inventory is not None else 0
            ),
            issue_count=0 if self.final_inventory is not None else 1,
            outcome="completed" if self.final_inventory is not None else "failed",
        )

        confirmation_started = perf_counter_ns()
        try:
            self.confirmation_inventory = runtimes.physical.observe_workspace()
        except Exception as exc:
            self.errors.append(f"Confirmation workspace inventory failed: {exc}")
            self.confirmation_inventory = None
        self.record_stage(
            EnterpriseExecutionStage.POST_CLEANUP_OBSERVATION_2,
            confirmation_started,
            item_count=(
                len(self.confirmation_inventory.devices)
                if self.confirmation_inventory is not None else 0
            ),
            issue_count=0 if self.confirmation_inventory is not None else 1,
            outcome="completed" if self.confirmation_inventory is not None else "failed",
        )

        if (
            self.baseline_inventory is None
            or self.final_inventory is None
            or self.confirmation_inventory is None
        ):
            # Sin las dos observaciones no se puede afirmar restauracion. None es
            # la respuesta honesta; escribir False afirmaria lo contrario.
            self.inventory_restored = None
            self.cleanup_confirmed_twice = None
            return
        first_restored = physical_workspace_restoration_matches(
            self.baseline_inventory, self.final_inventory,
        )
        second_restored = physical_workspace_restoration_matches(
            self.baseline_inventory, self.confirmation_inventory,
        )
        self.cleanup_confirmed_twice = first_restored and second_restored
        self.inventory_restored = self.cleanup_confirmed_twice

    def _result(
        self,
        status: EnterpriseExecutionStatus,
        stage: EnterpriseExecutionStage,
        errors,
    ) -> EnterpriseExecutionResult:
        return EnterpriseExecutionResult(
            status=status,
            stopped_at=stage,
            composition=self.composition,
            import_isolation=self.import_isolation,
            baseline_inventory=self.baseline_inventory,
            final_inventory=self.final_inventory,
            confirmation_inventory=self.confirmation_inventory,
            inventory_restored=self.inventory_restored,
            cleanup_confirmed_twice=self.cleanup_confirmed_twice,
            deployment=self.deployment,
            oriented_manifest=self.oriented_manifest,
            orientation=self.orientation,
            configuration_result=self.configuration_result,
            foundational_statuses=dict(self.foundational_statuses),
            voice_result=self.voice_result,
            control_plane_result=self.control_plane_result,
            cleanup_results=list(self.cleanup_results),
            e4_identity_preserved=self.e4_identity_preserved,
            diagnostics=list(self.diagnostics),
            stage_metrics=list(self.stage_metrics),
            started_at=self.started_at,
            finished_at=datetime.now(timezone.utc),
            errors=[*self.errors, *errors],
        )


def execute_enterprise_reference(
    intent: EnterpriseIntent,
    runtimes: EnterpriseRuntimes,
    control_plane_intent: ControlPlaneIntent,
    *,
    environment_fingerprint: EnvironmentFingerprint,
    import_preflight: ImportIsolationPreflight,
    packet_tracer_version: str | None = None,
    capability_store: CapabilitySnapshotStore | None = None,
    voice_intent: VoiceIntent | None = None,
    voice_capabilities: dict[str, VoiceCapabilityProfile] | None = None,
    deployment_id: str = "",
    require_empty_workspace: bool = True,
    policy: HardwarePlanningPolicy | None = None,
    pre_cleanup_diagnostic: DiagnosticHook | None = None,
) -> EnterpriseExecutionResult:
    """Ejecuta el producto de punta a punta y limpia pase lo que pase.

    `pre_cleanup_diagnostic` es un observador opcional que el PRODUCTO invoca
    una vez, despues de la etapa terminal y antes de la limpieza. No ordena
    etapas y no puede cambiar el resultado: ver `EnterpriseDiagnosticContext`.
    """
    started_at = datetime.now(timezone.utc)
    state = _ExecutionState(started_at=started_at)
    state.diagnostic = pre_cleanup_diagnostic

    stage_started = perf_counter_ns()
    isolation = import_preflight.ensure_isolated()
    state.import_isolation = isolation
    state.record_stage(
        EnterpriseExecutionStage.IMPORT_PREFLIGHT,
        stage_started,
        item_count=1,
        issue_count=0 if isolation.isolated else 1,
        outcome="completed" if isolation.isolated else "blocked",
    )
    if not isolation.isolated:
        # Antes de tocar nada: un gate que rechaza no deja mutar.
        return state.blocked(
            EnterpriseExecutionStage.IMPORT_PREFLIGHT, isolation.render(),
        )

    stage_started = perf_counter_ns()
    try:
        baseline = runtimes.physical.observe_workspace()
    except Exception as exc:
        state.record_stage(
            EnterpriseExecutionStage.WORKSPACE_INVENTORY,
            stage_started,
            issue_count=1,
            outcome="blocked",
        )
        return state.blocked(
            EnterpriseExecutionStage.WORKSPACE_INVENTORY,
            f"Read-only workspace inventory failed: {exc}",
        )
    state.baseline_inventory = baseline
    if require_empty_workspace:
        workspace_error = disposable_workspace_error(baseline)
        if workspace_error:
            state.record_stage(
                EnterpriseExecutionStage.WORKSPACE_INVENTORY,
                stage_started,
                item_count=len(baseline.devices),
                issue_count=1,
                outcome="blocked",
            )
            return state.blocked(
                EnterpriseExecutionStage.WORKSPACE_INVENTORY, workspace_error,
            )

    state.record_stage(
        EnterpriseExecutionStage.WORKSPACE_INVENTORY,
        stage_started,
        item_count=len(baseline.devices),
    )

    stage_started = perf_counter_ns()
    composition = compose_enterprise_reference(
        intent,
        packet_tracer_version=packet_tracer_version,
        capability_store=capability_store,
        policy=policy,
    )
    state.composition = composition
    state.record_stage(
        EnterpriseExecutionStage.COMPOSE,
        stage_started,
        item_count=len(composition.topology.devices) if composition.topology else 0,
        issue_count=len(composition.issues),
        outcome="completed" if composition.valid else "blocked",
    )
    if not composition.valid or composition.topology is None:
        return state.blocked(EnterpriseExecutionStage.COMPOSE, *composition.issues)

    topology = composition.topology
    e4_identity = topology.physical_identity_hash
    return _execute_mutating_stages(
        state,
        runtimes,
        control_plane_intent,
        intent=intent,
        topology=topology,
        e4_identity=e4_identity,
        environment_fingerprint=environment_fingerprint,
        packet_tracer_version=packet_tracer_version,
        capability_store=capability_store,
        voice_intent=voice_intent,
        voice_capabilities=voice_capabilities,
        deployment_id=deployment_id,
        require_empty_workspace=require_empty_workspace,
        policy=policy,
    )


def configuration_application_contradiction(
    result: ConfigurationApplicationResult,
) -> str:
    """Por que lo aplicado impide construir encima, o cadena vacia.

    NO es "el agregado no quedo VERIFIED". El agregado cae a PARTIAL en cuanto
    UNA sola relectura queda UNOBSERVABLE, aunque esa accion no sea prerrequisito
    de nada de lo que sigue. Exigirlo entero es mas fuerte que el criterio
    gobernado: `TD-ACCEPTANCE-001` fila 4 pide evidencia autentica, producida por
    `apply_configuration` desde relectura real, de las fundaciones que la
    operacion de plano de control DECLARA -- y esas las verifica
    `ControlPlaneApplicator._foundation_errors` contra el plan tipado, antes de
    tocar el runtime, exigiendo VERIFIED en cada una.

    Lo que sigue bloqueando aca es la CONTRADICCION, no la ausencia:

    * `FAILED` agregado -- el preflight rechazo el lote o una accion no se
      aplico, asi que el plan no se ejecuto como se compilo;
    * una accion `FAILED` -- se intento mutar y no surtio efecto, de modo que el
      device quedo en un estado que nadie pidio;
    * una verificacion `FAILED` -- se releyo y el backend dijo lo contrario de lo
      planificado. Eso no es "no se pudo mirar": es haber mirado y visto otra
      cosa, y desmiente el modelo que este proceso tiene del device, incluidas
      las fundaciones que si leyo bien.

    `UNOBSERVABLE` y `PARTIAL` no contradicen nada; conservan su estado y dejan
    la decision a la fundacion que corresponda, si es que alguna los declara.
    """
    if result.status is ConfigurationApplicationStatus.FAILED:
        return (
            f"Configuration application ended {result.status.value}"
            + (f": {'; '.join(result.preflight_errors)}" if result.preflight_errors else "")
            + ". A failed application is not a base the control plane may build on."
        )
    failed_actions = sorted(
        item.action_id for item in result.action_results
        if item.status is ActionExecutionStatus.FAILED
    )
    if failed_actions:
        return (
            "Configuration actions failed and did not take effect: "
            + ", ".join(failed_actions)
            + ". The control plane may not build on a device left in a state "
            "nobody planned."
        )
    contradicted = sorted(
        item.expectation_id for item in result.verification_results
        if item.status is ActionExecutionStatus.FAILED
    )
    if contradicted:
        return (
            "Configuration read-back contradicted the plan for: "
            + ", ".join(contradicted)
            + ". An observed contradiction is not an unobserved field, and it "
            "discredits this run's model of the device."
        )
    return ""


def _execute_mutating_stages(
    state: _ExecutionState,
    runtimes: EnterpriseRuntimes,
    control_plane_intent: ControlPlaneIntent,
    *,
    intent: EnterpriseIntent,
    topology,
    e4_identity: str,
    environment_fingerprint: EnvironmentFingerprint,
    packet_tracer_version: str | None,
    capability_store: CapabilitySnapshotStore | None,
    voice_intent: VoiceIntent | None,
    voice_capabilities: dict[str, VoiceCapabilityProfile] | None,
    deployment_id: str,
    require_empty_workspace: bool,
    policy: HardwarePlanningPolicy | None,
) -> EnterpriseExecutionResult:
    """Desde aqui se muta, asi que desde aqui la limpieza es obligatoria."""
    stage = EnterpriseExecutionStage.PHYSICAL_DEPLOYMENT
    stage_started = perf_counter_ns()
    try:
        deployment = EnterprisePhysicalTopologyDeployer(runtimes.physical).deploy(
            topology,
            environment_fingerprint=environment_fingerprint,
            deployment_id=deployment_id,
            require_empty_workspace=require_empty_workspace,
        )
        state.deployment = deployment
        state.record_stage(
            stage,
            stage_started,
            item_count=len(deployment.item_results),
            issue_count=len(deployment.errors),
            outcome="completed" if deployment.manifest is not None else "failed",
        )
        if deployment.manifest is None:
            return state.failed(stage, runtimes, topology, e4_identity, *deployment.errors)

        stage = EnterpriseExecutionStage.SERIAL_ORIENTATION
        stage_started = perf_counter_ns()
        orientation = SerialOrientationObserver(runtimes.serial_orientation).observe(
            topology, deployment.manifest,
        )
        state.orientation = orientation
        state.record_stage(
            stage,
            stage_started,
            item_count=len(orientation.observations),
            issue_count=len(orientation.errors),
            outcome="completed" if orientation.verified else "failed",
        )
        if not orientation.verified or orientation.oriented_manifest is None:
            return state.failed(stage, runtimes, topology, e4_identity, *orientation.errors)
        oriented = orientation.oriented_manifest
        state.oriented_manifest = oriented

        stage = EnterpriseExecutionStage.CONFIGURATION_COMPILE
        stage_started = perf_counter_ns()
        composed = compose_enterprise_reference(
            intent,
            packet_tracer_version=packet_tracer_version,
            capability_store=capability_store,
            deployment_manifest=oriented,
            control_plane_intent=control_plane_intent,
            voice_intent=voice_intent,
            voice_capabilities=voice_capabilities,
            policy=policy,
        )
        state.composition = composed
        required_voice_missing = voice_intent is not None and composed.voice is None
        state.record_stage(
            stage,
            stage_started,
            item_count=(
                len(composed.configuration.actions) if composed.configuration else 0
            ) + (len(composed.voice.actions) if composed.voice else 0)
            + (len(composed.control_plane.actions) if composed.control_plane else 0),
            issue_count=len(composed.issues),
            outcome=(
                "completed"
                if composed.valid and not required_voice_missing else "failed"
            ),
        )
        if (
            not composed.valid
            or composed.configuration is None
            or composed.control_plane is None
            or required_voice_missing
        ):
            return state.failed(stage, runtimes, topology, e4_identity, *composed.issues)

        stage = EnterpriseExecutionStage.CONFIGURATION_APPLY
        stage_started = perf_counter_ns()
        runtime_context = ConfigurationRuntimeContext(
            environment_fingerprint=oriented.environment_fingerprint,
        )
        configuration_applicator = ConfigurationApplicator(
            runtimes.configuration
        )
        configuration_result = configuration_applicator.apply(
            composed.configuration,
            actual_source_topology_hash=e4_identity,
            # Exactamente el mapa con el que se compilo, no una segunda
            # resolucion: si compilacion y aplicacion consultaran evidencia por
            # separado podrian discrepar sobre el mismo build.
            capabilities=composed.capabilities,
            runtime_context=runtime_context,
            deployment_manifest=oriented,
            defer_voice_signal_until_bootstrap=bool(
                voice_intent is not None and composed.voice is not None
            ),
        )
        state.configuration_result = configuration_result
        state.record_stage(
            stage,
            stage_started,
            item_count=len(configuration_result.action_results),
            issue_count=(
                len(configuration_result.preflight_errors)
                + sum(
                    item.status is ActionExecutionStatus.FAILED
                    for item in configuration_result.action_results
                )
            ),
            outcome=(
                "failed"
                if configuration_result.status is ConfigurationApplicationStatus.FAILED
                else "completed"
            ),
        )
        # APPLIED != VERIFIED, y el enum lo distingue. Seguir sobre APPLIED seria
        # tratar "la mutacion volvio bien" como evidencia de efecto, que es
        # exactamente lo que el ceiling de este proyecto prohibe.
        contradiction = configuration_application_contradiction(configuration_result)
        if contradiction:
            return state.failed(stage, runtimes, topology, e4_identity, contradiction)

        stage = EnterpriseExecutionStage.FOUNDATIONAL_EVIDENCE
        stage_started = perf_counter_ns()
        # Derivada de resultados ejecutados. No hay parametro por el que un
        # estado pudiera suministrarse: esa es la diferencia con el harness.
        foundational_statuses = derive_foundational_statuses(
            configuration_result=configuration_result,
            physical_result=state.deployment,
        )
        state.foundational_statuses = foundational_statuses
        state.record_stage(
            stage,
            stage_started,
            item_count=len(foundational_statuses),
            issue_count=sum(
                item is not ActionExecutionStatus.VERIFIED
                for item in foundational_statuses.values()
            ),
            outcome="completed" if foundational_statuses else "failed",
        )
        if not foundational_statuses:
            return state.failed(
                stage, runtimes, topology, e4_identity,
                "No foundational evidence was derived from the executed results.",
            )

        if voice_intent is not None:
            stage = EnterpriseExecutionStage.VOICE_APPLY
            stage_started = perf_counter_ns()
            if runtimes.voice is None or composed.voice is None:
                state.record_stage(stage, stage_started, issue_count=1, outcome="failed")
                return state.failed(
                    stage, runtimes, topology, e4_identity,
                    "Voice was requested but no voice runtime or plan is available.",
                )
            def complete_voice_signal() -> dict[str, ActionExecutionStatus]:
                nonlocal configuration_result, foundational_statuses
                configuration_result = (
                    configuration_applicator.complete_deferred_voice_signals(
                        composed.configuration,
                        configuration_result,
                        deployment_manifest=oriented,
                    )
                )
                state.configuration_result = configuration_result
                foundational_statuses = derive_foundational_statuses(
                    configuration_result=configuration_result,
                    physical_result=state.deployment,
                )
                state.foundational_statuses = foundational_statuses
                return foundational_statuses

            barrier = configuration_result.voice_signal_barrier
            voice_result = VoiceApplicator(runtimes.voice).apply(
                composed.voice,
                actual_source_topology_hash=e4_identity,
                actual_source_configuration_hash=composed.configuration.semantic_hash,
                foundational_statuses=foundational_statuses,
                capabilities=composed.voice_capabilities,
                runtime_context=runtime_context,
                deployment_manifest=oriented,
                complete_voice_signal=(
                    complete_voice_signal
                    if (
                        barrier is not None
                        and barrier.signal_status
                        is ActionExecutionStatus.INTENDED
                    )
                    else None
                ),
            )
            state.voice_result = voice_result
            state.record_stage(
                stage,
                stage_started,
                item_count=len(voice_result.action_results),
                issue_count=(
                    len(voice_result.preflight_errors)
                    + sum(
                        item.status is ActionExecutionStatus.FAILED
                        for item in voice_result.action_results
                    )
                ),
                outcome=(
                    "failed"
                    if voice_result.status is ActionExecutionStatus.FAILED
                    else "bounded" if voice_result.status is not ActionExecutionStatus.VERIFIED
                    else "completed"
                ),
            )
            # UNKNOWN/PARTIAL observations remain explicit and bounded. An
            # observed failure or rejected foundation cannot support later claims.
            if voice_result.status is ActionExecutionStatus.FAILED:
                return state.failed(
                    stage, runtimes, topology, e4_identity,
                    "Voice application or verification failed.",
                    *voice_result.preflight_errors,
                )

        stage = EnterpriseExecutionStage.CONTROL_PLANE_APPLY
        stage_started = perf_counter_ns()
        control_plane_result = ControlPlaneApplicator(runtimes.control_plane).apply(
            composed.control_plane,
            actual_source_topology_hash=e4_identity,
            actual_source_configuration_hash=composed.configuration.semantic_hash,
            foundational_statuses=foundational_statuses,
            foundational_hashes=derive_foundational_hashes(composed.control_plane),
            runtime_context=runtime_context,
            deployment_manifest=oriented,
        )
        state.control_plane_result = control_plane_result
        state.record_stage(
            stage,
            stage_started,
            item_count=len(control_plane_result.action_results),
            issue_count=(
                len(control_plane_result.preflight_errors)
                + sum(
                    item.status is ActionExecutionStatus.FAILED
                    for item in control_plane_result.action_results
                )
            ),
            outcome=(
                "completed"
                if control_plane_result.status is ConfigurationApplicationStatus.VERIFIED
                else "failed"
            ),
        )
        # E9 es la operacion terminal de esta secuencia: no hay consumidor
        # posterior al que acotar su claim, asi que aca el agregado SI manda.
        # Hasta ahora nadie lo miraba, y un E9 que se nego en preflight -- por
        # ejemplo con `FOUNDATIONAL_CONFIGURATION_MISSING` -- se reportaba como
        # corrida COMPLETED. Lo tapaba el gate agregado de E5, que impedia
        # llegar hasta aca con fundaciones malas; al acotar ese gate, el hueco
        # queda a la vista.
        if control_plane_result.status is not ConfigurationApplicationStatus.VERIFIED:
            return state.failed(
                stage, runtimes, topology, e4_identity,
                f"Control-plane application ended {control_plane_result.status.value}"
                + (
                    f" ({control_plane_result.failure_code.value})"
                    if control_plane_result.failure_code
                    is not ConfigurationFailureCode.NONE else ""
                )
                + ".",
                *control_plane_result.preflight_errors,
            )
        return state.completed_run(runtimes, topology, e4_identity)
    except Exception as exc:  # la limpieza corre igual
        if not state.stage_metrics or state.stage_metrics[-1].stage is not stage:
            state.record_stage(stage, stage_started, issue_count=1, outcome="failed")
        return state.failed(stage, runtimes, topology, e4_identity, f"{type(exc).__name__}: {exc}")
