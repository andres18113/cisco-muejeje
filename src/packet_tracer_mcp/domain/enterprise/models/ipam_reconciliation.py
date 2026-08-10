"""Backend-neutral models for reconciling infrastructure IPv4 identities."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AddressPurpose(str, Enum):
    """Semantic owner of an address; never a backend interface command."""

    ENDPOINT = "endpoint"
    SVI = "svi"
    MANAGEMENT = "management"
    TRANSIT = "transit"
    LOOPBACK = "loopback"
    FHRP_MEMBER = "fhrp_member"
    FHRP_VIP = "fhrp_vip"


class AddressReconcileStatus(str, Enum):
    ALLOCATED_WITHOUT_RENUMBER = "allocated_without_renumber"
    RENUMBER_REQUIRED = "renumber_required"
    INSUFFICIENT_CAPACITY = "insufficient_capacity"
    CONFLICT = "conflict"
    INVALID_DEMAND = "invalid_demand"


# Short neutral alias for consumers that do not need the IPAM-specific prefix.
ReconciliationStatus = AddressReconcileStatus


class AddressReconcileIssueCode(str, Enum):
    INVALID_ADDRESS_SPACE = "invalid_address_space"
    INVALID_DEMAND = "invalid_demand"
    DUPLICATE_DEMAND_ID = "duplicate_demand_id"
    INVALID_EXISTING_BINDING = "invalid_existing_binding"
    DUPLICATE_EXISTING_BINDING_ID = "duplicate_existing_binding_id"
    DUPLICATE_EXISTING_ADDRESS = "duplicate_existing_address"
    AMBIGUOUS_EXISTING_BINDING = "ambiguous_existing_binding"
    REQUESTED_ADDRESS_CONFLICT = "requested_address_conflict"
    EXISTING_BINDING_RENUMBER = "existing_binding_renumber"
    INSUFFICIENT_CAPACITY = "insufficient_capacity"


class InfrastructureAddressDemand(BaseModel):
    """One explicitly requested infrastructure identity within an IPv4 pool."""

    id: str
    purpose: AddressPurpose
    owner_id: str
    network: str
    segment_id: str = ""
    group_id: str = ""
    requested_ipv4: str = ""
    interface_prefix: int | None = None


class ExistingAddressBinding(BaseModel):
    """Observed or previously deployed address that reconciliation must preserve."""

    id: str
    purpose: AddressPurpose
    owner_id: str
    ipv4: str
    prefix: int
    demand_id: str = ""
    segment_id: str = ""
    group_id: str = ""
    source: str = "existing_plan"


class FinalAddressBinding(BaseModel):
    id: str
    demand_id: str = ""
    purpose: AddressPurpose
    owner_id: str
    ipv4: str
    prefix: int
    segment_id: str = ""
    group_id: str = ""
    preserved: bool = False
    source_binding_id: str = ""


class AddressRenumbering(BaseModel):
    demand_id: str
    owner_id: str
    previous_ipv4: str
    proposed_ipv4: str
    previous_prefix: int
    proposed_prefix: int
    reason: str


class AddressReconcileIssue(BaseModel):
    code: AddressReconcileIssueCode
    message: str
    demand_id: str = ""
    binding_id: str = ""


class FinalAddressPlan(BaseModel):
    address_space: str
    bindings: list[FinalAddressBinding] = Field(default_factory=list)
    renumbering: list[AddressRenumbering] = Field(default_factory=list)
    semantic_hash: str = ""

    def binding_for_demand(self, demand_id: str) -> FinalAddressBinding | None:
        return next(
            (item for item in self.bindings if item.demand_id == demand_id),
            None,
        )


class AddressReconcileResult(BaseModel):
    status: AddressReconcileStatus
    plan: FinalAddressPlan | None = None
    issues: list[AddressReconcileIssue] = Field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        """The result contains a complete candidate plan.

        ``RENUMBER_REQUIRED`` is intentionally usable for review, not safe to
        apply.  Callers that may mutate a deployment must use
        :attr:`can_apply_without_renumber` instead.
        """
        return self.status in {
            AddressReconcileStatus.ALLOCATED_WITHOUT_RENUMBER,
            AddressReconcileStatus.RENUMBER_REQUIRED,
        }

    @property
    def can_apply_without_renumber(self) -> bool:
        return self.status is AddressReconcileStatus.ALLOCATED_WITHOUT_RENUMBER

    @property
    def requires_renumbering_approval(self) -> bool:
        return self.status is AddressReconcileStatus.RENUMBER_REQUIRED

    def compact_summary(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "bindings": len(self.plan.bindings) if self.plan else 0,
            "renumbering": len(self.plan.renumbering) if self.plan else 0,
            "issues": [item.code.value for item in self.issues],
            "semantic_hash": self.plan.semantic_hash if self.plan else "",
        }
