"""Foundational evidence must be derived, never asserted.

The University Topology Acceptance satisfied the control-plane foundational
gate with a comprehension over the gate's own inputs. These tests exist to make
that shape impossible to reach again through the production helper: every path
that could mint a VERIFIED it did not observe is pinned here.
"""
from __future__ import annotations

import pytest

from packet_tracer_mcp.application.use_cases.foundational_evidence import (
    derive_foundational_hashes,
    derive_foundational_statuses,
    unmet_foundations,
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
from packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneFoundationRequirement,
    ControlPlanePlan,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    ApplicationExecutionJournal,
)
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentItemResult,
    PhysicalDeploymentItemStatus,
    PhysicalDeploymentResult,
    PhysicalDeploymentStatus,
    PhysicalObjectKind,
)


def _config(
    verifications: list[VerificationResult],
    actions: list[ActionApplicationResult] | None = None,
) -> ConfigurationApplicationResult:
    return ConfigurationApplicationResult(
        config_plan_id="cfg_reference",
        config_semantic_hash="cfg-hash",
        source_topology_hash="topo-hash",
        status=ConfigurationApplicationStatus.VERIFIED,
        action_results=actions or [],
        verification_results=verifications,
    )


def _verification(
    action_id: str, status: ActionExecutionStatus,
) -> VerificationResult:
    return VerificationResult(
        expectation_id=f"cfg/verify/{action_id}",
        action_id=action_id,
        status=status,
        evidence_method="fresh_show_ip_interface_brief",
        fresh_evidence=status is ActionExecutionStatus.VERIFIED,
    )


def _endpoint_verification(
    action_id: str = "cfg/endpoint-dhcp/pc-01",
) -> VerificationResult:
    """Mirror the fresh E5 endpoint evidence measured in Router0."""
    return VerificationResult(
        expectation_id="cfg/verify/endpoint-pc-01",
        action_id=action_id,
        status=ActionExecutionStatus.PARTIAL,
        evidence_method="structured_endpoint_getters",
        fresh_evidence=True,
        fields={
            "ipv4": FieldVerificationStatus.VERIFIED,
            "netmask": FieldVerificationStatus.VERIFIED,
            "gateway": FieldVerificationStatus.UNOBSERVABLE,
            "dns": FieldVerificationStatus.UNOBSERVABLE,
        },
        convergence=ConvergenceReport(
            attempts=1,
            final_status=ActionExecutionStatus.PARTIAL,
            details={
                "kind": "endpoint_addressing",
                "device_name": "MULTILAYER-BRANCH-MLS3-PC-01",
                "interface": "FastEthernet0",
                "last_observation": {
                    "device_found": True,
                    "port_found": True,
                    "address_channel": True,
                    "interface": "FastEthernet0",
                    "ipv4": "172.18.10.7",
                    "netmask": "255.255.255.0",
                    "fresh_evidence": True,
                    "failure_reason": "",
                },
            },
        ),
    )


def _physical(items: list[PhysicalDeploymentItemResult]) -> PhysicalDeploymentResult:
    return PhysicalDeploymentResult(
        topology_id="uce-topo",
        physical_topology_hash="phys-hash",
        deployment_id="deploy-1",
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer", backend_version="9.0.1.0858",
        ),
        status=PhysicalDeploymentStatus.VERIFIED,
        item_results=items,
        execution_journal=ApplicationExecutionJournal(plan_id="uce-topo"),
    )


def _link_item(
    target_id: str,
    status: PhysicalDeploymentItemStatus,
    *,
    observed: bool = True,
) -> PhysicalDeploymentItemResult:
    return PhysicalDeploymentItemResult(
        target_id=target_id,
        target_kind=PhysicalObjectKind.LINK,
        status=status,
        observed=observed,
    )


def _plan(
    requirements: list[ControlPlaneFoundationRequirement],
) -> ControlPlanePlan:
    return ControlPlanePlan(
        id="cp/reference",
        source_topology_id="uce-topo",
        source_topology_hash="topo-hash",
        source_configuration_id="cfg_reference",
        source_configuration_hash="cfg-hash",
        foundational_requirements=requirements,
    )


def _plan_for(kind: str, source_id: str) -> ControlPlanePlan:
    return _plan([
        ControlPlaneFoundationRequirement(
            id=f"foundation/{kind}/{source_id}",
            kind=kind,
            source_id=source_id,
        ),
    ])


# ============ A. VERIFIED is copied from evidence, never minted ============


