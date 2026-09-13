"""`platform.module_descriptors`: what one model is described as carrying.

The second discovered capability, and the first that reads a *tree*. It asks
the factory descriptor of one device model for its root module and walks the
chassis under it — which is MJ-003 again: behaviour selected from what the
platform reports, not from a table in this repository.

**A descriptor is not installed hardware.** `getRootModule()` describes what a
model can accept; it instantiates nothing and says nothing about a device on a
workspace. The runtime `Module` surface is a different interface, and the two
are never mixed (MJ-014).

**The model is addressed by index**, never by DeviceType and never by name, so
neither a numeric Cisco enum nor a catalogue of somebody's models has to exist
for this to work (MJ-002, MJ-014). What answered is reported back.

**The `OBSERVED` branch is driven against a stub.** The stub answers with the
shapes this repository's own factory surveys recorded against `9.0.1.0858`, and
that is still a claim about our code: nothing here establishes that Packet
Tracer answers these calls from a Script Module at all — one carrying
`privileges: []` was denied their root, and one carrying `GET_NETWORK_INFO`
reached the root but was denied the first member, `getAvailableDeviceCount`
(the index-2 evidence is why the manifest now also declares
`CHANGE_NETWORK_INFO`) — so the capability's live state is `PENDING_TARGET`
(MJ-015, MJ-031).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.platform_stub import CHASSIS_MODELS, platform_stub
from tests.muejeje.support import SCRIPT_ENGINE

OPERATION = "platform.module_descriptors"

RESULT_FIELDS = {
    "resolution", "unavailable_reason", "factory_index", "available_count",
    "descriptor_present", "model", "device_type", "root_present", "nodes",
    "nodes_truncated", "depth_truncated",
}
NODE_FIELDS = {
    "index", "parent_index", "depth", "module_index", "model", "module_type",
    "hot_swappable", "slot_types", "slot_types_truncated", "module_count",
    "children_truncated",
}

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(**args) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-modules", "op": OPERATION, "args": args,
    })


def _observed(models: str = CHASSIS_MODELS, **args) -> dict:
    args.setdefault("factory_index", 0)
    return dispatch_v6(_request(**args), prelude=platform_stub(models))["result"]


# ---------------------------------------------------------------------------
# Structural: the operation sits behind the adapters, and never beside them.
# ---------------------------------------------------------------------------

def test_the_operation_names_no_platform_symbol_of_its_own():
    """Operation -> adapter -> boundary -> platform, never a shortcut (MJ-019)."""
    body = (SCRIPT_ENGINE / "170_platform_modules.js").read_text(encoding="utf-8")

    assert "muejejeAdapterModuleDescriptors(" in body
    assert "ipc" not in body, "only the declared boundary reaches the platform"
    assert "muejejeAdapterCall" not in body
    assert "getRootModule" not in body


def test_the_operation_declares_its_own_argument_rules():
    """The dispatcher decides which names exist; the operation, what they mean."""
    body = (SCRIPT_ENGINE / "170_platform_modules.js").read_text(encoding="utf-8")
    dispatcher = (SCRIPT_ENGINE / "210_dispatcher_v6.js").read_text(encoding="utf-8")

    assert "MUEJEJE_PLATFORM_MODULE_ARGS = {" in body
    assert "MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX" in body
    assert "MUEJEJE_PLATFORM_MODULE_ARGS" in dispatcher
    assert "EXACT_INTEGER_MAX" not in dispatcher, (
        "the dispatcher holds no platform bound"
    )


# ---------------------------------------------------------------------------
# Executable: one shape, whether the platform answered or not.
# ---------------------------------------------------------------------------

@requires_node
def test_the_result_shape_is_the_same_whether_the_platform_answered():
    absent = dispatch_v6(_request(factory_index=0))["result"]

    assert set(absent) == set(_observed()) == RESULT_FIELDS
    assert absent["resolution"] == "UNAVAILABLE"
    assert absent["unavailable_reason"] == "PLATFORM_ABSENT"
    assert absent["nodes"] == []


@requires_node
def test_a_chassis_is_reported_node_by_node_with_its_own_identity():
    """The tree the recorded survey found, read back through the adapter."""
    result = _observed()

    assert result["resolution"] == "OBSERVED"
    assert result["unavailable_reason"] is None
    assert result["available_count"] == 2
    assert result["descriptor_present"] is True
    assert result["root_present"] is True
    assert result["model"] == "AccessPoint-PT"
    assert result["device_type"] == 7
    assert [node["model"] for node in result["nodes"]] == [
        "", "PT-REPEATER-NM-1CFE", "",
    ]
    assert all(set(node) == NODE_FIELDS for node in result["nodes"])


@requires_node
def test_every_node_says_where_in_the_chassis_it_was_read():
    """Parent, depth and module index, so a flat list still describes a tree.

    Reported flat on purpose: a nested answer has a depth a consumer cannot
    bound in advance, and each level would be a published shape of its own.

    `module_index` is the argument `getModuleAt` was called with, and is
    deliberately not called a slot: the descriptor's slot enumeration is a
    different one, and nothing observed here says the two correspond (MJ-015).
    """
    nodes = _observed()["nodes"]

    assert [node["index"] for node in nodes] == [0, 1, 2]
    assert [node["parent_index"] for node in nodes] == [None, 0, 0]
    assert [node["depth"] for node in nodes] == [0, 1, 1]
    assert [node["module_index"] for node in nodes] == [None, 0, 1]


@requires_node
def test_the_numbers_come_back_from_the_platform_untranslated():
    """MJ-014: slot and module types are Packet Tracer's own numbers.

    Naming them is a consumer's job, against Cisco's reference. The runtime
    reports what it was told, and asks for a model by index rather than by a
    DeviceType it would have to carry a table to name.
    """
    nodes = _observed()["nodes"]

    assert nodes[0]["slot_types"] == [6, 18]
    assert [node["module_type"] for node in nodes] == [18, 6, 18]
    assert [node["hot_swappable"] for node in nodes] == [False, False, False]
    assert [node["module_count"] for node in nodes] == [2, 0, 0]


@requires_node
def test_a_missing_module_inside_the_reported_count_is_unusable():
    """`null` from `getModuleAt` is not read as "this position is empty".

    That semantic was published once and withdrawn: nothing this repository has
    observed on `9.0.1.0858` says a null inside `0..getModuleCount()-1` means an
    empty bay, and inventing the meaning would state a fact about Packet
    Tracer's model that nobody measured. A missing module inside a count the
    platform itself reported is an answer that cannot be attributed — exactly
    what a missing descriptor inside the device count already is (MJ-015).
    """
    models = (
        "[{model: 'half', type: 1, supported: true, module_types: [], root:"
        " {model: 'root', module_type: 18, hot_swappable: false,"
        " slot_types: [1, 1], modules: [null,"
        " {model: 'card', module_type: 4, hot_swappable: true,"
        " slot_types: [], modules: []}]}}]"
    )
    result = _observed(models)

    assert result["resolution"] == "UNAVAILABLE"
    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
    assert result["nodes"] == []


@requires_node
def test_a_model_with_no_root_module_is_observed_rather_than_unreadable():
    """`getRootModule()` answering nothing is what the platform said."""
    result = _observed(factory_index=1)

    assert result["resolution"] == "OBSERVED"
    assert result["descriptor_present"] is True
    assert result["model"] == "bare"
    assert result["root_present"] is False
    assert result["nodes"] == []


@requires_node
def test_an_index_past_the_end_is_an_answer_not_an_unreadable_platform():
    """The factory said how many models it offers, and offers none there.

    Reporting that as an unavailable reading would send a consumer looking for
    a platform fault that nothing had.
    """
    result = _observed(factory_index=9)

    assert result["resolution"] == "OBSERVED"
    assert result["available_count"] == 2
    assert result["factory_index"] == 9
    assert result["descriptor_present"] is False
    assert result["model"] is None
    assert result["nodes"] == []


@requires_node
@pytest.mark.parametrize("args", [
    {"factory_index": -1}, {"factory_index": 9007199254740992},
    {"factory_index": "0"}, {"factory_index": 1.5}, {},
    {"factory_index": 0, "model": "2960-24TT"}, {"device_index": 0},
])
def test_an_argument_outside_its_declared_rule_is_refused(args: dict):
    response = dispatch_v6(_request(**args))

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGS"


@requires_node
def test_the_operation_reaches_no_verdict_about_what_it_read():
    reported = json.dumps(_observed())

    for verdict in ("VERIFIED", "QUALIFIED", "ATTESTED", "PASS", "SUPPORTED_BY"):
        assert verdict not in reported, verdict


@requires_node
def test_the_operation_is_read_only_in_the_catalogue_it_publishes():
    catalogue = dispatch_v6(_request(), report="muejejeV6OperationCatalog()")
    entry = next(item for item in catalogue if item["op"] == OPERATION)

    assert entry["read_only"] is True
