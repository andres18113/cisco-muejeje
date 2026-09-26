"""Compiled one-user Server-PT native DHCP plus dependent HTTP contract."""

import json
from types import SimpleNamespace

import pytest
from test_apply_enterprise_services import _harness
from test_service_dhcp_integration import _ModeConfigurationRuntime

from packet_tracer_mcp.adapters.cli.service_qualification import (
    _native_candidate_capabilities,
    _native_dhcp_http_intent,
    dhcp_product_contract,
    native_dhcp_http_product_contract,
)
from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    TransportSelection,
    _dhcp_authorities,
    _drift_conflicts,
    _e5_closure,
)
from packet_tracer_mcp.application.use_cases.apply_services import ServiceApplicator
from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
    ReadinessNotRequired,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.configuration import SetEndpointDhcp
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationRuntimeContext,
    RuntimeActionMutation,
    decide_mutation,
)
from packet_tracer_mcp.domain.enterprise.models.service_entry import ServiceEntryRefusal
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    AcquireDhcpLease,
    ConfigureServerDhcpPool,
    EnableHttpService,
    EnableServerDhcp,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
)
from packet_tracer_mcp.domain.enterprise.services.native_dhcp_policy import (
    native_policy_within_scope,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)
from packet_tracer_mcp.infrastructure.execution.endpoint_address_observer import (
    PacketTracerEndpointAddressObserver,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    BridgeObservationKind,
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)
from tests.service_qualification_engine import NodeEngine, require_node


def test_native_product_keeps_logical_and_physical_pool_identity_separate() -> None:
    """Only PC1 is selected and DHCP state must verify before its HTTP effect."""
    contract = native_dhcp_http_product_contract("9.0.1.0858", "native-product")
    mode_actions = [
        item
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointDhcp)
    ]
    assert {item.device_name for item in mode_actions} == {
        "Q3-DEFAULT-PC-01",
        "Q3-DEFAULT-PC-02",
    }
    pc1 = next(item for item in mode_actions if item.device_name == "Q3-DEFAULT-PC-01")
    pc2 = next(item for item in mode_actions if item.device_name == "Q3-DEFAULT-PC-02")
    assert pc1.native_server_device_name == "Q3-DEFAULT-SERVER-01"
    assert pc1.native_server_interface == "FastEthernet0"
    assert pc1.native_effective_pool_name == "serverPool"
    assert pc1.native_inactive_clients == [("Q3-DEFAULT-PC-02", "FastEthernet0")]
    assert pc2.native_effective_pool_name == ""
    e5_scope = _e5_closure(
        contract.configuration_plan,
        contract.service_plan,
        contract.service_plan.services,
    )
    assert pc1.id in e5_scope
    assert pc2.id not in e5_scope
    actions = contract.service_plan.actions
    pools = [item for item in actions if isinstance(item, ConfigureServerDhcpPool)]
    enables = [item for item in actions if isinstance(item, EnableServerDhcp)]
    assert len(pools) == len(enables) == 1
    pool, enable = pools[0], enables[0]
    assert pool.pool_name != "serverPool"
    assert pool.effective_pool_name == "serverPool"
    assert pool.pool_name_explicit is False
    assert pool.max_users == 1
    assert pool.lease_start == pool.lease_end == "192.0.2.100"
    assert enable.depends_on == [pool.id]
    assert enable.native_policy is not None
    assert enable.native_policy.effective_pool_name == "serverPool"
    assert enable.native_policy.lease_start == "192.0.2.100"
    assert [item.device_name for item in enable.native_policy.selected_clients] == [
        "Q3-DEFAULT-PC-01"
    ]
    assert [item.device_name for item in enable.native_policy.inactive_clients] == [
        "Q3-DEFAULT-PC-02"
    ]
    assert actions.index(pool) < actions.index(enable)
    assert not any(isinstance(item, AcquireDhcpLease) for item in actions)

    leases = [
        item
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    ]
    assert len(leases) == 1
    lease = leases[0]
    assert lease.client_device_name == "Q3-DEFAULT-PC-01"
    assert lease.required is True
    assert lease.action_id == enable.id
    assert lease.expected["state_only"] is True
    assert lease.expected["configure_only"] is False
    assert lease.expected["effective_pool_name"] == "serverPool"
    assert lease.expected["pool_name"] == pool.pool_name
    assert json.loads(lease.expected["native_inactive_clients_json"]) == [
        {"device_name": "Q3-DEFAULT-PC-02", "interface": "FastEthernet0"}
    ]

    server_reads = [
        item
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_SERVER_STATE
    ]
    assert len(server_reads) == 1
    assert server_reads[0].action_id == enable.id
    assert server_reads[0].expected["effective_pool_name"] == "serverPool"

    http_actions = [item for item in actions if isinstance(item, EnableHttpService)]
    assert len(http_actions) == 1
    http_fetches = [
        item
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.HTTP_FETCH
    ]
    assert len(http_fetches) == 1
    assert http_fetches[0].client_device_name == "Q3-DEFAULT-PC-01"
    assert lease.id in http_fetches[0].depends_on
    assert (
        contract.service_capabilities["PC-PT:acquire_dhcp_lease"].support
        is CapabilityStatus.UNKNOWN
    )
    [authority] = _dhcp_authorities(contract.service_plan)
    assert authority.pool_name == pool.pool_name
    assert authority.effective_pool_name == "serverPool"
    assert authority.pool_name_explicit is False


