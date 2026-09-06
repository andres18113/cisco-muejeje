from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.packet_tracer_mcp.domain.enterprise.models.poe_delivery import (
    PoEDeliveryArmObservation,
    PoEDeliveryArmState,
    PoEDeliveryBindingFixtureIdentity,
    PoEDeliveryBindingObservation,
    PoEDeliveryBindingRequest,
    PoEDeliveryDeviceIdentity,
    PoEDeliveryFixtureIdentity,
    PoEDeliveryLinkEndpoint,
    PoEDeliveryLinkIdentity,
    PoEDeliveryQualificationRequest,
)
from src.packet_tracer_mcp.infrastructure.execution.poe_delivery_observer import (
    GovernedPoEDeliveryObserver,
    PoEVisualCaptureReceipt,
)


UTC = timezone.utc
STARTED = datetime(2026, 9, 6, 3, 30, tzinfo=UTC)
DEADLINE = STARTED + timedelta(seconds=300)


def _request_and_fixture():
    binding = PoEDeliveryBindingRequest(
        candidate_port="FastEthernet0/1",
        comparison_port="FastEthernet0/1",
        endpoint_model="7960",
        endpoint_port="Switch",
    )
    request = PoEDeliveryQualificationRequest(
        packet_tracer_build="9.0.1.0858",
        candidate_model="3560-24PS",
        comparison_model="2960-24TT",
        bindings=[binding],
    )
    candidate_switch = PoEDeliveryDeviceIdentity(
        name="__MCP_POE_run_CANDIDATE_SWITCH",
        model=request.candidate_model,
        observed_ports=[binding.candidate_port],
    )
    comparison_switch = PoEDeliveryDeviceIdentity(
        name="__MCP_POE_run_COMPARISON_SWITCH",
        model=request.comparison_model,
        observed_ports=[binding.comparison_port],
    )
    candidate_endpoint = PoEDeliveryDeviceIdentity(
        name="__MCP_POE_run_CANDIDATE_ENDPOINT_01",
        model=binding.endpoint_model,
        observed_ports=[binding.endpoint_port],
    )
    comparison_endpoint = PoEDeliveryDeviceIdentity(
        name="__MCP_POE_run_COMPARISON_ENDPOINT_01",
        model=binding.endpoint_model,
        observed_ports=[binding.endpoint_port],
    )
    fixture_binding = PoEDeliveryBindingFixtureIdentity(
        request=binding,
        candidate_switch=candidate_switch,
        comparison_switch=comparison_switch,
        candidate_endpoint=candidate_endpoint,
        comparison_endpoint=comparison_endpoint,
        candidate_link=_link(
            candidate_switch, binding.candidate_port,
            candidate_endpoint, binding.endpoint_port,
        ),
        comparison_link=_link(
            comparison_switch, binding.comparison_port,
            comparison_endpoint, binding.endpoint_port,
        ),
    )
    return request, PoEDeliveryFixtureIdentity(
        candidate_switch=candidate_switch,
        comparison_switch=comparison_switch,
        bindings=[fixture_binding],
    )


def _link(switch, switch_port, endpoint, endpoint_port):
    return PoEDeliveryLinkIdentity(
        first=PoEDeliveryLinkEndpoint(
            device_name=switch.name,
            device_model=switch.model,
            port=switch_port,
        ),
        second=PoEDeliveryLinkEndpoint(
            device_name=endpoint.name,
            device_model=endpoint.model,
            port=endpoint_port,
        ),
    )


def _binding_observation(fixture):
    item = fixture.bindings[0]
    return PoEDeliveryBindingObservation(
        binding=item.request,
        candidate=PoEDeliveryArmObservation(
            switch_name=item.candidate_switch.name,
            switch_model=item.candidate_switch.model,
            switch_port=item.request.candidate_port,
            endpoint_name=item.candidate_endpoint.name,
            endpoint_model=item.candidate_endpoint.model,
            endpoint_port=item.request.endpoint_port,
            state=PoEDeliveryArmState.POWERED,
            visible_indicator="phone display booted",
            switch_ready=True,
            link_ready=True,
            endpoint_settled=True,
        ),
        comparison=PoEDeliveryArmObservation(
            switch_name=item.comparison_switch.name,
            switch_model=item.comparison_switch.model,
            switch_port=item.request.comparison_port,
            endpoint_name=item.comparison_endpoint.name,
            endpoint_model=item.comparison_endpoint.model,
            endpoint_port=item.request.endpoint_port,
            state=PoEDeliveryArmState.NOT_POWERED,
            visible_indicator="phone display remained dark",
            switch_ready=True,
            link_ready=True,
            endpoint_settled=True,
        ),
    )


class _Capture:
    def __init__(self, fixture, *, mutate=None) -> None:
        self.fixture = fixture
        self.mutate = mutate
        self.calls = []

    def __call__(self, capture_request):
        self.calls.append(capture_request)
        receipt = PoEVisualCaptureReceipt(
            request_id=capture_request.request_id,
            capture_id="screenshot-001",
            fixture_fingerprint=capture_request.fixture_fingerprint,
            observer_id="Codex-computer-use",
            captured_at=STARTED + timedelta(seconds=30),
            method="manual_visible_power_state",
            simultaneous=True,
            bindings=(_binding_observation(self.fixture),),
        )
        return self.mutate(receipt, capture_request) if self.mutate else receipt


