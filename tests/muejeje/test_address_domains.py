"""Two address domains, and a position from one never lands in the other.

A model's position in the hardware factory and a device's position on the
workspace are numbers of the same shape in two different enumerations of two
different subjects. An earlier contract called both `device_index`, and both
window starts `offset`, so a position read off the workspace and relayed by the
name it was published under was admitted as a factory position and answered
about whatever model stood there. Nothing refused it, because nothing could
tell the two apart (MJ-029, MJ-031).

So every argument and field that carries an address says which domain it is
in, and this module holds that from three sides:

* **Declared.** No operation admits an address argument that does not name its
  domain, and no reading publishes one.
* **Refused.** An address sent to an operation of the other domain is
  `INVALID_ARGS`, and so is either retired name.
* **Required where it selects a subject.** An operation about one model or one
  device refuses a request that names none, and reads nothing — it never answers
  for position 0 on the caller's behalf. A window's start keeps its default,
  because the origin of an enumeration *is* the question a first window asks.

Nothing here is a claim about Packet Tracer; it is the contract this artifact
publishes, driven under Node (MJ-015).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.platform_stub import (
    CHASSIS_MODELS,
    PORT_DEVICES,
    platform_stub,
)

# The domains an address in each namespace may belong to. A port position is
# inside one workspace device, so it lives in that namespace under its own name.
DOMAINS = {"platform": ("factory",), "network": ("workspace", "port")}
# A field or argument name that carries a position.
ADDRESS_NAME = re.compile(r"(?:^|_)(?:index|offset)$")
# Positions *inside* one reading rather than addresses into an enumeration: a
# chassis node's place in the flat list, its parent's place, and the argument
# `getModuleAt` was called with. No operation admits any of them back.
READING_LOCAL_POSITIONS = {
    "nodes[].index", "nodes[].parent_index", "nodes[].module_index",
}
# Every operation about one subject: the argument that selects it, and the
# other arguments it needs to be admitted at all.
SINGLE_SUBJECT = {
    "platform.module_descriptors": ("factory_index", {}),
    "platform.module_type_support": ("factory_index", {"module_type": 6}),
    "network.device_identity": ("workspace_index", {}),
    "network.device_ports": ("workspace_index", {}),
}
# Every window over an enumeration: the argument its start is, and the list.
WINDOWS = {
    "platform.device_descriptors": ("factory_offset", "descriptors"),
    "network.device_inventory": ("workspace_offset", "devices"),
}
READINGS = sorted(set(SINGLE_SUBJECT) | set(WINDOWS))

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(op: str, args: dict) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-domains", "op": op, "args": args,
    })


def _stub() -> str:
    return platform_stub(CHASSIS_MODELS, devices=PORT_DEVICES)


def _admitted_args(op: str) -> dict:
    """The smallest arguments `op` admits, selecting position 0 where it must."""
    if op not in SINGLE_SUBJECT:
        return {}
    selector, others = SINGLE_SUBJECT[op]
    return {selector: 0, **others}


def _prefixes(op: str) -> tuple[str, ...]:
    return tuple(f"{domain}_" for domain in DOMAINS[op.split(".")[0]])


def published_paths(result: dict) -> set[str]:
    """Every field path in a result; `name[]` marks the objects inside a list."""
    paths: set[str] = set()

    def visit(node: object, prefix: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                path = f"{prefix}.{key}" if prefix else key
                paths.add(path)
                visit(value, path)
        elif isinstance(node, list):
            for item in node:
                visit(item, f"{prefix}[]")

    visit(result, "")
    return paths


@requires_node
def test_every_address_argument_names_its_domain():
    declared = dispatch_v6(
        _request("runtime.identify", {}),
        report=(
            "(function () { var table = muejejeV6OperationTable(), names = {};"
            " for (var op in table) { names[op] = Object.keys(table[op].args); }"
            " return names; }())"
        ),
    )

    for op, names in declared.items():
        for name in names:
            if ADDRESS_NAME.search(name):
                assert name.startswith(_prefixes(op)), (op, name)


@requires_node
@pytest.mark.parametrize("op", READINGS)
def test_every_published_address_names_its_domain(op: str):
    result = dispatch_v6(_request(op, _admitted_args(op)), prelude=_stub())["result"]

    assert result["resolution"] == "OBSERVED"
    for path in published_paths(result) - READING_LOCAL_POSITIONS:
        name = path.rsplit(".", 1)[-1]
        if ADDRESS_NAME.search(name):
            assert name.startswith(_prefixes(op)), (op, path)


@requires_node
@pytest.mark.parametrize(("op", "foreign"), [
    ("platform.module_descriptors", {"workspace_index": 0}),
    ("platform.module_type_support", {"workspace_index": 0, "module_type": 6}),
    ("platform.device_descriptors", {"workspace_offset": 0}),
    ("network.device_identity", {"factory_index": 0}),
    ("network.device_inventory", {"factory_offset": 0}),
    ("network.device_ports", {"factory_index": 0}),
])
def test_an_address_from_the_other_domain_is_refused(op: str, foreign: dict):
    """Relayed by the name it was published under, it reaches only its own domain."""
    response = dispatch_v6(_request(op, foreign), prelude=_stub())

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGS"


@requires_node
@pytest.mark.parametrize("op", READINGS)
@pytest.mark.parametrize("retired", ["device_index", "offset"])
def test_the_names_that_crossed_domains_are_refused_everywhere(op: str, retired: str):
    response = dispatch_v6(_request(op, {**_admitted_args(op), retired: 0}))

    assert response["error"]["code"] == "INVALID_ARGS"


@requires_node
@pytest.mark.parametrize("op", sorted(SINGLE_SUBJECT))
def test_an_operation_about_one_subject_refuses_a_request_naming_none(op: str):
    """Refused, and nothing read: never an answer about position 0."""
    observed = dispatch_v6(
        _request(op, SINGLE_SUBJECT[op][1]), prelude=_stub(),
        report="{response: JSON.parse(mcpDispatchV6(REQUEST)), calls: CALLS}",
    )

    assert observed["response"]["ok"] is False
    assert observed["response"]["error"]["code"] == "INVALID_ARGS"
    assert observed["response"]["result"] is None
    assert observed["calls"] == [], "a refused request reached the platform"


@requires_node
@pytest.mark.parametrize("op", sorted(WINDOWS))
def test_a_window_still_starts_at_the_origin_of_its_enumeration(op: str):
    start, listed = WINDOWS[op]
    result = dispatch_v6(_request(op, {}), prelude=_stub())["result"]

    assert result["resolution"] == "OBSERVED"
    assert result[start] == 0
    assert result[listed], "a first window over a non-empty enumeration lists something"


def test_the_address_readers_can_tell_an_address_from_its_neighbours():
    """Guards the gates above from passing on names they never inspect."""
    assert ADDRESS_NAME.search("workspace_index")
    assert ADDRESS_NAME.search("offset") and ADDRESS_NAME.search("index")
    assert not ADDRESS_NAME.search("module_type")
    assert not ADDRESS_NAME.search("indexes")
    assert published_paths({"devices": [{"index": 0}]}) == {
        "devices", "devices[].index",
    }
    assert "devices[].index" not in READING_LOCAL_POSITIONS
