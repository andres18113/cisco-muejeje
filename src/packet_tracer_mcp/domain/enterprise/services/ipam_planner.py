"""Asignación VLSM IPv4 determinista con bloques resumibles por sede."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING

from ...models.errors import ErrorCode, PlanError, ValidationResult
from ..models.addressing import (
    AddressSpace,
    AddressingPlan,
    SiteAddressBlock,
    SubnetAllocation,
    SubnetRequirement,
)
from ..models.enterprise_plan import EnterprisePlan, SitePlan
from ..models.segments import NetworkSegment


@dataclass(frozen=True)
class IPAMPlanResult:
    plan: AddressingPlan | None
    validation: ValidationResult


def growth_fraction(value: float) -> Decimal:
    """Acepta 0.30 (fracción) y 30 (porcentaje), con una única semántica interna."""
    decimal_value = Decimal(str(value))
    return decimal_value if decimal_value <= 1 else decimal_value / Decimal("100")


def growth_hosts(raw_hosts: int, growth_percent: float) -> int:
    """Reserva crecimiento una vez mediante ceil, sin cálculos con float binario."""
    if raw_hosts <= 0:
        return 0
    return int((Decimal(raw_hosts) * growth_fraction(growth_percent)).to_integral_value(ROUND_CEILING))


def usable_hosts(prefix: int) -> int:
    return (1 << (32 - prefix)) - 2


def subnet_requirement_for(
    segment_id: str,
    raw_hosts: int,
    growth_percent: float,
    minimum_lan_prefix: int = 30,
    reserved_hosts: int = 0,
) -> SubnetRequirement:
    """Calcula una necesidad IPv4 LAN centralizada, incluida la gateway."""
    growth_count = growth_hosts(raw_hosts, growth_percent)
    required = raw_hosts + growth_count + 1 + reserved_hosts
    for prefix in range(minimum_lan_prefix, -1, -1):
        if usable_hosts(prefix) >= required:
            return SubnetRequirement(
                segment_id=segment_id,
                raw_hosts=raw_hosts,
                growth_percent=growth_percent,
                growth_hosts=growth_count,
                required_usable_hosts=required,
                reserved_hosts=reserved_hosts,
                prefix=prefix,
            )
    return SubnetRequirement(
        segment_id=segment_id,
        raw_hosts=raw_hosts,
        growth_percent=growth_percent,
        growth_hosts=growth_count,
        required_usable_hosts=required,
        reserved_hosts=reserved_hosts,
        prefix=0,
    )


class IPAMPlanner:
    """Planifica IPv4 sólo cuando la intención declara un address space Enterprise."""

    def __init__(self, minimum_lan_prefix: int = 30) -> None:
        self.minimum_lan_prefix = minimum_lan_prefix

    def plan(self, enterprise_plan: EnterprisePlan) -> IPAMPlanResult:
        result = ValidationResult()
        if enterprise_plan.address_space is None:
            return IPAMPlanResult(plan=None, validation=result)
        try:
            enterprise_network = ipaddress.ip_network(enterprise_plan.address_space, strict=True)
        except ValueError:
            return self._error(result, ErrorCode.ENTERPRISE_ADDRESS_SPACE_INVALID,
                               "El espacio Enterprise debe ser una red IPv4 CIDR válida.")
        if not isinstance(enterprise_network, ipaddress.IPv4Network):
            return self._error(result, ErrorCode.ENTERPRISE_ADDRESS_SPACE_INVALID,
                               "E2 sólo admite direccionamiento IPv4.")

        requirements = {
            site.site_id: self._site_requirements(site)
            for site in enterprise_plan.sites
        }
        explicit, explicit_errors = self._explicit_site_blocks(
            enterprise_plan.sites, enterprise_network, requirements
        )
        result.errors.extend(explicit_errors)
        if not result.is_valid:
            return IPAMPlanResult(plan=None, validation=result)

        available = [enterprise_network]
        for network in explicit.values():
            available = self._exclude(available, network)
        site_blocks = dict(explicit)
        automatic = [site for site in enterprise_plan.sites if site.site_id not in site_blocks and requirements[site.site_id]]
        for site in sorted(automatic, key=lambda item: (self._site_prefix(requirements[item.site_id]), item.site_id)):
            prefix = self._site_prefix(requirements[site.site_id])
            block, available = self._take_subnet(available, prefix)
            if block is None:
                return self._error(
                    result, ErrorCode.ENTERPRISE_NO_USABLE_SUBNET,
                    f"No hay bloque IPv4 disponible para la sede {site.name!r}.", site.name,
                )
            site_blocks[site.site_id] = block

        allocations: list[SubnetAllocation] = []
        blocks: list[SiteAddressBlock] = []
        for site in sorted(enterprise_plan.sites, key=lambda item: item.site_id):
            block = site_blocks.get(site.site_id)
            if block is None:
                continue
            blocks.append(SiteAddressBlock(
                site_id=site.site_id,
                network=str(block.network_address),
                prefix=block.prefixlen,
                explicit=site.address_block is not None,
            ))
            site_allocations, error = self._allocate_site(site, block, requirements[site.site_id])
            if error is not None:
                result.errors.append(error)
                continue
            allocations.extend(site_allocations)
        if not result.is_valid:
            return IPAMPlanResult(plan=None, validation=result)
        return IPAMPlanResult(
            plan=AddressingPlan(
                address_space=AddressSpace(network=str(enterprise_network)),
                site_blocks=blocks,
                allocations=allocations,
            ),
            validation=result,
        )

    def _site_requirements(self, site: SitePlan) -> list[SubnetRequirement]:
        requirements: list[SubnetRequirement] = []
        for segment in site.segments:
            growth = segment.growth_percent if segment.growth_percent is not None else site.growth_percent
            requirements.append(subnet_requirement_for(
                segment.name, segment.host_requirement, growth, self.minimum_lan_prefix
            ))
        return sorted(requirements, key=lambda item: (item.prefix, item.segment_id))

    @staticmethod
    def _site_prefix(requirements: list[SubnetRequirement]) -> int:
        footprint = sum(1 << (32 - requirement.prefix) for requirement in requirements)
        if footprint <= 1:
            return 32
        return 32 - (footprint - 1).bit_length()

    def _explicit_site_blocks(
        self,
        sites: list[SitePlan],
        enterprise: ipaddress.IPv4Network,
        requirements: dict[str, list[SubnetRequirement]],
    ) -> tuple[dict[str, ipaddress.IPv4Network], list[PlanError]]:
        blocks: dict[str, ipaddress.IPv4Network] = {}
        errors: list[PlanError] = []
        for site in sorted(sites, key=lambda item: item.site_id):
            if site.address_block is None:
                continue
            try:
                block = ipaddress.ip_network(site.address_block, strict=True)
            except ValueError:
                errors.append(PlanError(ErrorCode.ENTERPRISE_ADDRESS_SPACE_INVALID,
                                        f"El bloque de {site.name!r} no es una red IPv4 CIDR válida.", site.name))
                continue
            if not isinstance(block, ipaddress.IPv4Network) or not block.subnet_of(enterprise):
                errors.append(PlanError(ErrorCode.SITE_ADDRESS_SPACE_OUTSIDE_ENTERPRISE,
                                        f"El bloque de {site.name!r} debe pertenecer al espacio Enterprise.", site.name))
                continue
            footprint = sum(1 << (32 - requirement.prefix) for requirement in requirements[site.site_id])
            if block.num_addresses < footprint:
                errors.append(PlanError(ErrorCode.SITE_ADDRESS_SPACE_TOO_SMALL,
                                        f"El bloque de {site.name!r} no contiene el footprint VLSM requerido.", site.name))
                continue
            for other_id, other_block in blocks.items():
                if block.overlaps(other_block):
                    errors.append(PlanError(ErrorCode.SITE_ADDRESS_SPACE_OVERLAP,
                                            f"El bloque de {site.name!r} se solapa con {other_id!r}.", site.name))
                    break
            else:
                blocks[site.site_id] = block
        return blocks, errors

    def _allocate_site(
        self,
        site: SitePlan,
        block: ipaddress.IPv4Network,
        requirements: list[SubnetRequirement],
    ) -> tuple[list[SubnetAllocation], PlanError | None]:
        available = [block]
        allocations: list[SubnetAllocation] = []
        for requirement in requirements:
            subnet, available = self._take_subnet(available, requirement.prefix)
            if subnet is None:
                return [], PlanError(
                    ErrorCode.SEGMENT_ADDRESS_SPACE_TOO_SMALL,
                    f"El bloque de {site.name!r} no alcanza para {requirement.segment_id!r}.",
                    site.name,
                )
            allocations.append(self._allocation(subnet, requirement))
        return allocations, None

    @staticmethod
    def _allocation(network: ipaddress.IPv4Network, requirement: SubnetRequirement) -> SubnetAllocation:
        return SubnetAllocation(
            segment_id=requirement.segment_id,
            network=str(network.network_address),
            prefix=network.prefixlen,
            netmask=str(network.netmask),
            gateway=str(network[1]),
            first_usable=str(network[1]),
            last_usable=str(network[-2]),
            broadcast=str(network.broadcast_address),
            usable_hosts=usable_hosts(network.prefixlen),
            required_hosts=requirement.required_usable_hosts,
            growth_percent=requirement.growth_percent,
            reserved_hosts=requirement.reserved_hosts,
        )

    @staticmethod
    def _exclude(
        available: list[ipaddress.IPv4Network],
        reserved: ipaddress.IPv4Network,
    ) -> list[ipaddress.IPv4Network]:
        remainder: list[ipaddress.IPv4Network] = []
        for candidate in available:
            if reserved.subnet_of(candidate):
                if candidate != reserved:
                    remainder.extend(candidate.address_exclude(reserved))
            else:
                remainder.append(candidate)
        return sorted(remainder, key=lambda item: (int(item.network_address), item.prefixlen))

    def _take_subnet(
        self,
        available: list[ipaddress.IPv4Network],
        prefix: int,
    ) -> tuple[ipaddress.IPv4Network | None, list[ipaddress.IPv4Network]]:
        for candidate in available:
            if candidate.prefixlen <= prefix:
                subnet = next(candidate.subnets(new_prefix=prefix))
                return subnet, self._exclude(available, subnet)
        return None, available

    @staticmethod
    def _error(
        result: ValidationResult,
        code: ErrorCode,
        message: str,
        site: str = "",
    ) -> IPAMPlanResult:
        result.errors.append(PlanError(code=code, message=message, device=site))
        return IPAMPlanResult(plan=None, validation=result)
