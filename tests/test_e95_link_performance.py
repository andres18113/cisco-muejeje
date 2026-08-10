"""Politica de capacidad y modo de enlace: seleccion determinista y explicable.

"Conecta HQ y BR01 por serial" no significa 2 Mbps porque si. Significa que no
hubo informacion de trafico, y el resultado tiene que poder decirlo: la fuente
es la politica de medio, no una peticion del usuario.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.compilation import ConcreteLinkRole
from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
    ENTERPRISE_SERIAL_FALLBACK_BPS,
    CapacitySource,
    DuplexMode,
    HeadroomPolicy,
    LinkMedia,
    LinkPerformanceIntent,
    LinkPerformanceIssueCode,
    LinkSpeedMode,
    ObservedLinkPerformance,
    TrafficContribution,
    capacity_source_rank,
)
from src.packet_tracer_mcp.domain.enterprise.services.link_performance_planner import (
    LinkPerformancePlanner,
)


def _serial(**overrides) -> LinkPerformanceIntent:
    base = {
        "link_id": "hq-br01",
        "media": LinkMedia.SERIAL,
        "role": ConcreteLinkRole.WAN_LINK,
        "dce_endpoint_device_id": "HQ-R1",
        "dte_endpoint_device_id": "BR01-R1",
    }
    base.update(overrides)
    return LinkPerformanceIntent(**base)


def _ethernet(**overrides) -> LinkPerformanceIntent:
    base = {
        "link_id": "acc-uplink",
        "media": LinkMedia.ETHERNET,
        "role": ConcreteLinkRole.ACCESS_UPLINK,
    }
    base.update(overrides)
    return LinkPerformanceIntent(**base)


def _codes(decision) -> set[str]:
    return {item.code.value for item in decision.issues}


class TestSerialCapacity:
    def test_explicit_capacity_is_recorded_as_the_user_request(self):
        decision = LinkPerformancePlanner().plan(
            _serial(requested_capacity_bps=4_000_000),
        )

        assert decision.effective_capacity_bps == 4_000_000
        assert decision.capacity_source is CapacitySource.EXPLICIT_USER
        assert decision.selection_reason == "EXPLICIT_USER_RATE"

    def test_no_traffic_information_falls_back_to_media_policy_not_to_the_user(self):
        """El caso que no puede volver a confundirse."""
        decision = LinkPerformancePlanner().plan(_serial())

        assert decision.effective_capacity_bps == ENTERPRISE_SERIAL_FALLBACK_BPS
        assert decision.capacity_source is CapacitySource.MEDIA_DEFAULT_POLICY
        assert decision.capacity_source is not CapacitySource.EXPLICIT_USER
        assert decision.selection_reason == (
            "ENTERPRISE_SERIAL_FALLBACK_WITHOUT_TRAFFIC_INFORMATION"
        )

    def test_traffic_demand_raises_the_selected_rate_above_the_fallback(self):
        decision = LinkPerformancePlanner().plan(_serial(traffic=[
            TrafficContribution(source_id="branch-users", per_unit_bps=64_000, units=60),
        ]))

        assert decision.calculated_demand_bps == 3_840_000
        assert decision.effective_capacity_bps == 8_000_000
        assert decision.capacity_source is CapacitySource.SERVICE_REQUIREMENT
        assert decision.selection_reason == (
            "SMALLEST_SUPPORTED_RATE_MEETING_ENGINEERED_DEMAND"
        )

    def test_headroom_is_applied_and_reported_not_hidden(self):
        decision = LinkPerformancePlanner().plan(_serial(traffic=[
            TrafficContribution(source_id="voice", per_unit_bps=134_000, units=10),
        ]))

        assert decision.calculated_demand_bps == 1_340_000
        assert decision.headroom_percent == 25.0
        assert decision.engineered_demand_bps == 1_675_000
        assert decision.effective_capacity_bps == 2_000_000

    def test_the_headroom_policy_is_injectable(self):
        decision = LinkPerformancePlanner(HeadroomPolicy(engineering_headroom_percent=0.0)).plan(
            _serial(traffic=[
                TrafficContribution(source_id="voice", per_unit_bps=134_000, units=10),
            ]),
        )

        assert decision.engineered_demand_bps == 1_340_000
        assert decision.effective_capacity_bps == 2_000_000

    def test_a_low_explicit_rate_stays_valid_and_is_not_upgraded(self):
        """64k y 128k siguen siendo configuraciones explicitas legitimas."""
        for rate in (64_000, 128_000):
            decision = LinkPerformancePlanner().plan(
                _serial(requested_capacity_bps=rate),
            )

            assert decision.effective_capacity_bps == rate
            assert decision.capacity_source is CapacitySource.EXPLICIT_USER

    def test_an_explicit_rate_below_the_engineered_demand_warns(self):
        decision = LinkPerformancePlanner().plan(_serial(
            requested_capacity_bps=64_000,
            traffic=[TrafficContribution(source_id="users", per_unit_bps=64_000, units=20)],
        ))

        assert decision.effective_capacity_bps == 64_000
        assert decision.warnings

    def test_an_unlisted_explicit_rate_climbs_to_the_smallest_that_meets_it(self):
        decision = LinkPerformancePlanner().plan(
            _serial(requested_capacity_bps=3_000_000),
        )

        assert decision.effective_capacity_bps == 4_000_000
        assert decision.selection_reason == (
            "SMALLEST_SUPPORTED_RATE_MEETING_EXPLICIT_REQUEST"
        )

    def test_demand_beyond_the_medium_is_reported_not_silently_capped(self):
        decision = LinkPerformancePlanner().plan(_serial(traffic=[
            TrafficContribution(source_id="datacenter", per_unit_bps=12_000_000, units=1),
        ]))

        assert decision.effective_capacity_bps is None
        assert decision.serial_clock_rate_bps is None
        assert not decision.applicable
        assert LinkPerformanceIssueCode.LINK_CAPACITY_INSUFFICIENT.value in _codes(decision)


class TestConcurrencyAndScope:
    def test_concurrency_below_one_reduces_the_demand(self):
        decision = LinkPerformancePlanner().plan(_serial(traffic=[
            TrafficContribution(
                source_id="voice", per_unit_bps=100_000, units=100, concurrency=0.1,
            ),
        ]))

        assert decision.calculated_demand_bps == 1_000_000

    def test_full_concurrency_sums_every_unit(self):
        decision = LinkPerformancePlanner().plan(_serial(traffic=[
            TrafficContribution(
                source_id="cctv", per_unit_bps=100_000, units=8, concurrency=1.0,
            ),
        ]))

        assert decision.calculated_demand_bps == 800_000

    def test_an_uplink_aggregates_its_flows_rather_than_using_one_endpoint(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            traffic=[
                TrafficContribution(source_id="users", per_unit_bps=2_000_000, units=24),
                TrafficContribution(source_id="printers", per_unit_bps=500_000, units=2),
            ],
        ))

        assert decision.calculated_demand_bps == 49_000_000

    def test_only_the_declared_flows_count(self):
        """Un flujo que no atraviesa el enlace no se declara y no suma."""
        decision = LinkPerformancePlanner().plan(_serial())

        assert decision.calculated_demand_bps == 0


class TestFailureSurvival:
    def test_survival_demand_replaces_normal_load_when_it_is_larger(self):
        decision = LinkPerformancePlanner().plan(_serial(
            traffic=[TrafficContribution(source_id="users", per_unit_bps=500_000, units=1)],
            failure_survival_bps=3_000_000,
        ))

        assert decision.calculated_demand_bps == 3_000_000

    def test_the_two_demands_are_not_added_together(self):
        decision = LinkPerformancePlanner().plan(_serial(
            traffic=[TrafficContribution(source_id="users", per_unit_bps=1_000_000, units=1)],
            failure_survival_bps=2_000_000,
        ))

        assert decision.calculated_demand_bps == 2_000_000


class TestSerialClockAndBandwidth:
    def test_the_clock_belongs_to_the_dce_endpoint_only(self):
        decision = LinkPerformancePlanner().plan(
            _serial(requested_capacity_bps=2_000_000),
        )

        assert decision.serial_clock_rate_bps == 2_000_000
        assert decision.dce_endpoint_device_id == "HQ-R1"
        assert decision.dte_endpoint_device_id == "BR01-R1"

    def test_an_unresolved_dce_blocks_the_clock(self):
        """El extremo DCE nunca se deduce del hostname."""
        decision = LinkPerformancePlanner().plan(
            _serial(dce_endpoint_device_id="", requested_capacity_bps=2_000_000),
        )

        assert decision.serial_clock_rate_bps is None
        assert LinkPerformanceIssueCode.DCE_ENDPOINT_UNRESOLVED.value in _codes(decision)

    def test_routing_bandwidth_is_not_derived_unless_the_policy_asks(self):
        decision = LinkPerformancePlanner().plan(
            _serial(requested_capacity_bps=2_000_000),
        )

        assert decision.routing_bandwidth_kbps is None

    def test_the_sync_policy_derives_kbps_without_replacing_the_clock(self):
        decision = LinkPerformancePlanner().plan(_serial(
            requested_capacity_bps=2_000_000,
            sync_routing_bandwidth_to_effective_capacity=True,
        ))

        assert decision.serial_clock_rate_bps == 2_000_000
        assert decision.routing_bandwidth_kbps == 2_000
        assert decision.serial_clock_rate_bps != decision.routing_bandwidth_kbps


class TestEthernetPolicy:
    def test_no_intent_leaves_both_sides_negotiating(self):
        decision = LinkPerformancePlanner().plan(_ethernet())

        assert decision.effective_speed is LinkSpeedMode.AUTO
        assert decision.effective_duplex is DuplexMode.AUTO
        assert decision.capacity_source is CapacitySource.MEDIA_DEFAULT_POLICY
        assert decision.selection_reason == "AUTONEGOTIATION_LEFT_TO_THE_LINK"

    def test_auto_does_not_emit_a_routing_bandwidth(self):
        """La plataforma conserva su ancho de banda logico."""
        assert LinkPerformancePlanner().plan(_ethernet()).routing_bandwidth_kbps is None

    def test_an_explicit_mode_is_recorded_as_the_user_request(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M, requested_duplex=DuplexMode.FULL,
        ))

        assert decision.effective_speed is LinkSpeedMode.SPEED_100M
        assert decision.effective_duplex is DuplexMode.FULL
        assert decision.effective_capacity_bps == 100_000_000
        assert decision.capacity_source is CapacitySource.EXPLICIT_USER

    def test_a_duplex_mismatch_is_a_compile_error_not_a_runtime_surprise(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.FULL,
            peer_duplex=DuplexMode.HALF,
        ))

        assert not decision.applicable
        assert LinkPerformanceIssueCode.DUPLEX_MISMATCH.value in _codes(decision)

    def test_a_speed_the_peer_cannot_reach_is_rejected(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_1G,
            peer_supported_speeds=[LinkSpeedMode.SPEED_10M, LinkSpeedMode.SPEED_100M],
        ))

        assert LinkPerformanceIssueCode.SPEED_NOT_SUPPORTED.value in _codes(decision)

    def test_demand_beyond_the_requested_speed_is_reported(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_10M,
            traffic=[TrafficContribution(source_id="users", per_unit_bps=2_000_000, units=24)],
        ))

        assert LinkPerformanceIssueCode.LINK_CAPACITY_INSUFFICIENT.value in _codes(decision)

    def test_an_auto_peer_never_produces_a_mismatch(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.FULL,
            peer_duplex=DuplexMode.AUTO,
        ))

        assert decision.applicable


class TestRequestedEffectiveObserved:
    def test_an_observation_does_not_rewrite_the_request_or_the_plan(self):
        intent = _ethernet()
        decision = LinkPerformancePlanner().plan(intent)
        observed = ObservedLinkPerformance(
            link_id=intent.link_id, observed_speed=LinkSpeedMode.SPEED_1G,
            observed_duplex=DuplexMode.FULL, observed=True,
        )

        assert intent.requested_speed is LinkSpeedMode.AUTO
        assert decision.effective_speed is LinkSpeedMode.AUTO
        assert observed.observed_speed is LinkSpeedMode.SPEED_1G

    def test_media_must_be_resolved_before_any_policy_applies(self):
        decision = LinkPerformancePlanner().plan(
            LinkPerformanceIntent(link_id="x", media=LinkMedia.UNKNOWN),
        )

        assert LinkPerformanceIssueCode.MEDIA_UNKNOWN.value in _codes(decision)


class TestPrecedenceAndDeterminism:
    def test_the_documented_precedence_orders_the_sources(self):
        assert capacity_source_rank(CapacitySource.EXPLICIT_USER) < capacity_source_rank(
            CapacitySource.SERVICE_REQUIREMENT,
        )
        assert capacity_source_rank(CapacitySource.SERVICE_REQUIREMENT) < capacity_source_rank(
            CapacitySource.MEDIA_DEFAULT_POLICY,
        )
        assert capacity_source_rank(CapacitySource.MEDIA_DEFAULT_POLICY) < capacity_source_rank(
            CapacitySource.ENTERPRISE_FALLBACK,
        )

    def test_an_unresolved_source_never_outranks_a_real_one(self):
        assert capacity_source_rank(CapacitySource.UNRESOLVED) > capacity_source_rank(
            CapacitySource.ENTERPRISE_FALLBACK,
        )

    def test_the_flow_order_does_not_change_the_decision(self):
        flows = [
            TrafficContribution(source_id="a", per_unit_bps=300_000, units=2),
            TrafficContribution(source_id="b", per_unit_bps=90_000, units=5),
            TrafficContribution(source_id="c", per_unit_bps=41_000, units=3),
        ]
        planner = LinkPerformancePlanner()

        first = planner.plan(_serial(traffic=list(flows)))
        second = planner.plan(_serial(traffic=list(reversed(flows))))

        assert first.model_dump() == second.model_dump()

    def test_repeating_the_same_input_repeats_the_same_decision(self):
        planner = LinkPerformancePlanner()
        intent = _serial(traffic=[
            TrafficContribution(source_id="users", per_unit_bps=64_000, units=17),
        ])

        assert planner.plan(intent).model_dump() == planner.plan(intent).model_dump()


class TestExplainability:
    def test_the_summary_answers_why_this_rate_and_not_another(self):
        decision = LinkPerformancePlanner().plan(_serial(traffic=[
            TrafficContribution(source_id="voice", per_unit_bps=134_000, units=10),
        ]))
        summary = decision.explain()

        assert summary["calculated_demand_bps"] == 1_340_000
        assert summary["headroom_percent"] == 25.0
        assert summary["engineered_demand_bps"] == 1_675_000
        assert 1_000_000 in summary["supported_capacities_bps"]
        assert summary["selected_capacity_bps"] == 2_000_000
        assert summary["capacity_source"] == "service_requirement"
        assert summary["reason"] == "SMALLEST_SUPPORTED_RATE_MEETING_ENGINEERED_DEMAND"

    def test_the_fallback_summary_never_claims_the_user_asked_for_it(self):
        summary = LinkPerformancePlanner().plan(_serial()).explain()

        assert summary["capacity_source"] == "media_default_policy"
        assert summary["selected_capacity_bps"] == ENTERPRISE_SERIAL_FALLBACK_BPS

    def test_the_role_travels_with_the_decision(self):
        summary = LinkPerformancePlanner().plan(_serial()).explain()

        assert summary["role"] == ConcreteLinkRole.WAN_LINK.value


class TestTypedActions:
    def test_the_link_actions_exist_and_carry_no_command_strings(self):
        from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
            ConfigureEthernetLinkMode,
            ConfigureInterfaceBandwidth,
            ConfigureSerialClock,
        )

        fields = set(ConfigureSerialClock.model_fields)
        assert "clock_rate_bps" in fields
        assert "command" not in fields and "ios" not in fields
        assert "bandwidth_kbps" in set(ConfigureInterfaceBandwidth.model_fields)
        assert {"speed", "duplex"} <= set(ConfigureEthernetLinkMode.model_fields)

    def test_the_serial_clock_action_is_pinned_to_the_dce_role(self):
        from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
            ConfigureSerialClock,
        )
        from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
            ConfigurationPhase,
        )

        action = ConfigureSerialClock(
            id="a1", phase=ConfigurationPhase.L2_INTERFACES, device_id="d1",
            device_name="HQ-R1", site_id="hq", interface="Serial0/0/0",
            clock_rate_bps=2_000_000,
        )

        assert action.serial_endpoint_role == "dce"

    @pytest.mark.parametrize("bad", (-1, 0))
    def test_a_non_positive_headroom_never_shrinks_the_demand(self, bad):
        engineered = HeadroomPolicy(engineering_headroom_percent=bad).engineered_bps(1_000_000)

        assert engineered >= 1_000_000
