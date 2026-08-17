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


def _run(physical, *, preflight, intent=None):
    return execute_enterprise_reference(
        intent or _intent(),
        _runtimes(physical),
        _control_plane_intent(),
        environment_fingerprint=FINGERPRINT,
        import_preflight=preflight,
        packet_tracer_version="9.0.1.0858",
    )


def _isolated_preflight() -> ImportIsolationPreflight:
    return ImportIsolationPreflight(
        REPO,
        executable=lambda: str(REPO / ".venv" / "Scripts" / "python.exe"),
        resolve_package_file=lambda: str(
            REPO / "src" / "packet_tracer_mcp" / "__init__.py",
        ),
        modules=lambda: {},
    )


def _refusing_preflight() -> ImportIsolationPreflight:
    return ImportIsolationPreflight(
        REPO,
        executable=lambda: r"C:\Python312\python.exe",
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
        physical = _RecordingPhysicalRuntime(fail_devices=True)

        result = _run(physical, preflight=_isolated_preflight())

        assert physical.removed, "cleanup must run after a failure"
        assert result.cleanup_results
        assert "observe_workspace" in physical.calls[-1:] or result.final_inventory is not None

    def test_cleanup_re_observes_instead_of_trusting_the_removal_calls(self):
        physical = _RecordingPhysicalRuntime(fail_devices=True)

        result = _run(physical, preflight=_isolated_preflight())

        assert result.final_inventory is not None
        assert result.inventory_restored is True
        assert physical.calls.count("observe_workspace") >= 2

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
