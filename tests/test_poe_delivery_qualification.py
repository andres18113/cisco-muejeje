from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.packet_tracer_mcp.application.use_cases.poe_delivery_qualification import (
    PoEDeliveryQualificationService,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CleanupStatus,
    LiveSessionSafetyEvidence,
    ProbeExecutionStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.evidence import (
    ObservationStatus,
    VerificationStatus,
)
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
    PoEDeliveryManualObservation,
    PoEDeliveryQualificationRequest,
)
from src.packet_tracer_mcp.domain.enterprise.rules.poe_delivery import (
    validate_poe_delivery_observation,
)
from src.packet_tracer_mcp.domain.enterprise.services.poe_claims import (
    decode_poe_delivery_scope,
    poe_claim_has_delivery_basis,
)
from src.packet_tracer_mcp.infrastructure.execution.live_file_integrity import (
    PacketTracerLiveFileGuard,
    PacketTracerLiveSessionSafety,
)


def _request(*, bindings: int = 1) -> PoEDeliveryQualificationRequest:
    return PoEDeliveryQualificationRequest(
        packet_tracer_build="Packet Tracer 9.0.0 build 1234",
        candidate_model="3560-24PS",
        comparison_model="2960-24TT",
        bindings=[
            PoEDeliveryBindingRequest(
                candidate_port=f"FastEthernet0/{index}",
                comparison_port=f"FastEthernet0/{index}",
                endpoint_model="7960",
                endpoint_port="Port 1",
            )
            for index in range(1, bindings + 1)
        ],
    )


def _device(name: str, model: str, port: str) -> PoEDeliveryDeviceIdentity:
    return PoEDeliveryDeviceIdentity(name=name, model=model, observed_ports=[port])


def _link(
    switch: PoEDeliveryDeviceIdentity,
    switch_port: str,
    endpoint: PoEDeliveryDeviceIdentity,
    endpoint_port: str,
) -> PoEDeliveryLinkIdentity:
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


class FakeRuntime:
    def __init__(self, request: PoEDeliveryQualificationRequest) -> None:
        self.request = request
        self.initial_fingerprint = "inventory-before"
        self.final_fingerprint = self.initial_fingerprint
        self.fail_operation: str | None = None
        self.identity_drift = False
        self.delete_failures: set[str] = set()
        self.calls: list[str] = []
        self.attempted_names: list[str] = []

    def packet_tracer_build(self) -> str | None:
        self.calls.append("packet_tracer_build")
        return self.request.packet_tracer_build

    def inventory_fingerprint(self) -> str:
        self.calls.append("inventory_fingerprint")
        return self.initial_fingerprint

    def create_device(
        self, model: str, temporary_name: str, required_ports: tuple[str, ...],
    ) -> PoEDeliveryDeviceIdentity:
        self.calls.append(f"create:{temporary_name}")
        self.attempted_names.append(temporary_name)
        if self.fail_operation == "create" and len(self.attempted_names) == 3:
            raise RuntimeError("endpoint creation failed")
        return PoEDeliveryDeviceIdentity(
            name=temporary_name,
            model=(
                "unexpected-model"
                if self.identity_drift and len(self.attempted_names) == 1
                else model
            ),
            observed_ports=list(required_ports),
        )

    def create_link(
        self,
        switch: PoEDeliveryDeviceIdentity,
        switch_port: str,
        endpoint: PoEDeliveryDeviceIdentity,
        endpoint_port: str,
    ) -> PoEDeliveryLinkIdentity:
        self.calls.append(f"link:{switch.name}:{endpoint.name}")
        if self.fail_operation == "link":
            raise RuntimeError("link creation failed")
        return _link(switch, switch_port, endpoint, endpoint_port)

    def delete_device(self, temporary_name: str) -> bool:
        self.calls.append(f"delete:{temporary_name}")
        return temporary_name not in self.delete_failures

    def wait_for_inventory_fingerprint(self, expected: str) -> str:
        self.calls.append(f"restore:{expected}")
        if self.fail_operation == "restore":
            raise TimeoutError("inventory did not converge")
        return self.final_fingerprint


