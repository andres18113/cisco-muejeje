"""The maintained A1-E6 DHCP/HTTP product entry exercised on an owned fixture.

The phases are the subject binding (the composed contract must be this stage's
exact fixture and the stock native pool), the terminal inventory registered
before the first effect, the admitted baseline, the product application
through the registered entry or the private candidate path, and the pure
acceptance assessment of what the product reported.
"""

from __future__ import annotations

from ....domain.enterprise.models.configuration_runtime import ActionExecutionStatus
from ....domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceRunStatus,
    ServiceStage,
    ServiceStageResult,
)
from ....domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    ServiceVerificationKind,
)
from ....domain.enterprise.models.service_qualification import (
    Q3_OBSERVED_NATIVE_DEFAULT_POOL,
    MeasurementConclusion,
)
from ....domain.enterprise.services.dhcp_lease_evidence import (
    ClientReading,
    client_readings,
    is_dotted_mac,
    scans_by_pool,
    unobserved_scans,
)
from ....domain.enterprise.services.service_qualification_evidence import (
    Assessment,
    DefaultPoolSnapshot,
    default_pool_snapshot,
    native_policy_probe_baseline_admitted,
    native_policy_terminal_inventory_complete,
)
from ..contracts import Q3ProductContract
from ..execution import Execution
from ..fixtures import diagnostic_start
from ..product_support import (
    FreshPublicBinding,
    apply_private_product,
    product_stage_runtimes,
)

_SERVER = "Q3-DEFAULT-SERVER-01"
_PC1 = "Q3-DEFAULT-PC-01"
_PC2 = "Q3-DEFAULT-PC-02"


def run_q3_native_product(execution: Execution) -> None:
    """Exercise the maintained A1-E6 DHCP/HTTP entry on an owned fixture."""
    subject = _native_product_subject(execution)
    if subject is None:
        return
    contract, pool = subject
    execution.register_terminal(
        ("M-NATIVE-PRODUCT-FINAL",),
        "Q3_NATIVE_PRODUCT_FINAL",
        lambda: _native_product_final(execution, pool),
    )
    if not diagnostic_start(execution):
        return
    ids = ("M-NATIVE-PRODUCT",)
    if not execution.selected("NATIVE-product") or not execution.begin(
        ids, "Q3_NATIVE_PRODUCT"
    ):
        return
    with execution.procedure(ids):
        baseline, prior_clients = _native_product_baseline(execution, pool)
        if not native_policy_probe_baseline_admitted(
            baseline,
            server=_SERVER,
            interface="FastEthernet0",
            expected_row=Q3_OBSERVED_NATIVE_DEFAULT_POOL,
            expected_exclusions=(),
        ) or any(
            not item.observed
            or item.mode is not False
            or item.ipv4 not in {"", "0.0.0.0"}
            or item.netmask not in {"", "0.0.0.0"}
            or not is_dotted_mac(item.mac)
            for item in prior_clients.values()
        ):
            execution.conclude(
                "M-NATIVE-PRODUCT",
                Assessment(
                    MeasurementConclusion.INCONCLUSIVE,
                    facts={
                        "baseline": dict(baseline.raw),
                        "clients": {
                            name: item.__dict__ for name, item in prior_clients.items()
                        },
                    },
                    causes=["native_product_baseline_not_admitted"],
                ),
            )
            execution.stop("native_product_baseline_not_admitted")
            return
        if not execution.run.transition("experiment:Q3_NATIVE_PRODUCT:started"):
            execution.stop("persistence:native_product_not_announced")
            return
        product, fresh_public_build = _apply_native_product(execution, contract)
        assessment = _native_product_assessment(
            execution,
            contract,
            pool,
            product,
            fresh_public_build,
            baseline,
            prior_clients,
        )
        execution.conclude("M-NATIVE-PRODUCT", assessment)
    execution.finish("Q3_NATIVE_PRODUCT")
    if assessment.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.stop("native_product_not_verified")


