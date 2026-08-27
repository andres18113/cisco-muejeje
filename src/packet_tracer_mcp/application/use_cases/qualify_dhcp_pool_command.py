"""Bounded developer qualification for one DHCP-pool IOS candidate.

This is intentionally not a product observer.  It creates one owned disposable
2811, applies one existing typed ``ConfigureDhcpPool`` action, and asks the
closed ``SHOW_IP_DHCP_POOL`` qualification candidate exactly once.  No caller
can supply IOS text, and no result is parsed into product truth here.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from ...domain.enterprise.models.configuration import (
    AddressRange,
    ConfigurationPhase,
    ConfigureDhcpPool,
)
from ...domain.enterprise.models.configuration_runtime import RuntimeActionMutation
from ...domain.enterprise.models.physical_deployment import (
    PhysicalMutationResult,
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.models.plans import DevicePlan
from ...infrastructure.execution.ios_terminal import (
    DeviceIdentityProvenance,
    IosCommandResult,
    IosQualificationQueryId,
    ios_rejection_reason,
)


QUALIFICATION_PREFIX = "MCP-DHCPPOOLQ-"
QUALIFICATION_POOL_NAME = "MCP_DHCP_POOL_Q"
_NETWORK = "198.18.250.0"
_PREFIX = 29
_MASK = "255.255.255.248"
_GATEWAY = "198.18.250.1"
_LEASE_START = "198.18.250.2"
_LEASE_END = "198.18.250.6"


class DhcpPoolCommandSupport(str, Enum):
    YES = "YES"
    NO = "NO"
    UNOBSERVABLE = "UNOBSERVABLE"


class DhcpPoolPhysicalRuntime(Protocol):
    def observe_workspace(self) -> PhysicalWorkspaceObservation: ...
    def ensure_device(self, device: DevicePlan) -> PhysicalMutationResult: ...
    def remove_device(self, device: DevicePlan) -> PhysicalMutationResult: ...


class DhcpPoolConfigurationRuntime(Protocol):
    def apply_actions(
        self, actions: list[ConfigureDhcpPool],
    ) -> list[RuntimeActionMutation]: ...


class DhcpPoolCandidateQueryRuntime(Protocol):
    def qualify(
        self,
        device_name: str,
        query_id: IosQualificationQueryId,
    ) -> IosCommandResult: ...


class DhcpPoolModeRuntime(Protocol):
    def read_simulation_state(self): ...


@dataclass(frozen=True)
class DhcpPoolCommandQualificationResult:
    model: str
    device_name: str = ""
    command_support: DhcpPoolCommandSupport = (
        DhcpPoolCommandSupport.UNOBSERVABLE
    )
    configuration_applied: bool = False
    observation: IosCommandResult | None = None
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    workspace_restored: bool = False
    realtime_before: bool = False
    realtime_after: bool = False
    realtime_restored: bool = False
    removed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


def classify_dhcp_pool_command_support(
    observation: IosCommandResult,
) -> DhcpPoolCommandSupport:
    """Classify command support only from a usable attributed capture."""
    if observation.query_id is not IosQualificationQueryId.SHOW_IP_DHCP_POOL:
        return DhcpPoolCommandSupport.UNOBSERVABLE
    if not (
        observation.executed
        and observation.fresh_output_observed
        and observation.output_complete
        and observation.device_identity_provenance
        == DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
    ):
        return DhcpPoolCommandSupport.UNOBSERVABLE
    if ios_rejection_reason(observation.output) is not None:
        return DhcpPoolCommandSupport.NO
    return DhcpPoolCommandSupport.YES


class DhcpPoolCommandQualifier:
    """Measure one exact candidate against a known pool on an owned router."""

    def __init__(
        self,
        physical: DhcpPoolPhysicalRuntime,
        configuration: DhcpPoolConfigurationRuntime,
        query: DhcpPoolCandidateQueryRuntime,
        mode: DhcpPoolModeRuntime,
        *,
        name_token: str = "",
    ) -> None:
        self._physical = physical
        self._configuration = configuration
        self._query = query
        self._mode = mode
        self._token = name_token or secrets.token_hex(3)

    def qualify(
        self,
        model: str,
        *,
        require_empty_workspace: bool = True,
    ) -> DhcpPoolCommandQualificationResult:
        try:
            baseline = self._physical.observe_workspace()
        except Exception as exc:  # noqa: BLE001 - evidence, not a crash
            return DhcpPoolCommandQualificationResult(
                model=model,
                errors=(f"baseline_inventory_failed: {type(exc).__name__}: {exc}",),
            )
        if require_empty_workspace and not baseline.safe_for_disposable_mutation:
            return DhcpPoolCommandQualificationResult(
                model=model,
                baseline_inventory=baseline,
                errors=(
                    "The workspace is not an observed empty semantic workspace; "
                    "qualification refused every mutation.",
                ),
            )

        realtime_before = self._read_realtime()
        if not realtime_before:
            return DhcpPoolCommandQualificationResult(
                model=model,
                baseline_inventory=baseline,
                errors=(
                    "Realtime mode was not freshly observed before mutation; "
                    "qualification refused every mutation.",
                ),
            )

        device = DevicePlan(
            id="dhcp-pool-qualification/router",
            name=f"{QUALIFICATION_PREFIX}{self._token}",
            model=model,
            category="router",
            x=9600,
            y=9600,
        )
        attempted: list[DevicePlan] = []
        observation: IosCommandResult | None = None
        support = DhcpPoolCommandSupport.UNOBSERVABLE
        configuration_applied = False
        errors: list[str] = []
        try:
            attempted.append(device)
            creation = self._physical.ensure_device(device)
            if not creation.applied:
                errors.append("disposable_router_creation_not_applied")
            else:
                mutations = self._configuration.apply_actions([
                    self._pool_action(device),
                ])
                configuration_applied = bool(
                    mutations and all(item.applied for item in mutations)
                )
                if not configuration_applied:
                    errors.append("typed_dhcp_pool_configuration_not_applied")
                else:
                    observation = self._query.qualify(
                        device.name,
                        IosQualificationQueryId.SHOW_IP_DHCP_POOL,
                    )
                    support = classify_dhcp_pool_command_support(observation)
        except Exception as exc:  # noqa: BLE001 - cleanup remains authoritative
            errors.append(f"qualification_raised: {type(exc).__name__}: {exc}")
        finally:
            removed, cleanup_errors = self._cleanup(attempted)
            errors.extend(cleanup_errors)
            final, restored, final_errors = self._final_inventory(baseline)
            errors.extend(final_errors)
            realtime_after = self._read_realtime()

        return DhcpPoolCommandQualificationResult(
            model=model,
            device_name=device.name,
            command_support=support,
            configuration_applied=configuration_applied,
            observation=observation,
            baseline_inventory=baseline,
            final_inventory=final,
            workspace_restored=restored,
            realtime_before=realtime_before,
            realtime_after=realtime_after,
            realtime_restored=realtime_before and realtime_after,
            removed=tuple(removed),
            errors=tuple(errors),
        )

    @staticmethod
    def _pool_action(device: DevicePlan) -> ConfigureDhcpPool:
        return ConfigureDhcpPool(
            id="dhcp-pool-qualification/pool",
            phase=ConfigurationPhase.SERVICES,
            device_id=device.id,
            device_name=device.name,
            site_id="dhcp-pool-qualification",
            pool_name=QUALIFICATION_POOL_NAME,
            segment_id="dhcp-pool-qualification/segment",
            network=_NETWORK,
            prefix=_PREFIX,
            netmask=_MASK,
            gateway=_GATEWAY,
            excluded_ranges=[AddressRange(start=_GATEWAY, end=_GATEWAY)],
            lease_start=_LEASE_START,
            lease_end=_LEASE_END,
        )

    def _cleanup(
        self, attempted: list[DevicePlan],
    ) -> tuple[list[str], list[str]]:
        removed: list[str] = []
        errors: list[str] = []
        for device in reversed(attempted):
            try:
                result = self._physical.remove_device(device)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"cleanup_failed: {device.name}: {type(exc).__name__}: {exc}"
                )
                continue
            if result.applied:
                removed.append(device.name)
            else:
                errors.append(f"cleanup_not_applied: {device.name}")
        return removed, errors

    def _final_inventory(
        self, baseline: PhysicalWorkspaceObservation,
    ) -> tuple[PhysicalWorkspaceObservation | None, bool, list[str]]:
        try:
            final = self._physical.observe_workspace()
        except Exception as exc:  # noqa: BLE001
            return None, False, [
                f"final_inventory_failed: {type(exc).__name__}: {exc}"
            ]
        return final, physical_workspace_restoration_matches(baseline, final), []

    def _read_realtime(self) -> bool:
        try:
            state = self._mode.read_simulation_state()
        except Exception:  # noqa: BLE001 - false is the fail-closed answer
            return False
        return bool(
            getattr(state, "observed", False)
            and not getattr(state, "simulation_mode", True)
        )
