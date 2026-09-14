"""Procedencia del device que produjo una observación de control plane.

MEG-4 run 6 dejó `source_device_name` como el único campo inobservable de dos
lecturas por lo demás verificadas. Este módulo fija el contrato que lo cierra:
la identidad de la fuente sale de la ATRIBUCIÓN de la sesión que ejecutó, nunca
del nombre que se pidió. Es OFFLINE: no toca Packet Tracer.
"""

from __future__ import annotations

import json

import pytest

from src.packet_tracer_mcp.application.use_cases.apply_control_plane import (
    ControlPlaneApplicator,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureRipv2,
    ControlPlaneCapabilityDimension,
    ControlPlanePhase,
    ControlPlanePlan,
    ControlPlaneVerificationExpectation,
    ControlPlaneVerificationKind,
    RipNetwork,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentIdentityError,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
    PacketTracerEnterpriseControlPlaneRuntime,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    DeviceIdentityEvidence,
    DeviceIdentityProvenance,
    IosCommandResult,
    IosSessionState,
    OperationalQueryId,
)


# ==========================================================================
# A. La envolvente de ejecución: quién produjo la sesión
# ==========================================================================

_BASELINE = "Router con0 is now available\n\nPress RETURN to get started.\n\nRouter>"
_TRANSCRIPT = _BASELINE + "show ip protocols\nRouting Protocol is \"rip\"\nRouter>"


def _session_responses(*, attribution: dict) -> list[str]:
    """Las cuatro respuestas de una ejecución registrada, en orden."""
    return [
        json.dumps({
            "found": True, "booting": False, "terminal": True,
            "prompt": "Router>", "output": _BASELINE,
        }),
        json.dumps({"ok": True, "before": _BASELINE}),
        json.dumps({
            "found": True, "configuration_channel": True, "output": _TRANSCRIPT,
        }),
        json.dumps(attribution),
    ]


def _execute(attribution: dict, *, device_name: str = "R1"):
    sent: list[str] = []
    responses = iter(_session_responses(attribution=attribution))

    def terminal(script: str, _timeout: float) -> str:
        sent.append(script)
        return next(responses)

    result = ControlledIosExecutor(terminal).execute(
        device_name, OperationalQueryId.SHOW_IP_PROTOCOLS,
    )
    return result, sent


def _attribution(**updates) -> dict:
    values = {
        "found": True,
        "configuration_channel": True,
        "output": _TRANSCRIPT,
        "owner_name": "R1",
        "owner_evidence": DeviceIdentityEvidence.TERMINAL_OBJECT_IDENTITY.value,
        "owner_candidates": 1,
        "device_count": 8,
    }
    values.update(updates)
    return values


def test_terminal_object_identity_attributes_the_executing_session():
    result, _ = _execute(_attribution())

    assert result.executed
    assert result.observed_device_name == "R1"
    assert result.device_identity_provenance == (
        DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
    )
    assert result.device_identity_evidence == (
        DeviceIdentityEvidence.TERMINAL_OBJECT_IDENTITY.value
    )


def test_session_transcript_continuity_attributes_the_executing_session():
    result, _ = _execute(_attribution(
        owner_evidence=DeviceIdentityEvidence.SESSION_TRANSCRIPT_CONTINUITY.value,
    ))

    assert result.executed
    assert result.observed_device_name == "R1"
    assert result.device_identity_provenance == (
        DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
    )


def test_the_attribution_enumerates_the_network_instead_of_trusting_the_request():
    _, sent = _execute(_attribution())

    attribution_script = sent[-1]
    assert "getDeviceCount()" in attribution_script
    assert "getDeviceAt(i)" in attribution_script
    assert "dev.getName()" in attribution_script
    # La atribución se decide comparando el objeto terminal y la continuidad de
    # la transcripción, no el nombre pedido.
    assert "cl===t" in attribution_script
    # Ancla por SUFIJO retenido, no por prefijo: `fresh_command_window` ya midió
    # que una sesión fresca puede dejar de empezar por su línea base -- el pager
    # borra su marcador al salir y un buffer largo rueda por la cabeza. Exigir
    # prefijo dejaba esas lecturas sin atribuir, que es el hueco que MEG-4 run 7
    # midió en vivo.
    assert "co.indexOf(anchor)" in attribution_script
    assert "co.indexOf(base)===0" not in attribution_script
    # Y el comando despachado detrás de ese contexto: un gemelo ocioso no basta
    # con compartir banner de arranque.
    assert '"show ip protocols"' in attribution_script
    assert "indexOf(cmd)>=0" in attribution_script