def test_native_binding_refuses_an_explicit_different_pool_name() -> None:
    """An operator's explicit named pool is never silently mapped to serverPool."""
    payload = _native_dhcp_http_intent().model_dump(mode="json")
    dhcp_pool = payload["sites"][0]["services"][0]["dhcp_pool"]
    dhcp_pool["pool_name"] = "operator_named_pool"
    intent = type(_native_dhcp_http_intent()).model_validate(payload)
    with pytest.raises(ValueError, match="Native Server-PT binding requires"):
        dhcp_product_contract("9.0.1.0858", "explicit-name", 1, intent_override=intent)


def test_native_policy_derives_two_selected_clients_without_inactive_twins() -> None:
    """The requested capacity and selection reach the physical native plan."""
    payload = _native_dhcp_http_intent().model_dump(mode="json")
    services = payload["sites"][0]["services"]
    services[0]["client_device_ids"] = [
        "endpoint/q3/default/user_pc/001",
        "endpoint/q3/default/user_pc/002",
    ]
    services[0]["dhcp_pool"]["max_users"] = 2
    services[1]["client_device_ids"] = services[0]["client_device_ids"]
    intent = type(_native_dhcp_http_intent()).model_validate(payload)
    contract = dhcp_product_contract(
        "9.0.1.0858",
        "two-clients",
        2,
        intent_override=intent,
        capabilities_override=_native_candidate_capabilities("9.0.1.0858"),
        preserve_reference_topology=True,
    )

    [pool] = [
        item
        for item in contract.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    ]
    [enable] = [
        item
        for item in contract.service_plan.actions
        if isinstance(item, EnableServerDhcp)
    ]
    assert (pool.lease_start, pool.lease_end, pool.max_users) == (
        "192.0.2.100",
        "192.0.2.101",
        2,
    )
    assert enable.native_policy is not None
    assert len(enable.native_policy.selected_clients) == 2
    assert enable.native_policy.inactive_clients == []
    lease_checks = [
        item
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    ]
    assert len(lease_checks) == 2
    assert all(item.required for item in lease_checks)
    assert not any(
        item.kind is ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED
        for item in contract.service_plan.verification_expectations
    )


def test_native_candidate_derives_shifted_requested_allocation() -> None:
    """The requested offset reaches E6 rather than a fixed .100 fixture."""
    contract = native_dhcp_http_product_contract(
        "9.0.1.0858", "shifted", selected_count=2, start_offset=150
    )
    [pool] = [
        item
        for item in contract.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    ]
    assert (pool.lease_start, pool.lease_end, pool.max_users) == (
        "192.0.2.151",
        "192.0.2.152",
        2,
    )


