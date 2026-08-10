"""Reconcile infrastructure IPv4 demand without silently renumbering state."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from collections import defaultdict

from ..models.ipam_reconciliation import (
    AddressPurpose,
    AddressReconcileIssue,
    AddressReconcileIssueCode,
    AddressReconcileResult,
    AddressReconcileStatus,
    AddressRenumbering,
    ExistingAddressBinding,
    FinalAddressBinding,
    FinalAddressPlan,
    InfrastructureAddressDemand,
)


class AddressReconciler:
    """Preserve deployed identities first, then allocate explicit new demand.

    This service produces a desired plan only.  It never applies renumbering and
    does not assume Cisco IOS, Packet Tracer, or any particular backend.
    """

    def reconcile(
        self,
        address_space: str,
        demands: list[InfrastructureAddressDemand],
        existing_bindings: list[ExistingAddressBinding],
    ) -> AddressReconcileResult:
        enterprise = self._parse_network(address_space)
        if enterprise is None:
            return self._failure(
                AddressReconcileStatus.INVALID_DEMAND,
                AddressReconcileIssueCode.INVALID_ADDRESS_SPACE,
                f"Address space {address_space!r} is not a strict IPv4 network.",
            )

        demand_networks, demand_issues = self._validate_demands(
            enterprise, demands,
        )
        if demand_issues:
            return AddressReconcileResult(
                status=AddressReconcileStatus.INVALID_DEMAND,
                issues=demand_issues,
            )

        existing_addresses, existing_issues = self._validate_existing(
            enterprise, existing_bindings,
        )
        if existing_issues:
            return AddressReconcileResult(
                status=AddressReconcileStatus.CONFLICT,
                issues=existing_issues,
            )

        by_demand, by_semantics, binding_issues = self._index_existing(
            existing_bindings,
        )
        if binding_issues:
            return AddressReconcileResult(
                status=AddressReconcileStatus.CONFLICT,
                issues=binding_issues,
            )

        occupied = dict(existing_addresses)
        matched_binding_ids: set[str] = set()
        final: list[FinalAddressBinding] = []
        renumbering: list[AddressRenumbering] = []
        issues: list[AddressReconcileIssue] = []

        for demand in self._ordered_demands(demands, demand_networks):
            network = demand_networks[demand.id]
            prefix = self._interface_prefix(demand, network)
            matched, issue = self._match_existing(
                demand, by_demand, by_semantics, matched_binding_ids,
            )
            if issue is not None:
                return AddressReconcileResult(
                    status=AddressReconcileStatus.CONFLICT,
                    issues=[issue],
                )
            if matched is not None:
                matched_binding_ids.add(matched.id)
                if self._can_preserve(demand, matched, network, prefix):
                    final.append(self._final_from_existing(demand, matched, prefix))
                    continue

            requested, request_issue = self._requested_candidate(
                demand, network, occupied, matched,
            )
            if request_issue is not None:
                return AddressReconcileResult(
                    status=AddressReconcileStatus.CONFLICT,
                    issues=[request_issue],
                )
            candidate = requested or self._first_available(network, occupied)
            if candidate is None:
                return AddressReconcileResult(
                    status=AddressReconcileStatus.INSUFFICIENT_CAPACITY,
                    issues=[AddressReconcileIssue(
                        code=AddressReconcileIssueCode.INSUFFICIENT_CAPACITY,
                        message=(
                            f"No usable IPv4 address remains in {network} for "
                            f"demand {demand.id!r}."
                        ),
                        demand_id=demand.id,
                    )],
                )

            candidate_text = str(candidate)
            occupied[candidate_text] = f"demand:{demand.id}"
            final.append(FinalAddressBinding(
                id=f"address/{demand.id}",
                demand_id=demand.id,
                purpose=demand.purpose,
                owner_id=demand.owner_id,
                ipv4=candidate_text,
                prefix=prefix,
                segment_id=demand.segment_id,
                group_id=demand.group_id,
                preserved=False,
                source_binding_id=matched.id if matched else "",
            ))
            if matched is not None:
                reason = self._renumber_reason(demand, matched, network, prefix)
                renumbering.append(AddressRenumbering(
                    demand_id=demand.id,
                    owner_id=demand.owner_id,
                    previous_ipv4=matched.ipv4,
                    proposed_ipv4=candidate_text,
                    previous_prefix=matched.prefix,
                    proposed_prefix=prefix,
                    reason=reason,
                ))
                issues.append(AddressReconcileIssue(
                    code=AddressReconcileIssueCode.EXISTING_BINDING_RENUMBER,
                    message=reason,
                    demand_id=demand.id,
                    binding_id=matched.id,
                ))

        for binding in sorted(existing_bindings, key=self._binding_sort_key):
            if binding.id in matched_binding_ids:
                continue
            final.append(FinalAddressBinding(
                id=binding.id,
                demand_id=binding.demand_id,
                purpose=binding.purpose,
                owner_id=binding.owner_id,
                ipv4=str(existing_addresses[binding.ipv4]),
                prefix=binding.prefix,
                segment_id=binding.segment_id,
                group_id=binding.group_id,
                preserved=True,
                source_binding_id=binding.id,
            ))

        final.sort(key=self._final_sort_key)
        renumbering.sort(key=lambda item: (item.demand_id, item.owner_id))
        plan = FinalAddressPlan(
            address_space=str(enterprise),
            bindings=final,
            renumbering=renumbering,
        )
        plan.semantic_hash = self._semantic_hash(plan)
        return AddressReconcileResult(
            status=(
                AddressReconcileStatus.RENUMBER_REQUIRED
                if renumbering
                else AddressReconcileStatus.ALLOCATED_WITHOUT_RENUMBER
            ),
            plan=plan,
            issues=issues,
        )

    @staticmethod
    def _parse_network(value: str) -> ipaddress.IPv4Network | None:
        try:
            parsed = ipaddress.ip_network(value, strict=True)
        except ValueError:
            return None
        return parsed if isinstance(parsed, ipaddress.IPv4Network) else None

    def _validate_demands(
        self,
        enterprise: ipaddress.IPv4Network,
        demands: list[InfrastructureAddressDemand],
    ) -> tuple[dict[str, ipaddress.IPv4Network], list[AddressReconcileIssue]]:
        networks: dict[str, ipaddress.IPv4Network] = {}
        issues: list[AddressReconcileIssue] = []
        seen: set[str] = set()
        for demand in demands:
            if not demand.id or demand.id in seen:
                issues.append(AddressReconcileIssue(
                    code=(
                        AddressReconcileIssueCode.DUPLICATE_DEMAND_ID
                        if demand.id in seen
                        else AddressReconcileIssueCode.INVALID_DEMAND
                    ),
                    message=f"Demand id {demand.id!r} must be non-empty and unique.",
                    demand_id=demand.id,
                ))
                continue
            seen.add(demand.id)
            network = self._parse_network(demand.network)
            if (
                network is None
                or not network.subnet_of(enterprise)
                or not demand.owner_id
            ):
                issues.append(AddressReconcileIssue(
                    code=AddressReconcileIssueCode.INVALID_DEMAND,
                    message=(
                        f"Demand {demand.id!r} must name an owner and a strict "
                        "IPv4 pool inside the enterprise address space."
                    ),
                    demand_id=demand.id,
                ))
                continue
            if demand.purpose is AddressPurpose.ENDPOINT:
                issues.append(AddressReconcileIssue(
                    code=AddressReconcileIssueCode.INVALID_DEMAND,
                    message=(
                        f"Demand {demand.id!r} is an endpoint; this reconciler "
                        "only creates explicitly requested infrastructure identities."
                    ),
                    demand_id=demand.id,
                ))
                continue
            if demand.purpose in {
                AddressPurpose.FHRP_MEMBER, AddressPurpose.FHRP_VIP,
            } and (not demand.group_id or not demand.segment_id):
                issues.append(AddressReconcileIssue(
                    code=AddressReconcileIssueCode.INVALID_DEMAND,
                    message=(
                        f"FHRP demand {demand.id!r} requires group_id and segment_id."
                    ),
                    demand_id=demand.id,
                ))
                continue
            prefix = self._interface_prefix(demand, network)
            if not 0 <= prefix <= 32 or (
                demand.purpose is AddressPurpose.LOOPBACK and prefix != 32
            ):
                issues.append(AddressReconcileIssue(
                    code=AddressReconcileIssueCode.INVALID_DEMAND,
                    message=f"Demand {demand.id!r} has invalid interface prefix {prefix}.",
                    demand_id=demand.id,
                ))
                continue
            if demand.requested_ipv4:
                requested = self._parse_address(demand.requested_ipv4)
                if requested is None or not self._usable_in(requested, network):
                    issues.append(AddressReconcileIssue(
                        code=AddressReconcileIssueCode.INVALID_DEMAND,
                        message=(
                            f"Requested address {demand.requested_ipv4!r} is not "
                            f"usable in {network}."
                        ),
                        demand_id=demand.id,
                    ))
                    continue
            networks[demand.id] = network
        return networks, issues

    def _validate_existing(
        self,
        enterprise: ipaddress.IPv4Network,
        bindings: list[ExistingAddressBinding],
    ) -> tuple[dict[str, ipaddress.IPv4Address], list[AddressReconcileIssue]]:
        addresses: dict[str, ipaddress.IPv4Address] = {}
        owners: dict[str, ExistingAddressBinding] = {}
        ids: set[str] = set()
        issues: list[AddressReconcileIssue] = []
        for binding in bindings:
            if not binding.id or binding.id in ids:
                issues.append(AddressReconcileIssue(
                    code=(
                        AddressReconcileIssueCode.DUPLICATE_EXISTING_BINDING_ID
                        if binding.id in ids
                        else AddressReconcileIssueCode.INVALID_EXISTING_BINDING
                    ),
                    message=f"Existing binding id {binding.id!r} must be unique.",
                    binding_id=binding.id,
                ))
                continue
            ids.add(binding.id)
            address = self._parse_address(binding.ipv4)
            if (
                address is None
                or address not in enterprise
                or not 0 <= binding.prefix <= 32
                or not binding.owner_id
            ):
                issues.append(AddressReconcileIssue(
                    code=AddressReconcileIssueCode.INVALID_EXISTING_BINDING,
                    message=f"Existing binding {binding.id!r} is not valid in {enterprise}.",
                    binding_id=binding.id,
                ))
                continue
            canonical = str(address)
            previous = owners.get(canonical)
            if previous is not None:
                issues.append(AddressReconcileIssue(
                    code=AddressReconcileIssueCode.DUPLICATE_EXISTING_ADDRESS,
                    message=(
                        f"Address {canonical} is owned by both {previous.id!r} "
                        f"and {binding.id!r}."
                    ),
                    binding_id=binding.id,
                ))
                continue
            owners[canonical] = binding
            addresses[binding.ipv4] = address
        return addresses, issues

    @staticmethod
    def _index_existing(
        bindings: list[ExistingAddressBinding],
    ) -> tuple[
        dict[str, ExistingAddressBinding],
        dict[tuple[str, str, str, str], list[ExistingAddressBinding]],
        list[AddressReconcileIssue],
    ]:
        by_demand: dict[str, ExistingAddressBinding] = {}
        by_semantics: dict[
            tuple[str, str, str, str], list[ExistingAddressBinding]
        ] = defaultdict(list)
        issues: list[AddressReconcileIssue] = []
        for binding in bindings:
            if binding.demand_id:
                previous = by_demand.get(binding.demand_id)
                if previous is not None:
                    issues.append(AddressReconcileIssue(
                        code=AddressReconcileIssueCode.AMBIGUOUS_EXISTING_BINDING,
                        message=(
                            f"Demand {binding.demand_id!r} is claimed by existing "
                            f"bindings {previous.id!r} and {binding.id!r}."
                        ),
                        demand_id=binding.demand_id,
                        binding_id=binding.id,
                    ))
                else:
                    by_demand[binding.demand_id] = binding
            if binding.purpose is not AddressPurpose.ENDPOINT:
                by_semantics[AddressReconciler._semantic_key(binding)].append(binding)
        return by_demand, by_semantics, issues

    @staticmethod
    def _match_existing(
        demand: InfrastructureAddressDemand,
        by_demand: dict[str, ExistingAddressBinding],
        by_semantics: dict[
            tuple[str, str, str, str], list[ExistingAddressBinding]
        ],
        matched_ids: set[str],
    ) -> tuple[ExistingAddressBinding | None, AddressReconcileIssue | None]:
        exact = by_demand.get(demand.id)
        if exact is not None:
            if (
                AddressReconciler._semantic_key(exact)
                != AddressReconciler._semantic_key(demand)
            ):
                return None, AddressReconcileIssue(
                    code=AddressReconcileIssueCode.AMBIGUOUS_EXISTING_BINDING,
                    message=(
                        f"Existing binding {exact.id!r} claims demand {demand.id!r} "
                        "but identifies a different semantic owner."
                    ),
                    demand_id=demand.id,
                    binding_id=exact.id,
                )
            return exact, None
        candidates = [
            item for item in by_semantics.get(AddressReconciler._semantic_key(demand), [])
            if item.id not in matched_ids
        ]
        if len(candidates) > 1:
            return None, AddressReconcileIssue(
                code=AddressReconcileIssueCode.AMBIGUOUS_EXISTING_BINDING,
                message=(
                    f"Demand {demand.id!r} matches multiple existing semantic bindings."
                ),
                demand_id=demand.id,
            )
        return (candidates[0] if candidates else None), None

    @staticmethod
    def _semantic_key(item: object) -> tuple[str, str, str, str]:
        return (
            getattr(item, "purpose").value,
            getattr(item, "owner_id"),
            getattr(item, "segment_id"),
            getattr(item, "group_id"),
        )

    @staticmethod
    def _ordered_demands(
        demands: list[InfrastructureAddressDemand],
        networks: dict[str, ipaddress.IPv4Network],
    ) -> list[InfrastructureAddressDemand]:
        return sorted(demands, key=lambda item: (
            int(networks[item.id].network_address),
            networks[item.id].prefixlen,
            item.group_id,
            item.purpose.value,
            item.owner_id,
            item.id,
        ))

    @staticmethod
    def _interface_prefix(
        demand: InfrastructureAddressDemand,
        network: ipaddress.IPv4Network,
    ) -> int:
        if demand.interface_prefix is not None:
            return demand.interface_prefix
        return 32 if demand.purpose is AddressPurpose.LOOPBACK else network.prefixlen

    def _can_preserve(
        self,
        demand: InfrastructureAddressDemand,
        binding: ExistingAddressBinding,
        network: ipaddress.IPv4Network,
        prefix: int,
    ) -> bool:
        address = self._parse_address(binding.ipv4)
        return bool(
            address is not None
            and self._usable_in(address, network)
            and binding.prefix == prefix
            and (
                not demand.requested_ipv4
                or str(address) == str(self._parse_address(demand.requested_ipv4))
            )
        )

    @staticmethod
    def _final_from_existing(
        demand: InfrastructureAddressDemand,
        binding: ExistingAddressBinding,
        prefix: int,
    ) -> FinalAddressBinding:
        return FinalAddressBinding(
            id=f"address/{demand.id}",
            demand_id=demand.id,
            purpose=demand.purpose,
            owner_id=demand.owner_id,
            ipv4=str(ipaddress.IPv4Address(binding.ipv4)),
            prefix=prefix,
            segment_id=demand.segment_id,
            group_id=demand.group_id,
            preserved=True,
            source_binding_id=binding.id,
        )

    def _requested_candidate(
        self,
        demand: InfrastructureAddressDemand,
        network: ipaddress.IPv4Network,
        occupied: dict[str, object],
        matched: ExistingAddressBinding | None,
    ) -> tuple[ipaddress.IPv4Address | None, AddressReconcileIssue | None]:
        if not demand.requested_ipv4:
            return None, None
        requested = ipaddress.IPv4Address(demand.requested_ipv4)
        owner = occupied.get(str(requested))
        if owner is None or (
            matched is not None and str(requested) == str(ipaddress.IPv4Address(matched.ipv4))
        ):
            return requested, None
        return None, AddressReconcileIssue(
            code=AddressReconcileIssueCode.REQUESTED_ADDRESS_CONFLICT,
            message=(
                f"Requested address {requested} for {demand.id!r} is already bound."
            ),
            demand_id=demand.id,
        )

    @staticmethod
    def _first_available(
        network: ipaddress.IPv4Network,
        occupied: dict[str, object],
    ) -> ipaddress.IPv4Address | None:
        return next(
            (item for item in network.hosts() if str(item) not in occupied),
            None,
        )

    @staticmethod
    def _parse_address(value: str) -> ipaddress.IPv4Address | None:
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError:
            return None
        return parsed if isinstance(parsed, ipaddress.IPv4Address) else None

    @staticmethod
    def _usable_in(
        address: ipaddress.IPv4Address,
        network: ipaddress.IPv4Network,
    ) -> bool:
        if address not in network:
            return False
        if network.prefixlen >= 31:
            return True
        return address not in {network.network_address, network.broadcast_address}

    @staticmethod
    def _renumber_reason(
        demand: InfrastructureAddressDemand,
        binding: ExistingAddressBinding,
        network: ipaddress.IPv4Network,
        prefix: int,
    ) -> str:
        address = ipaddress.IPv4Address(binding.ipv4)
        if not AddressReconciler._usable_in(address, network):
            return (
                f"Existing address {address} for {demand.id!r} is outside usable "
                f"pool {network}; explicit renumbering approval is required."
            )
        if binding.prefix != prefix:
            return (
                f"Existing prefix /{binding.prefix} for {demand.id!r} does not "
                f"match required /{prefix}; explicit binding change is required."
            )
        return (
            f"Existing address {address} for {demand.id!r} differs from requested "
            f"address {demand.requested_ipv4}; explicit renumbering approval is required."
        )

    @staticmethod
    def _binding_sort_key(item: ExistingAddressBinding) -> tuple[object, ...]:
        return (
            int(ipaddress.IPv4Address(item.ipv4)), item.prefix,
            item.purpose.value, item.owner_id, item.id,
        )

    @staticmethod
    def _final_sort_key(item: FinalAddressBinding) -> tuple[object, ...]:
        return (
            int(ipaddress.IPv4Address(item.ipv4)), item.prefix,
            item.purpose.value, item.owner_id, item.demand_id, item.id,
        )

    @staticmethod
    def _semantic_hash(plan: FinalAddressPlan) -> str:
        payload = plan.model_dump(mode="json", exclude={"semantic_hash"})
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _failure(
        status: AddressReconcileStatus,
        code: AddressReconcileIssueCode,
        message: str,
    ) -> AddressReconcileResult:
        return AddressReconcileResult(
            status=status,
            issues=[AddressReconcileIssue(code=code, message=message)],
        )