def test_a_verified_configuration_foundation_comes_from_its_verification():
    statuses = derive_foundational_statuses(
        _plan_for("l3_interface", "cfg/routed/r1-lan"),
        configuration_result=_config([
            _verification("cfg/routed/r1-lan", ActionExecutionStatus.VERIFIED),
        ]),
    )

    assert statuses == {"cfg/routed/r1-lan": ActionExecutionStatus.VERIFIED}


def test_no_evidence_at_all_yields_no_statuses():
    """The gate must refuse, and refusing is what an empty mapping does."""
    assert derive_foundational_statuses(_plan([])) == {}


@pytest.mark.parametrize(
    "status",
    [
        ActionExecutionStatus.APPLIED,
        ActionExecutionStatus.PARTIAL,
        ActionExecutionStatus.UNOBSERVABLE,
        ActionExecutionStatus.SKIPPED,
        ActionExecutionStatus.FAILED,
        ActionExecutionStatus.DEPENDENCY_BLOCKED,
        ActionExecutionStatus.UNKNOWN,
    ],
)
def test_a_non_verified_verification_is_never_promoted(status):
    statuses = derive_foundational_statuses(
        _plan_for("l3_interface", "cfg/routed/r1"),
        configuration_result=_config([_verification("cfg/routed/r1", status)]),
    )

    assert statuses["cfg/routed/r1"] is status
    assert statuses["cfg/routed/r1"] is not ActionExecutionStatus.VERIFIED


def test_an_applied_action_result_never_becomes_a_foundation():
    """APPLIED means the channel accepted the payload. It is not evidence.

    This is the exact confusion the helper exists to prevent: reading
    `action_results` instead of `verification_results` would report every
    dispatched action as satisfying the gate.
    """
    statuses = derive_foundational_statuses(
        _plan_for("l3_interface", "cfg/routed/r1"),
        configuration_result=_config(
            verifications=[],
            actions=[ActionApplicationResult(
                action_id="cfg/routed/r1",
                status=ActionExecutionStatus.APPLIED,
            )],
        ),
    )

    assert statuses == {}


# ============ B. Link foundations come from physical read-back ============


def test_an_observed_link_is_verified():
    statuses = derive_foundational_statuses(
        _plan_for("link", "link/wan-r1-r2"),
        physical_result=_physical([
            _link_item("link/wan-r1-r2", PhysicalDeploymentItemStatus.OBSERVED),
        ]),
    )

    assert statuses == {"link/wan-r1-r2": ActionExecutionStatus.VERIFIED}


def test_an_observed_row_without_the_observed_flag_is_not_verified():
    """`status=OBSERVED` with `observed=False` contradicts itself.

    Fail closed rather than trusting the label over the evidence field.
    """
    statuses = derive_foundational_statuses(
        _plan_for("link", "link/wan-r1-r2"),
        physical_result=_physical([
            _link_item(
                "link/wan-r1-r2",
                PhysicalDeploymentItemStatus.OBSERVED,
                observed=False,
            ),
        ]),
    )

    assert statuses["link/wan-r1-r2"] is ActionExecutionStatus.UNKNOWN


@pytest.mark.parametrize(
    ("physical", "expected"),
    [
        (PhysicalDeploymentItemStatus.APPLIED, ActionExecutionStatus.APPLIED),
        (PhysicalDeploymentItemStatus.SATISFIED, ActionExecutionStatus.APPLIED),
        (PhysicalDeploymentItemStatus.NOT_ATTEMPTED, ActionExecutionStatus.INTENDED),
        (PhysicalDeploymentItemStatus.FAILED, ActionExecutionStatus.FAILED),
    ],
)
def test_only_an_observed_link_can_reach_verified(physical, expected):
    statuses = derive_foundational_statuses(
        _plan_for("link", "link/a"),
        physical_result=_physical([_link_item("link/a", physical)]),
    )

    assert statuses["link/a"] is expected
    assert statuses["link/a"] is not ActionExecutionStatus.VERIFIED


def test_a_non_link_physical_item_is_not_a_foundation():
    """Device foundations do not exist; only links are keyed by a plan id."""
    statuses = derive_foundational_statuses(
        _plan_for("link", "r1"),
        physical_result=_physical([
            PhysicalDeploymentItemResult(
                target_id="r1",
                target_kind=PhysicalObjectKind.DEVICE,
                status=PhysicalDeploymentItemStatus.OBSERVED,
                observed=True,
            ),
        ]),
    )

    assert statuses == {}


# ============ C. Conflicts fail closed ============


