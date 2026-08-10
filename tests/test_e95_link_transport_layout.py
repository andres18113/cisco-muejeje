from __future__ import annotations

import json
from pathlib import Path

from src.packet_tracer_mcp.infrastructure.execution.topology_observation import (
    LinkEndpoint,
    LinkExpectation,
    LinkObservationStatus,
    LayoutApplicationStatus,
    LayoutPoint,
    assess_layout_application,
    build_exact_link_readback_js,
    parse_exact_link_readback,
    verify_exact_link_convergence,
)
from src.packet_tracer_mcp.infrastructure.execution.transport_health import (
    TransportHealth,
    TransportHealthState,
    TransportName,
    select_transport,
)


def _expectation() -> LinkExpectation:
    return LinkExpectation(
        endpoint_a=LinkEndpoint("R1", "GigabitEthernet0/0"),
        endpoint_b=LinkEndpoint("SW1", "GigabitEthernet0/1"),
    )


def _link_payload(*, exact: bool, reason: str) -> str:
    endpoints = [
        {"device": "R1", "port": "GigabitEthernet0/0"},
        {"device": "SW1", "port": "GigabitEthernet0/1"},
    ]
    return json.dumps({
        "exact": exact,
        "reason": reason,
        "both_ports_bound": exact,
        "same_link": exact,
        "observed_link_a": endpoints if exact else [],
        "observed_link_b": list(reversed(endpoints)) if exact else [],
    })


def test_exact_link_js_reads_both_links_and_serializes_every_endpoint():
    expectation = LinkExpectation(
        endpoint_a=LinkEndpoint("R1');globalThis.pwned=true;//", "Gi0/0"),
        endpoint_b=LinkEndpoint("SW1", "Gi0/1"),
    )

    script = build_exact_link_readback_js(expectation)

    assert json.dumps(expectation.endpoint_a.device) in script
    assert ".getLink()" in script
    assert ".getPort1()" in script
    assert ".getPort2()" in script
    assert ".getOwnerDevice().getName()" in script
    assert (
        "__o.same_link&&__matches(__o.observed_link_a)&&"
        "__matches(__o.observed_link_b)"
    ) in script


def test_one_sided_or_wrong_peer_never_counts_as_exact_link_evidence():
    observation = parse_exact_link_readback(json.dumps({
        "exact": False,
        "reason": "ENDPOINT_MISMATCH",
        "both_ports_bound": True,
        "same_link": False,
        "observed_link_a": [
            {"device": "R1", "port": "GigabitEthernet0/0"},
            {"device": "OTHER", "port": "GigabitEthernet0/1"},
        ],
        "observed_link_b": [],
    }))

    assert observation.exact is False
    assert observation.status is LinkObservationStatus.ENDPOINT_MISMATCH


def test_matching_endpoints_from_distinct_link_objects_are_not_exact():
    endpoints = [
        {"device": "R1", "port": "GigabitEthernet0/0"},
        {"device": "SW1", "port": "GigabitEthernet0/1"},
    ]

    observation = parse_exact_link_readback(json.dumps({
        "exact": True,
        "reason": "EXACT",
        "both_ports_bound": True,
        "same_link": False,
        "observed_link_a": endpoints,
        "observed_link_b": list(reversed(endpoints)),
    }))

    assert not observation.exact
    assert not observation.same_link
    assert observation.status is LinkObservationStatus.ENDPOINT_MISMATCH


def test_link_convergence_waits_for_exact_current_readback():
    replies = iter([
        _link_payload(exact=False, reason="NO_LINK"),
        _link_payload(exact=True, reason="EXACT"),
    ])
    seen: list[tuple[str, float]] = []

    def send(script: str, timeout: float) -> str:
        seen.append((script, timeout))
        return next(replies)

    result = verify_exact_link_convergence(
        send,
        _expectation(),
        timeout_seconds=1.0,
        poll_interval_seconds=0.01,
    )

    assert result.verified is True
    assert result.attempts == 2
    assert result.observation.status is LinkObservationStatus.EXACT
    assert len(seen) == 2


