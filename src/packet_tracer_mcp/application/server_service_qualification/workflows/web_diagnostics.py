"""D-WEB: forwarding, page, ping and fetch diagnostics on the web fixture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ....domain.enterprise.models.forwarding import (
    ForwardingAddressMode,
    ForwardingEndpointSelection,
    ForwardingKnownAddress,
    ForwardingRuntimeEndpoint,
)
from ....domain.enterprise.models.service_plan import (
    ServiceEvidenceKind,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from ....domain.enterprise.models.service_qualification import (
    D_WEB_FORWARDING_SAMPLES_AFTER,
    D_WEB_FORWARDING_SAMPLES_BEFORE,
    D_WEB_INSPECTION_SCHEDULE,
    DIAGNOSTIC_ACCESS_VLAN,
    Q1_PC1,
    Q1_SERVER,
    Q1_SERVER_IPV4,
    Q1_SWITCH,
    DiagnosticPrecondition,
    FixtureDevice,
    MeasurementConclusion,
    ReleaseRecord,
)
from ....domain.enterprise.services.service_qualification_evidence import (
    ACTIVE_STIMULUS,
    DIAGNOSTIC_SCOPE,
    Assessment,
    assess_access_forwarding,
    assess_client_timeline,
    assess_forwarding_probe,
    assess_port_readiness,
    marker_page_established,
)
from ..contracts import MAX_DETAIL
from ..execution import Execution
from ..fixtures import (
    Readiness,
    await_readiness,
    configure_web_fixture,
    diagnostic_start,
    endpoint_action_id,
    fixture_endpoints,
)


@dataclass
class _DWebState:
    """What one D-WEB run has established, carried between its procedures."""

    endpoints: dict[str, ForwardingRuntimeEndpoint] = field(default_factory=dict)
    forwarding_admitted: bool = False
    listeners_before: dict[str, Any] = field(default_factory=dict)
    marker: str = ""


def _d_web_selection(
    execution: Execution, fixture: FixtureDevice
) -> ForwardingRuntimeEndpoint:
    """Bind one fixture endpoint to the E5 action this stage dispatched.

    The provenance is the stage's own, and it is real: the address comes from
    the fixture the authorization named, the action id is the one the endpoint
    batch this run applied actually carried, and the co-observed addresses are
    the other addressed fixtures of the same segment, so a duplicate address
    conflicts instead of binding.
    """
    definition = execution.definition
    scope = definition.stage.value.lower()
    network = ".".join([*fixture.ipv4.split(".")[:3], "0"])
    known = tuple(
        ForwardingKnownAddress(
            item.ipv4, endpoint_action_id(execution, item.name), item.name
        )
        for item in definition.fixtures
        if item.ipv4
    )
    selection = ForwardingEndpointSelection(
        policy_id=scope,
        policy_version=definition.profile_version,
        source_topology_id=definition.stage.value,
        source_topology_hash="",
        source_configuration_id=definition.stage.value,
        source_configuration_hash="",
        site_id=scope,
        routing_device_id="",
        endpoint_device_id=fixture.name,
        endpoint_device_name=fixture.name,
        endpoint_model=fixture.model,
        endpoint_role="fixture",
        link_id="",
        endpoint_interface="FastEthernet0",
        peer_device_id=Q1_SWITCH,
        peer_interface="",
        segment_id=scope,
        address_mode=ForwardingAddressMode.STATIC,
        configuration_action_id=endpoint_action_id(execution, fixture.name),
        planned_ipv4=fixture.ipv4,
        network=network,
        prefix_length=24,
        netmask=fixture.netmask,
        known_plan_addresses=known,
    )
    return ForwardingRuntimeEndpoint(
        selection=selection,
        runtime_device_name=fixture.name,
        identity_method="stage_fixture_binding",
        deployment_id=execution.record.run_id,
        deployment_manifest_hash="",
    )


def run_d_web(execution: Execution) -> None:
    """Observe every boundary an unretrieved page can fail at, in order."""
    state = _DWebState()
    # The after-boundaries are this stage's terminal observation and they are
    # registered before its first effect. An HTTP timeout is precisely the
    # case the diagnostic was asked about, and so is an exception raised out
    # of the middle of the sequence: neither may delete the fixtures without
    # the readings that locate it. They are read-only and dispatch no second
    # request.
    execution.register_terminal(
        ("M-DWEB-5",), "D_WEB_AFTER", lambda: _d_web_terminal(execution, state)
    )
    if not diagnostic_start(execution):
        return
    if not configure_web_fixture(execution):
        execution.not_run(
            [item.id for item in execution.definition.experiments if item.required],
            "fixture_setup_failed",
        )
        return
    for fixture in execution.definition.fixtures:
        if fixture.ipv4:
            state.endpoints[fixture.name] = _d_web_selection(execution, fixture)

    ids = ("M-DWEB-0",)
    if execution.selected("W0-listeners") and execution.begin(ids, "D_WEB_BOUNDARIES"):
        with execution.procedure(ids):
            _d_web_boundaries(execution, state, label="before")
        execution.finish("D_WEB_BOUNDARIES")

    ids = ("M-DWEB-1",)
    if execution.selected("W1-forwarding") and execution.begin(ids, "D_WEB_FORWARDING"):
        with execution.procedure(ids):
            _d_web_forwarding(
                execution,
                state,
                label="before",
                samples=D_WEB_FORWARDING_SAMPLES_BEFORE,
            )
        execution.finish("D_WEB_FORWARDING")

    ids = ("M-DWEB-2",)
    if execution.selected("W2-page") and execution.begin(ids, "D_WEB_PAGE"):
        with execution.procedure(ids):
            _d_web_page(execution, state)
        execution.finish("D_WEB_PAGE")

    ids = ("M-DWEB-3",)
    if execution.selected("W3-ping") and execution.begin(ids, "D_WEB_PING"):
        with execution.procedure(ids):
            _d_web_ping(execution, state)
        execution.finish("D_WEB_PING")

    ids = ("M-DWEB-4",)
    if execution.selected("W4-fetch") and execution.begin(ids, "D_WEB_FETCH"):
        with execution.procedure(ids):
            _d_web_fetch(execution, state)
        execution.finish("D_WEB_FETCH")


def _d_web_terminal(execution: Execution, state: _DWebState) -> None:
    """Take this stage's terminal reading, from finalization and only there."""
    ids = ("M-DWEB-5",)
    if not execution.selected("W5-after"):
        return
    if not execution.begin_terminal(ids, "D_WEB_AFTER"):
        return
    with execution.procedure(ids):
        _d_web_after(execution, state)
    execution.finish("D_WEB_AFTER")


