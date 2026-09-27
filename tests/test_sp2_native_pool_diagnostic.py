"""SP-2 experimental native-pool identity, authority and evidence contracts."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from packet_tracer_mcp.adapters.cli import (
    server_pt_commissioning,
    service_qualification,
)
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    CampaignQualificationAuthority,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign import (
    SP2_CAMPAIGN,
    ExecutionPurpose,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign_ledger import (
    SP2_ALLOWANCE,
    allowance_for,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    MeasurementConclusion,
    QualificationStage,
    RepositoryIdentity,
    stage_definition,
)
from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
    TERMINATION_NULL,
    TERMINATION_REPEAT,
    AddressRange,
    CalibrationState,
    ClientReading,
    LeaseRow,
    LeaseScan,
    assess_lease_calibration,
    classify_lease_scan,
)
from packet_tracer_mcp.domain.enterprise.services.service_qualification_evidence import (
    Assessment,
)
from packet_tracer_mcp.domain.enterprise.services.sp2_pool_diagnostic import (
    assess_sp2_pool_identity,
    cap_sp2_pool_identity,
    sp2_client_progression,
)
from tests.service_qualification_engine import (
    SIM_SHA,
    SIM_TREE,
    authorization_args,
    request_args,
)
from tests.test_q3_fastloop_coordinator import run_stage as q3_run_stage

ROOT = Path(__file__).resolve().parents[1]
CHARTER = (
    ROOT / "docs/reference/server-pt/assignments/Prompt_SP2_Generalized_DHCP_Relay.md"
)
run_stage = q3_run_stage


def _scan(pool: str, *rows: LeaseRow, termination: str = TERMINATION_NULL) -> LeaseScan:
    entries = [
        {
            "index": index,
            "return_kind": "object",
            "error": "",
            "row": {
                "ipAddress": row.ip,
                "macAddress": row.mac,
                "leaseTime": row.lease_time,
                "port": row.port,
            },
        }
        for index, row in enumerate(rows)
    ]
    if termination == TERMINATION_REPEAT:
        entries.append({**entries[0], "index": len(entries)})
    entries.extend(
        {"index": index, "return_kind": "null", "error": "", "row": None}
        for index in range(len(entries), 4)
    )
    return classify_lease_scan(
        {
            "requested": pool,
            "found": True,
            "name": pool,
            "max": 2,
            "window": 4,
            "entries": entries,
            "error": "",
        },
        pool_name=pool,
    )


def _clients(second_ip: str = "192.0.2.101") -> dict[str, ClientReading]:
    return {
        "PC-A": ClientReading(
            "PC-A", True, True, "0001.0001.0001", "192.0.2.100", "255.255.255.0"
        ),
        "PC-B": ClientReading(
            "PC-B", True, True, "0001.0001.0002", second_ip, "255.255.255.0"
        ),
    }


def _named() -> LeaseScan:
    return _scan(
        "named-a",
        LeaseRow(0, "192.0.2.100", "0001.0001.0001", 100.0, "FastEthernet0"),
        LeaseRow(1, "192.0.2.101", "0001.0001.0002", 100.0, "FastEthernet0"),
    )


def _calibrated_native():
    """Calibrate the fixture null end with empty and nonfull row states."""
    return assess_lease_calibration(
        [
            CalibrationState("empty", _scan("serverPool")),
            CalibrationState(
                "one",
                _scan(
                    "serverPool",
                    LeaseRow(
                        0,
                        "192.0.2.100",
                        "0001.0001.0001",
                        100.0,
                        "FastEthernet0",
                    ),
                ),
            ),
        ],
        pool="serverPool",
        capacity=2,
        fixture_macs=("0001.0001.0001", "0001.0001.0002"),
    )


def _assess(clients=None, named=None, native=None, **kwargs):
    kwargs.setdefault("native_calibration", _calibrated_native())
    return assess_sp2_pool_identity(
        ("PC-A", "PC-B"),
        clients or _clients(),
        named or _named(),
        native or _scan("serverPool"),
        named_pool="named-a",
        native_pool="serverPool",
        named_range=AddressRange("192.0.2.100", "192.0.2.101"),
        expected_netmask="255.255.255.0",
        **kwargs,
    )


def test_two_exact_named_rows_with_a_complete_empty_default_support_the_sample():
    """Calibrated native absence plus two named rows supports this sample."""
    result = _assess()
    assert result.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert result.facts["clients"]["PC-A"]["named_row"] == "exact_ip_mac_row"
    assert result.facts["clients"]["PC-B"]["native_row"] != "exact_ip_mac_row"


def test_uncalibrated_native_absence_cannot_support_named_pool():
    """A null in four reads alone says nothing about a later default row."""
    result = _assess(native_calibration=None)
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "native_absence_uncalibrated" in result.causes


def test_equivalent_mac_text_in_default_pool_is_a_competing_row():
    """A colon MAC with identical bytes cannot hide behind text inequality."""
    native = _scan(
        "serverPool",
        LeaseRow(0, "192.0.2.100", "00:01:00:01:00:01", 100.0, "FastEthernet0"),
    )
    result = _assess(native=native)
    assert result.conclusion is MeasurementConclusion.CONTRADICTED
    assert "PC-A:row_in_both_pools" in result.causes


def test_equivalent_mac_text_in_named_pool_keeps_positive_attribution():
    """Physical named identity survives a harmless MAC display change."""
    named = _scan(
        "named-a",
        LeaseRow(0, "192.0.2.100", "00:01:00:01:00:01", 100.0, "FastEthernet0"),
        _named().rows[1],
    )
    result = _assess(named=named)
    assert result.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert result.facts["clients"]["PC-A"]["named_row"] == (
        "mac_matches_only_after_normalization"
    )


def test_native_default_row_is_a_negative_physical_pool_finding():
    """A native row establishes the wrong physical authority in the sample."""
    native = _scan(
        "serverPool",
        LeaseRow(0, "192.0.2.101", "0001.0001.0002", 100.0, "FastEthernet0"),
    )
    result = _assess(
        named=_scan("named-a", _named().rows[0]),
        native=native,
    )
    assert result.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED
    assert "PC-B:served_by_native_default" in result.causes


def test_duplicate_address_and_repeated_scan_never_support_named_pool():
    """Duplicate identity and an incoherent table contradict positive serving."""
    duplicate = _assess(clients=_clients("192.0.2.100"))
    assert duplicate.conclusion is MeasurementConclusion.CONTRADICTED
    repeated = _assess(
        named=_scan("named-a", *_named().rows, termination=TERMINATION_REPEAT)
    )
    assert repeated.conclusion is MeasurementConclusion.CONTRADICTED


def test_unreadable_default_or_client_is_unknown_not_absence():
    """Missing observations cannot be interpreted as a clean pool absence."""
    unknown_default = _assess(native=LeaseScan("serverPool", False, "read_error"))
    assert unknown_default.conclusion is MeasurementConclusion.INCONCLUSIVE
    clients = _clients()
    clients["PC-B"] = ClientReading("PC-B", False, cause="read_error")
    unknown_client = _assess(clients=clients)
    assert unknown_client.conclusion is MeasurementConclusion.INCONCLUSIVE


def test_unexpected_pool_and_malformed_mac_refuse_positive_attribution():
    """An owned lab with a third pool or unusable MAC cannot prove authority."""
    unexpected = _assess(other_pools=("foreign",))
    assert unexpected.conclusion is MeasurementConclusion.CONTRADICTED
    clients = _clients()
    clients["PC-B"] = ClientReading(
        "PC-B", True, True, "invalid-mac", "192.0.2.101", "255.255.255.0"
    )
    malformed = _assess(clients=clients, named=_scan("named-a", _named().rows[0]))
    assert malformed.conclusion is MeasurementConclusion.INCONCLUSIVE


def test_sp2_campaign_and_stage_are_new_and_finitely_bounded():
    """The new stage and campaign carry the exact charter and finite grant."""
    assert SP2_CAMPAIGN.campaign_id == "SERVER-PT-SP2-GENERALIZED-DHCP-RELAY-01"
    assert (
        SP2_CAMPAIGN.charter_sha256 == hashlib.sha256(CHARTER.read_bytes()).hexdigest()
    )
    assert SP2_CAMPAIGN.purpose is ExecutionPurpose.EXPERIMENTAL
    assert SP2_CAMPAIGN.complete_attempt_limit is None
    assert allowance_for(SP2_CAMPAIGN.campaign_id) is SP2_ALLOWANCE
    assert (SP2_ALLOWANCE.total_operations, SP2_ALLOWANCE.protected_operations) == (
        20_000,
        1_000,
    )
    definition = stage_definition(QualificationStage.SP2_NATIVE_POOL.value)
    assert definition is not None and definition.executable
    assert definition.profile_id == "SP2-NATIVE-POOL"
    assert definition.profile_version == "2"
    assert definition.dhcp_pool_capacity == 2
    assert "M-SP2-POOL-IDENTITY" in definition.experiments_of_steps(("Q3FL-core",))
    assert definition.planned_minimum_operations <= definition.budget.max_operations


def test_sp2_stage_records_named_pool_service_from_stateful_scripts(run_stage):
    """Autonomous named rows do not turn default absence into support."""
    run = run_stage(
        "SP2-NATIVE-POOL",
        {"dhcp_pool_selection": "intended", "dhcp_mode_acquires": True},
    )

    result = run.measurement("M-SP2-POOL-IDENTITY")
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "native_absence_uncalibrated" in result.causes
    assert all(
        item["named_row"] == "exact_ip_mac_row"
        for item in result.facts["clients"].values()
    )
    assert run.snapshot["dhcp_runs"] == []
    assert [item["device"] for item in run.snapshot["background_acquisitions"]] == [
        "__MCP_E6Q_PC1",
        "__MCP_E6Q_PC2",
    ]
    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]] == [
        "addPool",
        "setEnable",
        "clientMode",
        "clientMode",
    ]
    server_scans = {
        row["label"]: row["pools"] for row in run.measurement("M-DHCP-1").facts["scans"]
    }
    assert {"before_pool_setup", "after_pool_setup", "after_enable_setup"} <= set(
        server_scans
    )
    assert server_scans["before_pool_setup"]["serverPool"]["observed"] is True
    assert server_scans["after_pool_setup"]["MCP_E6Q_DHCP"]["observed"] is True
    assert [item["label"] for item in result.facts["samples"]] == [
        "sample:__MCP_E6Q_PC1:1",
        "sample:__MCP_E6Q_PC1:2",
        "sample:__MCP_E6Q_PC2:1",
        "sample:__MCP_E6Q_PC2:2",
    ]
    assert result.facts["progression"]["__MCP_E6Q_PC1"]["admitted"] is True
    assert [row["client"] for row in result.facts["preclient_scans"]] == [
        "__MCP_E6Q_PC1",
        "__MCP_E6Q_PC2",
    ]
    assert (
        result.facts["preclient_scans"][1]["first_client_recheck"]["admitted"] is True
    )
    assert [row["clients"] for row in result.facts["mode_effects"]] == [
        ["__MCP_E6Q_PC1"],
        ["__MCP_E6Q_PC2"],
    ]
    assert {item.experiment_id for item in run.record.measurements} == {
        "M-DHCP-1",
        "M-DHCP-2",
        "M-SP2-POOL-IDENTITY",
        "M-DHCP-1-FINAL",
    }
    assert run.record.budget.used_operations <= 440
    assert run.result.outcome.value == "completed"
    assert run.record.restoration_proven is True


def test_sp2_stage_reports_native_pool_service_as_negative(run_stage):
    """The same two-client fixture records a competing native-pool result."""
    run = run_stage(
        "SP2-NATIVE-POOL",
        {"dhcp_pool_selection": "default", "dhcp_mode_acquires": True},
    )

    result = run.measurement("M-SP2-POOL-IDENTITY")
    assert result.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED
    assert any("served_by_native_default" in cause for cause in result.causes)
    assert result.facts["progression"]["__MCP_E6Q_PC1"]["admitted"] is False
    assert run.result.outcome.value == "completed"


def test_sp2_pool_setup_precedes_one_client_and_stops_on_default_row(run_stage):
    """The second native question isolates startup order before client mode."""
    run = run_stage(
        "SP2-NATIVE-POOL",
        {"dhcp_pool_selection": "default", "dhcp_mode_acquires": True},
    )

    timeline = run.snapshot["dhcp_timeline"]
    assert [item["effect"] for item in timeline] == [
        "addPool",
        "setEnable",
        "clientMode",
    ], (run.record.primary_failure, run.record.measurements)
    assert timeline[-1]["device"] == "__MCP_E6Q_PC1"
    assert run.snapshot["dhcp_runs"] == []
    assert [item["device"] for item in run.snapshot["background_acquisitions"]] == [
        "__MCP_E6Q_PC1"
    ]
    result = run.measurement("M-SP2-POOL-IDENTITY")
    assert result.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED
    assert any("served_by_native_default" in cause for cause in result.causes)


def test_sp2_progression_requires_stable_named_identity_and_usable_binding():
    """An incomplete default table does not erase a competing observed row."""
    first = ClientReading(
        "pc1", True, True, "0001.C75E.D477", "192.0.2.100", "255.255.255.0"
    )
    second = ClientReading(
        "pc1", True, True, "00:01:c7:5e:d4:77", "192.0.2.100", "255.255.255.0"
    )
    named = _scan(
        "named", LeaseRow(0, "192.0.2.100", "0001.C75E.D477", 3600.0, "FastEthernet0")
    )
    default = _scan("serverPool")
    binding = {
        "device": "pc1",
        "found": True,
        "port_found": True,
        "ipv4": "192.0.2.100",
        "netmask": "255.255.255.0",
        "error": "",
        "dns_api": True,
        "dns_server": "192.0.2.10",
        "dns_error": "",
        "gateway_reads": [
            {"api": True, "value": "192.0.2.1", "error": ""},
        ],
    }
    permitted, causes = sp2_client_progression(
        (first, second),
        (binding, binding),
        (named, named),
        (default, default),
        named_range=AddressRange("192.0.2.100", "192.0.2.101"),
        expected_mask="255.255.255.0",
        expected_gateway="192.0.2.1",
        expected_dns="192.0.2.10",
    )
    assert permitted and not causes

    competing = _scan(
        "serverPool",
        LeaseRow(0, "192.0.2.100", "0001.C75E.D477", 3600.0, "FastEthernet0"),
    )
    permitted, causes = sp2_client_progression(
        (first, second),
        (binding, binding),
        (named, named),
        (default, competing),
        named_range=AddressRange("192.0.2.100", "192.0.2.101"),
        expected_mask="255.255.255.0",
        expected_gateway="192.0.2.1",
        expected_dns="192.0.2.10",
    )
    assert not permitted and "competing_default_row" in causes

    conflicting_binding = {
        **binding,
        "gateway_reads": [
            {"api": True, "value": "192.0.2.1", "error": ""},
            {"api": True, "value": "192.0.2.254", "error": ""},
        ],
    }
    permitted, causes = sp2_client_progression(
        (first, second),
        (binding, conflicting_binding),
        (named, named),
        (default, default),
        named_range=AddressRange("192.0.2.100", "192.0.2.101"),
        expected_mask="255.255.255.0",
        expected_gateway="192.0.2.1",
        expected_dns="192.0.2.10",
    )
    assert not permitted and "sample_2:gateway_or_resolver_unusable" in causes

    incomplete_default = LeaseScan("serverPool", True, termination="throw")
    permitted, causes = sp2_client_progression(
        (first, second),
        (binding, binding),
        (named, named),
        (default, incomplete_default),
        named_range=AddressRange("192.0.2.100", "192.0.2.101"),
        expected_mask="255.255.255.0",
        expected_gateway="192.0.2.1",
        expected_dns="192.0.2.10",
    )
    assert not permitted and "sample_2:default_scan_incomplete" in causes

    permitted, causes = sp2_client_progression(
        (first, second),
        (binding, binding),
        (named, named),
        (default, default),
        named_range=AddressRange("192.0.2.100", "192.0.2.101"),
        expected_mask="255.255.255.0",
        expected_gateway="192.0.2.1",
        expected_dns="192.0.2.10",
        preclient_complete=False,
    )
    assert not permitted and "preclient_lease_absence_not_fully_observed" in causes


def test_sp2_positive_pool_result_requires_both_complete_progressions():
    """A clean final row cannot erase an earlier failed client sample."""
    result = cap_sp2_pool_identity(
        Assessment(MeasurementConclusion.SUPPORTED_IN_SAMPLE),
        {
            "pc1": {"admitted": True},
            "pc2": {
                "admitted": False,
                "causes": ["sample_1:gateway_or_resolver_unusable"],
            },
        },
        ("pc1", "pc2"),
    )
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "pc2:sample_1:gateway_or_resolver_unusable" in result.causes

    conflict = cap_sp2_pool_identity(
        Assessment(MeasurementConclusion.SUPPORTED_IN_SAMPLE),
        {"pc1": {"admitted": False, "causes": ["competing_default_row"]}},
        ("pc1",),
    )
    assert conflict.conclusion is MeasurementConclusion.CONTRADICTED

    uncertain_baseline = cap_sp2_pool_identity(
        Assessment(MeasurementConclusion.SUPPORTED_IN_SAMPLE),
        {"pc1": {"admitted": True}},
        ("pc1",),
        preclient_complete=False,
    )
    assert uncertain_baseline.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "preclient_lease_absence_not_fully_observed" in uncertain_baseline.causes


def test_sp2_refuses_client_activation_when_pc2_prebinds_on_server_enable(run_stage):
    """An autonomous mode change during setup invalidates the controlled probe."""
    run = run_stage(
        "SP2-NATIVE-POOL",
        {"dhcp_mode_acquires": True, "pc2_mode_on_server_enable": True},
    )

    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]] == [
        "addPool",
        "setEnable",
    ]
    assert run.record.primary_failure == "sp2_clients_not_unbound_after_enable"


def test_sp2_requires_a_physical_default_baseline_before_pool_effect(run_stage):
    """The discriminator cannot silently replace an absent native pool."""
    run = run_stage("SP2-NATIVE-POOL", {"dhcp_default_pool": False})

    assert run.snapshot["dhcp_timeline"] == []
    assert "sp2_native_default_baseline_not_exact" in run.record.primary_failure


def test_sp2_pool_effect_failure_blocks_enable_and_client_mode(run_stage):
    """A failed pool setter never permits a process or client mode effect."""
    run = run_stage("SP2-NATIVE-POOL", {"dhcp_add_pool_throws": True})

    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]] == ["addPool"]
    assert run.record.primary_failure


def test_sp2_incomplete_preclient_scan_withholds_second_client(run_stage):
    """A throwing table end allows one probe but cannot unlock expansion."""
    run = run_stage(
        "SP2-NATIVE-POOL",
        {
            "dhcp_pool_selection": "intended",
            "dhcp_mode_acquires": True,
            "dhcp_table_end": "throw",
        },
    )

    assert [item["effect"] for item in run.snapshot["dhcp_timeline"]] == [
        "addPool",
        "setEnable",
        "clientMode",
    ]
    identity = run.measurement("M-SP2-POOL-IDENTITY")
    assert identity.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert (
        "preclient_lease_absence_not_fully_observed"
        in identity.facts["progression"]["__MCP_E6Q_PC1"]["causes"]
    )


def test_sp2_lost_pool_response_quarantines_later_effects(run_stage):
    """A setter may run despite a lost response; no next mutation is admitted."""
    control = run_stage("SP2-NATIVE-POOL", {"dhcp_mode_acquires": True})
    pool_call = next(
        index
        for index, (_kind, script) in enumerate(control.transport.calls, start=1)
        if ".addPool(" in script
    )
    lost = run_stage("SP2-NATIVE-POOL", {"dhcp_mode_acquires": True}, lose={pool_call})

    assert [item["effect"] for item in lost.snapshot["dhcp_timeline"]] == ["addPool"]
    assert "outcome_unknown" in lost.record.primary_failure


def test_campaign_identity_cannot_borrow_sp1_or_prior_dhcp_authority():
    """An identical request and SHA need the SP-2 campaign identity."""
    stage = QualificationStage.SP2_NATIVE_POOL.value
    request = service_qualification._request(
        request_args(stage) + authorization_args(stage)
    )
    authorization = request.authorization
    assert authorization is not None
    repository = RepositoryIdentity(
        branch="feature/sim",
        head=SIM_SHA,
        tree=SIM_TREE,
        clean=True,
        upstream="cisco/feature/sim",
        upstream_head=SIM_SHA,
    )
    grant = CampaignQualificationAuthority(
        campaign_id=SP2_CAMPAIGN.campaign_id,
        episode=1,
        admission_record=f"episode-0001-{authorization.attempt_id}-qualification-admission",
        attempt_id=authorization.attempt_id,
        authorization_id=authorization.authorization_id,
        sha=SIM_SHA,
        tree=SIM_TREE,
        process_incarnation="sim-incarnation",
    )
    assert grant.permits(request, repository)
    assert not replace(grant, campaign_id="SERVER-PT-SP1-ROUTED-01").permits(
        request, repository
    )
    assert not replace(grant, campaign_id="SERVER-PT-DHCP-AUTONOMOUS-02").permits(
        request, repository
    )


def test_sp2_charter_and_stage_refuse_before_any_backend_read(tmp_path, capsys):
    """The CLI never opens a channel under a missing campaign or charter."""
    stage = QualificationStage.SP2_NATIVE_POOL.value
    args = request_args(stage) + authorization_args(stage)

    def forbidden(_root):
        raise AssertionError("a refusal must not compose a backend")

    assert (
        service_qualification.main(
            args,
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
            boundaries_factory=forbidden,
        )
        == 2
    )
    assert "stage_requires_its_campaign" in capsys.readouterr().out
    assert (
        service_qualification.main(
            [*args, "--campaign", "sp2", "--charter", str(tmp_path / "missing")],
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
            boundaries_factory=forbidden,
        )
        == 2
    )
    assert "charter_unreadable" in capsys.readouterr().out
    assert server_pt_commissioning._charter_refusal(SP2_CAMPAIGN, str(CHARTER)) == ""
    older = request_args("Q3-FL-C2") + authorization_args("Q3-FL-C2")
    assert (
        service_qualification.main(
            [*older, "--campaign", "sp2", "--charter", str(CHARTER)],
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
            boundaries_factory=forbidden,
        )
        == 2
    )
    assert "stage_not_part_of_the_dhcp_campaign" in capsys.readouterr().out
