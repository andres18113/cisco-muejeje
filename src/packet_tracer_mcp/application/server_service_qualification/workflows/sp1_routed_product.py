"""SP-1: routed DNS/HTTP through the registered four-input product route."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from ....domain.enterprise.models.configuration import SetEndpointStaticAddress
from ....domain.enterprise.models.configuration_runtime import ActionExecutionStatus
from ....domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceRunStatus,
    ServiceStage,
)
from ....domain.enterprise.models.service_plan import ServiceVerificationKind
from ....domain.enterprise.models.service_qualification import (
    SP1_DNS_SERVER,
    SP1_ROUTERS,
    SP1_WEB_SERVER,
    MeasurementConclusion,
    sp1_intent,
    sp1_run_parameters,
)
from ....domain.enterprise.models.service_run_record import SourceTreeIdentity
from ....domain.enterprise.services.qualification_terminal_evidence import (
    sp1_terminal_bindings_observed,
)
from ....domain.enterprise.services.service_qualification_evidence import Assessment
from ...use_cases.apply_enterprise_services import (
    ServiceInvocationBinding,
    ServiceStageRuntimes,
    TransportSelection,
)
from ..contracts import Q3ProductContract
from ..execution import Execution
from ..fixtures import diagnostic_start
from ..product_support import (
    SP1_CAPTURE_DEADLINE_SECONDS,
    SP1_CAPTURE_SAMPLE_CALLS,
    ExactInventoryServiceRuntime,
    RoutedInventoryConfigurationRuntime,
)

#: The client checks every selected SP-1 client must verify, in request order.
SP1_REQUIRED_CLIENT_KINDS = (
    ServiceVerificationKind.HTTP_FETCH,
    ServiceVerificationKind.DNS_RESOLUTION,
    ServiceVerificationKind.DNS_NEGATIVE_CONTROL,
    ServiceVerificationKind.HTTP_BY_HOSTNAME,
)
#: Advisory binding reads SP-1 measures without requiring them yet.
SP1_BINDING_KINDS = (
    ServiceVerificationKind.CLIENT_GATEWAY,
    ServiceVerificationKind.CLIENT_DNS_SERVER,
)


def _sp1_contract_mismatch(execution: Execution, contract: Q3ProductContract) -> str:
    """Name why a composed SP-1 contract is not this stage's exact fixture."""
    definition = execution.definition
    if not contract.intent_json:
        return "sp1_contract_without_intent"
    if {(item.name, item.model) for item in contract.topology.devices} != {
        (item.name, item.model) for item in definition.fixtures
    }:
        return "sp1_devices_differ_from_fixture"
    if {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in contract.topology.links
    } != {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in definition.links
    }:
        return "sp1_links_differ_from_fixture"
    clients = set(definition.selected_clients)
    hosts = {SP1_DNS_SERVER, SP1_WEB_SERVER}
    ids = {item.name: item.id for item in contract.topology.devices}
    # The intent is what the registered tool recomposes from, so it is
    # checked itself, not only the plans composed from it.
    try:
        intent = json.loads(contract.intent_json)
        services = [
            service
            for site in intent.get("sites", [])
            for service in site.get("services", [])
        ]
        declared = sorted(
            (
                service.get("service_type"),
                service.get("host_device_id"),
                tuple(sorted(service.get("client_device_ids", []))),
            )
            for service in services
        )
    except (TypeError, ValueError, AttributeError):
        return "sp1_intent_unreadable"
    wanted_clients = tuple(sorted(ids[name] for name in clients if name in ids))
    if len(wanted_clients) != len(clients) or declared != sorted(
        [
            ("dns", ids.get(SP1_DNS_SERVER), wanted_clients),
            ("http", ids.get(SP1_WEB_SERVER), wanted_clients),
        ]
    ):
        return "sp1_intent_services_differ_from_stage"
    # Every run-specific value is bound too: the address space, marker and
    # host name this coordinator derives from its own run id, and the server
    # addresses the composed plan assigned. A self-consistent intent with any
    # other value would verify against the wrong run.
    parameters = sp1_run_parameters(execution.record.run_id)
    addresses = {
        item.device_name: item.ipv4
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointStaticAddress)
    }
    dns_address = addresses.get(SP1_DNS_SERVER, "")
    web_address = addresses.get(SP1_WEB_SERVER, "")
    expected_services = {
        "dns": {
            "name": "sp1-dns",
            "service_type": "dns",
            "host_device_id": ids.get(SP1_DNS_SERVER),
            "address": dns_address,
            "dns_records": [{"hostname": parameters.hostname, "address": web_address}],
            "client_device_ids": list(wanted_clients),
        },
        "http": {
            "name": "sp1-web",
            "service_type": "http",
            "host_device_id": ids.get(SP1_WEB_SERVER),
            "address": web_address,
            "hostname": parameters.hostname,
            "http_content": parameters.marker,
            "client_device_ids": list(wanted_clients),
        },
    }
    canonical = sp1_intent(
        parameters.address_space,
        parameters.hostname,
        parameters.marker,
        dns_host_id=ids.get(SP1_DNS_SERVER, ""),
        web_host_id=ids.get(SP1_WEB_SERVER, ""),
        dns_address=dns_address,
        web_address=web_address,
        client_ids=wanted_clients,
    )

    def normalized(value: Any) -> str:
        for site in value.get("sites", []):
            for service in site.get("services", []):
                service["client_device_ids"] = sorted(
                    service.get("client_device_ids", [])
                )
        return json.dumps(value, sort_keys=True)

    if normalized(json.loads(contract.intent_json)) != normalized(canonical):
        # Uplinks, addressing, routing preference and every site are part of
        # what the tool recomposes; nothing outside the canonical form runs.
        return "sp1_intent_values_differ_from_run"
    if (
        not dns_address
        or not web_address
        or intent.get("address_space") != parameters.address_space
        or {
            service.get("service_type"): {
                **service,
                "client_device_ids": sorted(service.get("client_device_ids", [])),
            }
            for service in services
        }
        != expected_services
    ):
        return "sp1_intent_values_differ_from_run"
    if any(
        item.host_device_name not in hosts for item in contract.service_plan.actions
    ):
        return "sp1_service_action_outside_the_hosts"
    expectations = contract.service_plan.verification_expectations
    if any(
        item.host_device_name not in hosts
        or (item.client_device_name and item.client_device_name not in clients)
        for item in expectations
    ):
        return "sp1_expectation_outside_the_selection"
    required = sorted(
        (item.client_device_name, item.kind.value)
        for item in expectations
        if item.kind in SP1_REQUIRED_CLIENT_KINDS
    )
    if required != sorted(
        (name, kind.value) for name in clients for kind in SP1_REQUIRED_CLIENT_KINDS
    ):
        return "sp1_selected_clients_differ_from_stage"
    return ""