class FakeObserver:
    def __init__(self) -> None:
        self.calls = 0
        self.mutate = None
        self.raise_error = False
        self.return_none = False
        self.deadlines: list[datetime] = []

    def observe(
        self,
        request: PoEDeliveryQualificationRequest,
        fixture: PoEDeliveryFixtureIdentity,
        deadline_utc: datetime,
    ) -> PoEDeliveryManualObservation:
        self.calls += 1
        self.deadlines.append(deadline_utc)
        if self.raise_error:
            raise RuntimeError("observer unavailable")
        if self.return_none:
            return None
        observations = []
        for binding in fixture.bindings:
            observations.append(PoEDeliveryBindingObservation(
                binding=binding.request,
                candidate=PoEDeliveryArmObservation(
                    switch_name=binding.candidate_switch.name,
                    switch_model=binding.candidate_switch.model,
                    switch_port=binding.request.candidate_port,
                    endpoint_name=binding.candidate_endpoint.name,
                    endpoint_model=binding.candidate_endpoint.model,
                    endpoint_port=binding.request.endpoint_port,
                    state=PoEDeliveryArmState.POWERED,
                    visible_indicator="phone display booted",
                    switch_ready=True,
                    link_ready=True,
                    endpoint_settled=True,
                ),
                comparison=PoEDeliveryArmObservation(
                    switch_name=binding.comparison_switch.name,
                    switch_model=binding.comparison_switch.model,
                    switch_port=binding.request.comparison_port,
                    endpoint_name=binding.comparison_endpoint.name,
                    endpoint_model=binding.comparison_endpoint.model,
                    endpoint_port=binding.request.endpoint_port,
                    state=PoEDeliveryArmState.NOT_POWERED,
                    visible_indicator="phone display remained dark",
                    switch_ready=True,
                    link_ready=True,
                    endpoint_settled=True,
                ),
            ))
        observation = PoEDeliveryManualObservation(
            observer_id="operator@example.test",
            observed_at=datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc),
            method="manual_visible_power_state",
            simultaneous=True,
            bindings=observations,
        )
        if self.mutate is not None:
            self.mutate(observation)
        return observation


class FakeSnapshotWriter:
    def __init__(self) -> None:
        self.snapshots = []
        self.raise_error = False

    def save_runtime(self, snapshot):
        if self.raise_error:
            raise OSError("snapshot store unavailable")
        self.snapshots.append(snapshot)
        return Path("runtime-snapshot.json")


class FakeSessionSafety:
    def __init__(
        self,
        *,
        session_reusable: bool = True,
        positive_claim_allowed: bool = True,
        integrity_verified: bool = True,
        crash_detected: bool = False,
        failure_reasons: tuple[str, ...] = (),
        on_finalize=None,
        raise_error: bool = False,
    ) -> None:
        stable_sha256 = "a" * 64
        self.result = LiveSessionSafetyEvidence(
            canonical_path="C:/fixture/canonical.pts",
            canonical_pre_run_sha256=stable_sha256,
            canonical_observed_post_run_sha256=stable_sha256,
            canonical_verified_sha256=stable_sha256,
            disposable_path="C:/fixture/disposable.pts",
            disposable_pre_run_sha256=stable_sha256,
            disposable_post_run_sha256=stable_sha256,
            unexpected_canonical_modification=False,
            disposable_modified=False,
            runtime_healthy=True,
            session_reusable=session_reusable,
            positive_claim_allowed=positive_claim_allowed,
            integrity_verified=integrity_verified,
            crash_detected=crash_detected,
            failure_reasons=failure_reasons,
        )
        self.on_finalize = on_finalize
        self.raise_error = raise_error
        self.calls = 0

    def finalize(self) -> LiveSessionSafetyEvidence:
        self.calls += 1
        if self.on_finalize is not None:
            self.on_finalize()
        if self.raise_error:
            raise RuntimeError("session safety unavailable")
        return self.result


