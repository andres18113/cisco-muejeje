"""The PSE frontier: how a second delivery path may reach E5, and how it may not.

POE-2 does not remove `manual_visible_power_state`. That contract stays valid
and existing manual evidence keeps authorizing exactly as before. What POE-2
targets is its OBLIGATORINESS: once governed PSE evidence exists, E5 must be
able to authorize PoE without a human having looked at a phone.

The shape that allows is convergence at claim policy, not a widened door:

    validated manual evidence  ---\\
                                    >-- exact PoE authorized claim -- resolver/E5
    validated PSE evidence     ---/

So `_AUTHORIZED_OBSERVATION_METHODS` remains the allowlist of the MANUAL
contract. It is not a generic registry of every PoE source, and a PSE reading
must never be smuggled through it dressed as a manual receipt. Equally, PSE is
not raw CLI: the resolver and the providers consume decided claims only.

These invariants are outcome-independent — they hold whether the AP experiment
reports POSITIVE or NEGATIVE — which is why they are pinned before it runs.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus, EvidenceSource, PoEAuthorizedBinding,
)
from src.packet_tracer_mcp.domain.enterprise.services.poe_claims import (
    _AUTHORIZED_OBSERVATION_METHODS, PoEDeliveryClaimScope, PoEDeliveryTestedBinding,
    decode_poe_delivery_scope, encode_poe_delivery_dimensions, poe_claim_has_delivery_basis,
)
from src.packet_tracer_mcp.infrastructure.execution.poe2_evidence import BINDING, BUILD

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "packet_tracer_mcp"
MANUAL = "manual_visible_power_state"

# Names a PSE integration might reach for. None may enter the MANUAL allowlist;
# a PSE path, if it is ever authorized, arrives through its own validated
# contract and converges at claim policy.
PSE_METHOD_CANDIDATES = (
    "show_power_inline", "show power inline", "pse_inline_delivery",
    "governed_poe_inline_observer", "poe_inline_status", "cli_power_inline_table",
)


def _scope(**overrides) -> PoEDeliveryClaimScope:
    tested = PoEDeliveryTestedBinding(
        switch_port=BINDING["switch_port"], comparison_port="FastEthernet0/14",
        endpoint_model=BINDING["endpoint_model"], endpoint_port=BINDING["endpoint_port"],
        candidate_state="powered", comparison_state="not_powered",
        candidate_indicator="visible power state", comparison_indicator="dark",
        candidate_ready=True, comparison_ready=True,
    )
    base = PoEDeliveryClaimScope(
        candidate_model=BINDING["switch_model"], packet_tracer_build=BUILD,
        access_ports=(BINDING["switch_port"],), tested_bindings=(tested,),
        active_bindings=(tested.authorized_binding,), simultaneous_active_ports=1,
        comparison_model="2960-24TT", observation_method=MANUAL,
        observer_id="boundary-fixture", observed_at="2026-09-07T18:00:00Z",
        cleanup_status="clean", inventory_restoration="restored",
    )
    return replace(base, **overrides)


@dataclass
class _Claim:
    capability: str
    status: CapabilityStatus
    source: EvidenceSource
    packet_tracer_version: str
    verified: bool
    observed_value: int | None
    dimensions: dict


def _claim(scope: PoEDeliveryClaimScope) -> _Claim:
    return _Claim(capability="supports_poe", status=CapabilityStatus.SUPPORTED,
                  source=EvidenceSource.MANUAL_VERIFICATION, packet_tracer_version=BUILD,
                  verified=True, observed_value=scope.simultaneous_active_ports,
                  dimensions=encode_poe_delivery_dimensions(scope))


def test_the_manual_contract_keeps_authorizing_exactly_as_before():
    """Backward compatibility is the premise, not a casualty, of POE-2."""
    claim = _claim(_scope())
    scope = decode_poe_delivery_scope(claim)
    assert scope is not None
    assert scope.observation_method == MANUAL
    assert scope.active_bindings == (PoEAuthorizedBinding(
        BINDING["switch_port"], BINDING["endpoint_model"], BINDING["endpoint_port"]),)
    assert poe_claim_has_delivery_basis(claim)


def test_the_manual_allowlist_is_the_manual_contract_only():
    """It names the manual method. It is not a registry of all PoE sources.

    A second delivery path does not arrive by appending to this set; it arrives
    with its own validated contract. Growing this set would make PSE evidence
    indistinguishable from a human receipt at every downstream reader.
    """
    assert _AUTHORIZED_OBSERVATION_METHODS == frozenset({MANUAL})


@pytest.mark.parametrize("method", PSE_METHOD_CANDIDATES)
def test_no_pse_name_is_smuggled_into_the_manual_allowlist(method):
    assert method not in _AUTHORIZED_OBSERVATION_METHODS


@pytest.mark.parametrize("method", PSE_METHOD_CANDIDATES)
def test_pse_evidence_is_never_validated_as_a_manual_receipt(method):
    """Well-formed in every other respect; only the method differs, and it fails.

    This is what stops a PSE integration from taking the cheap route of
    renaming its reading into the manual vocabulary.
    """
    with pytest.raises(ValueError):
        encode_poe_delivery_dimensions(_scope(observation_method=method))
    claim = _claim(_scope())
    claim.dimensions = dict(claim.dimensions)
    claim.dimensions["poe_delivery_observation_method"] = method
    assert decode_poe_delivery_scope(claim) is None
    assert not poe_claim_has_delivery_basis(claim)


def test_a_claim_may_not_extrapolate_beyond_the_port_it_measured():
    scope = _scope()
    neighbour = PoEAuthorizedBinding(
        "FastEthernet0/14", BINDING["endpoint_model"], BINDING["endpoint_port"])
    widened = replace(scope, active_bindings=scope.active_bindings + (neighbour,),
                      simultaneous_active_ports=2)
    with pytest.raises(ValueError):
        encode_poe_delivery_dimensions(widened)


def test_the_observer_is_a_measurement_not_a_claim():
    """Whatever authority a PSE path earns, the observer object never carries it.

    It has no capability, no status and no dimensions, so it cannot be read as
    a claim by any downstream reader — it can only feed a validated contract.
    """
    from src.packet_tracer_mcp.infrastructure.execution.poe_inline_observer import (
        GovernedPoEInlineObserver,
    )
    observer = GovernedPoEInlineObserver(lambda *a, **k: None)
    for attribute in ("capability", "status", "dimensions", "verified"):
        assert not hasattr(observer, attribute), attribute


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or "." * node.level
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("relative", [
    "domain/enterprise/services/capability_resolver.py",
    "infrastructure/catalog/capability_providers.py",
])
def test_the_resolver_and_providers_never_reach_for_raw_cli(relative):
    """They consume decided claims. An import of the PSE stack would be the leak.

    PSE evidence must reach them already validated and typed, exactly as manual
    evidence does. A CLI table has no business this far downstream.
    """
    path = PACKAGE / relative
    forbidden = ("poe_inline_observer", "ios_terminal", "poe2_evidence",
                 "GovernedPoEInlineObserver", "ControlledIosExecutor")
    leaked = [name for name in _imported_modules(path)
              for token in forbidden if token in name]
    assert not leaked, f"{relative} imports {leaked}"
    source = path.read_text(encoding="utf-8")
    assert "show power inline" not in source
    assert "raw_output" not in source


def test_the_observer_module_never_imports_claim_authority():
    """Measurement must not be able to reach the thing that grants authority."""
    imports = _imported_modules(
        PACKAGE / "infrastructure/execution/poe_inline_observer.py")
    for token in ("poe_claims", "capability_resolver", "capability_providers"):
        assert not any(token in name for name in imports), token


def test_no_calibration_artifact_is_named_inside_the_authority_path():
    """A calibration path inside authority code would be evidence smuggling.

    Calibrations characterise what the PSE prints. They never, alone, promote.
    """
    for relative in ("domain/enterprise/services/poe_claims.py",
                     "domain/enterprise/services/capability_resolver.py",
                     "infrastructure/catalog/capability_providers.py"):
        source = (PACKAGE / relative).read_text(encoding="utf-8")
        for token in ("canonical-live-evidence", "poe-inline-calibration", "off-calibration"):
            assert token not in source, f"{relative} names {token}"
