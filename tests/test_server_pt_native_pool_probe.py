"""Native-pool probe through the governed qualification coordinator and engine."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from packet_tracer_mcp.adapters.cli import service_qualification
from packet_tracer_mcp.adapters.cli.service_qualification import _request
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    qualify_server_services,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    ExecutionMode,
    MeasurementConclusion,
    QualificationOutcome,
    RepositoryIdentity,
    stage_definition,
)
from packet_tracer_mcp.domain.enterprise.services.service_qualification_evidence import (
    DefaultPoolSnapshot,
    ProbeReading,
    assess_native_pool_start_probe,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from packet_tracer_mcp.infrastructure.persistence.service_qualification_store import (
    QualificationRecordStore,
)
from tests.service_qualification_engine import (
    SIM_PROCESS_ID,
    SIM_PROCESS_INCARNATION,
    SIM_PROCESS_PATH,
    SIM_SHA,
    SIM_TREE,
    NodeEngine,
    NodeEngineTransport,
    authorization_args,
    request_args,
    require_node,
    simulated_boundaries,
)

ATTEMPT = "d" * 32
CAMPAIGN = "SERVER-PT-DHCP-AUTONOMOUS-02"
MANDATE = (
    Path(__file__).resolve().parents[1]
    / "docs/reference/server-pt/assignments/ServerPT_DHCP_Delegated_Autonomy_Mandate.md"
)


def test_fixed_native_setter_probe_records_physical_change_and_cleans_up(tmp_path):
    """A setter is measured inside one bounded, archived qualification run."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
    )
    try:
        transport = NodeEngineTransport(engine)
        boundaries = simulated_boundaries(tmp_path, transport)
        request = _request(
            request_args("Q3-NATIVE-PROBE") + authorization_args("Q3-NATIVE-PROBE")
        )
        definition = stage_definition("Q3-NATIVE-PROBE")
        result = qualify_server_services(
            request,
            boundaries,
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is QualificationOutcome.COMPLETED, (
            result.record.primary_failure if result.record else result.refusals
        )
        assert result.record is not None
        measurement = result.record.measurements[0]
        assert measurement.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
        assert measurement.facts["before"]["start"] == "192.0.2.0"
        assert measurement.facts["after"]["start"] == "192.0.2.100"
        assert engine.snapshot()["dhcp_setter_calls"]["setStartIp"] == 1
        assert result.record.restoration_proven
    finally:
        engine.close()


@pytest.mark.parametrize(
    ("behavior", "conclusion", "outcome"),
    [
        (
            "noop",
            MeasurementConclusion.NEGATIVE_OBSERVED,
            QualificationOutcome.COMPLETED,
        ),
        ("throw", MeasurementConclusion.INCONCLUSIVE, QualificationOutcome.STOPPED),
    ],
)
def test_native_setter_noop_or_throw_never_becomes_support(
    tmp_path, behavior, conclusion, outcome
):
    """The real coordinator classifies a no-op and an uncertain exception."""
    require_node()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior=behavior,
    )
    try:
        transport = NodeEngineTransport(engine)
        request = _request(
            request_args("Q3-NATIVE-PROBE") + authorization_args("Q3-NATIVE-PROBE")
        )
        definition = stage_definition("Q3-NATIVE-PROBE")
        result = qualify_server_services(
            request,
            simulated_boundaries(tmp_path, transport),
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        assert result.outcome is outcome
        assert result.record is not None
        assert result.record.measurements[0].conclusion is conclusion
        assert result.record.restoration_proven
        assert engine.snapshot()["dhcp_setter_calls"]["setStartIp"] == 1
    finally:
        engine.close()


def test_native_start_probe_rejects_a_new_competing_pool():
    """A changed full inventory cannot be hidden by the filtered native view."""
    native = {
        "name": "serverPool",
        "network": "192.0.2.0",
        "mask": "255.255.255.0",
        "gateway": "0.0.0.0",
        "dns": "0.0.0.0",
        "start": "192.0.2.0",
        "end": "192.0.3.255",
        "max": 512,
    }
    changed = {**native, "start": "192.0.2.100"}
    intended = {**native, "name": "MCP_E6Q_DHCP"}
    before = DefaultPoolSnapshot(
        "before", True, pools=(native,), raw={"pool_count": 1, "pools": [native]}
    )
    after = DefaultPoolSnapshot(
        "after",
        True,
        pools=(changed,),
        intended_present=True,
        raw={"pool_count": 2, "pools": [changed, intended]},
    )
    probe = ProbeReading(
        "dhcp_native_start_probe",
        DispatchFact.ACCEPTED,
        ResultFact.CORRELATED,
        True,
        {
            "device": "__MCP_E6Q_SRV",
            "interface": "FastEthernet0",
            "pool": "serverPool",
            "found": True,
            "attempted": True,
            "call_error": "",
            "pre_start": "192.0.2.0",
            "post_start": "192.0.2.100",
        },
    )
    assessment = assess_native_pool_start_probe(
        before=before,
        probe=probe,
        after=after,
        server="__MCP_E6Q_SRV",
        interface="FastEthernet0",
        requested_start="192.0.2.100",
    )
    assert assessment.conclusion is MeasurementConclusion.CONTRADICTED
    assert assessment.facts["after_inventory"] == [changed, intended]


def test_native_start_probe_rejects_unrequested_process_activation():
    """A correct start field does not excuse a changed DHCP enable state."""
    native = {
        "name": "serverPool",
        "network": "192.0.2.0",
        "mask": "255.255.255.0",
        "gateway": "0.0.0.0",
        "dns": "0.0.0.0",
        "start": "192.0.2.0",
        "end": "192.0.3.255",
        "max": 512,
    }
    before = DefaultPoolSnapshot(
        "before",
        True,
        pools=(native,),
        raw={"pool_count": 1, "pools": [native], "enabled": False},
    )
    after = DefaultPoolSnapshot(
        "after",
        True,
        pools=({**native, "start": "192.0.2.100"},),
        raw={
            "pool_count": 1,
            "pools": [{**native, "start": "192.0.2.100"}],
            "enabled": True,
        },
    )
    probe = ProbeReading(
        "dhcp_native_start_probe",
        DispatchFact.ACCEPTED,
        ResultFact.CORRELATED,
        True,
        {
            "device": "__MCP_E6Q_SRV",
            "interface": "FastEthernet0",
            "pool": "serverPool",
            "found": True,
            "attempted": True,
            "call_error": "",
            "pre_start": "192.0.2.0",
            "post_start": "192.0.2.100",
        },
    )
    assessment = assess_native_pool_start_probe(
        before=before,
        probe=probe,
        after=after,
        server="__MCP_E6Q_SRV",
        interface="FastEthernet0",
        requested_start="192.0.2.100",
    )
    assert assessment.conclusion is MeasurementConclusion.CONTRADICTED


@pytest.mark.parametrize("mode", [ExecutionMode.LIVE, "live", "offline_simulation"])
def test_direct_live_application_refuses_campaign_stage_without_mission_authority(
    tmp_path, mode
):
    """Publishing a SHA alone cannot bypass the new campaign ledger."""
    source = RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head=SIM_SHA,
        tree=SIM_TREE,
        clean=True,
        upstream="cisco/feature/server-pt-goal-foundations",
        upstream_head=SIM_SHA,
    )
    boundaries = simulated_boundaries(tmp_path, object(), repository=lambda: source)
    boundaries = replace(
        boundaries,
        execution_mode=mode,
        open_transport=lambda _channel: pytest.fail("transport contacted before grant"),
    )
    request = _request(
        request_args("Q3-NATIVE-PROBE") + authorization_args("Q3-NATIVE-PROBE")
    )
    definition = stage_definition("Q3-NATIVE-PROBE")
    result = qualify_server_services(
        request,
        boundaries,
        experimental_capabilities=frozenset(definition.experimental_capabilities),
    )
    assert result.outcome is QualificationOutcome.REFUSED
    assert {item.subject.value for item in result.refusals} == {
        "authorization" if type(mode) is ExecutionMode else "execution"
    }