def _fixture_for_rules(request: PoEDeliveryQualificationRequest) -> PoEDeliveryFixtureIdentity:
    candidate_switch = PoEDeliveryDeviceIdentity(
        name="candidate",
        model=request.candidate_model,
        observed_ports=[binding.candidate_port for binding in request.bindings],
    )
    comparison_switch = PoEDeliveryDeviceIdentity(
        name="comparison",
        model=request.comparison_model,
        observed_ports=[binding.comparison_port for binding in request.bindings],
    )
    identities = []
    for index, binding in enumerate(request.bindings, start=1):
        candidate_endpoint = _device(f"candidate-endpoint-{index}", binding.endpoint_model, binding.endpoint_port)
        comparison_endpoint = _device(f"comparison-endpoint-{index}", binding.endpoint_model, binding.endpoint_port)
        identities.append(PoEDeliveryBindingFixtureIdentity(
            request=binding,
            candidate_switch=candidate_switch,
            comparison_switch=comparison_switch,
            candidate_endpoint=candidate_endpoint,
            comparison_endpoint=comparison_endpoint,
            candidate_link=_link(candidate_switch, binding.candidate_port, candidate_endpoint, binding.endpoint_port),
            comparison_link=_link(comparison_switch, binding.comparison_port, comparison_endpoint, binding.endpoint_port),
        ))
    return PoEDeliveryFixtureIdentity(
        candidate_switch=candidate_switch,
        comparison_switch=comparison_switch,
        bindings=identities,
    )


def _valid_observation(
    request: PoEDeliveryQualificationRequest,
    fixture: PoEDeliveryFixtureIdentity,
) -> PoEDeliveryManualObservation:
    return FakeObserver().observe(
        request,
        fixture,
        datetime(2026, 9, 4, 15, 5, tzinfo=timezone.utc),
    )


def test_observation_rule_accepts_complete_exact_differential() -> None:
    request = _request(bindings=2)
    fixture = _fixture_for_rules(request)

    result = validate_poe_delivery_observation(
        request, fixture, _valid_observation(request, fixture),
    )

    assert result.is_valid


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    [
        (lambda item: setattr(item, "observer_id", ""), "observer"),
        (lambda item: setattr(item, "simultaneous", False), "simultaneous"),
        (lambda item: setattr(item, "method", "structured_api"), "manual visible"),
        (lambda item: setattr(item.bindings[0].candidate, "visible_indicator", ""), "indicator"),
        (lambda item: setattr(item.bindings[0].candidate, "state", PoEDeliveryArmState.UNOBSERVABLE), "unobservable"),
        (lambda item: setattr(item.bindings[0].comparison, "state", PoEDeliveryArmState.POWERED), "comparison"),
        (lambda item: setattr(item.bindings[0].candidate, "switch_port", "FastEthernet0/24"), "identity"),
        (lambda item: setattr(item.bindings[0].candidate, "switch_ready", False), "switch_ready"),
        (lambda item: setattr(item.bindings[0].comparison, "link_ready", False), "link_ready"),
        (lambda item: setattr(item.bindings[0].comparison, "endpoint_settled", False), "endpoint_settled"),
        (
            lambda item: setattr(
                item,
                "observed_at",
                datetime(2026, 9, 4, 10, 0, tzinfo=timezone(timedelta(hours=-5))),
            ),
            "utc",
        ),
        (lambda item: item.bindings.append(item.bindings[0].model_copy(deep=True)), "duplicate"),
        (lambda item: item.bindings.pop(), "coverage"),
    ],
)
def test_observation_rule_fails_closed_for_each_incomplete_cause(mutation, expected_fragment: str) -> None:
    request = _request(bindings=2)
    fixture = _fixture_for_rules(request)
    observation = _valid_observation(request, fixture)
    mutation(observation)

    result = validate_poe_delivery_observation(request, fixture, observation)

    assert not result.is_valid
    assert expected_fragment in " ".join(result.error_messages()).casefold()


