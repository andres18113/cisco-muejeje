"""The second delegated native-pool experiment, using the governed runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from packet_tracer_mcp.adapters.cli.service_qualification import _request
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    qualify_server_services,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    Q3_NATIVE_START_AFTER,
    Q3_NATIVE_START_BEFORE,
    Q3_NATIVE_START_EVIDENCE_SHA256,
    MeasurementConclusion,
    QualificationOutcome,
    stage_definition,
    step_selection_refusals,
)
from tests.service_qualification_engine import (
    NodeEngine,
    NodeEngineTransport,
    authorization_args,
    request_args,
    require_node,
    simulated_boundaries,
)


def test_size_profile_pins_the_coupled_start_then_one_capacity_setter() -> None:
    """The new question cannot silently reuse the first probe's single setter."""
    definition = stage_definition("Q3-NATIVE-SIZE")
    assert definition is not None
    assert (definition.profile_id, definition.profile_version) == (
        "Q3-NATIVE-SIZE",
        "1",
    )
    assert definition.allowed_channels == ("file",)
    assert definition.fixture_models == (
        "__MCP_E6Q_SRV:Server-PT",
        "__MCP_E6Q_PC1:PC-PT",
        "__MCP_E6Q_PC2:PC-PT",
        "__MCP_E6Q_SW:2960-24TT",
    )
    assert definition.step_ids == ("NATIVE-size",)
    assert definition.experiments_of_steps(definition.step_ids) == (
        "M-NATIVE-REPEAT-START",
        "M-NATIVE-MAX",
        "M-NATIVE-FINAL",
    )
    assert definition.budget.max_operations == 120
    assert definition.budget.max_seconds == 600
    assert definition.planned_minimum_operations <= 120
    assert step_selection_refusals(definition, definition.step_ids) == []


def test_repeated_start_basis_matches_the_archived_primary_record() -> None:
    """The admitted physical values are the measured episode-1 values."""
    record_path = (
        Path(__file__).resolve().parents[1]
        / "docs/reference/server-pt/evidence/dhcp-autonomy-02/e1/record"
        / "q3-native-probe-2026-09-25T20-36-44Z-84514155.json"
    )
    raw = record_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == Q3_NATIVE_START_EVIDENCE_SHA256
    record = json.loads(raw)
    (measurement,) = [
        item
        for item in record["measurements"]
        if item["experiment_id"] == "M-NATIVE-START"
    ]
    assert measurement["facts"]["before"] == dict(Q3_NATIVE_START_BEFORE)
    assert measurement["facts"]["after"] == dict(Q3_NATIVE_START_AFTER)


