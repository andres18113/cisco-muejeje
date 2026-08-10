"""El reloj serial se resuelve por el manifest, nunca por un nombre suelto.

Observado en vivo sobre PT 9.0.1.0858 con dos 2911 + HWIC-2T: ambos puertos
quedaron enlazados, `getObjectUuid()` coincidio en los dos extremos, y
`show controllers` confirmo A=DCE / B=DTE. Ese identificador de runtime vive
solo en el manifest: un redespliegue del mismo enlace produce otro sin que la
red haya cambiado.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentBinding,
    DeploymentIdentityError,
    DeploymentLinkBinding,
    DeploymentLinkEndpoint,
    DeploymentManifest,
    EnvironmentFingerprint,
    SerialEndpointOrientation,
    validate_manifest_environment,
)

A, B = "hq-r1", "br01-r1"
IF, OTHER = "Serial0/0/0", "Serial0/0/1"
LINK = "hq-br01"
UUID = "{0745334b-b4d2-732c-0488-f9e613781f16}"
ENV = EnvironmentFingerprint(backend_version="9.0.1.0858", bridge_transport="file")
INVENTORY = [
    RuntimeConfigurationTarget(device_name=A, model="2911", interfaces=[IF, OTHER]),
    RuntimeConfigurationTarget(device_name=B, model="2911", interfaces=[IF, OTHER]),
]


def _manifest(*, dce_interface=IF, a_orientation=SerialEndpointOrientation.DCE):
    return DeploymentManifest(
        deployment_id="dep-1", physical_topology_hash="ph",
        backend_version="9.0.1.0858", environment_fingerprint=ENV,
        bindings=[
            DeploymentBinding(semantic_device_id=A, deployed_name=A, model="2911"),
            DeploymentBinding(semantic_device_id=B, deployed_name=B, model="2911"),
        ],
        link_bindings=[DeploymentLinkBinding(
            semantic_link_id=LINK,
            endpoint_a=DeploymentLinkEndpoint(
                semantic_device_id=A, interface=dce_interface,
                orientation=a_orientation,
            ),
            endpoint_b=DeploymentLinkEndpoint(
                semantic_device_id=B, interface=IF,
                orientation=SerialEndpointOrientation.DTE,
            ),
            runtime_link_identifier=UUID, runtime_link_identity_observed=True,
        )],
    )


class TestPositiveBinding:
    def test_the_dce_endpoint_resolves_to_its_exact_interface(self):
        target, interface = _manifest().resolve_serial_clock_target(
            LINK, A, INVENTORY,
            observed_orientation=SerialEndpointOrientation.DCE,
            observed_interface=IF,
        )

        assert target.device_name == A
        assert interface == IF

    def test_the_runtime_link_identity_stays_in_the_manifest(self):
        binding = _manifest().link_binding_for(LINK)

        assert binding.runtime_link_identifier == UUID
        assert binding.runtime_link_identity_observed

    def test_the_dce_endpoint_is_addressable_by_orientation(self):
        assert _manifest().link_binding_for(LINK).dce_endpoint.semantic_device_id == A


class TestNegativesBlockBeforeMutation:
    """Cada caso falla en la resolucion, que ocurre antes de cualquier mutacion."""

    def test_a_device_outside_the_link_is_refused(self):
        with pytest.raises(DeploymentIdentityError, match="no endpoint"):
            _manifest().resolve_serial_clock_target(LINK, "not-in-link", INVENTORY)

    def test_an_interface_that_does_not_hold_the_link_is_refused(self):
        """Existir en el dispositivo no prueba sostener este enlace."""
        with pytest.raises(DeploymentIdentityError, match="was observed on"):
            _manifest(dce_interface=OTHER).resolve_serial_clock_target(
                LINK, A, INVENTORY, observed_interface=IF,
            )

    def test_an_interface_absent_from_the_runtime_target_is_refused(self):
        with pytest.raises(DeploymentIdentityError, match="not present"):
            _manifest(dce_interface="Serial9/9/9").resolve_serial_clock_target(
                LINK, A, INVENTORY,
            )

    def test_the_dte_end_never_receives_a_clock(self):
        with pytest.raises(DeploymentIdentityError, match="clock belongs to the DCE"):
            _manifest().resolve_serial_clock_target(LINK, B, INVENTORY)

    def test_a_runtime_that_contradicts_the_bound_orientation_is_refused(self):
        """Observar lo contrario no autoriza intercambiar extremos."""
        with pytest.raises(DeploymentIdentityError, match="refusing to swap"):
            _manifest().resolve_serial_clock_target(
                LINK, A, INVENTORY,
                observed_orientation=SerialEndpointOrientation.DTE,
            )

    def test_a_stale_environment_fingerprint_is_refused(self):
        with pytest.raises(DeploymentIdentityError, match="EnvironmentFingerprint"):
            validate_manifest_environment(
                _manifest(), EnvironmentFingerprint(backend_version="8.0.0"),
            )

    def test_a_missing_link_binding_is_refused(self):
        with pytest.raises(DeploymentIdentityError, match="missing or ambiguous"):
            _manifest().link_binding_for("no-such-link")


class TestRuntimeIdentityStaysOutOfSemanticIdentity:
    def test_redeploying_one_link_changes_only_the_runtime_identifier(self):
        first, second = _manifest(), _manifest()
        second.link_bindings[0].runtime_link_identifier = (
            "{ffffffff-0000-0000-0000-000000000000}"
        )

        assert first.physical_topology_hash == second.physical_topology_hash
        assert (
            first.link_bindings[0].runtime_link_identifier
            != second.link_bindings[0].runtime_link_identifier
        )

    def test_the_orientation_is_semantic_while_the_identifier_is_not(self):
        swapped = _manifest(a_orientation=SerialEndpointOrientation.DTE)

        assert swapped.link_binding_for(LINK).dce_endpoint is None
        assert _manifest().link_binding_for(LINK).dce_endpoint is not None
