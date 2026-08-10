"""E8 capability baseline records measurements without optimistic defaults."""

from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    ConfigureSecurityNat,
    NatMode,
    SecurityCapabilityDimension as Dimension,
    SecurityCapabilityStatus as Status,
    SecurityVerificationKind,
    security_verification_capability,
)
from src.packet_tracer_mcp.infrastructure.catalog.security_capabilities import (
    packet_tracer_security_capabilities,
)
from tests.test_enterprise_security import _compile


def test_measured_2911_and_2960_security_capabilities_are_explicit():
    profiles = packet_tracer_security_capabilities()

    assert profiles["2911"].status(Dimension.ACL_READBACK) is Status.SUPPORTED
    assert profiles["2911"].status(Dimension.NAT_TRANSLATION_READBACK) is Status.SUPPORTED
    assert profiles["2911"].status(Dimension.NAT_INTERFACE_ROLE_READBACK) is Status.SUPPORTED
    assert profiles["2911"].status(Dimension.NAT_PAT_CONFIG) is Status.SUPPORTED
    assert profiles["2911"].status(Dimension.NAT_PAT_BEHAVIORAL) is Status.SUPPORTED
    assert profiles["2911"].status(Dimension.NAT_STATIC_CONFIG) is Status.UNKNOWN
    assert profiles["2911"].status(Dimension.NAT_DYNAMIC_CONFIG) is Status.UNKNOWN
    assert profiles["2911"].status(Dimension.NAT_STATIC_BEHAVIORAL) is Status.UNKNOWN
    assert profiles["2911"].status(Dimension.NAT_DYNAMIC_BEHAVIORAL) is Status.UNKNOWN
    assert profiles["2911"].status(Dimension.ACL_BEHAVIORAL) is Status.SUPPORTED
    assert profiles["2911"].status(Dimension.NAT_BEHAVIORAL) is Status.UNKNOWN
    assert profiles["2911"].status(Dimension.HARDENING_READBACK) is Status.SUPPORTED
    assert profiles["2960-24TT"].status(Dimension.PORT_SECURITY_READBACK) is Status.PARTIAL
    assert profiles["2960-24TT"].status(Dimension.DHCP_SNOOPING_READBACK) is Status.SUPPORTED
    assert profiles["2960-24TT"].status(Dimension.DAI_READBACK) is Status.PARTIAL


def test_unmeasured_models_and_behavior_do_not_inherit_generator_confidence():
    profiles = packet_tracer_security_capabilities()

    assert profiles["2811"].status(Dimension.ACL_CONFIG) is Status.UNKNOWN
    assert profiles["3560-24PS"].status(Dimension.DAI_CONFIG) is Status.UNKNOWN
    assert profiles["2960-24TT"].status(Dimension.PORT_SECURITY_BEHAVIORAL) is Status.UNKNOWN
    assert all(
        profiles["2811"].status(dimension) is Status.UNKNOWN
        for dimension in Dimension
    )
    assert all(
        profiles["3560-24PS"].status(dimension) is Status.UNKNOWN
        for dimension in Dimension
    )
    assert all(
        item.packet_tracer_version == "9.0.1.0858" for item in profiles.values()
    )


def test_nat_behavior_gate_is_bound_to_compiled_mode_not_generic_pat_evidence():
    plan = _compile().plan
    action = next(item for item in plan.actions if isinstance(item, ConfigureSecurityNat))
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind is SecurityVerificationKind.NAT_TRANSLATION
    )

    assert action.mode is NatMode.PAT
    assert security_verification_capability(expectation, action) is Dimension.NAT_PAT_BEHAVIORAL
    assert security_verification_capability(
        expectation, action.model_copy(update={"mode": NatMode.STATIC}),
    ) is Dimension.NAT_STATIC_BEHAVIORAL
    assert security_verification_capability(
        expectation, action.model_copy(update={"mode": NatMode.DYNAMIC}),
    ) is Dimension.NAT_DYNAMIC_BEHAVIORAL
