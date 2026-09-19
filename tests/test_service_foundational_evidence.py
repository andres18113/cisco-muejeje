"""R-ENTRY-04: E6 foundations come from executed rows, through the E9 predicate.

`ServiceApplicator` refuses to touch a service whose foundation is not
VERIFIED, and the only way to produce that mapping used to be for a caller to
write it out by hand. That is the same shape the E9 tests exist to forbid, in
the stage that mutates a server's services.

These tests hold the derivation to the E9 rules: the exact plan and hash, one
shared core predicate, one satisfied `configuration_action_id` per satisfied
core, and the weaker of two disagreeing rows. There is no status parameter to
pass, which is the point.
"""

from __future__ import annotations

from packet_tracer_mcp.application.use_cases.foundational_evidence import (
    derive_service_foundational_statuses,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    ConvergenceReport,
    FieldVerificationStatus,
    VerificationResult,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    FoundationalServiceRequirement,
    ServicePlan,
)

_CONFIG_ID = "cfg_reference"
_CONFIG_HASH = "cfg-hash"
_ENDPOINT_ACTION = "cfg/endpoint-static/hq-server-01"
_SWITCH_ACTION = "cfg/svi/hq-mls-01"
_DHCP_ACTION = "cfg/endpoint-dhcp/hq-client-01"


def _plan(
    *requirements: FoundationalServiceRequirement,
    configuration_id: str = _CONFIG_ID,
    configuration_hash: str = _CONFIG_HASH,
) -> ServicePlan:
    return ServicePlan(
        id="services_hq",
        source_topology_id="topo",
        source_topology_hash="topo-hash",
        source_configuration_id=configuration_id,
        source_configuration_hash=configuration_hash,
        foundational_requirements=list(requirements),
    )


def _endpoint_requirement(
    action_id: str = _ENDPOINT_ACTION,
) -> FoundationalServiceRequirement:
    return FoundationalServiceRequirement(
        id="svc/foundation/server",
        device_id="hq/server/1",
        device_name="HQ-SERVER-01",
        model="Server-PT",
        ipv4="198.18.160.10",
        segment_id="hq/data",
        configuration_action_id=action_id,
        kind="endpoint_address",
    )


def _config(
    *verifications: VerificationResult,
    plan_id: str = _CONFIG_ID,
    semantic_hash: str = _CONFIG_HASH,
    action_results: list[ActionApplicationResult] | None = None,
) -> ConfigurationApplicationResult:
    return ConfigurationApplicationResult(
        config_plan_id=plan_id,
        config_semantic_hash=semantic_hash,
        source_topology_hash="topo-hash",
        status=ConfigurationApplicationStatus.VERIFIED,
        action_results=list(action_results or []),
        verification_results=list(verifications),
    )


def _dhcp_mode_requirement() -> FoundationalServiceRequirement:
    return FoundationalServiceRequirement(
        id="svc/foundation/client-mode",
        device_id="hq/client/1",
        device_name="HQ-CLIENT-01",
        model="PC-PT",
        ipv4="",
        segment_id="hq/data",
        configuration_action_id=_DHCP_ACTION,
        kind="endpoint_dhcp_mode",
    )


def _dhcp_mode_row(
    *,
    status: ActionExecutionStatus = ActionExecutionStatus.VERIFIED,
    interface: str = "FastEthernet0",
    observed_interface: str | None = None,
    fresh_evidence: bool = True,
) -> VerificationResult:
    return VerificationResult(
        expectation_id="cfg/verify/client-mode",
        action_id=_DHCP_ACTION,
        status=status,
        evidence_method="structured_endpoint_dhcp_mode",
        fresh_evidence=fresh_evidence,
        fields={
            "dhcp_mode": (
                FieldVerificationStatus.VERIFIED
                if status is ActionExecutionStatus.VERIFIED
                else FieldVerificationStatus.FAILED
            )
        },
        convergence=ConvergenceReport(
            attempts=1,
            final_status=status,
            details={
                "kind": "endpoint_dhcp_mode",
                "device_name": "HQ-CLIENT-01",
                "interface": interface,
                "last_observation": {
                    "device_found": True,
                    "port_found": True,
                    "mode_channel": True,
                    "interface": (
                        interface if observed_interface is None else observed_interface
                    ),
                    "dhcp_mode": status is ActionExecutionStatus.VERIFIED,
                    "fresh_evidence": fresh_evidence,
                    "failure_reason": "",
                },
            },
        ),
    )


def _applied_dhcp_mode(
    status: ActionExecutionStatus = ActionExecutionStatus.APPLIED,
) -> ActionApplicationResult:
    return ActionApplicationResult(action_id=_DHCP_ACTION, status=status)