def test_two_sources_disagreeing_resolve_to_the_weaker():
    statuses = derive_foundational_statuses(
        _plan([
            ControlPlaneFoundationRequirement(
                id="foundation/l3_interface/shared/id",
                kind="l3_interface", source_id="shared/id",
            ),
            ControlPlaneFoundationRequirement(
                id="foundation/link/shared/id",
                kind="link", source_id="shared/id",
            ),
        ]),
        configuration_result=_config([
            _verification("shared/id", ActionExecutionStatus.VERIFIED),
        ]),
        physical_result=_physical([
            _link_item("shared/id", PhysicalDeploymentItemStatus.FAILED),
        ]),
    )

    assert statuses["shared/id"] is ActionExecutionStatus.FAILED


def test_conflict_resolution_does_not_depend_on_argument_order():
    duplicated = derive_foundational_statuses(
        _plan_for("l3_interface", "cfg/a"),
        configuration_result=_config([
            _verification("cfg/a", ActionExecutionStatus.FAILED),
            _verification("cfg/a", ActionExecutionStatus.VERIFIED),
        ]),
    )

    assert duplicated["cfg/a"] is ActionExecutionStatus.FAILED


def test_an_empty_source_id_is_never_recorded():
    statuses = derive_foundational_statuses(
        _plan_for("l3_interface", ""),
        configuration_result=_config([
            _verification("", ActionExecutionStatus.VERIFIED),
        ]),
    )

    assert statuses == {}


# ============ D. Hashes are only claimed where one is declared ============


def test_a_routing_only_plan_declares_no_hashes():
    plan = _plan([
        ControlPlaneFoundationRequirement(
            id="foundation/l3_interface/cfg/routed/r1",
            kind="l3_interface", source_id="cfg/routed/r1",
        ),
        ControlPlaneFoundationRequirement(
            id="foundation/link/link/wan", kind="link", source_id="link/wan",
        ),
    ])

    assert derive_foundational_hashes(plan) == {}


def test_a_security_foundation_carries_the_supplied_plan_hash():
    plan = _plan([
        ControlPlaneFoundationRequirement(
            id="foundation/security/sec/acl", kind="security",
            source_id="sec/acl", source_hash="sec-hash",
        ),
    ])

    assert derive_foundational_hashes(
        plan, security_plan_hash="sec-hash",
    ) == {"sec/acl": "sec-hash"}


def test_a_security_hash_is_not_invented_when_none_is_supplied():
    plan = _plan([
        ControlPlaneFoundationRequirement(
            id="foundation/security/sec/acl", kind="security",
            source_id="sec/acl", source_hash="sec-hash",
        ),
    ])

    assert derive_foundational_hashes(plan) == {}


# ============ E. The preview agrees with the gate ============


def test_the_preview_reports_an_absent_foundation():
    plan = _plan([
        ControlPlaneFoundationRequirement(
            id="foundation/link/link/wan", kind="link", source_id="link/wan",
        ),
    ])

    unmet = unmet_foundations(plan, {})

    assert unmet == ["link:link/wan is absent, not verified."]


def test_the_preview_names_the_status_it_actually_found():
    plan = _plan([
        ControlPlaneFoundationRequirement(
            id="foundation/l3_interface/cfg/routed/r1",
            kind="l3_interface", source_id="cfg/routed/r1",
        ),
    ])

    unmet = unmet_foundations(
        plan, {"cfg/routed/r1": ActionExecutionStatus.UNOBSERVABLE},
    )

    assert unmet == [
        "l3_interface:cfg/routed/r1 is unobservable, not verified.",
    ]


def test_the_preview_is_silent_when_every_foundation_is_verified():
    plan = _plan([
        ControlPlaneFoundationRequirement(
            id="foundation/link/link/wan", kind="link", source_id="link/wan",
        ),
    ])

    assert unmet_foundations(
        plan, {"link/wan": ActionExecutionStatus.VERIFIED},
    ) == []


def test_a_declared_hash_that_does_not_match_is_reported():
    plan = _plan([
        ControlPlaneFoundationRequirement(
            id="foundation/security/sec/acl", kind="security",
            source_id="sec/acl", source_hash="expected",
        ),
    ])

    unmet = unmet_foundations(
        plan,
        {"sec/acl": ActionExecutionStatus.VERIFIED},
        {"sec/acl": "different"},
    )

    assert unmet == ["security:sec/acl source hash does not match."]


# ============ F. The preview cannot drift from the real gate ============


