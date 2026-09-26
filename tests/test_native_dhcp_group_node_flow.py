"""Grouped native DHCP evidence through the product, decisions and records.

The real A1-E6 use case, E6 runtime, scheduler and record store run over the
Node engine. Only answers crossing the bridge are substituted: a plan rewrites
the engine's grouped lease scan or inactive-client reading for chosen samples,
the way a transient Packet Tracer getter failure or a conflicting reading
would arrive. The public default capability catalog admits the requested
`.125`-`.126` policy.
"""

from __future__ import annotations

import json

import pytest
from native_dhcp_product_flow import run_native_product

from packet_tracer_mcp.adapters.cli.service_qualification import (
    _native_dhcp_http_intent,
    native_dhcp_http_product_contract,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceVerificationKind,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)
from tests.service_qualification_engine import (
    FORWARDING_ROWS,
    NodeEngine,
    NodeEngineTransport,
    require_node,
)

PC1 = "Q3-DEFAULT-PC-01"
PC2 = "Q3-DEFAULT-PC-02"
LOST = "lost"


def _unreadable(client: dict) -> dict:
    """Answer one port the way the scan script's getter catch does."""
    return {
        **client,
        "mode": None,
        "mode_type": "error",
        "ipv4": "",
        "netmask": "",
        "mac": "",
        "error": "Error: client MAC getter failed",
    }


def _make_unreadable(device: str):
    def change(payload: dict) -> dict:
        payload["clients"] = [
            _unreadable(item) if item["device_name"] == device else item
            for item in payload["clients"]
        ]
        return payload

    return change


def _take_address_of(device: str, owner: str):
    """Report `device` on `owner`'s current address with its own MAC."""

    def change(payload: dict) -> dict:
        address = next(
            item["ipv4"] for item in payload["clients"] if item["device_name"] == owner
        )
        for item in payload["clients"]:
            if item["device_name"] == device:
                item["ipv4"] = address
        return payload

    return change


def _colon_mac(mac: str) -> str:
    """Spell a dotted Packet Tracer MAC in the colon form the parser accepts."""
    digits = mac.replace(".", "").lower()
    return ":".join(digits[index : index + 2] for index in range(0, 12, 2))


def _report_unassigned_with_mac_of(device: str, owner: str, spell=str):
    """Report `device` as not yet addressed but carrying `owner`'s MAC."""

    def change(payload: dict) -> dict:
        mac = spell(
            next(
                item["mac"]
                for item in payload["clients"]
                if item["device_name"] == owner
            )
        )
        for item in payload["clients"]:
            if item["device_name"] == device:
                item.update(ipv4="0.0.0.0", netmask="0.0.0.0", mac=mac)
        return payload

    return change


class _PlannedTransport(NodeEngineTransport):
    """Rewrite chosen grouped scans and inactive readings, per occurrence."""

    def __init__(self, engine, *, scans=None, inactive=None) -> None:
        super().__init__(engine)
        self.scan_plan = dict(scans or {})
        self.inactive_plan = dict(inactive or {})
        self.scans = 0
        self.inactive_reads = 0

    def dispatch_and_wait(self, js_code, timeout):
        outcome = super().dispatch_and_wait(js_code, timeout)
        if "var group=" in js_code:
            self.scans += 1
            change = self.scan_plan.get(self.scans)
        elif "{device:name,interface:want" in js_code:
            self.inactive_reads += 1
            change = self.inactive_plan.get(self.inactive_reads)
        else:
            return outcome
        if change is None:
            return outcome
        if change == LOST:
            return BridgeDispatchOutcome(
                dispatch=DispatchFact.ACCEPTANCE_UNKNOWN,
                result=ResultFact.NOT_OBSERVED,
                detail="planned_result_lost",
            )
        body = json.dumps(change(json.loads(outcome.body)))
        return BridgeDispatchOutcome(
            dispatch=outcome.dispatch, result=outcome.result, body=body
        )


def _run(tmp_path, selected_count: int, run_id: str, **plan):
    """Run the product once and return typed rows, stored rows and requests."""
    require_node()
    intent = _native_dhcp_http_intent(selected_count, 124)
    contract = native_dhcp_http_product_contract(
        "9.0.1.0858", run_id, selected_count=selected_count, start_offset=124
    )
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled_candidate",
        dhcp_native_max_behavior=(
            "resize_candidate" if selected_count == 2 else "resize"
        ),
        dhcp_mode_acquires=True,
        dhcp_retry_on_server_enable=True,
        stp_rows=FORWARDING_ROWS,
        terminals=True,
    )
    try:
        for device in contract.topology.devices:
            engine.seed_device(device.name, device.model)
        transport = _PlannedTransport(engine, **plan)
        result = run_native_product(
            tmp_path, contract, intent, transport, run_id=run_id
        )
        assert result.service_result is not None, (
            result.refusal_code,
            result.blocked_reason,
        )
        assert engine.snapshot()["dhcp_runs"] == []
    finally:
        engine.close()
    stored = ServiceRunRecordStore(tmp_path).load(result.deployment_id, result.run_id)
    kinds = {
        item.id: item.kind for item in contract.service_plan.verification_expectations
    }
    names = {
        item.id: item.client_device_name
        for item in contract.service_plan.verification_expectations
    }

    def by_client(rows, kind):
        return {
            names[item.expectation_id]: item
            for item in rows
            if kinds[item.expectation_id] is kind
        }

    requests = [script for _kind, script in transport.calls if ".go(" in script]
    return (
        by_client(result.service_result.verification_results, _LEASE),
        by_client(stored.service_result.verification_results, _LEASE),
        by_client(stored.service_result.verification_results, _FETCH),
        requests,
        transport,
    )