def test_native_capability_without_recorded_policy_scope_refuses_before_e5(
    tmp_path,
) -> None:
    """A broad marker cannot be an implicit public policy grant."""
    payload = _native_dhcp_http_intent().model_dump(mode="json")
    harness = _harness(tmp_path, payload)

    def unscoped(build):
        records = _native_candidate_capabilities(build)
        key = "Server-PT:dhcp_native_default_binding"
        records[key] = records[key].model_copy(update={"native_policy_scope": None})
        return records

    result = harness.run(intent_json=json.dumps(payload), capability_catalog=unscoped)
    assert result.refusal_code is ServiceEntryRefusal.COMPOSITION_FAILED
    assert "recorded policy scope" in result.blocked_reason
    assert harness.mutating_calls == []


@pytest.mark.parametrize("bad_duplicate", [False, True])
def test_group_trace_owner_is_the_client_that_reached_the_reader(
    monkeypatch, bad_duplicate
) -> None:
    """A skipped first client cannot leave a verified row with a dangling trace."""
    contract = native_dhcp_http_product_contract(
        "9.0.1.0858", "later-client", selected_count=2
    )
    leases = [
        item
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    ]
    group = [
        {
            "expectation_id": item.id,
            "device_name": item.client_device_name,
            "interface": item.expected["interface"],
        }
        for item in leases
    ]
    later = leases[1].model_copy(
        update={
            "expected": {
                **leases[1].expected,
                "native_selected_clients_json": json.dumps(group),
            }
        }
    )
    payload = {
        "server_found": True,
        "process_found": True,
        "pool_found": True,
        "pool_name": "serverPool",
        "scan_error": "",
        "termination": "bound",
        "error": "",
        "clients": [
            {
                **item,
                "found": True,
                "port_found": True,
                "mode": True,
                "mode_type": "boolean",
                "ipv4": f"192.0.2.{100 + index}",
                "netmask": "255.255.255.0",
                "mac": f"0000.0000.{index + 1:04d}",
                "error": "",
            }
            for index, item in enumerate(group)
        ],
        "rows": [
            {
                "ipAddress": f"192.0.2.{100 + index}",
                "macAddress": f"0000.0000.{index + 1:04d}",
                "leaseTime": 3600,
                "port": "FastEthernet0",
            }
            for index in range(2)
        ],
    }
    if bad_duplicate:
        payload["clients"][1]["ipv4"] = "192.0.2.100"
        payload["clients"][1]["netmask"] = "255.255.0.0"
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [], lambda *_: None, sleeper=lambda _: None
    )
    runtime._dhcp_state_max_samples = 2
    monkeypatch.setattr(
        runtime,
        "_verify_dhcp_server_state",
        lambda _: SimpleNamespace(
            status=ActionExecutionStatus.VERIFIED,
            observed={"native_policy_json": "{}"},
        ),
    )
    monkeypatch.setattr(
        runtime,
        "_native_group_snapshot",
        lambda *_: SimpleNamespace(kind=BridgeObservationKind.PAYLOAD, payload=payload),
    )

    row = runtime.verify(later)

    assert row.status is (
        ActionExecutionStatus.FAILED
        if bad_duplicate
        else ActionExecutionStatus.VERIFIED
    )
    assert row.observed["group_trace_ref"] == later.id
    assert len(json.loads(row.observed["group_trace_json"])) == (
        1 if bad_duplicate else 2
    )
    if bad_duplicate:
        first = runtime.verify(
            leases[0].model_copy(update={"expected": later.expected})
        )
        assert first.status is ActionExecutionStatus.FAILED


def test_native_single_pc_product_has_no_invented_inactive_client(tmp_path) -> None:
    """A one-PC deployment composes without a fictitious competing port."""
    payload = _native_dhcp_http_intent().model_dump(mode="json")
    site = payload["sites"][0]
    next(item for item in site["endpoints"] if item["role"] == "user_pc")["count"] = 1
    harness = _harness(tmp_path, payload)
    harness.configuration = _ModeConfigurationRuntime(
        targets=harness.configuration.targets
    )
    harness.transport = TransportSelection(channel="file")
    result = harness.run(
        intent_json=json.dumps(payload),
        capability_catalog=_native_candidate_capabilities,
    )

    assert result.refusal_code is ServiceEntryRefusal.NONE, result.blocked_reason
    assert result.service_result is not None
    assert len(result.clients) == 1


