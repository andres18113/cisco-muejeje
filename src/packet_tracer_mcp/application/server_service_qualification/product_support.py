"""Product integration shared by several qualification workflow families.

Exact-inventory runtime adapters, E5/E6 projections of a product contract,
the runtime context, the foundations a projection established, the rows an
application reported and the bounds of a terminal router capture.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ...domain.enterprise.models.configuration import (
    ConfigurationPlan,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationRuntimeContext,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    EnableServerDhcp,
    ServicePlan,
    ServiceVerificationKind,
)
from ...domain.enterprise.models.service_runtime import RuntimeServiceVerification
from ...domain.enterprise.services.configuration_compiler import (
    configuration_plan_semantic_hash,
)
from ..use_cases.apply_configuration import ConfigurationRuntime
from ..use_cases.apply_services import ServiceRuntime
from ..use_cases.foundational_evidence import derive_service_foundational_statuses
from ..use_cases.service_access_readiness_gate import ReadinessNotRequired
from .contracts import Q3ProductContract
from .execution import Execution

#: The ledger purpose prefix every native default reading is dispatched under.
#: Why the qualification stages run no product readiness gate. They take their
#: own exact-port/VLAN forwarding evidence, keep it in their immutable records
#: with its own admission dimensions, and are budgeted for precisely the
#: operations their profile declares. Adding the product gate inside them would
#: spend unbudgeted operations and publish a second forwarding claim with a
#: different scope beside the measured one.
DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE = ReadinessNotRequired(
    "diagnostic qualification measures access forwarding explicitly, records it "
    "as stage evidence, and is budgeted for its own declared operations"
)


@dataclass
class ExactInventoryConfigurationRuntime:
    """Give the product E5 runtime the exact manifest-directed Q3 inventory."""

    inner: ConfigurationRuntime
    inventory_rows: tuple[RuntimeConfigurationTarget, ...]

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        """Return a fresh copy of the exact inventory rows."""
        return [item.model_copy(deep=True) for item in self.inventory_rows]

    def apply_actions(self, actions) -> list[RuntimeActionMutation]:
        """Apply through the inner product runtime."""
        return self.inner.apply_actions(actions)

    def verify(self, expectations):
        """Verify through the inner product runtime."""
        return self.inner.verify(expectations)

    def wait_for_voice_access_forwarding(self, expectations):
        """Wait for voice access forwarding through the inner runtime."""
        return self.inner.wait_for_voice_access_forwarding(expectations)

    def observe_access_forwarding(self, *args, **kwargs):
        """Observe access forwarding through the inner runtime."""
        return self.inner.observe_access_forwarding(*args, **kwargs)


@dataclass
class ExactInventoryServiceRuntime:
    """Give the product E6 runtime the same exact Q3 inventory."""

    inner: ServiceRuntime
    inventory_rows: tuple[RuntimeConfigurationTarget, ...]

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        """Return a fresh copy of the exact inventory rows."""
        return [item.model_copy(deep=True) for item in self.inventory_rows]

    def apply_actions(self, actions) -> list[RuntimeActionMutation]:
        """Apply through the inner product runtime."""
        return self.inner.apply_actions(actions)

    def verify(self, expectation) -> RuntimeServiceVerification:
        """Verify through the inner product runtime."""
        return self.inner.verify(expectation)


def q3_endpoint_plan(contract: Q3ProductContract) -> ConfigurationPlan:
    """Project the real E5 plan to endpoint bootstrap on the prebuilt fixture.

    Q3 creates and verifies the exact physical links itself. Switch VLAN/port
    configuration is not a DHCP native claim, so this projection removes only
    those already-owned fixture dependencies; the endpoint action and reader
    identities remain the ones the real compiler produced.
    """
    action_types = (SetEndpointStaticAddress, SetEndpointDhcp)
    actions = [
        item.model_copy(update={"depends_on": [], "apply_dependencies": []})
        for item in contract.configuration_plan.actions
        if isinstance(item, action_types)
    ]
    action_ids = {item.id for item in actions}
    device_ids = {item.device_id for item in actions}
    plan = ConfigurationPlan(
        id=contract.configuration_plan.id + "/q3-endpoints",
        source_topology_id=contract.configuration_plan.source_topology_id,
        source_topology_hash=contract.configuration_plan.source_topology_hash,
        source_topology_hash_schema=(
            contract.configuration_plan.source_topology_hash_schema
        ),
        actions=actions,
        devices=[
            item.model_copy(deep=True)
            for item in contract.configuration_plan.devices
            if item.device_id in device_ids
        ],
        verification_expectations=[
            item.model_copy(deep=True)
            for item in contract.configuration_plan.verification_expectations
            if item.action_id in action_ids
        ],
    )
    plan.semantic_hash = configuration_plan_semantic_hash(plan)
    return plan


def q3_server_plan(plan: ServicePlan) -> ServicePlan:
    """Project exact server setup rows without changing source-plan identity."""
    actions = [
        item
        for item in plan.actions
        if isinstance(item, EnableServerDhcp | ConfigureServerDhcpPool)
    ]
    action_ids = {item.id for item in actions}
    expectations = [
        item
        for item in plan.verification_expectations
        if item.action_id in action_ids
        and item.kind is ServiceVerificationKind.DHCP_SERVER_STATE
    ]
    expectation_ids = {item.id for item in expectations}
    service_ids = {item.service_id for item in actions}
    services = [
        item.model_copy(
            update={
                "action_ids": [
                    identifier
                    for identifier in item.action_ids
                    if identifier in action_ids
                ],
                "verification_expectation_ids": [
                    identifier
                    for identifier in item.verification_expectation_ids
                    if identifier in expectation_ids
                ],
            },
            deep=True,
        )
        for item in plan.services
        if item.id in service_ids
    ]
    return plan.model_copy(
        update={
            "services": services,
            "actions": actions,
            "verification_expectations": expectations,
        },
        deep=True,
    )


def product_runtime_context(contract: Q3ProductContract) -> ConfigurationRuntimeContext:
    """Return the runtime context the contract's manifest names."""
    return ConfigurationRuntimeContext(
        backend=contract.manifest.backend,
        backend_version=contract.manifest.backend_version,
        environment_fingerprint=contract.manifest.environment_fingerprint,
    )