def _native_product_subject(
    execution: Execution,
) -> tuple[Q3ProductContract, ConfigureServerDhcpPool] | None:
    """Bind the composed contract to this fixture and the stock native pool.

    Stops the run and returns None when the contract is incomplete, names
    another topology, or asks for anything but one unnamed `serverPool` of one
    or two users on the fixture's server.
    """
    contract = execution.product_contract
    pool_actions = (
        [
            item
            for item in contract.service_plan.actions
            if isinstance(item, ConfigureServerDhcpPool)
        ]
        if contract is not None
        else []
    )
    if contract is None or len(pool_actions) != 1 or not contract.intent_json:
        execution.stop("native_product_contract_incomplete")
        return None
    pool = pool_actions[0]
    expected_fixtures = {
        (item.name, item.model) for item in execution.definition.fixtures
    }
    expected_links = {
        (item.device_a, item.port_a, item.device_b, item.port_b)
        for item in execution.definition.links
    }
    if (
        {(item.name, item.model) for item in contract.topology.devices}
        != expected_fixtures
        or {
            (item.device_a, item.port_a, item.device_b, item.port_b)
            for item in contract.topology.links
        }
        != expected_links
        or pool.effective_pool_name != "serverPool"
        or pool.pool_name_explicit
        or pool.host_device_name != _SERVER
        or not 1 <= pool.max_users <= 2
    ):
        execution.stop("native_product_manifest_or_pool_binding_mismatch")
        return None
    return contract, pool


def _native_product_final(execution: Execution, pool: ConfigureServerDhcpPool) -> None:
    """Take the terminal policy, client and lease inventory before cleanup."""
    ids = ("M-NATIVE-PRODUCT-FINAL",)
    if not execution.begin_terminal(ids, "Q3_NATIVE_PRODUCT_FINAL"):
        return
    with execution.procedure(ids):
        with execution.ledger.purpose_of("native-product:final:policy"):
            policy_read = execution.probes.read_dhcp_server_policy(
                _SERVER, "FastEthernet0"
            )
        snapshot = default_pool_snapshot(
            "native_product_final",
            policy_read,
            intended_pool=pool.pool_name,
            server=_SERVER,
            interface="FastEthernet0",
        )
        with execution.ledger.purpose_of("native-product:final:clients"):
            client_read = execution.probes.read_dhcp_clients(
                ((_PC1, "FastEthernet0"), (_PC2, "FastEthernet0"))
            )
        clients = client_readings(
            client_read.payload if client_read.observed else {}, (_PC1, _PC2)
        )
        with execution.ledger.purpose_of("native-product:final:leases"):
            lease_read = execution.probes.read_dhcp_lease_calibration(
                _SERVER,
                "FastEthernet0",
                (("serverPool", 4), (pool.pool_name, 2)),
            )
        lease_payload = lease_read.payload if lease_read.observed else {}
        scans = (
            scans_by_pool(lease_payload, ("serverPool", pool.pool_name))
            if lease_read.observed
            else unobserved_scans(("serverPool", pool.pool_name), lease_read.cause)
        )
        complete = (
            native_policy_terminal_inventory_complete(
                snapshot, server=_SERVER, interface="FastEthernet0"
            )
            and all(item.observed for item in clients.values())
            and all(item.observed for item in scans.values())
        )
        execution.conclude(
            "M-NATIVE-PRODUCT-FINAL",
            Assessment(
                MeasurementConclusion.SUPPORTED_IN_SAMPLE
                if complete
                else MeasurementConclusion.INCONCLUSIVE,
                facts={
                    "policy": dict(snapshot.raw),
                    "clients": {name: item.__dict__ for name, item in clients.items()},
                    "scans": {name: item.as_facts() for name, item in scans.items()},
                    "complete": complete,
                },
                causes=[]
                if complete
                else ["native_product_final_inventory_incomplete"],
                limitations=["terminal_inventory_is_not_product_acceptance"],
            ),
        )
    execution.finish("Q3_NATIVE_PRODUCT_FINAL")


