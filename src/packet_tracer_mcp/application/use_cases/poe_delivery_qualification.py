"""Governed powered-device delivery qualification orchestration.

This use case owns lifecycle and policy ordering.  Infrastructure supplies only
typed fixture primitives; a manual observer supplies only attributed visible
state.  Neither dependency can promote a capability by itself.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from ..live_session_safety import LiveSessionSafety
from ...domain.enterprise.models.capabilities import CapabilityStatus, EvidenceSource
from ...domain.enterprise.models.discovery import (
    BackendVersionProvenance,
    CapabilityBackend,
    CapabilityProbeResult,
    CapabilitySnapshot,
    CapabilityVerificationMethod,
    CleanupStatus,
    LiveSessionSafetyEvidence,
    ProbeContext,
    ProbeExecutionStatus,
    ProbeIsolationLevel,
    ProbeSession,
    ProbeSessionResult,
    inventory_restoration_matches,
    semantic_fingerprint,
)
from ...domain.enterprise.models.poe_delivery import (
    PoEDeliveryArmState,
    PoEDeliveryBindingFixtureIdentity,
    PoEDeliveryDeviceIdentity,
    PoEDeliveryFixtureIdentity,
    PoEDeliveryLinkIdentity,
    PoEDeliveryManualObservation,
    PoEDeliveryQualificationRequest,
    PoEDeliveryQualificationResult,
)
from ...domain.enterprise.models.evidence import (
    ObservationStatus,
    VerificationStatus,
)
from ...domain.enterprise.rules.poe_delivery import (
    validate_poe_delivery_device,
    validate_poe_delivery_fixture,
    validate_poe_delivery_observation,
    validate_poe_delivery_request,
)
from ...domain.enterprise.rules.live_session_safety import (
    validate_live_session_positive_admission,
)
from ...domain.enterprise.services.poe_claims import (
    PoEAuthorizedBinding,
    PoEDeliveryClaimScope,
    PoEDeliveryTestedBinding,
    encode_poe_delivery_dimensions,
)


_PROBE_ID = "poe-delivery-qualification"
_PROBE_VERSION = "2"
_CANDIDATE_ARM = "candidate"
_COMPARISON_ARM = "comparison"


class PoEDeliveryFixtureRuntime(Protocol):
    """Packet Tracer fixture primitives; no delivery judgment lives here."""

    def packet_tracer_build(self) -> str | None: ...

    def inventory_fingerprint(self) -> str: ...

    def create_device(
        self,
        model: str,
        temporary_name: str,
        required_ports: tuple[str, ...],
        *,
        arm: str | None = None,
    ) -> PoEDeliveryDeviceIdentity: ...

    def create_link(
        self,
        switch: PoEDeliveryDeviceIdentity,
        switch_port: str,
        endpoint: PoEDeliveryDeviceIdentity,
        endpoint_port: str,
    ) -> PoEDeliveryLinkIdentity: ...

    def delete_device(self, temporary_name: str) -> bool: ...

    def wait_for_inventory_fingerprint(self, expected: str) -> str: ...


class PoEDeliveryObserver(Protocol):
    """One observer invocation covers the complete simultaneous fixture."""

    def observe(
        self,
        request: PoEDeliveryQualificationRequest,
        fixture: PoEDeliveryFixtureIdentity,
        deadline_utc: datetime,
    ) -> PoEDeliveryManualObservation | None: ...


class CapabilitySnapshotWriter(Protocol):
    def save_runtime(self, snapshot: CapabilitySnapshot) -> Path: ...


class _FixtureValidationError(RuntimeError):
    pass


class PoEDeliveryQualificationService:
    def __init__(
        self,
        *,
        runtime: PoEDeliveryFixtureRuntime,
        observer: PoEDeliveryObserver,
        snapshots: CapabilitySnapshotWriter,
        session_safety: LiveSessionSafety,
        session_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        observation_window_seconds: float = 300.0,
    ) -> None:
        self._runtime = runtime
        self._observer = observer
        self._snapshots = snapshots
        self._session_safety = session_safety
        self._session_id_factory = session_id_factory or (
            lambda: uuid4().hex[:12]
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._observation_window_seconds = observation_window_seconds

    def qualify(
        self, request: PoEDeliveryQualificationRequest,
    ) -> PoEDeliveryQualificationResult:
        session_id = self._session_id_factory()
        prefix = f"__MCP_POE_{session_id}"
        attempted: list[str] = []
        created: list[str] = []
        endpoint_attempts: list[str] = []
        switch_attempts: list[str] = []
        deleted: list[str] = []
        cleanup_failed: list[str] = []
        failure_reasons: list[str] = []
        initial_fingerprint = ""
        final_fingerprint = ""
        inventory_restored: bool | None = None
        observation: PoEDeliveryManualObservation | None = None
        observation_valid = False
        fixture: PoEDeliveryFixtureIdentity | None = None
        execution_status = ProbeExecutionStatus.EXECUTION_ERROR
        observation_status = ObservationStatus.PROBE_FAILED
        verification_status = VerificationStatus.UNVERIFIED
        live_session_safety: LiveSessionSafetyEvidence | None = None

        request_validation = validate_poe_delivery_request(request)
        if not request_validation.is_valid:
            failure_reasons.extend(request_validation.error_messages())

        try:
            initial_fingerprint = self._runtime.inventory_fingerprint()
            if not initial_fingerprint:
                raise RuntimeError("Initial inventory fingerprint was not observed.")
            observed_build = self._runtime.packet_tracer_build()
            if observed_build != request.packet_tracer_build:
                raise RuntimeError(
                    "Exact Packet Tracer build identity does not match the qualification request."
                )
            if not request_validation.is_valid:
                raise _FixtureValidationError("PoE qualification request is incomplete.")
            fixture = self._create_fixture(
                request,
                prefix,
                attempted,
                created,
                endpoint_attempts,
                switch_attempts,
            )
            fixture_validation = validate_poe_delivery_fixture(request, fixture)
            if not fixture_validation.is_valid:
                raise _FixtureValidationError(
                    " ".join(fixture_validation.error_messages())
                )
            try:
                observation_started = self._clock()
                observation_deadline = observation_started + timedelta(
                    seconds=self._observation_window_seconds
                )
                observation = self._observer.observe(
                    request,
                    fixture,
                    observation_deadline,
                )
                observation_returned_at = self._clock()
            except Exception as exc:
                execution_status = ProbeExecutionStatus.VERIFY_FAILED
                observation_status = ObservationStatus.UNOBSERVABLE
                failure_reasons.append(f"PoE observer failed: {exc}")
            else:
                if observation is None:
                    execution_status = ProbeExecutionStatus.VERIFY_FAILED
                    observation_status = ObservationStatus.UNOBSERVABLE
                    failure_reasons.append(
                        "PoE observer returned no visible-state observation; delivery is unobservable."
                    )
                else:
                    validation = validate_poe_delivery_observation(
                        request, fixture, observation,
                    )
                    observation_valid = validation.is_valid
                    returned_after_deadline = (
                        observation_returned_at > observation_deadline
                    )
                    if returned_after_deadline:
                        observation_valid = False
                        failure_reasons.append(
                            "PoE observation returned after the bounded observation deadline."
                        )
                    timestamp_is_utc = (
                        observation.observed_at.tzinfo is not None
                        and observation.observed_at.utcoffset() is not None
                        and observation.observed_at.utcoffset().total_seconds() == 0
                    )
                    if timestamp_is_utc and not (
                        observation_started <= observation.observed_at <= observation_deadline
                    ):
                        observation_valid = False
                        failure_reasons.append(
                            "PoE observation timestamp is outside the bounded observation window."
                        )
                    if observation_valid:
                        execution_status = ProbeExecutionStatus.VERIFIED
                        observation_status = ObservationStatus.OBSERVED
                        verification_status = VerificationStatus.VERIFIED
                    else:
                        execution_status = ProbeExecutionStatus.VERIFY_FAILED
                        observation_status = (
                            ObservationStatus.UNOBSERVABLE
                            if returned_after_deadline
                            or _observation_is_unobservable(request, observation)
                            else ObservationStatus.OBSERVED
                        )
                        verification_status = (
                            VerificationStatus.UNVERIFIED
                            if observation_status is ObservationStatus.UNOBSERVABLE
                            else VerificationStatus.FAILED
                        )
                        failure_reasons.extend(validation.error_messages())
        except Exception as exc:
            if not failure_reasons or str(exc) not in " ".join(failure_reasons):
                failure_reasons.append(str(exc))
            execution_status = ProbeExecutionStatus.EXECUTION_ERROR
        finally:
            self._cleanup(
                endpoint_attempts,
                switch_attempts,
                deleted,
                cleanup_failed,
                failure_reasons,
            )
            if initial_fingerprint:
                try:
                    final_fingerprint = self._runtime.wait_for_inventory_fingerprint(
                        initial_fingerprint
                    )
                except Exception as exc:
                    failure_reasons.append(f"Inventory restoration was unobservable: {exc}")
                else:
                    inventory_restored = (
                        bool(final_fingerprint)
                        and inventory_restoration_matches(
                            initial_fingerprint, final_fingerprint,
                        )
                    )

        cleanup_status = (
            CleanupStatus.CLEAN
            if attempted and not cleanup_failed and inventory_restored is True
            else CleanupStatus.NOT_REQUIRED
            if not attempted and not cleanup_failed
            else CleanupStatus.DIRTY_SESSION
        )
        clean_restoration = (
            cleanup_status is CleanupStatus.CLEAN
            and inventory_restored is True
            and set(deleted) == set(attempted)
        )
        try:
            live_safety = self._session_safety.finalize()
        except Exception as exc:
            live_session_safety = LiveSessionSafetyEvidence(
                failure_reasons=[
                    f"LIVE session safety finalization failed: {exc}"
                ],
            )
        else:
            live_session_safety = live_safety
        failure_reasons.extend(live_session_safety.failure_reasons)
        live_claim_allowed = validate_live_session_positive_admission(
            live_session_safety,
        ).is_valid

        supported = observation_valid and clean_restoration and live_claim_allowed
        if observation_valid and not clean_restoration:
            verification_status = VerificationStatus.FAILED
            failure_reasons.append(
                "Valid delivery observation is not reusable because cleanup/restoration is incomplete."
            )
        if observation_valid and clean_restoration and not live_claim_allowed:
            verification_status = VerificationStatus.FAILED
            failure_reasons.append(
                "Valid delivery observation is not reusable because LIVE session "
                "health/file integrity did not pass."
            )
        if (
            not clean_restoration
            and attempted
            and execution_status is ProbeExecutionStatus.VERIFIED
        ):
            execution_status = ProbeExecutionStatus.VERIFY_FAILED
        if not supported and execution_status is ProbeExecutionStatus.VERIFIED:
            execution_status = ProbeExecutionStatus.VERIFY_FAILED

        dimensions: dict[str, str] = {}
        if supported and observation is not None:
            try:
                dimensions = _observation_dimensions(request, observation)
            except ValueError as exc:
                supported = False
                execution_status = ProbeExecutionStatus.VERIFY_FAILED
                verification_status = VerificationStatus.FAILED
                failure_reasons.append(
                    f"PoE delivery claim encoding failed closed: {exc}"
                )
        capability_result = self._capability_result(
            request=request,
            execution_status=execution_status,
            supported=supported,
            dimensions=dimensions,
            initial_fingerprint=initial_fingerprint,
            final_fingerprint=final_fingerprint,
            inventory_restored=inventory_restored,
            cleanup_status=cleanup_status,
            attempted=attempted,
            observation_status=observation_status,
            failure_reason=" ".join(reason for reason in failure_reasons if reason),
            live_session_safety=live_session_safety,
        )
        snapshot = _snapshot(
            request=request,
            session_id=session_id,
            result=capability_result,
            cleanup_status=cleanup_status,
            attempted=attempted,
            created=created,
            deleted=deleted,
            cleanup_failed=cleanup_failed,
            initial_fingerprint=initial_fingerprint,
            final_fingerprint=final_fingerprint,
            inventory_restored=inventory_restored,
        )
        runtime_snapshot_path: str | None = None
        try:
            runtime_snapshot_path = str(self._snapshots.save_runtime(snapshot))
        except Exception as exc:
            # Persistence is part of provenance.  A positive result that cannot
            # be retained must not escape as an authorized in-memory claim.
            failure_reasons.append(f"Runtime snapshot persistence failed: {exc}")
            execution_status = ProbeExecutionStatus.EXECUTION_ERROR
            verification_status = VerificationStatus.FAILED
            context = capability_result.context
            if context is not None:
                context = context.model_copy(update={
                    "result_status": CapabilityStatus.UNKNOWN,
                    "execution_status": execution_status,
                })
            capability_result = capability_result.model_copy(update={
                "status": CapabilityStatus.UNKNOWN,
                "execution_status": execution_status,
                "verified": False,
                "observed_value": None,
                "failure_reason": " ".join(failure_reasons),
                "context": context,
            })

        return PoEDeliveryQualificationResult(
            execution_status=execution_status,
            observation_status=observation_status,
            verification_status=verification_status,
            capability_result=capability_result,
            cleanup_status=cleanup_status,
            initial_inventory_fingerprint=initial_fingerprint,
            final_inventory_fingerprint=final_fingerprint,
            inventory_restored=inventory_restored,
            live_session_safety=live_session_safety,
            attempted_identities=attempted,
            created_identities=created,
            deleted_identities=deleted,
            cleanup_failed=cleanup_failed,
            fixture=fixture,
            observation=observation,
            failure_reason=" ".join(failure_reasons),
            runtime_snapshot_path=runtime_snapshot_path,
        )

    def _create_fixture(
        self,
        request: PoEDeliveryQualificationRequest,
        prefix: str,
        attempted: list[str],
        created: list[str],
        endpoint_attempts: list[str],
        switch_attempts: list[str],
    ) -> PoEDeliveryFixtureIdentity:
        candidate_switch = self._create_device(
            request.candidate_model,
            f"{prefix}_CANDIDATE_SWITCH",
            tuple(binding.candidate_port for binding in request.bindings),
            attempted,
            created,
            switch_attempts,
            _CANDIDATE_ARM,
        )
        comparison_switch = self._create_device(
            request.comparison_model,
            f"{prefix}_COMPARISON_SWITCH",
            tuple(binding.comparison_port for binding in request.bindings),
            attempted,
            created,
            switch_attempts,
            _COMPARISON_ARM,
        )
        binding_identities: list[PoEDeliveryBindingFixtureIdentity] = []
        for index, binding in enumerate(request.bindings, start=1):
            candidate_endpoint = self._create_device(
                binding.endpoint_model,
                f"{prefix}_CANDIDATE_ENDPOINT_{index:02d}",
                (binding.endpoint_port,),
                attempted,
                created,
                endpoint_attempts,
                _CANDIDATE_ARM,
            )
            comparison_endpoint = self._create_device(
                binding.endpoint_model,
                f"{prefix}_COMPARISON_ENDPOINT_{index:02d}",
                (binding.endpoint_port,),
                attempted,
                created,
                endpoint_attempts,
                _COMPARISON_ARM,
            )
            binding_identities.append(PoEDeliveryBindingFixtureIdentity(
                request=binding,
                candidate_switch=candidate_switch,
                comparison_switch=comparison_switch,
                candidate_endpoint=candidate_endpoint,
                comparison_endpoint=comparison_endpoint,
                candidate_link=self._runtime.create_link(
                    candidate_switch,
                    binding.candidate_port,
                    candidate_endpoint,
                    binding.endpoint_port,
                ),
                comparison_link=self._runtime.create_link(
                    comparison_switch,
                    binding.comparison_port,
                    comparison_endpoint,
                    binding.endpoint_port,
                ),
            ))
        return PoEDeliveryFixtureIdentity(
            candidate_switch=candidate_switch,
            comparison_switch=comparison_switch,
            bindings=binding_identities,
        )

    def _create_device(
        self,
        model: str,
        name: str,
        required_ports: tuple[str, ...],
        attempted: list[str],
        created: list[str],
        cleanup_group: list[str],
        arm: str,
    ) -> PoEDeliveryDeviceIdentity:
        attempted.append(name)
        cleanup_group.append(name)
        device = self._runtime.create_device(model, name, required_ports, arm=arm)
        # A returned identity proves that an object may exist even if its
        # model/ports drifted, so it must remain in the cleanup ledger.
        created.append(name)
        validation = validate_poe_delivery_device(
            device,
            expected_name=name,
            expected_model=model,
            expected_ports=required_ports,
        )
        if not validation.is_valid:
            raise _FixtureValidationError(" ".join(validation.error_messages()))
        return device

    def _cleanup(
        self,
        endpoints: list[str],
        switches: list[str],
        deleted: list[str],
        failed: list[str],
        failure_reasons: list[str],
    ) -> None:
        for name in [*reversed(endpoints), *reversed(switches)]:
            try:
                removed = self._runtime.delete_device(name)
            except Exception as exc:
                removed = False
                failure_reasons.append(f"Cleanup failed for {name}: {exc}")
            if removed:
                deleted.append(name)
            else:
                failed.append(name)
                failure_reasons.append(f"Cleanup did not verify deletion of {name}.")

    @staticmethod
    def _capability_result(
        *,
        request: PoEDeliveryQualificationRequest,
        execution_status: ProbeExecutionStatus,
        supported: bool,
        dimensions: dict[str, str],
        initial_fingerprint: str,
        final_fingerprint: str,
        inventory_restored: bool | None,
        cleanup_status: CleanupStatus,
        attempted: list[str],
        observation_status: ObservationStatus,
        failure_reason: str,
        live_session_safety: LiveSessionSafetyEvidence,
    ) -> CapabilityProbeResult:
        status = CapabilityStatus.SUPPORTED if supported else CapabilityStatus.UNKNOWN
        context = ProbeContext(
            probe_id=_PROBE_ID,
            probe_version=_PROBE_VERSION,
            backend=CapabilityBackend.PACKET_TRACER,
            backend_version=request.packet_tracer_build,
            device_model=request.candidate_model,
            environment_fingerprint=semantic_fingerprint({
                "backend": "packet_tracer",
                "build": request.packet_tracer_build,
            }),
            initial_inventory_hash=initial_fingerprint,
            final_inventory_hash=final_fingerprint,
            inventory_restored=inventory_restored,
            isolation_level=ProbeIsolationLevel.FRESH_SESSION_REQUIRED,
            mutations=[f"temporary-device-attempt:{name}" for name in attempted],
            cleanup_status=cleanup_status,
            result_status=status,
            execution_status=execution_status,
            probe_fingerprint=semantic_fingerprint({
                "probe_id": _PROBE_ID,
                "probe_version": _PROBE_VERSION,
                "request": request.model_dump(mode="json"),
            }),
            live_session_safety=live_session_safety,
        )
        return CapabilityProbeResult(
            probe_id=_PROBE_ID,
            model=request.candidate_model,
            capability="supports_poe",
            status=status,
            execution_status=execution_status,
            evidence_source=EvidenceSource.MANUAL_VERIFICATION,
            configured=bool(attempted),
            verified=supported,
            observed_value=len(request.bindings) if supported else None,
            raw_summary=(
                "Differential visible powered-device delivery observation completed."
                if supported else "PoE delivery remains UNKNOWN."
            ),
            failure_reason=failure_reason,
            packet_tracer_version=request.packet_tracer_build,
            verification_method=(
                CapabilityVerificationMethod.MANUAL_VERIFIED
                if observation_status is ObservationStatus.OBSERVED
                else CapabilityVerificationMethod.UNOBSERVABLE
            ),
            context=context,
            dimensions=dimensions,
        )


def _observation_dimensions(
    request: PoEDeliveryQualificationRequest,
    observation: PoEDeliveryManualObservation,
) -> dict[str, str]:
    scope = PoEDeliveryClaimScope(
        access_ports=tuple(binding.candidate_port for binding in request.bindings),
        tested_bindings=tuple(
            PoEDeliveryTestedBinding(
                switch_port=item.binding.candidate_port,
                comparison_port=item.binding.comparison_port,
                endpoint_model=item.binding.endpoint_model,
                endpoint_port=item.binding.endpoint_port,
                candidate_state=item.candidate.state.value,
                comparison_state=item.comparison.state.value,
                candidate_indicator=item.candidate.visible_indicator,
                comparison_indicator=item.comparison.visible_indicator,
                candidate_ready=(
                    item.candidate.switch_ready
                    and item.candidate.link_ready
                    and item.candidate.endpoint_settled
                ),
                comparison_ready=(
                    item.comparison.switch_ready
                    and item.comparison.link_ready
                    and item.comparison.endpoint_settled
                ),
            )
            for item in observation.bindings
        ),
        active_bindings=tuple(
            PoEAuthorizedBinding(
                switch_port=item.binding.candidate_port,
                endpoint_model=item.binding.endpoint_model,
                endpoint_port=item.binding.endpoint_port,
            )
            for item in observation.bindings
        ),
        simultaneous_active_ports=len(observation.bindings),
        comparison_model=request.comparison_model,
        observation_method=observation.method,
        observer_id=observation.observer_id,
        observed_at=(
            observation.observed_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        candidate_model=request.candidate_model,
        packet_tracer_build=request.packet_tracer_build,
        cleanup_status=CleanupStatus.CLEAN.value,
        inventory_restoration="restored",
    )
    return encode_poe_delivery_dimensions(scope)


def _observation_is_unobservable(
    request: PoEDeliveryQualificationRequest,
    observation: PoEDeliveryManualObservation,
) -> bool:
    if (
        not observation.observer_id.strip()
        or len(observation.bindings) != len(request.bindings)
    ):
        return True
    return any(
        arm.state is PoEDeliveryArmState.UNOBSERVABLE
        or not arm.visible_indicator.strip()
        or not arm.switch_ready
        or not arm.link_ready
        or not arm.endpoint_settled
        for item in observation.bindings
        for arm in (item.candidate, item.comparison)
    )


def _snapshot(
    *,
    request: PoEDeliveryQualificationRequest,
    session_id: str,
    result: CapabilityProbeResult,
    cleanup_status: CleanupStatus,
    attempted: list[str],
    created: list[str],
    deleted: list[str],
    cleanup_failed: list[str],
    initial_fingerprint: str,
    final_fingerprint: str,
    inventory_restored: bool | None,
) -> CapabilitySnapshot:
    session = ProbeSession(
        session_id=f"poe-{session_id}",
        packet_tracer_version=request.packet_tracer_build,
        created_devices=list(created),
        mutations=[f"temporary-device-attempt:{name}" for name in attempted],
        cleanup_status=cleanup_status,
        warnings=list(cleanup_failed),
    )
    return CapabilitySnapshot(
        packet_tracer_version=request.packet_tracer_build,
        backend_version_provenance=BackendVersionProvenance.DECLARED_ENVIRONMENT,
        backend=CapabilityBackend.PACKET_TRACER,
        environment_fingerprint=result.context.environment_fingerprint if result.context else "",
        probe_fingerprints={_PROBE_ID: result.context.probe_fingerprint if result.context else ""},
        initial_inventory_hash=initial_fingerprint,
        final_inventory_hash=final_fingerprint,
        inventory_restored=inventory_restored,
        session=ProbeSessionResult(
            session=session,
            results=[result],
            cleanup_deleted=list(deleted),
            cleanup_failed=list(cleanup_failed),
        ),
    )