def _endpoint_core(
    action_id: str = _ENDPOINT_ACTION,
    *,
    status: ActionExecutionStatus = ActionExecutionStatus.PARTIAL,
    evidence_method: str = "structured_endpoint_getters",
    fresh_evidence: bool = True,
    ipv4_field: FieldVerificationStatus = FieldVerificationStatus.VERIFIED,
    interface: str = "FastEthernet0",
    observed_interface: str | None = None,
) -> VerificationResult:
    """Build the fresh attributable core E5 actually reports."""
    return VerificationResult(
        expectation_id=f"cfg/verify/{action_id}",
        action_id=action_id,
        status=status,
        evidence_method=evidence_method,
        fresh_evidence=fresh_evidence,
        fields={
            "ipv4": ipv4_field,
            "netmask": FieldVerificationStatus.VERIFIED,
            "gateway": FieldVerificationStatus.UNOBSERVABLE,
            "dns": FieldVerificationStatus.UNOBSERVABLE,
        },
        convergence=ConvergenceReport(
            attempts=1,
            final_status=status,
            details={
                "kind": "endpoint_addressing",
                "device_name": "HQ-SERVER-01",
                "interface": interface,
                "last_observation": {
                    "device_found": True,
                    "port_found": True,
                    "address_channel": True,
                    "interface": (
                        interface if observed_interface is None else observed_interface
                    ),
                    "ipv4": "198.18.160.10",
                    "netmask": "255.255.255.0",
                    "fresh_evidence": True,
                    "failure_reason": "",
                },
            },
        ),
    )


# -- what satisfies a foundation ------------------------------------------


def test_a_partial_endpoint_with_an_attributable_core_satisfies_its_action():
    """The legitimate PT ceiling: IPv4 and netmask fresh, gateway and DNS not."""
    plan = _plan(_endpoint_requirement())

    statuses = derive_service_foundational_statuses(plan, _config(_endpoint_core()))

    assert statuses == {_ENDPOINT_ACTION: ActionExecutionStatus.VERIFIED}


def test_the_core_satisfies_only_its_own_action():
    """It never speaks for a second foundation, even on the same device."""
    other = _endpoint_requirement(_SWITCH_ACTION).model_copy(
        update={"id": "svc/foundation/other"}
    )
    plan = _plan(_endpoint_requirement(), other)

    statuses = derive_service_foundational_statuses(plan, _config(_endpoint_core()))

    assert statuses == {_ENDPOINT_ACTION: ActionExecutionStatus.VERIFIED}
    assert _SWITCH_ACTION not in statuses


def test_a_non_endpoint_foundation_copies_its_verification_status():
    """No core predicate exists for it, so nothing is promoted."""
    requirement = FoundationalServiceRequirement(
        id="svc/foundation/svi",
        device_id="hq/mls/1",
        device_name="HQ-MLS-01",
        model="3560-24PS",
        ipv4="198.18.160.1",
        segment_id="hq/data",
        configuration_action_id=_SWITCH_ACTION,
        kind="l3_interface",
    )
    row = VerificationResult(
        expectation_id="cfg/verify/svi",
        action_id=_SWITCH_ACTION,
        status=ActionExecutionStatus.VERIFIED,
        evidence_method="fresh_show_ip_interface_brief",
        fresh_evidence=True,
    )

    statuses = derive_service_foundational_statuses(_plan(requirement), _config(row))

    assert statuses == {_SWITCH_ACTION: ActionExecutionStatus.VERIFIED}


def test_fresh_true_dhcp_mode_satisfies_without_an_address():
    """S3-02: bootstrap proves mode on the exact port, not acquisition."""
    statuses = derive_service_foundational_statuses(
        _plan(_dhcp_mode_requirement()),
        _config(
            _dhcp_mode_row(),
            action_results=[_applied_dhcp_mode()],
        ),
    )

    assert statuses == {_DHCP_ACTION: ActionExecutionStatus.VERIFIED}


def test_applied_alone_never_satisfies_dhcp_mode():
    statuses = derive_service_foundational_statuses(
        _plan(_dhcp_mode_requirement()),
        _config(action_results=[_applied_dhcp_mode()]),
    )

    assert statuses == {}


def test_false_dhcp_mode_is_a_fresh_contradiction():
    statuses = derive_service_foundational_statuses(
        _plan(_dhcp_mode_requirement()),
        _config(
            _dhcp_mode_row(status=ActionExecutionStatus.FAILED),
            action_results=[_applied_dhcp_mode()],
        ),
    )

    assert statuses == {_DHCP_ACTION: ActionExecutionStatus.FAILED}


def test_dhcp_mode_on_another_interface_grants_nothing():
    statuses = derive_service_foundational_statuses(
        _plan(_dhcp_mode_requirement()),
        _config(
            _dhcp_mode_row(observed_interface="FastEthernet1"),
            action_results=[_applied_dhcp_mode()],
        ),
    )

    assert statuses == {_DHCP_ACTION: ActionExecutionStatus.UNKNOWN}


