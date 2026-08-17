"""Stage 3A4 product composition: immutable E4, serial facts, and typed traffic."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from src.packet_tracer_mcp.application.use_cases.compile_control_plane import (
    compile_enterprise_control_plane,
)
from src.packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentLinkBinding,
    DeploymentLinkEndpoint,
    EnvironmentFingerprint,
    SerialEndpointOrientation,
    build_deployment_manifest,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneIntent,
    ControlPlaneVerificationKind,
    DynamicRoutingIntent,
    DynamicRoutingProtocol,
)
from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
    TrafficFlowIntent,
)
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.domain.enterprise.services.traffic_attribution import (
    attribute_enterprise_traffic,
)
from tests.test_e95_serial_product_planning import (
    _compile_reference_planning,
    _reference_planning_intent,
)


def _product_chain():
    intent = _reference_planning_intent().model_copy(update={
        "address_space": "10.0.0.0/8",
        "traffic_flows": [
            TrafficFlowIntent(
                id="flow/a-to-c",
                source_site_id="a",
                destination_site_id="c",
                per_unit_bps=100_000,
            ),
        ],
    })
    designed = EnterpriseDesigner().design(intent)
    assert designed.validation.is_valid and designed.plan is not None
    _, hardware, original = _compile_reference_planning()
    # Hardware is the already-governed product-planner output; compile the
    # addressed semantic plan through the same production compiler.
    from src.packet_tracer_mcp.application.use_cases.compile_enterprise import (
        compile_enterprise_topology,
    )
    from src.packet_tracer_mcp.infrastructure.catalog.enterprise_topology import (
        PacketTracerTopologyCatalogAdapter,
    )

    catalog = PacketTracerTopologyCatalogAdapter()
    compiled = compile_enterprise_topology(
        designed.plan, hardware, catalog.compilation_profile(), catalog.cable_for,
    )
    assert original.is_valid and compiled.is_valid and compiled.plan is not None
    return designed.plan, compiled.plan


def _oriented_manifest(topology):
    targets = [
        RuntimeConfigurationTarget(
            device_name=device.name,
            model=device.model,
            interfaces=sorted({
                port
                for link in topology.links
                for name, port in (
                    (link.device_a, link.port_a), (link.device_b, link.port_b),
                )
                if name == device.name
            }),
        )
        for device in topology.devices
    ]
    bindings = []
    for link in topology.links:
        a_role = (
            SerialEndpointOrientation.DCE
            if link.cable == "serial" else SerialEndpointOrientation.UNRESOLVED
        )
        b_role = (
            SerialEndpointOrientation.DTE
            if link.cable == "serial" else SerialEndpointOrientation.UNRESOLVED
        )
        bindings.append(DeploymentLinkBinding(
            semantic_link_id=link.id,
            endpoint_a=DeploymentLinkEndpoint(
                semantic_device_id=link.device_a_id,
                interface=link.port_a,
                orientation=a_role,
            ),
            endpoint_b=DeploymentLinkEndpoint(
                semantic_device_id=link.device_b_id,
                interface=link.port_b,
                orientation=b_role,
            ),
        ))
    return build_deployment_manifest(
        topology,
        targets,
        fingerprint=EnvironmentFingerprint(
            backend_version="9.0.1.0858", bridge_transport="file",
        ),
        link_bindings=bindings,
    )


def _runtime_targets(topology):
    return [
        RuntimeConfigurationTarget(
            device_name=device.name,
            model=device.model,
            interfaces=sorted({
                port
                for link in topology.links
                for name, port in (
                    (link.device_a, link.port_a), (link.device_b, link.port_b),
                )
                if name == device.name
            }),
        )
        for device in topology.devices
    ]


class _NoMutationRuntime:
    def __init__(self, topology) -> None:
        self.targets = _runtime_targets(topology)
        self.apply_calls = 0

    def inventory(self):
        return self.targets

    def apply_actions(self, actions):
        self.apply_calls += 1
        raise AssertionError("serial-orientation preflight must precede mutation")

    def verify(self, expectations):
        return []


def test_ipam_allocates_deterministic_nonoverlapping_serial_transits():
    enterprise, _ = _product_chain()

    allocations = enterprise.addressing.transit_allocations

    assert len(allocations) == 3
    assert all(item.prefix == 30 for item in allocations)
    assert len({item.network for item in allocations}) == 3
    assert {
        tuple(sorted((item.source_site_id, item.target_site_id)))
        for item in allocations
    } == {("a", "b"), ("a", "c"), ("b", "c")}


def test_typed_flow_is_attributed_to_one_unambiguous_serial_path():
    enterprise, topology = _product_chain()

    result = attribute_enterprise_traffic(enterprise, topology)

    assert result.is_valid
    assert result.paths_by_flow["flow/a-to-c"] == [
        next(
            link.id for link in topology.links
            if link.cable == "serial"
            and {link.device_a_id.split("-")[2], link.device_b_id.split("-")[2]}
            == {"a", "c"}
        )
    ]
    used = {
        link_id for link_id, values in result.contributions_by_link.items() if values
    }
    assert used == set(result.paths_by_flow["flow/a-to-c"])


def test_oriented_manifest_drives_serial_l3_clock_and_readback_without_mutating_e4():
    enterprise, topology = _product_chain()
    before = topology.model_dump(mode="json")
    before_hash = topology.physical_identity_hash
    traffic = attribute_enterprise_traffic(enterprise, topology)
    manifest = _oriented_manifest(topology)

    compiled = compile_enterprise_configuration(
        enterprise,
        topology,
        deployment_manifest=manifest,
        traffic_by_link=traffic.contributions_by_link,
        packet_tracer_version="9.0.1.0858",
    )

    assert compiled.is_valid and compiled.plan is not None
    serial_l3 = [
        item for item in compiled.plan.actions
        if item.action_type is ConfigurationActionType.CONFIGURE_ROUTED_INTERFACE
        and item.segment_id.startswith("transit/")
    ]
    clocks = compiled.plan.actions_of_type(
        ConfigurationActionType.CONFIGURE_SERIAL_CLOCK,
    )
    assert len(serial_l3) == 6
    assert len(clocks) == 3
    assert {item.source_link_id for item in clocks} == {
        item.id for item in topology.links if item.cable == "serial"
    }
    selected = next(
        item for item in clocks
        if item.source_link_id in traffic.paths_by_flow["flow/a-to-c"]
    )
    assert selected.clock_rate_bps == 128_000
    assert all(item.serial_endpoint_role == "dce" for item in clocks)
    serial_expectations = [
        item for item in compiled.plan.verification_expectations
        if item.kind is VerificationKind.SERIAL_CONTROLLER
    ]
    assert len(serial_expectations) == 3
    assert topology.model_dump(mode="json") == before
    assert topology.physical_identity_hash == before_hash


def test_configuration_apply_revalidates_dce_target_before_any_mutation():
    enterprise, topology = _product_chain()
    traffic = attribute_enterprise_traffic(enterprise, topology)
    compiled_manifest = _oriented_manifest(topology)
    compiled = compile_enterprise_configuration(
        enterprise,
        topology,
        deployment_manifest=compiled_manifest,
        traffic_by_link=traffic.contributions_by_link,
        packet_tracer_version="9.0.1.0858",
    )
    assert compiled.plan is not None
    first_clock = compiled.plan.actions_of_type(
        ConfigurationActionType.CONFIGURE_SERIAL_CLOCK,
    )[0]
    runtime_manifest = compiled_manifest.model_copy(deep=True)
    link = runtime_manifest.link_binding_for(first_clock.source_link_id)
    dce = link.endpoint_for(first_clock.device_id)
    other = (
        link.endpoint_b if link.endpoint_a is dce else link.endpoint_a
    )
    dce.orientation = SerialEndpointOrientation.DTE
    other.orientation = SerialEndpointOrientation.DCE
    runtime = _NoMutationRuntime(topology)

    result = ConfigurationApplicator(runtime).apply(
        compiled.plan,
        actual_source_topology_hash=topology.physical_identity_hash,
        runtime_context=ConfigurationRuntimeContext(
            environment_fingerprint=runtime_manifest.environment_fingerprint,
        ),
        deployment_manifest=runtime_manifest,
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert runtime.apply_calls == 0


def test_ripv2_compiles_typed_flow_behavior_after_exact_route_readback():
    enterprise, topology = _product_chain()
    traffic = attribute_enterprise_traffic(enterprise, topology)
    configuration = compile_enterprise_configuration(
        enterprise,
        topology,
        deployment_manifest=_oriented_manifest(topology),
        traffic_by_link=traffic.contributions_by_link,
        packet_tracer_version="9.0.1.0858",
    ).plan
    assert configuration is not None
    router_ids = sorted(
        item.id for item in topology.devices if item.category == "router"
    )
    serial_ids = sorted(
        item.id for item in topology.links if item.cable == "serial"
    )

    compiled = compile_enterprise_control_plane(
        ControlPlaneIntent(
            id="cp/reference-ripv2",
            routing=DynamicRoutingIntent(
                id="routing/reference-ripv2",
                protocol=DynamicRoutingProtocol.RIPV2,
                device_ids=router_ids,
                transit_link_ids=serial_ids,
            ),
        ),
        topology,
        configuration,
        traffic_flows=enterprise.traffic_flows,
    )

    assert compiled.is_valid and compiled.plan is not None
    behavior = [
        item for item in compiled.plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
    ]
    assert len(behavior) == 1
    assert behavior[0].expected["traffic_flow_id"] == "flow/a-to-c"
    assert behavior[0].expected["destination_ipv4"]
    route_ids = {
        item.id for item in compiled.plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
        and item.device_id == next(
            action.device_id for action in compiled.plan.actions
            if action.id == behavior[0].action_id
        )
    }
    assert route_ids
    assert any(
        prerequisite.reference_id in route_ids
        and prerequisite.kind.value == "verification_verified"
        for prerequisite in behavior[0].verification_prerequisites
    )


def _compiled_control_plane(enterprise, topology, configuration, **kwargs):
    return compile_enterprise_control_plane(
        ControlPlaneIntent(
            id="cp/reference-ripv2",
            routing=DynamicRoutingIntent(
                id="routing/reference-ripv2",
                protocol=DynamicRoutingProtocol.RIPV2,
                device_ids=sorted(
                    item.id for item in topology.devices
                    if item.category == "router"
                ),
                transit_link_ids=sorted(
                    item.id for item in topology.links if item.cable == "serial"
                ),
            ),
        ),
        topology,
        configuration,
        **kwargs,
    )


def _configuration_for(enterprise, topology):
    traffic = attribute_enterprise_traffic(enterprise, topology)
    return compile_enterprise_configuration(
        enterprise,
        topology,
        deployment_manifest=_oriented_manifest(topology),
        traffic_by_link=traffic.contributions_by_link,
        packet_tracer_version="9.0.1.0858",
    ).plan


def test_declaring_no_traffic_flows_preserves_the_previous_plan_exactly():
    """El seam es opt-in: sin flujos, el plan compilado no se mueve un byte.

    Es la mitad que mas facil se rompe sin que nadie lo note, porque todo lo que
    ya existia sigue pasando aunque el plan haya cambiado de forma.
    """
    enterprise, topology = _product_chain()
    configuration = _configuration_for(enterprise, topology)

    without = _compiled_control_plane(enterprise, topology, configuration)
    explicit_empty = _compiled_control_plane(
        enterprise, topology, configuration, traffic_flows=(),
    )

    assert without.is_valid and explicit_empty.is_valid
    assert without.plan.semantic_hash == explicit_empty.plan.semantic_hash
    assert without.plan.model_dump(mode="json") == explicit_empty.plan.model_dump(
        mode="json"
    )
    # Y sin flujos NO se compila conducta extremo a extremo, como antes.
    assert not [
        item for item in without.plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
    ]


def test_a_flow_depends_only_on_the_route_to_its_own_destination_prefix():
    """El prerequisito es semantico, no "todas las rutas del router de origen".

    El router de origen aprende varios prefijos; solo uno contiene la IP de
    destino del flujo. Colgar la conducta de los otros seria exigir evidencia
    ajena, y ademas la haria pasar o fallar por motivos que no son del flujo.
    """
    import ipaddress

    enterprise, topology = _product_chain()
    configuration = _configuration_for(enterprise, topology)
    compiled = _compiled_control_plane(
        enterprise, topology, configuration,
        traffic_flows=enterprise.traffic_flows,
    )
    behavior = next(
        item for item in compiled.plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
    )
    destination = ipaddress.ip_address(behavior.expected["destination_ipv4"])
    routes = {
        item.id: item for item in compiled.plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
        and item.device_id == behavior.device_id
    }
    referenced = {
        prerequisite.reference_id
        for prerequisite in behavior.verification_prerequisites
        if prerequisite.kind.value == "verification_verified"
    }

    # Hay mas de una ruta candidata, o el test no probaria nada.
    assert len(routes) > 1
    assert len(referenced) == 1
    chosen = routes[next(iter(referenced))]
    assert destination in ipaddress.ip_network(
        f"{chosen.expected['network']}/{chosen.expected['prefix_length']}"
    )
    # Ninguna de las rutas NO elegidas contiene el destino.
    for identifier, route in routes.items():
        if identifier in referenced:
            continue
        assert destination not in ipaddress.ip_network(
            f"{route.expected['network']}/{route.expected['prefix_length']}"
        )


def test_a_verified_route_prerequisite_is_not_forwarding_evidence():
    """Tener la ruta no es haber llegado.

    La expectativa de conducta conserva su propia dimension de capacidad y su
    propio `reachable`, que solo satisface un ping tipado. Si la ruta bastara,
    el prerequisito habria reemplazado a la evidencia en vez de ordenarla.
    """
    enterprise, topology = _product_chain()
    configuration = _configuration_for(enterprise, topology)
    compiled = _compiled_control_plane(
        enterprise, topology, configuration,
        traffic_flows=enterprise.traffic_flows,
    )
    behavior = next(
        item for item in compiled.plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
    )
    routes = [
        item for item in compiled.plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
    ]

    assert behavior.expected["reachable"] is True
    assert behavior.required_capability not in {
        item.required_capability for item in routes
    }
    for route in routes:
        assert "reachable" not in route.expected
        assert "traffic_flow_id" not in route.expected


def test_a_flow_without_a_compiled_route_to_its_destination_fails_closed():
    """Antes que colgarlo de una ruta ajena, no se emite conducta.

    Un flujo hacia un sitio que no participa del dominio de ruteo no tiene
    ningun prerequisito honesto disponible, y eso es un error de compilacion,
    no una expectativa mas debil.
    """
    enterprise, topology = _product_chain()
    configuration = _configuration_for(enterprise, topology)
    orphan = TrafficFlowIntent(
        id="flow/a-to-nowhere",
        source_site_id="a",
        destination_site_id="site-that-does-not-exist",
        per_unit_bps=1_000,
    )

    compiled = _compiled_control_plane(
        enterprise, topology, configuration, traffic_flows=[orphan],
    )

    assert not compiled.is_valid
    assert any("flow/a-to-nowhere" in issue.message for issue in compiled.issues)
    assert compiled.plan is None
