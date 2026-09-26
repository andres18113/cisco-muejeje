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


class _RetainingReapplicationTransport(NodeEngineTransport):
    """Keep the first E5 realignment, then model an unchanged repeat."""

    exclusions = 0

    def dispatch_and_wait(self, js_code, timeout):
        outcome = super().dispatch_and_wait(js_code, timeout)
        if 'step:"dhcp_native_exclusion_probe"' in js_code:
            self.exclusions += 1
            if self.exclusions == 2:
                self.engine.configure(default_pool_realigns_on_address=False)
        return outcome


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


def test_serve_profile_requires_stability_and_binds_one_client() -> None:
    """Only the full measured chain authorizes client activation."""
    definition = stage_definition("Q3-NATIVE-SERVE")
    assert definition is not None
    assert definition.step_ids == (
        "NATIVE-size",
        "NATIVE-policy",
        "NATIVE-stability",
        "NATIVE-serve",
    )
    assert (definition.profile_id, definition.profile_version) == (
        "Q3-NATIVE-SERVE",
        "1",
    )
    assert definition.budget.max_operations == 260
    assert definition.budget.max_seconds == 1800
    assert definition.budget.reserve_seconds == 300
    assert definition.experiment("M-NATIVE-MODE").planned_operations == 9
    assert definition.experiment("M-NATIVE-SERVE").planned_operations == 39
    assert definition.planned_minimum_operations <= 260
    assert step_selection_refusals(definition, definition.step_ids) == []
    assert step_selection_refusals(definition, ["NATIVE-serve"])


