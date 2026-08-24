"""Product-owned canonical CP-SCALE composition and routing-core projection."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    compose_cp_scale_canonical,
    project_cp_scale_routing_core,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureRipv2,
    ControlPlaneVerificationKind,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)


def test_product_composes_the_exact_canonical_topology_and_plans():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )

    assert composition.valid, composition.issues
    assert composition.topology is not None
    assert composition.configuration is not None
    assert composition.control_plane is not None
    assert len(composition.topology.devices) == 314
    assert len(composition.topology.links) == 219
    assert len(composition.configuration.actions) == 609
    assert len(composition.control_plane.actions) == 217


def test_canonical_composition_uses_exact_build_2811_layer3_live_evidence():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )

    capability = composition.capabilities["2811"]
    assert capability.layer3 is CapabilityStatus.SUPPORTED
    assert any(
        item.capability == "layer3"
        and item.source is EvidenceSource.STATIC_OVERRIDE
        and item.verified
        and item.packet_tracer_version == MEASURED_BACKEND_VERSION
        for item in capability.evidence
    )


def test_product_projects_only_the_canonical_routing_core():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    core = project_cp_scale_routing_core(composition)

    assert {item.name for item in core.topology.devices} == {
        "Router0", "Router3", "Router4",
    }
    assert len(core.topology.modules) == 3
    assert len(core.topology.links) == 3
    assert {item.cable for item in core.topology.links} == {"serial"}

    assert {
        item.action_type for item in core.configuration.actions
    } == {
        ConfigurationActionType.CONFIGURE_HOSTNAME,
        ConfigurationActionType.CONFIGURE_ROUTED_INTERFACE,
        ConfigurationActionType.CONFIGURE_SUBINTERFACE,
    }
    assert len([
        item for item in core.control_plane.actions
        if isinstance(item, ConfigureRipv2)
    ]) == 3

    process = [
        item for item in core.control_plane.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS
    ]
    routes = [
        item for item in core.control_plane.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
    ]
    assert len(process) == 3
    assert [item.kind for item in core.control_plane.verification_expectations] == [
        *([ControlPlaneVerificationKind.ROUTING_PROCESS] * 3),
        *([ControlPlaneVerificationKind.ROUTE_PRESENT] * 3),
    ]
    assert {
        (str(item.expected["network"]), int(item.expected["prefix_length"]))
        for item in routes
    } == {
        ("10.0.0.0", 30),
        ("10.0.0.4", 30),
        ("10.0.0.8", 30),
    }
    assert len(routes) == 3
    assert core.forwarding_checks == {
        "Router4": "10.0.0.10",
        "Router0": "10.0.0.6",
        "Router3": "10.0.0.1",
    }