def test_native_e5_zero_address_and_zero_mask_are_unassigned() -> None:
    """A10 admits the cold PC1 sentinel without treating it as a foreign lease."""
    contract = native_dhcp_http_product_contract("9.0.1.0858", "zero-address")
    pc1 = next(
        item
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointDhcp) and item.device_name == "Q3-DEFAULT-PC-01"
    )
    raw = (
        '{"found":true,"port_found":true,"interface":"FastEthernet0",'
        '"address_channel":true,"ipv4":"0.0.0.0","netmask":"0.0.0.0"}'
    )
    observer = PacketTracerEndpointAddressObserver(lambda *_: raw)
    conflicts, unreadable, _confirmed = _drift_conflicts(
        contract.configuration_plan,
        {pc1.id},
        {pc1.device_id: pc1.device_name},
        observer,
        SimpleNamespace(read=lambda *_: None),
    )
    assert conflicts == []
    assert unreadable == []


def test_native_http_product_entry_persists_binding_and_gates_pc1(tmp_path) -> None:
    """A candidate run uses the real A1-E6 product path with only external seams."""
    payload = _native_dhcp_http_intent().model_dump(mode="json")
    harness = _harness(tmp_path, payload)
    harness.configuration = _ModeConfigurationRuntime(
        targets=harness.configuration.targets
    )
    harness.transport = TransportSelection(channel="file")

    result = harness.run(
        intent_json=json.dumps(payload),
        capability_catalog=_native_candidate_capabilities,
    )

    assert result.refusal_code is ServiceEntryRefusal.NONE, result.blocked_reason
    e5_called = {
        identifier for batch in harness.configuration.applied for identifier in batch
    }
    contract = native_dhcp_http_product_contract("9.0.1.0858", "entry-scope")
    mode_by_name = {
        item.device_name: item.id
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointDhcp)
    }
    assert mode_by_name["Q3-DEFAULT-PC-01"] in e5_called
    assert mode_by_name["Q3-DEFAULT-PC-02"] not in e5_called
    stored = ServiceRunRecordStore(tmp_path).load(result.deployment_id, result.run_id)
    [authority] = stored.dhcp_authorities
    assert authority.pool_name != "serverPool"
    assert authority.effective_pool_name == "serverPool"
    assert authority.pool_name_explicit is False
    assert authority.client_device_ids == ["endpoint/q3/default/user_pc/001"]
    assert not any(
        "acquire-dhcp" in identifier
        for batch in harness.services.applied
        for identifier in batch
    )
    assert stored.service_result is not None


def test_native_http_product_withholds_client_request_on_unknown_lease(
    tmp_path,
) -> None:
    """An inconclusive required DHCP state never becomes an HTTP probe."""
    payload = _native_dhcp_http_intent().model_dump(mode="json")
    harness = _harness(tmp_path, payload)
    harness.configuration = _ModeConfigurationRuntime(
        targets=harness.configuration.targets
    )
    harness.transport = TransportSelection(channel="file")
    harness.services.behavior_status = ActionExecutionStatus.UNKNOWN
    harness.services.behavior_observation = ObservationFact.INCONCLUSIVE

    result = harness.run(
        intent_json=json.dumps(payload),
        capability_catalog=_native_candidate_capabilities,
    )

    contract = native_dhcp_http_product_contract("9.0.1.0858", "unknown-lease")
    lease = next(
        item
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    )
    fetch = next(
        item
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.HTTP_FETCH
    )
    assert lease.id in harness.services.verified
    assert fetch.id not in harness.services.verified
    stored = ServiceRunRecordStore(tmp_path).load(result.deployment_id, result.run_id)
    assert stored.service_result is not None


