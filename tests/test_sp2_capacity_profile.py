"""The native capacity profile keeps all 36 local and 13/5 remote clients."""

import hashlib
import json

import pytest

from packet_tracer_mcp.adapters.cli import sp2_mixed_qualification
from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    _e5_closure,
    _path_admission,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    stage_definition,
)
from packet_tracer_mcp.domain.enterprise.services.native_dhcp_policy import (
    native_policy_network,
    native_policy_within_scope,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)

BUILD = "9.0.1.0858"
NATIVE_KEY = "Server-PT:dhcp_native_default_binding"
OLD_NATIVE_RECORD_SHA256 = (
    "af10ea312b2c491ec919f67aeca9c279ec2920fbbd52e3bb7e5c8852ff7911cf"
)


def _local_policy():
    return {
        "network": "10.80.1.0",
        "netmask": "255.255.255.192",
        "gateway": "10.80.1.1",
        "dns_server": "10.80.1.10",
        "lease_start": "10.80.1.16",
        "lease_end": "10.80.1.51",
        "max_users": 36,
        "selected_count": 36,
        "excluded_ranges": [("10.80.1.1", "10.80.1.1"), ("10.80.1.10", "10.80.1.10")],
    }


def test_structural_native_capacity_does_not_promote_the_old_public_grant():
    """Finite structural validity and measured scope admission are separate gates."""
    policy = _local_policy()
    network = native_policy_network(**policy)

    assert network is not None
    assert str(network) == "10.80.1.0/26"
    record = packet_tracer_service_capabilities(BUILD)[NATIVE_KEY]
    assert (
        record.native_policy_scope.network,
        record.native_policy_scope.max_users,
    ) == ("192.0.2.0", 2)
    serialized = json.dumps(
        record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    assert hashlib.sha256(serialized.encode()).hexdigest() == OLD_NATIVE_RECORD_SHA256
    admitted = {key: value for key, value in policy.items() if key != "selected_count"}
    assert not native_policy_within_scope(
        record.native_policy_scope, server_address="10.80.1.10", **admitted
    )


@pytest.mark.parametrize(
    "change",
    [
        {"max_users": 257, "selected_count": 257, "lease_end": "10.80.2.16"},
        {"max_users": True},
        {"selected_count": True},
        {"lease_end": "10.80.1.52"},
        {"gateway": "10.80.1.64"},
        {"excluded_ranges": [("10.80.1.16", "10.80.1.16")]},
    ],
)
def test_structural_native_capacity_retains_finite_policy_refusals(change):
    """Higher structural capacity cannot bypass malformed policy bounds."""
    assert native_policy_network(**{**_local_policy(), **change}) is None


def test_capacity_private_composition_preserves_all_three_simultaneous_demands():
    """The real plans retain all local and remote clients with distinct pools."""
    constructor = getattr(
        sp2_mixed_qualification, "sp2_capacity_product_contract", None
    )
    assert callable(constructor), (
        "The separately identified capacity profile is not composed."
    )
    contract = constructor(BUILD, "sp2-capacity-profile")

    assert len(contract.topology.devices) == 64
    assert len(contract.topology.links) == 65
    assert len(contract.configuration_plan.actions) == 153
    assert len(contract.service_plan.verification_expectations) == 437
    pools = {
        item.segment_id: item
        for item in contract.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    }
    assert {(name, item.max_users) for name, item in pools.items()} == {
        ("hq-data", 36),
        ("br1-data", 13),
        ("br2-data", 5),
    }
    hq = pools["hq-data"]
    assert (hq.prefix, hq.lease_start, hq.lease_end, hq.effective_pool_name) == (
        26,
        "10.80.1.16",
        "10.80.1.51",
        "serverPool",
    )
    assert (pools["br1-data"].prefix, pools["br2-data"].prefix) == (27, 27)
    leases = [
        item
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    ]
    assert len(leases) == 54
    assert len({item.client_device_name for item in leases}) == 54
    assert all(
        record.source.startswith("candidate:")
        for record in (
            contract.service_capabilities[NATIVE_KEY],
            contract.service_capabilities["Server-PT:dhcp_relay_named_pool_binding"],
        )
    )
    # The old mixed profile and default records stay independently reconstructible.
    old = sp2_mixed_qualification.sp2_mixed_product_contract(BUILD, "sp2-mixed-profile")
    assert len(old.topology.devices) == 18
    assert len(old.topology.links) == 17
    assert len(old.service_plan.verification_expectations) == 93
    assert old.service_capabilities[NATIVE_KEY].native_policy_scope.max_users == 5


def test_capacity_stage_has_its_own_pinned_fixture_and_protected_finalization():
    """The new demand cannot inherit the eleven-client stage's grants or shape."""
    definition = stage_definition("SP2-CAPACITY-PRODUCT")
    assert definition is not None, (
        "The capacity workload has no independently bounded stage."
    )
    contract = sp2_mixed_qualification.sp2_capacity_product_contract(
        BUILD, "capacity-stage"
    )

    assert definition.executable
    assert (definition.profile_id, definition.profile_version) == (
        "SP2-CAPACITY-PRODUCT",
        "1",
    )
    assert definition.allowed_channels == ("file",)
    assert len(definition.selected_clients) == 54
    assert {(item.name, item.model) for item in definition.fixtures} == {
        (item.name, item.model) for item in contract.topology.devices
    }
    assert {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in definition.links
    } == {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in contract.topology.links
    }
    assert definition.setup_operations == 261
    assert definition.reserve_operations == 131
    assert definition.budget.reserve_seconds >= 1630
    assert definition.planned_minimum_operations <= definition.budget.max_operations


def test_capacity_hybrid_stage_verifies_every_selected_client_and_preserves_budgets(
    tmp_path,
):
    """Real coordinator/product over substituted native and campus boundaries."""
    from test_sp2_mixed_product_stage import _run

    definition = stage_definition("SP2-CAPACITY-PRODUCT")
    assert definition is not None, (
        "The capacity workload has no independently bounded stage."
    )
    run = _run(
        tmp_path, stage="SP2-CAPACITY-PRODUCT", run_id="sp2-capacity-stage-offline"
    )

    product = run.measurement("M-SP2-CAPACITY-PRODUCT")
    assert product.conclusion.value == "supported_in_sample", (
        product.causes,
        run.record.primary_failure,
    )
    assert set(product.facts["clients"]) == set(definition.selected_clients)
    assert all(
        set(row["checks"].values()) == {"verified"}
        for row in product.facts["clients"].values()
    )
    final = run.measurement("M-SP2-CAPACITY-FINAL")
    assert final.conclusion.value == "supported_in_sample", final.facts
    assert run.record.restoration_proven
    assert run.snapshot["dhcp_runs"] == []
    assert run.record.budget.used_operations <= definition.budget.max_operations
    print(
        f"\nSP2-CAPACITY campus_calls={run.switching.campus_calls} engine_calls={run.switching.engine_product_calls} stage_operations={run.record.budget.used_operations} seconds={run.record.budget.elapsed_seconds}"
    )


@pytest.mark.parametrize("local_only", [False, True])
def test_capacity_selected_l2_components_are_in_the_actual_e5_effect_scope(local_only):
    """Blank native switches need the selected trunks before readiness can observe them."""
    contract = sp2_mixed_qualification.sp2_capacity_product_contract(
        BUILD, "capacity-scope"
    )
    services = contract.service_plan.services
    if local_only:
        services = [item for item in services if item.id == "service/hq/hq-dhcp"]
    assert services
    unsupported, paths = _path_admission(
        contract.configuration_plan,
        contract.service_plan,
        services,
        links=contract.topology.links,
    )
    assert unsupported == []
    scope = _e5_closure(
        contract.configuration_plan,
        contract.service_plan,
        services,
        extra_action_ids=sorted(
            {identifier for path in paths.values() for identifier in path.action_ids}
        ),
    )
    trunks = {
        item.id
        for item in contract.configuration_plan.actions
        if item.action_type.value == "configure_trunk" and item.site_id == "hq"
    }
    assert len(trunks) == 10
    assert trunks <= scope, sorted(trunks - scope)
    if local_only:
        assert not any(
            item.site_id != "hq"
            for item in contract.configuration_plan.actions
            if item.id in scope
        )


def test_capacity_starts_with_unconfigured_l2_and_installs_each_required_trunk(
    tmp_path,
):
    """A full plan is not an initial state oracle for the new native fixture."""
    from test_sp2_mixed_product_stage import _run

    run = _run(tmp_path, stage="SP2-CAPACITY-PRODUCT", run_id="capacity-blank-l2")

    product = run.measurement("M-SP2-CAPACITY-PRODUCT")
    assert product.conclusion.value == "supported_in_sample", product.causes
    assert len(run.campus.applied_switch_payloads) >= 10
    trunks = [
        end
        for switch in run.campus.network.switches.values()
        for end in switch.trunks.values()
    ]
    assert len(trunks) == 10
    assert all(10 in end.allowed for end in trunks)
    assert run.record.restoration_proven


def test_capacity_missing_actual_trunk_state_blocks_dependent_dhcp_and_services(
    tmp_path,
):
    """An ignored native setter cannot be replaced by a compiled desired value."""
    from test_sp2_mixed_product_stage import _run

    run = _run(
        tmp_path,
        stage="SP2-CAPACITY-PRODUCT",
        run_id="capacity-missing-l2",
        campus_config=lambda campus: setattr(
            campus, "ignored_trunk_switch", "HQ-DEFAULT-ACCESS-SW-01"
        ),
    )

    product = run.measurement("M-SP2-CAPACITY-PRODUCT")
    assert product.conclusion.value == "inconclusive"
    assert run.campus.applied_switch_payloads
    assert run.campus.network.switches["HQ-DEFAULT-ACCESS-SW-01"].trunks == {}
    assert not any(
        row["checks"]["http_fetch"] == "verified"
        for row in product.facts["clients"].values()
    )
    assert run.record.restoration_proven


def test_capacity_small_ordinary_allowance_retains_terminal_and_owned_cleanup(
    tmp_path, monkeypatch
):
    """A joint cutoff is truthful incomplete work with protected finalization."""
    from test_sp2_mixed_product_stage import _run

    run = _run(
        tmp_path,
        stage="SP2-CAPACITY-PRODUCT",
        run_id="capacity-small-grant",
        operation_ceiling=800,
        monkeypatch=monkeypatch,
    )

    assert (
        run.measurement("M-SP2-CAPACITY-PRODUCT").conclusion.value
        != "supported_in_sample"
    )
    assert run.measurement("M-SP2-CAPACITY-FINAL").conclusion.value == "inconclusive"
    assert run.record.restoration_proven
    assert run.record.budget.used_operations <= 800
    assert run.snapshot["devices"] == []


def test_capacity_profile_cannot_execute_a_legacy_mixed_contract(tmp_path):
    """The new fixture, plans and catalog cannot inherit the old profile identity."""
    from test_sp2_mixed_product_stage import _run

    run = _run(
        tmp_path,
        stage="SP2-CAPACITY-PRODUCT",
        run_id="capacity-wrong-contract",
        contract_factory=sp2_mixed_qualification.sp2_mixed_product_contract,
    )

    assert run.record.primary_failure == "sp2_mixed_topology_hash_changed"
    assert "service_apply" not in run.campus.events
    assert run.snapshot["dhcp_timeline"] == []
    assert run.record.restoration_proven