def _d_web_listener_reading(execution: Execution, label: str) -> dict[str, Any]:
    """Read both listeners, their port numbers and every fixture endpoint."""
    endpoints = fixture_endpoints(execution)
    with execution.ledger.purpose_of(f"d-web:listeners:{label}"):
        reading = execution.probes.read_listener_readiness(Q1_SERVER, endpoints)
    return dict(assess_port_readiness(reading, endpoints).facts)


def _d_web_boundaries(execution: Execution, state: _DWebState, *, label: str) -> None:
    """Establish the listener and endpoint boundaries before any request."""
    facts = _d_web_listener_reading(execution, label)
    state.listeners_before = facts
    endpoints = fixture_endpoints(execution)
    gate = Readiness(False, 0, 0.0, "readiness_not_selected")
    if execution.selected("W0-readiness"):
        gate = await_readiness(
            execution,
            endpoints,
            lambda timeout: execution.probes.read_port_readiness(endpoints, timeout),
            purpose="readiness:d_web_fixture_links",
        )
    listeners = facts.get("listeners") or {}
    causes: list[str] = []
    if not facts.get("observed"):
        causes.append(f"listener_reading_unobserved:{facts.get('cause', '')}")
    for key in ("http_enabled", "https_enabled"):
        if listeners.get(key) is not True:
            causes.append(f"listener_not_enabled:{key}")
    for key in ("http_port_number", "https_port_number"):
        if not isinstance(listeners.get(key), int) or isinstance(
            listeners.get(key), bool
        ):
            causes.append(f"listener_port_not_read_back:{key}")
    if execution.selected("W0-readiness") and not gate.ready:
        causes.append(f"readiness_not_established:{gate.reason}")
    execution.conclude(
        "M-DWEB-0",
        Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE
            if not causes
            else MeasurementConclusion.INCONCLUSIVE,
            facts={f"listeners_{label}": facts, "readiness": gate.facts()},
            causes=causes,
            limitations=[
                DIAGNOSTIC_SCOPE,
                "light_status_and_port_up_are_auxiliary_and_grant_no_forwarding",
            ],
        ),
    )
    if causes:
        execution.stop(f"d_web_boundaries_not_established:{causes[0]}")
        return
    execution.establish(DiagnosticPrecondition.LISTENERS_ESTABLISHED)


