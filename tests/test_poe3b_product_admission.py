"""POE-3B productive admission from persisted synthetic schema-3 probes."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    compose_cp_scale_canonical,
    project_cp_scale_canonical_delta,
    project_cp_scale_canonical_stage,
)
from src.packet_tracer_mcp.application.use_cases.plan_cp_scale_poe_capacity import (
    cp_scale_poe_capacity_qualification_plan,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCandidateStatus,
    EvidenceSource,
    PoEAuthorizedBinding,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    BackendVersionProvenance,
    CapabilityProbeResult,
    CapabilitySnapshot,
    CapabilityVerificationMethod,
    CleanupStatus,
    EphemeralUntitledWorkspaceSafetyEvidence,
    ProbeContext,
    ProbeExecutionStatus,
    ProbeIsolationLevel,
    ProbeSession,
    ProbeSessionResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.poe_capacity import (
    PoEModelQualificationPlan,
)
from src.packet_tracer_mcp.domain.enterprise.models.hardware import (
    EndpointPortBinding,
)
from src.packet_tracer_mcp.domain.enterprise.services.reference_hardware_planner import (
    ReferenceHardwarePlanner,
)
from src.packet_tracer_mcp.domain.enterprise.services.poe_pse_multiport_claims import (
    PoEPseBindingCapture,
    PoEPseMultiPortCapture,
    PoEPseMultiPortDeliveryScope,
    encode_poe_pse_multi_port_dimensions,
)
from src.packet_tracer_mcp.infrastructure.catalog.capability_providers import (
    ProbeCapabilityProvider,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    packet_tracer_enterprise_capability_adapter,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)


BUILD = "9.0.1.0858"
GATES = (
    "all_pagers_traversed",
    "attributable",
    "dispatch_integrity_valid",
    "expected_privileged_prompt_reached",
    "fresh",
    "no_pending_continuation",
    "observer_complete",
    "stable",
)
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


def _complete_ephemeral_safety() -> EphemeralUntitledWorkspaceSafetyEvidence:
    inventory = "a" * 64 + "|synthetic-pse-fixture"
    source_head = "b" * 40
    source_tree = "c" * 40
    return EphemeralUntitledWorkspaceSafetyEvidence(
        initial_device_count=0,
        final_device_count=0,
        initial_link_count=0,
        final_link_count=0,
        initial_saved_filename="",
        final_saved_filename="",
        authorized_file_operations=(),
        attempted_file_operations=(),
        denied_file_operations=(),
        invoked_file_operations=(),
        completed_file_operations=(),
        indeterminate_file_operations=(),
        initial_inventory_fingerprint=inventory,
        final_inventory_fingerprint=inventory,
        fixture_removed=True,
        initial_realtime=True,
        final_realtime=True,
        packet_tracer_pids_before=(4242,),
        packet_tracer_pids_after=(4242,),
        bridge_healthy_before=True,
        bridge_healthy_after=True,
        mailbox_entries_before=(),
        mailbox_entries_after=(),
        source_branch_before="test/poe3b-product-admission",
        source_branch_after="test/poe3b-product-admission",
        source_head_before=source_head,
        source_head_after=source_head,
        source_tree_before=source_tree,
        source_tree_after=source_tree,
        worktree_clean_before=True,
        worktree_clean_after=True,
        runtime_healthy=True,
        crash_detected=False,
        integrity_verified=True,
        session_reusable=True,
        positive_claim_allowed=True,
        failure_reasons=[],
    )


def _captures(
    bindings: tuple[PoEAuthorizedBinding, ...],
) -> tuple[PoEPseMultiPortCapture, ...]:
    captures = []
    for label, admin_mode, delivering in (
        ("AUTO_1", "auto", True),
        ("NEVER", "never", False),
        ("AUTO_2", "auto", True),
    ):
        captures.append(PoEPseMultiPortCapture(
            label=label,
            admin_mode=admin_mode,
            binding_captures=tuple(
                PoEPseBindingCapture(
                    switch_port=binding.switch_port,
                    endpoint_model=binding.endpoint_model,
                    endpoint_port=binding.endpoint_port,
                    oper_state="on" if delivering else "absent",
                    power_watts=10.0 if delivering else 0.0,
                    row_present=delivering,
                    delivering=delivering,
                )
                for binding in bindings
            ),
        ))
    return tuple(captures)


def _probe_result(
    model_plan: PoEModelQualificationPlan,
    *,
    run_number: int,
    bindings: tuple[PoEAuthorizedBinding, ...] | None = None,
) -> CapabilityProbeResult:
    admitted = bindings or model_plan.bindings
    experiment_id = (
        f"poe3b-product-{model_plan.candidate_model}-run-{run_number}"
    )
    scope = PoEPseMultiPortDeliveryScope(
        schema_version=3,
        switch_model=model_plan.candidate_model,
        packet_tracer_build=model_plan.packet_tracer_build,
        bindings=admitted,
        observer_id="SyntheticProductAdmissionObserver",
        experiment_id=experiment_id,
        observed_at=f"2026-09-09T18:00:{run_number:02d}Z",
        captures=_captures(admitted),
        gates=GATES,
        simultaneous_active_ports=len(admitted),
        cleanup_status="clean",
        inventory_restoration="restored",
    )
    return CapabilityProbeResult(
        probe_id="poe3b-multi-port-pse",
        model=model_plan.candidate_model,
        capability="supports_poe",
        status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.CONTROLLED_PROBE,
        configured=True,
        verified=True,
        observed_value=len(admitted),
        raw_summary=f"Synthetic contract fixture {experiment_id}.",
        packet_tracer_version=model_plan.packet_tracer_build,
        verification_method=CapabilityVerificationMethod.CLI_PLUS_READBACK,
        context=ProbeContext(
            probe_id="poe3b-multi-port-pse",
            probe_version="3",
            backend_version=model_plan.packet_tracer_build,
            device_model=model_plan.candidate_model,
            environment_fingerprint="synthetic-product-admission",
            initial_inventory_hash="d" * 64,
            final_inventory_hash="d" * 64,
            inventory_restored=True,
            isolation_level=ProbeIsolationLevel.FRESH_SESSION_REQUIRED,
            mutations=[f"temporary-device-attempt:{experiment_id}"],
            cleanup_status=CleanupStatus.CLEAN,
            result_status=CapabilityStatus.SUPPORTED,
            execution_status=ProbeExecutionStatus.VERIFIED,
            probe_fingerprint="e" * 64,
            live_session_safety=_complete_ephemeral_safety(),
        ),
        dimensions=encode_poe_pse_multi_port_dimensions(scope),
    )


def _persist_probe(
    store: CapabilitySnapshotStore,
    result: CapabilityProbeResult,
    *,
    run_number: int,
) -> None:
    store.save_runtime(CapabilitySnapshot(
        packet_tracer_version=BUILD,
        backend_version_provenance=BackendVersionProvenance.DIRECTLY_OBSERVED,
        environment_fingerprint="synthetic-product-admission",
        initial_inventory_hash="d" * 64,
        final_inventory_hash="d" * 64,
        inventory_restored=True,
        session=ProbeSessionResult(
            session=ProbeSession(
                session_id=f"poe3b-product-run-{run_number}",
                packet_tracer_version=BUILD,
                created_devices=[f"synthetic-probe-{run_number}"],
                mutations=[f"temporary-device-attempt:run-{run_number}"],
                cleanup_status=CleanupStatus.CLEAN,
            ),
            results=[result],
            cleanup_deleted=[f"synthetic-probe-{run_number}"],
        ),
    ))


def _qualification_models() -> tuple[
    PoEModelQualificationPlan, PoEModelQualificationPlan,
]:
    plan = cp_scale_poe_capacity_qualification_plan(BUILD)
    return plan.for_model("3560-24PS"), plan.for_model("3650-24PS")


def _productive_admission(
    store: CapabilitySnapshotStore,
    model_plan: PoEModelQualificationPlan,
    required: tuple[PoEAuthorizedBinding, ...],
):
    adapter = packet_tracer_enterprise_capability_adapter(BUILD, store=store)
    candidate = next(
        item
        for item in adapter.hardware_candidates("switch", BUILD)
        if item.model == model_plan.candidate_model
    )
    demanded = [
        EndpointPortBinding(
            endpoint_id=f"synthetic-phone-{index}",
            device_id="synthetic-switch",
            device_port=binding.switch_port,
            endpoint_model=binding.endpoint_model,
            endpoint_port=binding.endpoint_port,
        )
        for index, binding in enumerate(required, start=1)
    ]
    errors: list[str] = []
    unverified: list[str] = []
    admitted, status = ReferenceHardwarePlanner._admit_powered_ports(
        SimpleNamespace(id="synthetic-switch", model=model_plan.candidate_model),
        candidate,
        demanded,
        {port.name: port for port in candidate.ports},
        errors,
        unverified,
    )
    return admitted, status, errors, unverified


def _assert_sha256(value: str) -> None:
    assert _HASH_PATTERN.fullmatch(value)


def test_probe_a_admits_only_its_exact_model_scope_and_blocks_composition(
    tmp_path,
) -> None:
    """A provider dropping schema 3 would lose the exact 3560 authority."""
    model_3560, _ = _qualification_models()
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    _persist_probe(
        store, _probe_result(model_3560, run_number=1), run_number=1,
    )

    evidence = tuple(
        ProbeCapabilityProvider(store, BUILD).evidence_for("3560-24PS", BUILD)
    )
    adapter = packet_tracer_enterprise_capability_adapter(BUILD, store=store)
    resolved_3560 = adapter.capabilities_for("3560-24PS", BUILD)
    resolved_3650 = adapter.capabilities_for("3650-24PS", BUILD)
    composition = compose_cp_scale_canonical(
        packet_tracer_version=BUILD,
        capability_store=store,
    )

    assert len(evidence) == 1
    assert evidence[0].status is CapabilityStatus.SUPPORTED
    assert resolved_3560 is not None
    assert resolved_3560.supports_poe is CapabilityStatus.SUPPORTED
    assert resolved_3560.poe_ports == 21
    assert resolved_3560.poe_authorized_bindings == sorted(
        model_3560.bindings,
    )
    assert resolved_3650 is not None
    assert resolved_3650.supports_poe is CapabilityStatus.UNKNOWN
    assert resolved_3650.poe_ports is None
    assert resolved_3650.poe_authorized_bindings == []
    assert not composition.valid
    assert composition.topology is None
    assert any(
        "3650-24PS PoE capability is unknown" in issue
        for issue in composition.issues
    )
    assert composition.voice is None


def test_independent_same_model_runs_use_maximum_capacity_not_sum(
    tmp_path,
) -> None:
    """Summing independent scopes would invent unobserved simultaneity."""
    model_3560, _ = _qualification_models()
    first_bindings = model_3560.bindings[:11]
    second_bindings = model_3560.bindings[11:]
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    _persist_probe(
        store,
        _probe_result(
            model_3560, run_number=2, bindings=first_bindings,
        ),
        run_number=2,
    )
    _persist_probe(
        store,
        _probe_result(
            model_3560, run_number=3, bindings=second_bindings,
        ),
        run_number=3,
    )

    resolved = packet_tracer_enterprise_capability_adapter(
        BUILD, store=store,
    ).capabilities_for("3560-24PS", BUILD)

    assert resolved is not None
    assert resolved.supports_poe is CapabilityStatus.SUPPORTED
    assert resolved.poe_ports == 11
    assert resolved.poe_ports != len(first_bindings) + len(second_bindings)
    assert resolved.poe_authorized_bindings == sorted(model_3560.bindings)
    assert len(resolved.poe_authorized_scopes) == 2


def test_independent_scopes_cannot_authorize_a_cross_cohort_demand(
    tmp_path,
) -> None:
    model_3560, _ = _qualification_models()
    first_bindings = model_3560.bindings[:11]
    second_bindings = model_3560.bindings[11:]
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    _persist_probe(
        store,
        _probe_result(model_3560, run_number=7, bindings=first_bindings),
        run_number=7,
    )
    _persist_probe(
        store,
        _probe_result(model_3560, run_number=8, bindings=second_bindings),
        run_number=8,
    )
    cross_cohort = (first_bindings[0], second_bindings[0])
    admitted, status, errors, unverified = _productive_admission(
        store, model_3560, cross_cohort,
    )

    assert admitted is None
    assert status is DeviceCandidateStatus.NEEDS_VERIFICATION
    assert errors == []
    assert any("single simultaneous scope" in item for item in unverified)


def test_one_scope_covering_all_ports_authorizes_legitimate_subsets(
    tmp_path,
) -> None:
    model_3560, _ = _qualification_models()
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    _persist_probe(
        store,
        _probe_result(model_3560, run_number=9),
        run_number=9,
    )

    admitted, status, errors, unverified = _productive_admission(
        store,
        model_3560,
        (model_3560.bindings[0], model_3560.bindings[11]),
    )

    assert admitted == 21
    assert status is DeviceCandidateStatus.COMPATIBLE
    assert errors == []
    assert unverified == []


def test_repeated_claims_for_one_scope_do_not_duplicate_authority(
    tmp_path,
) -> None:
    model_3560, _ = _qualification_models()
    repeated = model_3560.bindings[:11]
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    for run_number in (10, 11):
        _persist_probe(
            store,
            _probe_result(
                model_3560,
                run_number=run_number,
                bindings=repeated,
            ),
            run_number=run_number,
        )

    resolved = packet_tracer_enterprise_capability_adapter(
        BUILD, store=store,
    ).capabilities_for(model_3560.candidate_model, BUILD)

    assert resolved is not None
    assert resolved.poe_ports == 11
    assert resolved.poe_authorized_bindings == sorted(repeated)
    assert len(resolved.poe_authorized_scopes) == 1
    assert resolved.poe_authorized_scopes[0].active_bindings == tuple(
        sorted(repeated)
    )


def test_unrepresentable_power_produces_unknown_without_authority(tmp_path) -> None:
    model_3560, _ = _qualification_models()
    result = _probe_result(model_3560, run_number=6)
    captures = json.loads(result.dimensions["poe_pse_captures"])
    captures[0]["binding_captures"][0]["power_watts"] = 10**400
    result.dimensions["poe_pse_captures"] = json.dumps(
        captures, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    _persist_probe(store, result, run_number=6)

    evidence = tuple(
        ProbeCapabilityProvider(store, BUILD).evidence_for("3560-24PS", BUILD)
    )
    assert len(evidence) == 1
    assert evidence[0].status is CapabilityStatus.UNKNOWN
    resolved = packet_tracer_enterprise_capability_adapter(
        BUILD, store=store,
    ).capabilities_for("3560-24PS", BUILD)
    assert resolved is not None
    assert resolved.supports_poe is CapabilityStatus.UNKNOWN
    assert resolved.poe_ports is None
    assert resolved.poe_authorized_bindings == []


def test_probe_a_plus_b_composes_and_projects_router0_with_current_hashes(
    tmp_path,
) -> None:
    """Losing either admitted model scope would block the product projection."""
    model_3560, model_3650 = _qualification_models()
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    _persist_probe(
        store, _probe_result(model_3560, run_number=4), run_number=4,
    )
    _persist_probe(
        store, _probe_result(model_3650, run_number=5), run_number=5,
    )

    adapter = packet_tracer_enterprise_capability_adapter(BUILD, store=store)
    for model_plan in (model_3560, model_3650):
        resolved = adapter.capabilities_for(model_plan.candidate_model, BUILD)
        assert resolved is not None
        assert resolved.supports_poe is CapabilityStatus.SUPPORTED
        assert resolved.poe_ports == model_plan.simultaneous_active_ports
        assert resolved.poe_authorized_bindings == sorted(model_plan.bindings)

    composition = compose_cp_scale_canonical(
        packet_tracer_version=BUILD,
        capability_store=store,
    )
    assert composition.valid
    assert composition.topology is not None
    assert composition.configuration is not None
    assert composition.control_plane is not None
    assert composition.voice is not None

    floor3 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.FLOOR3,
    )
    router0 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )
    delta = project_cp_scale_canonical_delta(
        floor3.topology, router0.topology,
    )
    assert any(device.name == "Router0" for device in router0.topology.devices)
    assert router0.voice is not None

    hashes = {
        "topology": router0.topology.physical_identity_hash,
        "configuration": router0.configuration.semantic_hash,
        "control": router0.control_plane.semantic_hash,
        "voice": router0.voice.semantic_hash,
        "delta": delta.physical_identity_hash,
    }
    for value in hashes.values():
        _assert_sha256(value)
    assert router0.voice.source_topology_hash == hashes["topology"]
    assert router0.voice.source_configuration_hash == hashes["configuration"]

    print("POE3B_CURRENT_HASHES=" + json.dumps(hashes, sort_keys=True))
    print(
        "POE3B_VOICE_SOURCES="
        + json.dumps({
            "source_topology_hash": router0.voice.source_topology_hash,
            "source_configuration_hash": (
                router0.voice.source_configuration_hash
            ),
        }, sort_keys=True)
    )
