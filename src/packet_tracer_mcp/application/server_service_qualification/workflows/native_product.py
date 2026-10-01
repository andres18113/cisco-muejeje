"""The maintained A1-E6 DHCP/HTTP product entry exercised on an owned fixture."""

from __future__ import annotations

from ....domain.enterprise.models.configuration_runtime import ActionExecutionStatus
from ....domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceRunStatus,
    ServiceStage,
)
from ....domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    ServiceVerificationKind,
)
from ....domain.enterprise.models.service_qualification import (
    Q3_OBSERVED_NATIVE_DEFAULT_POOL,
    MeasurementConclusion,
)
from ....domain.enterprise.models.service_run_record import SourceTreeIdentity
from ....domain.enterprise.services.dhcp_lease_evidence import (
    client_readings,
    is_dotted_mac,
    scans_by_pool,
    unobserved_scans,
)
from ....domain.enterprise.services.service_qualification_evidence import (
    Assessment,
    default_pool_snapshot,
    native_policy_probe_baseline_admitted,
    native_policy_terminal_inventory_complete,
)
from ...use_cases.apply_enterprise_services import (
    ServiceInvocationBinding,
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from ..execution import Execution
from ..fixtures import diagnostic_start
from ..product_support import (
    ExactInventoryConfigurationRuntime,
    ExactInventoryServiceRuntime,
)


def run_q3_native_product(execution: Execution) -> None:
    """Exercise the maintained A1-E6 DHCP/HTTP entry on an owned fixture."""
    contract = execution.product_contract
    boundaries = execution.run.boundaries
    server = "Q3-DEFAULT-SERVER-01"
    pc1 = "Q3-DEFAULT-PC-01"
    pc2 = "Q3-DEFAULT-PC-02"
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
        return
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
        or pool.host_device_name != server
        or not 1 <= pool.max_users <= 2
    ):
        execution.stop("native_product_manifest_or_pool_binding_mismatch")
        return

    def terminal() -> None:
        ids = ("M-NATIVE-PRODUCT-FINAL",)
        if not execution.begin_terminal(ids, "Q3_NATIVE_PRODUCT_FINAL"):
            return
        with execution.procedure(ids):
            with execution.ledger.purpose_of("native-product:final:policy"):
                policy_read = execution.probes.read_dhcp_server_policy(
                    server, "FastEthernet0"
                )
            snapshot = default_pool_snapshot(
                "native_product_final",
                policy_read,
                intended_pool=pool.pool_name,
                server=server,
                interface="FastEthernet0",
            )
            with execution.ledger.purpose_of("native-product:final:clients"):
                client_read = execution.probes.read_dhcp_clients(
                    ((pc1, "FastEthernet0"), (pc2, "FastEthernet0"))
                )
            clients = client_readings(
                client_read.payload if client_read.observed else {}, (pc1, pc2)
            )
            with execution.ledger.purpose_of("native-product:final:leases"):
                lease_read = execution.probes.read_dhcp_lease_calibration(
                    server,
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
                    snapshot, server=server, interface="FastEthernet0"
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
                        "clients": {
                            name: item.__dict__ for name, item in clients.items()
                        },
                        "scans": {
                            name: item.as_facts() for name, item in scans.items()
                        },
                        "complete": complete,
                    },
                    causes=[]
                    if complete
                    else ["native_product_final_inventory_incomplete"],
                    limitations=["terminal_inventory_is_not_product_acceptance"],
                ),
            )
        execution.finish("Q3_NATIVE_PRODUCT_FINAL")

    execution.register_terminal(
        ("M-NATIVE-PRODUCT-FINAL",), "Q3_NATIVE_PRODUCT_FINAL", terminal
    )
    if not diagnostic_start(execution):
        return
    ids = ("M-NATIVE-PRODUCT",)
    if not execution.selected("NATIVE-product") or not execution.begin(
        ids, "Q3_NATIVE_PRODUCT"
    ):
        return
    with execution.procedure(ids):
        with execution.ledger.purpose_of("native-product:before:policy"):
            baseline_read = execution.probes.read_dhcp_server_policy(
                server, "FastEthernet0"
            )
        baseline = default_pool_snapshot(
            "native_product_before",
            baseline_read,
            intended_pool=pool.pool_name,
            server=server,
            interface="FastEthernet0",
        )
        with execution.ledger.purpose_of("native-product:before:clients"):
            prior_read = execution.probes.read_dhcp_clients(
                ((pc1, "FastEthernet0"), (pc2, "FastEthernet0"))
            )
        prior_clients = client_readings(
            prior_read.payload if prior_read.observed else {}, (pc1, pc2)
        )
        if not native_policy_probe_baseline_admitted(
            baseline,
            server=server,
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

        class ExactManifest:
            def latest_by_deployment_id(self, identifier: str):
                return (
                    contract.manifest
                    if identifier == contract.manifest.deployment_id
                    else None
                )

        inner = boundaries.native_product_runtimes(execution.bound, contract.inventory)
        product_runtimes = ServiceStageRuntimes(
            configuration=ExactInventoryConfigurationRuntime(
                inner.configuration, contract.inventory
            ),
            services=ExactInventoryServiceRuntime(inner.services, contract.inventory),
        )
        fresh_public_build = ""
        with execution.ledger.effect_of("native-product:apply-enterprise-services"):
            if boundaries.native_public_product_entry is not None:

                def public_binding() -> ServiceInvocationBinding:
                    nonlocal fresh_public_build
                    reading = boundaries.build_reader(
                        execution.bound.send_and_wait
                    ).read()
                    if (
                        not reading.available
                        or reading.version
                        != execution.record.environment.observed_build
                    ):
                        raise ValueError("native_public_build_unobserved_or_mismatched")
                    fresh_public_build = reading.version
                    return ServiceInvocationBinding(
                        runtimes=product_runtimes,
                        record_store=boundaries.native_product_record_store_factory(),
                        environment_fingerprint=(
                            contract.manifest.environment_fingerprint.model_copy(
                                update={"backend_version": reading.version}
                            )
                        ),
                        transport_selection=TransportSelection(
                            channel=execution.channel, fixed_at=boundaries.now()
                        ),
                        source_tree=SourceTreeIdentity(
                            sha=execution.record.source.executed_sha,
                            tree=execution.record.source.executed_tree,
                            dirty=execution.record.source.clean is not True,
                        ),
                        endpoint_observer=boundaries.native_product_endpoint_observer(
                            execution.bound
                        ),
                    )

                product = boundaries.native_public_product_entry(
                    execution.bound,
                    public_binding,
                    contract.manifest,
                    contract.intent_json,
                    execution.record.environment.observed_build,
                    "SERVER-PT-DHCP-AUTONOMOUS-02 public native product",
                )
            else:
                product = apply_enterprise_services(
                    contract.intent_json,
                    deployment_id=contract.manifest.deployment_id,
                    packet_tracer_version=execution.record.environment.observed_build,
                    import_preflight=boundaries.native_product_import_preflight(),
                    manifest_store=ExactManifest(),
                    runtimes=product_runtimes,
                    record_store=boundaries.native_product_record_store_factory(),
                    environment_fingerprint=contract.manifest.environment_fingerprint,
                    transport_selection=TransportSelection(
                        channel=execution.channel,
                        fixed_at=boundaries.now(),
                    ),
                    endpoint_observer=boundaries.native_product_endpoint_observer(
                        execution.bound
                    ),
                    capability_catalog=lambda build: (
                        contract.service_capabilities
                        if build == execution.record.environment.observed_build
                        else {}
                    ),
                    source_tree=SourceTreeIdentity(
                        sha=execution.record.source.executed_sha,
                        tree=execution.record.source.executed_tree,
                        dirty=execution.record.source.clean is not True,
                    ),
                    run_label="SERVER-PT-DHCP-AUTONOMOUS-02 native product",
                    run_id=execution.record.run_id + "-product",
                )
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
                boundaries.native_public_product_entry is None
                or fresh_public_build == execution.record.environment.observed_build
            )
            and len(lease_ids) == len(fetch_ids) == pool.max_users
            and all(
                by_id.get(identifier) is not None
                and by_id[identifier].status is ActionExecutionStatus.VERIFIED
                for identifier in (*lease_ids, *fetch_ids)
            )
        )
        execution.conclude(
            "M-NATIVE-PRODUCT",
            Assessment(
                MeasurementConclusion.SUPPORTED_IN_SAMPLE
                if accepted
                else MeasurementConclusion.INCONCLUSIVE,
                facts={
                    "product_summary": product.compact_summary(),
                    "product_record_path": product.record_path,
                    "entry_surface": (
                        "registered_four_input"
                        if boundaries.native_public_product_entry is not None
                        else "private_candidate"
                    ),
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
                    if boundaries.native_public_product_entry is not None
                    else ["private_candidate_capabilities_not_global_product_promotion"]
                ),
            ),
        )
    execution.finish("Q3_NATIVE_PRODUCT")
    if not accepted:
        execution.stop("native_product_not_verified")