def _service_fixture():
    request = _request(bindings=2)
    runtime = FakeRuntime(request)
    observer = FakeObserver()
    writer = FakeSnapshotWriter()
    service = PoEDeliveryQualificationService(
        runtime=runtime,
        observer=observer,
        snapshots=writer,
        session_safety=FakeSessionSafety(),
        session_id_factory=lambda: "fixed-session",
        clock=lambda: datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc),
        observation_window_seconds=120,
    )
    return request, runtime, observer, writer, service


def test_service_persists_supported_manual_evidence_only_after_clean_restoration() -> None:
    request, runtime, observer, writer, service = _service_fixture()

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.VERIFIED
    assert result.observation_status is ObservationStatus.OBSERVED
    assert result.verification_status is VerificationStatus.VERIFIED
    assert result.capability_result.status is CapabilityStatus.SUPPORTED
    assert result.capability_result.evidence_source is EvidenceSource.MANUAL_VERIFICATION
    assert result.capability_result.verified is True
    assert result.capability_result.observed_value == 2
    assert result.cleanup_status is CleanupStatus.CLEAN
    assert result.inventory_restored is True
    assert result.live_session_safety.session_reusable is True
    assert result.live_session_safety.integrity_verified is True
    assert result.live_session_safety.crash_detected is False
    assert result.runtime_snapshot_path == "runtime-snapshot.json"
    assert len(writer.snapshots) == 1
    assert writer.snapshots[0].reusable is True
    assert writer.snapshots[0].session.results[0].evidence() is not None
    scope = decode_poe_delivery_scope(
        result.capability_result,
        expected_model=request.candidate_model,
        expected_packet_tracer_version=request.packet_tracer_build,
    )
    assert scope is not None
    assert scope.candidate_model == request.candidate_model
    assert scope.packet_tracer_build == request.packet_tracer_build
    assert scope.cleanup_status == "clean"
    assert scope.inventory_restoration == "restored"
    assert scope.observed_at == "2026-09-04T15:00:00Z"
    assert all(binding.candidate_state == "powered" for binding in scope.tested_bindings)
    assert all(binding.comparison_state == "not_powered" for binding in scope.tested_bindings)
    assert all(
        binding.candidate_indicator == "phone display booted"
        for binding in scope.tested_bindings
    )
    assert all(
        binding.comparison_indicator == "phone display remained dark"
        for binding in scope.tested_bindings
    )
    assert all(binding.candidate_ready for binding in scope.tested_bindings)
    assert all(binding.comparison_ready for binding in scope.tested_bindings)
    assert {binding.switch_port for binding in scope.active_bindings} == {
        "FastEthernet0/1", "FastEthernet0/2",
    }
    assert observer.calls == 1
    assert result.fixture is not None
    assert result.observation is not None
    assert result.observation.observed_at == datetime(
        2026, 9, 4, 15, 0, tzinfo=timezone.utc,
    )
    assert observer.deadlines == [datetime(2026, 9, 4, 15, 2, tzinfo=timezone.utc)]
    delete_calls = [call for call in runtime.calls if call.startswith("delete:")]
    assert "ENDPOINT" in delete_calls[0]
    assert "SWITCH" in delete_calls[-1]


@pytest.mark.parametrize("stage", ["create", "link"])
def test_service_attempts_cleanup_after_fixture_failure(stage: str) -> None:
    request, runtime, observer, writer, service = _service_fixture()
    runtime.fail_operation = stage

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.EXECUTION_ERROR
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.observation_status is ObservationStatus.PROBE_FAILED
    assert result.verification_status is VerificationStatus.UNVERIFIED
    assert result.capability_result.verified is False
    assert observer.calls == 0
    assert [name for name in result.attempted_identities] == runtime.attempted_names
    assert all(f"delete:{name}" in runtime.calls for name in result.attempted_identities)
    assert writer.snapshots[0].session.results[0].evidence() is None


def test_service_cleans_up_after_observer_failure_without_promoting_unknown() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    observer.raise_error = True

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.capability_result.verified is False
    assert set(result.deleted_identities) == set(result.attempted_identities)
    assert "observer" in result.failure_reason.casefold()


