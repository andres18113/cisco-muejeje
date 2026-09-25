"""Versioned native-pool policy qualification from compiled DHCP intent."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from packet_tracer_mcp.adapters.cli.service_qualification import (
    _request,
    dhcp_product_contract,
)
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    qualify_server_services,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    MeasurementConclusion,
    QualificationOutcome,
    stage_definition,
    step_selection_refusals,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)
from tests.service_qualification_engine import (
    NodeEngine,
    NodeEngineTransport,
    authorization_args,
    request_args,
    require_node,
    simulated_boundaries,
)


def test_policy_profile_requires_size_before_gateway_dns_and_exclusions() -> None:
    """Policy effects cannot run as a stand-alone diagnostic selection."""
    definition = stage_definition("Q3-NATIVE-POLICY")
    assert definition is not None
    assert (definition.profile_id, definition.profile_version) == (
        "Q3-NATIVE-POLICY",
        "1",
    )
    assert definition.allowed_channels == ("file",)
    assert definition.step_ids == ("NATIVE-size", "NATIVE-policy")
    assert definition.experiments_of_steps(definition.step_ids) == (
        "M-NATIVE-REPEAT-START",
        "M-NATIVE-MAX",
        "M-NATIVE-FINAL",
        "M-NATIVE-GATEWAY",
        "M-NATIVE-DNS",
        "M-NATIVE-EXCLUSIONS",
    )
    assert definition.budget.max_operations == 160
    assert definition.budget.max_seconds == 900
    assert definition.budget.reserve_seconds == 300
    assert definition.planned_minimum_operations <= 160
    assert step_selection_refusals(definition, definition.step_ids) == []
    assert step_selection_refusals(definition, ["NATIVE-policy"])


def test_stability_profile_requires_exact_policy_before_e5_reapplication() -> None:
    """The reapplication effect belongs after all policy measurements."""
    definition = stage_definition("Q3-NATIVE-STABILITY")
    assert definition is not None
    assert definition.step_ids == (
        "NATIVE-size",
        "NATIVE-policy",
        "NATIVE-stability",
    )
    assert (definition.profile_id, definition.profile_version) == (
        "Q3-NATIVE-STABILITY",
        "1",
    )
    assert definition.budget.max_operations == 180
    assert definition.budget.max_seconds == 1050
    assert definition.budget.reserve_seconds == 300
    assert step_selection_refusals(definition, definition.step_ids) == []
    assert step_selection_refusals(definition, ["NATIVE-stability"])


def test_stability_reapplies_product_e5_and_retains_exact_policy(tmp_path) -> None:
    """The complete native inventory is read through the real coordinator."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    class RetainingReapplicationTransport(NodeEngineTransport):
        exclusions = 0

        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if 'step:"dhcp_native_exclusion_probe"' in js_code:
                self.exclusions += 1
                if self.exclusions == 2:
                    self.engine.configure(default_pool_realigns_on_address=False)
            return outcome

    try:
        transport = RetainingReapplicationTransport(engine)
        definition = stage_definition("Q3-NATIVE-STABILITY")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-STABILITY")
                + authorization_args("Q3-NATIVE-STABILITY")
            ),
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.COMPLETED, (
            result.record.primary_failure if result.record else result.refusals
        )
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measured["M-NATIVE-STABILITY"].conclusion
            is MeasurementConclusion.SUPPORTED_IN_SAMPLE
        )
        before = measured["M-NATIVE-STABILITY"].facts["before"]
        after = measured["M-NATIVE-STABILITY"].facts["after"]
        assert before == after
        assert after["pools"][0]["start"] == "192.0.2.100"
        assert after["pools"][0]["gateway"] == "192.0.2.1"
        assert after["pools"][0]["dns"] == "192.0.2.10"
        assert after["excluded_count"] == 2
        assert (
            measured["M-NATIVE-STABILITY"].facts["product_action_results"][0]["status"]
            == "applied"
        )
        assert measured["M-NATIVE-STABILITY"].facts["unknown_dispatch_seqs"] == []
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_stability_detects_e5_reapplication_regenerating_native_range(tmp_path) -> None:
    """A real repeated E5 setter can reset start/end despite a correct pre-read."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )
    try:
        definition = stage_definition("Q3-NATIVE-STABILITY")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-STABILITY")
                + authorization_args("Q3-NATIVE-STABILITY")
            ),
            simulated_boundaries(tmp_path, NodeEngineTransport(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measured["M-NATIVE-STABILITY"].conclusion
            is MeasurementConclusion.CONTRADICTED
        )
        before = measured["M-NATIVE-STABILITY"].facts["before"]
        after = measured["M-NATIVE-STABILITY"].facts["after"]
        assert before["pools"][0]["start"] == "192.0.2.100"
        assert after["pools"][0]["start"] == "192.0.2.0"
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_stability_does_not_support_lost_post_read_and_keeps_terminal(tmp_path) -> None:
    """A lost policy read cannot establish preservation after product E5."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    class LostPostReadTransport(NodeEngineTransport):
        static_sends = 0
        lose_policy = False

        def send(self, js_code):
            if "configurePcIp(" in js_code:
                self.static_sends += 1
                if self.static_sends == 2:
                    self.lose_policy = True
            return super().send(js_code)

        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if self.lose_policy and 'step:"dhcp_server_policy"' in js_code:
                self.lose_policy = False
                return BridgeDispatchOutcome(
                    dispatch=DispatchFact.ACCEPTANCE_UNKNOWN,
                    result=ResultFact.NOT_OBSERVED,
                    detail="post_reapplication_policy_read_lost",
                )
            return outcome

    try:
        transport = LostPostReadTransport(engine)
        definition = stage_definition("Q3-NATIVE-STABILITY")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-STABILITY")
                + authorization_args("Q3-NATIVE-STABILITY")
            ),
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        stability = measured["M-NATIVE-STABILITY"]
        assert stability.conclusion is MeasurementConclusion.INCONCLUSIVE, (
            stability.causes,
            stability.facts["product_action_results"],
        )
        assert stability.outcome_unknown is False
        assert stability.causes[0].startswith("native_policy_after_unobserved:")
        assert measured["M-NATIVE-FINAL"].status.value == "ran"
        assert transport.static_sends == 2
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_stability_marks_queued_e5_with_lost_ack_unknown(tmp_path) -> None:
    """The counted E5 dispatch fact overrides a misleading failed batch row."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    class LostE5AckTransport(NodeEngineTransport):
        static_sends = 0

        def send(self, js_code):
            if "configurePcIp(" in js_code:
                self.static_sends += 1
                if self.static_sends == 2:
                    super().send(js_code)
                    return False
            return super().send(js_code)

    try:
        transport = LostE5AckTransport(engine)
        definition = stage_definition("Q3-NATIVE-STABILITY")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-STABILITY")
                + authorization_args("Q3-NATIVE-STABILITY")
            ),
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        stability = measured["M-NATIVE-STABILITY"]
        assert stability.conclusion is MeasurementConclusion.INCONCLUSIVE
        assert stability.outcome_unknown is True
        assert stability.causes == ["outcome_unknown:q3_native_stability_e5_dispatch"]
        assert len(stability.facts["unknown_dispatch_seqs"]) == 1
        assert measured["M-NATIVE-FINAL"].status.value == "ran"
        assert transport.static_sends == 2
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_stability_refuses_extra_pool_coupled_to_second_e5(tmp_path) -> None:
    """A readable overlapping physical pool breaks the singleton contract."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    class ExtraPoolTransport(NodeEngineTransport):
        static_sends = 0

        def send(self, js_code):
            if "configurePcIp(" in js_code:
                self.static_sends += 1
                if self.static_sends == 2:
                    accepted = super().send(js_code)
                    self.engine.queue(
                        'var d=ipc.network().getDevice("__MCP_E6Q_SRV");'
                        'd.getProcess("DhcpServerMain")'
                        '.getDhcpServerProcessByPortName("FastEthernet0")'
                        '.addPool("overlappingPool");'
                    )
                    return accepted
            return super().send(js_code)

    try:
        transport = ExtraPoolTransport(engine)
        definition = stage_definition("Q3-NATIVE-STABILITY")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-STABILITY")
                + authorization_args("Q3-NATIVE-STABILITY")
            ),
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        stability = measured["M-NATIVE-STABILITY"]
        assert stability.conclusion is MeasurementConclusion.CONTRADICTED
        assert stability.facts["after"]["pool_count"] == 2
        assert measured["M-NATIVE-FINAL"].status.value == "ran"
        assert transport.static_sends == 2
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_stability_refuses_second_e5_transport_exception(tmp_path) -> None:
    """An exception at dispatch leaves E5 acceptance unknown and stops."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    class ThrowingE5Transport(NodeEngineTransport):
        static_sends = 0

        def send(self, js_code):
            if "configurePcIp(" in js_code:
                self.static_sends += 1
                if self.static_sends == 2:
                    raise TimeoutError("second_e5_dispatch_failed")
            return super().send(js_code)

    try:
        transport = ThrowingE5Transport(engine)
        definition = stage_definition("Q3-NATIVE-STABILITY")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-STABILITY")
                + authorization_args("Q3-NATIVE-STABILITY")
            ),
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        stability = measured["M-NATIVE-STABILITY"]
        assert stability.conclusion is MeasurementConclusion.INCONCLUSIVE
        assert stability.outcome_unknown is True
        assert stability.facts["before"] == stability.facts["after"]
        assert measured["M-NATIVE-FINAL"].status.value == "ran"
        assert transport.static_sends == 2
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_stability_classifies_incomplete_exclusion_count_as_unknown(tmp_path) -> None:
    """A mismatched count/list is unreadable, not a proved physical change."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    class CountMismatchTransport(NodeEngineTransport):
        static_sends = 0
        tampered = False

        def send(self, js_code):
            if "configurePcIp(" in js_code:
                self.static_sends += 1
            return super().send(js_code)

        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if (
                self.static_sends == 2
                and not self.tampered
                and 'step:"dhcp_server_policy"' in js_code
                and outcome.result is ResultFact.CORRELATED
            ):
                self.tampered = True
                body = json.loads(outcome.body)
                body["excluded_count"] = 3
                return replace(outcome, body=json.dumps(body))
            return outcome

    try:
        definition = stage_definition("Q3-NATIVE-STABILITY")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-STABILITY")
                + authorization_args("Q3-NATIVE-STABILITY")
            ),
            simulated_boundaries(tmp_path, CountMismatchTransport(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        stability = measured["M-NATIVE-STABILITY"]
        assert stability.conclusion is MeasurementConclusion.INCONCLUSIVE
        assert stability.causes == ["native_policy_after_exclusions_incomplete"]
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_policy_stage_applies_each_compiled_field_through_governed_runtime(
    tmp_path,
) -> None:
    """Gateway, DNS and both exclusions are measured after the exact size."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )
    try:
        transport = NodeEngineTransport(engine)
        request = _request(
            request_args("Q3-NATIVE-POLICY") + authorization_args("Q3-NATIVE-POLICY")
        )
        definition = stage_definition("Q3-NATIVE-POLICY")
        result = qualify_server_services(
            request,
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.COMPLETED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        for name in (
            "M-NATIVE-REPEAT-START",
            "M-NATIVE-MAX",
            "M-NATIVE-GATEWAY",
            "M-NATIVE-DNS",
            "M-NATIVE-EXCLUSIONS",
        ):
            assert (
                measured[name].conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
            )
        final = measured["M-NATIVE-EXCLUSIONS"].facts["after"]
        assert final["gateway"] == "192.0.2.1"
        assert final["dns"] == "192.0.2.10"
        assert (final["start"], final["end"], final["max"]) == (
            "192.0.2.100",
            "192.0.2.100",
            1,
        )
        assert measured["M-NATIVE-EXCLUSIONS"].facts["after_exclusions"] == [
            {"start": "192.0.2.1", "end": "192.0.2.1"},
            {"start": "192.0.2.10", "end": "192.0.2.10"},
        ]
        calls = engine.snapshot()["dhcp_setter_calls"]
        assert calls["setStartIp"] == 1
        assert calls["setMaxUsers"] == 1
        assert calls["setDefaultRouter"] == 1
        assert calls["setDnsServerIp"] == 1
        assert calls["addExcludedAddress"] == 2
        assert calls["setEnable"] == 0
        assert calls["configurePcIpDhcp"] == 0
        assert engine.snapshot()["dhcp_runs"] == []
        assert result.record.restoration_proven
    finally:
        engine.close()


@pytest.mark.parametrize(
    ("config", "failed_measurement", "conclusion", "dns_calls", "exclusion_calls"),
    [
        (
            {"dhcp_native_gateway_behavior": "noop"},
            "M-NATIVE-GATEWAY",
            MeasurementConclusion.NEGATIVE_OBSERVED,
            0,
            0,
        ),
        (
            {"dhcp_native_gateway_behavior": "throw"},
            "M-NATIVE-GATEWAY",
            MeasurementConclusion.INCONCLUSIVE,
            0,
            0,
        ),
        (
            {"dhcp_native_dns_behavior": "noop"},
            "M-NATIVE-DNS",
            MeasurementConclusion.NEGATIVE_OBSERVED,
            1,
            0,
        ),
        (
            {"dhcp_native_dns_behavior": "throw"},
            "M-NATIVE-DNS",
            MeasurementConclusion.INCONCLUSIVE,
            1,
            0,
        ),
        (
            {"dhcp_native_exclusion_behavior": "noop_first"},
            "M-NATIVE-EXCLUSIONS",
            MeasurementConclusion.NEGATIVE_OBSERVED,
            1,
            1,
        ),
        (
            {"dhcp_native_exclusion_behavior": "throw_second"},
            "M-NATIVE-EXCLUSIONS",
            MeasurementConclusion.INCONCLUSIVE,
            1,
            2,
        ),
        (
            {"dhcp_native_exclusion_behavior": "extra_first"},
            "M-NATIVE-EXCLUSIONS",
            MeasurementConclusion.CONTRADICTED,
            1,
            1,
        ),
    ],
)
def test_policy_stops_at_the_first_noop_throw_or_extra_effect(
    tmp_path, config, failed_measurement, conclusion, dns_calls, exclusion_calls
) -> None:
    """No later policy setter may run from an unsupported predecessor."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        **{
            "dhcp_default_pool": "native",
            "default_pool_realigns_on_address": True,
            "dhcp_native_start_behavior": "coupled",
            "dhcp_native_max_behavior": "resize",
            **config,
        },
    )
    try:
        transport = NodeEngineTransport(engine)
        request = _request(
            request_args("Q3-NATIVE-POLICY") + authorization_args("Q3-NATIVE-POLICY")
        )
        definition = stage_definition("Q3-NATIVE-POLICY")
        result = qualify_server_services(
            request,
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert measured[failed_measurement].conclusion is conclusion
        calls = engine.snapshot()["dhcp_setter_calls"]
        assert calls["setDefaultRouter"] == 1
        assert calls["setDnsServerIp"] == dns_calls
        assert calls["addExcludedAddress"] == exclusion_calls
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_lost_gateway_result_blocks_dns_and_exclusions_without_replay(tmp_path) -> None:
    """An executed setter with no correlated reply authorizes no dependent call."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    class LostGatewayTransport(NodeEngineTransport):
        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if 'step:"dhcp_native_gateway_probe"' in js_code:
                return BridgeDispatchOutcome(
                    dispatch=DispatchFact.ACCEPTANCE_UNKNOWN,
                    result=ResultFact.NOT_OBSERVED,
                    detail="gateway_reply_lost_after_execution",
                )
            return outcome

    try:
        transport = LostGatewayTransport(engine)
        request = _request(
            request_args("Q3-NATIVE-POLICY") + authorization_args("Q3-NATIVE-POLICY")
        )
        definition = stage_definition("Q3-NATIVE-POLICY")
        result = qualify_server_services(
            request,
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measured["M-NATIVE-GATEWAY"].conclusion
            is MeasurementConclusion.INCONCLUSIVE
        )
        assert measured["M-NATIVE-GATEWAY"].outcome_unknown is True
        calls = engine.snapshot()["dhcp_setter_calls"]
        assert calls["setDefaultRouter"] == 1
        assert calls["setDnsServerIp"] == 0
        assert calls["addExcludedAddress"] == 0
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_lost_first_exclusion_reply_blocks_second_without_replay(tmp_path) -> None:
    """A first exclusion may execute despite a lost reply; the second waits."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    class LostFirstExclusionTransport(NodeEngineTransport):
        lost = False

        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if 'step:"dhcp_native_exclusion_probe"' in js_code and not self.lost:
                self.lost = True
                return BridgeDispatchOutcome(
                    dispatch=DispatchFact.ACCEPTANCE_UNKNOWN,
                    result=ResultFact.NOT_OBSERVED,
                    detail="first_exclusion_reply_lost_after_execution",
                )
            return outcome

    try:
        transport = LostFirstExclusionTransport(engine)
        definition = stage_definition("Q3-NATIVE-POLICY")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-POLICY")
                + authorization_args("Q3-NATIVE-POLICY")
            ),
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        exclusion = measured["M-NATIVE-EXCLUSIONS"]
        assert exclusion.conclusion is MeasurementConclusion.INCONCLUSIVE
        assert exclusion.outcome_unknown is True
        assert engine.snapshot()["dhcp_setter_calls"]["addExcludedAddress"] == 1
        assert (
            sum(
                'step:"dhcp_native_exclusion_probe"' in script
                for _kind, script in transport.calls
            )
            == 1
        )
        assert measured["M-NATIVE-FINAL"].facts["excluded_count"] == 1
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_final_policy_read_refuses_mismatched_exclusion_count(tmp_path) -> None:
    """A correlated but incomplete final list cannot be marked supported."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    class IncompleteFinalTransport(NodeEngineTransport):
        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if (
                'step:"dhcp_server_policy"' in js_code
                and self.engine.snapshot()["dhcp_setter_calls"]["addExcludedAddress"]
                == 2
                and outcome.result is ResultFact.CORRELATED
            ):
                body = json.loads(outcome.body)
                body["excluded_count"] = 3
                return replace(outcome, body=json.dumps(body))
            return outcome

    try:
        definition = stage_definition("Q3-NATIVE-POLICY")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-POLICY")
                + authorization_args("Q3-NATIVE-POLICY")
            ),
            simulated_boundaries(tmp_path, IncompleteFinalTransport(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measured["M-NATIVE-FINAL"].conclusion is MeasurementConclusion.INCONCLUSIVE
        )
        assert measured["M-NATIVE-FINAL"].facts["complete"] is False
        assert result.record.restoration_proven
    finally:
        engine.close()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host_device_id", "endpoint/q3/default/user_pc/001"),
        ("host_device_name", "__MCP_E6Q_PC1"),
        ("interface", "FastEthernet1"),
        ("segment_id", "wrong-segment"),
    ],
)
def test_policy_refuses_compiled_pool_wrong_subject_before_e5(
    tmp_path, field, value
) -> None:
    """A plausible pool name alone cannot authorize the server setter path."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    def wrong_contract(build, run_id, capacity):
        contract = dhcp_product_contract(build, run_id, capacity)
        actions = [
            item.model_copy(update={field: value})
            if isinstance(item, ConfigureServerDhcpPool)
            else item
            for item in contract.service_plan.actions
        ]
        return replace(
            contract,
            service_plan=contract.service_plan.model_copy(update={"actions": actions}),
        )

    try:
        definition = stage_definition("Q3-NATIVE-POLICY")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-POLICY")
                + authorization_args("Q3-NATIVE-POLICY")
            ),
            simulated_boundaries(
                tmp_path,
                NodeEngineTransport(engine),
                dhcp_product_contract=wrong_contract,
            ),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        assert result.record.primary_failure == "q3_native_requested_pool_ambiguous"
        calls = engine.snapshot()["dhcp_setter_calls"]
        assert calls["setStartIp"] == calls["setMaxUsers"] == 0
        assert calls["setDefaultRouter"] == calls["addExcludedAddress"] == 0
        assert result.record.restoration_proven
    finally:
        engine.close()


