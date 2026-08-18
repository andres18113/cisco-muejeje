"""Preferencia de modelo: desempata entre viables, nunca habilita a un inviable.

Por que existe. La seleccion por capacidad elige del catalogo completo, y para la
forma acotada de Stage 3A4 elige `1941`. El catalogo de capacidades de plano de
control solo tiene evidencia en vivo para `2911`, asi que RIPv2 sobre 1941 es
UNKNOWN y el compilador se niega -- correctamente. La corrida en vivo necesita
poder pedir 2911.

La linea que estos tests defienden es exactamente donde esta el riesgo: una
preferencia es un DESEMPATE entre candidatos ya viables. Si pudiera ascender a
uno que no cumple, seria la excepcion por nombre de modelo que TD-HARDWARE-001
prohibe, con otro nombre.
"""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from src.packet_tracer_mcp.application.use_cases.plan_enterprise_hardware import (
    plan_enterprise_hardware,
)
from src.packet_tracer_mcp.domain.enterprise.models.intent import (
    EnterpriseIntent,
    SiteIntent,
    SiteType,
)
from src.packet_tracer_mcp.domain.enterprise.models.link_performance import LinkMedia
from src.packet_tracer_mcp.domain.enterprise.models.requirements import (
    EndpointRequirement,
    WanLinkRequirement,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.domain.enterprise.services.hardware_planner import (
    HardwarePlanningPolicy,
)


def _enterprise():
    intent = EnterpriseIntent(
        name="Bounded serial slice",
        address_space="10.0.0.0/8",
        default_growth_percent=0,
        internet_required=True,
        sites=[
            SiteIntent(
                name="A", type=SiteType.HQ,
                endpoints=[EndpointRequirement(role=DeviceRole.USER_PC, count=2)],
                uplinks=[WanLinkRequirement(target_site_id="b", media=LinkMedia.SERIAL)],
            ),
            SiteIntent(
                name="B", type=SiteType.BRANCH,
                endpoints=[EndpointRequirement(role=DeviceRole.USER_PC, count=2)],
                uplinks=[WanLinkRequirement(target_site_id="a", media=LinkMedia.SERIAL)],
            ),
        ],
    )
    result = EnterpriseDesigner().design(intent)
    assert result.validation.is_valid and result.plan is not None
    return result.plan


def _composed_with_control_plane(*, policy):
    """Compone hasta E9 usando el manifiesto orientado del gate adversarial."""
    from tests.test_stage3a4_offline_adversarial_matrix import (
        _bounded_intent,
        _control_plane_intent,
        _oriented_manifest_for,
    )

    intent = _bounded_intent()
    # La version entra en las DOS composiciones. Desde el contrato de evidencia
    # de puertos, el build es una entrada de la composicion -- un modelo con
    # inventario medido se planifica con los nombres observados -- asi que
    # componer una vez sin version y otra con ella produce dos topologias
    # distintas y un manifiesto que no corresponde.
    topology = compose_enterprise_reference(
        intent, policy=policy, packet_tracer_version="9.0.1.0858",
    ).topology
    return compose_enterprise_reference(
        intent,
        policy=policy,
        deployment_manifest=_oriented_manifest_for(topology),
        control_plane_intent=_control_plane_intent(topology),
        packet_tracer_version="9.0.1.0858",
    )


def _router_models(composition) -> set[str]:
    return {
        device.selected_model or device.provisional_model
        for site in composition.plan.site_hardware
        for device in site.devices
        if device.role in {DeviceRole.EDGE_ROUTER, DeviceRole.WAN_ROUTER}
    }


class TestPreferenceSteersAmongViableCandidates:
    def test_without_a_preference_the_catalogue_decides(self):
        """Se fija el punto de partida: sin preferencia NO sale 2911."""
        composition = plan_enterprise_hardware(_enterprise())

        assert _router_models(composition) == {"1941"}

    def test_a_preferred_router_model_is_selected_when_it_is_viable(self):
        composition = plan_enterprise_hardware(
            _enterprise(),
            policy=HardwarePlanningPolicy(preferred_router_model="2911"),
        )

        assert _router_models(composition) == {"2911"}

    def test_the_preference_is_case_insensitive_like_every_other_model_match(self):
        composition = plan_enterprise_hardware(
            _enterprise(),
            policy=HardwarePlanningPolicy(preferred_router_model="2911 "),
        )

        assert _router_models(composition) == {"2911"}


class TestPreferenceNeverOverridesEligibility:
    def test_an_unknown_model_name_changes_nothing(self):
        """Un nombre que no existe no puede vaciar la seleccion ni romperla."""
        baseline = plan_enterprise_hardware(_enterprise())

        preferred = plan_enterprise_hardware(
            _enterprise(),
            policy=HardwarePlanningPolicy(preferred_router_model="NOT-A-MODEL"),
        )

        assert _router_models(preferred) == _router_models(baseline)
        assert preferred.plan.status is baseline.plan.status

    def test_a_switch_model_is_never_promoted_into_a_router_slot(self):
        """La preferencia se aplica DESPUES de filtrar viabilidad, no antes.

        Si se aplicara antes, pedir un switch como router lo colaria: es la
        forma exacta que tendria la excepcion por nombre de modelo prohibida.
        """
        composition = plan_enterprise_hardware(
            _enterprise(),
            policy=HardwarePlanningPolicy(preferred_router_model="2960-24TT"),
        )

        assert "2960-24TT" not in _router_models(composition)
        assert _router_models(composition) == {"1941"}

    def test_preference_does_not_disturb_switch_selection(self):
        baseline = plan_enterprise_hardware(_enterprise())

        preferred = plan_enterprise_hardware(
            _enterprise(),
            policy=HardwarePlanningPolicy(preferred_router_model="2911"),
        )

        def switches(composition):
            return {
                device.selected_model or device.provisional_model
                for site in composition.plan.site_hardware
                for device in site.devices
                if device.role is DeviceRole.ACCESS_SWITCH
            }

        assert switches(preferred) == switches(baseline)


class TestSteeringIsWhatTheLiveGateNeeds:
    """Por que importa el modelo, medido y no supuesto.

    Correccion sobre una lectura previa: la COMPILACION del plano de control no
    depende del modelo -- 1941 y 2911 compilan igual. Donde el modelo decide es
    en la evidencia de capacidad, y esa se consulta al APLICAR. El catalogo de
    capacidades de plano de control tiene evidencia en vivo unicamente para
    2911, asi que la corrida en vivo debe dirigirse a ese modelo.
    """

    def test_both_models_compile_the_same_control_plane_shape(self):
        default = _composed_with_control_plane(policy=None)
        steered = _composed_with_control_plane(
            policy=HardwarePlanningPolicy(preferred_router_model="2911"),
        )

        assert default.valid and steered.valid
        assert default.control_plane is not None
        assert steered.control_plane is not None
        assert len(default.control_plane.actions) == len(steered.control_plane.actions)

    def test_the_only_router_with_live_control_plane_evidence_is_the_steered_one(self):
        """El catalogo tambien perfila un switch; lo que importa es el router.

        Si algun dia se mide otro router, esto falla y hay que decidir a
        proposito si la corrida en vivo cambia de modelo.
        """
        from src.packet_tracer_mcp.infrastructure.catalog.control_plane_capabilities import (
            packet_tracer_control_plane_capabilities,
        )

        profiled = set(packet_tracer_control_plane_capabilities())

        assert "2911" in profiled
        assert "1941" not in profiled, (
            "1941 gained a control-plane profile; the steering rationale changed"
        )

    def test_steering_selects_the_model_that_has_that_evidence(self):
        composed = _composed_with_control_plane(
            policy=HardwarePlanningPolicy(preferred_router_model="2911"),
        )

        assert {
            item.model for item in composed.topology.devices
            if item.category == "router"
        } == {"2911"}


class TestTheSteeringIsDataNotACodeException:
    def test_the_policy_default_prefers_nothing(self):
        """Por defecto no hay modelo privilegiado en ningun lado."""
        assert HardwarePlanningPolicy().preferred_router_model == ""

    def test_planning_still_carries_no_model_name_literal(self):
        """La preferencia entra como dato del llamador, no como constante.

        Espejo del guard de `test_enterprise_hardware_composition`: si esta
        funcion se hubiera implementado escribiendo "2911" dentro del
        planificador, aquel test fallaria. Aqui se deja explicito el porque.
        """
        import pathlib
        import re

        planner = (
            pathlib.Path(__file__).resolve().parents[1]
            / "src" / "packet_tracer_mcp" / "domain" / "enterprise" / "services"
            / "hardware_planner.py"
        )
        forbidden = re.compile(r"""["'](?:\d{4}(?:-\d+[A-Z]{2,})?|ISR\d{4})["']""")

        assert not forbidden.findall(planner.read_text(encoding="utf-8"))
