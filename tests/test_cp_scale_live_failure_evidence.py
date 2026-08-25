"""A failed CP-SCALE stage must keep the evidence it already gathered.

The Floor-1 run died with a 43-identifier failure string and nothing else. The
per-field read-backs that would have named the root cause existed at the moment
of the raise -- `_execute_stage` had already written the full typed
`ConfigurationApplicationResult` into its local journal three lines earlier --
but that dict escapes only through the success return, and the outer loop
appends it only after the call returns. The exception threw away the exact
evidence and kept the summary. Reconstructing what the run had already seen
cost a full offline investigation.

`tools/cp_scale_canonical_live.py` imports the PRODUCTION `packet_tracer_mcp`
namespace, and `ImportIsolationPreflight` exists precisely so that the live
process is the only one holding it. Importing the tool here would load that
namespace into the pytest process and make this suite look like a live one, so
the tool is exercised in a child process instead and only its verdict crosses
back.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

_PROBE = '''
import inspect, json, subprocess, sys
from dataclasses import replace
from types import SimpleNamespace

sys.path.insert(0, {root!r})
sys.path.insert(0, {src!r})

from tools.cp_scale_canonical_live import (
    CHECKPOINT_PATH,
    EVIDENCE_PATH,
    FINAL_CHECKPOINT_PATH,
    CanonicalLiveFailure,
    _execute_stage,
    _trunk_vlan_traversal_evidence,
    _write_checkpoint_summary,
)
import tools.cp_scale_canonical_live as live
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentStatus,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    DeviceIdentityEvidence,
    DeviceIdentityProvenance,
    IosCommandResult,
    IosSessionState,
    OperationalQueryId,
)

verdict = {{}}

verdict["runtime_checkpoint_sits_with_ignored_evidence"] = (
    CHECKPOINT_PATH.parent == EVIDENCE_PATH.parent
)
verdict["runtime_checkpoint_is_gitignored"] = subprocess.run(
    ["git", "check-ignore", "-q", str(CHECKPOINT_PATH)],
    cwd={root!r},
).returncode == 0
verdict["runtime_checkpoint_is_writer_default"] = (
    inspect.signature(_write_checkpoint_summary)
    .parameters["destination"].default == CHECKPOINT_PATH
)
verdict["final_checkpoint_is_tracked"] = subprocess.run(
    ["git", "ls-files", "--error-unmatch", str(FINAL_CHECKPOINT_PATH)],
    cwd={root!r},
    capture_output=True,
).returncode == 0

carried = CanonicalLiveFailure("boom", stage_evidence={{"stage": "floor1"}})
verdict["carries_evidence"] = carried.stage_evidence == {{"stage": "floor1"}}
verdict["message_intact"] = str(carried) == "boom"

bare = CanonicalLiveFailure("boom")
verdict["defaults_to_none"] = bare.stage_evidence is None
verdict["still_runtime_error"] = isinstance(bare, RuntimeError)

trunk_plan = SimpleNamespace(verification_expectations=[SimpleNamespace(
    id="verify-trunk",
    kind=VerificationKind.TRUNK,
    device_id="switch-4",
    device_name="Switch4",
    expected={{"interface": "GigabitEthernet0/2", "allowed_vlans": [10, 20, 30]}},
)])
trunk_result = SimpleNamespace(verification_results=[SimpleNamespace(
    expectation_id="verify-trunk",
    status=ActionExecutionStatus.VERIFIED,
    evidence_method="fresh_show_interfaces_trunk",
    fresh_evidence=True,
    fields={{
        "interface": FieldVerificationStatus.VERIFIED,
        "status": FieldVerificationStatus.VERIFIED,
        "allowed_vlans": FieldVerificationStatus.VERIFIED,
        "active_vlans": FieldVerificationStatus.VERIFIED,
        "forwarding_vlans": FieldVerificationStatus.VERIFIED,
    }},
    message="",
)], model_dump=lambda mode="json": {{"status": "failed"}})
verdict["trunk_vlan_traversal"] = _trunk_vlan_traversal_evidence(
    trunk_plan, trunk_result,
)

binding_output = """Router4#show ip dhcp binding
IP address      Client-ID/              Lease expiration        Type
172.16.10.2     0001.1111.1111          --                      Automatic
172.16.30.22    0002.2222.2222          --                      Automatic
Router4#"""
binding_helper = getattr(live, "_dhcp_server_binding_evidence", None)
if binding_helper is not None:
    class BindingIos:
        def __init__(self, output=binding_output):
            self.calls = []
            self.output = output

        def execute(self, device_name, query_id):
            self.calls.append((device_name, query_id.value))
            return IosCommandResult(
                device_name=device_name,
                query_id=query_id,
                executed=True,
                output=self.output,
                session_state=IosSessionState.EXEC_PROMPT_READY,
                fresh_output_observed=True,
                output_complete=True,
                observed_device_name=device_name,
                device_identity_provenance=(
                    DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
                ),
                device_identity_evidence=(
                    DeviceIdentityEvidence.TERMINAL_OBJECT_IDENTITY.value
                ),
            )

    binding_ios = BindingIos()
    binding_plan = SimpleNamespace(actions=[
        SimpleNamespace(
            action_type=ConfigurationActionType.CONFIGURE_DHCP_POOL,
            device_name="Router4",
            segment_id="large-data",
            network="172.16.10.0",
            prefix=24,
        ),
        SimpleNamespace(
            action_type=ConfigurationActionType.CONFIGURE_DHCP_POOL,
            device_name="Router4",
            segment_id="large-voice",
            network="172.16.20.0",
            prefix=24,
        ),
    ])
    binding_voice = SimpleNamespace(phone_assignments=[SimpleNamespace(
        voice_segment_id="large-voice",
    )])
    verdict["dhcp_binding_evidence"] = binding_helper(
        binding_ios, binding_plan, binding_voice,
    )
    verdict["dhcp_binding_calls"] = binding_ios.calls
    verdict["dhcp_binding_without_rows"] = binding_helper(
        BindingIos("Router4#show ip dhcp binding\\nRouter4#"),
        binding_plan,
        binding_voice,
    )
    wrong_identity = BindingIos()
    original_execute = wrong_identity.execute
    def mismatched_execute(device_name, query_id):
        return replace(
            original_execute(device_name, query_id),
            observed_device_name="AnotherRouter",
            device_identity_provenance=(
                DeviceIdentityProvenance.MISMATCHED.value
            ),
        )
    wrong_identity.execute = mismatched_execute
    verdict["dhcp_binding_wrong_identity"] = binding_helper(
        wrong_identity, binding_plan, binding_voice,
    )
