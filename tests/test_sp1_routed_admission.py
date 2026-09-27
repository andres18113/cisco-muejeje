"""SP-1 SP1-01: routed admission and effect scope through the real use case.

The two runtimes are recording fakes (the external boundary); composition,
admission, the closure and the E5 applicator are production code. Every
refusal must leave the recording runtimes without one mutating call, and an
admitted run must dispatch exactly the closure its paths name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from service_entry_fixture import (
    BACKEND_VERSION,
    DEPLOYMENT_ID,
    FINGERPRINT,
    EndpointObserver,
    IsolationPreflight,
    ManifestStore,
    RecordingConfigurationRuntime,
    RecordingServiceRuntime,
)
from sp1_routed_fixture import compose, topology_payload, with_services

from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from packet_tracer_mcp.domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceRunStatus,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    SourceTreeIdentity,
)
from packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    candidate_capability_adapter,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)

#: What the SP-1 fixtures need beyond measured evidence, and nothing else.
STATIC_ROUTE_CANDIDATES = {
    "1941": ["supports_static_routes"],
    "2911": ["supports_static_routes"],
}


def _run(tmp_path: Path, payload: dict, *, candidate: bool = False):
    plans = compose(payload)
    configuration = RecordingConfigurationRuntime(targets=plans.inventory)
    services = RecordingServiceRuntime(targets=plans.inventory)
    result = apply_enterprise_services(
        json.dumps(payload),
        deployment_id=DEPLOYMENT_ID,
        packet_tracer_version=BACKEND_VERSION,
        runtimes=ServiceStageRuntimes(configuration=configuration, services=services),
        manifest_store=ManifestStore(manifest=plans.manifest),
        record_store=ServiceRunRecordStore(tmp_path),
        import_preflight=IsolationPreflight(),
        environment_fingerprint=FINGERPRINT,
        transport_selection=TransportSelection(channel="http"),
        endpoint_observer=EndpointObserver(address=""),
        source_tree=SourceTreeIdentity(sha="test-source", dirty=True),
        device_capability_catalog=(
            candidate_capability_adapter(
                BACKEND_VERSION, STATIC_ROUTE_CANDIDATES, label="sp1-test"
            )
            if candidate
            else None
        ),
    )
    return result, plans, configuration, services


def _workload(clients: list[str] | None = None, **kwargs) -> dict:
    base = topology_payload(**kwargs)
    return with_services(base, compose(base, services=False), clients=clients)


def _scope_devices(result, plans) -> dict[str, set[str]]:
    by_id = {item.id: item for item in plans.configuration.actions}
    found: dict[str, set[str]] = {}
    for identifier in result.e5_effect_scope.mutated:
        action = by_id[identifier]
        found.setdefault(action.action_type.value, set()).add(action.device_name)
    return found


def test_hq_inter_vlan_clients_admit_only_the_hq_gateway_closure(tmp_path: Path):
    """Single gateway: HQ subinterfaces and trunk, no transit, no route."""
    payload = _workload(["HQ-DEFAULT-PC-01", "HQ-DEFAULT-PC-02"])

    result, plans, configuration, _services = _run(tmp_path, payload)

    assert result.refusal_code is not ServiceEntryRefusal.SERVICE_PATH_UNSUPPORTED
    scope = _scope_devices(result, plans)
    assert scope["configure_subinterface"] == {"HQ-EDGE-RTR-01"}
    assert scope["configure_trunk"] == {"HQ-DEFAULT-ACCESS-SW-01"}
    assert "configure_static_route" not in scope
    assert "configure_routed_interface" not in scope
    dispatched = {item for batch in configuration.applied for item in batch}
    assert dispatched == set(result.e5_effect_scope.mutated)


def test_multi_site_routes_need_static_route_evidence_before_any_effect(
    tmp_path: Path,
):
    """The default catalog has no measured `supports_static_routes` yet."""
    result, _plans, configuration, services = _run(tmp_path, _workload())

    assert result.status is ServiceRunStatus.REFUSED
    assert result.refusal_code is ServiceEntryRefusal.CAPABILITY_UNKNOWN
    assert "supports_static_routes=unknown" in result.blocked_reason
    assert configuration.applied == [] and services.applied == []


def test_candidate_evidence_admits_the_whole_route_chain(tmp_path: Path):
    """Every router, transit end and route on both chains is in scope."""
    result, plans, configuration, _services = _run(
        tmp_path, _workload(), candidate=True
    )

    scope = _scope_devices(result, plans)
    assert scope["configure_static_route"] == {
        "HQ-EDGE-RTR-01",
        "BR1-EDGE-RTR-01",
        "BR2-EDGE-RTR-01",
    }
    assert scope["configure_routed_interface"] == {
        "HQ-EDGE-RTR-01",
        "BR1-EDGE-RTR-01",
        "BR2-EDGE-RTR-01",
    }
    assert "device_capability_catalog:injected" in result.limitations
    dispatched = {item for batch in configuration.applied for item in batch}
    assert dispatched == set(result.e5_effect_scope.mutated)


def test_a_partial_selection_excludes_what_its_paths_do_not_need(tmp_path: Path):
    """BR1 clients never touch BR2 or the BR1-BR2 link."""
    payload = _workload(["BR1-DEFAULT-PC-01", "BR1-DEFAULT-PC-02"])

    result, plans, _configuration, _services = _run(tmp_path, payload, candidate=True)

    scope = _scope_devices(result, plans)
    assert "BR2-EDGE-RTR-01" not in set().union(*scope.values())
    by_id = {item.id: item for item in plans.configuration.actions}
    excluded_routes = {
        by_id[item].device_name
        for item in result.e5_effect_scope.excluded
        if by_id[item].action_type.value == "configure_static_route"
    }
    assert "BR2-EDGE-RTR-01" in excluded_routes


@pytest.mark.parametrize("routing", ["", "ripv2"])
def test_without_compiled_routes_a_branch_client_is_refused_by_name(
    tmp_path: Path, routing: str
):
    """No static routing requested: the missing hop is named, nothing runs."""
    payload = _workload(["BR2-DEFAULT-PC-01"], routing=routing)

    result, _plans, configuration, services = _run(tmp_path, payload, candidate=True)

    assert result.refusal_code is ServiceEntryRefusal.SERVICE_PATH_UNSUPPORTED
    assert "route_missing:BR2-EDGE-RTR-01" in result.blocked_reason
    assert configuration.applied == [] and services.applied == []
