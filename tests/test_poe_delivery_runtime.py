from __future__ import annotations

import json

import pytest

from src.packet_tracer_mcp.infrastructure.execution.poe_delivery_runtime import (
    PacketTracerPoEDeliveryFixtureRuntime,
)


class RecordingTransport:
    def __init__(self, replies: list[str | None]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, float]] = []

    def __call__(self, script: str, timeout: float) -> str | None:
        self.calls.append((script, timeout))
        if not self.replies:
            raise AssertionError("unexpected Packet Tracer transport call")
        return self.replies.pop(0)


def _device_payload(name: str, model: str, ports: list[str]) -> str:
    return json.dumps({
        "found": True,
        "creation_attempted": True,
        "name": name,
        "model": model,
        "ports": ports,
        "missing_ports": [],
    })


def _endpoint(name: str, model: str, port: str) -> dict[str, str]:
    return {"device_name": name, "device_model": model, "port": port}


def _exact_link_readback_payload(
    switch_name: str,
    switch_model: str,
    switch_port: str,
    endpoint_name: str,
    endpoint_model: str,
    endpoint_port: str,
) -> str:
    ends = [
        {"device": switch_name, "model": switch_model, "port": switch_port},
        {"device": endpoint_name, "model": endpoint_model, "port": endpoint_port},
    ]
    return json.dumps({
        "exact": True,
        "reason": "EXACT",
        "port_a_bound": True,
        "port_b_bound": True,
        "both_ports_bound": True,
        "same_link": True,
        "runtime_link_identifier_a": "link-uuid",
        "runtime_link_identifier_b": "link-uuid",
        "observed_link_a": ends,
        "observed_link_b": list(reversed(ends)),
    })


def test_create_device_keeps_adversarial_fields_as_json_literals_and_never_reads_power():
    name = '__POE_";throw new Error("name")//\nENDPOINT'
    model = '7960";throw new Error("model")//'
    port = 'Switch";throw new Error("port")//'
    transport = RecordingTransport([_device_payload(name, model, [port])])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT build exact")

    observed = runtime.create_device(model, name, (port,))

    script = transport.calls[0][0]
    assert observed.name == name
    assert observed.model == model
    assert observed.observed_ports == [port]
    assert json.dumps(name, ensure_ascii=False) in script
    assert json.dumps(model, ensure_ascii=False) in script
    assert json.dumps(port, ensure_ascii=False) in script
    assert "\n" not in script
    assert ".getPower(" not in script
    assert ".isPowerOn(" not in script


def test_create_device_returns_exact_candidate_and_comparison_identities():
    transport = RecordingTransport([
        _device_payload("__POE_CANDIDATE", "3560-24PS", ["FastEthernet0/1"]),
        _device_payload("__POE_COMPARISON", "2960-24TT", ["FastEthernet0/2"]),
    ])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT build exact")

    candidate = runtime.create_device(
        "3560-24PS", "__POE_CANDIDATE", ("FastEthernet0/1",),
    )
    comparison = runtime.create_device(
        "2960-24TT", "__POE_COMPARISON", ("FastEthernet0/2",),
    )

    assert candidate.model_dump() == {
        "name": "__POE_CANDIDATE",
        "model": "3560-24PS",
        "observed_ports": ["FastEthernet0/1"],
    }
    assert comparison.model_dump() == {
        "name": "__POE_COMPARISON",
        "model": "2960-24TT",
        "observed_ports": ["FastEthernet0/2"],
    }
    assert all(".getPower(" not in script for script, _ in transport.calls)
    assert all(".isPowerOn(" not in script for script, _ in transport.calls)