def _d_web_switch_ports(execution: Execution) -> tuple[str, ...]:
    """Return the exact switch-side access ports of this stage's fixture."""
    return tuple(
        item.port_b if item.device_b == Q1_SWITCH else item.port_a
        for item in execution.definition.links
        if Q1_SWITCH in (item.device_a, item.device_b)
    )


def _d_web_forwarding(
    execution: Execution, state: _DWebState, *, label: str, samples: int
) -> None:
    """Observe the exact switch ports' per-VLAN forwarding state, neutrally."""
    interfaces = _d_web_switch_ports(execution)
    runtime = execution.run.boundaries.configuration_runtime(execution.bound)
    with execution.ledger.purpose_of(f"d-web:forwarding:{label}"):
        observation = runtime.observe_access_forwarding(
            Q1_SWITCH,
            DIAGNOSTIC_ACCESS_VLAN,
            interfaces,
            max_samples=samples,
        )
    lights = {
        key: {
            "light_status": value.get("light_status"),
            "light_status_type": value.get("light_status_type"),
            "light_status_name": value.get("light_status_name"),
        }
        for key, value in (state.listeners_before.get("ports") or {}).items()
    }
    assessment = assess_access_forwarding(
        observation, label=f"forwarding_{label}", lights=lights
    )
    state.forwarding_admitted = (
        assessment.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    if state.forwarding_admitted:
        execution.establish(DiagnosticPrecondition.FORWARDING_OBSERVED)
    execution.conclude("M-DWEB-1", assessment)
    if not state.forwarding_admitted:
        # No permission is granted by an unadmitted sample, and the stage says
        # so rather than continuing as if it had one.
        execution.record.limitations.append(
            f"forwarding_not_admitted:{assessment.causes[0] if assessment.causes else 'unknown'}"
        )


def _d_web_page(execution: Execution, state: _DWebState) -> None:
    """Write this run's marker into the existing index page through both handles."""
    texts = execution.probes.page_marker_texts()
    state.marker = texts["http_marker"]
    with execution.ledger.effect_of("d-web:marker_page"):
        reading = execution.probes.prepare_marker_page(Q1_SERVER, state.marker)
    established = marker_page_established(reading)
    execution.conclude(
        "M-DWEB-2",
        Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE
            if established
            else MeasurementConclusion.INCONCLUSIVE,
            facts={
                "marker_page": {
                    "marker": state.marker,
                    "observed": reading.observed,
                    "cause": reading.cause,
                    "payload": dict(reading.payload) if reading.observed else {},
                }
            },
            causes=[] if established else ["marker_page_not_established"],
            limitations=[DIAGNOSTIC_SCOPE],
        ),
    )
    if not established:
        execution.stop("d_web_marker_page_not_established")
        return
    execution.establish(DiagnosticPrecondition.MARKER_PAGE)


def _d_web_ping(execution: Execution, state: _DWebState) -> None:
    """Take exactly one attributed ping between the two selected bindings."""
    probe = execution.run.boundaries.forwarding_probe
    source = state.endpoints.get(Q1_PC1)
    destination = state.endpoints.get(Q1_SERVER)
    if probe is None or source is None or destination is None:
        execution.conclude(
            "M-DWEB-3",
            assess_forwarding_probe(
                None, forwarding_admitted=state.forwarding_admitted
            ),
        )
        execution.stop("d_web_forwarding_probe_not_composed")
        return
    execution.record.limitations.append(ACTIVE_STIMULUS)
    with execution.ledger.effect_of("d-web:ping"):
        evidence = probe(execution.bound).probe_once(
            source_device_name=Q1_PC1,
            destination_endpoint=destination,
            source_endpoint=source,
            expected_reachable=True,
        )
    probe_assessment = assess_forwarding_probe(
        evidence, forwarding_admitted=state.forwarding_admitted
    )
    if probe_assessment.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.establish(DiagnosticPrecondition.PING_ATTRIBUTED)
    execution.conclude("M-DWEB-3", probe_assessment)