@pytest.mark.parametrize(
    ("config", "failure", "start_calls", "max_calls"),
    [
        (
            {"dhcp_initial_exclusions": [{"start": "192.0.2.77", "end": "192.0.2.77"}]},
            "q3_native_baseline_not_admitted",
            0,
            0,
        ),
        (
            {"dhcp_native_start_behavior": "coupled_with_exclusion"},
            "contradiction:M-NATIVE-REPEAT-START",
            1,
            0,
        ),
    ],
)
def test_policy_reads_exclusions_before_e5_and_around_repeated_setters(
    tmp_path, config, failure, start_calls, max_calls
) -> None:
    """Hidden exclusion drift cannot authorize the next physical setter."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        **{
            "dhcp_default_pool": "native",
            "default_pool_realigns_on_address": True,
            "dhcp_native_start_behavior": "coupled",
            "dhcp_native_max_behavior": "resize",
            **config,
        },
    )
    try:
        transport = NodeEngineTransport(engine)
        request = _request(
            request_args("Q3-NATIVE-POLICY") + authorization_args("Q3-NATIVE-POLICY")
        )
        definition = stage_definition("Q3-NATIVE-POLICY")
        result = qualify_server_services(
            request,
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        assert result.record.primary_failure == failure
        calls = engine.snapshot()["dhcp_setter_calls"]
        assert calls["setStartIp"] == start_calls
        assert calls["setMaxUsers"] == max_calls
        assert calls["setDefaultRouter"] == 0
        assert result.record.restoration_proven
    finally:
        engine.close()
