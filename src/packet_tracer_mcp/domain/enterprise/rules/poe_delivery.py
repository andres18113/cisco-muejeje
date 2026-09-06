"""Fail-closed validation for powered-device delivery observations."""

from __future__ import annotations

from collections.abc import Iterable

from ...models.errors import ErrorCode, PlanError, ValidationResult
from ..models.poe_delivery import (
    PoEDeliveryArmObservation,
    PoEDeliveryArmState,
    PoEDeliveryBindingFixtureIdentity,
    PoEDeliveryBindingRequest,
    PoEDeliveryDeviceIdentity,
    PoEDeliveryFixtureIdentity,
    PoEDeliveryLinkEndpoint,
    PoEDeliveryLinkIdentity,
    PoEDeliveryManualObservation,
    PoEDeliveryQualificationRequest,
)


def validate_poe_delivery_request(
    request: PoEDeliveryQualificationRequest,
) -> ValidationResult:
    errors: list[PlanError] = []
    for field_name, value in (
        ("Packet Tracer build", request.packet_tracer_build),
        ("candidate model", request.candidate_model),
        ("comparison model", request.comparison_model),
    ):
        if not value.strip():
            errors.append(_error(f"PoE qualification requires an exact {field_name}."))
        elif value != value.strip():
            errors.append(_error(
                f"Exact {field_name} cannot contain leading or trailing whitespace."
            ))
    if not request.bindings:
        errors.append(_error("PoE qualification requires one non-empty simultaneous binding group."))
    keys: set[tuple[str, str, str, str]] = set()
    candidate_bindings: set[tuple[str, str, str]] = set()
    candidate_ports: set[str] = set()
    comparison_ports: set[str] = set()
    for binding in request.bindings:
        key = _binding_key(binding)
        if any(not value.strip() for value in key):
            errors.append(_error("Every PoE binding requires exact switch ports and endpoint identity."))
        elif any(value != value.strip() for value in key):
            errors.append(_error(
                "Exact PoE binding identity cannot contain leading or trailing whitespace."
            ))
        if key in keys:
            errors.append(_error("Duplicate PoE binding requests cannot widen one observation group."))
        keys.add(key)
        candidate_binding = (
            binding.candidate_port, binding.endpoint_model, binding.endpoint_port,
        )
        if candidate_binding in candidate_bindings:
            errors.append(_error("Duplicate candidate binding cannot widen PoE authorization."))
        candidate_bindings.add(candidate_binding)
        if binding.candidate_port in candidate_ports:
            errors.append(_error("Duplicate candidate port cannot authorize multiple powered endpoints."))
        candidate_ports.add(binding.candidate_port)
        if binding.comparison_port in comparison_ports:
            errors.append(_error("Duplicate comparison port cannot provide independent control coverage."))
        comparison_ports.add(binding.comparison_port)
    return ValidationResult(errors=errors)


def validate_poe_delivery_fixture(
    request: PoEDeliveryQualificationRequest,
    fixture: PoEDeliveryFixtureIdentity,
) -> ValidationResult:
    errors = list(validate_poe_delivery_request(request).errors)
    _check_device(
        fixture.candidate_switch,
        expected_name=fixture.candidate_switch.name,
        expected_model=request.candidate_model,
        expected_ports=(binding.candidate_port for binding in request.bindings),
        label="candidate switch",
        errors=errors,
    )
    _check_device(
        fixture.comparison_switch,
        expected_name=fixture.comparison_switch.name,
        expected_model=request.comparison_model,
        expected_ports=(binding.comparison_port for binding in request.bindings),
        label="comparison switch",
        errors=errors,
    )
    expected = {_binding_key(binding): binding for binding in request.bindings}
    seen: set[tuple[str, str, str, str]] = set()
    for identity in fixture.bindings:
        key = _binding_key(identity.request)
        if key in seen:
            errors.append(_error("Duplicate fixture binding identity is not one-to-one coverage."))
            continue
        seen.add(key)
        binding = expected.get(key)
        if binding is None:
            errors.append(_error("Fixture binding identity drifted outside the requested scope."))
            continue
        if identity.candidate_switch != fixture.candidate_switch:
            errors.append(_error("Candidate fixture switch identity is internally inconsistent."))
        if identity.comparison_switch != fixture.comparison_switch:
            errors.append(_error("Comparison fixture switch identity is internally inconsistent."))
        _check_binding_fixture(request, binding, identity, errors)
    if seen != set(expected):
        errors.append(_error("Fixture binding coverage is incomplete."))
    return ValidationResult(errors=errors)


