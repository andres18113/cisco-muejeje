"""Integración de evidencia de capacidad del control plane (TD-CAPABILITY-001).

El gate siempre estuvo bien: UNKNOWN no se ejecuta. Lo que faltaba era una
ruta de evidencia de producto. Estos tests fijan que la evidencia entra, que
sólo entra la que existe, y que la ausencia de evidencia sigue cerrando.
"""

from __future__ import annotations

import pathlib

import pytest

from src.packet_tracer_mcp.application.use_cases.apply_control_plane import (
    ControlPlaneApplicator,
    _profiles_in_environment_scope,
)
from src.packet_tracer_mcp.application.use_cases.compile_control_plane import (
    compile_enterprise_control_plane,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigureRoutedInterface,
    ConfigurationPhase,
    ConfigurationPlan,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneCapabilityDimension as Dimension,
    ControlPlaneCapabilityProfile,
    ControlPlaneIntent,
    DynamicRoutingIntent,
    DynamicRoutingProtocol,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    SecurityCapabilityStatus as Status,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from src.packet_tracer_mcp.infrastructure.catalog.control_plane_capabilities import (
    packet_tracer_control_plane_capabilities,
)

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "src" / "packet_tracer_mcp"


class _RecordingRuntime:
    def __init__(self) -> None:
        self.dispatched: list[str] = []

    def inventory(self):
        return [
            RuntimeConfigurationTarget(
                device_name=name, model="2911",
                interfaces=["GigabitEthernet0/0", "Serial0/0/0"],
            )
            for name in ("PROBE-R1", "PROBE-R2")
        ]

    def apply_actions(self, actions):
        self.dispatched.extend(item.id for item in actions)
        return [
            RuntimeActionMutation(action_id=item.id, applied=True)
            for item in actions
        ]

    def verify(self, expectations):
        return []

    def execute_failure_scenario(self, *args, **kwargs):
        raise AssertionError("not part of this ticket")


def _compiled_rip_plan():
    r1 = DevicePlan(id="r1", name="PROBE-R1", model="2911", category="router",
                    site_id="probe", network_layer="core")
    r2 = DevicePlan(id="r2", name="PROBE-R2", model="2911", category="router",
                    site_id="probe", network_layer="core")
    topology = TopologyPlan(
        id="t", semantic_hash="th", devices=[r1, r2],
        links=[LinkPlan(
            id="wan", device_a=r1.name, device_a_id="r1", port_a="Serial0/0/0",
            device_b=r2.name, device_b_id="r2", port_b="Serial0/0/0",
            cable="serial", link_role="core_link",
        )],
    )
    masks = {30: "255.255.255.252", 28: "255.255.255.240", 27: "255.255.255.224"}
    names = {"r1": r1.name, "r2": r2.name}
    configuration = ConfigurationPlan(
        id="c", source_topology_id="t", source_topology_hash="th",
        semantic_hash="ch",
        actions=[
            ConfigureRoutedInterface(
                id=f"cfg/l3/{device}/{segment}",
                phase=ConfigurationPhase.L3_INTERFACES,
                device_id=device, device_name=names[device], site_id="probe",
                interface=interface, ipv4=address, prefix=prefix,
                netmask=masks[prefix], segment_id=segment,
                required_capability="layer3",
            )
            for device, interface, address, prefix, segment in (
                ("r1", "Serial0/0/0", "150.1.1.85", 30, "wan"),
                ("r2", "Serial0/0/0", "150.1.1.86", 30, "wan"),
                ("r1", "GigabitEthernet0/0", "150.1.1.65", 28, "lan-r1"),
                ("r2", "GigabitEthernet0/0", "150.1.1.1", 27, "lan-r2"),
            )
        ],
    )
    intent = ControlPlaneIntent(
        id="rip", routing_domains=[DynamicRoutingIntent(
            id="routing/probe", site_id="probe",
            protocol=DynamicRoutingProtocol.RIPV2,
            device_ids=["r1", "r2"], transit_link_ids=["wan"],
        )],
    )
    compiled = compile_enterprise_control_plane(intent, topology, configuration)
    assert compiled.is_valid, compiled.issues
    return compiled.plan


def _apply(plan, runtime, **kwargs):
    return ControlPlaneApplicator(runtime, **kwargs.pop("applicator", {})).apply(
        plan,
        actual_source_topology_hash="th",
        actual_source_configuration_hash="ch",
        foundational_statuses={
            item.source_id: ActionExecutionStatus.VERIFIED
            for item in plan.foundational_requirements
        },
        foundational_hashes={},
        **kwargs,
    )


# ===================== A/B/C. estado por evidencia =========================


def test_without_evidence_ripv2_stays_unknown():
    empty = ControlPlaneCapabilityProfile(model="2911")

    assert empty.status(Dimension.RIPV2_CONFIG) is Status.UNKNOWN


def test_qualifying_live_evidence_makes_ripv2_supported():
    profile = packet_tracer_control_plane_capabilities()["2911"]

    assert profile.status(Dimension.RIPV2_CONFIG) is Status.SUPPORTED
    assert profile.packet_tracer_version == "9.0.1.0858"


def test_explicit_unsupported_evidence_is_preserved_as_unsupported():
    profile = ControlPlaneCapabilityProfile(
        model="2911",
        evidence_source="controlled probe recorded an explicit rejection",
        dimensions={Dimension.RIPV2_CONFIG: Status.UNSUPPORTED},
    )
    runtime = _RecordingRuntime()

    result = _apply(_compiled_rip_plan(), runtime, capabilities={"2911": profile})

    assert runtime.dispatched == []
    assert all(
        item.failure_code is ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
        for item in result.action_results
    )
    assert all(
        item.status is ActionExecutionStatus.SKIPPED
        for item in result.action_results
    )


# ===================== D/E. la evidencia no se contagia ====================


@pytest.mark.parametrize("dimension", [
    Dimension.OSPFV2_CONFIG,
    Dimension.EIGRP_IPV4_CONFIG,
    Dimension.STP_RAPID_PVST_CONFIG,
    Dimension.STP_PVST_CONFIG,
    Dimension.STP_MST_CONFIG,
    Dimension.HSRP_CONFIG,
    Dimension.ETHERCHANNEL_LACP_CONFIG,
])
def test_ripv2_evidence_never_qualifies_another_dimension(dimension):
    profile = packet_tracer_control_plane_capabilities()["2911"]

    assert profile.status(dimension) is Status.UNKNOWN


def test_a_model_without_attributed_evidence_claims_nothing():
    profile = packet_tracer_control_plane_capabilities()["2960-24TT"]

    assert set(profile.dimensions.values()) == {Status.UNKNOWN}
    assert "no per-model attribution" in profile.evidence_source


def test_an_unlisted_model_gets_no_profile_at_all():
    profiles = packet_tracer_control_plane_capabilities()

    assert "3560-24PS" not in profiles
    assert ControlPlaneApplicator._capability_status(
        profiles, "3560-24PS", Dimension.RIPV2_CONFIG,
    ) is Status.UNKNOWN


def test_only_dimensions_with_live_attributed_evidence_are_supported():
    profile = packet_tracer_control_plane_capabilities()["2911"]
    supported = {
        dimension for dimension, status in profile.dimensions.items()
        if status is Status.SUPPORTED
    }

    # ROUTING_PROCESS_STATE acompana a RIPV2_CONFIG porque la MISMA lectura en
    # vivo de R2-0 lo demuestra sobre este modelo y este build.
    # ROUTING_ROUTE_STATE se anade con la evidencia de R2-B fase 4, donde
    # `show ip route rip` se leyo en vivo en este mismo modelo y build.
    # ROUTING_BEHAVIOR se anade con R3: el `TypedPingExecutor` de produccion
    # despacho su `ping` registrado en el terminal de un 2911 disposable de este
    # build, con ventana fresca, eco exacto, estadistica parseada y sesion
    # atribuida a un unico device enumerado. Es el CANAL de medida, no su
    # resultado -- R3 cerro con `Success rate is 0 percent (0/5)` y cualifica
    # igual, porque lo que se midio es que se puede medir.
    assert supported == {
        Dimension.RIPV2_CONFIG,
        Dimension.ROUTING_PROCESS_STATE,
        Dimension.ROUTING_ROUTE_STATE,
        Dimension.ROUTING_BEHAVIOR,
    }


def test_1941_eigrp_capabilities_are_scoped_to_the_live_qualified_model():
    qualified = packet_tracer_control_plane_capabilities("9.0.1.0858")["1941"]
    unqualified = packet_tracer_control_plane_capabilities("9.0.1.0858")["2911"]

    assert qualified.status(Dimension.EIGRP_IPV4_CONFIG) is Status.SUPPORTED
    assert qualified.status(Dimension.ROUTING_NEIGHBOR_STATE) is Status.SUPPORTED
    assert "EIGRP" in qualified.evidence_source
    assert unqualified.status(Dimension.EIGRP_IPV4_CONFIG) is Status.UNKNOWN
    assert unqualified.status(Dimension.ROUTING_NEIGHBOR_STATE) is Status.UNKNOWN


def test_2811_ripv2_capabilities_are_scoped_to_cp_scale_live_evidence():
    profile = packet_tracer_control_plane_capabilities("9.0.1.0858")["2811"]

    assert {
        dimension
        for dimension, status in profile.dimensions.items()
        if status is Status.SUPPORTED
    } == {
        Dimension.RIPV2_CONFIG,
        Dimension.ROUTING_PROCESS_STATE,
        Dimension.ROUTING_ROUTE_STATE,
        Dimension.ROUTING_BEHAVIOR,
    }
    assert "CP-SCALE CORE" in profile.evidence_source


# ===================== completitud del mapeo ================================


@pytest.mark.parametrize(
    "model", sorted(packet_tracer_control_plane_capabilities()),
)
def test_every_dimension_is_explicitly_classified(model):
    """Una dimension nueva no puede colarse sin que alguien la clasifique."""
    profile = packet_tracer_control_plane_capabilities()[model]

    assert set(profile.dimensions) == set(Dimension)


def test_no_dimension_is_left_to_an_implicit_default():
    for profile in packet_tracer_control_plane_capabilities().values():
        missing = set(Dimension) - set(profile.dimensions)
        assert not missing, f"{profile.model} no clasifica {sorted(missing)}"


# ===================== F/G. procedencia de producto ========================


def test_the_product_path_needs_no_manually_supplied_profile():
    """Sin fixture inyectado, pero CON el entorno declarado.

    Declarar el entorno no es inyectar evidencia: es decir contra que build se
    esta ejecutando, que es la condicion para que la evidencia viva aplique.
    """
    runtime = _RecordingRuntime()

    result = _apply(
        _compiled_rip_plan(), runtime, runtime_context=_context("9.0.1.0858"),
    )

    assert len(runtime.dispatched) == 2
    assert all(
        item.status is ActionExecutionStatus.APPLIED
        for item in result.action_results
    )


def test_product_provenance_is_not_a_test_fixture():
    for profile in packet_tracer_control_plane_capabilities().values():
        assert profile.evidence_source
        assert "test fixture" not in profile.evidence_source.casefold()
    assert (
        "test fixture"
        in ControlPlaneCapabilityProfile.supported("2911").evidence_source
    ), "el helper de tests debe seguir declarandose como tal"


# ===================== H/I. contrato fail-closed ===========================


def test_unknown_capability_prevents_every_mutation():
    runtime = _RecordingRuntime()

    result = _apply(_compiled_rip_plan(), runtime, capabilities={})

    assert runtime.dispatched == []
    assert all(
        item.failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN
        for item in result.action_results
    )


def test_supported_ripv2_becomes_eligible_through_the_real_applicator():
    plan = _compiled_rip_plan()
    runtime = _RecordingRuntime()

    result = _apply(plan, runtime, runtime_context=_context("9.0.1.0858"))

    assert runtime.dispatched == [item.id for item in plan.actions]
    assert {item.status for item in result.action_results} == {
        ActionExecutionStatus.APPLIED,
    }
    assert not any(
        item.failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN
        for item in result.action_results
    )


def test_an_injected_provider_is_honoured_over_the_default():
    runtime = _RecordingRuntime()

    result = _apply(
        _compiled_rip_plan(), runtime,
        applicator={"capability_provider": dict},
    )

    assert runtime.dispatched == []
    assert all(
        item.failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN
        for item in result.action_results
    )


# ===================== J/K. sin atajos en produccion =======================


def test_production_never_builds_an_all_supported_profile():
    offenders = [
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*.py")
        if "ControlPlaneCapabilityProfile.supported(" in path.read_text(
            encoding="utf-8",
        )
    ]

    assert offenders == []


# ===================== alcance de entorno (version) =======================
#
# Guardar `packet_tracer_version` como metadato no es alcance. La regla que se
# aplica es la que `capability_resolver._evidence_matches_version` ya fija:
# evidencia de runtime/probe sólo se reutiliza con version EXACTA.


def _context(version: str) -> ConfigurationRuntimeContext:
    return ConfigurationRuntimeContext(
        backend="packet_tracer", backend_version=version,
    )


def test_matching_declared_environment_lets_live_evidence_qualify():
    runtime = _RecordingRuntime()

    result = _apply(
        _compiled_rip_plan(), runtime,
        runtime_context=_context("9.0.1.0858"),
    )

    assert len(runtime.dispatched) == 2
    assert all(
        item.status is ActionExecutionStatus.APPLIED
        for item in result.action_results
    )


@pytest.mark.parametrize(
    "declared", ["9.0.2.0000", "8.2.1.0118", "", "not-a-version"],
    ids=["newer-build", "older-build", "undeclared", "garbage"],
)
def test_an_unmatched_environment_never_inherits_supported(declared):
    runtime = _RecordingRuntime()

    result = _apply(
        _compiled_rip_plan(), runtime, runtime_context=_context(declared),
    )

    assert runtime.dispatched == []
    assert all(
        item.failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN
        for item in result.action_results
    )
    assert all(
        item.status is ActionExecutionStatus.SKIPPED
        for item in result.action_results
    )


def test_the_scope_rule_is_the_existing_exact_version_contract():
    from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
        CapabilityEvidence,
    )
    from src.packet_tracer_mcp.domain.enterprise.services.capability_resolver import (
        _evidence_matches_version,
    )

    from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
        CapabilityStatus,
        EvidenceSource,
    )

    qualified = packet_tracer_control_plane_capabilities()["2911"]
    evidence = CapabilityEvidence(
        capability="ripv2_config",
        status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.CONTROLLED_PROBE,
        packet_tracer_version=qualified.packet_tracer_version,
    )

    for declared in ("9.0.1.0858", "9.0.2.0000", ""):
        expected = _evidence_matches_version(evidence, declared or None)
        in_scope = "2911" in _profiles_in_environment_scope(
            {"2911": qualified}, declared,
        )
        assert in_scope is expected, declared