def test_create_link_returns_both_exact_observed_endpoint_views():
    switch_name = '__POE_SWITCH_";/*'
    endpoint_name = '__POE_PHONE_";/*'
    switch_port = 'FastEthernet0/1";/*'
    endpoint_port = 'Switch";/*'
    transport = RecordingTransport([
        _device_payload(switch_name, "3560-24PS", [switch_port]),
        _device_payload(endpoint_name, "7960", [endpoint_port]),
        json.dumps({"requested": True}),
        _exact_link_readback_payload(
            switch_name, "3560-24PS", switch_port,
            endpoint_name, "7960", endpoint_port,
        ),
    ])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT build exact")
    switch = runtime.create_device("3560-24PS", switch_name, (switch_port,))
    endpoint = runtime.create_device("7960", endpoint_name, (endpoint_port,))

    observed = runtime.create_link(switch, switch_port, endpoint, endpoint_port)

    mutation_script = transport.calls[2][0]
    readback_script = transport.calls[3][0]
    assert observed.first.model_dump() == _endpoint(
        switch_name, "3560-24PS", switch_port,
    )
    assert observed.second.model_dump() == _endpoint(
        endpoint_name, "7960", endpoint_port,
    )
    for value in (
        switch_name, "3560-24PS", switch_port,
        endpoint_name, "7960", endpoint_port,
    ):
        assert json.dumps(value, ensure_ascii=False) in mutation_script
    assert "lwAddLink(" in mutation_script
    assert ".getPort1()" not in mutation_script
    assert ".getPort2()" not in mutation_script
    assert ".getOwnerDevice()" not in mutation_script
    assert ".getPort1()" in readback_script
    assert ".getPort2()" in readback_script
    assert ".getOwnerDevice()" in readback_script
    assert "getObjectUuid" in readback_script
    assert "lwAddLink(" not in readback_script
    assert "\n" not in mutation_script
    assert mutation_script.count("{") == mutation_script.count("}")
    assert all(".getPower(" not in script for script, _ in transport.calls)
    assert all(".isPowerOn(" not in script for script, _ in transport.calls)


def test_create_link_observes_bilateral_convergence_after_mutation_without_replay():
    switch_name = "__POE_SWITCH"
    endpoint_name = "__POE_PHONE"
    switch_port = "FastEthernet0/1"
    endpoint_port = "Switch"
    transport = RecordingTransport([
        _device_payload(switch_name, "3560-24PS", [switch_port]),
        _device_payload(endpoint_name, "7960", [endpoint_port]),
        json.dumps({"requested": True}),
        json.dumps({
            "exact": False,
            "reason": "NO_LINK",
            "port_a_bound": False,
            "port_b_bound": False,
            "both_ports_bound": False,
            "same_link": False,
            "observed_link_a": [],
            "observed_link_b": [],
        }),
        _exact_link_readback_payload(
            switch_name, "3560-24PS", switch_port,
            endpoint_name, "7960", endpoint_port,
        ),
    ])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT build exact")
    switch = runtime.create_device(
        "3560-24PS", switch_name, (switch_port,),
    )
    endpoint = runtime.create_device("7960", endpoint_name, (endpoint_port,))

    observed = runtime.create_link(
        switch, switch_port, endpoint, endpoint_port,
    )

    assert observed.first.model_dump() == _endpoint(
        switch_name, "3560-24PS", switch_port,
    )
    assert observed.second.model_dump() == _endpoint(
        endpoint_name, "7960", endpoint_port,
    )
    mutation_scripts = [
        script for script, _ in transport.calls if "lwAddLink(" in script
    ]
    assert len(mutation_scripts) == 1
    readback_scripts = [script for script, _ in transport.calls[3:]]
    assert len(readback_scripts) == 2
    assert all("lwAddLink(" not in script for script in readback_scripts)
    assert all("getObjectUuid" in script for script in readback_scripts)


def test_create_link_requires_models_from_the_same_bilateral_readback_episode():
    switch_name = "__POE_SWITCH"
    endpoint_name = "__POE_PHONE"
    switch_port = "FastEthernet0/1"
    endpoint_port = "Switch"
    transport = RecordingTransport([
        _device_payload(switch_name, "3560-24PS", [switch_port]),
        _device_payload(endpoint_name, "7960", [endpoint_port]),
        json.dumps({"requested": True}),
        _exact_link_readback_payload(
            switch_name, "2960-24TT", switch_port,
            endpoint_name, "7960", endpoint_port,
        ),
        _exact_link_readback_payload(
            switch_name, "3560-24PS", switch_port,
            endpoint_name, "7960", endpoint_port,
        ),
    ])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT build exact")
    switch = runtime.create_device(
        "3560-24PS", switch_name, (switch_port,),
    )
    endpoint = runtime.create_device("7960", endpoint_name, (endpoint_port,))

    observed = runtime.create_link(
        switch, switch_port, endpoint, endpoint_port,
    )

    assert observed.first.model_dump() == _endpoint(
        switch_name, "3560-24PS", switch_port,
    )
    assert observed.second.model_dump() == _endpoint(
        endpoint_name, "7960", endpoint_port,
    )
    mutation_scripts = [
        script for script, _ in transport.calls if "lwAddLink(" in script
    ]
    assert len(mutation_scripts) == 1
    assert len(transport.calls[3:]) == 2