def validate_poe_delivery_device(
    device: PoEDeliveryDeviceIdentity,
    *,
    expected_name: str,
    expected_model: str,
    expected_ports: Iterable[str],
) -> ValidationResult:
    errors: list[PlanError] = []
    _check_device(
        device,
        expected_name=expected_name,
        expected_model=expected_model,
        expected_ports=expected_ports,
        label="created device",
        errors=errors,
    )
    return ValidationResult(errors=errors)


def validate_poe_delivery_observation(
    request: PoEDeliveryQualificationRequest,
    fixture: PoEDeliveryFixtureIdentity,
    observation: PoEDeliveryManualObservation,
) -> ValidationResult:
    return _validate_poe_delivery_observation(
        request, fixture, observation, require_differential=True,
    )


def validate_poe_delivery_observation_receipt(
    request: PoEDeliveryQualificationRequest,
    fixture: PoEDeliveryFixtureIdentity,
    observation: PoEDeliveryManualObservation,
) -> ValidationResult:
    """Validate attributable visible evidence without deciding its outcome."""

    return _validate_poe_delivery_observation(
        request, fixture, observation, require_differential=False,
    )


def _validate_poe_delivery_observation(
    request: PoEDeliveryQualificationRequest,
    fixture: PoEDeliveryFixtureIdentity,
    observation: PoEDeliveryManualObservation,
    *,
    require_differential: bool,
) -> ValidationResult:
    errors = list(validate_poe_delivery_fixture(request, fixture).errors)
    if not observation.observer_id.strip():
        errors.append(_error("PoE observation requires an attributed observer identity."))
    elif observation.observer_id != observation.observer_id.strip():
        errors.append(_error(
            "PoE observer identity cannot contain leading or trailing whitespace."
        ))
    if (
        observation.observed_at.tzinfo is None
        or observation.observed_at.utcoffset() is None
        or observation.observed_at.utcoffset().total_seconds() != 0
    ):
        errors.append(_error("PoE observer timestamp must be UTC."))
    if observation.method != "manual_visible_power_state":
        errors.append(_error(
            "PoE observation method must be the governed manual visible power state method."
        ))
    if not observation.simultaneous:
        errors.append(_error("PoE delivery bindings must be observed in one simultaneous episode."))

    fixture_by_key = {
        _binding_key(identity.request): identity for identity in fixture.bindings
    }
    seen: set[tuple[str, str, str, str]] = set()
    for item in observation.bindings:
        key = _binding_key(item.binding)
        if key in seen:
            errors.append(_error("Duplicate PoE observation cannot count as independent coverage."))
            continue
        seen.add(key)
        identity = fixture_by_key.get(key)
        if identity is None:
            errors.append(_error("PoE observation identity is outside the fixture scope."))
            continue
        _check_arm(
            item.candidate,
            identity.candidate_switch,
            identity.candidate_endpoint,
            item.binding.candidate_port,
            item.binding.endpoint_port,
            PoEDeliveryArmState.POWERED,
            "candidate",
            errors,
            require_expected_state=require_differential,
        )
        _check_arm(
            item.comparison,
            identity.comparison_switch,
            identity.comparison_endpoint,
            item.binding.comparison_port,
            item.binding.endpoint_port,
            PoEDeliveryArmState.NOT_POWERED,
            "comparison",
            errors,
            require_expected_state=require_differential,
        )
    if seen != set(fixture_by_key):
        errors.append(_error("PoE observation coverage is incomplete."))
    return ValidationResult(errors=errors)


