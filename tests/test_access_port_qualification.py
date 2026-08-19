"""La pasada que cualifica la lectura de puerto de acceso, y sus negativas.

`TD-ACCESSPORT-READBACK-001` exige que la lectura quede cualificada contra
salida real capturada de una sesión controlada sobre un switch desechable.
`AccessPortReadbackQualifier` es esa pasada. Lo que estos tests fijan es lo que
se niega a hacer, y una regresión que ya costó una fuga real:

* **el desechable se registra para limpieza en cuanto existe**, no cuando la
  medición termina bien. La primera versión devolvía "se creó" junto al
  resultado, así que una excepción posterior a la creación dejaba el switch
  puesto en el workspace del operador. Pasó de verdad;
* tres controles o ninguno: sin troncal no hay con qué medir el refuse de modo;
* no muta un workspace que no encontró vacío;
* limpia pase lo que pase y compara la restauración contra la línea base.
"""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.qualify_access_port_readback import (
    CONTROL_VLAN_ID,
    QUALIFICATION_PREFIX,
    AccessPortReadbackQualifier,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeVerification,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    MutationDisposition,
    PhysicalDeviceObservation,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    IosSessionState,
)

_PORTS = [f"FastEthernet0/{index}" for index in range(1, 6)] + ["Vlan1"]


class _Physical:
    def __init__(
        self,
        *,
        create_ok: bool = True,
        remove_ok: bool = True,
        observe_raises: bool = False,
        preexisting: list[str] | None = None,
        ports: list[str] | None = None,
    ) -> None:
        self._create_ok = create_ok
        self._remove_ok = remove_ok
        self._observe_raises = observe_raises
        self._preexisting = list(preexisting or [])
        self._ports = list(_PORTS if ports is None else ports)
        self.live: list[str] = []
        self.calls: list[str] = []

    def observe_workspace(self) -> PhysicalWorkspaceObservation:
        self.calls.append("observe_workspace")
        return PhysicalWorkspaceObservation(
            observed=True,
            devices=[
                PhysicalWorkspaceDeviceObservation(name=name, model="2950T-24")
                for name in [*self._preexisting, *self.live]
            ],
            links=[],
        )

    def ensure_device(self, device) -> PhysicalMutationResult:
        self.calls.append(f"ensure_device:{device.name}")
        if self._create_ok:
            self.live.append(device.name)
        return PhysicalMutationResult(
            target_id=device.id, target_kind=PhysicalObjectKind.DEVICE,
            disposition=(
                MutationDisposition.CHANGED if self._create_ok
                else MutationDisposition.FAILED
            ),
            applied=self._create_ok,
            message="" if self._create_ok else "backend refused",
        )

    def observe_device(self, device) -> PhysicalDeviceObservation:
        self.calls.append(f"observe_device:{device.name}")
        if self._observe_raises:
            raise RuntimeError("the read-back blew up after the device existed")
        return PhysicalDeviceObservation(
            target_id=device.id, observed=True, deployed_name=device.name,
            model=device.model, interfaces=list(self._ports),
        )

    def remove_device(self, device) -> PhysicalMutationResult:
        self.calls.append(f"remove_device:{device.name}")
        if self._remove_ok and device.name in self.live:
            self.live.remove(device.name)
        return PhysicalMutationResult(
            target_id=device.id, target_kind=PhysicalObjectKind.DEVICE,
            disposition=(
                MutationDisposition.CHANGED if self._remove_ok
                else MutationDisposition.FAILED
            ),
            applied=self._remove_ok,
            message="" if self._remove_ok else "still there",
        )


class _Configuration:
    def __init__(self, *, applied: bool = True) -> None:
        self._applied = applied
        self.actions: list = []
        self.expectations: list = []

    def inventory(self) -> list:
        return []

    def apply_actions(self, actions) -> list:
        self.actions.extend(actions)
        return [
            RuntimeActionMutation(
                action_id=action.id, applied=self._applied, message="",
            )
            for action in actions
        ]

    def verify(self, expectations) -> list:
        self.expectations.extend(expectations)
        return [
            RuntimeVerification(
                expectation_id=item.id,
                status=ActionExecutionStatus.VERIFIED,
                evidence_method="switch_port_object_state",
                fresh_evidence=True,
                fields={"vlan_id": FieldVerificationStatus.VERIFIED},
            )
            for item in expectations
        ]


class _Query:
    def __init__(self, *, output: str = "Access Mode VLAN: 742 (APQUAL)") -> None:
        self._output = output
        self.calls: list[tuple[str, str]] = []

    def execute(self, device_name, query_id, *, interface=""):
        self.calls.append((device_name, interface))
        return IosCommandResult(
            device_name=device_name, query_id=query_id, executed=True,
            output=self._output, session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True, output_complete=False,
            truncated_by_pager=True,
        )


