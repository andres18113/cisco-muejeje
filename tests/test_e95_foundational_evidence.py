"""Foundational evidence must be derived, never asserted.

The University Topology Acceptance satisfied the control-plane foundational
gate with a comprehension over the gate's own inputs. These tests exist to make
that shape impossible to reach again through the production helper: every path
that could mint a VERIFIED it did not observe is pinned here.
"""
from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.foundational_evidence import (
    derive_foundational_hashes,
    derive_foundational_statuses,
    unmet_foundations,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    VerificationResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneFoundationRequirement,
    ControlPlanePlan,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import (
    ApplicationExecutionJournal,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
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


# ============ A. VERIFIED is copied from evidence, never minted ============


def test_a_verified_configuration_foundation_comes_from_its_verification():
    statuses = derive_foundational_statuses(
        configuration_result=_config([
            _verification("cfg/routed/r1-lan", ActionExecutionStatus.VERIFIED),
        ]),
    )

    assert statuses == {"cfg/routed/r1-lan": ActionExecutionStatus.VERIFIED}


def test_no_evidence_at_all_yields_no_statuses():
    """The gate must refuse, and refusing is what an empty mapping does."""
    assert derive_foundational_statuses() == {}


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
        physical_result=_physical([_link_item("link/a", physical)]),
    )

    assert statuses["link/a"] is expected
    assert statuses["link/a"] is not ActionExecutionStatus.VERIFIED


def test_a_non_link_physical_item_is_not_a_foundation():
    """Device foundations do not exist; only links are keyed by a plan id."""
    statuses = derive_foundational_statuses(
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
        configuration_result=_config([
            _verification("cfg/a", ActionExecutionStatus.FAILED),
            _verification("cfg/a", ActionExecutionStatus.VERIFIED),
        ]),
    )

    assert duplicated["cfg/a"] is ActionExecutionStatus.FAILED


def test_an_empty_source_id_is_never_recorded():
    statuses = derive_foundational_statuses(
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
    from src.packet_tracer_mcp.application.use_cases.apply_control_plane import (
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

    `derive_foundational_statuses` takes only executed results, so the
    fabricated shape has no parameter to enter through.
    """
    import inspect

    parameters = set(
        inspect.signature(derive_foundational_statuses).parameters,
    )

    assert parameters == {"configuration_result", "physical_result"}


def test_a_full_reference_shape_verifies_only_what_was_observed():
    """One L3 interface verified, one unobservable, one link observed."""
    statuses = derive_foundational_statuses(
        configuration_result=_config([
            _verification("cfg/routed/r1-lan", ActionExecutionStatus.VERIFIED),
            _verification("cfg/endpoint/pc-a01", ActionExecutionStatus.PARTIAL),
        ]),
        physical_result=_physical([
            _link_item("link/wan-r1-r2", PhysicalDeploymentItemStatus.OBSERVED),
        ]),
    )
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

    assert statuses["cfg/routed/r1-lan"] is ActionExecutionStatus.VERIFIED
    assert statuses["link/wan-r1-r2"] is ActionExecutionStatus.VERIFIED
    # The endpoint is only PARTIAL, because gateway and DNS are unobservable
    # on this backend. The gate must therefore still refuse this plan.
    assert unmet_foundations(plan, statuses) == [
        "endpoint_address:cfg/endpoint/pc-a01 is partial, not verified.",
    ]
