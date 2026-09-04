"""La secuencia de ejecucion del producto vive en la aplicacion, no en un harness.

Que fija este archivo, y que NO:

Fija los gates, el corte por etapa y la limpieza -- que es donde un harness se
volvia la implementacion. La University Acceptance funciono y aun asi no probo
nada del producto, porque quien ordeno las etapas fue el harness. Aqui el orden
es del caso de uso y estos tests lo sujetan.

NO fija un camino feliz completo de punta a punta contra runtimes simulados.
Simular con fidelidad el despliegue fisico, la lectura de `show controllers`, la
aplicacion de configuracion y el plano de control seria escribir un segundo
Packet Tracer, y un camino feliz contra ese doble probaria que mi fake coincide
con mi codigo, no que el producto funciona. Esa evidencia es del gate en vivo.
"""

from __future__ import annotations

import ast
import pathlib

from src.packet_tracer_mcp.domain.enterprise.services.hardware_planner import (
    HardwarePlanningPolicy,
)
from src.packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
    EnterpriseExecutionStage,
    EnterpriseExecutionStatus,
    EnterpriseRuntimes,
    execute_enterprise_reference,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneIntent,
    DynamicRoutingIntent,
    DynamicRoutingProtocol,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import EnvironmentFingerprint
from src.packet_tracer_mcp.domain.enterprise.models.link_performance import TrafficFlowIntent
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    MutationDisposition,
    PhysicalDeploymentFailureCode,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
    ImportIsolationState,
)
from tests.test_e95_serial_product_planning import _reference_planning_intent
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)
from tests.subprocess_harness import (
    checkout_venv_python,
    checkout_venv_root,
    foreign_python,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "packet_tracer_mcp"

FINGERPRINT = EnvironmentFingerprint(backend_version="9.0.1.0858", bridge_transport="file")


def _intent():
    return _reference_planning_intent().model_copy(update={
        "address_space": "10.0.0.0/8",
        "traffic_flows": [
            TrafficFlowIntent(
                id="flow/a-to-c", source_site_id="a",
                destination_site_id="c", per_unit_bps=100_000,
            ),
        ],
    })


def _bounded_intent():
    """Un solo sitio, sin WAN y sin modulos: la forma minima que despliega.

    Sin enlace serial no hay HWIC que insertar, asi que el doble de este archivo
    -- que rechaza `module_effect_capability` a proposito -- llega intacto hasta
    `ensure_device`, que es lo que estos casos examinan. Los tres modelos que
    salen (`IE-2000`, `PC-PT`, y ningun router) tienen inventario de puertos
    medido, de modo que el preflight de puertos deja pasar.
    """
    from src.packet_tracer_mcp.domain.enterprise.models.intent import (
        EnterpriseIntent, SiteIntent, SiteType,
    )
    from src.packet_tracer_mcp.domain.enterprise.models.requirements import (
        EndpointRequirement,
    )
    from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole

    return EnterpriseIntent(
        name="bounded execution slice",
        address_space="10.0.0.0/8",
        default_growth_percent=0,
        internet_required=False,
        sites=[
            SiteIntent(
                name="A", type=SiteType.HQ,
                endpoints=[EndpointRequirement(role=DeviceRole.USER_PC, count=2)],
            ),
        ],
    )


def _control_plane_intent():
    return ControlPlaneIntent(
        id="cp/reference-ripv2",
        routing=DynamicRoutingIntent(
            id="routing/reference-ripv2",
            protocol=DynamicRoutingProtocol.RIPV2,
            device_ids=[],
            transit_link_ids=[],
        ),
    )


class _RecordingPhysicalRuntime:
    """Registra toda llamada y puede fallar en `ensure_device` a pedido."""

    def __init__(self, *, workspace: PhysicalWorkspaceObservation | None = None,
                 fail_devices: bool = False) -> None:
        self.calls: list[str] = []
        self.removed: list[str] = []
        self._fail_devices = fail_devices
        self.workspace = workspace or PhysicalWorkspaceObservation(
            devices=[
                PhysicalWorkspaceDeviceObservation(
                    name="Power Distribution Device0",
                    model="Power Distribution Device",
                    backend_managed=True,
                ),
            ],
        )

    def observe_workspace(self) -> PhysicalWorkspaceObservation:
        self.calls.append("observe_workspace")
        return self.workspace

    def ensure_device(self, device) -> PhysicalMutationResult:
        self.calls.append(f"ensure_device:{device.name}")
        return PhysicalMutationResult(
            target_id=device.name,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=(
                MutationDisposition.FAILED if self._fail_devices
                else MutationDisposition.APPLIED
            ),
            applied=not self._fail_devices,
            message="fake" if not self._fail_devices else "fake refuses to create",
        )

    def remove_device(self, device) -> PhysicalMutationResult:
        self.removed.append(device.name)
        return PhysicalMutationResult(
            target_id=device.name,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.NO_OP,
            applied=False,
        )

    def __getattr__(self, name):
        def _unused(*args, **kwargs):
            self.calls.append(f"{name}")
            raise AssertionError(f"{name} must not be reached in this scenario")
        return _unused


class _ForbiddenRuntime:
    """Cualquier uso es un fallo: prueba que la etapa nunca se alcanzo."""

    def __init__(self, label: str) -> None:
        self._label = label

    def __getattr__(self, name):
        def _forbidden(*args, **kwargs):
            raise AssertionError(f"{self._label}.{name} must not be reached")
        return _forbidden


def _runtimes(physical) -> EnterpriseRuntimes:
    return EnterpriseRuntimes(
        physical=physical,
        serial_orientation=_ForbiddenRuntime("serial_orientation"),
        configuration=_ForbiddenRuntime("configuration"),
        control_plane=_ForbiddenRuntime("control_plane"),
    )


#: Las etapas posteriores solo se alcanzan con una topologia desplegable, y eso
#: exige inventario de puertos verificado contra el backend. La seleccion sin
#: preferencia elige `1941`, que nadie midio nunca, asi que el preflight de
#: puertos cortaria antes de llegar a lo que estos tests examinan. Dirigir a un
#: modelo calificado mueve la corrida hasta la etapa bajo prueba; el rechazo del
#: modelo sin medir esta fijado en `test_stage3a4_offline_adversarial_matrix`.
_QUALIFIED = HardwarePlanningPolicy(preferred_router_model="2911")


def _run(
    physical, *, preflight, intent=None, policy=_QUALIFIED,
    capability_store=None, packet_tracer_version="9.0.1.0858",
):
    return execute_enterprise_reference(
        intent or _intent(),
        _runtimes(physical),
        _control_plane_intent(),
        environment_fingerprint=FINGERPRINT.model_copy(update={
            "backend_version": packet_tracer_version,
        }),
        import_preflight=preflight,
        packet_tracer_version=packet_tracer_version,
        capability_store=capability_store,
        policy=policy,
    )


def _isolated_preflight() -> ImportIsolationPreflight:
    return ImportIsolationPreflight(
        REPO,
        executable=lambda: str(checkout_venv_python(REPO)),
        environment_prefix=lambda: str(checkout_venv_root(REPO)),
        resolve_package_file=lambda: str(
            REPO / "src" / "packet_tracer_mcp" / "__init__.py",
        ),
        modules=lambda: {},
    )


def _refusing_preflight() -> ImportIsolationPreflight:
    return ImportIsolationPreflight(
        REPO,
        executable=lambda: str(foreign_python(REPO)),
        environment_prefix=lambda: str(REPO.parent / "foreign-environment"),
        resolve_package_file=lambda: None,
        modules=lambda: {},
    )


class TestAGateThatRefusesNeverLetsAMutationThrough:
    def test_a_failed_import_preflight_blocks_before_any_packet_tracer_call(self):
        """Ni siquiera el inventario de solo lectura llega a ejecutarse."""
        physical = _RecordingPhysicalRuntime()

        result = _run(physical, preflight=_refusing_preflight())

        assert result.status is EnterpriseExecutionStatus.BLOCKED
        assert result.stopped_at is EnterpriseExecutionStage.IMPORT_PREFLIGHT
        assert result.import_isolation.state is ImportIsolationState.FOREIGN_INTERPRETER
        assert physical.calls == []
        assert not result.mutated

    def test_a_workspace_with_user_topology_hard_stops_without_mutating(self):
        """G3: inventariar no es permiso. Topologia semantica presente -> alto."""
        physical = _RecordingPhysicalRuntime(workspace=PhysicalWorkspaceObservation(
            devices=[
                PhysicalWorkspaceDeviceObservation(
                    name="StudentRouter0", model="2911", backend_managed=False,
                ),
            ],
        ))

        result = _run(physical, preflight=_isolated_preflight())

        assert result.status is EnterpriseExecutionStatus.BLOCKED
        assert result.stopped_at is EnterpriseExecutionStage.WORKSPACE_INVENTORY
        assert physical.calls == ["observe_workspace"]
        assert physical.removed == []
        assert "Workspace is not empty" in " ".join(result.errors)

    def test_an_incomplete_inventory_blocks_rather_than_assuming_empty(self):
        physical = _RecordingPhysicalRuntime(workspace=PhysicalWorkspaceObservation(
            observed=False, message="bridge returned no inventory",
        ))

        result = _run(physical, preflight=_isolated_preflight())

        assert result.status is EnterpriseExecutionStatus.BLOCKED
        assert result.stopped_at is EnterpriseExecutionStage.WORKSPACE_INVENTORY
        assert physical.removed == []

    def test_a_blocked_run_reports_no_cleanup_because_none_happened(self):
        """`inventory_restored=None` es la respuesta honesta si no se muto."""
        physical = _RecordingPhysicalRuntime()

        result = _run(physical, preflight=_refusing_preflight())

        assert result.cleanup_results == []
        assert result.inventory_restored is None


class TestAFailedStageStopsTheRestAndStillCleansUp:
    def test_a_failed_physical_deployment_never_reaches_configuration(self):
        """Las etapas siguientes usan runtimes que fallan si alguien las toca."""
        physical = _RecordingPhysicalRuntime(fail_devices=True)

        result = _run(physical, preflight=_isolated_preflight())

        assert result.status is EnterpriseExecutionStatus.FAILED
        assert result.stopped_at is EnterpriseExecutionStage.PHYSICAL_DEPLOYMENT
        assert result.configuration_result is None
        assert result.control_plane_result is None
        assert result.foundational_statuses == {}

    def test_a_failed_deployment_still_removes_what_it_attempted(self):
        """Se usa la forma acotada porque el sujeto es la limpieza, no el tamano.

        La intencion de referencia elige `2950T-24` para sus bloques de acceso,
        y ese modelo no tiene inventario de puertos medido, asi que el preflight
        cortaria antes de intentar el primer dispositivo -- sin intento no hay
        nada que limpiar, y esta fila dejaria de probar su enunciado. Con la
        forma acotada la corrida llega al `ensure_device` que el doble hace
        fallar, que es exactamente la condicion bajo prueba.
        """
        physical = _RecordingPhysicalRuntime(fail_devices=True)

        result = _run(physical, preflight=_isolated_preflight(), intent=_bounded_intent())

        assert physical.removed, "cleanup must run after a failure"
        assert result.cleanup_results
        assert "observe_workspace" in physical.calls[-1:] or result.final_inventory is not None

    def test_a_preflight_refusal_removes_nothing_at_all(self, tmp_path):
        """Lo planificado no es lo creado, y borrar por nombre seria mutar ajeno.

        Se usa un store hermetico y el 2811 exact-build ya calificado. El
        runtime niega la observabilidad del efecto del modulo en preflight,
        antes de tocar nada. Antes de esta correccion la limpieza recorria
        `topology.devices` y pedia borrar los nombres igual.

        Lo que la fila prueba es rechazo de preflight sin mutacion ni limpieza
        inventada; el tipo concreto de evidencia negada no cambia ese contrato.
        """
        physical = _RecordingPhysicalRuntime()
        store = CapabilitySnapshotStore(tmp_path / "capabilities")

        result = _run(
            physical,
            preflight=_isolated_preflight(),
            policy=HardwarePlanningPolicy(preferred_router_model="2811"),
            capability_store=store,
        )

        assert result.deployment is not None
        assert result.deployment.failure_code is (
            PhysicalDeploymentFailureCode.MODULE_OBSERVATION_UNAVAILABLE
        )
        assert physical.removed == []
        assert result.cleanup_results == []

    def test_cleanup_re_observes_instead_of_trusting_the_removal_calls(self):
        physical = _RecordingPhysicalRuntime(fail_devices=True)

        result = _run(physical, preflight=_isolated_preflight())

        assert result.final_inventory is not None
        assert result.inventory_restored is True
        assert physical.calls.count("observe_workspace") >= 2

    def test_cleanup_requires_two_independent_post_cleanup_observations(self):
        physical = _RecordingPhysicalRuntime(fail_devices=True)

        result = _run(physical, preflight=_isolated_preflight())

        assert physical.calls.count("observe_workspace") >= 4
        assert physical.calls[-2:] == ["observe_workspace", "observe_workspace"]
        assert result.final_inventory is not None
        assert result.confirmation_inventory is not None
        assert result.cleanup_confirmed_twice is True

    def test_execution_reports_reached_stage_durations_and_counters(self):
        physical = _RecordingPhysicalRuntime(fail_devices=True)

        result = _run(physical, preflight=_isolated_preflight())

        stages = [item.stage for item in result.stage_metrics]
        assert stages[:4] == [
            EnterpriseExecutionStage.IMPORT_PREFLIGHT,
            EnterpriseExecutionStage.WORKSPACE_INVENTORY,
            EnterpriseExecutionStage.COMPOSE,
            EnterpriseExecutionStage.PHYSICAL_DEPLOYMENT,
        ]
        assert stages[-3:] == [
            EnterpriseExecutionStage.CLEANUP,
            EnterpriseExecutionStage.POST_CLEANUP_OBSERVATION_1,
            EnterpriseExecutionStage.POST_CLEANUP_OBSERVATION_2,
        ]
        assert all(item.duration_ms >= 0 for item in result.stage_metrics)
        assert all(item.item_count >= 0 for item in result.stage_metrics)

    def test_e4_identity_is_unchanged_across_the_whole_run(self):
        physical = _RecordingPhysicalRuntime(fail_devices=True)

        result = _run(physical, preflight=_isolated_preflight())

        assert result.e4_identity_preserved is True


class TestCompositionFailsBeforeTouchingPacketTracer:
    def test_an_invalid_intent_blocks_at_compose_with_no_mutation(self):
        """La validacion E4 corta antes de desplegar, no durante."""
        physical = _RecordingPhysicalRuntime()
        empty = _reference_planning_intent().model_copy(update={"sites": []})

        result = _run(physical, preflight=_isolated_preflight(), intent=empty)

        assert result.status is EnterpriseExecutionStatus.BLOCKED
        assert result.stopped_at is EnterpriseExecutionStage.COMPOSE
        assert result.errors
        assert physical.calls == ["observe_workspace"]
        assert physical.removed == []
        assert not result.mutated

    def test_composition_runs_only_after_both_gates_pass(self):
        """El orden importa: componer es despues de los gates, no antes."""
        physical = _RecordingPhysicalRuntime(fail_devices=True)

        result = _run(physical, preflight=_isolated_preflight())

        assert result.composition is not None
        assert result.composition.topology is not None
        assert physical.calls[0] == "observe_workspace"


class TestTheProductionNamespaceIsCanonical:
    def test_no_production_module_imports_the_src_namespace(self):
        """Produccion opera sobre `packet_tracer_mcp.*`, nunca sobre `src.*`.

        Espejo del escaneo inverso en `test_worktree_isolation.py`, que vigila
        que ningun test importe el nombre pelado. Este vigila lo contrario y por
        el mismo motivo: dos identidades del mismo codigo rompen `isinstance` en
        silencio, y el preflight en vivo es la ultima red, no la primera.
        """
        offenders: list[str] = []
        for path in PACKAGE.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    roots = {node.module.split(".")[0]}
                else:
                    continue
                if "src" in roots:
                    offenders.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")

        assert offenders == [], f"production code importing the test namespace: {offenders}"