def _qualify(physical=None, configuration=None, query=None):
    physical = physical or _Physical()
    configuration = configuration or _Configuration()
    query = query or _Query()
    qualifier = AccessPortReadbackQualifier(
        physical, configuration, query, name_token="tok",
    )
    return qualifier.qualify("2950T-24"), physical, configuration, query


# ===================== los tres controles ==================================


def test_it_configures_access_and_trunk_and_leaves_one_port_untouched():
    result, _, configuration, _ = _qualify()

    kinds = [item.action_type for item in configuration.actions]
    assert ConfigurationActionType.CREATE_VLAN in kinds
    assert ConfigurationActionType.CONFIGURE_ACCESS_PORT in kinds
    assert ConfigurationActionType.CONFIGURE_TRUNK in kinds
    assert len(result.captures) == 3
    assert [item.expected_vlan for item in result.captures] == [CONTROL_VLAN_ID, None, None]


def test_the_three_controls_are_three_different_ports():
    result, _, _, _ = _qualify()

    interfaces = [item.interface for item in result.captures]
    assert len(set(interfaces)) == 3


def test_a_switch_without_three_ethernet_ports_measures_nothing():
    """Sin troncal no hay refuse que medir, así que no se finge una pasada."""
    physical = _Physical(ports=["FastEthernet0/1", "FastEthernet0/2", "Vlan1"])

    result, _, _, _ = _qualify(physical)

    assert result.captures == ()
    assert any("trunk control" in item for item in result.errors)


def test_the_production_read_back_runs_against_every_control():
    result, _, configuration, _ = _qualify()

    assert len(configuration.expectations) == 3
    assert all(item.expected["vlan_id"] == CONTROL_VLAN_ID for item in configuration.expectations)
    assert all(item.readback is not None for item in result.captures)


# ===================== aislamiento y limpieza ==============================


def test_the_disposable_carries_the_reserved_prefix():
    result, _, _, _ = _qualify()

    assert result.device_name.startswith(QUALIFICATION_PREFIX)


def test_a_non_empty_workspace_is_never_mutated():
    physical = _Physical(preexisting=["OperatorSwitch"])

    result, physical, _, _ = _qualify(physical)

    assert result.captures == ()
    assert "ensure_device" not in " ".join(physical.calls)
    assert any("refuses to mutate" in item for item in result.errors)


def test_a_device_that_existed_is_removed_even_when_the_pass_raises():
    """La fuga real: la limpieza no puede depender de que la medición cierre."""
    physical = _Physical(observe_raises=True)

    result, physical, _, _ = _qualify(physical)

    assert physical.live == []
    assert result.removed == (result.device_name,)
    assert any("observation_raised" in item for item in result.errors)


def test_an_exception_that_escapes_the_measurement_still_cleans_up():
    """La fuga literal: un `ConfigureAccessPort` inválido levantó ValidationError.

    Esa excepción no la atrapaba ningún `except` de la medición, así que
    escapaba antes de que el resultado dijera "se creó" -- y el switch quedó
    puesto en el workspace del operador. Lo que se fija acá es que la limpieza
    ya no depende de que la medición devuelva.
    """

    class _Exploding(AccessPortReadbackQualifier):
        def _capture(self, *args, **kwargs):
            raise ValueError("anything at all, after the device already exists")

    physical = _Physical()
    result = _Exploding(
        physical, _Configuration(), _Query(), name_token="tok",
    ).qualify("2950T-24")

    assert physical.live == []
    assert result.removed == (result.device_name,)
    assert any("qualification_raised" in item for item in result.errors)


def test_a_cleanup_that_did_not_apply_is_reported_not_swallowed():
    physical = _Physical(remove_ok=False)

    result, _, _, _ = _qualify(physical)

    assert result.removed == ()
    assert any("Cleanup did not apply" in item for item in result.errors)


def test_restoration_is_compared_against_the_baseline():
    result, _, _, _ = _qualify()

    assert result.restored is True
    assert result.baseline_inventory is not None
    assert result.final_inventory is not None


def test_a_device_the_backend_refused_to_create_leaves_nothing_behind():
    physical = _Physical(create_ok=False)

    result, physical, _, _ = _qualify(physical)

    assert physical.live == []
    assert result.removed == ()
    assert any("device_not_created" in item for item in result.errors)


# ===================== lo que la captura afirma y lo que no ================


def test_a_paginated_ios_capture_is_never_usable():
    """La consulta IOS midió `--More--`; truncada no sostiene una afirmación."""
    result, _, _, _ = _qualify()

    assert all(item.truncated for item in result.captures)
    assert result.usable_captures == ()


def test_the_ios_query_is_targeted_at_one_interface():
    result, _, _, query = _qualify()

    assert len(query.calls) == 3
    assert all(interface for _device, interface in query.calls)