else:
    verdict["dhcp_binding_evidence"] = None
    verdict["dhcp_binding_calls"] = []
    verdict["dhcp_binding_without_rows"] = None
    verdict["dhcp_binding_wrong_identity"] = None

projection = SimpleNamespace(
    stage=SimpleNamespace(value="floor1"),
    topology=SimpleNamespace(
        physical_identity_hash="topology-hash", devices=[1, 2, 3], modules=[], links=[1, 2],
    ),
    configuration=SimpleNamespace(semantic_hash="config-hash", actions=[1]),
    control_plane=SimpleNamespace(
        semantic_hash="control-hash", actions=[], verification_expectations=[],
    ),
    voice=None,
)
deployment = SimpleNamespace(
    status=PhysicalDeploymentStatus.FAILED,
    manifest=None,
    errors=["exact physical binding was refused"],
    model_dump=lambda mode="json": {{"status": "failed"}},
)

try:
    _execute_stage(
        projection,
        composition=SimpleNamespace(capabilities={{}}),
        deployment=deployment,
        delta_deployment=None,
        physical=None,
        configuration_runtime=None,
        control_runtime=None,
        voice_runtime=None,
        transport=None,
        fingerprint=None,
        packet_tracer_version="9.0.1.0858",
    )
except CanonicalLiveFailure as exc:
    evidence = exc.stage_evidence
    verdict["raised_with_journal"] = evidence is not None
    verdict["stage"] = (evidence or {{}}).get("stage")
    verdict["configuration_hash"] = (
        (evidence or {{}}).get("plan", {{}}).get("configuration_hash")
    )
    verdict["physical"] = (evidence or {{}}).get("physical")
