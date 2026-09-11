"""Exact-build policy for modules a fresh Packet Tracer model needs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactoryModuleRequirement:
    """One closed factory requirement; callers never choose insertion details."""

    packet_tracer_build: str
    device_model: str
    module_model: str
    module_type: int
    required_count: int
    expected_available_watts_before: float
    expected_available_watts: float


class FactoryModulePolicyError(ValueError):
    """The model is governed, but no policy exists for this exact build."""


_C3650_BUILD = "9.0.1.0858"
_C3650_REQUIREMENT = FactoryModuleRequirement(
    packet_tracer_build=_C3650_BUILD,
    device_model="3650-24PS",
    module_model="AC-POWER-SUPPLY",
    module_type=4,
    required_count=1,
    expected_available_watts_before=0.0,
    expected_available_watts=390.0,
)


def factory_module_requirement_for(
    device_model: str,
    packet_tracer_build: str,
) -> FactoryModuleRequirement | None:
    """Resolve the closed model/build policy without accepting aliases."""

    if type(device_model) is not str or type(packet_tracer_build) is not str:
        raise TypeError("Factory module policy requires exact strings")
    if device_model != _C3650_REQUIREMENT.device_model:
        return None
    if packet_tracer_build != _C3650_REQUIREMENT.packet_tracer_build:
        raise FactoryModulePolicyError(
            "3650-24PS factory preparation requires the exact Packet Tracer build "
            + _C3650_REQUIREMENT.packet_tracer_build
        )
    return _C3650_REQUIREMENT