_LEASE = ServiceVerificationKind.DHCP_LEASE
_FETCH = ServiceVerificationKind.HTTP_FETCH


def test_positive_two_client_product_verifies_both_and_requests_both(tmp_path):
    """Positive control on the public route: both joins, both cold requests."""
    typed, stored, fetch, requests, transport = _run(tmp_path, 2, "group-positive")

    for name in (PC1, PC2):
        assert typed[name].status.value == "verified", typed[name].cause
        assert stored[name].status.value == "verified"
        assert stored[name].observed["local_failure_cause"] == ""
        assert stored[name].observed["global_failure_sample"] == 0
        assert fetch[name].status.value == "verified"
    assert {stored[name].observed["client_ipv4"] for name in (PC1, PC2)} == {
        "192.0.2.125",
        "192.0.2.126",
    }
    assert len(requests) == 2
    assert transport.scans == 2


@pytest.mark.parametrize(
    ("failing", "owner"),
    [(PC2, PC1), (PC1, PC2)],
)
def test_prior_local_failure_cannot_hide_a_later_duplicate(tmp_path, failing, owner):
    """The review counterexample, both ways round, closes every dependent request."""
    typed, stored, fetch, requests, transport = _run(
        tmp_path,
        2,
        f"group-duplicate-{failing[-1]}",
        scans={1: _make_unreadable(failing), 2: _take_address_of(failing, owner)},
    )

    for name in (PC1, PC2):
        assert typed[name].status.value == "failed", (name, typed[name].cause)
        assert stored[name].cause == "native_selected_identity_duplicate"
        assert stored[name].observed["global_failure_sample"] == 2
        assert fetch[name].status.value == "dependency_blocked"
    assert requests == []
    record = stored[failing].observed
    assert record["local_failure_cause"] == "native_client_identity_unobserved"
    assert record["local_failure_sample"] == 1
    readings = json.loads(record["client_readings_json"])
    assert [item["reading"] for item in readings] == ["unreadable", "assigned"]
    assert readings[1]["ipv4"] == stored[owner].observed["client_ipv4"]
    assert transport.scans == 2


@pytest.mark.parametrize("spell", [str, _colon_mac], ids=["same", "colon"])
def test_unassigned_peer_reporting_the_same_mac_withholds_every_request(
    tmp_path, spell
):
    """An ambiguous MAC owner, however spelled, never releases HTTP."""
    typed, stored, fetch, requests, _transport = _run(
        tmp_path,
        2,
        f"group-twin-mac-{spell.__name__}",
        scans={
            number: _report_unassigned_with_mac_of(PC2, PC1, spell)
            for number in (1, 2, 3)
        },
    )

    for name in (PC1, PC2):
        assert typed[name].status.value == "failed", (name, typed[name].cause)
        assert stored[name].cause == "native_selected_identity_duplicate"
        assert stored[name].observed["global_failure_sample"] == 1
        assert fetch[name].status.value == "dependency_blocked"
    assert requests == []


def test_local_unreadable_client_blocks_only_its_own_request(tmp_path):
    """Without a global reason the positive peer keeps its verified request."""
    typed, stored, fetch, requests, _transport = _run(
        tmp_path,
        2,
        "group-local-only",
        scans={number: _make_unreadable(PC2) for number in (1, 2, 3)},
    )

    assert typed[PC1].status.value == "verified"
    assert fetch[PC1].status.value == "verified"
    assert typed[PC2].status.value == "unknown"
    assert stored[PC2].cause == "native_client_identity_unobserved"
    assert stored[PC2].observed["local_failure_sample"] == 1
    assert fetch[PC2].status.value == "dependency_blocked"
    assert len(requests) == 1
    assert "192.0.2.10" in requests[0]


def _inactive_change(**fields):
    def change(payload: dict) -> dict:
        payload.update(fields)
        return payload

    return change


@pytest.mark.parametrize(
    ("second", "status", "cause", "detail"),
    [
        (
            _inactive_change(
                mode=None,
                mode_type="error",
                ipv4="",
                netmask="",
                mac="",
                error="read_error",
            ),
            "unknown",
            "native_inactive_client_unobserved",
            "read_error",
        ),
        (LOST, "unknown", "native_inactive_client_unobserved", "unobserved:"),
        (
            _inactive_change(ipv4="undefined"),
            "unknown",
            "native_inactive_client_unobserved",
            "reading_invalid",
        ),
        (
            _inactive_change(mac="00AA.00BB.00CC"),
            "failed",
            "native_inactive_client_changed",
            "mac_changed",
        ),
        (
            _inactive_change(mode=True),
            "failed",
            "native_inactive_client_changed",
            "dhcp_mode_on",
        ),
    ],
)
def test_inactive_client_reading_is_classified_and_persisted(
    tmp_path, second, status, cause, detail
):
    """Clear then unreadable is unobserved; a fresh change is a contradiction."""
    typed, stored, fetch, requests, transport = _run(
        tmp_path, 1, f"group-inactive-{status}-{detail[:8]}", inactive={2: second}
    )

    assert typed[PC1].status.value == status
    assert stored[PC1].cause == cause
    assert stored[PC1].observed["global_failure_sample"] == 2
    assert stored[PC1].observed["global_failure_detail"].startswith(f"{PC2}:{detail}")
    assert fetch[PC1].status.value == "dependency_blocked"
    assert requests == []
    assert transport.inactive_reads == 2
