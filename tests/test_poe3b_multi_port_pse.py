"""POE-3B: closed multi-port PSE evidence and canonical claim convergence."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityEvidence,
    CapabilityStatus,
    EvidenceSource,
    PoEAuthorizedBinding,
)
from src.packet_tracer_mcp.domain.enterprise.services.poe_claims import (
    decode_poe_authorized_claim,
)
from src.packet_tracer_mcp.domain.enterprise.services.poe_pse_claims import (
    PoEPseCapture,
    PoEPseDeliveryScope,
    decode_poe_pse_delivery_scope,
    encode_poe_pse_dimensions,
)
from src.packet_tracer_mcp.domain.enterprise.services.poe_pse_multiport_claims import (
    PoEPseBindingCapture,
    PoEPseMultiPortCapture,
    PoEPseMultiPortDeliveryScope,
    decode_poe_pse_multi_port_delivery_scope,
    encode_poe_pse_multi_port_dimensions,
)


BUILD = "9.0.1.0858"
SWITCH = "3560-24PS"
GATES = (
    "all_pagers_traversed",
    "attributable",
    "dispatch_integrity_valid",
    "expected_privileged_prompt_reached",
    "fresh",
    "no_pending_continuation",
    "observer_complete",
    "stable",
)
BINDING_A = PoEAuthorizedBinding("FastEthernet0/2", "7960", "Switch")
BINDING_B = PoEAuthorizedBinding("FastEthernet0/1", "7960", "Switch")
BINDINGS = (BINDING_A, BINDING_B)

# Hand-derived contract literal. In particular, its governed binding order is
# intentionally not lexical, so sorting it would make this fixture fail.
VALID_DIMENSIONS = {
    "poe_pse_evidence_kind": "pse_inline_delivery",
    "poe_pse_schema_version": "3",
    "poe_pse_switch_model": SWITCH,
    "poe_pse_packet_tracer_build": BUILD,
    "poe_pse_observer_id": "GovernedPoEInlineObserver",
    "poe_pse_experiment_id": "poe3b-two-port-fixture",
    "poe_pse_observed_at": "2026-09-09T18:00:00Z",
    "poe_pse_bindings": (
        '[{"endpoint_model":"7960","endpoint_port":"Switch",'
        '"switch_port":"FastEthernet0/2"},{"endpoint_model":"7960",'
        '"endpoint_port":"Switch","switch_port":"FastEthernet0/1"}]'
    ),
    "poe_pse_captures": (
        '[{"admin_mode":"auto","binding_captures":[{"delivering":true,'
        '"endpoint_model":"7960","endpoint_port":"Switch","oper_state":"on",'
        '"power_watts":10.0,"row_present":true,"switch_port":"FastEthernet0/2"},'
        '{"delivering":true,"endpoint_model":"7960","endpoint_port":"Switch",'
        '"oper_state":"on","power_watts":10.0,"row_present":true,'
        '"switch_port":"FastEthernet0/1"}],"label":"AUTO_1"},'
        '{"admin_mode":"never","binding_captures":[{"delivering":false,'
        '"endpoint_model":"7960","endpoint_port":"Switch","oper_state":"absent",'
        '"power_watts":0.0,"row_present":false,"switch_port":"FastEthernet0/2"},'
        '{"delivering":false,"endpoint_model":"7960","endpoint_port":"Switch",'
        '"oper_state":"off","power_watts":0.0,"row_present":true,'
        '"switch_port":"FastEthernet0/1"}],"label":"NEVER"},'
        '{"admin_mode":"auto","binding_captures":[{"delivering":true,'
        '"endpoint_model":"7960","endpoint_port":"Switch","oper_state":"on",'
        '"power_watts":10.0,"row_present":true,"switch_port":"FastEthernet0/2"},'
        '{"delivering":true,"endpoint_model":"7960","endpoint_port":"Switch",'
        '"oper_state":"on","power_watts":10.0,"row_present":true,'
        '"switch_port":"FastEthernet0/1"}],"label":"AUTO_2"}]'
    ),
    "poe_pse_gates": (
        '["all_pagers_traversed","attributable","dispatch_integrity_valid",'
        '"expected_privileged_prompt_reached","fresh","no_pending_continuation",'
        '"observer_complete","stable"]'
    ),
    "poe_pse_simultaneous_active_ports": "2",
    "poe_pse_cleanup_status": "clean",
    "poe_pse_inventory_restoration": "restored",
}


def _rows(label: str) -> tuple[PoEPseBindingCapture, ...]:
    delivering = label != "NEVER"
    return (
        PoEPseBindingCapture(
            "FastEthernet0/2", "7960", "Switch",
            "on" if delivering else "absent", 10.0 if delivering else 0.0,
            delivering, delivering,
        ),
        PoEPseBindingCapture(
            "FastEthernet0/1", "7960", "Switch",
            "on" if delivering else "off", 10.0 if delivering else 0.0,
            True, delivering,
        ),
    )


CAPTURES = (
    PoEPseMultiPortCapture("AUTO_1", "auto", _rows("AUTO_1")),
    PoEPseMultiPortCapture("NEVER", "never", _rows("NEVER")),
    PoEPseMultiPortCapture("AUTO_2", "auto", _rows("AUTO_2")),
)


def scope(**overrides) -> PoEPseMultiPortDeliveryScope:
    base = PoEPseMultiPortDeliveryScope(
        schema_version=3,
        switch_model=SWITCH,
        packet_tracer_build=BUILD,
        bindings=BINDINGS,
        observer_id="GovernedPoEInlineObserver",
        experiment_id="poe3b-two-port-fixture",
        observed_at="2026-09-09T18:00:00Z",
        captures=CAPTURES,
        gates=GATES,
        simultaneous_active_ports=2,
        cleanup_status="clean",
        inventory_restoration="restored",
    )
    return replace(base, **overrides)


def claim(dimensions: dict[str, str] | None = None, **overrides) -> CapabilityEvidence:
    fields = dict(
        capability="supports_poe",
        status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.CONTROLLED_PROBE,
        source_detail="poe3b-pse-probe",
        packet_tracer_version=BUILD,
        verified=True,
        observed_value=2,
        dimensions=dict(VALID_DIMENSIONS if dimensions is None else dimensions),
    )
    fields.update(overrides)
    return CapabilityEvidence(**fields)


def mutate_json(dimensions: dict[str, str], key: str, mutation) -> None:
    payload = json.loads(dimensions[key])
    mutation(payload)
    dimensions[key] = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def test_valid_schema_three_round_trips_in_governed_binding_order():
    decoded = decode_poe_pse_multi_port_delivery_scope(claim())
    assert decoded == scope()
    assert encode_poe_pse_multi_port_dimensions(decoded) == VALID_DIMENSIONS
    assert decoded.bindings == (BINDING_A, BINDING_B)


@pytest.mark.parametrize("invalid_scope", [
    None,
    scope(captures=(None, *CAPTURES[1:])),
    scope(captures=({}, *CAPTURES[1:])),
    scope(captures=(replace(CAPTURES[0], binding_captures=None), *CAPTURES[1:])),
    scope(captures=(replace(CAPTURES[0], binding_captures=1), *CAPTURES[1:])),
    scope(captures=(replace(CAPTURES[0], binding_captures=(None,)), *CAPTURES[1:])),
    scope(captures=(replace(CAPTURES[0], binding_captures=({},)), *CAPTURES[1:])),
    scope(gates=([], *GATES[1:])),
    scope(gates=(1, *GATES[1:])),
], ids=[
    "scope-none", "capture-none", "capture-dict", "rows-none", "rows-integer",
    "row-none", "row-dict", "gate-list", "gate-integer",
])
def test_encoder_refuses_malformed_runtime_types_with_value_error(invalid_scope):
    with pytest.raises(ValueError):
        encode_poe_pse_multi_port_dimensions(invalid_scope)


def test_schema_three_converges_only_to_the_canonical_authorized_claim():
    decoded = decode_poe_authorized_claim(
        claim(), expected_model=SWITCH, expected_packet_tracer_version=BUILD,
    )
    assert decoded is not None
    assert decoded.active_bindings == (BINDING_A, BINDING_B)
    assert decoded.simultaneous_active_ports == 2


def test_binding_declaration_must_be_duplicate_free():
    dimensions = dict(VALID_DIMENSIONS)
    mutate_json(
        dimensions, "poe_pse_bindings",
        lambda values: values.__setitem__(1, dict(values[0])),
    )
    mutate_json(
        dimensions, "poe_pse_captures",
        lambda captures: [
            capture["binding_captures"].__setitem__(
                1, dict(capture["binding_captures"][0]),
            )
            for capture in captures
        ],
    )
    assert decode_poe_pse_multi_port_delivery_scope(claim(dimensions)) is None


def test_empty_binding_declaration_fails_closed():
    dimensions = dict(VALID_DIMENSIONS)
    dimensions["poe_pse_bindings"] = "[]"
    mutate_json(
        dimensions, "poe_pse_captures",
        lambda captures: [capture.__setitem__("binding_captures", [])
                          for capture in captures],
    )
    dimensions["poe_pse_simultaneous_active_ports"] = "0"
    assert decode_poe_pse_multi_port_delivery_scope(
        claim(dimensions, observed_value=0),
    ) is None


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.pop(),
    lambda rows: rows.append(dict(rows[0])),
    lambda rows: rows.append({
        "switch_port": "FastEthernet0/3",
        "endpoint_model": "7960",
        "endpoint_port": "Switch",
        "oper_state": "on",
        "power_watts": 10.0,
        "row_present": True,
        "delivering": True,
    }),
    lambda rows: rows.reverse(),
])
def test_each_capture_has_exactly_the_declared_bindings_in_order(mutation):
    dimensions = dict(VALID_DIMENSIONS)
    mutate_json(
        dimensions, "poe_pse_captures",
        lambda captures: mutation(captures[0]["binding_captures"]),
    )
    assert decode_poe_pse_multi_port_delivery_scope(claim(dimensions)) is None


def test_one_non_delivering_auto_binding_fails_the_whole_claim():
    dimensions = dict(VALID_DIMENSIONS)
    def break_auto(captures):
        captures[0]["binding_captures"][1].update(
            delivering=False, oper_state="off", power_watts=0.0,
        )
    mutate_json(dimensions, "poe_pse_captures", break_auto)
    assert decode_poe_pse_multi_port_delivery_scope(claim(dimensions)) is None


def test_incomplete_never_capture_fails_closed():
    dimensions = dict(VALID_DIMENSIONS)
    mutate_json(
        dimensions, "poe_pse_captures",
        lambda captures: captures[1]["binding_captures"].pop(),
    )
    assert decode_poe_pse_multi_port_delivery_scope(claim(dimensions)) is None


def test_unrepresentable_json_power_fails_closed():
    dimensions = dict(VALID_DIMENSIONS)
    mutate_json(
        dimensions, "poe_pse_captures",
        lambda captures: captures[0]["binding_captures"][0].__setitem__(
            "power_watts", 10**400,
        ),
    )
    assert decode_poe_pse_multi_port_delivery_scope(claim(dimensions)) is None


@pytest.mark.parametrize("field, value", [
    ("row_present", 1),
    ("delivering", 1),
    ("power_watts", True),
])
def test_json_row_scalars_are_strict_even_when_python_equates_them(field, value):
    dimensions = dict(VALID_DIMENSIONS)
    mutate_json(
        dimensions, "poe_pse_captures",
        lambda captures: captures[0]["binding_captures"][0].__setitem__(field, value),
    )
    assert decode_poe_pse_multi_port_delivery_scope(claim(dimensions)) is None


@pytest.mark.parametrize("key, value", [
    ("poe_pse_simultaneous_active_ports", "1"),
    ("poe_pse_switch_model", "3650-24PS"),
    ("poe_pse_packet_tracer_build", "9.0.2.0000"),
    ("poe_pse_gates", '["fresh"]'),
])
def test_incoherent_schema_three_dimensions_fail_closed(key, value):
    dimensions = dict(VALID_DIMENSIONS)
    dimensions[key] = value
    assert decode_poe_pse_multi_port_delivery_scope(
        claim(dimensions), expected_model=SWITCH,
        expected_packet_tracer_version=BUILD,
    ) is None


@pytest.mark.parametrize("decoder", [
    decode_poe_pse_multi_port_delivery_scope,
    decode_poe_authorized_claim,
], ids=["multi-port", "authorized-claim"])
def test_expected_build_ceiling_rejects_an_internally_consistent_other_build(
    decoder,
):
    evidence = claim()
    assert evidence.packet_tracer_version == BUILD
    assert evidence.dimensions["poe_pse_packet_tracer_build"] == BUILD
    assert decoder(
        evidence, expected_model=SWITCH, expected_packet_tracer_version=BUILD,
    ) is not None
    assert decoder(
        evidence, expected_model=SWITCH,
        expected_packet_tracer_version="9.0.2.0000",
    ) is None


def test_observed_value_must_equal_the_binding_count():
    assert decode_poe_pse_multi_port_delivery_scope(
        claim(observed_value=1),
    ) is None


@pytest.mark.parametrize("field, value", [
    ("observed_value", True),
    ("verified", 1),
])
def test_claim_scalars_do_not_treat_booleans_and_numbers_as_interchangeable(
    field, value,
):
    evidence = claim().model_copy(update={field: value})
    assert decode_poe_pse_multi_port_delivery_scope(evidence) is None


@pytest.mark.parametrize("mutation", [
    lambda dimensions: dimensions.pop("poe_pse_observer_id"),
    lambda dimensions: dimensions.__setitem__("poe_pse_notes", "looked fine"),
])
def test_schema_three_dimension_set_is_closed(mutation):
    dimensions = dict(VALID_DIMENSIONS)
    mutation(dimensions)
    assert decode_poe_pse_multi_port_delivery_scope(claim(dimensions)) is None


def test_schema_two_shape_mislabeled_as_three_fails_both_pse_contracts():
    dimensions = _schema_two_literal()
    dimensions["poe_pse_schema_version"] = "3"
    evidence = claim(dimensions, observed_value=1)
    assert decode_poe_pse_multi_port_delivery_scope(evidence) is None
    assert decode_poe_authorized_claim(evidence) is None


def _schema_two_literal() -> dict[str, str]:
    return {
        "poe_pse_evidence_kind": "pse_inline_delivery",
        "poe_pse_schema_version": "2",
        "poe_pse_switch_model": SWITCH,
        "poe_pse_switch_port": "FastEthernet0/1",
        "poe_pse_endpoint_model": "7960",
        "poe_pse_endpoint_port": "Switch",
        "poe_pse_packet_tracer_build": BUILD,
        "poe_pse_observer_id": "GovernedPoEInlineObserver",
        "poe_pse_experiment_id": "schema-two-compatibility",
        "poe_pse_observed_at": "2026-09-09T17:00:00Z",
        "poe_pse_captures": (
            '[{"admin_mode":"auto","delivering":true,"label":"AUTO_1",'
            '"oper_state":"on","power_watts":10.0,"row_present":true},'
            '{"admin_mode":"never","delivering":false,"label":"NEVER",'
            '"oper_state":"absent","power_watts":0.0,"row_present":false},'
            '{"admin_mode":"auto","delivering":true,"label":"AUTO_2",'
            '"oper_state":"on","power_watts":10.0,"row_present":true}]'
        ),
        "poe_pse_gates": VALID_DIMENSIONS["poe_pse_gates"],
        "poe_pse_simultaneous_active_ports": "1",
        "poe_pse_cleanup_status": "clean",
        "poe_pse_inventory_restoration": "restored",
    }


def test_schema_two_encoder_still_has_its_exact_historical_mapping():
    dimensions = _schema_two_literal()
    schema_two_scope = PoEPseDeliveryScope(
        schema_version=2,
        switch_model=SWITCH,
        switch_port="FastEthernet0/1",
        endpoint_model="7960",
        endpoint_port="Switch",
        packet_tracer_build=BUILD,
        observer_id="GovernedPoEInlineObserver",
        experiment_id="schema-two-compatibility",
        observed_at="2026-09-09T17:00:00Z",
        captures=(
            PoEPseCapture("AUTO_1", "auto", "on", 10.0, True, True),
            PoEPseCapture("NEVER", "never", "absent", 0.0, False, False),
            PoEPseCapture("AUTO_2", "auto", "on", 10.0, True, True),
        ),
        gates=GATES,
        simultaneous_active_ports=1,
        cleanup_status="clean",
        inventory_restoration="restored",
    )
    assert encode_poe_pse_dimensions(schema_two_scope) == dimensions
    schema_two_claim = claim(dimensions, observed_value=1)
    decoded = decode_poe_pse_delivery_scope(schema_two_claim)
    assert decoded == schema_two_scope
    assert encode_poe_pse_dimensions(decoded) == dimensions