@pytest.mark.parametrize("table_end", ["null", "throw"])
def test_native_serve_attributes_autonomous_client_to_physical_pool(
    tmp_path, table_end
) -> None:
    """One client gets two matching mode/address/native-row observations."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
        dhcp_pool_selection="default",
        dhcp_table_end=table_end,
    )

    try:
        transport = _RetainingReapplicationTransport(engine)
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.COMPLETED, (
            result.record.primary_failure if result.record else result.refusals
        )
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        for name in ("M-NATIVE-ENABLE", "M-NATIVE-MODE", "M-NATIVE-SERVE"):
            assert (
                measured[name].conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
            )
        assert (
            measured["M-NATIVE-FINAL"].conclusion
            is MeasurementConclusion.SUPPORTED_IN_SAMPLE
        )
        assert measured["M-NATIVE-FINAL"].facts["complete"] is True
        samples = measured["M-NATIVE-SERVE"].facts["samples"]
        assert samples[-1]["ready"] is True
        assert measured["M-NATIVE-SERVE"].facts["consecutive_matches"] == 2
        calls = engine.snapshot()["dhcp_setter_calls"]
        assert calls["setEnable"] == 1
        assert calls["configurePcIpDhcp"] == 1
        assert engine.snapshot()["dhcp_runs"] == []
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_stops_when_enable_changes_pool_policy(tmp_path) -> None:
    """A successful enable flag cannot authorize the client after range drift."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        default_pool_change_on_enable={"start": "192.0.2.2"},
        dhcp_mode_acquires=True,
    )
    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, _RetainingReapplicationTransport(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measured["M-NATIVE-ENABLE"].conclusion is MeasurementConclusion.CONTRADICTED
        )
        assert measured["M-NATIVE-MODE"].status.value == "not_run"
        assert engine.snapshot()["dhcp_setter_calls"]["configurePcIpDhcp"] == 0
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_retains_unknown_enable_and_withholds_client_mode(
    tmp_path,
) -> None:
    """A setter that ran without its correlated reply cannot admit E5 mode."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
    )

    class LostEnable(_RetainingReapplicationTransport):
        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if 'step:"dhcp_native_enable_probe"' in js_code:
                return BridgeDispatchOutcome(
                    dispatch=DispatchFact.ACCEPTANCE_UNKNOWN,
                    result=ResultFact.NOT_OBSERVED,
                    detail="enable_reply_lost_after_execution",
                )
            return outcome

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, LostEnable(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measured["M-NATIVE-ENABLE"].conclusion is MeasurementConclusion.INCONCLUSIVE
        )
        assert measured["M-NATIVE-ENABLE"].outcome_unknown is True
        assert engine.snapshot()["dhcp_setter_calls"]["setEnable"] == 1
        assert engine.snapshot()["dhcp_setter_calls"]["configurePcIpDhcp"] == 0
        assert measured["M-NATIVE-FINAL"].status.value == "ran"
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_guard_refuses_policy_drift_before_enable(tmp_path) -> None:
    """A stale positive snapshot cannot enable a newly changed pool."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    class DriftBeforeEnable(_RetainingReapplicationTransport):
        drifted = False

        def dispatch_and_wait(self, js_code, timeout):
            if 'step:"dhcp_native_enable_probe"' in js_code and not self.drifted:
                self.drifted = True
                self.engine.evaluate(
                    'ipc.network().getDevice("__MCP_E6Q_SRV")'
                    '.getProcess("DhcpServerMain")'
                    '.getDhcpServerProcessByPortName("FastEthernet0")'
                    '.getPool("serverPool").setDefaultRouter("192.0.2.99");'
                )
            return super().dispatch_and_wait(js_code, timeout)

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, DriftBeforeEnable(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measured["M-NATIVE-ENABLE"].conclusion is MeasurementConclusion.CONTRADICTED
        )
        assert measured["M-NATIVE-ENABLE"].facts["probe"]["attempted"] is False
        assert engine.snapshot()["dhcp_setter_calls"]["setEnable"] == 0
        assert engine.snapshot()["dhcp_setter_calls"]["configurePcIpDhcp"] == 0
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_enable_guard_refuses_active_second_client(tmp_path) -> None:
    """PC2 becoming DHCP-on at dispatch cannot consume the one-user pool."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
    )

    class Pc2OnAtEnable(_RetainingReapplicationTransport):
        activated = False

        def dispatch_and_wait(self, js_code, timeout):
            if 'step:"dhcp_native_enable_probe"' in js_code and not self.activated:
                self.activated = True
                self.engine.evaluate(
                    'configurePcIp("__MCP_E6Q_PC2",true,null,null,null,null,'
                    '"FastEthernet0");'
                )
            return super().dispatch_and_wait(js_code, timeout)

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, Pc2OnAtEnable(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        enable = measured["M-NATIVE-ENABLE"]
        assert enable.conclusion is MeasurementConclusion.CONTRADICTED
        assert enable.facts["prior_clients"]["__MCP_E6Q_PC2"]["mode"] is False
        assert enable.facts["probe"]["clients_clear"] is False
        assert enable.facts["probe"]["attempted"] is False
        assert engine.snapshot()["dhcp_setter_calls"]["setEnable"] == 0
        assert measured["M-NATIVE-MODE"].status.value == "not_run"
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_enable_guard_refuses_zero_ip_with_residual_mask(tmp_path) -> None:
    """An off client with 0.0.0.0 and a nonzero mask is not unassigned."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )

    class ResidualMaskAtEnable(_RetainingReapplicationTransport):
        altered = False

        def dispatch_and_wait(self, js_code, timeout):
            if 'step:"dhcp_native_enable_probe"' in js_code and not self.altered:
                self.altered = True
                self.engine.evaluate(
                    'ipc.network().getDevice("__MCP_E6Q_PC2")'
                    '.getPort("FastEthernet0")'
                    '.setIpSubnetMask("0.0.0.0","255.255.255.0");'
                )
            return super().dispatch_and_wait(js_code, timeout)

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, ResidualMaskAtEnable(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        enable = measured["M-NATIVE-ENABLE"]
        assert enable.facts["prior_clients"]["__MCP_E6Q_PC2"]["netmask"] == ""
        assert enable.facts["probe"]["clients_clear"] is False
        assert enable.facts["probe"]["attempted"] is False
        assert engine.snapshot()["dhcp_setter_calls"]["setEnable"] == 0
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_lost_client_mode_ack_withholds_serving_reads(tmp_path) -> None:
    """An executed mode probe with lost reply cannot authorize attribution."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
    )

    class LostMode(_RetainingReapplicationTransport):
        mode_calls = 0

        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if 'step:"dhcp_native_client_mode_probe"' in js_code:
                self.mode_calls += 1
                return BridgeDispatchOutcome(
                    dispatch=DispatchFact.ACCEPTANCE_UNKNOWN,
                    result=ResultFact.NOT_OBSERVED,
                    detail="client_mode_reply_lost_after_execution",
                )
            return outcome

    try:
        transport = LostMode(engine)
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measured["M-NATIVE-MODE"].conclusion is MeasurementConclusion.INCONCLUSIVE
        )
        assert measured["M-NATIVE-MODE"].outcome_unknown is True
        assert measured["M-NATIVE-SERVE"].status.value == "not_run"
        assert transport.mode_calls == 1
        assert engine.snapshot()["dhcp_setter_calls"]["configurePcIpDhcp"] == 1
        assert engine.snapshot()["dhcp_runs"] == []
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_mode_guard_refuses_policy_drift_at_dispatch(tmp_path) -> None:
    """A changed server policy in the effect evaluation withholds DHCP mode."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
    )

    class DriftAtMode(_RetainingReapplicationTransport):
        drifted = False

        def dispatch_and_wait(self, js_code, timeout):
            if 'step:"dhcp_native_client_mode_probe"' in js_code and not self.drifted:
                self.drifted = True
                self.engine.evaluate(
                    'ipc.network().getDevice("__MCP_E6Q_SRV")'
                    '.getProcess("DhcpServerMain")'
                    '.getDhcpServerProcessByPortName("FastEthernet0")'
                    '.getPool("serverPool").setDefaultRouter("192.0.2.99");'
                )
            return super().dispatch_and_wait(js_code, timeout)

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, DriftAtMode(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        mode = measured["M-NATIVE-MODE"]
        assert mode.conclusion is MeasurementConclusion.CONTRADICTED
        assert mode.facts["probe"]["policy_match"] is False
        assert mode.facts["probe"]["attempted"] is False
        assert engine.snapshot()["dhcp_setter_calls"]["configurePcIpDhcp"] == 0
        assert engine.snapshot()["dhcp_runs"] == []
        assert measured["M-NATIVE-SERVE"].status.value == "not_run"
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_mode_guard_refuses_pc2_activation_at_dispatch(tmp_path) -> None:
    """The selected PC1 cannot be activated after PC2 starts competing."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
    )

    class Pc2OnAtMode(_RetainingReapplicationTransport):
        activated = False

        def dispatch_and_wait(self, js_code, timeout):
            if 'step:"dhcp_native_client_mode_probe"' in js_code and not self.activated:
                self.activated = True
                self.engine.evaluate(
                    'configurePcIp("__MCP_E6Q_PC2",true,null,null,null,null,'
                    '"FastEthernet0");'
                )
            return super().dispatch_and_wait(js_code, timeout)

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, Pc2OnAtMode(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        mode = measured["M-NATIVE-MODE"]
        assert mode.conclusion is MeasurementConclusion.CONTRADICTED
        assert mode.facts["probe"]["inactive_clients_clear"] is False
        assert mode.facts["probe"]["attempted"] is False
        assert mode.facts["before_inactive_client"]["mode"] is False
        assert mode.facts["after_inactive_client"]["mode"] is True
        assert engine.snapshot()["dhcp_setter_calls"]["configurePcIpDhcp"] == 1
        assert measured["M-NATIVE-SERVE"].status.value == "not_run"
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_refuses_named_competing_pool_after_client_mode(tmp_path) -> None:
    """A late logical pool is observable drift, never native attribution."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
        dhcp_pool_selection="default",
    )

    class CompetingPool(_RetainingReapplicationTransport):
        inserted = False

        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if 'step:"dhcp_native_client_mode_probe"' in js_code and not self.inserted:
                self.inserted = True
                self.engine.evaluate(
                    'ipc.network().getDevice("__MCP_E6Q_SRV")'
                    '.getProcess("DhcpServerMain")'
                    '.getDhcpServerProcessByPortName("FastEthernet0")'
                    '.addPool("MCP_E6Q_DHCP");'
                )
            return outcome

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, CompetingPool(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measured["M-NATIVE-MODE"].conclusion is MeasurementConclusion.CONTRADICTED
        )
        assert measured["M-NATIVE-MODE"].facts["after_policy"]["pool_count"] == 2
        assert measured["M-NATIVE-SERVE"].status.value == "not_run"
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_observes_no_autonomous_lease_without_request(tmp_path) -> None:
    """The bounded passive window stays negative when mode yields no lease."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=False,
    )
    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, _RetainingReapplicationTransport(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measured["M-NATIVE-MODE"].conclusion
            is MeasurementConclusion.SUPPORTED_IN_SAMPLE
        )
        assert (
            measured["M-NATIVE-SERVE"].conclusion
            is MeasurementConclusion.NEGATIVE_OBSERVED
        )
        assert len(measured["M-NATIVE-SERVE"].facts["samples"]) == 13
        assert engine.snapshot()["dhcp_runs"] == []
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_contradicts_client_mask_despite_exact_native_row(
    tmp_path,
) -> None:
    """An exact IP/MAC row cannot make a wrong client mask usable."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
        dhcp_pool_selection="default",
        dhcp_client_mask_override="255.255.0.0",
    )
    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, _RetainingReapplicationTransport(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        serving = measured["M-NATIVE-SERVE"]
        assert serving.conclusion is MeasurementConclusion.CONTRADICTED
        assert len(serving.facts["samples"]) == 1
        assert serving.facts["samples"][0]["client"]["ipv4"] == "192.0.2.100"
        assert serving.facts["samples"][0]["client"]["netmask"] == "255.255.0.0"
        assert serving.facts["samples"][0]["row_status"] == "exact_ip_mac_row"
        assert result.record.restoration_proven
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["missing_entry", "lookup_error"])
def test_native_serve_keeps_unreadable_named_pool_control_inconclusive(
    tmp_path, fault
) -> None:
    """A native exact row cannot prove there is no competing named pool."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
        dhcp_pool_selection="default",
    )

    class MissingNamedEntry(_RetainingReapplicationTransport):
        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if (
                'step:"dhcp_lease_calibration"' in js_code
                and outcome.result is ResultFact.CORRELATED
            ):
                body = json.loads(outcome.body)
                for item in body["pools"]:
                    if item["requested"] == "MCP_E6Q_DHCP":
                        if fault == "missing_entry":
                            item["requested"] = "unbound-pool"
                        else:
                            item["found"] = False
                            item["error"] = "getPool threw"
                return replace(outcome, body=json.dumps(body))
            return outcome

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, MissingNamedEntry(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        serving = measured["M-NATIVE-SERVE"]
        assert serving.conclusion is MeasurementConclusion.INCONCLUSIVE
        assert len(serving.facts["samples"]) == 13
        assert serving.facts["samples"][-1]["native"]["observed"] is True
        assert serving.facts["samples"][-1]["named"]["observed"] is False
        assert serving.facts["samples"][-1]["policy_exact"] is True
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_refuses_row_from_misidentified_physical_pool(tmp_path) -> None:
    """A lease reached by the serverPool key needs serverPool's own name."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
        dhcp_pool_selection="default",
    )

    class WrongReturnedName(_RetainingReapplicationTransport):
        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if (
                'step:"dhcp_lease_calibration"' in js_code
                and outcome.result is ResultFact.CORRELATED
            ):
                body = json.loads(outcome.body)
                for item in body["pools"]:
                    if item["requested"] == "serverPool":
                        item["name"] = "otherPool"
                return replace(outcome, body=json.dumps(body))
            return outcome

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, WrongReturnedName(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        serving = measured["M-NATIVE-SERVE"]
        assert serving.conclusion is MeasurementConclusion.INCONCLUSIVE
        assert len(serving.facts["samples"]) == 13
        assert serving.facts["samples"][-1]["client"]["ipv4"] == "192.0.2.100"
        assert serving.facts["samples"][-1]["native"]["observed"] is False
        assert serving.facts["samples"][-1]["native"]["cause"] == (
            "scan_pool_identity_mismatch"
        )
        assert result.record.restoration_proven
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["first_index_throw", "capacity_unreadable"])
def test_native_serve_keeps_assigned_client_with_incomplete_native_scan_unknown(
    tmp_path, fault
) -> None:
    """A client address with incomplete row/capacity evidence is not absent."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
        dhcp_pool_selection="default",
    )

    class IncompleteNative(_RetainingReapplicationTransport):
        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if (
                'step:"dhcp_lease_calibration"' in js_code
                and outcome.result is ResultFact.CORRELATED
            ):
                body = json.loads(outcome.body)
                for item in body["pools"]:
                    if item["requested"] == "serverPool":
                        if fault == "first_index_throw":
                            item["entries"][0] = {
                                "index": 0,
                                "return_kind": "throw",
                                "error": "getLeaseAt failed",
                                "row": None,
                            }
                        else:
                            item["max"] = None
                            item["max_type"] = "throw"
                return replace(outcome, body=json.dumps(body))
            return outcome

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, IncompleteNative(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        serving = next(
            item
            for item in result.record.measurements
            if item.experiment_id == "M-NATIVE-SERVE"
        )
        assert serving.conclusion is MeasurementConclusion.INCONCLUSIVE
        assert len(serving.facts["samples"]) == 13
        assert serving.facts["samples"][-1]["client"]["ipv4"] == "192.0.2.100"
        assert serving.facts["samples"][-1]["native"]["observed"] is True
        assert serving.facts["samples"][-1]["ready"] is False
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_contradicts_more_rows_than_capacity(tmp_path) -> None:
    """A second observed lease on capacity one is a direct contradiction."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
        dhcp_pool_selection="default",
    )

    class ExtraRow(_RetainingReapplicationTransport):
        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if (
                'step:"dhcp_lease_calibration"' in js_code
                and outcome.result is ResultFact.CORRELATED
            ):
                body = json.loads(outcome.body)
                for item in body["pools"]:
                    if item["requested"] == "serverPool":
                        item["entries"][1] = {
                            "index": 1,
                            "return_kind": "object",
                            "error": "",
                            "row": {
                                "ipAddress": "192.0.2.101",
                                "ipAddress_type": "string",
                                "macAddress": "0000.0000.ffff",
                                "macAddress_type": "string",
                                "leaseTime": 3600,
                                "leaseTime_type": "number",
                                "port": "FastEthernet0",
                                "port_type": "string",
                            },
                        }
                return replace(outcome, body=json.dumps(body))
            return outcome

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, ExtraRow(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        serving = next(
            item
            for item in result.record.measurements
            if item.experiment_id == "M-NATIVE-SERVE"
        )
        assert serving.conclusion is MeasurementConclusion.CONTRADICTED
        assert len(serving.facts["samples"]) == 1
        assert len(serving.facts["samples"][0]["native"]["rows"]) == 2
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_native_serve_rejects_pc2_activation_during_sampling(tmp_path) -> None:
    """One good PC1 row cannot hide a newly competing second client."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
        dhcp_pool_selection="default",
    )

    class Pc2DuringSamples(_RetainingReapplicationTransport):
        activated = False

        def dispatch_and_wait(self, js_code, timeout):
            outcome = super().dispatch_and_wait(js_code, timeout)
            if 'step:"dhcp_lease_calibration"' in js_code and not self.activated:
                self.activated = True
                self.engine.evaluate(
                    'configurePcIp("__MCP_E6Q_PC2",true,null,null,null,null,'
                    '"FastEthernet0");'
                )
            return outcome

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, Pc2DuringSamples(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        serving = measured["M-NATIVE-SERVE"]
        assert serving.conclusion is MeasurementConclusion.CONTRADICTED
        assert serving.facts["samples"][0]["ready"] is True
        assert serving.facts["samples"][-1]["inactive_ok"] is False
        assert engine.snapshot()["dhcp_runs"] == []
        assert result.record.restoration_proven
    finally:
        engine.close()


@pytest.mark.parametrize("field", ["macAddress", "port"])
def test_native_serve_refuses_wrong_native_row_identity(tmp_path, field) -> None:
    """An address alone cannot attribute a lease to the selected client."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
        dhcp_pool_selection="default",
    )

    class WrongRow(_RetainingReapplicationTransport):
        tampered = False

        def dispatch_and_wait(self, js_code, timeout):
            if 'step:"dhcp_lease_calibration"' in js_code and not self.tampered:
                self.tampered = True
                value = "0000.0000.0001" if field == "macAddress" else "FastEthernet1"
                self.engine.evaluate(
                    'var p=ipc.network().getDevice("__MCP_E6Q_SRV")'
                    '.getProcess("DhcpServerMain")'
                    '.getDhcpServerProcessByPortName("FastEthernet0")'
                    '.getPool("serverPool");'
                    f"p.getLeaseAt(0).{field}={json.dumps(value)};"
                )
            return super().dispatch_and_wait(js_code, timeout)

    try:
        definition = stage_definition("Q3-NATIVE-SERVE")
        result = qualify_server_services(
            _request(
                request_args("Q3-NATIVE-SERVE") + authorization_args("Q3-NATIVE-SERVE")
            ),
            simulated_boundaries(tmp_path, WrongRow(engine)),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        measured = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measured["M-NATIVE-SERVE"].conclusion is MeasurementConclusion.CONTRADICTED
        )
        assert len(measured["M-NATIVE-SERVE"].facts["samples"]) == 1
        assert result.record.restoration_proven
    finally:
        engine.close()


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

    try:
        transport = _RetainingReapplicationTransport(engine)
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