def _native_product_baseline(
    execution: Execution, pool: ConfigureServerDhcpPool
) -> tuple[DefaultPoolSnapshot, dict[str, ClientReading]]:
    """Read the server's native policy and both clients before the product."""
    with execution.ledger.purpose_of("native-product:before:policy"):
        baseline_read = execution.probes.read_dhcp_server_policy(
            _SERVER, "FastEthernet0"
        )
    baseline = default_pool_snapshot(
        "native_product_before",
        baseline_read,
        intended_pool=pool.pool_name,
        server=_SERVER,
        interface="FastEthernet0",
    )
    with execution.ledger.purpose_of("native-product:before:clients"):
        prior_read = execution.probes.read_dhcp_clients(
            ((_PC1, "FastEthernet0"), (_PC2, "FastEthernet0"))
        )
    prior_clients = client_readings(
        prior_read.payload if prior_read.observed else {}, (_PC1, _PC2)
    )
    return baseline, prior_clients


def _apply_native_product(
    execution: Execution, contract: Q3ProductContract
) -> tuple[ServiceStageResult, str]:
    """Apply the intent through the registered entry, or the private candidate.

    Returns the product result and the build the registered entry read afresh
    when it bound, which is empty on the private candidate path.
    """
    boundaries = execution.run.boundaries
    product_runtimes = product_stage_runtimes(execution, contract, routed=False)
    with execution.ledger.effect_of("native-product:apply-enterprise-services"):
        if boundaries.native_public_product_entry is not None:
            binding = FreshPublicBinding(
                execution,
                contract,
                product_runtimes,
                mismatch="native_public_build_unobserved_or_mismatched",
            )
            product = boundaries.native_public_product_entry(
                execution.bound,
                binding,
                contract.manifest,
                contract.intent_json,
                execution.record.environment.observed_build,
                "SERVER-PT-DHCP-AUTONOMOUS-02 public native product",
            )
            return product, binding.fresh_build
        product = apply_private_product(
            execution,
            contract,
            product_runtimes,
            run_label="SERVER-PT-DHCP-AUTONOMOUS-02 native product",
        )
        return product, ""


def _native_product_assessment(
    execution: Execution,
    contract: Q3ProductContract,
    pool: ConfigureServerDhcpPool,
    product: ServiceStageResult,
    fresh_public_build: str,
    baseline: DefaultPoolSnapshot,
    prior_clients: dict[str, ClientReading],
) -> Assessment:
    """Accept the product only when it verified every lease and fetch it planned."""
    public = execution.run.boundaries.native_public_product_entry is not None
    by_id = (
        {
            item.expectation_id: item
            for item in product.service_result.verification_results
        }
        if product.service_result is not None
        else {}
    )
    lease_ids = [
        item.id
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    ]
    fetch_ids = [
        item.id
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.HTTP_FETCH
    ]
    accepted = (
        product.refusal_code is ServiceEntryRefusal.NONE
        and product.status is ServiceRunStatus.VERIFIED
        and product.stage is ServiceStage.COMPLETED
        and product.persisted_stage is ServiceStage.COMPLETED
        and bool(product.record_path)
        and not product.persist_error
        and (
            not public
            or fresh_public_build == execution.record.environment.observed_build
        )
        and len(lease_ids) == len(fetch_ids) == pool.max_users
        and all(
            by_id.get(identifier) is not None
            and by_id[identifier].status is ActionExecutionStatus.VERIFIED
            for identifier in (*lease_ids, *fetch_ids)
        )
    )
    return Assessment(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if accepted
        else MeasurementConclusion.INCONCLUSIVE,
        facts={
            "product_summary": product.compact_summary(),
            "product_record_path": product.record_path,
            "entry_surface": "registered_four_input" if public else "private_candidate",
            "fresh_public_build": fresh_public_build,
            "lease_expectation_ids": lease_ids,
            "http_fetch_expectation_ids": fetch_ids,
            "baseline": dict(baseline.raw),
            "prior_clients": {
                name: item.__dict__ for name, item in prior_clients.items()
            },
        },
        causes=[]
        if accepted
        else [f"native_product_not_verified:{product.refusal_code.value}"],
        limitations=(
            []
            if public
            else ["private_candidate_capabilities_not_global_product_promotion"]
        ),
    )
