"""Fail-closed gates for the persistent canonical CP-SCALE LIVE session."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    compose_cp_scale_canonical,
    project_cp_scale_canonical_delta,
    project_cp_scale_canonical_stage,
)
from src.packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    canonical_capability_probe_error,
    canonical_required_capability_probes,
    canonical_checkpoint_repository_error,
    canonical_cleanup_restoration_error,
    canonical_configuration_retryable_operational_unknown,
    canonical_stage_configuration_error,
    canonical_stage_resume_error,
)
from src.packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
    configuration_application_contradiction,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
)
from src.packet_tracer_mcp.application.use_cases.reconcile_canonical_stage import (
    canonical_delta_deployment_error,
    reconcile_canonical_stage_deployment,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    FieldVerificationStatus,
    VerificationResult,
    VoiceSignalBarrierResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentLinkBinding,
    DeploymentLinkEndpoint,
    EnvironmentFingerprint,
    build_deployment_manifest,
)
from src.packet_tracer_mcp.domain.enterprise.models.evidence import (
    EvidenceFreshness,
    EvidenceRecord,
    EvidenceStrength,
    ObservationStatus,
    SupportStatus,
    VerificationMethod,
    VerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import (
    ApplicationExecutionJournal,
    MutationDisposition,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentItemResult,
    PhysicalDeploymentResult,
    PhysicalDeploymentStatus,
    PhysicalDeviceObservation,
    PhysicalLinkObservation,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceLinkObservation,
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    BackendVersionProvenance,
    CapabilityProbeResult,
    CapabilitySnapshot,
    CleanupStatus,
    DeviceIdentity,
    DiscoverySource,
    ModelIdentityStatus,
    ProbeExecutionStatus,
    ProbeSession,
    ProbeSessionResult,
    RuntimeDeviceDescriptor,
)


_VERSION = "9.0.1.0858"
_FINGERPRINT = EnvironmentFingerprint(
    backend="packet_tracer",
    backend_version=_VERSION,
    bridge_transport="http",
    runtime_mode="live",
)


def _supported_capability_snapshot(
    model: str,
    capabilities: list[str],
) -> CapabilitySnapshot:
    session = ProbeSession(
        session_id="probe-cp-scale",
        packet_tracer_version=_VERSION,
        mutations=[f"temporary-device:{model}"],
        cleanup_status=CleanupStatus.CLEAN,
    )
    return CapabilitySnapshot(
        packet_tracer_version=_VERSION,
        backend_version_provenance=BackendVersionProvenance.DECLARED_ENVIRONMENT,
        initial_inventory_hash="empty-baseline",
        final_inventory_hash="empty-baseline",
        inventory_restored=True,
        session=ProbeSessionResult(
            session=session,
            devices=[RuntimeDeviceDescriptor(
                identity=DeviceIdentity(
                    canonical_id=model,
                    runtime_id=model,
                    display_name=model,
                    packet_tracer_version=_VERSION,
                    status=ModelIdentityStatus.CATALOG_MATCHED,
                ),
                discovery_source=DiscoverySource.CONTROLLED_CREATE_PROBE,
                observed=True,
            )],
            results=[CapabilityProbeResult(
                probe_id=f"{capability}-probe",
                model=model,
                capability=capability,
                status=CapabilityStatus.SUPPORTED,
                execution_status=ProbeExecutionStatus.VERIFIED,
                evidence_source=EvidenceSource.CONTROLLED_PROBE,
                configured=True,
                verified=True,
                packet_tracer_version=_VERSION,
            ) for capability in capabilities],
            cleanup_deleted=["__MCP_PROBE_cp_scale_01"],
        ),
    )


def test_canonical_capability_prequalification_is_plan_derived_and_fail_closed():
    composition = compose_cp_scale_canonical(packet_tracer_version=_VERSION)

    required = canonical_required_capability_probes(composition)

    # `supports_cme` joins the 2811's set because the canonical voice plan puts
    # a call control on it. E7 skips an action whose model capability is
    # unmeasured, so without prequalifying it a stage would apply no voice and
    # still look like it had.
    assert required == {
        "2811": ["layer3", "supports_cme", "supports_dhcp_server"],
        "2960-24TT": ["supports_trunk", "supports_vlan"],
        "3560-24PS": ["supports_trunk", "supports_vlan"],
        "3650-24PS": ["supports_trunk", "supports_vlan"],
    }
    snapshot = _supported_capability_snapshot(
        "2960-24TT", required["2960-24TT"],
    )
    assert canonical_capability_probe_error(
        snapshot,
        model="2960-24TT",
        capabilities=required["2960-24TT"],
        packet_tracer_version=_VERSION,
    ) == ""

    unknown = snapshot.model_copy(deep=True)
    unknown.session.results[0].status = CapabilityStatus.UNKNOWN
    assert "unknown" in canonical_capability_probe_error(
        unknown,
        model="2960-24TT",
        capabilities=required["2960-24TT"],
        packet_tracer_version=_VERSION,
    ).casefold()

    dirty = snapshot.model_copy(deep=True)
    dirty.session.session.cleanup_status = CleanupStatus.DIRTY_SESSION
    assert "cleanup" in canonical_capability_probe_error(
        dirty,
        model="2960-24TT",
        capabilities=required["2960-24TT"],
        packet_tracer_version=_VERSION,
    ).casefold()

    unrestored = snapshot.model_copy(deep=True)
    unrestored.inventory_restored = False
    assert "restor" in canonical_capability_probe_error(
        unrestored,
        model="2960-24TT",
        capabilities=required["2960-24TT"],
        packet_tracer_version=_VERSION,
    ).casefold()


def _floor1_configuration_result():
    composition = compose_cp_scale_canonical(packet_tracer_version=_VERSION)
    projection = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.FLOOR1,
    )
    plan = projection.configuration
    expectations = {item.id: item for item in plan.verification_expectations}
    verification_results = []
    for expectation in plan.verification_expectations:
        if expectation.kind is VerificationKind.DHCP_POOL:
            verification_results.append(VerificationResult(
                expectation_id=expectation.id,
                action_id=expectation.action_id,
                status=ActionExecutionStatus.UNOBSERVABLE,
                evidence_method="runtime_observability_limit",
                fresh_evidence=False,
                fields={
                    field: FieldVerificationStatus.UNOBSERVABLE
                    for field in expectation.expected
                },
            ))
        elif expectation.kind is VerificationKind.ENDPOINT_ADDRESSING:
            verification_results.append(VerificationResult(
                expectation_id=expectation.id,
                action_id=expectation.action_id,
                status=ActionExecutionStatus.PARTIAL,
                evidence_method="structured_endpoint_getters",
                fresh_evidence=True,
                fields={
                    "ipv4": FieldVerificationStatus.VERIFIED,
                    "netmask": FieldVerificationStatus.VERIFIED,
                    "gateway": FieldVerificationStatus.UNOBSERVABLE,
                    "dns": FieldVerificationStatus.UNOBSERVABLE,
                },
            ))
        elif expectation.kind is VerificationKind.TRUNK:
            verification_results.append(VerificationResult(
                expectation_id=expectation.id,
                action_id=expectation.action_id,
                status=ActionExecutionStatus.VERIFIED,
                evidence_method="fresh_show_interfaces_trunk",
                fresh_evidence=True,
                fields={
                    "interface": FieldVerificationStatus.VERIFIED,
                    "status": FieldVerificationStatus.VERIFIED,
                    "allowed_vlans": FieldVerificationStatus.VERIFIED,
                    "active_vlans": FieldVerificationStatus.VERIFIED,
                    "forwarding_vlans": FieldVerificationStatus.VERIFIED,
                },
            ))
        else:
            verification_results.append(VerificationResult(
                expectation_id=expectation.id,
                action_id=expectation.action_id,
                status=ActionExecutionStatus.VERIFIED,
                evidence_method="fresh_typed_readback",
                fresh_evidence=True,
                fields={"state": FieldVerificationStatus.VERIFIED},
            ))
    result = ConfigurationApplicationResult(
        config_plan_id=plan.id,
        config_semantic_hash=plan.semantic_hash,
        source_topology_hash=plan.source_topology_hash,
        status=ConfigurationApplicationStatus.PARTIAL,
        action_results=[
            ActionApplicationResult(
                action_id=item.id,
                status=ActionExecutionStatus.APPLIED,
                disposition=MutationDisposition.CHANGED,
            )
            for item in plan.actions
        ],
        verification_results=verification_results,
    )
    assert expectations
    return plan, result


def test_canonical_configuration_accepts_only_exact_known_observability_ceilings():
    plan, result = _floor1_configuration_result()

    assert canonical_stage_configuration_error(plan, result) == ""

    unknown_action = result.model_copy(deep=True)
    unknown_action.action_results[0].status = ActionExecutionStatus.UNKNOWN
    assert "unknown" in canonical_stage_configuration_error(
        plan, unknown_action,
    ).casefold()

    endpoint = next(
        item for item in result.verification_results
        if item.status is ActionExecutionStatus.PARTIAL
    )
    unknown_field = result.model_copy(deep=True)
    next(
        item for item in unknown_field.verification_results
        if item.expectation_id == endpoint.expectation_id
    ).fields["gateway"] = FieldVerificationStatus.UNKNOWN
    assert "unknown" in canonical_stage_configuration_error(
        plan, unknown_field,
    ).casefold()

    non_ceiling = result.model_copy(deep=True)
    other = next(
        item for item in non_ceiling.verification_results
        if item.status is ActionExecutionStatus.VERIFIED
    )
    other.status = ActionExecutionStatus.UNOBSERVABLE
    assert "unobservable" in canonical_stage_configuration_error(
        plan, non_ceiling,
    ).casefold()


def test_canonical_gate_admits_only_typed_voice_signal_pending_bootstrap():
    plan, result = _floor1_configuration_result()
    expectations = {
        item.id: item for item in plan.verification_expectations
    }
    pending = result.model_copy(deep=True)
    voice_expectations = [
        item for item in plan.verification_expectations
        if (
            item.kind is VerificationKind.ACCESS_PORT
            and "voice_vlan_id" in item.expected
        )
    ]
    voice_action_ids = {item.action_id for item in voice_expectations}
    for item in pending.action_results:
        if item.action_id in voice_action_ids:
            item.status = ActionExecutionStatus.PARTIAL
    for item in pending.verification_results:
        if item.action_id in voice_action_ids:
            item.status = ActionExecutionStatus.PARTIAL
            item.evidence_method = ""
            item.fresh_evidence = False
            item.fields = {}
            item.message = "Voice VLAN verification is pending bootstrap."
    pending.voice_signal_barrier = VoiceSignalBarrierResult(
        required=True,
        deferred_action_ids=sorted(voice_action_ids),
        foundation_status=ActionExecutionStatus.VERIFIED,
        signal_status=ActionExecutionStatus.INTENDED,
    )

    assert canonical_stage_configuration_error(plan, pending)
    assert canonical_stage_configuration_error(
        plan,
        pending,
        allow_deferred_voice_signal=True,
    ) == ""
    l3 = next(
        item for item in pending.verification_results
        if expectations[item.expectation_id].kind
        is VerificationKind.L3_INTERFACE
    )
    l3.fields["status"] = FieldVerificationStatus.UNKNOWN
    l3.fields["protocol"] = FieldVerificationStatus.UNKNOWN
    assert not canonical_configuration_retryable_operational_unknown(
        plan, pending,
    )
    assert canonical_configuration_retryable_operational_unknown(
        plan,
        pending,
        allow_deferred_voice_signal=True,
    )


def test_an_unreadable_phone_voice_vlan_is_partial_but_cp_scale_fails_closed():
    plan, result = _floor1_configuration_result()
    expectations = {item.id: item for item in plan.verification_expectations}
    phone = next(
        item for item in plan.verification_expectations
        if item.kind is VerificationKind.ACCESS_PORT
        and "voice_vlan_id" in item.expected
    )
    observed = next(
        item for item in result.verification_results
        if item.expectation_id == phone.id
    )
    observed.status = ActionExecutionStatus.PARTIAL
    observed.evidence_method = "switch_port_object_state"
    observed.fresh_evidence = True
    observed.fields = {
        "device_identity": FieldVerificationStatus.VERIFIED,
        "interface": FieldVerificationStatus.VERIFIED,
        "switchport_mode": FieldVerificationStatus.VERIFIED,
        "vlan_id": FieldVerificationStatus.VERIFIED,
        "voice_vlan_id": FieldVerificationStatus.UNOBSERVABLE,
    }

    assert expectations[phone.id].expected["voice_vlan_id"] == 20
    assert configuration_application_contradiction(result) == ""
    error = canonical_stage_configuration_error(plan, result)
    assert "only fresh VERIFIED evidence is allowed" in error


def test_canonical_configuration_accepts_an_absent_address_channel_ceiling():
    """An AccessPoint-PT holds no address on this build, and says so cleanly.

    Measured on 9.0.1.0858: both its ports come up powered and neither exposes
    `getIpAddress`; nor does the device. Its designed management address can be
    applied and can never be read back, which is the same standing limit the
    DHCP-pool ceiling already accepts. Admitted on the same terms -- every field
    UNOBSERVABLE, nothing claimed -- and keyed on the exact evidence method, so
    an interface that was never found is still a failure.
    """
    plan, result = _floor1_configuration_result()
    expectations = {item.id: item for item in plan.verification_expectations}
    endpoint = next(
        item for item in result.verification_results
        if expectations[item.expectation_id].kind
        is VerificationKind.ENDPOINT_ADDRESSING
    )
    expected = expectations[endpoint.expectation_id].expected
    endpoint.status = ActionExecutionStatus.UNOBSERVABLE
    endpoint.evidence_method = "structured_endpoint_getters_absent"
    endpoint.fresh_evidence = False
    endpoint.fields = {
        name: FieldVerificationStatus.UNOBSERVABLE for name in expected
    }

    assert canonical_stage_configuration_error(plan, result) == ""

    # A port that was never found reaches the generic observability limit, and
    # that must stay a failure: not having looked is not the same as having
    # measured that there is nothing to look at.
    not_found = result.model_copy(deep=True)
    next(
        item for item in not_found.verification_results
        if item.expectation_id == endpoint.expectation_id
    ).evidence_method = "runtime_observability_limit"
    assert canonical_stage_configuration_error(plan, not_found) != ""

    # Nor may an absent channel come back carrying any claim at all.
    claimed = result.model_copy(deep=True)
    next(
        item for item in claimed.verification_results
        if item.expectation_id == endpoint.expectation_id
    ).fields["ipv4"] = FieldVerificationStatus.VERIFIED
    assert canonical_stage_configuration_error(plan, claimed) != ""


def test_canonical_configuration_requires_exact_trunk_vlan_traversal_proof():
    plan, result = _floor1_configuration_result()
    expectations = {item.id: item for item in plan.verification_expectations}
    trunk = next(
        item for item in result.verification_results
        if expectations[item.expectation_id].kind is VerificationKind.TRUNK
    )
    trunk.status = ActionExecutionStatus.VERIFIED
    trunk.evidence_method = "fresh_show_interfaces_trunk"
    trunk.fresh_evidence = True
    trunk.fields = {
        "interface": FieldVerificationStatus.VERIFIED,
        "status": FieldVerificationStatus.VERIFIED,
        "allowed_vlans": FieldVerificationStatus.VERIFIED,
        "active_vlans": FieldVerificationStatus.VERIFIED,
        "forwarding_vlans": FieldVerificationStatus.VERIFIED,
    }

    assert canonical_stage_configuration_error(plan, result) == ""

    unknown = result.model_copy(deep=True)
    next(
        item for item in unknown.verification_results
        if item.expectation_id == trunk.expectation_id
    ).fields["forwarding_vlans"] = FieldVerificationStatus.UNKNOWN
    assert "unknown" in canonical_stage_configuration_error(
        plan, unknown,
    ).casefold()

    stale = result.model_copy(deep=True)
    next(
        item for item in stale.verification_results
        if item.expectation_id == trunk.expectation_id
    ).fresh_evidence = False
    assert "trunk" in canonical_stage_configuration_error(plan, stale).casefold()


def test_only_l3_carrier_unknown_is_retryable_after_typed_convergence_proof():
    plan, result = _floor1_configuration_result()
    expectations = {item.id: item for item in plan.verification_expectations}
    l3 = next(
        item for item in result.verification_results
        if expectations[item.expectation_id].kind is VerificationKind.L3_INTERFACE
    )
    l3.fields = {
        "interface": FieldVerificationStatus.VERIFIED,
        "ipv4": FieldVerificationStatus.VERIFIED,
        "administrative_state": FieldVerificationStatus.VERIFIED,
        "status": FieldVerificationStatus.UNKNOWN,
        "protocol": FieldVerificationStatus.UNKNOWN,
    }
    assert canonical_stage_configuration_error(plan, result)
    assert canonical_configuration_retryable_operational_unknown(plan, result)

    l3.fields["ipv4"] = FieldVerificationStatus.UNKNOWN
    assert not canonical_configuration_retryable_operational_unknown(plan, result)


def _delta_result(delta, *, switch_disposition, link_disposition):
    items = []
    for device in delta.devices:
        disposition = (
            MutationDisposition.NO_OP
            if device.name == "Router4" else switch_disposition
        )
        items.append(PhysicalDeploymentItemResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            status="observed",
            disposition=disposition,
            applied=disposition is MutationDisposition.CHANGED,
            observed=True,
        ))
    for link in delta.links:
        items.append(PhysicalDeploymentItemResult(
            target_id=link.id,
            target_kind=PhysicalObjectKind.LINK,
            status="observed",
            disposition=link_disposition,
            applied=link_disposition is MutationDisposition.CHANGED,
            observed=True,
        ))
    return PhysicalDeploymentResult(
        topology_id=delta.id,
        physical_topology_hash=delta.physical_identity_hash,
        deployment_id="delta",
        environment_fingerprint=_FINGERPRINT,
        status=PhysicalDeploymentStatus.VERIFIED,
        item_results=items,
        execution_journal=ApplicationExecutionJournal(plan_id=delta.id),
    )


def test_delta_ownership_rejects_adopted_new_device_or_link():
    composition = compose_cp_scale_canonical(packet_tracer_version=_VERSION)
    previous = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTING_CORE,
    ).topology
    current = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER4_SWITCH10,
    ).topology
    delta = project_cp_scale_canonical_delta(previous, current)

    changed = _delta_result(
        delta,
        switch_disposition=MutationDisposition.CHANGED,
        link_disposition=MutationDisposition.CHANGED,
    )
    assert canonical_delta_deployment_error(previous, delta, changed) == ""

    adopted_switch = _delta_result(
        delta,
        switch_disposition=MutationDisposition.NO_OP,
        link_disposition=MutationDisposition.CHANGED,
    )
    assert "new physical device" in canonical_delta_deployment_error(
        previous, delta, adopted_switch,
    ).casefold()

    adopted_link = _delta_result(
        delta,
        switch_disposition=MutationDisposition.CHANGED,
        link_disposition=MutationDisposition.NO_OP,
    )
    assert "link" in canonical_delta_deployment_error(
        previous, delta, adopted_link,
    ).casefold()


class _CoreObservationRuntime:
    def __init__(self, topology, *, missing_port: tuple[str, str] | None = None):
        ports = {item.name: set() for item in topology.devices}
        for link in topology.links:
            ports[link.device_a].add(link.port_a)
            ports[link.device_b].add(link.port_b)
        for module in topology.modules:
            ports[module.device].update(
                f"Serial{module.slot.split('/')[0]}/{index}" for index in range(4)
            )
        if missing_port:
            ports[missing_port[0]].discard(missing_port[1])
        self.ports = {name: sorted(values) for name, values in ports.items()}
        self.topology = topology
        self.workspace = PhysicalWorkspaceObservation(
            devices=[PhysicalWorkspaceDeviceObservation(
                name=item.name,
                model=item.model,
                ports=self.ports[item.name],
            ) for item in topology.devices],
            links=[PhysicalWorkspaceLinkObservation(
                class_name="Serial",
                device_a=item.device_a,
                port_a=item.port_a,
                device_b=item.device_b,
                port_b=item.port_b,
            ) for item in topology.links],
            message="fresh_complete_workspace_inventory",
        )

    def observe_workspace(self):
        return self.workspace.model_copy(deep=True)

    def observe_device(self, device):
        return PhysicalDeviceObservation(
            target_id=device.id,
            deployed_name=device.name,
            model=device.model,
            interfaces=self.ports[device.name],
            runtime_identifier=f"runtime/{device.id}",
            runtime_identifier_stable=True,
            runtime_fingerprint=f"fingerprint/{device.id}",
        )

    def observe_link(self, link):
        return PhysicalLinkObservation(
            target_id=link.id,
            device_a=link.device_a,
            port_a=link.port_a,
            device_b=link.device_b,
            port_b=link.port_b,
            runtime_link_identifier=f"runtime/{link.id}",
            runtime_link_identity_observed=True,
        )


def _verified_core_ledger(topology, runtime):
    inventory = [RuntimeConfigurationTarget(
        device_name=item.name,
        model=item.model,
        interfaces=runtime.ports[item.name],
        runtime_identifier=f"runtime/{item.id}",
        runtime_identifier_stable=True,
        runtime_fingerprint=f"fingerprint/{item.id}",
    ) for item in topology.devices]
    bindings = [DeploymentLinkBinding(
        semantic_link_id=item.id,
        endpoint_a=DeploymentLinkEndpoint(
            semantic_device_id=item.device_a_id,
            interface=item.port_a,
        ),
        endpoint_b=DeploymentLinkEndpoint(
            semantic_device_id=item.device_b_id,
            interface=item.port_b,
        ),
        runtime_link_identifier=f"runtime/{item.id}",
        runtime_link_identity_observed=True,
    ) for item in topology.links]
    manifest = build_deployment_manifest(
        topology,
        inventory,
        fingerprint=_FINGERPRINT,
        deployment_id="core-ledger",
        link_bindings=bindings,
    )
    items = [
        PhysicalDeploymentItemResult(
            target_id=item.id,
            target_kind=PhysicalObjectKind.DEVICE,
            status="observed",
            disposition=MutationDisposition.CHANGED,
            applied=True,
            observed=True,
        )
        for item in topology.devices
    ]
    items.extend(
        PhysicalDeploymentItemResult(
            target_id=f"{item.device}:{item.slot}:{item.module}",
            target_kind=PhysicalObjectKind.MODULE,
            status="observed",
            disposition=MutationDisposition.CHANGED,
            applied=True,
            observed=True,
        )
        for item in topology.modules
    )
    items.extend(
        PhysicalDeploymentItemResult(
            target_id=item.id,
            target_kind=PhysicalObjectKind.LINK,
            status="observed",
            disposition=MutationDisposition.CHANGED,
            applied=True,
            observed=True,
        )
        for item in topology.links
    )
    module_evidence = []
    for module in topology.modules:
        module_id = f"{module.device}:{module.slot}:{module.module}"
        expected_ports = [
            f"Serial{module.slot.split('/')[0]}/{index}" for index in range(4)
        ]
        module_evidence.append(EvidenceRecord(
            id=f"e4/module-effect/{module_id}",
            subject=module_id,
            claim="this transaction caused the complete module port effect",
            method=VerificationMethod.STRUCTURED_API,
            strength=EvidenceStrength.CLAIM_DIRECT,
            freshness=EvidenceFreshness.FRESH,
            backend=_FINGERPRINT.backend,
            backend_version=_FINGERPRINT.backend_version,
            environment_fingerprint=_FINGERPRINT.semantic_hash,
            observed_value={
                "device_name": module.device,
                "requested_slot": module.slot,
                "requested_module": module.module,
                "device_newly_owned": True,
                "expected_ports": expected_ports,
                "effect_verification_status": "verified",
            },
            support_status=SupportStatus.SUPPORTED,
            observation_status=ObservationStatus.OBSERVED,
            verification_status=VerificationStatus.VERIFIED,
        ))
    return PhysicalDeploymentResult(
        topology_id=topology.id,
        physical_topology_hash=topology.physical_identity_hash,
        deployment_id="core-ledger",
        environment_fingerprint=_FINGERPRINT,
        status=PhysicalDeploymentStatus.VERIFIED,
        item_results=items,
        manifest=manifest,
        execution_journal=ApplicationExecutionJournal(plan_id=topology.id),
        evidence_records=module_evidence,
    )


def test_cumulative_reconciliation_binds_causal_core_ledger_and_fresh_module_ports():
    composition = compose_cp_scale_canonical(packet_tracer_version=_VERSION)
    core = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTING_CORE,
    ).topology
    runtime = _CoreObservationRuntime(core)
    ledger = _verified_core_ledger(core, runtime)

    result = reconcile_canonical_stage_deployment(
        core,
        runtime,
        environment_fingerprint=_FINGERPRINT,
        verified_core_topology=core,
        verified_core_deployment=ledger,
        deployment_id="core-reconciled",
    )
    assert result.status is PhysicalDeploymentStatus.VERIFIED
    assert result.manifest is not None
    assert len([
        item for item in result.evidence_records
        if item.id.startswith("e4/cumulative-module-presence/")
    ]) == 3

    forged = ledger.model_copy(update={"evidence_records": []})
    forged_result = reconcile_canonical_stage_deployment(
        core,
        runtime,
        environment_fingerprint=_FINGERPRINT,
        verified_core_topology=core,
        verified_core_deployment=forged,
        deployment_id="forged",
    )
    assert forged_result.status is PhysicalDeploymentStatus.FAILED
    assert forged_result.manifest is None

    missing_runtime = _CoreObservationRuntime(
        core, missing_port=("Router0", "Serial1/3"),
    )
    missing_result = reconcile_canonical_stage_deployment(
        core,
        missing_runtime,
        environment_fingerprint=_FINGERPRINT,
        verified_core_topology=core,
        verified_core_deployment=ledger,
        deployment_id="missing-port",
    )
    assert missing_result.status is PhysicalDeploymentStatus.FAILED
    assert missing_result.manifest is None
    assert any("Serial1/3" in item for item in missing_result.errors)


def _empty_workspace(*, pdd_model: str = "Power Distribution Device"):
    return PhysicalWorkspaceObservation(
        devices=[PhysicalWorkspaceDeviceObservation(
            name="Power Distribution Device0",
            model=pdd_model,
            ports=[],
            backend_managed=True,
        )],
        message="fresh_complete_workspace_inventory",
    )


def test_cleanup_and_resume_compare_exact_snapshots_not_generic_emptiness():
    baseline = _empty_workspace()
    same = _empty_workspace()
    replaced = _empty_workspace(pdd_model="Other Power Object")
    assert canonical_cleanup_restoration_error(baseline, same, same) == ""
    assert "baseline" in canonical_cleanup_restoration_error(
        baseline, replaced, replaced,
    ).casefold()

    topology = project_cp_scale_canonical_stage(
        compose_cp_scale_canonical(packet_tracer_version=_VERSION),
        CPScaleCanonicalStage.ROUTING_CORE,
    ).topology
    devices = [PhysicalWorkspaceDeviceObservation(
        name=item.name,
        model=item.model,
        ports=["FastEthernet0/0", "Serial1/0", "Serial1/1", "Serial1/2", "Serial1/3"],
    ) for item in topology.devices]
    links = [PhysicalWorkspaceLinkObservation(
        class_name="Serial",
        device_a=item.device_a,
        port_a=item.port_a,
        device_b=item.device_b,
        port_b=item.port_b,
    ) for item in topology.links]
    retained = PhysicalWorkspaceObservation(
        devices=devices,
        links=links,
        message="fresh_complete_workspace_inventory",
    )
    drifted = retained.model_copy(deep=True)
    drifted.devices[0].ports.append("Serial1/7")
    assert canonical_stage_resume_error(retained, retained, topology) == ""
    assert "snapshot" in canonical_stage_resume_error(
        retained, drifted, topology,
    ).casefold()


def test_checkpoint_resume_requires_clean_pushed_unchanged_governed_source():
    assert canonical_checkpoint_repository_error(
        branch="feature/runtime-ripv2",
        upstream="personal/feature/runtime-ripv2",
        head="a" * 40,
        upstream_head="a" * 40,
        dirty=False,
        governed_source_changed=False,
    ) == ""
    assert "pushed" in canonical_checkpoint_repository_error(
        branch="feature/runtime-ripv2",
        upstream="personal/feature/runtime-ripv2",
        head="a" * 40,
        upstream_head="b" * 40,
        dirty=False,
        governed_source_changed=False,
    ).casefold()
    assert "source" in canonical_checkpoint_repository_error(
        branch="feature/runtime-ripv2",
        upstream="personal/feature/runtime-ripv2",
        head="a" * 40,
        upstream_head="a" * 40,
        dirty=False,
        governed_source_changed=True,
    ).casefold()
