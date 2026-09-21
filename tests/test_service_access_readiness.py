"""The HTTP forwarding prerequisite: derivation, gate and the real composition.

Three levels, deliberately separate. The derivation is pure and is proved
against a plan whose access ports, VLAN and endpoint sets are known. The gate
is proved against a backend whose timer advances with simulated time rather
than with the number of queries, so "forwarding arrives later" is a statement
about time and not about call counts. The composition level then proves the
one thing neither can: that no HTTP request is dispatched before an admitted
sample, through `apply_enterprise_services` and the real applicator.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
from service_entry_fixture import (
    BACKEND_VERSION,
    DEPLOYMENT_ID,
    EndpointObserver,
    ForwardingBackend,
    IsolationPreflight,
    ManifestStore,
    RecordingConfigurationRuntime,
    RecordingServiceRuntime,
    SimulatedClock,
    deployment_manifest,
    intent_json,
)

from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from packet_tracer_mcp.application.use_cases.apply_services import ServiceApplicator
from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
    ReadinessGateConsumed,
    ReadinessNotRequired,
    ServiceAccessReadinessGate,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
)
from packet_tracer_mcp.domain.enterprise.models.forwarding import (
    AccessForwardingObservation,
    AccessForwardingRow,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    SourceTreeIdentity,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
)
from packet_tracer_mcp.domain.enterprise.services.service_access_readiness import (
    ACCESS_PORT_ACTION_TYPE,
    CAUSE_ANSWER_DOES_NOT_MATCH_REQUEST,
    CAUSE_ENDPOINT_NOT_ON_ACCESS_PORT,
    CAUSE_OBSERVER_UNAVAILABLE,
    CAUSE_PATH_NOT_SINGLE_SEGMENT,
    CAUSE_READINESS_NOT_DECLARED,
    CAUSE_SAMPLE_BUDGET_EXHAUSTED,
    READINESS_ADMITTED,
    READINESS_NOT_OBSERVED,
    READINESS_REFUSED,
    derive_access_readiness_plan,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)

SWITCH = "sw-acc-hq-default-01"
SWITCH_NAME = "HQ-DEFAULT-ACCESS-SW-01"
SERVER = "endpoint/hq/default/server/001"
PC1 = "endpoint/hq/default/user_pc/001"
PC2 = "endpoint/hq/default/user_pc/002"
HTTP_KINDS = frozenset(
    {
        ServiceVerificationKind.HTTP_FETCH.value,
        ServiceVerificationKind.HTTPS_FETCH.value,
        ServiceVerificationKind.HTTP_BY_HOSTNAME.value,
    }
)


class _Action:
    """One compiled access-port action, reduced to what derivation reads."""

    def __init__(
        self,
        interface: str,
        endpoints: tuple[str, ...],
        *,
        vlan: int = 10,
        device_id: str = SWITCH,
        device_name: str = SWITCH_NAME,
    ) -> None:
        self.interface = interface
        self.data_vlan_id = vlan
        self.device_id = device_id
        self.device_name = device_name
        self.endpoint_ids = list(endpoints)
        #: Derivation refuses anything that is not a declared access port, so
        #: the stand-in has to declare what the compiler declares.
        self.action_type = ConfigurationActionType.CONFIGURE_ACCESS_PORT


class _Expectation:
    """One verification expectation, reduced to what derivation reads."""

    def __init__(
        self,
        identifier: str,
        kind: ServiceVerificationKind,
        *,
        client: str = "",
        host: str = SERVER,
        service_id: str = "service/hq/lab-web",
    ) -> None:
        self.id = identifier
        self.kind = kind
        self.client_device_id = client
        self.host_device_id = host
        self.service_id = service_id


def _plan(actions: Any = None, expectations: Any = None):
    """Derive one readiness plan from the two-client single-segment fixture."""
    return derive_access_readiness_plan(
        configuration_actions=(
            actions
            if actions is not None
            else [
                _Action("FastEthernet1/1", (PC1,)),
                _Action("FastEthernet1/2", (PC2,)),
                _Action("FastEthernet1/3", (SERVER,)),
            ]
        ),
        verification_expectations=(
            expectations
            if expectations is not None
            else [
                _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1),
                _Expectation("http-2", ServiceVerificationKind.HTTP_FETCH, client=PC2),
            ]
        ),
    )


def _gate(plan, backend: ForwardingBackend | None = None, **kwargs: Any):
    """Bind one gate to a timed backend and the fixture switch name."""
    observer = backend if backend is not None else ForwardingBackend()
    return ServiceAccessReadinessGate(
        plan,
        observer,
        clock=observer.clock if observer is not None else SimulatedClock(),
        device_names={SWITCH: SWITCH_NAME},
        **kwargs,
    )


# -- B1: the requirement is derived from the plan ------------------------------


def test_required_ports_and_vlan_come_from_the_compiled_plan():
    """Both ends of each request are required, grouped by switch and VLAN."""
    plan = _plan()

    assert len(plan.requirements) == 1
    requirement = plan.requirements[0]
    assert requirement.key == (SWITCH, 10)
    assert requirement.switch_device_name == SWITCH_NAME
    # Plan order, not expectation order, so the report is stable.
    assert requirement.interfaces == (
        "FastEthernet1/1",
        "FastEthernet1/2",
        "FastEthernet1/3",
    )
    assert [item.expectation_id for item in requirement.dependents] == [
        "http-1",
        "http-2",
    ]
    assert requirement.dependents[0].interfaces == (
        "FastEthernet1/1",
        "FastEthernet1/3",
    )
    assert requirement.dependents[1].interfaces == (
        "FastEthernet1/2",
        "FastEthernet1/3",
    )


def test_derivation_ignores_device_names_and_interface_order():
    """Identity is the semantic device id, never a name or a port number."""
    plan = _plan(
        actions=[
            _Action("FastEthernet1/9", (SERVER,), device_name="ZZZ-UNRELATED-NAME"),
            _Action("FastEthernet1/4", (PC1,), device_name="ZZZ-UNRELATED-NAME"),
        ],
        expectations=[
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1)
        ],
    )

    requirement = plan.requirements[0]
    assert requirement.switch_device_id == SWITCH
    assert set(requirement.dependents[0].interfaces) == {
        "FastEthernet1/9",
        "FastEthernet1/4",
    }


def test_two_plan_rows_naming_one_interface_are_one_interface_to_observe():
    """A duplicated placement must not make the report ask about a port twice."""
    plan = _plan(
        actions=[
            _Action("FastEthernet1/1", (PC1,)),
            _Action("FastEthernet1/1", (PC1,)),
            _Action("FastEthernet1/3", (SERVER,)),
        ],
        expectations=[
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1)
        ],
    )

    requirement = plan.requirements[0]
    assert requirement.interfaces == ("FastEthernet1/1", "FastEthernet1/3")
    assert requirement.dependents[0].interfaces == (
        "FastEthernet1/1",
        "FastEthernet1/3",
    )


def test_only_http_family_kinds_are_gated():
    """A DNS or direct-state expectation is not an HTTP request and is not gated."""
    plan = _plan(
        expectations=[
            _Expectation("dns-1", ServiceVerificationKind.DNS_RESOLUTION, client=PC1),
            _Expectation(
                "direct-1", ServiceVerificationKind.DIRECT_SERVICE_STATE, client=""
            ),
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1),
            _Expectation("https-1", ServiceVerificationKind.HTTPS_FETCH, client=PC1),
            _Expectation(
                "name-1", ServiceVerificationKind.HTTP_BY_HOSTNAME, client=PC1
            ),
        ]
    )

    assert set(plan.gated_expectation_ids) == {"http-1", "https-1", "name-1"}


def test_an_endpoint_the_plan_never_placed_is_named_not_dropped():
    """A path whose ports cannot be identified is not a path anybody observed."""
    plan = _plan(
        actions=[_Action("FastEthernet1/1", (PC1,))],
        expectations=[
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1)
        ],
    )

    dependent = plan.requirements[0].dependents[0]
    assert dependent.unresolved_endpoint_ids == (SERVER,)

    result = _gate(plan).decide("http-1")
    assert result is not None
    assert result.admitted is False
    assert result.cause.startswith(CAUSE_ENDPOINT_NOT_ON_ACCESS_PORT)


def test_a_path_spanning_two_switches_is_not_a_single_segment_path():
    """No one grouped sample describes a request that crosses two switches."""
    plan = _plan(
        actions=[
            _Action("FastEthernet1/1", (PC1,)),
            _Action(
                "FastEthernet2/1",
                (SERVER,),
                device_id="sw-acc-hq-default-02",
                device_name="HQ-DEFAULT-ACCESS-SW-02",
            ),
        ],
        expectations=[
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1)
        ],
    )

    assert plan.requirements == ()
    assert [item.expectation_id for item in plan.unplaced] == ["http-1"]

    gate = _gate(plan)
    result = gate.decide("http-1")
    assert result is not None and result.admitted is False
    assert result.cause == CAUSE_PATH_NOT_SINGLE_SEGMENT
    assert gate.observations == []


# -- B4, B8, B10: grouping, the positive control and the independent timer -----


def test_one_grouped_query_serves_every_client_of_the_group():
    """Four dependents on one switch and VLAN cost one observation, not four."""
    plan = _plan(
        expectations=[
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1),
            _Expectation("http-2", ServiceVerificationKind.HTTP_FETCH, client=PC2),
            _Expectation(
                "name-1", ServiceVerificationKind.HTTP_BY_HOSTNAME, client=PC1
            ),
            _Expectation(
                "name-2", ServiceVerificationKind.HTTP_BY_HOSTNAME, client=PC2
            ),
        ]
    )
    backend = ForwardingBackend()
    gate = _gate(plan, backend)

    for identifier in ("http-1", "http-2", "name-1", "name-2"):
        decision = gate.decide(identifier)
        assert decision is not None and decision.admitted is True

    assert len(backend.calls) == 1
    device_name, vlan_id, interfaces = backend.calls[0]
    assert (device_name, vlan_id) == (SWITCH_NAME, 10)
    assert set(interfaces) == {
        "FastEthernet1/1",
        "FastEthernet1/2",
        "FastEthernet1/3",
    }


def test_an_already_forwarding_path_is_admitted_without_waiting():
    """The positive control: a first sample in FWD admits and records one sample."""
    backend = ForwardingBackend(forwards_at=0.0)
    gate = _gate(_plan(), backend)

    assert gate.decide("http-1").admitted is True

    rows = gate.rows()
    assert len(rows) == 1
    assert rows[0]["status"] == READINESS_ADMITTED
    assert rows[0]["dimension"] == "NONE"
    assert rows[0]["sample"]["rows"][0]["state"] == "FWD"
    assert backend.clock.now == 0.0


def test_the_backend_timer_advances_with_time_not_with_queries():
    """Repeated observation at one instant returns the same non-forwarding read."""
    backend = ForwardingBackend(forwards_at=4.0)

    first = backend.observe_access_forwarding(SWITCH_NAME, 10, ["FastEthernet1/1"])
    second = backend.observe_access_forwarding(SWITCH_NAME, 10, ["FastEthernet1/1"])
    assert [row.state for row in first.rows] == ["LIS"]
    assert [row.state for row in second.rows] == ["LIS"]

    backend.clock.advance(4.0)
    third = backend.observe_access_forwarding(SWITCH_NAME, 10, ["FastEthernet1/1"])
    assert [row.state for row in third.rows] == ["FWD"]


# -- B5, B6, B9: every refusal is named, and none of them passes ---------------


def test_persistent_non_forwarding_refuses_with_per_client_coverage():
    """LIS is a real sample that grants nothing, reported per dependent."""
    backend = ForwardingBackend(forwards_at=None)
    gate = _gate(_plan(), backend)

    assert gate.decide("http-1").admitted is False
    assert gate.decide("http-2").admitted is False

    row = gate.rows()[0]
    assert row["status"] == READINESS_REFUSED
    assert row["dimension"] == "NON_FORWARDING"
    assert row["sample"]["admitted"] is False
    coverage = {item["client_device_id"]: item for item in row["dependents"]}
    assert set(coverage) == {PC1, PC2}
    for item in coverage.values():
        assert item["admitted"] is False
        assert item["cause"].startswith("NON_FORWARDING:")
        assert item["kind"] in HTTP_KINDS
    # One grouped query, even though both dependents asked.
    assert len(backend.calls) == 1


@pytest.mark.parametrize(
    ("overrides", "dimension"),
    [
        ({"executed": False}, "EXECUTION"),
        ({"fresh_output_observed": False}, "FRESHNESS"),
        ({"output_complete": False}, "COMPLETENESS"),
        ({"observed_device_name": "SOMEONE-ELSE"}, "IDENTITY"),
        ({"device_identity_provenance": "ambiguous"}, "IDENTITY"),
        ({"vlan_present": False}, "VLAN_INSTANCE"),
        ({"missing_interfaces": frozenset({"FastEthernet1/3"})}, "MISSING_INTERFACE"),
        (
            {"duplicated_interfaces": frozenset({"FastEthernet1/3"})},
            "AMBIGUOUS_INTERFACE",
        ),
    ],
)
def test_a_foreign_or_partial_sample_never_authorizes(
    overrides: dict[str, Any], dimension: str
):
    """Each dimension refuses on its own, and a forwarding state never rescues it."""
    backend = ForwardingBackend(forwards_at=0.0, **overrides)
    gate = _gate(_plan(), backend)

    assert gate.decide("http-1").admitted is False
    assert gate.rows()[0]["dimension"] == dimension


def test_readiness_cannot_be_switched_off():
    """A composition with no observer blocks rather than passing through."""
    plan = _plan()
    gate = ServiceAccessReadinessGate(
        plan, None, clock=SimulatedClock(), device_names={SWITCH: SWITCH_NAME}
    )

    decision = gate.decide("http-1")
    assert decision is not None and decision.admitted is False
    assert decision.cause == CAUSE_OBSERVER_UNAVAILABLE
    assert gate.rows()[0]["status"] == READINESS_NOT_OBSERVED


def test_an_observer_that_raised_observed_nothing():
    """A raised read is the absence of a sample, not a negative one."""
    backend = ForwardingBackend(raises=RuntimeError("channel dropped"))
    gate = _gate(_plan(), backend)

    decision = gate.decide("http-1")
    assert decision is not None and decision.admitted is False
    assert decision.cause == "readiness_observation_failed:RuntimeError"
    assert gate.rows()[0]["sample"] == {}


def test_the_total_budget_is_checked_before_the_next_group_is_observed():
    """Bounded waits cannot be multiplied into an unbounded run."""
    plan = _plan(
        actions=[
            _Action("FastEthernet1/1", (PC1,), vlan=10),
            _Action("FastEthernet1/3", (SERVER,), vlan=10),
            _Action("FastEthernet2/1", (PC2,), vlan=20),
            _Action("FastEthernet2/3", ("endpoint/hq/other/server/001",), vlan=20),
        ],
        expectations=[
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1),
            _Expectation(
                "http-2",
                ServiceVerificationKind.HTTP_FETCH,
                client=PC2,
                host="endpoint/hq/other/server/001",
            ),
        ],
    )
    backend = ForwardingBackend(seconds_per_observation=30.0)
    gate = _gate(plan, backend, total_budget_seconds=20.0)

    assert gate.decide("http-1").admitted is True
    second = gate.decide("http-2")
    assert second is not None and second.admitted is False
    assert second.cause.startswith("readiness_budget_exhausted:seconds=")
    assert len(backend.calls) == 1


# -- B2, B3, B7: the real composition ------------------------------------------


def _run(backend: ForwardingBackend, tmp_path: Path):
    """Drive the real entry point with the two runtimes and one timed backend."""
    manifest, inventory = deployment_manifest()
    configuration = RecordingConfigurationRuntime(targets=inventory, forwarding=backend)
    services = RecordingServiceRuntime(targets=inventory)
    result = apply_enterprise_services(
        intent_json(),
        deployment_id=DEPLOYMENT_ID,
        packet_tracer_version=BACKEND_VERSION,
        import_preflight=IsolationPreflight(),
        manifest_store=ManifestStore(manifest=manifest),
        runtimes=ServiceStageRuntimes(configuration=configuration, services=services),
        record_store=ServiceRunRecordStore(tmp_path),
        environment_fingerprint=manifest.environment_fingerprint,
        transport_selection=TransportSelection(channel="http"),
        endpoint_observer=EndpointObserver(address=""),
        source_tree=SourceTreeIdentity(sha="test-source", dirty=True),
    )
    return result, configuration, services


def _http_rows(result: Any) -> list[Any]:
    """Return every HTTP-family verification row the run produced."""
    assert result.service_result is not None
    return [
        row
        for row in result.service_result.verification_results
        if row.expectation_id.startswith("svc/verify-http")
    ]


def test_no_http_request_is_dispatched_while_spanning_tree_is_still_listening(
    tmp_path: Path,
):
    """Ports are up and green, spanning tree is LIS, and nothing is requested."""
    backend = ForwardingBackend(forwards_at=None)

    result, _configuration, services = _run(backend, tmp_path)

    rows = _http_rows(result)
    assert rows, "the fixture intent compiles HTTP expectations"
    # Every HTTP row is blocked, and none of them was requested.
    for row in rows:
        assert row.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
    # The rows readiness itself refused carry the readiness code and cause.
    gated = [row for row in rows if row.expectation_id.startswith("svc/verify-http-ip")]
    assert gated, "the by-IP fetch is the first HTTP request of the DAG"
    for row in gated:
        assert row.failure_code is (
            ConfigurationFailureCode.ACCESS_FORWARDING_NOT_READY
        )
        assert row.observation is ObservationFact.NOT_ATTEMPTED
        assert row.claim_level == "request_not_attempted"
        assert "NON_FORWARDING" in row.cause
    # The by-hostname fetch never reaches readiness: its own DAG prerequisite
    # is the by-IP row readiness already blocked. Reporting it as a forwarding
    # refusal would claim a sample that was never taken on its behalf.
    for row in rows:
        if row not in gated:
            assert row.failure_code is ConfigurationFailureCode.DEPENDENCY_BLOCKED
    # The independent proof: the service runtime was never asked to fetch.
    assert not [
        item for item in services.verified if str(item).startswith("svc/verify-http")
    ]


def test_a_request_follows_the_first_admissible_observation(tmp_path: Path):
    """Once the sample forwards, the same run dispatches its HTTP requests."""
    backend = ForwardingBackend(forwards_at=0.0)

    result, _configuration, services = _run(backend, tmp_path)

    rows = _http_rows(result)
    assert rows
    for row in rows:
        assert row.failure_code is not (
            ConfigurationFailureCode.ACCESS_FORWARDING_NOT_READY
        )
        assert row.status is ActionExecutionStatus.VERIFIED
    assert [
        item for item in services.verified if str(item).startswith("svc/verify-http")
    ]
    assert len(backend.calls) == 1


def test_the_forwarding_evidence_round_trips_through_the_public_report(
    tmp_path: Path,
):
    """The sample, its verdict and its dependents reach the tool response."""
    backend = ForwardingBackend(forwards_at=None)

    result, _configuration, _services = _run(backend, tmp_path)

    summary = result.compact_summary()
    # Every pre-existing key keeps its name and meaning.
    for key in (
        "run_id",
        "stage",
        "status",
        "refusal_code",
        "services",
        "clients",
        "releases",
        "limitations",
    ):
        assert key in summary
    rows = summary["operational_readiness"]
    assert len(rows) == 1
    row = rows[0]
    assert row["switch_device_name"] == "HQ-DEFAULT-ACCESS-SW-01"
    assert row["vlan_id"] == 10
    assert row["status"] == READINESS_REFUSED
    assert row["dimension"] == "NON_FORWARDING"
    assert row["sample"]["light_status_is_auxiliary"] is True
    dependents = row["dependents"]
    assert {item["client_device_id"] for item in dependents} == {
        "endpoint/hq/default/user_pc/001",
        "endpoint/hq/default/user_pc/002",
    }
    for item in dependents:
        assert item["expectation_id"].startswith("svc/verify-http")
        assert item["admitted"] is False
        assert item["kind"] in HTTP_KINDS
    # The readiness rows are also in the durable record, not only the response.
    assert result.operational_readiness == rows


# -- regressions for the independent review findings ---------------------------


def _envelope_observer(
    *,
    switch: str = SWITCH_NAME,
    vlan: int = 10,
    interfaces: tuple[str, ...] | None = None,
    budget_exhausted: bool = False,
):
    """Build an observer whose answer envelope the caller chooses.

    Deliberately not `ForwardingBackend`: these cases are about an answer that
    describes a different question, which a backend built from the request
    cannot express.
    """

    class _Observer:
        calls = 0

        def observe_access_forwarding(self, device_name, vlan_id, requested):
            type(self).calls += 1
            reported = tuple(requested) if interfaces is None else interfaces
            return AccessForwardingObservation(
                switch_name=switch,
                vlan_id=vlan,
                requested_interfaces=reported,
                rows=tuple(
                    AccessForwardingRow(
                        interface=item, matches=1, state="FWD", role="Desg"
                    )
                    for item in reported
                ),
                executed=True,
                fresh_output_observed=True,
                output_complete=True,
                observed_device_name=switch,
                device_identity_provenance="confirmed_unique",
                vlan_present=True,
                samples=1,
                max_samples=3,
                deadline_seconds=30.0,
                sample_call_budget=6,
                channel_calls=6 if budget_exhausted else 1,
                sample_budget_exhausted=budget_exhausted,
            )

    return _Observer()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"switch": "SOMEONE-ELSE"}, "switch:SOMEONE-ELSE"),
        ({"vlan": 20}, "vlan:20"),
        ({"interfaces": ("FastEthernet1/1",)}, "interfaces:FastEthernet1/3"),
    ],
)
def test_an_answer_about_another_question_is_not_a_sample_of_this_group(
    overrides: dict[str, Any], expected: str
):
    """A self-consistent answer about another switch, VLAN or port set refuses.

    The shared admission rule checks that a sample is internally consistent. It
    never sees the request, so it cannot tell that the sample is about a
    different subject; the gate binds the answer to the question it asked.
    """
    plan = _plan(
        expectations=[
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1)
        ]
    )
    observer = _envelope_observer(**overrides)
    gate = ServiceAccessReadinessGate(
        plan,
        observer,
        clock=SimulatedClock(),
        device_names={SWITCH: SWITCH_NAME},
    )

    decision = gate.decide("http-1")

    assert decision is not None and decision.admitted is False
    assert decision.cause == f"{CAUSE_ANSWER_DOES_NOT_MATCH_REQUEST}:{expected}"
    row = gate.rows()[0]
    assert row["status"] == READINESS_NOT_OBSERVED
    # No sample is retained, because none of this group was sampled.
    assert row["sample"] == {}


def test_a_sample_that_ended_on_its_call_budget_grants_nothing():
    """An incomplete-by-construction sample is refused by the product gate.

    `AccessForwardingObservation.sample_budget_exhausted` documents itself as
    granting no permission, and the shared admission rule does not yet enforce
    that. The product path refuses here rather than waiting for the shared rule
    to change, because changing it would also move the diagnostic semantics the
    recorded evidence was measured under.
    """
    plan = _plan(
        expectations=[
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1)
        ]
    )
    gate = ServiceAccessReadinessGate(
        plan,
        _envelope_observer(budget_exhausted=True),
        clock=SimulatedClock(),
        device_names={SWITCH: SWITCH_NAME},
    )

    decision = gate.decide("http-1")

    assert decision is not None and decision.admitted is False
    row = gate.rows()[0]
    assert row["dimension"] == "SAMPLE_CALL_BUDGET_EXHAUSTED"
    assert CAUSE_SAMPLE_BUDGET_EXHAUSTED in row["causes"]
    # The sample is retained and still says what the shared rule concluded, so
    # the refusal is visibly the gate stricter than the rule, not a rewrite.
    assert row["sample"]["admitted"] is True
    assert row["sample"]["sample_budget_exhausted"] is True


def test_one_gate_serves_one_application():
    """A gate offered to a second application refuses instead of replaying."""
    backend = ForwardingBackend(forwards_at=0.0)
    gate = _gate(_plan(), backend)

    gate.begin_invocation()
    with pytest.raises(ReadinessGateConsumed):
        gate.begin_invocation()


def test_declaring_nothing_blocks_every_client_request(tmp_path: Path):
    """An omitted readiness decision is refused, not treated as permission.

    The default had to be the safe answer rather than the convenient one: a
    caller who never said how forwarding would be established has not
    established it, and the request is refused with its own cause instead of
    dispatched as though it had been observed.
    """
    parameter = inspect.signature(ServiceApplicator.apply).parameters[
        "operational_readiness"
    ]
    assert parameter.default is None
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY

    manifest, inventory = deployment_manifest()
    plan, capabilities = _compiled_service_plan(manifest)
    runtime = RecordingServiceRuntime(targets=inventory)

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=manifest.physical_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses={
            item.configuration_action_id: ActionExecutionStatus.VERIFIED
            for item in plan.foundational_requirements
        },
        capabilities=capabilities,
        deployment_manifest=manifest,
        runtime_context=ConfigurationRuntimeContext(
            environment_fingerprint=manifest.environment_fingerprint
        ),
    )
    assert not result.preflight_errors, result.preflight_errors

    http_rows = [
        row
        for row in result.verification_results
        if row.expectation_id.startswith("svc/verify-http")
    ]
    assert http_rows
    for row in http_rows:
        assert row.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
    # The first HTTP request of the DAG is the one readiness refused; the
    # by-hostname row is blocked by that refusal as its own prerequisite.
    gated = [
        row for row in http_rows if row.expectation_id.startswith("svc/verify-http-ip")
    ]
    assert gated
    for row in gated:
        assert row.failure_code is (
            ConfigurationFailureCode.ACCESS_FORWARDING_NOT_READY
        )
        assert row.cause == CAUSE_READINESS_NOT_DECLARED
    assert not [
        item for item in runtime.verified if str(item).startswith("svc/verify-http")
    ]


def _compiled_service_plan(manifest):
    """Compile the fixture intent to an E6 plan and its capability records."""
    from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
        compose_enterprise_reference,
    )
    from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
    from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
        packet_tracer_service_capabilities,
    )

    capabilities = packet_tracer_service_capabilities(BACKEND_VERSION)
    composition = compose_enterprise_reference(
        EnterpriseIntent.model_validate_json(intent_json()),
        packet_tracer_version=BACKEND_VERSION,
        deployment_manifest=manifest,
        services=True,
        service_capabilities=capabilities,
    )
    assert composition.services is not None, composition.issues
    return composition.services, capabilities


def test_an_exemption_must_state_its_reason():
    """The one way past the gate is explicit and has to say why."""
    with pytest.raises(ValueError):
        ReadinessNotRequired("")
    assert ReadinessNotRequired("measures its own forwarding").reason


def test_only_a_declared_access_port_action_produces_a_placement():
    """Four matching attribute names are not an access port."""

    class _Trunk:
        action_type = "configure_trunk"
        interface = "FastEthernet1/9"
        data_vlan_id = 10
        device_id = SWITCH
        device_name = SWITCH_NAME
        endpoint_ids = (PC1, SERVER)

    plan = derive_access_readiness_plan(
        configuration_actions=[_Trunk()],
        verification_expectations=[
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1)
        ],
    )

    assert plan.requirements == ()
    assert [item.expectation_id for item in plan.unplaced] == ["http-1"]


def test_the_real_access_port_action_type_is_the_one_derivation_accepts():
    """The accepted value is the compiled action type, not a guessed string."""
    assert (
        ACCESS_PORT_ACTION_TYPE == ConfigurationActionType.CONFIGURE_ACCESS_PORT.value
    )