def test_service_classifies_missing_observation_as_unobservable_verification_failure() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    observer.return_none = True

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.observation_status is ObservationStatus.UNOBSERVABLE
    assert result.verification_status is VerificationStatus.UNVERIFIED
    assert "unobservable" in result.failure_reason.casefold()
    assert set(result.deleted_identities) == set(result.attempted_identities)


def test_service_rejects_observation_outside_bounded_deadline() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    observer.mutate = lambda item: setattr(
        item,
        "observed_at",
        datetime(2026, 9, 4, 15, 3, tzinfo=timezone.utc),
    )

    result = service.qualify(request)

    assert observer.deadlines == [datetime(2026, 9, 4, 15, 2, tzinfo=timezone.utc)]
    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.observation_status is ObservationStatus.OBSERVED
    assert result.verification_status is VerificationStatus.FAILED
    assert "bounded observation window" in result.failure_reason


def test_service_rejects_observation_returned_after_deadline_even_with_timely_timestamp() -> None:
    request, runtime, observer, writer, _service = _service_fixture()
    started = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)
    times = iter((started, started + timedelta(seconds=121)))
    service = PoEDeliveryQualificationService(
        runtime=runtime,
        observer=observer,
        snapshots=writer,
        session_safety=FakeSessionSafety(),
        session_id_factory=lambda: "fixed-session",
        clock=lambda: next(times),
        observation_window_seconds=120,
    )

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.observation_status is ObservationStatus.UNOBSERVABLE
    assert result.verification_status is VerificationStatus.UNVERIFIED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert "returned after" in result.failure_reason.casefold()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: setattr(item, "observer_id", " operator@example.test "),
        lambda item: setattr(
            item.bindings[0].candidate,
            "visible_indicator",
            " phone display booted ",
        ),
        lambda item: setattr(
            item.bindings[0].comparison,
            "visible_indicator",
            " phone display remained dark ",
        ),
    ],
    ids=["observer-id", "candidate-indicator", "comparison-indicator"],
)
def test_service_rejects_untrimmed_manual_observation_text_without_raising(
    mutate,
) -> None:
    request, runtime, observer, writer, service = _service_fixture()
    observer.mutate = mutate

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.observation_status is ObservationStatus.OBSERVED
    assert result.verification_status is VerificationStatus.FAILED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert "whitespace" in result.failure_reason.casefold()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: setattr(
            item, "packet_tracer_build", " Packet Tracer 9.0.0 build 1234 ",
        ),
        lambda item: setattr(item, "candidate_model", " 3560-24PS "),
        lambda item: setattr(item, "comparison_model", " 2960-24TT "),
        lambda item: setattr(
            item.bindings[0], "candidate_port", " FastEthernet0/1 ",
        ),
        lambda item: setattr(
            item.bindings[0], "comparison_port", " FastEthernet0/1 ",
        ),
        lambda item: setattr(item.bindings[0], "endpoint_model", " 7960 "),
        lambda item: setattr(item.bindings[0], "endpoint_port", " Switch "),
    ],
    ids=[
        "packet-tracer-build",
        "candidate-model",
        "comparison-model",
        "candidate-port",
        "comparison-port",
        "endpoint-model",
        "endpoint-port",
    ],
)
def test_service_rejects_untrimmed_request_identity_without_raising(mutate) -> None:
    request, runtime, observer, writer, service = _service_fixture()
    mutate(request)

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.EXECUTION_ERROR
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.attempted_identities == []
    assert observer.calls == 0
    assert "whitespace" in result.failure_reason.casefold()


def test_service_degrades_dimension_encoder_rejection_to_typed_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, runtime, observer, writer, service = _service_fixture()

    def reject_scope(*_args) -> dict[str, str]:
        raise ValueError("synthetic canonical scope rejection")

    monkeypatch.setattr(
        "src.packet_tracer_mcp.application.use_cases.poe_delivery_qualification."
        "_observation_dimensions",
        reject_scope,
    )

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.observation_status is ObservationStatus.OBSERVED
    assert result.verification_status is VerificationStatus.FAILED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.capability_result.dimensions == {}
    assert "canonical scope rejection" in result.failure_reason
    assert len(writer.snapshots) == 1
    assert writer.snapshots[0].session.results[0].evidence() is None