def exact_inventory_runtimes(execution: Execution, contract: Q3ProductContract):
    """Bind the product E5/E6 runtimes to the exact manifest-directed fixture."""
    boundaries = execution.run.boundaries
    return (
        ExactInventoryConfigurationRuntime(
            boundaries.configuration_runtime(execution.bound), contract.inventory
        ),
        ExactInventoryServiceRuntime(
            boundaries.service_runtime(execution.bound), contract.inventory
        ),
    )


#: Terminal router capture bounds: one call budget per registered read and
#: one window for the whole capture, taken from the stage's own allowance.
#: LIVE at 710faca two `show ip interface brief` captures spent six calls
#: without converging; the readiness readings they mirror get twelve.
SP1_CAPTURE_SAMPLE_CALLS = 12
SP1_CAPTURE_DEADLINE_SECONDS = 120.0


@dataclass
class RoutedInventoryConfigurationRuntime(ExactInventoryConfigurationRuntime):
    """The exact-inventory E5 runtime plus the routed and continuity observers.

    The routed and continuity readiness groups find their observers on the
    runtime the product is given; without them every routed dependent would
    be refused, so SP-1 forwards both to the inner product runtime.
    """

    def observe_trunk_continuity(self, *args, **kwargs):
        """Observe trunk continuity through the inner runtime."""
        return self.inner.observe_trunk_continuity(*args, **kwargs)

    def observe_routed_forwarding(self, *args, **kwargs):
        """Observe routed forwarding through the inner runtime."""
        return self.inner.observe_routed_forwarding(*args, **kwargs)


def capability_digest(values: Mapping[str, Any]) -> str:
    """Hash the exact capability rows supplied to this private invocation."""
    return hashlib.sha256(
        json.dumps(
            {key: item.model_dump(mode="json") for key, item in sorted(values.items())},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def projection_foundations(
    contract: Q3ProductContract,
    plan: ConfigurationPlan,
    result: ConfigurationApplicationResult,
) -> dict[str, ActionExecutionStatus]:
    """Derive the foundations one E5 projection established, by its identity."""
    rebound = contract.service_plan.model_copy(
        update={
            "source_configuration_id": plan.id,
            "source_configuration_hash": plan.semantic_hash,
        },
        deep=True,
    )
    return derive_service_foundational_statuses(rebound, result)


def application_rows(result: Any) -> dict[str, Any]:
    """Return one application result's rows exactly as the product reported them."""
    if result is None:
        return {}
    return {
        "status": getattr(getattr(result, "status", None), "value", ""),
        "preflight_errors": list(getattr(result, "preflight_errors", []) or []),
        "action_results": [
            item.model_dump(mode="json") for item in result.action_results
        ],
        "verification_results": [
            item.model_dump(mode="json") for item in result.verification_results
        ],
    }
