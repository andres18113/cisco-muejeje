"""E5 application: preflight, capability gates y separación apply/verify."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from src.packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigureAccessPort,
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    RuntimeVerification,
)
from src.packet_tracer_mcp.domain.models.plans import TopologyPlan

from test_enterprise_configuration import _fixture
from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)


class FakeConfigurationRuntime:
    def __init__(self, topology: TopologyPlan) -> None:
        self.targets = [
            RuntimeConfigurationTarget(
                device_name=device.name,
                model=device.model,
                interfaces=sorted({
                    port
                    for link in topology.links
                    for endpoint_id, port in (
                        (link.device_a_id, link.port_a), (link.device_b_id, link.port_b),
                    )
                    if endpoint_id == device.id
                } | ({"Vlan1"} if device.enterprise_role == "ip_phone" else set())),
            )
            for device in topology.devices
        ]
        self.apply_calls: list[list[str]] = []
        self.verify_calls: list[list[str]] = []
        self.action_batches: list[list] = []
        self.events: list[tuple[str, list[str]]] = []
        self.fail_action_types: set[ConfigurationActionType] = set()
        self.verification_status = ActionExecutionStatus.VERIFIED
        self.verification_by_kind: dict[
            VerificationKind, ActionExecutionStatus
        ] = {}
        self.voice_forwarding_status = ActionExecutionStatus.VERIFIED

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        return self.targets

    def apply_actions(self, actions):
        self.action_batches.append(list(actions))
        self.apply_calls.append([action.id for action in actions])
        self.events.append(("apply", self.apply_calls[-1]))
        return [
            RuntimeActionMutation(
                action_id=action.id,
                applied=action.action_type not in self.fail_action_types,
                message=(
                    "forced failure"
                    if action.action_type in self.fail_action_types else "applied"
                ),
            )
            for action in actions
        ]

    def verify(self, expectations):
        self.verify_calls.append([expectation.id for expectation in expectations])
        self.events.append(("verify", self.verify_calls[-1]))
        return [
            RuntimeVerification(
                expectation_id=expectation.id,
                status=self.verification_by_kind.get(
                    expectation.kind, self.verification_status,
                ),
                evidence_method="fake_readback",
                fresh_evidence=True,
                fields={
                    field: FieldVerificationStatus.VERIFIED
                    for field in expectation.expected
                },
            )
            for expectation in expectations
        ]

    def wait_for_voice_access_forwarding(self, expectations):
        self.events.append((
            "voice_forwarding",
            [item.id for item in expectations],
        ))
        return [
            RuntimeVerification(
                expectation_id=item.id,
                status=self.voice_forwarding_status,
                evidence_method="fake_voice_access_forwarding",
                fresh_evidence=(
                    self.voice_forwarding_status
                    is ActionExecutionStatus.VERIFIED
                ),
                fields={
                    "voice_forwarding": (
                        FieldVerificationStatus.VERIFIED
                        if self.voice_forwarding_status
                        is ActionExecutionStatus.VERIFIED
                        else FieldVerificationStatus.UNOBSERVABLE
                    ),
                },
            )
            for item in expectations
        ]


def _compiled():
    enterprise, topology, policy = _fixture()
    compiled = compile_enterprise_configuration(enterprise, topology, policy)
    assert compiled.is_valid
    return topology, compiled.plan


def _supported_capabilities() -> dict[str, DeviceCapabilities]:
    return {
        "2911": DeviceCapabilities(
            model="2911", category="router", layer3=CapabilityStatus.SUPPORTED,
            supports_dhcp_server=CapabilityStatus.SUPPORTED,
        ),
        "2960-24TT": DeviceCapabilities(
            model="2960-24TT", category="switch",
            supports_vlan=CapabilityStatus.SUPPORTED,
            supports_trunk=CapabilityStatus.SUPPORTED,
        ),
    }


def test_source_topology_hash_mismatch_stops_before_any_mutation():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash="different-e4-hash",
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.SOURCE_TOPOLOGY_MISMATCH
    assert not runtime.apply_calls


def test_dependency_cycle_stops_preflight_before_inventory_or_mutation():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    first, second = plan.actions[:2]
    first.depends_on = [second.id]
    second.depends_on = [first.id]

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.DEPENDENCY_BLOCKED
    assert not runtime.apply_calls


def test_missing_capability_snapshot_is_unknown_and_not_blindly_applied():
    """Sin snapshot no hay permiso, y ahora tampoco hay mutacion parcial.

    Antes este test comprobaba que cada accion de red quedaba SKIPPED con
    CAPABILITY_UNKNOWN mientras el resto del lote seguia. Lo primero se
    conserva como codigo de fallo; lo segundo dejo de ser cierto a proposito:
    MEG-4 run 4 midio que un plan con acciones requeridas UNKNOWN igual mutaba
    un router en vivo, y el conjunto requerido pasa a ser una sola unidad de
    preflight.
    """
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
    )
    gated = [
        action for action in plan.actions
        if action.required_capability.startswith("supports_")
    ]

    assert gated
    assert runtime.apply_calls == []
    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN
    assert any("unknown" in message for message in result.preflight_errors)


def test_runtime_model_mismatch_stops_preflight_without_partial_application():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    target = next(item for item in runtime.targets if item.device_name == "__MCP_E5_ACCESS")
    target.model = "NOT-A-2960"

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert not runtime.apply_calls


def test_actions_are_submitted_by_phase_and_not_one_bridge_call_per_line():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.VERIFIED
    assert len(runtime.apply_calls) == (
        len({action.phase for action in plan.actions}) + 1
    )
    assert any(len(call) > 1 for call in runtime.apply_calls)
    assert all(item.status is ActionExecutionStatus.APPLIED for item in result.action_results)


def _phone_voice_action(plan):
    return next(
        action for action in plan.actions
        if isinstance(action, ConfigureAccessPort)
        and action.voice_vlan_id is not None
    )


def test_voice_vlan_signal_waits_for_network_foundation_verification():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    action = _phone_voice_action(plan)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    dispatched = [
        item
        for batch in runtime.action_batches
        for item in batch
        if item.id == action.id
    ]
    assert [item.voice_vlan_id for item in dispatched] == [
        None, action.voice_vlan_id,
    ]
    preparation = next(
        index for index, (kind, ids) in enumerate(runtime.events)
        if kind == "apply" and action.id in ids
    )
    foundation = next(
        index for index, (kind, ids) in enumerate(runtime.events)
        if kind == "verify" and any(
            expectation.id in ids
            and expectation.kind in {
                VerificationKind.VLAN,
                VerificationKind.TRUNK,
                VerificationKind.L3_INTERFACE,
                VerificationKind.DHCP_POOL,
            }
            for expectation in plan.verification_expectations
        )
    )
    signal = max(
        index for index, (kind, ids) in enumerate(runtime.events)
        if kind == "apply" and action.id in ids
    )
    assert preparation < foundation < signal
    assert result.voice_signal_barrier is not None
    assert (
        result.voice_signal_barrier.foundation_status
        is ActionExecutionStatus.VERIFIED
    )
    assert (
        result.voice_signal_barrier.signal_status
        is ActionExecutionStatus.VERIFIED
    )


def test_failed_trunk_foundation_blocks_voice_signal():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.verification_by_kind[VerificationKind.TRUNK] = (
        ActionExecutionStatus.FAILED
    )
    action = _phone_voice_action(plan)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    dispatched = [
        item
        for batch in runtime.action_batches
        for item in batch
        if item.id == action.id
    ]
    assert [item.voice_vlan_id for item in dispatched] == [None]
    assert (
        result.voice_signal_barrier.foundation_status
        is ActionExecutionStatus.FAILED
    )
    assert (
        result.voice_signal_barrier.signal_status
        is ActionExecutionStatus.DEPENDENCY_BLOCKED
    )
    by_id = {item.action_id: item for item in result.action_results}
    assert by_id[action.id].status is ActionExecutionStatus.PARTIAL
    assert "data-only access preparation was applied" in by_id[action.id].message


def test_unobservable_dhcp_pool_ceiling_does_not_make_signal_impossible():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.verification_by_kind[VerificationKind.DHCP_POOL] = (
        ActionExecutionStatus.UNOBSERVABLE
    )
    action = _phone_voice_action(plan)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    dispatched = [
        item
        for batch in runtime.action_batches
        for item in batch
        if item.id == action.id
    ]
    assert [item.voice_vlan_id for item in dispatched] == [
        None, action.voice_vlan_id,
    ]
    assert (
        result.voice_signal_barrier.foundation_status
        is ActionExecutionStatus.VERIFIED
    )


def test_voice_signal_can_be_held_pending_until_bootstrap_then_completed():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    applicator = ConfigurationApplicator(runtime)
    action = _phone_voice_action(plan)

    prepared = applicator.apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
        defer_voice_signal_until_bootstrap=True,
    )

    dispatched = [
        item
        for batch in runtime.action_batches
        for item in batch
        if item.id == action.id
    ]
    assert [item.voice_vlan_id for item in dispatched] == [None]
    assert (
        prepared.voice_signal_barrier.foundation_status
        is ActionExecutionStatus.VERIFIED
    )
    assert (
        prepared.voice_signal_barrier.signal_status
        is ActionExecutionStatus.INTENDED
    )

    lifecycle: list[str] = []
    completed = applicator.complete_deferred_voice_signals(
        plan,
        prepared,
        lifecycle_observer=lifecycle.append,
    )

    dispatched = [
        item
        for batch in runtime.action_batches
        for item in batch
        if item.id == action.id
    ]
    assert [item.voice_vlan_id for item in dispatched] == [
        None, action.voice_vlan_id,
    ]
    assert (
        completed.voice_signal_barrier.signal_status
        is ActionExecutionStatus.VERIFIED
    )
    access = next(
        item for item in completed.verification_results
        if item.action_id == action.id
    )
    assert access.fields["voice_forwarding"] is (
        FieldVerificationStatus.VERIFIED
    )
    signal_event = max(
        index for index, (kind, ids) in enumerate(runtime.events)
        if kind == "apply" and action.id in ids
    )
    forwarding_event = next(
        index for index, (kind, _) in enumerate(runtime.events)
        if kind == "voice_forwarding"
    )
    assert signal_event < forwarding_event
    assert lifecycle == [
        "VOICE_SIGNAL_VERIFIED",
        "PHONE_ACCESS_FWD_VERIFIED",
    ]


def test_unobservable_phone_port_forwarding_keeps_registration_gate_closed():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.voice_forwarding_status = ActionExecutionStatus.UNOBSERVABLE
    applicator = ConfigurationApplicator(runtime)

    prepared = applicator.apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
        defer_voice_signal_until_bootstrap=True,
    )
    completed = applicator.complete_deferred_voice_signals(plan, prepared)

    assert (
        completed.voice_signal_barrier.signal_status
        is ActionExecutionStatus.UNOBSERVABLE
    )
    deferred = set(completed.voice_signal_barrier.deferred_action_ids)
    assert all(
        item.status is ActionExecutionStatus.PARTIAL
        for item in completed.verification_results
        if item.action_id in deferred
    )


def test_hard_foundation_failure_outranks_an_earlier_unobservable_read():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.verification_by_kind[VerificationKind.VLAN] = (
        ActionExecutionStatus.UNOBSERVABLE
    )
    runtime.verification_by_kind[VerificationKind.TRUNK] = (
        ActionExecutionStatus.FAILED
    )

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert (
        result.voice_signal_barrier.foundation_status
        is ActionExecutionStatus.FAILED
    )
    assert result.failure_code is ConfigurationFailureCode.VERIFICATION_FAILED


def test_no_flag_disposable_live_uses_the_production_configuration_applicator():
    source = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(
        encoding="utf-8",
    )

    assert "production_pipeline=not experiment_mode" in source
    assert "actions = order_configuration_actions(actions)" in source
    assert "defer_voice_signal_until_bootstrap=True" in source
    assert "complete_production_voice_signal" in source
    assert '"production_pipeline"' in source
    assert '"production_configuration_application"' in source


def test_application_result_records_generic_runtime_reproducibility_context():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    context = ConfigurationRuntimeContext(
        backend="packet_tracer",
        backend_version="9.0.1.0858",
        capability_snapshot_hash="snapshot-hash",
    )

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
        runtime_context=context,
    )

    assert result.runtime_context == context
    assert result.compact_summary()["runtime_context"] == context.model_dump(mode="json")


def test_failed_vlan_blocks_dependent_access_and_trunk_actions():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.fail_action_types = {ConfigurationActionType.CREATE_VLAN}

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )
    by_id = {item.action_id: item for item in result.action_results}
    access_and_trunks = [
        action for action in plan.actions
        if action.action_type in {
            ConfigurationActionType.CONFIGURE_ACCESS_PORT,
            ConfigurationActionType.CONFIGURE_TRUNK,
        }
    ]

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert all(
        by_id[action.id].status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        for action in access_and_trunks
    )
    attempted = {action_id for call in runtime.apply_calls for action_id in call}
    assert not attempted.intersection(action.id for action in access_and_trunks)


def test_unknown_svi_is_skipped_without_becoming_unsupported_or_blocking_l2():
    enterprise, topology, policy = _fixture()
    policy.gateway_device_ids = {"hq": "sw-dist"}
    policy.dhcp_server_device_ids = {"hq": "sw-dist"}
    plan = compile_enterprise_configuration(enterprise, topology, policy).plan
    runtime = FakeConfigurationRuntime(topology)
    capabilities = _supported_capabilities()
    capabilities["2960-24TT"].supports_svi = CapabilityStatus.UNKNOWN
    capabilities["2960-24TT"].supports_dhcp_server = CapabilityStatus.UNKNOWN

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=capabilities,
    )
    by_id = {item.action_id: item for item in result.action_results}
    svi_actions = plan.actions_of_type(ConfigurationActionType.CONFIGURE_SVI)
    vlan_actions = plan.actions_of_type(ConfigurationActionType.CREATE_VLAN)

    # Lo que este test siempre defendio y sigue defendiendo: UNKNOWN no se
    # convierte en UNSUPPORTED, y no contagia a la capa 2. Lo que cambia es que
    # una accion REQUERIDA sin autorizar ya no deja aplicar el resto del lote.
    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN
    assert result.failure_code is not ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
    assert svi_actions and vlan_actions
    assert by_id == {}
    assert runtime.apply_calls == []
    assert capabilities["2960-24TT"].supports_vlan is CapabilityStatus.SUPPORTED


def test_explicitly_unsupported_required_action_is_not_attempted():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    capabilities = _supported_capabilities()
    capabilities["2911"].supports_dhcp_server = CapabilityStatus.UNSUPPORTED

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=capabilities,
    )
    pool = plan.actions_of_type(ConfigurationActionType.CONFIGURE_DHCP_POOL)[0]
    attempted = {action_id for call in runtime.apply_calls for action_id in call}

    assert pool.critical
    assert pool.id not in attempted
    assert attempted == set()
    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.CAPABILITY_UNSUPPORTED


def test_applied_is_not_promoted_to_verified_when_readback_is_partial():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.verification_status = ActionExecutionStatus.PARTIAL

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    voice = _phone_voice_action(plan)
    assert next(
        item.status for item in result.action_results
        if item.action_id == voice.id
    ) is ActionExecutionStatus.PARTIAL
    assert all(
        item.status is ActionExecutionStatus.APPLIED
        for item in result.action_results
        if item.action_id != voice.id
    )
    assert result.failure_code is ConfigurationFailureCode.VERIFICATION_FAILED
    assert (
        result.voice_signal_barrier.foundation_status
        is ActionExecutionStatus.PARTIAL
    )


def test_fully_unobservable_readback_is_an_observability_limit_not_a_failure():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.verification_status = ActionExecutionStatus.UNOBSERVABLE

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert result.failure_code is ConfigurationFailureCode.OBSERVABILITY_LIMITATION
    assert all(
        item.status in {
            ActionExecutionStatus.UNOBSERVABLE,
            ActionExecutionStatus.DEPENDENCY_BLOCKED,
        }
        for item in result.verification_results
    )


def test_dhcp_verification_preserves_field_level_observability():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)

    def verify(expectations):
        runtime.verify_calls.append([item.id for item in expectations])
        return [
            RuntimeVerification(
                expectation_id=item.id,
                status=(
                    ActionExecutionStatus.PARTIAL
                    if item.kind.value == "endpoint_addressing"
                    and item.expected.get("mode") == "dhcp"
                    else ActionExecutionStatus.VERIFIED
                ),
                evidence_method="structured_endpoint_getters",
                fresh_evidence=True,
                fields=(
                    {
                        "ipv4": FieldVerificationStatus.VERIFIED,
                        "netmask": FieldVerificationStatus.VERIFIED,
                        "gateway": FieldVerificationStatus.UNOBSERVABLE,
                        "dns": FieldVerificationStatus.UNOBSERVABLE,
                    }
                    if item.kind.value == "endpoint_addressing"
                    and item.expected.get("mode") == "dhcp"
                    else {field: FieldVerificationStatus.VERIFIED for field in item.expected}
                ),
            )
            for item in expectations
        ]

    runtime.verify = verify
    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )
    dhcp = next(
        item for item in result.verification_results
        if item.fields.get("gateway") is FieldVerificationStatus.UNOBSERVABLE
    )

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert dhcp.fields["ipv4"] is FieldVerificationStatus.VERIFIED
    assert dhcp.fields["netmask"] is FieldVerificationStatus.VERIFIED
    assert dhcp.fields["gateway"] is FieldVerificationStatus.UNOBSERVABLE
    assert dhcp.fields["dns"] is FieldVerificationStatus.UNOBSERVABLE