def test_visible_non_discriminating_comparison_is_failed_not_unobservable() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    observer.mutate = lambda item: setattr(
        item.bindings[0].comparison,
        "state",
        PoEDeliveryArmState.POWERED,
    )

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.observation_status is ObservationStatus.OBSERVED
    assert result.verification_status is VerificationStatus.FAILED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN


def test_missing_arm_prerequisite_is_unobservable_not_failed() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    observer.mutate = lambda item: setattr(
        item.bindings[0].comparison,
        "endpoint_settled",
        False,
    )

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.observation_status is ObservationStatus.UNOBSERVABLE
    assert result.verification_status is VerificationStatus.UNVERIFIED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN


def test_service_retains_all_cleanup_failures_and_invalidates_positive_observation() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    runtime.delete_failures = {
        "__MCP_POE_fixed-session_CANDIDATE_ENDPOINT_01",
        "__MCP_POE_fixed-session_COMPARISON_ENDPOINT_02",
    }

    result = service.qualify(request)

    assert result.cleanup_status is CleanupStatus.DIRTY_SESSION
    assert set(result.cleanup_failed) == runtime.delete_failures
    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert writer.snapshots[0].reusable is False
    assert writer.snapshots[0].session.results[0].evidence() is None


def test_service_requires_exact_final_inventory_restoration() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    runtime.final_fingerprint = "inventory-drifted"

    result = service.qualify(request)

    assert result.inventory_restored is False
    assert result.cleanup_status is CleanupStatus.DIRTY_SESSION
    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert writer.snapshots[0].reusable is False


def test_service_fails_closed_when_created_model_identity_drifts() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    runtime.identity_drift = True

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.EXECUTION_ERROR
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert observer.calls == 0
    assert all(f"delete:{name}" in runtime.calls for name in result.attempted_identities)


def test_service_fails_closed_when_runtime_build_is_not_exact() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    runtime.packet_tracer_build = lambda: "Packet Tracer 8.2"

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.EXECUTION_ERROR
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.attempted_identities == []
    assert observer.calls == 0


def test_runtime_error_remains_execution_error_when_cleanup_also_fails() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    runtime.fail_operation = "create"
    runtime.delete_failures.add("__MCP_POE_fixed-session_CANDIDATE_ENDPOINT_01")

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.EXECUTION_ERROR
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.cleanup_failed == ["__MCP_POE_fixed-session_CANDIDATE_ENDPOINT_01"]


def test_invalid_duplicate_authorization_request_fails_closed_without_mutation() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    request.bindings[1].candidate_port = request.bindings[0].candidate_port
    request.bindings[1].endpoint_model = request.bindings[0].endpoint_model
    request.bindings[1].endpoint_port = request.bindings[0].endpoint_port

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.EXECUTION_ERROR
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.attempted_identities == []
    assert "duplicate candidate" in result.failure_reason.casefold()


def test_snapshot_persistence_failure_demotes_in_memory_positive_claim() -> None:
    request, runtime, observer, writer, service = _service_fixture()
    writer.raise_error = True

    result = service.qualify(request)

    assert result.execution_status is ProbeExecutionStatus.EXECUTION_ERROR
    assert result.observation_status is ObservationStatus.OBSERVED
    assert result.verification_status is VerificationStatus.FAILED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.capability_result.verified is False
    assert result.capability_result.context is not None
    assert result.capability_result.context.result_status is CapabilityStatus.UNKNOWN
    assert result.capability_result.evidence() is None
    assert result.runtime_snapshot_path is None


