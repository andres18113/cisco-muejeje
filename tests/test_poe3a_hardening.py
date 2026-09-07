"""POE-3A hardening: measurement, contract and authority kept apart.

Three things were being conflated, and each is separated here.

*A valid measurement* says what the PSE reported and under what causality.
*A valid PSE contract* says that measurement is well formed and exact.
*Productive authority* additionally requires the LIVE session to have been
admitted — and that admission has exactly one source, the real
`LiveSessionSafetyEvidence` on the probe's context.

The first version of the PSE contract carried a `live_safety` string of its
own. A record could therefore assert its own admission, which is precisely
the claim no record is allowed to make about itself. Schema 2 removes it, and
schema 1 records fail closed rather than being reinterpreted.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import replace

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityEvidence, CapabilityStatus, EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.services.poe_pse_claims import (
    PSE_SCHEMA_VERSION, PoEPseCapture, PoEPseDeliveryScope,
    POE_PSE_EVIDENCE_KIND, decode_poe_pse_delivery_scope, encode_poe_pse_dimensions,
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
RUN = "poe3a-20260907T213914Z-20f42991"
LIVE_SHA = "e4b0d1479cd2fe10a6c97b446d3a7b87ee421415"
BUNDLE = (pathlib.Path(__file__).resolve().parents[1]
          / "docs" / "reference" / "cp-scale" / "canonical-live-evidence" / RUN)


def scope(**overrides) -> PoEPseDeliveryScope:
    base = PoEPseDeliveryScope(
        schema_version=PSE_SCHEMA_VERSION, switch_model=SWITCH, switch_port=PORT,
        endpoint_model="7960", endpoint_port="Switch", packet_tracer_build=BUILD,
        observer_id="GovernedPoEInlineObserver", experiment_id="hardening-fixture",
        observed_at="2026-09-07T21:39:14Z", captures=CAUSAL, gates=GATES,
        simultaneous_active_ports=1, cleanup_status="clean",
        inventory_restoration="restored",
    )
    return replace(base, **overrides)


# ==========================================================================
# 1 -- the PSE contract may not speak about its own LIVE admission
# ==========================================================================

def test_the_pse_contract_has_no_live_safety_field_of_its_own():
    """Admission is not something a measurement can assert about itself."""
    assert not hasattr(scope(), "live_safety")
    assert "poe_pse_live_safety" not in encode_poe_pse_dimensions(scope())


def test_the_schema_version_moved_so_self_admitting_records_are_not_reread():
    assert PSE_SCHEMA_VERSION == 2


def _claim(dimensions: dict) -> CapabilityEvidence:
    return CapabilityEvidence(
        capability="supports_poe", status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.CONTROLLED_PROBE, source_detail="hardening",
        packet_tracer_version=BUILD, verified=True, observed_value=1,
        dimensions=dimensions,
    )


def test_a_schema_one_record_that_admitted_itself_fails_closed():
    """The exact shape the first LIVE produced must no longer decode.

    It carried `poe_pse_live_safety = admitted` -- a string asserting the very
    thing only the session's own safety evidence may establish.
    """
    legacy = encode_poe_pse_dimensions(scope())
    legacy["poe_pse_schema_version"] = "1"
    legacy["poe_pse_live_safety"] = "admitted"
    assert decode_poe_pse_delivery_scope(_claim(legacy)) is None


def test_an_unknown_future_schema_also_fails_closed():
    forward = encode_poe_pse_dimensions(scope())
    forward["poe_pse_schema_version"] = "3"
    assert decode_poe_pse_delivery_scope(_claim(forward)) is None


def test_a_current_record_still_decodes_so_the_guard_is_not_vacuous():
    assert decode_poe_pse_delivery_scope(_claim(encode_poe_pse_dimensions(scope()))) is not None


# ==========================================================================
# 5 -- one authoritative source for LIVE admission
# ==========================================================================

def _probe(dimensions: dict, *, safety):
    from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
        CapabilityProbeResult, CapabilityVerificationMethod, ProbeContext,
        ProbeExecutionStatus,
    )
    return CapabilityProbeResult(
        probe_id="poe3a-pse-inline", model=SWITCH, capability="supports_poe",
        status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.CONTROLLED_PROBE, configured=True,
        verified=True, observed_value=1, packet_tracer_version=BUILD,
        verification_method=CapabilityVerificationMethod.CLI_PLUS_READBACK,
        dimensions=dimensions,
        context=ProbeContext(
            probe_id="poe3a-pse-inline", device_model=SWITCH, backend_version=BUILD,
            inventory_restored=True, live_session_safety=safety,
        ),
    )


def _compose(results, tmp_path):
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
            session=ProbeSession(session_id="hardening", packet_tracer_version=BUILD),
            results=list(results),
        ),
    ))
    adapter = packet_tracer_enterprise_capability_adapter(BUILD, store=store)
    return adapter.capabilities_for(SWITCH, packet_tracer_version=BUILD)


def test_a_valid_measurement_without_admitted_safety_is_not_authority(tmp_path):
    """Valid measurement, valid contract, no admission: E5 stays UNKNOWN."""
    composed = _compose(
        [_probe(encode_poe_pse_dimensions(scope()), safety=None)], tmp_path)
    assert composed.supports_poe is CapabilityStatus.UNKNOWN
    assert composed.poe_authorized_bindings == []


def test_the_same_measurement_with_admitted_safety_is_authority(tmp_path):
    from tests.poe_session_safety import healthy_live_session_safety

    composed = _compose(
        [_probe(encode_poe_pse_dimensions(scope()),
                safety=healthy_live_session_safety())], tmp_path)
    assert composed.supports_poe is CapabilityStatus.SUPPORTED
    assert [(b.switch_port, b.endpoint_model, b.endpoint_port)
            for b in composed.poe_authorized_bindings] == [(PORT, "7960", "Switch")]
    assert composed.poe_ports == 1


def test_unadmitted_safety_evidence_is_not_enough_either(tmp_path):
    """Present but failing admission is refused just like absent."""
    from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
        LiveSessionSafetyEvidence,
    )
    incomplete = LiveSessionSafetyEvidence(
        runtime_healthy=True, crash_detected=False, integrity_verified=True,
        session_reusable=True, positive_claim_allowed=True,
        unexpected_canonical_modification=False, disposable_modified=False,
    )
    composed = _compose(
        [_probe(encode_poe_pse_dimensions(scope()), safety=incomplete)], tmp_path)
    assert composed.supports_poe is CapabilityStatus.UNKNOWN


def test_no_productive_provider_injects_pse_evidence_without_a_probe_context():
    """The one direct-`CapabilityEvidence` provider carries no PSE at all.

    `CapabilityEvidence` has no context field, so safety cannot travel with
    it. Every snapshot-derived record is validated as a `CapabilityProbeResult`
    first, where the context exists; the only provider that supplies evidence
    directly is the static measured catalog, and this is what keeps it from
    ever being a PSE bypass.
    """
    from src.packet_tracer_mcp.infrastructure.catalog.measured_capabilities import (
        measured_capability_evidence,
    )
    assert "context" not in CapabilityEvidence.model_fields
    for model, records in measured_capability_evidence().items():
        for record in records:
            assert POE_PSE_EVIDENCE_KIND not in (record.dimensions or {}), model
            if record.capability == "supports_poe":
                assert record.status is CapabilityStatus.UNKNOWN, model


# ==========================================================================
# 2 -- the port defect, proven behaviourally
# ==========================================================================

class _Sentinel(Exception):
    """Raised by the observer spy once it has recorded its arguments."""


def test_the_experiment_configures_and_observes_only_its_own_port(monkeypatch):
    """The real defect: fixture on Fa0/1, mutation and observation on Fa0/13.

    Driven through `Experiment` itself with spies, so it fails against the
    implementation that read the port from the module-level AP binding.
    """
    import sys
    root = pathlib.Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "tools"))
    import poe2_ap_live
    from poe_inline_calibration_live import PoEInlineMode

    monkeypatch.setattr(poe2_ap_live.time, "sleep", lambda _seconds: None)
    experiment = poe2_ap_live.Experiment("spy-run", switch_port=PORT, endpoint_role="PH")
    assert experiment.switch_port == PORT

    configured: list[tuple[str, str]] = []
    observed: list[tuple] = []

    class _Config:
        def configure_ios(self, device, payload):
            configured.append((device, payload))
            return True

    class _Observer:
        def observe_poe_inline_status(self, device, ports):
            observed.append((device, tuple(ports)))
            raise _Sentinel

    class _Bridge:
        _pending: dict = {}

        def collect_completed(self):
            return None

    experiment.config = _Config()
    experiment.observer = _Observer()
    experiment.bridge = _Bridge()

    experiment.apply(PoEInlineMode.NEVER)
    assert len(configured) == 1
    device, payload = configured[0]
    assert device == experiment.switch
    assert f"interface {PORT}" in payload
    assert "interface FastEthernet0/13" not in payload
    assert " power inline never" in payload

    with pytest.raises(_Sentinel):
        experiment.capture("AUTO_1")
    assert observed == [(experiment.switch, (PORT,))]


def test_the_experiment_still_defaults_to_the_poe2_binding(monkeypatch):
    """POE-2's two runners pass no port and must be unaffected."""
    import sys
    root = pathlib.Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "tools"))
    import poe2_ap_live

    assert poe2_ap_live.Experiment("default-run").switch_port == (
        poe2_ap_live.BINDING["switch_port"]
    )