def _d_web_fetch(execution: Execution, state: _DWebState) -> None:
    """Instrument one real owned background client, start to release."""
    factory = execution.run.boundaries.diagnostic_service_runtime
    if factory is None:
        execution.conclude(
            "M-DWEB-4",
            assess_client_timeline(
                None, marker=state.marker, schedule=D_WEB_INSPECTION_SCHEDULE
            ),
        )
        execution.stop("d_web_service_runtime_not_composed")
        return
    expectation = ServiceVerificationExpectation(
        id="d-web-http",
        service_id="d-web-http",
        action_id="d-web-fixture",
        kind=ServiceVerificationKind.HTTP_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id=Q1_SERVER,
        host_device_name=Q1_SERVER,
        client_device_id=Q1_PC1,
        client_device_name=Q1_PC1,
        expected={
            "scheme": "http",
            "address": Q1_SERVER_IPV4,
            "marker": state.marker,
        },
        host_model="Server-PT",
        client_model="PC-PT",
    )
    with execution.ledger.effect_of("d-web:fetch:http"):
        row = factory(execution.bound, execution.ledger.allowance).verify(expectation)
    released = str(row.observed.get("released", ""))
    execution.record.releases.append(
        ReleaseRecord(
            resource="client:d-web-http",
            kind="client",
            outcome=released or "unknown",
            detail="; ".join(row.limitations)[:MAX_DETAIL],
        )
    )
    if released not in ("released", "nothing_owned"):
        execution.record.engine_residue.append(
            f"client:d-web-http:{released or 'unknown'}"
        )
    execution.conclude(
        "M-DWEB-4",
        assess_client_timeline(
            row, marker=state.marker, schedule=D_WEB_INSPECTION_SCHEDULE
        ),
    )
    if released not in ("released", "nothing_owned"):
        execution.stop("outcome_unknown:fetch_client:d-web-http")


def _d_web_after(execution: Execution, state: _DWebState) -> None:
    """Read the same boundaries again and retain whatever moved."""
    after = _d_web_listener_reading(execution, "after")
    # This completed sub-read is evidence even when the next terminal reader
    # is cancelled. Keep it on the existing measurement before starting that
    # reader; a complete assessment below replaces these partial facts.
    execution.measurement("M-DWEB-5").facts["listeners_after"] = after
    execution.run.transition("experiment:D_WEB_AFTER:listeners_observed")
    interfaces = _d_web_switch_ports(execution)
    runtime = execution.run.boundaries.configuration_runtime(execution.bound)
    with execution.ledger.purpose_of("d-web:forwarding:after"):
        observation = runtime.observe_access_forwarding(
            Q1_SWITCH,
            DIAGNOSTIC_ACCESS_VLAN,
            interfaces,
            max_samples=D_WEB_FORWARDING_SAMPLES_AFTER,
        )
    forwarding = assess_access_forwarding(observation, label="forwarding_after")
    before = state.listeners_before.get("listeners") or {}
    listeners = after.get("listeners") or {}
    limitations = [DIAGNOSTIC_SCOPE, ACTIVE_STIMULUS, *forwarding.limitations]
    causes = list(forwarding.causes)
    moved: list[str] = []
    if not before:
        # Without the earlier reading there is nothing to compare against.
        # Reporting every field as changed would manufacture a difference out
        # of an observation that was never taken.
        limitations.append("listener_comparison_unavailable:no_reading_before")
        causes.append("listeners_before_not_observed")
    else:
        moved = sorted(
            key
            for key in set(before) | set(listeners)
            if before.get(key) != listeners.get(key)
        )
        causes.extend(f"listener_changed:{item}" for item in moved)
    execution.conclude(
        "M-DWEB-5",
        Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE
            if not causes
            else MeasurementConclusion.INCONCLUSIVE,
            facts={
                "listeners_after": after,
                **forwarding.facts,
                "listener_differences": moved,
                "listener_comparison_observed": bool(before),
            },
            causes=causes,
            limitations=limitations,
        ),
    )
