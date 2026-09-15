"""Resolve the productive PhoneControl from existing qualified capabilities."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from ...application.cp_scale_live.contracts import (
    CPScaleCallObservabilityEvidence,
    CPScaleCheckState,
    CPScalePreflightOutcome,
    CPScalePreflightResult,
    call_observations_required,
)
from ...application.cp_scale_live.errors import CanonicalLiveFailure
from ...application.ports.phone_control import PhoneControlPort
from ...domain.enterprise.services.call_observability import (
    decode_call_observability_probe,
)
from ...shared.utils import resolve_within
from ..persistence.capability_snapshot_store import CapabilitySnapshotStore
from .native_ui_phone_driver import PacketTracerNativeUiCallDriver
from .phone_control import (
    PacketTracerNativeUiPhoneControlAdapter,
    UnavailablePhoneControl,
)


class PacketTracerNativeUiPhoneControlProvider:
    """Select one exact driver only from reusable hash-pinned LIVE evidence."""

    def __init__(
        self,
        *,
        governed_root: str | Path,
        store: CapabilitySnapshotStore,
        exchange_dir: str | Path | None,
        driver_source_path: str | Path | None = None,
        readiness_probe: Callable[..., bool] | None = None,
    ) -> None:
        self._root = Path(governed_root).resolve()
        self._store = store
        self._exchange_dir = Path(exchange_dir) if exchange_dir else None
        self._driver_source = Path(driver_source_path) if driver_source_path else Path(
            __file__
        ).with_name("native_ui_phone_driver.py")
        self._readiness_probe = readiness_probe or (
            lambda driver, version, source_hash: driver.probe_readiness(
                version, source_hash,
            )
        )
        self.phone_control = UnavailablePhoneControl()
        self.capability_snapshot_hash = ""

    def phone_control_for(self, admitted: CPScalePreflightResult) -> PhoneControlPort:
        """Bind a voice runtime from the admitted preflight's own policy.

        The admitted target and qualification policy decide whether the strict
        call gate applies; no policy is resolved a second time. When the gate
        applies, only the adapter that ``read`` selected from qualified
        evidence and a fresh readiness handshake is returned;
        ``UnavailablePhoneControl`` is never substituted for it. Otherwise the
        explicit unavailable control is returned, so calls stay UNOBSERVABLE
        and are never promoted.
        """

        if (
            not isinstance(admitted, CPScalePreflightResult)
            or admitted.outcome is not CPScalePreflightOutcome.ADMITTED
        ):
            raise CanonicalLiveFailure(
                "PhoneControl binds only from an admitted CP-SCALE preflight."
            )
        if not call_observations_required(
            admitted.target,
            admitted.qualification_policy,
        ):
            return UnavailablePhoneControl()
        if (
            not self.capability_snapshot_hash
            or not isinstance(
                self.phone_control, PacketTracerNativeUiPhoneControlAdapter,
            )
        ):
            raise CanonicalLiveFailure(
                "The strict call gate applies but preflight selected no "
                "qualified PhoneControl; UnavailablePhoneControl is never "
                "substituted for call evidence."
            )
        return self.phone_control

    def read(self, packet_tracer_version: str) -> CPScaleCallObservabilityEvidence:
        self.phone_control = UnavailablePhoneControl()
        self.capability_snapshot_hash = ""
        if self._exchange_dir is None:
            return self._failed(
                packet_tracer_version,
                "No native-UI PhoneControl exchange directory is configured.",
            )
        try:
            driver_hash = hashlib.sha256(
                self._driver_source.read_bytes(),
            ).hexdigest()
            snapshots = self._store.list_verified(packet_tracer_version)
        except (OSError, ValueError) as exc:
            return self._failed(
                packet_tracer_version,
                f"Qualified PhoneControl evidence could not be read: {exc}",
            )
        for snapshot in reversed(snapshots):
            if (
                snapshot.packet_tracer_version != packet_tracer_version
                or snapshot.backend.value != "packet_tracer"
            ):
                continue
            for result in snapshot.session.results:
                authority = decode_call_observability_probe(
                    result,
                    packet_tracer_version=packet_tracer_version,
                    driver_source_sha256=driver_hash,
                )
                if authority is None or not snapshot.reusable:
                    continue
                try:
                    artifact = resolve_within(
                        self._root,
                        *Path(authority.evidence_path).parts,
                    )
                    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
                except (OSError, ValueError):
                    continue
                if artifact_hash != authority.evidence_sha256:
                    continue
                driver = PacketTracerNativeUiCallDriver(
                    exchange_dir=self._exchange_dir,
                    physical_phone_names={},
                    timeout_seconds=180.0,
                )
                try:
                    ready = self._readiness_probe(
                        driver,
                        packet_tracer_version,
                        driver_hash,
                    ) is True
                except Exception as exc:
                    return self._failed(
                        packet_tracer_version,
                        "Qualified native-UI PhoneControl readiness failed: "
                        f"{type(exc).__name__}: {exc}",
                    )
                if not ready:
                    return self._failed(
                        packet_tracer_version,
                        "Qualified native-UI PhoneControl provider is not ready.",
                    )
                self.phone_control = PacketTracerNativeUiPhoneControlAdapter(driver)
                self.capability_snapshot_hash = snapshot.stable_hash()
                return CPScaleCallObservabilityEvidence(
                    state=CPScaleCheckState.PASSED,
                    required=True,
                    expectation_results=authority.expectation_results,
                    provider_id=authority.provider_id,
                    execution_method=authority.execution_method,
                    packet_tracer_version=authority.packet_tracer_version,
                    call_control_models=authority.call_control_models,
                    phone_models=authority.phone_models,
                    qualification_run_identity=authority.run_identity,
                    qualification_executed_sha=authority.executed_sha,
                    evidence_path=authority.evidence_path,
                    evidence_sha256=authority.evidence_sha256,
                    driver_source_sha256=authority.driver_source_sha256,
                )
        return self._failed(
            packet_tracer_version,
            "No qualified observable PhoneControl capability matches this build and driver.",
        )

    @staticmethod
    def _failed(
        packet_tracer_version: str,
        error: str,
    ) -> CPScaleCallObservabilityEvidence:
        return CPScaleCallObservabilityEvidence(
            state=CPScaleCheckState.FAILED,
            required=True,
            packet_tracer_version=packet_tracer_version,
            error=error,
        )
