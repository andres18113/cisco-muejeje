"""Offline replay of later final W1/W2 IOS against the corrected rule.

The qualification's terminal capture was taken after the product readiness
episodes. Matching the archived product's selected destination and interface
facts does not reconstruct the original next-hop lookups, which its projection
did not retain. This test makes no new native readiness claim.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packet_tracer_mcp.adapters.cli.sp1_routed_qualification import (
    sp1_routed_product_contract,
)
from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    _paths_by_pair,
)
from packet_tracer_mcp.application.use_cases.service_path_admission import (
    path_admission,
)
from packet_tracer_mcp.domain.enterprise.models.routed_forwarding import (
    RoutedForwardingObservation,
    RoutedForwardingRound,
)
from packet_tracer_mcp.domain.enterprise.services.routed_readiness import (
    round_admits_all,
    routed_verdicts,
)
from packet_tracer_mcp.domain.enterprise.services.service_access_readiness import (
    SERVICE_REQUEST_KINDS,
    derive_access_readiness_plan,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    _routed_reading,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)

ARCHIVE = (
    Path(__file__).resolve().parents[1]
    / "docs/reference/server-pt/evidence/sp1-routed-01"
)


def _ios(item: dict) -> IosCommandResult:
    """Rehydrate one archived, attributed terminal read at the typed boundary."""
    return IosCommandResult(
        device_name=item["device"],
        query_id=OperationalQueryId(item["query"]),
        executed=item["executed"],
        output=item["output"],
        failure_reason=item["failure_reason"],
        fresh_output_observed=item["fresh_output_observed"],
        output_complete=item["output_complete"],
        truncated_by_pager=item["truncated_by_pager"],
        observed_device_name=item["observed_device_name"],
        device_identity_provenance=item["device_identity_provenance"],
    )


@pytest.mark.parametrize("episode", ["e3", "e4"])
def test_final_native_readings_replay_through_corrected_routed_rule(episode):
    """Later complete tables admit the same compiled W1/W2 paths offline."""
    record_dir = ARCHIVE / episode / "record"
    [qualification_path] = record_dir.glob("sp1-routed-w*.json")
    [product_path] = (
        path for path in record_dir.glob("*.json") if path != qualification_path
    )
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    product = json.loads(product_path.read_text(encoding="utf-8"))
    selected = tuple(qualification["measurements"][0]["facts"]["selected_clients"])
    contract = sp1_routed_product_contract(
        qualification["environment"]["observed_build"],
        qualification["run_id"],
        selected,
    )
    assert contract.topology.physical_identity_hash == product["physical_topology_hash"]
    assert (
        contract.configuration_plan.semantic_hash
        == product["configuration_semantic_hash"]
    )
    assert contract.service_plan.semantic_hash == product["service_semantic_hash"]
    unsupported, paths = path_admission(
        contract.configuration_plan,
        contract.service_plan,
        contract.service_plan.services,
        links=contract.topology.links,
    )
    assert not unsupported
    plan = derive_access_readiness_plan(
        configuration_actions=contract.configuration_plan.actions,
        verification_expectations=contract.service_plan.verification_expectations,
        request_kinds=SERVICE_REQUEST_KINDS,
        routed_paths=_paths_by_pair(paths),
    )
    assert len(plan.routed) == (1 if episode == "e3" else 3)
    ids = {device.name: device.id for device in contract.topology.devices}
    names = {device.id: device.name for device in contract.topology.devices}
    captures: dict[str, dict] = {}
    for item in qualification["measurements"][1]["facts"]["routers"]:
        captures.setdefault(item["device"], {})[item["query"]] = item
    readings = {}
    for name, pair in captures.items():
        brief = pair["show_ip_interface_brief"]
        routes = pair["show_ip_route"]
        readings[ids[name]] = _routed_reading(
            name,
            _ios(brief),
            _ios(routes),
            channel_calls=brief["channel_calls"] + routes["channel_calls"],
            exhausted=False,
            after_deadline=False,
        )
    assert len(readings) == 3
    assert all(item.authoritative for item in readings.values())
    prior = {
        (row["client_segment_id"], row["host_segment_id"]): row
        for row in product["operational_readiness"]
        if row.get("kind") == "routed_forwarding"
    }
    for group in plan.routed:
        key = (group.client_segment_id, group.host_segment_id)
        mapping = {device_id: names[device_id] for device_id in group.device_ids}
        round_ = RoutedForwardingRound(
            index=0,
            elapsed_ms=0,
            readings=tuple(readings[device_id] for device_id in group.device_ids),
            complete=True,
        )
        assert round_admits_all(group, round_, mapping)
        observation = RoutedForwardingObservation(
            device_names=tuple(mapping.values()),
            rounds=(round_,),
            episode_end_reason="required_paths_forwarding",
        )
        admitted = {
            expectation_id
            for expectation_id, verdict in routed_verdicts(
                group, observation, mapping
            ).items()
            if verdict.admitted
        }
        assert len(admitted) == 8
        archived = prior[key]
        assert admitted == {
            item["expectation_id"]
            for item in archived["dependents"]
            if item["admitted"]
        }
        for device_id, facts in archived["sample"]["devices"].items():
            reading = readings[device_id]
            assert facts["route_rows"] == len(reading.route_table.rows)
            for destination, old in facts["routes"].items():
                now = [
                    {
                        "code": row.code,
                        "prefix": f"{row.network}/{row.prefix_length}",
                        "next_hop": row.next_hop,
                        "interface": row.interface,
                    }
                    for row in reading.route_table.longest_match(destination)
                ]
                assert old == now
            for interface, old in facts["interfaces"].items():
                now = [
                    {"ipv4": row.ipv4, "status": row.status, "protocol": row.protocol}
                    for row in reading.interface(interface)
                ]
                assert old == now