@pytest.mark.parametrize("server_enabled", [False, True])
def test_native_product_client_mode_is_guarded_in_its_effect_evaluation(
    tmp_path, server_enabled
) -> None:
    """An enabled foreign authority cannot receive an E5 client-mode effect."""
    require_node()
    contract = native_dhcp_http_product_contract("9.0.1.0858", "mode-guard")
    action = next(
        item
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointDhcp) and item.device_name == "Q3-DEFAULT-PC-01"
    )
    directory = tmp_path / ("enabled" if server_enabled else "disabled")
    directory.mkdir()
    engine = NodeEngine(
        directory,
        dhcp_default_pool="native",
        dhcp_server_initial_enabled=server_enabled,
    )
    try:
        engine.seed_device("Q3-DEFAULT-SERVER-01", "Server-PT")
        engine.seed_device("Q3-DEFAULT-PC-01", "PC-PT")
        engine.seed_device("Q3-DEFAULT-PC-02", "PC-PT")
        engine.evaluate(
            PacketTracerEnterpriseConfigurationRuntime._endpoint_call(action)
        )
        assert engine.snapshot()["dhcp_setter_calls"]["configurePcIpDhcp"] == (
            0 if server_enabled else 1
        )
    finally:
        engine.close()


def test_native_binding_rejects_capacity_beyond_scoped_family_before_e5(
    tmp_path,
) -> None:
    """The marker cannot authorize capacity beyond the candidate scope."""
    payload = _native_dhcp_http_intent().model_dump(mode="json")
    payload["sites"][0]["services"][0]["dhcp_pool"]["max_users"] = 17
    harness = _harness(tmp_path, payload)

    result = harness.run(
        intent_json=json.dumps(payload),
        capability_catalog=_native_candidate_capabilities,
    )

    assert result.refusal_code is ServiceEntryRefusal.COMPOSITION_FAILED
    assert "does not admit" in result.blocked_reason
    assert harness.mutating_calls == []


@pytest.mark.parametrize("server_enabled", [False, True])
def test_native_e5_runtime_reports_the_guarded_client_effect(
    tmp_path, server_enabled
) -> None:
    """A queued-script receipt alone cannot claim the guarded setter ran."""
    require_node()
    contract = native_dhcp_http_product_contract("9.0.1.0858", "e5-guarded")
    action = next(
        item
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointDhcp) and item.device_name == "Q3-DEFAULT-PC-01"
    )
    directory = tmp_path / ("enabled-runtime" if server_enabled else "disabled-runtime")
    directory.mkdir()
    engine = NodeEngine(
        directory,
        dhcp_default_pool="native",
        dhcp_server_initial_enabled=server_enabled,
    )
    try:
        engine.seed_device("Q3-DEFAULT-SERVER-01", "Server-PT")
        engine.seed_device("Q3-DEFAULT-PC-01", "PC-PT")
        engine.seed_device("Q3-DEFAULT-PC-02", "PC-PT")
        runtime = PacketTracerEnterpriseConfigurationRuntime(
            lambda: [], engine.queue, lambda script, _timeout: engine.evaluate(script)
        )
        [mutation] = runtime.apply_actions([action])
        assert mutation.attempted is (not server_enabled)
        assert decide_mutation(mutation).frontier is (not server_enabled)
        assert engine.snapshot()["dhcp_setter_calls"]["configurePcIpDhcp"] == (
            0 if server_enabled else 1
        )
    finally:
        engine.close()


def test_native_e5_guard_accepts_a_real_one_pc_inventory(tmp_path) -> None:
    """No competing PC is needed to authorize the selected client effect."""
    require_node()
    contract = native_dhcp_http_product_contract("9.0.1.0858", "one-pc-guard")
    action = next(
        item
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointDhcp) and item.device_name == "Q3-DEFAULT-PC-01"
    ).model_copy(update={"native_inactive_clients": []})
    engine = NodeEngine(tmp_path, dhcp_default_pool="native")
    try:
        engine.seed_device("Q3-DEFAULT-SERVER-01", "Server-PT")
        engine.seed_device("Q3-DEFAULT-PC-01", "PC-PT")
        runtime = PacketTracerEnterpriseConfigurationRuntime(
            lambda: [], engine.queue, lambda script, _timeout: engine.evaluate(script)
        )
        [mutation] = runtime.apply_actions([action])
        assert decide_mutation(mutation).frontier is True
        assert engine.snapshot()["dhcp_setter_calls"]["configurePcIpDhcp"] == 1
    finally:
        engine.close()