def _clock(*values):
    remaining = iter(values)
    return lambda: next(remaining)


def test_observer_owns_one_complete_synchronous_capture_and_returns_typed_observation():
    request, fixture = _request_and_fixture()
    capture = _Capture(fixture)
    observer = GovernedPoEDeliveryObserver(
        capture=capture,
        clock=_clock(STARTED, STARTED + timedelta(seconds=31)),
        request_id_factory=lambda: "observation-request-001",
    )

    observation = observer.observe(request, fixture, DEADLINE)

    assert observation is not None
    assert observation.observer_id == "Codex-computer-use"
    assert observation.observed_at == STARTED + timedelta(seconds=30)
    assert observation.simultaneous is True
    assert observation.bindings == [_binding_observation(fixture)]
    assert len(capture.calls) == 1
    issued = capture.calls[0]
    assert issued.request_id == "observation-request-001"
    assert issued.deadline_utc == DEADLINE
    assert issued.fixture == fixture


def test_observer_rejects_capture_delivered_after_deadline_even_if_image_timestamp_is_earlier():
    request, fixture = _request_and_fixture()
    capture = _Capture(fixture)
    observer = GovernedPoEDeliveryObserver(
        capture=capture,
        clock=_clock(STARTED, DEADLINE + timedelta(microseconds=1)),
        request_id_factory=lambda: "observation-request-001",
    )

    observation = observer.observe(request, fixture, DEADLINE)

    assert observation is None
    assert len(capture.calls) == 1


def test_observer_returns_attributed_visible_negative_for_service_classification():
    request, fixture = _request_and_fixture()

    def visible_but_not_differential(receipt, _request):
        binding = receipt.bindings[0].model_copy(deep=True)
        binding.comparison.state = PoEDeliveryArmState.POWERED
        return PoEVisualCaptureReceipt(
            **{**receipt.__dict__, "bindings": (binding,)},
        )

    capture = _Capture(fixture, mutate=visible_but_not_differential)
    observer = GovernedPoEDeliveryObserver(
        capture=capture,
        clock=_clock(STARTED, STARTED + timedelta(seconds=31)),
        request_id_factory=lambda: "observation-request-001",
    )

    observation = observer.observe(request, fixture, DEADLINE)

    assert observation is not None
    assert observation.bindings[0].comparison.state is PoEDeliveryArmState.POWERED
    assert len(capture.calls) == 1


def test_observer_capture_failure_returns_no_evidence_without_retrying():
    request, fixture = _request_and_fixture()
    calls = []

    def fail(capture_request):
        calls.append(capture_request)
        raise RuntimeError("visual channel failed")

    observer = GovernedPoEDeliveryObserver(
        capture=fail,
        clock=_clock(STARTED),
        request_id_factory=lambda: "observation-request-001",
    )

    assert observer.observe(request, fixture, DEADLINE) is None
    assert len(calls) == 1


def test_observer_rejects_stale_capture_from_another_request_without_retrying():
    request, fixture = _request_and_fixture()
    capture = _Capture(
        fixture,
        mutate=lambda receipt, _request: PoEVisualCaptureReceipt(
            **{**receipt.__dict__, "request_id": "previous-request"},
        ),
    )
    observer = GovernedPoEDeliveryObserver(
        capture=capture,
        clock=_clock(STARTED, STARTED + timedelta(seconds=31)),
        request_id_factory=lambda: "observation-request-001",
    )

    assert observer.observe(request, fixture, DEADLINE) is None
    assert len(capture.calls) == 1

def test_observer_rejects_wrong_fixture_attribution_without_retrying():
    request, fixture = _request_and_fixture()
    wrong = _binding_observation(fixture).model_copy(deep=True)
    wrong.candidate.endpoint_name = "__MCP_POE_previous_CANDIDATE_ENDPOINT_01"
    capture = _Capture(
        fixture,
        mutate=lambda receipt, _request: PoEVisualCaptureReceipt(
            **{**receipt.__dict__, "bindings": (wrong,)},
        ),
    )
    observer = GovernedPoEDeliveryObserver(
        capture=capture,
        clock=_clock(STARTED, STARTED + timedelta(seconds=31)),
        request_id_factory=lambda: "observation-request-001",
    )

    assert observer.observe(request, fixture, DEADLINE) is None
    assert len(capture.calls) == 1


def test_observer_rejects_receipt_with_a_stale_fixture_fingerprint():
    request, fixture = _request_and_fixture()
    capture = _Capture(
        fixture,
        mutate=lambda receipt, _request: PoEVisualCaptureReceipt(
            **{**receipt.__dict__, "fixture_fingerprint": "0" * 64},
        ),
    )
    observer = GovernedPoEDeliveryObserver(
        capture=capture,
        clock=_clock(STARTED, STARTED + timedelta(seconds=31)),
        request_id_factory=lambda: "observation-request-001",
    )

    assert observer.observe(request, fixture, DEADLINE) is None
    assert len(capture.calls) == 1
