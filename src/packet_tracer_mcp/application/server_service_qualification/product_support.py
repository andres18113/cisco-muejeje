"""Product integration shared by several qualification workflow families.

Exact-inventory runtime adapters, E5/E6 projections of a product contract,
the runtime context, the foundations a projection established, the rows an
application reported, the product invocation the product workflows share
(the exact manifest store, the fresh public binding and the private
candidate path) and the bounded terminal router capture.
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
    decide_mutation,
)
from ...domain.enterprise.models.deployment import DeploymentManifest
from ...domain.enterprise.models.execution import DispatchFact, ResultFact
from ...domain.enterprise.models.service_entry import ServiceStageResult
from ...domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    EnableServerDhcp,
    ServicePlan,
    ServiceVerificationKind,
)
from ...domain.enterprise.models.service_run_record import SourceTreeIdentity
from ...domain.enterprise.models.service_runtime import (
    RuntimeServiceVerification,
    ServiceApplicationResult,
)
from ...domain.enterprise.services.configuration_compiler import (
    configuration_plan_semantic_hash,
)
from ..use_cases.apply_configuration import ConfigurationRuntime
from ..use_cases.apply_enterprise_services import (
    ServiceInvocationBinding,
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from ..use_cases.apply_services import ServiceRuntime
from ..use_cases.foundational_evidence import derive_service_foundational_statuses
from ..use_cases.service_access_readiness_gate import ReadinessNotRequired
from .contracts import Q3ProductContract, bounded
from .execution import Execution

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


class ExactManifestStore:
    """A manifest store that answers for exactly one deployment's manifest."""

    def __init__(self, manifest: DeploymentManifest) -> None:
        """Hold the one manifest this store answers for."""
        self._manifest = manifest

    def latest_by_deployment_id(self, identifier: str) -> DeploymentManifest | None:
        """Return the manifest when `identifier` is its deployment, else None."""
        return self._manifest if identifier == self._manifest.deployment_id else None


def product_stage_runtimes(
    execution: Execution, contract: Q3ProductContract, *, routed: bool
) -> ServiceStageRuntimes:
    """Bind the composed product runtimes to the contract's exact inventory.

    `routed` adds the trunk-continuity and routed-forwarding observers that
    the product's routed readiness groups find on its E5 runtime.
    """
    inner = execution.run.boundaries.native_product_runtimes(
        execution.bound, contract.inventory
    )
    configuration = (
        RoutedInventoryConfigurationRuntime
        if routed
        else ExactInventoryConfigurationRuntime
    )
    return ServiceStageRuntimes(
        configuration=configuration(inner.configuration, contract.inventory),
        services=ExactInventoryServiceRuntime(inner.services, contract.inventory),
    )


def acquisition_request_outcome(
    result: ServiceApplicationResult, action_id: str
) -> str:
    """Classify one acquisition's dispatch from its own canonical row.

    This is the Q3-FL decision predicate the brief records, shared with the
    SP-2 acquisition discriminator. The product keeps a void `dhcpRun`
    unsettled for product dependents until a read-back verifies it, and
    nothing here changes that. What a diagnostic needs is narrower: whether
    the claim script's single evaluation is known. A row
    that reproduces its canonical decision, was accepted and correlated,
    reported `attempted=true` and carried no call error is a known dispatch.
    `attempted=false` is a known non-dispatch with its skip reason. A
    preflight refusal dispatched nothing. Anything else is an unknown outcome,
    which stops every later effect and is never retried.
    """
    row = next(
        (item for item in result.action_results if item.action_id == action_id), None
    )
    if row is None:
        if result.preflight_errors and not result.action_results:
            return "not_dispatched:preflight:" + bounded(result.preflight_errors[0])
        return "outcome_unknown:acquisition_row_absent"
    snapshot = row.received_mutation
    if snapshot is None or snapshot.action_id != action_id:
        return "outcome_unknown:acquisition_snapshot_absent"
    decision = decide_mutation(snapshot)
    if not (
        row.status is decision.status
        and row.failure_code is decision.failure_code
        and row.disposition is decision.disposition
        and row.dispatch is snapshot.dispatch
        and row.result is snapshot.result
        and row.attempted is snapshot.attempted
        and row.cause == decision.cause
    ):
        return "outcome_unknown:acquisition_row_incoherent"
    if snapshot.attempted is False and not snapshot.call_error:
        return "not_dispatched:" + bounded(row.cause or snapshot.cause or "skipped")
    if (
        row.dispatch is not DispatchFact.ACCEPTED
        or row.result is not ResultFact.CORRELATED
        or snapshot.attempted is not True
        or bool(snapshot.call_error)
    ):
        return "outcome_unknown:acquisition_dispatch"
    return "dispatched"


