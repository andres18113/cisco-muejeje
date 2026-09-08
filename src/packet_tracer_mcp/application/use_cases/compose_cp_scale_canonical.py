"""Product composition for the governed canonical CP-SCALE topology.

The generic reference composer remains capacity-driven.  CP-SCALE has a
separate, document-governed physical design, so its exact hardware binding must
use ``ReferenceHardwarePlanner`` rather than silently falling back to capacity
allocation.  This module is the production seam shared by offline inspection
and bounded LIVE qualification.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from enum import Enum

from ...domain.enterprise.models.capabilities import DeviceCapabilities
from ...domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigurationIssueSeverity,
    ConfigurationPlan,
    SetEndpointStaticAddress,
)
from ...domain.enterprise.models.roles import DeviceRole
from ...domain.enterprise.models.voice_plan import (
    GeneratePhoneConfigurationFiles,
    VoicePlan,
)
from ...domain.enterprise.models.control_plane import (
    ConfigureRipv2,
    ControlPlaneCapabilityProfile,
    ControlPlanePlan,
    ControlPlaneVerificationKind,
)
from ...domain.enterprise.services.configuration_compiler import (
    configuration_plan_semantic_hash,
)
from ...domain.enterprise.services.control_plane_compiler import (
    control_plane_plan_semantic_hash,
    representative_static_endpoint_for_routing_device,
)
from ...domain.enterprise.services.enterprise_designer import EnterpriseDesigner
from ...domain.enterprise.services.reference_hardware_planner import (
    ReferenceHardwarePlanner,
)
from ...domain.enterprise.services.topology_identity import (
    compute_topology_hashes,
    stamp_topology_hashes,
)
from ...domain.enterprise.services.traffic_attribution import (
    attribute_enterprise_traffic,
)
from ...domain.enterprise.scenarios.cp_scale import cp_scale_intent
from ...domain.enterprise.scenarios.cp_scale_physical import (
    LARGE,
    MULTILAYER,
    R0,
    R3,
    R4,
    SMALL,
    SW10,
    Z1,
    Z2,
    ZC,
    ZD,
    cp_scale_canonical_control_plane_intent,
    cp_scale_canonical_voice_intent,
    cp_scale_physical_design,
)
from ...domain.models.plans import TopologyPlan
from ...infrastructure.catalog.control_plane_capabilities import (
    packet_tracer_control_plane_capabilities,
)
from ...infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from ...infrastructure.catalog.enterprise_topology import (
    PacketTracerTopologyCatalogAdapter,
)
from ...infrastructure.catalog.voice_capabilities import voice_capability_profiles
from ...infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)
from .compile_configuration import compile_enterprise_configuration
from .compile_control_plane import compile_enterprise_control_plane
from .compile_voice import compile_enterprise_voice
from .compile_enterprise import compile_enterprise_topology
from .compose_enterprise_reference import EnterpriseReferenceComposition
from .plan_enterprise_hardware import (
    EnterpriseHardwareComposition,
    capability_catalog_for,
)


_CORE_ROUTER_NAMES = frozenset(("Router0", "Router3", "Router4"))
_CORE_ROUTER_IDS = frozenset((R0, R3, R4))
_CORE_CONFIGURATION_TYPES = frozenset((
    ConfigurationActionType.CONFIGURE_HOSTNAME,
    ConfigurationActionType.CONFIGURE_ROUTED_INTERFACE,
    ConfigurationActionType.CONFIGURE_SUBINTERFACE,
))


@dataclass(frozen=True)
class CPScaleRoutingCore:
    """Exact typed plans and forwarding probes for the serial routing core."""

    topology: TopologyPlan
    configuration: ConfigurationPlan
    control_plane: ControlPlanePlan
    forwarding_checks: dict[str, str]


class CPScaleCanonicalStage(str, Enum):
    """Ordered cumulative stages of the governed 314/219 physical design."""

    ROUTING_CORE = "routing-core"
    ROUTER4_SWITCH10 = "router4-switch10"
    FLOOR1 = "floor1"
    FLOOR2 = "floor2"
    FLOOR3 = "floor3"
    ROUTER0_BRANCH = "router0-branch"
    ROUTER3_BRANCH = "router3-branch"
    REMAINING = "remaining"


class CPScaleCanonicalTarget(str, Enum):
    """Terminal boundary selected for one governed canonical LIVE run."""

    FULL_QUALIFICATION = "full-qualification"
    ROUTER0_BRANCH = CPScaleCanonicalStage.ROUTER0_BRANCH.value


@dataclass(frozen=True)
class CPScaleCanonicalTargetContract:
    """Exact stages and terminal claims authorized by a LIVE target."""

    target: CPScaleCanonicalTarget
    build_stages: tuple[CPScaleCanonicalStage, ...]
    terminal_stage: CPScaleCanonicalStage
    run_remaining_reconciliation: bool
    run_full_qualification: bool
    allow_retention: bool
    precleanup_closure: str
    cleaned_closure: str


@dataclass(frozen=True)
class CPScaleCanonicalStageTransition:
    """Typed mutation boundary between two cumulative canonical stages."""

    previous_stage: CPScaleCanonicalStage
    current_stage: CPScaleCanonicalStage
    new_device_ids: tuple[str, ...]
    anchor_device_ids: tuple[str, ...]
    new_link_ids: tuple[str, ...]
    configuration_mutation_ids: tuple[str, ...]
    configuration_retained_ids: tuple[str, ...]
    control_plane_mutation_ids: tuple[str, ...]
    control_plane_retained_ids: tuple[str, ...]
    voice_mutation_ids: tuple[str, ...]
    voice_retained_ids: tuple[str, ...]
    replayed_configuration_ids: tuple[str, ...]
    replayed_control_plane_ids: tuple[str, ...]
    replayed_voice_ids: tuple[str, ...]

    @property
    def no_mutation_replay(self) -> bool:
        return not (
            self.replayed_configuration_ids
            or self.replayed_control_plane_ids
            or self.replayed_voice_ids
        )

    @property
    def claim(self) -> str:
        return (
            "NO_MUTATION_REPLAY"
            if self.no_mutation_replay
            else "MUTATION_REPLAY_DETECTED"
        )


@dataclass(frozen=True)
class CPScaleSiteForwardingCheck:
    """One E4-related and E5-addressed inter-site forwarding observation."""

    id: str
    direction: str
    traffic_flow_id: str
    source_site_id: str
    destination_site_id: str
    source_device_id: str
    source_device_name: str
    destination_device_id: str
    destination_device_name: str
    destination_router_id: str
    destination_action_id: str
    destination_segment_id: str
    destination_ipv4: str
    source_topology_hash: str
    source_configuration_hash: str


@dataclass(frozen=True)
class CPScaleCanonicalStageProjection:
    """Exact typed plans for one cumulative LIVE construction boundary."""

    stage: CPScaleCanonicalStage
    topology: TopologyPlan
    configuration: ConfigurationPlan
    control_plane: ControlPlanePlan
    forwarding_checks: dict[str, str]
    #: Compiled per stage, never projected from the full plan: E7 binds the
    #: exact E4/E5 hashes it will be applied against, and a stage's hashes are
    #: not the full topology's. None where the stage carries no phone yet.
    voice: VoicePlan | None = None
    branch_forwarding_checks: tuple[CPScaleSiteForwardingCheck, ...] = ()


_CANONICAL_STAGE_ORDER = {
    stage: index for index, stage in enumerate(CPScaleCanonicalStage)
}
_CORE_FORWARDING_CHECKS = {
    "Router4": "10.0.0.10",
    "Router0": "10.0.0.6",
    "Router3": "10.0.0.1",
}


def canonical_cp_scale_target_contract(
    target: CPScaleCanonicalTarget | str,
) -> CPScaleCanonicalTargetContract:
    """Resolve the bounded run contract while keeping the legacy default exact."""

    target = CPScaleCanonicalTarget(target)
    full_build_stages = tuple(
        stage for stage in CPScaleCanonicalStage
        if stage is not CPScaleCanonicalStage.REMAINING
    )
    if target is CPScaleCanonicalTarget.ROUTER0_BRANCH:
        terminal = CPScaleCanonicalStage.ROUTER0_BRANCH
        terminal_index = full_build_stages.index(terminal)
        return CPScaleCanonicalTargetContract(
            target=target,
            build_stages=full_build_stages[:terminal_index + 1],
            terminal_stage=terminal,
            run_remaining_reconciliation=False,
            run_full_qualification=False,
            allow_retention=False,
            precleanup_closure="ROUTER0_BRANCH_VERIFIED_PRECLEANUP",
            cleaned_closure="ROUTER0_BRANCH_VERIFIED_AND_CLEANED",
        )
    return CPScaleCanonicalTargetContract(
        target=target,
        build_stages=full_build_stages,
        terminal_stage=CPScaleCanonicalStage.ROUTER3_BRANCH,
        run_remaining_reconciliation=True,
        run_full_qualification=True,
        allow_retention=True,
        precleanup_closure="CP_SCALE_GOVERNED_VOICE_VERIFIED_PRECLEANUP",
        cleaned_closure="CP_SCALE_GOVERNED_VOICE_VERIFIED_AND_CLEANED",
    )


def compose_cp_scale_canonical(
    *,
    packet_tracer_version: str,
    capability_store: CapabilitySnapshotStore | None = None,
    capability_catalog: EnterpriseCapabilityAdapter | None = None,
    control_plane_capabilities: (
        dict[str, ControlPlaneCapabilityProfile] | None
    ) = None,
) -> EnterpriseReferenceComposition:
    """Compose the exact 314-device/219-link CP-SCALE product plans."""

    designed = EnterpriseDesigner().design(cp_scale_intent())
    if not designed.validation.is_valid or designed.plan is None:
        return EnterpriseReferenceComposition(issues=[
            f"E4 design: {item.message}" for item in designed.validation.errors
        ] or ["E4 design produced no plan."])
    enterprise = designed.plan

    capability_catalog = capability_catalog or capability_catalog_for(
        packet_tracer_version, capability_store=capability_store,
    )
    switch_candidates = capability_catalog.hardware_candidates(
        "switch", packet_tracer_version,
    )
    router_candidates = capability_catalog.hardware_candidates(
        "router", packet_tracer_version,
    )
    hardware_plan = ReferenceHardwarePlanner().plan(
        enterprise,
        cp_scale_physical_design(),
        [*router_candidates, *switch_candidates],
    )
    hardware = EnterpriseHardwareComposition(
        plan=hardware_plan,
        switch_candidates=switch_candidates,
        router_candidates=router_candidates,
        packet_tracer_version=packet_tracer_version,
    )

    topology_catalog = PacketTracerTopologyCatalogAdapter()
    compiled = compile_enterprise_topology(
        enterprise,
        hardware_plan,
        topology_catalog.compilation_profile(),
        topology_catalog.cable_for,
    )
    if not compiled.is_valid or compiled.plan is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise,
            hardware=hardware,
            topology_summary=compiled.summary,
            issues=[f"E5 compile: {item.message}" for item in compiled.issues]
            or ["E5 compilation produced no topology."],
        )
    topology = compiled.plan
    capabilities = {
        model: (
            capability_catalog.capabilities_for(model, packet_tracer_version)
            or DeviceCapabilities(model=model)
        )
        for model in sorted({item.model for item in topology.devices})
    }

    traffic = attribute_enterprise_traffic(enterprise, topology)
    if not traffic.is_valid:
        return EnterpriseReferenceComposition(
            enterprise=enterprise,
            hardware=hardware,
            topology=topology,
            topology_summary=compiled.summary,
            traffic=traffic,
            capabilities=capabilities,
            issues=[f"traffic: {item.message}" for item in traffic.issues],
        )

    configuration = compile_enterprise_configuration(
        enterprise,
        topology,
        capabilities=capabilities,
        traffic_by_link=traffic.contributions_by_link,
        packet_tracer_version=packet_tracer_version,
    )
    if not configuration.is_valid or configuration.plan is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise,
            hardware=hardware,
            topology=topology,
            topology_summary=compiled.summary,
            traffic=traffic,
            capabilities=capabilities,
            issues=[
                f"E5 configuration: {item.message}" for item in configuration.issues
            ] or ["Configuration compilation produced no plan."],
        )

    control = compile_enterprise_control_plane(
        cp_scale_canonical_control_plane_intent(topology),
        topology,
        configuration.plan,
        capabilities=(
            control_plane_capabilities
            if control_plane_capabilities is not None
            else packet_tracer_control_plane_capabilities(packet_tracer_version)
        ),
        traffic_flows=enterprise.traffic_flows,
    )
    if not control.is_valid or control.plan is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise,
            hardware=hardware,
            topology=topology,
            topology_summary=compiled.summary,
            traffic=traffic,
            capabilities=capabilities,
            configuration=configuration.plan,
            issues=[f"E9 control plane: {item.message}" for item in control.issues]
            or ["Control-plane compilation produced no plan."],
        )

    voice_capabilities = voice_capability_profiles(
        capabilities, packet_tracer_version=packet_tracer_version,
    )
    voice = compile_enterprise_voice(
        cp_scale_canonical_voice_intent(topology),
        enterprise,
        topology,
        configuration.plan,
        capabilities=voice_capabilities,
    )
    if not voice.is_valid or voice.plan is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise,
            hardware=hardware,
            topology=topology,
            topology_summary=compiled.summary,
            traffic=traffic,
            capabilities=capabilities,
            configuration=configuration.plan,
            control_plane=control.plan,
            voice_capabilities=voice_capabilities,
            issues=[f"E7 voice: {item.message}" for item in voice.issues]
            or ["Voice compilation produced no plan."],
        )

    return EnterpriseReferenceComposition(
        enterprise=enterprise,
        hardware=hardware,
        topology=topology,
        topology_summary=compiled.summary,
        traffic=traffic,
        capabilities=capabilities,
        configuration=configuration.plan,
        control_plane=control.plan,
        voice=voice.plan,
        voice_capabilities=voice_capabilities,
    )


def project_cp_scale_canonical_stage(
    composition: EnterpriseReferenceComposition,
    stage: CPScaleCanonicalStage,
    *,
    control_plane_capabilities: (
        dict[str, ControlPlaneCapabilityProfile] | None
    ) = None,
) -> CPScaleCanonicalStageProjection:
    """Project one exact cumulative stage without preconfiguring future links.

    The routing core remains the already-qualified first closure.  Later stages
    add only canonical devices whose site/zone is in scope, links whose two
    endpoints are in scope, and configuration actions whose physical source is
    already present.  This keeps a VERIFIED stage meaningful: no future-facing
    trunk or access-port action can be counted before its link/endpoint exists.
    """

    if (
        not composition.valid
        or composition.topology is None
        or composition.configuration is None
    ):
        raise ValueError("A complete canonical composition is required.")
    if stage is CPScaleCanonicalStage.ROUTING_CORE:
        core = project_cp_scale_routing_core(
            composition,
            control_plane_capabilities=control_plane_capabilities,
        )
        return CPScaleCanonicalStageProjection(
            stage=stage,
            topology=core.topology,
            configuration=core.configuration,
            control_plane=core.control_plane,
            forwarding_checks=dict(core.forwarding_checks),
        )

    full_topology = composition.topology
    selected_devices = [
        item.model_copy(deep=True)
        for item in full_topology.devices
        if _stage_includes_device(stage, item.id, item.site_id, item.zone_id)
    ]
    selected_ids = {item.id for item in selected_devices}
    selected_names = {item.name for item in selected_devices}
    topology = full_topology.model_copy(deep=True)
    topology.id = f"cp-scale-canonical-{stage.value}"
    topology.name = f"CP-SCALE canonical {stage.value}"
    topology.devices = selected_devices
    topology.modules = [
        item.model_copy(deep=True)
        for item in full_topology.modules
        if item.device in selected_names
    ]
    topology.links = [
        item.model_copy(deep=True)
        for item in full_topology.links
        if item.device_a_id in selected_ids and item.device_b_id in selected_ids
    ]
    stamp_topology_hashes(topology)

    configuration = _project_stage_configuration(
        composition.configuration,
        topology,
        stage,
    )
    control_plane = _project_stage_control_plane(
        composition,
        topology,
        configuration,
        stage,
        control_plane_capabilities=control_plane_capabilities,
    )
    projection = CPScaleCanonicalStageProjection(
        stage=stage,
        topology=topology,
        configuration=configuration,
        control_plane=control_plane,
        forwarding_checks=dict(_CORE_FORWARDING_CHECKS),
        voice=_compile_stage_voice(composition, topology, configuration, stage),
    )
    if stage is CPScaleCanonicalStage.ROUTER0_BRANCH:
        projection = replace(
            projection,
            branch_forwarding_checks=derive_cp_scale_site_forwarding_checks(
                composition,
                projection,
                source_site_id=LARGE,
                destination_site_id=MULTILAYER,
            ),
        )
    return projection


def _compile_stage_voice(
    composition: EnterpriseReferenceComposition,
    topology: TopologyPlan,
    configuration: ConfigurationPlan,
    stage: CPScaleCanonicalStage,
) -> VoicePlan | None:
    """Compile E7 against this stage's exact E4/E5, or return None for no phones.

    Projecting the full-scale plan would carry the full-scale source hashes, and
    `VoiceApplicator` refuses a plan whose hashes are not the ones it is being
    applied against -- correctly. So each stage compiles its own.
    """
    if composition.enterprise is None:
        return None
    if not any(
        item.enterprise_role == DeviceRole.IP_PHONE.value
        for item in topology.devices
    ):
        return None
    compiled = compile_enterprise_voice(
        cp_scale_canonical_voice_intent(topology),
        composition.enterprise,
        topology,
        configuration,
        capabilities=composition.voice_capabilities,
    )
    if not compiled.is_valid or compiled.plan is None:
        raise ValueError(
            f"Canonical stage {stage.value!r} could not compile its voice plan: "
            + "; ".join(
                item.message for item in compiled.issues
                if item.severity is ConfigurationIssueSeverity.ERROR
            )
        )
    return compiled.plan


def project_cp_scale_canonical_delta(
    previous: TopologyPlan,
    current: TopologyPlan,
) -> TopologyPlan:
    """Return the physical delta plus existing link anchors for one stage.

    Already VERIFIED modules are deliberately absent.  Packet Tracer can prove
    a module's newly caused port effect only in the transaction that installed
    it; replaying the cumulative module list would turn legitimate NO_OP state
    into a false causation claim.  Existing devices appear only when a new link
    needs them as an anchor.
    """

    previous_device_ids = {item.id for item in previous.devices}
    current_device_ids = {item.id for item in current.devices}
    previous_link_ids = {item.id for item in previous.links}
    current_link_ids = {item.id for item in current.links}
    if not previous_device_ids <= current_device_ids:
        raise ValueError("Canonical stage devices are not cumulative.")
    if not previous_link_ids <= current_link_ids:
        raise ValueError("Canonical stage links are not cumulative.")

    new_device_ids = current_device_ids - previous_device_ids
    new_links = [
        item.model_copy(deep=True)
        for item in current.links if item.id not in previous_link_ids
    ]
    anchor_ids = {
        identifier
        for item in new_links
        for identifier in (item.device_a_id, item.device_b_id)
    }
    delta_device_ids = new_device_ids | anchor_ids
    new_device_names = {
        item.name for item in current.devices if item.id in new_device_ids
    }
    delta = current.model_copy(deep=True)
    delta.id = f"{current.id}/physical-delta"
    delta.name = f"{current.name} physical delta"
    delta.devices = [
        item.model_copy(deep=True)
        for item in current.devices if item.id in delta_device_ids
    ]
    delta.modules = [
        item.model_copy(deep=True)
        for item in current.modules if item.device in new_device_names
    ]
    delta.links = new_links
    stamp_topology_hashes(delta)
    return delta


def canonical_stage_configuration_mutation_ids(
    previous: ConfigurationPlan,
    current: ConfigurationPlan,
) -> tuple[str, ...]:
    """Return only actions introduced by a monotonic canonical stage.

    Stage projections remain cumulative because their full verification contract
    must be re-read after every physical expansion. Runtime mutation is a
    different concern: an action already applied by the preceding VERIFIED
    stage is retained, not replayed. Stable IDs are sufficient only after proving
    that every retained action is byte-for-byte the same typed action.
    """

    previous_by_id = {item.id: item for item in previous.actions}
    current_by_id = {item.id: item for item in current.actions}
    if len(previous_by_id) != len(previous.actions):
        raise ValueError("Previous canonical configuration has duplicate action IDs.")
    if len(current_by_id) != len(current.actions):
        raise ValueError("Current canonical configuration has duplicate action IDs.")
    omitted = sorted(set(previous_by_id) - set(current_by_id))
    if omitted:
        raise ValueError(
            "Canonical stage configuration actions are not cumulative: "
            + ", ".join(omitted)
        )
    changed = sorted(
        identifier
        for identifier, previous_action in previous_by_id.items()
        if current_by_id[identifier] != previous_action
    )
    if changed:
        raise ValueError(
            "Canonical stage retained configuration actions changed identity: "
            + ", ".join(changed)
        )
    return tuple(
        item.id for item in current.actions if item.id not in previous_by_id
    )


def canonical_stage_control_plane_mutation_ids(
    previous: ControlPlanePlan,
    current: ControlPlanePlan,
) -> tuple[str, ...]:
    """Return only unchanged-ID-safe control actions introduced by a stage."""

    previous_by_id = {item.id: item for item in previous.actions}
    current_by_id = {item.id: item for item in current.actions}
    if len(previous_by_id) != len(previous.actions):
        raise ValueError(
            "Previous canonical control-plane plan has duplicate action IDs."
        )
    if len(current_by_id) != len(current.actions):
        raise ValueError(
            "Current canonical control-plane plan has duplicate action IDs."
        )
    omitted = sorted(set(previous_by_id) - set(current_by_id))
    if omitted:
        raise ValueError(
            "Canonical stage control-plane actions are not cumulative: "
            + ", ".join(omitted)
        )
    changed = sorted(
        identifier
        for identifier, previous_action in previous_by_id.items()
        if current_by_id[identifier] != previous_action
    )
    if changed:
        raise ValueError(
            "Canonical retained control-plane actions changed identity: "
            + ", ".join(changed)
        )
    return tuple(
        item.id for item in current.actions if item.id not in previous_by_id
    )


def canonical_stage_voice_mutation_ids(
    previous: VoicePlan,
    current: VoicePlan,
) -> tuple[str, ...]:
    """Return new Voice actions plus typed phone-file dependency expansions."""

    previous_by_id = {item.id: item for item in previous.actions}
    current_by_id = {item.id: item for item in current.actions}
    if len(previous_by_id) != len(previous.actions):
        raise ValueError("Previous canonical Voice plan has duplicate action IDs.")
    if len(current_by_id) != len(current.actions):
        raise ValueError("Current canonical Voice plan has duplicate action IDs.")
    omitted = sorted(set(previous_by_id) - set(current_by_id))
    if omitted:
        raise ValueError(
            "Canonical stage Voice actions are not cumulative: "
            + ", ".join(omitted)
        )
    changed = {
        identifier
        for identifier, previous_action in previous_by_id.items()
        if current_by_id[identifier] != previous_action
    }
    invalid_changed: list[str] = []
    for identifier in changed:
        previous_action = previous_by_id[identifier]
        current_action = current_by_id[identifier]
        previous_payload = previous_action.model_dump()
        current_payload = current_action.model_dump()
        previous_dependencies = set(previous_payload.pop("depends_on", []))
        current_dependencies = set(current_payload.pop("depends_on", []))
        previous_apply_dependencies = set(
            previous_payload.pop("apply_dependencies", []),
        )
        current_apply_dependencies = set(
            current_payload.pop("apply_dependencies", []),
        )
        if (
            not isinstance(
                previous_action,
                GeneratePhoneConfigurationFiles,
            )
            or not isinstance(
                current_action,
                GeneratePhoneConfigurationFiles,
            )
            or previous_payload != current_payload
            or not previous_dependencies.issubset(current_dependencies)
            or not previous_apply_dependencies.issubset(
                current_apply_dependencies,
            )
            or current_dependencies != current_apply_dependencies
        ):
            invalid_changed.append(identifier)
    if invalid_changed:
        raise ValueError(
            "Canonical retained Voice actions changed outside a monotonic "
            "phone-file dependency expansion: "
            + ", ".join(sorted(invalid_changed))
        )
    return tuple(
        item.id
        for item in current.actions
        if item.id not in previous_by_id or item.id in changed
    )


def canonical_stage_transition_contract(
    previous: CPScaleCanonicalStageProjection,
    current: CPScaleCanonicalStageProjection,
) -> CPScaleCanonicalStageTransition:
    """Prove one adjacent stage is a physical and typed-action delta only."""

    previous_order = _CANONICAL_STAGE_ORDER[previous.stage]
    current_order = _CANONICAL_STAGE_ORDER[current.stage]
    if current_order != previous_order + 1:
        raise ValueError(
            "Canonical transition contract requires adjacent ordered stages."
        )

    delta = project_cp_scale_canonical_delta(
        previous.topology,
        current.topology,
    )
    previous_device_ids = {item.id for item in previous.topology.devices}
    current_device_ids = {item.id for item in current.topology.devices}
    new_device_ids = current_device_ids - previous_device_ids
    anchor_device_ids = {
        item.id for item in delta.devices
        if item.id in previous_device_ids
    }

    configuration_mutation_ids = canonical_stage_configuration_mutation_ids(
        previous.configuration,
        current.configuration,
    )
    control_plane_mutation_ids = canonical_stage_control_plane_mutation_ids(
        previous.control_plane,
        current.control_plane,
    )
    previous_voice = previous.voice
    current_voice = current.voice
    if current_voice is None:
        voice_mutation_ids: tuple[str, ...] = ()
    elif previous_voice is None or not previous_voice.actions:
        voice_mutation_ids = tuple(item.id for item in current_voice.actions)
    else:
        voice_mutation_ids = canonical_stage_voice_mutation_ids(
            previous_voice,
            current_voice,
        )

    previous_configuration_ids = {
        item.id for item in previous.configuration.actions
    }
    previous_control_plane_ids = {
        item.id for item in previous.control_plane.actions
    }
    previous_voice_ids = {
        item.id for item in previous_voice.actions
    } if previous_voice is not None else set()
    return CPScaleCanonicalStageTransition(
        previous_stage=previous.stage,
        current_stage=current.stage,
        new_device_ids=tuple(sorted(new_device_ids)),
        anchor_device_ids=tuple(sorted(anchor_device_ids)),
        new_link_ids=tuple(sorted(item.id for item in delta.links)),
        configuration_mutation_ids=configuration_mutation_ids,
        configuration_retained_ids=tuple(sorted(
            previous_configuration_ids
        )),
        control_plane_mutation_ids=control_plane_mutation_ids,
        control_plane_retained_ids=tuple(sorted(previous_control_plane_ids)),
        voice_mutation_ids=voice_mutation_ids,
        voice_retained_ids=tuple(sorted(previous_voice_ids)),
        replayed_configuration_ids=tuple(sorted(
            set(configuration_mutation_ids) & previous_configuration_ids
        )),
        replayed_control_plane_ids=tuple(sorted(
            set(control_plane_mutation_ids) & previous_control_plane_ids
        )),
        replayed_voice_ids=tuple(sorted(
            set(voice_mutation_ids) & previous_voice_ids
        )),
    )


def derive_cp_scale_site_forwarding_checks(
    composition: EnterpriseReferenceComposition,
    projection: CPScaleCanonicalStageProjection,
    *,
    source_site_id: str,
    destination_site_id: str,
) -> tuple[CPScaleSiteForwardingCheck, ...]:
    """Derive bidirectional site probes from E4 and static E5 endpoints.

    The E4 traffic flow authorizes the site relationship. The projected E4
    topology identifies each site's edge router. The control-plane compiler's
    deterministic endpoint selector chooses one projected E5 static endpoint
    in each destination site. No address is selected by convention or copied
    into this runtime contract.
    """

    if composition.enterprise is None:
        raise ValueError("Canonical enterprise E4 plan is required for forwarding.")
    flows = [
        item for item in composition.enterprise.traffic_flows
        if item.source_site_id == source_site_id
        and item.destination_site_id == destination_site_id
    ]
    if len(flows) != 1:
        raise ValueError(
            "Canonical site forwarding requires exactly one matching E4 "
            f"traffic flow; found {len(flows)} for "
            f"{source_site_id!r} -> {destination_site_id!r}."
        )
    if (
        compute_topology_hashes(projection.topology).physical_topology_hash
        != projection.topology.physical_identity_hash
    ):
        raise ValueError(
            "Canonical site forwarding E4 physical provenance is stale."
        )
    if (
        projection.configuration.source_topology_hash
        != projection.topology.physical_identity_hash
    ):
        raise ValueError(
            "Canonical site forwarding E5 source does not match projected E4."
        )
    if (
        configuration_plan_semantic_hash(projection.configuration)
        != projection.configuration.semantic_hash
    ):
        raise ValueError(
            "Canonical site forwarding E5 semantic provenance is stale."
        )
    if (
        projection.control_plane.source_topology_hash
        != projection.topology.physical_identity_hash
        or projection.control_plane.source_configuration_hash
        != projection.configuration.semantic_hash
        or control_plane_plan_semantic_hash(projection.control_plane)
        != projection.control_plane.semantic_hash
    ):
        raise ValueError(
            "Canonical site forwarding control-plane provenance is stale."
        )

    edge_by_site: dict[str, object] = {}
    for site_id in (source_site_id, destination_site_id):
        candidates = [
            item for item in projection.topology.devices
            if item.site_id == site_id
            and item.enterprise_role == DeviceRole.EDGE_ROUTER.value
        ]
        if len(candidates) != 1:
            raise ValueError(
                "Canonical site forwarding requires exactly one projected E4 "
                f"edge router for {site_id!r}; found {len(candidates)}."
            )
        edge_by_site[site_id] = candidates[0]

    routing_actions = {
        item.device_id: item for item in projection.control_plane.actions
        if isinstance(item, ConfigureRipv2)
    }
    l3_by_device: dict[str, list[object]] = defaultdict(list)
    static_endpoints_by_segment: dict[
        str, list[SetEndpointStaticAddress]
    ] = defaultdict(list)
    for action in projection.configuration.actions:
        if action.action_type in {
            ConfigurationActionType.CONFIGURE_ROUTED_INTERFACE,
            ConfigurationActionType.CONFIGURE_SUBINTERFACE,
            ConfigurationActionType.CONFIGURE_SVI,
        }:
            l3_by_device[action.device_id].append(action)
        elif isinstance(action, SetEndpointStaticAddress):
            static_endpoints_by_segment[action.segment_id].append(action)

    destination_by_site: dict[str, SetEndpointStaticAddress] = {}
    device_by_id = {item.id: item for item in projection.topology.devices}
    linked_device_ids = {
        identifier
        for link in projection.topology.links
        for identifier in (link.device_a_id, link.device_b_id)
    }
    for site_id, router in edge_by_site.items():
        destination = representative_static_endpoint_for_routing_device(
            router.id,
            routing_actions,
            l3_by_device,
            static_endpoints_by_segment,
        )
        if destination is None:
            raise ValueError(
                "Canonical site forwarding requires a representative static "
                f"E5 endpoint for {site_id!r}; router fallback is forbidden."
            )
        endpoint = device_by_id.get(destination.device_id)
        if (
            endpoint is None
            or endpoint.site_id != site_id
            or destination.device_id not in linked_device_ids
        ):
            raise ValueError(
                "Canonical site forwarding representative endpoint is not "
                f"present and linked in projected E4: {destination.device_id!r}."
            )
        destination_by_site[site_id] = destination

    checks: list[CPScaleSiteForwardingCheck] = []
    for from_site, to_site in (
        (source_site_id, destination_site_id),
        (destination_site_id, source_site_id),
    ):
        source_device = edge_by_site[from_site]
        destination_router = edge_by_site[to_site]
        action = destination_by_site[to_site]
        destination_device = device_by_id[action.device_id]
        direction = f"{from_site}-to-{to_site}"
        checks.append(CPScaleSiteForwardingCheck(
            id=f"forwarding/{flows[0].id}/{direction}/{action.id}",
            direction=direction,
            traffic_flow_id=flows[0].id,
            source_site_id=from_site,
            destination_site_id=to_site,
            source_device_id=source_device.id,
            source_device_name=source_device.name,
            destination_device_id=destination_device.id,
            destination_device_name=destination_device.name,
            destination_router_id=destination_router.id,
            destination_action_id=action.id,
            destination_segment_id=action.segment_id,
            destination_ipv4=action.ipv4,
            source_topology_hash=projection.topology.physical_identity_hash,
            source_configuration_hash=projection.configuration.semantic_hash,
        ))
    if len({item.id for item in checks}) != len(checks):
        raise ValueError("Canonical site forwarding produced duplicate check IDs.")
    return tuple(checks)


def _stage_includes_device(
    stage: CPScaleCanonicalStage,
    device_id: str,
    site_id: str,
    zone_id: str,
) -> bool:
    order = _CANONICAL_STAGE_ORDER[stage]
    if device_id in _CORE_ROUTER_IDS:
        return True
    if (
        order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.ROUTER4_SWITCH10]
        and device_id == SW10
    ):
        return True
    if order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.FLOOR1] and zone_id == Z1:
        return True
    if order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.FLOOR2] and zone_id == Z2:
        return True
    if (
        order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.FLOOR3]
        and zone_id in {ZC, ZD}
    ):
        return True
    if (
        order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.ROUTER0_BRANCH]
        and site_id == MULTILAYER
    ):
        return True
    return (
        order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.ROUTER3_BRANCH]
        and site_id == SMALL
    )


def _project_stage_configuration(
    full: ConfigurationPlan,
    topology: TopologyPlan,
    stage: CPScaleCanonicalStage,
) -> ConfigurationPlan:
    selected_device_ids = {item.id for item in topology.devices}
    selected_link_ids = {item.id for item in topology.links}
    active_sites = _active_lan_sites(stage)

    def in_scope(action) -> bool:
        if action.device_id not in selected_device_ids:
            return False
        source_link_id = getattr(action, "source_link_id", "")
        if source_link_id and source_link_id not in selected_link_ids:
            return False
        endpoint_ids = set(getattr(action, "endpoint_ids", ()))
        if endpoint_ids and not endpoint_ids <= selected_device_ids:
            return False
        if (
            action.action_type is ConfigurationActionType.CONFIGURE_DHCP_POOL
            and action.site_id not in active_sites
        ):
            return False
        return True

    actions = [
        item.model_copy(deep=True) for item in full.actions if in_scope(item)
    ]
    action_ids = {item.id for item in actions}
    missing_dependencies = sorted({
        dependency
        for item in actions
        for dependency in [*item.depends_on, *item.apply_dependencies]
        if dependency not in action_ids
    })
    if missing_dependencies:
        raise ValueError(
            f"Canonical stage {stage.value!r} has omitted configuration "
            "dependencies: " + ", ".join(missing_dependencies)
        )

    devices = []
    for item in full.devices:
        if item.device_id not in selected_device_ids:
            continue
        device_action_ids = [
            identifier for identifier in item.action_ids if identifier in action_ids
        ]
        required = sorted({
            action.required_capability
            for action in actions
            if action.device_id == item.device_id and action.required_capability
        })
        devices.append(item.model_copy(update={
            "action_ids": device_action_ids,
            "required_capabilities": required,
        }))
    configuration = ConfigurationPlan(
        id=f"cfg_cp-scale-canonical-{stage.value}",
        source_topology_id=topology.id,
        source_topology_hash=topology.physical_identity_hash,
        source_topology_hash_schema="physical-topology-v2",
        actions=actions,
        devices=devices,
        verification_expectations=[
            item.model_copy(deep=True)
            for item in full.verification_expectations
            if item.action_id in action_ids
        ],
    )
    configuration.semantic_hash = configuration_plan_semantic_hash(configuration)
    return configuration


def _project_stage_control_plane(
    composition: EnterpriseReferenceComposition,
    topology: TopologyPlan,
    configuration: ConfigurationPlan,
    stage: CPScaleCanonicalStage,
    *,
    control_plane_capabilities: (
        dict[str, ControlPlaneCapabilityProfile] | None
    ),
) -> ControlPlanePlan:
    assert composition.topology is not None
    canonical = cp_scale_canonical_control_plane_intent(composition.topology)
    stp_sites = _completed_stp_sites(stage)
    intent = canonical.model_copy(update={
        "id": f"control-plane/cp-scale-canonical/{stage.value}",
        "stp_domains": [
            item for item in canonical.stp_domains if item.site_id in stp_sites
        ],
    })
    compiled = compile_enterprise_control_plane(
        intent,
        topology,
        configuration,
        capabilities=(
            control_plane_capabilities
            if control_plane_capabilities is not None
            else packet_tracer_control_plane_capabilities()
        ),
        traffic_flows=(
            [
                item for item in composition.enterprise.traffic_flows
                if item.source_site_id in _active_lan_sites(stage)
                and item.destination_site_id in _active_lan_sites(stage)
            ]
            if composition.enterprise is not None else None
        ),
    )
    if not compiled.is_valid or compiled.plan is None:
        raise ValueError(
            f"Canonical stage {stage.value!r} control plane did not compile: "
            + "; ".join(item.message for item in compiled.issues)
        )
    control = compiled.plan
    active_prefixes = {
        LARGE: "172.16.",
        SMALL: "172.17.",
        MULTILAYER: "172.18.",
    }
    advertised_prefixes = {
        active_prefixes[item] for item in _active_lan_sites(stage)
    }
    control.verification_expectations = [
        item for item in control.verification_expectations
        if item.kind is not ControlPlaneVerificationKind.ROUTE_PRESENT
        or (
            int(item.expected.get("prefix_length", -1)) == 30
            and str(item.expected.get("network", "")).startswith("10.0.0.")
        )
        or (
            int(item.expected.get("prefix_length", -1)) == 24
            and any(
                str(item.expected.get("network", "")).startswith(prefix)
                for prefix in advertised_prefixes
            )
        )
    ]
    control.semantic_hash = control_plane_plan_semantic_hash(control)
    return control


def _active_lan_sites(stage: CPScaleCanonicalStage) -> set[str]:
    order = _CANONICAL_STAGE_ORDER[stage]
    sites: set[str] = set()
    if order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.ROUTER4_SWITCH10]:
        sites.add(LARGE)
    if order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.ROUTER0_BRANCH]:
        sites.add(MULTILAYER)
    if order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.ROUTER3_BRANCH]:
        sites.add(SMALL)
    return sites


def _completed_stp_sites(stage: CPScaleCanonicalStage) -> set[str]:
    order = _CANONICAL_STAGE_ORDER[stage]
    sites: set[str] = set()
    if order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.FLOOR3]:
        sites.add(LARGE)
    if order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.ROUTER0_BRANCH]:
        sites.add(MULTILAYER)
    if order >= _CANONICAL_STAGE_ORDER[CPScaleCanonicalStage.ROUTER3_BRANCH]:
        sites.add(SMALL)
    return sites


def project_cp_scale_routing_core(
    composition: EnterpriseReferenceComposition,
    *,
    control_plane_capabilities: (
        dict[str, ControlPlaneCapabilityProfile] | None
    ) = None,
) -> CPScaleRoutingCore:
    """Project the exact three-router LIVE slice from a canonical composition.

    The LAN subinterfaces remain in E5 so the RIP process retains the canonical
    classful site statements and passive-interface policy.  Learned-route
    expectations are narrowed to the three physically operational /30 transit
    foundations; the LAN trunks are intentionally outside this first slice.
    """

    if (
        not composition.valid
        or composition.enterprise is None
        or composition.topology is None
        or composition.configuration is None
    ):
        raise ValueError("A complete canonical composition is required.")

    full_topology = composition.topology
    router_ids = {
        item.id for item in full_topology.devices if item.name in _CORE_ROUTER_NAMES
    }
    if len(router_ids) != 3:
        raise ValueError("The canonical composition does not contain the routing core.")
    core_topology = full_topology.model_copy(deep=True)
    core_topology.id = "cp-scale-canonical-routing-core"
    core_topology.name = "CP-SCALE canonical routing core"
    core_topology.devices = [
        item for item in core_topology.devices if item.id in router_ids
    ]
    core_topology.modules = [
        item for item in core_topology.modules if item.device in _CORE_ROUTER_NAMES
    ]
    core_topology.links = [
        item for item in core_topology.links
        if item.device_a_id in router_ids and item.device_b_id in router_ids
    ]
    stamp_topology_hashes(core_topology)

    selected_actions = [
        item.model_copy(deep=True)
        for item in composition.configuration.actions
        if item.device_id in router_ids and item.action_type in _CORE_CONFIGURATION_TYPES
    ]
    selected_ids = {item.id for item in selected_actions}
    for action in selected_actions:
        action.depends_on = [
            item for item in action.depends_on if item in selected_ids
        ]
        action.apply_dependencies = list(action.depends_on)
    selected_expectations = [
        item.model_copy(deep=True)
        for item in composition.configuration.verification_expectations
        if item.action_id in selected_ids
    ]
    selected_devices = []
    for item in composition.configuration.devices:
        if item.device_id not in router_ids:
            continue
        action_ids = [identifier for identifier in item.action_ids if identifier in selected_ids]
        required = sorted({
            action.required_capability
            for action in selected_actions
            if action.device_id == item.device_id and action.required_capability
        })
        selected_devices.append(item.model_copy(update={
            "action_ids": action_ids,
            "required_capabilities": required,
        }))
    core_configuration = ConfigurationPlan(
        id="cfg_cp-scale-canonical-routing-core",
        source_topology_id=core_topology.id,
        source_topology_hash=core_topology.physical_identity_hash,
        source_topology_hash_schema="physical-topology-v2",
        actions=selected_actions,
        devices=selected_devices,
        verification_expectations=selected_expectations,
    )
    core_configuration.semantic_hash = configuration_plan_semantic_hash(
        core_configuration,
    )

    canonical_control = cp_scale_canonical_control_plane_intent(full_topology)
    routing_only = canonical_control.model_copy(update={"stp_domains": []})
    compiled_control = compile_enterprise_control_plane(
        routing_only,
        core_topology,
        core_configuration,
        capabilities=(
            control_plane_capabilities
            if control_plane_capabilities is not None
            else packet_tracer_control_plane_capabilities()
        ),
    )
    if not compiled_control.is_valid or compiled_control.plan is None:
        raise ValueError(
            "Canonical routing-core control plane did not compile: "
            + "; ".join(item.message for item in compiled_control.issues)
        )
    core_control = compiled_control.plan
    core_control.verification_expectations = [
        item for item in core_control.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS
        or (
            item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
            and int(item.expected.get("prefix_length", -1)) == 30
            and str(item.expected.get("network", "")).startswith("10.0.0.")
        )
    ]
    core_control.verification_expectations.sort(key=lambda item: (
        0 if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS else 1,
        item.id,
    ))
    core_control.semantic_hash = control_plane_plan_semantic_hash(core_control)

    return CPScaleRoutingCore(
        topology=core_topology,
        configuration=core_configuration,
        control_plane=core_control,
        forwarding_checks={
            "Router4": "10.0.0.10",
            "Router0": "10.0.0.6",
            "Router3": "10.0.0.1",
        },
    )