def test_a_session_owned_by_another_device_never_returns_evidence_for_the_requested_one():
    """Pedido A, ejecutado en B: A no puede certificarse, ni con la salida."""
    result, _ = _execute(_attribution(owner_name="R2"))

    assert not result.executed
    assert result.output == ""
    assert result.observed_device_name == "R2"
    assert result.device_identity_provenance == (
        DeviceIdentityProvenance.MISMATCHED.value
    )
    assert "DEVICE_PROVENANCE_MISMATCH" in result.failure_reason
    assert "'R1'" in result.failure_reason and "'R2'" in result.failure_reason


def test_more_than_one_candidate_owner_is_ambiguous_rather_than_attributed():
    result, _ = _execute(_attribution(owner_name="", owner_candidates=2))

    assert result.executed
    assert result.observed_device_name == ""
    assert result.device_identity_provenance == (
        DeviceIdentityProvenance.AMBIGUOUS.value
    )


def test_a_session_that_could_not_be_attributed_stays_not_observed():
    result, _ = _execute({
        "found": True, "configuration_channel": True, "output": _TRANSCRIPT,
    })

    assert result.executed
    assert result.observed_device_name == ""
    assert result.device_identity_provenance == (
        DeviceIdentityProvenance.NOT_OBSERVED.value
    )
    assert result.device_identity_evidence == DeviceIdentityEvidence.NONE.value


def test_an_owner_without_a_recognised_evidence_path_is_not_an_attribution():
    result, _ = _execute(_attribution(owner_evidence="because_it_was_requested"))

    assert result.observed_device_name == ""
    assert result.device_identity_provenance == (
        DeviceIdentityProvenance.NOT_OBSERVED.value
    )


# ==========================================================================
# B. La observación: qué puede certificar esa procedencia
# ==========================================================================

_RIP_OUTPUT = (
    "show ip protocols\n"
    'Routing Protocol is "rip"\n'
    "Sending updates every 30 seconds, next due in 21 seconds\n"
    "Invalid after 180 seconds, hold down 180, flushed after 240\n"
    "Outgoing update filter list for all interfaces is not set\n"
    "Incoming update filter list for all interfaces is not set\n"
    "Redistributing: rip\n"
    "Default version control: send version 2, receive 2\n"
    "  Interface             Send  Recv  Triggered RIP  Key-chain\n"
    "  GigabitEthernet0/1    2     2                                    \n"
    "Automatic network summarization is not in effect\n"
    "Maximum path: 4\n"
    "Routing for Networks:\n"
    "\t150.1.0.0\n"
    "Passive Interface(s):\n"
    "\tGigabitEthernet0/0\n"
    "Routing Information Sources:\n"
    "\tGateway         Distance      Last Update\n"
    "Distance: (default is 120)\n"
    "\n"
    "Router>"
)

_RIP_ROUTE_OUTPUT = (
    "show ip route rip\n"
    "R    150.1.2.0/24 [120/1] via 150.1.100.2, 00:00:07, Serial0/0/0\n"
    "\n"
    "Router>"
)


def _rip_action() -> ConfigureRipv2:
    return ConfigureRipv2(
        id="cp/ripv2/provenance",
        phase=ControlPlanePhase.DYNAMIC_ROUTING,
        device_id="r1",
        device_name="A-EDGE-RTR-01",
        model="2911",
        site_id="hq",
        required_capability=ControlPlaneCapabilityDimension.RIPV2_CONFIG,
        networks=[RipNetwork(
            network="150.1.0.0",
            source_segment_ids=["hq-lan"],
            source_configuration_action_ids=["cfg/l3/r1/hq-lan"],
        )],
        passive_interfaces=["GigabitEthernet0/0"],
    )


