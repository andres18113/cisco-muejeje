"""`platform.device_descriptors`: the first discovered capability.

It asks Packet Tracer which device models it offers and what module types each
one supports, through the one declared adapter. That is MJ-003 in code —
behaviour selected from what the platform reports rather than from a table in
this repository — and it is MJ-014's answer to a numeric enum mirror: every
number here comes back out of the platform untranslated.

The adapter's own boundary, and the readings it reports when the platform will
not answer, are `test_platform_adapter`. This module is the operation: its
result shape, what it reports from a well-formed answer, its window, and the
argument rules it declares.

**The `OBSERVED` branch is driven against a stub.** It establishes what our
operation does with a well-formed answer and **nothing** about `9.0.1.0858`.
No `.pts` has been built from these sources and nothing here has reached the
target, so this capability's live state is `PENDING_TARGET` (MJ-015, MJ-031).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.platform_stub import platform_stub
from tests.muejeje.support import SCRIPT_ENGINE

OPERATION = "platform.device_descriptors"

RESULT_FIELDS = {
    "resolution", "unavailable_reason", "available_count", "factory_offset",
    "limit",
    "descriptors", "window_truncated",
}
# `factory_index` is the index each model was read at, reported rather than
# counted off from `factory_offset`: it is the value a consumer sends back to ask
# about this model, and a reusable input a reader has to derive is one two
# readers will derive differently.
DESCRIPTOR_FIELDS = {
    "factory_index", "model", "device_type", "model_supported",
    "supported_module_types", "module_types_truncated",
}

THREE_MODELS = (
    "[{model: '2960-24TT', type: 1, supported: true, module_types: [18]},"
    " {model: '', type: 7, supported: false, module_types: [6, 18]},"
    " {model: '3650-24PS', type: 16, supported: true, module_types: [4, 18]}]"
)

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(**args) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-descriptors", "op": OPERATION, "args": args,
    })


def _observed(**args) -> dict:
    return dispatch_v6(_request(**args), prelude=platform_stub(THREE_MODELS))["result"]


# ---------------------------------------------------------------------------
# Structural: the operation sits behind the adapter, and never beside it.
# ---------------------------------------------------------------------------

def test_the_operation_names_no_platform_symbol_of_its_own():
    """Operation -> adapter -> platform, and never a shortcut (MJ-019)."""
    body = (SCRIPT_ENGINE / "platform_discovery.js").read_text(encoding="utf-8")

    assert "muejejeAdapterDeviceDescriptors(" in body
    assert "ipc" not in body, "only the declared adapter reaches the platform"
    assert "hardwareFactory" not in body


def test_the_operation_declares_its_own_argument_rules():
    """The dispatcher decides which names exist; the operation, what they mean.

    Both bounds come from the adapter's ceiling rather than from a second set
    of numbers written down beside it: two copies of a bound are two bounds,
    and the one a caller is held to would eventually not be the one the
    adapter honours.
    """
    body = (SCRIPT_ENGINE / "platform_discovery.js").read_text(encoding="utf-8")
    dispatcher = (SCRIPT_ENGINE / "dispatcher_v6.js").read_text(encoding="utf-8")

    assert "MUEJEJE_PLATFORM_DESCRIPTOR_ARGS = {" in body
    assert "MUEJEJE_PLATFORM_LIMITS.MAX_FACTORY_WINDOW" in body
    assert "MUEJEJE_PLATFORM_DESCRIPTOR_ARGS" in dispatcher
    assert "MAX_FACTORY_WINDOW" not in dispatcher, "the dispatcher holds no platform bound"


# ---------------------------------------------------------------------------
# Executable: one shape, whether the platform answered or not.
# ---------------------------------------------------------------------------

@requires_node
def test_the_result_shape_is_the_same_whether_the_platform_answered():
    """One shape, so a consumer's parser is total over both outcomes."""
    absent = dispatch_v6(_request())["result"]

    assert set(absent) == set(_observed()) == RESULT_FIELDS


@requires_node
def test_a_well_formed_answer_is_reported_model_by_model():
    result = _observed()

    assert result["resolution"] == "OBSERVED"
    assert result["unavailable_reason"] is None
    assert result["available_count"] == 3
    assert result["window_truncated"] is False
    assert [entry["model"] for entry in result["descriptors"]] == [
        "2960-24TT", "", "3650-24PS",
    ]
    assert all(set(entry) == DESCRIPTOR_FIELDS for entry in result["descriptors"])


