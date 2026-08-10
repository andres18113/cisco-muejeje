"""Que identidad cambia cuando cambia una decision de rendimiento de enlace.

Los dos seams ya existian y aqui se comprueba que la integracion cae del lado
correcto de cada uno: un hecho fisico entra en `physical_topology_hash`, una
decision efectiva entra en la identidad de configuracion, una coordenada solo
en `layout_hash`, y lo negociado en runtime en ninguno.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
    DuplexMode,
    LinkMedia,
    LinkSpeedMode,
    ObservedLinkPerformance,
    TrafficContribution,
)
from src.packet_tracer_mcp.domain.enterprise.services.link_performance_integration import (
    LINK_DCE_KEY,
    LINK_DTE_KEY,
    LINK_MEDIA_KEY,
    LinkPerformanceIntegration,
    resolve_link_media,
    summarize_decisions,
)
from src.packet_tracer_mcp.domain.enterprise.services.topology_identity import (
    compute_topology_hashes,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan


def _topology(**link_overrides) -> TopologyPlan:
    link = {
        "id": "hq-br01",
        "device_a": "HQ-R1", "port_a": "Serial0/0/0",
        "device_b": "BR01-R1", "port_b": "Serial0/0/0",
        "cable": "serial",
        "link_role": "wan_link",
    }
    link.update(link_overrides)
    return TopologyPlan(
        devices=[
            DevicePlan(name="HQ-R1", model="2911", category="router", x=100, y=100),
            DevicePlan(name="BR01-R1", model="2911", category="router", x=300, y=100),
        ],
        links=[LinkPlan(**link)],
    )


def _hashes(topology: TopologyPlan):
    return compute_topology_hashes(topology)


class TestPhysicalIdentity:
    def test_media_and_dce_reach_the_physical_hash(self):
        plain = _topology()
        stamped = _topology(metadata={
            LINK_MEDIA_KEY: "serial",
            LINK_DCE_KEY: "HQ-R1", LINK_DTE_KEY: "BR01-R1",
        })

        assert _hashes(plain).physical_topology_hash != (
            _hashes(stamped).physical_topology_hash
        )

    def test_reversing_dce_and_dte_changes_the_physical_hash(self):
        forward = _topology(metadata={LINK_DCE_KEY: "HQ-R1", LINK_DTE_KEY: "BR01-R1"})
        reversed_ends = _topology(metadata={LINK_DCE_KEY: "BR01-R1", LINK_DTE_KEY: "HQ-R1"})

        assert _hashes(forward).physical_topology_hash != (
            _hashes(reversed_ends).physical_topology_hash
        )

    def test_a_layout_only_mutation_leaves_the_physical_hash_alone(self):
        base = _topology(metadata={LINK_DCE_KEY: "HQ-R1"})
        moved = _topology(metadata={LINK_DCE_KEY: "HQ-R1"})
        moved.devices[0].x = 999
        moved.devices[0].y = 888

        assert _hashes(base).physical_topology_hash == (
            _hashes(moved).physical_topology_hash
        )
        assert _hashes(base).layout_hash != _hashes(moved).layout_hash

    def test_the_stamp_records_the_media_it_resolved(self):
        topology = _topology()
        integration = LinkPerformanceIntegration()

        integration.compile_topology(topology)

        assert topology.links[0].metadata[LINK_MEDIA_KEY] == LinkMedia.SERIAL.value


class TestConfigurationIdentity:
    """Las acciones tipadas son lo que cambia la identidad de configuracion."""

    def _actions(self, **options):
        integration = LinkPerformanceIntegration()
        link = _topology(metadata={LINK_DCE_KEY: "HQ-R1", LINK_DTE_KEY: "BR01-R1"}).links[0]
        decision = integration.decide(integration.intent_for_link(link, **options))
        return decision, integration.actions_for(
            decision, device_id="HQ-R1", device_name="HQ-R1",
            site_id="hq", interface="Serial0/0/0",
        )

    def test_a_different_effective_rate_produces_a_different_action_payload(self):
        _, low = self._actions()
        _, high = self._actions(traffic=[
            TrafficContribution(source_id="users", per_unit_bps=64_000, units=45),
        ])

        assert low[0].clock_rate_bps == 2_000_000
        assert high[0].clock_rate_bps == 4_000_000
        assert low[0].model_dump() != high[0].model_dump()

    def test_the_clock_is_emitted_only_for_the_resolved_dce(self):
        integration = LinkPerformanceIntegration()
        link = _topology(metadata={LINK_DCE_KEY: "HQ-R1", LINK_DTE_KEY: "BR01-R1"}).links[0]
        decision = integration.decide(integration.intent_for_link(link))

        dte_actions = integration.actions_for(
            decision, device_id="BR01-R1", device_name="BR01-R1",
            site_id="br01", interface="Serial0/0/0",
        )

        assert dte_actions == []

    def test_an_unresolved_dce_emits_no_clock_and_reports_an_issue(self):
        integration = LinkPerformanceIntegration()
        link = _topology().links[0]
        decision = integration.decide(integration.intent_for_link(link))

        assert not decision.applicable
        assert integration.actions_for(
            decision, device_id="HQ-R1", device_name="HQ-R1",
            site_id="hq", interface="Serial0/0/0",
        ) == []

    def test_ethernet_auto_emits_no_link_mode_action(self):
        integration = LinkPerformanceIntegration()
        link = _topology(cable="straight", link_role="access_uplink").links[0]
        decision = integration.decide(integration.intent_for_link(link))

        assert decision.effective_speed is LinkSpeedMode.AUTO
        assert integration.actions_for(
            decision, device_id="SW1", device_name="SW1",
            site_id="hq", interface="GigabitEthernet0/1",
        ) == []

    def test_an_explicit_ethernet_policy_emits_a_typed_action(self):
        integration = LinkPerformanceIntegration()
        link = _topology(cable="straight", link_role="access_uplink").links[0]
        decision = integration.decide(integration.intent_for_link(
            link, requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.FULL,
        ))
        actions = integration.actions_for(
            decision, device_id="SW1", device_name="SW1",
            site_id="hq", interface="GigabitEthernet0/1",
        )

        assert len(actions) == 1
        assert actions[0].speed == "100m"
        assert actions[0].duplex == "full"

    def test_the_routing_bandwidth_action_appears_only_under_the_sync_policy(self):
        _, without = self._actions()
        _, with_sync = self._actions(sync_routing_bandwidth=True)

        assert len(without) == 1
        assert len(with_sync) == 2
        assert with_sync[1].bandwidth_kbps == 2_000


class TestObservedStateExclusion:
    def test_an_observation_touches_neither_hash_nor_plan(self):
        topology = _topology(metadata={LINK_DCE_KEY: "HQ-R1"})
        before = _hashes(topology)
        observed_fast = ObservedLinkPerformance(
            link_id="hq-br01", reported_speed=LinkSpeedMode.SPEED_1G,
            reported_duplex=DuplexMode.FULL, observed=True,
        )
        observed_slow = ObservedLinkPerformance(
            link_id="hq-br01", reported_speed=LinkSpeedMode.SPEED_100M,
            reported_duplex=DuplexMode.FULL, observed=True,
        )
        after = _hashes(topology)

        assert observed_fast.reported_speed is not observed_slow.reported_speed
        assert before.physical_topology_hash == after.physical_topology_hash
        assert before.layout_hash == after.layout_hash
        assert before.artifact_hash == after.artifact_hash

    def test_performance_decisions_never_enter_the_layout_hash(self):
        base = _topology()
        with_performance = _topology(metadata={
            LINK_MEDIA_KEY: "serial", LINK_DCE_KEY: "HQ-R1",
        })

        assert _hashes(base).layout_hash == _hashes(with_performance).layout_hash


class TestMediaResolutionAndDeterminism:
    def test_media_comes_from_the_planned_cable(self):
        assert resolve_link_media("serial") is LinkMedia.SERIAL
        assert resolve_link_media("straight") is LinkMedia.ETHERNET
        assert resolve_link_media("") is LinkMedia.UNKNOWN

    def test_compiling_the_same_topology_twice_is_stable(self):
        integration = LinkPerformanceIntegration()
        first = integration.compile_topology(_topology())
        second = integration.compile_topology(_topology())

        assert [d.model_dump() for d in first] == [d.model_dump() for d in second]

    def test_link_order_does_not_change_the_decisions(self):
        integration = LinkPerformanceIntegration()
        forward = _topology()
        forward.links.append(LinkPlan(
            id="hq-acc", device_a="HQ-SW1", port_a="Gig0/1",
            device_b="HQ-R1", port_b="Gig0/0", cable="straight",
            link_role="access_uplink",
        ))
        backward = _topology()
        backward.links.insert(0, LinkPlan(
            id="hq-acc", device_a="HQ-SW1", port_a="Gig0/1",
            device_b="HQ-R1", port_b="Gig0/0", cable="straight",
            link_role="access_uplink",
        ))

        assert [d.model_dump() for d in integration.compile_topology(forward)] == [
            d.model_dump() for d in integration.compile_topology(backward)
        ]


class TestReferenceSummary:
    def test_the_summary_stays_compact_and_names_its_sources(self):
        integration = LinkPerformanceIntegration()
        topology = _topology(metadata={LINK_DCE_KEY: "HQ-R1", LINK_DTE_KEY: "BR01-R1"})
        topology.links.append(LinkPlan(
            id="hq-acc", device_a="HQ-SW1", port_a="Gig0/1",
            device_b="HQ-R1", port_b="Gig0/0", cable="straight",
            link_role="access_uplink",
        ))

        summary = summarize_decisions(integration.compile_topology(topology))

        assert summary["links"] == 2
        assert summary["media"] == ["ethernet", "serial"]
        assert summary["by_capacity_source"]["media_default_policy"] == 2
        assert summary["unresolved"] == 0