def test_link_convergence_rejects_an_exact_flag_for_the_wrong_peer_pair():
    wrong = json.dumps({
        "exact": True,
        "reason": "EXACT",
        "both_ports_bound": True,
        "same_link": True,
        "observed_link_a": [
            {"device": "R1", "port": "GigabitEthernet0/0"},
            {"device": "WRONG", "port": "GigabitEthernet0/1"},
        ],
        "observed_link_b": [
            {"device": "WRONG", "port": "GigabitEthernet0/1"},
            {"device": "R1", "port": "GigabitEthernet0/0"},
        ],
    })
    now = [0.0]

    result = verify_exact_link_convergence(
        lambda _script, _timeout: wrong,
        _expectation(),
        timeout_seconds=0.01,
        clock=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert result.verified is False
    assert result.observation.status is LinkObservationStatus.ENDPOINT_MISMATCH


def test_link_convergence_has_a_hard_deadline():
    now = [0.0]

    def clock() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    result = verify_exact_link_convergence(
        lambda _script, _timeout: _link_payload(exact=False, reason="NO_LINK"),
        _expectation(),
        timeout_seconds=0.05,
        poll_interval_seconds=0.02,
        clock=clock,
        sleeper=sleep,
    )

    assert result.verified is False
    assert result.elapsed_seconds <= 0.05
    assert result.attempts == 4
    assert result.observation.status is LinkObservationStatus.NO_LINK


def test_transport_health_separates_polling_from_command_roundtrip():
    polling = TransportHealth(
        transport=TransportName.HTTP,
        transport_up=True,
        polling=True,
        command_path_responsive=False,
        command_probe_attempted=False,
    )
    degraded = TransportHealth(
        transport=TransportName.HTTP,
        transport_up=True,
        polling=True,
        command_path_responsive=False,
        command_probe_attempted=True,
    )

    assert polling.state is TransportHealthState.POLLING
    assert polling.selectable is True
    assert degraded.state is TransportHealthState.DEGRADED
    assert degraded.selectable is False


def test_transport_health_distinguishes_local_transport_from_unresponsive():
    transport_only = TransportHealth(
        transport=TransportName.HTTP,
        transport_up=True,
        polling=False,
        command_path_responsive=False,
        command_probe_attempted=False,
    )
    absent = TransportHealth(
        transport=TransportName.FILE,
        transport_up=False,
        polling=False,
        command_path_responsive=False,
        command_probe_attempted=False,
    )

    assert transport_only.state is TransportHealthState.TRANSPORT_UP
    assert absent.state is TransportHealthState.UNRESPONSIVE


def test_transport_selection_declares_fallback_but_forbids_silent_replay():
    responsive_http = TransportHealth(
        transport=TransportName.HTTP,
        transport_up=True,
        polling=True,
        command_path_responsive=True,
    )
    responsive_file = TransportHealth(
        transport=TransportName.FILE,
        transport_up=True,
        polling=True,
        command_path_responsive=True,
    )

    selection = select_transport(responsive_http, responsive_file)

    assert selection.selected is TransportName.HTTP
    assert selection.fallback is TransportName.FILE
    assert selection.pinned_for_operation is True
    assert selection.silent_replay_allowed is False


def test_degraded_http_selects_file_explicitly():
    degraded_http = TransportHealth(
        transport=TransportName.HTTP,
        transport_up=True,
        polling=True,
        command_path_responsive=False,
    )
    responsive_file = TransportHealth(
        transport=TransportName.FILE,
        transport_up=True,
        polling=True,
        command_path_responsive=True,
    )

    selection = select_transport(degraded_http, responsive_file)

    assert selection.selected is TransportName.FILE
    assert "explicit fallback" in selection.reason


def test_layout_evidence_preserves_requested_ack_observation_and_tolerance():
    evidence = assess_layout_application(
        LayoutPoint(200, 300),
        acknowledged=True,
        observed=LayoutPoint(205, 292),
        tolerance=8,
    )

    assert evidence.status is LayoutApplicationStatus.OBSERVED
    assert evidence.drift is not None
    assert evidence.drift.x == 5
    assert evidence.drift.y == -8
    assert evidence.within_tolerance is True


def test_layout_drift_is_not_misreported_as_verified_position():
    evidence = assess_layout_application(
        LayoutPoint(200, 300),
        acknowledged=True,
        observed=LayoutPoint(220, 300),
        tolerance=8,
    )

    assert evidence.status is LayoutApplicationStatus.DRIFTED
    assert evidence.within_tolerance is False


def test_layout_without_ack_remains_requested_even_if_a_coordinate_is_visible():
    evidence = assess_layout_application(
        LayoutPoint(200, 300),
        acknowledged=False,
        observed=LayoutPoint(200, 300),
        tolerance=8,
    )

    assert evidence.status is LayoutApplicationStatus.REQUESTED
    assert evidence.acknowledged is False
    assert evidence.within_tolerance is None


def test_tool_registry_wires_exact_link_readback_and_pinned_transports():
    source = Path(
        "src/packet_tracer_mcp/adapters/mcp/tool_registry.py"
    ).read_text(encoding="utf-8")

    add_link = source[source.index("    def pt_add_link("):]
    add_link = add_link[:add_link.index("    # RAW JS EXECUTION")]
    deploy = source[source.index("    def pt_live_deploy("):]
    deploy = deploy[:deploy.index("    def _stale_client_message")]
    move = source[source.index("    def pt_move_device("):]
    move = move[:move.index("    def pt_delete_link(")]
    bridge_status = source[source.index("    def pt_bridge_status("):]
    bridge_status = bridge_status[:bridge_status.index("    def pt_verify_connectivity(")]
    capability_probe = source[source.index("    def pt_probe_capabilities("):]
    capability_probe = capability_probe[:capability_probe.index("    def pt_capability_report(")]
    assert "verify_exact_link_convergence(" in add_link
    assert "verify_exact_link_convergence(" in deploy
    assert "channel=operation_channel" in add_link
    assert "channel=operation_channel" in deploy
    assert "require_command_path=True" in add_link
    assert "require_command_path=True" in deploy
    assert "no se reejecutó por otro canal" in add_link
    assert "build_layout_observation_js(" in move
    assert "assess_layout_application(" in move
    assert "tolerance" in move
    assert "_transport_health_snapshot(" in bridge_status
    assert "format_transport_health(" in bridge_status
    assert "silent_replay_allowed=false" in bridge_status
    assert "_run_on_pinned_transport" in capability_probe
    assert "operation_channel=operation_channel" in capability_probe
    assert "require_command_path=True" in capability_probe
    assert deploy.index('if plan.hash_schema_version == "2":') < deploy.index(
        "script = generate_executable_script(plan)"
    )
    assert deploy.index("EnterprisePhysicalTopologyDeployer(") < deploy.index(
        "script = generate_executable_script(plan)"
    )
    assert "E5-E9 no fueron aplicados por esta operación física" in deploy


def test_explicit_channel_is_consumed_only_by_send_and_wait_helper():
    source = Path(
        "src/packet_tracer_mcp/adapters/mcp/tool_registry.py"
    ).read_text(encoding="utf-8")
    bridge_helper = source[source.index("    def _bridge_send_and_wait("):]
    bridge_helper = bridge_helper[:bridge_helper.index("    def _check_bridge(")]
    check_bridge = source[source.index("    def _check_bridge("):]
    check_bridge = check_bridge[:check_bridge.index("    def _capability_preflight(")]

    assert "ch = channel if channel is not None else _pick_channel()" in bridge_helper
    assert "ch = _pick_channel()" in check_bridge
    assert "channel if channel is not None" not in check_bridge