@requires_node
def test_an_empty_model_is_a_real_answer_and_not_a_malformed_one():
    """On 9.0.1 a chassis root reports `model: ""`.

    Requiring a name discarded correct factory metadata once already, in the
    Python-side reader, and the same rule would discard it again here.
    """
    reported = _observed()["descriptors"][1]

    assert reported["model"] == ""
    assert reported["device_type"] == 7
    assert reported["model_supported"] is False


@requires_node
def test_the_reported_numbers_come_back_from_the_platform_untranslated():
    """MJ-014: the descriptor API is the authority, not a table of ours.

    Naming these numbers is the consumer's job, against Cisco's own reference.
    The runtime reports what it was told.
    """
    result = _observed()

    assert [entry["device_type"] for entry in result["descriptors"]] == [1, 7, 16]
    assert [
        entry["supported_module_types"] for entry in result["descriptors"]
    ] == [[18], [6, 18], [4, 18]]


@requires_node
def test_the_operation_reaches_no_verdict_about_what_it_read():
    """`resolution` says a reading was obtained, not that anything is proven.

    Python decides what an observation establishes, from outside the artifact
    (MJ-011), so no word in the answer may certify it.
    """
    reported = json.dumps(_observed())

    for verdict in ("VERIFIED", "QUALIFIED", "ATTESTED", "PASS", "SUPPORTED_BY"):
        assert verdict not in reported, verdict


# ---------------------------------------------------------------------------
# Executable: the window, and the bounds around it.
# ---------------------------------------------------------------------------

@requires_node
def test_the_window_is_reported_back_and_a_tail_is_marked_truncated():
    """An omitted tail stays visibly absent; it never reads as an absence."""
    result = _observed(factory_offset=0, limit=2)

    assert result["factory_offset"] == 0
    assert result["limit"] == 2
    assert result["available_count"] == 3
    assert result["window_truncated"] is True
    assert [entry["model"] for entry in result["descriptors"]] == ["2960-24TT", ""]


@requires_node
def test_an_offset_past_the_end_reports_the_count_and_no_descriptor():
    result = _observed(factory_offset=9)

    assert result["resolution"] == "OBSERVED"
    assert result["available_count"] == 3
    assert result["descriptors"] == []
    assert result["window_truncated"] is False


@requires_node
def test_a_factory_longer_than_any_window_is_paged_rather_than_capped():
    """The window bounds the work, and nothing caps how far a consumer pages.

    An earlier revision refused any offset past 4096 and any count past 65536,
    so a factory that long was unreadable rather than merely long. Neither
    number bounded work: reading model 59,990 costs what reading model 0 does.
    """
    result = dispatch_v6(
        _request(factory_offset=59990, limit=32),
        prelude=platform_stub(THREE_MODELS, count="60000", dense=True),
    )["result"]

    assert result["resolution"] == "OBSERVED"
    assert result["available_count"] == 60000
    assert [entry["factory_index"] for entry in result["descriptors"]] == list(
        range(59990, 60000)
    )
    assert result["window_truncated"] is False


@requires_node
def test_more_module_types_than_the_adapter_reads_are_marked_truncated():
    many = ", ".join(str(value) for value in range(80))
    result = dispatch_v6(
        _request(),
        prelude=platform_stub(
            f"[{{model: 'wide', type: 1, supported: true, module_types: [{many}]}}]"
        ),
    )["result"]
    descriptor = result["descriptors"][0]

    assert len(descriptor["supported_module_types"]) == 64
    assert descriptor["module_types_truncated"] is True


@requires_node
def test_both_arguments_are_optional_and_default_to_the_first_window():
    """A consumer discovering the platform has no count to page from yet."""
    result = _observed()

    assert result["factory_offset"] == 0
    assert result["limit"] == 32


@requires_node
@pytest.mark.parametrize("args", [
    {"limit": 0}, {"limit": 33}, {"factory_offset": -1},
    {"factory_offset": 9007199254740992}, {"offset": 0},
    {"limit": "8"}, {"limit": 1.5}, {"page": 1},
])
def test_an_argument_outside_its_declared_rule_is_refused(args: dict):
    """The rules the operation declares, driven through the dispatcher."""
    response = dispatch_v6(_request(**args))

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGS"


@requires_node
def test_the_operation_is_read_only_in_the_catalogue_it_publishes():
    catalogue = dispatch_v6(_request(), report="muejejeV6OperationCatalog()")
    entry = next(item for item in catalogue if item["op"] == OPERATION)

    assert entry["read_only"] is True