def _check_binding_fixture(
    request: PoEDeliveryQualificationRequest,
    binding: PoEDeliveryBindingRequest,
    identity: PoEDeliveryBindingFixtureIdentity,
    errors: list[PlanError],
) -> None:
    _check_device(
        identity.candidate_switch,
        expected_name=identity.candidate_switch.name,
        expected_model=request.candidate_model,
        expected_ports=(binding.candidate_port,),
        label="candidate switch",
        errors=errors,
    )
    _check_device(
        identity.comparison_switch,
        expected_name=identity.comparison_switch.name,
        expected_model=request.comparison_model,
        expected_ports=(binding.comparison_port,),
        label="comparison switch",
        errors=errors,
    )
    _check_device(
        identity.candidate_endpoint,
        expected_name=identity.candidate_endpoint.name,
        expected_model=binding.endpoint_model,
        expected_ports=(binding.endpoint_port,),
        label="candidate endpoint",
        errors=errors,
    )
    _check_device(
        identity.comparison_endpoint,
        expected_name=identity.comparison_endpoint.name,
        expected_model=binding.endpoint_model,
        expected_ports=(binding.endpoint_port,),
        label="comparison endpoint",
        errors=errors,
    )
    _check_link(
        identity.candidate_link,
        identity.candidate_switch,
        binding.candidate_port,
        identity.candidate_endpoint,
        binding.endpoint_port,
        "candidate",
        errors,
    )
    _check_link(
        identity.comparison_link,
        identity.comparison_switch,
        binding.comparison_port,
        identity.comparison_endpoint,
        binding.endpoint_port,
        "comparison",
        errors,
    )


def _check_device(
    device: PoEDeliveryDeviceIdentity,
    *,
    expected_name: str,
    expected_model: str,
    expected_ports: Iterable[str],
    label: str,
    errors: list[PlanError],
) -> None:
    required = set(expected_ports)
    if (
        not device.name.strip()
        or device.name != expected_name
        or device.model != expected_model
        or not required <= set(device.observed_ports)
    ):
        errors.append(_error(f"Exact {label} model/port identity was not observed."))


def _check_link(
    link: PoEDeliveryLinkIdentity,
    switch: PoEDeliveryDeviceIdentity,
    switch_port: str,
    endpoint: PoEDeliveryDeviceIdentity,
    endpoint_port: str,
    label: str,
    errors: list[PlanError],
) -> None:
    expected_first = PoEDeliveryLinkEndpoint(
        device_name=switch.name, device_model=switch.model, port=switch_port,
    )
    expected_second = PoEDeliveryLinkEndpoint(
        device_name=endpoint.name, device_model=endpoint.model, port=endpoint_port,
    )
    if link.first != expected_first or link.second != expected_second:
        errors.append(_error(f"Exact {label} link endpoint identity was not observed."))


def _check_arm(
    arm: PoEDeliveryArmObservation,
    switch: PoEDeliveryDeviceIdentity,
    endpoint: PoEDeliveryDeviceIdentity,
    switch_port: str,
    endpoint_port: str,
    expected_state: PoEDeliveryArmState,
    label: str,
    errors: list[PlanError],
    *,
    require_expected_state: bool,
) -> None:
    exact_identity = (
        arm.switch_name == switch.name
        and arm.switch_model == switch.model
        and arm.switch_port == switch_port
        and arm.endpoint_name == endpoint.name
        and arm.endpoint_model == endpoint.model
        and arm.endpoint_port == endpoint_port
    )
    if not exact_identity:
        errors.append(_error(f"Exact {label} observation identity does not match the fixture."))
    if not arm.visible_indicator.strip():
        errors.append(_error(f"The {label} observation requires a visible indicator."))
    elif arm.visible_indicator != arm.visible_indicator.strip():
        errors.append(_error(
            f"The {label} visible indicator cannot contain leading or trailing whitespace."
        ))
    missing_prerequisites = [
        name
        for name, ready in (
            ("switch_ready", arm.switch_ready),
            ("link_ready", arm.link_ready),
            ("endpoint_settled", arm.endpoint_settled),
        )
        if not ready
    ]
    if missing_prerequisites:
        errors.append(_error(
            f"The {label} state is unobservable without ready prerequisites: "
            + ", ".join(missing_prerequisites)
            + "."
        ))
    if arm.state is PoEDeliveryArmState.UNOBSERVABLE:
        errors.append(_error(f"The {label} powered-device state is unobservable."))
    elif require_expected_state and arm.state is not expected_state:
        errors.append(_error(
            f"The {label} arm did not provide the required differential power state."
        ))


def _binding_key(binding: PoEDeliveryBindingRequest) -> tuple[str, str, str, str]:
    return (
        binding.candidate_port,
        binding.comparison_port,
        binding.endpoint_model,
        binding.endpoint_port,
    )


def _error(message: str) -> PlanError:
    return PlanError(
        code=ErrorCode.CAPABILITY_PROBE_FAILED,
        message=message,
        suggestion="Keep capability UNKNOWN and repeat only in a fresh governed fixture.",
    )
