"""Runtime E9: mutaciones cerradas, evidencia tipada y restauración obligatoria."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneCapabilityDimension,
    ControlPlaneVerificationExpectation,
    ControlPlaneVerificationKind,
    EtherChannelProtocol,
    StpMode,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane_runtime import (
    ControlPlaneExecutionStage,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
    PacketTracerEnterpriseControlPlaneRuntime,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    IosSessionState,
    OperationalQueryId,
)
from src.packet_tracer_mcp.infrastructure.execution.typed_ping import TypedPingResult
from test_enterprise_control_plane import _compile
from test_ios_terminal import (
    _PT_9_0_1_0858_EIGRP_NEIGHBORS_R1,
    _PT_9_0_1_0858_EIGRP_NEIGHBORS_EMPTY,
    _PT_9_0_1_0858_EIGRP_PROTOCOL_R1,
    _PT_9_0_1_0858_EIGRP_ROUTE_R1,
    _PT_9_0_1_0858_EIGRP_ROUTES_EMPTY,
    _PT_9_0_1_0858_ETHERCHANNEL_SUMMARY,
    _PT_9_0_1_0858_OSPF_NEIGHBOR_R1,
    _PT_9_0_1_0858_OSPF_ROUTE_R1,
    _PT_9_0_1_0858_STP_NON_ROOT,
    _PT_9_0_1_0858_STP_ROOT,
)


class SequencePing:
    def __init__(self, outcomes: Iterable[TypedPingResult | Exception]) -> None:
        self.outcomes = iter(outcomes)
        self.calls: list[tuple[str, str]] = []

    def ping(self, source_device: str, destination: str) -> TypedPingResult:
        self.calls.append((source_device, destination))
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeControlPlaneIos:
    def __init__(self, outputs) -> None:
        self.outputs = outputs
        self.calls: list[tuple[str, OperationalQueryId]] = []

    def execute(self, device_name, query_id, *, interface=""):
        assert not interface
        self.calls.append((device_name, query_id))
        value = self.outputs[(device_name, query_id)]
        if isinstance(value, IosCommandResult):
            return value
        return IosCommandResult(
            device_name=device_name,
            query_id=query_id,
            executed=True,
            output=value,
            session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True,
            output_complete=True,
            window_strategy="prefix_delta",
        )


class SequenceControlPlaneIos:
    def __init__(self, outcomes: Iterable[IosCommandResult]) -> None:
        self.outcomes = iter(outcomes)
        self.calls: list[tuple[str, OperationalQueryId, str]] = []

    def execute(self, device_name, query_id, *, interface=""):
        self.calls.append((device_name, query_id, interface))
        return next(self.outcomes)


def _stp_output(*, root_vlans: set[int]) -> str:
    blocks: list[str] = []
    for vlan_id in (10, 20):
        fixture = (
            _PT_9_0_1_0858_STP_ROOT
            if vlan_id in root_vlans else _PT_9_0_1_0858_STP_NON_ROOT
        )
        block = fixture.split("show spanning-tree\n", 1)[1].rsplit("Switch>", 1)[0]
        blocks.append(block.replace("VLAN0001", f"VLAN{vlan_id:04d}"))
    return "show spanning-tree\n" + "".join(blocks) + "Switch>"


def _ping(reachable: bool, *, fresh: bool = True) -> TypedPingResult:
    return TypedPingResult(
        reachable=reachable,
        fresh_output_observed=fresh,
        window_strategy="prefix_delta" if fresh else "none",
        failure_reason="" if fresh else "no_fresh_ping_result",
    )


def _failure_parts(plan):
    scenario = plan.failure_scenarios[0]
    expectations = {
        item.id: item for item in plan.verification_expectations
        if item.id in scenario.verification_expectation_ids
    }
    failure = next(
        item for item in expectations.values()
        if item.kind is ControlPlaneVerificationKind.LINK_FAILURE_CONVERGENCE
    )
    recovery = next(
        item for item in expectations.values()
        if item.kind is ControlPlaneVerificationKind.RESTORE_RECOVERY
    )
    return scenario, failure, recovery


def test_runtime_applies_every_compiled_action_through_closed_ios_route():
    plan = _compile().plan
    sent: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda script: sent.append(script) or True,
        lambda _script, _timeout: None,
    )

    results = runtime.apply_actions(plan.actions)

    assert len(results) == len(plan.actions)
    assert all(item.applied for item in results)
    assert len(sent) == len(plan.actions)
    assert all("configureIosDevice" in script for script in sent)
    assert not any("getCommandPrompt" in script for script in sent)


def test_only_typed_reachability_can_be_verified():
    plan = _compile().plan
    actions = {item.id: item for item in plan.actions}
    reachability = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
        and item.expected.get("destination_ipv4")
        and actions[item.action_id].device_id == item.device_id
    )
    direct = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS
    )
    ping = SequencePing([_ping(True)])
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=ping,
    )
    runtime.apply_actions(plan.actions)

    verified, unobservable = runtime.verify([reachability, direct])

    source = actions[reachability.action_id].device_name
    assert ping.calls == [(source, reachability.expected["destination_ipv4"])]
    assert verified.stage is ControlPlaneExecutionStage.BEHAVIOR
    assert verified.fresh_evidence
    # Contabilidad normal: TODO campo reclamado aparece. Esta prueba afirmaba
    # antes `fields == {"reachable": ...}`, que era el defecto: el observador
    # construia el mapa a mano y los demas campos reclamados desaparecian del
    # resultado en lugar de reportarse como no observados.
    assert set(verified.fields) == set(reachability.expected)
    assert verified.fields["reachable"] is FieldVerificationStatus.VERIFIED
    # El agregado se queda abajo porque esta expectativa reclama campos que
    # ninguna medida observa. Es el techo real de una afirmacion de reenvio, no
    # un fallo: nada se cae, simplemente no todo se observa.
    assert verified.status is ActionExecutionStatus.UNOBSERVABLE
    assert FieldVerificationStatus.FAILED not in set(verified.fields.values())
    assert unobservable.stage is ControlPlaneExecutionStage.OBSERVED
    assert unobservable.status is ActionExecutionStatus.UNOBSERVABLE
    assert not unobservable.fresh_evidence


def test_reachability_without_fresh_ping_evidence_is_unobservable_not_verified():
    plan = _compile().plan
    actions = {item.id: item for item in plan.actions}
    reachability = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
        and item.expected.get("destination_ipv4")
        and actions[item.action_id].device_id == item.device_id
    )
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([_ping(False, fresh=False)]),
    )
    runtime.apply_actions(plan.actions)

    result = runtime.verify([reachability])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.fields["reachable"] is FieldVerificationStatus.UNOBSERVABLE


def test_nonboolean_reachability_expectation_is_never_promoted():
    plan = _compile().plan
    actions = {item.id: item for item in plan.actions}
    reachability = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
        and item.expected.get("destination_ipv4")
        and actions[item.action_id].device_id == item.device_id
    ).model_copy(deep=True)
    reachability.expected["reachable"] = "false"
    ping = SequencePing([_ping(True)])
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=ping,
    )
    runtime.apply_actions(plan.actions)

    result = runtime.verify([reachability])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert ping.calls == []


def test_direct_control_plane_state_uses_only_fresh_registered_ios_evidence():
    plan = _compile().plan
    expectations = [
        next(item for item in plan.verification_expectations
             if item.kind is ControlPlaneVerificationKind.STP_STATE
             and item.device_id == "sw1"),
        next(item for item in plan.verification_expectations
             if item.kind is ControlPlaneVerificationKind.ETHERCHANNEL_STATE
             and item.device_id == "sw1"),
        next(item for item in plan.verification_expectations
             if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS
             and item.device_id == "r1"),
        next(item for item in plan.verification_expectations
             if item.kind is ControlPlaneVerificationKind.ROUTING_NEIGHBOR
             and item.device_id == "r1"),
        next(item for item in plan.verification_expectations
             if item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
             and item.device_id == "r1"),
        next(item for item in plan.verification_expectations
             if item.kind is ControlPlaneVerificationKind.HSRP_STATE
             and item.device_id == "r1"),
        next(item for item in plan.verification_expectations
             if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS
             and item.device_id == "b1"),
    ]
    ios = FakeControlPlaneIos({
        ("HQ-SW1", OperationalQueryId.SHOW_SPANNING_TREE):
            _stp_output(root_vlans={10}),
        ("HQ-SW1", OperationalQueryId.SHOW_ETHERCHANNEL_SUMMARY):
            _PT_9_0_1_0858_ETHERCHANNEL_SUMMARY
            .replace("Fa0/1", "Gi0/1").replace("Fa0/2", "Gi0/2"),
        ("HQ-R1", OperationalQueryId.SHOW_IP_OSPF_NEIGHBOR):
            _PT_9_0_1_0858_OSPF_NEIGHBOR_R1
            .replace("2.2.2.2", "10.0.10.3")
            .replace("198.18.100.2", "10.255.0.2"),
        ("HQ-R1", OperationalQueryId.SHOW_IP_ROUTE_OSPF):
            _PT_9_0_1_0858_OSPF_ROUTE_R1
            .replace("198.18.102.0", "10.0.102.0"),
    })
    ping = SequencePing([])
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=ping, ios_executor=ios,
    )
    runtime.apply_actions(plan.actions)

    results = runtime.verify(expectations)

    stp, channel, process, neighbor, route, hsrp, eigrp = results
    assert stp.status is ActionExecutionStatus.VERIFIED
    assert all(item is FieldVerificationStatus.VERIFIED for item in stp.fields.values())
    assert channel.status is ActionExecutionStatus.VERIFIED
    assert all(item is FieldVerificationStatus.VERIFIED for item in channel.fields.values())
    # OSPF estrecho su `expected` a lo que una consulta registrada puede
    # comprobar, pero el techo de evidencia NO se movio: `router_id` sigue
    # apareciendo como no observado y el agregado sigue siendo UNOBSERVABLE.
    assert process.status is ActionExecutionStatus.UNOBSERVABLE
    assert process.fields == {
        "protocol": FieldVerificationStatus.VERIFIED,
        "router_id": FieldVerificationStatus.UNOBSERVABLE,
    }
    assert neighbor.status is ActionExecutionStatus.VERIFIED
    assert all(item is FieldVerificationStatus.VERIFIED for item in neighbor.fields.values())
    assert neighbor.fields["adjacent"] is FieldVerificationStatus.VERIFIED
    assert route.status is ActionExecutionStatus.UNOBSERVABLE
    assert route.fields == {
        "network": FieldVerificationStatus.VERIFIED,
        "prefix_length": FieldVerificationStatus.UNOBSERVABLE,
        "protocol": FieldVerificationStatus.VERIFIED,
        "wildcard": FieldVerificationStatus.UNOBSERVABLE,
        "segment_id": FieldVerificationStatus.UNOBSERVABLE,
    }
    assert hsrp.status is ActionExecutionStatus.UNOBSERVABLE
    assert eigrp.status is ActionExecutionStatus.UNOBSERVABLE
    assert all(item.stage is ControlPlaneExecutionStage.OBSERVED for item in results)
    assert ping.calls == []
    assert ios.calls == [
        ("HQ-SW1", OperationalQueryId.SHOW_SPANNING_TREE),
        ("HQ-SW1", OperationalQueryId.SHOW_ETHERCHANNEL_SUMMARY),
        ("HQ-R1", OperationalQueryId.SHOW_IP_OSPF_NEIGHBOR),
        ("HQ-R1", OperationalQueryId.SHOW_IP_ROUTE_OSPF),
        ("BR-R1", OperationalQueryId.SHOW_IP_PROTOCOLS),
    ]


def test_stp_state_reobserves_without_redispatch_until_an_instance_converges():
    plan = _compile().plan
    stp = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.STP_STATE
        and item.device_id == "sw1"
    )

    def result(output: str) -> IosCommandResult:
        return IosCommandResult(
            device_name="HQ-SW1",
            query_id=OperationalQueryId.SHOW_SPANNING_TREE,
            executed=True,
            output=output,
            session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True,
            output_complete=True,
            window_strategy="prefix_delta",
        )

    ios = SequenceControlPlaneIos((result(""), result(_stp_output(root_vlans={10}))))
    dispatched: list[str] = []

    def dispatch(script: str) -> bool:
        dispatched.append(script)
        return True

    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], dispatch, lambda _script, _timeout: None,
        ping_executor=SequencePing([]),
        ios_executor=ios,
        stp_convergence_timeout_seconds=1.0,
        stp_convergence_interval_seconds=0.0,
        stp_convergence_attempts=2,
    )
    runtime.apply_actions(plan.actions)
    mutation_count = len(dispatched)

    observed = runtime.verify([stp])[0]

    assert observed.status is ActionExecutionStatus.VERIFIED
    assert observed.convergence is not None
    assert observed.convergence.attempts == 2
    assert len(dispatched) == mutation_count
    assert len(ios.calls) == 2


def test_stp_state_reobserves_transitional_rows_before_judging_root_state():
    plan = _compile().plan
    action = next(
        item for item in plan.actions
        if item.device_id == "sw1" and item.action_type.value == "configure_stp"
    )
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.STP_STATE
        and item.device_id == "sw1"
    )

    def result(output: str) -> IosCommandResult:
        return IosCommandResult(
            device_name="HQ-SW1",
            query_id=OperationalQueryId.SHOW_SPANNING_TREE,
            executed=True,
            output=output,
            session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True,
            output_complete=True,
            window_strategy="prefix_delta",
        )

    transitional = _stp_output(root_vlans=set()).replace("Root FWD", "Root LRN")
    ios = SequenceControlPlaneIos((
        result(transitional),
        result(_stp_output(root_vlans={10})),
    ))
    dispatched: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda script: dispatched.append(script) or True,
        lambda _script, _timeout: None,
        ping_executor=SequencePing([]),
        ios_executor=ios,
        stp_convergence_timeout_seconds=1.0,
        stp_convergence_interval_seconds=0.0,
        stp_convergence_attempts=2,
    )
    runtime.apply_actions([action])
    mutation_count = len(dispatched)

    observed = runtime.verify([expectation])[0]

    assert observed.status is ActionExecutionStatus.VERIFIED
    assert observed.convergence is not None
    assert observed.convergence.attempts == 2
    assert len(dispatched) == mutation_count
    assert len(ios.calls) == 2


def test_stp_behavior_uses_fresh_stable_roles_without_dispatching_ping():
    plan = _compile().plan
    action = next(
        item for item in plan.actions
        if item.device_id == "sw1" and item.action_type.value == "configure_stp"
    )
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
        and item.action_id == action.id
    )
    ios = FakeControlPlaneIos({
        ("HQ-SW1", OperationalQueryId.SHOW_SPANNING_TREE):
            _stp_output(root_vlans={10}),
    })
    ping = SequencePing([])
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=ping, ios_executor=ios,
    )
    runtime.apply_actions([action])

    observed = runtime.verify([expectation])[0]

    assert observed.status is ActionExecutionStatus.VERIFIED
    assert observed.evidence_method == "fresh_show_spanning_tree_stable_roles"
    assert observed.fields == {
        "loop_free": FieldVerificationStatus.VERIFIED,
        "forwarding_converged": FieldVerificationStatus.VERIFIED,
    }
    assert observed.convergence is not None
    assert observed.convergence.attempts == 1
    assert ping.calls == []
    assert ios.calls == [
        ("HQ-SW1", OperationalQueryId.SHOW_SPANNING_TREE),
    ]


def test_stp_behavior_reobserves_learning_without_redispatch():
    plan = _compile().plan
    action = next(
        item for item in plan.actions
        if item.device_id == "sw1" and item.action_type.value == "configure_stp"
    )
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
        and item.action_id == action.id
    )

    def result(output: str) -> IosCommandResult:
        return IosCommandResult(
            device_name="HQ-SW1",
            query_id=OperationalQueryId.SHOW_SPANNING_TREE,
            executed=True,
            output=output,
            session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True,
            output_complete=True,
            window_strategy="prefix_delta",
        )

    ios = SequenceControlPlaneIos((
        result(_stp_output(root_vlans={10}).replace("Desg FWD", "Desg LRN")),
        result(_stp_output(root_vlans={10})),
    ))
    dispatched: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda script: dispatched.append(script) or True,
        lambda _script, _timeout: None,
        ping_executor=SequencePing([]),
        ios_executor=ios,
        stp_convergence_timeout_seconds=1.0,
        stp_convergence_interval_seconds=0.0,
        stp_convergence_attempts=2,
    )
    runtime.apply_actions([action])
    mutation_count = len(dispatched)

    observed = runtime.verify([expectation])[0]

    assert observed.status is ActionExecutionStatus.VERIFIED
    assert observed.convergence is not None
    assert observed.convergence.attempts == 2
    assert len(dispatched) == mutation_count
    assert len(ios.calls) == 2


def test_stp_behavior_fails_a_stable_forwarding_alternate_role():
    plan = _compile().plan
    action = next(
        item for item in plan.actions
        if item.device_id == "sw1" and item.action_type.value == "configure_stp"
    )
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
        and item.action_id == action.id
    )
    output = _stp_output(root_vlans={10}).replace("Desg FWD", "Altn FWD")
    ios = FakeControlPlaneIos({
        ("HQ-SW1", OperationalQueryId.SHOW_SPANNING_TREE): output,
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
        stp_convergence_attempts=2,
        stp_convergence_interval_seconds=0.0,
    )
    runtime.apply_actions([action])

    observed = runtime.verify([expectation])[0]

    assert observed.status is ActionExecutionStatus.FAILED
    assert observed.fields["loop_free"] is FieldVerificationStatus.FAILED
    assert observed.fields[
        "forwarding_converged"
    ] is FieldVerificationStatus.VERIFIED
    assert len(ios.calls) == 1


def test_stp_behavior_exhausted_without_instances_stays_unobservable():
    plan = _compile().plan
    action = next(
        item for item in plan.actions
        if item.device_id == "sw1" and item.action_type.value == "configure_stp"
    )
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
        and item.action_id == action.id
    )

    def result() -> IosCommandResult:
        return IosCommandResult(
            device_name="HQ-SW1",
            query_id=OperationalQueryId.SHOW_SPANNING_TREE,
            executed=True,
            output="show spanning-tree\nSwitch>",
            session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True,
            output_complete=True,
            window_strategy="prefix_delta",
        )

    ios = SequenceControlPlaneIos((result(), result()))
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]),
        ios_executor=ios,
        stp_convergence_timeout_seconds=1.0,
        stp_convergence_interval_seconds=0.0,
        stp_convergence_attempts=2,
    )
    runtime.apply_actions([action])

    observed = runtime.verify([expectation])[0]

    assert observed.status is ActionExecutionStatus.UNOBSERVABLE
    assert observed.fresh_evidence is False
    assert all(
        value is FieldVerificationStatus.UNOBSERVABLE
        for value in observed.fields.values()
    )
    assert observed.convergence is not None
    assert observed.convergence.attempts == 2
    assert observed.convergence.last_observable_state == (
        "no_parser_backed_instance"
    )


def test_pvst_state_verifies_ieee_mode_and_compiled_numeric_priorities():
    plan = _compile().plan
    original_action = next(
        item for item in plan.actions
        if item.device_id == "sw1" and item.action_type.value == "configure_stp"
    )
    action = original_action.model_copy(update={
        "mode": StpMode.PVST,
        "required_capability": ControlPlaneCapabilityDimension.STP_PVST_CONFIG,
    })
    original_expectation = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.STP_STATE
        and item.device_id == "sw1"
    )
    expectation = original_expectation.model_copy(update={
        "expected": {
            "mode": "pvst",
            "vlan_ids": [10, 20],
            "root_primary_vlans": [10],
            "root_secondary_vlans": [20],
            "priorities": {10: 24576, 20: 28672},
        },
    })
    output = _stp_output(root_vlans={10}).replace(
        "enabled protocol rstp", "enabled protocol ieee",
    )
    ios = FakeControlPlaneIos({
        ("HQ-SW1", OperationalQueryId.SHOW_SPANNING_TREE): output,
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions([action])

    observed = runtime.verify([expectation])[0]

    assert observed.status is ActionExecutionStatus.VERIFIED
    assert observed.fields == {
        "mode": FieldVerificationStatus.VERIFIED,
        "vlan_ids": FieldVerificationStatus.VERIFIED,
        "root_primary_vlans": FieldVerificationStatus.VERIFIED,
        "root_secondary_vlans": FieldVerificationStatus.VERIFIED,
        "priorities": FieldVerificationStatus.VERIFIED,
    }


def test_stp_numeric_priority_mismatch_fails_fresh_readback():
    plan = _compile().plan
    action = next(
        item for item in plan.actions
        if item.device_id == "sw1" and item.action_type.value == "configure_stp"
    )
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.STP_STATE
        and item.device_id == "sw1"
    )
    output = _stp_output(root_vlans={10}).replace(
        "(priority 24576 sys-id-ext 1)",
        "(priority 32768 sys-id-ext 1)",
        1,
    )
    ios = FakeControlPlaneIos({
        ("HQ-SW1", OperationalQueryId.SHOW_SPANNING_TREE): output,
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions([action])

    observed = runtime.verify([expectation])[0]

    assert observed.status is ActionExecutionStatus.FAILED
    assert observed.fields["priorities"] is FieldVerificationStatus.FAILED


def test_stale_or_unparseable_ios_output_never_promotes_direct_state():
    plan = _compile().plan
    stp = next(item for item in plan.verification_expectations
               if item.kind is ControlPlaneVerificationKind.STP_STATE
               and item.device_id == "sw1")
    channel = next(item for item in plan.verification_expectations
                   if item.kind is ControlPlaneVerificationKind.ETHERCHANNEL_STATE
                   and item.device_id == "sw1")
    ios = FakeControlPlaneIos({
        ("HQ-SW1", OperationalQueryId.SHOW_SPANNING_TREE): IosCommandResult(
            device_name="HQ-SW1",
            query_id=OperationalQueryId.SHOW_SPANNING_TREE,
            executed=True,
            output=_stp_output(root_vlans={10}),
            fresh_output_observed=False,
        ),
        ("HQ-SW1", OperationalQueryId.SHOW_ETHERCHANNEL_SUMMARY):
            "show etherchannel summary\n% Invalid input detected at '^' marker.",
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions(plan.actions)

    results = runtime.verify([stp, channel])

    assert all(item.status is ActionExecutionStatus.UNOBSERVABLE for item in results)
    assert all(not item.fresh_evidence for item in results)
    assert all(
        status is FieldVerificationStatus.UNOBSERVABLE
        for item in results for status in item.fields.values()
    )


def _interface_state(scenario, *, down: bool) -> IosCommandResult:
    status = "administratively down" if down else "up"
    protocol = "down" if down else "up"
    return IosCommandResult(
        device_name=scenario.target_device_name,
        query_id=OperationalQueryId.SHOW_IP_INTERFACE,
        executed=True,
        output=(
            f"{scenario.target_interface} is {status}, "
            f"line protocol is {protocol}\n"
            "  Internet protocol processing disabled"
        ),
        session_state=IosSessionState.EXEC_PROMPT_READY,
        fresh_output_observed=True,
        window_strategy="prefix_delta",
    )


@pytest.mark.parametrize(
    ("kind", "device_id", "query_id", "output"),
    (
        (
            ControlPlaneVerificationKind.STP_STATE,
            "sw1",
            OperationalQueryId.SHOW_SPANNING_TREE,
            _stp_output(root_vlans={10}),
        ),
        (
            ControlPlaneVerificationKind.ETHERCHANNEL_STATE,
            "sw1",
            OperationalQueryId.SHOW_ETHERCHANNEL_SUMMARY,
            _PT_9_0_1_0858_ETHERCHANNEL_SUMMARY
            .replace("Fa0/1", "Gi0/1").replace("Fa0/2", "Gi0/2"),
        ),
        (
            ControlPlaneVerificationKind.ROUTING_NEIGHBOR,
            "r1",
            OperationalQueryId.SHOW_IP_OSPF_NEIGHBOR,
            _PT_9_0_1_0858_OSPF_NEIGHBOR_R1
            .replace("2.2.2.2", "10.0.10.3")
            .replace("198.18.100.2", "10.255.0.2"),
        ),
        (
            ControlPlaneVerificationKind.ROUTE_PRESENT,
            "r1",
            OperationalQueryId.SHOW_IP_ROUTE_OSPF,
            _PT_9_0_1_0858_OSPF_ROUTE_R1
            .replace("198.18.102.0", "10.0.102.0"),
        ),
    ),
)
def test_truncated_direct_ios_output_is_fully_unobservable(
    kind, device_id, query_id, output,
):
    plan = _compile().plan
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is kind and item.device_id == device_id
    )
    action = next(item for item in plan.actions if item.id == expectation.action_id)
    ios = FakeControlPlaneIos({
        (action.device_name, query_id): IosCommandResult(
            device_name=action.device_name,
            query_id=query_id,
            executed=True,
            output=output,
            session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True,
            truncated_by_pager=True,
            window_strategy="pager_isolated",
        ),
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions(plan.actions)

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.evidence_method == "registered_ios_output_truncated"
    assert not result.fresh_evidence
    assert all(
        status is FieldVerificationStatus.UNOBSERVABLE
        for status in result.fields.values()
    )


def test_mst_state_stays_fully_unobservable_without_an_mst_fixture_parser():
    plan = _compile().plan
    actions = {item.id: item for item in plan.actions}
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.STP_STATE
        and item.device_id == "sw1"
    ).model_copy(deep=True)
    action = actions[expectation.action_id].model_copy(update={
        "mode": StpMode.MST,
        "required_capability": ControlPlaneCapabilityDimension.STP_MST_CONFIG,
        "mst_instances": {1: [10], 2: [20]},
    })
    expectation.expected["mode"] = StpMode.MST.value
    ios = FakeControlPlaneIos({
        (action.device_name, OperationalQueryId.SHOW_SPANNING_TREE):
            _stp_output(root_vlans={10}),
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions([action])

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert not result.fresh_evidence
    assert all(
        status is FieldVerificationStatus.UNOBSERVABLE
        for status in result.fields.values()
    )
    assert ios.calls == []


@pytest.mark.parametrize(
    ("protocol", "display"),
    (
        (EtherChannelProtocol.PAGP, "PAgP"),
        (EtherChannelProtocol.STATIC, "STATIC"),
    ),
)
def test_unfixture_backed_channel_protocols_are_unobservable_not_failed(
    protocol, display,
):
    plan = _compile().plan
    actions = {item.id: item for item in plan.actions}
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ETHERCHANNEL_STATE
        and item.device_id == "sw1"
    ).model_copy(deep=True)
    capability = (
        ControlPlaneCapabilityDimension.ETHERCHANNEL_PAGP_CONFIG
        if protocol is EtherChannelProtocol.PAGP
        else ControlPlaneCapabilityDimension.ETHERCHANNEL_STATIC_CONFIG
    )
    action = actions[expectation.action_id].model_copy(update={
        "protocol": protocol,
        "required_capability": capability,
    })
    expectation.expected["protocol"] = protocol.value
    ios = FakeControlPlaneIos({
        (action.device_name, OperationalQueryId.SHOW_ETHERCHANNEL_SUMMARY):
            _PT_9_0_1_0858_ETHERCHANNEL_SUMMARY.replace("LACP", display),
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions([action])

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert not result.fresh_evidence
    assert all(
        status is FieldVerificationStatus.UNOBSERVABLE
        for status in result.fields.values()
    )
    assert ios.calls == []


def test_hsrp_role_readback_is_explicitly_unobservable_without_a_query():
    plan = _compile().plan
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.HSRP_STATE
        and item.device_id == "r1"
    )
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=FakeControlPlaneIos({}),
    )
    runtime.apply_actions(plan.actions)

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.evidence_method == "hsrp_role_readback_unavailable"
    assert "role" in result.message.casefold()


def test_eigrp_process_readback_is_unobservable_without_current_output():
    plan = _compile().plan
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS
        and item.device_id == "b1"
    )
    ios = FakeControlPlaneIos({})
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions(plan.actions)

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert ios.calls == [("BR-R1", OperationalQueryId.SHOW_IP_PROTOCOLS)]


def test_fresh_eigrp_process_neighbor_and_route_rows_are_typed_evidence():
    plan = _compile().plan
    process = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS
        and item.device_id == "b1"
    )
    neighbor = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTING_NEIGHBOR
        and item.device_id == "b1"
    )
    action = next(item for item in plan.actions if item.id == process.action_id)
    route = ControlPlaneVerificationExpectation(
        id="verify-eigrp-route-b1",
        kind=ControlPlaneVerificationKind.ROUTE_PRESENT,
        action_id=action.id,
        device_id="b1",
        peer_device_id="b2",
        required_capability=ControlPlaneCapabilityDimension.ROUTING_ROUTE_STATE,
        expected={
            "network": "10.1.20.0",
            "prefix_length": 24,
            "protocol": "eigrp",
            "wildcard": "0.0.0.255",
            "segment_id": "branch-b2-lan",
        },
        depends_on=[action.id],
    )
    local_process = (
        _PT_9_0_1_0858_EIGRP_PROTOCOL_R1
        .replace(" 100 ", " 200 ")
        .replace("AS(100)", "AS(200)")
        .replace("198.18.210.1", "10.1.10.2")
    )
    peer_process = local_process.replace("10.1.10.2", "10.1.10.3")
    neighbor_output = (
        _PT_9_0_1_0858_EIGRP_NEIGHBORS_R1
        .replace("process 100", "process 200")
        .replace("198.18.212.2", "10.255.1.2")
    )
    route_output = _PT_9_0_1_0858_EIGRP_ROUTE_R1.replace(
        "198.18.211.0", "10.1.20.0",
    )
    ios = FakeControlPlaneIos({
        ("BR-R1", OperationalQueryId.SHOW_IP_PROTOCOLS): local_process,
        ("BR-R2", OperationalQueryId.SHOW_IP_PROTOCOLS): peer_process,
        ("BR-R1", OperationalQueryId.SHOW_IP_EIGRP_NEIGHBORS): neighbor_output,
        ("BR-R1", OperationalQueryId.SHOW_IP_ROUTE_EIGRP): route_output,
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
        route_convergence_attempts=1,
    )
    runtime.apply_actions(plan.actions)

    process_result, neighbor_result, route_result = runtime.verify(
        [process, neighbor, route],
    )

    assert process_result.status is ActionExecutionStatus.VERIFIED
    assert set(process_result.fields.values()) == {FieldVerificationStatus.VERIFIED}
    assert process_result.evidence_method == "fresh_show_ip_protocols_eigrp"

    assert neighbor_result.status is ActionExecutionStatus.VERIFIED
    assert set(neighbor_result.fields.values()) == {FieldVerificationStatus.VERIFIED}
    assert neighbor_result.evidence_method == "fresh_show_ip_eigrp_neighbors"

    assert route_result.status is ActionExecutionStatus.PARTIAL
    assert route_result.fields["network"] is FieldVerificationStatus.VERIFIED
    assert route_result.fields["prefix_length"] is FieldVerificationStatus.VERIFIED
    assert route_result.fields["protocol"] is FieldVerificationStatus.VERIFIED
    assert route_result.fields["wildcard"] is FieldVerificationStatus.VERIFIED
    assert route_result.fields["segment_id"] is FieldVerificationStatus.UNOBSERVABLE
    assert route_result.evidence_method == "fresh_show_ip_route_eigrp"


def test_fresh_supported_empty_eigrp_tables_fail_required_state():
    plan = _compile().plan
    neighbor = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTING_NEIGHBOR
        and item.device_id == "b1"
    )
    action = next(item for item in plan.actions if item.id == neighbor.action_id)
    route = ControlPlaneVerificationExpectation(
        id="verify-eigrp-route-absent",
        kind=ControlPlaneVerificationKind.ROUTE_PRESENT,
        action_id=action.id,
        device_id="b1",
        peer_device_id="b2",
        required_capability=ControlPlaneCapabilityDimension.ROUTING_ROUTE_STATE,
        expected={
            "network": "10.1.20.0", "prefix_length": 24,
            "protocol": "eigrp",
        },
    )
    peer_process = (
        _PT_9_0_1_0858_EIGRP_PROTOCOL_R1
        .replace(" 100 ", " 200 ")
        .replace("AS(100)", "AS(200)")
        .replace("198.18.210.1", "10.1.10.3")
    )
    ios = FakeControlPlaneIos({
        ("BR-R1", OperationalQueryId.SHOW_IP_EIGRP_NEIGHBORS):
            _PT_9_0_1_0858_EIGRP_NEIGHBORS_EMPTY.replace("process 90", "process 200"),
        ("BR-R2", OperationalQueryId.SHOW_IP_PROTOCOLS): peer_process,
        ("BR-R1", OperationalQueryId.SHOW_IP_ROUTE_EIGRP):
            _PT_9_0_1_0858_EIGRP_ROUTES_EMPTY,
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
        route_convergence_attempts=1,
    )
    runtime.apply_actions(plan.actions)

    neighbor_result, route_result = runtime.verify([neighbor, route])

    assert neighbor_result.status is ActionExecutionStatus.FAILED
    assert neighbor_result.fields["adjacent"] is FieldVerificationStatus.FAILED
    assert route_result.status is ActionExecutionStatus.FAILED
    assert route_result.convergence.last_observable_state == "route_absent"


def test_incomplete_eigrp_route_window_cannot_verify_or_fail_route_state():
    plan = _compile().plan
    process = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS
        and item.device_id == "b1"
    )
    action = next(item for item in plan.actions if item.id == process.action_id)
    route = ControlPlaneVerificationExpectation(
        id="verify-eigrp-route-incomplete",
        kind=ControlPlaneVerificationKind.ROUTE_PRESENT,
        action_id=action.id,
        device_id="b1",
        required_capability=ControlPlaneCapabilityDimension.ROUTING_ROUTE_STATE,
        expected={
            "network": "10.1.20.0", "prefix_length": 24,
            "protocol": "eigrp",
        },
    )
    incomplete = IosCommandResult(
        device_name="BR-R1",
        query_id=OperationalQueryId.SHOW_IP_ROUTE_EIGRP,
        executed=True,
        output=_PT_9_0_1_0858_EIGRP_ROUTE_R1.replace(
            "198.18.211.0", "10.1.20.0",
        ),
        session_state=IosSessionState.EXEC_PROMPT_READY,
        fresh_output_observed=True,
        output_complete=False,
        window_strategy="prefix_delta",
    )
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]),
        ios_executor=FakeControlPlaneIos({
            ("BR-R1", OperationalQueryId.SHOW_IP_ROUTE_EIGRP): incomplete,
        }),
        route_convergence_attempts=1,
    )
    runtime.apply_actions(plan.actions)

    result = runtime.verify([route])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.evidence_method == "eigrp_route_readback_incomplete"


def test_fresh_ospf_rows_must_match_the_expected_neighbor_instance():
    plan = _compile().plan
    neighbor = next(item for item in plan.verification_expectations
                    if item.kind is ControlPlaneVerificationKind.ROUTING_NEIGHBOR
                    and item.device_id == "r1")
    ios = FakeControlPlaneIos({
        ("HQ-R1", OperationalQueryId.SHOW_IP_OSPF_NEIGHBOR):
            _PT_9_0_1_0858_OSPF_NEIGHBOR_R1,
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions(plan.actions)

    result = runtime.verify([neighbor])[0]

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["peer_router_id"] is FieldVerificationStatus.FAILED
    assert result.fields["peer_ipv4"] is FieldVerificationStatus.FAILED
    assert result.fields["protocol"] is FieldVerificationStatus.VERIFIED


def test_ospf_neighbor_fields_are_typed_from_the_same_parser_row():
    plan = _compile().plan
    neighbor = next(item for item in plan.verification_expectations
                    if item.kind is ControlPlaneVerificationKind.ROUTING_NEIGHBOR
                    and item.device_id == "r1")
    output = _PT_9_0_1_0858_OSPF_NEIGHBOR_R1.replace(
        "2.2.2.2", neighbor.expected["peer_router_id"],
    )
    ios = FakeControlPlaneIos({
        ("HQ-R1", OperationalQueryId.SHOW_IP_OSPF_NEIGHBOR): output,
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions(plan.actions)

    result = runtime.verify([neighbor])[0]

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["peer_router_id"] is FieldVerificationStatus.VERIFIED
    assert result.fields["peer_ipv4"] is FieldVerificationStatus.FAILED


def test_ospf_route_requires_an_exact_network_row_not_a_nearby_prefix():
    plan = _compile().plan
    route = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
        and item.device_id == "r1"
    )
    nearby = route.expected["network"].rsplit(".", 1)[0] + ".1"
    ios = FakeControlPlaneIos({
        ("HQ-R1", OperationalQueryId.SHOW_IP_ROUTE_OSPF):
            _PT_9_0_1_0858_OSPF_ROUTE_R1.replace("198.18.102.0", nearby),
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions(plan.actions)

    result = runtime.verify([route])[0]

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["network"] is FieldVerificationStatus.FAILED
    assert result.fields["prefix_length"] is FieldVerificationStatus.UNOBSERVABLE


def test_ospf_route_verifies_explicit_prefix_and_rejects_wrong_expected_next_hop():
    plan = _compile().plan
    route = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
        and item.device_id == "r1"
    ).model_copy(deep=True)
    route.expected["next_hop"] = "10.255.0.99"
    prefix_length = route.expected["prefix_length"]
    output = _PT_9_0_1_0858_OSPF_ROUTE_R1.replace(
        "198.18.102.0",
        f"{route.expected['network']}/{prefix_length}",
    )
    ios = FakeControlPlaneIos({
        ("HQ-R1", OperationalQueryId.SHOW_IP_ROUTE_OSPF): output,
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions(plan.actions)

    result = runtime.verify([route])[0]

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["network"] is FieldVerificationStatus.VERIFIED
    assert result.fields["prefix_length"] is FieldVerificationStatus.VERIFIED
    assert result.fields["protocol"] is FieldVerificationStatus.VERIFIED
    assert result.fields["next_hop"] is FieldVerificationStatus.FAILED


def test_compiled_ospf_route_verifies_from_an_explicit_prefix_row():
    plan = _compile().plan
    route = next(
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
        and item.device_id == "r1"
    )
    output = _PT_9_0_1_0858_OSPF_ROUTE_R1.replace(
        "198.18.102.0",
        f"{route.expected['network']}/{route.expected['prefix_length']}",
    )
    ios = FakeControlPlaneIos({
        ("HQ-R1", OperationalQueryId.SHOW_IP_ROUTE_OSPF): output,
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ping_executor=SequencePing([]), ios_executor=ios,
    )
    runtime.apply_actions(plan.actions)

    result = runtime.verify([route])[0]

    # Todo lo RECLAMADO se verifica contra una fila de ruta explicita...
    for field in route.expected:
        assert result.fields[field] is FieldVerificationStatus.VERIFIED, field

    # ...y aun asi el agregado NO llega a VERIFIED, porque los campos que la
    # expectativa declara no reclamables siguen contando como no observados.
    # Ese es justamente el ascenso que estrechar `expected` habria regalado.
    assert route.unclaimed_fields == ["wildcard", "segment_id"]
    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.fields == {
        "network": FieldVerificationStatus.VERIFIED,
        "prefix_length": FieldVerificationStatus.VERIFIED,
        "protocol": FieldVerificationStatus.VERIFIED,
        "wildcard": FieldVerificationStatus.UNOBSERVABLE,
        "segment_id": FieldVerificationStatus.UNOBSERVABLE,
    }


def test_narrowing_ospf_expectations_never_raises_the_aggregate_claim():
    """Estrechar lo que se afirma no puede subir lo que se concluye.

    Se compara contra el techo historico explicitamente: antes de estrechar,
    proceso y ruta OSPF resolvian UNOBSERVABLE porque `router_id`, `wildcard` y
    `segment_id` no los establece ninguna consulta registrada. Despues de
    estrechar deben seguir resolviendo UNOBSERVABLE. Si alguna vez suben, tiene
    que ser porque se observo algo nuevo, no porque se borro un campo.
    """
    plan = _compile().plan
    ospf = [
        item for item in plan.verification_expectations
        if item.kind in {
            ControlPlaneVerificationKind.ROUTING_PROCESS,
            ControlPlaneVerificationKind.ROUTE_PRESENT,
        }
        and item.expected.get("protocol") == "ospfv2"
    ]

    assert ospf
    for expectation in ospf:
        # Lo no reclamado esta declarado, no borrado.
        assert expectation.unclaimed_fields
        assert not set(expectation.unclaimed_fields) & set(expectation.expected)
        removed = {"router_id", "wildcard", "segment_id"}
        assert not removed & set(expectation.expected)
        assert set(expectation.unclaimed_fields) <= removed


def test_route_evidence_never_stands_in_for_forwarding_evidence():
    """Una ruta en la tabla no es un paquete que llego.

    ROUTE_PRESENT y END_TO_END_REACHABILITY son dimensiones de capacidad
    distintas y se satisfacen con evidencia distinta: la primera con una lectura
    registrada, la segunda con un ping tipado. Estrechar la primera no puede
    acercar a la segunda.
    """
    plan = _compile().plan
    routes = [
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
    ]
    behavior = [
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
    ]

    assert routes and behavior
    assert {item.required_capability for item in routes}.isdisjoint(
        {item.required_capability for item in behavior}
    )
    # Ninguna expectativa de ruta afirma alcanzabilidad ni estado de fallo.
    for item in routes:
        assert "reachable" not in item.expected
        assert "loop_free" not in item.expected
        assert item.kind not in {
            ControlPlaneVerificationKind.LINK_FAILURE_CONVERGENCE,
            ControlPlaneVerificationKind.RESTORE_RECOVERY,
        }


def test_failure_scenario_observes_effect_and_does_not_infer_surviving_path():
    plan = _compile().plan
    scenario, failure, recovery = _failure_parts(plan)
    ping = SequencePing([_ping(True) for _ in range(6)])
    sent: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda script: sent.append(script) or True,
        lambda _script, _timeout: None, ping_executor=ping, stable_samples=2,
        ios_executor=SequenceControlPlaneIos([
            _interface_state(scenario, down=True),
            _interface_state(scenario, down=False),
        ]),
    )

    result = runtime.execute_failure_scenario(scenario, failure, recovery)

    assert result.before.status is ActionExecutionStatus.VERIFIED
    assert result.before.convergence.attempts == 2
    assert result.injection.applied
    assert result.during.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.during.fields["link_down"] is FieldVerificationStatus.VERIFIED
    assert result.during.fields["reachable"] is FieldVerificationStatus.VERIFIED
    assert (
        result.during.fields["surviving_link_ids"]
        is FieldVerificationStatus.UNOBSERVABLE
    )
    assert result.during.convergence.attempts == 2
    assert result.restore_attempted
    assert result.restore.applied
    assert result.after.status is ActionExecutionStatus.VERIFIED
    assert result.after.convergence.attempts == 2
    assert len(ping.calls) == 6
    assert len(sent) == 2
    assert " shutdown" in sent[0]
    assert " no shutdown" in sent[1]
    assert all("write memory" not in script for script in sent)
    assert [item.sequence for item in result.transitions] == list(range(5))
    assert [item.phase.value for item in result.transitions] == [
        "baseline_observed",
        "fault_injected",
        "failover_observed",
        "restore_dispatched",
        "recovery_observed",
    ]
    assert [item.elapsed_ms for item in result.transitions] == sorted(
        item.elapsed_ms for item in result.transitions
    )


def test_failure_scenario_never_promotes_dispatch_without_fault_effect_readback():
    plan = _compile().plan
    scenario, failure, recovery = _failure_parts(plan)
    interface_stays_up = IosCommandResult(
        device_name=scenario.target_device_name,
        query_id=OperationalQueryId.SHOW_IP_INTERFACE,
        executed=True,
        output=(
            f"{scenario.target_interface} is up, line protocol is up\n"
            "  Internet protocol processing disabled"
        ),
        session_state=IosSessionState.EXEC_PROMPT_READY,
        fresh_output_observed=True,
        window_strategy="prefix_delta",
    )
    interface_restored = interface_stays_up
    ios = SequenceControlPlaneIos([interface_stays_up, interface_restored])
    ping = SequencePing([_ping(True) for _ in range(4)])
    sent: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda script: sent.append(script) or True,
        lambda _script, _timeout: None, ping_executor=ping, ios_executor=ios,
        stable_samples=2,
    )

    result = runtime.execute_failure_scenario(scenario, failure, recovery)

    assert result.injection.applied
    assert result.during.status is ActionExecutionStatus.FAILED
    assert result.during.fields["link_down"] is FieldVerificationStatus.FAILED
    assert result.restore_attempted
    assert result.restore.applied
    assert result.after.status is ActionExecutionStatus.VERIFIED
    assert result.after.fields["link_restored"] is FieldVerificationStatus.VERIFIED
    assert len(ping.calls) == 4
    assert len(sent) == 2


def test_unstable_baseline_prevents_fault_injection():
    plan = _compile().plan
    scenario, failure, recovery = _failure_parts(plan)
    ping = SequencePing([_ping(False) for _ in range(6)])
    sent: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda script: sent.append(script) or True,
        lambda _script, _timeout: None, ping_executor=ping,
        stable_samples=2, max_probe_attempts=6,
    )

    result = runtime.execute_failure_scenario(scenario, failure, recovery)

    assert result.before.status is ActionExecutionStatus.FAILED
    assert result.injection is None
    assert not result.restore_attempted
    assert result.during is None
    assert result.after is None
    assert sent == []


def test_failure_scenario_rejects_nonboolean_reachability_before_shutdown():
    plan = _compile().plan
    scenario, failure, recovery = _failure_parts(plan)
    failure = failure.model_copy(deep=True)
    failure.expected["reachable"] = "false"
    sent: list[str] = []
    ping = SequencePing([])
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda script: sent.append(script) or True,
        lambda _script, _timeout: None, ping_executor=ping,
    )

    with pytest.raises(ValueError, match="reachable"):
        runtime.execute_failure_scenario(scenario, failure, recovery)

    assert sent == []
    assert ping.calls == []


def test_failure_restore_runs_in_finally_when_shutdown_send_raises():
    plan = _compile().plan
    scenario, failure, recovery = _failure_parts(plan)
    ping = SequencePing([_ping(True), _ping(True), _ping(True), _ping(True)])
    sent: list[str] = []

    def send(script: str) -> bool:
        sent.append(script)
        if len(sent) == 1:
            raise TimeoutError("bridge timeout after dispatch")
        return True

    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], send, lambda _script, _timeout: None,
        ping_executor=ping, stable_samples=2,
        ios_executor=SequenceControlPlaneIos([
            _interface_state(scenario, down=False),
        ]),
    )

    result = runtime.execute_failure_scenario(scenario, failure, recovery)

    assert not result.injection.applied
    assert result.restore_attempted
    assert result.restore.applied
    assert result.after.status is ActionExecutionStatus.VERIFIED
    assert len(sent) == 2
    assert " shutdown" in sent[0]
    assert " no shutdown" in sent[1]


def test_failure_restore_runs_after_unobservable_convergence_timeout():
    plan = _compile().plan
    scenario, failure, recovery = _failure_parts(plan)
    timeout_samples = [_ping(False, fresh=False) for _ in range(6)]
    ping = SequencePing([
        _ping(True), _ping(True), *timeout_samples, _ping(True), _ping(True),
    ])
    sent: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda script: sent.append(script) or True,
        lambda _script, _timeout: None, ping_executor=ping,
        stable_samples=2, max_probe_attempts=6,
        ios_executor=SequenceControlPlaneIos([
            _interface_state(scenario, down=True),
            _interface_state(scenario, down=False),
        ]),
    )

    result = runtime.execute_failure_scenario(scenario, failure, recovery)

    assert result.during.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.restore_attempted
    assert result.restore.applied
    assert result.after.status is ActionExecutionStatus.VERIFIED
    assert len(sent) == 2


def test_recovery_is_not_claimed_when_restore_is_rejected():
    plan = _compile().plan
    scenario, failure, recovery = _failure_parts(plan)
    ping = SequencePing([_ping(True) for _ in range(4)])
    sent: list[str] = []

    def send(script: str) -> bool:
        sent.append(script)
        return len(sent) == 1

    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], send, lambda _script, _timeout: None,
        ping_executor=ping, stable_samples=2,
        ios_executor=SequenceControlPlaneIos([
            _interface_state(scenario, down=True),
        ]),
    )

    result = runtime.execute_failure_scenario(scenario, failure, recovery)

    assert result.restore_attempted
    assert not result.restore.applied
    assert result.after is None
    assert len(ping.calls) == 4


@pytest.mark.parametrize("stable_samples", [1, 2.5, True])
def test_failure_scenario_rejects_invalid_stable_samples(stable_samples):
    with pytest.raises(ValueError, match="stable_samples"):
        PacketTracerEnterpriseControlPlaneRuntime(
            lambda: [], lambda _script: True, lambda _script, _timeout: None,
            stable_samples=stable_samples,
        )


@pytest.mark.parametrize("max_probe_attempts", [1.5, True])
def test_failure_scenario_rejects_noninteger_probe_attempts(max_probe_attempts):
    with pytest.raises(ValueError, match="max_probe_attempts"):
        PacketTracerEnterpriseControlPlaneRuntime(
            lambda: [], lambda _script: True, lambda _script, _timeout: None,
            max_probe_attempts=max_probe_attempts,
        )
