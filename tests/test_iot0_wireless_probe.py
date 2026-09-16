"""IoT-0 is prepared, not run. These tests hold it to what it promised.

Nothing here talks to Packet Tracer. What is checked is the shape of the plan:
that it only reads, that it stays bounded and build-scoped, that it never asks
for a credential, and that it identifies a pairing by identity rather than by
where something sits on a canvas.
"""

from __future__ import annotations

import json
import re

import pytest

from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)
from src.packet_tracer_mcp.infrastructure.execution.iot0_wireless_probe import (
    FORBIDDEN_PROFILE_FIELDS,
    MAX_RECEIVERS,
    PROFILE_FIELDS,
    IoT0WirelessProbe,
    ProbeRole,
    ProbeStep,
    ProbeTarget,
)


ENDPOINT = ProbeTarget(
    runtime_device_name="LAB-SMOKE-01",
    role=ProbeRole.ENDPOINT,
    model="Smoke Detector",
)
ACCESS_POINT = ProbeTarget(
    runtime_device_name="LAB-AP-01",
    role=ProbeRole.ACCESS_POINT,
    model="AccessPoint-PT",
)
ANTENNA = ProbeTarget(
    runtime_device_name="LAB-AP-01", role=ProbeRole.ANTENNA,
)
TARGETS = (ENDPOINT, ACCESS_POINT, ANTENNA)


def _contract():
    return IoT0WirelessProbe().contract(TARGETS)


def test_the_probe_is_scoped_to_one_exact_build():
    probe = IoT0WirelessProbe(MEASURED_BACKEND_VERSION)

    assert probe.contract(TARGETS).backend_version == MEASURED_BACKEND_VERSION
    with pytest.raises(ValueError):
        IoT0WirelessProbe("8.2.2")


def test_the_contract_covers_the_authoritative_surface_first():
    contract = _contract()

    endpoint_steps = [item.step for item in contract.scripts_for(ProbeRole.ENDPOINT)]
    assert endpoint_steps[0] is ProbeStep.ENDPOINT_WIRELESS_CLIENT_PROCESS
    assert set(endpoint_steps) == {
        ProbeStep.ENDPOINT_WIRELESS_CLIENT_PROCESS,
        ProbeStep.ENDPOINT_CURRENT_PROFILE,
        ProbeStep.ENDPOINT_SSID,
        ProbeStep.ENDPOINT_CURRENT_AP_MAC,
        ProbeStep.ENDPOINT_WIRELESS_PORT,
        ProbeStep.ENDPOINT_PORT_INVENTORY,
    }

    ap_steps = [item.step for item in contract.scripts_for(ProbeRole.ACCESS_POINT)]
    assert ap_steps[0] is ProbeStep.ACCESS_POINT_WIRELESS_SERVER_PROCESS
    assert set(ap_steps) == {
        ProbeStep.ACCESS_POINT_WIRELESS_SERVER_PROCESS,
        ProbeStep.ACCESS_POINT_SERVICE_SET,
        ProbeStep.ACCESS_POINT_RADIO_PORT,
        ProbeStep.ACCESS_POINT_PORT_INVENTORY,
    }

    assert [item.step for item in contract.scripts_for(ProbeRole.ANTENNA)] == [
        ProbeStep.ANTENNA_RECEIVERS,
    ]


def test_the_probe_asks_for_the_documented_wireless_processes_by_name():
    contract = _contract()
    sources = {item.step: item.source for item in contract.scripts}

    assert '"WirelessClient"' in sources[ProbeStep.ENDPOINT_WIRELESS_CLIENT_PROCESS]
    assert (
        '"WirelessServer"'
        in sources[ProbeStep.ACCESS_POINT_WIRELESS_SERVER_PROCESS]
    )
    assert "getCurrentApMac" in sources[ProbeStep.ENDPOINT_CURRENT_AP_MAC]
    assert "getCurrentProfile" in sources[ProbeStep.ENDPOINT_CURRENT_PROFILE]
    assert "getSsid" in sources[ProbeStep.ENDPOINT_SSID]
    assert "getReceiverCount" in sources[ProbeStep.ANTENNA_RECEIVERS]
    assert "getReceiverAt" in sources[ProbeStep.ANTENNA_RECEIVERS]


