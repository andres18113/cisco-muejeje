"""Stage 3A4 MEG-5 — la referencia de 41 dispositivos ya no la rechaza ningun gate.

MEG-5 no es "la corrida 41/41". Es la condicion que la hacia imposible, y el
registro gobernado la enuncia dos veces:

  * `TD-CATALOG-PORT-001`: *"MEG-5 cannot open on the 41-device reference until
    `2960-24TT` -- and any other model that run selects -- has a measured port
    inventory for the build it will run against."*
  * `TD-CONFIG-CAPABILITY-001`: *"Qualificar los modelos de la topologia de
    referencia pertenece a la pasada pre-MEG-5"*, y *"la referencia de 41
    dispositivos toparia con el mismo gate en su primera accion VLAN"*.

La seleccion por capacidades elige `1941`, `2950T-24`, `IE-2000` y `PC-PT` --
no el `2960-24TT` que la referencia fijada a mano usa. Estos tests fijan que los
cuatro tienen la evidencia que cada gate exige, medida en la build contra la que
correria, y que **ningun gate se relajo** para conseguirlo.

Lo que estos tests NO afirman: que la corrida 41/41 pase. No se ha ejecutado.
Autorizar y funcionar son cosas distintas, y esa es la misma distincion que
`ROUTING_BEHAVIOR` lleva desde R3.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from src.packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    _port_evidence_errors,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneCapabilityDimension,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    SecurityCapabilityStatus,
)
from src.packet_tracer_mcp.infrastructure.catalog.control_plane_capabilities import (
    packet_tracer_control_plane_capabilities,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    backend_verified_port_inventory,
)
from src.packet_tracer_mcp.domain.enterprise.models.port_inventory import (
    PortInventoryEvidenceTier,
)

from test_enterprise_reference_composition import _intent

BUILD = "9.0.1.0858"
FINGERPRINT = EnvironmentFingerprint(
    backend="packet_tracer", backend_version=BUILD,
    bridge_transport="file", extension_version="script-engine",
    runtime_mode="logical-workspace",
)


def _reference():
    composed = compose_enterprise_reference(_intent(), packet_tracer_version=BUILD)
    assert composed.valid, composed.issues
    return composed


def _selected_models() -> set[str]:
    return {device.model for device in _reference().topology.devices}


class TestTheShapeIsStillTheGovernedOne:
    def test_the_reference_is_still_41_devices_and_41_links(self):
        topology = _reference().topology

        assert len(topology.devices) == 41
        assert len(topology.links) == 41

    def test_selection_picks_the_models_this_qualification_measured(self):
        """Si la seleccion cambia, la cualificacion deja de cubrir la corrida."""
        assert _selected_models() == {"1941", "2950T-24", "IE-2000", "PC-PT"}


class TestThePortEvidenceGateNoLongerRefusesIt:
    def test_the_reference_draws_no_port_evidence_refusal(self):
        topology = _reference().topology

        errors = _port_evidence_errors(
            topology,
            environment_fingerprint=FINGERPRINT,
            port_inventory=backend_verified_port_inventory,
        )

        assert errors == []

    def test_every_selected_model_is_backend_verified_on_this_build(self):
        for model in sorted(_selected_models()):
            resolution = backend_verified_port_inventory(model, backend_version=BUILD)
            assert resolution.tier is PortInventoryEvidenceTier.BACKEND_VERIFIED, model

    def test_the_router_is_authorised_in_the_module_state_it_deploys_in(self):
        """La referencia inserta HWIC-2T en `0/0`; sin tarjeta no hay Serial."""
        topology = _reference().topology
        assert {(item.module, item.slot) for item in topology.modules} == {
            ("HWIC-2T", "0/0"),
        }

        carded = backend_verified_port_inventory(
            "1941", backend_version=BUILD, installed_modules=["HWIC-2T@0/0"],
        )
        bare = backend_verified_port_inventory("1941", backend_version=BUILD)

        assert carded.permits(["Serial0/0/0", "Serial0/0/1"]) is True
        assert bare.permits(["Serial0/0/0"]) is False

    def test_the_gate_itself_was_not_relaxed(self):
        """Un modelo sin medir sigue siendo rechazado por el mismo predicado."""
        resolution = backend_verified_port_inventory("2901", backend_version=BUILD)

        assert resolution.tier is PortInventoryEvidenceTier.UNKNOWN
        assert resolution.permits(["GigabitEthernet0/0"]) is False


class TestTheCapabilityGatesNoLongerRefuseIt:
    @pytest.mark.parametrize("model,capability", [
        ("1941", "layer3"),
        ("2950T-24", "supports_vlan"),
        ("IE-2000", "supports_vlan"),
    ])
    def test_the_e5_capabilities_the_reference_requires_are_supported(
        self, model, capability,
    ):
        capabilities = _reference().capabilities
        profile = capabilities.get(model)

        assert profile is not None, model
        assert getattr(profile, capability).value == "supported"

    @pytest.mark.parametrize("dimension", [
        ControlPlaneCapabilityDimension.RIPV2_CONFIG,
        ControlPlaneCapabilityDimension.ROUTING_PROCESS_STATE,
        ControlPlaneCapabilityDimension.ROUTING_ROUTE_STATE,
        ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR,
    ])
    def test_the_e9_dimensions_the_reference_requires_are_supported_on_1941(
        self, dimension,
    ):
        profile = packet_tracer_control_plane_capabilities(BUILD)["1941"]

        assert profile.status(dimension) is SecurityCapabilityStatus.SUPPORTED

    def test_the_1941_profile_names_its_own_measurement(self):
        """No hereda del 2911: la evidencia es suya y lo dice."""
        profile = packet_tracer_control_plane_capabilities(BUILD)["1941"]

        assert "R4" in profile.evidence_source
        assert "1941" in profile.evidence_source

    def test_a_model_with_no_measurement_still_gets_no_profile(self):
        assert "2901" not in packet_tracer_control_plane_capabilities(BUILD)


class TestWhatThisDoesNotClaim:
    def test_the_reference_run_itself_is_not_asserted_here(self):
        """Autorizar no es funcionar, y nada de este archivo ejecuta la corrida.

        Si algun dia este archivo despliega los 41 dispositivos, deja de ser una
        prueba de la CONDICION de MEG-5 y pasa a ser la corrida de referencia,
        que es otra cosa y tiene su propio registro.
        """
        import sys

        namespace = vars(sys.modules[__name__])

        # Nada que pueda mutar Packet Tracer esta al alcance de este modulo:
        # se comprueba sobre el espacio de nombres, no sobre el texto, para que
        # nombrarlo en un comentario no baste para pasar ni para fallar.
        for forbidden in (
            "execute_enterprise_reference",
            "EnterprisePhysicalTopologyDeployer",
            "PacketTracerPhysicalTopologyRuntime",
            "PortInventoryQualifier",
        ):
            assert forbidden not in namespace

    def test_unmeasured_models_stay_unknown_everywhere(self):
        """La cualificacion no se derramo sobre el resto del catalogo."""
        for model in ("2901", "2620XM", "Server-PT"):
            assert backend_verified_port_inventory(
                model, backend_version=BUILD,
            ).tier is PortInventoryEvidenceTier.UNKNOWN
