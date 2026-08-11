"""La capacidad Ethernet sale de lo que el backend hizo, y con su contexto.

Stage 3A3 escribio aqui dos premisas falsas que Stage 3A3-B corrigio midiendo:

* `duplex half` no esta rechazado "por ser un puerto Gigabit". El backend cita
  el subset de autonegociacion, y el rechazo se reprodujo tambien despues de
  fijar `speed 100`. Se guarda como rechazo EN CONTEXTO, no como universal.
* el texto de `show interfaces` no es la tasa negociada: un enlace
  Gigabit<->Gigabit informa "100Mbps" mientras su bandwidth de routing dice
  1 Gbps. Lo que sigue a la negociacion es el bandwidth de routing, y solo
  mientras nadie lo fije a mano.

Y una tercera que faltaba: aceptar no autoriza. `speed 100` sobre un Gigabit
enlazado se acepta sin efecto observable ni tras rebotar el enlace.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.evidence import ReadinessStatus
from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
    DuplexMode,
    LinkMedia,
    LinkModeContext,
    LinkModeOutcome,
    LinkPerformanceIntent,
    LinkPerformanceIssueCode,
    BandwidthProvenance,
    LinkSpeedMode,
    NominalCapacitySource,
    ObservedLinkPerformance,
    TrafficContribution,
    nominal_link_ceiling_bps,
    port_kind_of,
)
from src.packet_tracer_mcp.domain.enterprise.services.link_performance_planner import (
    LinkPerformancePlanner,
)
from src.packet_tracer_mcp.infrastructure.catalog.link_mode_capabilities import (
    PT_2911_GIGABIT_LINK_MODE,
    PT_3560_FASTETHERNET_LINK_MODE,
    PT_3560_GIGABIT_LINK_MODE,
    link_mode_capability_for,
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

# Capturado de un uplink Gigabit sin cable: informa cifras que no describen
# ningun enlace, y ademas se contradicen entre si.
UNPLUGGED_SHOW = """GigabitEthernet0/1 is down, line protocol is down (disabled)
  Hardware is Lance, address is 0060.4741.0119
  MTU 1500 bytes, BW 1000000 Kbit, DLY 10 usec,
  Half-duplex, 100Mb/s
"""

# Capturado de un enlace Gigabit<->Gigabit realmente negociado a 1 Gbps.
GIG_TO_GIG_SHOW = """GigabitEthernet0/0 is up, line protocol is up (connected)
  MTU 1500 bytes, BW 1000000 Kbit, DLY 10 usec,
  Full Duplex, 100Mbps, link type is auto, media type is RJ45
