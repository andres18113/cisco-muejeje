"""Plan-driven scale through the whole scalable envelope, over SIMULATED campuses.

Two hundred clients on one site and a thousand over three sites (each site has
its own Server-PT and HTTP service, because the planner's two distribution
switches bound one site's access capacity) run through the production
coordinator, composition, product, runtimes, readiness gate, ledger, evaluator
and stores. The campuses are what the real planner compiles; only what lies
beyond the bridge is simulated. A campus larger than the maintained CP-SCALE
reference in declared devices and links is not evidence of Packet Tracer
capacity.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from campus_product_simulation import campus_payload, compose_campus
from cold_http_acceptance_harness import MARKER
from poe_delivery_capabilities import compose_delivery_qualified_cp_scale_canonical
from scalable_http_acceptance_harness import build_scalable_harness

from packet_tracer_mcp.domain.enterprise.models.cold_http_acceptance import (
    CampaignOutcome,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    ServiceRunRecord,
)
from packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)


@pytest.fixture(scope="module")
def campus1000():
    """One thousand clients over three sites, compiled once."""
    return compose_campus(campus_payload(1000, marker=MARKER, sites=3))


def test_the_generated_campus_is_larger_than_the_cp_scale_reference(campus1000):
    """Compared in declared devices and links; the reference is only read."""
    reference = compose_delivery_qualified_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION
    )
    assert reference.topology is not None, reference.issues

    devices = len(reference.topology.devices)
    links = len(reference.topology.links)
    assert (devices, links) == (314, 219)
    assert campus1000.device_count >= devices
    assert campus1000.link_count >= links


def _one_request_each(envelope, clients: int) -> None:
    assert len(envelope.clients) == clients
    assert all(item.accepted for item in envelope.clients)
    assert all(item.release_dispatches == 1 for item in envelope.clients)
    orders = sorted(envelope.clients, key=lambda item: item.request_order)
    assert [item.request_order for item in orders] == list(range(1, clients + 1))
    assert [item.expectation_id for item in orders] == sorted(
        item.expectation_id for item in orders
    )


def test_two_hundred_clients_on_one_site_through_the_whole_envelope(tmp_path: Path):
    """Nine access groups and one component, every client accepted once."""
    harness = build_scalable_harness(tmp_path, 200)

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is True, envelope.reasons[:10]
    _one_request_each(envelope, 200)
    # Shared evidence is kept once: the envelope references the record's rows.
    assert envelope.readiness == []
    record = ServiceRunRecord.model_validate_json(
        Path(envelope.product["reloaded_record_path"]).read_text(encoding="utf-8")
    )
    rows = [dict(item) for item in record.operational_readiness]
    assert envelope.product["readiness_rows"] == len(rows)
    assert (
        envelope.product["readiness_sha256"]
        == hashlib.sha256(
            json.dumps(rows, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    )
    kinds = [row.get("kind", "access") for row in rows]
    assert kinds.count("trunk_continuity") == 1
    assert kinds.count("access") == len(harness.prepared.scope.groups) - 1
    assert envelope.budget.reserve_used == 200


def test_a_thousand_clients_over_three_sites_through_the_whole_envelope(
    tmp_path: Path, campus1000
):
    """Every selected client has one request, one outcome and one release."""
    harness = build_scalable_harness(tmp_path, 1000, plans=campus1000)

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is True, envelope.reasons[:10]
    assert envelope.campaign_outcome is CampaignOutcome.COMPLETED
    _one_request_each(envelope, 1000)
    assert len(envelope.scope["servers"]) == 3
    assert envelope.budget.used_operations <= envelope.budget.max_operations
    assert harness.product_dispatches().count("http_start") == 1000
    stored = harness.envelope_store.load(envelope.attempt_id)
    assert stored.http_accepted is True
    assert len(stored.clients) == 1000
