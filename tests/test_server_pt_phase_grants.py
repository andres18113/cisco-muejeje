"""Child phase grants cannot widen the activated C31 target or cost ceiling."""

from __future__ import annotations

from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
    prepare_server_pt_commissioning,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    RepositoryIdentity,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_campaign_authority import (
    ExactCiEvidence,
)

ATTEMPT = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def test_setup_grant_is_derived_from_the_full_bundle_and_fixed_phase_caps():
    """Changing a target or allowance is not another valid grant for this SHA."""
    from packet_tracer_mcp.application.use_cases.server_pt_phase_grant import (
        derive_server_pt_phase_grant,
        phase_grant_findings,
    )

    bundle = prepare_server_pt_commissioning(30, "COLD_HTTP_" + ATTEMPT)
    source = RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head="a" * 40,
        tree="b" * 40,
        clean=True,
        upstream_head="a" * 40,
    )
    process = DiagnosticLifecycleObservation(
        process_id=123,
        process_path="C:\\Program Files\\Cisco Packet Tracer\\PacketTracer.exe",
        process_incarnation="2026-09-23T00:00:00Z",
        product_version="9.0.1.0858",
    )
    ci = ExactCiEvidence(
        run_id=42, head_sha="a" * 40, url="https://example.test/42", jobs=("six",)
    )

    grant = derive_server_pt_phase_grant(
        "setup",
        ATTEMPT,
        source,
        process,
        ci,
        bundle_sha256="c" * 64,
        prequalification_sha256="d" * 64,
        bundle=bundle,
    )

    assert grant.max_operations == 4750
    assert grant.max_seconds == 1500
    assert len(grant.device_targets) == 35
    assert len(grant.link_targets) == 36
    assert len(grant.configuration_actions) == 14
    assert grant.deployment_id == "server-pt-c31-" + ATTEMPT
    assert phase_grant_findings(
        grant.model_copy(update={"max_operations": 5001}),
        "setup",
        ATTEMPT,
        source,
        process,
        ci,
        bundle_sha256="c" * 64,
        prequalification_sha256="d" * 64,
        bundle=bundle,
    ) == ("phase_grant_mismatch",)


def test_distinct_attempts_with_the_same_prefix_have_distinct_deployments():
    """A new 32-hex attempt cannot alias an earlier manifest or service history."""
    from packet_tracer_mcp.application.use_cases.server_pt_phase_grant import (
        derive_server_pt_phase_grant,
    )

    source = RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head="a" * 40,
        tree="b" * 40,
        clean=True,
        upstream_head="a" * 40,
    )
    process = DiagnosticLifecycleObservation(
        process_id=123,
        process_path="C:\\PacketTracer.exe",
        process_incarnation="2026-09-23T00:00:00Z",
        product_version="9.0.1.0858",
    )
    ci = ExactCiEvidence(42, "a" * 40, "https://example.test/42", ("six",))
    other = ATTEMPT[:12] + "f" * 20
    first = derive_server_pt_phase_grant(
        "prequalification", ATTEMPT, source, process, ci
    )
    second = derive_server_pt_phase_grant(
        "prequalification", other, source, process, ci
    )

    assert first.deployment_id != second.deployment_id