def test_a_profile_that_declares_no_version_claims_no_scope():
    unscoped = ControlPlaneCapabilityProfile(
        model="2911",
        evidence_source="explicit caller declaration",
        dimensions={Dimension.RIPV2_CONFIG: Status.SUPPORTED},
    )

    assert unscoped.packet_tracer_version is None
    for declared in ("9.0.1.0858", "anything", ""):
        assert "2911" in _profiles_in_environment_scope(
            {"2911": unscoped}, declared,
        )


def test_the_environment_scope_uses_the_fingerprint_when_present():
    from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
        EnvironmentFingerprint,
    )

    context = ConfigurationRuntimeContext(
        backend="ignored", backend_version="ignored",
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer", backend_version="9.0.1.0858",
        ),
    )

    assert context.evidence_backend_version == "9.0.1.0858"
    assert "2911" in _profiles_in_environment_scope(
        packet_tracer_control_plane_capabilities(),
        context.evidence_backend_version,
    )


# ===================== semantica de ROUTING_PROCESS_STATE ==================
#
# El enum separa la CONFIGURACION por protocolo/modo y deja UNA sola dimension
# de observacion por familia. Esa asimetria es el contrato: `*_STATE` describe
# el canal de observacion del dispositivo, y el estrechamiento por protocolo lo
# hace el runtime en el momento de observar.


