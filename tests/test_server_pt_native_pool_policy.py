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