def _process_expectation(source: str) -> ControlPlaneVerificationExpectation:
    return ControlPlaneVerificationExpectation(
        id="cp/verify-rip/provenance",
        kind=ControlPlaneVerificationKind.ROUTING_PROCESS,
        action_id="cp/ripv2/provenance",
        device_id="r1",
        required_capability=ControlPlaneCapabilityDimension.RIPV2_CONFIG,
        expected={
            "protocol": "ripv2",
            "version_send": 2,
            "version_recv": 2,
            "auto_summary": False,
            "networks": ["150.1.0.0"],
            "passive_interfaces": ["GigabitEthernet0/0"],
            "source_device_name": source,
        },
    )


def _route_expectation(source: str) -> ControlPlaneVerificationExpectation:
    return ControlPlaneVerificationExpectation(
        id="cp/verify-rip-route/provenance",
        kind=ControlPlaneVerificationKind.ROUTE_PRESENT,
        action_id="cp/ripv2/provenance",
        device_id="r1",
        required_capability=ControlPlaneCapabilityDimension.RIPV2_CONFIG,
        expected={
            "protocol": "ripv2",
            "network": "150.1.2.0",
            "prefix_length": 24,
            "source_device_name": source,
        },
    )


class _FakeIos:
    def __init__(self, result: IosCommandResult) -> None:
        self._result = result
        self.calls: list[tuple[str, OperationalQueryId]] = []

    def execute(self, device_name, query_id, *, interface=""):
        assert not interface
        self.calls.append((device_name, query_id))
        return self._result


def _show(output: str, query_id: OperationalQueryId, **updates) -> IosCommandResult:
    values = {
        "device_name": "A-EDGE-RTR-01",
        "query_id": query_id,
        "executed": True,
        "output": output,
        "session_state": IosSessionState.EXEC_PROMPT_READY,
        "fresh_output_observed": True,
        "window_strategy": "prefix_delta",
        "observed_device_name": "A-EDGE-RTR-01",
        "device_identity_provenance": (
            DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
        ),
        "device_identity_evidence": (
            DeviceIdentityEvidence.TERMINAL_OBJECT_IDENTITY.value
        ),
    }
    values.update(updates)
    return IosCommandResult(**values)


def _verify(expectation, show: IosCommandResult):
    action = _rip_action()
    ios = _FakeIos(show)
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda _script: True,
        lambda _script, _timeout: None,
        ios_executor=ios,
        route_convergence_attempts=1,
        route_convergence_timeout_seconds=0.0,
        route_convergence_interval_seconds=0.0,
        sleeper=lambda _seconds: None,
    )
    runtime.apply_actions([action])
    return runtime.verify([expectation])[0]


@pytest.mark.parametrize(
    ("expectation_factory", "output", "query_id"),
    [
        (_process_expectation, _RIP_OUTPUT, OperationalQueryId.SHOW_IP_PROTOCOLS),
        (_route_expectation, _RIP_ROUTE_OUTPUT, OperationalQueryId.SHOW_IP_ROUTE_RIP),
    ],
    ids=["rip-process", "rip-learned-route"],
)
def test_execution_provenance_closes_the_source_device_field(
    expectation_factory, output, query_id,
):
    result = _verify(
        expectation_factory("A-EDGE-RTR-01"), _show(output, query_id),
    )

    assert result.fields["source_device_name"] is FieldVerificationStatus.VERIFIED
    assert set(result.fields.values()) == {FieldVerificationStatus.VERIFIED}
    assert result.status is ActionExecutionStatus.VERIFIED


@pytest.mark.parametrize(
    ("expectation_factory", "output", "query_id"),
    [
        (_process_expectation, _RIP_OUTPUT, OperationalQueryId.SHOW_IP_PROTOCOLS),
        (_route_expectation, _RIP_ROUTE_OUTPUT, OperationalQueryId.SHOW_IP_ROUTE_RIP),
    ],
    ids=["rip-process", "rip-learned-route"],
)
def test_evidence_attributed_to_another_device_fails_instead_of_certifying(
    expectation_factory, output, query_id,
):
    """Mezcla de resultados entre devices: es un defecto, no una ausencia."""
    result = _verify(
        expectation_factory("A-EDGE-RTR-01"),
        _show(output, query_id, observed_device_name="B-EDGE-RTR-01"),
    )

    assert result.fields["source_device_name"] is FieldVerificationStatus.FAILED
    assert result.status is ActionExecutionStatus.FAILED