def test_configuration_dimensions_are_split_per_protocol_but_state_is_not():
    config_families = {
        "stp": [Dimension.STP_PVST_CONFIG, Dimension.STP_RAPID_PVST_CONFIG,
                Dimension.STP_MST_CONFIG],
        "etherchannel": [Dimension.ETHERCHANNEL_LACP_CONFIG,
                         Dimension.ETHERCHANNEL_PAGP_CONFIG,
                         Dimension.ETHERCHANNEL_STATIC_CONFIG],
        "routing": [Dimension.OSPFV2_CONFIG, Dimension.EIGRP_IPV4_CONFIG,
                    Dimension.RIPV2_CONFIG],
    }
    for members in config_families.values():
        assert len(members) == 3

    # Una sola dimension de estado para las tres variantes de cada familia.
    state_dimensions = [
        item for item in Dimension
        if item.value.endswith("_state")
    ]
    assert Dimension.STP_STATE in state_dimensions
    assert Dimension.ETHERCHANNEL_STATE in state_dimensions
    assert Dimension.ROUTING_PROCESS_STATE in state_dimensions
    assert len([
        item for item in state_dimensions
        if item.value.startswith("routing_process")
    ]) == 1


def test_every_routing_protocol_shares_the_same_process_state_gate():
    """Prueba que la dimension no es protocol-specific en el compilador."""
    source = (
        PACKAGE / "domain" / "enterprise" / "services" / "control_plane_compiler.py"
    ).read_text(encoding="utf-8")

    # Las dos ramas -- RIP y OSPF/EIGRP -- piden la MISMA dimension.
    assert source.count(
        "ControlPlaneCapabilityDimension.ROUTING_PROCESS_STATE",
    ) == 2


