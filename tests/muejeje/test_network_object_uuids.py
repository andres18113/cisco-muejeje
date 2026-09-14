"""The object UUID the device readings now carry, and what it may not become.

`network.device_inventory`, `network.device_identity` and `network.device_ports`
each gained the object UUID Packet Tracer reports for a device, and the ports
reading one for each port — beside every field they already published (MJ-030).
It is what a link's end reports too, which is the whole reason to read it. Three
claims, driven over the three readings:

* **Reported as answered.** A bounded string, published unchanged — never
  parsed, required to take a form, or derived from a name or a position.
* **All-or-nothing, like every other fact.** A device or a port that does not
  offer the getter is `PLATFORM_MEMBER_ABSENT` at it, an answer that is not a
  bounded string is `PLATFORM_ANSWER_UNUSABLE` there, and nothing else the
  reading read is published beside the failure.
* **The platform's answer, not an identity vouched for.** What it means across a
  restart, a save or a re-creation has not been observed, and no reading here
  claims more than that the platform said it (MJ-011, MJ-015).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import declared_platform_bound
from tests.muejeje.platform_stub import CHASSIS_MODELS, linked_stub, platform_stub

UUID_BOUND = declared_platform_bound("MAX_OBJECT_UUID_CHARS")
DEVICE_READINGS = {
    "network.device_inventory": {},
    "network.device_identity": {"workspace_index": 0},
    "network.device_ports": {"workspace_index": 0},
}

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _result(prelude: str, op: str) -> dict:
    request = json.dumps({
        "v": 6, "operation_rid": "rid-uuid", "op": op, "args": DEVICE_READINGS[op],
    })
    return dispatch_v6(request, prelude=prelude)["result"]


def _device_uuid(op: str, result: dict) -> str:
    if op == "network.device_inventory":
        return result["devices"][0]["object_uuid"]
    return result["object_uuid"]


def _one_device(uuid_field: str) -> str:
    """One device answering every getter the three readings ask but its UUID,
    which is `uuid_field` — written as it would sit in the spec, or omitted."""
    return platform_stub(CHASSIS_MODELS, devices=(
        f"[{{name: 'd', model: 'm', device_type: 1{uuid_field},"
        " ports: [{name: 'p', object_uuid: 'port-uuid'}]}]"
    ))


@requires_node
@pytest.mark.parametrize("op", sorted(DEVICE_READINGS))
def test_every_device_reading_reports_the_uuid_it_was_answered(op: str):
    result = _result(linked_stub(), op)

    assert result["resolution"] == "OBSERVED"
    assert _device_uuid(op, result) == "device-uuid-a"


@requires_node
def test_the_ports_reading_reports_each_ports_uuid_beside_its_name():
    result = _result(linked_stub(), "network.device_ports")

    assert [(port["name"], port["object_uuid"]) for port in result["ports"]] == [
        ("a-0", "port-uuid-a0"), ("a-1", "port-uuid-a1"),
    ]


@requires_node
@pytest.mark.parametrize("op", sorted(DEVICE_READINGS))
@pytest.mark.parametrize(("literal", "expected"), [
    (f"'x'.repeat({UUID_BOUND})", "x" * UUID_BOUND),
    ("''", ""),
    ("'not-a-uuid-shape'", "not-a-uuid-shape"),
], ids=["at-its-bound", "empty", "any-form"])
def test_a_bounded_string_is_an_answer_whatever_its_form(op: str, literal: str, expected: str):
    """Bound, not wall; and nothing documents a UUID's form, so none is required."""
    result = _result(_one_device(f", object_uuid: {literal}"), op)

    assert result["resolution"] == "OBSERVED"
    assert _device_uuid(op, result) == expected


@requires_node
@pytest.mark.parametrize("op", sorted(DEVICE_READINGS))
@pytest.mark.parametrize(("uuid_field", "reason"), [
    ("", "PLATFORM_MEMBER_ABSENT"),
    (", object_uuid: 7", "PLATFORM_ANSWER_UNUSABLE"),
    (", object_uuid: null", "PLATFORM_ANSWER_UNUSABLE"),
    (f", object_uuid: 'x'.repeat({UUID_BOUND + 1})", "PLATFORM_ANSWER_UNUSABLE"),
], ids=["no-getter", "number", "null", "past-its-bound"])
def test_a_uuid_that_cannot_be_attributed_takes_the_whole_reading_with_it(
    op: str, uuid_field: str, reason: str,
):
    result = _result(_one_device(uuid_field), op)

    assert (result["resolution"], result["unavailable_reason"]) == ("UNAVAILABLE", reason)
    assert (result["unavailable_member"], result["unavailable_argument"]) == (
        "Device.getObjectUuid", None,
    )
    for listed in ("devices", "ports"):
        assert result.get(listed, []) == [], listed
    for fact in ("name", "model", "object_uuid"):
        assert result.get(fact) is None, fact


@requires_node
def test_a_port_that_offers_no_uuid_makes_the_ports_reading_unavailable():
    prelude = platform_stub(CHASSIS_MODELS, devices=(
        "[{name: 'd', model: 'm', object_uuid: 'u', ports: [{name: 'p'}]}]"
    ))
    result = _result(prelude, "network.device_ports")

    assert (result["unavailable_reason"], result["unavailable_member"]) == (
        "PLATFORM_MEMBER_ABSENT", "Port.getObjectUuid",
    )
    assert result["ports"] == [] and result["object_uuid"] is None
