"""CP-SCALE stages the voice plan, and judges only what it observed.

Floor 1 applied 136 typed configuration actions, powered every phone, put every
access port on data VLAN 10 with voice VLAN 20, and then reported 21 x 7960
contradicting the plan. The live runner contained no reference to voice at all:
it planned phone addressing as an ordinary endpoint action, staged it without
option 150 or a call control, and reported the missing stage as the device
disagreeing.

`tools/cp_scale_canonical_live.py` imports the PRODUCTION `packet_tracer_mcp`
namespace and `ImportIsolationPreflight` exists so the live process is the only
holder of it, so the tool is exercised in a child process and only its verdict
crosses back -- the same reason `test_cp_scale_live_failure_evidence` does.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    compose_cp_scale_canonical,
    project_cp_scale_canonical_stage,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import VoiceActionType
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def composition():
    composed = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
        capability_store=CapabilitySnapshotStore(ROOT / "data" / "capabilities"),
    )
    if not composed.valid:
        pytest.skip(
            "The canonical composition needs this environment's measured "
            "capability snapshot: " + "; ".join(composed.issues[:2])
        )
    return composed


def _stage(composition, stage: CPScaleCanonicalStage):
    return project_cp_scale_canonical_stage(composition, stage)


def test_the_canonical_composition_compiles_a_voice_plan(composition):
    assert composition.voice is not None
    assert len(composition.voice.phone_assignments) == 69


def test_a_stage_with_no_phone_carries_no_voice_plan(composition):
    for stage in (
        CPScaleCanonicalStage.ROUTING_CORE, CPScaleCanonicalStage.ROUTER4_SWITCH10,
    ):
        assert _stage(composition, stage).voice is None


def test_floor1_stages_voice_for_exactly_the_phones_it_deployed(composition):
    projection = _stage(composition, CPScaleCanonicalStage.FLOOR1)
    deployed = {
        item.id for item in projection.topology.devices
        if item.enterprise_role == DeviceRole.IP_PHONE.value
    }

    assert projection.voice is not None
    assert len(deployed) == 21
    assert {
        item.phone_id for item in projection.voice.phone_assignments
    } == deployed


def test_each_active_call_control_uses_its_final_designed_site_capacity(
    composition,
):
    full = {
        item.call_control_id: (item.max_phones, item.max_extensions)
        for item in composition.voice.actions_of_type(
            VoiceActionType.ENABLE_CALL_CONTROL,
        )
    }
    assert set(full.values()) == {(42, 42), (20, 20), (7, 7)}

    for stage in (
        CPScaleCanonicalStage.FLOOR1,
        CPScaleCanonicalStage.FLOOR2,
        CPScaleCanonicalStage.FLOOR3,
        CPScaleCanonicalStage.ROUTER0_BRANCH,
        CPScaleCanonicalStage.ROUTER3_BRANCH,
    ):
        projection = _stage(composition, stage)
        assert projection.voice is not None
        for action in projection.voice.actions_of_type(
            VoiceActionType.ENABLE_CALL_CONTROL,
        ):
            assert (action.max_phones, action.max_extensions) == full[
                action.call_control_id
            ]


def test_every_stage_voice_plan_binds_that_stage_and_not_the_full_scale(composition):
    """A plan carrying full-scale hashes is refused at apply, and rightly.

    E7 checks its source hashes against what it is applied against. Projecting
    the full plan onto a stage would fail that check instead of staging voice,
    so each stage compiles its own.
    """
    seen = set()
    for stage in CPScaleCanonicalStage:
        projection = _stage(composition, stage)
        if projection.voice is None:
            continue
        assert (
            projection.voice.source_topology_hash
            == projection.topology.physical_identity_hash
        )
        assert (
            projection.voice.source_configuration_hash
            == projection.configuration.semantic_hash
        )
        seen.add(projection.voice.semantic_hash)
    assert len(seen) > 1, "every stage produced the same plan"


def test_the_staged_plan_carries_the_actions_a_phone_acquires_through(composition):
    """Option 150, a call control to answer, and the files the phone fetches."""
    projection = _stage(composition, CPScaleCanonicalStage.FLOOR1)
    kinds = {item.action_type for item in projection.voice.actions}

    assert VoiceActionType.CONFIGURE_VOICE_DHCP_OPTION in kinds
    assert VoiceActionType.ENABLE_CALL_CONTROL in kinds
    assert VoiceActionType.GENERATE_PHONE_CONFIGURATION_FILES in kinds
    assert VoiceActionType.BIND_PHONE_TO_EXTENSION in kinds
    assert len(
        projection.voice.actions_of_type(VoiceActionType.BIND_PHONE_TO_EXTENSION)
    ) == 21


def test_option_150_points_at_the_call_control_that_answers(composition):
    projection = _stage(composition, CPScaleCanonicalStage.FLOOR1)
    options = projection.voice.actions_of_type(
        VoiceActionType.CONFIGURE_VOICE_DHCP_OPTION,
    )
    sources = projection.voice.actions_of_type(
        VoiceActionType.CONFIGURE_CALL_CONTROL_SOURCE,
    )

    assert options and sources
    assert {item.tftp_address for item in options} == {
        item.source_address for item in sources
    }
    # The documented CME address for the large branch is its voice gateway.
    assert {item.tftp_address for item in options} == {"172.16.20.1"}


_PROBE = '''
import json, sys
from types import SimpleNamespace

sys.path.insert(0, {root!r})
sys.path.insert(0, {src!r})

from tools.cp_scale_canonical_live import _stage_voice
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationRuntimeContext,
)
from packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    PhoneRegistrationResult,
)

verdict = {{}}


def _assignment(phone_id):
    return SimpleNamespace(phone_id=phone_id)


def _registration(phone_id, addressing, status, message=""):
    # Built from the real result model, not hand-mirrored: the stage reads
    # whatever fields the observation carries, and a namespace that has to be
    # kept in step with it breaks on every honest field the runtime learns to
    # report -- which is exactly what this stage keeps learning to do.
    return PhoneRegistrationResult(
        expectation_id="voice/verify/" + phone_id,
        phone_id=phone_id,
        extension="3001",
        addressing_status=addressing,
        addressing_message=message,
        status=status,
        message=message,
        call_control_ipv4="172.16.20.5",
        endpoint_ipv4="172.16.20.5",
        endpoint_interface="Vlan20",
        endpoint_interface_present=True,
        endpoint_address_channel=True,
        endpoint_dhcp_enabled=True,
        evidence_method="fresh_privileged_show_ephone",
    )


def _plan(actions=1):
    return SimpleNamespace(
        actions=[SimpleNamespace(id="voice/a")] * actions,
        phone_assignments=[_assignment("phone-1")],
    )


class _Applied:
    def __init__(self, registrations, refused=()):
        self.registrations = registrations
        self.mutation_action_ids = ["voice/a"]
        self.retained_action_ids = []
        self.action_results = [
            SimpleNamespace(
                action_id=item, status=ActionExecutionStatus.FAILED,
                message="refused",
            ) for item in refused
        ]
        self.preflight_errors = []

    def model_dump(self, mode="json"):
        return {{"status": "applied"}}


def _run(plan, result):
    import tools.cp_scale_canonical_live as live
    original = live.VoiceApplicator
    live.VoiceApplicator = lambda runtime: SimpleNamespace(
        apply=lambda *a, **k: result,
    )
    try:
        return _stage_voice(
            SimpleNamespace(
                voice=plan,
                stage=SimpleNamespace(value="floor1"),
                topology=SimpleNamespace(physical_identity_hash="t"),
                configuration=SimpleNamespace(semantic_hash="c"),
            ),
            voice_runtime=None,
            composition=SimpleNamespace(voice_capabilities={{}}),
            configuration=None,
            statuses={{}},
            context=ConfigurationRuntimeContext(),
            manifest=None,
        )
    finally:
        live.VoiceApplicator = original


# No phone in this stage: nothing applied, nothing claimed, no failure.
empty = _run(None, None)
verdict["no_phone_not_staged"] = empty["staged"] is False

# Two agreeing reads inside the voice segment: the stage stands.
good = _run(_plan(), _Applied([
    _registration("phone-1", ActionExecutionStatus.VERIFIED,
                  ActionExecutionStatus.VERIFIED),
]))
verdict["verified_has_no_error"] = good["error"] == ""
verdict["verified_records_address"] = good["addressed_phones"] == [
    "phone-1=172.16.20.5",
]

# An observed contradiction fails the stage.
bad = _run(_plan(), _Applied([
    _registration("phone-1", ActionExecutionStatus.FAILED,
                  ActionExecutionStatus.VERIFIED, "outside the voice segment"),
]))
verdict["contradiction_fails"] = bool(bad["error"])
verdict["contradiction_named"] = "outside the voice segment" in bad["error"]

# A registration this build cannot observe is bounded, not a contradiction.
bounded = _run(_plan(), _Applied([
    _registration("phone-1", ActionExecutionStatus.UNOBSERVABLE,
                  ActionExecutionStatus.UNOBSERVABLE),
]))
verdict["unobservable_is_not_failure"] = bounded["error"] == ""
verdict["unobservable_claims_nothing"] = bounded["addressed_phones"] == []

# A phone the call control reports UNREGISTERED contradicts a claim the plan
# made, and is not the same as never having looked.
unregistered = _run(_plan(), _Applied([
    _registration("phone-1", ActionExecutionStatus.UNOBSERVABLE,
                  ActionExecutionStatus.FAILED, "remained UNREGISTERED"),
]))
verdict["unregistered_fails"] = bool(unregistered["error"])

# Packet Tracer refusing an action stops the stage before anything is judged.
refused = _run(_plan(), _Applied([], refused=["voice/a"]))
verdict["refused_action_fails"] = "refused voice actions" in refused["error"]

print(json.dumps(verdict))
'''


@pytest.fixture(scope="module")
def gate() -> dict:
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE.format(root=str(ROOT), src=str(ROOT / "src"))],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_a_stage_without_phones_stages_no_voice_and_does_not_fail(gate):
    assert gate["no_phone_not_staged"]


def test_two_agreeing_reads_close_the_stage_and_record_the_address(gate):
    assert gate["verified_has_no_error"]
    assert gate["verified_records_address"]


def test_an_observed_contradiction_fails_the_stage(gate):
    assert gate["contradiction_fails"]
    assert gate["contradiction_named"]


def test_an_unobservable_registration_is_bounded_not_failed(gate):
    assert gate["unobservable_is_not_failure"]
    assert gate["unobservable_claims_nothing"]


def test_an_unregistered_phone_contradicts_the_plan(gate):
    assert gate["unregistered_fails"]


def test_a_refused_voice_action_stops_the_stage(gate):
    assert gate["refused_action_fails"]


def test_this_suite_never_loaded_the_production_namespace():
    assert "packet_tracer_mcp" not in sys.modules