# ==========================================================================
# 3 -- the binding is resolved by identity, not by position
# ==========================================================================

def test_the_runner_resolves_its_binding_by_stable_scenario_identity(monkeypatch):
    import sys
    root = pathlib.Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "tools"))
    import poe3a_pse_live

    assert poe3a_pse_live.TARGET_ENDPOINT_ID == (
        "endpoint/large-branch/campus/floor-1/zone-a/ip_phone/001"
    )
    binding = poe3a_pse_live.governed_binding()
    assert binding == {
        "endpoint_id": poe3a_pse_live.TARGET_ENDPOINT_ID,
        "device_id": "sw-acc-large-branch-zone-a-02",
        "switch_model": SWITCH, "switch_port": PORT,
        "endpoint_model": "7960", "endpoint_port": "Switch",
    }


def test_the_binding_resolution_fails_closed_when_it_disappears(monkeypatch):
    import sys
    root = pathlib.Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "tools"))
    import poe3a_pse_live

    monkeypatch.setattr(poe3a_pse_live, "TARGET_ENDPOINT_ID", "endpoint/does/not/exist")
    with pytest.raises(RuntimeError, match="no longer carries"):
        poe3a_pse_live.governed_binding()


def test_the_binding_resolution_fails_closed_on_ambiguity(monkeypatch):
    import sys
    root = pathlib.Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "tools"))
    import poe3a_pse_live

    design = poe3a_pse_live.cp_scale_physical_design()
    target = next(b for site in design.sites for b in site.endpoint_bindings
                  if b.endpoint_id == poe3a_pse_live.TARGET_ENDPOINT_ID)
    design.sites[0].endpoint_bindings.append(target.model_copy())
    monkeypatch.setattr(poe3a_pse_live, "cp_scale_physical_design", lambda: design)
    with pytest.raises(RuntimeError, match="ambiguous"):
        poe3a_pse_live.governed_binding()