else:
    verdict["raised_with_journal"] = False

# A typed configuration contradiction happens after the full application
# result exists. Its human-readable trunk projection must escape with the same
# failed-stage journal, not be deferred until the success-only return path.
projection.configuration.verification_expectations = (
    trunk_plan.verification_expectations
)
verified_deployment = SimpleNamespace(
    status=PhysicalDeploymentStatus.VERIFIED,
    manifest=SimpleNamespace(),
    errors=[],
    model_dump=lambda mode="json": {{"status": "verified"}},
)
live.ConfigurationApplicator = lambda _runtime: SimpleNamespace(
    apply=lambda *args, **kwargs: trunk_result,
)
live.configuration_application_contradiction = lambda _result: "typed mismatch"
live.inherit_verified_serial_orientation = lambda *args, **kwargs: SimpleNamespace(
    verified=True,
    oriented_manifest=verified_deployment.manifest,
    errors=[],
    model_dump=lambda mode="json": {{"verified": True}},
)
try:
    _execute_stage(
        projection,
        composition=SimpleNamespace(capabilities={{}}),
        deployment=verified_deployment,
        delta_deployment=None,
        physical=None,
        configuration_runtime=None,
        control_runtime=None,
        voice_runtime=None,
        transport=None,
        fingerprint=None,
        packet_tracer_version="9.0.1.0858",
        verified_serial_topology=SimpleNamespace(),
        verified_serial_manifest=SimpleNamespace(),
    )
except CanonicalLiveFailure as exc:
    contradiction_evidence = exc.stage_evidence or {{}}
    verdict["contradicted_stage_trunk"] = contradiction_evidence.get(
        "trunk_vlan_traversal"
    )
else:
    verdict["contradicted_stage_trunk"] = None

# A voice contradiction is precisely when server bindings are diagnostic. The
# additive observation must therefore be journalled before that contradiction
# escapes, not on the stage's success-only tail.
live.configuration_application_contradiction = lambda _result: ""
live.canonical_stage_configuration_error = lambda *args, **kwargs: ""
live._wait_for_serial_interfaces = lambda *args, **kwargs: (True, [])
live.derive_foundational_statuses = lambda *args, **kwargs: {{}}
live._stage_voice = lambda *args, **kwargs: {{
    "staged": True, "error": "voice mismatch",
}}
live._dhcp_server_binding_evidence = lambda *args, **kwargs: [{{
    "sentinel": "binding evidence retained",
}}]
projection.voice = SimpleNamespace(actions=[], phone_assignments=[])
try:
    _execute_stage(
        projection,
        composition=SimpleNamespace(capabilities={{}}),
        deployment=verified_deployment,
        delta_deployment=None,
        physical=None,
        configuration_runtime=None,
        control_runtime=None,
        voice_runtime=None,
        transport=SimpleNamespace(send_and_wait=lambda *args, **kwargs: None),
        fingerprint=None,
        packet_tracer_version="9.0.1.0858",
        verified_serial_topology=SimpleNamespace(),
        verified_serial_manifest=SimpleNamespace(),
    )
except CanonicalLiveFailure as exc:
    voice_failure_evidence = exc.stage_evidence or {{}}
    verdict["bindings_before_voice_failure"] = voice_failure_evidence.get(
        "dhcp_server_bindings"
    )
