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

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    ConfigurationRuntimeContext,
)
from ...domain.enterprise.models.control_plane import ControlPlaneIntent
from ...domain.enterprise.models.control_plane_runtime import ControlPlaneApplicationResult
from ...domain.enterprise.models.deployment import DeploymentManifest, EnvironmentFingerprint
from ...domain.enterprise.models.intent import EnterpriseIntent
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentResult,
    PhysicalMutationResult,
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


class EnterpriseExecutionStage(str, Enum):
    IMPORT_PREFLIGHT = "import_preflight"
    WORKSPACE_INVENTORY = "workspace_inventory"
    COMPOSE = "compose"
    PHYSICAL_DEPLOYMENT = "physical_deployment"
    SERIAL_ORIENTATION = "serial_orientation"
    CONFIGURATION_COMPILE = "configuration_compile"
    CONFIGURATION_APPLY = "configuration_apply"
    FOUNDATIONAL_EVIDENCE = "foundational_evidence"
    CONTROL_PLANE_APPLY = "control_plane_apply"
    COMPLETED = "completed"


class EnterpriseExecutionStatus(str, Enum):
    #: Todas las etapas corrieron y la limpieza restauro el workspace.
    COMPLETED = "completed"
    #: Un gate rechazo ANTES de mutar. No hay nada que limpiar.
    BLOCKED = "blocked"
    #: Una etapa fallo despues de empezar a mutar. La limpieza si corrio.
    FAILED = "failed"


@dataclass(frozen=True)
class EnterpriseRuntimes:
    """Los cuatro runtimes de produccion que la secuencia necesita."""

    physical: DisposablePhysicalTopologyRuntime
    serial_orientation: object
    configuration: ConfigurationRuntime
    control_plane: ControlPlaneRuntime


