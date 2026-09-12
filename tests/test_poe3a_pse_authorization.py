"""POE-3A: valid positive PSE evidence authorizes an exact binding on its own.

`manual_visible_power_state` stays fully supported and keeps authorizing
exactly as it did. What changes is that it stops being *mandatory*: a binding
with valid positive PSE evidence no longer needs a human to have watched a
phone light up.

The two bases stay independent all the way down -- manual evidence through the
manual contract, PSE evidence through the PSE contract -- and converge only at
the canonical authorized claim the resolver consumes. E5 sees `supports_poe`,
`poe_authorized_bindings` and `poe_ports`, and nothing about which mechanism
proved them.

Everything here runs through the productive resolver, not through a decoder in
isolation, because the question is what E5 is authorized to believe.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityEvidence, CapabilityStatus, EvidenceSource, PoEAuthorizedBinding,
)
from src.packet_tracer_mcp.domain.enterprise.services.capability_resolver import (
    CapabilityResolver, CatalogDeviceFacts,
)
from src.packet_tracer_mcp.domain.enterprise.services.poe_claims import (
    _AUTHORIZED_OBSERVATION_METHODS, PoEDeliveryClaimScope, PoEDeliveryTestedBinding,
    encode_poe_delivery_dimensions,
)
from src.packet_tracer_mcp.domain.enterprise.services.poe_pse_claims import (
    PoEPseCapture, PoEPseDeliveryScope, POE_PSE_CAPTURES, POE_PSE_GATES,
    POE_PSE_PACKET_TRACER_BUILD, POE_PSE_SWITCH_MODEL, POE_PSE_SWITCH_PORT,
    encode_poe_pse_dimensions,
)

BUILD = "9.0.1.0858"
SWITCH = "3560-24PS"
PORT = "FastEthernet0/1"
GATES = (
    "all_pagers_traversed", "attributable", "dispatch_integrity_valid",
    "expected_privileged_prompt_reached", "fresh", "no_pending_continuation",
    "observer_complete", "stable",
)
CAUSAL = (
    PoEPseCapture("AUTO_1", "auto", "on", 10.0, True, True),
    PoEPseCapture("NEVER", "never", "absent", 0.0, False, False),
    PoEPseCapture("AUTO_2", "auto", "on", 10.0, True, True),
)


# ---------------------------------------------------------------- PSE basis

def pse_scope(**overrides) -> PoEPseDeliveryScope:
    base = PoEPseDeliveryScope(
        schema_version=2, switch_model=SWITCH, switch_port=PORT,
        endpoint_model="7960", endpoint_port="Switch", packet_tracer_build=BUILD,
        observer_id="governed-poe-inline-observer", experiment_id="poe3a-fixture",
        observed_at="2026-09-07T18:00:00Z", captures=CAUSAL, gates=GATES,
        simultaneous_active_ports=1, cleanup_status="clean",
        inventory_restoration="restored",
    )
    return replace(base, **overrides)


def pse_evidence(scope: PoEPseDeliveryScope | None = None, **overrides) -> CapabilityEvidence:
    scope = scope or pse_scope()
    fields = dict(
        capability="supports_poe", status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.CONTROLLED_PROBE, source_detail="poe3a-pse-probe",
        packet_tracer_version=BUILD, verified=True,
        observed_value=scope.simultaneous_active_ports,
        dimensions=encode_poe_pse_dimensions(scope),
    )
    fields.update(overrides)
    return CapabilityEvidence(**fields)


# ------------------------------------------------------------- manual basis

def manual_evidence(port: str = PORT, endpoint_model: str = "7960") -> CapabilityEvidence:
    tested = PoEDeliveryTestedBinding(
        switch_port=port, comparison_port="FastEthernet0/24",
        endpoint_model=endpoint_model, endpoint_port="Switch",
        candidate_state="powered", comparison_state="not_powered",
        candidate_indicator="screen lit", comparison_indicator="dark",
        candidate_ready=True, comparison_ready=True,
    )
    scope = PoEDeliveryClaimScope(
        candidate_model=SWITCH, packet_tracer_build=BUILD, access_ports=(port,),
        tested_bindings=(tested,), active_bindings=(tested.authorized_binding,),
        simultaneous_active_ports=1, comparison_model="2960-24TT",
        observation_method="manual_visible_power_state", observer_id="andres18113",
        observed_at="2026-09-07T02:44:24Z", cleanup_status="clean",
        inventory_restoration="restored",
    )
    return CapabilityEvidence(
        capability="supports_poe", status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.MANUAL_VERIFICATION, source_detail="manual receipt",
        packet_tracer_version=BUILD, verified=True, observed_value=1,
        dimensions=encode_poe_delivery_dimensions(scope),
    )


def compose(*evidence: CapabilityEvidence, model: str = SWITCH):
    """Resolve through the productive path, as E5 does."""
    resolver = CapabilityResolver()
    base = resolver.resolve(CatalogDeviceFacts(
        model=model, category="switch", packet_tracer_version=BUILD,
    ))
    return resolver.with_evidence(base, list(evidence), packet_tracer_version=BUILD)


def binding(port: str = PORT, endpoint_model: str = "7960") -> PoEAuthorizedBinding:
    return PoEAuthorizedBinding(port, endpoint_model, "Switch")


# ==========================================================================
# 1 / 2 -- the two bases, each on its own
# ==========================================================================

def test_manual_evidence_still_authorizes_exactly_as_before():
    composed = compose(manual_evidence())
    assert composed.supports_poe is CapabilityStatus.SUPPORTED
    assert composed.poe_authorized_bindings == [binding()]
    assert composed.poe_ports == 1


def test_valid_positive_pse_authorizes_without_any_manual_evidence():
    """The whole point of POE-3A, asserted at the resolver."""
    composed = compose(pse_evidence())
    assert composed.supports_poe is CapabilityStatus.SUPPORTED
    assert composed.poe_authorized_bindings == [binding()]
    assert composed.poe_ports == 1


def test_the_manual_allowlist_did_not_grow_to_make_that_work():
    assert _AUTHORIZED_OBSERVATION_METHODS == frozenset({"manual_visible_power_state"})


# ==========================================================================
# 3 -- producers are not authority
# ==========================================================================

def test_the_observer_and_its_raw_captures_are_not_a_claim():
    from src.packet_tracer_mcp.infrastructure.execution.poe_inline_observer import (
        GovernedPoEInlineObserver,
    )
    observer = GovernedPoEInlineObserver(lambda *a, **k: None)
    for attribute in ("capability", "status", "dimensions", "verified"):
        assert not hasattr(observer, attribute), attribute


def test_no_raw_cli_reaches_the_claim_or_resolver_layer():
    import ast
    import pathlib

    package = pathlib.Path(__file__).resolve().parents[1] / "src" / "packet_tracer_mcp"
    forbidden = ("poe_inline_observer", "ios_terminal", "poe2_evidence",
                 "GovernedPoEInlineObserver", "ControlledIosExecutor")
    for relative in ("domain/enterprise/services/poe_claims.py",
                     "domain/enterprise/services/poe_pse_claims.py",
                     "domain/enterprise/services/capability_resolver.py",
                     "infrastructure/catalog/capability_providers.py"):
        path = package / relative
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names.add(module)
                names.update(f"{module}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
        assert not [n for n in names for token in forbidden if token in n], relative
        source = path.read_text(encoding="utf-8")
        assert "raw_output" not in source, relative


def test_a_calibration_alone_authorizes_nothing():
    """A single reading is a calibration, not a proof of delivery.

    The producer refuses to encode it at all, and a record hand-assembled to
    carry it anyway still authorizes nothing.
    """
    import json

    with pytest.raises(ValueError):
        encode_poe_pse_dimensions(pse_scope(captures=(CAUSAL[0],)))

    evidence = pse_evidence()
    dimensions = dict(evidence.dimensions)
    captures = json.loads(dimensions[POE_PSE_CAPTURES])
    dimensions[POE_PSE_CAPTURES] = json.dumps(
        captures[:1], sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    composed = compose(evidence.model_copy(update={"dimensions": dimensions}))
    assert composed.supports_poe is CapabilityStatus.UNKNOWN
    assert composed.poe_authorized_bindings == []


# ==========================================================================
# 4 -- invalid PSE fails closed, every way it can be invalid
# ==========================================================================

@pytest.mark.parametrize("mutate, label", [
    (lambda d: d.__setitem__(POE_PSE_PACKET_TRACER_BUILD, "9.0.2.0000"), "wrong build"),
    (lambda d: d.__setitem__(POE_PSE_SWITCH_MODEL, "2960-24TT"), "wrong switch model"),
    (lambda d: d.__setitem__(POE_PSE_GATES, '["fresh"]'), "incomplete gates"),
    (lambda d: d.__setitem__(POE_PSE_CAPTURES, "not json"), "corrupt captures"),
    (lambda d: d.pop(POE_PSE_CAPTURES), "captures missing"),
    (lambda d: d.__setitem__("poe_pse_schema_version", "1"), "superseded schema version"),
    (lambda d: d.__setitem__("poe_pse_schema_version", "9"), "unknown schema version"),
    (lambda d: d.__setitem__("poe_pse_cleanup_status", "dirty"), "unclean teardown"),
    (lambda d: d.__setitem__("poe_pse_inventory_restoration", "unrestored"), "inventory left dirty"),
    (lambda d: d.__setitem__("poe_pse_observed_at", "yesterday"), "unusable timestamp"),
    (lambda d: d.__setitem__("poe_pse_observer_id", ""), "unattributable"),
])
def test_invalid_pse_evidence_authorizes_nothing(mutate, label):
    evidence = pse_evidence()
    dimensions = dict(evidence.dimensions)
    mutate(dimensions)
    composed = compose(evidence.model_copy(update={"dimensions": dimensions}))
    assert composed.supports_poe is CapabilityStatus.UNKNOWN, label
    assert composed.poe_authorized_bindings == [], label


@pytest.mark.parametrize("captures, label", [
    ((CAUSAL[0], CAUSAL[2]), "no NEVER arm: delivery never removed"),
    ((CAUSAL[0], CAUSAL[1]), "no restoration: delivery never returned"),
    ((CAUSAL[0], replace(CAUSAL[1], delivering=True, oper_state="on", power_watts=10.0,
                         row_present=True), CAUSAL[2]), "delivery survived `never`"),
    ((replace(CAUSAL[0], power_watts=0.0), CAUSAL[1], CAUSAL[2]), "AUTO_1 drew nothing"),
    ((CAUSAL[2], CAUSAL[1], CAUSAL[0]), "sequence out of order"),
])
def test_a_broken_causal_sequence_authorizes_nothing(captures, label):
    with pytest.raises(ValueError):
        encode_poe_pse_dimensions(pse_scope(captures=captures))


def test_pse_evidence_authorizes_the_port_it_measured_and_no_other():
    """There is no external port to contradict, so the guard is non-leakage.

    A PSE record naming another port is a coherent claim about that port. What
    it must never be is authority for the port it did not watch.
    """
    moved = pse_evidence(pse_scope(switch_port="FastEthernet0/2"))
    composed = compose(moved)
    assert composed.poe_authorized_bindings == [binding("FastEthernet0/2")]
    assert binding(PORT) not in composed.poe_authorized_bindings
    assert composed.poe_ports == 1


def test_pse_evidence_from_an_unverified_probe_authorizes_nothing():
    composed = compose(pse_evidence(verified=False))
    assert composed.supports_poe is CapabilityStatus.UNKNOWN


def test_pse_evidence_from_the_wrong_source_authorizes_nothing():
    """A PSE payload carried by a manual receipt is not a manual receipt."""
    composed = compose(pse_evidence(source=EvidenceSource.MANUAL_VERIFICATION))
    assert composed.supports_poe is CapabilityStatus.UNKNOWN
    assert composed.poe_authorized_bindings == []


def test_pse_evidence_is_not_reused_across_builds():
    resolver = CapabilityResolver()
    base = resolver.resolve(CatalogDeviceFacts(
        model=SWITCH, category="switch", packet_tracer_version="9.0.2.0000",
    ))
    composed = resolver.with_evidence(
        base, [pse_evidence()], packet_tracer_version="9.0.2.0000",
    )
    assert composed.supports_poe is CapabilityStatus.UNKNOWN


def test_pse_evidence_does_not_authorize_another_switch_model():
    composed = compose(pse_evidence(), model="3650-24PS")
    assert composed.supports_poe is CapabilityStatus.UNKNOWN
    assert composed.poe_authorized_bindings == []


# ==========================================================================
# 5 -- negative and unknown PSE grant nothing, and never say UNSUPPORTED
# ==========================================================================

@pytest.mark.parametrize("status", [
    CapabilityStatus.UNSUPPORTED, CapabilityStatus.UNKNOWN,
])
def test_non_positive_pse_never_authorizes_and_never_denies(status):
    """POE-3A productivises positive PSE only.

    A PSE reading of "not delivering" is a fact about one binding on one
    build. It is not a statement that the switch has no PoE, and this route
    must never turn it into one.
    """
    composed = compose(pse_evidence(status=status, observed_value=None))
    assert composed.supports_poe is not CapabilityStatus.UNSUPPORTED
    assert composed.supports_poe is CapabilityStatus.UNKNOWN
    assert composed.poe_authorized_bindings == []


# ==========================================================================
# 6 -- invalid PSE must not destroy an independent manual authority
# ==========================================================================

def test_invalid_pse_never_erases_a_valid_independent_manual_claim():
    """A broken reading from the switch does not make the human wrong.

    `CONTROLLED_PROBE` outranks `MANUAL_VERIFICATION`, so an unusable PSE
    record would otherwise cap the whole model at UNKNOWN and destroy a
    manual observation that is still perfectly true.
    """
    broken = pse_evidence()
    dimensions = dict(broken.dimensions)
    dimensions[POE_PSE_CAPTURES] = "not json"
    broken = broken.model_copy(update={"dimensions": dimensions})

    composed = compose(manual_evidence(), broken)
    assert composed.supports_poe is CapabilityStatus.SUPPORTED
    assert composed.poe_authorized_bindings == [binding()]
    assert composed.poe_ports == 1


def test_a_malformed_non_pse_claim_still_caps_as_it_always_did():
    """The pre-existing ceiling is untouched for claims of unknown kind."""
    opaque = CapabilityEvidence(
        capability="supports_poe", status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.CONTROLLED_PROBE, source_detail="unknown shape",
        packet_tracer_version=BUILD, verified=True, observed_value=1,
        dimensions={"something": "else"},
    )
    composed = compose(manual_evidence(), opaque)
    assert composed.supports_poe is CapabilityStatus.UNKNOWN


# ==========================================================================
# 7 / 8 / 9 -- union of exact bindings, capacity never summed
# ==========================================================================

def test_manual_and_pse_for_one_binding_authorize_it_once():
    composed = compose(manual_evidence(), pse_evidence())
    assert composed.supports_poe is CapabilityStatus.SUPPORTED
    assert composed.poe_authorized_bindings == [binding()]
    assert composed.poe_ports == 1


def test_manual_and_pse_for_different_bindings_union_exactly_those():
    other = "FastEthernet0/9"
    composed = compose(
        manual_evidence(port=other),
        pse_evidence(pse_scope(switch_port=PORT)),
    )
    assert composed.supports_poe is CapabilityStatus.SUPPORTED
    assert composed.poe_authorized_bindings == sorted([binding(PORT), binding(other)])
    # Two runs, one port each. Neither ever showed two ports lit at once.
    assert composed.poe_ports == 1


def test_capacity_is_the_largest_single_run_never_the_sum():
    tested = tuple(
        PoEDeliveryTestedBinding(
            switch_port=f"FastEthernet0/{index}", comparison_port=f"FastEthernet0/{index + 10}",
            endpoint_model="7960", endpoint_port="Switch", candidate_state="powered",
            comparison_state="not_powered", candidate_indicator="lit",
            comparison_indicator="dark", candidate_ready=True, comparison_ready=True,
        )
        for index in (2, 3, 4)
    )
    wide = CapabilityEvidence(
        capability="supports_poe", status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.MANUAL_VERIFICATION, source_detail="three at once",
        packet_tracer_version=BUILD, verified=True, observed_value=3,
        dimensions=encode_poe_delivery_dimensions(PoEDeliveryClaimScope(
            candidate_model=SWITCH, packet_tracer_build=BUILD,
            access_ports=tuple(item.switch_port for item in tested),
            tested_bindings=tested,
            active_bindings=tuple(item.authorized_binding for item in tested),
            simultaneous_active_ports=3, comparison_model="2960-24TT",
            observation_method="manual_visible_power_state", observer_id="andres18113",
            observed_at="2026-09-07T03:00:00Z", cleanup_status="clean",
            inventory_restoration="restored",
        )),
    )
    composed = compose(wide, pse_evidence())
    assert composed.poe_ports == 3, "max of the runs, not 3 + 1"
    assert len(composed.poe_authorized_bindings) == 4


# ==========================================================================
# 10 / 12 -- legacy and history stay where they are
# ==========================================================================

def test_a_legacy_poe_claim_without_a_scope_still_fails_closed():
    legacy = CapabilityEvidence(
        capability="supports_poe", status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.CATALOG, source_detail="legacy datasheet",
        packet_tracer_version=BUILD, verified=True, observed_value=24,
        dimensions={},
    )
    composed = compose(legacy)
    assert composed.supports_poe is CapabilityStatus.UNKNOWN
    assert composed.poe_authorized_bindings == []


def test_historical_poe2_evidence_does_not_become_authority():
    """The POE-2 bundle is an experiment record, not a capability claim.

    It has no dimensions the claim layer reads, so it cannot authorize, and
    nothing in POE-3A retroactively promotes it.
    """
    from src.packet_tracer_mcp.infrastructure.execution import poe2_evidence

    assert not hasattr(poe2_evidence, "encode_poe_pse_dimensions")
    historical = CapabilityEvidence(
        capability="supports_poe", status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.CONTROLLED_PROBE, source_detail="poe2-20260907T173336Z",
        packet_tracer_version=BUILD, verified=True, observed_value=1,
        dimensions={"poe2_experiment_id": "poe2-20260907T173336Z-b4d3459e"},
    )
    composed = compose(historical)
    assert composed.supports_poe is CapabilityStatus.UNKNOWN


# ==========================================================================
# The productive chain: snapshot -> store -> provider -> adapter
# ==========================================================================

def _pse_probe_result(scope: PoEPseDeliveryScope | None = None, **overrides):
    """A PSE reading as it is actually persisted and read back."""
    from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
        CapabilityProbeResult, CapabilityVerificationMethod, ProbeContext,
        ProbeExecutionStatus,
    )
    from tests.poe_session_safety import healthy_live_session_safety

    scope = scope or pse_scope()
    fields = dict(
        probe_id="poe3a-pse-inline", model=SWITCH, capability="supports_poe",
        status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.CONTROLLED_PROBE,
        configured=True, verified=True,
        observed_value=scope.simultaneous_active_ports,
        packet_tracer_version=BUILD,
        verification_method=CapabilityVerificationMethod.CLI_PLUS_READBACK,
        dimensions=encode_poe_pse_dimensions(scope),
        context=ProbeContext(
            probe_id="poe3a-pse-inline", device_model=SWITCH,
            backend_version=BUILD, inventory_restored=True,
            live_session_safety=healthy_live_session_safety(),
        ),
    )
    fields.update(overrides)
    return CapabilityProbeResult(**fields)


def _adapter_for(tmp_path, results):
    from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
        CapabilitySnapshot, ProbeSession, ProbeSessionResult,
    )
    from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
        packet_tracer_enterprise_capability_adapter,
    )
    from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
        CapabilitySnapshotStore,
    )
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    store.save_runtime(CapabilitySnapshot(
        packet_tracer_version=BUILD,
        session=ProbeSessionResult(
            session=ProbeSession(session_id="poe3a-e2e", packet_tracer_version=BUILD),
            results=list(results),
        ),
    ))
    return packet_tracer_enterprise_capability_adapter(BUILD, store=store)


def test_persisted_pse_evidence_authorizes_through_the_productive_composition(tmp_path):
    """The end the LIVE has to reach: a stored PSE reading, no manual receipt.

    This is the productive composition root, not a resolver call: the snapshot
    is written to a real store, read back by the real provider, and composed
    by the adapter E5 uses.
    """
    adapter = _adapter_for(tmp_path, [_pse_probe_result()])
    capabilities = adapter.capabilities_for(SWITCH, packet_tracer_version=BUILD)

    assert capabilities.supports_poe is CapabilityStatus.SUPPORTED
    assert capabilities.poe_authorized_bindings == [binding()]
    assert capabilities.poe_ports == 1


def test_persisted_pse_evidence_without_live_safety_authorizes_nothing(tmp_path):
    """A positive PoE claim still needs its LIVE session admitted."""
    adapter = _adapter_for(tmp_path, [_pse_probe_result(context=None)])
    capabilities = adapter.capabilities_for(SWITCH, packet_tracer_version=BUILD)

    assert capabilities.supports_poe is CapabilityStatus.UNKNOWN
    assert capabilities.poe_authorized_bindings == []


def test_persisted_pse_evidence_does_not_leak_to_another_model(tmp_path):
    adapter = _adapter_for(tmp_path, [_pse_probe_result()])
    other = adapter.capabilities_for("2960-24TT", packet_tracer_version=BUILD)
    assert other.poe_authorized_bindings == []


# ==========================================================================
# The runner measures the port it was given
# ==========================================================================

@pytest.mark.parametrize("option", ["--command", "--ios", "--javascript", "--binding", "--switch-port"])
def test_the_capacity_runner_has_no_caller_command_or_binding_escape_hatch(monkeypatch, option):
    import importlib
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    runner = importlib.import_module("poe3a_pse_live")
    with pytest.raises(SystemExit):
        runner.parse_args(["--execute", "--model", "3560-24PS", "--qualification-id", "offline",
                           option, "arbitrary"])



def _raw_capture(label: str, raw_output: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        raw_file=label.lower() + ".txt",
        observation={"raw_output": raw_output},
    )


def test_a_second_capture_never_overwrites_earlier_raw_evidence(monkeypatch):
    """Raw output is the only unnormalised record of what the switch printed.

    The raw file is named after the capture label, so re-capturing under a
    label already used would silently replace the earlier bytes and destroy
    the pre-mutation reading the run is audited against.
    """

    import importlib
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    runner = importlib.import_module("poe3a_pse_live")

    raw_files: dict[str, bytes] = {}
    runner._record_raw(raw_files, _raw_capture("PSU_BEFORE", "Available: 0.0"))
    assert raw_files["psu_before.txt"] == b"Available: 0.0"

    # Re-recording the identical bytes is a no-op, never a silent loss.
    runner._record_raw(raw_files, _raw_capture("PSU_BEFORE", "Available: 0.0"))
    assert raw_files["psu_before.txt"] == b"Available: 0.0"

    with pytest.raises(RuntimeError, match="overwrite different earlier evidence"):
        runner._record_raw(raw_files, _raw_capture("PSU_BEFORE", "Available: 390.0"))
    assert raw_files["psu_before.txt"] == b"Available: 0.0"


def test_the_post_false_power_recapture_uses_its_own_label(monkeypatch):
    """The fallback re-read must not be filed under the pre-mutation label."""

    import importlib
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    runner = importlib.import_module("poe3a_pse_live")
    source = Path(runner.__file__).read_text(encoding="utf-8")

    marker = 'fallback_power_capture = session.capture_inline_status('
    assert marker in source
    tail = source.split(marker, 1)[1].split(")", 1)[0]
    assert '"PSU_BEFORE"' not in tail
    assert "PSU_AFTER_NATIVE_FALSE" in tail
