"""La mitad determinista del producto, como una sola funcion de produccion.

Hasta ahora la cadena E4 -> hardware -> E5 -> trafico solo existia ensamblada a
mano dentro de tests. Estos fijan que la funcion productiva produce la forma de
referencia gobernada -- 41 dispositivos, 41 enlaces, tres seriales -- partiendo
de un intent semantico y eligiendo hardware por catalogo, sin candidatos fijados
a mano.

Que NO se fija aqui: los hashes de `test_e95_reference_regression.py`. Esa
referencia fija sus candidatos deliberadamente y sigue siendo la pinza de
determinismo. Esta composicion elige entre todo el catalogo, que es justamente
la diferencia, y duplicar alli sus hashes ataria dos cosas que deben poder
moverse por separado.
"""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from src.packet_tracer_mcp.domain.enterprise.models.link_performance import TrafficFlowIntent
from tests.test_e95_serial_product_planning import _reference_planning_intent


def _intent(**overrides):
    base = {
        "address_space": "10.0.0.0/8",
        "traffic_flows": [
            TrafficFlowIntent(
                id="flow/a-to-c", source_site_id="a",
                destination_site_id="c", per_unit_bps=100_000,
            ),
        ],
    }
    base.update(overrides)
    return _reference_planning_intent().model_copy(update=base)


class TestTheProductionCompositionReproducesTheGovernedShape:
    def test_it_produces_41_devices_and_41_links_from_a_semantic_intent(self):
        composed = compose_enterprise_reference(_intent())

        assert composed.valid, composed.issues
        assert len(composed.topology.devices) == 41
        assert len(composed.topology.links) == 41

    def test_it_produces_exactly_three_serial_wan_links(self):
        """Serial llega por media del requisito WAN, no por `CABLE_RULES`."""
        composed = compose_enterprise_reference(_intent())

        serial = [item for item in composed.topology.links if item.cable == "serial"]

        assert len(serial) == 3

    def test_hardware_selection_runs_through_the_capability_consumer(self):
        composed = compose_enterprise_reference(_intent())

        assert composed.hardware is not None
        assert composed.hardware.switch_candidates
        assert composed.hardware.router_candidates
        assert composed.hardware_plan is composed.hardware.plan

    def test_a_declared_flow_is_attributed_to_one_unambiguous_serial_path(self):
        composed = compose_enterprise_reference(_intent())

        path = composed.traffic.paths_by_flow["flow/a-to-c"]

        assert len(path) == 1
        assert path[0] in {item.id for item in composed.topology.links if item.cable == "serial"}

    def test_the_same_intent_composes_to_the_same_physical_identity(self):
        first = compose_enterprise_reference(_intent())
        second = compose_enterprise_reference(_intent())

        assert first.topology.physical_identity_hash
        assert (
            first.topology.physical_identity_hash
            == second.topology.physical_identity_hash
        )


class TestItStopsWhereTheEvidenceStops:
    def test_without_a_manifest_it_stops_before_configuration(self):
        """La orientacion DCE/DTE la decide el cable; sin leerla no hay reloj."""
        composed = compose_enterprise_reference(_intent())

        assert composed.valid
        assert composed.configuration is None
        assert composed.control_plane is None

    def test_a_flow_naming_an_unknown_site_fails_closed_at_attribution(self):
        """Se detiene en trafico, con la topologia ya compilada y sin configurar."""
        composed = compose_enterprise_reference(_intent(traffic_flows=[
            TrafficFlowIntent(
                id="flow/a-to-nowhere", source_site_id="a",
                destination_site_id="site-that-does-not-exist", per_unit_bps=1_000,
            ),
        ]))

        assert not composed.valid
        assert composed.topology is not None
        assert composed.traffic is not None and not composed.traffic.is_valid
        assert any(issue.startswith("traffic:") for issue in composed.issues)
        assert composed.configuration is None

    def test_a_site_less_intent_is_rejected_by_e5_not_by_e4(self):
        """Medido, no supuesto: E4 valida un intent sin sitios y E5 lo rechaza.

        El diseno no falla -- produce un plan vacio, y el planificador fisico lo
        deja UNRESOLVED. Quien corta es la compilacion E5, que se niega a
        construir una topologia sobre hardware sin evidencia suficiente. Se fija
        asi para que el dia que la validacion se mueva de capa se note.
        """
        composed = compose_enterprise_reference(
            _reference_planning_intent().model_copy(update={"sites": []}),
        )

        assert not composed.valid
        assert composed.enterprise is not None
        assert composed.topology is None
        assert all(issue.startswith("E5 compile") for issue in composed.issues)


class TestTheSummaryIsHonest:
    def test_the_compact_summary_reports_what_was_composed(self):
        composed = compose_enterprise_reference(_intent())

        summary = composed.compact_summary()

        assert summary["valid"] is True
        assert summary["devices"] == 41
        assert summary["links"] == 41
        assert summary["sites"] == 3
        assert summary["physical_topology_hash"]
        # No se compilo configuracion, y el resumen no puede insinuar que si.
        assert summary["configuration_actions"] == 0
        assert summary["control_plane_actions"] == 0