else:
    verdict["bindings_before_voice_failure"] = None

print(json.dumps(verdict))
'''


@pytest.fixture(scope="module")
def verdict() -> dict:
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE.format(root=str(ROOT), src=str(ROOT / "src"))],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_canonical_live_failure_carries_the_stage_evidence_it_had(verdict):
    assert verdict["carries_evidence"]
    assert verdict["message_intact"]


def test_runtime_checkpoint_summary_cannot_dirty_the_governed_worktree(verdict):
    assert verdict["runtime_checkpoint_sits_with_ignored_evidence"]
    assert verdict["runtime_checkpoint_is_gitignored"]
    assert verdict["runtime_checkpoint_is_writer_default"]


def test_terminal_reference_checkpoint_remains_a_tracked_artifact(verdict):
    assert verdict["final_checkpoint_is_tracked"]


def test_canonical_live_failure_without_evidence_still_behaves_as_before(verdict):
    assert verdict["defaults_to_none"]
    assert verdict["still_runtime_error"]


def test_a_failed_stage_raises_with_the_journal_it_had_already_written(verdict):
    assert verdict["raised_with_journal"], "the stage journal was thrown away again"
    assert verdict["stage"] == "floor1"
    assert verdict["configuration_hash"] == "config-hash"
    assert verdict["physical"] == {"status": "failed"}


def test_governed_evidence_names_each_typed_trunk_vlan_traversal(verdict):
    assert verdict["trunk_vlan_traversal"] == [{
        "expectation_id": "verify-trunk",
        "device_id": "switch-4",
        "device_name": "Switch4",
        "interface": "GigabitEthernet0/2",
        "expected_vlans": [10, 20, 30],
        "status": "verified",
        "evidence_method": "fresh_show_interfaces_trunk",
        "fresh_evidence": True,
        "fields": {
            "active_vlans": "verified",
            "allowed_vlans": "verified",
            "forwarding_vlans": "verified",
            "interface": "verified",
            "status": "verified",
        },
        "message": "",
    }]


def test_configuration_contradiction_keeps_named_trunk_evidence(verdict):
    assert verdict["contradicted_stage_trunk"] == verdict["trunk_vlan_traversal"]


def test_governed_binding_evidence_keeps_zero_distinct_from_unreadable(verdict):
    evidence = verdict["dhcp_binding_evidence"]
    assert evidence is not None
    assert verdict["dhcp_binding_calls"] == [["Router4", "show_ip_dhcp_binding"]]
    assert evidence[0]["table_readable"] is True
    assert evidence[0]["bindings"] == ["172.16.10.2", "172.16.30.22"]
    assert evidence[0]["pools"] == [
        {
            "segment_id": "large-data",
            "network": "172.16.10.0/24",
            "voice": False,
            "binding_count": 1,
            "bindings": ["172.16.10.2"],
        },
        {
            "segment_id": "large-voice",
            "network": "172.16.20.0/24",
            "voice": True,
            "binding_count": 0,
            "bindings": [],
        },
    ]

    unreadable = verdict["dhcp_binding_without_rows"][0]
    assert unreadable["table_readable"] is False
    assert all(item["binding_count"] is None for item in unreadable["pools"])
    assert all(item["bindings"] == [] for item in unreadable["pools"])

    wrong_identity = verdict["dhcp_binding_wrong_identity"][0]
    assert wrong_identity["device_identity_confirmed"] is False
    assert wrong_identity["table_readable"] is False
    assert all(item["binding_count"] is None for item in wrong_identity["pools"])


def test_voice_failure_keeps_the_additive_server_binding_observation(verdict):
    assert verdict["bindings_before_voice_failure"] == [
        {"sentinel": "binding evidence retained"},
    ]


def test_this_suite_never_loaded_the_production_namespace():
    """The isolation invariant this file must not be the one to break."""
    assert "packet_tracer_mcp" not in sys.modules