def _sp1_expected_routed_groups(
    execution: Execution, contract: Q3ProductContract
) -> set[tuple[str, str]]:
    """Return every (client segment, host segment) pair the selection routes.

    Derived from the composed endpoint addressing: each selected client and
    each server sit in one segment, and a request between two segments is a
    routed dependency the product must have admitted by a routed group.
    """
    segments = {
        item.device_name: item.segment_id
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointStaticAddress)
    }
    return {
        (segments.get(client, ""), segments.get(host, ""))
        for client in execution.definition.selected_clients
        for host in (SP1_DNS_SERVER, SP1_WEB_SERVER)
        if segments.get(client, "") != segments.get(host, "")
    }


def _sp1_client_checks(
    contract: Q3ProductContract, by_id: Mapping[str, Any]
) -> dict[str, dict[str, str]]:
    """Return each selected client's planned check kinds and their outcomes."""
    checks: dict[str, dict[str, str]] = {}
    for item in contract.service_plan.verification_expectations:
        if item.kind not in (*SP1_REQUIRED_CLIENT_KINDS, *SP1_BINDING_KINDS):
            continue
        observed = by_id.get(item.id)
        checks.setdefault(item.client_device_name, {})[item.kind.value] = (
            observed.status.value if observed is not None else "absent"
        )
    return checks


