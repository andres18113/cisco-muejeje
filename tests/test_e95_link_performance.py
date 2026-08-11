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
    CapacityRequestMode,
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
            TrafficContribution(source_id="branch-users", per_unit_bps=64_000, units=45),
        ]))

        assert decision.calculated_demand_bps == 2_880_000
        assert decision.effective_capacity_bps == 4_000_000
        assert decision.capacity_source is CapacitySource.TRAFFIC_CALCULATION
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
            "SMALLEST_SUPPORTED_RATE_MEETING_MINIMUM_REQUEST"
        )

    def test_an_exact_unsupported_rate_is_rejected_not_rounded_up(self):
        """"Exactamente 3 Mbps" no puede convertirse en 4 en silencio."""
        decision = LinkPerformancePlanner().plan(_serial(
            requested_capacity_bps=3_000_000,
            requested_capacity_mode=CapacityRequestMode.EXACT,
        ))

        assert decision.effective_capacity_bps is None
        assert decision.serial_clock_rate_bps is None
        assert not decision.applicable
        assert LinkPerformanceIssueCode.EXACT_CAPACITY_UNSUPPORTED.value in _codes(decision)

    def test_an_exact_supported_rate_is_accepted(self):
        decision = LinkPerformancePlanner().plan(_serial(
            requested_capacity_bps=2_000_000,
            requested_capacity_mode=CapacityRequestMode.EXACT,
        ))

        assert decision.effective_capacity_bps == 2_000_000
        assert decision.applicable

    def test_the_decision_records_which_policy_produced_it(self):
        """Fijada a proposito: subir la version sin querer rompe aqui.

        v2 la subio Stage 3A3, v3 Stage 3A3-B, v4 Stage 3A3-C, v5 Stage 3A3-G
        y v6 Stage 3A3-H al revertir aquella sustitucion del techo
        negociable por la capacidad efectiva. La politica serial no cambio
        con ninguna de ellas.
        """
        decision = LinkPerformancePlanner().plan(_serial())

        assert decision.policy_id == "enterprise-link-performance"
        assert decision.policy_version == "6"

    def test_a_different_policy_version_is_visible_in_the_decision(self):
        """Un cambio de politica que altere el comportamiento se puede ver."""
        decision = LinkPerformancePlanner(policy_version="9").plan(_serial())

        assert decision.policy_version == "9"
        assert decision.explain()["policy"] == "enterprise-link-performance@9"

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
            link_id=intent.link_id, reported_speed=LinkSpeedMode.SPEED_1G,
            reported_duplex=DuplexMode.FULL, observed=True,
        )

        assert intent.requested_speed is LinkSpeedMode.AUTO
        assert decision.effective_speed is LinkSpeedMode.AUTO
        assert observed.reported_speed is LinkSpeedMode.SPEED_1G

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
        assert summary["capacity_source"] == "traffic_calculation"
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


class TestLiveVerifiedSerialCeiling:
    """El techo serial sale de una reproduccion controlada, no de una tabla.

    Sobre PT 9.0.1.0858, un 2911 con HWIC-2T acepto y volvio a leer 64k, 128k,
    2M y 4M; 8M y 3M dejaron la interfaz en su valor anterior.
    """

    def test_the_live_verified_rates_are_the_selectable_ones(self):
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            SUPPORTED_SERIAL_RATES_BPS,
        )

        assert 4_000_000 in SUPPORTED_SERIAL_RATES_BPS
        assert 8_000_000 not in SUPPORTED_SERIAL_RATES_BPS

    def test_demand_above_the_verified_ceiling_is_insufficient_not_capped(self):
        decision = LinkPerformancePlanner().plan(_serial(traffic=[
            TrafficContribution(source_id="wan", per_unit_bps=5_000_000, units=1),
        ]))

        assert decision.effective_capacity_bps is None
        assert LinkPerformanceIssueCode.LINK_CAPACITY_INSUFFICIENT.value in _codes(decision)

    def test_a_backend_with_more_headroom_can_declare_it(self):
        planner = LinkPerformancePlanner(
            supported_serial_rates_bps=(2_000_000, 4_000_000, 8_000_000),
        )
        decision = planner.plan(_serial(traffic=[
            TrafficContribution(source_id="wan", per_unit_bps=5_000_000, units=1),
        ]))

        assert decision.effective_capacity_bps == 8_000_000