"""


def _codes(decision) -> list[str]:
    return [issue.code.value for issue in decision.issues]


def _ethernet(**overrides) -> LinkPerformanceIntent:
    return LinkPerformanceIntent(**{
        "link_id": "hq-core", "media": LinkMedia.ETHERNET, **overrides,
    })


class TestTheShowTextIsNotTheNegotiatedRate:
    def test_both_backend_text_formats_are_read(self):
        """Un 2911 imprime "Full Duplex, 100Mbps" y un 3560 "Full-duplex, 100Mb/s"."""
        router = parse_ethernet_link_mode(ROUTER_SHOW)
        switch = parse_ethernet_link_mode(SWITCH_SHOW)

        assert (router.duplex, router.speed_bps) == ("full", 100_000_000)
        assert (switch.duplex, switch.speed_bps) == ("full", 100_000_000)

    def test_a_gigabit_link_reports_100mbps_while_its_bandwidth_says_1g(self):
        """La razon por la que ese texto no puede usarse como tasa negociada."""
        gig = parse_ethernet_link_mode(GIG_TO_GIG_SHOW)

        assert gig.reported_speed_bps == 100_000_000
        assert gig.routing_bandwidth_kbps == 1_000_000

    def test_routing_bandwidth_moves_without_moving_the_reported_speed(self):
        throttled = parse_ethernet_link_mode(THROTTLED_SHOW)

        assert throttled.routing_bandwidth_kbps == 5_000
        assert throttled.speed_bps == 100_000_000

    def test_output_without_an_interface_header_is_not_invented(self):
        assert parse_ethernet_link_mode("% Invalid input detected") is None


class TestADownPortIsNotANegotiatedLink:
    def test_the_idle_line_is_read_but_not_reported_as_a_link(self):
        unplugged = parse_ethernet_link_mode(UNPLUGGED_SHOW)

        assert unplugged.speed_bps == 100_000_000
        assert unplugged.reported_speed_bps is None
        assert unplugged.reported_duplex == ""

    def test_the_idle_line_contradicts_its_own_routing_bandwidth(self):
        unplugged = parse_ethernet_link_mode(UNPLUGGED_SHOW)

        assert unplugged.routing_bandwidth_kbps == 1_000_000
        assert unplugged.line_protocol_up is False


class TestRejectionIsNotDetectedByPercentAlone:
    def test_a_syslog_line_is_not_a_rejection(self):
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


class TestCapabilityIsContextual:
    def test_half_duplex_is_refused_on_a_gigabit_port_even_after_forcing_100(self):
        """Reproducido: el rechazo persiste tras `speed 100`."""
        outcome = PT_2911_GIGABIT_LINK_MODE.outcome_for(
            LinkSpeedMode.SPEED_100M, DuplexMode.HALF, LinkModeContext.LINKED,
        )

        assert outcome is LinkModeOutcome.COMMAND_REJECTED

    def test_the_same_port_applies_full_duplex_at_100(self):
        outcome = PT_2911_GIGABIT_LINK_MODE.outcome_for(
            LinkSpeedMode.SPEED_100M, DuplexMode.FULL, LinkModeContext.LINKED,
        )

        assert outcome is LinkModeOutcome.MODE_EFFECT_OBSERVED

    def test_speed_on_a_linked_gigabit_port_is_accepted_without_effect(self):
        outcome = PT_2911_GIGABIT_LINK_MODE.outcome_for(
            LinkSpeedMode.SPEED_100M, DuplexMode.AUTO, LinkModeContext.LINKED,
        )

        assert outcome is LinkModeOutcome.COMMAND_ACCEPTED

    def test_the_uplink_effect_was_only_seen_unlinked(self):
        """El contexto cambia el resultado, y por eso se guarda."""
        unlinked = PT_3560_GIGABIT_LINK_MODE.outcome_for(
            LinkSpeedMode.SPEED_1G, DuplexMode.AUTO, LinkModeContext.UNLINKED,
        )
        linked = PT_3560_GIGABIT_LINK_MODE.outcome_for(
            LinkSpeedMode.SPEED_100M, DuplexMode.AUTO, LinkModeContext.LINKED,
        )

        assert unlinked is LinkModeOutcome.MODE_EFFECT_OBSERVED
        assert linked is LinkModeOutcome.COMMAND_ACCEPTED

    def test_an_unmeasured_combination_is_not_measured(self):
        assert PT_3560_FASTETHERNET_LINK_MODE.outcome_for(
            LinkSpeedMode.SPEED_10M, DuplexMode.HALF, LinkModeContext.LINKED,
        ) is LinkModeOutcome.NOT_MEASURED

    def test_no_profile_is_enumerated_completely(self):
        for capability in (PT_2911_GIGABIT_LINK_MODE, PT_3560_FASTETHERNET_LINK_MODE,
                           PT_3560_GIGABIT_LINK_MODE):
            assert capability.enumeration_complete is False


class TestEvidenceUsesTheSharedVocabulary:
    def test_every_observation_carries_an_evidence_record(self):
        for capability in (PT_2911_GIGABIT_LINK_MODE, PT_3560_FASTETHERNET_LINK_MODE,
                           PT_3560_GIGABIT_LINK_MODE):
            for observation in capability.observations:
                assert observation.evidence is not None

    def test_provenance_travels_with_the_evidence(self):
        record = PT_2911_GIGABIT_LINK_MODE.observations[0].evidence

        assert record.backend_version == "9.0.1.0858"
        assert record.backend == "packet_tracer"

    def test_an_accepted_command_records_its_limitation(self):
        """No basta con no marcarlo verificado: hay que decir por que."""
        observation = PT_2911_GIGABIT_LINK_MODE.observation_for(
            LinkSpeedMode.SPEED_100M, DuplexMode.AUTO, LinkModeContext.LINKED,
        )

        assert observation.evidence.limitations
        assert not observation.evidence.verifies_claim

    def test_a_rejection_is_recorded_as_unsupported_and_observed(self):
        observation = PT_2911_GIGABIT_LINK_MODE.observation_for(
            LinkSpeedMode.SPEED_100M, DuplexMode.HALF, LinkModeContext.LINKED,
        )

        assert observation.evidence.classification == "unsupported"
        assert "1Gbps" in observation.prerequisite


class TestReadinessSeparatesCompileFromApply:
    def test_a_measured_mode_is_ready_on_all_three_axes(self):
        readiness = PT_2911_GIGABIT_LINK_MODE.readiness_for(
            LinkSpeedMode.SPEED_100M, DuplexMode.FULL, LinkModeContext.LINKED,
        )

        assert readiness.apply is ReadinessStatus.READY
        assert readiness.verify is ReadinessStatus.READY

    def test_an_accepted_mode_compiles_but_does_not_reach_apply_readiness(self):
        readiness = PT_2911_GIGABIT_LINK_MODE.readiness_for(
            LinkSpeedMode.SPEED_100M, DuplexMode.AUTO, LinkModeContext.LINKED,
        )

        assert readiness.compile is ReadinessStatus.READY
        assert readiness.apply is ReadinessStatus.PARTIAL

    def test_an_unmeasured_mode_compiles_with_unknown_apply(self):
        """UNKNOWN no es UNSUPPORTED, y tampoco es permiso."""
        readiness = PT_3560_FASTETHERNET_LINK_MODE.readiness_for(
            LinkSpeedMode.SPEED_10M, DuplexMode.HALF, LinkModeContext.LINKED,
        )

        assert readiness.compile is ReadinessStatus.READY
        assert readiness.apply is ReadinessStatus.UNKNOWN
        assert readiness.apply is not ReadinessStatus.UNSUPPORTED

    def test_a_rejected_mode_is_unsupported_on_all_three_axes(self):
        readiness = PT_3560_GIGABIT_LINK_MODE.readiness_for(
            LinkSpeedMode.SPEED_100M, DuplexMode.FULL, LinkModeContext.LINKED,
        )

        assert readiness.apply is ReadinessStatus.UNSUPPORTED


class TestUnknownDoesNotAuthorizeAMutation:
    def test_an_unmeasured_mode_does_not_reach_a_production_mutation(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_10M,
            requested_duplex=DuplexMode.HALF,
            local_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert not decision.applicable
        assert LinkPerformanceIssueCode.LINK_MODE_NOT_VERIFIED.value in _codes(decision)

    def test_the_unmeasured_mode_is_not_reported_as_unsupported(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_10M,
            requested_duplex=DuplexMode.HALF,
            local_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert LinkPerformanceIssueCode.SPEED_NOT_SUPPORTED.value not in _codes(decision)
        assert LinkPerformanceIssueCode.DUPLEX_NOT_SUPPORTED.value not in _codes(decision)
        assert decision.mode_readiness.apply is ReadinessStatus.UNKNOWN

    def test_a_controlled_exploration_may_request_it_deliberately(self):
        """La ruta de probe existe; no es la productiva."""
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_10M,
            requested_duplex=DuplexMode.HALF,
            local_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
            allow_unverified_mode_exploration=True,
        ))

        assert decision.applicable
        assert any("Controlled exploration" in w for w in decision.warnings)

    def test_acceptance_alone_never_authorizes_forcing_a_speed(self):
        """`speed 100` enlazado fue aceptado y no cambio nada: eso no es soporte."""
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.AUTO,
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_2911_GIGABIT_LINK_MODE,
        ))

        assert not decision.applicable
        assert LinkPerformanceIssueCode.LINK_MODE_NOT_VERIFIED.value in _codes(decision)


class TestAPortRefusesWhatTheBackendRefused:
    def test_half_duplex_on_a_gigabit_port_is_refused_with_its_condition(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.HALF,
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
        ))

        assert LinkPerformanceIssueCode.DUPLEX_NOT_SUPPORTED.value in _codes(decision)
        assert "1Gbps" in decision.issues[0].message

    def test_the_refusal_names_the_backend_and_the_context(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.FULL,
            local_port_capability=PT_3560_GIGABIT_LINK_MODE,
        ))

        assert "9.0.1.0858" in decision.issues[0].message
        assert "linked" in decision.issues[0].message

    def test_a_gigabit_request_on_a_fast_ethernet_port_is_refused(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_1G,
            requested_duplex=DuplexMode.FULL,
            local_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert not decision.applicable
        assert decision.effective_capacity_bps is None

    def test_the_refusal_blames_the_axis_that_actually_failed(self):
        """1G/full en un FastEthernet lo rechaza la velocidad, no el duplex."""
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_1G,
            requested_duplex=DuplexMode.FULL,
            local_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert LinkPerformanceIssueCode.SPEED_NOT_SUPPORTED.value in _codes(decision)
        assert LinkPerformanceIssueCode.DUPLEX_NOT_SUPPORTED.value not in _codes(decision)

    def test_a_duplex_only_refusal_still_blames_the_duplex(self):
        """En el uplink Gigabit la velocidad pasa y lo que cae es el duplex."""
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.FULL,
            local_port_capability=PT_3560_GIGABIT_LINK_MODE,
        ))

        assert LinkPerformanceIssueCode.DUPLEX_NOT_SUPPORTED.value in _codes(decision)

    def test_a_refused_request_selects_no_capacity_at_all(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.HALF,
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
        ))

        assert decision.effective_capacity_bps is None


class TestNominalIsNotVerifiedMutual:
    def test_nominal_capacity_declares_where_it_came_from(self):
        assert (
            PT_2911_GIGABIT_LINK_MODE.nominal_capacity_source
            is NominalCapacitySource.PORT_CLASS
        )

    def test_no_profile_derives_nominal_capacity_from_a_bandwidth_getter(self):
        """`getBandwidth()` es metadata de routing: no puede fundar una capacidad."""
        for capability in (PT_2911_GIGABIT_LINK_MODE, PT_3560_FASTETHERNET_LINK_MODE,
                           PT_3560_GIGABIT_LINK_MODE):
            assert (
                capability.nominal_capacity_source
                is not NominalCapacitySource.CONTROLLED_RUNTIME_OBSERVATION
            )

    def test_the_nominal_ceiling_is_the_slower_endpoint(self):
        ceiling = nominal_link_ceiling_bps(
            PT_2911_GIGABIT_LINK_MODE, PT_3560_FASTETHERNET_LINK_MODE,
        )

        assert ceiling == 100_000_000

    def test_one_known_endpoint_is_not_enough_to_claim_a_ceiling(self):
        assert nominal_link_ceiling_bps(PT_2911_GIGABIT_LINK_MODE, None) is None

    def test_two_gigabit_nominals_negotiate_a_gigabit_but_force_nothing(self):
        """Negociable y forzable divergen, y el enlace Gigabit es el caso claro."""
        decision = LinkPerformancePlanner().plan(_ethernet(
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_3560_GIGABIT_LINK_MODE,
        ))

        assert decision.nominal_link_ceiling_bps == 1_000_000_000
        assert decision.auto_negotiable_ceiling_bps == 1_000_000_000
        assert decision.forceable_speed_ceiling_bps is None

    def test_a_hundred_megabit_request_on_a_gigabit_link_is_refused(self):
        """El sobreclaim que 3A3-B dejaba pasar: prometer 100 sobre 1 Gbps."""
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.FULL,
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_2911_GIGABIT_LINK_MODE,
        ))

        assert not decision.applicable
        assert LinkPerformanceIssueCode.LINK_MODE_NOT_VERIFIED.value in _codes(decision)
        assert "negotiates 1000000000 bps" in decision.issues[0].message

    def test_a_request_the_link_already_negotiates_is_met_without_forcing(self):
        """Se satisface, pero se dice como: negociando, no forzando."""
        decision = LinkPerformancePlanner().plan(_ethernet(
            requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.FULL,
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert decision.applicable
        assert decision.speed_forced is False
        assert decision.selection_reason == "REQUESTED_SPEED_MET_BY_NEGOTIATION_NOT_FORCED"
        assert any("no speed command is emitted" in w for w in decision.warnings)

    def test_an_asymmetric_link_is_reported_without_blocking(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))

        assert decision.applicable
        assert any("asymmetric" in warning for warning in decision.warnings)

    def test_demand_beyond_the_nominal_ceiling_is_caught_under_autonegotiation(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
            traffic=[TrafficContribution(
                source_id="floor", per_unit_bps=8_000_000, units=25,
            )],
        ))

        assert LinkPerformanceIssueCode.LINK_CAPACITY_INSUFFICIENT.value in _codes(decision)


class TestObservedCapacityIsInferredNotRead:
    def test_the_effective_capacity_needs_the_bandwidth_to_still_mirror_the_link(self):
        forced = ObservedLinkPerformance(
            link_id="hq-core", routing_bandwidth_kbps=5_000,
            bandwidth_autonegotiated=False, line_protocol_up=True, observed=True,
        )

        assert forced.effective_capacity_bps is None

    def test_a_platform_tracked_bandwidth_yields_the_effective_capacity(self):
        observed = ObservedLinkPerformance(
            link_id="hq-core", routing_bandwidth_kbps=100_000,
            bandwidth_autonegotiated=True, line_protocol_up=True, observed=True,
            bandwidth_provenance=BandwidthProvenance.PLATFORM_TRACKED,
        )

        assert observed.effective_capacity_bps == 100_000_000

    def test_autonegotiation_alone_is_not_enough_without_a_measured_profile(self):
        """Que otro backend derive el BW de la negociacion no dice nada de este."""
        observed = ObservedLinkPerformance.from_runtime(
            "hq-core", capability=None,
            routing_bandwidth_kbps=100_000, bandwidth_autonegotiated=True,
            line_protocol_up=True,
        )

        assert observed.bandwidth_provenance is BandwidthProvenance.UNKNOWN
        assert observed.effective_capacity_bps is None

    def test_a_measured_profile_promotes_the_reading_to_platform_tracked(self):
        observed = ObservedLinkPerformance.from_runtime(
            "hq-core", capability=PT_2911_GIGABIT_LINK_MODE,
            routing_bandwidth_kbps=1_000_000, bandwidth_autonegotiated=True,
            line_protocol_up=True,
        )

        assert observed.bandwidth_provenance is BandwidthProvenance.PLATFORM_TRACKED
        assert observed.effective_capacity_bps == 1_000_000_000

    def test_an_explicitly_configured_bandwidth_is_never_read_as_capacity(self):
        """`bandwidth 5000` sobre un enlace de 1 Gbps no son 5 Mbps."""
        observed = ObservedLinkPerformance.from_runtime(
            "hq-core", capability=PT_2911_GIGABIT_LINK_MODE,
            routing_bandwidth_kbps=5_000, bandwidth_autonegotiated=False,
            line_protocol_up=True,
        )

        assert observed.bandwidth_provenance is BandwidthProvenance.EXPLICITLY_CONFIGURED
        assert observed.effective_capacity_bps is None

    def test_a_down_link_yields_no_effective_capacity(self):
        observed = ObservedLinkPerformance(
            link_id="hq-core", routing_bandwidth_kbps=1_000_000,
            bandwidth_autonegotiated=True, line_protocol_up=False, observed=True,
        )

        assert observed.effective_capacity_bps is None


class TestRuntimeShortfallIsNotAnApplyFailure:
    def test_negotiating_below_the_requirement_is_its_own_issue(self):
        decision = LinkPerformancePlanner().plan(_ethernet())
        observed = ObservedLinkPerformance(
            link_id=decision.link_id, routing_bandwidth_kbps=100_000,
            bandwidth_autonegotiated=True, line_protocol_up=True, observed=True,
            bandwidth_provenance=BandwidthProvenance.PLATFORM_TRACKED,
        )

        issues = LinkPerformancePlanner.verify_observed_capacity(
            decision, observed, minimum_capacity_bps=1_000_000_000,
        )

        assert [issue.code for issue in issues] == [
            LinkPerformanceIssueCode.LINK_CAPACITY_BELOW_REQUIREMENT,
        ]

    def test_meeting_the_requirement_raises_nothing(self):
        decision = LinkPerformancePlanner().plan(_ethernet())
        observed = ObservedLinkPerformance(
            link_id=decision.link_id, routing_bandwidth_kbps=1_000_000,
            bandwidth_autonegotiated=True, line_protocol_up=True, observed=True,
            bandwidth_provenance=BandwidthProvenance.PLATFORM_TRACKED,
        )

        assert LinkPerformancePlanner.verify_observed_capacity(
            decision, observed, minimum_capacity_bps=1_000_000_000,
        ) == []

    def test_insufficient_evidence_is_not_reported_as_a_shortfall(self):
        decision = LinkPerformancePlanner().plan(_ethernet())
        observed = ObservedLinkPerformance(link_id=decision.link_id, observed=False)

        assert LinkPerformancePlanner.verify_observed_capacity(
            decision, observed, minimum_capacity_bps=1_000_000_000,
        ) == []


class TestCapabilityLookupLivesOutsideTheDomain:
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
        assert link_mode_capability_for("2950-24", "FastEthernet0/1") is None

    def test_a_different_backend_version_does_not_inherit_the_profile(self):
        assert link_mode_capability_for(
            "3560-24PS", "FastEthernet0/1", backend_version="8.2.0",
        ) is None


class TestPolicyIdentityMovedWithTheBehaviour:
    def test_the_policy_version_records_the_new_ethernet_rules(self):
        assert LinkPerformancePlanner().plan(_ethernet()).policy_version == "4"

    def test_the_three_ceilings_travel_in_the_explanation(self):
        decision = LinkPerformancePlanner().plan(_ethernet(
            local_port_capability=PT_2911_GIGABIT_LINK_MODE,
            peer_port_capability=PT_3560_FASTETHERNET_LINK_MODE,
        ))
        explained = decision.explain()

        assert explained["nominal_link_ceiling_bps"] == 100_000_000
        assert explained["auto_negotiable_ceiling_bps"] == 100_000_000
        assert explained["forceable_speed_ceiling_bps"] is None