# ==========================================================================
# 4 -- the committed LIVE bundle, verified as bytes and as behaviour
# ==========================================================================

def _bundle() -> dict:
    return json.loads((BUNDLE / "evidence.json").read_text(encoding="utf-8"))


def test_the_committed_run_is_the_one_it_says_it_is():
    body = _bundle()
    assert body["experiment_id"] == RUN
    assert body["frozen_live_sha"] == LIVE_SHA
    assert body["packet_tracer_build"] == BUILD
    assert body["exact_binding"]["switch_model"] == SWITCH
    assert body["exact_binding"]["switch_port"] == PORT
    assert body["exact_binding"]["endpoint_model"] == "7960"
    assert body["exact_binding"]["endpoint_port"] == "Switch"
    assert body["problems"] == []


def test_the_committed_run_measured_the_causal_sequence():
    captures = _bundle()["captures"]
    assert [c["label"] for c in captures] == ["AUTO_1", "NEVER", "AUTO_2"]
    deliveries = [c["observation"]["ports"][0]["delivery"] for c in captures]
    assert deliveries == ["delivering", "not_delivering", "delivering"]
    for capture in captures:
        assert set(capture["table_completeness"]) == set(GATES), capture["label"]
        assert all(capture["table_completeness"].values()), capture["label"]
        assert capture["stable"] is True


def test_the_committed_raw_bytes_hash_to_their_declared_digests():
    body = _bundle()
    entries = list(body["captures"]) + [body["restoration"]["fresh_readback"]]
    for entry in entries:
        raw = (BUNDLE / entry["raw_file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["raw_sha256"], entry["raw_file"]


def test_the_committed_run_restored_and_stayed_safe():
    body = _bundle()
    restoration, safety = body["restoration"], body["safety"]
    for key in ("power_inline_auto_proven", "endpoint_deleted", "switch_deleted",
                "inventory_restored", "fixture_removed", "realtime_restored"):
        assert restoration[key] is True, key
    assert restoration["inventory_fingerprint_after"] == body["baseline"]["inventory_fingerprint"]
    for key in ("clean", "mailbox_clean", "runtime_heartbeat_fresh",
                "same_pt_processes", "frozen_source_unchanged"):
        assert safety[key] is True, key
    assert safety["transport_problems"] == []


def test_the_committed_run_claims_no_authority():
    body = _bundle()
    assert body["productive"] is False
    assert body["integration_result"] == "NOT_ATTEMPTED"
    assert body["authority_delta"] == "none; measurement only"


def test_the_committed_bundle_alone_cannot_become_authority(tmp_path):
    """Behaviour, not spelling: its own dimensions no longer decode.

    The run was produced under schema 1, which let a record assert its own
    LIVE admission. Replaying those exact persisted dimensions through the
    productive composition must yield nothing.
    """
    dimensions = _bundle()["pse_dimensions"]
    assert dimensions["poe_pse_schema_version"] == "1"
    assert dimensions["poe_pse_live_safety"] == "admitted"
    assert decode_poe_pse_delivery_scope(_claim(dict(dimensions))) is None

    from tests.poe_session_safety import healthy_live_session_safety
    composed = _compose(
        [_probe(dict(dimensions), safety=healthy_live_session_safety())], tmp_path)
    assert composed.supports_poe is CapabilityStatus.UNKNOWN
    assert composed.poe_authorized_bindings == []


def test_the_bundle_is_classified_beside_its_own_bytes():
    """The original evidence is not rewritten; it is qualified in place."""
    classification = BUNDLE / "CLASSIFICATION.md"
    text = classification.read_text(encoding="utf-8")
    assert "MEASUREMENT = VALID" in text
    assert "PRODUCTIVE AUTHORITY = NO" in text
    assert LIVE_SHA in text
    assert "poe_pse_live_safety" in text