class TestSerialRenderer:
    def test_the_clock_renders_in_bits_per_second_on_its_interface(self):
        from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
            ConfigurationPhase, ConfigureSerialClock,
        )
        from src.packet_tracer_mcp.infrastructure.generator.link_performance_renderer import (
            render_serial_clock,
        )

        lines = render_serial_clock(ConfigureSerialClock(
            id="a", phase=ConfigurationPhase.L2_INTERFACES, device_id="d",
            device_name="HQ-R1", site_id="hq", interface="Serial0/0/0",
            clock_rate_bps=2_000_000,
        ))

        assert lines == ["interface Serial0/0/0", " clock rate 2000000"]

    def test_bandwidth_renders_in_kbps_and_never_as_a_clock(self):
        from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
            ConfigurationPhase, ConfigureInterfaceBandwidth,
        )
        from src.packet_tracer_mcp.infrastructure.generator.link_performance_renderer import (
            render_interface_bandwidth,
        )

        lines = render_interface_bandwidth(ConfigureInterfaceBandwidth(
            id="a", phase=ConfigurationPhase.L2_INTERFACES, device_id="d",
            device_name="HQ-R1", site_id="hq", interface="Serial0/0/0",
            bandwidth_kbps=2_000,
        ))

        assert lines == ["interface Serial0/0/0", " bandwidth 2000"]
        assert "clock" not in " ".join(lines)

    def test_auto_ethernet_renders_nothing(self):
        from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
            ConfigurationPhase, ConfigureEthernetLinkMode,
        )
        from src.packet_tracer_mcp.infrastructure.generator.link_performance_renderer import (
            render_ethernet_link_mode,
        )

        assert render_ethernet_link_mode(ConfigureEthernetLinkMode(
            id="a", phase=ConfigurationPhase.L2_INTERFACES, device_id="d",
            device_name="SW1", site_id="hq", interface="Gig0/1",
        )) == []


class TestControllerParser:
    """Lectura real de `show controllers` de PT 9.0.1.0858."""

    _DCE = (
        "show controllers Serial0/0/0\n"
        "Interface Serial0/0/0\n"
        "Hardware is PowerQUICC MPC860\n"
        "DCE V.35, clock rate 2000000\n"
    )
    _DTE = (
        "show controllers Serial0/0/0\n"
        "Interface Serial0/0/0\n"
        "Hardware is PowerQUICC MPC860\n"
        "DTE V.35 TX and RX clocks detected\n"
    )

    def test_the_dce_end_reports_its_role_and_clock(self):
        from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
            parse_serial_controller,
        )
        row = parse_serial_controller(self._DCE)

        assert row.endpoint_role == "dce"
        assert row.clock_rate_bps == 2_000_000

    def test_the_dte_end_reports_no_clock_of_its_own(self):
        from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
            parse_serial_controller,
        )
        row = parse_serial_controller(self._DTE)

        assert row.endpoint_role == "dte"
        assert row.clock_rate_bps is None

    def test_unrelated_output_yields_nothing(self):
        from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
            parse_serial_controller,
        )

        assert parse_serial_controller("% Invalid input") is None


class TestProvenanceScoping:
    """La capability serial es evidencia con procedencia, no una tabla Cisco."""

    def test_the_measured_profile_names_its_backend_and_hardware(self):
        from src.packet_tracer_mcp.infrastructure.catalog.link_mode_capabilities import (
            PT_2911_HWIC2T_SERIAL_CLOCK,
        )
        profile = PT_2911_HWIC2T_SERIAL_CLOCK

        assert profile.backend_version == "9.0.1.0858"
        assert profile.device_model == "2911"
        assert 4_000_000 in profile.verified_rates_bps
        assert 8_000_000 in profile.rejected_rates_bps

    def test_the_highest_tested_rate_is_not_claimed_as_an_absolute_maximum(self):
        from src.packet_tracer_mcp.infrastructure.catalog.link_mode_capabilities import (
            PT_2911_HWIC2T_SERIAL_CLOCK,
        )
        profile = PT_2911_HWIC2T_SERIAL_CLOCK

        assert profile.highest_verified_tested_rate_bps == 4_000_000
        assert not profile.enumeration_complete

    def test_traffic_calculation_outranks_role_and_media_policy(self):
        assert capacity_source_rank(CapacitySource.TRAFFIC_CALCULATION) < (
            capacity_source_rank(CapacitySource.MEDIA_DEFAULT_POLICY)
        )

    def test_a_declared_service_requirement_stays_a_separate_source(self):
        """Un calculo de trafico no es un requisito de servicio declarado."""
        assert CapacitySource.TRAFFIC_CALCULATION is not CapacitySource.SERVICE_REQUIREMENT
        assert capacity_source_rank(CapacitySource.SERVICE_REQUIREMENT) < (
            capacity_source_rank(CapacitySource.TRAFFIC_CALCULATION)
        )

    def test_encapsulation_defaults_are_never_claimed_as_a_choice(self):
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            EncapsulationSource,
        )
        decision = LinkPerformancePlanner().plan(_serial())

        assert decision.encapsulation_source is EncapsulationSource.PLATFORM_DEFAULT
        assert decision.explain()["encapsulation_source"] == "platform_default"