def test_native_e5_refuses_pc2_activated_at_dispatch(tmp_path) -> None:
    """A competing client in the same evaluation withholds the PC1 setter."""
    require_node()
    contract = native_dhcp_http_product_contract("9.0.1.0858", "pc2-race")
    action = next(
        item
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointDhcp) and item.device_name == "Q3-DEFAULT-PC-01"
    )
    engine = NodeEngine(tmp_path, dhcp_default_pool="native")
    try:
        engine.seed_device("Q3-DEFAULT-SERVER-01", "Server-PT")
        engine.seed_device("Q3-DEFAULT-PC-01", "PC-PT")
        engine.seed_device("Q3-DEFAULT-PC-02", "PC-PT")
        injected = False

        def waited(script, _timeout):
            nonlocal injected
            if not injected:
                injected = True
                engine.evaluate(
                    'configurePcIp("Q3-DEFAULT-PC-02",true,null,null,null,null,'
                    '"FastEthernet0");'
                )
            return engine.evaluate(script)

        runtime = PacketTracerEnterpriseConfigurationRuntime(
            lambda: [], engine.queue, waited
        )
        [mutation] = runtime.apply_actions([action])
        assert mutation.attempted is False
        assert decide_mutation(mutation).frontier is False
        # The one recorded DHCP-mode call is the injected PC2 change.
        assert engine.snapshot()["dhcp_setter_calls"]["configurePcIpDhcp"] == 1
    finally:
        engine.close()


@pytest.mark.parametrize("lease_verified", [False, True])
def test_required_native_state_is_staged_before_pc1_http_request(
    lease_verified,
) -> None:
    """The existing scheduler withholds HTTP until this client's state verifies."""
    contract = native_dhcp_http_product_contract("9.0.1.0858", "http-gate")

    class Runtime:
        def __init__(self):
            self.applied = []
            self.verified = []

        def inventory(self):
            return list(contract.inventory)

        def apply_actions(self, actions):
            self.applied.extend(item.id for item in actions)
            return [
                RuntimeActionMutation(action_id=item.id, applied=True)
                for item in actions
            ]

        def verify(self, expectation):
            self.verified.append(expectation.id)
            status = (
                ActionExecutionStatus.VERIFIED
                if lease_verified
                or expectation.kind is not ServiceVerificationKind.DHCP_LEASE
                else ActionExecutionStatus.UNKNOWN
            )
            return RuntimeServiceVerification(
                expectation_id=expectation.id,
                status=status,
                evidence_kind=expectation.evidence_kind,
                fresh_evidence=status is ActionExecutionStatus.VERIFIED,
                observation=(
                    ObservationFact.OBSERVED
                    if status is ActionExecutionStatus.VERIFIED
                    else ObservationFact.INCONCLUSIVE
                ),
            )

    runtime = Runtime()
    plan = contract.service_plan
    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=contract.manifest.physical_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses={
            item.configuration_action_id: ActionExecutionStatus.VERIFIED
            for item in plan.foundational_requirements
        },
        capabilities=contract.service_capabilities,
        runtime_context=ConfigurationRuntimeContext(
            backend=contract.manifest.backend,
            backend_version=contract.manifest.backend_version,
            environment_fingerprint=contract.manifest.environment_fingerprint,
        ),
        deployment_manifest=contract.manifest,
        operational_readiness=ReadinessNotRequired(
            "test fixture isolates lease scheduler ordering from forwarding"
        ),
    )
    lease = next(
        item
        for item in plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    )
    fetch = next(
        item
        for item in plan.verification_expectations
        if item.kind is ServiceVerificationKind.HTTP_FETCH
    )
    assert lease.id in runtime.verified
    assert (fetch.id in runtime.verified) is lease_verified, [
        (item.expectation_id, item.status, item.message)
        for item in result.verification_results
    ]
    assert result is not None