def source_tree_identity(execution: Execution) -> SourceTreeIdentity:
    """Return the executed source identity a product record must name."""
    source = execution.record.source
    return SourceTreeIdentity(
        sha=source.executed_sha,
        tree=source.executed_tree,
        dirty=source.clean is not True,
    )


@dataclass
class FreshPublicBinding:
    """Bind the registered four-input product entry to a freshly read build.

    The entry calls it when it binds. It reads the executable build again
    through the counted transport and refuses a build that is not the one
    this qualification admitted; `fresh_build` keeps the build it read.
    """

    execution: Execution
    contract: Q3ProductContract
    runtimes: ServiceStageRuntimes
    #: The refusal raised when the fresh build is unobserved or different.
    mismatch: str
    #: Whether the contract's device capability catalog is bound as well.
    bind_device_catalog: bool = False
    fresh_build: str = ""

    def __call__(self) -> ServiceInvocationBinding:
        """Read the build again and return the binding for exactly that build."""
        execution = self.execution
        boundaries = execution.run.boundaries
        reading = boundaries.build_reader(execution.bound.send_and_wait).read()
        if (
            not reading.available
            or reading.version != execution.record.environment.observed_build
        ):
            raise ValueError(self.mismatch)
        self.fresh_build = reading.version
        catalog = (
            {"device_capability_catalog": self.contract.device_capability_catalog}
            if self.bind_device_catalog
            else {}
        )
        return ServiceInvocationBinding(
            runtimes=self.runtimes,
            record_store=boundaries.native_product_record_store_factory(),
            environment_fingerprint=(
                self.contract.manifest.environment_fingerprint.model_copy(
                    update={"backend_version": reading.version}
                )
            ),
            transport_selection=TransportSelection(
                channel=execution.channel, fixed_at=boundaries.now()
            ),
            source_tree=source_tree_identity(execution),
            endpoint_observer=boundaries.native_product_endpoint_observer(
                execution.bound
            ),
            **catalog,
        )


def apply_private_product(
    execution: Execution,
    contract: Q3ProductContract,
    runtimes: ServiceStageRuntimes,
    *,
    run_label: str,
    bind_device_catalog: bool = False,
) -> ServiceStageResult:
    """Run the private-candidate product path on this contract's exact inputs.

    The manifest store knows only this contract's deployment, the service
    capability catalog answers only for the observed build, and the product
    run is named after this qualification run.
    """
    boundaries = execution.run.boundaries
    observed_build = execution.record.environment.observed_build
    catalog = (
        {"device_capability_catalog": contract.device_capability_catalog}
        if bind_device_catalog
        else {}
    )
    return apply_enterprise_services(
        contract.intent_json,
        deployment_id=contract.manifest.deployment_id,
        packet_tracer_version=observed_build,
        import_preflight=boundaries.native_product_import_preflight(),
        manifest_store=ExactManifestStore(contract.manifest),
        runtimes=runtimes,
        record_store=boundaries.native_product_record_store_factory(),
        environment_fingerprint=contract.manifest.environment_fingerprint,
        transport_selection=TransportSelection(
            channel=execution.channel, fixed_at=boundaries.now()
        ),
        endpoint_observer=boundaries.native_product_endpoint_observer(execution.bound),
        capability_catalog=lambda build: (
            contract.service_capabilities if build == observed_build else {}
        ),
        source_tree=source_tree_identity(execution),
        run_label=run_label,
        run_id=execution.record.run_id + "-product",
        **catalog,
    )


def capture_terminal_routers(
    execution: Execution,
    contract: Q3ProductContract,
    routers: tuple[str, ...],
    purpose: str,
) -> tuple[list[Any], bool]:
    """Capture each router's terminal text through the composed product reader.

    Returns the rows and whether the reader offers a capture at all. Without
    one nothing is read and the rows are empty; the capture is bounded by the
    shared per-read call budget and one window for the whole capture.
    """
    reader = execution.run.boundaries.native_product_runtimes(
        execution.bound, contract.inventory
    ).configuration
    capture = getattr(reader, "capture_routed_text", None)
    with execution.ledger.purpose_of(purpose):
        rows = (
            list(
                capture(
                    routers,
                    sample_calls=SP1_CAPTURE_SAMPLE_CALLS,
                    deadline_seconds=SP1_CAPTURE_DEADLINE_SECONDS,
                )
            )
            if callable(capture)
            else []
        )
    return rows, callable(capture)
