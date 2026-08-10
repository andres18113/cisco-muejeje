"""La capacidad Ethernet sale de lo que el backend hizo, no de una tabla.

Medido en vivo sobre PT 9.0.1.0858 (E9.5 Stage 3A3):

* un 2911 Gig0/0 contra un 3560 Fa0/1 negocia 100 Mbps, no 1 Gbps;
* `speed 1000` sobre un FastEthernet responde "% Invalid input";
* el uplink Gigabit del 3560 rechaza las tres formas de `duplex`;
* `duplex half` sobre un Gigabit en autonegociacion se rechaza con un texto
  que no contiene "% Invalid";
* `bandwidth 5000` mueve "BW 5000 Kbit" y deja "100Mbps" intacto.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
    PT_2911_GIGABIT_LINK_MODE,
    PT_3560_FASTETHERNET_LINK_MODE,
    PT_3560_GIGABIT_LINK_MODE,
    DuplexMode,
    LinkMedia,
    LinkPerformanceIntent,
    LinkPerformanceIssueCode,
    LinkSpeedMode,
    ModeEvidence,
    TrafficContribution,
    link_mode_capability_for,
    port_kind_of,
)
from src.packet_tracer_mcp.domain.enterprise.services.link_performance_planner import (
    LinkPerformancePlanner,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ios_rejection_reason,
    parse_ethernet_link_mode,
)

ROUTER_SHOW = """GigabitEthernet0/0 is up, line protocol is up (connected)
  Hardware is CN Gigabit Ethernet, address is 0001.4257.1901
  MTU 1500 bytes, BW 100000 Kbit, DLY 100 usec,
     reliability 255/255, txload 1/255, rxload 1/255
  Full Duplex, 100Mbps, link type is auto, media type is RJ45
"""

SWITCH_SHOW = """FastEthernet0/1 is up, line protocol is up (connected)
  Hardware is Lance, address is 0060.4741.0101
  MTU 1500 bytes, BW 100000 Kbit, DLY 100 usec,
  Full-duplex, 100Mb/s
"""

THROTTLED_SHOW = """GigabitEthernet0/0 is up, line protocol is up (connected)
  MTU 1500 bytes, BW 5000 Kbit, DLY 100 usec,
  Full Duplex, 100Mbps, link type is auto, media type is RJ45
"""

# Capturado tal cual de un uplink Gigabit sin cable. La linea fisica dice
# 100 Mb/s mientras el BW de routing dice 1 Gbps: el puerto en reposo informa
# cifras que no describen ningun enlace.
UNPLUGGED_SHOW = """GigabitEthernet0/1 is down, line protocol is down (disabled)
  Hardware is Lance, address is 0060.4741.0119
  MTU 1500 bytes, BW 1000000 Kbit, DLY 10 usec,
  Half-duplex, 100Mb/s