@pytest.mark.parametrize(
    ("statuses", "hashes"),
    [
        ({}, {}),
        ({"cfg/routed/r1": ActionExecutionStatus.VERIFIED}, {}),
        ({"cfg/routed/r1": ActionExecutionStatus.APPLIED}, {}),
        ({"cfg/routed/r1": ActionExecutionStatus.UNOBSERVABLE}, {}),
        (
            {"cfg/routed/r1": ActionExecutionStatus.VERIFIED,
             "sec/acl": ActionExecutionStatus.VERIFIED},
            {"sec/acl": "expected"},
        ),
        (
            {"cfg/routed/r1": ActionExecutionStatus.VERIFIED,
             "sec/acl": ActionExecutionStatus.VERIFIED},
            {"sec/acl": "wrong"},
        ),
    ],
)
def test_the_preview_agrees_with_the_applicator_gate(statuses, hashes):
    """`unmet_foundations` must accept exactly what the applicator accepts.

    A preview that disagreed with the gate would be worse than no preview: an
    orchestrator would dispatch believing it had cleared a check it had not.
    Compared against the real `_foundation_errors`, not against a copy of it.
    """
    from packet_tracer_mcp.application.use_cases.apply_control_plane import (
        ControlPlaneApplicator,
    )

    plan = _plan([
        ControlPlaneFoundationRequirement(
            id="foundation/l3_interface/cfg/routed/r1",
            kind="l3_interface", source_id="cfg/routed/r1",
        ),
        ControlPlaneFoundationRequirement(
            id="foundation/security/sec/acl", kind="security",
            source_id="sec/acl", source_hash="expected",
        ),
    ])

    gate_errors = ControlPlaneApplicator._foundation_errors(plan, statuses, hashes)
    preview = unmet_foundations(plan, statuses, hashes)

    assert bool(preview) == bool(gate_errors)


# ============ G. The acceptance-harness shape cannot be reproduced ============


def test_the_helper_exposes_no_way_to_supply_a_status_directly():
    """The defect was a caller-supplied mapping of VERIFIED.

    `derive_foundational_statuses` takes the typed requirement scope and only
    executed results, so the fabricated shape has no parameter to enter through.
    """
    import inspect

    parameters = set(
        inspect.signature(derive_foundational_statuses).parameters,
    )

    assert parameters == {"plan", "configuration_result", "physical_result"}


def test_a_full_reference_shape_verifies_only_what_was_observed():
    """One L3 interface verified, one unobservable, one link observed."""
    plan = _plan([
        ControlPlaneFoundationRequirement(
            id="foundation/l3_interface/cfg/routed/r1-lan",
            kind="l3_interface", source_id="cfg/routed/r1-lan",
        ),
        ControlPlaneFoundationRequirement(
            id="foundation/endpoint_address/cfg/endpoint/pc-a01",
            kind="endpoint_address", source_id="cfg/endpoint/pc-a01",
        ),
        ControlPlaneFoundationRequirement(
            id="foundation/link/link/wan-r1-r2",
            kind="link", source_id="link/wan-r1-r2",
        ),
    ])
    statuses = derive_foundational_statuses(
        plan,
        configuration_result=_config([
            _verification("cfg/routed/r1-lan", ActionExecutionStatus.VERIFIED),
            _verification("cfg/endpoint/pc-a01", ActionExecutionStatus.PARTIAL),
        ]),
        physical_result=_physical([
            _link_item("link/wan-r1-r2", PhysicalDeploymentItemStatus.OBSERVED),
        ]),
    )

    assert statuses["cfg/routed/r1-lan"] is ActionExecutionStatus.VERIFIED
    assert statuses["link/wan-r1-r2"] is ActionExecutionStatus.VERIFIED
    # The endpoint is only PARTIAL, because gateway and DNS are unobservable
    # on this backend. The gate must therefore still refuse this plan.
    assert unmet_foundations(plan, statuses) == [
        "endpoint_address:cfg/endpoint/pc-a01 is partial, not verified.",
    ]


# ============ H. E5 endpoint evidence resolves its exact E9 requirement ============


def _endpoint_plan(
    *, source_hash: str = "cfg-hash",
) -> ControlPlanePlan:
    return _plan([
        ControlPlaneFoundationRequirement(
            id="foundation/endpoint_address/cfg/endpoint-dhcp/pc-01",
            kind="endpoint_address",
            source_id="cfg/endpoint-dhcp/pc-01",
            source_hash=source_hash,
        ),
    ])


