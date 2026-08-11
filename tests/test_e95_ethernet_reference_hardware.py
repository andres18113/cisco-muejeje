"""El hardware que la referencia usa de verdad, y el CLI que llega a emitirse.

Stage 3A3-B midio 2911 y 3560-24PS y dio Ethernet por cubierto. El
EnterprisePlan de referencia no usa ninguno de los dos: conmuta con 2960-24TT,
seis unidades, y sus enlaces entre switches son Fa<->Gig y Gig<->Gig. La
cobertura real era cero.

Aparte, las tres acciones de rendimiento de enlace no estaban en la lista
blanca del renderer de configuracion, asi que un reloj serial o un modo
Ethernet compilaban y no producian una sola linea de CLI. Se comprueba aqui
porque un descarte silencioso no falla por si solo en ninguna otra parte.
"""

from __future__ import annotations

import collections

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigureEthernetLinkMode,
    ConfigureInterfaceBandwidth,
    ConfigureSerialClock,
)
from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
    DuplexMode,
    LinkModeContext,
    LinkSpeedMode,
)
from src.packet_tracer_mcp.infrastructure.catalog.link_mode_capabilities import (
    PT_2960_FASTETHERNET_LINK_MODE,
    PT_2960_GIGABIT_LINK_MODE,
    link_mode_capability_for,
)
from src.packet_tracer_mcp.infrastructure.generator.configuration_renderer import (
    PacketTracerIosRenderer,
)


@pytest.fixture(scope="module")
def reference_topology():
    from tests.test_enterprise_compiler import _reference

    _plan, _hardware, result = _reference()
    return result.plan


class TestTheReferenceUsesHardwareWeMeasured:
    def test_the_reference_switches_are_2960s(self, reference_topology):
        models = collections.Counter(
            device.model for device in reference_topology.devices
        )

        assert models["2960-24TT"] == 6
        assert models["3560-24PS"] == 0
        assert models["3650-24PS"] == 0

    def test_every_switch_to_switch_link_resolves_to_a_measured_profile(
        self, reference_topology,
    ):
        """El hueco que 3A3-B no vio: sin perfil, la politica no decide nada."""
        models = {d.name: d.model for d in reference_topology.devices}
        unresolved = []
        for link in reference_topology.links:
            for device, port in (
                (link.device_a, link.port_a), (link.device_b, link.port_b),
            ):
                model = models.get(device, "")
                if model != "2960-24TT":
                    continue
                if link_mode_capability_for(model, port) is None:
                    unresolved.append(f"{model} {port}")

        assert unresolved == [], f"Reference endpoints without a profile: {set(unresolved)}"

    def test_both_reference_port_classes_are_covered(self):
        assert link_mode_capability_for("2960-24TT", "FastEthernet0/1") is not None
        assert link_mode_capability_for("2960-24TT", "GigabitEthernet0/1") is not None


class TestWhatWasMeasuredOnTheReferenceSwitch:
    def test_autonegotiation_was_observed_on_both_port_classes(self):
        assert PT_2960_FASTETHERNET_LINK_MODE.autonegotiation_observed()
        assert PT_2960_GIGABIT_LINK_MODE.autonegotiation_observed()

    def test_the_bandwidth_reading_is_scoped_to_what_was_correlated(self):
        assert PT_2960_FASTETHERNET_LINK_MODE.bandwidth_tracks_negotiated_capacity
        assert PT_2960_GIGABIT_LINK_MODE.bandwidth_tracks_negotiated_capacity

    def test_no_speed_is_forceable_on_the_reference_switch(self):
        """Medido en los dos sentidos: `speed 100` en Gig y `speed 10` en Fa."""
        for speed in (LinkSpeedMode.SPEED_10M, LinkSpeedMode.SPEED_100M,
                      LinkSpeedMode.SPEED_1G):
            assert not PT_2960_GIGABIT_LINK_MODE.speed_is_forceable(speed)
            assert not PT_2960_FASTETHERNET_LINK_MODE.speed_is_forceable(speed)

    def test_full_duplex_is_forceable_on_both_port_classes(self):
        for capability in (PT_2960_FASTETHERNET_LINK_MODE, PT_2960_GIGABIT_LINK_MODE):
            observation = capability.observation_for(
                LinkSpeedMode.AUTO, DuplexMode.FULL, LinkModeContext.LINKED,
            )

            assert observation is not None
            assert observation.evidence.verifies_claim

    def test_half_duplex_is_refused_on_the_gigabit_uplink_with_its_condition(self):
        observation = PT_2960_GIGABIT_LINK_MODE.observation_for(
            LinkSpeedMode.AUTO, DuplexMode.HALF, LinkModeContext.LINKED,
        )

        assert "1Gbps" in observation.prerequisite

    def test_neither_profile_claims_a_complete_enumeration(self):
        assert not PT_2960_FASTETHERNET_LINK_MODE.enumeration_complete
        assert not PT_2960_GIGABIT_LINK_MODE.enumeration_complete


def _action(kind):
    common = dict(
        id="a1", phase=ConfigurationPhase.L2_INTERFACES,
        device_id="d", device_name="SW1", site_id="hq",
    )
    if kind == "clock":
        return ConfigureSerialClock(
            **common, interface="Serial0/0/0", clock_rate_bps=2_000_000)
    if kind == "bandwidth":
        return ConfigureInterfaceBandwidth(
            **common, interface="Serial0/0/0", bandwidth_kbps=2000)
    return ConfigureEthernetLinkMode(
        **common, interface="GigabitEthernet0/1", speed="auto", duplex="full")


class TestTheRendererNoLongerDropsLinkPerformanceSilently:
    """El fallo era mudo: compilaba, validaba y no emitia nada."""

    @pytest.mark.parametrize("kind, expected", [
        ("clock", " clock rate 2000000"),
        ("bandwidth", " bandwidth 2000"),
        ("link_mode", " duplex full"),
    ])
    def test_each_link_performance_action_reaches_the_cli(self, kind, expected):
        batches = PacketTracerIosRenderer().render_device_batches(
            "SW1", "2960-24TT", [_action(kind)],
        )

        assert batches, f"{kind} produced no batch at all"
        assert expected in batches[0].ios_payload

    def test_the_serial_clock_regression_was_shared_not_ethernet_only(self):
        """Serial se tocaba aqui por la misma lista blanca, no por otra causa."""
        batches = PacketTracerIosRenderer().render_device_batches(
            "R1", "2911", [_action("clock"), _action("bandwidth")],
        )

        payload = "\n".join(batch.ios_payload for batch in batches)
        assert "clock rate 2000000" in payload
        assert "bandwidth 2000" in payload

    def test_an_autonegotiated_mode_still_emits_nothing(self):
        """No forzar nada sigue significando no escribir nada."""
        auto = ConfigureEthernetLinkMode(
            id="a1", phase=ConfigurationPhase.L2_INTERFACES,
            device_id="d", device_name="SW1", site_id="hq",
            interface="GigabitEthernet0/1", speed="auto", duplex="auto",
        )

        assert PacketTracerIosRenderer().render_device_batches(
            "SW1", "2960-24TT", [auto],
        ) == []
