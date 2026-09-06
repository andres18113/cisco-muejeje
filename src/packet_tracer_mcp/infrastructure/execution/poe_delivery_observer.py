"""Synchronous visual-observation adapter for governed PoE qualification.

The acquisition mechanism is injected so this module has no dependency on a
particular UI automation stack.  This adapter owns the governed request and
receipt boundary: a capture is requested exactly once, tied to the exact
fixture episode, received before the caller's deadline, attributed, validated,
and only then converted into a ``PoEDeliveryManualObservation``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from ...domain.enterprise.models.poe_delivery import (
    PoEDeliveryBindingObservation,
    PoEDeliveryFixtureIdentity,
    PoEDeliveryManualObservation,
    PoEDeliveryQualificationRequest,
)
from ...domain.enterprise.rules.poe_delivery import (
    validate_poe_delivery_observation_receipt,
)


@dataclass(frozen=True)
class PoEVisualCaptureRequest:
    """Exact identity and time envelope handed to one visual capture call."""

    request_id: str
    requested_at: datetime
    deadline_utc: datetime
    fixture_fingerprint: str
    request: PoEDeliveryQualificationRequest
    fixture: PoEDeliveryFixtureIdentity


@dataclass(frozen=True)
class PoEVisualCaptureReceipt:
    """Facts returned synchronously by the injected visual capture mechanism."""

    request_id: str
    capture_id: str
    fixture_fingerprint: str
    observer_id: str
    captured_at: datetime
    method: str
    simultaneous: bool
    bindings: tuple[PoEDeliveryBindingObservation, ...]


class GovernedPoEDeliveryObserver:
    """Turn one fresh, identity-bound visual receipt into domain evidence."""

    def __init__(
        self,
        *,
        capture: Callable[
            [PoEVisualCaptureRequest], PoEVisualCaptureReceipt | None
        ],
        clock: Callable[[], datetime] | None = None,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._capture = capture
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._request_id_factory = request_id_factory or (
            lambda: uuid4().hex
        )

    def observe(
        self,
        request: PoEDeliveryQualificationRequest,
        fixture: PoEDeliveryFixtureIdentity,
        deadline_utc: datetime,
    ) -> PoEDeliveryManualObservation | None:
        """Perform one complete synchronous capture, with no retry or waiting."""

        if not _is_utc(deadline_utc):
            return None
        requested_at = self._clock()
        if not _is_utc(requested_at) or requested_at > deadline_utc:
            return None
        request_id = self._request_id_factory()
        if not request_id.strip() or request_id != request_id.strip():
            return None
        fixture_fingerprint = _fixture_fingerprint(request, fixture)
        capture_request = PoEVisualCaptureRequest(
            request_id=request_id,
            requested_at=requested_at,
            deadline_utc=deadline_utc,
            fixture_fingerprint=fixture_fingerprint,
            request=request.model_copy(deep=True),
            fixture=fixture.model_copy(deep=True),
        )

        try:
            receipt = self._capture(capture_request)
        except Exception:
            return None
        received_at = self._clock()
        if (
            not _is_utc(received_at)
            or received_at < requested_at
            or received_at > deadline_utc
        ):
            return None
        if not isinstance(receipt, PoEVisualCaptureReceipt):
            return None
        if (
            receipt.request_id != request_id
            or receipt.fixture_fingerprint != fixture_fingerprint
            or not receipt.capture_id.strip()
            or receipt.capture_id != receipt.capture_id.strip()
            or not _is_utc(receipt.captured_at)
            or not requested_at <= receipt.captured_at <= received_at
        ):
            return None

        observation = PoEDeliveryManualObservation(
            observer_id=receipt.observer_id,
            observed_at=receipt.captured_at,
            method=receipt.method,
            simultaneous=receipt.simultaneous,
            bindings=[item.model_copy(deep=True) for item in receipt.bindings],
        )
        validation = validate_poe_delivery_observation_receipt(
            request, fixture, observation,
        )
        return observation if validation.is_valid else None


def _fixture_fingerprint(
    request: PoEDeliveryQualificationRequest,
    fixture: PoEDeliveryFixtureIdentity,
) -> str:
    payload = {
        "request": request.model_dump(mode="json"),
        "fixture": fixture.model_dump(mode="json"),
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_utc(value: datetime) -> bool:
    return (
        value.tzinfo is not None
        and value.utcoffset() is not None
        and value.utcoffset().total_seconds() == 0
    )