def test_session_safety_gate_runs_after_cleanup_and_before_snapshot_persistence() -> None:
    request = _request(bindings=2)
    runtime = FakeRuntime(request)
    observer = FakeObserver()
    writer = FakeSnapshotWriter()

    def assert_gate_order() -> None:
        assert runtime.calls[-1] == "restore:inventory-before"
        assert writer.snapshots == []

    safety = FakeSessionSafety(
        session_reusable=False,
        positive_claim_allowed=False,
        integrity_verified=False,
        crash_detected=True,
        failure_reasons=("synthetic post-deadline crash",),
        on_finalize=assert_gate_order,
    )
    service = PoEDeliveryQualificationService(
        runtime=runtime,
        observer=observer,
        snapshots=writer,
        session_safety=safety,
        session_id_factory=lambda: "fixed-session",
        clock=lambda: datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc),
        observation_window_seconds=120,
    )

    result = service.qualify(request)

    assert safety.calls == 1
    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.verification_status is VerificationStatus.FAILED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.capability_result.verified is False
    assert result.capability_result.evidence() is None
    assert result.live_session_safety.session_reusable is False
    assert result.live_session_safety.integrity_verified is False
    assert result.live_session_safety.crash_detected is True
    assert "post-deadline crash" in result.failure_reason
    assert len(writer.snapshots) == 1
    snapshot = writer.snapshots[0]
    assert snapshot.reusable is False
    assert snapshot.session.results[0].context is not None
    assert snapshot.session.results[0].context.live_session_safety is not None
    assert not snapshot.session.results[0].context.live_session_safety.session_reusable
    assert snapshot.session.results[0].evidence() is None


def test_session_safety_exception_is_fail_closed_before_snapshot_persistence() -> None:
    request = _request(bindings=2)
    runtime = FakeRuntime(request)
    observer = FakeObserver()
    writer = FakeSnapshotWriter()
    safety = FakeSessionSafety(raise_error=True)
    service = PoEDeliveryQualificationService(
        runtime=runtime,
        observer=observer,
        snapshots=writer,
        session_safety=safety,
        session_id_factory=lambda: "fixed-session",
        clock=lambda: datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc),
        observation_window_seconds=120,
    )

    result = service.qualify(request)

    assert safety.calls == 1
    assert result.execution_status is ProbeExecutionStatus.VERIFY_FAILED
    assert result.verification_status is VerificationStatus.FAILED
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.live_session_safety.session_reusable is False
    assert result.live_session_safety.integrity_verified is False
    assert result.live_session_safety.crash_detected is None
    assert "safety finalization failed" in result.failure_reason.casefold()
    assert writer.snapshots[0].reusable is False
    assert writer.snapshots[0].session.results[0].evidence() is None


def test_real_file_safety_evidence_is_persisted_before_positive_release(
    tmp_path: Path,
) -> None:
    request = _request(bindings=2)
    runtime = FakeRuntime(request)
    observer = FakeObserver()
    writer = FakeSnapshotWriter()
    canonical = tmp_path / "canonical.pts"
    canonical.write_bytes(b"canonical Packet Tracer module")
    safety = PacketTracerLiveSessionSafety(
        file_guard=PacketTracerLiveFileGuard(
            canonical_path=canonical,
            disposable_root=tmp_path / "sessions",
            run_identity="fixed-session",
        ),
        runtime_health=lambda: True,
        crash_detector=lambda: False,
    )
    identity = safety.prepare()
    service = PoEDeliveryQualificationService(
        runtime=runtime,
        observer=observer,
        snapshots=writer,
        session_safety=safety,
        session_id_factory=lambda: "fixed-session",
        clock=lambda: datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc),
        observation_window_seconds=120,
    )

    result = service.qualify(request)

    assert result.capability_result.status is CapabilityStatus.SUPPORTED
    persisted = writer.snapshots[0].session.results[0]
    assert persisted.evidence() is not None
    assert persisted.context is not None
    file_evidence = persisted.context.live_session_safety
    assert file_evidence is not None
    assert file_evidence.canonical_path == identity.canonical_path
    assert file_evidence.canonical_pre_run_sha256 == identity.canonical_sha256
    assert file_evidence.canonical_observed_post_run_sha256 == identity.canonical_sha256
    assert file_evidence.canonical_verified_sha256 == identity.canonical_sha256
    assert file_evidence.disposable_path == identity.disposable_path
    assert file_evidence.disposable_pre_run_sha256 == identity.disposable_sha256
    assert file_evidence.disposable_post_run_sha256 == identity.disposable_sha256
    relocated = writer.snapshots[0].model_copy(deep=True)
    relocated_safety = relocated.session.results[0].context.live_session_safety
    assert relocated_safety is not None
    relocated_safety.canonical_path = str((tmp_path / "relocated.pts").resolve())
    relocated_safety.disposable_path = str((tmp_path / "other.pts").resolve())
    assert relocated.stable_hash() == writer.snapshots[0].stable_hash()