@dataclass(frozen=True)
class EnterpriseExecutionResult:
    status: EnterpriseExecutionStatus
    stopped_at: EnterpriseExecutionStage
    composition: EnterpriseReferenceComposition | None = None
    import_isolation: ImportIsolationResult | None = None
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    inventory_restored: bool | None = None
    deployment: PhysicalDeploymentResult | None = None
    oriented_manifest: DeploymentManifest | None = None
    orientation: SerialOrientationResult | None = None
    configuration_result: ConfigurationApplicationResult | None = None
    foundational_statuses: dict[str, ActionExecutionStatus] = field(default_factory=dict)
    control_plane_result: ControlPlaneApplicationResult | None = None
    cleanup_results: list[PhysicalMutationResult] = field(default_factory=list)
    e4_identity_preserved: bool | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def completed(self) -> bool:
        return self.status is EnterpriseExecutionStatus.COMPLETED

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
            "foundational_statuses": {
                key: value.value for key, value in sorted(self.foundational_statuses.items())
            },
            "control_plane_status": (
                self.control_plane_result.status.value
                if self.control_plane_result else None
            ),
            "inventory_restored": self.inventory_restored,
            "e4_identity_preserved": self.e4_identity_preserved,
            "cleanup": [item.model_dump(mode="json") for item in self.cleanup_results],
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
        self.inventory_restored: bool | None = None
        self.deployment: PhysicalDeploymentResult | None = None
        self.oriented_manifest: DeploymentManifest | None = None
        self.orientation: SerialOrientationResult | None = None
        self.configuration_result: ConfigurationApplicationResult | None = None
        self.foundational_statuses: dict[str, ActionExecutionStatus] = {}
        self.control_plane_result: ControlPlaneApplicationResult | None = None
        self.cleanup_results: list[PhysicalMutationResult] = []
        self.e4_identity_preserved: bool | None = None
        self.errors: list[str] = []

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
        self._cleanup(runtimes, topology, e4_identity)
        return self._result(EnterpriseExecutionStatus.FAILED, stage, errors)

    def completed_run(
        self, runtimes: EnterpriseRuntimes, topology, e4_identity: str,
    ) -> EnterpriseExecutionResult:
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

    def _cleanup(
        self, runtimes: EnterpriseRuntimes, topology, e4_identity: str,
    ) -> None:
        """Solo recursos gestionados por el producto, y verificado observando."""
        # E4 no puede haberse movido: la orientacion observada es evidencia de
        # despliegue y vive en el manifiesto, nunca en el TopologyPlan.
        self.e4_identity_preserved = topology.physical_identity_hash == e4_identity

        for device in reversed(list(topology.devices)):
            try:
                self.cleanup_results.append(runtimes.physical.remove_device(device))
            except Exception as exc:
                self.errors.append(f"Cleanup failed for {device.name!r}: {exc}")

        try:
            self.final_inventory = runtimes.physical.observe_workspace()
        except Exception as exc:
            self.errors.append(f"Final workspace inventory failed: {exc}")
            self.final_inventory = None

        if self.baseline_inventory is None or self.final_inventory is None:
            # Sin las dos observaciones no se puede afirmar restauracion. None es
            # la respuesta honesta; escribir False afirmaria lo contrario.
            self.inventory_restored = None
            return
        self.inventory_restored = physical_workspace_restoration_matches(
            self.baseline_inventory, self.final_inventory,
        )

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
            inventory_restored=self.inventory_restored,
            deployment=self.deployment,
            oriented_manifest=self.oriented_manifest,
            orientation=self.orientation,
            configuration_result=self.configuration_result,
            foundational_statuses=dict(self.foundational_statuses),
            control_plane_result=self.control_plane_result,
            cleanup_results=list(self.cleanup_results),
            e4_identity_preserved=self.e4_identity_preserved,
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
    deployment_id: str = "",
    require_empty_workspace: bool = True,
) -> EnterpriseExecutionResult:
    """Ejecuta el producto de punta a punta y limpia pase lo que pase."""
    started_at = datetime.now(timezone.utc)
    state = _ExecutionState(started_at=started_at)

    isolation = import_preflight.ensure_isolated()
    state.import_isolation = isolation
    if not isolation.isolated:
        # Antes de tocar nada: un gate que rechaza no deja mutar.
        return state.blocked(
            EnterpriseExecutionStage.IMPORT_PREFLIGHT, isolation.render(),
        )

    try:
        baseline = runtimes.physical.observe_workspace()
    except Exception as exc:
        return state.blocked(
            EnterpriseExecutionStage.WORKSPACE_INVENTORY,
            f"Read-only workspace inventory failed: {exc}",
        )
    state.baseline_inventory = baseline
    if require_empty_workspace:
        workspace_error = disposable_workspace_error(baseline)
        if workspace_error:
            return state.blocked(
                EnterpriseExecutionStage.WORKSPACE_INVENTORY, workspace_error,
            )

    composition = compose_enterprise_reference(
        intent,
        packet_tracer_version=packet_tracer_version,
        capability_store=capability_store,
    )
    state.composition = composition
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
        deployment_id=deployment_id,
        require_empty_workspace=require_empty_workspace,
    )


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
    deployment_id: str,
    require_empty_workspace: bool,
) -> EnterpriseExecutionResult:
    """Desde aqui se muta, asi que desde aqui la limpieza es obligatoria."""
    stage = EnterpriseExecutionStage.PHYSICAL_DEPLOYMENT
    try:
        deployment = EnterprisePhysicalTopologyDeployer(runtimes.physical).deploy(
            topology,
            environment_fingerprint=environment_fingerprint,
            deployment_id=deployment_id,
            require_empty_workspace=require_empty_workspace,
        )
        state.deployment = deployment
        if deployment.manifest is None:
            return state.failed(stage, runtimes, topology, e4_identity, *deployment.errors)

        stage = EnterpriseExecutionStage.SERIAL_ORIENTATION
        orientation = SerialOrientationObserver(runtimes.serial_orientation).observe(
            topology, deployment.manifest,
        )
        state.orientation = orientation
        if not orientation.verified or orientation.oriented_manifest is None:
            return state.failed(stage, runtimes, topology, e4_identity, *orientation.errors)
        oriented = orientation.oriented_manifest
        state.oriented_manifest = oriented

        stage = EnterpriseExecutionStage.CONFIGURATION_COMPILE
        composed = compose_enterprise_reference(
            intent,
            packet_tracer_version=packet_tracer_version,
            capability_store=capability_store,
            deployment_manifest=oriented,
            control_plane_intent=control_plane_intent,
        )
        state.composition = composed
        if not composed.valid or composed.configuration is None or composed.control_plane is None:
            return state.failed(stage, runtimes, topology, e4_identity, *composed.issues)

        stage = EnterpriseExecutionStage.CONFIGURATION_APPLY
        runtime_context = ConfigurationRuntimeContext(
            environment_fingerprint=oriented.environment_fingerprint,
        )
        configuration_result = ConfigurationApplicator(runtimes.configuration).apply(
            composed.configuration,
            actual_source_topology_hash=e4_identity,
            runtime_context=runtime_context,
            deployment_manifest=oriented,
        )
        state.configuration_result = configuration_result
        # APPLIED != VERIFIED, y el enum lo distingue. Seguir sobre APPLIED seria
        # tratar "la mutacion volvio bien" como evidencia de efecto, que es
        # exactamente lo que el ceiling de este proyecto prohibe.
        if configuration_result.status is not ConfigurationApplicationStatus.VERIFIED:
            return state.failed(
                stage, runtimes, topology, e4_identity,
                f"Configuration application ended {configuration_result.status.value}, "
                "and only VERIFIED is evidence the control plane may build on.",
            )

        stage = EnterpriseExecutionStage.FOUNDATIONAL_EVIDENCE
        # Derivada de resultados ejecutados. No hay parametro por el que un
        # estado pudiera suministrarse: esa es la diferencia con el harness.
        foundational_statuses = derive_foundational_statuses(
            configuration_result=configuration_result,
            physical_result=state.deployment,
        )
        state.foundational_statuses = foundational_statuses
        if not foundational_statuses:
            return state.failed(
                stage, runtimes, topology, e4_identity,
                "No foundational evidence was derived from the executed results.",
            )

        stage = EnterpriseExecutionStage.CONTROL_PLANE_APPLY
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
        return state.completed_run(runtimes, topology, e4_identity)
    except Exception as exc:  # la limpieza corre igual
        return state.failed(stage, runtimes, topology, e4_identity, f"{type(exc).__name__}: {exc}")