@pytest.mark.parametrize(
    "reply",
    [
        None,
        "not-json",
        "[]",
        json.dumps({"found": False}),
        json.dumps({
            "found": True,
            "name": "__POE_PHONE",
            "model": "7960",
            "ports": [],
            "missing_ports": ["Switch"],
        }),
        json.dumps({
            "found": True,
            "name": 7,
            "model": "7960",
            "ports": ["Switch"],
            "missing_ports": [],
        }),
    ],
)
def test_create_device_fails_closed_on_incomplete_bridge_payload(reply):
    runtime = PacketTracerPoEDeliveryFixtureRuntime(
        RecordingTransport([reply]), "PT build exact",
    )

    with pytest.raises((RuntimeError, TimeoutError)):
        runtime.create_device("7960", "__POE_PHONE", ("Switch",))


@pytest.mark.parametrize(
    "reply",
    [
        None,
        "not-json",
        "[]",
        json.dumps({"requested": False}),
        json.dumps({"linked": True}),
        json.dumps({"requested": False, "error": "mutation rejected"}),
    ],
)
def test_create_link_fails_closed_on_incomplete_mutation_acknowledgement(reply):
    transport = RecordingTransport([
        _device_payload("__POE_SWITCH", "3560-24PS", ["FastEthernet0/1"]),
        _device_payload("__POE_PHONE", "7960", ["Switch"]),
        reply,
    ])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT build exact")
    switch = runtime.create_device(
        "3560-24PS", "__POE_SWITCH", ("FastEthernet0/1",),
    )
    endpoint = runtime.create_device("7960", "__POE_PHONE", ("Switch",))

    with pytest.raises((RuntimeError, TimeoutError)):
        runtime.create_link(switch, "FastEthernet0/1", endpoint, "Switch")


def test_delete_is_confined_to_recorded_attempts_and_preserves_cleanup_order():
    names = [
        "__POE_CANDIDATE_SWITCH",
        "__POE_COMPARISON_SWITCH",
        "__POE_CANDIDATE_ENDPOINT",
        "__POE_COMPARISON_ENDPOINT",
    ]
    transport = RecordingTransport([
        *[_device_payload(name, "7960", ["Switch"]) for name in names],
        *[json.dumps({"deleted": True}) for _ in names],
    ])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT build exact")
    for name in names:
        runtime.create_device("7960", name, ("Switch",))

    calls_before_unrecorded = len(transport.calls)
    assert runtime.delete_device("USER_DEVICE") is False
    assert len(transport.calls) == calls_before_unrecorded

    cleanup_order = [names[2], names[3], names[0], names[1]]
    assert [runtime.delete_device(name) for name in cleanup_order] == [True] * 4

    delete_scripts = [script for script, _ in transport.calls if "removeDevice" in script]
    assert len(delete_scripts) == 4
    for script, expected_name in zip(delete_scripts, cleanup_order, strict=True):
        assert json.dumps(expected_name, ensure_ascii=False) in script
        assert "USER_DEVICE" not in script


def test_explicit_duplicate_rejection_never_authorizes_deleting_preexisting_name():
    duplicate_name = "USER_PREEXISTING_DEVICE"
    transport = RecordingTransport([json.dumps({
        "found": False,
        "creation_attempted": False,
        "error": "duplicate fixture name",
    })])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT build exact")

    with pytest.raises(RuntimeError, match="duplicate fixture name"):
        runtime.create_device("7960", duplicate_name, ("Switch",))

    assert runtime.delete_device(duplicate_name) is False
    assert len(transport.calls) == 1


def test_packet_tracer_build_and_inventory_lifecycle_delegate_to_probe_runtime():
    inventory = json.dumps({"items": [], "links": []})
    transport = RecordingTransport([inventory, inventory])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT 9.0.1.0858")

    initial = runtime.inventory_fingerprint()
    restored = runtime.wait_for_inventory_fingerprint(initial)

    assert runtime.packet_tracer_build() == "PT 9.0.1.0858"
    assert restored == initial
    assert len(transport.calls) == 2
    assert all("getDeviceCount()" in script for script, _ in transport.calls)
    assert all("getLinkCount()" in script for script, _ in transport.calls)