def test_default_catalog_admits_scoped_native_product_without_override(
    tmp_path,
) -> None:
    """The public catalog admits the measured policy through normal A1-E6."""
    payload = _native_dhcp_http_intent().model_dump(mode="json")
    harness = _harness(tmp_path, payload)
    harness.configuration = _ModeConfigurationRuntime(
        targets=harness.configuration.targets
    )
    harness.transport = TransportSelection(channel="file")

    result = harness.run(intent_json=json.dumps(payload))

    assert result.refusal_code is ServiceEntryRefusal.NONE, result.blocked_reason
    assert result.service_result is not None
    [authority] = (
        ServiceRunRecordStore(tmp_path)
        .load(result.deployment_id, result.run_id)
        .dhcp_authorities
    )
    assert authority.effective_pool_name == "serverPool"
    assert authority.client_device_ids == ["endpoint/q3/default/user_pc/001"]


def test_native_public_binding_rejects_unmeasured_transport_before_e5(tmp_path) -> None:
    """An HTTP-selected session cannot inherit file-channel native evidence."""
    payload = _native_dhcp_http_intent().model_dump(mode="json")
    harness = _harness(tmp_path, payload)

    result = harness.run(intent_json=json.dumps(payload))

    assert result.refusal_code is ServiceEntryRefusal.SERVICE_PATH_UNSUPPORTED
    assert "measured file channel" in result.blocked_reason
    assert harness.mutating_calls == []


@pytest.mark.parametrize(
    "outside",
    [
        "capacity",
        "start",
        "named_pool",
        "server_address",
        "gateway",
        "dns",
    ],
)
def test_default_native_binding_refuses_outside_recorded_scope_before_e5(
    tmp_path, outside
) -> None:
    """The public marker grants only native actions within its exact scope."""
    payload = _native_dhcp_http_intent().model_dump(mode="json")
    dhcp = payload["sites"][0]["services"][0]
    if outside == "capacity":
        dhcp["dhcp_pool"]["max_users"] = 3
    elif outside == "start":
        dhcp["dhcp_pool"]["start_offset"] = 152
    elif outside == "named_pool":
        dhcp["verification_mode"] = "configure_only"
        dhcp["dhcp_pool"]["pool_name"] = "OPERATOR_POOL"
    elif outside == "server_address":
        server = next(
            item
            for item in payload["sites"][0]["endpoints"]
            if item["role"] == "server"
        )
        server["metadata"]["ipv4"] = "192.0.2.20"
    elif outside == "gateway":
        payload["sites"][0]["segments"][0]["gateway"] = "192.0.2.2"
    elif outside == "dns":
        dhcp["dhcp_pool"]["dns_server"] = "192.0.2.11"
    harness = _harness(tmp_path, payload)

    result = harness.run(intent_json=json.dumps(payload))

    assert result.refusal_code is not ServiceEntryRefusal.NONE
    assert harness.mutating_calls == []


def test_foreign_build_has_only_an_unknown_native_marker() -> None:
    """A different PT build cannot inherit the measured public scope."""
    record = packet_tracer_service_capabilities("9.0.2.0000")[
        "Server-PT:dhcp_native_default_binding"
    ]
    assert record.support is CapabilityStatus.UNKNOWN
    assert record.native_policy_scope is None


def test_default_native_scope_requires_exact_exclusions() -> None:
    """An extra static address cannot be hidden inside a measured policy."""
    scope = packet_tracer_service_capabilities("9.0.1.0858")[
        "Server-PT:dhcp_native_default_binding"
    ].native_policy_scope
    common = dict(
        network="192.0.2.0",
        netmask="255.255.255.0",
        server_address="192.0.2.10",
        gateway="192.0.2.1",
        dns_server="192.0.2.10",
        lease_start="192.0.2.125",
        lease_end="192.0.2.126",
        max_users=2,
    )
    expected = [("192.0.2.1", "192.0.2.1"), ("192.0.2.10", "192.0.2.10")]
    assert native_policy_within_scope(scope, excluded_ranges=expected, **common)
    assert not native_policy_within_scope(
        scope, excluded_ranges=[*expected, ("192.0.2.20", "192.0.2.20")], **common
    )
    assert not native_policy_within_scope(
        scope,
        excluded_ranges=expected,
        **{**common, "network": "198.51.100.0"},
    )
    assert not native_policy_within_scope(
        scope,
        excluded_ranges=expected,
        **{**common, "netmask": "255.255.0.0"},
    )