@pytest.mark.parametrize(
    "provenance",
    [
        DeviceIdentityProvenance.NOT_OBSERVED,
        DeviceIdentityProvenance.AMBIGUOUS,
    ],
    ids=["unattributed", "ambiguous"],
)
def test_without_a_unique_attribution_the_source_stays_unobservable(provenance):
    result = _verify(
        _process_expectation("A-EDGE-RTR-01"),
        _show(
            _RIP_OUTPUT,
            OperationalQueryId.SHOW_IP_PROTOCOLS,
            observed_device_name="",
            device_identity_provenance=provenance.value,
            device_identity_evidence=DeviceIdentityEvidence.NONE.value,
        ),
    )

    assert result.fields["source_device_name"] is (
        FieldVerificationStatus.UNOBSERVABLE
    )
    assert result.status is ActionExecutionStatus.UNOBSERVABLE


def test_an_unknown_provenance_classification_never_certifies():
    result = _verify(
        _process_expectation("A-EDGE-RTR-01"),
        _show(
            _RIP_OUTPUT,
            OperationalQueryId.SHOW_IP_PROTOCOLS,
            device_identity_provenance="attributed_somehow",
        ),
    )

    assert result.fields["source_device_name"] is (
        FieldVerificationStatus.UNOBSERVABLE
    )
    assert result.status is ActionExecutionStatus.UNOBSERVABLE


def test_a_provenance_mismatch_at_the_executor_yields_no_observation_at_all():
    """El ejecutor no devuelve la sesión ajena, así que nada puede certificar."""
    result = _verify(
        _process_expectation("A-EDGE-RTR-01"),
        _show(
            "",
            OperationalQueryId.SHOW_IP_PROTOCOLS,
            executed=False,
            fresh_output_observed=False,
            observed_device_name="B-EDGE-RTR-01",
            device_identity_provenance=DeviceIdentityProvenance.MISMATCHED.value,
            failure_reason=(
                "DEVICE_PROVENANCE_MISMATCH: requested 'A-EDGE-RTR-01' but the "
                "executing session is owned by 'B-EDGE-RTR-01'."
            ),
        ),
    )

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert set(result.fields.values()) == {FieldVerificationStatus.UNOBSERVABLE}
    assert "DEVICE_PROVENANCE_MISMATCH" in result.message


def test_an_absent_rip_process_still_keeps_the_observed_provenance():
    result = _verify(
        _process_expectation("A-EDGE-RTR-01"),
        _show("show ip protocols\n\nRouter>", OperationalQueryId.SHOW_IP_PROTOCOLS),
    )

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["source_device_name"] is FieldVerificationStatus.VERIFIED
    assert result.fields["protocol"] is FieldVerificationStatus.FAILED


# ==========================================================================
# C. El manifiesto: a qué device semántico pertenece el nombre atribuido
# ==========================================================================

def _plan() -> ControlPlanePlan:
    return ControlPlanePlan(
        id="cp/plan/provenance",
        source_topology_id="topo",
        source_topology_hash="hash",
        source_configuration_id="cfg",
        source_configuration_hash="cfghash",
        actions=[_rip_action()],
        verification_expectations=[_process_expectation("")],
    )


def test_two_semantic_devices_bound_to_one_runtime_target_are_refused():
    with pytest.raises(DeploymentIdentityError) as excinfo:
        ControlPlaneApplicator._runtime_plan(
            _plan(), {"r1": "A-EDGE-RTR-01", "r2": "A-EDGE-RTR-01"},
        )

    assert "A-EDGE-RTR-01" in str(excinfo.value)


def test_a_unique_manifest_binding_names_the_source_device():
    runtime_plan = ControlPlaneApplicator._runtime_plan(
        _plan(), {"r1": "A-EDGE-RTR-01", "r2": "B-EDGE-RTR-01"},
    )

    assert runtime_plan.verification_expectations[0].expected[
        "source_device_name"
    ] == "A-EDGE-RTR-01"