@pytest.mark.parametrize(
    "mutator",
    [
        "set", "add", "remove", "delete", "reset", "swap", "create", "apply",
    ],
)
def test_no_generated_script_calls_a_mutating_member(mutator):
    """Read-only is enforced on the scripts, not promised in a docstring."""
    pattern = re.compile(rf"\.{mutator}[A-Za-z0-9_]*\s*\(", re.IGNORECASE)

    for script in _contract().scripts:
        assert not pattern.search(script.source), (script.step, mutator)
        assert script.reads_only


def test_no_generated_script_reads_a_credential():
    """Checked as a literal or a member access, not as a loose substring."""
    for credential in FORBIDDEN_PROFILE_FIELDS:
        assert credential not in PROFILE_FIELDS
        patterns = [
            json.dumps(credential),
            f"'{credential}'",
            f".{credential}",
            f"[{credential}]",
        ]
        for script in _contract().scripts:
            for pattern in patterns:
                assert pattern not in script.source, (script.step, pattern)


def test_the_profile_projection_names_exactly_what_it_takes():
    source = next(
        item.source for item in _contract().scripts
        if item.step is ProbeStep.ENDPOINT_CURRENT_PROFILE
    )

    encoded = json.dumps(list(PROFILE_FIELDS))
    assert encoded in source
    assert "ssid" in PROFILE_FIELDS
    assert "macAddress" in PROFILE_FIELDS
    assert "isDhcpEnabled" in PROFILE_FIELDS


def test_the_receiver_walk_is_bounded():
    source = next(
        item.source for item in _contract().scripts
        if item.step is ProbeStep.ANTENNA_RECEIVERS
    )

    assert f"var cap={MAX_RECEIVERS}" in source
    assert "limit=(rc<cap)?rc:cap" in source


def test_every_script_serializes_the_device_name():
    hostile = 'BAD"); reportResult("pwned'
    targets = (
        ProbeTarget(runtime_device_name=hostile, role=ProbeRole.ENDPOINT),
        ProbeTarget(runtime_device_name=hostile, role=ProbeRole.ACCESS_POINT),
        ProbeTarget(runtime_device_name=hostile, role=ProbeRole.ANTENNA),
    )

    for script in IoT0WirelessProbe().contract(targets).scripts:
        assert hostile not in script.source, script.step
        assert json.dumps(hostile) in script.source, script.step


def test_every_script_reports_where_it_stopped():
    for script in _contract().scripts:
        assert "stopped_at" in script.source, script.step
        assert "reportResult" in script.source, script.step
        assert "catch(e){reportResult('ERROR:'+e);}" in script.source, script.step


def test_the_pairing_walk_uses_identity_and_never_a_coordinate():
    source = next(
        item.source for item in _contract().scripts
        if item.step is ProbeStep.ANTENNA_RECEIVERS
    )

    assert "getOwnerDevice" in source
    assert "getMacAddress" in source
    for coordinate in ("getXCoordinate", "getYCoordinate", ".x", ".y"):
        assert coordinate not in source


def test_the_probe_enumerates_nothing_beyond_its_targets():
    """One device in, one bounded read out; no workspace sweep."""
    contract = _contract()

    for script in contract.scripts:
        if script.step is ProbeStep.ANTENNA_RECEIVERS:
            # The link table has no per-device accessor, so the walk filters by
            # the transmitter owner instead and reads nothing else.
            assert "tn!==want" in script.source
            continue
        assert "getDeviceCount" not in script.source, script.step
        assert "getDeviceAt" not in script.source, script.step

    assert {item.runtime_device_name for item in contract.scripts} == {
        item.runtime_device_name for item in TARGETS
    }


def test_the_probe_is_not_wired_to_any_transport():
    """Preparing a contract must not be one refactor away from running it."""
    source_path = (
        "src/packet_tracer_mcp/infrastructure/execution/iot0_wireless_probe.py"
    )
    with open(source_path, encoding="utf-8") as handle:
        text = handle.read()

    assert "send_and_wait" not in text
    assert "PTCommandBridge" not in text
    assert "import requests" not in text
