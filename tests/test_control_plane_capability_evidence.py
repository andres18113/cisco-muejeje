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
    assert supported == {Dimension.RIPV2_CONFIG, Dimension.ROUTING_PROCESS_STATE}


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
    runtime = _RecordingRuntime()

    result = _apply(_compiled_rip_plan(), runtime)

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

    result = _apply(plan, runtime)

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
