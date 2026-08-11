"""E9.5 infrastructure IPAM reconciliation regressions."""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.ipam_reconciliation import (
    AddressPurpose,
    AddressReconcileStatus,
    ExistingAddressBinding,
    InfrastructureAddressDemand,
)
from src.packet_tracer_mcp.domain.enterprise.services.address_reconciler import (
    AddressReconciler,
)


def _demand(
    identifier: str,
    purpose: AddressPurpose,
    owner: str,
    network: str,
    *,
    segment: str = "",
    group: str = "",
) -> InfrastructureAddressDemand:
    return InfrastructureAddressDemand(
        id=identifier,
        purpose=purpose,
        owner_id=owner,
        network=network,
        segment_id=segment,
        group_id=group,
    )


def _binding(
    identifier: str,
    purpose: AddressPurpose,
    owner: str,
    ipv4: str,
    prefix: int,
    *,
    demand: str = "",
    segment: str = "",
    group: str = "",
) -> ExistingAddressBinding:
    return ExistingAddressBinding(
        id=identifier,
        demand_id=demand,
        purpose=purpose,
        owner_id=owner,
        ipv4=ipv4,
        prefix=prefix,
        segment_id=segment,
        group_id=group,
    )


def test_hsrp_gets_two_members_and_one_vip_without_renumbering_endpoints():
    existing = [
        _binding("pc-1", AddressPurpose.ENDPOINT, "pc-1", "10.20.0.10", 24),
        _binding("pc-2", AddressPurpose.ENDPOINT, "pc-2", "10.20.0.11", 24),
        _binding(
            "r1-member", AddressPurpose.FHRP_MEMBER, "r1", "10.20.0.2", 24,
            demand="hsrp-r1", segment="data", group="hsrp-data",
        ),
        _binding(
            "r2-member", AddressPurpose.FHRP_MEMBER, "r2", "10.20.0.3", 24,
            demand="hsrp-r2", segment="data", group="hsrp-data",
        ),
    ]
    demands = [
        _demand(
            "hsrp-r1", AddressPurpose.FHRP_MEMBER, "r1", "10.20.0.0/24",
            segment="data", group="hsrp-data",
        ),
        _demand(
            "hsrp-r2", AddressPurpose.FHRP_MEMBER, "r2", "10.20.0.0/24",
            segment="data", group="hsrp-data",
        ),
        _demand(
            "hsrp-vip", AddressPurpose.FHRP_VIP, "hsrp-data", "10.20.0.0/24",
            segment="data", group="hsrp-data",
        ),
    ]

    result = AddressReconciler().reconcile(
        address_space="10.20.0.0/24",
        demands=demands,
        existing_bindings=existing,
    )

    assert result.status is AddressReconcileStatus.ALLOCATED_WITHOUT_RENUMBER
    assert result.plan is not None
    by_demand = {
        item.demand_id: item
        for item in result.plan.bindings
        if item.demand_id
    }
    assert by_demand["hsrp-r1"].ipv4 == "10.20.0.2"
    assert by_demand["hsrp-r2"].ipv4 == "10.20.0.3"
    assert len({by_demand[key].ipv4 for key in ("hsrp-r1", "hsrp-r2", "hsrp-vip")}) == 3
    endpoints = {
        item.owner_id: item.ipv4
        for item in result.plan.bindings
        if item.purpose is AddressPurpose.ENDPOINT
    }
    assert endpoints == {"pc-1": "10.20.0.10", "pc-2": "10.20.0.11"}
    assert result.plan.renumbering == []


def test_transit_reconciliation_preserves_existing_peer_bindings():
    demands = [
        _demand(
            "wan-r1", AddressPurpose.TRANSIT, "r1:G0/0", "10.30.0.0/30",
            group="wan-link-1",
        ),
        _demand(
            "wan-r2", AddressPurpose.TRANSIT, "r2:G0/0", "10.30.0.0/30",
            group="wan-link-1",
        ),
    ]
    existing = [
        _binding(
            "wan-r1-old", AddressPurpose.TRANSIT, "r1:G0/0", "10.30.0.1", 30,
            demand="wan-r1", group="wan-link-1",
        ),
        _binding(
            "wan-r2-old", AddressPurpose.TRANSIT, "r2:G0/0", "10.30.0.2", 30,
            demand="wan-r2", group="wan-link-1",
        ),
    ]

    result = AddressReconciler().reconcile("10.30.0.0/24", demands, existing)

    assert result.status is AddressReconcileStatus.ALLOCATED_WITHOUT_RENUMBER
    assert result.plan is not None
    assigned = {
        item.demand_id: item.ipv4
        for item in result.plan.bindings
        if item.demand_id
    }
    assert assigned == {"wan-r1": "10.30.0.1", "wan-r2": "10.30.0.2"}
    assert all(
        item.preserved
        for item in result.plan.bindings
        if item.demand_id in {"wan-r1", "wan-r2"}
    )


