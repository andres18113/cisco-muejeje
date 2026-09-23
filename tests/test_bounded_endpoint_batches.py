"""Endpoint addressing is sent in bounded chunks, each with its own outcome."""

from __future__ import annotations

import pytest
from campus_product_simulation import campus_payload, compose_campus

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    SetEndpointStaticAddress,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    MAX_ENDPOINT_CALLS_PER_SEND,
    PacketTracerEnterpriseConfigurationRuntime,
)


@pytest.fixture(scope="module")
def endpoints():
    """Every static endpoint action a 150-client campus compiles."""
    plans = compose_campus(campus_payload(150))
    return [
        item
        for item in plans.configuration_plan.actions
        if isinstance(item, SetEndpointStaticAddress)
    ]


def _runtime(sent: list[str], refuse: set[int] = frozenset()):
    def send(payload: str) -> bool:
        sent.append(payload)
        return len(sent) - 1 not in refuse

    return PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=send,
        send_and_wait=lambda script, timeout: None,
    )


def test_many_endpoints_are_sent_in_bounded_chunks(endpoints):
    """Script size is bounded by the call count of one send."""
    sent: list[str] = []

    rows = _runtime(sent).apply_actions(endpoints)

    expected = -(-len(endpoints) // MAX_ENDPOINT_CALLS_PER_SEND)
    assert len(sent) == expected > 1
    assert all(
        payload.count("configurePcIp(") <= MAX_ENDPOINT_CALLS_PER_SEND
        for payload in sent
    )
    assert sum(payload.count("configurePcIp(") for payload in sent) == len(endpoints)
    phase = int(endpoints[0].phase)
    assert {row.batch_id for row in rows} == {
        f"endpoints:{phase}:{index}" for index in range(expected)
    }
    assert all(row.applied for row in rows)


def test_a_refused_chunk_marks_only_its_own_actions(endpoints):
    """Partial outcomes stay visible; nothing is hidden behind one batch."""
    sent: list[str] = []

    rows = _runtime(sent, refuse={1}).apply_actions(endpoints)

    phase = int(endpoints[0].phase)
    refused = {row.action_id for row in rows if not row.applied}
    assert refused and {row.batch_id for row in rows if row.action_id in refused} == {
        f"endpoints:{phase}:1"
    }
    assert len(refused) == MAX_ENDPOINT_CALLS_PER_SEND
    assert all(row.applied for row in rows if row.action_id not in refused)


def test_a_plan_within_one_chunk_sends_exactly_as_before(endpoints):
    """Up to the bound, one send and the historical batch id."""
    sent: list[str] = []

    rows = _runtime(sent).apply_actions(endpoints[:3])

    assert len(sent) == 1
    assert {row.batch_id for row in rows} == {f"endpoints:{int(endpoints[0].phase)}"}