@pytest.mark.parametrize(
    ("stage", "engine_config", "max_calls", "policy_calls"),
    [
        ("Q3-NATIVE-PROBE", {}, 0, False),
        (
            "Q3-NATIVE-SIZE",
            {
                "dhcp_native_start_behavior": "coupled",
                "dhcp_native_max_behavior": "resize",
            },
            1,
            False,
        ),
        (
            "Q3-NATIVE-POLICY",
            {
                "dhcp_native_start_behavior": "coupled",
                "dhcp_native_max_behavior": "resize",
            },
            1,
            True,
        ),
    ],
)
def test_new_campaign_cli_binds_and_archives_the_probe(
    tmp_path, monkeypatch, capsys, stage, engine_config, max_calls, policy_calls
):
    """The fixed probe executes only after the new mandate, launch and grant bind."""
    require_node()
    assert (
        "dhcp-autonomy"
        in service_qualification._parser()._option_string_actions["--campaign"].choices
    )
    source = RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head=SIM_SHA,
        tree=SIM_TREE,
        clean=True,
        upstream="cisco/feature/server-pt-goal-foundations",
        upstream_head="b" * 40,
    )
    monkeypatch.setattr(service_qualification, "repository_identity", lambda _: source)
    definition = stage_definition(stage)
    store = ServerPtCommissioningStore(tmp_path, CAMPAIGN)
    store.save_ledger_record(
        "episode-0001-opening",
        {
            "kind": "episode_opening",
            "episode": 1,
            "question": f"Does {stage} measure its native setter?",
            "stop_rule": "stop on unknown effect or incomplete readback",
            "source_sha": SIM_SHA,
            "source_tree": SIM_TREE,
            "attempt_ids": [ATTEMPT],
            "tests_run": ["tests/test_server_pt_native_pool_probe.py"],
            "targets": ["__MCP_E6Q_SRV"],
            "permitted_effects": [f"qualification:{stage}"],
            "allocated_operations": definition.budget.max_operations,
            "allocated_seconds": 1800.0,
            "opened_at_utc": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
        },
    )
    store.save_process_launch(
        ATTEMPT,
        {
            "pid": SIM_PROCESS_ID,
            "process_path": SIM_PROCESS_PATH,
            "process_incarnation": SIM_PROCESS_INCARNATION,
            "campaign_id": CAMPAIGN,
            "execution_purpose": "experimental",
            "source_sha": SIM_SHA,
            "source_tree": SIM_TREE,
        },
    )
    store.refresh_index()
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        **engine_config,
    )
    try:
        transport = NodeEngineTransport(engine)

        def boundaries(_root):
            return simulated_boundaries(
                tmp_path,
                transport,
                repository=lambda: source,
                record_store=QualificationRecordStore(
                    tmp_path / "data/services/qualification"
                ),
            )

        code = service_qualification.main(
            request_args(stage)
            + authorization_args(stage, attempt_id=ATTEMPT)
            + [
                "--campaign",
                "dhcp-autonomy",
                "--charter",
                str(MANDATE),
                "--episode",
                "1",
            ],
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
            boundaries_factory=boundaries,
        )
        summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert code == 0, summary
        assert summary["campaign"]["campaign_id"] == CAMPAIGN
        assert store.load_phase_status(ATTEMPT, "qualification")["restoration_proven"]
        assert store.verify_index() == ()
        assert engine.snapshot()["dhcp_setter_calls"]["setStartIp"] == 1
        assert engine.snapshot()["dhcp_setter_calls"]["setMaxUsers"] == max_calls
        assert engine.snapshot()["dhcp_setter_calls"]["setDefaultRouter"] == int(
            policy_calls
        )
        assert engine.snapshot()["dhcp_setter_calls"]["setDnsServerIp"] == int(
            policy_calls
        )
        assert engine.snapshot()["dhcp_setter_calls"]["addExcludedAddress"] == (
            2 if policy_calls else 0
        )
    finally:
        engine.close()
