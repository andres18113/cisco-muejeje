"""SP-1 SP1-03 at dispatch: later traffic waits until the cold request was sent.

Review findings on 26ee053/9175fd6: a client's DNS could run after its
HTTP-by-address request was blocked, and a cross-service prerequisite could
dangle when an optional service was excluded. The rule now lives in the
applicator and reads only the selected plan: a client's DNS, negative control
and host-name rows wait until each of its selected HTTP-by-address requests
was actually dispatched, and a plan with no such request holds nothing.
"""

from __future__ import annotations

from test_service_application import (
    NO_READINESS,
    FakeServiceRuntime,
    _compiled,
    _foundation,
)

from packet_tracer_mcp.application.use_cases.apply_services import ServiceApplicator
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceVerificationKind,
)

_LATER = {
    ServiceVerificationKind.DNS_RESOLUTION,
    ServiceVerificationKind.DNS_NEGATIVE_CONTROL,
    ServiceVerificationKind.HTTP_BY_HOSTNAME,
}


def _apply(plan, capabilities, runtime, *, readiness=NO_READINESS):
    """Apply the plan; without a readiness declaration HTTP is never sent."""
    extra = {} if readiness is None else {"operational_readiness": readiness}
    return ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundation(plan),
        capabilities=capabilities,
        **extra,
    )


def test_a_blocked_cold_request_holds_every_later_request_of_that_client():
    """The fetch never runs; no DNS, negative or host-name request follows it."""
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()

    result = _apply(plan, capabilities, runtime, readiness=None)

    rows = {item.expectation_id: item for item in result.verification_results}
    kinds = {item.id: item.kind for item in plan.verification_expectations}
    assert any(
        kinds[key] is ServiceVerificationKind.HTTP_FETCH
        and row.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        for key, row in rows.items()
    )
    later = [row for key, row in rows.items() if kinds[key] in _LATER]
    assert later
    for row in later:
        assert row.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
    # The first held request names why: its client's cold request never ran.
    resolution = next(
        row
        for key, row in rows.items()
        if kinds[key] is ServiceVerificationKind.DNS_RESOLUTION
    )
    assert "cold_request_not_sent" in resolution.message
    sent = {getattr(item, "id", item) for item in getattr(runtime, "verified", [])}
    assert not any(kinds.get(key) in _LATER for key in sent)


def test_a_plan_without_a_cold_request_holds_no_dns():
    """An excluded or absent HTTP service leaves nothing to wait for."""
    plan, capabilities = _compiled()
    plan.verification_expectations = [
        item
        for item in plan.verification_expectations
        if item.kind
        not in {
            ServiceVerificationKind.HTTP_FETCH,
            ServiceVerificationKind.HTTP_BY_HOSTNAME,
        }
    ]
    runtime = FakeServiceRuntime()

    result = _apply(plan, capabilities, runtime)

    dns = [
        row
        for row in result.verification_results
        if "verify-dns/" in row.expectation_id
    ]
    assert dns
    assert all(row.status is ActionExecutionStatus.VERIFIED for row in dns)


def test_a_negative_with_no_positive_is_held_by_the_blocked_cold_request():
    """A record-less DNS service: its negative still waits for the cold fetch."""
    plan, capabilities = _compiled()
    positives = {
        item.id
        for item in plan.verification_expectations
        if item.kind is ServiceVerificationKind.DNS_RESOLUTION
    }
    plan.verification_expectations = [
        item.model_copy(
            update={
                "depends_on": [d for d in item.depends_on if d not in positives],
                "verification_prerequisites": [
                    prerequisite
                    for prerequisite in item.verification_prerequisites
                    if prerequisite.reference_id not in positives
                ],
            }
        )
        for item in plan.verification_expectations
        if item.id not in positives
        and item.kind is not ServiceVerificationKind.HTTP_BY_HOSTNAME
    ]

    result = _apply(plan, capabilities, FakeServiceRuntime(), readiness=None)

    negative = next(
        row
        for row in result.verification_results
        if "verify-dns-negative/" in row.expectation_id
    )
    assert negative.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
    assert "cold_request_not_sent" in negative.message


def _http_answer(runtime, *, go_result):
    """Make the runtime's HTTP-by-address read UNKNOWN, with or without a start."""
    original = runtime.verify

    def verify(expectation):
        row = original(expectation)
        if expectation.kind is not ServiceVerificationKind.HTTP_FETCH:
            return row
        observed = {} if go_result is None else {"go_result": go_result}
        return row.model_copy(
            update={
                "status": ActionExecutionStatus.UNKNOWN,
                "observed": observed,
                "cause": "client_go_false" if go_result is False else "incomplete",
            }
        )

    runtime.verify = verify


def test_a_cold_request_that_never_started_holds_the_clients_dns():
    """Review finding: UNKNOWN with `client_go_false` is not a sent request."""
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()
    _http_answer(runtime, go_result=False)

    result = _apply(plan, capabilities, runtime)

    dns = [
        row
        for row in result.verification_results
        if "verify-dns/" in row.expectation_id
    ]
    assert dns
    for row in dns:
        assert row.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        assert "cold_request_not_sent" in row.message


def test_a_cold_request_that_started_but_read_unknown_releases_dns():
    """`go()` returned true: the request left, so later traffic may follow."""
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()
    _http_answer(runtime, go_result=True)

    result = _apply(plan, capabilities, runtime)

    dns = [
        row
        for row in result.verification_results
        if "verify-dns/" in row.expectation_id
    ]
    assert dns
    assert all(row.status is ActionExecutionStatus.VERIFIED for row in dns)