def test_uncertain_dhcp_mode_dispatch_cannot_found_e6():
    statuses = derive_service_foundational_statuses(
        _plan(_dhcp_mode_requirement()),
        _config(
            _dhcp_mode_row(),
            action_results=[_applied_dhcp_mode(ActionExecutionStatus.UNKNOWN)],
        ),
    )

    assert statuses == {_DHCP_ACTION: ActionExecutionStatus.UNKNOWN}


# -- what does not -------------------------------------------------------


def test_an_aggregate_verified_without_a_core_degrades_to_unknown():
    """A row that claims success without the observation that backs it."""
    bare = VerificationResult(
        expectation_id="cfg/verify/endpoint",
        action_id=_ENDPOINT_ACTION,
        status=ActionExecutionStatus.VERIFIED,
        evidence_method="fresh_show_ip_interface_brief",
        fresh_evidence=True,
    )

    statuses = derive_service_foundational_statuses(
        _plan(_endpoint_requirement()), _config(bare)
    )

    assert statuses == {_ENDPOINT_ACTION: ActionExecutionStatus.UNKNOWN}


def test_a_result_for_another_configuration_satisfies_nothing():
    """Same action id, different plan: the rows are about something else."""
    plan = _plan(_endpoint_requirement())

    by_id = derive_service_foundational_statuses(
        plan, _config(_endpoint_core(), plan_id="cfg_other")
    )
    by_hash = derive_service_foundational_statuses(
        plan, _config(_endpoint_core(), semantic_hash="different-hash")
    )

    assert by_id == {_ENDPOINT_ACTION: ActionExecutionStatus.UNKNOWN}
    assert by_hash == {_ENDPOINT_ACTION: ActionExecutionStatus.UNKNOWN}


def test_a_stale_evidence_method_does_not_satisfy_the_core():
    """The core is a fresh structured read, not any read at all."""
    statuses = derive_service_foundational_statuses(
        _plan(_endpoint_requirement()),
        _config(_endpoint_core(evidence_method="cached_endpoint_snapshot")),
    )

    assert statuses == {_ENDPOINT_ACTION: ActionExecutionStatus.PARTIAL}


def test_a_row_without_fresh_evidence_does_not_satisfy_the_core():
    """A cached agreement is not an observation of this run."""
    statuses = derive_service_foundational_statuses(
        _plan(_endpoint_requirement()), _config(_endpoint_core(fresh_evidence=False))
    )

    assert statuses == {_ENDPOINT_ACTION: ActionExecutionStatus.PARTIAL}


def test_a_failed_address_field_does_not_satisfy_the_core():
    """The core is IPv4 AND netmask; one failing field ends it."""
    statuses = derive_service_foundational_statuses(
        _plan(_endpoint_requirement()),
        _config(_endpoint_core(ipv4_field=FieldVerificationStatus.FAILED)),
    )

    assert statuses == {_ENDPOINT_ACTION: ActionExecutionStatus.PARTIAL}


def test_an_observation_of_another_interface_does_not_satisfy_the_core():
    """Evidence about another port is evidence about another subject."""
    statuses = derive_service_foundational_statuses(
        _plan(_endpoint_requirement()),
        _config(_endpoint_core(observed_interface="FastEthernet1")),
    )

    assert statuses == {_ENDPOINT_ACTION: ActionExecutionStatus.PARTIAL}


def test_a_foundation_with_no_executed_row_is_absent_so_the_gate_refuses():
    """Absence is not permission: the applicator refuses on a missing key."""
    statuses = derive_service_foundational_statuses(
        _plan(_endpoint_requirement()), _config()
    )

    assert statuses == {}


def test_two_disagreeing_rows_resolve_to_the_weaker_one():
    """A conflict is never settled by choosing the success."""
    failed = VerificationResult(
        expectation_id="cfg/verify/endpoint-again",
        action_id=_ENDPOINT_ACTION,
        status=ActionExecutionStatus.FAILED,
        evidence_method="structured_endpoint_getters",
        fresh_evidence=True,
    )

    statuses = derive_service_foundational_statuses(
        _plan(_endpoint_requirement()), _config(_endpoint_core(), failed)
    )

    assert statuses == {_ENDPOINT_ACTION: ActionExecutionStatus.FAILED}


def test_rows_for_actions_this_plan_does_not_found_on_are_ignored():
    """Only the plan's own foundations become statuses."""
    foreign = VerificationResult(
        expectation_id="cfg/verify/unrelated",
        action_id="cfg/vlan/hq-data",
        status=ActionExecutionStatus.VERIFIED,
        evidence_method="fresh_show_vlan",
        fresh_evidence=True,
    )

    statuses = derive_service_foundational_statuses(
        _plan(_endpoint_requirement()), _config(_endpoint_core(), foreign)
    )

    assert set(statuses) == {_ENDPOINT_ACTION}


def test_a_plan_with_no_foundations_derives_nothing():
    """Nothing to found on means nothing to derive."""
    assert (
        derive_service_foundational_statuses(_plan(), _config(_endpoint_core())) == {}
    )