def test_fresh_e5_ipv4_and_netmask_satisfy_the_matching_e9_endpoint_requirement():
    """Catch treating the legitimate gateway/DNS ceiling as an E9 failure."""
    plan = _endpoint_plan()

    statuses = derive_foundational_statuses(
        plan,
        configuration_result=_config([_endpoint_verification()]),
    )

    assert statuses == {
        "cfg/endpoint-dhcp/pc-01": ActionExecutionStatus.VERIFIED,
    }
    assert derive_foundational_hashes(plan) == {
        "cfg/endpoint-dhcp/pc-01": "cfg-hash",
    }


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("stale", ActionExecutionStatus.PARTIAL),
        ("ipv4_failed", ActionExecutionStatus.PARTIAL),
        ("netmask_failed", ActionExecutionStatus.PARTIAL),
        ("channel_absent", ActionExecutionStatus.PARTIAL),
        ("observation_absent", ActionExecutionStatus.PARTIAL),
        ("convergence_status_mismatch", ActionExecutionStatus.PARTIAL),
    ],
)
def test_endpoint_requirement_stays_closed_without_exact_fresh_core_evidence(
    mutation: str,
    expected: ActionExecutionStatus,
):
    """Catch broad promotion of PARTIAL or trust in an incomplete E5 row."""
    evidence = _endpoint_verification()
    if mutation == "stale":
        evidence.fresh_evidence = False
    elif mutation == "ipv4_failed":
        evidence.fields["ipv4"] = FieldVerificationStatus.FAILED
    elif mutation == "netmask_failed":
        evidence.fields["netmask"] = FieldVerificationStatus.FAILED
    elif mutation == "channel_absent":
        evidence.convergence.details["last_observation"]["address_channel"] = False
    elif mutation == "observation_absent":
        evidence.convergence = None
    elif mutation == "convergence_status_mismatch":
        evidence.convergence.final_status = ActionExecutionStatus.FAILED

    statuses = derive_foundational_statuses(
        _endpoint_plan(),
        configuration_result=_config([evidence]),
    )

    assert statuses["cfg/endpoint-dhcp/pc-01"] is expected


def test_endpoint_evidence_is_scoped_to_the_requirement_and_configuration_identity():
    """Catch evidence reuse across an action id or configuration hash boundary."""
    plan = _endpoint_plan()
    wrong_action = derive_foundational_statuses(
        plan,
        configuration_result=_config([
            _endpoint_verification("cfg/endpoint-dhcp/other"),
        ]),
    )
    wrong_configuration = _config([_endpoint_verification()])
    wrong_configuration.config_semantic_hash = "other-cfg-hash"

    assert wrong_action == {
        "cfg/endpoint-dhcp/other": ActionExecutionStatus.PARTIAL,
    }
    assert "cfg/endpoint-dhcp/pc-01" not in wrong_action
    assert derive_foundational_statuses(
        plan,
        configuration_result=wrong_configuration,
    )["cfg/endpoint-dhcp/pc-01"] is ActionExecutionStatus.PARTIAL


def test_non_endpoint_partial_is_not_promoted_by_endpoint_shaped_fields():
    """Catch a global PARTIAL-to-VERIFIED translation."""
    plan = _plan([
        ControlPlaneFoundationRequirement(
            id="foundation/l3_interface/cfg/endpoint-dhcp/pc-01",
            kind="l3_interface",
            source_id="cfg/endpoint-dhcp/pc-01",
        ),
    ])

    statuses = derive_foundational_statuses(
        plan,
        configuration_result=_config([_endpoint_verification()]),
    )

    assert statuses["cfg/endpoint-dhcp/pc-01"] is ActionExecutionStatus.PARTIAL


def test_control_plane_scope_does_not_hide_verified_foundations_from_voice():
    """Catch dropping E5 rows that another downstream applicator consumes."""
    statuses = derive_foundational_statuses(
        _endpoint_plan(),
        configuration_result=_config([
            _verification("cfg/access/phone-01", ActionExecutionStatus.VERIFIED),
            _verification("cfg/dhcp/voice", ActionExecutionStatus.VERIFIED),
        ]),
    )

    assert statuses == {
        "cfg/access/phone-01": ActionExecutionStatus.VERIFIED,
        "cfg/dhcp/voice": ActionExecutionStatus.VERIFIED,
    }


def test_endpoint_hash_is_not_projected_across_a_configuration_hash_mismatch():
    """Catch copying a requirement's arbitrary source hash into E9 authority."""
    plan = _endpoint_plan(source_hash="other-cfg-hash")

    assert derive_foundational_hashes(plan) == {}