def test_a_supported_process_state_gate_does_not_fabricate_eigrp_evidence():
    """El gate autoriza observar; sin salida actual el runtime no promueve."""
    from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
        ConfigureEigrpIpv4, ControlPlanePhase, ControlPlaneVerificationExpectation,
        ControlPlaneVerificationKind, RoutingNetwork,
    )
    from src.packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
        PacketTracerEnterpriseControlPlaneRuntime,
    )

    action = ConfigureEigrpIpv4(
        id="cp/eigrp/x", phase=ControlPlanePhase.DYNAMIC_ROUTING,
        device_id="r1", device_name="PROBE-R1", model="2911", site_id="probe",
        required_capability=Dimension.EIGRP_IPV4_CONFIG,
        as_number=100, router_id="1.1.1.1",
        networks=[RoutingNetwork(
            network="10.0.0.0", wildcard="0.0.0.255", segment_id="lan",
            interface="GigabitEthernet0/0",
            source_configuration_action_id="cfg/l3/r1/lan",
        )],
    )
    expectation = ControlPlaneVerificationExpectation(
        id="verify/eigrp", kind=ControlPlaneVerificationKind.ROUTING_PROCESS,
        action_id=action.id, device_id="r1",
        required_capability=Dimension.ROUTING_PROCESS_STATE,
        expected={"protocol": "eigrp", "router_id": "1.1.1.1"},
    )
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
    )
    runtime.apply_actions([action])

    observed = runtime.verify([expectation])[0]

    assert observed.status is ActionExecutionStatus.UNOBSERVABLE
    assert observed.evidence_method == "runtime_observability_limit"
    assert not observed.fresh_evidence


def test_the_runtime_narrows_by_mode_for_other_families_too():
    """El mismo patron ya existia para STP/EtherChannel antes de RIP."""
    source = (
        PACKAGE / "infrastructure" / "execution"
        / "enterprise_control_plane_runtime.py"
    ).read_text(encoding="utf-8")

    for evidence_method in (
        "mst_readback_unavailable",
        "etherchannel_protocol_readback_unavailable",
        "hsrp_role_readback_unavailable",
        "fresh_show_ip_protocols_eigrp",
        "fresh_show_ip_eigrp_neighbors",
        "fresh_show_ip_route_eigrp",
    ):
        assert evidence_method in source


def test_the_capability_source_has_no_model_string_special_case():
    catalog = (
        PACKAGE / "infrastructure" / "catalog" / "control_plane_capabilities.py"
    ).read_text(encoding="utf-8")
    applicator = (
        PACKAGE / "application" / "use_cases" / "apply_control_plane.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("if model ==", "model ==", "model.startswith("):
        assert forbidden not in catalog
    # El applicator resuelve por dato, nunca por folclore de model-string.
    assert "2911" not in applicator
    assert "2960" not in applicator