@pytest.mark.parametrize(
    ("max_behavior", "conclusion"),
    [
        ("resize", MeasurementConclusion.SUPPORTED_IN_SAMPLE),
        ("noop", MeasurementConclusion.NEGATIVE_OBSERVED),
        ("throw", MeasurementConclusion.INCONCLUSIVE),
    ],
)
def test_size_stage_runs_through_real_coordinator_and_records_the_max_effect(
    tmp_path, max_behavior, conclusion
) -> None:
    """One exact repeated start permits one separately observed capacity call."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior=max_behavior,
    )
    try:
        transport = NodeEngineTransport(engine)
        request = _request(
            request_args("Q3-NATIVE-SIZE") + authorization_args("Q3-NATIVE-SIZE")
        )
        definition = stage_definition("Q3-NATIVE-SIZE")
        result = qualify_server_services(
            request,
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.record is not None
        measurements = {item.experiment_id: item for item in result.record.measurements}
        assert (
            measurements["M-NATIVE-REPEAT-START"].conclusion
            is MeasurementConclusion.SUPPORTED_IN_SAMPLE
        )
        assert measurements["M-NATIVE-MAX"].conclusion is conclusion
        assert result.record.restoration_proven
        calls = engine.snapshot()["dhcp_setter_calls"]
        assert calls["setStartIp"] == 1
        assert calls["setMaxUsers"] == 1
        if max_behavior == "resize":
            assert result.outcome is QualificationOutcome.COMPLETED
            assert measurements["M-NATIVE-MAX"].facts["after"] == {
                "name": "serverPool",
                "network": "192.0.2.0",
                "mask": "255.255.255.0",
                "gateway": "0.0.0.0",
                "dns": "0.0.0.0",
                "start": "192.0.2.100",
                "end": "192.0.2.100",
                "max": 1,
            }
        elif max_behavior == "throw":
            assert result.outcome is QualificationOutcome.STOPPED
    finally:
        engine.close()


@pytest.mark.parametrize(
    ("start_behavior", "expected_failure"),
    [
        ("change", "contradiction:M-NATIVE-REPEAT-START"),
        (
            "noop",
            "q3_native_size_repeat_start_not_supported:negative_observed",
        ),
    ],
)
def test_size_stage_withholds_capacity_when_start_coupling_differs(
    tmp_path, start_behavior, expected_failure
) -> None:
    """A different backend response cannot inherit episode 1's admission."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior=start_behavior,
        dhcp_native_max_behavior="resize",
    )
    try:
        transport = NodeEngineTransport(engine)
        request = _request(
            request_args("Q3-NATIVE-SIZE") + authorization_args("Q3-NATIVE-SIZE")
        )
        definition = stage_definition("Q3-NATIVE-SIZE")
        result = qualify_server_services(
            request,
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record is not None
        assert result.record.primary_failure == expected_failure
        assert engine.snapshot()["dhcp_setter_calls"]["setMaxUsers"] == 0
        assert result.record.restoration_proven
    finally:
        engine.close()


@pytest.mark.parametrize(
    ("case", "config"),
    [
        ("pool_missing", {"dhcp_default_pool": None}),
        ("enabled", {"dhcp_server_initial_enabled": True}),
        ("inventory_unreadable", {"dhcp_pool_count_invalid": True}),
    ],
)
def test_size_stage_refuses_unowned_or_enabled_baseline_before_e5(
    tmp_path, case, config
) -> None:
    """An incomplete or enabled first read cannot authorize server addressing."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        **{
            "dhcp_default_pool": "native",
            "default_pool_realigns_on_address": True,
            **config,
        },
    )
    try:
        transport = NodeEngineTransport(engine)
        request = _request(
            request_args("Q3-NATIVE-SIZE") + authorization_args("Q3-NATIVE-SIZE")
        )
        definition = stage_definition("Q3-NATIVE-SIZE")
        result = qualify_server_services(
            request,
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.record is not None
        assert result.outcome is QualificationOutcome.STOPPED
        assert result.record.primary_failure == "q3_native_baseline_not_admitted"
        snapshot = result.record.native_default_pool[0]
        if case == "enabled":
            assert snapshot.raw["enabled"] is True
        elif case == "inventory_unreadable":
            assert snapshot.observed is False
        else:
            assert snapshot.pools == []
        state = engine.snapshot()
        assert state["static_addresses"] == []
        assert state["dhcp_setter_calls"]["setStartIp"] == 0
        assert state["dhcp_setter_calls"]["setMaxUsers"] == 0
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_size_stage_rejects_a_new_competing_pool_before_max(tmp_path) -> None:
    """A filtered native row cannot hide another physical pool from admission."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled_extra_pool",
        dhcp_native_max_behavior="resize",
    )
    try:
        transport = NodeEngineTransport(engine)
        request = _request(
            request_args("Q3-NATIVE-SIZE") + authorization_args("Q3-NATIVE-SIZE")
        )
        definition = stage_definition("Q3-NATIVE-SIZE")
        result = qualify_server_services(
            request,
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.record is not None
        measurement = next(
            item
            for item in result.record.measurements
            if item.experiment_id == "M-NATIVE-REPEAT-START"
        )
        assert measurement.conclusion is MeasurementConclusion.CONTRADICTED
        assert {row["name"] for row in measurement.facts["after_inventory"]} == {
            "serverPool",
            "MCP_E6Q_DHCP",
        }
        assert engine.snapshot()["dhcp_setter_calls"]["setMaxUsers"] == 0
        assert result.record.restoration_proven
    finally:
        engine.close()


def test_size_stage_refuses_process_enabled_by_server_address(tmp_path) -> None:
    """The E5 readback cannot authorize a setter on an enabled DHCP process."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_enable_on_server_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
    )
    try:
        transport = NodeEngineTransport(engine)
        request = _request(
            request_args("Q3-NATIVE-SIZE") + authorization_args("Q3-NATIVE-SIZE")
        )
        definition = stage_definition("Q3-NATIVE-SIZE")
        result = qualify_server_services(
            request,
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.record is not None
        assert result.outcome is QualificationOutcome.STOPPED
        assert (
            result.record.primary_failure == "q3_native_process_not_disabled_after_e5"
        )
        assert result.record.native_default_pool[1].raw["enabled"] is True
        state = engine.snapshot()
        assert any(
            row["device"] == "__MCP_E6Q_SRV" for row in state["static_addresses"]
        )
        assert state["dhcp_setter_calls"]["setStartIp"] == 0
        assert state["dhcp_setter_calls"]["setMaxUsers"] == 0
        assert result.record.restoration_proven
    finally:
        engine.close()
