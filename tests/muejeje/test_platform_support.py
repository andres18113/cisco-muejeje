"""`platform.module_type_support`: does this model accept this module type?

The third discovered capability, and the narrowest: one flag, from
`DeviceDescriptor.isModuleTypeSupported(ModuleType)` — a *descriptor* method,
not a method on a runtime device, and not a statement about installed hardware
(MJ-014).

**Neither argument is translated here.** The model is addressed by its index in
the factory enumeration that `platform.device_descriptors` reports, and the
module type is a value the platform itself handed a consumer — from that
operation, or from the chassis of `platform.module_descriptors`. This artifact
carries no table of either, which is what lets it ask the question without
owning an answer to "which types exist".

**The answer is attributed.** A support flag with no model beside it is a fact
nobody can place, so the identity is read back from the same descriptor and
reported with it.

**The `OBSERVED` branch is driven against a stub**, and establishes what our
code does. Nothing here reaches `9.0.1.0858`, so the capability is
`PENDING_TARGET` (MJ-015, MJ-031).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.platform_stub import CHASSIS_MODELS, platform_stub
from tests.muejeje.support import SCRIPT_ENGINE

OPERATION = "platform.module_type_support"

RESULT_FIELDS = {
    "resolution", "unavailable_reason", "device_index", "module_type",
    "available_count", "descriptor_present", "model", "device_type",
    "module_type_supported",
}

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(**args) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-support", "op": OPERATION, "args": args,
    })


def _observed(**args) -> dict:
    args.setdefault("module_type", 6)
    return dispatch_v6(
        _request(**args), prelude=platform_stub(CHASSIS_MODELS),
    )["result"]


# ---------------------------------------------------------------------------
# Structural: one adapter, one subject.
# ---------------------------------------------------------------------------

def test_the_operation_names_no_platform_symbol_of_its_own():
    """Operation -> adapter -> boundary -> platform, never a shortcut (MJ-019)."""
    body = (SCRIPT_ENGINE / "platform_support.js").read_text(encoding="utf-8")

    assert "muejejeAdapterModuleTypeSupport(" in body
    assert "ipc" not in body
    assert "muejejeAdapterCall" not in body
    assert "isModuleTypeSupported" not in body


def test_the_support_reading_did_not_grow_inside_the_chassis_walk():
    """One adapter, one subject (MJ-018).

    "What does this model accept" and "what is it described as carrying" are
    two readings of the same descriptor, and the walk is already the longer of
    the two. Folding this into it would have made one file answer two
    questions, which is the split this budget exists to force.
    """
    walk = (SCRIPT_ENGINE / "platform_module_adapter.js").read_text(encoding="utf-8")
    support = (SCRIPT_ENGINE / "platform_support_adapter.js").read_text(
        encoding="utf-8",
    )

    assert "isModuleTypeSupported" not in walk
    assert "getRootModule" not in support
    assert "muejejeAdapterModuleTypeSupport" in support


def test_the_operation_declares_its_own_argument_rules():
    body = (SCRIPT_ENGINE / "platform_support.js").read_text(encoding="utf-8")
    dispatcher = (SCRIPT_ENGINE / "dispatcher_v6.js").read_text(encoding="utf-8")

    assert "MUEJEJE_PLATFORM_SUPPORT_ARGS = {" in body
    assert "MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MIN" in body
    assert "MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX" in body
    assert "MUEJEJE_PLATFORM_SUPPORT_ARGS" in dispatcher
    assert "EXACT_INTEGER_" not in dispatcher, "the dispatcher holds no bound"


# ---------------------------------------------------------------------------
# Executable: one shape, and an answer that can be placed.
# ---------------------------------------------------------------------------

@requires_node
def test_the_result_shape_is_the_same_whether_the_platform_answered():
    absent = dispatch_v6(_request(module_type=6))["result"]

    assert set(absent) == set(_observed()) == RESULT_FIELDS
    assert absent["resolution"] == "UNAVAILABLE"
    assert absent["unavailable_reason"] == "PLATFORM_ABSENT"
    assert absent["module_type"] == 6, "the question is echoed even unanswered"
    assert absent["module_type_supported"] is None


@requires_node
@pytest.mark.parametrize(("module_type", "supported"), [(6, True), (18, False)])
def test_the_platform_answers_for_the_type_it_was_asked_about(
    module_type: int, supported: bool,
):
    """Both directions of the flag, so it is a reading and not a constant."""
    result = _observed(module_type=module_type)

    assert result["resolution"] == "OBSERVED"
    assert result["module_type"] == module_type
    assert result["module_type_supported"] is supported


@requires_node
def test_the_answer_carries_the_identity_it_is_an_answer_about():
    """A flag with no model beside it is a fact nobody can place (MJ-010)."""
    result = _observed(device_index=0)

    assert result["descriptor_present"] is True
    assert result["model"] == "AccessPoint-PT"
    assert result["device_type"] == 7
    assert result["device_index"] == 0
    assert result["available_count"] == 2


@requires_node
def test_an_index_past_the_end_is_an_answer_not_an_unreadable_platform():
    result = _observed(device_index=9)

    assert result["resolution"] == "OBSERVED"
    assert result["available_count"] == 2
    assert result["descriptor_present"] is False
    assert result["model"] is None
    assert result["module_type_supported"] is None


@requires_node
def test_the_operation_reaches_no_verdict_about_what_it_read():
    reported = json.dumps(_observed())

    for verdict in ("VERIFIED", "QUALIFIED", "ATTESTED", "PASS", "SUPPORTED_BY"):
        assert verdict not in reported, verdict


@requires_node
def test_the_operation_is_read_only_in_the_catalogue_it_publishes():
    catalogue = dispatch_v6(
        _request(module_type=6), report="muejejeV6OperationCatalog()",
    )
    entry = next(item for item in catalogue if item["op"] == OPERATION)

    assert entry["read_only"] is True


# ---------------------------------------------------------------------------
# Executable: the arguments, and the one that has no honest default.
# ---------------------------------------------------------------------------

@requires_node
def test_the_type_is_required_because_no_default_would_be_honest():
    """Every value in that space is a different question.

    Defaulting it would answer one the caller did not ask, and report the
    answer as an observation. A missing required argument is `INVALID_ARGS` —
    a request this operation does not support — and never a reading, because
    nothing was read (MJ-022).
    """
    response = dispatch_v6(_request(device_index=0))

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGS"
    assert response["result"] is None


@requires_node
def test_the_device_index_still_defaults_to_the_first_model():
    """The other argument does have an honest default: the enumeration origin."""
    result = _observed()

    assert result["device_index"] == 0
    assert result["model"] == "AccessPoint-PT"


# Past the published `ModuleType` domain in either direction. The old cases
# here were `-1` and `65536`, and both were wrong: the readings publish those
# values, so refusing them meant refusing this artifact's own output. What is
# still refused is a magnitude that no longer round-trips — past it the value
# handed back would not be the value sent (`test_relay_closure`).
BEYOND_TYPE_DOMAIN = 9007199254740992


@requires_node
@pytest.mark.parametrize("args", [
    {"module_type": BEYOND_TYPE_DOMAIN}, {"module_type": -BEYOND_TYPE_DOMAIN},
    {"module_type": "6"},
    {"module_type": 1.5}, {"module_type": 6, "device_index": -1},
    {"module_type": 6, "device_index": 9007199254740992}, {"module_type": 6, "model": "x"},
])
def test_an_argument_outside_its_declared_rule_is_refused(args: dict):
    response = dispatch_v6(_request(**args))

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGS"


@requires_node
@pytest.mark.parametrize("module_type", [-1, 0, 65536])
def test_a_type_value_the_readings_publish_is_not_refused_here(module_type: int):
    """The pair the old rule got wrong, pinned so it cannot come back.

    `-1` and `65536` are values `platform.device_descriptors` and
    `platform.module_descriptors` will publish if the platform answers them, so
    this operation admitting them is not leniency — it is the contract not
    contradicting itself (`test_relay_closure` drives the whole relay).
    """
    response = dispatch_v6(_request(module_type=module_type))

    assert response["ok"] is True
    assert response["result"]["module_type"] == module_type


@requires_node
@pytest.mark.parametrize(("prelude", "reason"), [
    ("", "PLATFORM_ABSENT"),
    ("var ipc = {hardwareFactory: function () { return {}; }};",
     "PLATFORM_MEMBER_ABSENT"),
])
def test_an_unreadable_platform_is_an_observation_with_its_reason(
    prelude: str, reason: str,
):
    response = dispatch_v6(_request(module_type=6), prelude=prelude)

    assert response["ok"] is True
    assert response["result"]["unavailable_reason"] == reason


@requires_node
def test_an_answer_that_is_not_a_flag_cannot_be_attributed():
    """The platform said something, and it is not the shape of an answer."""
    lying = platform_stub(CHASSIS_MODELS).replace(
        "return spec.module_types.indexOf(type) !== -1;", "return 'yes';",
    )
    result = dispatch_v6(_request(module_type=6), prelude=lying)["result"]

    assert result["resolution"] == "UNAVAILABLE"
    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
    assert result["module_type_supported"] is None