def test_real_disposable_pts_change_blocks_persisted_positive_claim(
    tmp_path: Path,
) -> None:
    request = _request(bindings=2)
    runtime = FakeRuntime(request)
    observer = FakeObserver()
    writer = FakeSnapshotWriter()
    canonical = tmp_path / "canonical.pts"
    canonical.write_bytes(b"canonical Packet Tracer module")
    safety = PacketTracerLiveSessionSafety(
        file_guard=PacketTracerLiveFileGuard(
            canonical_path=canonical,
            disposable_root=tmp_path / "sessions",
            run_identity="fixed-session",
        ),
        runtime_health=lambda: True,
        crash_detector=lambda: False,
    )
    identity = safety.prepare()
    observer.mutate = lambda _item: Path(identity.disposable_path).write_bytes(
        b"unexpected post-run bytes"
    )
    service = PoEDeliveryQualificationService(
        runtime=runtime,
        observer=observer,
        snapshots=writer,
        session_safety=safety,
        session_id_factory=lambda: "fixed-session",
        clock=lambda: datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc),
        observation_window_seconds=120,
    )

    result = service.qualify(request)

    assert canonical.read_bytes() == b"canonical Packet Tracer module"
    assert result.capability_result.status is CapabilityStatus.UNKNOWN
    assert result.live_session_safety.disposable_modified is True
    persisted = writer.snapshots[0].session.results[0]
    assert persisted.context is not None
    assert persisted.context.live_session_safety is not None
    assert persisted.context.live_session_safety.disposable_modified is True
    assert persisted.evidence() is None


@pytest.mark.parametrize(
    "unsafe_update",
    [
        {"crash_detected": True},
        {"integrity_verified": False},
        {"canonical_pre_run_sha256": None},
        {"disposable_post_run_sha256": "b" * 64},
        {
            "disposable_pre_run_sha256": "b" * 64,
            "disposable_post_run_sha256": "b" * 64,
        },
    ],
    ids=[
        "crash",
        "integrity",
        "missing-hash",
        "changed-disposable",
        "wrong-disposable-origin",
    ],
)
def test_loaded_contradictory_safety_context_never_releases_evidence(
    unsafe_update: dict[str, object],
) -> None:
    request, _runtime, _observer, writer, service = _service_fixture()
    service.qualify(request)
    snapshot = writer.snapshots[0].model_copy(deep=True)
    persisted = snapshot.session.results[0]
    assert persisted.context is not None
    assert persisted.context.live_session_safety is not None
    persisted.context.live_session_safety = (
        persisted.context.live_session_safety.model_copy(update=unsafe_update)
    )

    assert persisted.evidence() is None
    assert snapshot.reusable is False


def test_legacy_decided_poe_result_without_session_safety_cannot_release_claim() -> None:
    request, _runtime, _observer, writer, service = _service_fixture()
    service.qualify(request)
    legacy = writer.snapshots[0].session.results[0].model_copy(deep=True)
    assert legacy.context is not None
    legacy.context.live_session_safety = None

    assert poe_claim_has_delivery_basis(legacy) is False
    evidence = legacy.evidence()
    assert evidence is not None
    assert evidence.status is CapabilityStatus.UNKNOWN
    assert evidence.observed_value is None
    assert evidence.dimensions == {}
