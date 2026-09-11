"""`network.device_identity`: one device, one reading, and nothing joined.

The operation answers what the platform says the device at one workspace
position *is* — its name, its model, its DeviceType — and everything it reports
comes from a single observation of a single device.

Three claims this module is responsible for, and they are the three a reader is
most likely to assume rather than check:

* **One shape, whether the platform answered or not.** The five resolutions are
  the same five every other reading has (MJ-031), and an identity field is
  filled in only once it was read. A reading that half-answered would look like
  a fact about the platform rather than about our inability to read it.
* **The index is a position in *this* reading, not an identity.** It is where
  the platform handed the device over, in this observation. Nothing here claims
  it is stable across readings, and the identity facts are reported beside it
  precisely so a consumer can tell what actually answered.
* **Nothing is correlated to the hardware factory.** Not by index, not by name,
  not by model string, not by assumption. A workspace index and a factory index
  are different enumerations of different subjects, and equal names do not make
  two readings the same device.

What the closure between this operation and `network.device_inventory` has to
satisfy is `test_relay_closure`: every index the inventory publishes is one this
operation admits.

Everything here runs against a stub under Node. It establishes what our adapter
and operation do, and nothing about `9.0.1.0858` — `Device.getType()` in
particular is documented and unmeasured, so this capability is `PENDING_TARGET`
(MJ-015, MJ-031).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.platform_stub import IDENTITY_DEVICES, identity_stub
from tests.muejeje.support import SCRIPT_ENGINE

OPERATION = "network.device_identity"

RESULT_FIELDS = {
    "resolution", "unavailable_reason", "workspace_index", "available_count",
    "device_present", "name", "model", "device_type",
}
# Every identity fact, so a test can assert the whole set is absent at once
# rather than naming three fields and forgetting the fourth one added later.
IDENTITY_FIELDS = ("name", "model", "device_type")

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(**args) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-identity", "op": OPERATION, "args": args,
    })


def _observed(**args) -> dict:
    args.setdefault("workspace_index", 0)
    return dispatch_v6(_request(**args), prelude=identity_stub())["result"]


# ---------------------------------------------------------------------------
# Structural: an operation, an adapter, and the arrow between them.
# ---------------------------------------------------------------------------

def test_the_operation_reads_the_workspace_only_through_its_adapter():
    """The arrow points operation -> adapter -> boundary, and never back."""
    operation = (SCRIPT_ENGINE / "network_identity.js").read_text(encoding="utf-8")

    assert "muejejeAdapterDeviceIdentity" in operation
    assert "ipc" not in operation.replace("muejeje", "")
    assert "muejejeAdapterCall" not in operation, (
        "an operation reaches the platform through its adapter, not past it"
    )


def test_the_operation_declares_its_own_argument_rule():
    body = (SCRIPT_ENGINE / "network_identity.js").read_text(encoding="utf-8")
    dispatcher = (SCRIPT_ENGINE / "dispatcher_v6.js").read_text(encoding="utf-8")

    assert "MUEJEJE_NETWORK_IDENTITY_ARGS = {" in body
    assert "MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX" in body
    assert "MUEJEJE_NETWORK_IDENTITY_ARGS" in dispatcher
    assert "EXACT_INTEGER_MAX" not in dispatcher, "the dispatcher holds no bound"


def test_the_reading_correlates_nothing_to_the_hardware_factory():
    """A workspace and the factory are two subjects, and this joins neither.

    The adapter names no factory symbol at all: not `hardwareFactory`, not
    `devices`, not `getDescriptor`. Correlating by index or by name would be
    worse than useless — it would publish a relationship nobody observed, in a
    result a consumer would reasonably trust (MJ-002, MJ-015).
    """
    adapter = (
        SCRIPT_ENGINE / "network_identity_adapter.js"
    ).read_text(encoding="utf-8")
    code = adapter.split("*/")[-1]

    for factory_symbol in ("hardwareFactory", "getDescriptor", "devices",
                           "getAvailableDeviceAt"):
        assert factory_symbol not in code, (
            f"the identity reading names {factory_symbol}; a workspace device is "
            "not a factory descriptor"
        )


# ---------------------------------------------------------------------------
# Executable: one shape, whether the platform answered or not.
# ---------------------------------------------------------------------------

@requires_node
def test_the_result_shape_is_the_same_whether_the_platform_answered():
    absent = dispatch_v6(_request(workspace_index=0))["result"]

    assert set(absent) == set(_observed()) == RESULT_FIELDS
    assert absent["resolution"] == "UNAVAILABLE"
    assert absent["unavailable_reason"] == "PLATFORM_ABSENT"
    assert absent["available_count"] is None
    assert absent["device_present"] is False
    assert [absent[field] for field in IDENTITY_FIELDS] == [None] * 3


@requires_node
def test_one_device_answers_with_the_identity_read_in_that_same_reading():
    result = _observed(workspace_index=1)

    assert result["resolution"] == "OBSERVED"
    assert result["unavailable_reason"] is None
    assert result["workspace_index"] == 1
    assert result["available_count"] == 2
    assert result["device_present"] is True
    assert result["name"] == "b"
    assert result["model"] == ""
    assert result["device_type"] == 7


@requires_node
def test_a_request_that_names_no_position_is_refused_and_reads_nothing():
    """Every position holds a different device, so no default could be honest.

    An earlier revision read position 0 when none was named and reported that
    device as the answer (MJ-029). `test_address_domains` holds the same rule
    for every operation about one subject.
    """
    observed = dispatch_v6(
        _request(), prelude=identity_stub(),
        report="{response: JSON.parse(mcpDispatchV6(REQUEST)), calls: CALLS}",
    )

    assert observed["response"]["error"]["code"] == "INVALID_ARGS"
    assert observed["calls"] == []


@requires_node
def test_an_empty_model_is_an_answer_and_not_a_malformed_one():
    """Measured on 9.0.1 for a chassis root, and the same rule applies here:
    requiring a non-empty string discarded correct metadata once already."""
    result = _observed(workspace_index=1)

    assert result["resolution"] == "OBSERVED"
    assert result["model"] == ""


@requires_node
def test_an_index_past_the_end_is_an_answer_not_an_unreadable_platform():
    """The workspace said how many devices it holds, and holds none there.

    Reporting that as unavailable would send a consumer looking for a platform
    fault that nothing had.
    """
    result = _observed(workspace_index=9)

    assert result["resolution"] == "OBSERVED"
    assert result["available_count"] == 2
    assert result["workspace_index"] == 9
    assert result["device_present"] is False
    assert [result[field] for field in IDENTITY_FIELDS] == [None] * 3


# ---------------------------------------------------------------------------
# Executable: whose failure was it, and what cannot be attributed.
# ---------------------------------------------------------------------------

@requires_node
@pytest.mark.parametrize(("prelude", "reason"), [
    ("", "PLATFORM_ABSENT"),
    ("var ipc = {network: function () { return {}; }};",
     "PLATFORM_MEMBER_ABSENT"),
])
def test_an_unreadable_platform_is_an_observation_with_its_reason(
    prelude: str, reason: str,
):
    response = dispatch_v6(_request(workspace_index=0), prelude=prelude)

    assert response["ok"] is True, "an unreadable platform is an answer"
    assert response["result"]["unavailable_reason"] == reason


@requires_node
def test_a_device_the_platform_will_not_hand_over_cannot_be_attributed():
    """A hole inside the count is not an absence.

    Reporting `device_present: false` would say the workspace holds nothing at
    a position its own count claims it does.
    """
    result = dispatch_v6(
        _request(workspace_index=2), prelude=identity_stub(device_count="3"),
    )["result"]

    assert result["resolution"] == "UNAVAILABLE"
    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
    assert result["device_present"] is False


@requires_node
@pytest.mark.parametrize(("field", "value"), [
    ("name", "7"),
    ("name", "null"),
    ("name", "'x'.repeat(257)"),
    ("model", "null"),
    ("device_type", "'1'"),
    ("device_type", "1.5"),
])
def test_every_identity_field_is_checked_before_it_is_reported(
    field: str, value: str,
):
    """One malformed field makes the whole reading unusable, not partial.

    This is the rule the serial number is kept out of the slice by: an
    all-or-nothing reading is only honest while every getter in it is one the
    platform reliably answers.
    """
    spec = {"name": "'a'", "model": "'PT-Router'", "device_type": "1"}
    spec[field] = value
    inner = ", ".join(f"{name}: {literal}" for name, literal in spec.items())
    prelude = identity_stub().replace(f"var DEVICES = {IDENTITY_DEVICES};",
                              f"var DEVICES = [{{{inner}}}];")

    result = dispatch_v6(_request(workspace_index=0), prelude=prelude)["result"]

    assert result["resolution"] == "UNAVAILABLE"
    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
    assert [result[name] for name in IDENTITY_FIELDS] == [None] * 3


@requires_node
@pytest.mark.parametrize("index", ["-1", "9007199254740992", "'0'", "1.5", "null"])
def test_an_index_this_adapter_would_not_accept_is_a_defect_not_a_clamp(
    index: str,
):
    """V6 admission refuses these from a caller, so one here came from us.

    Reading position 0 instead would report an observation about a device
    nobody asked about, as if the platform had answered the question sent.
    """
    observed = dispatch_v6(
        _request(), prelude=identity_stub(),
        report=(
            "(function () {"
            f"  try {{ return {{read: muejejeAdapterDeviceIdentity({index})}}; }}"
            "  catch (thrown) { return {refused: String(thrown)}; }"
            "}())"
        ),
    )

    assert "read" not in observed, "a bad argument was answered, not refused"
    assert "PLATFORM_" not in observed["refused"], (
        "an argument defect is ours, and never a platform reading"
    )


@requires_node
@pytest.mark.parametrize("args", [
    {"workspace_index": -1}, {"workspace_index": 9007199254740992},
    {"workspace_index": "0"}, {"workspace_index": 1.5},
    {"workspace_index": 0, "name": "a"}, {"device_index": 0},
])
def test_an_argument_outside_its_declared_rule_is_refused(args: dict):
    """Including `name`: addressing a device by name is not this contract."""
    response = dispatch_v6(_request(**args))

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGS"