def test_duplicate_existing_address_is_a_conflict():
    existing = [
        _binding("pc-1", AddressPurpose.ENDPOINT, "pc-1", "10.40.0.10", 24),
        _binding("pc-2", AddressPurpose.ENDPOINT, "pc-2", "10.40.0.10", 24),
    ]

    result = AddressReconciler().reconcile("10.40.0.0/24", [], existing)

    assert result.status is AddressReconcileStatus.CONFLICT
    assert result.plan is None
    assert any(issue.code == "duplicate_existing_address" for issue in result.issues)


def test_demand_id_cannot_silently_retarget_an_existing_owner():
    demands = [
        _demand("mgmt-dist", AddressPurpose.MANAGEMENT, "dist-2", "10.41.0.0/24")
    ]
    existing = [
        _binding(
            "mgmt-old", AddressPurpose.MANAGEMENT, "dist-1", "10.41.0.2", 24,
            demand="mgmt-dist",
        )
    ]

    result = AddressReconciler().reconcile("10.41.0.0/24", demands, existing)

    assert result.status is AddressReconcileStatus.CONFLICT
    assert result.plan is None
    assert result.issues[0].code == "ambiguous_existing_binding"


def test_exhausted_pool_is_reported_as_insufficient_capacity():
    existing = [
        _binding("pc-1", AddressPurpose.ENDPOINT, "pc-1", "10.50.0.1", 30),
        _binding("pc-2", AddressPurpose.ENDPOINT, "pc-2", "10.50.0.2", 30),
    ]
    demands = [
        _demand("svi-data", AddressPurpose.SVI, "dist-1", "10.50.0.0/30")
    ]

    result = AddressReconciler().reconcile("10.50.0.0/30", demands, existing)

    assert result.status is AddressReconcileStatus.INSUFFICIENT_CAPACITY
    assert result.plan is None
    assert result.issues[0].demand_id == "svi-data"


def test_out_of_scope_existing_binding_proposes_explicit_renumber():
    demands = [
        _demand(
            "mgmt-dist", AddressPurpose.MANAGEMENT, "dist-1", "10.60.10.0/24",
            segment="management",
        )
    ]
    existing = [
        _binding(
            "mgmt-old", AddressPurpose.MANAGEMENT, "dist-1", "10.60.9.2", 24,
            demand="mgmt-dist", segment="management",
        ),
        _binding("pc-1", AddressPurpose.ENDPOINT, "pc-1", "10.60.10.10", 24),
    ]

    result = AddressReconciler().reconcile("10.60.0.0/16", demands, existing)

    assert result.status is AddressReconcileStatus.RENUMBER_REQUIRED
    assert result.is_usable
    assert result.requires_renumbering_approval
    assert not result.can_apply_without_renumber
    assert result.plan is not None
    assert len(result.plan.renumbering) == 1
    change = result.plan.renumbering[0]
    assert change.demand_id == "mgmt-dist"
    assert change.previous_ipv4 == "10.60.9.2"
    assert change.proposed_ipv4 == "10.60.10.1"
    assert next(
        item for item in result.plan.bindings if item.owner_id == "pc-1"
    ).ipv4 == "10.60.10.10"


def test_invalid_demand_is_rejected_without_guessing_a_network():
    demands = [
        _demand("bad-loopback", AddressPurpose.LOOPBACK, "r1", "not-a-network")
    ]

    result = AddressReconciler().reconcile("10.70.0.0/16", demands, [])

    assert result.status is AddressReconcileStatus.INVALID_DEMAND
    assert result.plan is None


def test_reconciliation_is_deterministic_and_loopbacks_are_only_demand_driven():
    demands = [
        _demand("svi", AddressPurpose.SVI, "dist", "10.80.10.0/24"),
        _demand("loop-r2", AddressPurpose.LOOPBACK, "r2", "10.80.255.0/29"),
        _demand("loop-r1", AddressPurpose.LOOPBACK, "r1", "10.80.255.0/29"),
    ]
    existing = [
        _binding("pc", AddressPurpose.ENDPOINT, "pc", "10.80.10.10", 24)
    ]

    first = AddressReconciler().reconcile("10.80.0.0/16", demands, existing)
    second = AddressReconciler().reconcile(
        "10.80.0.0/16", list(reversed(demands)), list(reversed(existing))
    )

    assert first.plan is not None and second.plan is not None
    assert first.plan.semantic_hash == second.plan.semantic_hash
    assert [item.model_dump() for item in first.plan.bindings] == [
        item.model_dump() for item in second.plan.bindings
    ]
    loopbacks = [
        item for item in first.plan.bindings
        if item.purpose is AddressPurpose.LOOPBACK
    ]
    assert len(loopbacks) == 2
    assert all(item.prefix == 32 for item in loopbacks)
