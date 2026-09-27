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
    ClientReading,
    LeaseRow,
    LeaseScan,
    classify_lease_scan,
)
from packet_tracer_mcp.domain.enterprise.services.sp2_pool_diagnostic import (
    assess_sp2_pool_identity,
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


def _assess(clients=None, named=None, native=None, **kwargs):
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
    """Both clients must have exact named rows and no native rows."""
    result = _assess()
    assert result.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert result.facts["clients"]["PC-A"]["named_row"] == "exact_ip_mac_row"
    assert result.facts["clients"]["PC-B"]["native_row"] != "exact_ip_mac_row"


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
    assert definition.dhcp_pool_capacity == 2
    assert "M-SP2-POOL-IDENTITY" in definition.experiments_of_steps(("Q3FL-core",))
    assert definition.planned_minimum_operations <= definition.budget.max_operations


def test_sp2_stage_records_named_pool_service_from_stateful_scripts(run_stage):
    """Generated scripts, rather than a copied predicate, populate both rows."""
    run = run_stage("SP2-NATIVE-POOL", {"dhcp_pool_selection": "intended"})

    result = run.measurement("M-SP2-POOL-IDENTITY")
    assert result.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert len(run.snapshot["dhcp_runs"]) == 2
    assert run.record.restoration_proven is True


def test_sp2_stage_reports_native_pool_service_as_negative(run_stage):
    """The same two-client fixture records a competing native-pool result."""
    run = run_stage("SP2-NATIVE-POOL", {"dhcp_pool_selection": "default"})

    result = run.measurement("M-SP2-POOL-IDENTITY")
    assert result.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED
    assert any("served_by_native_default" in cause for cause in result.causes)


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