def run_sp1_routed_product(execution: Execution) -> None:
    """Run the SP-1 routed intent through the registered product tool."""
    contract = execution.product_contract
    boundaries = execution.run.boundaries
    definition = execution.definition
    if contract is None or boundaries.sp1_public_product_entry is None:
        execution.stop("sp1_product_contract_or_entry_absent")
        return
    mismatch = _sp1_contract_mismatch(execution, contract)
    if mismatch:
        execution.stop(mismatch)
        return
    clients = definition.selected_clients

    def terminal() -> None:
        ids = ("M-SP1-ROUTED-FINAL",)
        if not execution.begin_terminal(ids, "SP1_ROUTED_FINAL"):
            return
        with execution.procedure(ids):
            reader = boundaries.native_product_runtimes(
                execution.bound, contract.inventory
            ).configuration
            capture = getattr(reader, "capture_routed_text", None)
            with execution.ledger.purpose_of("sp1:final:routers"):
                routers = (
                    list(
                        capture(
                            SP1_ROUTERS,
                            sample_calls=SP1_CAPTURE_SAMPLE_CALLS,
                            deadline_seconds=SP1_CAPTURE_DEADLINE_SECONDS,
                        )
                    )
                    if callable(capture)
                    else []
                )
            with execution.ledger.purpose_of("sp1:final:clients"):
                binding_read = execution.probes.read_client_bindings(clients)
            bindings = (
                binding_read.payload.get("clients")
                if binding_read.observed and isinstance(binding_read.payload, dict)
                else None
            )
            complete = (
                len(routers) == 2 * len(SP1_ROUTERS)
                and all(
                    row.get("executed") and row.get("output_complete")
                    for row in routers
                )
                and sp1_terminal_bindings_observed(bindings, clients)
            )
            execution.conclude(
                "M-SP1-ROUTED-FINAL",
                Assessment(
                    MeasurementConclusion.SUPPORTED_IN_SAMPLE
                    if complete
                    else MeasurementConclusion.INCONCLUSIVE,
                    facts={
                        "routers": routers,
                        "router_capture_available": callable(capture),
                        "client_bindings": bindings,
                        "client_binding_read": binding_read.cause
                        if not binding_read.observed
                        else "observed",
                        "complete": complete,
                    },
                    causes=[] if complete else ["sp1_final_inventory_incomplete"],
                    limitations=["terminal_inventory_is_not_product_acceptance"],
                ),
            )
        execution.finish("SP1_ROUTED_FINAL")

    execution.register_terminal(("M-SP1-ROUTED-FINAL",), "SP1_ROUTED_FINAL", terminal)
    if not diagnostic_start(execution):
        return
    ids = ("M-SP1-ROUTED-PRODUCT",)
    if not execution.selected("SP1-product") or not execution.begin(
        ids, "SP1_ROUTED_PRODUCT"
    ):
        return
    with execution.procedure(ids):
        if not execution.run.transition("experiment:SP1_ROUTED_PRODUCT:started"):
            execution.stop("persistence:sp1_product_not_announced")
            return
        inner = boundaries.native_product_runtimes(execution.bound, contract.inventory)
        product_runtimes = ServiceStageRuntimes(
            configuration=RoutedInventoryConfigurationRuntime(
                inner.configuration, contract.inventory
            ),
            services=ExactInventoryServiceRuntime(inner.services, contract.inventory),
        )
        fresh_public_build = ""

        def public_binding() -> ServiceInvocationBinding:
            nonlocal fresh_public_build
            reading = boundaries.build_reader(execution.bound.send_and_wait).read()
            if (
                not reading.available
                or reading.version != execution.record.environment.observed_build
            ):
                raise ValueError("sp1_public_build_unobserved_or_mismatched")
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
                device_capability_catalog=contract.device_capability_catalog,
            )

        with execution.ledger.effect_of("sp1:apply-enterprise-services"):
            product = boundaries.sp1_public_product_entry(
                execution.bound,
                public_binding,
                contract.manifest,
                contract.intent_json,
                execution.record.environment.observed_build,
                f"SERVER-PT-SP1-ROUTED-01 {definition.stage.value}",
            )
        by_id = (
            {
                item.expectation_id: item
                for item in product.service_result.verification_results
            }
            if product.service_result is not None
            else {}
        )
        checks = _sp1_client_checks(contract, by_id)
        routed = [
            row
            for row in product.operational_readiness
            if row.get("kind") == "routed_forwarding"
        ]
        routed_keys = [
            (row.get("client_segment_id"), row.get("host_segment_id")) for row in routed
        ]
        expected_groups = _sp1_expected_routed_groups(execution, contract)
        candidate = contract.device_capability_catalog is not None
        injected = "device_capability_catalog:injected" in product.limitations
        accepted = (
            product.refusal_code is ServiceEntryRefusal.NONE
            and product.status is ServiceRunStatus.VERIFIED
            and product.stage is ServiceStage.COMPLETED
            and product.persisted_stage is ServiceStage.COMPLETED
            and bool(product.record_path)
            and not product.persist_error
            and fresh_public_build == execution.record.environment.observed_build
            and set(checks) == set(clients)
            and all(
                checks[name].get(kind.value) == ActionExecutionStatus.VERIFIED.value
                for name in clients
                for kind in SP1_REQUIRED_CLIENT_KINDS
            )
            and bool(expected_groups)
            and len(routed_keys) == len(set(routed_keys))
            and set(routed_keys) == expected_groups
            and all(row.get("status") == "admitted" for row in routed)
            and injected == candidate
            and bool(contract.device_capability_evidence) == candidate
        )
        execution.conclude(
            "M-SP1-ROUTED-PRODUCT",
            Assessment(
                MeasurementConclusion.SUPPORTED_IN_SAMPLE
                if accepted
                else MeasurementConclusion.INCONCLUSIVE,
                facts={
                    "product_summary": product.compact_summary(),
                    "product_record_path": product.record_path,
                    "entry_surface": "registered_four_input",
                    "device_catalog": "candidate" if candidate else "default",
                    "device_candidate_evidence": list(
                        contract.device_capability_evidence
                    ),
                    "device_candidate_evidence_sha256": hashlib.sha256(
                        json.dumps(
                            list(contract.device_capability_evidence),
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                    "product_device_catalog_injected": injected,
                    "expected_routed_groups": sorted(
                        list(item) for item in expected_groups
                    ),
                    "fresh_public_build": fresh_public_build,
                    "selected_clients": list(clients),
                    "client_checks": checks,
                    "routed_groups": [
                        {
                            "client_segment_id": row.get("client_segment_id"),
                            "host_segment_id": row.get("host_segment_id"),
                            "status": row.get("status"),
                            "device_ids": row.get("device_ids"),
                        }
                        for row in routed
                    ],
                },
                causes=[]
                if accepted
                else [f"sp1_product_not_verified:{product.refusal_code.value}"],
                limitations=(
                    ["candidate_device_evidence_not_global_product_promotion"]
                    if candidate
                    else []
                ),
            ),
        )
    execution.finish("SP1_ROUTED_PRODUCT")
    if not accepted:
        execution.stop("sp1_product_not_verified")
