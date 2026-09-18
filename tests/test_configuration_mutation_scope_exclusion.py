"""P-E5-2: applying part of a plan, and saying so.

A services run needs the endpoint, access-port and VLAN actions of the devices
it touches, and nothing else. Before this, narrowing the scope meant supplying
a retained result for every other action, which a first application does not
have: the only ways to satisfy the old contract were to fabricate retained
successes or to hand the applicator a shrunken copy of the plan whose hash no
longer matched anything. Both are ways of lying about what ran.

Exclusion is the third answer. An excluded action is rendered nowhere,
dispatched nowhere and verified nowhere, and it says exactly that:
SKIPPED/OUT_OF_SCOPE. These tests hold the partition invariants that keep it
from becoming a way to hide a failure.
"""

from __future__ import annotations

from test_configuration_application import (
    FakeConfigurationRuntime,
    _compiled,
    _supported_capabilities,
)

from packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
)

_ENDPOINT_KINDS = {
    ConfigurationActionType.SET_ENDPOINT_STATIC,
    ConfigurationActionType.SET_ENDPOINT_DHCP,
}


def _closure(plan, action_ids: set[str]) -> set[str]:
    """Close a set over depends_on and apply_dependencies, as the product does."""
    by_id = {item.id: item for item in plan.actions}
    frontier = set(action_ids)
    closed: set[str] = set()
    while frontier:
        identifier = frontier.pop()
        if identifier in closed or identifier not in by_id:
            continue
        closed.add(identifier)
        action = by_id[identifier]
        frontier |= {*action.depends_on, *action.apply_dependencies}
    return closed


def _endpoint_closure(plan) -> set[str]:
    return _closure(
        plan,
        {item.id for item in plan.actions if item.action_type in _ENDPOINT_KINDS},
    )


def _apply(plan, topology, **kwargs):
    runtime = FakeConfigurationRuntime(topology)
    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
        **kwargs,
    )
    return runtime, result


def test_the_default_api_still_applies_the_whole_plan():
    """Omitting the parameter must leave the previous contract untouched."""
    topology, plan = _compiled()

    runtime, result = _apply(plan, topology)

    dispatched = {item for batch in runtime.apply_calls for item in batch}
    assert dispatched == {item.id for item in plan.actions}
    assert result.excluded_action_ids == []
    assert result.retained_action_ids == []


def test_a_first_application_needs_no_fabricated_retained_results():
    """Exactly the closure is dispatched; the rest is SKIPPED/OUT_OF_SCOPE."""
    topology, plan = _compiled()
    scope = _endpoint_closure(plan)
    excluded = {item.id for item in plan.actions} - scope
    assert excluded, "the fixture must have actions outside the endpoint closure"

    runtime, result = _apply(
        plan,
        topology,
        mutation_action_ids=scope,
        excluded_action_ids=excluded,
    )

    dispatched = {item for batch in runtime.apply_calls for item in batch}
    assert dispatched == scope
    rows = {item.action_id: item for item in result.action_results}
    for identifier in excluded:
        assert rows[identifier].status is ActionExecutionStatus.SKIPPED
        assert rows[identifier].failure_code is ConfigurationFailureCode.OUT_OF_SCOPE
    assert set(result.excluded_action_ids) == excluded
    assert result.retained_action_ids == []
    assert result.status is not ConfigurationApplicationStatus.FAILED


def test_the_three_lists_account_for_every_identity_exactly_once():
    """Mutated, retained and excluded partition the plan, with no overlap."""
    topology, plan = _compiled()
    scope = _endpoint_closure(plan)
    excluded = {item.id for item in plan.actions} - scope

    _runtime, result = _apply(
        plan,
        topology,
        mutation_action_ids=scope,
        excluded_action_ids=excluded,
    )

    mutated = set(result.mutation_action_ids)
    retained = set(result.retained_action_ids)
    out_of_scope = set(result.excluded_action_ids)
    assert mutated | retained | out_of_scope == {item.id for item in plan.actions}
    assert not mutated & retained
    assert not mutated & out_of_scope
    assert not retained & out_of_scope


def test_an_excluded_action_is_never_verified_either():
    """Its action did not run, so there is nothing to read back."""
    topology, plan = _compiled()
    scope = _endpoint_closure(plan)
    excluded = {item.id for item in plan.actions} - scope

    runtime, result = _apply(
        plan,
        topology,
        mutation_action_ids=scope,
        excluded_action_ids=excluded,
    )

    verified_ids = {item for batch in runtime.verify_calls for item in batch}
    excluded_expectations = {
        item.id for item in plan.verification_expectations if item.action_id in excluded
    }
    assert excluded_expectations
    assert not excluded_expectations & verified_ids
    rows = {item.expectation_id: item for item in result.verification_results}
    for identifier in excluded_expectations:
        assert rows[identifier].status is ActionExecutionStatus.SKIPPED


def test_a_foreign_id_in_either_set_refuses_before_any_effect():
    """An id that is not in the plan grants nothing and stops the run."""
    topology, plan = _compiled()
    scope = _endpoint_closure(plan)
    excluded = {item.id for item in plan.actions} - scope

    runtime, result = _apply(
        plan,
        topology,
        mutation_action_ids=scope,
        excluded_action_ids=excluded | {"not-an-action-of-this-plan"},
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.DEPENDENCY_BLOCKED
    assert runtime.apply_calls == []
    assert any("outside the typed plan" in item for item in result.preflight_errors)


def test_an_action_cannot_be_mutated_and_excluded_at_once():
    """The two sets are disjoint or the scope is refused."""
    topology, plan = _compiled()
    scope = _endpoint_closure(plan)
    overlapping = next(iter(scope))

    runtime, result = _apply(
        plan,
        topology,
        mutation_action_ids=scope,
        excluded_action_ids={overlapping},
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert runtime.apply_calls == []
    assert any(
        "mutated and excluded at once" in item for item in result.preflight_errors
    )


def test_a_mutated_action_may_not_depend_on_an_excluded_one():
    """It could never establish its effect, and that is knowable beforehand."""
    topology, plan = _compiled()
    scope = _endpoint_closure(plan)
    by_id = {item.id: item for item in plan.actions}
    dependent = next(
        item
        for item in plan.actions
        if item.id in scope and any(dep in scope for dep in item.depends_on)
    )
    prerequisite = next(dep for dep in dependent.depends_on if dep in scope)
    assert prerequisite in by_id

    runtime, result = _apply(
        plan,
        topology,
        mutation_action_ids=scope - {prerequisite},
        excluded_action_ids=(
            ({item.id for item in plan.actions} - scope) | {prerequisite}
        ),
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert runtime.apply_calls == []
    assert any("depend on excluded actions" in item for item in result.preflight_errors)


def test_exclusions_without_an_explicit_mutation_scope_are_refused():
    """Narrowing has to be stated on both sides or not at all."""
    topology, plan = _compiled()

    runtime, result = _apply(
        plan,
        topology,
        excluded_action_ids={plan.actions[0].id},
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert runtime.apply_calls == []
    assert any(
        "require an explicit mutation action scope" in item
        for item in result.preflight_errors
    )


def test_an_excluded_action_is_never_rendered_for_the_runtime():
    """Not merely undispatched: the applicator never builds the payload."""
    topology, plan = _compiled()
    scope = _endpoint_closure(plan)
    excluded = {item.id for item in plan.actions} - scope

    runtime, _result = _apply(
        plan,
        topology,
        mutation_action_ids=scope,
        excluded_action_ids=excluded,
    )

    rendered = {action.id for batch in runtime.action_batches for action in batch}
    assert not rendered & excluded