"""


def _codes(decision) -> list[str]:
    return [issue.code.value for issue in decision.issues]


def _ethernet(**overrides) -> LinkPerformanceIntent:
    return LinkPerformanceIntent(**{
        "link_id": "hq-core", "media": LinkMedia.ETHERNET, **overrides,
    })


class TestReadbackKeepsPhysicalAndRoutingApart:
    def test_both_backend_text_formats_are_read(self):
        """Un 2911 imprime "Full Duplex, 100Mbps" y un 3560 "Full-duplex, 100Mb/s"."""
        router = parse_ethernet_link_mode(ROUTER_SHOW)
        switch = parse_ethernet_link_mode(SWITCH_SHOW)

        assert (router.duplex, router.speed_bps) == ("full", 100_000_000)
        assert (switch.duplex, switch.speed_bps) == ("full", 100_000_000)

    def test_routing_bandwidth_moves_without_moving_the_physical_rate(self):
        throttled = parse_ethernet_link_mode(THROTTLED_SHOW)

        assert throttled.routing_bandwidth_kbps == 5_000
        assert throttled.speed_bps == 100_000_000

    def test_a_gigabit_port_negotiated_against_fast_ethernet_reads_100m(self):
        assert parse_ethernet_link_mode(ROUTER_SHOW).negotiated_speed_bps == 100_000_000

    def test_output_without_an_interface_header_is_not_invented(self):
        assert parse_ethernet_link_mode("% Invalid input detected") is None


class TestADownPortIsNotANegotiatedLink:
    """Un puerto sin cable informa "Half-duplex, 100Mb/s" igualmente."""

    def test_the_idle_line_is_read_but_not_taken_as_negotiated(self):
        unplugged = parse_ethernet_link_mode(UNPLUGGED_SHOW)

        assert unplugged.speed_bps == 100_000_000
        assert unplugged.negotiated_speed_bps is None
        assert unplugged.negotiated_duplex == ""

    def test_the_idle_line_contradicts_its_own_routing_bandwidth(self):
        """1 Gbps de BW junto a 100 Mb/s fisicos: no describen lo mismo."""
        unplugged = parse_ethernet_link_mode(UNPLUGGED_SHOW)

        assert unplugged.routing_bandwidth_kbps == 1_000_000
        assert unplugged.line_protocol_up is False

    def test_a_live_link_does_report_a_negotiated_rate(self):
        assert parse_ethernet_link_mode(SWITCH_SHOW).negotiated_speed_bps == 100_000_000


class TestRejectionIsNotDetectedByPercentAlone:
    def test_a_syslog_line_is_not_a_rejection(self):
        """`no shutdown` correcto emite %LINK-5-CHANGED y no rechaza nada."""
        output = (
            "no shutdown\n"
            "%LINK-5-CHANGED: Interface GigabitEthernet0/0, changed state to up\n"
            "%LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet0/0, "
            "changed state to up\n"
        )

        assert ios_rejection_reason(output) is None

    def test_an_invalid_input_is_a_rejection(self):
        assert ios_rejection_reason("speed 1000\n^\n% Invalid input detected") is not None

    def test_a_semantic_rejection_without_invalid_input_is_still_a_rejection(self):
        output = (
            "duplex half\n%Duplex cannot be set to half when speed "
            "autonegotiation subset contains 1Gbps.\n"
        )

        assert "Duplex cannot be set" in (ios_rejection_reason(output) or "")

    def test_a_clean_command_is_not_a_rejection(self):
        assert ios_rejection_reason("bandwidth 5000\nRouter(config-if)#") is None


class TestCapabilityKeepsEvidenceGrades:
    def test_a_rejected_speed_is_not_confused_with_an_untested_one(self):
        capability = PT_3560_FASTETHERNET_LINK_MODE

        assert capability.speed_evidence(LinkSpeedMode.SPEED_1G) is ModeEvidence.REJECTED
        assert capability.speed_evidence(LinkSpeedMode.SPEED_10M) is ModeEvidence.ACCEPTED

    def test_accepted_is_not_promoted_to_observed(self):
        """El CLI trago `speed 1000` en un Gig ya negociado sin cambiar nada."""
        assert PT_2911_GIGABIT_LINK_MODE.speed_evidence(
            LinkSpeedMode.SPEED_1G,
        ) is ModeEvidence.ACCEPTED

    def test_an_unmeasured_combination_stays_untested(self):
        assert PT_3560_GIGABIT_LINK_MODE.speed_evidence(
            LinkSpeedMode.SPEED_10M,
        ) is ModeEvidence.OBSERVED
        assert PT_2911_GIGABIT_LINK_MODE.duplex_evidence(
            DuplexMode.HALF,
        ) is ModeEvidence.REJECTED

    def test_no_profile_is_enumerated_completely(self):
        for capability in (PT_2911_GIGABIT_LINK_MODE, PT_3560_FASTETHERNET_LINK_MODE,
                           PT_3560_GIGABIT_LINK_MODE):
            assert capability.enumeration_complete is False


class TestCapabilityLookup:
    def test_the_port_kind_comes_from_the_interface_name(self):
        assert port_kind_of("GigabitEthernet0/1") == "GigabitEthernet"
        assert port_kind_of("FastEthernet0/24") == "FastEthernet"

    def test_a_model_and_port_kind_resolve_to_the_measured_profile(self):
        assert link_mode_capability_for(
            "3560-24PS", "FastEthernet0/1",
        ) is PT_3560_FASTETHERNET_LINK_MODE

    def test_the_same_model_yields_a_different_profile_per_port_kind(self):
        fast = link_mode_capability_for("3560-24PS", "FastEthernet0/1")
        gig = link_mode_capability_for("3560-24PS", "GigabitEthernet0/1")

        assert fast is not gig
        assert fast.nominal_capacity_bps < gig.nominal_capacity_bps

    def test_an_unmeasured_model_has_no_profile_instead_of_a_default(self):
        assert link_mode_capability_for("2960-24TT", "FastEthernet0/1") is None

    def test_a_different_backend_version_does_not_inherit_the_profile(self):
        assert link_mode_capability_for(
            "3560-24PS", "FastEthernet0/1", backend_version="8.2.0",
        ) is None


class TestLinkCeilingComesFromTheSlowerEnd:
    def test_a_gigabit_port_against_fast_ethernet_yields_a_100m_link(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert decision.link_ceiling_bps == 100_000_000

    def test_an_asymmetric_link_is_reported_without_blocking(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert decision.applicable
        assert any("asymmetric" in warning for warning in decision.warnings)

    def test_one_known_endpoint_is_not_enough_to_claim_a_ceiling(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
        ))

        assert decision.link_ceiling_bps is None

    def test_a_symmetric_link_reports_no_asymmetry(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_3560_GIGABIT_LINK_MODE,
        ))

        assert decision.link_ceiling_bps == 1_000_000_000
        assert decision.warnings == []

    def test_demand_beyond_the_ceiling_is_caught_even_under_autonegotiation(self):
        """Negociar no crea capacidad: 200 Mbps no caben en un enlace de 100."""
        decision = LinkPerformancePlanner().plan(_ethernet(
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
            traffic=[TrafficContribution(
                source_id="floor", per_unit_bps=8_000_000, units=25,
            )],
        ))

        assert LinkPerformanceIssueCode.LINK_CAPACITY_INSUFFICIENT.value in _codes(decision)


class TestAPortRefusesWhatTheBackendRefused:
    def test_a_gigabit_request_on_a_fast_ethernet_port_is_refused(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_1G,
            local_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert not decision.applicable
        assert LinkPerformanceIssueCode.SPEED_NOT_SUPPORTED.value in _codes(decision)

    def test_the_refusal_names_the_backend_it_was_measured_on(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_1G,
            local_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert "9.0.1.0858" in decision.issues[0].message

    def test_a_gigabit_request_is_refused_by_the_slower_far_end(self):
        """El extremo que no se configura tambien decide."""
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_1G,
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert not decision.applicable
        assert LinkPerformanceIssueCode.SPEED_NOT_SUPPORTED.value in _codes(decision)

    def test_half_duplex_on_a_gigabit_port_is_refused(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.HALF,
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
        ))

        assert LinkPerformanceIssueCode.DUPLEX_NOT_SUPPORTED.value in _codes(decision)

    def test_the_3560_uplink_refuses_every_duplex_form(self):
        for duplex in (DuplexMode.FULL, DuplexMode.HALF):
            decision = LinkPerformancePlanner().plan(_ethernet(
                requested_speed=LinkSpeedMode.SPEED_100M,
                requested_duplex=duplex,
                local_port_capability=PT_3560_GIGABIT_LINK_MODE,
            ))

            assert LinkPerformanceIssueCode.DUPLEX_NOT_SUPPORTED.value in _codes(decision)

    def test_an_untested_speed_is_not_refused_as_if_it_were_rejected(self):
        """No haberla probado no la invalida."""
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            local_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
            peer_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert decision.applicable

    def test_a_refused_request_selects_no_capacity_at_all(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_1G,
            local_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert decision.effective_capacity_bps is None


class TestPolicyIdentityMovedWithTheBehaviour:
    def test_the_policy_version_records_the_new_ethernet_rules(self):
        assert LinkPerformancePlanner().plan(_ethernet()).policy_version == "2"

    def test_the_ceiling_travels_in_the_explanation(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert decision.explain()["link_ceiling_bps"] == 100_000_000
